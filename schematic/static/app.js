const FILTER_STORE = "schematic-port-filter";
const PALETTE_STORE = "schematic-palette";
const UI_STORE = "schematic-ui";
const MAX_PORT_PATTERNS = 64;
const MAX_PORT_PATTERN_LEN = 80;

const els = {
  fileMeta: document.getElementById("file-meta"),
  portFilterReset: document.getElementById("port-filter-reset"),
  portIncludeList: document.getElementById("port-include-list"),
  portExcludeList: document.getElementById("port-exclude-list"),
  portIncludeCount: document.getElementById("port-include-count"),
  portExcludeCount: document.getElementById("port-exclude-count"),
  portIncludeForm: document.getElementById("port-include-form"),
  portExcludeForm: document.getElementById("port-exclude-form"),
  portIncludeInput: document.getElementById("port-include-input"),
  portExcludeInput: document.getElementById("port-exclude-input"),
  simpleMode: document.getElementById("simple-mode"),
  toolbar: document.getElementById("toolbar"),
  toolbarFold: document.getElementById("toolbar-fold"),
  palette: document.getElementById("palette"),
  paletteReset: document.getElementById("palette-reset"),
  tree: document.getElementById("tree"),
  checkedCount: document.getElementById("checked-count"),
  status: document.getElementById("status"),
  drawBtn: document.getElementById("draw-btn"),
  downloadBtn: document.getElementById("download-btn"),
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
};

const VIEW_MIN = 0.1;
const VIEW_MAX = 16;
const ZOOM_STEP = 1.2;

let lastSvg = "";
let lastSvgName = "graph.svg";
let basePalette = {};
let baseSwatches = [];
let view = { scale: 1, x: 0, y: 0 };
let pointers = new Map();
let pinchStart = null;
let panSession = null;
let edgeGraph = null;
/** @type {{ ports: object[], edges: { el: Element, pts: Float32Array }[] } | null} */
let pickCache = null;
let cursorPickRaf = 0;
let cursorPickXY = { x: 0, y: 0 };
let driverHopCursor = { portId: "", index: 0 };

const CLICK_MOVE_PX = 5;
const EDGE_HIT_PX = 24;
const PORT_HIT_PX = 12;
let swatches = [];
let palette = loadPalette();
let portInclude = [];
let portExclude = [];

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
    const fillable = el.classList.contains("swatch-fill")
      ? el
      : el.querySelector(".swatch-fill");
    if (!fillable) return;
    fillable.setAttribute("fill", color);
    fillable.setAttribute("stroke", darkenHex(color, 0.35));
  });
}

function applyPalette() {
  applyPaletteTo(els.tree);
  applyPaletteTo(els.previewContent.querySelector("svg"));
}

