# 电路图 JSON

文档是一个对象，至少有 `root`。`palette` 和 `swatches` 可选。

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
      { "from": "top.si", "to": "top.u.a", "invert": false, "swatch": "port:scan" }
    ],
    "children": []
  }
}
```

## 节点

- `id`：全局唯一。层次用点分隔，例如 `top.u.mux`。
- `title`：框上的标题。省略时用 `id` 的最后一段。
- `shape`：`box`、`mux`、`reg`、`logic` 之一。
- `swatch`：配色键。查看器只拿它去 `palette` 里查色值。
- `badge`：画在 `mux` 里的短标签，例如 `CLK`、`DATA`、`1H`。
- `note`：悬停提示。
- `expr`：`logic` 框里的表达式，过长会自动折行。
- `ports`、`edges`、`children`。

`box` 是矩形。有子节点时它是复合框，端口画成边上的五边形。`mux` 是梯形，标题在框外。`reg` 底部有时钟缺口，左侧端口按固定顺序排布。`logic` 是圆角矩形。

## 端口

- `name`：在该节点内唯一。
- `side`：`west`、`east`、`south`、`north`。
- `dir`：`in` 或 `out`，只作说明，布局看 `side`。
- `label`：显示文字，默认同 `name`。
- `swatch`：可选配色键。
- `keep`：为 true 时，端口过滤也留着它。

`mux`、`reg`、`logic` 的端口默认全部画出，不吃 Include / Exclude。

## 连线

写在**拥有这条连接的节点**上，通常是两端的公共父节点。

- `from` / `to`：`节点id.端口名`。节点 id 可以含点，按已知节点 id 的最长前缀拆开。
- `invert`：true 时在箭头前画反相小圆。
- `swatch`：可选。省略时，若两端端口的配色键以 `clock:`、`reset:`、`port:` 开头，按这个顺序挑一个给连线上色。

## 配色

`palette` 是「键 → #hex」。没有键时，`box` / `mux` / `reg` / `logic` 使用各自的默认填充。

`swatches` 只给查看器的配色列表用：`key`、`label`、`group`。组名是自由字符串。导出器若把某一组标成「内部逻辑」，查看器在「只留方框」时会藏起这一组。
