"""Native draw.io export from ELK layout (scheme C, vector-only)."""

from schematic.drawio_mx import MxDocument, _html_value
from schematic.drawio_edges import canvas_edge_points, drawio_port_label_top, jump_size
from schematic.drawio_symbol import add_symbol_node
from schematic.drawio_vector import add_port_pentagon
from schematic.symbol import is_cell_node
from schematic.style import SHAPE_FILL, SHAPE_STROKE, color_for, darken
from schematic.svg import (
    INVERT_R,
    LOGIC_SEQ_NOTCH,
    _node_title,
    _prop,
    _shape,
    prepare_scene,
    wrap_expr,
)


def _tx(x, ox):
    return x + ox


def _ty(y, oy):
    return y + oy


def _base_style(extra="", *, valign="middle"):
    base = (
        "whiteSpace=wrap;html=1;align=center;verticalAlign=%s;"
        "fontFamily=DejaVu Sans;fontSize=12;fontStyle=1;"
        % valign
    )
    return base + (extra or "")


def _node_style(node, palette):
    shape = _shape(node)
    swatch = _prop(node, "swatch")
    fill = color_for(palette, swatch, SHAPE_FILL.get(shape, "#ffffff"))
    stroke = SHAPE_STROKE.get(shape) or darken(fill)
    valign = "middle"
    extra_shape = ""
    if shape in ("box", "reg"):
        valign = "top"
        extra_shape = "spacingTop=6;"
    elif shape == "logic":
        valign = "top"
        extra_shape = "spacingTop=4;rounded=1;absoluteArcSize=1;arcSize=14;"
        lk = (_prop(node, "kind") or "comb").lower()
        if lk == "seq":
            extra_shape += "schematicLogicKind=seq;"
    else:
        extra_shape = "rounded=0;"
    style = _base_style(
        "fillColor=%s;strokeColor=%s;strokeWidth=1.2;%s"
        % (fill, stroke, extra_shape),
        valign=valign,
    )
    style += "schematicId=%s;schematicShape=%s;" % (node["id"], shape)
    if swatch:
        style += "schematicSwatch=%s;" % swatch
    return style, fill, stroke


def _node_label(node):
    title = _node_title(node)
    shape = _shape(node)
    if shape != "logic":
        return _html_value(title)
    expr = _prop(node, "expr")
    lines = wrap_expr(expr)
    if not lines:
        return _html_value(title)
    body = "<br>".join(_html_value(line) for line in lines)
    return _html_value(title) + "<br><font style=\"font-size:9px;\">" + body + "</font>"


def _add_reg_clock(doc, layer, x, y, w, h, stroke, ox, oy):
    cx = _tx(x + w / 2.0, ox)
    cy = _ty(y + h, oy)
    style = "shape=triangle;direction=north;fillColor=%s;strokeColor=%s;strokeWidth=1;" % (
        stroke, stroke,
    )
    doc.add_vertex(layer, cx - 6.0, cy - 9.0, 12.0, 9.0, value="", style=style)


def _add_logic_seq_notch(doc, layer, x, y, w, h, stroke, ox, oy):
    style = "shape=triangle;direction=north;fillColor=%s;strokeColor=%s;strokeWidth=1;" % (
        stroke, stroke,
    )
    cx = _tx(x + w / 2.0, ox)
    cy = _ty(y + h, oy)
    doc.add_vertex(layer, cx - 6.0, cy - LOGIC_SEQ_NOTCH, 12.0, LOGIC_SEQ_NOTCH, value="", style=style)


def render_drawio_native(graph, palette=None, *, title="diagram", libs=None):
    scene = prepare_scene(graph, palette, libs=libs)
    palette = scene["palette"]
    origins = scene["origins"]
    canvas = scene["canvas"]
    ox, oy = canvas["ox"], canvas["oy"]

    doc = MxDocument(page_name=title, page_width=canvas["width"], page_height=canvas["height"])
    layer = "1"

    cell_ids = {
        n["id"] for n in scene["nodes"]
        if is_cell_node(n, libs) and not n.get("children")
    }
    labels_by_node = {}
    free_labels = []
    for item in scene["labels"]:
        nid = item[0]
        if nid in cell_ids:
            labels_by_node.setdefault(nid, []).append(item)
        else:
            free_labels.append(item)

    for node in sorted(scene["nodes"], key=lambda n: n["id"]):
        nid = node["id"]
        x, y = origins[nid]
        w = float(node.get("width") or 0)
        h = float(node.get("height") or 0)
        shape = _shape(node)

        if is_cell_node(node, libs):
            add_symbol_node(
                doc, layer, node, x, y, w, h, palette, ox, oy, libs,
                port_labels=labels_by_node.get(nid),
            )
            continue

        style, fill, stroke = _node_style(node, palette)
        doc.add_vertex(
            layer, _tx(x, ox), _ty(y, oy), w, h,
            value=_node_label(node), style=style,
        )
        if shape == "reg":
            _add_reg_clock(doc, layer, x, y, w, h, stroke, ox, oy)
        if shape == "logic" and (_prop(node, "kind") or "comb").lower() == "seq":
            _add_logic_seq_notch(doc, layer, x, y, w, h, stroke, ox, oy)

    pins = scene["pins"]
    for geom in pins.values():
        if geom.get("shape") == "snap":
            continue
        add_port_pentagon(doc, layer, geom, palette, ox, oy)

    for _nid, tx, ty, anchor, name, swatch, port_id in free_labels:
        fill = darken(color_for(palette, swatch, "#333333"), 0.15) if swatch else "#333333"
        align = {"start": "left", "middle": "center", "end": "right"}.get(anchor, "left")
        tw = max(8.0, len(name) * 6.2)
        lx = _tx(tx, ox)
        ly = _ty(drawio_port_label_top(ty), oy)
        if anchor == "middle":
            lx -= tw / 2.0
        elif anchor == "end":
            lx -= tw
        style = (
            "text;html=1;strokeColor=none;fillColor=none;align=%s;verticalAlign=top;"
            "fontFamily=DejaVu Sans;fontSize=10;fontColor=%s;schematicPortId=%s;"
            % (align, fill, port_id)
        )
        doc.add_vertex(layer, lx, ly, tw, 14.0, value=_html_value(name), style=style)

    node_shapes = {n["id"]: _shape(n) for n in scene["nodes"]}

    js = jump_size()
    for route in scene["routes"]:
        canvas_pts = canvas_edge_points(route, pins, ox, oy, node_shapes=node_shapes)
        swatch = route.get("swatch") or ""
        stroke = color_for(palette, swatch, "#111111") if swatch else "#111111"
        if len(canvas_pts) >= 2:
            # Always use explicit tip polyline (same as SVG). mxGraph cell links hit the
            # pentagon bbox center/wrong side and wires cut through the port shape.
            doc.add_edge_points(
                layer, canvas_pts, stroke=stroke, swatch=swatch, jump_size=js,
            )
        invert_pt = route.get("invert")
        if invert_pt:
            cx, cy = invert_pt
            doc.add_vertex(
                layer,
                _tx(cx, ox) - INVERT_R,
                _ty(cy, oy) - INVERT_R,
                INVERT_R * 2,
                INVERT_R * 2,
                value="",
                style=(
                    "ellipse;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=%s;"
                    "strokeWidth=1.2;" % stroke
                ),
            )

    return doc.to_xml()