function visibleSwatches() {
  const boxesOnly = Boolean(els.simpleMode && els.simpleMode.checked);
  return swatches.filter((item) => !boxesOnly || item.group !== "内部逻辑");
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
  els.drawBtn.disabled = count === 0;
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

function setViewControls(enabled) {
  els.zoomInBtn.disabled = !enabled;
  els.zoomOutBtn.disabled = !enabled;
  els.zoomFitBtn.disabled = !enabled;
  els.zoomResetBtn.disabled = !enabled;
  els.downloadBtn.disabled = !enabled;
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

function jumpToUpstreamDriver(portEl) {
  const portId = portEl.getAttribute("data-id") || "";
  const drivers = upstreamDriverPortIds(portId);
  if (!drivers.length) {
    setStatus("该端口没有上游驱动", "ok");
    return;
  }
  if (driverHopCursor.portId !== portId) {
    driverHopCursor = { portId, index: 0 };
  } else {
    driverHopCursor.index = (driverHopCursor.index + 1) % drivers.length;
  }
  const targetId = drivers[driverHopCursor.index];
  const target = findPortElement(targetId);
  if (!target) {
    setStatus("上游端口不在当前视图中", "error");
    return;
  }
  focusPortInView(target);
  applyPortPathHighlight(target);
  const name = target.querySelector(".port-label")?.textContent
    || targetId.split("__").pop()
    || targetId;
  const suffix = drivers.length > 1 ? ` (${driverHopCursor.index + 1}/${drivers.length})` : "";
  setStatus(`已跳转到上游驱动 · ${name}${suffix}`, "ok");
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

function clearPathHighlight() {
  const svg = els.previewContent.querySelector("svg");
  if (!svg) return;
  svg.querySelectorAll("g.edge.path-hl").forEach((el) => {
    restoreEdgeStroke(el);
    el.classList.remove("path-hl");
  });
  svg.querySelectorAll("g.port.port-hl").forEach((el) => {
    restorePortStroke(el);
    el.classList.remove("port-hl");
  });
}

function highlightEdgeSet(edgeEls) {
  edgeEls.forEach((el) => {
    el.classList.add("path-hl");
    emphasizeEdgeStroke(el);
  });
}

function applyPathHighlightFromEdges(edgeSet) {
  clearPathHighlight();
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
  portEl.classList.add("port-hl");
  emphasizePortStroke(portEl);
  const name = portEl.querySelector(".port-label")?.textContent
    || portEl.getAttribute("data-id")?.split("__").pop()
    || "port";
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
  const edgeCount = applyPathHighlightFromEdges(edges);
  setStatus(`已高亮通路 · ${edgeCount} 条连线`, "ok");
}

function handlePickAt(clientX, clientY) {
  const hit = pickAt(clientX, clientY);
  if (hit?.port) {
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

function resetPreview() {
  lastSvg = "";
  pointers.clear();
  pinchStart = null;
  panSession = null;
  edgeGraph = null;
  pickCache = null;
  driverHopCursor = { portId: "", index: 0 };
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
  const onPick = (event) => {
    if (!hasSvg()) return;
    handlePickAt(event.clientX, event.clientY);
  };
  svg.addEventListener("click", onPick);
  svg.addEventListener("dblclick", (event) => {
    if (!hasSvg()) return;
    event.preventDefault();
    const hit = pickAt(event.clientX, event.clientY);
    if (hit?.port) jumpToUpstreamDriver(hit.port);
  });
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
  driverHopCursor = { portId: "", index: 0 };
  wireSvgInteraction(live);
  applyPalette();
  setViewControls(true);
  requestAnimationFrame(() => {
    fitView();
    if (live) pickCache = buildPickCache(live);
  });
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

async function loadDocument() {
  setStatus("正在加载电路图…");
  try {
    const resp = await fetch("/api/document");
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.error || "无法加载电路图");
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
    els.fileMeta.textContent = data.name || "design.json";
    renderPalette();
    renderTree(data.tree);
    checkAll();
    resetPreview();
    setStatus("勾选要绘制的节点后点击 Draw", "ok");
  } catch (err) {
    setStatus(err.message, "error");
  }
}

loadDocument();

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

if (els.simpleMode) {
  els.simpleMode.addEventListener("change", () => {
    renderPalette();
  });
}

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

els.drawBtn.addEventListener("click", async () => {
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
        boxes_only: Boolean(els.simpleMode && els.simpleMode.checked),
        palette,
      }),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.error || "出图失败");
    lastSvg = data.svg;
    lastSvgName = data.filename || "graph.svg";
    renderSvg(lastSvg);
    setStatus("出图完成", "ok");
  } catch (err) {
    setStatus(err.message, "error");
  } finally {
    updateCheckedCount();
  }
});

els.downloadBtn.addEventListener("click", () => {
  const live = els.previewContent.querySelector("svg");
  const text = live ? new XMLSerializer().serializeToString(live) : lastSvg;
  if (!text) return;
  const blob = new Blob([text], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = lastSvgName;
  a.click();
  URL.revokeObjectURL(url);
});

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
      try {
        els.preview.releasePointerCapture(event.pointerId);
      } catch (err) {
        /* ignore */
      }
    } else if (panSession) {
      handlePickAt(event.clientX, event.clientY);
    }
    els.preview.classList.remove("panning");
    panSession = null;
    updatePreviewCursor(event.clientX, event.clientY);
  }
}

els.preview.addEventListener("pointerup", endPointer);
els.preview.addEventListener("pointercancel", endPointer);
els.preview.addEventListener("lostpointercapture", endPointer);

document.addEventListener("keydown", (event) => {
  if (!hasSvg()) return;
  const tag = (event.target && event.target.tagName) || "";
  if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
  if (event.key === "+" || event.key === "=") {
    event.preventDefault();
    zoomBy(ZOOM_STEP);
  } else if (event.key === "-" || event.key === "_") {
    event.preventDefault();
    zoomBy(1 / ZOOM_STEP);
  } else if (event.key === "0") {
    event.preventDefault();
    fitView();
  } else if (event.key === "f" || event.key === "F") {
    event.preventDefault();
    toggleFullscreen();
  } else if (event.key === "Escape") {
    clearPathHighlight();
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
