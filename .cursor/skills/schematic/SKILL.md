---
name: schematic
description: >-
  Draw orthogonal circuit schematics from a neutral JSON netlist and open an
  interactive preview. Use when the user asks for a circuit diagram, schematic,
  hierarchical netlist drawing, orthogonal wiring SVG, or 电路图、原理图、正交布线。
---

# Schematic

要画正交电路图、层次模块连线，或打开可点选的预览时，用这个 skill。不要手写 SVG，也不要改 ELK 参数。

## 文档

写一份 JSON，交给 `schematic draw` 或 `schematic view`。字段的完整说明在 schematic 仓库的 `docs/schema.md`（英文为 `docs/schema.en.md`）。这里只记形状，避免再抄一份长文档。

根对象有可选的 `palette`（配色键到 `#hex`）、可选的 `swatches`（查看器里的名字和分组），以及必填的 `root`。

节点字段：`id`、`title`、`shape`、`swatch`、`badge`、`note`、`expr`、`ports`、`edges`、`children`。

`shape`：

- `box`：矩形模块。有子节点时是复合框。
- `reg`：带时钟缺口的寄存器。
- `logic`：圆角框，表达式放在 `expr`。可选 `kind`：`comb`（默认，组合）或 `seq`（时序，框底画时钟缺口，与 `reg` 类似）。
- `cell`：lib 例化后的符号（展开后带 `symbol`）；门、mux、ICG 等用 **`use_lib`**，不要 inline 写 `shape: and|or|…`。

自定义 lib：在 JSON 的 **`libs`** 里定义 `symbol`（`viewBox` + `svg` + `anchors`）、`ports`（每项含 `desc`）、`desc`。可复制 `schematic/lib/gates.json` 或 `examples/lib/acme_cells.json` 再改。与网表合并：`schematic draw lib.json design.json -o out.svg` 或 `-f filelist`。

端口：`name`、`side`（`west` / `east` / `south` / `north`）、`dir`、`label`、`swatch`，以及可选的 `keep`、`bubble`。在 **`libs` 里**每个 cell 必填 **`desc`**（一句话功能），每个 port 也必填 **`desc`**（悬停显示）。

连线写在公共父节点上：`from` 和 `to` 都是 `节点id.端口名`，可选 `invert` 和 `swatch`。`invert` 是箭头前的小圆，不是引脚气泡。

## 命令

```bash
schematic draw design.json -o out.svg
schematic view design.json
schematic draw -f lib.f -top mytop -o out.svg
schematic elaborate -f lib.f -top mytop -o flat.json
```

门与最小符号：在 `children` 里用 **`use_lib`**（内置见 `schematic/lib/gates.json`，可扩展 `libs`）。层次复用：**`use`** 例化 module。见 `docs/modules.md`；读入时展开为经典 `root` 树。源 JSON 中不要 inline 写 `shape: and|or|…`。

少画端口、收起子模块、只留方框时，用出图选项，不要改文档来模拟过滤：

- `--include 节点id`（可重复；会带上祖先）
- `--port-include` / `--port-exclude`（`*` 通配；Include 优先）
- `--boxes-only`（隐藏 `cell`、`reg`、`logic`，只留 `box`）
- `--palette key=#hex`

`cell` / `reg` / `logic` 的端口不受端口过滤。`keep: true` 的端口始终保留。
