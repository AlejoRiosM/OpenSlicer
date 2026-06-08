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

