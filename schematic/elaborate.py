"""Merge module libraries and elaborate instances into a classic document."""

from __future__ import annotations

import copy
import json
import os

from schematic.document import normalize_document
from schematic.graph import index_nodes
from schematic.symbol import validate_symbol

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
BUILTIN_LIB_PATH = os.path.join(_PKG_DIR, "lib", "gates.json")

_INSTANCE_FORBIDDEN = ("children", "edges", "ports", "use_lib")
_CELL_FORBIDDEN = ("children", "edges", "ports", "use", "port_map")
_LIB_FORBIDDEN = ("children", "edges", "use", "use_lib", "id", "port_map")


def parse_filelist(path: str) -> list[str]:
    base = os.path.dirname(os.path.abspath(path))
    out: list[str] = []
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("//"):
                continue
            if "//" in line:
                line = line.split("//", 1)[0].strip()
            if not line:
                continue
            if not os.path.isabs(line):
                line = os.path.join(base, line)
            out.append(os.path.normpath(line))
    return out


def collect_source_paths(json_paths: list[str], filelists: list[str] | None) -> list[str]:
    paths = [os.path.normpath(p) for p in json_paths]
    for fl in filelists or []:
        paths.extend(parse_filelist(fl))
    if not paths:
        raise ValueError("需要至少一个 JSON 路径或 -f filelist")
    return paths


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("JSON 根必须是对象: %s" % path)
    return data


def _merge_swatches(existing: list, new_items) -> list:
    by_key = {}
    for item in existing or []:
        if isinstance(item, dict) and item.get("key"):
            by_key[item["key"]] = item
    for item in new_items or []:
        if isinstance(item, dict) and item.get("key"):
            by_key[item["key"]] = item
    return list(by_key.values())


def load_builtin_libs() -> dict[str, dict]:
    data = _load_json(BUILTIN_LIB_PATH)
    libs = data.get("libs")
    if not isinstance(libs, dict):
        raise ValueError("内置 lib 无效: %s" % BUILTIN_LIB_PATH)
    out = {}
    for name, body in libs.items():
        if not isinstance(name, str) or not name:
            raise ValueError("内置 lib 名无效")
        if not isinstance(body, dict):
            raise ValueError("内置 lib %s 必须是对象" % name)
        _validate_lib_body(name, body)
        out[name] = body
    return out


