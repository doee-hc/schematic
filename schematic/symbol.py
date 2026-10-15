"""Lib symbol vectors: validation, anchors, and shared SVG helpers."""

from __future__ import annotations

import re
import urllib.parse

from schematic.graph import SIDES

ANCHOR_BACK = 6.0
_SIDES = frozenset(("WEST", "EAST", "NORTH", "SOUTH"))
_VIEWBOX_RE = re.compile(
    r"^\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*$"
)


def parse_viewbox(text):
    m = _VIEWBOX_RE.match(str(text or "").strip())
    if not m:
        raise ValueError("symbol.viewBox 无效: %s" % text)
    x, y, w, h = (float(m.group(i)) for i in range(1, 5))
    if w <= 0 or h <= 0:
        raise ValueError("symbol.viewBox 宽高必须为正")
    return x, y, w, h


def symbol_size(symbol):
    _x, _y, w, h = parse_viewbox(symbol["viewBox"])
    return w, h


def _normalize_anchor_entry(name, raw):
    if not isinstance(raw, dict):
        raise ValueError("symbol.anchors.%s 必须是对象" % name)
    tip = raw.get("tip")
    if not (isinstance(tip, (list, tuple)) and len(tip) == 2):
        raise ValueError("symbol.anchors.%s 缺少 tip [x,y]" % name)
    tip = [float(tip[0]), float(tip[1])]
    back = raw.get("back")
    if back is not None:
        if not (isinstance(back, (list, tuple)) and len(back) == 2):
            raise ValueError("symbol.anchors.%s.back 必须是 [x,y]" % name)
        back = [float(back[0]), float(back[1])]
    side = raw.get("side")
    if side is not None:
        side = str(side).upper()
        if side not in _SIDES:
            raise ValueError("symbol.anchors.%s.side 无效" % name)
    return {"tip": tip, "back": back, "side": side}


def validate_symbol(name, symbol, ports):
    if not isinstance(symbol, dict):
        raise ValueError("lib %s symbol 必须是对象" % name)
    parse_viewbox(symbol.get("viewBox"))
    svg = symbol.get("svg")
    if not isinstance(svg, str) or not svg.strip():
        raise ValueError("lib %s symbol 缺少 svg" % name)
    anchors = symbol.get("anchors")
    if not isinstance(anchors, dict) or not anchors:
        raise ValueError("lib %s symbol 缺少 anchors" % name)
    port_names = {p.get("name") for p in (ports or []) if isinstance(p, dict) and p.get("name")}
    for pname in port_names:
        if pname not in anchors:
            raise ValueError("lib %s symbol.anchors 缺少端口 %s" % (name, pname))
    for key, raw in anchors.items():
        _normalize_anchor_entry(key, raw)


def default_back(tip, side):
    x, y = tip
    d = ANCHOR_BACK
    if side == "WEST":
        return [x - d, y]
    if side == "EAST":
        return [x + d, y]
    if side == "SOUTH":
        return [x, y + d]
    if side == "NORTH":
        return [x, y - d]
    return [x - d, y]


def anchor_record(symbol, port_name):
    anchors = symbol.get("anchors") or {}
    raw = anchors.get(port_name)
    if not raw:
        return None
    rec = _normalize_anchor_entry(port_name, raw)
    side = rec["side"]
    if not side:
        tx, ty = rec["tip"]
        _x, _y, w, h = parse_viewbox(symbol["viewBox"])
        if tx <= 0.5:
            side = "WEST"
        elif tx >= w - 0.5:
            side = "EAST"
        elif ty >= h - 0.5:
            side = "SOUTH"
        elif ty <= 0.5:
            side = "NORTH"
        else:
            side = "WEST"
        rec["side"] = side
    if rec["back"] is None:
        rec["back"] = default_back(rec["tip"], rec["side"])
    return rec


def canvas_anchor(symbol, port_name, node_x, node_y):
    rec = anchor_record(symbol, port_name)
    if not rec:
        return None
    tip = rec["tip"]
    back = rec["back"]
    return {
        "tip": (node_x + tip[0], node_y + tip[1]),
        "back": (node_x + back[0], node_y + back[1]),
        "side": rec["side"],
    }


def place_elk_ports_from_symbol(elk_ports, symbol, kept):
    del kept
    positions = {}
    for port in elk_ports:
        name = (port.get("properties") or {}).get("name")
        if not name:
            continue
        rec = anchor_record(symbol, name)
        if rec:
            positions[name] = tuple(rec["tip"])
    for port in elk_ports:
        name = (port.get("properties") or {}).get("name")
        if name not in positions:
            continue
        port["x"], port["y"] = positions[name]
        side = anchor_record(symbol, name)["side"]
        opts = dict(port.get("layoutOptions") or {})
        opts["elk.port.side"] = side
        port["layoutOptions"] = opts


def tint_symbol_svg(svg, fill, stroke):
    """Substitute palette colors; keep swatch-fill / gate-stroke classes for the viewer."""
    return (svg or "").replace("__FILL__", fill).replace("__STROKE__", stroke)


def symbol_svg_document(symbol, fill, stroke):
    _x, _y, w, h = parse_viewbox(symbol["viewBox"])
    inner = tint_symbol_svg(symbol.get("svg") or "", fill, stroke)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %.4f %.4f" width="%.4f" height="%.4f">'
        "%s</svg>"
        % (w, h, w, h, inner)
    )


def svg_data_uri(svg_text):
    text = (svg_text or "").strip()
    if text.startswith("<?xml"):
        text = text.split("?>", 1)[-1].strip()
    encoded = urllib.parse.quote(text, safe="")
    return "data:image/svg+xml," + encoded


def resolve_node_symbol(node, libs):
    if isinstance(node.get("symbol"), dict) and node["symbol"].get("svg"):
        return node["symbol"]
    props = node.get("properties") or {}
    sym = props.get("symbol")
    if isinstance(sym, dict) and sym.get("svg"):
        return sym
    lib_name = props.get("module_lib") or ""
    if not lib_name and isinstance(node.get("meta"), dict):
        lib_name = node["meta"].get("lib") or ""
    if lib_name and isinstance(libs, dict):
        body = libs.get(lib_name)
        if isinstance(body, dict):
            sym = body.get("symbol")
            if isinstance(sym, dict) and sym.get("svg"):
                return sym
    return None


def is_cell_node(node, libs):
    shape = (node.get("properties") or {}).get("shape") or node.get("shape") or ""
    if shape != "cell":
        return False
    return resolve_node_symbol(node, libs) is not None
