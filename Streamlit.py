import streamlit as st
import trimesh
import math
import numpy as np
import os
import tempfile
from streamlit_stl import stl_from_file
from Slicer import OpenSlicer
from DXFExporter import DXFExporter


st.set_page_config(page_title="OpenSlicer Web", layout="wide")

# --- UI STYLING & ZERO-BORDER CANVAS ---
st.markdown("""
    <style>
    /* 1. Eliminate all default Streamlit page padding and margins */
    .block-container {
        padding-top: 0rem !important;
        padding-bottom: 0rem !important;
        padding-left: 0rem !important;
        padding-right: 0rem !important;
        max-width: 100% !important;
    }
    
    /* 2. Remove padding around the main content layout area */
    [data-testid="stMain"] {
        padding: 0rem !important;
    }
    
    /* 3. Align Sidebar cleanly to the edge */
    [data-testid="stSidebarUserContent"] {
        padding-top: 1.5rem !important;
    }
    
    /* 4. Pure White Watermark Title (No background) */
    .watermark-title {
        position: absolute;
        top: 25px;
        left: 25px;
        z-index: 999;
        background: transparent !important; /* Sin fondo */
        padding: 0px !important;            /* Sin espaciado interno */
        border: none !important;            /* Sin bordes */
        box-shadow: none !important;        /* Sin sombras de contenedor */
        pointer-events: none;               /* Permite rotar el modelo haciendo click a través del texto */
    }
    
    .watermark-title h1 {
        margin: 0 !important;
        font-size: 2.2rem !important;       /* Un poco más grande para destacar en blanco */
        color: #ffffff !important;          /* Texto blanco puro */
        font-family: 'Inter', sans-serif;
        letter-spacing: -0.5px;
        opacity: 0.8;                       /* Opacidad sutil de marca de agua */
        text-shadow: 1px 1px 4px rgba(0,0,0,0.4); /* Sombra de texto suave para que no se pierda si el fondo es claro */
    }
    
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; }
    </style>
    """, unsafe_allow_html=True)

# --- INITIALIZE SESSION STATE ------------------------------
def reset_slicer_data():
    if "slicer" in st.session_state:
        st.session_state.slicer.slices_2d = []
        st.session_state.slicer.slice_transforms = []
    if "exporter" in st.session_state:
        st.session_state.exporter.layouts = []  
    if "render_counter" in st.session_state:
        st.session_state.render_counter += 1
    if "view_mode" in st.session_state:
        st.session_state.view_mode = "3D"

if 'slicer' not in st.session_state:
    st.session_state.slicer = OpenSlicer(material_thickness=2.0)
    st.session_state.exporter  = DXFExporter(st.session_state.slicer)
if 'file_name' not in st.session_state:
    st.session_state.file_name = None
if 'render_counter' not in st.session_state:
    st.session_state.render_counter = 0
if 'dims' not in st.session_state:
    st.session_state.dims = {"X": 0.0, "Y": 0.0, "Z": 0.0}
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = "3D"

# --- SIDEBAR CONTROLS --------------------------------------
with st.sidebar:
    st.header("Controls")
    
