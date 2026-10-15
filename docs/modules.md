# 库、模块与例化（草案）

[English](modules.en.md)

本文约定 **lib / cell**（绘图最小单元）与 **module / instance**（结构复用）两套概念，以及多文件合并与 filelist。读入阶段 **elaboration** 之后，产物仍是 [schema.md](schema.md) 里的单棵 `root` 树；布局与 SVG 管线不变，但节点会携带 **`meta`** 区分来源（cell / instance）。

> **状态**：`module` + `use`、`libs` + `use_lib`、内置 `schematic/lib/gates.json` 与 `black_box` module 均已实现；见文末检查清单。

## 术语

| 术语 | 含义 | JSON 中的位置 |
|------|------|----------------|
| **lib** | 可例化的**符号单元**定义：`symbol`（SVG + anchors）、`ports`、说明字段 | 内置 lib 文件 + 可选用户 `libs` |
| **cell** | 对某个 lib 的一次**例化**，图上不可再展开成「用户 module 内部网表」 | 父节点 `children` 里 `use_lib`；展开后 `meta.kind = "cell"` |
| **module** | 用户/设计侧的**层次块**定义：边界端口 + 可选内部 `children` / `edges`；可为 **black box**（仅端口） | `modules` 的键与定义体 |
| **instance** | 对某个 module 的一次**例化** | 父节点 `children` 里 `use`；展开后 `meta.kind = "instance"` |
| **复合节点** | 直接写 `shape: box`（等）与 `children` / `edges` 的层次块 | 仅用于非门外形；**门必须用 `use_lib`** |

**原则**

- **cell** 是绘图最小组件（AND、OR、mux、ICG 等）；展开后 `shape: cell`，几何与连线吸附来自 lib 的 **`symbol.anchors`**，不应通过复制 module 来「画一个门」。
- **module** 表达结构复用（adder、寄存器堆、datapath）；例化后是 **instance**，可在 viewer 中按路径 **展开一层 / Go in**。
- **lib 与 module 是两种命名空间**：`use_lib` 查 `libs`（及内置 lib），`use` 查 `modules`；**同一节点二者互斥**。

### 两种「黑盒」（勿混用）

| 概念 | 含义 | 如何表达 |
|------|------|----------|
| **定义型 black box module** | module **本身没有**内部网表（IP 占位、加密核、仅知端口） | module 上 `"black_box": true`，仅允许 `ports`（及壳字段），**不得**有 `children` / `edges` |
| **视图型 stub（折叠 instance）** | module **有完整定义**，当前 view 只画实例壳 | elaboration 的 `expanded_paths` / viewer 双击展开；与 `black_box` 无关 |

定义型 black box 展开后仍是带 `meta.use` 的 instance，但**永远没有**可展开的 `children`；视图型 stub 在展开路径上会出现 module 内部子树。

## 目标

- **lib + cell**：内置门与标准符号进 **lib 库**，例化后统一称为 cell。
- **module + instance**：可复用层次与多文件 `-top`，与 lib 分离。
- 同一批源文件：`modules` / `libs` 可在一个 JSON 里，也可拆分；用多个路径或 `-f filelist` 读入。
- CLI `-top` 选择要画（要 view）的**顶层 module**（不是 lib），语义类似 VCS `-top`。

## 文档形态

读入时支持下列输入，合并后选 top 并展开。

| 形态 | 字段 | 说明 |
|------|------|------|
| 经典文档 | `root` 为**对象** | 可含 `use_lib` / `use`；门仅能通过 `use_lib` |
| 已展开文档 | `root` 为**对象**、无 `use`/`use_lib` | `schematic elaborate` 产物，可直接 draw/view |
| 库文档 | `modules` / `libs` 为对象 | 键为名称，值为定义 |
| 顶名 | `root` 为**字符串** | 必须是 `modules` 里的键（top 只能是 module，不能是 lib 名） |

允许 **库 + 顶混在同一文件**。纯库文件可以只有 `modules` / `libs`（和可选 `palette` / `swatches`），没有 `root`；此时必须 `-top`。

## Lib 定义

`libs` 中每一项描述一个可例化符号（与 module 不同，**不是**层次网表容器）。

| 字段 | 必填 | 说明 |
|------|------|------|
| （键名） | 是 | lib 名，如 `and`、`or2`、`mux2`、`icg` |
| `symbol` | **是** | 矢量符号：`viewBox`、`svg`（可用 `__FILL__` / `__STROKE__` 占位符）、`anchors`（端口名 → `tip` + `side`） |
| `desc` | **是** | 一句话说明该 cell 的功能；展开后在 viewer/SVG 悬停时显示 |
| `title` | 否 | 默认显示名；省略时用 lib 名 |
| `swatch` | 否 | 默认配色 |
| `ports` | **是** | 引脚列表，名称须与 `symbol.anchors` 一致；**每个端口必填 `desc`**（悬停显示） |
| `badge` | 否 | 例化时可继承的短标签（如 mux 上的 `CLK`） |

**Lib 内规则**

