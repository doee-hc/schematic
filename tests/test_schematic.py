import unittest

from schematic.engine import layout
from schematic.graph import (
    PortFilter,
    document_to_elk,
    port_id,
)
from schematic.render import draw
from schematic.svg import (
    _abs_origins,
    _attach,
    _collect_ports,
    _mux_border_point,
    _mux_polygon,
    render_svg,
)


def _nodes(graph):
    acc = {}

    def walk(node):
        acc[node["id"]] = node
        for child in node.get("children") or []:
            walk(child)

    for child in graph.get("children") or []:
        walk(child)
    return acc


def _edges(graph):
    return [
        (edge["sources"][0], edge["targets"][0])
        for edge in graph.get("edges") or []
    ]


def _doc():
    return {
        "palette": {"family:box": "#F4F6F8", "port:scan": "#3D7ECC"},
        "root": {
            "id": "top",
            "title": "top",
            "shape": "box",
            "swatch": "family:box",
            "ports": [
                {"name": "si", "side": "west", "dir": "in", "swatch": "port:scan"},
                {"name": "so", "side": "east", "dir": "out", "swatch": "port:scan", "keep": True},
                {"name": "sel", "side": "west", "dir": "in"},
            ],
            "edges": [
                {"from": "top.si", "to": "top.mux.a", "swatch": "port:scan"},
                {"from": "top.mux.y", "to": "top.reg.d"},
                {"from": "top.reg.q", "to": "top.so", "invert": True, "swatch": "port:scan"},
                {"from": "top.logic.y", "to": "top.mux.sel"},
            ],
            "children": [
                {
                    "id": "top.mux",
                    "title": "scan_in_mux",
                    "shape": "mux",
                    "badge": "CLK",
                    "ports": [
                        {"name": "a", "side": "west", "dir": "in", "label": "1'b0"},
                        {"name": "b", "side": "west", "dir": "in", "label": "1'b1"},
                        {"name": "sel", "side": "south", "dir": "in"},
                        {"name": "y", "side": "east", "dir": "out"},
                    ],
                },
                {
                    "id": "top.reg",
                    "title": "bus_out",
                    "shape": "reg",
                    "note": "RST=1'b0",
                    "ports": [
                        {"name": "d", "side": "west", "dir": "in"},
                        {"name": "q", "side": "east", "dir": "out"},
                    ],
                },
                {
                    "id": "top.logic",
                    "title": "gate",
                    "shape": "logic",
                    "expr": "enable, sib == 2'b11",
                    "ports": [
                        {"name": "enable", "side": "west", "dir": "in"},
                        {"name": "y", "side": "east", "dir": "out"},
                    ],
                },
                {
                    "id": "top.leaf",
                    "title": "leaf",
                    "shape": "box",
                    "ports": [
                        {"name": "x", "side": "west", "dir": "in"},
                    ],
                },
            ],
        },
    }


class PortFilterTests(unittest.TestCase):
    def test_include_overrides_exclude(self):
        filt = PortFilter(["ijtag*si", "*tck*"], ["ijtag*"])
        self.assertTrue(filt.match("ijtag_si"))
        self.assertTrue(filt.match("ijtag_tck"))
        self.assertFalse(filt.match("ijtag_ce"))
        self.assertTrue(filt.match("enable"))

    def test_empty_lists_keep_all(self):
        filt = PortFilter([], [])
        self.assertTrue(filt.match("ijtag_sel"))
        self.assertTrue(filt.match("enable"))

    def test_glob_is_literal_except_star(self):
        filt = PortFilter([], ["ijtag.sel"])
        self.assertTrue(filt.match("ijtagXsel"))
        self.assertFalse(filt.match("ijtag.sel"))


class GraphTests(unittest.TestCase):
    def test_shapes_edges_and_sides(self):
        graph = document_to_elk(_doc())
        nodes = _nodes(graph)
        self.assertEqual(nodes["top.mux"]["properties"]["shape"], "mux")
        self.assertEqual(nodes["top.reg"]["properties"]["shape"], "reg")
        self.assertEqual(nodes["top.logic"]["properties"]["shape"], "logic")
        self.assertEqual(nodes["top.mux"]["properties"]["badge"], "CLK")
        sel = next(port for port in nodes["top.mux"]["ports"] if port["id"].endswith("__sel"))
        self.assertEqual(sel["layoutOptions"]["elk.port.side"], "SOUTH")
        edges = _edges(graph)
        self.assertIn((port_id("top", "si"), port_id("top.mux", "a")), edges)
        self.assertIn((port_id("top.mux", "y"), port_id("top.reg", "d")), edges)
        inverted = [
            edge for edge in graph["edges"]
            if (edge.get("properties") or {}).get("invert") == "true"
        ]
        self.assertEqual(len(inverted), 1)

    def test_boxes_only_hides_detail_shapes(self):
        graph = document_to_elk(_doc(), {"boxes_only": True})
        nodes = _nodes(graph)
        self.assertIn("top", nodes)
        self.assertIn("top.leaf", nodes)
        self.assertNotIn("top.mux", nodes)
        self.assertNotIn("top.reg", nodes)
        self.assertNotIn("top.logic", nodes)
        self.assertFalse(_edges(graph))

    def test_include_keeps_ancestors(self):
        graph = document_to_elk(_doc(), {"include": ["top.leaf"]})
        nodes = _nodes(graph)
        self.assertIn("top", nodes)
        self.assertIn("top.leaf", nodes)
        self.assertNotIn("top.mux", nodes)

    def test_keep_survives_exclude(self):
        graph = document_to_elk(_doc(), {"port_exclude": ["s*"]})
        names = {port["id"].rsplit("__", 1)[-1] for port in _nodes(graph)["top"]["ports"]}
        self.assertIn("so", names)
        self.assertNotIn("si", names)
        self.assertNotIn("sel", names)

    def test_detail_shapes_keep_ports(self):
        graph = document_to_elk(_doc(), {"port_exclude": ["*"]})
        mux_ports = {port["id"].rsplit("__", 1)[-1] for port in _nodes(graph)["top.mux"]["ports"]}
        self.assertIn("a", mux_ports)
        self.assertIn("y", mux_ports)

    def test_mux_width_ignores_long_title(self):
        doc = {
            "root": {
                "id": "m",
                "title": "m",
                "shape": "box",
                "ports": [],
                "children": [{
                    "id": "m.mux",
                    "title": "streaming_through_ijtag_en_si_mux",
                    "shape": "mux",
                    "ports": [
                        {"name": "a", "side": "west", "dir": "in", "label": "1'b0"},
                        {"name": "b", "side": "west", "dir": "in", "label": "1'b1"},
                        {"name": "sel", "side": "south", "dir": "in", "label": "sib"},
                        {"name": "y", "side": "east", "dir": "out"},
                    ],
                }],
            }
        }
        graph = document_to_elk(doc)
        mux = _nodes(graph)["m.mux"]
        self.assertGreaterEqual(mux["width"], 96.0)
        self.assertLess(mux["width"], 160.0)


