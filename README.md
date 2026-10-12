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

The server loads one JSON file. It does not parse a netlist language and it does not keep a session cache.

### Features

| Feature | Description |
|---------|-------------|
| **Hierarchy** | Check nodes to include. Ancestors of a checked node stay visible so the path remains in the layout. |
| **Boxes only** | Hide `mux`, `reg`, and `logic`. `box` nodes remain. |
| **Port filter** | Include / exclude globs (`*`). Include wins over exclude. Ports that match neither rule stay visible. Ports with `"keep": true` stay visible. Ports on `mux`, `reg`, and `logic` are not filtered. |
| **Palette** | Colors come from the document `palette`. Overrides apply to the tree and the SVG and are stored in `localStorage`. |
| **Export** | **Download SVG** saves the current preview, including palette overrides. |

### Page layout

- **Top bar:** boxes-only toggle and the open file name.
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
| **Click a port** | Highlight the connected component. The status line shows the edge count. |
| **Click an edge** | Highlight the related path closure. |
| **Double-click a port** | Center an upstream driver. Multiple drivers cycle `(1/N)`. |
| **Esc** | Clear the highlight. |
| **+ / − / 0** | Zoom in, zoom out, or fit (when focus is not in an input). |
| **F** | Toggle preview fullscreen. |
| **Fit / 1:1** | Fit the window, or reset the scale to 100%. |

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
| `--boxes-only` | Omit `mux`, `reg`, and `logic`. |
| `--palette` | Override `key=#hex`. Repeatable. |

**view** — serve the viewer for one JSON file. See [Web UI](#web-ui).

## Document

The file is one object: optional `palette`, optional `swatches`, and required `root`. The field reference is [docs/schema.en.md](docs/schema.en.md).

| `shape` | Drawing |
|---------|---------|
| `box` | Rectangle. With children, a compound frame; ports are pentagons on the border. |
| `mux` | Trapezoid. `badge` is an optional short label (`CLK`, `DATA`, `1H`). The title sits outside the shape. |
| `reg` | Rectangle with a clock notch. West ports use a fixed order. |
| `logic` | Rounded rectangle. `expr` is wrapped inside the shape. |

An edge is stored on the common parent. `from` and `to` are `nodeId.portName`. `invert` draws a bubble before the arrow.

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
| `docs/images/` | README figure |

## Notes

Swatch keys are arbitrary strings. `palette` maps each key to a `#hex` color. When a key is missing, the renderer uses the default fill for that `shape`.

If an edge omits `swatch`, and the endpoint ports use keys prefixed `clock:`, `reset:`, or `port:`, the edge takes one of those, in that order.
