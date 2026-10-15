import copy
import unittest
import xml.etree.ElementTree as ET

from schematic.elaborate import load_builtin_libs
from schematic.engine import layout
from schematic.graph import PortFilter, document_to_elk, port_id
from schematic.document import load_document, normalize_document
from schematic.render import draw, draw_drawio
from schematic.server import QuietThreadingHTTPServer, document_api_payload, make_handler
from schematic.svg import _abs_origins, _attach, _collect_ports, render_svg


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


def _lib_cell(node_id, lib_name, **extra):
    lib = load_builtin_libs()[lib_name]
    ports = copy.deepcopy(lib.get("ports") or [])
    for patch in extra.get("port_patches") or []:
        for port in ports:
            if port.get("name") == patch.get("name"):
                port.update({k: v for k, v in patch.items() if k != "name"})
    node = {
        "id": node_id,
        "shape": "cell",
        "title": extra.get("title", lib.get("title", lib_name)),
        "swatch": extra.get("swatch", lib.get("swatch", "")),
        "badge": extra.get("badge", lib.get("badge")),
        "symbol": copy.deepcopy(lib["symbol"]),
        "ports": ports,
        "meta": {"kind": "cell", "lib": lib_name},
    }
    if extra.get("note") is not None:
        node["note"] = extra["note"]
    return node


def _doc():
    return {
        "libs": load_builtin_libs(),
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
                _lib_cell(
                    "top.mux",
                    "mux2",
                    title="scan_in_mux",
                    badge="CLK",
                    port_patches=[
                        {"name": "a", "label": "1'b0"},
                        {"name": "b", "label": "1'b1"},
                    ],
                ),
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
        self.assertEqual(nodes["top.mux"]["properties"]["shape"], "cell")
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
                "children": [
                    _lib_cell("m.mux", "mux2", title="streaming_through_ijtag_en_si_mux"),
                ],
            }
        }
        doc["libs"] = load_builtin_libs()
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
                    "x": 130, "y": 40, "width": 96, "height": 76,
                    "labels": [{"text": "scan_in_mux"}],
                    "properties": {"shape": "cell", "module_lib": "mux2", "badge": "CLK"},
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
        libs = load_builtin_libs()
        svg = render_svg(graph, libs=libs)
        self.assertIn('data-shape="reg"', svg)
        start = svg.find('data-shape="reg"')
        self.assertNotIn('rx="', svg[start:svg.find("</g>", start)])
        self.assertIn("#eee8f8", svg)
        self.assertIn('data-shape="cell"', svg)
        self.assertIn('class="gate-title"', svg)
        self.assertIn('data-symbol-cell="true"', svg)
        self.assertIn('data-shape="logic"', svg)
        self.assertIn('rx="14"', svg)
        self.assertIn("enable, sib == 2'b11", svg)

    def test_draw_invert_and_palette(self):
        svg = draw(_doc(), {"include": ["top", "top.mux", "top.reg", "top.logic"]})
        self.assertIn('class="edge-invert"', svg)
        self.assertIn('data-shape="cell"', svg)
        self.assertIn('data-shape="reg"', svg)
        self.assertIn("#3D7ECC", svg)

    def test_mux_wires_meet_border(self):
        doc = _wrap([_lib_cell("m.mux", "mux2", title="mux")])
        doc["root"]["id"] = "m"
        doc["root"]["ports"] = [
            {"name": "si", "side": "west", "dir": "in"},
            {"name": "so", "side": "east", "dir": "out"},
        ]
        doc["root"]["edges"] = [
            {"from": "m.si", "to": "m.mux.a"},
            {"from": "m.mux.y", "to": "m.so"},
        ]
        libs = doc["libs"]
        laid = layout(document_to_elk(doc))
        origins = _abs_origins(laid)
        pins, _labels = _collect_ports(laid, origins, libs=libs)
        snap = pins[port_id("m.mux", "a")]
        other = pins[port_id("m.mux", "b")]
        self.assertLess(snap["tip"][1], other["tip"][1])
        self.assertEqual(snap.get("shape"), "snap")
        self.assertEqual(_attach(snap, (snap["tip"][0] - 40, snap["tip"][1])), snap["tip"])