- 定义体上**不写** `id`（身份由 `libs` 的键决定）。
- **不得**含 `children`、`edges`、`use`、`use_lib`（lib 不是层次 module）。
- lib **不能**例化 module；module 内可以例化 lib（cell）和 module（instance）。

### 内置 lib

工具自带 **[schematic/lib/gates.json](../schematic/lib/gates.json)**（`and2`、`and3`、`or2`、`xor2`、`buf`、`inv`、`icg`、`mux2` 等），在合并用户文件**之前**自动载入。用户可在任意 JSON 中增加 **`libs`** 扩展符号库；与内置 **同名 → 报错**（可选将来 `--redefine-ok`）。

filelist 中可显式加入内置库或用户扩展库：

```
// 可选：用户扩展 lib
lib/custom_cells.json
lib/full_adder.json
tops/adder4.json
```

## Cell 例化

cell 是父节点 `children` 里用 **`use_lib`** 引用 lib 的节点。

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 在本父节点下唯一；展开前缀为「父路径 + `.` + id」 |
| `use_lib` | 是 | lib 名，须在合并后的内置 + 用户 `libs` 中存在 |
| `title`、`swatch`、`note` | 否 | 覆盖 lib 默认显示 |
| `children`、`edges`、`ports` | — | **禁止**（引脚来自 lib 模板） |
| `use` | — | **禁止**与 `use_lib` 同时出现 |

读入报错示例：同时有 `use` 与 `use_lib`；cell 上自带 `ports` / `children` / `edges`。

展开后节点示例（概念）：

```json
{
  "id": "top.fa0.xp",
  "title": "p",
  "shape": "xor",
  "ports": [ "..." ],
  "meta": { "kind": "cell", "lib": "xor2" }
}
```

门电路在源 JSON 中**必须**写 cell 例化，例如：

```json
{ "id": "xp", "use_lib": "xor2", "title": "p", "swatch": "gate" }
```

在 module / `root` 的 `children` 里直接写 `shape: and|or|…` 会在 elaboration 时报错。需要特殊引脚（气泡、时钟色）时，在 **`libs`** 里定义变体（见 `examples/gates.json` 中的 `and3_b_bub_y_bub`、`icg_clk`）。

## Module 定义

`modules` 中每个 module 与 [schema.md](schema.md) 节点字段一致，但有以下区别：

| 字段 | Module 内规则 |
|------|----------------|
| （无 `id`） | module 身份由 `modules` 的键决定 |
| `black_box` | 可选，默认 `false`；为 `true` 时仅允许 `ports` 与壳字段，**禁止** `children` / `edges` |
| `title`、`shape`、`swatch`、`badge`、`note`、`expr` | 与节点相同 |
| `ports` | instance 边界端口 |
| `children` | 内部子节点：**cell**（`use_lib`）或 **instance**（`use`），或复合 `box` 等（非门） |
| `edges` | 写在 module 壳上；black box module **不得**有 edges |

**Module 内节点 `id`**：相对名，**不得**包含 `.`。

**Module 内连线端点**：

- 边界端口：端口名，如 `"from": "a"`。
- 内部：`子id.端口名`，如 `"from": "xp.y"`。

Module 定义体上**不得**出现 `use` / `use_lib`（例化只出现在上层 `children`）。

### Black box module 示例

```json
{
  "modules": {
    "pcie_phy": {
      "black_box": true,
      "title": "PHY",
      "shape": "box",
      "swatch": "family:module",
      "ports": [
        { "name": "refclk", "side": "west", "dir": "in" },
        { "name": "tx", "side": "east", "dir": "out" }
      ]
    }
  }
}
```

## Instance（module 例化）

instance 是父节点 `children` 里用 **`use`** 引用 **module** 的节点（不是 lib）。

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 在本父节点下唯一 |
| `use` | 是 | module 名，须在合并后的 `modules` 中存在 |
| `title`、`swatch`、`note` | 否 | 覆盖 module 壳显示 |
| `port_map` | 否 | 实例外端口名 → module 端口名 |
| `use_lib` | — | **禁止**与 `use` 同时出现 |
| `children`、`edges`、`ports` | — | **禁止** |

### `port_map`

对象：**实例对外端口名 → module 定义里的端口名**。省略时按同名对齐。详见下文单文件示例。

## 嵌套规则（摘要）

```
module (definition)
  └── children[]
        ├── cell      → use_lib  →  libs[*]     → 展开为叶子符号节点
        ├── instance  → use       →  modules[*]  → 展开或 stub 为 instance 子树
        └── box 等    →  非门复合块（shape + children/edges）
```

- top 只能是 **module**（`root: "adder4"` 或经典 `root` 对象）。
- **lib 不得**引用 module；**module 可以**包含 cell + instance。
- **black box module** 被 instance 例化后，viewer「展开一层」无内部网表可显示（仅壳 + 端口）。

## 单文件示例

