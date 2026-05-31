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

const TOPICS = [
  { name: "滑坡", keywords: ["滑坡", "边坡", "抗滑", "稳定", "勘查", "防治"] },
  { name: "暴雨", keywords: ["暴雨", "降雨", "雨量", "灾害等级"] },
  { name: "风险评估", keywords: ["风险", "危险性", "评估", "评价", "承灾体"] },
  { name: "监测", keywords: ["监测", "预警", "观测", "位移", "变形"] },
];

const REQUIRED_CODES = [
  "GB/T 32864-2016",
  "GB/T 38509-2020",
  "T/CAGHP 002-2018",
  "GB/T 4012-2021",
  "GB/T 33680-2017",
  "GB/T 44011.1-2024",
];

let graphData = null;
let searchIndex = [];
let state = {
  activeStandard: null,
  activeChapter: null,
  activeClause: null,
};

const by = {
  standardCode: new Map(),
  chaptersByCode: new Map(),
  clausesByChapter: new Map(),
  clausesByCode: new Map(),
  clauseById: new Map(),
  termsByClause: new Map(),
  requirementsByClause: new Map(),
  indicatorsByClause: new Map(),
  methodsByClause: new Map(),
  searchItems: [],
};

document.addEventListener("DOMContentLoaded", async () => {
  try {
    graphData = await loadJson("data/graph_data.json", "graphDataFrame");
    searchIndex = await loadJson("data/search_index.json", "searchDataFrame");
    buildIndexes();
    renderHeader();
    renderLegend();
    renderStandards();
    renderTopics();
    bindSearch();
    selectStandard(REQUIRED_CODES[0]);
    selectTopic(TOPICS[0]);
  } catch (error) {
    document.body.insertAdjacentHTML(
      "afterbegin",
      `<div class="load-error"><strong>数据加载失败</strong><br>${escapeHtml(error.message)}<br>请确认 docs/data/graph_data.json 和 docs/data/search_index.json 存在。</div>`,
    );
  }
});

