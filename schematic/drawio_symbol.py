"""Draw.io cells from lib symbols (embedded SVG, pixel-aligned with preview)."""

from schematic.drawio_mx import _html_value
from schematic.style import SHAPE_FILL, SHAPE_STROKE, color_for, darken
from schematic.symbol import is_cell_node, resolve_node_symbol, symbol_svg_document, svg_data_uri
from schematic.drawio_edges import drawio_port_label_top
from schematic.svg import _node_title, _prop, _shape

CELL_TITLE_BAND = 14.0


def _add_port_labels(doc, group_id, node_x, node_y, title_band, port_labels, palette):
    """Port labels inside the cell group (relative coords)."""
    origin_y = node_y - title_band
    for _nid, tx, ty, anchor, name, swatch, port_id in port_labels or []:
        fill = darken(color_for(palette, swatch, "#333333"), 0.15) if swatch else "#333333"
        align = {"start": "left", "middle": "center", "end": "right"}.get(anchor, "left")
        tw = max(8.0, len(name) * 6.2)
        rx = tx - node_x
        ry = drawio_port_label_top(ty) - origin_y
        if anchor == "middle":
            rx -= tw / 2.0
        elif anchor == "end":
            rx -= tw
        style = (
            "text;html=1;strokeColor=none;fillColor=none;align=%s;verticalAlign=top;"
            "fontFamily=DejaVu Sans;fontSize=10;fontColor=%s;schematicPortId=%s;"
            % (align, fill, port_id)
        )
        doc.add_vertex(group_id, rx, ry, tw, 14.0, value=_html_value(name), style=style)


def add_symbol_node(doc, layer, node, x, y, w, h, palette, ox, oy, libs, port_labels=None):
    if not is_cell_node(node, libs):
        return None
    sym = resolve_node_symbol(node, libs)
    if not sym:
        return None
    swatch = _prop(node, "swatch")
    shape = _shape(node)
    fill = color_for(palette, swatch, SHAPE_FILL.get(shape, "#e7f0fb"))
    stroke = SHAPE_STROKE.get(shape) or darken(fill)
    uri = svg_data_uri(symbol_svg_document(sym, fill, stroke))
    extra = "schematicId=%s;schematicSymbol=1;" % _html_value(node["id"])
    image_style = (
        "shape=image;aspect=fixed;verticalLabelPosition=bottom;verticalAlign=top;"
        "imageAspect=0;image=%s;%s"
        % (uri, extra)
    )
    title = _node_title(node)
    title_band = CELL_TITLE_BAND if title else 0.0
    gx = x + ox
    gy = y + oy - title_band
    group_id = doc.add_group(layer, gx, gy, w, h + title_band)
    doc.add_vertex(group_id, 0, title_band, w, h, value="", style=image_style)
    if title:
        tw = max(24.0, len(title) * 6.6)
        doc.add_vertex(
            group_id,
            w / 2.0 - tw / 2.0,
            title_band - 12.0,
            tw,
            14.0,
            value=_html_value(title),
            style=(
                "text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=bottom;"
                "fontFamily=DejaVu Sans;fontSize=11;fontStyle=1;fontColor=#111111;"
            ),
        )
    _add_port_labels(doc, group_id, x, y, title_band, port_labels, palette)
    return group_id
