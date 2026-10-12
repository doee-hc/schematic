"""Build an ELK graph from a neutral schematic document."""

import re

CHAR_W = 7.2
ROW_H = 16.0
PAD_X = 14.0
MIN_W = 72.0
MIN_H = 48.0
PORT_H = 14.0
PORT_TIP = 7.0
PORT_TEXT_PAD = 5.0
PORT_CHAR_W = 6.2
PORT_GAP = 6.0
PORT_SURROUND_TOP = 28.0
PORT_SURROUND_BOTTOM = 12.0
COMPOUND_PAD_TOP = 32.0
COMPOUND_PAD_BOTTOM = 20.0
COMPOUND_PAD_MIN_X = 28.0
LOGIC_EXPR_CHARS = 36
LOGIC_LINE_H = 14.0

SHAPES = ("box", "mux", "reg", "logic")
DETAIL_SHAPES = frozenset(("mux", "reg", "logic"))
SIDES = {
    "west": "WEST",
    "east": "EAST",
    "south": "SOUTH",
    "north": "NORTH",
}

LAYOUT_OPTIONS = {
    "elk.algorithm": "layered",
    "elk.direction": "RIGHT",
    "elk.edgeRouting": "ORTHOGONAL",
    "elk.hierarchyHandling": "INCLUDE_CHILDREN",
    "elk.spacing.edgeEdge": "12",
    "elk.spacing.edgeNode": "16",
    "elk.spacing.nodeNode": "28",
    "elk.spacing.portPort": str(int(PORT_GAP)),
    "elk.layered.spacing.nodeNodeBetweenLayers": "50",
    "elk.layered.spacing.edgeNodeBetweenLayers": "16",
    "elk.layered.spacing.edgeEdgeBetweenLayers": "12",
    "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
    "elk.layered.nodePlacement.favorStraightEdges": "true",
    "elk.layered.considerModelOrder.strategy": "NONE",
    "elk.layered.considerModelOrder.portModelOrder": "false",
    "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
    "elk.layered.crossingMinimization.greedySwitchHierarchical.type": "TWO_SIDED",
    "elk.layered.thoroughness": "10",
    "elk.padding": "[left=20, top=16, right=20, bottom=16]",
}

NODE_OPTIONS = {
    "elk.portConstraints": "FIXED_SIDE",
    "elk.portAlignment.west": "JUSTIFIED",
    "elk.portAlignment.east": "JUSTIFIED",
    "elk.portAlignment.south": "CENTER",
    "elk.spacing.portsSurrounding": "[top=%.0f, left=0, bottom=%.0f, right=0]" % (
        PORT_SURROUND_TOP, PORT_SURROUND_BOTTOM,
    ),
}

COMPOUND_OPTIONS = {
    "elk.portConstraints": "FIXED_SIDE",
    "elk.portAlignment.west": "JUSTIFIED",
    "elk.portAlignment.east": "JUSTIFIED",
    "elk.spacing.portsSurrounding": "[top=%.0f, left=0, bottom=%.0f, right=0]" % (
        COMPOUND_PAD_TOP, COMPOUND_PAD_BOTTOM,
    ),
    "elk.padding": "[left=28, top=32, right=28, bottom=20]",
    "elk.spacing.nodeNode": "24",
    "elk.layered.spacing.nodeNodeBetweenLayers": "56",
}

_MAX_PORT_PATTERNS = 64
_MAX_PORT_PATTERN_LEN = 80


def clean_port_patterns(raw):
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    seen = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or len(text) > _MAX_PORT_PATTERN_LEN:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= _MAX_PORT_PATTERNS:
            break
    return out


def _glob_to_re(pattern):
    return re.compile("^" + re.escape(pattern).replace(r"\*", ".*") + "$", re.IGNORECASE)


class PortFilter:
    """Include overrides Exclude. Unmatched ports stay visible."""

    def __init__(self, include=None, exclude=None):
        self.include = list(include or [])
        self.exclude = list(exclude or [])
        self._include = [_glob_to_re(item) for item in self.include]
        self._exclude = [_glob_to_re(item) for item in self.exclude]

    def match(self, name):
        text = name or ""
        if any(item.match(text) for item in self._include):
            return True
        if any(item.match(text) for item in self._exclude):
            return None
        return True


def _safe_id(text):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", text)


def port_id(node_id, port_name):
    return "%s__%s" % (node_id, _safe_id(port_name))


def _text_width(text):
    return max(8.0, len(text or "") * CHAR_W)


