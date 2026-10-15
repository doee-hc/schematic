"""Draw.io edge point extraction (aligned with SVG port attachment)."""

from schematic.svg import EPS, JUMP_R, _attach

# draw.io html=1 labels sit visually lower than SVG at the same schematic y.
DRAWIO_PORT_LABEL_RAISE = 3.0


def drawio_port_label_top(schematic_ty):
    """Schematic anchor y → draw.io text box top (verticalAlign=top)."""
    return schematic_ty - 10.0 - DRAWIO_PORT_LABEL_RAISE


def _port_endpoint(geom, toward):
    if geom.get("shape") == "snap":
        return tuple(geom["tip"])
    return tuple(_attach(geom, toward))


def _fix_terminal_leg(pts, geom, *, at_start):
    """One orthogonal bend into exact port tip (no Y nudge, no full re-ortho)."""
    if len(pts) < 2 or not geom:
        return pts
    out = list(pts)
    tip = out[0] if at_start else out[-1]
    prev_idx = 1 if at_start else -2
    prev = out[prev_idx]
    if abs(prev[0] - tip[0]) < EPS or abs(prev[1] - tip[1]) < EPS:
        return out
    side = (geom.get("side") or "EAST").upper()
    if side in ("NORTH", "SOUTH"):
        bend = (tip[0], prev[1])
    else:
        bend = (prev[0], tip[1])
    if at_start:
        out.insert(1, bend)
    else:
        out.insert(-1, bend)
    return out


def schematic_edge_points(route, pins, node_shapes=None):
    del node_shapes
    pts = [tuple(p) for p in route.get("pts") or []]
    if len(pts) < 2:
        return pts
    src_id = route.get("src") or ""
    dst_id = route.get("dst") or ""
    arrow = route.get("arrow") or ()

    start = pts[0]
    if src_id and src_id in pins:
        toward = pts[1] if len(pts) > 1 else start
        start = _port_endpoint(pins[src_id], toward)

    end = pts[-1]
    if dst_id and dst_id in pins and len(arrow) == 2:
        end = tuple(arrow[1])
    elif dst_id and dst_id in pins:
        toward = pts[-2] if len(pts) > 1 else end
        end = _port_endpoint(pins[dst_id], toward)

    if len(pts) == 2:
        out = [start, end]
    else:
        out = [start] + list(pts[1:-1]) + [end]

    if src_id and src_id in pins:
        out = _fix_terminal_leg(out, pins[src_id], at_start=True)
    if dst_id and dst_id in pins:
        out = _fix_terminal_leg(out, pins[dst_id], at_start=False)
    return out


def canvas_edge_points(route, pins, ox, oy, node_shapes=None):
    return [
        (x + ox, y + oy)
        for x, y in schematic_edge_points(route, pins, node_shapes=node_shapes)
    ]


def jump_size():
    return max(4.0, JUMP_R * 2.0)
