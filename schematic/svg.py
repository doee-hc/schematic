"""Render a laid-out ELK graph to SVG, then add small hop jumpers."""

import math

from schematic.graph import LOGIC_LINE_H, PORT_H, PORT_TIP, wrap_expr
from schematic.style import SHAPE_FILL, SHAPE_STROKE, color_for, darken, pick_swatch
from schematic.symbol import canvas_anchor, is_cell_node, resolve_node_symbol, tint_symbol_svg

JUMP_R = 2.0
EPS = 0.6
ARROW_LEN = 8.0
ARROW_HALF = 3.0
PORT_APPROACH_STUB = 14.0
LOGIC_TITLE_Y = 16.0
LOGIC_BODY_TOP = 20.0
LOGIC_SEQ_NOTCH = 9.0


def _logic_text_baselines(y, h, expr_line_count, seq=False):
    """标题固定在框顶；expr 在标题下方剩余区域内垂直居中。"""
    title_y = y + LOGIC_TITLE_Y
    if not expr_line_count:
        return title_y, None
    body_bottom = y + h - (LOGIC_SEQ_NOTCH if seq else 2.0)
    body_h = max(0.0, body_bottom - (y + LOGIC_BODY_TOP))
    expr_block_h = expr_line_count * LOGIC_LINE_H
    expr_block_top = y + LOGIC_BODY_TOP + max(0.0, (body_h - expr_block_h) / 2.0)
    expr_start = expr_block_top + 9.0
    return title_y, expr_start
PAD = 16.0
PORT_FILL = "#fffef6"
PORT_STROKE = "#333"
EDGE_HIT_WIDTH = 12.0
INVERT_R = 3.5


def _esc(text):
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _svg_title(text):
    if not text or not str(text).strip():
        return ""
    return "<title>%s</title>" % _esc(str(text))


def _port_desc(port):
    return (port.get("properties") or {}).get("desc") or ""


def _port_label(port):
    labels = port.get("labels") or []
    if labels and labels[0].get("text"):
        return labels[0].get("text") or ""
    props = port.get("properties") or {}
    return props.get("label") or props.get("name") or _port_name(port)


def _node_tooltip_text(node):
    parts = []
    title = _node_title(node)
    if title:
        parts.append(title)
    lib = _prop(node, "module_lib")
    if lib:
        parts.append("lib: %s" % lib)
    desc = _prop(node, "desc")
    if desc and desc != title:
        parts.append(desc)
    note = _prop(node, "note")
    if note and note not in (desc, title):
        parts.append(note)
    port_lines = []
    for port in node.get("ports") or []:
        name = (port.get("properties") or {}).get("name") or _port_name(port)
        pd = _port_desc(port)
        label = _port_label(port)
        if pd:
            tag = label if label else name
            port_lines.append("%s — %s" % (tag, pd) if tag else pd)
        elif label or name:
            line = label or name
            if label and name and label != name:
                line = "%s (%s)" % (label, name)
            port_lines.append(line)
    if port_lines:
        if parts:
            parts.append("")
        parts.append("引脚:")
        parts.extend(port_lines)
    return "\n".join(parts)


def _abs_origins(node, ox=0.0, oy=0.0, acc=None):
    if acc is None:
        acc = {}
    x = ox + float(node.get("x") or 0)
    y = oy + float(node.get("y") or 0)
    acc[node["id"]] = (x, y)
    for child in node.get("children") or []:
        _abs_origins(child, x, y, acc)
    return acc


def _iter_nodes(node):
    yield node
    for child in node.get("children") or []:
        for item in _iter_nodes(child):
            yield item


def _iter_edges(node):
    for edge in node.get("edges") or []:
        yield edge
    for child in node.get("children") or []:
        for edge in _iter_edges(child):
            yield edge


def _section_points(section):
    pts = [section.get("startPoint")]
    pts.extend(section.get("bendPoints") or [])
    pts.append(section.get("endPoint"))
    out = []
    for pt in pts:
        if not pt:
            continue
        out.append((float(pt["x"]), float(pt["y"])))
    return out


def _force_ortho(pts):
    if not pts:
        return pts
    out = [pts[0]]
    for pt in pts[1:]:
        prev = out[-1]
        dx = abs(prev[0] - pt[0])
        dy = abs(prev[1] - pt[1])
        if dx < EPS and dy < EPS:
            continue
        if dy < EPS:
            out.append((pt[0], prev[1]))
        elif dx < EPS:
            out.append((prev[0], pt[1]))
        else:
            out.append((pt[0], prev[1]))
            out.append(pt)
    cleaned = [out[0]]
    for pt in out[1:]:
        if abs(cleaned[-1][0] - pt[0]) < 0.05 and abs(cleaned[-1][1] - pt[1]) < 0.05:
            continue
        cleaned.append(pt)
    return cleaned


def _offset_pts(pts, origin):
    ox, oy = origin
    return [(x + ox, y + oy) for x, y in pts]


