"""Render a laid-out ELK graph to SVG, then add small hop jumpers."""

import math

from schematic.graph import (
    GATE_MARGIN,
    GATE_PAD_Y,
    GATE_SHAPES,
    LOGIC_LINE_H,
    PORT_H,
    PORT_TIP,
    XOR_GAP,
    wrap_expr,
)
from schematic.style import SHAPE_FILL, SHAPE_STROKE, color_for, darken, pick_swatch

JUMP_R = 2.0
EPS = 0.6
ARROW_LEN = 8.0
ARROW_HALF = 3.0
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
MUX_INSET_X = 3.0
MUX_END_PAD = 4.0
MUX_SLANT_FRAC = 0.22
BUBBLE_R = 3.5
LABEL_DY = 3.6


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
    return props.get(key) or ""


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


def _collect_ports(graph, origins):
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
            if shape == "mux":
                along = geom["tip"][1] if side in ("WEST", "EAST") else geom["tip"][0]
                geom["tip"] = _mux_border_point(x, y, w, h, side, along)
            gate_name = ""
            if shape in GATE_SHAPES:
                gate_name = (port.get("properties") or {}).get("name") or _port_name(port)
                bubble = str((port.get("properties") or {}).get("bubble") or "") == "true"
                along = geom["tip"][1] if side in ("WEST", "EAST") else geom["tip"][0]
                border = _gate_border_point(
                    x, y, w, h, shape, side, along, gate_name, _node_has_te(node),
                )
                geom["border"] = border
                geom["tip"] = _bubble_tip(border, side, bubble)
            geom["shape"] = "snap"
            pins[port["id"]] = geom
            if shape == "logic":
                continue
            if shape == "mux" and side == "EAST":
                continue
            if shape in GATE_SHAPES:
                if shape == "icg" and side == "WEST" and gate_name not in ("en", "te", "clk"):
                    continue
                tx, ty, anchor = _gate_label_pos(
                    x, y, w, h, shape, gate_name, geom.get("border") or geom["tip"],
                    _node_has_te(node), side,
                )
                labels.append((tx, ty, anchor, name, _port_swatch(port), port["id"]))
                continue
            metrics = _mux_metrics(x, y, w, h) if shape == "mux" else None
            if side == "EAST":
                tx, ty, anchor = x + w - 5, max(y + 18.0, min(y + h - 6.0, py + 3.0)), "end"
            elif side == "SOUTH" and metrics:
                bottom = (metrics["left_bot"] + metrics["right_bot"]) / 2.0
                tx, ty, anchor = (x + w / 2.0, bottom - 8.0, "middle")
            elif side == "SOUTH":
                tx, ty, anchor = x + w / 2.0, y + h - 3.0, "middle"
            elif metrics:
                tx, ty, anchor = (
                    metrics["left_x"] + 6.0,
                    max(metrics["left_top"] + 12.0, min(metrics["left_bot"] - 4.0, py + 3.0)),
                    "start",
                )
            else:
                tx, ty, anchor = x + 6, max(y + 18.0, min(y + h - 6.0, py + 3.0)), "start"
            labels.append((tx, ty, anchor, name, _port_swatch(port), port["id"]))
    return pins, labels


def _attach(geom, other):
    if geom.get("shape") == "snap":
        return geom["tip"]
    if geom["side"] == "WEST":
        return geom["tip"] if other[0] >= geom["tip"][0] - 0.5 else geom["back"]
    if geom["side"] in ("SOUTH", "NORTH"):
        return geom["tip"]
    return geom["tip"] if other[0] <= geom["tip"][0] + 0.5 else geom["back"]


def _snap_end(pts, attach, at_start):
    if at_start:
        nxt = pts[1]
        pts[0] = attach
        if abs(attach[0] - nxt[0]) > EPS and abs(attach[1] - nxt[1]) > EPS:
            pts.insert(1, (nxt[0], attach[1]))
    else:
        prev = pts[-2]
        pts[-1] = attach
        if abs(attach[0] - prev[0]) > EPS and abs(attach[1] - prev[1]) > EPS:
            pts.insert(-1, (prev[0], attach[1]))
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


def _mux_metrics(x, y, w, h):
    left_x = x + MUX_INSET_X
    right_x = x + w - MUX_INSET_X
    left_top = y + MUX_END_PAD
    left_bot = y + h - MUX_END_PAD
    slant = max(8.0, (left_bot - left_top) * MUX_SLANT_FRAC)
    slant = min(slant, (left_bot - left_top) / 2.0 - 4.0)
    return {
        "left_x": left_x,
        "right_x": right_x,
        "left_top": left_top,
        "left_bot": left_bot,
        "right_top": left_top + slant,
        "right_bot": left_bot - slant,
        "slant": slant,
    }


