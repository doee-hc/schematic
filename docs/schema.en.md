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
| `shape` | One of `box`, `mux`, `reg`, `logic`, `and`, `or`, `xor`, `buf`, `icg`. |
| `swatch` | Palette key. The renderer looks the key up in `palette`. |
| `badge` | Short label inside a `mux`, such as `CLK`, `DATA`, or `1H`. |
| `note` | Tooltip text. |
| `expr` | Expression drawn inside a `logic` node. Long text wraps. |
| `kind` | Only for `shape: logic`: `comb` (combinational, **default**) or `seq` (sequential). `seq` draws the same clock notch as `reg` at the bottom of the rounded box. |
| `ports` | Port array. |
| `edges` | Edges whose common parent is this node. |
| `children` | Child nodes. |

A `box` is a rectangle. With children it is a compound frame, and its ports are pentagons on the border. A `mux` is a trapezoid with the title outside the shape. A `reg` has a clock notch; west ports use a fixed order. A `logic` node is a rounded rectangle; with `kind: seq` it also gets a clock notch to mean clocked/update behavior rather than pure combinational logic.

`and`, `or`, `xor`, `buf`, and `icg` are leaves. They cannot have `children`. The title sits above the symbol and does not change its width. Ports are not pentagons; wires meet the outline.

- `and` is a D, `or` is a shield, and `xor` adds a second arc on the input side. Each needs at least two west inputs and exactly one east output. North and south ports are not allowed. West ports are ordered top to bottom as written.
- `buf` is a triangle pointing right, with exactly one west input and one east output. `"bubble": true` on the output draws an inverter.
- `icg` is a rectangle. `en` is west, `clk` is south, optional `te` is west, and exactly one east output uses any other name.

## Ports

| Field | Description |
|-------|-------------|
| `name` | Unique on the node. |
| `side` | `west`, `east`, `south`, or `north`. Layout uses this field. |
| `dir` | `in` or `out`. Descriptive only; it does not set the side. |
| `label` | Display text. Defaults to `name`. |
| `desc` | One-line pin purpose. **Required** on ports in **lib** definitions (hover tooltip). Optional on module / elaborated nodes. |
| `swatch` | Optional palette key. |
| `keep` | When `true`, port filters still draw the port. |
| `bubble` | When `true`, a bubble is drawn on that pin and the wire meets the outside of the bubble. |

Ports on `mux`, `reg`, `logic`, `and`, `or`, `xor`, `buf`, and `icg` nodes are not subject to include / exclude filters.

## Edges

Store an edge on the common parent of its endpoints.

| Field | Description |
|-------|-------------|
| `from` / `to` | `nodeId.portName`. Node ids may contain `.`. The longest known node id that is a prefix is the node; the remainder is the port name. |
| `invert` | When `true`, a bubble is drawn before the arrow. This is separate from a port `bubble`. |
| `swatch` | Optional. If omitted, and the endpoint keys start with `clock:`, `reset:`, or `port:`, one of those is chosen for the stroke, in that order. |

## Palette

`palette` maps a key to a `#hex` color. A missing key uses the default fill of that `shape`. `and`, `or`, `xor`, and `buf` share one fill. `icg` uses a warm clock color.

`swatches` is only the viewer’s legend: `key`, `label`, and `group`. `group` is an arbitrary string. A group named `内部逻辑` is hidden in the viewer when boxes-only is on.

## Module reuse (extension)

A classic document is one elaborated `root` tree. For **lib/cell** (built-in gates and atomic symbols), **module/instance** (hierarchy, black box), multi-file merge, or `-f` filelists, see [modules.en.md](modules.en.md) ([modules.md](modules.md) in Chinese). Load-time elaboration produces a `root` object as in this document, then layout and draw run unchanged.
