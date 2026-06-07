"""
DXFExporter.py
Handles all DXF post-processing: layer injection, color assignment,
multi-sheet nesting layout, and export.

Used by OpenSlicer via:
    from DXFExporter import DXFExporter
    exporter = DXFExporter(slicer)
    exporter.arrange_grid_nesting(600, 400)
    exporter.layouts[0].export()
"""

import copy
import re
import numpy as np


# ---------------------------------------------------------------------------
# Module-level DXF text helpers (pure functions, no class needed)
# ---------------------------------------------------------------------------

def _make_layer_table_entry(layer_name, aci_color, handle):
    """Returns a DXF LAYER table record as a string."""
    return (
        f"0\nLAYER\n"
        f"5\n{handle}\n"
        f"330\n2\n"
        f"100\nAcDbSymbolTableRecord\n"
        f"100\nAcDbLayerTableRecord\n"
        f"2\n{layer_name}\n"
        f"70\n0\n"
        f"62\n{aci_color}\n"
        f"6\nCONTINUOUS\n"
        f"370\n0\n"
        f"390\nF\n"
    )


def _extract_entities_body(dxf_text):
    """
    Extract only the body of the ENTITIES section, without the surrounding:
        0
        SECTION
        2
        ENTITIES
    and without:
        0
        ENDSEC
    """
    if not dxf_text:
        return ""

    m = re.search(
        r'0\s*\nSECTION\s*\n2\s*\nENTITIES\s*\n(.*?)\n0\s*\nENDSEC',
        dxf_text,
        re.DOTALL
    )
    return m.group(1).strip() if m else ""


def _relabel_entities(dxf_text, new_layer, aci_color):
    """
    Replace every entity layer name (group code 8) and color (group code 62)
    in the ENTITIES section of a DXF string.
    """
    if not dxf_text:
        return ""

    lines = dxf_text.splitlines()
    result = []
    i = 0
    in_entities = False

    while i < len(lines):
        line = lines[i].strip()

        if line == "ENTITIES":
            in_entities = True
            result.append(lines[i])
            i += 1
            continue

        if in_entities and line == "ENDSEC":
            in_entities = False

        if in_entities and line == "8" and i + 1 < len(lines):
            result.append(lines[i])      # group code 8
            result.append(new_layer)     # overwrite layer
            i += 2
            continue

        if in_entities and line == "62" and i + 1 < len(lines):
            result.append(lines[i])          # group code 62
            result.append(str(aci_color))    # overwrite color
            i += 2
            continue

        result.append(lines[i])
        i += 1

    return "\n".join(result)


def _merge_dxf_layers(cut_dxf, label_dxf, layer_cut, layer_labels):
    """
    Given two DXF strings (cut geometry and label geometry),
    relabel their entities, inject proper LAYER table entries,
    and return one merged DXF string with both layers.
    """
    cut_name, cut_color = layer_cut
    label_name, label_color = layer_labels

    cut_dxf_fixed = _relabel_entities(cut_dxf, cut_name, cut_color)
    label_dxf_fixed = _relabel_entities(label_dxf, label_name, label_color) if label_dxf else ""

    cut_entities = _extract_entities_body(cut_dxf_fixed)
    label_entities = _extract_entities_body(label_dxf_fixed)

    layer_table = (
        "0\nTABLE\n"
        "2\nLAYER\n"
        "5\n2\n"
        "100\nAcDbSymbolTable\n"
        "70\n2\n"
        + _make_layer_table_entry(cut_name, cut_color, "A1")
        + _make_layer_table_entry(label_name, label_color, "A2")
        + "0\nENDTAB\n"
    )

    merged = re.sub(
        r'0\s*\nTABLE\s*\n2\s*\nLAYER\b.*?0\s*\nENDTAB',
        layer_table.strip(),
        cut_dxf_fixed,
        count=1,
        flags=re.DOTALL
    )

    if label_entities:
        merged = re.sub(
            r'(0\s*\nSECTION\s*\n2\s*\nENTITIES\s*\n)(.*?)(\n0\s*\nENDSEC)',
            lambda m: (
                m.group(1)
                + m.group(2).rstrip()
                + "\n"
                + label_entities
                + m.group(3)
            ),
            merged,
            count=1,
            flags=re.DOTALL
        )

    return merged

# ---------------------------------------------------------------------------
# Thin wrapper so layouts have a .export() interface Streamlit can call
# ---------------------------------------------------------------------------

