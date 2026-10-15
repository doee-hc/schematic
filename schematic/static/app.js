const FILTER_STORE = "schematic-port-filter";
const PALETTE_STORE = "schematic-palette";
const UI_STORE = "schematic-ui";
const MAX_PORT_PATTERNS = 64;
const MAX_PORT_PATTERN_LEN = 80;

const els = {
  fileMeta: document.getElementById("file-meta"),
  fileOpen: document.getElementById("file-open"),
  portFilterReset: document.getElementById("port-filter-reset"),
  portIncludeList: document.getElementById("port-include-list"),
  portExcludeList: document.getElementById("port-exclude-list"),
  portIncludeCount: document.getElementById("port-include-count"),
  portExcludeCount: document.getElementById("port-exclude-count"),
  portIncludeForm: document.getElementById("port-include-form"),
  portExcludeForm: document.getElementById("port-exclude-form"),
  portIncludeInput: document.getElementById("port-include-input"),
  portExcludeInput: document.getElementById("port-exclude-input"),
  toolbar: document.getElementById("toolbar"),
  toolbarFold: document.getElementById("toolbar-fold"),
  palette: document.getElementById("palette"),
  paletteReset: document.getElementById("palette-reset"),
  tree: document.getElementById("tree"),
  checkedCount: document.getElementById("checked-count"),
  status: document.getElementById("status"),
  drawBtn: document.getElementById("draw-btn"),
  downloadBtn: document.getElementById("download-btn"),
  downloadDrawioBtn: document.getElementById("download-drawio-btn"),
  previewWrap: document.getElementById("preview-wrap"),
  preview: document.getElementById("preview"),
  previewPlaceholder: document.getElementById("preview-placeholder"),
  previewContent: document.getElementById("preview-content"),
  zoomInBtn: document.getElementById("zoom-in-btn"),
  zoomOutBtn: document.getElementById("zoom-out-btn"),
  zoomFitBtn: document.getElementById("zoom-fit-btn"),
  zoomResetBtn: document.getElementById("zoom-reset-btn"),
  zoomLabel: document.getElementById("zoom-label"),
  fullscreenBtn: document.getElementById("fullscreen-btn"),
  portMenu: document.getElementById("port-menu"),
  portMenuDriver: document.getElementById("port-menu-driver"),
  portMenuLoad: document.getElementById("port-menu-load"),
  navActions: document.getElementById("nav-actions"),
  goInBtn: document.getElementById("go-in-btn"),
  goOutBtn: document.getElementById("go-out-btn"),
  navCrumb: document.getElementById("nav-crumb"),
};

const VIEW_MIN = 0.1;
const VIEW_MAX = 16;
const ZOOM_STEP = 1.2;

let lastSvg = "";
let lastSvgName = "graph.svg";
let lastDrawio = "";
let lastDrawioName = "graph.drawio";
let lastDrawioError = "";
let basePalette = {};
let baseSwatches = [];
let view = { scale: 1, x: 0, y: 0 };
let pointers = new Map();
let pinchStart = null;
let panSession = null;
let clickGesture = null;
let edgeGraph = null;
/** @type {{ ports: object[], edges: { el: Element, pts: Float32Array }[] } | null} */
let pickCache = null;
let cursorPickRaf = 0;
let cursorPickXY = { x: 0, y: 0 };
let driverHopCursor = { portId: "", index: 0 };
let loadHopCursor = { portId: "", index: 0 };
let hopStack = [];
let hopAnchorId = "";
let focusedPortId = "";

const CLICK_MOVE_PX = 5;
const DBLCLICK_MS = 500;
const DBLCLICK_PX = 10;
const EDGE_HIT_PX = 12;
const PORT_HIT_PX = 12;
let swatches = [];
let palette = loadPalette();
let portInclude = [];
let portExclude = [];
let hierarchical = false;
let viewModule = "";
/** @type {Set<string>} */
let expandedPaths = new Set();
/** @type {{ viewModule: string, expandedPaths: string[], label: string }[]} */
let navStack = [];
let selectedInstance = { path: "", moduleUse: "" };

function loadPalette() {
  try {
    const raw = JSON.parse(localStorage.getItem(PALETTE_STORE) || "{}");
    return raw && typeof raw === "object" ? raw : {};
  } catch (err) {
    return {};
  }
}

function savePalette() {
  localStorage.setItem(PALETTE_STORE, JSON.stringify(palette));
}

function loadUi() {
  try {
    const raw = JSON.parse(localStorage.getItem(UI_STORE) || "{}");
    return raw && typeof raw === "object" ? raw : {};
  } catch (err) {
    return {};
  }
}

function saveUi(patch) {
  localStorage.setItem(UI_STORE, JSON.stringify({ ...loadUi(), ...patch }));
}

function refitIfNeeded() {
  if (hasSvg()) requestAnimationFrame(fitView);
}

function setToolbarCollapsed(collapsed) {
  els.toolbar.classList.toggle("is-collapsed", collapsed);
  els.toolbarFold.textContent = collapsed ? "展开" : "收起";
  els.toolbarFold.setAttribute("aria-expanded", String(!collapsed));
  saveUi({ toolbarCollapsed: collapsed });
  refitIfNeeded();
}

function normalizePattern(value) {
  return String(value || "").trim();
}

function cleanPatternList(raw) {
  if (!Array.isArray(raw)) return [];
  const out = [];
  const seen = new Set();
  raw.forEach((item) => {
    const text = normalizePattern(item);
    if (!text || text.length > MAX_PORT_PATTERN_LEN) return;
    const key = text.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push(text);
  });
  return out.slice(0, MAX_PORT_PATTERNS);
}

function loadPortFilter() {
  try {
    const raw = JSON.parse(localStorage.getItem(FILTER_STORE) || "null");
    if (!raw || typeof raw !== "object") return;
    if (Array.isArray(raw.include)) portInclude = cleanPatternList(raw.include);
    if (Array.isArray(raw.exclude)) portExclude = cleanPatternList(raw.exclude);
  } catch (err) {
    /* keep defaults */
  }
}

function savePortFilter() {
  localStorage.setItem(FILTER_STORE, JSON.stringify({
    include: portInclude,
    exclude: portExclude,
  }));
}

function renderChipList(container, countEl, items, emptyText, onRemove) {
  container.replaceChildren();
  countEl.textContent = String(items.length);
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "filter-empty";
    empty.textContent = emptyText;
    container.append(empty);
    return;
  }
  items.forEach((item, index) => {
    const chip = document.createElement("div");
    chip.className = "filter-chip";
    const label = document.createElement("span");
    label.textContent = item;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", `移除 ${item}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => onRemove(index));
    chip.append(label, remove);
    container.append(chip);
  });
}

function renderPortFilter() {
  renderChipList(
    els.portIncludeList,
    els.portIncludeCount,
    portInclude,
    "暂无 Include，未命中端口默认保留",
    (index) => {
      portInclude.splice(index, 1);
      savePortFilter();
      renderPortFilter();
    },
  );
  renderChipList(
    els.portExcludeList,
    els.portExcludeCount,
    portExclude,
    "暂无 Exclude",
    (index) => {
      portExclude.splice(index, 1);
      savePortFilter();
      renderPortFilter();
    },
  );
}

function addPattern(kind) {
  const input = kind === "include" ? els.portIncludeInput : els.portExcludeInput;
  const list = kind === "include" ? portInclude : portExclude;
  const text = normalizePattern(input.value);
  if (!text) {
    setStatus("请输入一条 pattern，例如 ijtag*si 或 *clk*", "error");
    input.focus();
    return;
  }
  if (text.length > MAX_PORT_PATTERN_LEN) {
    setStatus(`pattern 最长 ${MAX_PORT_PATTERN_LEN} 个字符`, "error");
    return;
  }
  if (list.length >= MAX_PORT_PATTERNS) {
    setStatus(`每份列表最多 ${MAX_PORT_PATTERNS} 条`, "error");
    return;
  }
  if (list.some((item) => item.toLowerCase() === text.toLowerCase())) {
    setStatus(`已存在 ${text}`, "error");
    input.select();
    return;
  }
  list.push(text);
  input.value = "";
  savePortFilter();
  renderPortFilter();
  setStatus("");
}

