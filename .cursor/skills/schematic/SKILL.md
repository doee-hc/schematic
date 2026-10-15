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
- `mux`：梯形。短标签放在 `badge`（如 `CLK`、`DATA`、`1H`）。
- `reg`：带时钟缺口的寄存器。
- `logic`：圆角框，表达式放在 `expr`。可选 `kind`：`comb`（默认，组合）或 `seq`（时序，框底画时钟缺口，与 `reg` 类似）。
- `and` / `or` / `xor`：D 形、盾形、盾形再加一条输入弧。至少两个西侧输入，恰好一个东侧输出。西侧书写顺序是从上到下。
- `buf`：朝右的三角。一个西侧输入、一个东侧输出。输出 `"bubble": true` 就是反相器。
- `icg`：方块。`en` 在西侧，`clk` 在南侧，可选 `te` 在西侧，恰好一个东侧输出。

门电路不能有 `children`。端口可加 `"bubble": true`，气泡画在该引脚上。

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
- `--boxes-only`（隐藏 `mux`、`reg`、`logic`、`and`、`or`、`xor`、`buf`、`icg`）
- `--palette key=#hex`

`mux` / `reg` / `logic` / `and` / `or` / `xor` / `buf` / `icg` 的端口不受端口过滤。`keep: true` 的端口始终保留。