def _edge_origin(edge, origins):
    container = edge.get("container")
    if container and container in origins:
        return origins[container]
    return (0.0, 0.0)


def _overlap_1d(a1, a2, b1, b2):
    lo = max(min(a1, a2), min(b1, b2))
    hi = min(max(a1, a2), max(b1, b2))
    return hi - lo > 1.0


def _seg_intersect(a1, a2, b1, b2):
    ax1, ay1 = a1
    ax2, ay2 = a2
    bx1, by1 = b1
    bx2, by2 = b2
    a_h = abs(ay1 - ay2) < EPS and abs(ax1 - ax2) >= EPS
    a_v = abs(ax1 - ax2) < EPS and abs(ay1 - ay2) >= EPS
    b_h = abs(by1 - by2) < EPS and abs(bx1 - bx2) >= EPS
    b_v = abs(bx1 - bx2) < EPS and abs(by1 - by2) >= EPS
    if a_h and b_v:
        x, y = bx1, ay1
        if min(ax1, ax2) + EPS < x < max(ax1, ax2) - EPS and min(by1, by2) + EPS < y < max(by1, by2) - EPS:
            return (x, y)
    if a_v and b_h:
        x, y = ax1, by1
        if min(ay1, ay2) + EPS < y < max(ay1, ay2) - EPS and min(bx1, bx2) + EPS < x < max(bx1, bx2) - EPS:
            return (x, y)
    return None


def _collect_jumps(routes):
    jumps = [[] for _ in routes]
    for i, pts_a in enumerate(routes):
        for sa in range(len(pts_a) - 1):
            for j in range(i + 1, len(routes)):
                pts_b = routes[j]
                for sb in range(len(pts_b) - 1):
                    hit = _seg_intersect(pts_a[sa], pts_a[sa + 1], pts_b[sb], pts_b[sb + 1])
                    if hit is None:
                        continue
                    x, y = hit
                    if abs(pts_a[sa][0] - pts_a[sa + 1][0]) < EPS:
                        jumps[i].append((sa, x, y))
                    else:
                        jumps[j].append((sb, x, y))
    return jumps


def jump_polyline(pts, hops, radius=JUMP_R):
    """Orthogonal polyline with jump arcs tessellated (for draw.io edges)."""
    by_seg = {}
    for seg, _x, y in hops:
        by_seg.setdefault(seg, []).append(y)
    out = [pts[0]]
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        seg_hops = by_seg.get(i, [])
        if not seg_hops or abs(x1 - x2) >= EPS:
            if out[-1] != (x2, y2):
                out.append((x2, y2))
            continue
        going_down = y2 > y1
        ordered = sorted(seg_hops, reverse=not going_down)
        used = []
        for yc in ordered:
            if abs(yc - y1) < radius * 2.4 or abs(yc - y2) < radius * 2.4:
                continue
            if used and abs(yc - used[-1]) < radius * 2.6:
                continue
            used.append(yc)
        for yc in used:
            if going_down:
                out.append((x1, yc - radius))
                _append_semi_arc(out, x1, yc, radius, going_down=True)
            else:
                out.append((x1, yc + radius))
                _append_semi_arc(out, x1, yc, radius, going_down=False)
        if out[-1] != (x2, y2):
            out.append((x2, y2))
    return out


def _append_semi_arc(out, x, yc, radius, going_down, steps=6):
    cx = x + radius
    cy = yc
    if going_down:
        start, end = math.pi, 0.0
    else:
        start, end = 0.0, math.pi
    for i in range(1, steps):
        t = i / float(steps)
        ang = start + (end - start) * t
        pt = (cx + radius * math.cos(ang), cy + radius * math.sin(ang))
        if out[-1] != pt:
            out.append(pt)


def _path_d(pts, hops, radius=JUMP_R):
    by_seg = {}
    for seg, _x, y in hops:
        by_seg.setdefault(seg, []).append(y)
    parts = ["M%.2f,%.2f" % pts[0]]
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        seg_hops = by_seg.get(i, [])
        if not seg_hops or abs(x1 - x2) >= EPS:
            parts.append("L%.2f,%.2f" % (x2, y2))
            continue
        going_down = y2 > y1
        ordered = sorted(seg_hops, reverse=not going_down)
        used = []
        for yc in ordered:
            if abs(yc - y1) < radius * 2.4 or abs(yc - y2) < radius * 2.4:
                continue
            if used and abs(yc - used[-1]) < radius * 2.6:
                continue
            used.append(yc)
        if going_down:
            for yc in used:
                parts.append("L%.2f,%.2f" % (x1, yc - radius))
                parts.append("A%.2f,%.2f 0 0 1 %.2f,%.2f" % (radius, radius, x1, yc + radius))
        else:
            for yc in used:
                parts.append("L%.2f,%.2f" % (x1, yc + radius))
                parts.append("A%.2f,%.2f 0 0 0 %.2f,%.2f" % (radius, radius, x1, yc - radius))
        parts.append("L%.2f,%.2f" % (x2, y2))
    return "".join(parts)


