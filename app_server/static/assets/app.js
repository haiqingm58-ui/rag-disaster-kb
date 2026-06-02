const HOT_KEYWORDS = ["滑坡", "泥石流", "暴雨", "风险评估", "监测预警", "抗滑桩", "地震应急"];
const SEARCH_GROUPS = ["标准规范", "知识点", "灾害类型", "工程措施", "监测预警", "实时事件", "文档片段"];
const ADMIN_MESSAGE = "你需要登录管理员账号后才能使用此功能";
const USAGE_PATHS = [
  {title: "想了解灾害知识", target: "chat", action: "进入智能问答", text: "围绕滑坡、泥石流、洪水、监测预警等主题进行专业问答。"},
  {title: "想查标准条款", target: "standards", action: "进入标准库", text: "按标准编号或名称查找规范依据，再进入图谱查看相关条款。"},
  {title: "想看知识关系", target: "graph", action: "进入知识图谱", text: "按标准、节点类型、关系类型和灾害类型浏览结构化知识。"},
  {title: "想查近期灾害", target: "events", action: "进入灾害事件", text: "筛选洪水、山地滑坡等实时事件，查看时间、地点和坐标信息。"},
  {title: "想扩展知识库", target: "documents", action: "进入文档管理", text: "管理员上传 PDF、TXT、MD 文档，将内容解析、切分并入库。"},
];

const state = {
  token: localStorage.getItem("rag_access_token") || "",
  username: localStorage.getItem("rag_username") || "",
  sessionId: null,
  summary: null,
  standards: [],
  events: [],
  documents: [],
  diagnostics: null,
  graphResults: [],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function highlight(text, keyword) {
  const safe = escapeHtml(text || "");
  if (!keyword) return safe;
  const pattern = keyword.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return safe.replace(new RegExp(pattern, "gi"), (match) => `<mark>${match}</mark>`);
}

function hasToken() {
  return Boolean(state.token);
}

function authHeaders(required = false) {
  if (required && !hasToken()) {
    throw createAppError(401, ADMIN_MESSAGE);
  }
  return hasToken() ? {Authorization: `Bearer ${state.token}`} : {};
}

async function api(path, options = {}) {
  const headers = {
    Accept: "application/json",
    ...(options.body instanceof FormData ? {} : {"Content-Type": "application/json"}),
    ...authHeaders(Boolean(options.auth)),
    ...(options.headers || {}),
  };
  let response;
  try {
    response = await fetch(path, {
      method: options.method || "GET",
      headers,
      body: options.body instanceof FormData ? options.body : options.body ? JSON.stringify(options.body) : undefined,
    });
  } catch (error) {
    throw createAppError(0, "服务器连接失败，请稍后重试");
  }
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = {detail: text || "服务返回格式异常。"};
  }
  if (!response.ok) {
    if (response.status === 401 && options.auth) {
      clearAuthStorage();
      updateAuthState();
    }
    throw createAppError(response.status, data.detail);
  }
  return data;
}

function createAppError(status, detail) {
  const messageMap = {
    0: "服务器连接失败，请稍后重试",
    401: "登录已失效，请重新登录",
    429: "请求过于频繁，请稍后再试",
    500: "服务器处理失败，请查看日志",
  };
  const error = new Error(messageMap[status] || sanitizeErrorMessage(detail));
  error.status = status;
  return error;
}

function sanitizeErrorMessage(message) {
  const text = String(message || "请求处理失败，请稍后重试。");
  if (/traceback|stack|exception|internal server error/i.test(text)) {
    return "服务器处理失败，请查看日志";
  }
  return text.length > 160 ? `${text.slice(0, 160)}...` : text;
}

function toast(message) {
  const box = $("#toast");
  if (!box) return;
  box.textContent = sanitizeErrorMessage(message);
  box.classList.remove("hidden");
  clearTimeout(box._timer);
  box._timer = setTimeout(() => box.classList.add("hidden"), 3200);
}

function updateAuthState() {
  state.token = localStorage.getItem("rag_access_token") || "";
  state.username = localStorage.getItem("rag_username") || "";
  const userState = $("#userState");
  const loginLink = $("#loginLink");
  const logoutBtn = $("#logoutBtn");
  if (hasToken()) {
    userState.textContent = `管理员：${state.username || "admin"}`;
    loginLink.classList.add("hidden");
    logoutBtn.classList.remove("hidden");
  } else {
    userState.textContent = "游客";
    loginLink.classList.remove("hidden");
    logoutBtn.classList.add("hidden");
  }
  const authNotice = $("#authNotice");
  if (authNotice) authNotice.classList.toggle("hidden", hasToken());
  renderAdminGate("documentsGate");
  renderAdminGate("diagnosticsGate");
  renderAdminGate("eventsGate", true);
}