```json
{
  "palette": {
    "family:module": "#EEF2F6",
    "family:top": "#F4F6F8",
    "gate": "#E7F0FB"
  },
  "modules": {
    "full_adder": {
      "title": "fa",
      "shape": "box",
      "swatch": "family:module",
      "ports": [
        { "name": "a", "side": "west", "dir": "in" },
        { "name": "b", "side": "west", "dir": "in" },
        { "name": "ci", "side": "west", "dir": "in", "label": "ci" },
        { "name": "s", "side": "east", "dir": "out" },
        { "name": "co", "side": "east", "dir": "out", "label": "co" }
      ],
      "edges": [
        { "from": "a", "to": "xp.a" },
        { "from": "b", "to": "xp.b" },
        { "from": "xp.y", "to": "s" }
      ],
      "children": [
        { "id": "xp", "use_lib": "xor2", "title": "p", "swatch": "gate" }
      ]
    },
    "adder4": {
      "title": "adder4",
      "shape": "box",
      "swatch": "family:top",
      "ports": [
        { "name": "a0", "side": "west", "dir": "in" },
        { "name": "s0", "side": "east", "dir": "out" },
        { "name": "ci", "side": "west", "dir": "in" }
      ],
      "edges": [
        { "from": "ci", "to": "fa0.ci" },
        { "from": "a0", "to": "fa0.a" },
        { "from": "fa0.s", "to": "s0" }
      ],
      "children": [
        { "id": "fa0", "use": "full_adder", "title": "fa0" }
      ]
    }
  },
  "root": "adder4"
}
```

（示例 JSON 若含笔误以实现校验为准；`edges` 项应均为 `from` / `to`。）

展开后：`top.fa0` 为 **instance**；`top.fa0.xp` 为 **cell**（来自 lib `xor2`）。

## 多文件与合并

### 读入顺序

1. **内置 lib**（自动）；
2. CLI positional JSON，从左到右；
3. `-f` filelist 行顺序追加。

### 合并规则

| 内容 | 规则 |
|------|------|
| `libs` | 与内置 lib、彼此 **同名 → 报错** |
| `modules` | 同名 module **报错** |
| `palette` / `swatches` | 后读覆盖先读 |
| `root` | 仅一个文件可声明 top，否则报错 |

### Filelist（`.f`）

一行一个路径；空行与 `//` 注释忽略（与 VCS 一致）。相对路径相对于 **filelist 所在目录**。

## CLI

与 today 相同：`draw` / `view` / `elaborate` 支持多路径、`-f`、`-top`。`-top` 只选 **module 名**。

`--include`、`--port-include`、`--palette` 等在 **展开之后** 作用；id 形如 `top.fa0.xp`。

调试：

```bash
schematic elaborate -f design.f -top adder4 -o expanded.json
```

## Elaboration 规则摘要

1. 合并 `libs`（内置 + 用户）与 `modules`，解析 top module。
2. 深度优先展开 `children`：
   - `use_lib` → 拷贝 lib 模板为 **cell** 节点，`meta.kind = "cell"`, `meta.lib = …`；
   - `use` → 展开 module 体或 **stub 壳**，`meta.kind = "instance"`, `meta.use = …`；
   - 非门复合块 → 拷贝并递归展开其 `children` 中的 cell/instance；
   - `black_box: true` 的 module → 仅壳 + ports，无内部展开。
3. 父级 `edges` 端点仍用实例/cell 边界端口名。
4. 调用 `normalize_document` / `index_nodes` 校验。

### Top 与 `root.id`

展开后 classic 文档：`root.id` = **`top`**；`root.title` 来自 top module。外部端口仍为 `top.*`，instance 为 `top.fa0.*`，cell 为 `top.fa0.xp.*` 等。

## 配色命名（建议）

| 旧键（示例中仍常见） | 建议键 | 用于 |
|---------------------|--------|------|
| `family:cell` | `family:module` | instance / module 壳 |
| `gate` | `gate` | cell / 门 lib |

迁移期二者可并存于 `palette`；新文档优先 `family:module`。

## 与 Verilog 的对照

| Verilog / EDA | Schematic 草案 |
|---------------|----------------|
| 标准单元库 / `.lib` 单元 | **lib**（内置 + `libs`） |
| 单元例化 | **cell**（`use_lib`） |
| `module` | `modules` 的一项 |
| `module u0 (...)` | **instance**（`use`） |
| 加密核 / 空 module 仅端口 | **black box module** |
| filelist | `-f design.f` |
| `-top tb` | `-top adder4` |

## 实现检查清单

- [x] 内置 `schematic/lib/gates.json` 自动合并
- [x] 用户 `libs` 扩展与 `use_lib` → cell（`meta.kind` / `meta.lib`）
- [x] `modules` + `use`（instance）、`black_box`、merge、`-f`、`-top`
- [x] viewer：instance 展开 / Go in / Go out
- [x] 示例：`full_adder`、`gates.json` 使用 `use_lib`
- [ ] viewer 文案区分 cell / instance（可选）
- [ ] `family:module` palette 命名迁移（可选）

## 故意不做（后续）

- **参数化** `#(W)`：`params` 预留。
- **generate 循环**：module / lib 循环依赖 → 报错。
- **用 module 模拟门**：不推荐；门应走 lib / cell。