def _mux_polygon(x, y, w, h):
    m = _mux_metrics(x, y, w, h)
    return [
        (m["left_x"], m["left_top"]),
        (m["right_x"], m["right_top"]),
        (m["right_x"], m["right_bot"]),
        (m["left_x"], m["left_bot"]),
    ]


def _mux_border_point(x, y, w, h, side, along):
    m = _mux_metrics(x, y, w, h)
    if side == "WEST":
        return (m["left_x"], along)
    if side == "EAST":
        return (m["right_x"], along)
    if side == "SOUTH":
        span = m["right_x"] - m["left_x"]
        t = 0.5 if abs(span) < 1e-6 else (along - m["left_x"]) / span
        t = max(0.0, min(1.0, t))
        return (along, m["left_bot"] + t * (m["right_bot"] - m["left_bot"]))
    return (x + w / 2.0, y)


def _mux_title_pos(node, x, y, w):
    return x + w / 2.0, y - 4.0


def _bubble_tip(border, side, bubble):
    if not bubble:
        return border
    shift = 2.0 * BUBBLE_R
    x, y = border
    if side == "WEST":
        return (x - shift, y)
    if side == "EAST":
        return (x + shift, y)
    if side == "SOUTH":
        return (x, y + shift)
    if side == "NORTH":
        return (x, y - shift)
    return border


def _node_has_te(node):
    for port in node.get("ports") or []:
        name = (port.get("properties") or {}).get("name") or ""
        if name == "te" or str(port.get("id") or "").endswith("__te"):
            return True
    return False


def _and_metrics(x, y, w, h):
    top = y + GATE_PAD_Y
    bot = y + h - GATE_PAD_Y
    left = x + GATE_MARGIN
    right = x + w - GATE_MARGIN
    mid = (top + bot) / 2.0
    radius = max(8.0, (bot - top) / 2.0)
    if right - left - radius < 10.0:
        radius = max(8.0, (right - left) * 0.62)
    arc_x = right - radius
    if arc_x < left:
        arc_x = left
    return {
        "left": left,
        "right": right,
        "top": top,
        "bot": bot,
        "mid": mid,
        "radius": radius,
        "arc_x": arc_x,
    }


def _and_path(metrics):
    left, top, bot = metrics["left"], metrics["top"], metrics["bot"]
    arc_x, radius = metrics["arc_x"], metrics["radius"]
    if arc_x <= left + 0.5:
        return "M%.2f,%.2f L%.2f,%.2f A%.2f,%.2f 0 0 0 %.2f,%.2f Z" % (
            left, top, left, bot, radius, radius, left, top,
        )
    return "M%.2f,%.2f L%.2f,%.2f L%.2f,%.2f A%.2f,%.2f 0 0 0 %.2f,%.2f Z" % (
        left, top, left, bot, arc_x, bot, radius, radius, arc_x, top,
    )


def _or_metrics(x, y, w, h, xor):
    gap = XOR_GAP if xor else 0.0
    right = x + w - GATE_MARGIN
    top = y + GATE_PAD_Y
    bot = y + h - GATE_PAD_Y
    mid = (top + bot) / 2.0
    left = x + GATE_MARGIN + gap
    span_x = max(8.0, right - left)
    span_y = max(8.0, bot - top)
    # 比 and 更内凹的输入背弧；宽度仍与 and 同级，靠较浅的 end_x 留出门腹。
    end_x = left + span_x * 0.05
    indent = max(6.0, min(span_y * 0.14, span_x * 0.17))
    return {
        "left": left,
        "right": right,
        "top": top,
        "bot": bot,
        "mid": mid,
        "end_x": end_x,
        "span_x": span_x,
        "span_y": span_y,
        "back0": (end_x, top),
        "back1": (end_x, bot),
        "back_c": (end_x + 2.0 * indent, mid),
        "xor_gap": gap,
    }


def _quad_at(p0, p1, p2, t):
    omt = 1.0 - t
    return (
        omt * omt * p0[0] + 2.0 * omt * t * p1[0] + t * t * p2[0],
        omt * omt * p0[1] + 2.0 * omt * t * p1[1] + t * t * p2[1],
    )


