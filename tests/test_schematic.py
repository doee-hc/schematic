import unittest

from schematic.engine import layout
from schematic.graph import (
    AND_W,
    BUF_W,
    ICG_H,
    ICG_H_TE,
    ICG_W,
    OR_W,
    XOR_GAP,
    XOR_W,
    PortFilter,
    document_to_elk,
    port_id,
)
from schematic.document import load_document, normalize_document
from schematic.render import draw
from schematic.server import QuietThreadingHTTPServer, document_api_payload, make_handler
from schematic.svg import (
    BUBBLE_R,
    GATE_MARGIN,
    _abs_origins,
    _attach,
    _collect_ports,
    _gate_border_point,
    _mux_border_point,
    _mux_polygon,
    _or_back_point,
    _or_metrics,
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
        other = pins[port_id("m.mux", "b")]
        self.assertLess(snap["tip"][1], other["tip"][1])
        south = next(item for item in labels if item[3] == "sib")
        self.assertLess(south[1], max(pts[2][1], pts[3][1]))
        self.assertEqual(snap.get("shape"), "snap")
        expected = _mux_border_point(x, y, w, h, snap["side"], snap["tip"][1])
        self.assertAlmostEqual(snap["tip"][0], expected[0], places=2)
        self.assertAlmostEqual(snap["tip"][1], expected[1], places=2)
        self.assertEqual(_attach(snap, (snap["tip"][0] - 40, snap["tip"][1])), snap["tip"])


def _wrap(children, edges=None, ports=None):
    return {
        "root": {
            "id": "top",
            "title": "top",
            "shape": "box",
            "ports": ports or [],
            "edges": edges or [],
            "children": children,
        }
    }


def _and_ports(count, bubble_at=None, out_bubble=False):
    ports = []
    for index in range(count):
        port = {"name": "i%d" % index, "side": "west", "dir": "in"}
        if bubble_at is not None and index == bubble_at:
            port["bubble"] = True
        ports.append(port)
    out = {"name": "y", "side": "east", "dir": "out"}
    if out_bubble:
        out["bubble"] = True
    ports.append(out)
    return ports


class GateTests(unittest.TestCase):
    def test_rejects_bad_pins(self):
        cases = [
            (_wrap([{
                "id": "top.and", "shape": "and",
                "ports": _and_ports(1),
            }]), "至少需要两个西侧输入"),
            (_wrap([{
                "id": "top.or", "shape": "or",
                "ports": _and_ports(2) + [{"name": "sel", "side": "south", "dir": "in"}],
            }]), "只允许西侧输入和东侧输出"),
            (_wrap([{
                "id": "top.buf", "shape": "buf",
                "ports": _and_ports(2),
            }]), "恰好一个西侧输入"),
            (_wrap([{
                "id": "top.and", "shape": "and",
                "ports": _and_ports(2),
                "children": [{"id": "top.and.x", "shape": "box"}],
            }]), "不能有子节点"),
            (_wrap([{
                "id": "top.icg", "shape": "icg",
                "ports": [
                    {"name": "clk", "side": "south", "dir": "in"},
                    {"name": "gclk", "side": "east", "dir": "out"},
                ],
            }]), "en 必须在西侧"),
            (_wrap([{
                "id": "top.icg", "shape": "icg",
                "ports": [
                    {"name": "en", "side": "west", "dir": "in"},
                    {"name": "clk", "side": "south", "dir": "in"},
                    {"name": "y", "side": "east", "dir": "out"},
                    {"name": "z", "side": "east", "dir": "out"},
                ],
            }]), "恰好一个东侧输出"),
            (_wrap([{
                "id": "top.icg", "shape": "icg",
                "ports": [
                    {"name": "en", "side": "west", "dir": "in"},
                    {"name": "te", "side": "south", "dir": "in"},
                    {"name": "clk", "side": "south", "dir": "in"},
                    {"name": "gclk", "side": "east", "dir": "out"},
                ],
            }]), "te 必须在西侧"),
            (_wrap([{
                "id": "top.icg", "shape": "icg",
                "ports": [
                    {"name": "en", "side": "west", "dir": "in"},
                    {"name": "se", "side": "west", "dir": "in"},
                    {"name": "clk", "side": "south", "dir": "in"},
                    {"name": "gclk", "side": "east", "dir": "out"},
                ],
            }]), "未约定的端口"),
        ]
        for doc, text in cases:
            with self.assertRaises(ValueError) as caught:
                document_to_elk(doc)
            self.assertIn(text, str(caught.exception))

    def test_size_bubble_and_order(self):
        wide = "streaming_through_ijtag_en_and"
        doc = _wrap([
            {"id": "top.and", "title": wide, "shape": "and", "ports": _and_ports(2, bubble_at=1, out_bubble=True)},
            {"id": "top.and_short", "title": "a", "shape": "and", "ports": _and_ports(2, bubble_at=1, out_bubble=True)},
            {"id": "top.wide", "title": wide, "shape": "and", "ports": _and_ports(8)},
            {"id": "top.buf", "title": wide, "shape": "buf", "ports": [
                {"name": "a", "side": "west", "dir": "in"},
                {"name": "y", "side": "east", "dir": "out", "bubble": True},
            ]},
            {"id": "top.or", "shape": "or", "ports": _and_ports(2)},
            {"id": "top.xor", "shape": "xor", "ports": _and_ports(2)},
            {"id": "top.icg", "shape": "icg", "ports": [
                {"name": "en", "side": "west", "dir": "in"},
                {"name": "clk", "side": "south", "dir": "in"},
                {"name": "gclk", "side": "east", "dir": "out"},
            ]},
            {"id": "top.icg_te", "shape": "icg", "ports": [
                {"name": "en", "side": "west", "dir": "in"},
                {"name": "te", "side": "west", "dir": "in"},
                {"name": "clk", "side": "south", "dir": "in"},
                {"name": "gclk", "side": "east", "dir": "out"},
            ]},
        ])
        nodes = _nodes(document_to_elk(doc))
        and_node = nodes["top.and"]
        self.assertEqual(and_node["width"], nodes["top.and_short"]["width"])
        self.assertGreater(nodes["top.wide"]["width"], and_node["width"])
        self.assertGreater(nodes["top.wide"]["height"], and_node["height"])
        self.assertEqual(nodes["top.buf"]["width"], BUF_W)
        self.assertGreater(nodes["top.or"]["width"], nodes["top.or"]["height"])
        self.assertGreater(nodes["top.xor"]["width"], nodes["top.or"]["width"])
        self.assertEqual(nodes["top.icg"]["width"], ICG_W)
        self.assertEqual(nodes["top.icg"]["height"], ICG_H)
        self.assertEqual(nodes["top.icg_te"]["height"], ICG_H_TE)
        bubbled = [
            port for port in and_node["ports"]
            if (port.get("properties") or {}).get("bubble") == "true"
        ]
        self.assertEqual(sorted(port["properties"]["name"] for port in bubbled), ["i1", "y"])
        west = [port for port in and_node["ports"] if port["layoutOptions"]["elk.port.side"] == "WEST"]
        first = next(port for port in west if port["properties"]["name"] == "i0")
        second = next(port for port in west if port["properties"]["name"] == "i1")
        self.assertLess(first["y"], second["y"])

    def test_boxes_only_and_port_filter(self):
        doc = _wrap([
            {"id": "top.and", "shape": "and", "ports": _and_ports(2)},
            {"id": "top.leaf", "shape": "box", "ports": [{"name": "x", "side": "west", "dir": "in"}]},
        ])
        hidden = _nodes(document_to_elk(doc, {"boxes_only": True}))
        self.assertIn("top.leaf", hidden)
        self.assertNotIn("top.and", hidden)
        kept = _nodes(document_to_elk(doc, {"port_exclude": ["*"]}))
        names = {port["properties"]["name"] for port in kept["top.and"]["ports"]}
        self.assertEqual(names, {"i0", "i1", "y"})

    def test_logic_seq_kind_clock_notch(self):
        doc = _wrap([{
            "id": "top.ue",
            "title": "tdr_update",
            "shape": "logic",
            "kind": "seq",
            "expr": "ue & tdr_en → fields",
            "ports": [
                {"name": "ue", "side": "west", "dir": "in"},
                {"name": "y", "side": "east", "dir": "out"},
            ],
        }])
        node = _nodes(document_to_elk(doc))["top.ue"]
        self.assertEqual(node["properties"].get("kind"), "seq")
        svg = draw(doc)
        self.assertIn('data-logic-kind="seq"', svg)
        start = svg.find('data-logic-kind="seq"')
        chunk = svg[start : start + 900]
        self.assertIn('rx="14"', chunk)
        self.assertIn("<polygon", chunk)

    def test_logic_kind_invalid(self):
        doc = _wrap([{"id": "top.x", "shape": "logic", "kind": "flop", "ports": []}])
        with self.assertRaises(ValueError):
            document_to_elk(doc)

    def test_logic_ports_are_spaced(self):
        doc = _wrap([{
            "id": "top.fn",
            "shape": "logic",
            "expr": "(a & ~b & c) | q ^ c",
            "ports": [
                {"name": "a", "side": "west", "dir": "in"},
                {"name": "b", "side": "west", "dir": "in"},
                {"name": "c", "side": "west", "dir": "in"},
                {"name": "q", "side": "west", "dir": "in"},
                {"name": "y", "side": "east", "dir": "out"},
            ],
        }])
        node = _nodes(document_to_elk(doc))["top.fn"]
        west = [
            port for port in node["ports"]
            if port["layoutOptions"]["elk.port.side"] == "WEST"
        ]
        ys = [port["y"] for port in west]
        gaps = [b - a for a, b in zip(ys, ys[1:])]
        self.assertGreaterEqual(min(gaps), 18.0)
        self.assertLess(ys[0], ys[-1])

    def test_outline_bulges_the_right_way(self):
        metrics = _or_metrics(0, 0, OR_W, 48, False)
        mid = _or_back_point(metrics, metrics["mid"])
        self.assertGreater(mid[0], metrics["end_x"])
        xor = _or_metrics(0, 0, XOR_W, 48, True)
        self.assertLess(xor["left"] - xor["xor_gap"], xor["left"])
        east = _gate_border_point(0, 0, AND_W, 48, "and", "EAST", 24)
        west = _gate_border_point(0, 0, AND_W, 48, "and", "WEST", 24, "i0")
        self.assertGreater(east[0], west[0])
        self.assertAlmostEqual(west[0], GATE_MARGIN, places=2)
        xor_border = _gate_border_point(0, 0, XOR_W, 56, "xor", "WEST", 28, "a")
        inner = _or_back_point(_or_metrics(0, 0, XOR_W, 56, True), xor_border[1])
        self.assertAlmostEqual(inner[0] - xor_border[0], XOR_GAP, places=2)

    def test_drawing_and_wire_ends(self):
        graph = {
            "id": "root",
            "width": 520,
            "height": 160,
            "children": [
                {
                    "id": "and", "x": 10, "y": 30, "width": AND_W, "height": 48,
                    "labels": [{"text": "and3"}],
                    "properties": {"shape": "and"},
                    "ports": [{
                        "id": "and__b", "x": 0, "y": 16, "width": 0, "height": 0,
                        "labels": [{"text": "b"}],
                        "properties": {"name": "b", "bubble": "true"},
                        "layoutOptions": {"elk.port.side": "WEST"},
                    }],
                },
                {
                    "id": "or", "x": 90, "y": 30, "width": OR_W, "height": 48,
                    "labels": [{"text": "or2"}],
                    "properties": {"shape": "or"},
                    "ports": [],
                },
                {
                    "id": "xor", "x": 170, "y": 30, "width": XOR_W, "height": 48,
                    "labels": [{"text": "xor2"}],
                    "properties": {"shape": "xor"},
                    "ports": [],
                },
                {
                    "id": "buf", "x": 260, "y": 30, "width": BUF_W, "height": 40,
                    "labels": [{"text": "inv"}],
                    "properties": {"shape": "buf"},
                    "ports": [],
                },
                {
                    "id": "icg", "x": 330, "y": 20, "width": ICG_W, "height": ICG_H_TE,
                    "labels": [{"text": "icg"}],
                    "properties": {"shape": "icg"},
                    "ports": [
                        {"id": "icg__te", "properties": {"name": "te"}, "labels": [{"text": "te"}]},
                    ],
                },
            ],
            "edges": [],
        }
        svg = render_svg(graph)
        for shape in ("and", "or", "xor", "buf", "icg"):
            self.assertIn('data-shape="%s"' % shape, svg)
        self.assertIn('class="gate-title"', svg)
        self.assertIn('class="gate-bubble"', svg)
        self.assertIn('class="gate-stroke"', svg)
        self.assertIn("#e7f0fb", svg)
        self.assertIn("#fff3e0", svg)

        doc = _wrap(
            [{
                "id": "top.and",
                "title": "and3",
                "shape": "and",
                "ports": [
                    {"name": "a", "side": "west", "dir": "in"},
                    {"name": "b", "side": "west", "dir": "in", "bubble": True},
                    {"name": "c", "side": "west", "dir": "in"},
                    {"name": "y", "side": "east", "dir": "out", "bubble": True},
                ],
            }],
            edges=[
                {"from": "top.a", "to": "top.and.a"},
                {"from": "top.b", "to": "top.and.b"},
                {"from": "top.c", "to": "top.and.c"},
                {"from": "top.and.y", "to": "top.y"},
            ],
            ports=[
                {"name": "a", "side": "west", "dir": "in"},
                {"name": "b", "side": "west", "dir": "in"},
                {"name": "c", "side": "west", "dir": "in"},
                {"name": "y", "side": "east", "dir": "out"},
            ],
        )
        laid = layout(document_to_elk(doc))
        origins = _abs_origins(laid)
        pins, labels = _collect_ports(laid, origins)
        node = _nodes(laid)["top.and"]
        x, y = origins["top.and"]
        w = float(node["width"])
        h = float(node["height"])
        plain = pins[port_id("top.and", "a")]
        bubbled = pins[port_id("top.and", "b")]
        output = pins[port_id("top.and", "y")]
        plain_border = _gate_border_point(x, y, w, h, "and", "WEST", plain["tip"][1], "a")
        bubbled_border = _gate_border_point(x, y, w, h, "and", "WEST", bubbled["tip"][1], "b")
        out_border = _gate_border_point(x, y, w, h, "and", "EAST", output["tip"][1], "y")
        self.assertAlmostEqual(plain["tip"][0], plain_border[0], places=2)
        self.assertAlmostEqual(plain["tip"][0], x + GATE_MARGIN, places=2)
        self.assertAlmostEqual(bubbled["tip"][0], bubbled_border[0] - 2.0 * BUBBLE_R, places=2)
        self.assertAlmostEqual(output["tip"][0], out_border[0] + 2.0 * BUBBLE_R, places=2)
        self.assertAlmostEqual(out_border[0], x + w - GATE_MARGIN, places=2)
        self.assertTrue(any(item[3] == "a" for item in labels))
        self.assertTrue(any(item[3] == "y" for item in labels))
        drawn = draw(doc)
        self.assertEqual(drawn.count('class="gate-bubble"'), 2)

    def test_compound_south_port_lays_out(self):
        doc = {
            "root": {
                "id": "top",
                "title": "t",
                "shape": "box",
                "ports": [
                    {"name": "d", "side": "west", "dir": "in"},
                    {"name": "dir", "side": "south", "dir": "in"},
                    {"name": "y", "side": "east", "dir": "out"},
                ],
                "edges": [
                    {"from": "top.d", "to": "top.m.a"},
                    {"from": "top.dir", "to": "top.m.sel"},
                    {"from": "top.m.y", "to": "top.y"},
                ],
                "children": [{
                    "id": "top.m",
                    "shape": "mux",
                    "ports": [
                        {"name": "a", "side": "west", "dir": "in"},
                        {"name": "b", "side": "west", "dir": "in"},
                        {"name": "sel", "side": "south", "dir": "in"},
                        {"name": "y", "side": "east", "dir": "out"},
                    ],
                }],
            }
        }
        graph = document_to_elk(doc)
        self.assertEqual(
            graph["layoutOptions"]["elk.layered.nodePlacement.strategy"],
            "BRANDES_KOEPF",
        )
        laid = layout(graph)
        self.assertGreater(laid.get("width") or 0, 0)
        ports = _nodes(laid)["top"]["ports"]
        south = [port for port in ports if port["layoutOptions"]["elk.port.side"] == "SOUTH"]
        self.assertEqual(len(south), 1)
        self.assertGreater(south[0].get("x") or 0, 0)

    def test_complex_examples_draw(self):
        import os
        root = os.path.join(os.path.dirname(__file__), "..", "examples")
        for name, title in (
            ("adder.json", "adder4"),
            ("multiplier.json", "mul4"),
            ("shifter.json", "barrel4"),
            ("comparator.json", "cmp4"),
            ("accumulator.json", "acc4"),
        ):
            svg = draw(load_document(os.path.join(root, name)))
            self.assertIn(title, svg)
            self.assertIn("<svg", svg)


    def test_inline_mux_title_hover_svg(self):
        doc = normalize_document({
            "root": {
                "id": "top",
                "title": "t",
                "shape": "box",
                "children": [{
                    "id": "m",
                    "title": "SCAN_OUT_d",
                    "shape": "mux",
                    "badge": "SO",
                    "ports": [
                        {"name": "a", "side": "west", "dir": "in", "label": "bypass"},
                        {"name": "b", "side": "west", "dir": "in", "label": "shift"},
                        {"name": "sel", "side": "south", "dir": "in"},
                        {"name": "y", "side": "east", "dir": "out"},
                    ],
                }],
            },
        })
        svg = draw(doc)
        self.assertIn("<title>SCAN_OUT_d", svg)
        self.assertIn("bypass", svg)

    def test_cell_desc_hover_svg(self):
        import os

        from schematic.elaborate import load_schematic

        root = os.path.join(os.path.dirname(__file__), "..", "examples")
        doc = load_schematic(json_paths=[os.path.join(root, "gates.json")])
        svg = draw(doc)
        self.assertIn("<title>", svg)
        self.assertIn("三输入与门", svg)
        self.assertIn("输入 A", svg)
        self.assertIn("data-module-lib=", svg)

    def test_normalize_document_requires_root(self):
        with self.assertRaises(ValueError):
            normalize_document({})

    def test_viewer_open_document_api(self):
        import json
        import os
        import threading
        import urllib.error
        import urllib.request

        server = QuietThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(), log_to_stderr=False,
        )
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = "http://127.0.0.1:%s" % port
            with urllib.request.urlopen(base + "/api/document") as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["loaded"])

            doc = load_document(os.path.join(os.path.dirname(__file__), "..", "examples", "gates.json"))
            body = json.dumps({"name": "gates.json", "document": doc}).encode("utf-8")
            req = urllib.request.Request(
                base + "/api/document",
                data=body,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req) as resp:
                opened = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(opened["loaded"])
            self.assertEqual(opened["name"], "gates.json")
            self.assertIsInstance(opened["tree"], dict)

            draw_body = json.dumps({"include": [opened["tree"]["full_name"]]}).encode("utf-8")
            draw_req = urllib.request.Request(
                base + "/api/draw",
                data=draw_body,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(draw_req) as resp:
                drawn = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(drawn["ok"])
            self.assertIn("<svg", drawn["svg"])

            server.schematic_document = None
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(draw_req)
        finally:
            server.shutdown()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