def _arrow(base, tip):
    dx = tip[0] - base[0]
    dy = tip[1] - base[1]
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    left = (base[0] + px * ARROW_HALF, base[1] + py * ARROW_HALF)
    right = (base[0] - px * ARROW_HALF, base[1] - py * ARROW_HALF)
    return " ".join("%.2f,%.2f" % pt for pt in (left, tip, right, left))


def _edge_swatch(edge):
    props = edge.get("properties") or {}
    return props.get("swatch") or ""


def _port_swatch(port):
    props = port.get("properties") or {}
    return props.get("swatch") or ""


def _port_swatch_map(graph):
    acc = {}
    for node in _iter_nodes(graph):
        for port in node.get("ports") or []:
            key = _port_swatch(port)
            if key and port.get("id"):
                acc[port["id"]] = key
    return acc


def _shape(node):
    props = node.get("properties") or {}
    return props.get("shape") or "box"


def _prop(node, key):
    props = node.get("properties") or {}
    val = props.get(key)
    if val is None or val is False:
        return ""
    return val


SYMBOL_PORT_LABEL_INSET = 6.0


def _symbol_port_label(tip, side):
    """Port name just inside the lib symbol, aligned with the anchor tip."""
    tx, ty = tip
    side = (side or "WEST").upper()
    dy = 3.0
    inset = SYMBOL_PORT_LABEL_INSET
    if side == "EAST":
        return tx - inset, ty + dy, "end"
    if side == "SOUTH":
        return tx, ty - inset, "middle"
    if side == "NORTH":
        return tx, ty + inset + dy, "middle"
    return tx + inset, ty + dy, "start"


def _box_snap_port_label(tip, side, x, y, w, h):
    """Port name on reg / logic / box border (inside the node rectangle)."""
    _tx, ty = tip
    side = (side or "WEST").upper()
    dy = 3.0
    if side == "EAST":
        return x + w - 5, max(y + 18.0, min(y + h - 6.0, ty + dy)), "end"
    if side == "SOUTH":
        return x + w / 2.0, y + h - 3.0, "middle"
    if side == "NORTH":
        return x + w / 2.0, y + 3.0, "middle"
    return x + 6, max(y + 18.0, min(y + h - 6.0, ty + dy)), "start"


def _node_title(node):
    labels = node.get("labels") or []
    if labels:
        return labels[0].get("text") or node["id"]
    return node["id"]


def _port_name(port):
    labels = port.get("labels") or []
    if labels and labels[0].get("text"):
        return labels[0]["text"]
    return port["id"].split("__")[-1]


def _port_side(port, node_w=0.0):
    options = port.get("layoutOptions") or {}
    side = options.get("elk.port.side") or options.get("port.side") or ""
    if side:
        return side
    px = float(port.get("x") or 0)
    return "EAST" if node_w and px > node_w * 0.5 else "WEST"


def _port_geom(node_x, node_y, node_w, node_h, port):
    side = _port_side(port, node_w)
    px = node_x + float(port.get("x") or 0)
    py = node_y + float(port.get("y") or 0)
    pw = float(port.get("width") or 0)
    ph = float(port.get("height") or PORT_H)
    if pw <= 0:
        pw = 24.0
    if ph <= 0:
        ph = PORT_H
    cy = py + ph / 2.0
    if side == "EAST":
        tip = (px, cy)
        back = (px + pw, cy)
    elif side == "SOUTH":
        cx = px + pw / 2.0
        tip = (cx, py)
        back = (cx, py + ph)
    elif side == "NORTH":
        cx = px + pw / 2.0
        tip = (cx, py + ph)
        back = (cx, py)
    else:
        tip = (px + pw, cy)
        back = (px, cy)
    return {
        "id": port.get("id"),
        "side": side,
        "x": px,
        "y": py,
        "w": pw,
        "h": ph,
        "tip": tip,
        "back": back,
        "name": _port_name(port),
        "swatch": _port_swatch(port),
    }