class _DXFLayout:
    def __init__(self, dxf_text: str):
        self._dxf = dxf_text

    def export(self, file_type='dxf'):
        if isinstance(self._dxf, str):
            return self._dxf.encode('utf-8')
        return self._dxf


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class DXFExporter:
    """
    Handles nesting and DXF export for an OpenSlicer instance.

    Usage:
        exporter = DXFExporter(slicer)
        exporter.arrange_grid_nesting(width=600, height=400)
        dxf_bytes = exporter.layouts[0].export()

    Layer config:
        exporter = DXFExporter(
            slicer,
            layer_cut=("CUT", 5),       # Blue
            layer_labels=("LABELS", 2)  # Yellow
        )
    """

    def __init__(self, slicer,
                 layer_cut=("CUT", 5),
                 layer_labels=("LABELS", 2)):
        self.slicer       = slicer
        self.layer_cut    = layer_cut
        self.layer_labels = layer_labels
        self.layouts      = []   # list of _DXFLayout, one per sheet

    def arrange_grid_nesting(self, width=600, height=400):
        """
        Pack all slices from self.slicer into sheets of the given size,
        assign CUT / LABELS layers, and populate self.layouts.
        """
        import rectpack
        from trimesh.path.util import concatenate
        from polylabel import polylabel

        self.layouts = []

        if not self.slicer.slices_2d:
            return

        spacing, margin = 5.0, 10.0

        # Build cut + label paths separately for every slice
        cut_paths   = []
        label_paths = []

        for i, slice_2d in enumerate(self.slicer.slices_2d):
            slice_copy = copy.deepcopy(slice_2d)
            polys      = sorted(slice_copy.polygons_full, key=lambda p: p.area, reverse=True)

            cut_paths.append(slice_copy)

            piece_labels = []
            for idx, poly in enumerate(polys):
                label    = f"{i + 1}" if idx == 0 else f"{i + 1}-{idx}"
                coords   = [list(poly.exterior.coords)]
                label_pt = polylabel(coords, precision=1.0)
                size     = 5.0 if idx == 0 else 3.0

                text_path = self.slicer.make_text_path(label, h_size=size)
                if text_path is None:
                    continue

                t_center = text_path.bounds.mean(axis=0)
                move     = np.eye(3)
                move[0, 2] = label_pt[0] - t_center[0]
                move[1, 2] = label_pt[1] - t_center[1]
                text_path.apply_transform(move)
                piece_labels.append(text_path)

            label_paths.append(concatenate(piece_labels) if piece_labels else None)

        # Compute bounding boxes for the packer (cut + labels combined)
        all_bounds = []
        for i in range(len(cut_paths)):
            parts = [cut_paths[i]] + ([label_paths[i]] if label_paths[i] else [])
            full  = concatenate(parts)
            all_bounds.append(full.bounds)

        # Packing
        packer = rectpack.newPacker(rotation=False)
        for _ in range(50):
            packer.add_bin(width, height)
        for i, b in enumerate(all_bounds):
            packer.add_rect(b[1][0] - b[0][0] + spacing,
                            b[1][1] - b[0][1] + spacing, i)
        packer.pack()

        # Group by sheet
        bins_cut:   dict[int, list] = {}
        bins_label: dict[int, list] = {}

        for b_idx, x, y, w, h, p_id in packer.rect_list():
            b  = all_bounds[p_id]
            dx = -b[0][0] + x + margin
            dy = -b[0][1] + y + margin
            move = np.eye(3)
            move[0, 2] = dx
            move[1, 2] = dy

            cut = copy.deepcopy(cut_paths[p_id])
            cut.apply_transform(move)
            bins_cut.setdefault(b_idx, []).append(cut)

            if label_paths[p_id] is not None:
                lbl = copy.deepcopy(label_paths[p_id])
                lbl.apply_transform(move)
                bins_label.setdefault(b_idx, []).append(lbl)

        # Build one DXF per sheet
        for b_idx in sorted(bins_cut.keys()):
            cut_merged   = concatenate(bins_cut[b_idx])
            label_merged = concatenate(bins_label[b_idx]) if b_idx in bins_label else None

            cut_dxf   = cut_merged.export(file_type='dxf')
            label_dxf = label_merged.export(file_type='dxf') if label_merged else None

            if isinstance(cut_dxf, bytes):
                cut_dxf = cut_dxf.decode('utf-8')
            if isinstance(label_dxf, bytes):
                label_dxf = label_dxf.decode('utf-8')

            final_dxf = _merge_dxf_layers(
                cut_dxf,
                label_dxf,
                layer_cut=self.layer_cut,
                layer_labels=self.layer_labels
            )

            self.layouts.append(_DXFLayout(final_dxf))

        print(f"[DXFExporter] {sum(len(v) for v in bins_cut.values())} pieces "
              f"across {len(self.layouts)} sheet(s) — "
              f"layers: {self.layer_cut[0]}, {self.layer_labels[0]}")