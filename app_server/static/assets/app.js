let sessionId = crypto.randomUUID();
let lastTab = "overview";

const $ = (id) => document.getElementById(id);
const card = (title, body) => `<div class="mini-card"><strong>${escapeHtml(title || "未命名")}</strong>${escapeHtml(body || "")}</div>`;

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

function renderMarkdown(text) {
  let html = escapeHtml(text || "");
  html = html.replace(/^### (.*)$/gm, "<h4>$1</h4>");
  html = html.replace(/^## (.*)$/gm, "<h3>$1</h3>");
  html = html.replace(/^# (.*)$/gm, "<h2>$1</h2>");
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  html = html.replace(/^- (.*)$/gm, "<li>$1</li>");
  html = html.replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>");
  return html.replace(/\n/g, "<br>");
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let message = await res.text();
    try {
      const data = JSON.parse(message);
      message = data.detail || message;
    } catch {}
    throw new Error(message);
  }
  return res.json();
}

function addMessage(role, text) {
  const el = document.createElement("div");
  el.className = `bubble ${role}`;
  el.innerHTML = role === "ai" ? renderMarkdown(text) : escapeHtml(text);
  $("messages").appendChild(el);
  $("messages").scrollTop = $("messages").scrollHeight;
  return el;
}

async function loadHealth() {
  try {
    const h = await api("/api/health");
    $("statusTags").innerHTML = [
      `FastAPI ${h.status}`,
      `DeepSeek ${h.llm_provider === "deepseek" ? "已配置模式" : h.llm_provider}`,
      `Embedding ${h.embedding_ready ? "就绪" : "需配置"}`,
      `Chroma ${h.chroma_ready ? "就绪" : "异常"}`,
      `知识图谱 ${h.graph_ready ? "就绪" : "缺失"}`,
      `实时数据 API`,
    ].map((x) => `<span class="tag ${h.status === "degraded" ? "tag-warn" : ""}">${x}</span>`).join("");
  } catch {
    $("statusTags").innerHTML = `<span class="tag">服务状态未知</span>`;
  }
}

function boolText(value) {
  return value ? "正常" : "异常";
}

function listItems(items) {
  return (items || []).length ? `<ul>${items.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : "<p>暂无</p>";
}

async function showDiagnostics() {
  $("diagnosticsPanel").classList.remove("hidden");
  $("diagnosticsContent").innerHTML = `<div class="mini-card">正在读取系统诊断信息...</div>`;
  try {
    const data = await api("/api/diagnostics");
    const paths = data.paths || {};
    $("diagnosticsContent").innerHTML = `
      <article class="diagnostic-card"><h3>应用状态</h3><p>${escapeHtml(data.status)} · ${escapeHtml(data.app.env)} · v${escapeHtml(data.app.version)}</p><p>运行 ${data.app.uptime_seconds}s</p></article>
      <article class="diagnostic-card"><h3>LLM 状态</h3><p>${escapeHtml(data.config.llm_provider)}</p></article>
      <article class="diagnostic-card"><h3>Embedding 状态</h3><p>${escapeHtml(data.config.embedding_provider)} · ${data.config.embedding_ready ? "就绪" : "需配置"}</p><p>${escapeHtml(data.config.embedding_model || "")}</p></article>
      <article class="diagnostic-card"><h3>Chroma 状态</h3><p>${boolText(paths.chroma_dir)}</p></article>
      <article class="diagnostic-card"><h3>图谱数据</h3><p>graph_data: ${boolText(paths.graph_data)}</p><p>search_index: ${boolText(paths.search_index)}</p></article>
      <article class="diagnostic-card"><h3>数据目录</h3><p>data: ${boolText(paths.data_dir)}</p><p>cache: ${boolText(paths.cache_dir)}</p><p>logs: ${boolText(paths.logs_dir)}</p></article>
      <article class="diagnostic-card wide"><h3>最近错误</h3>${listItems(data.recent_errors)}</article>
      <article class="diagnostic-card wide"><h3>部署建议</h3>${listItems(data.recommendations)}</article>`;
  } catch (err) {
    $("diagnosticsContent").innerHTML = `<div class="diagnostic-card error-card">诊断信息读取失败：${escapeHtml(err.message)}</div>`;
  }
}

async function loadDocuments() {
  try {
    const docs = await api("/api/documents");
    $("docList").innerHTML = docs.length
      ? docs.map((d) => card(d.name, `${d.chunks} 个切片`)).join("")
      : `<div class="hint">暂无文档或 Chroma 未启动。</div>`;
  } catch (err) {
    $("docList").innerHTML = `<div class="hint">${escapeHtml(err.message)}</div>`;
  }
}

async function sendQuestion(question) {
  addMessage("user", question);
  const ai = addMessage("ai", "正在检索文档、图谱和实时灾害数据...");
  ai.classList.add("loading");
  try {
    const data = await api("/api/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question, session_id: sessionId, use_graph: true, use_realtime: true, top_k: 5}),
    });
    sessionId = data.debug.session_id || sessionId;
    ai.classList.remove("loading");
    ai.innerHTML = renderMarkdown(data.answer);
    $("sources").innerHTML = data.sources.map((s) => card(`${s.type} · ${s.title}`, s.content)).join("") || `<div class="hint">暂无来源</div>`;
    $("graphContext").innerHTML = data.graph_context.map((g) => `<button class="mini-card node-card" data-node-id="${escapeHtml(g.node_id || "")}"><strong>${escapeHtml(g.type)} · ${escapeHtml(g.label)}</strong>${escapeHtml(g.content || "")}</button>`).join("") || `<div class="hint">暂无图谱节点</div>`;
    bindNodeCards();
    $("events").innerHTML = data.realtime_events.map((e) => card(`${e.source} · ${e.title}`, `${e.time || ""} ${e.place || ""} ${e.risk || ""}`)).join("") || `<div class="hint">暂无实时事件</div>`;
    $("debugInfo").textContent = JSON.stringify(data.debug, null, 2);
  } catch (err) {
    ai.classList.remove("loading");
    ai.classList.add("error");
    ai.textContent = `请求失败：${err.message}`;
  }
}

async function uploadDocument() {
  const file = $("fileInput").files[0];
  if (!file) return;
  $("uploadState").textContent = "正在上传并写入向量库...";
  const body = new FormData();
  body.append("file", file);
  try {
    const result = await api("/api/documents/upload", {method: "POST", body});
    $("uploadState").textContent = `已入库：${result.filename}，${result.chunk_count} 个切片。`;
    loadDocuments();
  } catch (err) {
    $("uploadState").textContent = `上传失败：${err.message}`;
  }
}

async function renderOverview() {
  const [summary, standards] = await Promise.all([api("/api/graph/summary"), api("/api/graph/standards")]);
  $("tabContent").innerHTML = `
    <div class="hint">标准 ${summary.standards}，章节 ${summary.chapters}，条款 ${summary.clauses}，术语 ${summary.terms}，要求 ${summary.requirements}，指标 ${summary.indicators}，方法 ${summary.methods}</div>
    <div class="grid">${standards.map((s) => `
      <article class="std-card">
        <h3>${escapeHtml(s.title)}</h3>
        <p>${escapeHtml(s.code)} · 条款 ${s.clauses || 0} · 术语 ${s.terms || 0} · 指标 ${s.indicators || 0}</p>
      </article>`).join("")}</div>`;
}

function groupByType(results) {
  return results.reduce((acc, item) => {
    const key = item.type || "其他";
    acc[key] = acc[key] || [];
    acc[key].push(item);
    return acc;
  }, {});
}

async function showNodeDetail(nodeId) {
  if (!nodeId) return;
  try {
    const detail = await api(`/api/graph/node/${encodeURIComponent(nodeId)}`);
    const node = detail.node || {};
    $("graphContext").innerHTML = `
      <div class="mini-card">
        <strong>${escapeHtml(node.collection || "节点")} · ${escapeHtml(node.title || node.name || node.number || node.id)}</strong>
        ${escapeHtml(node.content || node.definition || node.text || node.description || "")}
      </div>
      ${(detail.relations || []).map((rel) => card(rel.type, JSON.stringify(rel.target || {}, null, 2))).join("")}`;
    activateSideTab("graphContext");
  } catch (err) {
    $("graphContext").innerHTML = `<div class="mini-card error-card">节点详情加载失败：${escapeHtml(err.message)}</div>`;
  }
}

function bindNodeCards() {
  document.querySelectorAll("[data-node-id]").forEach((el) => {
    el.addEventListener("click", () => showNodeDetail(el.dataset.nodeId));
  });
}

function renderSearch() {
  $("tabContent").innerHTML = `
    <div class="searchbar"><input id="kgSearchInput" placeholder="搜索滑坡、稳定系数、勘查、应急等"><button id="kgSearchBtn">搜索</button></div>
    <div id="kgResults" class="grid"></div>`;
  $("kgSearchBtn").onclick = async () => {
    const q = $("kgSearchInput").value.trim();
    if (!q) return;
    const results = await api(`/api/graph/search?q=${encodeURIComponent(q)}&limit=30`);
    const grouped = groupByType(results);
    $("kgResults").innerHTML = Object.entries(grouped).map(([type, items]) => `
      <section class="result-group">
        <h3>${escapeHtml(type)} <span>${items.length}</span></h3>
        ${items.map((r) => `<button class="std-card node-card" data-node-id="${escapeHtml(r.node_id || "")}"><strong>${escapeHtml(r.title || r.text)}</strong><p>${escapeHtml(r.code)} ${escapeHtml(r.text)}</p></button>`).join("")}
      </section>`).join("") || `<div class="hint">没有找到相关知识点。</div>`;
    bindNodeCards();
  };
}

async function renderEvents() {
  const data = await api("/api/disasters/events?days=7");
  $("tabContent").innerHTML = `<div class="grid">${data.events.slice(0, 60).map((e) => `
    <article class="std-card"><h3>${escapeHtml(e.title)}</h3><p>${escapeHtml(e.source)} · ${escapeHtml(e.event_type)} · ${escapeHtml(e.time)} · ${escapeHtml(e.risk)}</p></article>`).join("")}</div>`;
}

async function switchTab(tab) {
  lastTab = tab;
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  if (tab === "overview") await renderOverview();
  if (tab === "search") renderSearch();
  if (tab === "events") await renderEvents();
}

$("chatForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const question = $("question").value.trim();
  if (!question) return;
  $("question").value = "";
  sendQuestion(question);
});
$("uploadBtn").addEventListener("click", uploadDocument);
$("newChat").addEventListener("click", () => {
  sessionId = crypto.randomUUID();
  $("messages").innerHTML = "";
  $("sources").innerHTML = "";
  $("graphContext").innerHTML = "";
  $("events").innerHTML = "";
  $("debugInfo").textContent = "{}";
});
$("diagnosticsBtn").addEventListener("click", showDiagnostics);
$("closeDiagnostics").addEventListener("click", () => $("diagnosticsPanel").classList.add("hidden"));
document.querySelectorAll(".tabs button").forEach((button) => button.addEventListener("click", () => switchTab(button.dataset.tab)));
function activateSideTab(tabName) {
  document.querySelectorAll(".side-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.sideTab === tabName));
  document.querySelectorAll(".side-pane").forEach((pane) => pane.classList.remove("active"));
  $(`${tabName}Pane`).classList.add("active");
}
document.querySelectorAll(".side-tabs button").forEach((button) => button.addEventListener("click", () => activateSideTab(button.dataset.sideTab)));

loadHealth();
loadDocuments();
switchTab(lastTab);