def _collect_ports(graph, origins, libs=None):
    pins = {}
    labels = []
    for node in _iter_nodes(graph):
        if node.get("id") == "root":
            continue
        x, y = origins[node["id"]]
        w = float(node.get("width") or 0)
        h = float(node.get("height") or 0)
        compound = bool(node.get("children"))
        shape = _shape(node)
        if is_cell_node(node, libs) and not compound:
            sym = resolve_node_symbol(node, libs)
            for port in node.get("ports") or []:
                boxed = float(port.get("width") or 0) > 1.0
                if boxed:
                    pins[port["id"]] = _port_geom(x, y, w, h, port)
                    continue
                name = _port_name(port)
                pname = (port.get("properties") or {}).get("name") or name
                anch = canvas_anchor(sym, pname, x, y)
                if not anch:
                    continue
                side = anch["side"] or _port_side(port, w)
                geom = _port_geom(x, y, w, h, port)
                geom["tip"] = anch["tip"]
                geom["back"] = anch["back"]
                geom["border"] = anch["tip"]
                geom["side"] = side
                geom["shape"] = "snap"
                pins[port["id"]] = geom
                tx, ty, anchor = _symbol_port_label(anch["tip"], side)
                labels.append((node["id"], tx, ty, anchor, name, _port_swatch(port), port["id"]))
            continue
        for port in node.get("ports") or []:
            boxed = float(port.get("width") or 0) > 1.0
            if compound or boxed:
                pins[port["id"]] = _port_geom(x, y, w, h, port)
                continue
            side = _port_side(port, w)
            name = _port_name(port)
            py = y + float(port.get("y") or 0)
            geom = _port_geom(x, y, w, h, port)
            py_mid = y + float(port.get("y") or 0) + float(port.get("height") or 0) / 2.0
            if py_mid <= y + 0.5 or py_mid >= y + h - 0.5:
                py_mid = y + h / 2.0
            if side == "WEST":
                geom["tip"] = (x, py_mid)
                geom["back"] = (x - 6.0, py_mid)
            elif side == "EAST":
                geom["tip"] = (x + w, py_mid)
                geom["back"] = (x + w + 6.0, py_mid)
            elif side == "SOUTH":
                cx = x + float(port.get("x") or 0)
                if abs(cx - x) < 0.5:
                    cx = x + w / 2.0
                geom["tip"] = (cx, y + h)
                geom["back"] = (cx, y + h + 6.0)
            else:
                geom["tip"] = (x + w / 2.0, y)
                geom["back"] = (x + w / 2.0, y - 6.0)
            geom["shape"] = "snap"
            pins[port["id"]] = geom
            if shape == "logic":
                continue
            tx, ty, anchor = _box_snap_port_label(geom["tip"], side, x, y, w, h)
            labels.append((node["id"], tx, ty, anchor, name, _port_swatch(port), port["id"]))
    return pins, labels


def _attach(geom, other):
    if geom.get("shape") == "snap":
        return geom["tip"]
    if geom["side"] == "WEST":
        return geom["tip"] if other[0] >= geom["tip"][0] - 0.5 else geom["back"]
    if geom["side"] in ("SOUTH", "NORTH"):
        return geom["tip"]
    return geom["tip"] if other[0] <= geom["tip"][0] + 0.5 else geom["back"]


def _snap_end(pts, geom, at_start):
    if not pts:
        return pts
    other = pts[1] if at_start and len(pts) > 1 else (pts[-2] if len(pts) > 1 else pts[0])
    tip = _attach(geom, other)
    side = (geom.get("side") or "EAST").upper()
    stub = PORT_APPROACH_STUB

    if at_start:
        pts[0] = tip
        if len(pts) < 2:
            return pts
        nxt = pts[1]
        if side in ("WEST", "EAST"):
            if abs(tip[1] - nxt[1]) >= EPS:
                stub_x = tip[0] - stub if side == "WEST" else tip[0] + stub
                pts.insert(1, (stub_x, tip[1]))
                if abs(nxt[0] - stub_x) > EPS and abs(nxt[1] - tip[1]) > EPS:
                    pts.insert(2, (nxt[0], tip[1]))
        elif abs(tip[0] - nxt[0]) >= EPS:
            stub_y = tip[1] - stub if side == "NORTH" else tip[1] + stub
            pts.insert(1, (tip[0], stub_y))
            if abs(nxt[0] - tip[0]) > EPS and abs(nxt[1] - stub_y) > EPS:
                pts.insert(2, (tip[0], nxt[1]))
        return pts

    prev = pts[-2] if len(pts) > 1 else tip
    pts[-1] = tip
    if side in ("WEST", "EAST"):
        if abs(prev[1] - tip[1]) < EPS and abs(prev[0] - tip[0]) > EPS:
            return pts
        if abs(prev[0] - tip[0]) < EPS:
            stub_x = tip[0] - stub if side == "WEST" else tip[0] + stub
            pts.insert(-1, (stub_x, tip[1]))
        elif abs(prev[1] - tip[1]) > EPS:
            pts.insert(-1, (prev[0], tip[1]))
    else:
        if abs(prev[0] - tip[0]) < EPS and abs(prev[1] - tip[1]) > EPS:
            return pts
        if abs(prev[1] - tip[1]) < EPS:
            stub_y = tip[1] - stub if side == "NORTH" else tip[1] + stub
            pts.insert(-1, (tip[0], stub_y))
        elif abs(prev[0] - tip[0]) > EPS:
            pts.insert(-1, (tip[0], prev[1]))
    return pts


def _section_shapes(section):
    return section.get("incomingShape"), section.get("outgoingShape")