def _or_back_point(metrics, along):
    span = metrics["bot"] - metrics["top"]
    t = 0.5 if span < 1e-6 else (along - metrics["top"]) / span
    t = max(0.0, min(1.0, t))
    return _quad_at(metrics["back0"], metrics["back_c"], metrics["back1"], t)


def _or_path(metrics):
    left = metrics["left"]
    span_x = metrics["span_x"]
    span_y = metrics["span_y"]
    end_x = metrics["end_x"]
    right, top, bot, mid = metrics["right"], metrics["top"], metrics["bot"], metrics["mid"]
    back_c = metrics["back_c"]
    return (
        "M%.2f,%.2f C%.2f,%.2f %.2f,%.2f %.2f,%.2f C%.2f,%.2f %.2f,%.2f %.2f,%.2f Q%.2f,%.2f %.2f,%.2f Z"
        % (
            end_x, top,
            left + span_x * 0.50, top + span_y * 0.05,
            left + span_x * 0.88, mid - span_y * 0.38,
            right, mid,
            left + span_x * 0.88, mid + span_y * 0.38,
            left + span_x * 0.50, bot - span_y * 0.05,
            end_x, bot,
            back_c[0], mid,
            end_x, top,
        )
    )


def _xor_arc_path(metrics):
    off = metrics["xor_gap"]
    return "M%.2f,%.2f Q%.2f,%.2f %.2f,%.2f" % (
        metrics["back0"][0] - off, metrics["back0"][1],
        metrics["back_c"][0] - off, metrics["back_c"][1],
        metrics["back1"][0] - off, metrics["back1"][1],
    )


def _buf_metrics(x, y, w, h):
    top = y + 6.0
    bot = y + h - 6.0
    return {
        "left": x + GATE_MARGIN,
        "right": x + w - GATE_MARGIN,
        "top": top,
        "bot": bot,
        "mid": (top + bot) / 2.0,
    }


def _buf_path(metrics):
    return "M%.2f,%.2f L%.2f,%.2f L%.2f,%.2f Z" % (
        metrics["left"], metrics["top"],
        metrics["right"], metrics["mid"],
        metrics["left"], metrics["bot"],
    )


def _label_y(pin_y, top, bot):
    baseline = pin_y + LABEL_DY
    low = top + 11.0
    high = bot - 3.0
    if low > high:
        return (top + bot) / 2.0 + LABEL_DY
    return min(max(baseline, low), high)


def _icg_metrics(x, y, w, h, has_te=False):
    return {
        "left": x + GATE_MARGIN,
        "right": x + w - GATE_MARGIN,
        "top": y + GATE_PAD_Y,
        "bot": y + h - GATE_MARGIN,
        "mid": y + h / 2.0,
    }


def _gate_border_point(x, y, w, h, shape, side, along, name="", has_te=False):
    if shape == "and":
        metrics = _and_metrics(x, y, w, h)
        if side == "EAST":
            return (metrics["right"], metrics["mid"])
        yy = min(max(along, metrics["top"] + 2.0), metrics["bot"] - 2.0)
        return (metrics["left"], yy)
    if shape in ("or", "xor"):
        metrics = _or_metrics(x, y, w, h, shape == "xor")
        if side == "EAST":
            return (metrics["right"], metrics["mid"])
        yy = min(max(along, metrics["top"] + 1.0), metrics["bot"] - 1.0)
        point = _or_back_point(metrics, yy)
        if shape == "xor":
            # 连线停在外侧那条弧上，不穿进门腹。
            return (point[0] - metrics["xor_gap"], point[1])
        return point
    if shape == "buf":
        metrics = _buf_metrics(x, y, w, h)
        if side == "EAST":
            return (metrics["right"], metrics["mid"])
        yy = min(max(along, metrics["top"] + 1.0), metrics["bot"] - 1.0)
        return (metrics["left"], yy)
    metrics = _icg_metrics(x, y, w, h)
    if side == "EAST":
        return (metrics["right"], metrics["mid"])
    if name == "clk" or side == "SOUTH":
        return ((metrics["left"] + metrics["right"]) / 2.0, metrics["bot"])
    yy = min(max(along, metrics["top"] + 2.0), metrics["bot"] - 2.0)
    return (metrics["left"], yy)


