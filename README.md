# Schematic

把中立电路图 JSON 画成正交布线 SVG，并提供本地交互查看器。电路从哪来无所谓：可以是手写的 JSON，也可以是别的工具导出的结果。

## 命令

需要 Python 3.7+ 和 [Node.js](https://nodejs.org/)。

```bash
pip install -e .
schematic draw design.json -o design.svg
schematic view design.json          # http://127.0.0.1:8765
```

`draw` 的出图选项不改文档本身：

- `--include 节点id` 可重复。省略则画出全部节点；写了则保留这些节点及其祖先。
- `--port-include` / `--port-exclude` 端口通配（`*`）。Include 优先于 Exclude，未命中的端口保留。带 `"keep": true` 的端口始终保留。`mux` / `reg` / `logic` 的端口不受过滤。
- `--boxes-only` 隐藏 `mux`、`reg`、`logic`，只留 `box`。
- `--palette key=#hex` 可重复，覆盖文档里的配色。

查看器里可以勾选层次、改配色、过滤端口、缩放平移、点选通路、下载 SVG。字段说明见 [docs/schema.md](docs/schema.md)。

## 测试

```bash
python -m pytest tests/ -q
```
