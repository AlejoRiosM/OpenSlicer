import trimesh
import numpy as np
import math
import rectpack  # Importación para el empaquetado

class OpenSlicer:

    def __init__(self, material_thickness=2.0):
        self.material_thickness = material_thickness
        self.mesh = None
        self.slices_2d = []
        self.slice_transforms = []

    def load_model(self, file_path):
        print(f"Loading model from {file_path}...")
        geometry = trimesh.load(file_path)
        
        # Si trimesh lo detecta como escena, lo unifica en una sola malla
        if isinstance(geometry, trimesh.Scene):
            if len(geometry.geometry) > 0:
                self.mesh = trimesh.util.concatenate(list(geometry.geometry.values()))
            else:
                self.mesh = None
        else:
            self.mesh = geometry
        
    def scale_model(self, scale_factor):
        """
        Escala la malla 3D en su lugar usando un factor multiplicador.
        """
        if self.mesh is not None:
            self.mesh.apply_scale(scale_factor)
            print(f"[DEBUG] Modelo escalado con éxito por: {scale_factor}x")
        else:
            print("[DEBUG] Advertencia: Intentando escalar una malla inexistente (None).")

    def add_notches(self, slice_2d, notch_depth=10.0):
        """
        Añade muescas de ensamble a los bordes de la pieza.
        Utiliza operaciones booleanas de shapely para restar rectángulos de muesca.
        """
        from shapely.geometry import box
        
        # Obtenemos los polígonos de la pieza
        polys = slice_2d.polygons_full
        new_polys = []
        
        for poly in polys:
            # Creamos una muesca: un rectángulo con el ancho del material
            # Aquí centramos la muesca en el borde superior del polígono como ejemplo
            minx, miny, maxx, maxy = poly.bounds
            
            # Definir la geometría de la muesca (rectángulo)
            # Anchura = espesor del material, Altura = profundidad de muesca
            notch_width = self.material_thickness
            notch = box(
                (minx + maxx)/2 - notch_width/2, 
                maxy - notch_depth, 
                (minx + maxx)/2 + notch_width/2, 
                maxy
            )
            
            # Operación booleana de resta
            new_poly = poly.difference(notch)
            new_polys.append(new_poly)
            
        # Reconstruir el Path2D con las nuevas geometrías
        # Nota: trimesh.path.path.Path2D permite reconstruir desde shapely
        from trimesh.path.creation import path_2d
        return path_2d(new_polys)

    # --- MÉTODOS DE REBANADO (SLICING) ---
    def _clear_previous_results(self):
        """Limpia los contenedores de datos antes de un nuevo cálculo."""
        self.slices_2d = []
        self.slice_transforms = []

    def slice_interlocking(self, spacing_x=20.0, spacing_y=20.0):
        """
        Genera una cuadrícula ortogonal (Grilla) de costillas estructurales en X e Y,
        calculando matemáticamente las ranuras (notches) de interconexión real en 3D
        y aplicándolas a los perfiles 2D mediante Shapely.
        """
        self._clear_previous_results()
        print(f"\n--- [DEBUG] INICIANDO INTERLOCKING CON RANURAS REALES (X: {spacing_x}mm, Y: {spacing_y}mm) ---")
        
        import numpy as np
        import trimesh
        from shapely.geometry import Polygon as ShapelyPolygon, LineString
        from shapely.ops import unary_union
        
        bounds = self.mesh.bounds
        
        # 1. Definir los planos de corte numéricamente
        x_levels = np.arange(bounds[0][0] + spacing_x, bounds[1][0], spacing_x)
        y_levels = np.arange(bounds[0][1] + spacing_y, bounds[1][1], spacing_y)
        
        x_slices = []
        y_slices = []

        # --- FASE 1: Extracción limpia de perfiles sólidos primarios ---
        for x in x_levels:
            slice_3d = self.mesh.section(plane_origin=[x, 0, 0], plane_normal=[1, 0, 0])
            if slice_3d is not None:
                slice_2d, to_3d = slice_3d.to_planar()
                if len(slice_2d.polygons_full) > 0:
                    x_slices.append({'slice_3d': slice_3d, 'slice_2d': slice_2d, 'transform': to_3d, 'coord': x, 'type': 'X'})

        for y in y_levels:
            slice_3d = self.mesh.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
            if slice_3d is not None:
                slice_2d, to_3d = slice_3d.to_planar()
                if len(slice_2d.polygons_full) > 0:
                    y_slices.append({'slice_3d': slice_3d, 'slice_2d': slice_2d, 'transform': to_3d, 'coord': y, 'type': 'Y'})

        # --- FASE 2: Conversión a Shapely y Sanamiento Topológico Inicial ---
        x_slices_polys = []
        for item in x_slices:
            polys = []
            for p in item['slice_2d'].polygons_full:
                p_valid = p.buffer(0)
                if p_valid.geom_type == 'Polygon': polys.append(p_valid)
                elif p_valid.geom_type == 'MultiPolygon': polys.extend(p_valid.geoms)
            x_slices_polys.append(polys)

        y_slices_polys = []
        for item in y_slices:
            polys = []
            for p in item['slice_2d'].polygons_full:
                p_valid = p.buffer(0)
                if p_valid.geom_type == 'Polygon': polys.append(p_valid)
                elif p_valid.geom_type == 'MultiPolygon': polys.extend(p_valid.geoms)
            y_slices_polys.append(polys)

        t = self.material_thickness

        # --- FASE 3: Calado de muescas por Proyección de Intersecciones ---
        for i, x_item in enumerate(x_slices):
            for j, y_item in enumerate(y_slices):
                int_x = x_item['coord']
                int_y = y_item['coord']
                
                vertices_x = x_item['slice_3d'].vertices
                if len(vertices_x) == 0: continue
                z_min_global = np.min(vertices_x[:, 2]) - 10.0
                z_max_global = np.max(vertices_x[:, 2]) + 10.0
                
                p3d_low = np.array([int_x, int_y, z_min_global, 1])
                p3d_high = np.array([int_x, int_y, z_max_global, 1])
                
                # --- PROCESAR COSTILLA X (Corta mitad INFERIOR) ---
                inv_transform_x = np.linalg.inv(x_item['transform'])
                p2d_low_x = np.dot(inv_transform_x, p3d_low)[:2]
                p2d_high_x = np.dot(inv_transform_x, p3d_high)[:2]
                line_x = LineString([p2d_low_x, p2d_high_x])
                
                new_polys_x = []
                for poly in x_slices_polys[i]:
                    inter = poly.intersection(line_x)
                    if inter.is_empty:
                        new_polys_x.append(poly)
                        continue
                        
                    segments = [inter] if inter.geom_type == 'LineString' else [g for g in inter.geoms if g.geom_type == 'LineString']
                    current_poly = poly
                    
                    for seg in segments:
                        pt1, pt2 = np.array(seg.coords[0]), np.array(seg.coords[1])
                        z_dir = p2d_high_x - p2d_low_x
                        norm_z = np.linalg.norm(z_dir)
                        if norm_z < 1e-5: continue
                        z_dir /= norm_z
                        
                        v1 = np.dot(pt1 - p2d_low_x, z_dir)
                        v2 = np.dot(pt2 - p2d_low_x, z_dir)
                        pt_bottom, pt_top = (pt2, pt1) if v1 > v2 else (pt1, pt2)
                        
                        if np.linalg.norm(pt_top - pt_bottom) < 0.5: continue
                            
                        pt_center = (pt_bottom + pt_top) / 2.0
                        width_dir = np.array([-z_dir[1], z_dir[0]])
                        
                        pt_bottom_ext = pt_bottom - z_dir * 5.0
                        n1 = pt_bottom_ext - width_dir * (t / 2.0)
                        n2 = pt_bottom_ext + width_dir * (t / 2.0)
                        n3 = pt_center + width_dir * (t / 2.0)
                        n4 = pt_center - width_dir * (t / 2.0)
                        
                        notch_box = ShapelyPolygon([n1, n2, n3, n4]).buffer(0)
                        current_poly = current_poly.difference(notch_box).buffer(0)
                    
                    if current_poly.geom_type == 'Polygon' and not current_poly.is_empty:
                        new_polys_x.append(current_poly)
                    elif current_poly.geom_type == 'MultiPolygon':
                        new_polys_x.extend([p for p in current_poly.geoms if not p.is_empty])
                x_slices_polys[i] = new_polys_x

                # --- PROCESAR COSTILLA Y (Corta mitad SUPERIOR) ---
                inv_transform_y = np.linalg.inv(y_item['transform'])
                p2d_low_y = np.dot(inv_transform_y, p3d_low)[:2]
                p2d_high_y = np.dot(inv_transform_y, p3d_high)[:2]
                line_y = LineString([p2d_low_y, p2d_high_y])
                
                new_polys_y = []
                for poly in y_slices_polys[j]:
                    inter = poly.intersection(line_y)
                    if inter.is_empty:
                        new_polys_y.append(poly)
                        continue
                        
                    segments = [inter] if inter.geom_type == 'LineString' else [g for g in inter.geoms if g.geom_type == 'LineString']
                    current_poly = poly
                    
                    for seg in segments:
                        pt1, pt2 = np.array(seg.coords[0]), np.array(seg.coords[1])
                        z_dir = p2d_high_y - p2d_low_y
                        norm_z = np.linalg.norm(z_dir)
                        if norm_z < 1e-5: continue
                        z_dir /= norm_z
                        
                        v1 = np.dot(pt1 - p2d_low_y, z_dir)
                        v2 = np.dot(pt2 - p2d_low_y, z_dir)
                        pt_bottom, pt_top = (pt2, pt1) if v1 > v2 else (pt1, pt2)
                        
                        if np.linalg.norm(pt_top - pt_bottom) < 0.5: continue
                            
                        pt_center = (pt_bottom + pt_top) / 2.0
                        width_dir = np.array([-z_dir[1], z_dir[0]])
                        
                        pt_top_ext = pt_top + z_dir * 5.0
                        n1 = pt_center - width_dir * (t / 2.0)
                        n2 = pt_center + width_dir * (t / 2.0)
                        n3 = pt_top_ext + width_dir * (t / 2.0)
                        n4 = pt_top_ext - width_dir * (t / 2.0)
                        
                        notch_box = ShapelyPolygon([n1, n2, n3, n4]).buffer(0)
                        current_poly = current_poly.difference(notch_box).buffer(0)
                    
                    if current_poly.geom_type == 'Polygon' and not current_poly.is_empty:
                        new_polys_y.append(current_poly)
                    elif current_poly.geom_type == 'MultiPolygon':
                        new_polys_y.extend([p for p in current_poly.geoms if not p.is_empty])
                y_slices_polys[j] = new_polys_y

        # --- FASE 4: Reconstrucción y Empaquetado Final a Trimesh ---
        final_slices = []
        final_transforms = []

        for idx, item in enumerate(x_slices):
            if idx < len(x_slices_polys) and x_slices_polys[idx]:
                valid_polys = [p for p in x_slices_polys[idx] if not p.is_empty]
                if valid_polys:
                    merged_geometry = unary_union(valid_polys)
                    item['slice_2d'] = trimesh.load_path(merged_geometry)
            final_slices.append(item['slice_2d'])
            final_transforms.append(item['transform'])

        for idx, item in enumerate(y_slices):
            if idx < len(y_slices_polys) and y_slices_polys[idx]:
                valid_polys = [p for p in y_slices_polys[idx] if not p.is_empty]
                if valid_polys:
                    merged_geometry = unary_union(valid_polys)
                    item['slice_2d'] = trimesh.load_path(merged_geometry)
            final_slices.append(item['slice_2d'])
            final_transforms.append(item['transform'])

        self.slices_2d = final_slices
        self.slice_transforms = final_transforms
        print(f"[DEBUG] Interlocking finalizado con éxito. Costillas totales listas: {len(final_slices)}")
        return final_slices

    
    def slice_flat(self, angle_x=0.0, angle_y=0.0, angle_z=0.0):
        print("\n--- [DEBUG] INICIANDO FLAT SLICING ---")
        self._clear_previous_results()   
        rad_x = math.radians(angle_x)
        rad_y = math.radians(angle_y)
        rad_z = math.radians(angle_z)

        # Matriz de rotación y su inversa (para devolver las piezas a su posición original)
        rot_matrix = trimesh.transformations.euler_matrix(rad_x, rad_y, rad_z, 'sxyz')
        inv_rot_matrix = trimesh.transformations.inverse_matrix(rot_matrix)
        
        temp_mesh = self.mesh.copy()
        temp_mesh.apply_transform(rot_matrix)

        z_min = temp_mesh.bounds[0][2]
        z_max = temp_mesh.bounds[1][2]
        
        step = self.material_thickness
        z_levels = np.arange(z_min + (step / 2), z_max, step)

        generated_slices = []
        generated_transforms = []

        for z in z_levels:
            slice_3d = temp_mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
            
            if slice_3d is not None:
                # AQUÍ ESTÁ LA MAGIA: Guardamos la matriz to_3d_transform
                slice_2d, to_3d_transform = slice_3d.to_planar()
                if len(slice_2d.polygons_full) > 0:
                    generated_slices.append(slice_2d)
                    
                    # Multiplicamos por la inversa para deshacer la rotación temporal
                    final_transform = np.dot(inv_rot_matrix, to_3d_transform)
                    generated_transforms.append(final_transform)
        
        print(f"[DEBUG] Se lograron extraer con éxito: {len(generated_slices)} láminas 2D válidas.")
        self.slices_2d = generated_slices
        self.slice_transforms = generated_transforms # Guardamos las posiciones
        
        print("--- [DEBUG] FIN DE FLAT SLICING ---\n")
        return generated_slices
    
    # Esqueleto para el método radial
    def slice_radial(self, rad_cuts=12, vert_cuts=10):
        """
        Generates radial slices (vertical wedges around Z) and horizontal
        slices (discs), then cuts interlocking notches at every intersection.

        Notch convention (mirrors slice_interlocking):
          - Radial ribs  → notch cut from the BOTTOM half (disc slots in from below)
          - Horizontal discs → notch cut from the TOP half (radial slots in from above)
        """
        self._clear_previous_results()
        print(f"\n--- [DEBUG] RADIAL SLICING WITH NOTCHES: "
              f"{rad_cuts} radial, {vert_cuts} horizontal ---")

        from shapely.geometry import Polygon as ShapelyPolygon, LineString
        from shapely.ops import unary_union

        center = self.mesh.centroid
        bounds = self.mesh.bounds
        t      = self.material_thickness

        # ------------------------------------------------------------------
        # PHASE 1: Extract raw slices and keep their 3D section objects
        # ------------------------------------------------------------------
        rad_slices  = []   # vertical wedge planes
        horiz_slices = []  # horizontal disc planes

        for i in range(rad_cuts):
            angle  = (np.pi * i) / rad_cuts
            normal = [np.sin(angle), -np.cos(angle), 0]
            slice_3d = self.mesh.section(plane_origin=center, plane_normal=normal)
            if slice_3d is None:
                continue
            slice_2d, to_3d = slice_3d.to_planar()
            if len(slice_2d.polygons_full) == 0:
                continue
            rad_slices.append({
                'slice_3d': slice_3d,
                'slice_2d': slice_2d,
                'transform': to_3d,
                'normal': np.array(normal, dtype=float),
                'angle': angle,
            })

        z_levels = np.linspace(
            bounds[0][2] + (t / 2),
            bounds[1][2] - (t / 2),
            vert_cuts
        )
        for z in z_levels:
            slice_3d = self.mesh.section(
                plane_origin=[center[0], center[1], z],
                plane_normal=[0, 0, 1]
            )
            if slice_3d is None:
                continue
            slice_2d, to_3d = slice_3d.to_planar()
            if len(slice_2d.polygons_full) == 0:
                continue
            horiz_slices.append({
                'slice_3d': slice_3d,
                'slice_2d': slice_2d,
                'transform': to_3d,
                'z': z,
            })

        # ------------------------------------------------------------------
        # PHASE 2: Convert to Shapely and sanitise topology
        # ------------------------------------------------------------------
        def to_shapely(slice_item):
            polys = []
            for p in slice_item['slice_2d'].polygons_full:
                pv = p.buffer(0)
                if pv.geom_type == 'Polygon':
                    polys.append(pv)
                elif pv.geom_type == 'MultiPolygon':
                    polys.extend(pv.geoms)
            return polys

        rad_polys   = [to_shapely(s) for s in rad_slices]
        horiz_polys = [to_shapely(s) for s in horiz_slices]

        # ------------------------------------------------------------------
        # PHASE 3: Cut notches at every radial × horizontal intersection
        #
        # Strategy: for each pair (rad_slice i, horiz_slice j) find the 3D
        # intersection line, project it into each slice's local 2D space,
        # then subtract a notch rectangle — exactly as slice_interlocking does.
        #
        # The intersection of a vertical radial plane and a horizontal plane
        # is a horizontal line at height z passing through the model center,
        # perpendicular to the radial plane's normal.
        # ------------------------------------------------------------------
        def cut_notch_bottom(polys, line_2d, z_dir_2d, t):
            """Remove lower-half notch from polys along line_2d (for radial ribs)."""
            new_polys = []
            for poly in polys:
                inter = poly.intersection(line_2d)
                if inter.is_empty:
                    new_polys.append(poly)
                    continue
                segs = ([inter] if inter.geom_type == 'LineString'
                        else [g for g in inter.geoms
                              if g.geom_type == 'LineString'])
                current = poly
                for seg in segs:
                    pt1 = np.array(seg.coords[0])
                    pt2 = np.array(seg.coords[-1])
                    if np.linalg.norm(pt2 - pt1) < 0.5:
                        continue
                    # Identify bottom vs top endpoint along z_dir
                    v1 = np.dot(pt1, z_dir_2d)
                    v2 = np.dot(pt2, z_dir_2d)
                    pt_bot, pt_top = (pt2, pt1) if v1 > v2 else (pt1, pt2)
                    pt_mid   = (pt_bot + pt_top) / 2.0
                    w_dir    = np.array([-z_dir_2d[1], z_dir_2d[0]])
                    pt_bot_x = pt_bot - z_dir_2d * 5.0   # extend past edge
                    n1 = pt_bot_x - w_dir * (t / 2.0)
                    n2 = pt_bot_x + w_dir * (t / 2.0)
                    n3 = pt_mid   + w_dir * (t / 2.0)
                    n4 = pt_mid   - w_dir * (t / 2.0)
                    notch = ShapelyPolygon([n1, n2, n3, n4]).buffer(0)
                    current = current.difference(notch).buffer(0)
                if current.geom_type == 'Polygon' and not current.is_empty:
                    new_polys.append(current)
                elif current.geom_type == 'MultiPolygon':
                    new_polys.extend([p for p in current.geoms if not p.is_empty])
            return new_polys

        def cut_notch_top(polys, line_2d, z_dir_2d, t):
            """Remove upper-half notch from polys along line_2d (for horizontal discs)."""
            new_polys = []
            for poly in polys:
                inter = poly.intersection(line_2d)
                if inter.is_empty:
                    new_polys.append(poly)
                    continue
                segs = ([inter] if inter.geom_type == 'LineString'
                        else [g for g in inter.geoms
                              if g.geom_type == 'LineString'])
                current = poly
                for seg in segs:
                    pt1 = np.array(seg.coords[0])
                    pt2 = np.array(seg.coords[-1])
                    if np.linalg.norm(pt2 - pt1) < 0.5:
                        continue
                    v1 = np.dot(pt1, z_dir_2d)
                    v2 = np.dot(pt2, z_dir_2d)
                    pt_bot, pt_top = (pt2, pt1) if v1 > v2 else (pt1, pt2)
                    pt_mid   = (pt_bot + pt_top) / 2.0
                    w_dir    = np.array([-z_dir_2d[1], z_dir_2d[0]])
                    pt_top_x = pt_top + z_dir_2d * 5.0   # extend past edge
                    n1 = pt_mid   - w_dir * (t / 2.0)
                    n2 = pt_mid   + w_dir * (t / 2.0)
                    n3 = pt_top_x + w_dir * (t / 2.0)
                    n4 = pt_top_x - w_dir * (t / 2.0)
                    notch = ShapelyPolygon([n1, n2, n3, n4]).buffer(0)
                    current = current.difference(notch).buffer(0)
                if current.geom_type == 'Polygon' and not current.is_empty:
                    new_polys.append(current)
                elif current.geom_type == 'MultiPolygon':
                    new_polys.extend([p for p in current.geoms if not p.is_empty])
            return new_polys

        for i, r_item in enumerate(rad_slices):
            for j, h_item in enumerate(horiz_slices):

                z_val = h_item['z']

                # The 3D intersection is a horizontal line at height z_val,
                # passing through center, perpendicular to the radial normal.
                # Radial plane normal = r_item['normal'] (in XY plane)
                # The line direction = normal × Z = (ny, -nx, 0) → already in XY
                rad_normal = r_item['normal']           # [nx, ny, 0]
                line_dir_3d = np.array([-rad_normal[1], rad_normal[0], 0.0])

                # Two 3D points far apart along that line at height z_val
                far = 1000.0
                p3d_A = np.array([center[0] + line_dir_3d[0] * far,
                                  center[1] + line_dir_3d[1] * far,
                                  z_val, 1.0])
                p3d_B = np.array([center[0] - line_dir_3d[0] * far,
                                  center[1] - line_dir_3d[1] * far,
                                  z_val, 1.0])

                # ---- Project into RADIAL slice 2D space ----
                inv_r = np.linalg.inv(r_item['transform'])
                p2d_rA = np.dot(inv_r, p3d_A)[:2]
                p2d_rB = np.dot(inv_r, p3d_B)[:2]
                line_r = LineString([p2d_rA, p2d_rB])

                # Local "up" direction in radial 2D space is the projection of
                # the world Z axis through the transform.
                z3d_up   = np.array([center[0], center[1], z_val + 1.0, 1.0])
                z3d_down = np.array([center[0], center[1], z_val - 1.0, 1.0])
                z_up_2d  = np.dot(inv_r, z3d_up)[:2]
                z_dn_2d  = np.dot(inv_r, z3d_down)[:2]
                z_dir_r  = z_up_2d - z_dn_2d
                norm_r   = np.linalg.norm(z_dir_r)
                if norm_r < 1e-5:
                    continue
                z_dir_r /= norm_r

                rad_polys[i] = cut_notch_bottom(rad_polys[i], line_r, z_dir_r, t)

                # ---- Project into HORIZONTAL slice 2D space ----
                # Two 3D points along the radial direction at height z_val
                p3d_C = np.array([center[0] + rad_normal[0] * far,
                                  center[1] + rad_normal[1] * far,
                                  z_val, 1.0])
                p3d_D = np.array([center[0] - rad_normal[0] * far,
                                  center[1] - rad_normal[1] * far,
                                  z_val, 1.0])

                inv_h = np.linalg.inv(h_item['transform'])
                p2d_hC = np.dot(inv_h, p3d_C)[:2]
                p2d_hD = np.dot(inv_h, p3d_D)[:2]
                line_h = LineString([p2d_hC, p2d_hD])

                # In the horizontal disc's 2D space, "up" maps to the radial
                # direction (the disc is flat, so we use the radial normal as
                # the notch depth direction).
                p3d_up_h   = np.array([center[0] + rad_normal[0],
                                       center[1] + rad_normal[1],
                                       z_val, 1.0])
                p3d_orig_h = np.array([center[0], center[1], z_val, 1.0])
                z_up_h   = np.dot(inv_h, p3d_up_h)[:2]
                z_orig_h = np.dot(inv_h, p3d_orig_h)[:2]
                z_dir_h  = z_up_h - z_orig_h
                norm_h   = np.linalg.norm(z_dir_h)
                if norm_h < 1e-5:
                    continue
                z_dir_h /= norm_h

                horiz_polys[j] = cut_notch_top(horiz_polys[j], line_h, z_dir_h, t)

        # ------------------------------------------------------------------
        # PHASE 4: Reconstruct trimesh Path2D objects and store
        # ------------------------------------------------------------------
        final_slices     = []
        final_transforms = []

        for i, item in enumerate(rad_slices):
            if rad_polys[i]:
                valid = [p for p in rad_polys[i] if not p.is_empty]
                if valid:
                    item['slice_2d'] = trimesh.load_path(unary_union(valid))
            final_slices.append(item['slice_2d'])
            final_transforms.append(item['transform'])

        for j, item in enumerate(horiz_slices):
            if horiz_polys[j]:
                valid = [p for p in horiz_polys[j] if not p.is_empty]
                if valid:
                    item['slice_2d'] = trimesh.load_path(unary_union(valid))
            final_slices.append(item['slice_2d'])
            final_transforms.append(item['transform'])

        self.slices_2d        = final_slices
        self.slice_transforms = final_transforms
        print(f"[DEBUG] Radial slicing complete: {len(final_slices)} pieces "
              f"({len(rad_slices)} radial + {len(horiz_slices)} horizontal).")
        return final_slices


    # Esqueleto para el método de contorno
    def slice_contour(
        self,
        num_circles: int = 5,
        ring_thickness: float = None,
        center_x: float = None,
        center_y: float = None,
        center_z: float = None,
    ):
        """
        Circular-ring slicer.

        Genera N anillos cilíndricos concéntricos cuyo eje pasa por
        (center_x, center_y, center_z). Para cada radio calcula la
        intersección del cilindro con la malla 3D y produce los segmentos
        de arco reales que quedan dentro del sólido.

        Parámetros
        ----------
        num_circles   : cantidad de anillos/circunferencias.
        ring_thickness: grosor de cada anillo en mm.
                        Si es None usa self.material_thickness.
        center_x/y/z  : centro del sistema de anillos en coordenadas del
                        modelo. Si es None se usa el centroide de la malla.

        Lógica
        ------
        1. Calcula r_max = distancia máxima de cualquier vértice al eje Z
           pasando por (cx, cy).
        2. Distribuye N radios equidistantes entre r_max/N y r_max.
        3. Por cada radio R construye un anillo Shapely:
               disco(R + t/2) − disco(R − t/2)
        4. Intersecta ese anillo con la silueta horizontal de la malla a
           cada nivel Z (paso = material_thickness) → segmentos de arco
           reales dentro del sólido.
        5. Cada segmento se almacena como Path2D en self.slices_2d.
        """
        import trimesh
        import numpy as np
        from shapely.geometry import Point
        from shapely.ops import unary_union

        self._clear_previous_results()

        t = ring_thickness if ring_thickness is not None else self.material_thickness

        # --- Centro del sistema de anillos ---
        c  = self.mesh.centroid
        cx = center_x if center_x is not None else c[0]
        cy = center_y if center_y is not None else c[1]
        cz = center_z if center_z is not None else c[2]  # informativo, no usado en corte

        print(
            f"\n--- [DEBUG] CIRCULAR CONTOUR SLICING ---\n"
            f"    Centro: ({cx:.2f}, {cy:.2f}, {cz:.2f})\n"
            f"    Circunferencias: {num_circles},  grosor anillo: {t:.2f} mm"
        )

        bounds = self.mesh.bounds

        # --- Radio máximo: distancia de cualquier vértice al eje (cx, cy) ---
        verts_xy = self.mesh.vertices[:, :2] - np.array([cx, cy])
        r_max    = float(np.max(np.linalg.norm(verts_xy, axis=1)))

        if r_max < 1e-6:
            print("[DEBUG] Radio máximo prácticamente cero — malla demasiado pequeña.")
            return []

        # N radios equidistantes; el más interno arranca en r_max/N
        radii = np.linspace(r_max / num_circles, r_max, num_circles)

        print(f"    Radio máximo detectado: {r_max:.2f} mm")
        print(f"    Radios: {[round(r, 2) for r in radii]}")

        # Paso Z = material_thickness (igual que slice_flat)
        z_step   = self.material_thickness
        z_levels = np.arange(bounds[0][2] + z_step / 2.0, bounds[1][2], z_step)

        generated_slices     = []
        generated_transforms = []

        for r in radii:
            r_outer = r + t / 2.0
            r_inner = max(r - t / 2.0, 0.0)

            for z in z_levels:
                # 1. Sección horizontal de la malla a este nivel Z
                sec = self.mesh.section(
                    plane_origin=[cx, cy, z],
                    plane_normal=[0, 0, 1],
                )
                if sec is None:
                    continue

                slice_2d, to_3d = sec.to_planar()
                if len(slice_2d.polygons_full) == 0:
                    continue

                # 2. Unión de todos los polígonos de la sección
                mesh_union = unary_union(
                    [p.buffer(0) for p in slice_2d.polygons_full]
                )

                # 3. Proyectar el centro del anillo al espacio 2D local
                #    to_planar() puede rotar/trasladar; usamos su inversa.
                inv_to_3d = np.linalg.inv(to_3d)
                c3d       = np.array([cx, cy, z, 1.0])
                c2d       = np.dot(inv_to_3d, c3d)[:2]

                # 4. Construir el anillo en el espacio 2D local
                ring_local = (
                    Point(c2d[0], c2d[1]).buffer(r_outer, resolution=128)
                    .difference(Point(c2d[0], c2d[1]).buffer(r_inner, resolution=128))
                )

                # 5. Intersección → solo los arcos DENTRO del sólido
                segment = mesh_union.intersection(ring_local)
                if segment.is_empty:
                    continue

                segment = segment.buffer(0)

                # 6. Convertir a Path2D y guardar
                path_2d = trimesh.load_path(segment)
                if path_2d is not None and len(path_2d.entities) > 0:
                    generated_slices.append(path_2d)
                    generated_transforms.append(to_3d)

        self.slices_2d        = generated_slices
        self.slice_transforms = generated_transforms

        print(
            f"[DEBUG] Circular contour finalizado: "
            f"{len(generated_slices)} segmentos de arco en "
            f"{num_circles} anillos × {len(z_levels)} niveles Z."
        )
        return generated_slices
    
    def get_visual_prediction(self):
        """
        Convierte las láminas 2D de vuelta a 3D mediante extrusión y aplica 
        sus matrices de transformación originales para previsualizar el ensamble.
        """
        import trimesh
        import numpy as np
        
        if not self.slices_2d or len(self.slices_2d) != len(self.slice_transforms):
            return self.mesh

        visual_parts = []
        
        for slice_2d, transform in zip(self.slices_2d, self.slice_transforms):
            # 1. Extruir el Path2D para darle el grosor del material
            mesh_3d = slice_2d.extrude(self.material_thickness)
            
            # CORRECCIÓN: Si el corte generó piezas desconectadas (islas), Trimesh devuelve una lista.
            # Debemos unirlas en un solo objeto 3D antes de aplicar las transformaciones.
            if isinstance(mesh_3d, list):
                if not mesh_3d:
                    continue  # Saltar si la lista está vacía
                mesh_3d = trimesh.util.concatenate(mesh_3d)
            
            # 2. Centrar la extrusión en el eje Z (extrude() crece hacia +Z)
            center_z_matrix = trimesh.transformations.translation_matrix([0, 0, -self.material_thickness / 2.0])
            mesh_3d.apply_transform(center_z_matrix)
            
            # 3. Aplicar la matriz de transformación guardada para enviarlo a su lugar
            mesh_3d.apply_transform(transform)
            
            visual_parts.append(mesh_3d)

        # Retornamos una sola malla combinada
        if visual_parts:
            return trimesh.util.concatenate(visual_parts)
        else:
            return self.mesh
        

    # --- MÉTODO DE ANIDADO (NESTING) ---

    def make_text_path(self, text, h_size):
        """
        Generates stick-font vector paths for the given text string.
        Characters not in stroke_map are silently skipped.
        Returns None if the text produces no renderable characters.
        """
        import trimesh
        from trimesh.path.entities import Line
        import numpy as np

        w_size = 0.6
        stroke_map = {
            '0': [[0,1], [w_size,1], [w_size,0], [0,0], [0,1]],
            '1': [[w_size/2,1], [w_size/2,0]],
            '2': [[0,1], [w_size,1], [w_size,0.5], [0,0.5], [0,0], [w_size,0]],
            '3': [[0,1], [w_size,1], [w_size,0], [0,0], [w_size,0], [w_size,0.5], [0,0.5]],
            '4': [[0,1], [0,0.5], [w_size,0.5], [w_size,1], [w_size,0]],
            '5': [[w_size,1], [0,1], [0,0.5], [w_size,0.5], [w_size,0], [0,0]],
            '6': [[w_size,1], [0,1], [0,0], [w_size,0], [w_size,0.5], [0,0.5]],
            '7': [[0,1], [w_size,1], [0,0]],
            '8': [[0,0], [w_size,0], [w_size,1], [0,1], [0,0], [0,0.5], [w_size,0.5]],
            '9': [[w_size,0], [w_size,1], [0,1], [0,0.5], [w_size,0.5], [w_size,0], [0,0]],
            '-': [[0, 0.5], [w_size, 0.5]]
        }

        vertices = []
        entities = []
        v_idx = 0
        stride = 0.8

        for char_idx, char in enumerate(text):
            if char not in stroke_map:
                continue

            pts = np.array(stroke_map[char], dtype=float)
            pts[:, 0] += char_idx * stride
            pts *= h_size

            for pt in pts:
                vertices.append(pt)

            num_pts = len(pts)
            entities.append(Line(points=list(range(v_idx, v_idx + num_pts))))
            v_idx += num_pts

        if not vertices:
            return None

        return trimesh.path.Path2D(entities=entities, vertices=np.array(vertices))
