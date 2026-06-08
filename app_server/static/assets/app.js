const HOT_KEYWORDS = ["滑坡", "泥石流", "暴雨", "风险评估", "监测预警", "抗滑桩", "地震应急"];
const SEARCH_GROUPS = ["标准规范", "知识点", "灾害类型", "工程措施", "监测预警", "实时事件", "文档片段"];
const HOME_SEARCH_PAGE_SIZE = 4;
const OFFICIAL_SOURCE_IDS = new Set([
  "hunan_natural_resource",
  "cma_warning",
  "hunan_water",
  "changsha_water",
  "changsha_natural_resource",
]);
const ADMIN_MESSAGE = "你需要登录管理员账号后才能使用此功能";
const PUBLIC_PAGES = new Set(["home", "chat", "graph", "standards", "events", "about"]);
const USAGE_PATHS = [
  {title: "想了解灾害知识", target: "chat", text: "围绕滑坡、泥石流、洪水、监测预警等主题进行专业问答。"},
  {title: "想查标准条款", target: "standards", text: "按标准编号或名称查找规范依据，再进入图谱查看相关条款。"},
  {title: "想看知识关系", target: "graph", text: "按标准、节点类型、关系类型和灾害类型浏览结构化知识。"},
  {title: "想查近期灾害", target: "events", text: "筛选洪水、山地滑坡等实时事件，查看时间、地点和坐标信息。"},
];

function storageAccount() {
  const username = localStorage.getItem("rag_username") || "guest";
  return encodeURIComponent(username).replaceAll("%", "_");
}

function userStorageKey(name) {
  return `rag_${storageAccount()}_${name}`;
}

let accountSaveTimer = null;
let graphCanvasRuntime = null;