# 1. IMPORT
    uploaded_file = st.file_uploader("Import STL File", type=['stl'])
    
    if uploaded_file:
        if st.session_state.file_name != uploaded_file.name:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".stl") as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name
            
            st.session_state.slicer.load_model(tmp_path)
            os.unlink(tmp_path) # Limpieza segura inmediata del archivo temporal
            
            # VALIDACIÓN DE SEGURIDAD: Validar que el objeto mesh exista antes de leer vértices
            if st.session_state.slicer.mesh is not None:
                st.session_state.file_name = uploaded_file.name
                
                vertices = st.session_state.slicer.mesh.vertices
                st.session_state.dims = {
                    "X": float(vertices[:, 0].max() - vertices[:, 0].min()),
                    "Y": float(vertices[:, 1].max() - vertices[:, 1].min()),
                    "Z": float(vertices[:, 2].max() - vertices[:, 2].min())
                }
                
                st.success(f"Loaded: {uploaded_file.name}")
                st.session_state.render_counter += 1
                st.rerun()
            else:
                st.error("The STL file could not be parsed into a valid 3D Mesh. Please verify the file integrity.")

    # 2. CONTROL DE ESCALA E INFORMACIÓN DEL MODELO
    if st.session_state.file_name:
        with st.container(border=True):
            st.markdown("**Model Properties**")
            
            is_watertight = "Yes" if st.session_state.slicer.mesh.is_watertight else "No"
            st.markdown(
                f"<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: -5px;'>"
                f"<span style='color: #666; font-size: 0.85rem;'>Watertight</span>"
                f"<span style='font-weight: bold; font-size: 1rem;'>{is_watertight}</span>"
                f"</div>", 
                unsafe_allow_html=True
            )
            
            st.markdown("<hr style='margin-top: 5px; margin-bottom: 5px; border: 0; border-top: 1px solid #ddd;'>", unsafe_allow_html=True)
            
            # --- CORRECCIÓN SELECTOR DE UNIDADES ---
            # Forzamos opciones en minúsculas y agregamos la función rerun para actualizar al cambiar
            unit_system = st.selectbox(
                "Dimensions Unit",
                options=["mm", "inch"],
                index=0,
                key="unit_selector",
                label_visibility="collapsed",
                on_change=st.rerun
            )
            
            conversion_factor = 1.0 if unit_system == "mm" else (1.0 / 25.4)
            unit_label = "mm" if unit_system == "mm" else "in"
            
            st.markdown(
                f"<div style='color: #666; font-size: 0.85rem; margin-top: 5px; margin-bottom: 2px;'>Dimensions ({unit_label})</div>", 
                unsafe_allow_html=True
            )
            
            col_x, col_y, col_z = st.columns(3)
            with col_x:
                val_x = st.session_state.dims['X'] * conversion_factor
                st.markdown(f"<small style='color: #888;'>X</small><br>**{val_x:.2f}**", unsafe_allow_html=True)
            with col_y:
                val_y = st.session_state.dims['Y'] * conversion_factor
                st.markdown(f"<small style='color: #888;'>Y</small><br>**{val_y:.2f}**", unsafe_allow_html=True)
            with col_z:
                val_z = st.session_state.dims['Z'] * conversion_factor
                st.markdown(f"<small style='color: #888;'>Z</small><br>**{val_z:.2f}**", unsafe_allow_html=True)

        with st.form("scale_form"):
            scale_factor = st.number_input("Scale Factor", min_value=0.1, max_value=10.0, value=1.0, step=0.1)
            submit_scale = st.form_submit_button("Apply Scale")
            
            if submit_scale:
                st.session_state.slicer.scale_model(scale_factor)
                vertices = st.session_state.slicer.mesh.vertices
                st.session_state.dims = {
                    "X": float(vertices[:, 0].max() - vertices[:, 0].min()),
                    "Y": float(vertices[:, 1].max() - vertices[:, 1].min()),
                    "Z": float(vertices[:, 2].max() - vertices[:, 2].min())
                }
                st.session_state.render_counter += 1
                st.toast(f"Model scaled to {scale_factor}x")
                st.rerun()
    else:
        st.info("Upload an STL file to see its properties.")

    st.divider()

    # --- LÓGICA DE ACTUALIZACIÓN DE HOJA PARA NESTING ---
    current_unit = st.session_state.get("unit_selector", "mm")

    # Inicializar las variables internas la primera vez
    if "prev_unit" not in st.session_state:
        st.session_state.prev_unit = current_unit
        st.session_state.width_val = 600.0
        st.session_state.height_val = 400.0

    # Si detectamos un cambio real de unidad, hacemos la conversión matemática exacta
    if current_unit != st.session_state.prev_unit:
        if current_unit == "inch":
            st.session_state.width_val = round(st.session_state.width_val / 25.4, 2)
            st.session_state.height_val = round(st.session_state.height_val / 25.4, 2)
        else:
            st.session_state.width_val = round(st.session_state.width_val * 25.4, 1)
            st.session_state.height_val = round(st.session_state.height_val * 25.4, 1)
        st.session_state.prev_unit = current_unit

    # Configuración de límites y textos según el estado actual
    if current_unit == "inch":
        min_sheet_val = 1.0
        step_sheet_val = 0.5
        label_suffix = "(inch)"
    else:
        min_sheet_val = 10.0
        step_sheet_val = 10.0
        label_suffix = "(mm)"

    # Renderizado en pantalla de los inputs vinculados al session_state
    st.subheader("Sheet Size for Nesting")
    col_w, col_h = st.columns(2)
    
    with col_w:
        paper_width = st.number_input(
            f"Sheet Width {label_suffix}", 
            min_value=min_sheet_val, 
            value=st.session_state.width_val, 
            step=step_sheet_val,
            key=f"sheet_width_{current_unit}"  # Key dinámica para forzar refresco limpio en la UI
        )
    with col_h:
        paper_height = st.number_input(
            f"Sheet Height {label_suffix}", 
            min_value=min_sheet_val, 
            value=st.session_state.height_val, 
            step=step_sheet_val,
            key=f"sheet_height_{current_unit}" # Key dinámica para forzar refresco limpio en la UI
        )
    
    # Guardamos cualquier modificación manual del usuario para no perder el dato
    st.session_state.width_val = paper_width
    st.session_state.height_val = paper_height

    # Normalización: Las variables finales quedan convertidas siempre a milímetros (mm) para el motor DXF
    if current_unit == "inch":
        paper_width *= 25.4
        paper_height *= 25.4
    
    st.divider()


    # 3. PARÁMETROS DE CORTE (FORMULARIOS DEDICADOS PARA LAS 4 TÉCNICAS)
    st.subheader("Slicing Settings")
    
    # El selector vive afuera para cambiar el contexto de la UI dinámicamente
    # Actualizado con las 4 técnicas estándar de fabricación digital
    slice_method = st.selectbox(
        "Slicing Method",
        options=["Interlocking Grid", "Radial Interlocking", "Flat / Stacked", "Contour Slicing"],
        index=0,
        on_change=reset_slicer_data
    )
    
    # --- CASO A: FORMULARIO PARA INTERLOCKING GRID (MATRIZ X/Y) ---
    if slice_method == "Flat / Stacked":
        with st.form("form_flat_stacked"):
            thick = st.number_input("Material Thickness (mm)", min_value=0.1, max_value=50.0, value=3.0, step=0.5)
            
            st.markdown("<small style='color: #666;'>Slice Plane Rotation (Degrees)</small>", unsafe_allow_html=True)
            angle_x = st.slider("Rotate X", min_value=0, max_value=360, value=0, step=5)
            angle_y = st.slider("Rotate Y", min_value=0, max_value=360, value=0, step=5)
            angle_z = st.slider("Rotate Z", min_value=0, max_value=360, value=0, step=5)
            
            submit_flat = st.form_submit_button("Generate Flat Slices")
            
            if submit_flat:
                st.session_state.slicer.material_thickness = thick
                with st.spinner("Processing Flat Geometry..."):
                    st.session_state.slicer.slice_flat(angle_x=angle_x, angle_y=angle_y, angle_z=angle_z)
                    st.session_state.exporter.arrange_grid_nesting(paper_width, paper_height)
                st.success("Flat Slicing Complete!")
                st.rerun()

    # --- CASO B: FORMULARIO PARA RADIAL INTERLOCKING (DIVISIONES ANGULARES) ---
    elif slice_method == "Radial Interlocking":
        with st.form("form_radial"):
            thick = st.number_input("Material Thickness (mm)", min_value=0.1, max_value=50.0, value=3.0, step=0.5)
            # Parámetros angulares típicos para radiales
            radial_count = st.number_input("Number of Radial Slices", min_value=3, value=12, step=1)
            layer_count = st.number_input("Number of Vertical Layers", min_value=2, value=10, step=1)
            
            submit_radial = st.form_submit_button("Generate Radial Slices")
            
            if submit_radial:
                st.session_state.slicer.material_thickness = thick
                with st.spinner("Processing Radial Geometry..."):
                    # Llamada a tu método radial dedicado (Asegúrate de que exista en Slicer.py)
                    st.session_state.slicer.slice_radial(rad_cuts=radial_count, vert_cuts=layer_count)
                    st.session_state.exporter.arrange_grid_nesting(paper_width, paper_height)
                st.success("Radial Slicing Complete!")
                st.rerun()

    # --- CASO C: FORMULARIO PARA FLAT / STACKED (CAPAS PARALELAS ORIENTABLES) ---
    elif slice_method == "Interlocking Grid":
        with st.form("form_interlocking_grid"):
            thick = st.number_input("Material Thickness (mm)", min_value=0.1, max_value=50.0, value=3.0, step=0.5)
            spacing_x = st.number_input("X-Axis Spacing (mm)", min_value=5.0, value=20.0)
            spacing_y = st.number_input("Y-Axis Spacing (mm)", min_value=5.0, value=20.0)
            
            submit_grid = st.form_submit_button("Generate Grid Slices")
            
            if submit_grid:
                st.session_state.slicer.material_thickness = thick
                with st.spinner("Processing Interlocking Grid..."):
                    # Tu backend debe aceptar espaciado X/Y diferenciado
                    st.session_state.slicer.slice_interlocking(spacing_x, spacing_y)
                    st.session_state.exporter.arrange_grid_nesting(paper_width, paper_height)
                st.success("Grid Slicing Complete!")
                st.rerun()

    # --- CASO D: FORMULARIO PARA CONTOUR SLICING (TOPOGRÁFICO/CURVO) ---
    elif slice_method == "Contour Slicing":
        with st.form("form_contour"):
            st.markdown("**Circular Slicing Parameters**")
            thick       = st.number_input("Circle Thickness (mm)", min_value=0.1, max_value=50.0, value=3.0, step=0.5)
            num_circles = st.number_input("Number of Circles", min_value=1, max_value=100, value=5, step=1)
            
            st.markdown('<small style="color:666">Center Location Coordinates</small>', unsafe_allow_html=True)
            col_cx, col_cy, col_cz = st.columns(3)        # ← añadir col_cz
            with col_cx:
                cx = st.number_input("Center X (mm)", value=0.0, step=10.0)
            with col_cy:
                cy = st.number_input("Center Y (mm)", value=0.0, step=10.0)
            with col_cz:                                   # ← nuevo
                cz = st.number_input("Center Z (mm)", value=0.0, step=10.0)

            submit_contour = st.form_submit_button("Generate Circular Slices")
            if submit_contour:
                st.session_state.slicer.material_thickness = thick
                with st.spinner("Processing Concentric Circular Geometry..."):
                    st.session_state.slicer.slice_contour(
                        center_x=cx,
                        center_y=cy,
                        center_z=cz,               # ← nuevo
                        num_circles=num_circles,
                        ring_thickness=thick       # ← corregido
                    )
                st.session_state.exporter.arrange_grid_nesting(paper_width, paper_height)
                st.success("Concentric Slicing Complete!")
                st.rerun()

    st.divider()

    # 4. EXPORTACIÓN DE RESULTADOS
    if st.session_state.exporter.layouts:
        st.subheader("Preview & Download")

        # --- BOTÓN DE VISUALIZACIÓN DXF (Efecto Presionado) ---
        is_dxf_view = (st.session_state.view_mode == "DXF")
        btn_label = "Viewing DXF (Click to return to 3D)" if is_dxf_view else "View 2D DXF Layouts"
        
        if st.button(btn_label, type="secondary", use_container_width=True):
            st.session_state.view_mode = "DXF" if not is_dxf_view else "3D"
            st.rerun()
            
        st.divider()

        num_sheets = len(st.session_state.exporter.layouts)

        # FIX 3: inform the user how many sheets were generated.
        if num_sheets == 1:
            st.caption("1 sheet generated.")
        else:
            st.caption(f"{num_sheets} sheets generated.")

        # Offer a download button for every sheet.
        for sheet_idx, layout in enumerate(st.session_state.exporter.layouts, start=1):
            dxf_data = layout.export(file_type='dxf')
            st.download_button(
                label=f"Export DXF — Sheet {sheet_idx}",
                data=dxf_data,
                file_name=f"OpenSlicer_Sheet_{sheet_idx}.dxf",
                mime="application/dxf",
                key=f"dxf_download_{sheet_idx}",   # unique key required by Streamlit
            )

