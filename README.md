# OpenSlicer
An open-source, web-based 3D slicing application built with Python and Streamlit. OpenSlicer is engineered specifically to convert 3D models into flat, manufacturing-ready 2D profiles for laser cutting, interlocking assembly, and CNC applications.

---

## Key Features

- **Dynamic 3D-to-2D Slicing:** Automatically decomposes standard 3D meshes (STL) into accurate 2D slices mapped directly to your material thickness.
- **Interlocking Joints & Notches:** Computes assembly slots on the fly, allowing physical parts to snap together seamlessly without additional fasteners.
- **Smart Sheet Nesting:** Leverages the `rectpack` library to arrange layout pieces across multiple manufacturing sheets, significantly reducing material waste.
- **Production-Ready DXF Export:** Generates clean, multi-layer DXF files that separate structural cutlines (`CUT`) from vector text (`LABELS`), ensuring native compatibility with CNC/laser software like LightBurn and AutoCAD.
- **Streamlined UI:** A borderless, minimalist frontend featuring interactive 3D and 2D canvas previews powered by Plotly and `streamlit-stl`.

## Project Structure

- **`Slicer.py`** – The geometric core. Handles mesh parsing (via `trimesh`), scaling, slicing planes, notch calculations, and single-stroke font vector mapping for laser marking.
- **`DXFExporter.py`** – The post-processing engine. Manages multi-sheet nesting workflows, layer isolation, color-coding, and raw DXF building.
- **`Streamlit.py`** – The user interface. Controls live parameters (thickness, nesting limits, margins) and structures the interactive web workspace.

## Getting Started

### Prerequisites

Make sure you have Python 3.9+ installed, then install the required dependencies:

```bash
pip install streamlit trimesh numpy rectpack plotly streamlit-stl
```

----------------------------------------------------------------------------------
----------------------------------------------------------------------------------

# Español:

Esta es una aplicación web de código abierto para el rebanado (slicing) de modelos 3D desarrollada en Python y Streamlit. OpenSlicer está diseñada específicamente para convertir modelos 3D en perfiles planos 2D listos para manufactura mediante corte láser, ensambles entrelazados (interlocking) y aplicaciones CNC.

---

## Características Principales

- **Corte Dinámico de 3D a 2D:** Descompone automáticamente mallas 3D estándar (STL, OBJ) en rebanadas 2D precisas, ajustadas directamente al espesor de tu material.
- **Uniones y Muescas de Ensamble:** Calcula ranuras de encaje en tiempo real, permitiendo que las piezas físicas se ensamblen a presión sin necesidad de herrajes adicionales.
- **Optimización de Material (Nesting Inteligente):** Implementa la librería `rectpack` para distribuir estratégicamente las piezas sobre múltiples planchas o láminas de material, reduciendo significativamente el desperdicio.
- **Exportación DXF Lista para Producción:** Genera archivos DXF multicapa limpios que separan los contornos de corte exterior (`CUT`) de los textos vectoriales (`LABELS`), garantizando compatibilidad nativa con softwares de diseño y CNC como LightBurn y AutoCAD.
- **Interfaz de Usuario Fluida:** Un panel web minimalista y sin bordes con previsualizaciones interactivas en 3D y 2D desarrolladas con Plotly y `streamlit-stl`.

## Estructura del Proyecto

- **`Slicer.py`** – El núcleo geométrico. Gestiona la lectura de mallas (vía `trimesh`), el escalado, los planos de corte, el cálculo de muescas y el mapeo de fuentes vectoriales de un solo trazo para grabado láser.
- **`DXFExporter.py`** – El motor de post-procesamiento. Administra los flujos de acomodo en múltiples hojas (nesting), el aislamiento de capas, la asignación de colores y la estructura final del archivo DXF.
- **`Streamlit.py`** – La interfaz de usuario. Controla los parámetros en tiempo real (espesor, límites de nesting, márgenes) y organiza el entorno de trabajo web interactivo.

## Cómo Empezar

### Prerrequisitos

Asegúrate de tener instalado Python 3.9 o superior, y luego instala las dependencias necesarias:

```bash
pip install streamlit trimesh numpy rectpack plotly streamlit-stl
```
