# Schematic

[简体中文](README.zh-CN.md)

Language-neutral JSON in, orthogonal circuit diagrams out. A hierarchical netlist of modules, ports, and nets is laid out with [ELK](https://www.eclipse.org/elk/) and rendered as SVG. The same pipeline can emit native [draw.io](https://www.drawio.com/) (`.drawio`) with embedded symbol geometry. A local web viewer adds pan, zoom, hierarchy filtering, and interactive path tracing.

## Quick start

```bash
pip install -e .
schematic draw examples/top.json -o top.svg
schematic view examples/top.json
```

## Preview

From [examples/tessent_occ/](examples/tessent_occ/): a Tessent on-chip clock controller — nested modules, lib `cell` symbols (gates, mux, clock gating), registers, and clock / scan / IJTAG net styling after ELK layout.

<p align="center">
  <img src="docs/images/tessent_occ.svg" alt="Tessent OCC schematic" width="720" />
</p>

Regenerate:

```bash
schematic draw -f examples/tessent_occ/occ.f \
  -top processor_core_rtl2_tessent_occ \
  -o docs/images/tessent_occ.svg
```

## Web viewer

```bash
schematic view examples/top.json
```

Open `http://127.0.0.1:8765` (default). Options: `--host`, `--port`, `--verbose`.

Pass a JSON path at startup, or use **Open file** to load a local document. The browser sends the JSON to the local server; nothing is written to disk as a session cache.

| Feature | Description |
|---------|-------------|
| **Hierarchy** | Check nodes to include; ancestors stay visible so paths remain in the layout. |
| **Boxes only** | Hide `cell`, `reg`, and `logic`; keep `box` frames. |
| **Port filter** | Include / exclude globs (`*`). Include wins. `"keep": true` ports always show. Ports on `cell`, `reg`, and `logic` are not filtered. |
| **Palette** | Document `palette` plus viewer overrides (stored in `localStorage`). |
| **Export** | **Download SVG** for the current preview, including palette overrides. |

Path tracing: click a port or edge to highlight a connected region; `[` / `]` step upstream drivers and downstream loads; double-click a port or use the context menu to jump. See the status line and on-screen hints for shortcuts (zoom, fit, fullscreen, Esc to clear).

### HTTP API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/document` | File name, palette, swatches, hierarchy tree |
| POST | `/api/draw` | Body: `include`, `port_include`, `port_exclude`, `boxes_only`, `palette` |

## CLI

**draw** — write SVG or draw.io (output extension selects format). Draw options do not modify the source JSON.

```bash
schematic draw examples/top.json -o top.svg
schematic draw examples/top.json -o top.drawio
schematic draw examples/top.json -o top.svg \
  --include top --include top.reg \
  --port-include 'si' --port-exclude 'sel' \
  --boxes-only \
  --palette 'clock:clk=#E6A23C'
```

| Option | Description |
|--------|-------------|
| `-o`, `--output` | Output path (`.svg` or `.drawio`). |
| `--include` | Node id to draw (repeatable). Ancestors are added. |
| `--port-include` / `--port-exclude` | Port globs (repeatable). |
| `--boxes-only` | Omit `cell`, `reg`, and `logic`. |
| `--palette` | Override `key=#hex` (repeatable). |
| `--drawio-via-svg` | draw.io via SVG conversion; default is native mxGraph export. |

**view** — start the web viewer (optional JSON path).

**elaborate** — merge libraries and expand `use` / `use_lib` into a flat `root` tree (no layout):

```bash
schematic elaborate -f examples/adder.f -o build/adder-flat.json
schematic draw -f examples/adder.f -o adder.svg
```

Module libraries and file lists: [docs/modules.en.md](docs/modules.en.md).

## Document format

One JSON object: optional `palette`, optional `swatches`, required `root`. Full reference: [docs/schema.en.md](docs/schema.en.md).

| `shape` | Role |
|---------|------|
| `box` | Rectangular module; with `children`, a compound frame. Border ports use pentagons. |
| `reg` | Register with a clock notch. |
| `logic` | Rounded combinational or sequential block (`kind`: `comb` or `seq`); `expr` wraps inside. |
| `cell` | Lib symbol: vector `symbol` (`viewBox`, `svg`, `anchors`) and ports. Gates, mux, ICG, and custom cells use **`use_lib`** in source JSON, not inline gate shapes. |

Built-in cells live in [schematic/lib/gates.json](schematic/lib/gates.json). Define your own in a document `libs` block (see [examples/lib/acme_cells.json](examples/lib/acme_cells.json)).

Edges sit on the common parent: `from` / `to` are `nodeId.portName`. Edge `invert` is a bubble before the arrow; port `bubble` inverts at the pin.

## Setup

- Python 3.7+ (3.9+ recommended)
- [Node.js](https://nodejs.org/) for the bundled ELK layout engine

```bash
pip install -e .
python -m pytest tests/ -q
```

Optional draw.io conversion helper (Python 3.11+): `pip install -e ".[drawio]"`.

## Repository layout

| Path | Description |
|------|-------------|
| `schematic/` | Layout, SVG and draw.io renderers, CLI, viewer |
| `schematic/lib/gates.json` | Default symbol library |
| `docs/schema.en.md` | JSON field reference |
| `docs/modules.en.md` | Hierarchical modules and file lists |
| `examples/` | Sample designs (datapath, adder, Tessent OCC, …) |

## Notes

`palette` maps arbitrary string keys to `#hex`. Missing keys fall back to per-shape defaults.

If an edge omits `swatch`, and endpoint ports use keys prefixed `clock:`, `reset:`, or `port:`, the edge picks one of those colors in that order.