const state = {
  token: localStorage.getItem("rag_access_token") || "",
  username: localStorage.getItem("rag_username") || "",
  role: localStorage.getItem("rag_user_role") || "",
  sessionId: null,
  summary: null,
  standards: [],
  events: [],
  documents: [],
  graphResults: [],
  graphView: "overview",
  expandedStandardCode: "",
  homeSearch: {
    grouped: null,
    keyword: "",
    page: 1,
  },
  conversations: loadStoredConversations(),
  activeConversationId: localStorage.getItem(userStorageKey("active_conversation")) || "",
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

function loadStoredConversations() {
  try {
    const raw = localStorage.getItem(userStorageKey("conversations")) || localStorage.getItem("rag_conversations") || "[]";
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.slice(0, 30) : [];
  } catch {
    return [];
  }
}

function saveConversations() {
  localStorage.setItem(userStorageKey("conversations"), JSON.stringify(state.conversations.slice(0, 30)));
  if (state.activeConversationId) {
    localStorage.setItem(userStorageKey("active_conversation"), state.activeConversationId);
  } else {
    localStorage.removeItem(userStorageKey("active_conversation"));
  }
  queueAccountDataSave();
}

function accountDataPayload() {
  return {
    conversations: state.conversations.slice(0, 30),
    active_conversation_id: state.activeConversationId || null,
  };
}

function queueAccountDataSave() {
  if (!hasToken()) return;
  clearTimeout(accountSaveTimer);
  accountSaveTimer = setTimeout(() => {
    syncAccountData().catch(() => undefined);
  }, 500);
}

async function syncAccountData() {
  if (!hasToken()) return;
  await api("/api/user-data", {method: "PUT", auth: true, body: accountDataPayload()});
}

async function loadAccountData() {
  if (!hasToken()) return;
  try {
    const data = await api("/api/user-data", {auth: true});
    if (Array.isArray(data.conversations) && data.conversations.length) {
      state.conversations = data.conversations.slice(0, 30);
      state.activeConversationId = data.active_conversation_id || state.conversations[0]?.id || "";
      localStorage.setItem(userStorageKey("conversations"), JSON.stringify(state.conversations));
      if (state.activeConversationId) {
        localStorage.setItem(userStorageKey("active_conversation"), state.activeConversationId);
      }
    } else if (state.conversations.length) {
      await syncAccountData();
    }
  } catch {
    // Keep the browser-local account data available if server sync is temporarily unavailable.
  }
}

function createConversation(title = "新会话") {
  const conversation = {
    id: `conv-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    title,
    messages: [],
    sources: [],
    relatedQuestions: [],
    retrieval: null,
    sessionId: null,
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
  state.conversations.unshift(conversation);
  state.activeConversationId = conversation.id;
  saveConversations();
  renderConversationList();
  return conversation;
}

function getActiveConversation() {
  let conversation = state.conversations.find((item) => item.id === state.activeConversationId);
  if (!conversation) {
    conversation = createConversation();
  }
  return conversation;
}

function recordMessage(role, content) {
  const conversation = getActiveConversation();
  conversation.messages.push({role, content, time: Date.now()});
  conversation.updatedAt = Date.now();
  if (role === "user" && (!conversation.title || conversation.title === "新会话")) {
    conversation.title = content.length > 24 ? `${content.slice(0, 24)}...` : content;
  }
  state.conversations = [conversation, ...state.conversations.filter((item) => item.id !== conversation.id)].slice(0, 30);
  state.activeConversationId = conversation.id;
  saveConversations();
  renderConversationList();
}

function updateConversationArtifacts(data, question) {
  const conversation = getActiveConversation();
  conversation.sources = data.sources || [];
  conversation.relatedQuestions = buildRelatedQuestions(question, data.sources || []);
  conversation.retrieval = buildRetrievalSummaryModel(data);
  conversation.sessionId = state.sessionId || conversation.sessionId || null;
  conversation.updatedAt = Date.now();
  saveConversations();
  renderConversationList();
}

function clearChatPanels() {
  $("#messages").innerHTML = "";
  $("#sources").innerHTML = "";
  $("#relatedQuestions").innerHTML = "";
  $("#retrievalSummary").innerHTML = '<div class="empty-state">发送问题后显示本次检索过程。</div>';
}

function restoreConversation(conversationId) {
  const conversation = state.conversations.find((item) => item.id === conversationId);
  if (!conversation) return;
  state.activeConversationId = conversation.id;
  state.sessionId = conversation.sessionId || null;
  localStorage.setItem(userStorageKey("active_conversation"), conversation.id);
  saveConversations();
  clearChatPanels();
  (conversation.messages || []).forEach((message) => appendMessage(message.role, message.content, {skipRecord: true}));
  renderSources(conversation.sources || []);
  renderRelatedQuestionsFromList(conversation.relatedQuestions || []);
  renderRetrievalSummaryModel(conversation.retrieval);
  renderConversationList();
}

function startNewConversation() {
  createConversation();
  state.sessionId = null;
  clearChatPanels();
  appendMessage("assistant", "已创建新会话。旧对话已保存在右侧历史会话中。", {skipRecord: true});
}

function deleteConversation(conversationId) {
  const conversation = state.conversations.find((item) => item.id === conversationId);
  if (!conversation) return;
  const title = conversation.title || "新会话";
  if (!window.confirm(`确定删除“${title}”吗？`)) return;
  const wasActive = state.activeConversationId === conversationId;
  state.conversations = state.conversations.filter((item) => item.id !== conversationId);
  if (!wasActive) {
    saveConversations();
    renderConversationList();
    return;
  }
  const next = state.conversations[0];
  state.activeConversationId = next?.id || "";
  state.sessionId = next?.sessionId || null;
  if (next) {
    restoreConversation(next.id);
    return;
  }
  saveConversations();
  clearChatPanels();
  appendMessage("assistant", "历史会话已删除。点击“新建会话”或直接提问即可开始新的问答。", {skipRecord: true});
  renderConversationList();
}

function initChatState() {
  const savedActive = state.conversations.find((item) => item.id === state.activeConversationId);
  if (savedActive) {
    restoreConversation(savedActive.id);
    return;
  }
  if (state.conversations.length) {
    restoreConversation(state.conversations[0].id);
    return;
  }
  createConversation();
  clearChatPanels();
  appendMessage("assistant", "您好，我可以基于地质灾害标准、知识图谱、已上传文档和实时灾害事件回答问题。回答会尽量给出参考来源。", {skipRecord: true});
}

function renderConversationList() {
  const container = $("#conversationList");
  if (!container) return;
  if (!state.conversations.length) {
    container.innerHTML = '<div class="empty-state">暂无历史会话。</div>';
    return;
  }
  container.innerHTML = state.conversations.slice(0, 12).map((conversation) => `
    <div class="conversation-row ${conversation.id === state.activeConversationId ? "active" : ""}">
      <button class="conversation-item" type="button" data-conversation-id="${escapeHtml(conversation.id)}">
        <strong>${escapeHtml(conversation.title || "新会话")}</strong>
        <span>${escapeHtml(formatConversationTime(conversation.updatedAt))} · ${(conversation.messages || []).length} 条消息</span>
      </button>
      <button class="conversation-delete" type="button" data-delete-conversation-id="${escapeHtml(conversation.id)}" aria-label="删除会话">删除</button>
    </div>
  `).join("");
  container.querySelectorAll("[data-conversation-id]").forEach((button) => {
    button.addEventListener("click", () => restoreConversation(button.dataset.conversationId));
  });
  container.querySelectorAll("[data-delete-conversation-id]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteConversation(button.dataset.deleteConversationId);
    });
  });
}

function formatConversationTime(timestamp) {
  if (!timestamp) return "刚刚";
  return new Date(timestamp).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function hasToken() {
  return Boolean(state.token);
}

function tokenExpired() {
  const expiresAt = Number(localStorage.getItem("rag_token_expires_at") || 0);
  return Boolean(expiresAt) && expiresAt <= Math.floor(Date.now() / 1000);
}

function ensureAuthenticatedPage() {
  state.token = localStorage.getItem("rag_access_token") || "";
  state.username = localStorage.getItem("rag_username") || "";
  if (!state.token || tokenExpired()) {
    clearAuthStorage();
    window.location.replace("/");
    return false;
  }
  return true;
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
  state.role = localStorage.getItem("rag_user_role") || "";
  const userState = $("#userState");
  const loginLink = $("#loginLink");
  const logoutBtn = $("#logoutBtn");
  if (hasToken()) {
    const label = state.role === "admin" ? "管理员" : "用户";
    userState.textContent = `${label}：${state.username || "admin"}`;
    loginLink.classList.add("hidden");
    logoutBtn.classList.remove("hidden");
  } else {
    userState.textContent = "游客";
    loginLink.classList.remove("hidden");
    logoutBtn.classList.add("hidden");
  }
  renderAdminGate("eventsGate", true);
}

function clearAuthStorage() {
  localStorage.removeItem("rag_access_token");
  localStorage.removeItem("rag_token_expires_at");
  localStorage.removeItem("rag_username");
  localStorage.removeItem("rag_user_role");
  localStorage.removeItem("rag_active_conversation");
  state.token = "";
  state.username = "";
}

async function logout() {
  saveConversations();
  try {
    await syncAccountData();
  } catch {
    // Logout should still proceed if account data sync is temporarily unavailable.
  }
  const token = state.token;
  try {
    await fetch("/api/auth/logout", {
      method: "POST",
      headers: token ? {Authorization: `Bearer ${token}`} : {},
    });
  } catch {
    // Local cleanup still matters if the network request fails.
  }
  clearTimeout(accountSaveTimer);
  document.cookie = "rag_access_token=; Max-Age=0; path=/; SameSite=Lax";
  clearAuthStorage();
  updateAuthState();
  renderOverview();
  window.location.replace("/");
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
    <p>登录后可以同步灾害数据和查看管理信息。</p>
    <a class="secondary admin-login-link" href="/">去登录</a>
  `;
}

function showPage(name) {
  const targetName = PUBLIC_PAGES.has(name) ? name : "home";
  if (name === "documents") toast("该功能已关闭。");
  $$(".page").forEach((page) => page.classList.toggle("active", page.id === `page-${targetName}`));
  $$("#topNav button").forEach((button) => button.classList.toggle("active", button.dataset.page === targetName));
  if (location.hash !== `#${targetName}`) history.replaceState(null, "", `#${targetName}`);
  $("#topNav").classList.remove("open");

  if (targetName === "graph") loadGraphPage();
  if (targetName === "standards") loadStandards();
  if (targetName === "events") loadEvents();
  if (targetName === "about") updateAuthState();
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
  renderOverview();
  renderHomeEvents();
}

function renderOverview() {
  const container = $("#overviewCards");
  if (!container) return;
  const summary = state.summary || {};
  const cards = [
    ["标准数量", summary.standards ?? "-"],
    ["知识节点数量", summary.nodes ?? sumNodeCounts(summary)],
    ["关系数量", summary.relationships ?? "-"],
    ["灾害事件数量", state.events.length || "-"],
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
      <p>${escapeHtml(item.text)}</p>
      <button class="ghost" type="button" data-jump="${escapeHtml(item.target)}">进入</button>
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
  if (!output) return;
  if (!keyword) {
    state.homeSearch = {grouped: null, keyword: "", page: 1};
    renderSearchPlaceholder();
    return;
  }
  if ($("#homeSearchInput")) $("#homeSearchInput").value = keyword;
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

  state.homeSearch = {grouped, keyword, page: 1};
  renderGroupedResults(grouped, keyword, 1);
}

function runGlobalSearch(query) {
  const keyword = (query || "").trim();
  if (!keyword) return;
  showPage("home");
  performSearch(keyword);
  setTimeout(() => {
    $("#searchResults")?.scrollIntoView({behavior: "smooth", block: "start"});
  }, 0);
}

function eventMatchesKeyword(event, keyword) {
  const text = `${event.title || ""} ${event.event_type || ""} ${event.event_type_group || ""} ${event.place || ""} ${event.source_note || ""}`;
  const aliases = keyword === "暴雨" ? ["暴雨", "flood", "flash flood"] : [keyword];
  return aliases.some((word) => text.toLowerCase().includes(word.toLowerCase()));
}

function renderSearchPlaceholder() {
  const output = $("#searchResults");
  if (!output) return;
  output.innerHTML = '<div class="empty-state">请输入关键词，或点击上方热门关键词开始检索。</div>';
}

function flattenGroupedResults(grouped) {
  return SEARCH_GROUPS.flatMap((groupName) => (grouped[groupName] || []).map((item) => ({...item, groupName})));
}

function regroupResults(items) {
  const grouped = Object.fromEntries(SEARCH_GROUPS.map((name) => [name, []]));
  items.forEach((item) => grouped[item.groupName]?.push(item));
  return grouped;
}

function paginationItems(current, total) {
  if (total <= 7) return Array.from({length: total}, (_, index) => index + 1);
  const pages = [];
  for (let page = 1; page <= total; page += 1) {
    if (page === 1 || page === total || Math.abs(page - current) <= 1) {
      pages.push(page);
    } else if (pages[pages.length - 1] !== "...") {
      pages.push("...");
    }
  }
  return pages;
}

function renderSearchPagination(page, totalPages, totalItems) {
  if (totalPages <= 1) {
    return `<div class="search-result-meta">共 ${totalItems} 条结果</div>`;
  }
  const pages = paginationItems(page, totalPages).map((item) => {
    if (item === "...") return '<span class="pagination-ellipsis">...</span>';
    return `<button type="button" class="${item === page ? "active" : ""}" data-search-page="${item}">${item}</button>`;
  }).join("");
  return `
    <div class="search-pagination" aria-label="检索结果分页">
      <span>共 ${totalItems} 条结果，第 ${page} / ${totalPages} 页</span>
      <button type="button" data-search-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>上一页</button>
      ${pages}
      <button type="button" data-search-page="${page + 1}" ${page >= totalPages ? "disabled" : ""}>下一页</button>
    </div>
  `;
}

function bindSearchResultActions(output) {
  output.querySelectorAll("[data-node-id]").forEach((item) => {
    item.addEventListener("click", () => {
      showPage("graph");
      loadNodeDetail(item.dataset.nodeId);
    });
  });
  output.querySelectorAll("[data-search-page]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextPage = Number(button.dataset.searchPage || 1);
      renderGroupedResults(state.homeSearch.grouped, state.homeSearch.keyword, nextPage);
      output.scrollIntoView({behavior: "smooth", block: "start"});
    });
  });
}

