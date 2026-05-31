const TYPE_LABELS = {
  StandardDocument: "标准文档",
  Chapter: "章节",
  Clause: "条款",
  Term: "术语",
  Requirement: "规范要求",
  Indicator: "指标参数",
  Method: "方法",
  StandardObject: "适用对象",
};

const COLORS = {
  StandardDocument: "#174a7c",
  Chapter: "#2f9e65",
  Clause: "#56a8e8",
  Term: "#8e44ad",
  Requirement: "#e68632",
  Indicator: "#d94b4b",
  Method: "#18a6a6",
  StandardObject: "#7b8794",
};

const STANDARD_ORDER = [
  "GB/T 32864-2016",
  "GB/T 38509-2020",
  "T/CAGHP 002-2018",
  "GB/T 4012-2021",
  "GB/T 33680-2017",
  "GB/T 44011.1-2024",
];

const STANDARD_DESCRIPTIONS = {
  "GB/T 32864-2016": "滑坡防治工程勘查相关标准",
  "GB/T 38509-2020": "滑坡防治工程设计相关标准",
  "T/CAGHP 002-2018": "地质灾害防治术语标准",
  "GB/T 4012-2021": "地质灾害危险性评估标准",
  "GB/T 33680-2017": "暴雨灾害等级标准",
  "GB/T 44011.1-2024": "自然灾害综合风险评估标准",
};

const POPULAR_KEYWORDS = ["滑坡", "暴雨", "风险评估", "监测", "抗滑桩"];

const TOPICS = [
  { name: "滑坡", keywords: ["滑坡", "边坡", "抗滑", "稳定", "勘查", "防治"] },
  { name: "暴雨", keywords: ["暴雨", "降雨", "雨量", "灾害等级"] },
  { name: "风险评估", keywords: ["风险", "危险性", "评估", "评价", "承灾体"] },
  { name: "监测", keywords: ["监测", "预警", "观测", "位移", "变形"] },
];

let graphData = {};
let searchData = [];
let activeStandard = null;
let activeChapter = null;
let activeClause = null;

const index = {
  standardsByCode: new Map(),
  chaptersByCode: new Map(),
  clausesByCode: new Map(),
  clausesByChapter: new Map(),
  clausesById: new Map(),
  termsByClause: new Map(),
  requirementsByClause: new Map(),
  indicatorsByClause: new Map(),
  methodsByClause: new Map(),
  objectsByClause: new Map(),
  searchItems: [],
};

document.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadData();
    buildIndex();
    renderHome();
    renderSchema();
    renderStandards();
    renderTopic(TOPICS[0].name);
    bindSearch();
    renderStandardDetail(STANDARD_ORDER[0], { scroll: false });
    setLoading(false);
  } catch (error) {
    showLoadError(error);
  }
});

async function loadData() {
  graphData = await readJson("data/graph_data.json", "graphDataFrame");
  searchData = await readJson("data/search_index.json", "searchDataFrame");
}

