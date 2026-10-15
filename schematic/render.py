"""Load a schematic document and render it to SVG."""

import json
import os
import re

from schematic.document import load_document, normalize_document
from schematic.elaborate import load_builtin_libs, load_schematic
from schematic.engine import layout
from schematic.graph import document_to_elk
from schematic.drawio import svg_to_drawio
from schematic.drawio_native import render_drawio_native
from schematic.svg import render_svg

_HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def clean_palette(raw):
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if len(key) > 96:
            continue
        text = value.strip()
        if not _HEX.match(text):
            continue
        out[key] = text
    return out


def document_libs(document):
    import copy

    libs = document.get("libs") if isinstance(document, dict) else None
    if not isinstance(libs, dict) or not libs:
        libs = load_builtin_libs()
    else:
        libs = copy.deepcopy(libs)
    return libs


def merged_palette(document, override=None):
    palette = {}
    base = document.get("palette") if isinstance(document, dict) else None
    if isinstance(base, dict):
        palette.update(clean_palette(base))
    palette.update(clean_palette(override))
    return palette


def _preserve_edge_metadata(graph, laid):
    """elkjs may drop custom edge fields; restore from pre-layout graph."""
    by_id = {}
    for edge in graph.get("edges") or []:
        eid = edge.get("id")
        if not eid:
            continue
        by_id[eid] = edge
    for edge in laid.get("edges") or []:
        src = by_id.get(edge.get("id"))
        if not src:
            continue
        if src.get("properties"):
            merged = dict(edge.get("properties") or {})
            merged.update(src["properties"])
            edge["properties"] = merged
        if src.get("labels"):
            edge["labels"] = src["labels"]


def draw(document, options=None):
    """Return an SVG string for a schematic document."""
    options = dict(options or {})
    palette = merged_palette(document, options.get("palette"))
    libs = document_libs(document)
    graph = document_to_elk(document, options)
    laid = layout(graph)
    _preserve_edge_metadata(graph, laid)
    return render_svg(laid, palette, libs=libs)


def draw_drawio(document, options=None, *, title="diagram"):
    """Return draw.io XML for a schematic document (same layout as :func:`draw`)."""
    options = dict(options or {})
    if options.get("drawio_via_svg"):
        return svg_to_drawio(draw(document, options), title=title)
    palette = merged_palette(document, options.get("palette"))
    libs = document_libs(document)
    graph = document_to_elk(document, options)
    laid = layout(graph)
    _preserve_edge_metadata(graph, laid)
    return render_drawio_native(laid, palette, title=title, libs=libs)


def draw_drawio_via_svg(document, options=None, *, title="diagram"):
    """Scheme B: SVG decomposed through svg-to-drawio."""
    return svg_to_drawio(draw(document, options), title=title)


def _write_text(out_path, text):
    folder = os.path.dirname(os.path.abspath(out_path))
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return out_path


def _out_stem(out_path):
    base = os.path.basename(out_path)
    stem, _ = os.path.splitext(base)
    return stem or "graph"


def draw_sources(json_paths, out_path, options=None, filelists=None, top=None):
    document = load_schematic(json_paths, filelists=filelists, top=top)
    options = dict(options or {})
    if out_path.lower().endswith(".drawio"):
        text = draw_drawio(document, options, title=_out_stem(out_path))
    else:
        text = draw(document, options)
    return _write_text(out_path, text)


def draw_file(path, out_path, options=None):
    document = load_document(path)
    options = dict(options or {})
    if out_path.lower().endswith(".drawio"):
        text = draw_drawio(document, options, title=_out_stem(out_path))
    else:
        text = draw(document, options)
    return _write_text(out_path, text)
