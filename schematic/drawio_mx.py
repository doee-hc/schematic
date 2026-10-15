"""Minimal mxGraph / draw.io XML writer (uncompressed mxfile)."""

import xml.etree.ElementTree as ET


def _esc_attr(text):
    text = str(text or "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _html_value(text):
    return _esc_attr(text).replace("\n", "&#xa;")


class MxDocument:
    def __init__(self, page_name="Page-1", page_width=850, page_height=1100):
        self.page_name = page_name or "Page-1"
        self.page_width = float(page_width)
        self.page_height = float(page_height)
        self._next_id = 2
        self._cells = []

    def alloc_id(self):
        cid = str(self._next_id)
        self._next_id += 1
        return cid

    def add_cell(self, cell_id, *, parent, value="", style="", vertex=False, edge=False, geometry=None):
        self._cells.append({
            "id": cell_id,
            "parent": parent,
            "value": value,
            "style": style,
            "vertex": vertex,
            "edge": edge,
            "geometry": geometry or {},
        })
        return cell_id

    def add_vertex(self, parent, x, y, w, h, *, value="", style=""):
        cid = self.alloc_id()
        self.add_cell(
            cid,
            parent=parent,
            value=value,
            style=style,
            vertex=True,
            geometry={"x": x, "y": y, "width": w, "height": h},
        )
        return cid

    def add_group(self, parent, x, y, w, h):
        """mxGraph group; child vertex geometry is relative to this box."""
        return self.add_vertex(
            parent,
            x,
            y,
            w,
            h,
            value="",
            style="group;childLayout=stackLayout;horizontal=1;startSize=0;horizontalStack=0;"
            "resizeParent=0;resizeParentMax=0;resizeLast=0;collapsible=0;swimlaneFillColor=none;",
        )

    def add_edge_points(
        self,
        parent,
        points,
        *,
        stroke="#111111",
        swatch="",
        width=1.2,
        end_arrow=True,
        jump_style="arc",
        jump_size=4.0,
    ):
        if len(points) < 2:
            return None
        style = (
            "edgeStyle=none;rounded=0;orthogonalLoop=1;jettySize=0;"
            "html=1;strokeWidth=%.1f;strokeColor=%s;fillColor=%s;endArrow=%s;startArrow=none;"
            % (width, stroke, stroke, "classic" if end_arrow else "none")
        )
        if jump_style:
            style += "jumpStyle=%s;jumpSize=%.1f;" % (jump_style, jump_size)
        if swatch:
            style += "schematicSwatch=%s;" % _esc_attr(swatch)
        cid = self.alloc_id()
        self.add_cell(
            cid,
            parent=parent,
            style=style,
            edge=True,
            geometry={
                "relative": "1",
                "sourcePoint": points[0],
                "targetPoint": points[-1],
                "points": points[1:-1],
            },
        )
        return cid

    def add_edge_linked(
        self,
        parent,
        source_id,
        target_id,
        waypoints,
        *,
        stroke="#111111",
        swatch="",
        width=1.2,
        jump_style="arc",
        jump_size=4.0,
    ):
        style = (
            "edgeStyle=none;rounded=0;orthogonalLoop=1;jettySize=0;"
            "html=1;strokeWidth=%.1f;strokeColor=%s;fillColor=%s;"
            "endArrow=classic;startArrow=none;"
            % (width, stroke, stroke)
        )
        if jump_style:
            style += "jumpStyle=%s;jumpSize=%.1f;" % (jump_style, jump_size)
        if swatch:
            style += "schematicSwatch=%s;" % _esc_attr(swatch)
        cid = self.alloc_id()
        self._cells.append({
            "id": cid,
            "parent": parent,
            "value": "",
            "style": style,
            "vertex": False,
            "edge": True,
            "source": source_id,
            "target": target_id,
            "geometry": {"relative": "1", "points": waypoints or []},
        })
        return cid

    def to_xml(self):
        root_el = ET.Element("root")
        ET.SubElement(root_el, "mxCell", id="0")
        ET.SubElement(root_el, "mxCell", id="1", parent="0")

        for spec in self._cells:
            attrs = {
                "id": spec["id"],
                "parent": spec["parent"],
                "value": spec["value"],
                "style": spec["style"],
            }
            if spec["vertex"]:
                attrs["vertex"] = "1"
            if spec["edge"]:
                attrs["edge"] = "1"
            if spec.get("source"):
                attrs["source"] = spec["source"]
            if spec.get("target"):
                attrs["target"] = spec["target"]
            cell = ET.SubElement(root_el, "mxCell", attrs)
            geom = spec["geometry"]
            g_attrs = {"as": "geometry"}
            if spec["vertex"]:
                g_attrs.update({
                    "x": "%.2f" % geom["x"],
                    "y": "%.2f" % geom["y"],
                    "width": "%.2f" % geom["width"],
                    "height": "%.2f" % geom["height"],
                })
            else:
                g_attrs["relative"] = geom.get("relative", "1")
            geo = ET.SubElement(cell, "mxGeometry", g_attrs)
            if spec["edge"]:
                if geom.get("sourcePoint") and geom.get("targetPoint"):
                    sp = geom["sourcePoint"]
                    tp = geom["targetPoint"]
                    ET.SubElement(
                        geo,
                        "mxPoint",
                        {"x": "%.2f" % sp[0], "y": "%.2f" % sp[1], "as": "sourcePoint"},
                    )
                    ET.SubElement(
                        geo,
                        "mxPoint",
                        {"x": "%.2f" % tp[0], "y": "%.2f" % tp[1], "as": "targetPoint"},
                    )
                if geom.get("points"):
                    arr = ET.SubElement(geo, "Array", **{"as": "points"})
                    for px, py in geom["points"]:
                        ET.SubElement(arr, "mxPoint", x="%.2f" % px, y="%.2f" % py)

        model = ET.Element(
            "mxGraphModel",
            dx="1422",
            dy="794",
            grid="1",
            gridSize="10",
            guides="1",
            tooltips="1",
            connect="1",
            arrows="1",
            fold="1",
            page="1",
            pageScale="1",
            pageWidth=str(int(self.page_width)),
            pageHeight=str(int(self.page_height)),
            math="0",
            shadow="0",
        )
        model.append(root_el)

        diagram = ET.Element("diagram", id="schematic-page", name=_esc_attr(self.page_name))
        diagram.append(model)

        mxfile = ET.Element(
            "mxfile",
            host="app.diagrams.net",
            agent="schematic",
            version="24.7.0",
        )
        mxfile.append(diagram)

        ET.indent(mxfile, space="  ")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(mxfile, encoding="unicode")