function renderGroupedResults(grouped, keyword, requestedPage = 1) {
  const output = $("#searchResults");
  if (!output || !grouped) return;
  const allItems = flattenGroupedResults(grouped);
  if (!allItems.length) {
    output.innerHTML = '<div class="empty-state">没有找到匹配结果，请换一个关键词。</div>';
    return;
  }
  const totalPages = Math.max(1, Math.ceil(allItems.length / HOME_SEARCH_PAGE_SIZE));
  const page = Math.min(Math.max(Number(requestedPage) || 1, 1), totalPages);
  const pageItems = allItems.slice((page - 1) * HOME_SEARCH_PAGE_SIZE, page * HOME_SEARCH_PAGE_SIZE);
  const visibleGrouped = regroupResults(pageItems);
  state.homeSearch = {grouped, keyword, page};
  const sections = SEARCH_GROUPS.map((groupName) => {
    const items = visibleGrouped[groupName] || [];
    if (!items.length) return "";
    const groupTotal = (grouped[groupName] || []).length;
    return `
      <section class="result-group">
        <h3>${groupName}<span>${groupTotal}</span></h3>
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
  output.innerHTML = renderSearchPagination(page, totalPages, allItems.length) + sections;
  bindSearchResultActions(output);
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

function standardPublisher(standard) {
  const explicit = standard.publisher || standard.issuing_body || standard.issuer || standard.release_unit || standard.organization;
  if (explicit) return explicit;
  const code = standard.code || standard.standard_id || "";
  if (code.startsWith("GB")) return "国家市场监督管理总局 / 国家标准化管理委员会";
  if (code.startsWith("T/")) return "团体标准发布单位";
  return "行业标准发布单位";
}

function renderStandards() {
  const container = $("#standardsList");
  if (!container) return;
  const keyword = ($("#standardSearchInput")?.value || "").trim();
  const items = state.standards.filter((standard) => {
    const text = `${standard.code || ""} ${standard.name || ""} ${standard.title || ""}`;
    return !keyword || text.includes(keyword);
  });
  if (!items.length) {
    container.innerHTML = '<div class="empty-state">暂无标准数据。</div>';
    return;
  }
  container.innerHTML = `
    <div class="standards-table-wrap">
      <table class="standards-table">
        <thead>
          <tr>
            <th>文件名称</th>
            <th>文件编号</th>
            <th>发布单位</th>
            <th>查看</th>
          </tr>
        </thead>
        <tbody>
          ${items.map((standard) => {
            const code = standard.code || standard.standard_id || "";
            return `
              <tr>
                <td>
                  <strong>${escapeHtml(standard.name || standard.title || "未命名标准")}</strong>
                  <span class="type-tag">标准规范</span>
                </td>
                <td>${escapeHtml(code || "暂无编号")}</td>
                <td>${escapeHtml(standardPublisher(standard))}</td>
                <td>
                  <button class="ghost" type="button" data-standard-code="${escapeHtml(code)}">查看</button>
                </td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
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
    renderGraphOverview();
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
  const rawQuery = ($("#graphSearchInput")?.value || "").trim();
  const standard = $("#graphStandardFilter")?.value || "";
  const type = $("#graphTypeFilter")?.value || selectedRelationTypeToNodeType($("#graphRelationFilter")?.value || "");
  const disaster = $("#graphDisasterFilter")?.value || "";
  const query = rawQuery || disaster || standard;
  const container = $("#graphNodes");
  if (!container) return;
  if (!query && !type) {
    renderGraphOverview();
    return;
  }
  container.innerHTML = '<div class="loading">正在加载图谱节点...</div>';
  try {
    const items = await api(`/api/graph/search?q=${encodeURIComponent(query || "灾害")}&limit=80`);
    state.graphResults = items.filter((item) => {
      const text = `${item.title || ""} ${item.text || ""}`;
      if (standard && item.code !== standard) return false;
      if (type && item.type !== type) return false;
      if (disaster && !text.includes(disaster)) return false;
      return true;
    });
    state.graphView = "search";
    state.expandedStandardCode = standard || "";
    renderGraphCanvas();
    renderGraphNodes();
  } catch (error) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    $("#graphCanvas").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderGraphOverview() {
  state.graphView = "overview";
  state.expandedStandardCode = "";
  state.graphResults = (state.standards || []).map((standard) => ({
    type: "标准",
    code: standard.code || "",
    title: standard.title || standard.name || standard.code || "未命名标准",
    text: `${standard.code || ""} ${standard.title || ""}`,
    node_id: standard.standard_id || "",
    chapters: standard.chapters || 0,
    clauses: standard.clauses || 0,
    terms: standard.terms || 0,
    requirements: standard.requirements || 0,
    indicators: standard.indicators || 0,
    methods: standard.methods || 0,
    overview: true,
  }));
  renderGraphCanvas();
  renderGraphNodes();
}

async function expandStandardGraph(code, nodeId = "") {
  if (!code) return;
  const canvas = $("#graphCanvas");
  const list = $("#graphNodes");
  if (canvas) canvas.innerHTML = '<div class="loading">正在展开标准子节点...</div>';
  if (list) list.innerHTML = '<div class="loading">正在加载章节、条款和知识点...</div>';
  try {
    const detail = await api(`/api/graph/standards/${encodeURIComponent(code)}`);
    renderStandardSubgraph(detail);
    if (nodeId) loadNodeDetail(nodeId);
  } catch (error) {
    if (canvas) canvas.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (list) list.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderStandardSubgraph(detail) {
  const standard = detail.standard || {};
  const rootId = standard.standard_id || `std-code-${standard.code || "standard"}`;
  state.graphView = "standard";
  state.expandedStandardCode = standard.code || "";
  state.graphResults = [
    {
      type: "标准",
      code: standard.code || "",
      title: standard.title || standard.name || standard.code || "未命名标准",
      text: `${standard.code || ""} ${standard.title || ""}`,
      node_id: rootId,
      expandedRoot: true,
      chapters: standard.chapters || (detail.chapters || []).length,
      clauses: standard.clauses || (detail.clauses || []).length,
      terms: standard.terms || (detail.terms || []).length,
      requirements: standard.requirements || (detail.requirements || []).length,
      indicators: standard.indicators || (detail.indicators || []).length,
      methods: standard.methods || (detail.methods || []).length,
    },
    ...standardChildItems(detail, rootId),
  ];
  renderGraphCanvas();
  renderGraphNodes();
}

function standardChildItems(detail, parentId) {
  const mapNode = (item, type) => ({
    type,
    code: item.code || detail.standard?.code || "",
    title: item.title || item.name || item.text || item.number || "未命名节点",
    text: item.content || item.definition || item.description || item.text || item.name || item.title || "",
    node_id: item.id || item.standard_id || "",
    number: item.number || item.clause_number || "",
    parentId,
    child: true,
  });
  return [
    ...(detail.chapters || []).map((item) => mapNode(item, "章节")),
    ...(detail.clauses || []).map((item) => mapNode(item, "条款")),
    ...(detail.terms || []).map((item) => mapNode(item, "术语")),
    ...(detail.requirements || []).map((item) => mapNode(item, "要求")),
    ...(detail.indicators || []).map((item) => mapNode(item, "指标")),
    ...(detail.methods || []).map((item) => mapNode(item, "方法")),
    ...(detail.objects || []).map((item) => mapNode(item, "对象")),
  ].filter((item) => item.node_id);
}

function buildGraphCanvasData(items) {
  const expanded = (items || []).some((item) => item.expandedRoot);
  const limit = expanded ? 42 : 28;
  const limited = (items || []).slice(0, limit);
  const nodeMap = new Map();
  const edges = [];

  function putNode(node) {
    if (!node.id || nodeMap.has(node.id)) return;
    nodeMap.set(node.id, node);
  }

  const overview = limited.length > 0 && limited.every((item) => item.type === "标准" && item.overview);
  if (overview) {
    putNode({id: "standards-root", label: "标准库", type: "总览", virtual: true});
  }

  const expandedRoot = limited.find((item) => item.expandedRoot);
  if (expandedRoot) {
    putNode({
      id: expandedRoot.node_id,
      label: expandedRoot.title || expandedRoot.code || "标准",
      type: "标准",
      code: expandedRoot.code || "",
      sourceItem: expandedRoot,
      expandedRoot: true,
    });
  }

  limited.forEach((item, index) => {
    if (item.expandedRoot) return;
    const nodeId = item.node_id || (item.type === "标准" && item.code ? `std-code-${item.code}` : `search-${index}`);
    const type = item.type || "节点";
    const label = item.title || item.text?.slice(0, 28) || "未命名节点";
    putNode({
      id: nodeId,
      label,
      type,
      code: item.code || "",
      sourceItem: item,
    });
    if (overview) {
      edges.push({
        source: "standards-root",
        target: nodeId,
        label: "包含标准",
      });
    } else if (expandedRoot) {
      edges.push({
        source: expandedRoot.node_id,
        target: nodeId,
        label: relationLabelForType(type),
      });
    } else if (item.code && type !== "标准") {
      const standardId = `std-code-${item.code}`;
      putNode({
        id: standardId,
        label: item.code,
        type: "标准",
        code: item.code,
        virtual: true,
      });
      edges.push({
        source: standardId,
        target: nodeId,
        label: relationLabelForType(type),
      });
    }
  });

  return {nodes: Array.from(nodeMap.values()), edges, totalItems: (items || []).length};
}

function relationLabelForType(type) {
  return {
    标准: "同类标准",
    章节: "包含章节",
    条款: "包含条款",
    术语: "定义术语",
    要求: "规范要求",
    指标: "指标参数",
    方法: "工程措施",
    对象: "适用对象",
  }[type] || "相关";
}

function renderGraphCanvas() {
  const container = $("#graphCanvas");
  if (!container) return;
  if (graphCanvasRuntime?.stop) graphCanvasRuntime.stop();
  const {nodes, edges, totalItems} = buildGraphCanvasData(state.graphResults);
  if (!nodes.length) {
    container.innerHTML = '<div class="empty-state">没有可展示的节点关系，请调整筛选条件。</div>';
    return;
  }

  const width = 920;
  const height = 430;
  seedGraphPositions(nodes, edges, width, height);

  const edgeMarkup = edges.map((edge, index) => {
    const pathId = `graphEdgePath${index}`;
    return `
      <g class="graph-edge" data-edge-index="${index}">
        <path id="${pathId}" class="graph-edge-path"></path>
        <path class="graph-edge-flow"></path>
        <text><textPath href="#${pathId}" xlink:href="#${pathId}" startOffset="50%">${escapeHtml(edge.label)}</textPath></text>
      </g>
    `;
  }).join("");

  const nodeMarkup = nodes.map((node) => {
    node.radius = node.type === "标准" ? 29 : node.type === "条款" ? 23 : 20;
    const label = truncateGraphLabel(node.label, node.type === "标准" ? 16 : 12);
    return `
      <g class="graph-node graph-node-${nodeClass(node.type)}" data-node-id="${escapeHtml(node.virtual ? "" : node.id)}" data-code="${escapeHtml(node.code || "")}" data-node-type="${escapeHtml(node.type || "")}" data-graph-id="${escapeHtml(node.id)}">
        <circle class="graph-node-halo" r="${node.radius + 9}"></circle>
        <circle class="graph-node-core" r="${node.radius}"></circle>
        <text class="graph-node-label" y="${node.radius + 18}">${escapeHtml(label)}</text>
        <title>${escapeHtml(node.label)}</title>
      </g>
    `;
  }).join("");

  container.innerHTML = `
    <div class="graph-canvas-head">
      <div>
        <strong>节点关系图</strong>
        <span>${nodes.length} 个画布节点 · ${edges.length} 条关系${totalItems > nodes.length ? ` · 共 ${totalItems} 个可浏览节点` : ""}</span>
      </div>
      <div class="graph-toolbar" aria-label="图谱交互工具">
        <button type="button" data-graph-action="zoom-out">缩小</button>
        <button type="button" data-graph-action="fit">适配视图</button>
        <button type="button" data-graph-action="zoom-in">放大</button>
        <button type="button" data-graph-action="restart">重新布局</button>
      </div>
    </div>
    <div class="graph-hint">${state.graphView === "standard" ? "拖拽节点调整布局，滚轮缩放，点击子节点查看详情" : "拖拽和滚轮浏览图谱，点击标准节点展开子节点"}</div>
    <svg viewBox="0 0 ${width} ${height}" xmlns:xlink="http://www.w3.org/1999/xlink" role="img" aria-label="知识图谱节点关系图">
      <defs>
        <marker id="graphArrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L0,6 L9,3 z"></path>
        </marker>
        <radialGradient id="graphGlow" cx="50%" cy="40%" r="60%">
          <stop offset="0%" stop-color="#ffffff" stop-opacity="0.82"></stop>
          <stop offset="100%" stop-color="#ffffff" stop-opacity="0"></stop>
        </radialGradient>
      </defs>
      <rect class="graph-background" width="${width}" height="${height}" rx="12"></rect>
      <g class="graph-viewport">
        <g class="graph-edges">${edgeMarkup}</g>
        <g class="graph-nodes">${nodeMarkup}</g>
      </g>
    </svg>
  `;
  graphCanvasRuntime = startGraphSimulation(container, nodes, edges, width, height);
  container.querySelectorAll(".graph-node").forEach((node) => {
    node.addEventListener("click", (event) => {
      if (node._dragMoved) {
        node._dragMoved = false;
        return;
      }
      const nodeId = node.dataset.nodeId;
      const code = node.dataset.code;
      const nodeType = node.dataset.nodeType;
      if (nodeType === "标准" && code) {
        expandStandardGraph(code, nodeId);
        return;
      }
      if (nodeId) {
        loadNodeDetail(nodeId);
        return;
      }
      if (code) {
        $("#graphStandardFilter").value = code;
        searchGraphNodes();
      }
    });
    node.addEventListener("dblclick", (event) => {
      event.preventDefault();
      event.stopPropagation();
      graphCanvasRuntime?.focusNode(node.dataset.graphId);
    });
  });
  container.querySelector('[data-graph-action="restart"]')?.addEventListener("click", () => graphCanvasRuntime?.restart());
  container.querySelector('[data-graph-action="fit"]')?.addEventListener("click", () => graphCanvasRuntime?.fit());
  container.querySelector('[data-graph-action="zoom-out"]')?.addEventListener("click", () => graphCanvasRuntime?.zoomBy(0.86));
  container.querySelector('[data-graph-action="zoom-in"]')?.addEventListener("click", () => graphCanvasRuntime?.zoomBy(1.16));
}

function seedGraphPositions(nodes, edges, width, height) {
  const centerX = width / 2;
  const centerY = height / 2 + 6;
  const expandedRoot = nodes.find((node) => node.expandedRoot || node.type === "总览");
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const degree = Object.fromEntries(nodes.map((node) => [node.id, 0]));
  edges.forEach((edge) => {
    degree[edge.source] = (degree[edge.source] || 0) + 1;
    degree[edge.target] = (degree[edge.target] || 0) + 1;
  });

  nodes.forEach((node, index) => {
    node.degree = degree[node.id] || 0;
    node.vx = 0;
    node.vy = 0;
    if (node === expandedRoot) {
      node.x = centerX;
      node.y = centerY;
      node.fx = centerX;
      node.fy = centerY;
      return;
    }
    const parent = node.parentId ? nodeById.get(node.parentId) : null;
    const angle = (Math.PI * 2 * index) / Math.max(nodes.length - 1, 1) - Math.PI / 2;
    const radius = parent ? 155 + (index % 4) * 24 : Math.min(310, 130 + nodes.length * 6);
    node.x = centerX + Math.cos(angle) * radius;
    node.y = centerY + Math.sin(angle) * Math.min(radius * 0.68, 150);
  });
}

function startGraphSimulation(container, nodes, edges, width, height) {
  const svg = container.querySelector("svg");
  const viewport = container.querySelector(".graph-viewport");
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const nodeElements = new Map(Array.from(container.querySelectorAll(".graph-node")).map((element) => [element.dataset.graphId, element]));
  const edgeElements = Array.from(container.querySelectorAll(".graph-edge"));
  let view = {x: 0, y: 0, k: 1};
  let alpha = 1;
  let frame = null;
  let stopped = false;
  let draggingNode = null;
  let panning = null;

  function svgPoint(event) {
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const mapped = point.matrixTransform(svg.getScreenCTM().inverse());
    return {
      x: (mapped.x - view.x) / view.k,
      y: (mapped.y - view.y) / view.k,
      rawX: mapped.x,
      rawY: mapped.y,
    };
  }

  function applyView() {
    viewport.setAttribute("transform", `translate(${view.x} ${view.y}) scale(${view.k})`);
  }

  function setZoom(nextK, rawX = width / 2, rawY = height / 2) {
    const point = {
      x: (rawX - view.x) / view.k,
      y: (rawY - view.y) / view.k,
    };
    view.x = rawX - point.x * nextK;
    view.y = rawY - point.y * nextK;
    view.k = nextK;
    applyView();
  }

  function zoomBy(factor) {
    const nextK = Math.max(0.55, Math.min(2.1, view.k * factor));
    setZoom(nextK);
  }

  function updateFrame() {
    edges.forEach((edge, index) => {
      const source = nodeById.get(edge.source);
      const target = nodeById.get(edge.target);
      const group = edgeElements[index];
      if (!source || !target || !group) return;
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const distance = Math.hypot(dx, dy) || 1;
      const sx = source.x + (dx / distance) * (source.radius || 22);
      const sy = source.y + (dy / distance) * (source.radius || 22);
      const tx = target.x - (dx / distance) * ((target.radius || 22) + 6);
      const ty = target.y - (dy / distance) * ((target.radius || 22) + 6);
      const curve = Math.min(42, Math.max(-42, (index % 5 - 2) * 12));
      const cx = (sx + tx) / 2 - (dy / distance) * curve;
      const cy = (sy + ty) / 2 + (dx / distance) * curve;
      const path = `M${sx.toFixed(1)},${sy.toFixed(1)} Q${cx.toFixed(1)},${cy.toFixed(1)} ${tx.toFixed(1)},${ty.toFixed(1)}`;
      group.querySelectorAll("path").forEach((item) => item.setAttribute("d", path));
    });
    nodes.forEach((node) => {
      const element = nodeElements.get(node.id);
      if (element) element.setAttribute("transform", `translate(${node.x.toFixed(1)}, ${node.y.toFixed(1)})`);
    });
  }

  function edgeTargetDistance(edge) {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    if (source?.expandedRoot || target?.expandedRoot || source?.type === "总览" || target?.type === "总览") return 150;
    if (source?.type === "标准" || target?.type === "标准") return 125;
    return 108;
  }

  function tick() {
    if (stopped) return;
    alpha = Math.max(alpha * 0.965, 0.012);
    const centerX = width / 2;
    const centerY = height / 2 + 8;

    edges.forEach((edge) => {
      const source = nodeById.get(edge.source);
      const target = nodeById.get(edge.target);
      if (!source || !target) return;
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const distance = Math.hypot(dx, dy) || 1;
      const desired = edgeTargetDistance(edge);
      const force = (distance - desired) * 0.022 * alpha;
      const fx = (dx / distance) * force;
      const fy = (dy / distance) * force;
      if (source.fx == null) {
        source.vx += fx;
        source.vy += fy;
      }
      if (target.fx == null) {
        target.vx -= fx;
        target.vy -= fy;
      }
    });

    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = nodes[i];
        const b = nodes[j];
        const dx = b.x - a.x || 0.01;
        const dy = b.y - a.y || 0.01;
        const distanceSq = dx * dx + dy * dy;
        const minDistance = (a.radius || 22) + (b.radius || 22) + 42;
        const repulse = Math.min(2.6, (minDistance * minDistance) / Math.max(distanceSq, 80)) * alpha;
        const distance = Math.sqrt(distanceSq);
        const fx = (dx / distance) * repulse;
        const fy = (dy / distance) * repulse;
        if (a.fx == null) {
          a.vx -= fx;
          a.vy -= fy;
        }
        if (b.fx == null) {
          b.vx += fx;
          b.vy += fy;
        }
      }
    }

    nodes.forEach((node) => {
      const targetY = node.type === "标准" && state.graphView !== "standard" ? height * 0.28 : centerY;
      if (node.fx == null) {
        node.vx += (centerX - node.x) * 0.006 * alpha;
        node.vy += (targetY - node.y) * 0.006 * alpha;
        node.vx *= 0.82;
        node.vy *= 0.82;
        node.x = Math.max(54, Math.min(width - 54, node.x + node.vx));
        node.y = Math.max(58, Math.min(height - 58, node.y + node.vy));
      } else {
        node.x = node.fx;
        node.y = node.fy;
      }
    });

    updateFrame();
    if (alpha > 0.014 || draggingNode) {
      frame = requestAnimationFrame(tick);
    } else {
      frame = null;
    }
  }

  function restart() {
    nodes.forEach((node) => {
      if (!node.expandedRoot && node.type !== "总览") {
        node.fx = null;
        node.fy = null;
      }
      node.vx = 0;
      node.vy = 0;
    });
    alpha = 1;
    if (!frame) frame = requestAnimationFrame(tick);
  }

  function fit() {
    const xs = nodes.map((node) => node.x);
    const ys = nodes.map((node) => node.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const boxWidth = Math.max(maxX - minX, 1);
    const boxHeight = Math.max(maxY - minY, 1);
    const nextK = Math.min(1.35, Math.max(0.68, Math.min((width - 120) / boxWidth, (height - 110) / boxHeight)));
    view = {
      k: nextK,
      x: width / 2 - ((minX + maxX) / 2) * nextK,
      y: height / 2 - ((minY + maxY) / 2) * nextK,
    };
    applyView();
  }

  function focusNode(nodeId) {
    const node = nodeById.get(nodeId);
    if (!node) return;
    view = {k: 1.45, x: width / 2 - node.x * 1.45, y: height / 2 - node.y * 1.45};
    applyView();
    nodeElements.forEach((element) => element.classList.toggle("dimmed", element.dataset.graphId !== nodeId));
    setTimeout(() => nodeElements.forEach((element) => element.classList.remove("dimmed")), 1200);
  }

  svg.addEventListener("wheel", (event) => {
    event.preventDefault();
    const point = svgPoint(event);
    const nextK = Math.max(0.55, Math.min(2.1, view.k * (event.deltaY > 0 ? 0.9 : 1.1)));
    setZoom(nextK, point.rawX, point.rawY);
  }, {passive: false});

  svg.addEventListener("pointerdown", (event) => {
    if (!event.target.classList.contains("graph-background")) return;
    const point = svgPoint(event);
    panning = {x: point.rawX, y: point.rawY, viewX: view.x, viewY: view.y};
    svg.setPointerCapture(event.pointerId);
  });
  svg.addEventListener("pointermove", (event) => {
    if (!panning) return;
    const point = svgPoint(event);
    view.x = panning.viewX + point.rawX - panning.x;
    view.y = panning.viewY + point.rawY - panning.y;
    applyView();
  });
  svg.addEventListener("pointerup", () => {
    panning = null;
  });
  svg.addEventListener("pointercancel", () => {
    panning = null;
  });

  nodeElements.forEach((element, nodeId) => {
    const node = nodeById.get(nodeId);
    if (!node) return;
    element.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      event.stopPropagation();
      draggingNode = node;
      element._dragMoved = false;
      const point = svgPoint(event);
      node.fx = point.x;
      node.fy = point.y;
      element.classList.add("dragging");
      element.setPointerCapture(event.pointerId);
      alpha = Math.max(alpha, 0.42);
      if (!frame) frame = requestAnimationFrame(tick);
    });
    element.addEventListener("pointermove", (event) => {
      if (draggingNode !== node) return;
      const point = svgPoint(event);
      if (Math.hypot(node.fx - point.x, node.fy - point.y) > 2) element._dragMoved = true;
      node.fx = point.x;
      node.fy = point.y;
      alpha = Math.max(alpha, 0.28);
    });
    element.addEventListener("pointerup", (event) => {
      if (draggingNode !== node) return;
      draggingNode = null;
      element.classList.remove("dragging");
      if (!node.expandedRoot && node.type !== "总览") {
        node.fx = null;
        node.fy = null;
      }
      element.releasePointerCapture?.(event.pointerId);
    });
  });

  applyView();
  updateFrame();
  frame = requestAnimationFrame(tick);
  setTimeout(fit, 220);
  return {
    restart,
    fit,
    focusNode,
    zoomBy,
    stop() {
      stopped = true;
      if (frame) cancelAnimationFrame(frame);
      frame = null;
    },
  };
}

function truncateGraphLabel(label, maxLength) {
  const value = String(label || "");
  return value.length > maxLength ? `${value.slice(0, maxLength)}...` : value;
}

function renderGraphNodes() {
  const container = $("#graphNodes");
  const visible = state.graphResults.slice(0, state.graphView === "standard" ? 180 : state.graphResults.length);
  const hiddenCount = Math.max(state.graphResults.length - visible.length, 0);
  const header = state.graphView === "standard" ? `
    <div class="graph-subgraph-note">
      <strong>${escapeHtml(state.expandedStandardCode || "标准子图")}</strong>
      <span>已展开 ${state.graphResults.length - 1} 个子节点，列表展示前 ${visible.length - 1} 个。</span>
      <button class="ghost" type="button" id="backToGraphOverview">返回标准总览</button>
    </div>
  ` : "";
  container.innerHTML = header + (visible.map((item) => `
    <button class="node-card ${nodeClass(item.type)}" type="button" data-node-id="${escapeHtml(item.node_id || "")}" data-node-type="${escapeHtml(item.type || "")}" data-code="${escapeHtml(item.code || "")}">
      <span>${escapeHtml(item.type || "节点")}</span>
      <strong>${escapeHtml(item.title || item.text?.slice(0, 36) || "未命名节点")}</strong>
      <small>${escapeHtml(graphNodeMeta(item))}</small>
    </button>
  `).join("") || '<div class="empty-state">没有匹配的图谱节点。</div>') + (hiddenCount > 0 ? `<div class="empty-state">还有 ${hiddenCount} 个子节点未在列表中展开，请用上方搜索或筛选继续定位。</div>` : "");
  $("#backToGraphOverview")?.addEventListener("click", () => {
    $("#graphStandardFilter").value = "";
    $("#graphSearchInput").value = "";
    renderGraphOverview();
  });
  container.querySelectorAll(".node-card").forEach((button, index) => {
    button.addEventListener("click", () => {
      if (button.dataset.nodeType === "标准" && button.dataset.code) {
        expandStandardGraph(button.dataset.code, button.dataset.nodeId);
      } else if (button.dataset.nodeId) {
        loadNodeDetail(button.dataset.nodeId);
      } else {
        renderNodeDetail({node: visible[index], relations: []});
      }
    });
  });
}

function graphNodeMeta(item) {
  if (item.overview) {
    return `${item.code || "标准"} · ${item.clauses || 0} 条款 · ${item.requirements || 0} 要求`;
  }
  if (item.expandedRoot) {
    return `${item.code || "标准"} · ${item.clauses || 0} 条款 · ${item.requirements || 0} 要求`;
  }
  if (item.child) {
    return [item.code, item.number].filter(Boolean).join(" · ") || "子节点";
  }
  return item.code || "知识图谱";
}

function nodeClass(type) {
  return {
    总览: "root",
    标准: "standard",
    条款: "clause",
    术语: "term",
    要求: "requirement",
    方法: "method",
    指标: "indicator",
    对象: "object",
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
    const [data, officialEvents] = await Promise.all([
      api(`/api/disasters/events?${params.toString()}`),
      loadOfficialEvents({source, days, type}),
    ]);
    state.events = [...(data.events || []), ...officialEvents];
    renderOverview();
    renderHomeEvents();
    if (!options.homeOnly) renderEvents();
  } catch (error) {
    if (!options.silent) toast(error.message);
  }
}

async function loadOfficialEvents({source, days, type}) {
  if (source && !OFFICIAL_SOURCE_IDS.has(source)) return [];
  const params = new URLSearchParams({active_only: "true", limit: "200"});
  if (source) params.set("source_id", source);
  const start = new Date(Date.now() - Number(days || 365) * 24 * 60 * 60 * 1000);
  params.set("start_time", start.toISOString().slice(0, 19).replace("T", " "));
  try {
    const data = await api(`/api/disaster-events/latest?${params.toString()}`);
    return (data.events || []).filter((event) => officialTypeMatches(event.disaster_type, type)).map(officialEventToRealtime);
  } catch {
    return [];
  }
}

function officialTypeMatches(disasterType, selectedType) {
  if (!selectedType) return true;
  const type = disasterType || "";
  if (selectedType === "Flood") return ["flood", "mountain_flood", "rainfall", "water_level", "reservoir"].includes(type);
  if (selectedType === "Landslide") return ["landslide", "debris_flow", "collapse", "geological_disaster"].includes(type);
  return selectedType.toLowerCase() === type.toLowerCase();
}

function officialEventToRealtime(event) {
  return {
    event_uid: `official::${event.source_id || "source"}::${event.content_hash || event.id}`,
    event_id: String(event.id || event.content_hash || ""),
    source: event.source_name || event.source_id || "官方采集",
    source_id: event.source_id || "",
    source_note: event.confidence || "official_news",
    event_type: disasterTypeText(event.disaster_type),
    event_type_group: event.disaster_type || "official",
    title: event.title || "灾害信息",
    place: event.address_text || event.county || event.city || event.province || "长沙周边",
    time: event.published_at || event.updated_at || "",
    latitude: event.lat,
    longitude: event.lng,
    risk: warningLevelText(event.warning_level),
    risk_score: warningScore(event.warning_level),
    color: warningColor(event.warning_level),
    radius_m: 18000 + warningScore(event.warning_level) * 12000,
    url: event.original_url || event.source_url || "",
    summary: event.summary || "",
  };
}

function disasterTypeText(type) {
  return {
    flood: "洪水",
    mountain_flood: "山洪",
    landslide: "滑坡",
    debris_flow: "泥石流",
    collapse: "崩塌",
    geological_disaster: "地质灾害",
    rainfall: "暴雨",
    water_level: "水位",
    reservoir: "水库",
  }[type] || type || "灾害信息";
}

function warningLevelText(level) {
  return {red: "红色预警", orange: "橙色预警", yellow: "黄色预警", blue: "蓝色预警"}[level] || level || "未知";
}

function warningScore(level) {
  return {red: 4, orange: 3, yellow: 2, blue: 1}[level] || 0;
}

function warningColor(level) {
  return {
    red: [214, 39, 40, 190],
    orange: [245, 124, 0, 180],
    yellow: [250, 204, 21, 170],
    blue: [37, 99, 235, 170],
  }[level] || [15, 159, 143, 150];
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
      ${event.url ? `<a class="text-link event-link" href="${escapeHtml(event.url)}" target="_blank" rel="noopener noreferrer">查看来源</a>` : ""}
    </article>
  `).join("") || '<div class="empty-state">当前筛选条件下没有事件。</div>';
}

function formatCoord(lat, lon) {
  if (lat === null || lat === undefined || lon === null || lon === undefined) return "暂无坐标";
  return `${Number(lat).toFixed(3)}, ${Number(lon).toFixed(3)}`;
}

function geolocationErrorMessage(error) {
  if (!error) return "无法获取当前位置，请稍后重试。";
  if (error.code === 1) return "定位权限被拒绝，请在浏览器地址栏允许位置权限后重试。";
  if (error.code === 2) return "无法获取当前位置，请检查系统定位服务或网络状态。";
  if (error.code === 3) return "定位请求超时，请稍后重试。";
  return "无法获取当前位置，请稍后重试。";
}

function getCurrentLocation() {
  const button = $("#getLocationBtn");
  if (!navigator.geolocation) {
    toast("当前浏览器不支持定位功能。");
    return;
  }
  if (!window.isSecureContext) {
    toast("定位功能需要 HTTPS 环境，请使用 https://georisklab.com.cn 访问。");
    return;
  }
  if (button) {
    button.disabled = true;
    button.textContent = "定位中...";
  }
  navigator.geolocation.getCurrentPosition(
    async (position) => {
      const lat = position.coords.latitude;
      const lon = position.coords.longitude;
      $("#eventLatInput").value = lat.toFixed(6);
      $("#eventLonInput").value = lon.toFixed(6);
      if (!$("#eventRadiusFilter").value) {
        $("#eventRadiusFilter").value = "200";
      }
      const accuracy = position.coords.accuracy ? `，精度约 ${Math.round(position.coords.accuracy)} 米` : "";
      toast(`已获取当前位置${accuracy}，正在查询附近事件。`);
      try {
        await loadEvents();
      } finally {
        if (button) {
          button.disabled = false;
          button.textContent = "获取当前位置";
        }
      }
    },
    (error) => {
      if (button) {
        button.disabled = false;
        button.textContent = "获取当前位置";
      }
      toast(geolocationErrorMessage(error));
    },
    {enableHighAccuracy: true, timeout: 10000, maximumAge: 300000},
  );
}

async function syncEvents() {
  if (!hasToken()) {
    renderAdminGate("eventsGate");
    toast(ADMIN_MESSAGE);
    return;
  }
  try {
    const data = await api("/api/disasters/sync", {method: "POST", auth: true});
    const firecrawl = data.statuses?.Firecrawl;
    const firecrawlText = firecrawl?.configured ? "，已包含 Firecrawl 联网爬取" : "，Firecrawl 未配置";
    toast(`同步完成：${data.count || 0} 条事件，新增入库 ${data.new_events || 0} 条${firecrawlText}。`);
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
  if (!options.loading && !options.skipRecord) {
    recordMessage(role, content);
  }
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
    updateConversationArtifacts(data, question);
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
    ["联网搜索", grouped.web],
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
    else if (source.type === "web") groups.web.push(source);
    else if (source.standard || source.clause) groups.standard.push(source);
    else groups.graph.push(source);
    return groups;
  }, {standard: [], graph: [], document: [], web: []});
}

function sourceLabel(source) {
  if (source.type === "document") return "文档片段";
  if (source.type === "web") return "联网搜索";
  if (source.standard || source.clause) return "标准条款";
  if (source.type === "graph") return "图谱节点";
  if (source.type === "realtime") return "实时事件";
  return source.type || "来源";
}

function sourceMeta(source) {
  if (source.type === "document") return source.source || source.title || "本地文档";
  if (source.type === "web") return source.url || source.source || "联网搜索";
  return [source.standard, source.clause].filter(Boolean).join(" · ") || source.source || "知识图谱";
}

function renderRetrievalSummary(data) {
  renderRetrievalSummaryModel(buildRetrievalSummaryModel(data));
}

function buildRetrievalSummaryModel(data) {
  if (!data) return null;
  const sources = data.sources || [];
  const standardCount = new Set(sources.map((source) => source.standard).filter(Boolean)).size;
  const graphCount = Number(data.debug?.graph_count || data.graph_context?.length || 0);
  const documentCount = Number(data.debug?.retrieval_count || sources.filter((source) => source.type === "document").length || 0);
  const webCount = Number(data.debug?.web_count || sources.filter((source) => source.type === "web").length || 0);
  const evidenceCount = sources.length;
  const llmUsage = data.debug?.llm_usage || {};
  const llmErrors = data.debug?.errors || [];
  const isAiMode = Boolean(llmUsage.total_tokens || llmUsage.usage_source === "api") && !llmErrors.some((item) => String(item).includes("生成模型不可用"));
  const modeText = isAiMode ? "AI 生成模式" : "检索证据摘要模式";
  return {standardCount, graphCount, documentCount, webCount, evidenceCount, isAiMode, modeText};
}

function renderRetrievalSummaryModel(summary) {
  const container = $("#retrievalSummary");
  if (!container) return;
  if (!summary) {
    container.innerHTML = '<div class="empty-state">发送问题后显示本次检索过程。</div>';
    return;
  }
  container.innerHTML = `
    <div class="retrieval-mode ${summary.isAiMode ? "ai" : "fallback"}">${escapeHtml(summary.modeText)}</div>
    <div class="summary-grid">
      <div><strong>${summary.evidenceCount}</strong><span>证据数量</span></div>
      <div><strong>${summary.standardCount}</strong><span>命中标准</span></div>
      <div><strong>${summary.graphCount}</strong><span>图谱节点</span></div>
      <div><strong>${summary.documentCount}</strong><span>文档片段</span></div>
      <div><strong>${summary.webCount}</strong><span>联网结果</span></div>
    </div>
    <p>${summary.isAiMode ? "回答由大模型结合检索证据生成。" : "当前未检测到可用大模型调用结果，页面展示基于检索证据的摘要。"}</p>
  `;
}

function renderRelatedQuestions(question, sources) {
  renderRelatedQuestionsFromList(buildRelatedQuestions(question, sources));
}

function buildRelatedQuestions(question, sources) {
  const disaster = HOT_KEYWORDS.find((word) => question.includes(word)) || "滑坡";
  const standard = (sources || []).find((source) => source.standard)?.standard || "相关标准";
  return [
    `${disaster}风险评估需要关注哪些指标？`,
    `${standard}中有哪些监测预警要求？`,
    `针对${disaster}有哪些工程治理措施？`,
  ];
}

function renderRelatedQuestionsFromList(questions) {
  const container = $("#relatedQuestions");
  if (!container) return;
  container.innerHTML = questions.map((item) => `<button type="button">${escapeHtml(item)}</button>`).join("");
  container.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      $("#question").value = button.textContent;
      $("#chatForm").requestSubmit();
    });
  });
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
  $("#getLocationBtn")?.addEventListener("click", getCurrentLocation);
  $("#chatForm")?.addEventListener("submit", sendQuestion);
  $("#question")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      $("#chatForm")?.requestSubmit();
    }
  });
  $("#newChat")?.addEventListener("click", startNewConversation);
  $("#syncEventsBtn")?.addEventListener("click", syncEvents);
  $("#logoutBtn")?.addEventListener("click", logout);
}

async function init() {
  if (!ensureAuthenticatedPage()) return;
  setupNavigation();
  bindForms();
  updateAuthState();
  renderHotKeywords();
  renderUsagePaths();
  window.GeoRiskMap?.renderPlaceholder($("#eventMap"), state.events);
  await loadAccountData();
  initChatState();
  showPage((location.hash || "#home").slice(1));
  loadDashboard();
  if ($("#homeSearchInput")) $("#homeSearchInput").value = "";
  renderSearchPlaceholder();
}

document.addEventListener("DOMContentLoaded", () => {
  init().catch((error) => toast(error.message || "页面初始化失败。"));
});