def _pentagon(geom):
    x, y, w, h = geom["x"], geom["y"], geom["w"], geom["h"]
    tip = min(PORT_TIP, max(4.0, w * 0.35))
    if geom["side"] == "WEST":
        pts = [
            (x, y),
            (x + w - tip, y),
            (x + w, y + h / 2.0),
            (x + w - tip, y + h),
            (x, y + h),
        ]
        tx = x + (w - tip) / 2.0
        ty = y + h / 2.0 + 3.5
    elif geom["side"] == "SOUTH":
        pts = [
            (x, y),
            (x + w, y),
            (x + w, y + h - tip),
            (x + w / 2.0, y + h),
            (x, y + h - tip),
        ]
        tx = x + w / 2.0
        ty = y + (h - tip) / 2.0 + 3.5
    else:
        pts = [
            (x, y + h / 2.0),
            (x + tip, y),
            (x + w, y),
            (x + w, y + h),
            (x + tip, y + h),
        ]
        tx = x + tip + (w - tip) / 2.0
        ty = y + h / 2.0 + 3.5
    return pts, tx, ty


def _cell_title_pos(node, x, y, w):
    del node
    return x + w / 2.0, y - 4.0


def _poly(pts):
    return " ".join("%.2f,%.2f" % pt for pt in pts)


def _cell_port_label_svg(port_labels, palette, port_desc_by_id):
    chunks = []
    for _nid, tx, ty, anchor, name, swatch, port_id in port_labels or []:
        fill = darken(color_for(palette, swatch, "#333"), 0.15) if swatch else "#333"
        pdesc = port_desc_by_id.get(port_id, "")
        if pdesc:
            port_tip = _svg_title("%s: %s" % (name, pdesc))
        elif name:
            port_tip = _svg_title(name)
        else:
            port_tip = ""
        chunks.append(
            '<g class="port port-text" data-id="%s" data-swatch="%s" pointer-events="all">'
            "%s"
            '<text class="port-label port-label-hit" pointer-events="all" data-swatch="%s" '
            'x="%.2f" y="%.2f" text-anchor="%s" font-family="DejaVu Sans, sans-serif" font-size="10" '
            'fill="%s">%s</text>'
            "</g>"
            % (_esc(port_id), _esc(swatch), port_tip, _esc(swatch), tx, ty, anchor, fill, _esc(name))
        )
    return "".join(chunks)


def _symbol_node_svg(node, x, y, w, h, palette, libs, port_labels=None, port_desc_by_id=None):
    sym = resolve_node_symbol(node, libs)
    if not sym:
        return ""
    swatch = _prop(node, "swatch")
    fill = color_for(palette, swatch, SHAPE_FILL.get("cell", "#e7f0fb"))
    stroke = SHAPE_STROKE.get("cell") or darken(fill)
    title = _esc(_node_title(node))
    nid = _esc(node["id"])
    mod_lib = _prop(node, "module_lib") or ""
    attrs = 'class="node" data-id="%s" data-shape="cell" data-swatch="%s"' % (
        nid, _esc(swatch),
    )
    if mod_lib:
        attrs += ' data-module-lib="%s"' % _esc(mod_lib)
    attrs += ' data-symbol-cell="true"'
    inner = tint_symbol_svg(sym.get("svg") or "", fill, stroke)
    node_tooltip = _svg_title(_node_tooltip_text(node))
    port_desc_by_id = port_desc_by_id or {}
    port_svg = _cell_port_label_svg(port_labels, palette, port_desc_by_id)
    return (
        "<g %s>"
        "%s"
        '<rect class="node-hit" x="%.2f" y="%.2f" width="%.2f" height="%.2f" '
        'fill="transparent" pointer-events="all"/>'
        '<g transform="translate(%.2f,%.2f)">%s</g>'
        '<text class="gate-title" x="%.2f" y="%.2f" text-anchor="middle" '
        'font-family="DejaVu Sans, sans-serif" font-size="11" font-weight="700" fill="#111">%s</text>'
        "%s"
        "</g>"
        % (
            attrs, node_tooltip, x, y, w, h, x, y, inner,
            x + w / 2.0, y - 4.0, title, port_svg,
        )
    )