async function loadJson(path, frameId) {
  try {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path} HTTP ${response.status}`);
    return await response.json();
  } catch (fetchError) {
    return new Promise((resolve, reject) => {
      const frame = document.getElementById(frameId);
      if (!frame) {
        reject(fetchError);
        return;
      }
      const readFrame = () => {
        try {
          const text = frame.contentDocument?.body?.innerText || frame.contentWindow?.document?.body?.innerText || "";
          if (!text.trim()) throw fetchError;
          resolve(JSON.parse(text));
        } catch (frameError) {
          reject(frameError);
        }
      };
      if (frame.contentDocument?.readyState === "complete") readFrame();
      else frame.addEventListener("load", readFrame, { once: true });
      setTimeout(() => reject(fetchError), 4000);
    });
  }
}

function buildIndexes() {
  for (const standard of graphData.standards || []) {
    by.standardCode.set(standard.code, standard);
  }

  for (const code of REQUIRED_CODES) {
    by.chaptersByCode.set(code, []);
    by.clausesByCode.set(code, []);
  }

  for (const chapter of graphData.chapters || []) {
    const chapters = by.chaptersByCode.get(chapter.code) || [];
    chapters.push(chapter);
    by.chaptersByCode.set(chapter.code, chapters);
  }

  for (const clause of graphData.clauses || []) {
    by.clauseById.set(clause.id, clause);
    const clauses = by.clausesByCode.get(clause.code) || [];
    clauses.push(clause);
    by.clausesByCode.set(clause.code, clauses);
  }

  for (const [code, chapters] of by.chaptersByCode) {
    chapters.sort(compareNumber);
    const chapterByNumber = new Map(chapters.map((chapter) => [chapter.number, chapter]));
    const clauses = by.clausesByCode.get(code) || [];
    clauses.sort(compareNumber);
    for (const clause of clauses) {
      const numberChapterId = chapterByNumber.get(String(clause.number || "").split(".")[0])?.id;
      const chapterId = numberChapterId || clause.chapter_id || "unassigned";
      const group = by.clausesByChapter.get(chapterId) || [];
      group.push(clause);
      by.clausesByChapter.set(chapterId, group);
    }
  }

  indexByClauseId(graphData.terms || [], by.termsByClause, "source_clause_id");
  indexByClauseNumber(graphData.requirements || [], by.requirementsByClause);
  indexByClauseNumber(graphData.indicators || [], by.indicatorsByClause);
  indexByClauseNumber(graphData.methods || [], by.methodsByClause);
  by.searchItems = buildSearchItems();
}

function indexByClauseId(items, target, field) {
  for (const item of items) {
    if (!item[field]) continue;
    const group = target.get(item[field]) || [];
    group.push(item);
    target.set(item[field], group);
  }
}

function indexByClauseNumber(items, target) {
  for (const item of items) {
    const key = `${item.code}::${item.clause_number || ""}`;
    const group = target.get(key) || [];
    group.push(item);
    target.set(key, group);
  }
}

function buildSearchItems() {
  const items = [];
  for (const standard of graphData.standards || []) {
    items.push({
      type: "StandardDocument",
      code: standard.code,
      title: `${standard.code} ${standard.title}`,
      text: `${standard.code} ${standard.title}`,
      payload: standard,
    });
  }
  for (const chapter of graphData.chapters || []) {
    items.push({
      type: "Chapter",
      code: chapter.code,
      title: `${chapter.number} ${chapter.title}`,
      text: `${chapter.code} ${chapter.number} ${chapter.title}`,
      payload: chapter,
    });
  }
  for (const clause of graphData.clauses || []) {
    items.push({
      type: "Clause",
      code: clause.code,
      title: `${clause.number} ${clause.title || clause.content || ""}`,
      text: `${clause.code} ${clause.number} ${clause.title || ""} ${clause.content || ""}`,
      payload: clause,
    });
  }
  for (const term of graphData.terms || []) {
    items.push({
      type: "Term",
      code: term.code,
      title: term.name,
      text: `${term.code} ${term.name} ${term.definition || ""}`,
      payload: term,
    });
  }
  for (const requirement of graphData.requirements || []) {
    items.push({
      type: "Requirement",
      code: requirement.code,
      title: requirement.text,
      text: `${requirement.code} ${requirement.clause_number || ""} ${requirement.text || ""}`,
      payload: requirement,
    });
  }
  for (const indicator of graphData.indicators || []) {
    items.push({
      type: "Indicator",
      code: indicator.code,
      title: `${indicator.name || ""} ${indicator.operator || ""} ${indicator.value || ""}${indicator.unit || ""}`,
      text: `${indicator.code} ${indicator.clause_number || ""} ${indicator.name || ""} ${indicator.operator || ""} ${indicator.value || ""} ${indicator.unit || ""}`,
      payload: indicator,
    });
  }
  for (const method of graphData.methods || []) {
    items.push({
      type: "Method",
      code: method.code,
      title: method.name,
      text: `${method.code} ${method.clause_number || ""} ${method.name || ""} ${method.description || ""}`,
      payload: method,
    });
  }
  for (const indexed of searchIndex || []) {
    if (indexed.text && indexed.code) {
      items.push({
        type: normalizeSearchType(indexed.type),
        code: indexed.code,
        title: indexed.title || indexed.text,
        text: indexed.text,
        payload: indexed,
      });
    }
  }
  return items;
}

function normalizeSearchType(type) {
  const map = {
    标准: "StandardDocument",
    章节: "Chapter",
    条款: "Clause",
    术语: "Term",
    要求: "Requirement",
    指标: "Indicator",
    方法: "Method",
  };
  return map[type] || type || "Clause";
}

function renderHeader() {
  const counts = Object.fromEntries((graphData.node_counts || []).map((item) => [item.type, item.count]));
  document.getElementById("headerStats").innerHTML = [
    ["标准", graphData.standards?.length || 0],
    ["章节", graphData.chapters?.length || counts.Chapter || 0],
    ["条款", graphData.clauses?.length || counts.Clause || 0],
    ["实体", (counts.Term || 0) + (counts.Requirement || 0) + (counts.Indicator || 0) + (counts.Method || 0)],
  ]
    .map(([label, value]) => `<div class="stat-pill"><strong>${value}</strong><span>${label}</span></div>`)
    .join("");
  document.getElementById("generatedAt").textContent = graphData.generated_at ? `生成时间：${graphData.generated_at}` : "";
}

function renderLegend() {
  document.getElementById("legend").innerHTML = Object.entries(TYPE_LABELS)
    .map(([type, label]) => `<span class="legend-item"><i class="legend-dot" style="background:${COLORS[type]}"></i>${type} ${label}</span>`)
    .join("");
}

function renderStandards() {
  const grid = document.getElementById("standardGrid");
  grid.innerHTML = REQUIRED_CODES.map((code) => {
    const standard = by.standardCode.get(code);
    if (!standard) return "";
    return `
      <button class="standard-card" data-code="${escapeAttr(code)}">
        <strong>${escapeHtml(standard.code)}</strong>
        <h3>${escapeHtml(standard.title)}</h3>
        <div class="card-stats">
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
  grid.querySelectorAll(".standard-card").forEach((card) => {
    card.addEventListener("click", () => {
      selectStandard(card.dataset.code);
      document.getElementById("single").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function selectStandard(code) {
  const standard = by.standardCode.get(code);
  if (!standard) return;
  state.activeStandard = standard;
  state.activeChapter = null;
  state.activeClause = null;
  document.querySelectorAll(".standard-card").forEach((card) => card.classList.toggle("active", card.dataset.code === code));
  document.getElementById("activeStandardTitle").textContent = `${standard.code}`;
  document.getElementById("activeStandardMeta").textContent = standard.title;
  renderChapterList(standard.code);
  renderStandardGraph(standard);
  renderDetail(standard, "StandardDocument");
}

function renderChapterList(code) {
  const chapters = by.chaptersByCode.get(code) || [];
  document.getElementById("chapterList").innerHTML = chapters
    .map((chapter) => `
      <button class="list-button" data-id="${escapeAttr(chapter.id)}">
        ${escapeHtml(chapter.number)} ${escapeHtml(chapter.title)}
        <small>${(by.clausesByChapter.get(chapter.id) || []).length} 个条款</small>
      </button>
    `)
    .join("");
  document.querySelectorAll("#chapterList .list-button").forEach((button) => {
    button.addEventListener("click", () => selectChapter(button.dataset.id));
  });
}

function selectChapter(chapterId) {
  const chapter = (by.chaptersByCode.get(state.activeStandard.code) || []).find((item) => item.id === chapterId);
  if (!chapter) return;
  state.activeChapter = chapter;
  state.activeClause = null;
  document.querySelectorAll("#chapterList .list-button").forEach((button) => button.classList.toggle("active", button.dataset.id === chapterId));
  renderChapterGraph(chapter);
  renderDetail(chapter, "Chapter");
}

function selectClause(clauseId) {
  const clause = by.clauseById.get(clauseId);
  if (!clause) return;
  state.activeClause = clause;
  renderClauseGraph(clause);
  renderDetail(clause, "Clause");
}

function renderStandardGraph(standard) {
  const chapters = (by.chaptersByCode.get(standard.code) || []).slice(0, 119);
  const nodes = [
    makeNode(standard.standard_id, "StandardDocument", standard.code, standard.title, standard),
    ...chapters.map((chapter) => makeNode(chapter.id, "Chapter", `${chapter.number} ${chapter.title}`, "点击查看条款", chapter)),
  ];
  const edges = chapters.map((chapter) => ({ source: standard.standard_id, target: chapter.id, label: "HAS_CHAPTER" }));
  renderGraph("graphStage", nodes, edges, { title: `${standard.code} 章节图谱`, counterId: "nodeCounter" });
}

function renderChapterGraph(chapter) {
  const clauses = (by.clausesByChapter.get(chapter.id) || []).slice(0, 119);
  const nodes = [
    makeNode(chapter.id, "Chapter", `${chapter.number} ${chapter.title}`, state.activeStandard.code, chapter),
    ...clauses.map((clause) => makeNode(clause.id, "Clause", `${clause.number} ${clause.title || truncate(clause.content, 28)}`, "点击查看关联实体", clause)),
  ];
  const edges = clauses.map((clause) => ({ source: chapter.id, target: clause.id, label: "HAS_CLAUSE" }));
  renderGraph("graphStage", nodes, edges, { title: `${chapter.number} ${chapter.title}`, counterId: "nodeCounter" });
}

function renderClauseGraph(clause) {
  const related = getRelatedEntities(clause);
  const nodes = [makeNode(clause.id, "Clause", `${clause.number} ${clause.title || "条款"}`, truncate(clause.content, 42), clause)];
  const edges = [];
  for (const [type, items] of Object.entries(related)) {
    for (const item of items.slice(0, 24)) {
      const id = entityId(type, item);
      nodes.push(makeNode(id, type, entityTitle(type, item), TYPE_LABELS[type], item));
      edges.push({ source: clause.id, target: id, label: relationLabel(type) });
    }
  }
  renderGraph("graphStage", nodes.slice(0, 120), edges.filter((edge) => nodes.some((node) => node.id === edge.target)), {
    title: `${clause.number} 条款关联图谱`,
    counterId: "nodeCounter",
  });
}

function getRelatedEntities(clause) {
  const key = `${clause.code}::${clause.number}`;
  return {
    Term: by.termsByClause.get(clause.id) || [],
    Requirement: by.requirementsByClause.get(key) || [],
    Indicator: by.indicatorsByClause.get(key) || [],
    Method: by.methodsByClause.get(key) || [],
    StandardObject: [],
  };
}

function renderGraph(stageId, nodes, edges, options = {}) {
  document.getElementById(options.counterId || "nodeCounter").textContent = `${nodes.length} 节点`;
  if (options.title) {
    const titleEl = stageId === "topicStage" ? document.getElementById("topicTitle") : document.getElementById("graphTitle");
    titleEl.textContent = options.title;
  }

  const stage = document.getElementById(stageId);
  if (!nodes.length) {
    stage.innerHTML = `<div class="muted">没有可展示的节点。</div>`;
    return;
  }

  const levels = layoutLevels(nodes, edges);
  const colWidth = 240;
  const rowHeight = 82;
  const width = Math.max(760, levels.length * colWidth + 80);
  const height = Math.max(320, Math.max(...levels.map((level) => level.length), 1) * rowHeight + 80);
  const positions = new Map();

  levels.forEach((level, levelIndex) => {
    const totalHeight = (level.length - 1) * rowHeight;
    level.forEach((node, rowIndex) => {
      positions.set(node.id, {
        x: 40 + levelIndex * colWidth,
        y: 40 + (height - 80 - totalHeight) / 2 + rowIndex * rowHeight,
      });
    });
  });

  const edgeMarkup = edges
    .map((edge) => {
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      if (!source || !target) return "";
      const x1 = source.x + 174;
      const y1 = source.y + 26;
      const x2 = target.x;
      const y2 = target.y + 26;
      const mid = (x1 + x2) / 2;
      return `
        <path class="graph-edge" d="M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}" fill="none" marker-end="url(#arrow)"></path>
        <text class="graph-edge-label" x="${mid - 38}" y="${(y1 + y2) / 2 - 4}">${escapeHtml(edge.label)}</text>
      `;
    })
    .join("");

  const nodeMarkup = nodes
    .map((node) => {
      const pos = positions.get(node.id);
      const fill = COLORS[node.type] || "#64748b";
      return `
        <g class="graph-node" data-id="${escapeAttr(node.id)}" transform="translate(${pos.x}, ${pos.y})">
          <rect width="174" height="52" rx="8" fill="${fill}"></rect>
          <text x="12" y="22">${escapeHtml(truncate(node.label, 17))}</text>
          <text class="sub" x="12" y="39">${escapeHtml(truncate(node.sub || TYPE_LABELS[node.type] || node.type, 20))}</text>
        </g>
      `;
    })
    .join("");

  stage.innerHTML = `
    <svg class="graph-svg" viewBox="0 0 ${width} ${height}" role="img">
      <defs>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
          <path d="M 0 0 L 8 4 L 0 8 z" fill="#b8c7d9"></path>
        </marker>
      </defs>
      ${edgeMarkup}
      ${nodeMarkup}
    </svg>
  `;

  stage.querySelectorAll(".graph-node").forEach((element) => {
    const node = nodes.find((item) => item.id === element.dataset.id);
    element.addEventListener("click", () => handleGraphNodeClick(node));
  });
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
  const roots = nodes.filter((node) => !incoming.get(node.id));
  const levels = [];
  const seen = new Set();
  let frontier = roots.length ? roots : [nodes[0]];
  while (frontier.length) {
    levels.push(frontier);
    const next = [];
    for (const node of frontier) {
      seen.add(node.id);
      for (const target of outgoing.get(node.id) || []) {
        if (!seen.has(target)) next.push(byId.get(target));
      }
    }
    frontier = uniqueById(next);
  }
  const rest = nodes.filter((node) => !seen.has(node.id));
  if (rest.length) levels.push(rest);
  return levels;
}

function handleGraphNodeClick(node) {
  if (!node) return;
  if (node.type === "StandardDocument") selectStandard(node.payload.code);
  else if (node.type === "Chapter") selectChapter(node.payload.id);
  else if (node.type === "Clause") selectClause(node.payload.id);
  else renderDetail(node.payload, node.type);
}

function renderDetail(item, type) {
  const detail = document.getElementById("detailBox");
  detail.classList.remove("muted");
  if (type === "StandardDocument") {
    detail.innerHTML = `
      <h4>${escapeHtml(item.code)} ${escapeHtml(item.title)}</h4>
      ${detailRow("章节数", item.chapters)}
      ${detailRow("条款数", item.clauses)}
      ${detailRow("术语数", item.terms)}
      ${detailRow("要求数", item.requirements)}
      ${detailRow("指标数", item.indicators)}
    `;
    return;
  }
  if (type === "Chapter") {
    const clauses = by.clausesByChapter.get(item.id) || [];
    detail.innerHTML = `
      <h4>${escapeHtml(item.number)} ${escapeHtml(item.title)}</h4>
      ${detailRow("所属标准", item.code)}
      ${detailRow("条款数量", clauses.length)}
      <div class="entity-group"><b>条款</b><div class="entity-list">
      ${clauses.slice(0, 30).map((clause) => `<button class="entity-button" data-clause="${escapeAttr(clause.id)}">${escapeHtml(clause.number)} ${escapeHtml(truncate(clause.title || clause.content, 46))}</button>`).join("")}
      </div></div>
    `;
    detail.querySelectorAll("[data-clause]").forEach((button) => button.addEventListener("click", () => selectClause(button.dataset.clause)));
    return;
  }
  if (type === "Clause") {
    const related = getRelatedEntities(item);
    detail.innerHTML = `
      <h4>${escapeHtml(item.number)} ${escapeHtml(item.title || "条款")}</h4>
      ${detailRow("所属标准", item.code)}
      ${detailRow("正文", item.content || item.title || "")}
      ${entitySection("术语", related.Term, "Term")}
      ${entitySection("规范要求", related.Requirement, "Requirement")}
      ${entitySection("指标参数", related.Indicator, "Indicator")}
      ${entitySection("方法", related.Method, "Method")}
    `;
    detail.querySelectorAll("[data-entity]").forEach((button) => {
      const [entityType, index] = button.dataset.entity.split(":");
      renderDetail(related[entityType][Number(index)], entityType);
    });
    return;
  }
  detail.innerHTML = `
    <h4>${escapeHtml(TYPE_LABELS[type] || type)}：${escapeHtml(entityTitle(type, item))}</h4>
    ${Object.entries(item)
      .filter(([key]) => !["id"].includes(key))
      .map(([key, value]) => detailRow(key, value))
      .join("")}
  `;
}

function entitySection(title, items, type) {
  if (!items.length) return "";
  return `
    <div class="entity-group">
      <b>${title} ${items.length}</b>
      <div class="entity-list">
      ${items.slice(0, 12).map((item, index) => `
        <button class="entity-button" data-entity="${type}:${index}">
          ${escapeHtml(truncate(entityTitle(type, item), 60))}
        </button>
      `).join("")}
      </div>
    </div>
  `;
}

function detailRow(label, value) {
  const safe = value === undefined || value === null || value === "" ? "无" : value;
  return `<div class="detail-row"><b>${escapeHtml(label)}</b><span>${escapeHtml(String(safe))}</span></div>`;
}

function renderTopics() {
  document.getElementById("topicActions").innerHTML = TOPICS.map((topic) => `<button class="topic-button" data-topic="${escapeAttr(topic.name)}">${escapeHtml(topic.name)}</button>`).join("");
  document.querySelectorAll(".topic-button").forEach((button) => {
    button.addEventListener("click", () => selectTopic(TOPICS.find((topic) => topic.name === button.dataset.topic)));
  });
}

function selectTopic(topic) {
  if (!topic) return;
  document.querySelectorAll(".topic-button").forEach((button) => button.classList.toggle("active", button.dataset.topic === topic.name));
  const matches = by.searchItems
    .filter((item) => ["Clause", "Term", "Requirement", "Indicator", "Method"].includes(item.type))
    .filter((item) => topic.keywords.some((keyword) => item.text.includes(keyword)))
    .slice(0, 79);
  const root = makeNode(`topic-${topic.name}`, "StandardDocument", `${topic.name}专题`, "Topic", topic);
  const nodes = [root];
  const edges = [];
  for (const item of matches) {
    const id = `${item.type}-${stableKey(item.title)}-${nodes.length}`;
    nodes.push(makeNode(id, item.type, item.title, item.code, item.payload));
    edges.push({ source: root.id, target: id, label: "RELATED_TO" });
  }
  renderGraph("topicStage", nodes, edges, { title: `${topic.name}专题`, counterId: "topicCounter" });
  document.getElementById("topicDetail").innerHTML = `
    ${detailRow("关键词", topic.keywords.join("、"))}
    ${detailRow("展示节点", nodes.length)}
    ${detailRow("说明", "专题图谱从真实图谱文本中按关键词抽取，控制在 80 个节点以内，便于截图和浏览。")}
  `;
}

function bindSearch() {
  const input = document.getElementById("searchInput");
  input.addEventListener("input", () => {
    const keyword = input.value.trim();
    const box = document.getElementById("searchResults");
    if (!keyword) {
      box.innerHTML = `<p class="muted">输入关键词后显示匹配结果。</p>`;
      return;
    }
    const results = uniqueSearchResults(by.searchItems.filter((item) => item.text.includes(keyword))).slice(0, 40);
    box.innerHTML = results.length
      ? results.map((item, index) => `
          <button class="search-result" data-index="${index}">
            <span class="tag type-${escapeAttr(item.type)}">${escapeHtml(TYPE_LABELS[item.type] || item.type)}</span>
            <strong>${escapeHtml(truncate(item.title, 92))}</strong>
            <small>${escapeHtml(item.code || "")}</small>
          </button>
        `).join("")
      : `<p class="muted">没有找到匹配结果。</p>`;
    box.querySelectorAll(".search-result").forEach((button) => {
      button.addEventListener("click", () => openSearchResult(results[Number(button.dataset.index)]));
    });
  });
  document.getElementById("searchResults").innerHTML = `<p class="muted">输入关键词后显示匹配结果。</p>`;
}

function openSearchResult(item) {
  selectStandard(item.code);
  if (item.type === "Chapter") {
    selectChapter(item.payload.id);
  } else if (item.type === "Clause") {
    const chapterId = item.payload.chapter_id || findChapterForClause(item.payload)?.id;
    if (chapterId) state.activeChapter = findChapterForClause(item.payload);
    selectClause(item.payload.id);
  } else if (["Term", "Requirement", "Indicator", "Method"].includes(item.type)) {
    const clause = findClauseForEntity(item.type, item.payload);
    if (clause) selectClause(clause.id);
    renderDetail(item.payload, item.type);
  }
  document.getElementById("single").scrollIntoView({ behavior: "smooth", block: "start" });
}

function findChapterForClause(clause) {
  const number = String(clause.number || "").split(".")[0];
  const chapters = by.chaptersByCode.get(clause.code) || [];
  return chapters.find((chapter) => chapter.number === number) || chapters.find((chapter) => chapter.id === clause.chapter_id);
}

function findClauseForEntity(type, item) {
  if (type === "Term" && item.source_clause_id) return by.clauseById.get(item.source_clause_id);
  if (item.clause_number) {
    return (by.clausesByCode.get(item.code) || []).find((clause) => clause.number === item.clause_number);
  }
  return null;
}

function makeNode(id, type, label, sub, payload) {
  return { id, type, label: label || TYPE_LABELS[type] || type, sub, payload };
}

function entityId(type, item) {
  return item.id || `${type}-${item.code || ""}-${item.clause_number || ""}-${stableKey(entityTitle(type, item))}`;
}

function entityTitle(type, item) {
  if (type === "Term") return item.name || item.title || "术语";
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

function compareNumber(a, b) {
  return String(a.number || "").localeCompare(String(b.number || ""), "zh-CN", { numeric: true });
}

function uniqueById(items) {
  const seen = new Set();
  return items.filter((item) => {
    if (!item || seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

function uniqueSearchResults(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = `${item.type}:${item.code}:${item.title}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function stableKey(value) {
  let hash = 0;
  const text = String(value || "");
  for (let i = 0; i < text.length; i += 1) hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
  return Math.abs(hash).toString(36);
}

function truncate(value, length) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > length ? `${text.slice(0, length - 1)}…` : text;
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
