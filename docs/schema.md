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
| `shape` | `box`、`mux`、`reg`、`logic` 之一。 |
| `swatch` | 配色键。渲染时到 `palette` 中取色。 |
| `badge` | 画在 `mux` 内的短标签，例如 `CLK`、`DATA`、`1H`。 |
| `note` | 悬停提示。 |
| `expr` | `logic` 框内的表达式。超出宽度时折行。 |
| `ports` | 端口数组。 |
| `edges` | 以本节点为公共父节点的连线。 |
| `children` | 子节点数组。 |

`box` 为矩形。存在子节点时它是复合框，端口画成边框上的五边形。`mux` 为梯形，标题在图形外侧。`reg` 底部有时钟缺口，西侧端口按固定顺序排布。`logic` 为圆角矩形。

## 端口

| 字段 | 说明 |
|------|------|
| `name` | 在该节点内唯一。 |
| `side` | `west`、`east`、`south`、`north`。布局使用该字段。 |
| `dir` | `in` 或 `out`。只作说明，不决定边侧。 |
| `label` | 显示文字。省略时与 `name` 相同。 |
| `swatch` | 可选配色键。 |
| `keep` | 为 `true` 时，端口过滤仍保留该端口。 |

`mux`、`reg`、`logic` 的端口不参与 Include / Exclude 过滤。

## 连线

连线写在两端的公共父节点上。

| 字段 | 说明 |
|------|------|
| `from` / `to` | `节点id.端口名`。节点 id 可以包含 `.`。解析时在已知节点 id 中取最长前缀，其余为端口名。 |
| `invert` | 为 `true` 时，在箭头前绘制反相圆。 |
| `swatch` | 可选。省略时，若两端端口键以 `clock:`、`reset:`、`port:` 开头，则按此顺序选择一个作为连线颜色。 |

## 配色

`palette` 的形式为「键 → `#hex`」。键缺失时，`box`、`mux`、`reg`、`logic` 分别使用各自的默认填充色。

`swatches` 只供查看器的配色列表使用，字段为 `key`、`label`、`group`。`group` 为任意字符串。若某一组的名字为 `内部逻辑`，查看器在「只留方框」时不显示该组。
