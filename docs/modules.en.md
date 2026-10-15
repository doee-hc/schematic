# Libraries, modules, and elaboration (draft)

[中文](modules.md)

This document separates **lib / cell** (atomic schematic symbols) from **module / instance** (structural reuse), plus multi-file merge and filelists. After **elaboration**, the result is still a single `root` tree as in [schema.en.md](schema.en.md); layout and SVG stay the same, with optional **`meta`** on nodes (cell / instance / inline).

> **Status**: **`modules` + `use`**, **`libs` + `use_lib`**, bundled **`schematic/lib/gates.json`**, and **`black_box`** modules are implemented. See checklist at the end.

## Terminology

| Term | Meaning | In JSON |
|------|---------|---------|
| **lib** | Definition of an instantiable **symbol** (fixed `shape`, pin rules) | Built-in lib files + optional user `libs` |
| **cell** | One **instance of a lib**; not a expandable user netlist | `use_lib` in `children`; after elaboration `meta.kind = "cell"` |
| **module** | User **hierarchical block**; may be **black box** (ports only) | Entry in `modules` |
| **instance** | One **instance of a module** | `use` in `children`; `meta.kind = "instance"` |
| **Compound node** | Non-gate `box` (etc.) with `children` / `edges` | Gates must use `use_lib` |

**Rules**

- **Cells** are the smallest drawn components (AND, OR, mux, ICG, …).
- **Modules** are for reuse (adders, datapaths); elaborated as **instances** (viewer expand / Go in).
- **Separate namespaces**: `use_lib` → `libs`; `use` → `modules`; **mutually exclusive** on the same node.

### Two kinds of “black box”

| | Meaning | How |
|---|---------|-----|
| **Black box module (definition)** | No internal netlist | `"black_box": true`, only `ports` (+ shell fields); no `children` / `edges` |
| **View stub (collapsed instance)** | Full module body exists; view shows shell only | `expanded_paths` / viewer; unrelated to `black_box` |

## Goals

- **lib + cell** for gates and standard symbols.
- **module + instance** for hierarchy, filelists, `-top`.
- Load many JSONs or `-f filelist`; `-top` selects a **module** name (not a lib).

## Document shapes

| Shape | Fields | Meaning |
|-------|--------|---------|
| Classic | `root` object | Same as today; may contain inline gates (legacy) |
| Library | `modules` / `libs` | Named definitions |
| Top name | `root` string | Key in `modules` only |

Library-only files omit `root`; then `-top` is required.

## Lib definition

Each entry in `libs` is a symbol template, not a hierarchical module.

| Field | Required | Notes |
|-------|----------|-------|
| Key | yes | Lib name, e.g. `and`, `xor2`, `mux2` |
| `shape` | yes | As in [schema.en.md](schema.en.md) |
| `desc` | **yes** | One-line cell purpose; shown on hover in viewer/SVG |
| `title`, `swatch` | no | Defaults |
| `ports` | depends | Required for user libs; built-in lib supplies templates; **each port needs `desc`** |

**Lib rules (draft)**

- No `id` on the body (name is the key).
- No `children`, `edges`, `use`, `use_lib`.
- Libs do not instantiate modules; modules may contain cells and instances.

### Built-in lib

Tool ships **[schematic/lib/gates.json](../schematic/lib/gates.json)**, loaded **before** user files. Add **`libs`** in your JSON to extend the library; duplicate names → error.

## Cell instantiation

| Field | Required | Notes |
|-------|----------|-------|
| `id` | yes | Unique under parent |
| `use_lib` | yes | Lib name after merge |
| `title`, `swatch`, `note` | no | Overrides |
| `use` | — | **Forbidden** together with `use_lib` |
| `children`, `edges`, `ports` | — | **Forbidden** |

After elaboration (conceptual):

```json
"meta": { "kind": "cell", "lib": "xor2" }
```

Inline `{ "shape": "xor", "ports": [...] }` in source JSON is **rejected** at elaboration; use `{ "use_lib": "xor2" }`. Elaborated flat JSON (output of `schematic elaborate`) may still contain expanded gate nodes for draw/view.

## Module definition

Same as before, plus:

| Field | Notes |
|-------|-------|
| `black_box` | If true: ports (+ shell) only; no `children` / `edges` |
| `children` | May contain cells (`use_lib`), instances (`use`), or inline nodes |
| No `use` / `use_lib` on the module **body** | Instantiations live in parent `children` |

Relative child `id` (no `.`). Shell edges: boundary by name; internal as `child.port`.

## Instance (module instantiation)

| Field | Required | Notes |
|-------|----------|-------|
| `id`, `use` | yes | Module name |
| `port_map` | no | External port → module port |
| `use_lib` | — | Forbidden with `use` |

## Nesting (summary)

```
module definition
  children[]
    cell     → use_lib → libs
    instance → use     → modules
    inline   → legacy shape + ports
```

Top is always a **module**. Black box modules yield instances with no expandable interior.

## Single-file example

See [modules.md](modules.md) for the full JSON ( `full_adder` with `use_lib: xor2`, `adder4` with `use: full_adder` ).

## Multi-file merge

1. Built-in lib (automatic);
2. Positional JSON paths;
3. `-f` filelist lines.

| Content | Rule |
|---------|------|
| `libs` | Duplicate names → error |
| `modules` | Duplicate names → error |
| `palette` / `swatches` | Later wins |
| `root` | Only one top-bearing file |

Filelist: one path per line; `//` comments; paths relative to filelist directory (VCS-style).

## CLI

Unchanged: `draw` / `view` / `elaborate`, `-f`, `-top` (module name only).

```bash
schematic elaborate -f design.f -top adder4 -o expanded.json
```

## Elaboration (summary)

1. Merge libs + modules; resolve top.
2. Expand `use_lib` → cell; `use` → instance (full or view stub); honor `black_box`.
3. Run existing normalization / validation.
4. Classic output: `root.id` = **`top`**.

## Palette naming (recommended)

| Legacy | Preferred | Use |
|--------|-----------|-----|
| `family:cell` | `family:module` | Module / instance shells |
| `gate` | `gate` | Cells / gates |

## Verilog analogy

| Verilog / EDA | Schematic |
|---------------|-----------|
| Standard cell library | **lib** |
| Cell placement | **cell** (`use_lib`) |
| `module` | `modules` entry |
| `foo u0 (...)` | **instance** (`use`) |
| Port-only IP | **black box module** |
| filelist | `-f` |
| `-top` | `-top module_name` |

## Implementation checklist

**Done**

- [x] `modules` + `use`, merge, `-f`, `-top`, `elaborate`
- [x] Viewer: instance expand, Go in / Go out, stubs
- [x] Inline gate shapes

**Planned / optional**

- [ ] Viewer wording for cell vs instance
- [ ] `family:module` palette migration

## Out of scope (later)

- Parameterized `params`.
- Circular dependencies → error.
- Using modules to duplicate built-in gates (use lib / cell instead).