class SvgTests(unittest.TestCase):
    def test_shape_drawing(self):
        graph = {
            "id": "root",
            "width": 400,
            "height": 200,
            "children": [
                {
                    "id": "reg",
                    "x": 10, "y": 10, "width": 96, "height": 56,
                    "labels": [{"text": "bus_out"}],
                    "properties": {"shape": "reg", "note": "RST=1'b0"},
                    "ports": [],
                },
                {
                    "id": "mux",
                    "x": 130, "y": 40, "width": 84, "height": 64,
                    "labels": [{"text": "scan_in_mux"}],
                    "properties": {"shape": "mux", "badge": "CLK"},
                    "ports": [],
                },
                {
                    "id": "logic",
                    "x": 240, "y": 10, "width": 120, "height": 64,
                    "labels": [{"text": "gate"}],
                    "properties": {"shape": "logic", "expr": "enable, sib == 2'b11"},
                    "ports": [],
                },
            ],
            "edges": [],
        }
        svg = render_svg(graph)
        self.assertIn('data-shape="reg"', svg)
        start = svg.find('data-shape="reg"')
        self.assertNotIn('rx="', svg[start:svg.find("</g>", start)])
        self.assertIn("#eee8f8", svg)
        self.assertIn('data-shape="mux"', svg)
        self.assertIn('class="mux-title"', svg)
        self.assertIn(">CLK</text>", svg)
        self.assertIn('data-shape="logic"', svg)
        self.assertIn('rx="14"', svg)
        self.assertIn("enable, sib == 2'b11", svg)

    def test_draw_invert_and_palette(self):
        svg = draw(_doc(), {"include": ["top", "top.mux", "top.reg", "top.logic"]})
        self.assertIn('class="edge-invert"', svg)
        self.assertIn('data-shape="mux"', svg)
        self.assertIn('data-shape="reg"', svg)
        self.assertIn("#3D7ECC", svg)

    def test_mux_wires_meet_border(self):
        doc = {
            "root": {
                "id": "m",
                "title": "m",
                "shape": "box",
                "ports": [
                    {"name": "si", "side": "west", "dir": "in"},
                    {"name": "so", "side": "east", "dir": "out"},
                ],
                "edges": [
                    {"from": "m.si", "to": "m.mux.a"},
                    {"from": "m.mux.y", "to": "m.so"},
                ],
                "children": [{
                    "id": "m.mux",
                    "title": "mux",
                    "shape": "mux",
                    "ports": [
                        {"name": "a", "side": "west", "dir": "in", "label": "1'b0"},
                        {"name": "b", "side": "west", "dir": "in", "label": "1'b1"},
                        {"name": "sel", "side": "south", "dir": "in", "label": "sib"},
                        {"name": "y", "side": "east", "dir": "out"},
                    ],
                }],
            }
        }
        graph = document_to_elk(doc)
        laid = layout(graph)
        origins = _abs_origins(laid)
        pins, labels = _collect_ports(laid, origins)
        node = _nodes(laid)["m.mux"]
        x, y = origins["m.mux"]
        w = float(node["width"])
        h = float(node["height"])
        pts = _mux_polygon(x, y, w, h)
        self.assertAlmostEqual(pts[1][1] - pts[0][1], pts[3][1] - pts[2][1], places=2)
        west = [item for item in labels if item[3] in ("1'b0", "1'b1")]
        self.assertEqual(len(west), 2)
        for tx, ty, _anchor, _name, _swatch, _pid in west:
            self.assertGreaterEqual(tx, pts[0][0])
            self.assertLessEqual(tx, pts[1][0])
        snap = pins[port_id("m.mux", "a")]
        self.assertEqual(snap.get("shape"), "snap")
        expected = _mux_border_point(x, y, w, h, snap["side"], snap["tip"][1])
        self.assertAlmostEqual(snap["tip"][0], expected[0], places=2)
        self.assertAlmostEqual(snap["tip"][1], expected[1], places=2)
        self.assertEqual(_attach(snap, (snap["tip"][0] - 40, snap["tip"][1])), snap["tip"])


if __name__ == "__main__":
    unittest.main()
