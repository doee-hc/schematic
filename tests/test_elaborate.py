import json
import os
import tempfile
import unittest

from schematic.document import load_document
from schematic.elaborate import elaborate_view, load_builtin_libs, load_schematic, merge_sources
from schematic.graph import index_nodes


def _edge_set(doc):
    out = set()

    def walk(node):
        for edge in node.get("edges") or []:
            out.add((edge["from"], edge["to"]))
        for child in node.get("children") or []:
            walk(child)

    walk(doc["root"])
    return out


def _node_ids(doc):
    nodes, _ = index_nodes(doc["root"])
    return set(nodes.keys())


class ElaborateTests(unittest.TestCase):
    def test_adder_filelist_matches_flat(self):
        root = os.path.join(os.path.dirname(__file__), "..", "examples")
        flat = load_document(os.path.join(root, "adder.json"))
        mod = load_schematic(
            filelists=[os.path.join(root, "adder.f")],
        )
        self.assertEqual(_node_ids(flat), _node_ids(mod))
        self.assertEqual(_edge_set(flat), _edge_set(mod))

    def test_filelist_double_slash_comments(self):
        root = os.path.join(os.path.dirname(__file__), "..", "examples")
        with tempfile.TemporaryDirectory() as tmp:
            fl = os.path.join(tmp, "t.f")
            lib = os.path.join(root, "lib/full_adder.json")
            top = os.path.join(root, "adder_modular.json")
            with open(fl, "w", encoding="utf-8") as handle:
                handle.write("// header\n")
                handle.write("%s  // cell\n" % lib)
                handle.write("%s\n" % top)
            mod = load_schematic(filelists=[fl])
        flat = load_document(os.path.join(root, "adder.json"))
        self.assertEqual(_node_ids(flat), _node_ids(mod))

    def test_duplicate_lib_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, "a.json")
            body = {
                "libs": {
                    "and2": {
                        "desc": "dup",
                        "ports": [
                            {"name": "a", "side": "west", "dir": "in", "desc": "a"},
                            {"name": "b", "side": "west", "dir": "in", "desc": "b"},
                            {"name": "y", "side": "east", "dir": "out", "desc": "y"},
                        ],
                        "symbol": {
                            "viewBox": "0 0 10 10",
                            "svg": "<rect width='10' height='10' fill='__FILL__' stroke='__STROKE__'/>",
                            "anchors": {
                                "a": {"tip": [0, 5], "side": "WEST"},
                                "b": {"tip": [0, 7], "side": "WEST"},
                                "y": {"tip": [10, 5], "side": "EAST"},
                            },
                        },
                    }
                }
            }
            with open(a, "w", encoding="utf-8") as handle:
                json.dump(body, handle)
            with self.assertRaises(ValueError):
                merge_sources([a])

    def test_lib_custom_symbol(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sym.json")
            body = {
                "libs": {
                    "chip": {
                        "desc": "自定义块",
                        "ports": [
                            {"name": "a", "side": "west", "dir": "in", "desc": "入"},
                            {"name": "y", "side": "east", "dir": "out", "desc": "出"},
                        ],
                        "symbol": {
                            "viewBox": "0 0 40 20",
                            "svg": '<rect x="1" y="1" width="38" height="18" fill="__FILL__" stroke="__STROKE__"/>',
                            "anchors": {
                                "a": {"tip": [0, 10], "side": "WEST"},
                                "y": {"tip": [40, 10], "side": "EAST"},
                            },
                        },
                    }
                }
            }
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(body, handle)
            merged = merge_sources([path])
            self.assertIn("svg", merged["libs"]["chip"]["symbol"])

    def test_lib_desc_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, "a.json")
            body = {
                "libs": {
                    "mybuf": {
                        "desc": "测试缓冲",
                        "ports": [
                            {"name": "a", "side": "west", "dir": "in", "desc": "输入"},
                            {"name": "y", "side": "east", "dir": "out"},
                        ],
                        "symbol": {
                            "viewBox": "0 0 10 10",
                            "svg": "<rect width='10' height='10' fill='__FILL__' stroke='__STROKE__'/>",
                            "anchors": {
                                "a": {"tip": [0, 5], "side": "WEST"},
                                "y": {"tip": [10, 5], "side": "EAST"},
                            },
                        },
                    }
                }
            }
            with open(a, "w", encoding="utf-8") as handle:
                json.dump(body, handle)
            with self.assertRaises(ValueError) as ctx:
                merge_sources([a])
            self.assertIn("desc", str(ctx.exception))

    def test_user_lib_palette_and_use_lib(self):
        root = os.path.join(os.path.dirname(__file__), "..", "examples")
        doc = load_schematic(
            json_paths=[
                os.path.join(root, "lib/acme_cells.json"),
                os.path.join(root, "acme_demo.json"),
            ],
        )
        nodes, _ = index_nodes(doc["root"])
        u1 = nodes["top.u1"]
        u2 = nodes["top.u2"]
        self.assertEqual(u1.get("meta", {}).get("lib"), "acme_and3")
        self.assertIn("svg", (u1.get("symbol") or {}))
        self.assertEqual(u1.get("desc"), "Acme 三输入与门")
        self.assertEqual(u1.get("swatch"), "acme:alu")
        self.assertEqual(u2.get("meta", {}).get("lib"), "acme_or2")
        self.assertEqual(u2.get("shape"), "cell")
        self.assertEqual(doc.get("palette", {}).get("acme:alu"), "#FFE8F0")
        bub = [
            p for p in u2.get("ports") or []
            if p.get("name") == "y"
        ]
        self.assertTrue(bub and bub[0].get("bubble"))

    def test_user_lib_via_filelist(self):
        root = os.path.join(os.path.dirname(__file__), "..", "examples")
        doc = load_schematic(filelists=[os.path.join(root, "acme_demo.f")])
        nodes, _ = index_nodes(doc["root"])
        self.assertIn("top.u1", nodes)
        self.assertEqual(nodes["top.u1"].get("meta", {}).get("lib"), "acme_and3")

    def test_builtin_mux2_use_lib(self):
        self.assertIn("mux2", load_builtin_libs())
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.json")
            body = {
                "root": {
                    "id": "top",
                    "title": "t",
                    "shape": "box",
                    "children": [{"id": "m", "use_lib": "mux2", "title": "u"}],
                },
            }
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(body, handle)
            doc = load_schematic(json_paths=[path])
        nodes, _ = index_nodes(doc["root"])
        mux = nodes["top.m"]
        self.assertEqual(mux.get("meta", {}).get("lib"), "mux2")
        self.assertEqual(mux.get("shape"), "cell")
        self.assertEqual(mux.get("desc"), "二选一数据多路器")

    def test_gates_use_lib_elaborates(self):
        root = os.path.join(os.path.dirname(__file__), "..", "examples")
        doc = load_schematic(json_paths=[os.path.join(root, "gates.json")])
        nodes, _ = index_nodes(doc["root"])
        and3 = nodes["top.and3"]
        self.assertEqual(and3.get("meta", {}).get("lib"), "and3_b_bub_y_bub")
        self.assertEqual(and3.get("shape"), "cell")

    def test_duplicate_module_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, "a.json")
            b = os.path.join(tmp, "b.json")
            body = {"modules": {"cell": {"title": "c", "shape": "box"}}}
            with open(a, "w", encoding="utf-8") as handle:
                json.dump(body, handle)
            with open(b, "w", encoding="utf-8") as handle:
                json.dump(body, handle)
            with self.assertRaises(ValueError):
                merge_sources([a, b])

    def test_port_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "m.json")
            payload = {
                "modules": {
                    "leaf": {
                        "shape": "box",
                        "ports": [{"name": "x", "side": "west", "dir": "in"}],
                        "edges": [],
                        "children": [],
                    },
                    "topmod": {
                        "shape": "box",
                        "ports": [{"name": "a", "side": "west", "dir": "in"}],
                        "edges": [{"from": "a", "to": "u.pin"}],
                        "children": [
                            {
                                "id": "u",
                                "use": "leaf",
                                "port_map": {"pin": "x"},
                            }
                        ],
                    },
                },
                "root": "topmod",
            }
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            out = load_schematic(json_paths=[path])
        nodes, _ = index_nodes(out["root"])
        self.assertIn("top.u", nodes)
        port_names = {p["name"] for p in nodes["top.u"].get("ports") or []}
        self.assertEqual(port_names, {"pin"})
        self.assertEqual(_edge_set(out), {("top.a", "top.u.pin")})

    def test_view_stubs_nested_instances(self):
        root = os.path.join(os.path.dirname(__file__), "..", "examples")
        merged = merge_sources([
            os.path.join(root, "lib/full_adder.json"),
            os.path.join(root, "adder_modular.json"),
        ])
        view = elaborate_view(merged, "adder4", set())
        nodes, _ = index_nodes(view["root"])
        fa0 = nodes["top.fa0"]
        self.assertEqual(fa0.get("children") or [], [])
        self.assertTrue(fa0.get("meta", {}).get("stub"))
        full = load_schematic(
            json_paths=[
                os.path.join(root, "lib/full_adder.json"),
                os.path.join(root, "adder_modular.json"),
            ],
        )
        self.assertGreater(len(_node_ids(full)), len(_node_ids(view)))

    def test_view_expand_one_instance(self):
        root = os.path.join(os.path.dirname(__file__), "..", "examples")
        merged = merge_sources([
            os.path.join(root, "lib/full_adder.json"),
            os.path.join(root, "adder_modular.json"),
        ])
        view = elaborate_view(merged, "adder4", {"top.fa0"})
        nodes, _ = index_nodes(view["root"])
        fa0 = nodes["top.fa0"]
        self.assertTrue(fa0.get("children"))
        self.assertFalse(fa0.get("meta", {}).get("stub"))
        for child in fa0.get("children") or []:
            meta = child.get("meta") or {}
            if meta.get("use"):
                self.assertTrue(meta.get("stub"))


if __name__ == "__main__":
    unittest.main()