function clearAuthStorage() {
  localStorage.removeItem("rag_access_token");
  localStorage.removeItem("rag_token_expires_at");
  localStorage.removeItem("rag_username");
  localStorage.removeItem("rag_user_role");
  state.token = "";
  state.username = "";
}

function logout() {
  clearAuthStorage();
  updateAuthState();
  renderDocuments();
  renderOverview();
  window.location.href = "/";
}

function renderAdminGate(targetId, hideUntilNeeded = false) {
  const container = $(`#${targetId}`);
  if (!container) return;
  if (hasToken() || hideUntilNeeded) {
    container.classList.add("hidden");
    container.innerHTML = "";
    return;
  }
  container.classList.remove("hidden");
  container.innerHTML = `
    <strong>${ADMIN_MESSAGE}</strong>
    <p>登录后可以上传文档、删除文档、同步灾害数据和查看系统诊断。</p>
    <a class="secondary admin-login-link" href="/">去登录</a>
  `;
}

function showPage(name) {
  $$(".page").forEach((page) => page.classList.toggle("active", page.id === `page-${name}`));
  $$("#topNav button").forEach((button) => button.classList.toggle("active", button.dataset.page === name));
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  $("#topNav").classList.remove("open");

  if (name === "graph") loadGraphPage();
  if (name === "standards") loadStandards();
  if (name === "events") loadEvents();
  if (name === "documents") loadDocuments();
  if (name === "about") loadDiagnostics(false);
  if (name === "documents" || name === "about") updateAuthState();
}

function setupNavigation() {
  $("#navToggle")?.addEventListener("click", () => $("#topNav").classList.toggle("open"));
  $$("#topNav button").forEach((button) => button.addEventListener("click", () => showPage(button.dataset.page)));
  $$("[data-jump]").forEach((button) => button.addEventListener("click", () => showPage(button.dataset.jump)));
  $$("[data-nav-link]").forEach((link) => link.addEventListener("click", (event) => {
    event.preventDefault();
    showPage(link.dataset.navLink);
  }));
  window.addEventListener("hashchange", () => showPage((location.hash || "#home").slice(1)));
}

async function loadDashboard() {
  try {
    state.summary = await api("/api/graph/summary");
  } catch (error) {
    toast(error.message);
  }
  await loadEvents({silent: true, homeOnly: true});
  if (hasToken()) {
    await loadDocuments({silent: true});
  }
  renderOverview();
  renderHomeEvents();
}

function renderOverview() {
  const container = $("#overviewCards");
  if (!container) return;
  const summary = state.summary || {};
  const documentCount = hasToken() ? state.documents.length : "需登录";
  const cards = [
    ["标准数量", summary.standards ?? "-"],
    ["知识节点数量", summary.nodes ?? sumNodeCounts(summary)],
    ["关系数量", summary.relationships ?? "-"],
    ["灾害事件数量", state.events.length || "-"],
    ["文档数量", documentCount],
  ];
  container.innerHTML = cards.map(([label, value]) => `
    <article class="metric-card">
      <strong>${escapeHtml(value)}</strong>
      <span>${escapeHtml(label)}</span>
    </article>
  `).join("");
}

function renderUsagePaths() {
  const container = $("#usagePathCards");
  if (!container) return;
  container.innerHTML = USAGE_PATHS.map((item) => `
    <article class="usage-card">
      <span>${escapeHtml(item.title)}</span>
      <h3>${escapeHtml(item.action)}</h3>
      <p>${escapeHtml(item.text)}</p>
      <button class="ghost" type="button" data-jump="${escapeHtml(item.target)}">打开</button>
    </article>
  `).join("");
  container.querySelectorAll("[data-jump]").forEach((button) => {
    button.addEventListener("click", () => showPage(button.dataset.jump));
  });
}

function sumNodeCounts(summary) {
  return ["standards", "chapters", "clauses", "terms", "requirements", "indicators", "methods"]
    .reduce((total, key) => total + Number(summary[key] || 0), 0) || "-";
}

function renderHotKeywords() {
  const container = $("#hotKeywords");
  if (!container) return;
  container.innerHTML = HOT_KEYWORDS.map((word) => `<button type="button" data-keyword="${word}">${word}</button>`).join("");
  container.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      $("#homeSearchInput").value = button.dataset.keyword;
      performSearch(button.dataset.keyword);
    });
  });
}

