#!/usr/bin/env python3
"""Compare native draw.io node geometry against SVG scene (scheme C diagnostics)."""

import argparse
import re
import sys
import xml.etree.ElementTree as ET

from schematic.document import load_document
from schematic.engine import layout
from schematic.graph import document_to_elk
from schematic.render import merged_palette
from schematic.drawio_vector import node_drawio_bbox
from schematic.drawio_native import render_drawio_native
from schematic.render import _preserve_edge_metadata
from schematic.svg import prepare_scene


def _parse_drawio_cells(xml_text):
    cells = {}
    root = ET.fromstring(xml_text)
    for cell in root.iter("mxCell"):
        cid = cell.get("id")
        if not cid:
            continue
        geo = cell.find("mxGeometry")
        cells[cid] = {
            "parent": cell.get("parent") or "0",
            "style": cell.get("style") or "",
            "geo": geo,
        }
    return cells


def _abs_geometry(cid, cells):
    x = y = 0.0
    w = h = 0.0
    cur = cid
    chain = []
    while cur and cur not in ("0", "1") and cur in cells:
        chain.append(cur)
        cur = cells[cur]["parent"]
    for cur in reversed(chain):
        geo = cells[cur]["geo"]
        if geo is None:
            continue
        x += float(geo.get("x") or 0)
        y += float(geo.get("y") or 0)
        w = float(geo.get("width") or 0)
        h = float(geo.get("height") or 0)
    return x, y, w, h


def _parse_drawio_nodes(xml_text):
    cells = _parse_drawio_cells(xml_text)
    out = {}
    for cid, meta in cells.items():
        m = re.search(r"schematicId=([^;]+);", meta["style"])
        if not m:
            continue
        out[m.group(1)] = _abs_geometry(cid, cells)
    return out


def _load_document(path, filelist=None, top=None):
    if filelist:
        from schematic.elaborate import load_schematic
        return load_schematic([], filelists=[filelist], top=top)
    return load_document(path)


def _expected_nodes(document, options=None):
    options = dict(options or {})
    palette = merged_palette(document, options.get("palette"))
    graph = document_to_elk(document, options)
    laid = layout(graph)
    _preserve_edge_metadata(graph, laid)
    scene = prepare_scene(laid, palette)
    ox, oy = scene["canvas"]["ox"], scene["canvas"]["oy"]
    expected = {}
    for node in scene["nodes"]:
        x, y = scene["origins"][node["id"]]
        w = float(node.get("width") or 0)
        h = float(node.get("height") or 0)
        lx, ly, lw, lh = node_drawio_bbox(node, x, y, w, h, palette)
        expected[node["id"]] = (lx + ox, ly + oy, lw, lh)
    return expected, scene["canvas"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Diagnose native draw.io vs ELK/SVG scene")
    parser.add_argument("json", nargs="?", help="Schematic JSON path")
    parser.add_argument("-f", dest="filelist", help="filelist（与 schematic draw 相同）")
    parser.add_argument("-top", dest="top", default=None, help="顶层 module")
    parser.add_argument("--tol", type=float, default=1.5, help="Max |delta| per coordinate")
    args = parser.parse_args(argv)

    if not args.json and not args.filelist:
        parser.error("需要 json 路径或 -f filelist")
    document = _load_document(args.json or "", filelist=args.filelist, top=args.top)
    options = {}
    expected, canvas = _expected_nodes(document, options)
    graph = document_to_elk(document, options)
    laid = layout(graph)
    _preserve_edge_metadata(graph, laid)
    palette = merged_palette(document, options.get("palette"))
    xml = render_drawio_native(laid, palette, title="diag")
    actual = _parse_drawio_nodes(xml)

    missing = []
    mismatches = []
    for nid, box in sorted(expected.items()):
        if nid not in actual:
            missing.append(nid)
            continue
        for i, label in enumerate(("x", "y", "w", "h")):
            delta = abs(actual[nid][i] - box[i])
            if delta > args.tol:
                mismatches.append((nid, label, box[i], actual[nid][i], delta))

    print("canvas: %.0f x %.0f" % (canvas["width"], canvas["height"]))
    print("nodes expected: %d  in draw.io: %d" % (len(expected), len(actual)))
    if missing:
        print("missing schematicId:", ", ".join(missing))
    if mismatches:
        print("geometry mismatches (tol=%.2f):" % args.tol)
        for row in mismatches[:40]:
            print("  %s.%s expected=%.2f actual=%.2f delta=%.2f" % row)
        if len(mismatches) > 40:
            print("  ... %d more" % (len(mismatches) - 40))
    if not missing and not mismatches:
        print("OK — node boxes align with SVG scene within tolerance.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