def _expr_width(text):
    return max(8.0, len(text) * 5.6)


def wrap_expr(text, max_chars=LOGIC_EXPR_CHARS):
    rest = (text or "").strip()
    if not rest:
        return []
    seps = (" ", ",", "&&", "||", "&", "|", "==", "!=")
    lines = []
    while rest:
        if len(rest) <= max_chars:
            lines.append(rest)
            break
        window = rest[:max_chars]
        cut = -1
        for sep in seps:
            pos = window.rfind(sep)
            if pos >= max_chars // 4:
                cut = max(cut, pos if sep == " " else pos + len(sep))
        if cut < 1:
            extra = rest.find(" ", max_chars)
            comma = rest.find(",", max_chars)
            later = [item for item in (extra, comma) if item != -1]
            cut = (min(later) + (0 if rest[min(later)] == " " else 1)) if later else len(rest)
        lines.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    return lines


def port_box_size(name):
    text_w = max(8.0, len(str(name)) * PORT_CHAR_W)
    return PORT_TIP + PORT_TEXT_PAD * 2 + text_w, PORT_H


def _max_label(ports):
    return max((_text_width(port.get("label") or port.get("name") or "") for port in ports), default=0.0)


def _leaf_size(title, inputs, outputs):
    rows = max(len(inputs), len(outputs), 1)
    inner = _text_width(title)
    if inputs or outputs:
        inner = max(inner, _max_label(inputs) + _max_label(outputs) + 16.0)
    width = max(MIN_W, inner + PAD_X * 2)
    height = max(MIN_H, PORT_SURROUND_TOP + rows * ROW_H + PORT_SURROUND_BOTTOM)
    return width, height


def _shape_size(shape, title, inputs, outputs, south, expr):
    if shape == "reg":
        rows = max(len(inputs), len(outputs), 1)
        width = max(96.0, _text_width(title) + 24.0, _max_label(inputs) + 40.0)
        height = max(80.0, 28.0 + rows * 20.0 + 16.0)
        return width, height
    if shape == "mux":
        rows = max(len(inputs), len(outputs), 1)
        width = max(96.0, _max_label(inputs) + 40.0)
        height = max(68.0, 20.0 + rows * ROW_H + 24.0)
        if south:
            height = max(height, 72.0)
        return width, height
    if shape == "logic":
        lines = wrap_expr(expr)
        width = max(120.0, _text_width(title) + 28.0)
        if lines:
            width = max(width, max(_expr_width(line) for line in lines) + 24.0)
            height = max(56.0, 32.0 + len(lines) * LOGIC_LINE_H + 10.0)
        else:
            height = 48.0
        return width, height
    return _leaf_size(title, inputs, outputs)


def _port_index(side, index, count):
    if side == "WEST":
        return count - 1 - index
    return index


def _port_list(node_id, ports, side, compound=False, numbered=False):
    result = []
    count = len(ports)
    for index, port in enumerate(ports):
        name = port.get("name") or ""
        label = port.get("label") or name
        labels = [{
            "id": port_id(node_id, name) + "_lbl",
            "text": label,
            "width": 0,
            "height": 0,
        }]
        props = {}
        if port.get("swatch"):
            props["swatch"] = port["swatch"]
        options = {"elk.port.side": side}
        if numbered:
            options["elk.port.index"] = str(_port_index(side, index, count))
        if not compound:
            item = {
                "id": port_id(node_id, name),
                "width": 0,
                "height": 0,
                "labels": labels,
                "layoutOptions": options,
            }
            if props:
                item["properties"] = props
            result.append(item)
            continue
        width, height = port_box_size(label)
        if side == "WEST":
            anchor = "(%.1f, %.1f)" % (width, height / 2.0)
            offset = str(-width)
        elif side == "SOUTH":
            anchor = "(%.1f, 0.0)" % (width / 2.0)
            offset = str(-height)
        else:
            anchor = "(0, %.1f)" % (height / 2.0)
            offset = str(-width)
        options["elk.port.anchor"] = anchor
        options["elk.port.borderOffset"] = offset
        rec = {
            "id": port_id(node_id, name),
            "width": width,
            "height": height,
            "labels": labels,
            "layoutOptions": options,
        }
        if props:
            rec["properties"] = props
        result.append(rec)
    return result