function groupGraphItem(item) {
  const type = item.type || "";
  const text = `${item.title || ""} ${item.text || ""}`;
  if (type === "标准") return "标准规范";
  if (/抗滑桩|挡墙|排水|治理|加固|支护|工程/.test(text)) return "工程措施";
  if (/监测|预警|雨量|位移|阈值|指标/.test(text)) return "监测预警";
  if (/滑坡|泥石流|崩塌|洪水|暴雨|地震/.test(text)) return "灾害类型";
  return "知识点";
}

async function performSearch(query) {
  const keyword = (query || "").trim();
  const output = $("#searchResults");
  if (!keyword || !output) return;
  output.innerHTML = '<div class="loading">正在检索知识图谱、实时事件和文档索引...</div>';
  const grouped = Object.fromEntries(SEARCH_GROUPS.map((name) => [name, []]));

  try {
    const graphItems = await api(`/api/graph/search?q=${encodeURIComponent(keyword)}&limit=60`);
    graphItems.forEach((item) => {
      grouped[groupGraphItem(item)].push({
        title: item.title || item.text?.slice(0, 40) || "知识点",
        type: item.type || "知识点",
        source: item.code || "知识图谱",
        summary: item.text || item.title || "",
        nodeId: item.node_id,
      });
    });
  } catch (error) {
    grouped["知识点"].push({title: "知识图谱检索失败", type: "错误", source: "系统", summary: error.message});
  }

  try {
    const events = await api(`/api/disasters/events?days=365&focus=true`);
    (events.events || [])
      .filter((event) => eventMatchesKeyword(event, keyword))
      .slice(0, 12)
      .forEach((event) => grouped["实时事件"].push({
        title: event.title || event.event_type || "灾害事件",
        type: event.event_type || "事件",
        source: event.source || "实时数据",
        summary: `${event.time || ""} ${event.place || ""} ${event.risk || ""}`,
      }));
  } catch (error) {
    grouped["实时事件"].push({title: "实时事件检索失败", type: "错误", source: "系统", summary: error.message});
  }

  if (hasToken()) {
    try {
      const docs = state.documents.length ? state.documents : await api("/api/documents", {auth: true});
      docs
        .filter((doc) => `${doc.name} ${doc.source}`.includes(keyword))
        .forEach((doc) => grouped["文档片段"].push({
          title: doc.name,
          type: "文档",
          source: doc.source,
          summary: `已入库切片 ${doc.chunks || 0} 个`,
        }));
    } catch (error) {
      grouped["文档片段"].push({title: "文档索引不可用", type: "提示", source: "登录态", summary: error.message});
    }
  }

  renderGroupedResults(grouped, keyword);
}

function eventMatchesKeyword(event, keyword) {
  const text = `${event.title || ""} ${event.event_type || ""} ${event.event_type_group || ""} ${event.place || ""} ${event.source_note || ""}`;
  const aliases = keyword === "暴雨" ? ["暴雨", "flood", "flash flood"] : [keyword];
  return aliases.some((word) => text.toLowerCase().includes(word.toLowerCase()));
}

function renderGroupedResults(grouped, keyword) {
  const output = $("#searchResults");
  const sections = SEARCH_GROUPS.map((groupName) => {
    const items = grouped[groupName] || [];
    if (!items.length) return "";
    return `
      <section class="result-group">
        <h3>${groupName}<span>${items.length}</span></h3>
        ${items.map((item) => `
          <article class="result-item" ${item.nodeId ? `data-node-id="${escapeHtml(item.nodeId)}"` : ""}>
            <div>
              <strong>${highlight(item.title, keyword)}</strong>
              <span class="type-tag">${escapeHtml(item.type)}</span>
            </div>
            <small>${escapeHtml(item.source || "未知来源")}</small>
            <p>${highlight(item.summary || "", keyword)}</p>
          </article>
        `).join("")}
      </section>
    `;
  }).join("");
  output.innerHTML = sections || '<div class="empty-state">没有找到匹配结果，请换一个关键词。</div>';
  output.querySelectorAll("[data-node-id]").forEach((item) => {
    item.addEventListener("click", () => {
      showPage("graph");
      loadNodeDetail(item.dataset.nodeId);
    });
  });
}