def _node_svg(node, x, y, w, h, palette, libs=None, port_labels=None, port_desc_by_id=None):
    if is_cell_node(node, libs):
        return _symbol_node_svg(
            node, x, y, w, h, palette, libs,
            port_labels=port_labels, port_desc_by_id=port_desc_by_id,
        )
    shape = _shape(node)
    swatch = _prop(node, "swatch")
    title = _esc(_node_title(node))
    note = _prop(node, "note")
    expr = _prop(node, "expr")
    badge_text = _prop(node, "badge")
    fill = color_for(palette, swatch, SHAPE_FILL.get(shape, "#fff"))
    stroke = SHAPE_STROKE.get(shape) or darken(fill)
    nid = _esc(node["id"])
    mod_use = _prop(node, "module_use") or ""
    mod_lib = _prop(node, "module_lib") or ""
    mod_stub = "true" if _prop(node, "module_stub") else "false"
    attrs = 'class="node" data-id="%s" data-shape="%s" data-swatch="%s"' % (
        nid, _esc(shape), _esc(swatch),
    )
    if mod_use:
        attrs += ' data-module-use="%s" data-module-stub="%s"' % (
            _esc(mod_use), mod_stub,
        )
    if mod_lib:
        attrs += ' data-module-lib="%s"' % _esc(mod_lib)
    node_tooltip = _svg_title(_node_tooltip_text(node))
    if mod_use and mod_stub != "true":
        title_h = min(22.0, h)
        node_hit = (
            '<rect class="node-hit node-hit-chrome" x="%.2f" y="%.2f" width="%.2f" height="%.2f" '
            'fill="transparent" pointer-events="all"/>'
            % (x, y, w, title_h)
        )
    else:
        node_hit = (
            '<rect class="node-hit" x="%.2f" y="%.2f" width="%.2f" height="%.2f" '
            'fill="transparent" pointer-events="all"/>'
            % (x, y, w, h)
        )
    if shape == "reg":
        cx = x + w / 2.0
        clock = "%.2f,%.2f %.2f,%.2f %.2f,%.2f" % (
            cx - 6.0, y + h, cx, y + h - 9.0, cx + 6.0, y + h,
        )
        extra = ""
        tooltip = node_tooltip or (_svg_title(note) if note else "")
        return (
            "<g %s>"
            "%s"
            '<rect class="swatch-fill" x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s" stroke="%s" stroke-width="1.2"/>'
            '<polygon fill="%s" stroke="%s" stroke-width="1" points="%s"/>'
            '<text x="%.2f" y="%.2f" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-size="12" font-weight="700" fill="#111">%s</text>'
            "%s"
            "</g>"
            % (attrs, tooltip, x, y, w, h, fill, stroke, stroke, stroke, clock, cx, y + 16, title, extra)
        )
    if shape == "logic":
        lines = wrap_expr(expr)
        lk = (_prop(node, "kind") or "comb").lower()
        if lk not in ("comb", "seq"):
            lk = "comb"
        if lk == "seq":
            attrs += ' data-logic-kind="seq"'
        tooltip_parts = []
        base = _node_tooltip_text(node)
        if base:
            tooltip_parts.append(base)
        if lk == "seq":
            tooltip_parts.append("时序 logic (kind=seq)")
        if expr:
            tooltip_parts.append(expr)
        tooltip = _svg_title("\n".join(tooltip_parts)) if tooltip_parts else ""
        cx = x + w / 2.0
        title_y, expr_start = _logic_text_baselines(y, h, len(lines), seq=(lk == "seq"))
        extra = ""
        if lines and expr_start is not None:
            tspans = "".join(
                '<tspan x="%.2f" y="%.2f">%s</tspan>'
                % (cx, expr_start + index * LOGIC_LINE_H, _esc(line))
                for index, line in enumerate(lines)
            )
            extra = (
                '<text text-anchor="middle" font-family="DejaVu Sans, sans-serif" '
                'font-size="9" fill="#333">%s</text>'
                % tspans
            )
        clock = ""
        if lk == "seq":
            clock = (
                '<polygon fill="%s" stroke="%s" stroke-width="1" points="%.2f,%.2f %.2f,%.2f %.2f,%.2f"/>'
                % (stroke, stroke, cx - 6.0, y + h, cx, y + h - LOGIC_SEQ_NOTCH, cx + 6.0, y + h)
            )
        return (
            "<g %s>"
            "%s"
            '<rect class="swatch-fill" x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="14" ry="14" fill="%s" stroke="%s" stroke-width="1.2"/>'
            "%s"
            '<text x="%.2f" y="%.2f" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-size="11" font-weight="700" fill="#111">%s</text>'
            "%s"
            "</g>"
            % (attrs, tooltip, x, y, w, h, fill, stroke, clock, cx, title_y, title, extra)
        )
    return (
        "<g %s>"
        "%s"
        "%s"
        '<rect class="swatch-fill" x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s" stroke="%s" stroke-width="1"/>'
        '<text x="%.2f" y="%.2f" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-size="12" font-weight="700" fill="#111">%s</text>'
        "</g>"
        % (attrs, node_tooltip, node_hit, x, y, w, h, fill, stroke, x + w / 2.0, y + 14, title)
    )


def _expand_box(box, x, y):
    box[0] = min(box[0], x)
    box[1] = min(box[1], y)
    box[2] = max(box[2], x)
    box[3] = max(box[3], y)


def _port_desc_by_id(graph):
    acc = {}
    for node in _iter_nodes(graph):
        for port in node.get("ports") or []:
            pd = _port_desc(port)
            if port.get("id") and pd:
                acc[port["id"]] = pd
    return acc