def index_nodes(root):
    """Return id -> node and id -> parent id."""
    nodes = {}
    parent_of = {}

    def walk(node, parent_id):
        node_id = node.get("id")
        if not node_id or not isinstance(node_id, str):
            raise ValueError("节点缺少 id")
        if node_id in nodes:
            raise ValueError("重复的节点 id: %s" % node_id)
        shape = node.get("shape") or "box"
        if shape not in SHAPES:
            raise ValueError("未知外形 %s: %s" % (shape, node_id))
        nodes[node_id] = node
        if parent_id:
            parent_of[node_id] = parent_id
        for child in node.get("children") or []:
            if not isinstance(child, dict):
                raise ValueError("子节点必须是对象: %s" % node_id)
            walk(child, node_id)

    if not isinstance(root, dict):
        raise ValueError("root 必须是对象")
    walk(root, None)
    return nodes, parent_of


def _shape_ok(node, boxes_only):
    if not boxes_only:
        return True
    return (node.get("shape") or "box") == "box"


def visible_ids(nodes, parent_of, options):
    options = options or {}
    boxes_only = bool(options.get("boxes_only"))
    include = options.get("include")
    if include is not None and not isinstance(include, (list, tuple, set)):
        raise ValueError("include 必须是节点 id 列表")

    if include is None:
        chosen = {nid for nid, node in nodes.items() if _shape_ok(node, boxes_only)}
    else:
        chosen = set()
        for nid in include:
            node = nodes.get(nid)
            if node is None or not _shape_ok(node, boxes_only):
                continue
            chosen.add(nid)
        extra = set()
        for nid in list(chosen):
            parent = parent_of.get(nid)
            while parent:
                node = nodes.get(parent)
                if node is None or not _shape_ok(node, boxes_only):
                    break
                extra.add(parent)
                parent = parent_of.get(parent)
        chosen |= extra

    final = set()
    for nid in chosen:
        parent = parent_of.get(nid)
        ok = True
        while parent:
            if parent not in chosen:
                ok = False
                break
            parent = parent_of.get(parent)
        if ok:
            final.add(nid)
    return final


def _ports_by_side(node):
    groups = {"WEST": [], "EAST": [], "SOUTH": [], "NORTH": []}
    for port in node.get("ports") or []:
        if not isinstance(port, dict):
            continue
        side = SIDES.get((port.get("side") or "west").lower())
        if side is None:
            raise ValueError("未知端口边侧 %s: %s" % (port.get("side"), node.get("id")))
        if not port.get("name"):
            raise ValueError("端口缺少 name: %s" % node.get("id"))
        groups[side].append(port)
    return groups


def _port_visible(port, shape, pattern):
    if port.get("keep"):
        return True
    if shape in DETAIL_SHAPES:
        return True
    return bool(pattern.match(port.get("name") or ""))


def _split_endpoint(text, node_ids):
    if not text or not isinstance(text, str):
        return None, None
    best = None
    for nid in node_ids:
        prefix = nid + "."
        if text.startswith(prefix) and (best is None or len(nid) > len(best)):
            best = nid
    if best is None:
        return None, None
    port = text[len(best) + 1:]
    if not port or "." in port and any(
        text.startswith(other + ".") and len(other) > len(best) for other in node_ids
    ):
        return None, None
    return best, port


def _visible_port_map(node, pattern):
    shape = node.get("shape") or "box"
    found = {}
    for port in node.get("ports") or []:
        if not isinstance(port, dict) or not port.get("name"):
            continue
        if _port_visible(port, shape, pattern):
            found[port["name"]] = port
    return found