async function loadStandards() {
  if (!state.standards.length) {
    try {
      state.standards = await api("/api/graph/standards");
      fillStandardFilter();
    } catch (error) {
      toast(error.message);
    }
  }
  renderStandards();
}

function fillStandardFilter() {
  const select = $("#graphStandardFilter");
  if (!select) return;
  const current = select.value;
  select.innerHTML = '<option value="">全部标准</option>' + state.standards.map((standard) => {
    const code = standard.code || standard.standard_id || "";
    const label = `${code} ${standard.name || standard.title || ""}`.trim();
    return `<option value="${escapeHtml(code)}">${escapeHtml(label)}</option>`;
  }).join("");
  select.value = current;
}

function renderStandards() {
  const container = $("#standardsList");
  if (!container) return;
  const keyword = ($("#standardSearchInput")?.value || "").trim();
  const items = state.standards.filter((standard) => {
    const text = `${standard.code || ""} ${standard.name || ""} ${standard.title || ""}`;
    return !keyword || text.includes(keyword);
  });
  container.innerHTML = items.map((standard) => `
    <article class="standard-card">
      <span class="type-tag">标准规范</span>
      <h3>${escapeHtml(standard.name || standard.title || "未命名标准")}</h3>
      <p>${escapeHtml(standard.code || standard.standard_id || "")}</p>
      <button class="ghost" type="button" data-standard-code="${escapeHtml(standard.code || "")}">查看相关条款</button>
    </article>
  `).join("") || '<div class="empty-state">暂无标准数据。</div>';
  container.querySelectorAll("[data-standard-code]").forEach((button) => {
    button.addEventListener("click", () => {
      showPage("graph");
      $("#graphStandardFilter").value = button.dataset.standardCode;
      searchGraphNodes();
    });
  });
}

async function loadGraphPage() {
  await loadStandards();
  if (!state.graphResults.length) {
    await searchGraphNodes();
  }
}

function selectedRelationTypeToNodeType(relationType) {
  return {
    DEFINES: "术语",
    HAS_REQUIREMENT: "要求",
    HAS_INDICATOR: "指标",
    USES_METHOD: "方法",
  }[relationType] || "";
}