# --- MAIN VIEWPORT ---
if st.session_state.slicer.mesh:
    st.markdown('<div class="watermark-title"><h1>OpenSlicer</h1></div>', unsafe_allow_html=True)
    
    # DECISIÓN DE RENDER: ¿DXF 2D o Visualización 3D?
    if st.session_state.exporter.layouts and st.session_state.view_mode == "DXF":
        import plotly.graph_objects as go
        
        st.markdown("<h3 style='text-align: center; color: #555; padding-top: 20px;'>DXF Nesting Layout Preview</h3>", unsafe_allow_html=True)
        
        for sheet_idx, layout in enumerate(st.session_state.exporter.layouts, start=1):
            dxf_bytes = layout.export(file_type='dxf')
            path = trimesh.load_path(trimesh.util.wrap_as_stream(dxf_bytes), file_type='dxf')
            
            # Agrupar todos los segmentos separados por 'None' (optimización para Plotly)
            all_x = []
            all_y = []
            for entity in path.entities:
                discrete = entity.discrete(path.vertices)
                all_x.extend(discrete[:, 0].tolist() + [None])
                all_y.extend(discrete[:, 1].tolist() + [None])
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=all_x, 
                y=all_y, 
                mode='lines', 
                line=dict(color='#1f77b4', width=1.5),
                hoverinfo='skip', 
                showlegend=False
            ))
            
            # Forzar escala 1:1, fondo blanco y quitar grillas
            fig.update_layout(
                yaxis=dict(scaleanchor="x", scaleratio=1, showgrid=False, zeroline=False, visible=False),
                xaxis=dict(showgrid=False, zeroline=False, visible=False),
                plot_bgcolor='white',
                paper_bgcolor='white',
                margin=dict(l=10, r=10, t=40, b=10),
                title=dict(text=f"Sheet {sheet_idx}", x=0.5, font=dict(size=16)),
                dragmode='pan'
            )
            
            st.plotly_chart(fig, use_container_width=True)

    else:
        # VISUALIZADOR 3D ESTÁNDAR (¡Todo este bloque va indentado dentro del else!)
        if st.session_state.exporter.layouts:
            with st.spinner("Generating 3D Preview..."):
                display_mesh = st.session_state.slicer.get_visual_prediction()
                display_color = '#e67e22'  # Color naranja/madera para el resultado final
        else:
            display_mesh = st.session_state.slicer.mesh
            display_color = '#1f77b4'  # Azul para el modelo original

        tmp_preview_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".stl") as tmp_preview:
                display_mesh.export(tmp_preview.name, file_type='stl')
                tmp_preview_path = tmp_preview.name

            stl_from_file(
                file_path=tmp_preview_path,
                color=display_color,
                auto_rotate=False,
                height=900,
                key=f"stl_viewer_{st.session_state.render_counter}"
            )
        finally:
            if tmp_preview_path and os.path.exists(tmp_preview_path):
                os.unlink(tmp_preview_path)