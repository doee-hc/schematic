"""Load a schematic document and render it to SVG."""

import json
import os
import re

from schematic.engine import layout
from schematic.graph import document_to_elk
from schematic.svg import render_svg

_HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def load_document(path):
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("root"), dict):
        raise ValueError("电路图 JSON 需要对象根，且包含 root")
    data.setdefault("palette", {})
    data.setdefault("swatches", [])
    return data


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


def merged_palette(document, override=None):
    palette = {}
    base = document.get("palette") if isinstance(document, dict) else None
    if isinstance(base, dict):
        palette.update(clean_palette(base))
    palette.update(clean_palette(override))
    return palette


def draw(document, options=None):
    """Return an SVG string for a schematic document."""
    options = dict(options or {})
    palette = merged_palette(document, options.get("palette"))
    graph = document_to_elk(document, options)
    laid = layout(graph)
    return render_svg(laid, palette)


def draw_file(path, out_path, options=None):
    document = load_document(path)
    svg = draw(document, options)
    folder = os.path.dirname(os.path.abspath(out_path))
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(svg)
    return out_path