def prepare_scene(graph, palette=None, libs=None):
    """Shared layout geometry for SVG and native draw.io export."""
    palette = palette or {}
    if libs is None:
        from schematic.elaborate import load_builtin_libs
        libs = load_builtin_libs()
    origins = _abs_origins(graph)
    pins, labels = _collect_ports(graph, origins, libs=libs)
    port_swatches = _port_swatch_map(graph)
    port_desc_by_id = _port_desc_by_id(graph)
    routes = []
    box = [0.0, 0.0, float(graph.get("width") or 0), float(graph.get("height") or 0)]

    for edge in _iter_edges(graph):
        origin = _edge_origin(edge, origins)
        pts = []
        src_id = tgt_id = None
        for section in edge.get("sections") or []:
            incoming, outgoing = _section_shapes(section)
            if incoming:
                src_id = incoming
            if outgoing:
                tgt_id = outgoing
            pts.extend(_offset_pts(_force_ortho(_section_points(section)), origin))
        if not src_id and (edge.get("sources") or []):
            src_id = edge["sources"][0]
        if not tgt_id and (edge.get("targets") or []):
            tgt_id = edge["targets"][0]
        pts = _force_ortho(pts)
        if len(pts) < 2:
            continue
        if src_id in pins:
            pts = _snap_end(pts, pins[src_id], True)
        if tgt_id in pins:
            pts = _snap_end(pts, pins[tgt_id], False)
        pts = _force_ortho(pts)
        if len(pts) < 2:
            continue
        tip = pts[-1]
        prev = pts[-2]
        dx = tip[0] - prev[0]
        dy = tip[1] - prev[1]
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        base = (tip[0] - ux * ARROW_LEN, tip[1] - uy * ARROW_LEN)
        if length > ARROW_LEN + 1:
            pts = pts[:-1] + [base]
        swatch = pick_swatch(
            _edge_swatch(edge),
            pins.get(src_id, {}).get("swatch") if src_id else "",
            pins.get(tgt_id, {}).get("swatch") if tgt_id else "",
            port_swatches.get(src_id),
            port_swatches.get(tgt_id),
        )
        invert = str((edge.get("properties") or {}).get("invert") or "") == "true"
        invert_pt = None
        if invert:
            cx = base[0] - ux * (INVERT_R + 1.0)
            cy = base[1] - uy * (INVERT_R + 1.0)
            pts = pts[:-1] + [(cx - ux * INVERT_R, cy - uy * INVERT_R)]
            invert_pt = (cx, cy)
            _expand_box(box, cx - INVERT_R, cy - INVERT_R)
            _expand_box(box, cx + INVERT_R, cy + INVERT_R)
        routes.append({
            "pts": pts,
            "swatch": swatch,
            "src": src_id or "",
            "dst": tgt_id or "",
            "arrow": (base, tip),
            "invert": invert_pt,
        })
        for x, y in pts:
            _expand_box(box, x, y)

    jumps = _collect_jumps([route["pts"] for route in routes])

    nodes = []
    for node in _iter_nodes(graph):
        if node.get("id") == "root":
            continue
        x, y = origins[node["id"]]
        w = float(node.get("width") or 0)
        h = float(node.get("height") or 0)
        if w <= 0 or h <= 0:
            continue
        _expand_box(box, x, y)
        _expand_box(box, x + w, y + h)
        if is_cell_node(node, libs):
            tx, ty = _cell_title_pos(node, x, y, w)
            tw = max(8.0, len(_node_title(node)) * 6.6)
            _expand_box(box, tx - tw / 2.0, ty - 12.0)
            _expand_box(box, tx + tw / 2.0, ty + 2.0)
        nodes.append(node)

    minx, miny, maxx, maxy = box
    width = max(40.0, maxx - minx + PAD * 2)
    height = max(40.0, maxy - miny + PAD * 2)
    return {
        "palette": palette,
        "origins": origins,
        "pins": pins,
        "labels": labels,
        "routes": routes,
        "jumps": jumps,
        "nodes": nodes,
        "port_desc_by_id": port_desc_by_id,
        "canvas": {
            "width": width,
            "height": height,
            "ox": PAD - minx,
            "oy": PAD - miny,
        },
    }


