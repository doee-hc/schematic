# 电路图 JSON

[English](schema.en.md)

文档是一个 JSON 对象。`root` 必填。`palette` 与 `swatches` 可选。出图时的层次勾选、端口过滤、只留方框和配色覆盖不属于文档，由 `schematic draw` 或查看器传入。

```json
{
  "palette": { "port:scan": "#3D7ECC" },
  "swatches": [{ "key": "port:scan", "label": "Scan", "group": "端口" }],
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

## 节点

| 字段 | 说明 |
|------|------|
| `id` | 文档内唯一。层次用 `.` 分隔，例如 `top.u.mux`。 |
| `title` | 框上的标题。省略时使用 `id` 的最后一段。 |
| `shape` | `box`、`reg`、`logic`、`cell` 之一。门与 mux 等标准符号须通过 `use_lib` 例化为 `cell`。 |
| `symbol` | **`shape: cell` 必填**。`viewBox`、`svg`、`anchors`；SVG 与 draw.io 共用同一嵌入矢量。 |
| `swatch` | 配色键。渲染时到 `palette` 中取色。 |
| `badge` | 画在符号内的短标签，例如 `CLK`（多来自 lib 定义）。 |
| `note` | 悬停提示。 |
| `expr` | `logic` 框内的表达式。超出宽度时折行。 |
| `kind` | 仅 `shape: logic`：`comb`（组合，**默认**）或 `seq`（时序）。`seq` 在框底画与 `reg` 相同的时钟缺口，表示行为由时钟沿/update 触发，而非纯组合。 |
| `ports` | 端口数组。 |
| `edges` | 以本节点为公共父节点的连线。 |
| `children` | 子节点数组。 |

`box` 为矩形。存在子节点时它是复合框，端口画成边框上的五边形。`reg` 底部有时钟缺口，西侧端口按固定顺序排布。`logic` 为圆角矩形；`kind: seq` 时同样画时钟缺口，与 `reg` 区分语义（多输入/多输出的表达式块 vs 单寄存器符号）。

`cell` 为 lib 例化后的叶子符号：几何来自 `symbol.svg`，端口吸附来自 `symbol.anchors`，不能有 `children`。内置门、mux、ICG 等均在 [schematic/lib/gates.json](../schematic/lib/gates.json) 中以 `symbol` 定义；源 JSON 里用 `{ "use_lib": "and2" }` 例化，勿再写 `shape: and` 等内联门形。

## 端口

| 字段 | 说明 |
|------|------|
| `name` | 在该节点内唯一。 |
| `side` | `west`、`east`、`south`、`north`。布局使用该字段。 |
| `dir` | `in` 或 `out`。只作说明，不决定边侧。 |
| `label` | 显示文字。省略时与 `name` 相同。 |
| `desc` | 一句话引脚功能；在 **lib** 定义中为必填（悬停提示）。module / 展开后节点上的端口可选。 |
| `swatch` | 可选配色键。 |
| `keep` | 为 `true` 时，端口过滤仍保留该端口。 |
| `bubble` | 为 `true` 时，在该引脚上画气泡，连线接到气泡外侧。 |

`cell`、`reg`、`logic` 的端口不参与 Include / Exclude 过滤。

## 连线

连线写在两端的公共父节点上。

| 字段 | 说明 |
|------|------|
| `from` / `to` | `节点id.端口名`。节点 id 可以包含 `.`。解析时在已知节点 id 中取最长前缀，其余为端口名。 |
| `invert` | 为 `true` 时，在箭头前绘制反相圆。这与端口上的 `bubble` 是两回事。 |
| `swatch` | 可选。省略时，若两端端口键以 `clock:`、`reset:`、`port:` 开头，则按此顺序选择一个作为连线颜色。 |

## 配色

`palette` 的形式为「键 → `#hex`」。键缺失时使用该 `shape` 的默认填充色；`cell` 使用与门级符号相同的默认填充/描边（由 `swatch` 覆盖）。

`swatches` 只供查看器的配色列表使用，字段为 `key`、`label`、`group`。`group` 为任意字符串。若某一组的名字为 `内部逻辑`，查看器在「只留方框」时不显示该组。

## 模块复用（扩展）

经典文档只有一棵展开的 `root` 树。若要用 **lib/cell**（内置门等最小符号）、**module/instance**（层次复用与 black box）、多 JSON 合并或 `-f` filelist，见 [modules.md](modules.md)（英文 [modules.en.md](modules.en.md)）。读入时会展开为本文档描述的 `root` 对象，再交给布局与出图。