def _wrap(children, edges=None, ports=None):
    return {
        "libs": load_builtin_libs(),
        "root": {
            "id": "top",
            "title": "top",
            "shape": "box",
            "ports": ports or [],
            "edges": edges or [],
            "children": children,
        },
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
    def test_rejects_legacy_gate_shapes(self):
        cases = [
            (_wrap([{"id": "top.g", "shape": "and", "ports": []}]), "未知外形"),
            (_wrap([{"id": "top.g", "shape": "cell", "ports": []}]), "缺少 symbol"),
        ]
        for doc, text in cases:
            with self.assertRaises(ValueError) as caught:
                document_to_elk(doc)
            self.assertIn(text, str(caught.exception))

    def test_size_bubble_and_order(self):
        doc = _wrap([
            _lib_cell("top.and2", "and2"),
            _lib_cell("top.and3", "and3"),
            _lib_cell("top.inv", "inv"),
            _lib_cell("top.or2", "or2"),
            _lib_cell("top.xor2", "xor2"),
            _lib_cell("top.icg", "icg"),
        ])
        nodes = _nodes(document_to_elk(doc))
        self.assertGreater(nodes["top.and3"]["width"], nodes["top.and2"]["width"])
        self.assertGreater(nodes["top.xor2"]["width"], nodes["top.or2"]["width"])
        inv = nodes["top.inv"]
        bubbled = [
            port for port in inv["ports"]
            if (port.get("properties") or {}).get("bubble") == "true"
        ]
        self.assertEqual([port["properties"]["name"] for port in bubbled], ["y"])
        west = [port for port in nodes["top.and2"]["ports"] if port["layoutOptions"]["elk.port.side"] == "WEST"]
        first = next(port for port in west if port["properties"]["name"] == "a")
        second = next(port for port in west if port["properties"]["name"] == "b")
        self.assertLess(first["y"], second["y"])

    def test_boxes_only_and_port_filter(self):
        doc = _wrap([
            _lib_cell("top.and2", "and2"),
            {"id": "top.leaf", "shape": "box", "ports": [{"name": "x", "side": "west", "dir": "in"}]},
        ])
        hidden = _nodes(document_to_elk(doc, {"boxes_only": True}))
        self.assertIn("top.leaf", hidden)
        self.assertNotIn("top.and2", hidden)
        kept = _nodes(document_to_elk(doc, {"port_exclude": ["*"]}))
        names = {port["properties"]["name"] for port in kept["top.and2"]["ports"]}
        self.assertEqual(names, {"a", "b", "y"})

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

    def test_cell_port_labels_inside_symbol(self):
        doc = _wrap([_lib_cell("top.u", "and2")])
        laid = layout(document_to_elk(doc))
        origins = _abs_origins(laid)
        libs = doc["libs"]
        _pins, labels = _collect_ports(laid, origins, libs=libs)
        x, y = origins["top.u"]
        sym = libs["and2"]["symbol"]
        from schematic.symbol import canvas_anchor

        for item in labels:
            if item[0] != "top.u":
                continue
            _nid, tx, _ty, anchor, name, _sw, port_id = item
            pname = port_id.rsplit("__", 1)[-1]
            tip = canvas_anchor(sym, pname, x, y)["tip"]
            side = (sym["anchors"][pname].get("side") or "WEST").upper()
            if side == "WEST":
                self.assertGreater(tx, tip[0], msg=name)
            elif side == "EAST":
                self.assertLess(tx, tip[0], msg=name)

    def test_cell_symbol_svg_is_well_formed_xml(self):
        doc = _wrap([_lib_cell("top.u", "xor2", swatch="gate")])
        svg = draw(doc)
        ET.fromstring(svg)
        self.assertNotRegex(svg, r'fill="[^"]+"\s+fill="')

    def test_drawing_and_wire_ends(self):
        libs = load_builtin_libs()
        graph = {
            "id": "root",
            "width": 520,
            "height": 160,
            "children": [
                {
                    "id": "xor", "x": 10, "y": 30,
                    "width": float(libs["xor2"]["symbol"]["viewBox"].split()[2]),
                    "height": float(libs["xor2"]["symbol"]["viewBox"].split()[3]),
                    "labels": [{"text": "xor2"}],
                    "properties": {"shape": "cell", "module_lib": "xor2"},
                    "ports": [],
                },
                {
                    "id": "inv", "x": 120, "y": 30,
                    "width": float(libs["inv"]["symbol"]["viewBox"].split()[2]),
                    "height": float(libs["inv"]["symbol"]["viewBox"].split()[3]),
                    "labels": [{"text": "inv"}],
                    "properties": {"shape": "cell", "module_lib": "inv", "swatch": "gate"},
                    "ports": [],
                },
            ],
            "edges": [],
        }
        svg = render_svg(graph, libs=libs)
        self.assertIn('data-shape="cell"', svg)
        self.assertIn('class="gate-title"', svg)
        self.assertIn("stroke-width=\"1.2\"", svg)
        self.assertIn("<circle", svg)

        doc = _wrap([_lib_cell("top.and3", "and3")])
        laid = layout(document_to_elk(doc))
        origins = _abs_origins(laid)
        pins, labels = _collect_ports(laid, origins, libs=doc["libs"])
        self.assertTrue(any(item[4] == "a" for item in labels))
        self.assertIn('data-symbol-cell="true"', draw(doc))

    def test_compound_south_port_lays_out(self):
        doc = _wrap([
            _lib_cell("top.m", "mux2"),
        ])
        doc["root"]["ports"] = [
            {"name": "d", "side": "west", "dir": "in"},
            {"name": "dir", "side": "south", "dir": "in"},
            {"name": "y", "side": "east", "dir": "out"},
        ]
        doc["root"]["edges"] = [
            {"from": "top.d", "to": "top.m.a"},
            {"from": "top.dir", "to": "top.m.sel"},
            {"from": "top.m.y", "to": "top.y"},
        ]
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

    def test_drawio_native_adder(self):
        import os
        root = os.path.join(os.path.dirname(__file__), "..", "examples")
        xml = draw_drawio(load_document(os.path.join(root, "adder.json")), title="adder")
        self.assertIn("<mxfile", xml)
        self.assertIn("schematicId=", xml)
        self.assertIn("shape=image", xml)
        self.assertIn("schematicSymbol=1", xml)

    def test_drawio_native_gates_vector(self):
        import os
        from schematic.elaborate import load_schematic
        root = os.path.join(os.path.dirname(__file__), "..", "examples")
        doc = load_schematic([os.path.join(root, "gates.json")])
        xml = draw_drawio(doc, title="gates")
        self.assertIn("shape=image", xml)
        self.assertIn("schematicSymbol=1", xml)
        self.assertIn('edge="1"', xml)
        self.assertIn("jumpStyle=arc", xml)
        svg = draw(doc)
        self.assertIn('data-symbol-cell="true"', svg)

    def test_drawio_pentagon_edges_use_port_tips(self):
        import xml.etree.ElementTree as ET
        from schematic.drawio_edges import canvas_edge_points, schematic_edge_points
        from schematic.drawio_native import render_drawio_native
        from schematic.engine import layout
        from schematic.svg import prepare_scene

        doc = _wrap([
            {
                "id": "top.u",
                "title": "U",
                "shape": "box",
                "ports": [{"name": "a", "side": "west", "dir": "in"}],
                "children": [],
            },
        ])
        doc["root"]["ports"] = [{"name": "si", "side": "west", "dir": "in"}]
        doc["root"]["edges"] = [{"from": "top.si", "to": "top.u.a"}]
        graph = document_to_elk(doc)
        laid = layout(graph)
        scene = prepare_scene(laid, {}, libs=load_builtin_libs())
        ox, oy = scene["canvas"]["ox"], scene["canvas"]["oy"]
        dst_id = None
        for route in scene["routes"]:
            if route["dst"].endswith("__a"):
                dst_id = route["dst"]
                break
        self.assertIsNotNone(dst_id)
        dst_geom = scene["pins"][dst_id]
        self.assertEqual(dst_geom["side"], "WEST")
        route = next(r for r in scene["routes"] if r["dst"] == dst_id)
        attach = tuple(route["arrow"][1])
        end_pt = schematic_edge_points(route, scene["pins"])[-1]
        self.assertAlmostEqual(end_pt[0], attach[0], delta=0.5)
        self.assertAlmostEqual(end_pt[1], attach[1], delta=0.5)
        self.assertGreater(abs(end_pt[0] - float(route["pts"][-1][0])), 4.0)
        xml = render_drawio_native(laid, {}, title="top", libs=load_builtin_libs())
        expected = canvas_edge_points(route, scene["pins"], ox, oy)
        root_el = ET.fromstring(xml)
        edge_cells = [
            c for c in root_el.iter("mxCell")
            if c.get("edge") == "1" and c.get("source") is None
        ]
        self.assertGreaterEqual(len(edge_cells), 1)
        geo = edge_cells[0].find("mxGeometry")
        points = {p.get("as"): p for p in geo.findall("mxPoint")}
        tp = points["targetPoint"]
        self.assertAlmostEqual(float(tp.get("x")), expected[-1][0], delta=0.5)
        self.assertAlmostEqual(float(tp.get("y")), expected[-1][1], delta=0.5)

    def test_drawio_native_top_geometry(self):
        import os
        import re
        import xml.etree.ElementTree as ET
        from schematic.engine import layout
        from schematic.graph import document_to_elk
        from schematic.render import _preserve_edge_metadata, document_libs, merged_palette
        from schematic.drawio_vector import node_drawio_bbox
        from schematic.drawio_native import render_drawio_native
        from schematic.svg import prepare_scene

        root = os.path.join(os.path.dirname(__file__), "..", "examples")
        document = load_document(os.path.join(root, "top.json"))
        options = {}
        palette = merged_palette(document, options.get("palette"))
        libs = document_libs(document)
        graph = document_to_elk(document, options)
        laid = layout(graph)
        _preserve_edge_metadata(graph, laid)
        scene = prepare_scene(laid, palette, libs=libs)
        ox, oy = scene["canvas"]["ox"], scene["canvas"]["oy"]
        xml = render_drawio_native(laid, palette, title="top", libs=libs)
        raw = {}
        root_el = ET.fromstring(xml)
        for cell in root_el.iter("mxCell"):
            cid = cell.get("id")
            if not cid:
                continue
            raw[cid] = {
                "parent": cell.get("parent") or "0",
                "style": cell.get("style") or "",
                "geo": cell.find("mxGeometry"),
            }

        def abs_xy(schematic_id):
            cid = None
            for k, meta in raw.items():
                m = re.search(r"schematicId=%s;" % re.escape(schematic_id), meta["style"])
                if m:
                    cid = k
                    break
            self.assertIsNotNone(cid)
            x = y = 0.0
            cur = cid
            chain = []
            while cur and cur not in ("0", "1"):
                chain.append(cur)
                cur = raw[cur]["parent"]
            for cur in reversed(chain):
                geo = raw[cur]["geo"]
                if geo is not None:
                    x += float(geo.get("x") or 0)
                    y += float(geo.get("y") or 0)
            return x, y

        for node in scene["nodes"]:
            nid = node["id"]
            ax, ay = abs_xy(nid)
            x, y = scene["origins"][nid]
            w = float(node.get("width") or 0)
            h = float(node.get("height") or 0)
            lx, ly, _lw, _lh = node_drawio_bbox(node, x, y, w, h, palette)
            self.assertAlmostEqual(ax, lx + ox, delta=1.5)
            self.assertAlmostEqual(ay, ly + oy, delta=1.5)

    def test_drawio_native_occ(self):
        import os
        from schematic.elaborate import load_schematic
        occ_f = os.path.join(os.path.dirname(__file__), "..", "examples", "tessent_occ", "occ.f")
        doc = load_schematic([], filelists=[occ_f], top="processor_core_rtl2_tessent_occ")
        xml = draw_drawio(doc, title="occ")
        self.assertIn("<mxfile", xml)
        self.assertIn("<mxGraphModel", xml)

    def test_inline_mux_title_hover_svg(self):
        doc = normalize_document(_wrap([
            _lib_cell(
                "m",
                "mux2",
                title="SCAN_OUT_d",
                badge="SO",
                port_patches=[
                    {"name": "a", "label": "bypass"},
                    {"name": "b", "label": "shift"},
                ],
            ),
        ]))
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