def document_to_elk(document, options=None):
    options = options or {}
    root = document.get("root") if isinstance(document, dict) else None
    if not isinstance(root, dict):
        raise ValueError("文档缺少 root")
    nodes, parent_of = index_nodes(root)
    shown = visible_ids(nodes, parent_of, options)
    if root.get("id") not in shown:
        raise ValueError("没有可出图的节点")
    pattern = PortFilter(
        clean_port_patterns(options.get("port_include")),
        clean_port_patterns(options.get("port_exclude")),
    )
    visible_ports = {}
    for nid in shown:
        visible_ports[nid] = _visible_port_map(nodes[nid], pattern)

    def emit(node):
        node_id = node["id"]
        title = node.get("title") or node_id.split(".")[-1]
        shape = node.get("shape") or "box"
        children = [
            child for child in (node.get("children") or [])
            if child.get("id") in shown
        ]
        compound = bool(children)
        groups = _ports_by_side(node)
        kept = {
            side: [port for port in ports if port["name"] in visible_ports.get(node_id, {})]
            for side, ports in groups.items()
        }
        numbered = shape == "reg" and not compound
        elk_node = {
            "id": node_id,
            "labels": [{
                "id": node_id + "_title",
                "text": title,
                "width": _text_width(title),
                "height": 14,
            }],
            "ports": (
                _port_list(node_id, kept["WEST"], "WEST", compound, numbered)
                + _port_list(node_id, kept["EAST"], "EAST", compound, numbered)
                + _port_list(node_id, kept["SOUTH"], "SOUTH", compound, numbered)
                + _port_list(node_id, kept["NORTH"], "NORTH", compound, numbered)
            ),
        }
        props = {"shape": shape}
        if node.get("swatch"):
            props["swatch"] = node["swatch"]
        if node.get("note"):
            props["note"] = node["note"]
        if node.get("expr"):
            props["expr"] = node["expr"]
        if node.get("badge"):
            props["badge"] = node["badge"]
        elk_node["properties"] = props
        if compound:
            left = max(
                COMPOUND_PAD_MIN_X,
                max((port_box_size(port.get("label") or port.get("name"))[0] for port in kept["WEST"]), default=0.0) + 12.0,
            )
            right = max(
                COMPOUND_PAD_MIN_X,
                max((port_box_size(port.get("label") or port.get("name"))[0] for port in kept["EAST"]), default=0.0) + 12.0,
            )
            opts = dict(COMPOUND_OPTIONS)
            opts["elk.padding"] = "[left=%.0f, top=%.0f, right=%.0f, bottom=%.0f]" % (
                left, COMPOUND_PAD_TOP, right, COMPOUND_PAD_BOTTOM,
            )
            elk_node["layoutOptions"] = opts
            elk_node["children"] = [emit(child) for child in children]
        else:
            width, height = _shape_size(
                shape, title, kept["WEST"], kept["EAST"], kept["SOUTH"], node.get("expr") or "",
            )
            elk_node["width"] = width
            elk_node["height"] = height
            opts = dict(NODE_OPTIONS)
            if shape == "mux":
                opts["elk.spacing.portsSurrounding"] = "[top=18, left=0, bottom=20, right=0]"
                opts["elk.nodeLabels.placement"] = "[H_CENTER, V_TOP, OUTSIDE]"
                opts["elk.nodeSize.constraints"] = "[]"
            if shape == "reg":
                opts["elk.portConstraints"] = "FIXED_ORDER"
                opts["elk.portAlignment.west"] = "JUSTIFIED"
                opts["elk.spacing.portPort"] = "18"
                opts["elk.spacing.portsSurrounding"] = "[top=28, left=0, bottom=16, right=0]"
            elk_node["layoutOptions"] = opts
        return elk_node

    edges = []
    seen_ports = set()

    def collect_port_ids(elk_node):
        for port in elk_node.get("ports") or []:
            seen_ports.add(port["id"])
        for child in elk_node.get("children") or []:
            collect_port_ids(child)

    child = emit(root)
    collect_port_ids(child)

    def add_edge(edge):
        src_node, src_port = _split_endpoint(edge.get("from"), shown)
        dst_node, dst_port = _split_endpoint(edge.get("to"), shown)
        if not src_node or not dst_node or not src_port or not dst_port:
            return
        if src_port not in visible_ports.get(src_node, {}):
            return
        if dst_port not in visible_ports.get(dst_node, {}):
            return
        src_id = port_id(src_node, src_port)
        dst_id = port_id(dst_node, dst_port)
        if src_id not in seen_ports or dst_id not in seen_ports:
            return
        item = {
            "id": "e%d" % (len(edges) + 1),
            "sources": [src_id],
            "targets": [dst_id],
        }
        props = {}
        if edge.get("swatch"):
            props["swatch"] = edge["swatch"]
        if edge.get("invert"):
            props["invert"] = "true"
        if props:
            item["properties"] = props
        edges.append(item)

    for nid in shown:
        for edge in nodes[nid].get("edges") or []:
            if isinstance(edge, dict):
                add_edge(edge)

    return {
        "id": "root",
        "layoutOptions": dict(LAYOUT_OPTIONS),
        "children": [child],
        "edges": edges,
    }


def tree_of(node):
    node_id = node.get("id") or ""
    children = [tree_of(child) for child in node.get("children") or [] if isinstance(child, dict)]
    return {
        "name": node_id.split(".")[-1] or node.get("title") or node_id,
        "full_name": node_id,
        "shape": node.get("shape") or "box",
        "swatch": node.get("swatch") or "",
        "children": children,
    }