async function searchGraphNodes() {
  const query = ($("#graphSearchInput")?.value || $("#graphDisasterFilter")?.value || "滑坡").trim();
  const standard = $("#graphStandardFilter")?.value || "";
  const type = $("#graphTypeFilter")?.value || selectedRelationTypeToNodeType($("#graphRelationFilter")?.value || "");
  const disaster = $("#graphDisasterFilter")?.value || "";
  const container = $("#graphNodes");
  if (!container) return;
  container.innerHTML = '<div class="loading">正在加载图谱节点...</div>';
  try {
    const items = await api(`/api/graph/search?q=${encodeURIComponent(query || disaster || "灾害")}&limit=80`);
    state.graphResults = items.filter((item) => {
      const text = `${item.title || ""} ${item.text || ""}`;
      if (standard && item.code !== standard) return false;
      if (type && item.type !== type) return false;
      if (disaster && !text.includes(disaster)) return false;
      return true;
    });
    renderGraphNodes();
  } catch (error) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderGraphNodes() {
  const container = $("#graphNodes");
  container.innerHTML = state.graphResults.map((item) => `
    <button class="node-card ${nodeClass(item.type)}" type="button" data-node-id="${escapeHtml(item.node_id || "")}">
      <span>${escapeHtml(item.type || "节点")}</span>
      <strong>${escapeHtml(item.title || item.text?.slice(0, 36) || "未命名节点")}</strong>
      <small>${escapeHtml(item.code || "知识图谱")}</small>
    </button>
  `).join("") || '<div class="empty-state">没有匹配的图谱节点。</div>';
  container.querySelectorAll(".node-card").forEach((button, index) => {
    button.addEventListener("click", () => {
      if (button.dataset.nodeId) loadNodeDetail(button.dataset.nodeId);
      else renderNodeDetail({node: state.graphResults[index], relations: []});
    });
  });
}

function nodeClass(type) {
  return {
    标准: "standard",
    条款: "clause",
    术语: "term",
    方法: "method",
    指标: "indicator",
  }[type] || "default";
}

async function loadNodeDetail(nodeId) {
  const container = $("#nodeDetail");
  if (!container) return;
  container.innerHTML = '<div class="loading">正在加载节点详情...</div>';
  try {
    const detail = await api(`/api/graph/node/${encodeURIComponent(nodeId)}`);
    renderNodeDetail(detail);
  } catch (error) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderNodeDetail(detail) {
  const node = detail.node || {};
  const relations = detail.relations || [];
  const title = node.title || node.name || node.term || node.text || node.number || "未命名节点";
  const type = node.type || node.collection || "知识节点";
  const clause = node.clause_number || node.number || "";
  const related = relations.map((relation) => {
    const target = relation.target || {};
    return `<li><span>${escapeHtml(relation.type)}</span>${escapeHtml(target.title || target.name || target.term || target.code || target.id || "相邻节点")}</li>`;
  }).join("");
  $("#nodeDetail").innerHTML = `
    <article class="detail-card">
      <span class="type-tag">${escapeHtml(type)}</span>
      <h3>${escapeHtml(title)}</h3>
      <dl>
        <dt>来源标准</dt><dd>${escapeHtml(node.code || "暂无")}</dd>
        <dt>相关条款</dt><dd>${escapeHtml(clause || "暂无")}</dd>
        <dt>相关知识点</dt><dd>${escapeHtml(node.content || node.text || node.description || "暂无摘要")}</dd>
      </dl>
      <h4>相邻节点</h4>
      <ul class="relation-list">${related || "<li>暂无相邻节点</li>"}</ul>
      <button id="askNodeBtn" class="primary" type="button">一键向 AI 提问该节点</button>
    </article>
  `;
  $("#askNodeBtn").addEventListener("click", () => {
    showPage("chat");
    $("#question").value = `请结合标准和知识图谱解释“${title}”，并说明它与地质灾害风险防控的关系。`;
    $("#chatForm").requestSubmit();
  });
}

async function loadEvents(options = {}) {
  const type = $("#eventTypeFilter")?.value || "";
  const days = $("#eventDaysFilter")?.value || "365";
  const source = $("#eventSourceFilter")?.value || "";
  const radius = $("#eventRadiusFilter")?.value || "";
  const lat = $("#eventLatInput")?.value || "";
  const lon = $("#eventLonInput")?.value || "";
  const params = new URLSearchParams({days, focus: "true"});
  if (type) params.set("type", type);
  if (source) params.set("source", source);
  if (radius && lat && lon) {
    params.set("radius_km", radius);
    params.set("lat", lat);
    params.set("lon", lon);
  }
  try {
    const data = await api(`/api/disasters/events?${params.toString()}`);
    state.events = data.events || [];
    renderOverview();
    renderHomeEvents();
    if (!options.homeOnly) renderEvents();
  } catch (error) {
    if (!options.silent) toast(error.message);
  }
}

function renderHomeEvents() {
  const container = $("#homeEvents");
  if (!container) return;
  container.innerHTML = state.events.slice(0, 5).map((event) => `
    <article>
      <strong>${escapeHtml(event.title || event.event_type || "灾害事件")}</strong>
      <span>${escapeHtml(event.time || "时间未知")} · ${escapeHtml(event.place || "地点未知")}</span>
    </article>
  `).join("") || '<div class="empty-state">暂无洪水或滑坡事件。</div>';
}

function renderEvents() {
  const container = $("#eventList");
  if (!container) return;
  window.GeoRiskMap?.renderPlaceholder($("#eventMap"), state.events);
  container.innerHTML = state.events.map((event) => `
    <article class="event-card">
      <div>
        <span class="type-tag">${escapeHtml(event.event_type || event.event_type_group || "事件")}</span>
        <h3>${escapeHtml(event.title || event.place || "灾害事件")}</h3>
        <p>${escapeHtml(event.time || "时间未知")} · ${escapeHtml(event.place || "地点未知")}</p>
      </div>
      <dl>
        <dt>经纬度</dt><dd>${escapeHtml(formatCoord(event.latitude, event.longitude))}</dd>
        <dt>风险等级</dt><dd>${escapeHtml(event.risk || "未知")}</dd>
        <dt>来源</dt><dd>${escapeHtml(event.source || "未知")}</dd>
        <dt>距离</dt><dd>${escapeHtml(event.distance_km ? `${event.distance_km} km` : "未计算")}</dd>
      </dl>
    </article>
  `).join("") || '<div class="empty-state">当前筛选条件下没有事件。</div>';
}

function formatCoord(lat, lon) {
  if (lat === null || lat === undefined || lon === null || lon === undefined) return "暂无坐标";
  return `${Number(lat).toFixed(3)}, ${Number(lon).toFixed(3)}`;
}

async function syncEvents() {
  if (!hasToken()) {
    renderAdminGate("eventsGate");
    toast(ADMIN_MESSAGE);
    return;
  }
  try {
    const data = await api("/api/disasters/sync", {method: "POST", auth: true});
    toast(`同步完成：${data.count || 0} 条事件。`);
    await loadEvents();
  } catch (error) {
    toast(error.message);
  }
}

function appendMessage(role, content, options = {}) {
  const messages = $("#messages");
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.innerHTML = `
    <div class="message-meta">${role === "user" ? "用户提问" : "知识库回答"}</div>
    <div class="message-content">${escapeHtml(content).replaceAll("\n", "<br>")}</div>
    ${role === "assistant" && !options.loading ? '<button class="copy-answer" type="button">复制回答</button>' : ""}
  `;
  if (role === "assistant" && !options.loading) {
    article.querySelector(".copy-answer").addEventListener("click", async () => {
      await navigator.clipboard.writeText(content);
      toast("回答已复制。");
    });
  }
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
  return article;
}

async function sendQuestion(event) {
  event.preventDefault();
  const input = $("#question");
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  appendMessage("user", question);
  const loading = appendMessage("assistant", "正在检索文档、知识图谱和实时灾害事件...", {loading: true});
  try {
    const data = await api("/api/chat", {
      method: "POST",
      body: {question, session_id: state.sessionId, use_graph: true, use_realtime: true, top_k: 6},
    });
    state.sessionId = data.debug?.session_id || state.sessionId;
    loading.remove();
    appendMessage("assistant", data.answer || "当前知识库中没有找到足够依据。");
    renderRetrievalSummary(data);
    renderSources(data.sources || []);
    renderRelatedQuestions(question, data.sources || []);
  } catch (error) {
    loading.remove();
    appendMessage("assistant", error.message);
  }
}

function renderSources(sources) {
  const container = $("#sources");
  if (!container) return;
  const grouped = groupSources(sources);
  const sections = [
    ["标准条款", grouped.standard],
    ["图谱节点", grouped.graph],
    ["文档片段", grouped.document],
  ].map(([title, items]) => {
    if (!items.length) return "";
    return `
      <section class="source-group">
        <h4>${title}<span>${items.length}</span></h4>
        ${items.map((source, index) => `
          <details class="source-card" ${index === 0 ? "open" : ""}>
            <summary>
              <span class="type-tag">${escapeHtml(sourceLabel(source))}</span>
              <strong>${escapeHtml(source.title || source.source || "参考来源")}</strong>
            </summary>
            <small>${escapeHtml(sourceMeta(source))}</small>
            <p>${escapeHtml(source.snippet || source.content || "")}</p>
          </details>
        `).join("")}
      </section>
    `;
  }).join("");
  container.innerHTML = sections || '<div class="empty-state">当前知识库中没有找到足够依据。</div>';
}

function groupSources(sources) {
  return (sources || []).reduce((groups, source) => {
    if (source.type === "document") groups.document.push(source);
    else if (source.standard || source.clause) groups.standard.push(source);
    else groups.graph.push(source);
    return groups;
  }, {standard: [], graph: [], document: []});
}

function sourceLabel(source) {
  if (source.type === "document") return "文档片段";
  if (source.standard || source.clause) return "标准条款";
  if (source.type === "graph") return "图谱节点";
  if (source.type === "realtime") return "实时事件";
  return source.type || "来源";
}

function sourceMeta(source) {
  if (source.type === "document") return source.source || source.title || "本地文档";
  return [source.standard, source.clause].filter(Boolean).join(" · ") || source.source || "知识图谱";
}

function renderRetrievalSummary(data) {
  const container = $("#retrievalSummary");
  if (!container) return;
  const sources = data.sources || [];
  const standardCount = new Set(sources.map((source) => source.standard).filter(Boolean)).size;
  const graphCount = Number(data.debug?.graph_count || data.graph_context?.length || 0);
  const documentCount = Number(data.debug?.retrieval_count || sources.filter((source) => source.type === "document").length || 0);
  const evidenceCount = sources.length;
  const llmUsage = data.debug?.llm_usage || {};
  const llmErrors = data.debug?.errors || [];
  const isAiMode = Boolean(llmUsage.total_tokens || llmUsage.usage_source === "api") && !llmErrors.some((item) => String(item).includes("生成模型不可用"));
  const modeText = isAiMode ? "AI 生成模式" : "检索证据摘要模式";
  container.innerHTML = `
    <div class="retrieval-mode ${isAiMode ? "ai" : "fallback"}">${modeText}</div>
    <div class="summary-grid">
      <div><strong>${evidenceCount}</strong><span>证据数量</span></div>
      <div><strong>${standardCount}</strong><span>命中标准</span></div>
      <div><strong>${graphCount}</strong><span>图谱节点</span></div>
      <div><strong>${documentCount}</strong><span>文档片段</span></div>
    </div>
    <p>${isAiMode ? "回答由大模型结合检索证据生成。" : "当前未检测到可用大模型调用结果，页面展示基于检索证据的摘要。"}</p>
  `;
}

function renderRelatedQuestions(question, sources) {
  const container = $("#relatedQuestions");
  if (!container) return;
  const disaster = HOT_KEYWORDS.find((word) => question.includes(word)) || "滑坡";
  const standard = sources.find((source) => source.standard)?.standard || "相关标准";
  const questions = [
    `${disaster}风险评估需要关注哪些指标？`,
    `${standard}中有哪些监测预警要求？`,
    `针对${disaster}有哪些工程治理措施？`,
  ];
  container.innerHTML = questions.map((item) => `<button type="button">${escapeHtml(item)}</button>`).join("");
  container.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      $("#question").value = button.textContent;
      $("#chatForm").requestSubmit();
    });
  });
}

