# Schematic

[简体中文](README.zh-CN.md)

Orthogonal schematic renderer for a neutral circuit JSON document. A hierarchical netlist of modules, ports, and nets is laid out with [ELK](https://www.eclipse.org/elk/) and drawn as SVG. A local web viewer provides pan, zoom, and path highlighting.

The document format is not tied to a hardware language. [ICL Visual](https://github.com/doee-hc/icl_visual) is one exporter: it turns IEEE 1687 ICL into this JSON.

## Contents

- [Preview](#preview)
- [Web UI](#web-ui)
- [CLI](#cli)
- [Document](#document)
- [Setup & run](#setup--run)
- [Project layout](#project-layout)
- [Notes](#notes)

## Preview

The figure below is `examples/top.json`: a compound `box`, a `mux`, and a `reg`, with clock and scan swatches.

<p align="center">
  <img src="docs/images/top.svg" alt="top schematic" width="480" />
</p>

Regenerate the figure:

```bash
schematic draw examples/top.json -o docs/images/top.svg
```

## Web UI

```bash
schematic view examples/top.json
```

Open `http://127.0.0.1:8765` (default bind address and port). Options: `--host`, `--port`, `--verbose`.

Pass a JSON path at startup (`schematic view design.json`), or omit it and use **Open file** in the top bar to pick a local file. The browser POSTs the JSON to the local server, which replaces the in-memory document. It does not parse a netlist language and it does not persist an on-disk session cache.

### Features

| Feature | Description |
|---------|-------------|
| **Hierarchy** | Check nodes to include. Ancestors of a checked node stay visible so the path remains in the layout. |
| **Boxes only** | Hide `mux`, `reg`, `logic`, `and`, `or`, `xor`, `buf`, and `icg`. `box` nodes remain. |
| **Port filter** | Include / exclude globs (`*`). Include wins over exclude. Ports that match neither rule stay visible. Ports with `"keep": true` stay visible. Ports on `mux`, `reg`, `logic`, and gate shapes are not filtered. |
| **Palette** | Colors come from the document `palette`. Overrides apply to the tree and the SVG and are stored in `localStorage`. |
| **Export** | **Download SVG** saves the current preview, including palette overrides. |

### Page layout

- **Top bar:** **Open file**, boxes-only toggle, and the current file name.
- **Toolbar (collapsible):** palette editor; port filter (Include / Exclude lists and Add).
- **Left panel:** **Draw**, status line, hierarchy tree.
- **Right panel:** zoom, fit, 1:1, fullscreen, download, and the canvas.

### Interactions

| Action | Behavior |
|--------|----------|
| **Check a node** | Checking a parent selects the whole subtree. Checking a child checks its ancestors. |
| **Draw** | Requires at least one checked node. Submits the filter, boxes-only flag, palette, and selection. |
| **Wheel** | Zoom toward the cursor. |
| **Drag** | Pan the canvas. A small movement counts as a click. |
| **Pinch** | Two-finger zoom. |
| **Click a port** | Highlight its connected component and dim everything else. That port becomes the hop anchor. The status line shows the edge count. |
| **Click an edge** | Highlight the related path closure and dim everything else. |
| **Double-click a port** / **`[`** | Center the next upstream driver. Multiple drivers cycle `(1/N)`. `[` starts from the hop anchor. |
| **`]`** | Center the next downstream load, cycling the same way. On an output, the next pins are the loads. On an input, the loads are the other sinks of that net. |
| **Right-click a port** | Menu: upstream drivers (N), downstream loads (N). |
| **Backspace** | Return to the port you hopped from. |
| **Shift+0** | Fit the highlighted path in the view. |
| **Esc** | Close the menu, or clear the highlight if the menu is already closed. |
| **+ / − / 0** | Zoom in, zoom out, or fit (when focus is not in an input). |
| **F** | Toggle preview fullscreen. |
| **Fit / 1:1** | Fit the window, or reset the scale to 100%. |

Press `[` or `]` again to cycle drivers or loads of the same net. Click the port you landed on before hopping further along the path.

### HTTP API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/document` | File name, palette, swatches, and hierarchy tree |
| POST | `/api/draw` | JSON: `include`, `port_include`, `port_exclude`, `boxes_only`, `palette` |

## CLI

**draw** — write an SVG file. Draw options do not modify the document.

```bash
schematic draw examples/top.json -o top.svg
schematic draw examples/top.json -o top.svg \
  --include top --include top.reg \
  --port-include 'si' --port-exclude 'sel' \
  --boxes-only \
  --palette 'clock:clk=#E6A23C'
```

| Option | Description |
|--------|-------------|
| `-o`, `--output` | Output SVG path (required). |
| `--include` | Node id to draw. Repeatable. Ancestors are added. Omit to draw every node. |
| `--port-include` | Include glob. Repeatable. |
| `--port-exclude` | Exclude glob. Repeatable. |
| `--boxes-only` | Omit `mux`, `reg`, `logic`, `and`, `or`, `xor`, `buf`, and `icg`. |
| `--palette` | Override `key=#hex`. Repeatable. |

**view** — serve the viewer (optional JSON path; open another file in the UI). See [Web UI](#web-ui).

**Module libraries** — define reusable `modules`, instantiate with `use`, merge sources with multiple JSON paths or `-f filelist`, and pick the top with `-top` (VCS-style). Expand only:

```bash
schematic elaborate -f examples/adder.f -o build/adder-flat.json
schematic draw -f examples/adder.f -o adder.svg
```

See [docs/modules.en.md](docs/modules.en.md).

## Document

The file is one object: optional `palette`, optional `swatches`, and required `root`. The field reference is [docs/schema.en.md](docs/schema.en.md).

| `shape` | Drawing |
|---------|---------|
| `box` | Rectangle. With children, a compound frame; ports are pentagons on the border. |
| `mux` | Trapezoid. `badge` is an optional short label (`CLK`, `DATA`, `1H`). The title sits outside the shape. |
| `reg` | Rectangle with a clock notch. West ports use a fixed order. |
| `logic` | Rounded rectangle. `expr` is wrapped inside the shape. |
| `and` | D shape. At least two west inputs and one east output. West ports are top to bottom as written. |
| `or` | Shield. Same pin rule as `and`. |
| `xor` | Shield plus a second input arc. Same pin rule as `and`. |
| `buf` | Triangle pointing right. One west input and one east output. An output `bubble` draws an inverter. |
| `icg` | Rectangle. `en` is west, `clk` is south, optional `te` is west, and there is one east output. |

An edge is stored on the common parent. `from` and `to` are `nodeId.portName`. `invert` draws a bubble before the arrow. A port `bubble` draws a bubble on that pin instead. See [examples/gates.json](examples/gates.json).

## Setup & run

**Requirements**

- Python 3.7+ (3.9+ recommended)
- [Node.js](https://nodejs.org/) for the vendored ELK layout

```bash
pip install -e .
python -m pytest tests/ -q
```

`icl_visual` vendors this repository as a submodule. From a full clone of that project, `pip install -r requirements.txt` installs this package in editable mode.

## Project layout

| Path | Description |
|------|-------------|
| `schematic/graph.py` | Document and draw options → ELK graph |
| `schematic/svg.py` | Laid-out graph → SVG |
| `schematic/engine.py` + `schematic/vendor/elkjs/` | ELK layout through Node.js |
| `schematic/server.py` + `schematic/static/` | Viewer |
| `schematic/cli.py` | `schematic draw` and `schematic view` |
| `docs/schema.en.md` | Document reference |
| `examples/top.json` | Preview netlist |
| `examples/adder.json` | 4-bit ripple-carry adder |
| `examples/multiplier.json` | Unsigned 4×4 array multiplier |
| `examples/shifter.json` | 4-bit logical barrel shifter |
| `examples/comparator.json` | Unsigned 4-bit comparator |
| `examples/accumulator.json` | Clock-gated 4-bit accumulator |
| `docs/images/` | README figure |

## Notes

Swatch keys are arbitrary strings. `palette` maps each key to a `#hex` color. When a key is missing, the renderer uses the default fill for that `shape`.

If an edge omits `swatch`, and the endpoint ports use keys prefixed `clock:`, `reset:`, or `port:`, the edge takes one of those, in that order.