def _gate_label_pos(x, y, w, h, shape, name, border, has_te, side="WEST"):
    if side == "EAST":
        if shape == "and":
            metrics = _and_metrics(x, y, w, h)
            return metrics["right"] - 6.0, _label_y(border[1], metrics["top"], metrics["bot"]), "end"
        if shape == "buf":
            metrics = _buf_metrics(x, y, w, h)
            return metrics["right"] - 4.0, _label_y(border[1], metrics["top"], metrics["bot"]), "end"
        if shape in ("or", "xor"):
            metrics = _or_metrics(x, y, w, h, shape == "xor")
            return metrics["right"] - 6.0, _label_y(border[1], metrics["top"], metrics["bot"]), "end"
        metrics = _icg_metrics(x, y, w, h)
        return metrics["right"] - 6.0, _label_y(border[1], metrics["top"], metrics["bot"]), "end"
    if shape == "and":
        metrics = _and_metrics(x, y, w, h)
        return metrics["left"] + 6.0, _label_y(border[1], metrics["top"], metrics["bot"]), "start"
    if shape == "buf":
        metrics = _buf_metrics(x, y, w, h)
        return metrics["left"] + 4.0, _label_y(border[1], metrics["top"], metrics["bot"]), "start"
    if shape in ("or", "xor"):
        metrics = _or_metrics(x, y, w, h, shape == "xor")
        yy = min(max(border[1], metrics["top"] + 1.0), metrics["bot"] - 1.0)
        back = _or_back_point(metrics, yy)
        return back[0] + 10.0, _label_y(border[1], metrics["top"], metrics["bot"]), "start"
    metrics = _icg_metrics(x, y, w, h)
    if name == "clk":
        return (metrics["left"] + metrics["right"]) / 2.0 + 6.0, metrics["bot"] - 8.0, "start"
    return metrics["left"] + 8.0, _label_y(border[1], metrics["top"], metrics["bot"] - 16.0), "start"


def _gate_bubbles(node, x, y, w, h, stroke):
    shape = _shape(node)
    has_te = _node_has_te(node)
    parts = []
    for port in node.get("ports") or []:
        if str((port.get("properties") or {}).get("bubble") or "") != "true":
            continue
        side = _port_side(port, w)
        name = (port.get("properties") or {}).get("name") or _port_name(port)
        py_mid = y + float(port.get("y") or 0) + float(port.get("height") or 0) / 2.0
        if side == "SOUTH":
            along = x + float(port.get("x") or 0) + float(port.get("width") or 0) / 2.0
        else:
            along = py_mid
        border = _gate_border_point(x, y, w, h, shape, side, along, name, has_te)
        tip = _bubble_tip(border, side, True)
        parts.append(
            '<circle class="gate-bubble" cx="%.2f" cy="%.2f" r="%.2f" fill="#fff" stroke="%s" stroke-width="1.2"/>'
            % ((border[0] + tip[0]) / 2.0, (border[1] + tip[1]) / 2.0, BUBBLE_R, stroke)
        )
    return "".join(parts)


def _gate_svg(node, x, y, w, h, fill, stroke, attrs, title, tooltip=""):
    shape = _shape(node)
    extra = ""
    if shape == "and":
        body = _and_path(_and_metrics(x, y, w, h))
    elif shape in ("or", "xor"):
        metrics = _or_metrics(x, y, w, h, shape == "xor")
        body = _or_path(metrics)
        if shape == "xor":
            extra = (
                '<path class="gate-stroke" fill="none" stroke="%s" stroke-width="1.2" d="%s"/>'
                % (stroke, _xor_arc_path(metrics))
            )
    elif shape == "buf":
        body = _buf_path(_buf_metrics(x, y, w, h))
    else:
        metrics = _icg_metrics(x, y, w, h)
        return (
            "<g %s>"
            "%s"
            '<rect class="swatch-fill" x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s" stroke="%s" stroke-width="1.2"/>'
            "%s"
            '<text class="gate-title" x="%.2f" y="%.2f" text-anchor="middle" '
            'font-family="DejaVu Sans, sans-serif" font-size="11" font-weight="700" fill="#111">%s</text>'
            "</g>"
            % (
                attrs,
                tooltip,
                metrics["left"], metrics["top"],
                metrics["right"] - metrics["left"], metrics["bot"] - metrics["top"],
                fill, stroke,
                _gate_bubbles(node, x, y, w, h, stroke),
                x + w / 2.0, y - 4.0, title,
            )
        )
    return (
        "<g %s>"
        "%s"
        '<path class="swatch-fill" fill="%s" stroke="%s" stroke-width="1.2" d="%s"/>'
        "%s%s"
        '<text class="gate-title" x="%.2f" y="%.2f" text-anchor="middle" '
        'font-family="DejaVu Sans, sans-serif" font-size="11" font-weight="700" fill="#111">%s</text>'
        "</g>"
        % (
            attrs, tooltip, fill, stroke, body, extra, _gate_bubbles(node, x, y, w, h, stroke),
            x + w / 2.0, y - 4.0, title,
        )
    )