async function loadDocuments(options = {}) {
  if (!hasToken()) {
    state.documents = [];
    renderDocuments();
    renderRagStatus();
    renderOverview();
    return;
  }
  try {
    state.documents = await api("/api/documents", {auth: true});
    await loadDiagnostics(false);
    renderDocuments();
    renderRagStatus();
    renderOverview();
  } catch (error) {
    renderDocuments();
    if (!options.silent) toast(error.message);
  }
}

function renderDocuments() {
  const container = $("#docList");
  if (!container) return;
  if (!hasToken()) {
    container.innerHTML = `<div class="empty-state">${ADMIN_MESSAGE}</div>`;
    return;
  }
  container.innerHTML = state.documents.map((doc) => `
    <article class="doc-row">
      <div>
        <strong>${escapeHtml(doc.name || "未命名文档")}</strong>
        <span>${escapeHtml(fileType(doc.name))} · 已入库 · ${escapeHtml(doc.chunks || 0)} 个切片</span>
        <small>${escapeHtml(doc.source || "")}</small>
      </div>
      <button class="danger" type="button" data-source="${escapeHtml(doc.source)}">删除</button>
    </article>
  `).join("") || '<div class="empty-state">暂无上传文档。</div>';
  container.querySelectorAll("[data-source]").forEach((button) => {
    button.addEventListener("click", () => deleteDocument(button.dataset.source));
  });
}

