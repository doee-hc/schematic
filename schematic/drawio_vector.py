"""Draw.io vector helpers (port pentagons, shared polygon utilities)."""

from schematic.style import color_for, darken
from schematic.svg import _pentagon


def _format_poly_coords(rel_points):
    return "[" + ",".join("[%.5f,%.5f]" % (p[0], p[1]) for p in rel_points) + "]"


def polygon_style(rel_points, fill, stroke, *, polyline=0, extra=""):
    return (
        "html=1;labelBackgroundColor=none;"
        "shape=mxgraph.basic.polygon;polyCoords=%s;polyline=%d;"
        "fillColor=%s;strokeColor=%s;strokeWidth=1.2;%s"
        % (_format_poly_coords(rel_points), polyline, fill, stroke, extra or "")
    )


def _bbox(abs_points, pad=0.0):
    minx = min(p[0] for p in abs_points) - pad
    miny = min(p[1] for p in abs_points) - pad
    maxx = max(p[0] for p in abs_points) + pad
    maxy = max(p[1] for p in abs_points) + pad
    return minx, miny, max(1.0, maxx - minx), max(1.0, maxy - miny)


def _rel_points(abs_points, minx, miny, w, h):
    w = w or 1.0
    h = h or 1.0
    return [((px - minx) / w, (py - miny) / h) for px, py in abs_points]


def add_polygon(doc, layer, abs_points, fill, stroke, ox, oy, *, value="", polyline=0, extra=""):
    minx, miny, w, h = _bbox(abs_points)
    rel = _rel_points(abs_points, minx, miny, w, h)
    style = polygon_style(rel, fill, stroke, polyline=polyline, extra=extra)
    cid = doc.add_vertex(layer, minx + ox, miny + oy, w, h, value=value, style=style)
    return cid, minx, miny, w, h


def add_port_pentagon(doc, layer, geom, palette, ox, oy):
    from schematic.svg import PORT_FILL, PORT_STROKE

    poly, tx, ty = _pentagon(geom)
    swatch = geom.get("swatch") or ""
    fill = color_for(palette, swatch, PORT_FILL) if swatch else PORT_FILL
    stroke = darken(fill, 0.45) if swatch else PORT_STROKE
    extra = "schematicPortId=%s;" % (geom.get("id") or "")
    if swatch:
        extra += "schematicSwatch=%s;" % swatch
    pname = geom.get("name") or ""
    cid, minx, miny, pw, ph = add_polygon(
        doc, layer, poly, fill, stroke, ox, oy, value="", extra=extra,
    )
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    tw = max(8.0, len(pname) * 6.2)
    th = 10.0
    doc.add_vertex(
        layer,
        cx + ox - tw / 2.0,
        cy + oy - th / 2.0 - 0.5,
        tw,
        th,
        value=_html_esc(pname),
        style=(
            "text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;"
            "fontFamily=DejaVu Sans;fontSize=10;fontColor=#222222;pointerEvents=0;"
        ),
    )
    return cid, minx, miny, pw, ph


def _html_esc(text):
    from schematic.drawio_mx import _html_value
    return _html_value(text)


def node_drawio_bbox(node, x, y, w, h, palette):
    del node, palette
    return x, y, w, h