loadPortFilter();
renderPortFilter();

function darkenHex(hex, amount) {
  const value = (hex || "").replace("#", "");
  const full = value.length === 3
    ? value.split("").map((ch) => ch + ch).join("")
    : value;
  if (full.length !== 6) return "#222222";
  const rgb = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16));
  return `#${rgb.map((c) => Math.max(0, Math.min(255, Math.round(c * (1 - amount))))
    .toString(16).padStart(2, "0")).join("")}`;
}

function swatchColor(key, fallback) {
  return palette[key] || fallback || "#cccccc";
}

function applyPaletteTo(root) {
  if (!root) return;
  root.querySelectorAll("[data-swatch]").forEach((el) => {
    const key = el.getAttribute("data-swatch");
    if (!key) return;
    const color = palette[key];
    if (!color) return;
    if (el.classList.contains("family-dot")) {
      el.style.background = color;
      return;
    }
    if (el.classList.contains("port-label")) {
      el.setAttribute("fill", darkenHex(color, 0.15));
      return;
    }
    if (el.classList.contains("edge") || el.classList.contains("edge-arrow")) {
      const shapes = el.classList.contains("swatch-stroke")
        ? [el]
        : Array.from(el.querySelectorAll(".swatch-stroke"));
      shapes.forEach((shape) => {
        shape.setAttribute("stroke", color);
        if (shape.tagName.toLowerCase() === "polygon") shape.setAttribute("fill", color);
      });
      return;
    }
    const fillables = el.classList.contains("swatch-fill")
      ? [el]
      : Array.from(el.querySelectorAll(".swatch-fill"));
    fillables.forEach((fillable) => {
      fillable.setAttribute("fill", color);
      fillable.setAttribute("stroke", darkenHex(color, 0.35));
    });
    el.querySelectorAll(".gate-stroke, .gate-bubble").forEach((shape) => {
      shape.setAttribute("stroke", darkenHex(color, 0.35));
    });
  });
}

function applyPalette() {
  applyPaletteTo(els.tree);
  applyPaletteTo(els.previewContent.querySelector("svg"));
}

function visibleSwatches() {
  return swatches;
}

function renderPalette() {
  const items = visibleSwatches();
  if (!items.length) {
    els.palette.classList.add("empty");
    els.palette.textContent = "文档里没有配色键";
    return;
  }
  els.palette.classList.remove("empty");
  els.palette.replaceChildren();
  const groups = [];
  items.forEach((item) => {
    if (!palette[item.key]) palette[item.key] = item.color;
    let group = groups.find((g) => g.name === item.group);
    if (!group) {
      group = { name: item.group, items: [] };
      groups.push(group);
    }
    group.items.push(item);
  });
  groups.forEach((group) => {
    const title = document.createElement("div");
    title.className = "palette-group-title";
    title.textContent = group.name;
    const wrap = document.createElement("div");
    wrap.className = "palette-group";
    wrap.append(title);
    group.items.forEach((item) => {
      const row = document.createElement("label");
      row.className = "palette-row";
      const input = document.createElement("input");
      input.type = "color";
      input.value = swatchColor(item.key, item.color);
      input.dataset.key = item.key;
      const name = document.createElement("span");
      name.textContent = item.label;
      input.addEventListener("input", () => {
        palette[item.key] = input.value;
        savePalette();
        applyPalette();
      });
      row.append(input, name);
      wrap.append(row);
    });
    els.palette.append(wrap);
  });
  savePalette();
}

function setStatus(message, kind) {
  if (!message) {
    els.status.hidden = true;
    els.status.textContent = "";
    els.status.className = "status";
    return;
  }
  els.status.hidden = false;
  els.status.textContent = message;
  els.status.className = `status ${kind || ""}`;
}

function updateCheckedCount() {
  const count = els.tree.querySelectorAll('input[type="checkbox"]:checked').length;
  els.checkedCount.textContent = `${count} selected`;
  if (hierarchical) {
    els.drawBtn.disabled = false;
    return;
  }
  els.drawBtn.disabled = count === 0;
}

function syncNavUi() {
  if (els.navActions) els.navActions.hidden = !hierarchical;
  if (els.goInBtn) {
    els.goInBtn.disabled = !hierarchical || !selectedInstance.moduleUse;
  }
  if (els.goOutBtn) {
    els.goOutBtn.disabled = !hierarchical || navStack.length === 0;
  }
  if (els.navCrumb) {
    const parts = [...navStack.map((frame) => frame.label), viewModule].filter(Boolean);
    els.navCrumb.textContent = parts.join(" › ");
  }
}

function syncInstanceSelectionVisual() {
  const svg = els.previewContent.querySelector("svg");
  if (!svg) return;
  svg.querySelectorAll("g.node.node-selected").forEach((el) => {
    el.classList.remove("node-selected");
  });
  if (!selectedInstance.path) return;
  const node = svg.querySelector(`g.node[data-id="${cssEscape(selectedInstance.path)}"]`);
  if (node) node.classList.add("node-selected");
}