function renderRagStatus() {
  const container = $("#ragStatusCards");
  if (!container) return;
  if (!hasToken()) {
    container.innerHTML = "";
    return;
  }
  const diagnostics = state.diagnostics || {};
  const config = diagnostics.config || {};
  const paths = diagnostics.paths || {};
  const chunks = state.documents.reduce((total, doc) => total + Number(doc.chunks || 0), 0);
  const ready = Boolean(config.embedding_ready && paths.chroma_dir);
  const checkedAt = new Date().toLocaleString("zh-CN", {hour12: false});
  const cards = [
    ["文档库名称", "local_docs / Chroma"],
    ["chunks 数量", chunks],
    ["索引状态", ready ? "可用" : "需检查"],
    ["最近检查时间", checkedAt],
    ["可用于问答", ready && chunks > 0 ? "是" : "否"],
  ];
  container.innerHTML = cards.map(([label, value]) => `
    <article class="rag-status-card">
      <strong>${escapeHtml(value)}</strong>
      <span>${escapeHtml(label)}</span>
    </article>
  `).join("");
}

function fileType(name = "") {
  const ext = name.split(".").pop()?.toUpperCase() || "FILE";
  return ext;
}

function setUploadStep(activeStep, doneSteps = []) {
  $$("#uploadSteps [data-step]").forEach((step) => {
    step.classList.toggle("active", step.dataset.step === activeStep);
    step.classList.toggle("done", doneSteps.includes(step.dataset.step));
  });
}