async function readJson(path, frameId) {
  try {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path} ${response.status}`);
    return await response.json();
  } catch (fetchError) {
    return new Promise((resolve, reject) => {
      const frame = document.getElementById(frameId);
      const readFrame = () => {
        try {
          const text = frame?.contentDocument?.body?.innerText || "";
          if (!text.trim()) throw fetchError;
          resolve(JSON.parse(text));
        } catch (frameError) {
          reject(frameError);
        }
      };
      if (!frame) {
        reject(fetchError);
        return;
      }
      if (frame.contentDocument?.readyState === "complete") readFrame();
      else frame.addEventListener("load", readFrame, { once: true });
      setTimeout(() => reject(fetchError), 4000);
    });
  }
}

function setLoading(isLoading) {
  document.getElementById("loadingState")?.classList.toggle("hidden", !isLoading);
}

function showLoadError(error) {
  const box = document.getElementById("loadingState");
  if (!box) return;
  box.classList.remove("hidden");
  box.innerHTML = `
    <div class="load-error">
      <strong>知识图谱数据加载失败</strong>
      <span>请确认 data/graph_data.json 和 data/search_index.json 已随 docs 目录一起发布。</span>
      <small>${escapeHtml(error.message)}</small>
    </div>
  `;
}

function buildIndex() {
  for (const standard of graphData.standards || []) {
    index.standardsByCode.set(standard.code, standard);
    index.chaptersByCode.set(standard.code, []);
    index.clausesByCode.set(standard.code, []);
  }

  for (const chapter of graphData.chapters || []) {
    appendToMap(index.chaptersByCode, chapter.code, chapter);
  }

  for (const chapters of index.chaptersByCode.values()) {
    chapters.sort(compareNumber);
  }

  for (const clause of graphData.clauses || []) {
    index.clausesById.set(clause.id, clause);
    appendToMap(index.clausesByCode, clause.code, clause);
  }

  for (const [code, clauses] of index.clausesByCode) {
    clauses.sort(compareNumber);
    const chapters = index.chaptersByCode.get(code) || [];
    const chapterByNumber = new Map(chapters.map((chapter) => [chapter.number, chapter]));
    for (const clause of clauses) {
      const chapterNumber = String(clause.number || "").split(".")[0];
      const chapter = chapterByNumber.get(chapterNumber) || chapters.find((item) => item.id === clause.chapter_id);
      appendToMap(index.clausesByChapter, chapter?.id || "unassigned", clause);
    }
  }

  for (const term of graphData.terms || []) {
    if (term.source_clause_id) appendToMap(index.termsByClause, term.source_clause_id, term);
  }

  for (const item of graphData.requirements || []) appendToMap(index.requirementsByClause, clauseKey(item), item);
  for (const item of graphData.indicators || []) appendToMap(index.indicatorsByClause, clauseKey(item), item);
  for (const item of graphData.methods || []) appendToMap(index.methodsByClause, clauseKey(item), item);
  for (const item of graphData.objects || []) appendToMap(index.objectsByClause, clauseKey(item), item);

  index.searchItems = buildSearchItems();
}

function renderHome() {
  const counts = Object.fromEntries((graphData.node_counts || []).map((item) => [item.type, item.count]));
  const stats = [
    ["标准数量", graphData.standards?.length || 0],
    ["章节数量", graphData.chapters?.length || counts.Chapter || 0],
    ["条款数量", graphData.clauses?.length || counts.Clause || 0],
    ["术语数量", graphData.terms?.length || counts.Term || 0],
    ["规范要求数量", graphData.requirements?.length || counts.Requirement || 0],
    ["指标参数数量", graphData.indicators?.length || counts.Indicator || 0],
  ];
  document.getElementById("homeStats").innerHTML = stats
    .map(([label, value]) => `<div class="stat-card"><strong>${value}</strong><span>${label}</span></div>`)
    .join("");
  document.getElementById("generatedAt").textContent = graphData.generated_at ? `数据生成时间：${graphData.generated_at}` : "";
}

function renderSchema() {
  const node = (type) => `<div class="schema-node node-${type}">${type}<span>${TYPE_LABELS[type]}</span></div>`;
  const arrow = (label) => `<div class="schema-arrow"><span>${label}</span></div>`;
  document.getElementById("schemaBoard").innerHTML = `
    <div class="schema-main">
      ${node("StandardDocument")}
      ${arrow("HAS_CHAPTER")}
      ${node("Chapter")}
      ${arrow("HAS_CLAUSE")}
      ${node("Clause")}
    </div>
    <div class="schema-branches">
      ${node("Term")}
      ${node("Requirement")}
      ${node("Indicator")}
      ${node("Method")}
      ${node("StandardObject")}
    </div>
  `;
  document.getElementById("legend").innerHTML = Object.entries(TYPE_LABELS)
    .map(([type, label]) => `<span class="legend-item"><i class="legend-dot" style="background:${COLORS[type]}"></i>${type} ${label}</span>`)
    .join("");
}

function renderStandards() {
  document.getElementById("standardGrid").innerHTML = STANDARD_ORDER.map((code) => {
    const standard = index.standardsByCode.get(code);
    if (!standard) return "";
    return `
      <button class="standard-card" data-code="${escapeAttr(code)}">
        <strong>${escapeHtml(standard.code)}</strong>
        <h3>${escapeHtml(standard.title)}</h3>
        <p class="standard-desc">${escapeHtml(STANDARD_DESCRIPTIONS[code] || "行业标准知识图谱节点")}</p>
        <div class="card-metrics">
          <span>${standard.chapters || 0} 章</span>
          <span>${standard.clauses || 0} 条款</span>
          <span>${standard.terms || 0} 术语</span>
          <span>${standard.requirements || 0} 要求</span>
          <span>${standard.indicators || 0} 指标</span>
          <span>${standard.methods || 0} 方法</span>
        </div>
      </button>
    `;
  }).join("");

  document.querySelectorAll(".standard-card").forEach((card) => {
    card.addEventListener("click", () => renderStandardDetail(card.dataset.code, { scroll: true }));
  });
}

function renderStandardDetail(code, options = {}) {
  activeStandard = index.standardsByCode.get(code);
  if (!activeStandard) return;
  activeChapter = null;
  activeClause = null;

  document.querySelectorAll(".standard-card").forEach((card) => {
    card.classList.toggle("active", card.dataset.code === code);
  });

  const chapters = index.chaptersByCode.get(code) || [];
  document.getElementById("activeStandardIntro").textContent = `${activeStandard.code} ${activeStandard.title}`;
  document.getElementById("chapterCount").textContent = `${chapters.length} 章`;
  document.getElementById("chapterTree").innerHTML = chapters.map((chapter) => {
    const clauses = index.clausesByChapter.get(chapter.id) || [];
    return `
      <button class="chapter-button" data-id="${escapeAttr(chapter.id)}">
        ${escapeHtml(chapter.number)} ${escapeHtml(chapter.title)}
        <small>${clauses.length} 个条款</small>
      </button>
    `;
  }).join("");

  document.querySelectorAll(".chapter-button").forEach((button) => {
    button.addEventListener("click", () => renderChapterDetail(button.dataset.id));
  });

  renderStandardSummary();
  const firstUsefulChapter = chapters.find((chapter) => (index.clausesByChapter.get(chapter.id) || []).length > 0) || chapters[0];
  if (firstUsefulChapter) renderChapterDetail(firstUsefulChapter.id, { keepDetail: true });
  if (options.scroll) document.getElementById("standard-detail").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderStandardSummary() {
  document.getElementById("nodeDetail").innerHTML = `
    <h4>${escapeHtml(activeStandard.code)} ${escapeHtml(activeStandard.title)}</h4>
    ${detailRow("章节数量", activeStandard.chapters || 0)}
    ${detailRow("条款数量", activeStandard.clauses || 0)}
    ${detailRow("术语数量", activeStandard.terms || 0)}
    ${detailRow("规范要求数量", activeStandard.requirements || 0)}
    ${detailRow("指标参数数量", activeStandard.indicators || 0)}
    ${detailRow("方法数量", activeStandard.methods || 0)}
  `;
  document.getElementById("relationCount").textContent = "标准";
  renderSmallGraph("clauseGraph", [
    graphNode(activeStandard.standard_id, "StandardDocument", activeStandard.code, activeStandard.title),
    ...((index.chaptersByCode.get(activeStandard.code) || []).slice(0, 12).map((chapter) => graphNode(chapter.id, "Chapter", `${chapter.number} ${chapter.title}`, "章节"))),
  ], (index.chaptersByCode.get(activeStandard.code) || []).slice(0, 12).map((chapter) => ({
    source: activeStandard.standard_id,
    target: chapter.id,
    label: "HAS_CHAPTER",
  })));
}

function renderChapterDetail(chapterId, options = {}) {
  const chapters = index.chaptersByCode.get(activeStandard?.code) || [];
  activeChapter = chapters.find((chapter) => chapter.id === chapterId);
  if (!activeChapter) return;
  activeClause = null;

  document.querySelectorAll(".chapter-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.id === chapterId);
  });

  const clauses = index.clausesByChapter.get(chapterId) || [];
  document.getElementById("clausePanelTitle").textContent = `${activeChapter.number} ${activeChapter.title}`;
  document.getElementById("clauseCount").textContent = `${clauses.length} 条`;
  document.getElementById("clauseList").innerHTML = clauses.length
    ? clauses.slice(0, 120).map((clause) => `
        <button class="clause-button" data-id="${escapeAttr(clause.id)}">
          ${escapeHtml(clause.number)} ${escapeHtml(truncate(clause.title || clause.content, 80))}
          <small>${escapeHtml(truncate(clause.content || clause.title || "", 110))}</small>
        </button>
      `).join("")
    : `<div class="empty">该章节暂无可展示条款。</div>`;

  document.querySelectorAll(".clause-button").forEach((button) => {
    button.addEventListener("click", () => renderClauseDetail(button.dataset.id));
  });

  if (!options.keepDetail) {
    document.getElementById("nodeDetail").innerHTML = `
      <h4>${escapeHtml(activeChapter.number)} ${escapeHtml(activeChapter.title)}</h4>
      ${detailRow("所属标准", activeChapter.code)}
      ${detailRow("条款数量", clauses.length)}
    `;
    document.getElementById("relationCount").textContent = `${clauses.length} 条`;
    renderSmallGraph("clauseGraph", [
      graphNode(activeChapter.id, "Chapter", `${activeChapter.number} ${activeChapter.title}`, "章节"),
      ...clauses.slice(0, 24).map((clause) => graphNode(clause.id, "Clause", `${clause.number} ${clause.title || "条款"}`, "条款")),
    ], clauses.slice(0, 24).map((clause) => ({ source: activeChapter.id, target: clause.id, label: "HAS_CLAUSE" })));
  }
}

function renderClauseDetail(clauseId) {
  activeClause = index.clausesById.get(clauseId);
  if (!activeClause) return;

  document.querySelectorAll(".clause-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.id === clauseId);
  });

  const related = getClauseRelations(activeClause);
  const relatedCount = Object.values(related).reduce((sum, items) => sum + items.length, 0);
  document.getElementById("relationCount").textContent = `${relatedCount} 关联`;
  document.getElementById("nodeDetail").innerHTML = `
    <h4>${escapeHtml(activeClause.number)} ${escapeHtml(activeClause.title || "条款")}</h4>
    <div class="clause-actions">
      <button class="copy-button" data-copy="plain">复制条款原文</button>
      <button class="copy-button" data-copy="markdown">复制为 Markdown</button>
    </div>
    ${detailBlock("条款原文", `
      ${detailRow("所属标准", activeClause.code)}
      ${detailRow("条款编号", activeClause.number || "")}
      ${detailRow("条款内容", activeClause.content || activeClause.title || "")}
    `)}
    ${entitySection("关联术语", "Term", related.Term)}
    ${entitySection("规范要求", "Requirement", related.Requirement)}
    ${entitySection("指标参数", "Indicator", related.Indicator)}
    ${entitySection("方法", "Method", related.Method)}
    ${entitySection("适用对象", "StandardObject", related.StandardObject)}
  `;

  document.querySelectorAll(".copy-button").forEach((button) => {
    button.addEventListener("click", () => copyClause(button.dataset.copy));
  });

  document.querySelectorAll(".entity-button").forEach((button) => {
    button.addEventListener("click", () => {
      const [type, position] = button.dataset.entity.split(":");
      renderEntityDetail(type, related[type][Number(position)]);
    });
  });

  const graphNodes = [graphNode(activeClause.id, "Clause", `${activeClause.number} ${activeClause.title || "条款"}`, "条款")];
  const graphEdges = [];
  for (const [type, items] of Object.entries(related)) {
    for (const item of items.slice(0, 18)) {
      const id = entityId(type, item);
      graphNodes.push(graphNode(id, type, entityTitle(type, item), TYPE_LABELS[type]));
      graphEdges.push({ source: activeClause.id, target: id, label: relationLabel(type) });
    }
  }
  renderSmallGraph("clauseGraph", graphNodes.slice(0, 80), graphEdges);
}

function renderEntityDetail(type, item) {
  if (!item) return;
  document.getElementById("nodeDetail").innerHTML = `
    <h4>${escapeHtml(TYPE_LABELS[type] || type)}：${escapeHtml(entityTitle(type, item))}</h4>
    ${Object.entries(item).map(([key, value]) => detailRow(key, value)).join("")}
  `;
}

function renderTopic(topicName) {
  const topic = TOPICS.find((item) => item.name === topicName) || TOPICS[0];
  document.getElementById("topicTabs").innerHTML = TOPICS.map((item) => (
    `<button class="topic-button ${item.name === topic.name ? "active" : ""}" data-topic="${escapeAttr(item.name)}">${escapeHtml(item.name)}</button>`
  )).join("");
  document.querySelectorAll(".topic-button").forEach((button) => {
    button.addEventListener("click", () => renderTopic(button.dataset.topic));
  });

  const matches = index.searchItems
    .filter((item) => ["Clause", "Term", "Requirement", "Indicator", "Method"].includes(item.type))
    .filter((item) => topic.keywords.some((keyword) => item.text.includes(keyword)))
    .slice(0, 79);
  const relatedClauses = uniqueByKey(index.searchItems
    .filter((item) => item.type === "Clause")
    .filter((item) => topic.keywords.some((keyword) => item.text.includes(keyword))))
    .slice(0, 40);
  const root = graphNode(`topic-${topic.name}`, "StandardDocument", `${topic.name}专题`, "专题");
  const nodes = [root, ...matches.map((item, position) => graphNode(`topic-${position}`, item.type, item.title, item.code))];
  const edges = matches.map((item, position) => ({ source: root.id, target: `topic-${position}`, label: "RELATED_TO" }));
  renderSmallGraph("topicGraph", nodes, edges);

  document.getElementById("topicList").innerHTML = relatedClauses.length
    ? relatedClauses.map((item) => `
      <button class="result-button" data-key="${escapeAttr(item.key)}">
        <span class="type-pill type-${escapeAttr(item.type)}">${escapeHtml(TYPE_LABELS[item.type] || item.type)}</span>
        <strong>${escapeHtml(truncate(item.title, 76))}</strong>
        <small>${escapeHtml(item.code)}</small>
      </button>
    `).join("")
    : `<div class="empty">没有找到该专题的节点。</div>`;

  document.querySelectorAll("#topicList .result-button").forEach((button) => {
    button.addEventListener("click", () => openSearchItem(button.dataset.key));
  });
}

function performSearch(query) {
  const box = document.getElementById("searchResults");
  const keyword = query.trim();
  if (!keyword) {
    box.innerHTML = `<div class="empty">输入关键词后，搜索结果会按类型分组显示。</div>`;
    return;
  }

  const results = uniqueByKey(index.searchItems.filter((item) => item.text.includes(keyword))).slice(0, 80);
  if (!results.length) {
    box.innerHTML = `<div class="empty">没有找到匹配结果。</div>`;
    return;
  }

  const groups = groupBy(results, "type");
  box.innerHTML = Object.entries(groups).map(([type, items]) => `
    <div class="result-group">
      <h3>${escapeHtml(TYPE_LABELS[type] || type)} ${items.length}</h3>
      ${items.slice(0, 20).map((item) => `
        <button class="result-button" data-key="${escapeAttr(item.key)}">
          <strong>${highlightText(truncate(item.title, 92), keyword)}</strong>
          <small>${escapeHtml(item.code || "")}</small>
        </button>
      `).join("")}
    </div>
  `).join("");

  document.querySelectorAll("#searchResults .result-button").forEach((button) => {
    button.addEventListener("click", () => openSearchItem(button.dataset.key));
  });
}

function bindSearch() {
  const input = document.getElementById("searchInput");
  document.getElementById("popularKeywords").innerHTML = POPULAR_KEYWORDS.map((keyword) => (
    `<button class="keyword-button" data-keyword="${escapeAttr(keyword)}">${escapeHtml(keyword)}</button>`
  )).join("");
  document.querySelectorAll(".keyword-button").forEach((button) => {
    button.addEventListener("click", () => {
      input.value = button.dataset.keyword;
      performSearch(input.value);
      document.getElementById("search").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
  input.addEventListener("input", () => performSearch(input.value));
  performSearch("");
}

function openSearchItem(key) {
  const item = index.searchItems.find((candidate) => candidate.key === key);
  if (!item) return;
  renderStandardDetail(item.code, { scroll: false });

  if (item.type === "Chapter") {
    renderChapterDetail(item.payload.id);
  } else if (item.type === "Clause") {
    const chapter = findChapterForClause(item.payload);
    if (chapter) renderChapterDetail(chapter.id);
    renderClauseDetail(item.payload.id);
  } else if (["Term", "Requirement", "Indicator", "Method", "StandardObject"].includes(item.type)) {
    const clause = findClauseForEntity(item.type, item.payload);
    if (clause) {
      const chapter = findChapterForClause(clause);
      if (chapter) renderChapterDetail(chapter.id);
      renderClauseDetail(clause.id);
    }
    renderEntityDetail(item.type, item.payload);
  }

  document.getElementById("standard-detail").scrollIntoView({ behavior: "smooth", block: "start" });
}

function buildSearchItems() {
  const items = [];
  for (const standard of graphData.standards || []) {
    pushSearch(items, "StandardDocument", standard.code, `${standard.code} ${standard.title}`, `${standard.code} ${standard.title}`, standard);
  }
  for (const chapter of graphData.chapters || []) {
    pushSearch(items, "Chapter", chapter.code, `${chapter.number} ${chapter.title}`, `${chapter.code} ${chapter.number} ${chapter.title}`, chapter);
  }
  for (const clause of graphData.clauses || []) {
    pushSearch(items, "Clause", clause.code, `${clause.number} ${clause.title || clause.content || "条款"}`, `${clause.code} ${clause.number} ${clause.title || ""} ${clause.content || ""}`, clause);
  }
  for (const term of graphData.terms || []) {
    pushSearch(items, "Term", term.code, term.name || "术语", `${term.code} ${term.name || ""} ${term.definition || ""}`, term);
  }
  for (const requirement of graphData.requirements || []) {
    pushSearch(items, "Requirement", requirement.code, requirement.text || "规范要求", `${requirement.code} ${requirement.clause_number || ""} ${requirement.text || ""}`, requirement);
  }
  for (const indicator of graphData.indicators || []) {
    pushSearch(items, "Indicator", indicator.code, entityTitle("Indicator", indicator), `${indicator.code} ${indicator.clause_number || ""} ${entityTitle("Indicator", indicator)}`, indicator);
  }
  for (const method of graphData.methods || []) {
    pushSearch(items, "Method", method.code, method.name || "方法", `${method.code} ${method.clause_number || ""} ${method.name || ""} ${method.description || ""}`, method);
  }
  for (const object of graphData.objects || []) {
    pushSearch(items, "StandardObject", object.code, entityTitle("StandardObject", object), JSON.stringify(object), object);
  }
  for (const item of searchData || []) {
    const type = normalizeType(item.type);
    pushSearch(items, type, item.code, item.title || item.text || type, item.text || item.title || "", item);
  }
  return items;
}

function pushSearch(items, type, code, title, text, payload) {
  const key = `${type}:${code}:${stableHash(title)}:${items.length}`;
  items.push({ key, type, code, title, text, payload });
}

function getClauseRelations(clause) {
  const key = `${clause.code}::${clause.number}`;
  return {
    Term: index.termsByClause.get(clause.id) || [],
    Requirement: index.requirementsByClause.get(key) || [],
    Indicator: index.indicatorsByClause.get(key) || [],
    Method: index.methodsByClause.get(key) || [],
    StandardObject: index.objectsByClause.get(key) || [],
  };
}

function findClauseForEntity(type, item) {
  if (type === "Term" && item.source_clause_id) return index.clausesById.get(item.source_clause_id);
  if (item.clause_number) {
    return (index.clausesByCode.get(item.code) || []).find((clause) => clause.number === item.clause_number);
  }
  return null;
}

function findChapterForClause(clause) {
  const chapterNumber = String(clause.number || "").split(".")[0];
  const chapters = index.chaptersByCode.get(clause.code) || [];
  return chapters.find((chapter) => chapter.number === chapterNumber) || chapters.find((chapter) => chapter.id === clause.chapter_id);
}

function renderSmallGraph(containerId, nodes, edges) {
  const container = document.getElementById(containerId);
  if (!nodes.length) {
    container.innerHTML = `<div class="empty">没有可展示的关系图。</div>`;
    return;
  }

  const limitedNodes = nodes.slice(0, 80);
  const allowed = new Set(limitedNodes.map((node) => node.id));
  const limitedEdges = edges.filter((edge) => allowed.has(edge.source) && allowed.has(edge.target));
  const levels = layoutLevels(limitedNodes, limitedEdges);
  const colWidth = 230;
  const rowHeight = 78;
  const width = Math.max(680, levels.length * colWidth + 70);
  const height = Math.max(270, Math.max(...levels.map((level) => level.length), 1) * rowHeight + 70);
  const positions = new Map();

  levels.forEach((level, levelIndex) => {
    const total = (level.length - 1) * rowHeight;
    level.forEach((node, rowIndex) => {
      positions.set(node.id, {
        x: 36 + levelIndex * colWidth,
        y: 36 + (height - 70 - total) / 2 + rowIndex * rowHeight,
      });
    });
  });

  const edgeMarkup = limitedEdges.map((edge) => {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (!source || !target) return "";
    const x1 = source.x + 170;
    const y1 = source.y + 25;
    const x2 = target.x;
    const y2 = target.y + 25;
    const mid = (x1 + x2) / 2;
    return `
      <path class="graph-edge" d="M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}" fill="none" marker-end="url(#arrow)"></path>
      <text class="graph-label" x="${mid - 35}" y="${(y1 + y2) / 2 - 5}">${escapeHtml(edge.label)}</text>
    `;
  }).join("");

  const nodeMarkup = limitedNodes.map((node) => {
    const pos = positions.get(node.id);
    return `
      <g class="graph-node" transform="translate(${pos.x}, ${pos.y})">
        <rect width="170" height="50" rx="8" fill="${COLORS[node.type] || "#64748b"}"></rect>
        <text x="11" y="21">${escapeHtml(truncate(node.label, 17))}</text>
        <text class="sub" x="11" y="38">${escapeHtml(truncate(node.sub || TYPE_LABELS[node.type], 20))}</text>
      </g>
    `;
  }).join("");

  container.innerHTML = `
    <svg class="graph-svg" viewBox="0 0 ${width} ${height}" role="img">
      <defs>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
          <path d="M 0 0 L 8 4 L 0 8 z" fill="#b9c7d7"></path>
        </marker>
      </defs>
      ${edgeMarkup}
      ${nodeMarkup}
    </svg>
  `;
}

function layoutLevels(nodes, edges) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const incoming = new Map(nodes.map((node) => [node.id, 0]));
  const outgoing = new Map(nodes.map((node) => [node.id, []]));
  for (const edge of edges) {
    if (!byId.has(edge.source) || !byId.has(edge.target)) continue;
    incoming.set(edge.target, (incoming.get(edge.target) || 0) + 1);
    outgoing.get(edge.source).push(edge.target);
  }
  const levels = [];
  const seen = new Set();
  let frontier = nodes.filter((node) => !incoming.get(node.id));
  if (!frontier.length) frontier = [nodes[0]];
  while (frontier.length) {
    levels.push(frontier);
    const next = [];
    for (const node of frontier) {
      seen.add(node.id);
      for (const target of outgoing.get(node.id) || []) {
        if (!seen.has(target)) next.push(byId.get(target));
      }
    }
    frontier = uniqueNodes(next);
  }
  const rest = nodes.filter((node) => !seen.has(node.id));
  if (rest.length) levels.push(rest);
  return levels;
}

function entitySection(title, type, items) {
  if (!items.length) return "";
  return `
    <div class="detail-block entity-section">
      <h5>${escapeHtml(title)} ${items.length}</h5>
      <div class="entity-list">
        ${items.slice(0, 16).map((item, position) => `
          <button class="entity-button" data-entity="${type}:${position}">
            ${escapeHtml(truncate(entityTitle(type, item), 72))}
          </button>
        `).join("")}
      </div>
    </div>
  `;
}

function detailRow(label, value) {
  const text = value === undefined || value === null || value === "" ? "无" : String(value);
  return `<div class="detail-row"><b>${escapeHtml(label)}</b><span>${escapeHtml(text)}</span></div>`;
}

function detailBlock(title, content) {
  return `<div class="detail-block"><h5>${escapeHtml(title)}</h5>${content}</div>`;
}

async function copyClause(mode) {
  if (!activeClause) return;
  const title = `${activeClause.number || ""} ${activeClause.title || "条款"}`.trim();
  const content = activeClause.content || activeClause.title || "";
  const text = mode === "markdown"
    ? `### ${title}\n\n**所属标准：** ${activeClause.code}\n\n${content}`
    : content;
  try {
    await navigator.clipboard.writeText(text);
    flashCopyStatus(mode === "markdown" ? "已复制 Markdown" : "已复制条款原文");
  } catch {
    flashCopyStatus("浏览器限制了剪贴板，请手动选中文本复制");
  }
}

