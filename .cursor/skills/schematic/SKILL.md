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

`shape` 只有四个：

- `box`：矩形模块。有子节点时是复合框。
- `mux`：梯形。短标签放在 `badge`（如 `CLK`、`DATA`、`1H`）。
- `reg`：带时钟缺口的寄存器。
- `logic`：圆角框，表达式放在 `expr`。

端口：`name`、`side`（`west` / `east` / `south` / `north`）、`dir`、`label`、`swatch`，以及可选的 `keep`。

连线写在公共父节点上：`from` 和 `to` 都是 `节点id.端口名`，可选 `invert` 和 `swatch`。

## 命令

```bash
schematic draw design.json -o out.svg
schematic view design.json
```

少画端口、收起子模块、只留方框时，用出图选项，不要改文档来模拟过滤：

- `--include 节点id`（可重复；会带上祖先）
- `--port-include` / `--port-exclude`（`*` 通配；Include 优先）
- `--boxes-only`（隐藏 `mux`、`reg`、`logic`）
- `--palette key=#hex`

`mux` / `reg` / `logic` 的端口不受端口过滤。`keep: true` 的端口始终保留。