def _poly(pts):
    return " ".join("%.2f,%.2f" % pt for pt in pts)


def _node_svg(node, x, y, w, h, palette):
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
    if shape == "mux":
        pts = _mux_polygon(x, y, w, h)
        badge = ""
        if badge_text:
            m = _mux_metrics(x, y, w, h)
            badge = (
                '<text x="%.2f" y="%.2f" text-anchor="end" font-family="DejaVu Sans, sans-serif" '
                'font-size="8" fill="%s">%s</text>'
                % (m["right_x"] - 3.0, m["right_top"] + 10.0, stroke, _esc(badge_text))
            )
        tx, ty = _mux_title_pos(node, x, y, w)
        mux_hit = (
            '<rect class="node-hit" x="%.2f" y="%.2f" width="%.2f" height="%.2f" '
            'fill="transparent" pointer-events="all"/>'
            % (x, ty - 14.0, w, h + (y - ty) + 14.0)
        )
        return (
            "<g %s>"
            "%s"
            "%s"
            '<polygon class="swatch-fill" fill="%s" stroke="%s" stroke-width="1.2" points="%s"/>'
            '<text class="mux-title" x="%.2f" y="%.2f" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-size="11" font-weight="700" fill="#111">%s</text>'
            "%s"
            "</g>"
            % (attrs, node_tooltip, mux_hit, fill, stroke, _poly(pts), tx, ty, title, badge)
        )
    if shape in GATE_SHAPES:
        return _gate_svg(node, x, y, w, h, fill, stroke, attrs, title, node_tooltip)
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


def render_svg(graph, palette=None):
    palette = palette or {}
    origins = _abs_origins(graph)
    pins, labels = _collect_ports(graph, origins)
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
            pts = _snap_end(pts, _attach(pins[src_id], pts[1]), True)
        if tgt_id in pins:
            pts = _snap_end(pts, _attach(pins[tgt_id], pts[-2]), False)
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

    parts = []
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
        if _shape(node) == "mux" or _shape(node) in GATE_SHAPES:
            tx, ty = _mux_title_pos(node, x, y, w)
            tw = max(8.0, len(_node_title(node)) * 6.6)
            _expand_box(box, tx - tw / 2.0, ty - 12.0)
            _expand_box(box, tx + tw / 2.0, ty + 2.0)
        parts.append(_node_svg(node, x, y, w, h, palette))

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
        parts.append(
            '<g class="edge" data-swatch="%s" data-src="%s" data-dst="%s" data-edge-id="%d">%s</g>'
            % (_esc(swatch), _esc(route["src"]), _esc(route["dst"]), idx, "".join(chunks))
        )

    for geom in pins.values():
        if geom.get("shape") == "snap":
            continue
        _expand_box(box, geom["x"], geom["y"])
        _expand_box(box, geom["x"] + geom["w"], geom["y"] + geom["h"])
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

    for tx, ty, anchor, name, swatch, port_id in labels:
        fill = darken(color_for(palette, swatch, "#333"), 0.15) if swatch else "#333"
        tw = max(8.0, len(name) * 6.2)
        if anchor == "middle":
            _expand_box(box, tx - tw / 2.0, ty - 10.0)
            _expand_box(box, tx + tw / 2.0, ty + 4.0)
        elif anchor == "end":
            _expand_box(box, tx - tw, ty - 10.0)
            _expand_box(box, tx, ty + 4.0)
        else:
            _expand_box(box, tx, ty - 10.0)
            _expand_box(box, tx + tw, ty + 4.0)
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

    minx, miny, maxx, maxy = box
    width = max(40.0, maxx - minx + PAD * 2)
    height = max(40.0, maxy - miny + PAD * 2)
    inner = "\n".join(parts)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="%.2f" height="%.2f" viewBox="0 0 %.2f %.2f">\n'
        '<rect width="100%%" height="100%%" fill="#fff"/>\n'
        '<g transform="translate(%.2f,%.2f)">\n%s\n</g>\n</svg>\n'
        % (width, height, width, height, PAD - minx, PAD - miny, inner)
    )