function flashCopyStatus(message) {
  const box = document.getElementById("relationCount");
  const previous = box.textContent;
  box.textContent = message;
  setTimeout(() => {
    if (activeClause) box.textContent = previous;
  }, 1600);
}

function graphNode(id, type, label, sub) {
  return { id, type, label: label || TYPE_LABELS[type] || type, sub };
}

function entityId(type, item) {
  return item.id || `${type}-${stableHash(entityTitle(type, item))}`;
}

function entityTitle(type, item) {
  if (type === "Term") return item.name || "术语";
  if (type === "Requirement") return item.text || "规范要求";
  if (type === "Indicator") return `${item.name || "指标"} ${item.operator || ""} ${item.value || ""}${item.unit || ""}`.trim();
  if (type === "Method") return item.name || item.description || "方法";
  if (type === "StandardObject") return item.name || item.title || "适用对象";
  return item.title || item.name || item.text || type;
}

function relationLabel(type) {
  return {
    Term: "MENTIONS_TERM",
    Requirement: "HAS_REQUIREMENT",
    Indicator: "HAS_INDICATOR",
    Method: "USES_METHOD",
    StandardObject: "APPLIES_TO",
  }[type] || "RELATED_TO";
}

function appendToMap(map, key, value) {
  if (!map.has(key)) map.set(key, []);
  map.get(key).push(value);
}

