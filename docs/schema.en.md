# Schematic JSON

[简体中文](schema.md)

The file is one JSON object. `root` is required. `palette` and `swatches` are optional. Hierarchy selection, port filters, boxes-only, and palette overrides are draw options. They are not stored in the document. Pass them to `schematic draw` or the viewer.

```json
{
  "palette": { "port:scan": "#3D7ECC" },
  "swatches": [{ "key": "port:scan", "label": "Scan", "group": "Ports" }],
  "root": {
    "id": "top",
    "title": "top",
    "shape": "box",
    "swatch": "family:top",
    "ports": [
      { "name": "si", "side": "west", "dir": "in", "label": "si", "swatch": "port:scan" }
    ],
    "edges": [
      { "from": "top.si", "to": "top.u.a", "swatch": "port:scan" }
    ],
    "children": []
  }
}
```

## Nodes

| Field | Description |
|-------|-------------|
| `id` | Unique in the document. Dots separate hierarchy levels, for example `top.u.mux`. |
| `title` | Label drawn on the node. Defaults to the last segment of `id`. |
| `shape` | One of `box`, `mux`, `reg`, `logic`. |
| `swatch` | Palette key. The renderer looks the key up in `palette`. |
| `badge` | Short label inside a `mux`, such as `CLK`, `DATA`, or `1H`. |
| `note` | Tooltip text. |
| `expr` | Expression drawn inside a `logic` node. Long text wraps. |
| `ports` | Port array. |
| `edges` | Edges whose common parent is this node. |
| `children` | Child nodes. |

A `box` is a rectangle. With children it is a compound frame, and its ports are pentagons on the border. A `mux` is a trapezoid with the title outside the shape. A `reg` has a clock notch; west ports use a fixed order. A `logic` node is a rounded rectangle.

## Ports

| Field | Description |
|-------|-------------|
| `name` | Unique on the node. |
| `side` | `west`, `east`, `south`, or `north`. Layout uses this field. |
| `dir` | `in` or `out`. Descriptive only; it does not set the side. |
| `label` | Display text. Defaults to `name`. |
| `swatch` | Optional palette key. |
| `keep` | When `true`, port filters still draw the port. |

Ports on `mux`, `reg`, and `logic` nodes are not subject to include / exclude filters.

## Edges

Store an edge on the common parent of its endpoints.

| Field | Description |
|-------|-------------|
| `from` / `to` | `nodeId.portName`. Node ids may contain `.`. The longest known node id that is a prefix is the node; the remainder is the port name. |
| `invert` | When `true`, a bubble is drawn before the arrow. |
| `swatch` | Optional. If omitted, and the endpoint keys start with `clock:`, `reset:`, or `port:`, one of those is chosen for the stroke, in that order. |

## Palette

`palette` maps a key to a `#hex` color. A missing key uses the default fill of that `shape`.

`swatches` is only the viewer’s legend: `key`, `label`, and `group`. `group` is an arbitrary string. A group named `内部逻辑` is hidden in the viewer when boxes-only is on.