def _require_desc(value, where: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s 缺少 desc（简短功能描述）" % where)


def _validate_lib_body(name: str, lib: dict) -> None:
    if not isinstance(lib, dict):
        raise ValueError("lib %s 必须是对象" % name)
    for key in _LIB_FORBIDDEN:
        if lib.get(key):
            raise ValueError("lib %s 不能包含 %s" % (name, key))
    symbol = lib.get("symbol")
    if not symbol:
        raise ValueError("lib %s 缺少 symbol" % name)
    _require_desc(lib.get("desc"), "lib %s" % name)
    ports = lib.get("ports")
    if not ports:
        raise ValueError("lib %s 缺少 ports" % name)
    validate_symbol(name, symbol, ports)
    if ports is not None:
        if not isinstance(ports, list):
            raise ValueError("lib %s 的 ports 必须是数组" % name)
        for index, port in enumerate(ports):
            if not isinstance(port, dict):
                raise ValueError("lib %s ports[%d] 必须是对象" % (name, index))
            pname = port.get("name") or ("[%d]" % index)
            _require_desc(port.get("desc"), "lib %s 端口 %s" % (name, pname))


def merge_sources(paths: list[str]) -> dict:
    merged = {
        "modules": {},
        "libs": copy.deepcopy(load_builtin_libs()),
        "palette": {},
        "swatches": [],
        "root": None,
        "_root_declarations": 0,
    }
    builtin = _load_json(BUILTIN_LIB_PATH)
    if isinstance(builtin.get("palette"), dict):
        merged["palette"].update(builtin["palette"])
    merged["swatches"] = _merge_swatches(merged["swatches"], builtin.get("swatches"))
    for path in paths:
        data = _load_json(path)
        libs = data.get("libs")
        if libs is not None:
            if not isinstance(libs, dict):
                raise ValueError("libs 必须是对象: %s" % path)
            for name, body in libs.items():
                if not isinstance(name, str) or not name:
                    raise ValueError("lib 名无效: %s" % path)
                if name in merged["libs"]:
                    raise ValueError("重复的 lib %s（%s）" % (name, path))
                _validate_lib_body(name, body)
                merged["libs"][name] = body
        modules = data.get("modules")
        if modules is not None:
            if not isinstance(modules, dict):
                raise ValueError("modules 必须是对象: %s" % path)
            for name, body in modules.items():
                if not isinstance(name, str) or not name:
                    raise ValueError("module 名无效: %s" % path)
                if name in merged["modules"]:
                    raise ValueError("重复的 module %s（%s）" % (name, path))
                if not isinstance(body, dict):
                    raise ValueError("module %s 必须是对象: %s" % (name, path))
                merged["modules"][name] = body
        palette = data.get("palette")
        if isinstance(palette, dict):
            merged["palette"].update(palette)
        merged["swatches"] = _merge_swatches(merged["swatches"], data.get("swatches"))
        if "root" in data:
            merged["_root_declarations"] += 1
            if merged["_root_declarations"] > 1:
                raise ValueError("多个文件声明了 root: %s" % path)
            merged["root"] = data["root"]
    del merged["_root_declarations"]
    return merged


def tree_uses_modules(node: dict) -> bool:
    if not isinstance(node, dict):
        return False
    for child in node.get("children") or []:
        if not isinstance(child, dict):
            continue
        if child.get("use"):
            return True
        if tree_uses_modules(child):
            return True
    return False


def tree_uses_libs(node: dict) -> bool:
    if not isinstance(node, dict):
        return False
    for child in node.get("children") or []:
        if not isinstance(child, dict):
            continue
        if child.get("use_lib"):
            return True
        if tree_uses_libs(child):
            return True
    return False


def tree_needs_elaboration(node: dict) -> bool:
    return tree_uses_modules(node) or tree_uses_libs(node)


def _mod_port_names(mod: dict) -> set[str]:
    names = set()
    for port in mod.get("ports") or []:
        if isinstance(port, dict) and port.get("name"):
            names.add(port["name"])
    return names


def _external_port_name(module_port: str, port_map: dict) -> str:
    for inst, mod in port_map.items():
        if mod == module_port:
            return inst
    return module_port


def _resolve_module_endpoint(
    endpoint: str,
    prefix: str,
    module_port_names: set[str],
    child_ids: set[str],
    port_map: dict,
) -> str:
    if not endpoint or not isinstance(endpoint, str):
        raise ValueError("连线端点无效")
    if endpoint in module_port_names:
        return prefix + "." + _external_port_name(endpoint, port_map)
    if "." in endpoint:
        head = endpoint.split(".", 1)[0]
        if head in child_ids:
            return prefix + "." + endpoint
    raise ValueError("无法解析端点 %s（前缀 %s）" % (endpoint, prefix))


def _rewrite_edge(
    edge: dict,
    prefix: str,
    module_port_names: set[str],
    child_ids: set[str],
    port_map: dict,
) -> dict:
    if not isinstance(edge, dict):
        raise ValueError("连线必须是对象")
    out = copy.deepcopy(edge)
    for key in ("from", "to"):
        if key in out:
            out[key] = _resolve_module_endpoint(
                out[key], prefix, module_port_names, child_ids, port_map
            )
    return out


def _validate_instance(instance: dict) -> None:
    for key in _INSTANCE_FORBIDDEN:
        if instance.get(key):
            raise ValueError("实例 %s 不能包含 %s" % (instance.get("id"), key))


def _validate_relative_id(node_id: str, label: str) -> None:
    if not node_id or not isinstance(node_id, str):
        raise ValueError("%s 缺少 id" % label)
    if "." in node_id:
        raise ValueError("%s id 不能包含 '.': %s" % (label, node_id))


def _instance_shell(instance: dict, mod: dict, mod_name: str, prefix: str) -> dict:
    port_map = instance.get("port_map") or {}
    if port_map and not isinstance(port_map, dict):
        raise ValueError("port_map 必须是对象")
    node = {}
    for key in ("shape", "badge", "expr", "kind"):
        if key in mod:
            node[key] = copy.deepcopy(mod[key])
    node["id"] = prefix
    node["title"] = instance.get("title") if instance.get("title") is not None else mod.get("title")
    if node["title"] is None:
        node["title"] = prefix.split(".")[-1]
    if "swatch" in instance:
        node["swatch"] = copy.deepcopy(instance["swatch"])
    elif "swatch" in mod:
        node["swatch"] = copy.deepcopy(mod["swatch"])
    if "note" in instance:
        node["note"] = copy.deepcopy(instance["note"])
    elif "note" in mod:
        node["note"] = copy.deepcopy(mod["note"])
    node["ports"] = _instance_ports(mod, port_map)
    node["meta"] = {"kind": "instance", "use": mod_name, "stub": True}
    return node


def _stub_instance(instance: dict, modules: dict, parent_prefix: str) -> dict:
    _validate_instance(instance)
    _validate_relative_id(instance.get("id"), "实例")
    mod_name = instance.get("use")
    if not mod_name or mod_name not in modules:
        known = ", ".join(sorted(modules)) if modules else "（无）"
        raise ValueError("未知 module %s，已知: %s" % (mod_name, known))
    prefix = parent_prefix + "." + instance["id"]
    node = _instance_shell(instance, modules[mod_name], mod_name, prefix)
    node["children"] = []
    return node


def _instance_ports(mod: dict, port_map: dict) -> list:
    if not isinstance(port_map, dict):
        raise ValueError("port_map 必须是对象")
    mod_names = _mod_port_names(mod)
    for mapped in port_map.values():
        if mapped not in mod_names:
            raise ValueError("port_map 引用未知 module 端口 %s" % mapped)
    out = []
    for port in mod.get("ports") or []:
        if not isinstance(port, dict) or not port.get("name"):
            continue
        item = copy.deepcopy(port)
        item["name"] = _external_port_name(port["name"], port_map)
        out.append(item)
    return out


def _validate_cell(cell: dict) -> None:
    if cell.get("use") and cell.get("use_lib"):
        raise ValueError("节点 %s 不能同时 use 与 use_lib" % cell.get("id"))
    for key in _CELL_FORBIDDEN:
        if cell.get(key):
            raise ValueError("cell %s 不能包含 %s" % (cell.get("id"), key))
    if not cell.get("use_lib"):
        raise ValueError("cell %s 缺少 use_lib" % cell.get("id"))


_LEGACY_CELL_SHAPES = frozenset(("and", "or", "xor", "buf", "icg", "mux"))


def _reject_inline_gate(child: dict) -> None:
    shape = child.get("shape")
    if shape in _LEGACY_CELL_SHAPES:
        raise ValueError(
            "门级符号请用 use_lib 例化（内置库 %s）: %s"
            % (BUILTIN_LIB_PATH, child.get("id"))
        )


def _expand_cell(cell: dict, libs: dict, parent_prefix: str) -> dict:
    _validate_cell(cell)
    _validate_relative_id(cell.get("id"), "cell")
    lib_name = cell["use_lib"]
    if lib_name not in libs:
        known = ", ".join(sorted(libs)) if libs else "（无）"
        raise ValueError("未知 lib %s，已知: %s" % (lib_name, known))
    lib = libs[lib_name]
    prefix = parent_prefix + "." + cell["id"]
    node = {}
    for key in ("badge", "expr"):
        if key in lib:
            node[key] = copy.deepcopy(lib[key])
    node["shape"] = "cell"
    node["symbol"] = copy.deepcopy(lib["symbol"])
    node["id"] = prefix
    node["title"] = cell.get("title") if cell.get("title") is not None else lib.get("title")
    if node["title"] is None:
        node["title"] = prefix.split(".")[-1]
    if "swatch" in cell:
        node["swatch"] = copy.deepcopy(cell["swatch"])
    elif "swatch" in lib:
        node["swatch"] = copy.deepcopy(lib["swatch"])
    if "note" in cell:
        node["note"] = copy.deepcopy(cell["note"])
    elif "note" in lib:
        node["note"] = copy.deepcopy(lib["note"])
    if cell.get("desc") is not None:
        node["desc"] = copy.deepcopy(cell["desc"])
    elif lib.get("desc") is not None:
        node["desc"] = copy.deepcopy(lib["desc"])
    node["ports"] = copy.deepcopy(lib.get("ports") or [])
    node["meta"] = {"kind": "cell", "lib": lib_name}
    return node


def _dispatch_child(
    ch: dict,
    modules: dict,
    libs: dict,
    parent_prefix: str,
    stack: set[str],
    expanded_paths: set[str] | None,
) -> dict:
    if not isinstance(ch, dict):
        raise ValueError("子节点必须是对象")
    if ch.get("use_lib"):
        return _expand_cell(ch, libs, parent_prefix)
    if ch.get("use"):
        inst_path = parent_prefix + "." + ch["id"]
        if expanded_paths is None:
            return _expand_instance(ch, modules, libs, parent_prefix, stack, None)
        if inst_path in expanded_paths:
            return _expand_instance(ch, modules, libs, parent_prefix, stack, expanded_paths)
        return _stub_instance(ch, modules, parent_prefix)
    _reject_inline_gate(ch)
    return _elaborate_inline_child(ch, modules, libs, parent_prefix, stack, expanded_paths)


def _expand_module_def(
    mod_name: str,
    mod: dict,
    prefix: str,
    modules: dict,
    libs: dict,
    stack: set[str],
    overrides: dict | None,
    expanded_paths: set[str] | None = None,
) -> dict:
    if mod.get("id"):
        raise ValueError("module %s 定义不能含 id" % mod_name)
    if mod.get("use_lib"):
        raise ValueError("module %s 定义不能 use_lib" % mod_name)
    black_box = bool(mod.get("black_box"))
    if black_box and (mod.get("children") or mod.get("edges")):
        raise ValueError("black_box module %s 不能有 children/edges" % mod_name)
    overrides = overrides or {}
    port_map = overrides.get("port_map") or {}
    if port_map and not isinstance(port_map, dict):
        raise ValueError("port_map 必须是对象")

    mod_ports = mod.get("ports") or []
    module_port_names = _mod_port_names(mod)
    raw_children = [] if black_box else (mod.get("children") or [])
    child_ids = set()
    for ch in raw_children:
        if isinstance(ch, dict) and ch.get("id"):
            _validate_relative_id(ch["id"], "module %s 子节点" % mod_name)
            child_ids.add(ch["id"])

    children_out = []
    for ch in raw_children:
        children_out.append(
            _dispatch_child(ch, modules, libs, prefix, stack, expanded_paths)
        )

    node = {}
    for key in ("shape", "badge", "expr", "kind"):
        if key in mod:
            node[key] = copy.deepcopy(mod[key])
    node["id"] = prefix
    node["title"] = overrides.get("title") if overrides.get("title") is not None else mod.get("title")
    if node["title"] is None:
        node["title"] = prefix.split(".")[-1]
    if "swatch" in overrides:
        node["swatch"] = copy.deepcopy(overrides["swatch"])
    elif "swatch" in mod:
        node["swatch"] = copy.deepcopy(mod["swatch"])
    if "note" in overrides:
        node["note"] = copy.deepcopy(overrides["note"])
    elif "note" in mod:
        node["note"] = copy.deepcopy(mod["note"])
    if overrides.get("desc") is not None:
        node["desc"] = copy.deepcopy(overrides["desc"])
    elif mod.get("desc") is not None:
        node["desc"] = copy.deepcopy(mod["desc"])
    node["ports"] = _instance_ports(mod, port_map)
    node["children"] = children_out
    edges = []
    if not black_box:
        for edge in mod.get("edges") or []:
            edges.append(
                _rewrite_edge(edge, prefix, module_port_names, child_ids, port_map)
            )
    if edges:
        node["edges"] = edges
    if expanded_paths is not None and overrides:
        node["meta"] = {"kind": "instance", "use": mod_name, "stub": False}
    elif black_box and overrides:
        node["meta"] = {"kind": "instance", "use": mod_name, "stub": False}
    return node


def _expand_instance(
    instance: dict,
    modules: dict,
    libs: dict,
    parent_prefix: str,
    stack: set[str],
    expanded_paths: set[str] | None,
) -> dict:
    _validate_instance(instance)
    _validate_relative_id(instance.get("id"), "实例")
    mod_name = instance.get("use")
    if not mod_name or mod_name not in modules:
        known = ", ".join(sorted(modules)) if modules else "（无）"
        raise ValueError("未知 module %s，已知: %s" % (mod_name, known))
    if mod_name in stack:
        raise ValueError("循环 module: %s" % mod_name)
    prefix = parent_prefix + "." + instance["id"]
    stack_next = set(stack)
    stack_next.add(mod_name)
    return _expand_module_def(
        mod_name,
        modules[mod_name],
        prefix,
        modules,
        libs,
        stack_next,
        instance,
        expanded_paths,
    )


def _elaborate_inline_child(
    child: dict,
    modules: dict,
    libs: dict,
    parent_prefix: str,
    stack: set[str],
    expanded_paths: set[str] | None,
) -> dict:
    _validate_relative_id(child.get("id"), "节点")
    if child.get("use_lib") or child.get("use"):
        raise ValueError("use / use_lib 应通过 module children 例化: %s" % child.get("id"))
    prefix = parent_prefix + "." + child["id"]
    node = copy.deepcopy(child)
    node["id"] = prefix
    node.pop("use", None)
    node.pop("use_lib", None)
    node.pop("port_map", None)
    module_port_names = _mod_port_names(node)
    child_ids = set()
    for ch in node.get("children") or []:
        if isinstance(ch, dict) and ch.get("id"):
            _validate_relative_id(ch["id"], "节点")
            child_ids.add(ch["id"])
    new_children = []
    for ch in node.get("children") or []:
        new_children.append(
            _dispatch_child(ch, modules, libs, prefix, stack, expanded_paths)
        )
    node["children"] = new_children
    if node.get("edges"):
        port_map = {}
        node["edges"] = [
            _rewrite_edge(e, prefix, module_port_names, child_ids, port_map)
            for e in node["edges"]
        ]
    return node


def _elaborate_node(node: dict, modules: dict, libs: dict, stack: set[str]) -> dict:
    if node.get("use") or node.get("use_lib"):
        raise ValueError("use / use_lib 只能出现在 children 里")
    if not tree_needs_elaboration(node):
        return copy.deepcopy(node)
    prefix = node.get("id")
    if not prefix:
        raise ValueError("节点缺少 id")
    out = copy.deepcopy(node)
    new_children = []
    for ch in out.get("children") or []:
        if not isinstance(ch, dict):
            raise ValueError("子节点必须是对象")
        _validate_relative_id(ch.get("id"), "子节点")
        if ch.get("use_lib") or ch.get("use") or tree_needs_elaboration(ch):
            new_children.append(_dispatch_child(ch, modules, libs, prefix, stack, None))
        else:
            _reject_inline_gate(ch)
            new_children.append(copy.deepcopy(ch))
    out["children"] = new_children
    return out


def _expand_module_as_top(name: str, mod: dict, modules: dict, libs: dict) -> dict:
    node = _expand_module_def(name, mod, "top", modules, libs, set(), {}, None)
    node["id"] = "top"
    node["title"] = mod.get("title") or name
    return node


def resolve_view_module(merged: dict, top_cli: str | None) -> str:
    modules = merged.get("modules") or {}
    root_spec = merged.get("root")
    if isinstance(root_spec, str):
        name = top_cli or root_spec
        if name not in modules:
            known = ", ".join(sorted(modules)) if modules else "（无）"
            raise ValueError("未知 top %s，已知: %s" % (name, known))
        return name
    if top_cli:
        if top_cli not in modules:
            known = ", ".join(sorted(modules)) if modules else "（无）"
            raise ValueError("未知 top %s，已知: %s" % (top_cli, known))
        return top_cli
    raise ValueError("层次视图需要 -top 或 root 为 module 名")


def elaborate_view(
    merged: dict,
    view_module: str,
    expanded_paths: set[str] | None = None,
) -> dict:
    modules = merged.get("modules") or {}
    if view_module not in modules:
        known = ", ".join(sorted(modules)) if modules else "（无）"
        raise ValueError("未知 module %s，已知: %s" % (view_module, known))
    paths = set(expanded_paths or [])
    libs = merged.get("libs") or {}
    mod = modules[view_module]
    root = _expand_module_def(view_module, mod, "top", modules, libs, set(), {}, paths)
    root["id"] = "top"
    root["title"] = mod.get("title") or view_module
    doc = {
        "palette": merged.get("palette") or {},
        "swatches": merged.get("swatches") or [],
        "libs": copy.deepcopy(libs),
        "root": root,
    }
    doc = normalize_document(doc)
    index_nodes(doc["root"])
    return doc


def load_view_context(
    json_paths: list[str] | None = None,
    filelists: list[str] | None = None,
    top: str | None = None,
) -> dict:
    paths = collect_source_paths(json_paths or [], filelists)
    if len(paths) == 1 and not filelists and top is None:
        data = _load_json(paths[0])
        if not data.get("modules") and isinstance(data.get("root"), dict):
            if not tree_needs_elaboration(data["root"]) and not data.get("libs"):
                return {"mode": "flat", "document": normalize_document(data)}
    merged = merge_sources(paths)
    if not needs_elaboration(merged):
        if isinstance(merged.get("root"), dict):
            doc = {
                "palette": merged.get("palette") or {},
                "swatches": merged.get("swatches") or [],
                "root": copy.deepcopy(merged["root"]),
            }
            return {"mode": "flat", "document": normalize_document(doc)}
        raise ValueError("需要 -top")
    view_module = resolve_view_module(merged, top)
    return {
        "mode": "hierarchical",
        "merged": merged,
        "top_cli": top,
        "view_module": view_module,
    }


def elaborate_merged(merged: dict, top_cli: str | None) -> dict:
    modules = merged.get("modules") or {}
    root_spec = merged.get("root")
    libs = merged.get("libs") or {}
    if isinstance(root_spec, dict):
        if top_cli:
            pass
        if tree_needs_elaboration(root_spec):
            root = _elaborate_node(root_spec, modules, libs, set())
        else:
            root = copy.deepcopy(root_spec)
    elif isinstance(root_spec, str):
        top_name = top_cli or root_spec
        if top_name not in modules:
            known = ", ".join(sorted(modules)) if modules else "（无）"
            raise ValueError("未知 top %s，已知: %s" % (top_name, known))
        root = _expand_module_as_top(top_name, modules[top_name], modules, libs)
    else:
        top_name = top_cli
        if not top_name:
            raise ValueError("需要 -top")
        if top_name not in modules:
            known = ", ".join(sorted(modules)) if modules else "（无）"
            raise ValueError("未知 top %s，已知: %s" % (top_name, known))
        root = _expand_module_as_top(top_name, modules[top_name], modules, libs)

    doc = {
        "palette": merged.get("palette") or {},
        "swatches": merged.get("swatches") or [],
        "libs": copy.deepcopy(libs),
        "root": root,
    }
    doc = normalize_document(doc)
    index_nodes(doc["root"])
    return doc


def needs_elaboration(merged: dict) -> bool:
    if merged.get("modules"):
        root_spec = merged.get("root")
        if isinstance(root_spec, str):
            return True
        if isinstance(root_spec, dict) and tree_needs_elaboration(root_spec):
            return True
        if root_spec is None:
            return True
    if isinstance(merged.get("root"), dict) and tree_needs_elaboration(merged["root"]):
        return True
    return False


def load_schematic(
    json_paths: list[str] | None = None,
    filelists: list[str] | None = None,
    top: str | None = None,
) -> dict:
    paths = collect_source_paths(json_paths or [], filelists)
    if len(paths) == 1 and not filelists and top is None:
        data = _load_json(paths[0])
        if not data.get("modules") and isinstance(data.get("root"), dict):
            if not tree_needs_elaboration(data["root"]) and not data.get("libs"):
                return normalize_document(data)
    merged = merge_sources(paths)
    if not needs_elaboration(merged):
        if isinstance(merged.get("root"), dict):
            doc = {
                "palette": merged.get("palette") or {},
                "swatches": merged.get("swatches") or [],
                "root": copy.deepcopy(merged["root"]),
            }
            return normalize_document(doc)
        raise ValueError("需要 -top")
    return elaborate_merged(merged, top)


def write_document(path: str, document: dict) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