async function uploadDocument() {
  const file = $("#fileInput").files?.[0];
  const stateText = $("#uploadState");
  if (!hasToken()) {
    renderAdminGate("documentsGate");
    toast(ADMIN_MESSAGE);
    return;
  }
  if (!file) {
    stateText.textContent = "请先选择文件。";
    setUploadStep("select");
    return;
  }
  const allowed = [".pdf", ".txt", ".md"];
  const suffix = `.${file.name.split(".").pop()?.toLowerCase()}`;
  if (!allowed.includes(suffix)) {
    stateText.textContent = "文件类型不支持，仅允许 PDF、TXT、MD。";
    return;
  }
  if (file.size > 30 * 1024 * 1024) {
    stateText.textContent = "文件过大，默认限制为 30MB。";
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  try {
    setUploadStep("upload", ["select"]);
    stateText.textContent = "正在上传文件...";
    const result = await api("/api/documents/upload", {method: "POST", body: formData, auth: true});
    setUploadStep("store", ["select", "upload", "parse", "split", "vector"]);
    stateText.textContent = `入库完成：${result.filename}，切片 ${result.chunk_count} 个。`;
    await loadDocuments();
  } catch (error) {
    stateText.textContent = error.message;
    setUploadStep("select");
  }
}

async function deleteDocument(source) {
  if (!source) return;
  try {
    const data = await api(`/api/documents?source=${encodeURIComponent(source)}`, {method: "DELETE", auth: true});
    toast(`已删除 ${data.deleted_chunks || 0} 个切片。`);
    await loadDocuments();
  } catch (error) {
    toast(error.message);
  }
}

async function rebuildIndex() {
  if (!hasToken()) {
    renderAdminGate("documentsGate");
    toast(ADMIN_MESSAGE);
    return;
  }
  try {
    const data = await api("/api/documents/rebuild-index", {method: "POST", auth: true});
    toast(data.message || "索引状态检查完成。");
    await loadDocuments();
  } catch (error) {
    toast(error.message);
  }
}

async function loadDiagnostics(showToast = true) {
  const container = $("#diagnosticsContent");
  if (!container) return;
  if (!hasToken()) {
    container.textContent = ADMIN_MESSAGE;
    renderAdminGate("diagnosticsGate");
    return;
  }
  try {
    const data = await api("/api/diagnostics", {auth: true});
    state.diagnostics = data;
    container.textContent = JSON.stringify(data, null, 2);
    renderRagStatus();
    if (showToast) toast("诊断信息已更新。");
  } catch (error) {
    container.textContent = sanitizeErrorMessage(error.message);
  }
}

function bindForms() {
  $("#homeSearchForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    performSearch($("#homeSearchInput").value);
  });
  $("#graphSearchForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    searchGraphNodes();
  });
  ["graphStandardFilter", "graphTypeFilter", "graphRelationFilter", "graphDisasterFilter"].forEach((id) => {
    $(`#${id}`)?.addEventListener("change", searchGraphNodes);
  });
  $("#standardSearchForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    renderStandards();
  });
  ["eventTypeFilter", "eventDaysFilter", "eventRadiusFilter", "eventSourceFilter", "eventLatInput", "eventLonInput"].forEach((id) => {
    $(`#${id}`)?.addEventListener("change", () => loadEvents());
  });
  $("#chatForm")?.addEventListener("submit", sendQuestion);
  $("#newChat")?.addEventListener("click", () => {
    state.sessionId = null;
    $("#messages").innerHTML = "";
    $("#sources").innerHTML = "";
    $("#relatedQuestions").innerHTML = "";
    $("#retrievalSummary").innerHTML = '<div class="empty-state">发送问题后显示本次检索过程。</div>';
  });
  $("#uploadBtn")?.addEventListener("click", uploadDocument);
  $("#refreshDocsBtn")?.addEventListener("click", () => loadDocuments());
  $("#rebuildIndexBtn")?.addEventListener("click", rebuildIndex);
  $("#diagnosticsBtn")?.addEventListener("click", () => loadDiagnostics(true));
  $("#syncEventsBtn")?.addEventListener("click", syncEvents);
  $("#logoutBtn")?.addEventListener("click", logout);
  $("#fileInput")?.addEventListener("change", () => setUploadStep("select"));
}

function init() {
  setupNavigation();
  bindForms();
  updateAuthState();
  renderHotKeywords();
  renderUsagePaths();
  window.GeoRiskMap?.renderPlaceholder($("#eventMap"), state.events);
  appendMessage("assistant", "您好，我可以基于地质灾害标准、知识图谱、已上传文档和实时灾害事件回答问题。回答会尽量给出参考来源。");
  showPage((location.hash || "#home").slice(1));
  loadDashboard();
  performSearch("滑坡");
}

document.addEventListener("DOMContentLoaded", init);