function cssEscape(value) {
  if (typeof CSS !== "undefined" && CSS.escape) return CSS.escape(value);
  return String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function pickInstanceNodeAt(clientX, clientY) {
  const stack = document.elementsFromPoint(clientX, clientY);
  for (let i = 0; i < stack.length; i += 1) {
    const el = stack[i];
    if (el.closest && el.closest("g.edge")) return null;
    if (el.closest && el.closest("g.port")) return null;
  }
  for (let i = 0; i < stack.length; i += 1) {
    const node = stack[i].closest && stack[i].closest("g.node[data-module-use]");
    if (node) return node;
  }
  return null;
}

function toggleInstanceExpand(path) {
  const next = new Set(expandedPaths);
  if (next.has(path)) {
    next.delete(path);
    Array.from(next).forEach((item) => {
      if (item.startsWith(`${path}.`)) next.delete(item);
    });
  } else {
    next.add(path);
  }
  expandedPaths = next;
  runDraw(false);
}

function goIn() {
  if (!hierarchical || !selectedInstance.moduleUse) return;
  navStack.push({
    viewModule,
    expandedPaths: Array.from(expandedPaths),
    label: viewModule,
  });
  viewModule = selectedInstance.moduleUse;
  expandedPaths = new Set();
  selectedInstance = { path: "", moduleUse: "" };
  syncNavUi();
  runDraw(false);
}

function goOut() {
  if (!hierarchical || !navStack.length) return;
  const frame = navStack.pop();
  viewModule = frame.viewModule;
  expandedPaths = new Set(frame.expandedPaths);
  selectedInstance = { path: "", moduleUse: "" };
  syncNavUi();
  runDraw(false);
}

function getCheckedInstances() {
  return Array.from(els.tree.querySelectorAll('input[type="checkbox"]:checked'))
    .map((input) => input.dataset.fullName);
}

function setSubtreeChecked(li, checked) {
  li.querySelectorAll('input[type="checkbox"]').forEach((input) => {
    input.checked = checked;
  });
}

function setAncestorsChecked(li) {
  let parent = li.parentElement && li.parentElement.closest(".tree-node");
  while (parent) {
    const box = parent.querySelector(":scope > .tree-row input[type='checkbox']");
    if (box) box.checked = true;
    parent = parent.parentElement && parent.parentElement.closest(".tree-node");
  }
}

function renderNode(node) {
  const li = document.createElement("div");
  li.className = "tree-node";

  const row = document.createElement("div");
  row.className = "tree-row";

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "toggle";
  toggle.textContent = node.children && node.children.length ? "▾" : "·";
  if (!node.children || !node.children.length) toggle.classList.add("placeholder");

  const box = document.createElement("input");
  box.type = "checkbox";
  box.dataset.fullName = node.full_name;

  const dot = document.createElement("span");
  dot.className = "family-dot";
  if (node.swatch) {
    dot.dataset.swatch = node.swatch;
    dot.title = node.shape ? `${node.shape} · ${node.swatch}` : node.swatch;
  }

  const label = document.createElement("span");
  label.textContent = node.name;

  row.append(toggle, box, dot, label);
  li.append(row);

  const childWrap = document.createElement("div");
  childWrap.className = "children";
  (node.children || []).forEach((child) => childWrap.append(renderNode(child)));
  if (node.children && node.children.length) li.append(childWrap);

  toggle.addEventListener("click", () => {
    if (!node.children || !node.children.length) return;
    const collapsed = childWrap.classList.toggle("collapsed");
    toggle.textContent = collapsed ? "▸" : "▾";
  });

  box.addEventListener("change", () => {
    setSubtreeChecked(li, box.checked);
    if (box.checked) setAncestorsChecked(li);
    updateCheckedCount();
  });

  return li;
}

function renderTree(tree) {
  els.tree.innerHTML = "";
  els.tree.classList.remove("empty");
  els.tree.append(renderNode(tree));
  applyPaletteTo(els.tree);
  updateCheckedCount();
}

function hasSvg() {
  return Boolean(lastSvg && els.previewContent.querySelector("svg"));
}

function clampScale(scale) {
  return Math.min(VIEW_MAX, Math.max(VIEW_MIN, scale));
}

function applyView() {
  els.previewContent.style.transform =
    `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
  els.zoomLabel.textContent = `${Math.round(view.scale * 100)}%`;
}

function syncDrawioDownload() {
  const hasDrawio = Boolean(lastDrawio);
  if (els.downloadDrawioBtn) {
    els.downloadDrawioBtn.disabled = !hasSvg() || !hasDrawio;
    els.downloadDrawioBtn.title = hasDrawio
      ? "下载 draw.io 可编辑图"
      : (lastDrawioError || "需服务端 Python 3.11+ 与 pip install svg-to-drawio");
  }
}

function setViewControls(enabled) {
  els.zoomInBtn.disabled = !enabled;
  els.zoomOutBtn.disabled = !enabled;
  els.zoomFitBtn.disabled = !enabled;
  els.zoomResetBtn.disabled = !enabled;
  els.downloadBtn.disabled = !enabled;
  syncDrawioDownload();
  els.preview.classList.toggle("has-svg", enabled);
  els.preview.classList.toggle("empty", !enabled);
}

function parseLength(value) {
  const n = parseFloat(value);
  return Number.isFinite(n) ? n : 0;
}

function svgSize(svg) {
  try {
    const box = svg.getBBox();
    if (box.width && box.height) return { width: box.width, height: box.height };
  } catch (err) {
    /* SVG not rendered yet */
  }
  const viewBox = svg.viewBox && svg.viewBox.baseVal;
  const width = parseLength(svg.getAttribute("width")) || (viewBox && viewBox.width) || 1;
  const height = parseLength(svg.getAttribute("height")) || (viewBox && viewBox.height) || 1;
  return { width, height };
}

function setView(scale, x, y) {
  view.scale = clampScale(scale);
  view.x = x;
  view.y = y;
  applyView();
}

function zoomAt(clientX, clientY, factor) {
  if (!hasSvg()) return;
  const rect = els.preview.getBoundingClientRect();
  const px = clientX - rect.left;
  const py = clientY - rect.top;
  const next = clampScale(view.scale * factor);
  const ratio = next / view.scale;
  setView(next, px - (px - view.x) * ratio, py - (py - view.y) * ratio);
}

function zoomBy(factor) {
  const rect = els.preview.getBoundingClientRect();
  zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, factor);
}

function elementBoxInRoot(el) {
  const svg = el.ownerSVGElement;
  if (!svg || !el.getBBox) return null;
  let box;
  try {
    box = el.getBBox();
  } catch (err) {
    return null;
  }
  if (!box || (!box.width && !box.height)) return null;
  const ctm = el.getCTM && el.getCTM();
  const corners = [
    [box.x, box.y],
    [box.x + box.width, box.y],
    [box.x, box.y + box.height],
    [box.x + box.width, box.y + box.height],
  ];
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  corners.forEach(([x, y]) => {
    const p = svgPointToRoot(svg, x, y, ctm);
    minX = Math.min(minX, p.x);
    minY = Math.min(minY, p.y);
    maxX = Math.max(maxX, p.x);
    maxY = Math.max(maxY, p.y);
  });
  return { minX, minY, maxX, maxY };
}

function fitHighlighted() {
  const svg = els.previewContent.querySelector("svg");
  if (!svg || !svg.classList.contains("path-dim")) {
    setStatus("请先高亮一条通路", "ok");
    return;
  }
  const bounds = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
  svg.querySelectorAll("g.edge.path-hl, g.port.port-hl, g.port.port-onpath").forEach((el) => {
    const box = elementBoxInRoot(el);
    if (!box) return;
    bounds.minX = Math.min(bounds.minX, box.minX);
    bounds.minY = Math.min(bounds.minY, box.minY);
    bounds.maxX = Math.max(bounds.maxX, box.maxX);
    bounds.maxY = Math.max(bounds.maxY, box.maxY);
  });
  if (!Number.isFinite(bounds.minX)) {
    setStatus("当前高亮没有可适应的范围", "ok");
    return;
  }
  const minSpan = 64;
  if (bounds.maxX - bounds.minX < minSpan) {
    const mid = (bounds.minX + bounds.maxX) / 2;
    bounds.minX = mid - minSpan / 2;
    bounds.maxX = mid + minSpan / 2;
  }
  if (bounds.maxY - bounds.minY < minSpan) {
    const mid = (bounds.minY + bounds.maxY) / 2;
    bounds.minY = mid - minSpan / 2;
    bounds.maxY = mid + minSpan / 2;
  }
  const rect = els.preview.getBoundingClientRect();
  const pad = 48;
  const w = bounds.maxX - bounds.minX;
  const h = bounds.maxY - bounds.minY;
  const scale = clampScale(Math.min(
    Math.max(rect.width - pad, 1) / w,
    Math.max(rect.height - pad, 1) / h,
  ));
  setView(
    scale,
    (rect.width - w * scale) / 2 - bounds.minX * scale,
    (rect.height - h * scale) / 2 - bounds.minY * scale,
  );
}

function fitView() {
  const svg = els.previewContent.querySelector("svg");
  if (!svg) return;
  const rect = els.preview.getBoundingClientRect();
  const size = svgSize(svg);
  if (!size.width || !size.height) return;
  const pad = 32;
  const availableW = Math.max(rect.width - pad, 1);
  const availableH = Math.max(rect.height - pad, 1);
  const scale = clampScale(Math.min(availableW / size.width, availableH / size.height));
  setView(
    scale,
    (rect.width - size.width * scale) / 2,
    (rect.height - size.height * scale) / 2,
  );
}

function resetView() {
  const svg = els.previewContent.querySelector("svg");
  if (!svg) return;
  const rect = els.preview.getBoundingClientRect();
  const size = svgSize(svg);
  setView(1, (rect.width - size.width) / 2, (rect.height - size.height) / 2);
}

function isFullscreen() {
  return document.fullscreenElement === els.previewWrap
    || document.webkitFullscreenElement === els.previewWrap;
}

function updateFullscreenButton() {
  els.fullscreenBtn.textContent = isFullscreen() ? "退出全屏" : "全屏";
}

async function toggleFullscreen() {
  try {
    if (isFullscreen()) {
      if (document.exitFullscreen) await document.exitFullscreen();
      else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
      return;
    }
    if (els.previewWrap.requestFullscreen) await els.previewWrap.requestFullscreen();
    else if (els.previewWrap.webkitRequestFullscreen) els.previewWrap.webkitRequestFullscreen();
  } catch (err) {
    setStatus(err.message || "无法切换全屏", "error");
  }
}

function buildEdgeGraph(svg) {
  const bySrc = new Map();
  const byDst = new Map();
  svg.querySelectorAll("g.edge[data-src][data-dst]").forEach((el) => {
    const src = el.getAttribute("data-src") || "";
    const dst = el.getAttribute("data-dst") || "";
    if (src) {
      if (!bySrc.has(src)) bySrc.set(src, []);
      bySrc.get(src).push(el);
    }
    if (dst) {
      if (!byDst.has(dst)) byDst.set(dst, []);
      byDst.get(dst).push(el);
    }
  });
  return { bySrc, byDst };
}

function closureEdgesFromPort(portId, graph) {
  const out = new Set();
  const visitUp = (port) => {
    if (!port) return;
    (graph.byDst.get(port) || []).forEach((el) => {
      if (out.has(el)) return;
      out.add(el);
      visitUp(el.getAttribute("data-src") || "");
    });
  };
  const visitDown = (port) => {
    if (!port) return;
    (graph.bySrc.get(port) || []).forEach((el) => {
      if (out.has(el)) return;
      out.add(el);
      visitDown(el.getAttribute("data-dst") || "");
    });
  };
  visitUp(portId);
  visitDown(portId);
  return out;
}

function escapePortId(portId) {
  if (typeof CSS !== "undefined" && CSS.escape) return CSS.escape(portId);
  return String(portId).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function upstreamDriverPortIds(portId) {
  if (!edgeGraph || !portId) return [];
  const seen = new Set();
  const out = [];
  (edgeGraph.byDst.get(portId) || []).forEach((edgeEl) => {
    const src = edgeEl.getAttribute("data-src") || "";
    if (!src || seen.has(src)) return;
    seen.add(src);
    out.push(src);
  });
  return out.sort();
}

function outgoingPortIds(portId) {
  const seen = new Set();
  const out = [];
  (edgeGraph.bySrc.get(portId) || []).forEach((edgeEl) => {
    const dst = edgeEl.getAttribute("data-dst") || "";
    if (!dst || dst === portId || seen.has(dst)) return;
    seen.add(dst);
    out.push(dst);
  });
  return out;
}

/** 输出脚的下一级就是负载；输入脚则取直接驱动的扇出，去掉自己。 */
function downstreamLoadPortIds(portId) {
  if (!edgeGraph || !portId) return [];
  const direct = outgoingPortIds(portId);
  if (direct.length) return direct.sort();
  const seen = new Set();
  const out = [];
  (edgeGraph.byDst.get(portId) || []).forEach((edgeEl) => {
    const src = edgeEl.getAttribute("data-src") || "";
    if (!src) return;
    outgoingPortIds(src).forEach((dst) => {
      if (!dst || dst === portId || seen.has(dst)) return;
      seen.add(dst);
      out.push(dst);
    });
  });
  return out.sort();
}

function nodeIdOfPort(portId) {
  const cut = String(portId).lastIndexOf("__");
  return cut > 0 ? portId.slice(0, cut) : "";
}

function resetHopState() {
  driverHopCursor = { portId: "", index: 0 };
  loadHopCursor = { portId: "", index: 0 };
  hopStack = [];
  hopAnchorId = "";
  focusedPortId = "";
  clickGesture = null;
  closePortMenu();
}

function findPortElement(portId) {
  const svg = els.previewContent.querySelector("svg");
  if (!svg || !portId) return null;
  return svg.querySelector(`g.port[data-id="${escapePortId(portId)}"]`);
}

function portCenterInSvgRoot(portEl) {
  const svg = portEl.ownerSVGElement;
  if (!svg) return null;
  const hit = portEl.querySelector("circle.port-hit");
  if (hit) {
    const ctm = hit.getCTM && hit.getCTM();
    return svgPointToRoot(
      svg,
      parseFloat(hit.getAttribute("cx") || "0"),
      parseFloat(hit.getAttribute("cy") || "0"),
      ctm,
    );
  }
  const text = portEl.querySelector(".port-label-hit, .port-label");
  if (text) {
    try {
      const box = text.getBBox();
      const ctm = text.getCTM && text.getCTM();
      return svgPointToRoot(svg, box.x + box.width / 2, box.y + box.height / 2, ctm);
    } catch (err) {
      /* not laid out */
    }
  }
  const shape = portEl.querySelector(".port-shape, polygon");
  if (shape) {
    try {
      const box = shape.getBBox();
      const ctm = shape.getCTM && shape.getCTM();
      return svgPointToRoot(svg, box.x + box.width / 2, box.y + box.height / 2, ctm);
    } catch (err) {
      /* not laid out */
    }
  }
  return null;
}

function focusPortInView(portEl) {
  const center = portCenterInSvgRoot(portEl);
  if (!center) return;
  const rect = els.preview.getBoundingClientRect();
  const scale = view.scale;
  setView(scale, rect.width / 2 - center.x * scale, rect.height / 2 - center.y * scale);
}

function portDisplayName(portEl, portId) {
  return portEl?.querySelector(".port-label")?.textContent
    || String(portId || "").split("__").pop()
    || portId
    || "port";
}

function rememberHop(fromId) {
  if (!fromId) return;
  if (hopStack[hopStack.length - 1] === fromId) return;
  hopStack.push(fromId);
  if (hopStack.length > 64) hopStack.shift();
}

function jumpToRelatedPort(fromEl, targetId, label, index, total, missingMsg) {
  const target = findPortElement(targetId);
  if (!target) {
    setStatus(missingMsg, "error");
    return false;
  }
  const fromId = fromEl?.getAttribute("data-id") || "";
  if (fromId && fromId !== targetId) rememberHop(fromId);
  focusPortInView(target);
  applyPortPathHighlight(target);
  const name = portDisplayName(target, targetId);
  const suffix = total > 1 ? ` (${index + 1}/${total})` : "";
  setStatus(`已跳转到${label} · ${name}${suffix}`, "ok");
  return true;
}

function hopFromPort(portEl, direction) {
  if (!portEl) return;
  closePortMenu();
  const portId = portEl.getAttribute("data-id") || "";
  hopAnchorId = portId;
  const goingLoad = direction === "load";
  const targets = goingLoad ? downstreamLoadPortIds(portId) : upstreamDriverPortIds(portId);
  if (!targets.length) {
    setStatus(goingLoad ? "该端口没有下游负载" : "该端口没有上游驱动", "ok");
    return;
  }
  const cursor = goingLoad ? loadHopCursor : driverHopCursor;
  let index;
  if (cursor.portId !== portId) {
    index = 0;
  } else {
    index = (cursor.index + 1) % targets.length;
  }
  const next = { portId, index };
  if (goingLoad) loadHopCursor = next;
  else driverHopCursor = next;
  jumpToRelatedPort(
    portEl,
    targets[index],
    goingLoad ? "下游负载" : "上游驱动",
    index,
    targets.length,
    goingLoad ? "下游端口不在当前视图中" : "上游端口不在当前视图中",
  );
}

function hopAnchored(direction) {
  const portEl = findPortElement(hopAnchorId) || findPortElement(focusedPortId);
  if (!portEl) {
    setStatus("请先点选一个端口", "ok");
    return;
  }
  hopFromPort(portEl, direction);
}

function hopBack() {
  closePortMenu();
  if (!hopStack.length) {
    setStatus("没有可回退的跳转", "ok");
    return;
  }
  const portId = hopStack.pop();
  const portEl = findPortElement(portId);
  if (!portEl) {
    setStatus("上一个端口不在当前视图中", "error");
    return;
  }
  hopAnchorId = portId;
  focusPortInView(portEl);
  applyPortPathHighlight(portEl);
  setStatus(`已回到 · ${portDisplayName(portEl, portId)}`, "ok");
}

function closePortMenu() {
  if (!els.portMenu || els.portMenu.hidden) return;
  els.portMenu.hidden = true;
  delete els.portMenu.dataset.portId;
}

function openPortMenu(portEl, clientX, clientY) {
  if (!els.portMenu) return;
  const portId = portEl.getAttribute("data-id") || "";
  hopAnchorId = portId;
  applyPortPathHighlight(portEl);
  const drivers = upstreamDriverPortIds(portId);
  const loads = downstreamLoadPortIds(portId);
  els.portMenuDriver.textContent = `上游驱动 (${drivers.length})`;
  els.portMenuLoad.textContent = `下游负载 (${loads.length})`;
  els.portMenuDriver.disabled = !drivers.length;
  els.portMenuLoad.disabled = !loads.length;
  els.portMenu.dataset.portId = portId;
  els.portMenu.hidden = false;
  els.portMenu.style.left = "0px";
  els.portMenu.style.top = "0px";
  const box = els.portMenu.getBoundingClientRect();
  const left = Math.max(8, Math.min(clientX, window.innerWidth - box.width - 8));
  const top = Math.max(8, Math.min(clientY, window.innerHeight - box.height - 8));
  els.portMenu.style.left = `${left}px`;
  els.portMenu.style.top = `${top}px`;
}

function svgMarkupForDownload() {
  const live = els.previewContent.querySelector("svg");
  if (!live) return lastSvg;
  const clone = live.cloneNode(true);
  clone.classList.remove("path-dim");
  clone.querySelectorAll("g.edge.path-hl").forEach((el) => {
    restoreEdgeStroke(el);
    el.classList.remove("path-hl");
  });
  clone.querySelectorAll("g.port").forEach((el) => {
    if (el.classList.contains("port-hl")) restorePortStroke(el);
    el.classList.remove("port-hl", "port-onpath");
  });
  clone.querySelectorAll("g.node.node-hl").forEach((el) => {
    el.classList.remove("node-hl");
  });
  return new XMLSerializer().serializeToString(clone);
}

function clientToSvgRoot(clientX, clientY) {
  const svg = els.previewContent.querySelector("svg");
  if (!svg) return null;
  const ctm = svg.getScreenCTM();
  if (!ctm) return null;
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  const local = pt.matrixTransform(ctm.inverse());
  const pxPerUnit = Math.hypot(ctm.a, ctm.b) || view.scale || 1;
  return { x: local.x, y: local.y, pxPerUnit };
}

function svgPointToRoot(svg, x, y, matrix) {
  if (!matrix) return { x, y };
  const pt = svg.createSVGPoint();
  pt.x = x;
  pt.y = y;
  const out = pt.matrixTransform(matrix);
  return { x: out.x, y: out.y };
}

function distToSegment(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  if (len2 === 0) return Math.hypot(px - x1, py - y1);
  let t = ((px - x1) * dx + (py - y1) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

function distToPolyline(px, py, coords) {
  let min = Infinity;
  for (let i = 0; i < coords.length - 3; i += 2) {
    const d = distToSegment(px, py, coords[i], coords[i + 1], coords[i + 2], coords[i + 3]);
    if (d < min) min = d;
  }
  return min;
}

function distToDiagramRect(px, py, x, y, w, h) {
  const cx = Math.max(x, Math.min(px, x + w));
  const cy = Math.max(y, Math.min(py, y + h));
  return Math.hypot(px - cx, py - cy);
}

function distPointToRectScreen(clientX, clientY, rect, pad = 0) {
  const left = rect.left - pad;
  const top = rect.top - pad;
  const right = rect.right + pad;
  const bottom = rect.bottom + pad;
  const cx = Math.max(left, Math.min(clientX, right));
  const cy = Math.max(top, Math.min(clientY, bottom));
  return Math.hypot(clientX - cx, clientY - cy);
}

function samplePathDiagram(path, maxSamples = 64) {
  if (!path || !path.getTotalLength) return new Float32Array(0);
  const svg = path.ownerSVGElement;
  const toRoot = path.getCTM && path.getCTM();
  let total;
  try {
    total = path.getTotalLength();
  } catch (err) {
    return new Float32Array(0);
  }
  if (!Number.isFinite(total) || total <= 0) return new Float32Array(0);
  const n = Math.min(maxSamples, Math.max(2, Math.ceil(total / 6) + 1));
  const coords = new Float32Array(n * 2);
  for (let i = 0; i < n; i += 1) {
    const p = path.getPointAtLength((total * i) / (n - 1));
    const root = svg && toRoot ? svgPointToRoot(svg, p.x, p.y, toRoot) : p;
    coords[i * 2] = root.x;
    coords[i * 2 + 1] = root.y;
  }
  return coords;
}

function buildPickCache(svg) {
  const ports = [];
  svg.querySelectorAll("g.port").forEach((el) => {
    const text = el.querySelector(".port-label-hit, .port-label");
    if (text) {
      ports.push({ el, kind: "text", textEl: text });
    }
    const hit = el.querySelector("circle.port-hit");
    if (!hit) return;
    const ctm = hit.getCTM && hit.getCTM();
    const cx = parseFloat(hit.getAttribute("cx") || "0");
    const cy = parseFloat(hit.getAttribute("cy") || "0");
    const center = svgPointToRoot(svg, cx, cy, ctm);
    const edge = svgPointToRoot(svg, cx + parseFloat(hit.getAttribute("r") || "12"), cy, ctm);
    const r = Math.hypot(edge.x - center.x, edge.y - center.y);
    ports.push({ el, kind: "circle", cx: center.x, cy: center.y, r });
  });

  const edges = [];
  svg.querySelectorAll("g.edge").forEach((el) => {
    const path = el.querySelector("path.edge-stroke, path.swatch-stroke");
    if (!path) return;
    const pts = samplePathDiagram(path);
    if (pts.length >= 4) edges.push({ el, pts });
  });
  return { ports, edges };
}

function portPickDistDiagram(entry, x, y, pxPerUnit) {
  const pad = PORT_HIT_PX / pxPerUnit;
  const hitR = Math.max(entry.r, pad);
  return Math.max(0, Math.hypot(x - entry.cx, y - entry.cy) - hitR);
}

function portPickScoreScreen(entry, clientX, clientY) {
  if (entry.kind !== "text" || !entry.textEl) return Infinity;
  const rect = entry.textEl.getBoundingClientRect();
  if (!rect.width && !rect.height) return Infinity;
  const pad = 2;
  return distPointToRectScreen(clientX, clientY, rect, pad) / PORT_HIT_PX;
}

/** Nearest port/edge by geometry (cached polylines; screen threshold via scale). */
function pickAt(clientX, clientY) {
  if (!pickCache) return null;
  const root = clientToSvgRoot(clientX, clientY);
  if (!root) return null;
  const { x, y, pxPerUnit } = root;
  let bestPort = null;
  let bestEdge = null;
  let bestScore = 1;
  pickCache.ports.forEach((entry) => {
    const score = entry.kind === "text"
      ? portPickScoreScreen(entry, clientX, clientY)
      : (portPickDistDiagram(entry, x, y, pxPerUnit) * pxPerUnit) / PORT_HIT_PX;
    if (score < bestScore) {
      bestScore = score;
      bestPort = entry.el;
      bestEdge = null;
    }
  });
  pickCache.edges.forEach(({ el, pts }) => {
    const score = (distToPolyline(x, y, pts) * pxPerUnit) / EDGE_HIT_PX;
    if (score < bestScore) {
      bestScore = score;
      bestPort = null;
      bestEdge = el;
    }
  });
  if (bestScore >= 1) return null;
  return { port: bestPort, edge: bestEdge };
}

function updatePreviewCursor(clientX, clientY) {
  if (!hasSvg() || pointers.size > 0) {
    els.preview.style.cursor = "";
    return;
  }
  const hit = pickAt(clientX, clientY);
  els.preview.style.cursor = hit ? "pointer" : "";
}

function schedulePreviewCursor(clientX, clientY) {
  cursorPickXY.x = clientX;
  cursorPickXY.y = clientY;
  if (cursorPickRaf) return;
  cursorPickRaf = requestAnimationFrame(() => {
    cursorPickRaf = 0;
    updatePreviewCursor(cursorPickXY.x, cursorPickXY.y);
  });
}

const PATH_HL_STROKE = "#1d4ed8";
const PATH_HL_PORT_WIDTH = "2.8";
const PATH_HL_EDGE_WIDTH = "3";

function restoreEdgeStroke(el) {
  el.querySelectorAll(".edge-stroke, path.swatch-stroke").forEach((path) => {
    if (path.dataset.prevStrokeWidth != null) {
      path.setAttribute("stroke-width", path.dataset.prevStrokeWidth);
      delete path.dataset.prevStrokeWidth;
    }
  });
}

function emphasizeEdgeStroke(el) {
  el.querySelectorAll(".edge-stroke, path.swatch-stroke").forEach((path) => {
    if (path.dataset.prevStrokeWidth == null) {
      path.dataset.prevStrokeWidth = path.getAttribute("stroke-width") || "1.2";
    }
    path.setAttribute("stroke-width", PATH_HL_EDGE_WIDTH);
  });
}

function restorePortStroke(el) {
  const shape = portShapeEl(el);
  if (!shape) return;
  if (shape.tagName.toLowerCase() === "text") {
    if (shape.dataset.prevFill != null) {
      shape.setAttribute("fill", shape.dataset.prevFill);
      delete shape.dataset.prevFill;
    }
    if (shape.dataset.prevWeight != null) {
      shape.setAttribute("font-weight", shape.dataset.prevWeight);
      delete shape.dataset.prevWeight;
    } else {
      shape.removeAttribute("font-weight");
    }
    return;
  }
  if (shape.dataset.prevStroke != null) {
    shape.setAttribute("stroke", shape.dataset.prevStroke);
    delete shape.dataset.prevStroke;
  }
  if (shape.dataset.prevStrokeWidth != null) {
    shape.setAttribute("stroke-width", shape.dataset.prevStrokeWidth);
    delete shape.dataset.prevStrokeWidth;
  }
}

function portShapeEl(el) {
  if (el.classList.contains("port-text")) {
    return el.querySelector(".port-label-hit, .port-label");
  }
  return el.querySelector(".port-shape, polygon.swatch-fill, polygon");
}

function emphasizePortStroke(el) {
  const shape = portShapeEl(el);
  if (!shape) return;
  if (shape.tagName.toLowerCase() === "text") {
    if (shape.dataset.prevFill == null) {
      shape.dataset.prevFill = shape.getAttribute("fill") || "";
    }
    if (shape.dataset.prevWeight == null) {
      shape.dataset.prevWeight = shape.getAttribute("font-weight") || "";
    }
    shape.setAttribute("fill", PATH_HL_STROKE);
    shape.setAttribute("font-weight", "700");
    return;
  }
  if (shape.dataset.prevStroke == null) {
    shape.dataset.prevStroke = shape.getAttribute("stroke") || "";
  }
  if (shape.dataset.prevStrokeWidth == null) {
    shape.dataset.prevStrokeWidth = shape.getAttribute("stroke-width") || "1";
  }
  shape.setAttribute("stroke", PATH_HL_STROKE);
  shape.setAttribute("stroke-width", PATH_HL_PORT_WIDTH);
}

function clearPathHighlightVisuals() {
  const svg = els.previewContent.querySelector("svg");
  if (!svg) return;
  svg.classList.remove("path-dim");
  svg.querySelectorAll("g.edge.path-hl").forEach((el) => {
    restoreEdgeStroke(el);
    el.classList.remove("path-hl");
  });
  svg.querySelectorAll("g.port.port-hl").forEach((el) => {
    restorePortStroke(el);
    el.classList.remove("port-hl");
  });
  svg.querySelectorAll("g.port.port-onpath").forEach((el) => {
    el.classList.remove("port-onpath");
  });
  svg.querySelectorAll("g.node.node-hl").forEach((el) => {
    el.classList.remove("node-hl");
  });
}

function clearPathHighlight() {
  clearPathHighlightVisuals();
  focusedPortId = "";
  hopAnchorId = "";
}

function raiseHighlighted(svg) {
  const layer = svg.querySelector("g");
  if (!layer) return;
  layer.querySelectorAll("g.edge.path-hl").forEach((el) => layer.appendChild(el));
  layer.querySelectorAll("g.port.port-onpath").forEach((el) => layer.appendChild(el));
  layer.querySelectorAll("g.port.port-hl").forEach((el) => layer.appendChild(el));
}

function syncPathDim(edgeSet, focusId) {
  const svg = els.previewContent.querySelector("svg");
  if (!svg) return;
  const portIds = new Set();
  if (focusId) portIds.add(focusId);
  edgeSet.forEach((el) => {
    const src = el.getAttribute("data-src") || "";
    const dst = el.getAttribute("data-dst") || "";
    if (src) portIds.add(src);
    if (dst) portIds.add(dst);
  });
  if (!portIds.size && !edgeSet.size) {
    svg.classList.remove("path-dim");
    return;
  }
  svg.classList.add("path-dim");
  const nodeIds = new Set();
  portIds.forEach((id) => {
    const nid = nodeIdOfPort(id);
    if (nid) nodeIds.add(nid);
  });
  svg.querySelectorAll("g.node").forEach((el) => {
    el.classList.toggle("node-hl", nodeIds.has(el.getAttribute("data-id") || ""));
  });
  svg.querySelectorAll("g.port").forEach((el) => {
    const id = el.getAttribute("data-id") || "";
    el.classList.toggle("port-onpath", Boolean(id) && portIds.has(id) && id !== focusId);
  });
  raiseHighlighted(svg);
}

function highlightEdgeSet(edgeEls) {
  edgeEls.forEach((el) => {
    el.classList.add("path-hl");
    emphasizeEdgeStroke(el);
  });
}

function applyPathHighlightFromEdges(edgeSet) {
  clearPathHighlightVisuals();
  highlightEdgeSet(edgeSet);
  return edgeSet.size;
}

function applyPortPathHighlight(portEl) {
  if (!portEl) return;
  const portId = portEl.getAttribute("data-id") || "";
  const edges = new Set();
  if (edgeGraph && portId) {
    closureEdgesFromPort(portId, edgeGraph).forEach((el) => edges.add(el));
  }
  const edgeCount = applyPathHighlightFromEdges(edges);
  focusedPortId = portId;
  portEl.classList.add("port-hl");
  emphasizePortStroke(portEl);
  syncPathDim(edges, portId);
  const name = portDisplayName(portEl, portId);
  if (edgeCount) {
    setStatus(`已高亮 ${name} · ${edgeCount} 条连线`, "ok");
  } else {
    setStatus("");
  }
}

function applyEdgePathHighlight(edgeEl) {
  if (!edgeEl) return;
  const edges = new Set([edgeEl]);
  if (edgeGraph) {
    const src = edgeEl.getAttribute("data-src") || "";
    const dst = edgeEl.getAttribute("data-dst") || "";
    if (src) closureEdgesFromPort(src, edgeGraph).forEach((el) => edges.add(el));
    if (dst) closureEdgesFromPort(dst, edgeGraph).forEach((el) => edges.add(el));
  }
  focusedPortId = "";
  hopAnchorId = "";
  const edgeCount = applyPathHighlightFromEdges(edges);
  syncPathDim(edges, "");
  setStatus(`已高亮通路 · ${edgeCount} 条连线`, "ok");
}

function handlePickAt(clientX, clientY) {
  const hit = pickAt(clientX, clientY);
  if (hit?.port) {
    hopAnchorId = hit.port.getAttribute("data-id") || "";
    applyPortPathHighlight(hit.port);
    return;
  }
  if (hit?.edge) {
    applyEdgePathHighlight(hit.edge);
    return;
  }
  clearPathHighlight();
  setStatus("");
}

function notePreviewClick(clientX, clientY) {
  const now = performance.now();
  const hit = pickAt(clientX, clientY);
  const portId = hit?.port?.getAttribute("data-id") || "";
  const edgeHit = Boolean(hit?.edge);
  const instNode = !portId && !edgeHit ? pickInstanceNodeAt(clientX, clientY) : null;
  const instanceId = instNode?.getAttribute("data-id") || "";
  const previous = clickGesture;
  clickGesture = { x: clientX, y: clientY, t: now, portId, instanceId };
  if (
    previous
    && previous.portId
    && now - previous.t <= DBLCLICK_MS
    && Math.hypot(clientX - previous.x, clientY - previous.y) <= DBLCLICK_PX
  ) {
    const portEl = findPortElement(previous.portId);
    clickGesture = null;
    if (portEl) {
      hopFromPort(portEl, "driver");
      return;
    }
  }
  if (
    hierarchical
    && instanceId
    && previous
    && previous.instanceId === instanceId
    && !portId
    && !previous.portId
    && !edgeHit
    && now - previous.t <= DBLCLICK_MS
    && Math.hypot(clientX - previous.x, clientY - previous.y) <= DBLCLICK_PX
  ) {
    clickGesture = null;
    toggleInstanceExpand(instanceId);
    return;
  }
  if (hierarchical && instNode && !portId && !edgeHit) {
    selectedInstance = {
      path: instanceId,
      moduleUse: instNode.getAttribute("data-module-use") || "",
    };
    syncNavUi();
    syncInstanceSelectionVisual();
    clearPathHighlight();
    setStatus(`已选 instance ${instanceId}`, "ok");
    return;
  }
  handlePickAt(clientX, clientY);
}

function applyDrawPayload(data) {
  lastDrawio = data.drawio || "";
  lastDrawioName = data.drawio_filename || "graph.drawio";
  lastDrawioError = data.drawio_error || "";
  syncDrawioDownload();
}

function resetPreview() {
  lastSvg = "";
  lastDrawio = "";
  lastDrawioError = "";
  pointers.clear();
  pinchStart = null;
  panSession = null;
  edgeGraph = null;
  pickCache = null;
  resetHopState();
  els.preview.style.cursor = "";
  els.preview.classList.remove("panning");
  els.previewPlaceholder.hidden = false;
  els.previewContent.hidden = true;
  els.previewContent.replaceChildren();
  setView(1, 0, 0);
  setViewControls(false);
}

function wireSvgInteraction(svg) {
  if (!svg || svg.dataset.wiredInteraction === "1") return;
  svg.dataset.wiredInteraction = "1";
  svg.style.pointerEvents = "auto";
}

function renderSvg(svgText) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(svgText, "image/svg+xml");
  const svg = doc.documentElement;
  if (!svg || svg.nodeName.toLowerCase() !== "svg") {
    throw new Error("返回内容不是有效 SVG");
  }
  els.previewPlaceholder.hidden = true;
  els.previewContent.hidden = false;
  els.previewContent.replaceChildren(document.importNode(svg, true));
  const live = els.previewContent.querySelector("svg");
  edgeGraph = live ? buildEdgeGraph(live) : null;
  pickCache = live ? buildPickCache(live) : null;
  resetHopState();
  wireSvgInteraction(live);
  applyPalette();
  setViewControls(true);
  requestAnimationFrame(() => {
    fitView();
    if (live) pickCache = buildPickCache(live);
    syncInstanceSelectionVisual();
  });
}

async function runDraw(manual) {
  if (hierarchical) {
    els.drawBtn.disabled = true;
    setStatus("正在出图…");
    try {
      const resp = await fetch("/api/draw", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          view_module: viewModule,
          expanded_paths: Array.from(expandedPaths),
          port_include: portInclude,
          port_exclude: portExclude,
          palette,
        }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) throw new Error(data.error || "出图失败");
      lastSvg = data.svg;
      lastSvgName = data.filename || "graph.svg";
      applyDrawPayload(data);
      renderSvg(lastSvg);
      if (data.tree) {
        renderTree(data.tree);
        checkAll();
      }
      if (data.view_module) viewModule = data.view_module;
      if (Array.isArray(data.expanded_paths)) {
        expandedPaths = new Set(data.expanded_paths);
      }
      syncNavUi();
      const drawioNote = lastDrawio ? "" : (lastDrawioError ? " · draw.io 未生成" : "");
      setStatus((manual ? "出图完成" : "层次视图已更新") + drawioNote, "ok");
    } catch (err) {
      setStatus(err.message, "error");
    } finally {
      updateCheckedCount();
    }
    return;
  }

  const include = getCheckedInstances();
  if (!include.length) {
    setStatus("请至少勾选一个节点", "error");
    return;
  }

  els.drawBtn.disabled = true;
  setStatus("正在出图…");
  try {
    const resp = await fetch("/api/draw", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        port_include: portInclude,
        port_exclude: portExclude,
        include,
        palette,
      }),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.error || "出图失败");
    lastSvg = data.svg;
    lastSvgName = data.filename || "graph.svg";
    applyDrawPayload(data);
    renderSvg(lastSvg);
    const drawioNote = lastDrawio ? "" : (lastDrawioError ? " · draw.io 未生成" : "");
    setStatus("出图完成" + drawioNote, "ok");
  } catch (err) {
    setStatus(err.message, "error");
  } finally {
    updateCheckedCount();
  }
}

function checkAll() {
  els.tree.querySelectorAll('input[type="checkbox"]').forEach((input) => {
    input.checked = true;
  });
  updateCheckedCount();
}

function swatchesFromPalette(colors) {
  return Object.keys(colors || {}).map((key) => ({
    key,
    label: key,
    group: "配色",
    color: colors[key],
  }));
}

function showDocumentEmpty() {
  hierarchical = false;
  viewModule = "";
  expandedPaths = new Set();
  navStack = [];
  selectedInstance = { path: "", moduleUse: "" };
  syncNavUi();
  basePalette = {};
  baseSwatches = [];
  swatches = [];
  palette = { ...loadPalette() };
  const label = "未打开文件";
  els.fileMeta.textContent = label;
  els.fileMeta.title = label;
  renderPalette();
  els.tree.replaceChildren();
  els.tree.classList.add("empty");
  els.tree.textContent = "打开 JSON 后显示层次";
  updateCheckedCount();
  resetPreview();
}

async function applyDocumentPayload(data) {
  basePalette = data.palette || {};
  baseSwatches = (data.swatches && data.swatches.length)
    ? data.swatches
    : swatchesFromPalette(basePalette);
  swatches = baseSwatches.map((item) => ({
    ...item,
    color: basePalette[item.key] || item.color || "#cccccc",
  }));
  const stored = loadPalette();
  palette = { ...basePalette };
  Object.keys(stored).forEach((key) => {
    if (palette[key] || swatches.some((item) => item.key === key)) palette[key] = stored[key];
  });
  const name = data.name || "design.json";
  els.fileMeta.textContent = name;
  els.fileMeta.title = name;
  hierarchical = Boolean(data.hierarchical);
  viewModule = data.view_module || "";
  expandedPaths = new Set(data.expanded_paths || []);
  navStack = [];
  selectedInstance = { path: "", moduleUse: "" };
  syncNavUi();
  renderPalette();
  renderTree(data.tree);
  checkAll();
  resetPreview();
  if (hierarchical) {
    setStatus("双击 instance 展开一层 · Go in 进入 module", "ok");
    await runDraw(false);
    return;
  }
  setStatus("勾选要绘制的节点后点击 Draw", "ok");
}

async function loadDocument() {
  setStatus("正在加载电路图…");
  try {
    const resp = await fetch("/api/document");
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.error || "无法加载电路图");
    if (data.loaded === false) {
      showDocumentEmpty();
      setStatus("点击顶栏「打开文件」选择 JSON，或启动时传入 schematic view 路径", "ok");
      return;
    }
    applyDocumentPayload(data);
  } catch (err) {
    setStatus(err.message, "error");
  }
}

async function openDocumentFile(file) {
  if (!file) return;
  setStatus(`正在打开 ${file.name}…`);
  let document;
  try {
    document = JSON.parse(await file.text());
  } catch (err) {
    setStatus("JSON 解析失败", "error");
    return;
  }
  try {
    const resp = await fetch("/api/document", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: file.name, document }),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.error || "无法打开文件");
    applyDocumentPayload(data);
  } catch (err) {
    setStatus(err.message, "error");
  } finally {
    if (els.fileOpen) els.fileOpen.value = "";
  }
}

loadDocument();

if (els.fileOpen) {
  els.fileOpen.addEventListener("change", () => {
    const file = els.fileOpen.files && els.fileOpen.files[0];
    openDocumentFile(file);
  });
}

setToolbarCollapsed(Boolean(loadUi().toolbarCollapsed));

els.toolbarFold.addEventListener("click", () => {
  setToolbarCollapsed(!els.toolbar.classList.contains("is-collapsed"));
});

els.paletteReset.addEventListener("click", () => {
  palette = { ...basePalette };
  swatches.forEach((item) => {
    if (!palette[item.key] && item.color) palette[item.key] = item.color;
  });
  savePalette();
  renderPalette();
  applyPalette();
});

els.portIncludeForm.addEventListener("submit", (event) => {
  event.preventDefault();
  addPattern("include");
});

els.portExcludeForm.addEventListener("submit", (event) => {
  event.preventDefault();
  addPattern("exclude");
});

els.portFilterReset.addEventListener("click", () => {
  portInclude = [];
  portExclude = [];
  savePortFilter();
  renderPortFilter();
  setStatus("已清空 Port filter", "ok");
});

els.drawBtn.addEventListener("click", () => {
  runDraw(true);
});

if (els.goInBtn) els.goInBtn.addEventListener("click", goIn);
if (els.goOutBtn) els.goOutBtn.addEventListener("click", goOut);

els.downloadBtn.addEventListener("click", () => {
  const text = svgMarkupForDownload();
  if (!text) return;
  const blob = new Blob([text], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = lastSvgName;
  a.click();
  URL.revokeObjectURL(url);
});

if (els.downloadDrawioBtn) {
  els.downloadDrawioBtn.addEventListener("click", () => {
    if (!lastDrawio) {
      setStatus(lastDrawioError || "draw.io 不可用", "error");
      return;
    }
    const blob = new Blob([lastDrawio], { type: "application/xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = lastDrawioName;
    a.click();
    URL.revokeObjectURL(url);
  });
}

els.zoomInBtn.addEventListener("click", () => zoomBy(ZOOM_STEP));
els.zoomOutBtn.addEventListener("click", () => zoomBy(1 / ZOOM_STEP));
els.zoomFitBtn.addEventListener("click", fitView);
els.zoomResetBtn.addEventListener("click", resetView);
els.fullscreenBtn.addEventListener("click", toggleFullscreen);

els.preview.addEventListener("mousemove", (event) => {
  schedulePreviewCursor(event.clientX, event.clientY);
});

els.preview.addEventListener("mouseleave", () => {
  els.preview.style.cursor = "";
});

els.preview.addEventListener("wheel", (event) => {
  if (!hasSvg()) return;
  event.preventDefault();
  const factor = event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
  zoomAt(event.clientX, event.clientY, factor);
}, { passive: false });

els.preview.addEventListener("pointerdown", (event) => {
  if (!hasSvg()) return;
  if (event.pointerType === "mouse" && event.button !== 0) return;
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
  if (pointers.size === 1) {
    panSession = {
      x0: event.clientX,
      y0: event.clientY,
      dragging: false,
      lastX: event.clientX,
      lastY: event.clientY,
      pointerId: event.pointerId,
    };
  } else if (pointers.size === 2) {
    panSession = null;
    try {
      els.preview.setPointerCapture(event.pointerId);
    } catch (err) {
      /* ignore */
    }
    els.preview.classList.add("panning");
    const pts = Array.from(pointers.values());
    pinchStart = {
      dist: Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y),
      scale: view.scale,
      midX: (pts[0].x + pts[1].x) / 2,
      midY: (pts[0].y + pts[1].y) / 2,
      x: view.x,
      y: view.y,
    };
  }
});

els.preview.addEventListener("pointermove", (event) => {
  if (!pointers.has(event.pointerId)) return;
  const prev = pointers.get(event.pointerId);
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

  if (pointers.size === 2 && pinchStart) {
    const pts = Array.from(pointers.values());
    const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
    const midX = (pts[0].x + pts[1].x) / 2;
    const midY = (pts[0].y + pts[1].y) / 2;
    if (pinchStart.dist > 0) {
      const factor = dist / pinchStart.dist;
      const rect = els.preview.getBoundingClientRect();
      const px = pinchStart.midX - rect.left;
      const py = pinchStart.midY - rect.top;
      const next = clampScale(pinchStart.scale * factor);
      const ratio = next / pinchStart.scale;
      setView(
        next,
        px - (px - pinchStart.x) * ratio + (midX - pinchStart.midX),
        py - (py - pinchStart.y) * ratio + (midY - pinchStart.midY),
      );
    }
    return;
  }

  if (pointers.size === 1 && panSession) {
    const dx0 = event.clientX - panSession.x0;
    const dy0 = event.clientY - panSession.y0;
    if (!panSession.dragging && Math.hypot(dx0, dy0) > CLICK_MOVE_PX) {
      panSession.dragging = true;
      try {
        els.preview.setPointerCapture(panSession.pointerId);
      } catch (err) {
        /* ignore */
      }
      els.preview.classList.add("panning");
    }
    if (panSession.dragging) {
      view.x += event.clientX - panSession.lastX;
      view.y += event.clientY - panSession.lastY;
      applyView();
    }
    panSession.lastX = event.clientX;
    panSession.lastY = event.clientY;
  }
});

function endPointer(event) {
  if (!pointers.has(event.pointerId)) return;
  pointers.delete(event.pointerId);
  if (pointers.size < 2) pinchStart = null;
  if (pointers.size === 0) {
    if (panSession && panSession.dragging) {
      clickGesture = null;
      try {
        els.preview.releasePointerCapture(event.pointerId);
      } catch (err) {
        /* ignore */
      }
    } else if (panSession) {
      notePreviewClick(event.clientX, event.clientY);
    }
    els.preview.classList.remove("panning");
    panSession = null;
    updatePreviewCursor(event.clientX, event.clientY);
  }
}

els.preview.addEventListener("pointerup", endPointer);
els.preview.addEventListener("pointercancel", endPointer);
els.preview.addEventListener("lostpointercapture", endPointer);

function typingTarget(event) {
  if (event.isComposing) return true;
  const tag = (event.target && event.target.tagName) || "";
  return tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA";
}

els.preview.addEventListener("contextmenu", (event) => {
  if (!hasSvg()) return;
  event.preventDefault();
  const hit = pickAt(event.clientX, event.clientY);
  if (!hit?.port) {
    closePortMenu();
    return;
  }
  openPortMenu(hit.port, event.clientX, event.clientY);
});

if (els.portMenu) {
  els.portMenu.addEventListener("contextmenu", (event) => {
    event.preventDefault();
  });
  els.portMenu.addEventListener("click", (event) => {
    const btn = event.target.closest("button");
    if (!btn || btn.disabled) return;
    const portEl = findPortElement(els.portMenu.dataset.portId || hopAnchorId);
    const direction = btn.dataset.hop === "load" ? "load" : "driver";
    closePortMenu();
    if (!portEl) {
      setStatus("该端口不在当前视图中", "error");
      return;
    }
    hopFromPort(portEl, direction);
  });
}

document.addEventListener("pointerdown", (event) => {
  if (!els.portMenu || els.portMenu.hidden) return;
  if (els.portMenu.contains(event.target)) return;
  closePortMenu();
});

document.addEventListener("keydown", (event) => {
  if (!hasSvg()) return;
  if (typingTarget(event)) return;
  const chord = event.ctrlKey || event.metaKey || event.altKey;
  if (event.key === "Escape") {
    if (els.portMenu && !els.portMenu.hidden) {
      closePortMenu();
      return;
    }
    clearPathHighlight();
    setStatus("");
    return;
  }
  if (chord) return;
  if (event.key === "+" || event.key === "=") {
    event.preventDefault();
    zoomBy(ZOOM_STEP);
  } else if (event.key === "-" || event.key === "_") {
    event.preventDefault();
    zoomBy(1 / ZOOM_STEP);
  } else if ((event.code === "Digit0" || event.code === "Numpad0") && event.shiftKey) {
    event.preventDefault();
    fitHighlighted();
  } else if (event.key === "0") {
    event.preventDefault();
    fitView();
  } else if (event.key === "f" || event.key === "F") {
    event.preventDefault();
    toggleFullscreen();
  } else if (event.key === "[") {
    event.preventDefault();
    hopAnchored("driver");
  } else if (event.key === "]") {
    event.preventDefault();
    hopAnchored("load");
  } else if (event.key === "Backspace") {
    event.preventDefault();
    hopBack();
  }
});

document.addEventListener("fullscreenchange", () => {
  updateFullscreenButton();
  if (hasSvg()) requestAnimationFrame(fitView);
});
document.addEventListener("webkitfullscreenchange", () => {
  updateFullscreenButton();
  if (hasSvg()) requestAnimationFrame(fitView);
});

window.addEventListener("resize", () => {
  if (hasSvg() && isFullscreen()) requestAnimationFrame(fitView);
});