function clauseKey(item) {
  return `${item.code}::${item.clause_number || ""}`;
}

function compareNumber(a, b) {
  return String(a.number || "").localeCompare(String(b.number || ""), "zh-CN", { numeric: true });
}

function groupBy(items, field) {
  return items.reduce((groups, item) => {
    const key = item[field] || "Other";
    groups[key] = groups[key] || [];
    groups[key].push(item);
    return groups;
  }, {});
}

function uniqueByKey(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = `${item.type}:${item.code}:${item.title}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function uniqueNodes(nodes) {
  const seen = new Set();
  return nodes.filter((node) => {
    if (!node || seen.has(node.id)) return false;
    seen.add(node.id);
    return true;
  });
}

function normalizeType(type) {
  return {
    标准: "StandardDocument",
    章节: "Chapter",
    条款: "Clause",
    术语: "Term",
    要求: "Requirement",
    指标: "Indicator",
    方法: "Method",
  }[type] || type || "Clause";
}

function truncate(value, length) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}

function highlightText(value, keyword) {
  const text = String(value || "");
  if (!keyword) return escapeHtml(text);
  const escaped = escapeHtml(text);
  const safeKeyword = escapeHtml(keyword);
  return escaped.replaceAll(safeKeyword, `<mark>${safeKeyword}</mark>`);
}

function stableHash(value) {
  let hash = 0;
  const text = String(value || "");
  for (let i = 0; i < text.length; i += 1) hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
  return Math.abs(hash).toString(36);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}