def render_svg(graph, palette=None, libs=None):
    scene = prepare_scene(graph, palette, libs=libs)
    palette = scene["palette"]
    origins = scene["origins"]
    pins = scene["pins"]
    labels = scene["labels"]
    routes = scene["routes"]
    jumps = scene["jumps"]
    port_desc_by_id = scene["port_desc_by_id"]
    canvas = scene["canvas"]

    cell_ids = {
        n["id"] for n in scene["nodes"]
        if is_cell_node(n, libs) and not n.get("children")
    }
    labels_by_node = {}
    free_labels = []
    for item in labels:
        nid = item[0]
        if nid in cell_ids:
            labels_by_node.setdefault(nid, []).append(item)
        else:
            free_labels.append(item)

    node_parts = []
    for node in scene["nodes"]:
        x, y = origins[node["id"]]
        w = float(node.get("width") or 0)
        h = float(node.get("height") or 0)
        node_parts.append(
            _node_svg(
                node, x, y, w, h, palette, libs=libs,
                port_labels=labels_by_node.get(node["id"]),
                port_desc_by_id=port_desc_by_id,
            )
        )

    edge_over = []
    for idx, (route, hops) in enumerate(zip(routes, jumps)):
        pts = route["pts"]
        swatch = route["swatch"]
        stroke = color_for(palette, swatch, "#111") if swatch else "#111"
        path_d = _path_d(pts, hops)
        hit_path = (
            '<path class="edge-hit" fill="none" stroke="transparent" stroke-width="%.1f" '
            'pointer-events="stroke" d="%s"/>'
            % (EDGE_HIT_WIDTH, path_d)
        )
        chunks = [
            '<path class="swatch-stroke edge-stroke" fill="none" stroke="%s" stroke-width="1.2" d="%s"/>'
            % (stroke, path_d),
        ]
        invert_pt = route.get("invert")
        if invert_pt:
            cx, cy = invert_pt
            chunks.append(
                '<circle class="edge-invert" data-swatch="%s" cx="%.2f" cy="%.2f" r="%.2f" '
                'fill="#fff" stroke="%s" stroke-width="1.2"/>'
                % (_esc(swatch), cx, cy, INVERT_R, stroke)
            )
        base, tip = route["arrow"]
        chunks.append(
            '<polygon class="edge-arrow swatch-stroke edge-pick" data-swatch="%s" fill="%s" '
            'stroke="%s" pointer-events="all" points="%s"/>'
            % (_esc(swatch), stroke, stroke, _arrow(base, tip))
        )
        chunks.append(hit_path)
        edge_over.append(
            '<g class="edge" data-swatch="%s" data-src="%s" data-dst="%s" data-edge-id="%d">%s</g>'
            % (_esc(swatch), _esc(route["src"]), _esc(route["dst"]), idx, "".join(chunks))
        )

    parts = node_parts + edge_over

    for geom in pins.values():
        if geom.get("shape") == "snap":
            continue
        poly, tx, ty = _pentagon(geom)
        swatch = geom.get("swatch") or ""
        fill = color_for(palette, swatch, PORT_FILL) if swatch else PORT_FILL
        stroke = darken(fill, 0.45) if swatch else PORT_STROKE
        pname = geom.get("name") or ""
        pdesc = port_desc_by_id.get(geom.get("id") or "", "")
        if pdesc:
            port_tip = _svg_title("%s: %s" % (pname, pdesc))
        elif pname:
            port_tip = _svg_title(pname)
        else:
            port_tip = ""
        parts.append(
            '<g class="port" data-id="%s" data-swatch="%s" pointer-events="all">'
            "%s"
            '<circle class="port-hit" cx="%.2f" cy="%.2f" r="12" fill="transparent" stroke="none"/>'
            '<polygon class="swatch-fill port-shape" fill="%s" stroke="%s" stroke-width="1" points="%s"/>'
            '<text class="port-label port-label-hit" pointer-events="all" x="%.2f" y="%.2f" '
            'text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-size="10" fill="#222">%s</text>'
            "</g>"
            % (
                _esc(geom["id"]), _esc(swatch), port_tip, tx, ty,
                fill, stroke, _poly(poly), tx, ty, _esc(pname),
            )
        )

    for _nid, tx, ty, anchor, name, swatch, port_id in free_labels:
        fill = darken(color_for(palette, swatch, "#333"), 0.15) if swatch else "#333"
        pdesc = port_desc_by_id.get(port_id, "")
        if pdesc:
            port_tip = _svg_title("%s: %s" % (name, pdesc))
        elif name:
            port_tip = _svg_title(name)
        else:
            port_tip = ""
        parts.append(
            '<g class="port port-text" data-id="%s" data-swatch="%s" pointer-events="all">'
            "%s"
            '<text class="port-label port-label-hit" pointer-events="all" data-swatch="%s" '
            'x="%.2f" y="%.2f" text-anchor="%s" font-family="DejaVu Sans, sans-serif" font-size="10" '
            'fill="%s">%s</text>'
            "</g>"
            % (_esc(port_id), _esc(swatch), port_tip, _esc(swatch), tx, ty, anchor, fill, _esc(name))
        )

    width = canvas["width"]
    height = canvas["height"]
    inner = "\n".join(parts)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="%.2f" height="%.2f" viewBox="0 0 %.2f %.2f">\n'
        '<rect width="100%%" height="100%%" fill="#fff"/>\n'
        '<g transform="translate(%.2f,%.2f)">\n%s\n</g>\n</svg>\n'
        % (width, height, width, height, canvas["ox"], canvas["oy"], inner)
    )
