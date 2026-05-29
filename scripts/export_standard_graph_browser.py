#!/usr/bin/env python3
"""Export complete knowledge graph as a self-contained HTML browser.

Usage:
  python scripts/export_standard_graph_browser.py
  python scripts/export_standard_graph_browser.py --output-dir exports/my_browser
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.graph.common.neo4j_client import get_session, neo4j_config


def _fetch_graph(session) -> dict:
    """Fetch complete graph data for browser export."""
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "standards": [], "chapters": [], "clauses": [], "terms": [],
        "requirements": [], "indicators": [], "methods": [], "objects": [],
        "relationships": [], "node_counts": [],
    }

    # Standards with stats
    for rec in session.run("MATCH (s:StandardDocument) RETURN s ORDER BY s.code"):
        s = rec["s"]; sid = s["standard_id"]
        stats = {}
        for label, cypher in [
            ("chapters", "MATCH (s {standard_id:$sid})-[:HAS_CHAPTER]->(c:Chapter) RETURN count(c) AS n"),
            ("clauses", "MATCH (s {standard_id:$sid})-[:HAS_CLAUSE]->(c:Clause) RETURN count(c) AS n"),
            ("terms", "MATCH (s {standard_id:$sid})-[:DEFINES]->(t:Term) RETURN count(t) AS n"),
            ("requirements", "MATCH (n:Requirement {standard_id:$sid}) RETURN count(n) AS n"),
            ("indicators", "MATCH (n:Indicator {standard_id:$sid}) RETURN count(n) AS n"),
            ("methods", "MATCH (n:Method {standard_id:$sid}) RETURN count(n) AS n"),
            ("objects", "MATCH (n:StandardObject {standard_id:$sid}) RETURN count(n) AS n"),
        ]:
            stats[label] = session.run(cypher, {"sid": sid}).single()["n"]

        data["standards"].append({
            "standard_id": sid,
            "code": s.get("code", ""), "title": s.get("title", ""),
            "industry": s.get("industry", ""),
            "source_file": Path(s.get("source_file", "")).name,
            **stats,
        })

    # Chapters
    for rec in session.run(
        "MATCH (s:StandardDocument)-[:HAS_CHAPTER]->(c:Chapter) "
        "RETURN s.code AS code, c.chapter_number AS num, c.title AS title, c.chapter_id AS cid "
        "ORDER BY s.code, toInteger(c.chapter_number)"):
        data["chapters"].append({"code": rec["code"], "number": rec["num"],
                                  "title": rec["title"] or "", "id": rec["cid"]})

    # Clauses (all)
    for rec in session.run(
        "MATCH (s:StandardDocument)-[:HAS_CLAUSE]->(c:Clause) "
        "RETURN s.code AS code, c.clause_number AS num, c.title AS title, "
        "c.content AS content, c.clause_id AS cid, c.chapter_id AS ch_id, c.level AS level "
        "ORDER BY s.code, c.clause_number"):
        data["clauses"].append({
            "code": rec["code"], "number": rec["num"],
            "title": (rec["title"] or "")[:200],
            "content": (rec["content"] or "")[:2000],
            "id": rec["cid"], "chapter_id": rec["ch_id"], "level": rec["level"],
        })

    # Terms
    for rec in session.run(
        "MATCH (s:StandardDocument)-[:DEFINES]->(t:Term) "
        "RETURN s.code AS code, t.name AS name, t.term_id AS tid, "
        "t.definition AS def, t.source_clause_id AS scid ORDER BY s.code, t.name"):
        data["terms"].append({
            "code": rec["code"], "name": rec["name"], "id": rec["tid"],
            "definition": (rec["def"] or "")[:500], "source_clause_id": rec["scid"],
        })

    # Requirements
    for rec in session.run(
        "MATCH (s:StandardDocument)-[:HAS_CLAUSE]->(cl:Clause)-[:HAS_REQUIREMENT]->(r:Requirement) "
        "RETURN s.code AS code, cl.clause_number AS cnum, r.text AS text, "
        "r.obligation AS obl, r.requirement_id AS rid ORDER BY s.code, cl.clause_number"):
        data["requirements"].append({
            "code": rec["code"], "clause_number": rec["cnum"],
            "text": (rec["text"] or "")[:500], "obligation": rec["obl"] or "", "id": rec["rid"],
        })

    # Indicators
    for rec in session.run(
        "MATCH (s:StandardDocument)-[:HAS_CLAUSE]->(cl:Clause)-[:HAS_INDICATOR]->(i:Indicator) "
        "RETURN s.code AS code, cl.clause_number AS cnum, i.name AS name, "
        "i.value AS value, i.operator AS op, i.unit AS unit ORDER BY s.code"):
        data["indicators"].append({
            "code": rec["code"], "clause_number": rec["cnum"],
            "name": rec["name"] or "", "value": rec["value"] or "",
            "operator": rec["op"] or "", "unit": rec["unit"] or "",
        })

    # Methods
    for rec in session.run(
        "MATCH (s:StandardDocument)-[:HAS_CLAUSE]->(cl:Clause)-[:USES_METHOD]->(m:Method) "
        "RETURN s.code AS code, cl.clause_number AS cnum, m.name AS name, m.description AS desc"
    ):
        data["methods"].append({
            "code": rec["code"], "clause_number": rec["cnum"],
            "name": rec["name"] or "", "description": (rec["desc"] or "")[:300],
        })

    # Objects
    for rec in session.run(
        "MATCH (s:StandardDocument)-[:HAS_CLAUSE]->(cl:Clause)-[:APPLIES_TO]->(o:StandardObject) "
        "RETURN s.code AS code, cl.clause_number AS cnum, o.name AS name, o.object_type AS otype"
    ):
        data["objects"].append({
            "code": rec["code"], "clause_number": rec["cnum"],
            "name": rec["name"] or "", "object_type": rec["otype"] or "",
        })

    # Node counts
    for rec in session.run("MATCH (n) RETURN labels(n)[0] AS t, count(n) AS c ORDER BY c DESC"):
        data["node_counts"].append({"type": rec["t"], "count": rec["c"]})

    return data


def _build_search_index(data: dict) -> list[dict]:
    """Build a search index from all graph data."""
    idx = []
    for s in data["standards"]:
        idx.append({"type": "标准", "code": s["code"], "text": f"{s['code']} {s['title']}", "title": s["title"]})
    for c in data["clauses"]:
        idx.append({"type": "条款", "code": c["code"], "number": c["number"],
                     "text": f"[{c['number']}] {c['title']} {c['content'][:200]}",
                     "title": c["title"]})
    for t in data["terms"]:
        idx.append({"type": "术语", "code": t["code"], "text": f"{t['name']}: {t['definition'][:200]}",
                     "title": t["name"]})
    for r in data["requirements"][:2000]:
        idx.append({"type": "要求", "code": r["code"], "number": r["clause_number"],
                     "text": f"[{r['clause_number']}] {r['text'][:200]}", "title": r["text"][:80]})
    for i in data["indicators"][:1000]:
        idx.append({"type": "指标", "code": i["code"], "number": i["clause_number"],
                     "text": f"{i['name']} {i['operator']} {i['value']} {i['unit']}",
                     "title": i["name"]})
    return idx


def _build_html() -> str:
    """Generate standalone HTML with embedded CSS/JS and data."""
    return r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>行业标准知识图谱浏览器</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#f5f6fa;color:#2c3e50}
.header{background:linear-gradient(135deg,#2c3e50,#3498db);color:white;padding:20px 30px}
.header h1{font-size:1.5em}.header .stats{display:flex;gap:20px;flex-wrap:wrap;margin-top:10px;font-size:.9em}
.stat{background:rgba(255,255,255,.15);padding:6px 12px;border-radius:4px}
.nav{background:white;padding:10px 30px;display:flex;gap:15px;border-bottom:1px solid #e0e0e0;flex-wrap:wrap;position:sticky;top:0;z-index:10}
.nav a,.nav button{color:#3498db;text-decoration:none;padding:6px 14px;border-radius:4px;cursor:pointer;border:1px solid #3498db;background:white;font-size:.9em}
.nav a:hover,.nav button:hover{background:#3498db;color:white}
.nav input{padding:6px 12px;border:1px solid #ddd;border-radius:4px;width:250px;font-size:.9em}
.content{padding:30px;max-width:1400px;margin:0 auto}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}
.card{background:white;border-radius:8px;padding:18px;box-shadow:0 2px 8px rgba(0,0,0,.06);cursor:pointer;transition:transform .15s;border-left:4px solid #3498db}
.card:hover{transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,.1)}
.card h3{font-size:1.05em;margin-bottom:4px}.card .code{color:#7f8c8d;font-size:.85em}
.card .meta{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px;font-size:.82em;color:#555}
.card .meta span{background:#f0f0f0;padding:2px 8px;border-radius:3px}
.tree{margin-left:20px}.tree-item{margin:3px 0;padding:4px 8px;cursor:pointer;border-radius:3px}
.tree-item:hover{background:#eef2ff}.tree-item.active{background:#3498db;color:white}
.clause-detail{background:#f9fafb;padding:16px;border-radius:6px;margin:8px 0}
.rel-badge{display:inline-block;padding:3px 10px;margin:2px;border-radius:12px;font-size:.82em}
.rel-term{background:#d5f5e3;color:#1e8449}.rel-req{background:#fdebd0;color:#b9770e}
.rel-ind{background:#d6eaf8;color:#2471a3}.rel-method{background:#e8daef;color:#6c3483}
.rel-obj{background:#fadbd8;color:#922b21}
.search-results{max-height:70vh;overflow-y:auto}
.search-item{padding:10px;border-bottom:1px solid #eee;cursor:pointer}
.search-item:hover{background:#f0f4ff}
.search-item .type{font-size:.75em;padding:2px 6px;border-radius:3px;color:white;margin-right:6px}
.type-标准{background:#e74c3c}.type-条款{background:#3498db}.type-术语{background:#2ecc71}
.type-要求{background:#e67e22}.type-指标{background:#9b59b6}
.topic-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.topic-card{background:white;border-radius:8px;padding:18px;box-shadow:0 2px 8px rgba(0,0,0,.06)}
.topic-card h3{color:#2c3e50;margin-bottom:8px}
.topic-card ul{list-style:none}.topic-card li{padding:4px 0;border-bottom:1px solid #f0f0f0;font-size:.9em}
.hidden{display:none}.back-btn{margin-bottom:16px}.loading{padding:40px;text-align:center;color:#999}
.empty-state{padding:60px;text-align:center;color:#999}.export-time{color:#bdc3c7;font-size:.8em;margin-top:30px}
@media(max-width:768px){.cards{grid-template-columns:1fr}.content{padding:15px}}
</style></head>
<body>
<div class="header">
  <h1>📚 行业标准知识图谱浏览器</h1>
  <div class="stats" id="globalStats"></div>
</div>
<div class="nav">
  <button onclick="showHome()">🏠 首页</button>
  <button onclick="showTopics()">🏷️ 专题</button>
  <input type="text" id="searchInput" placeholder="搜索术语/要求/条款..." oninput="doSearch(this.value)">
  <div id="searchResults" class="search-results hidden"></div>
</div>
<div class="content" id="mainContent"><div class="loading">加载中...</div></div>
<div class="export-time" id="exportTime" style="text-align:center"></div>
<script id="graphData" type="application/json">__DATA_PLACEHOLDER__</script>
<script>
const D=JSON.parse(document.getElementById('graphData').textContent);
const stdMap={};D.standards.forEach(s=>{stdMap[s.code]=s});
const clausesByCode={};D.clauses.forEach(c=>{if(!clausesByCode[c.code])clausesByCode[c.code]=[];clausesByCode[c.code].push(c)});
const termsByCode={};D.terms.forEach(t=>{if(!termsByCode[t.code])termsByCode[t.code]=[];termsByCode[t.code].push(t)});
const reqsByCode={};D.requirements.forEach(r=>{if(!reqsByCode[r.code])reqsByCode[r.code]=[];reqsByCode[r.code].push(r)});
const indsByCode={};D.indicators.forEach(i=>{if(!indsByCode[i.code])indsByCode[i.code]=[];indsByCode[i.code].push(i)});
const methodsByCode={};D.methods.forEach(m=>{if(!methodsByCode[m.code])methodsByCode[m.code]=[];methodsByCode[m.code].push(m)});
const objsByCode={};D.objects.forEach(o=>{if(!objsByCode[o.code])objsByCode[o.code]=[];objsByCode[o.code].push(o)});
const chByCode={};D.chapters.forEach(c=>{if(!chByCode[c.code])chByCode[c.code]=[];chByCode[c.code].push(c)});
const SI=D.search_index||[];const TOPIC_KEYWORDS={滑坡:['滑坡','崩塌','泥石流','地面塌陷','地裂缝'],暴雨:['暴雨','降水','降雨','洪水','洪涝'],风险评估:['风险评估','危险性评估','风险','危险'],监测:['监测','观测','检测','预警']};

function fmt(n){return n.toLocaleString()}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function showHome(){
  document.getElementById('searchResults').classList.add('hidden');
  let h=`<div class="cards">`;
  D.standards.forEach(s=>{h+=`<div class="card" onclick="showStandard('${esc(s.code)}')">
    <div class="code">${esc(s.code)}</div><h3>${esc(s.title)}</h3>
    <div class="meta"><span>📖 ${s.chapters}章</span><span>📝 ${s.clauses}条</span>
    <span>📘 ${s.terms||0}术语</span><span>✅ ${s.requirements||0}要求</span>
    <span>📊 ${s.indicators||0}指标</span></div></div>`});
  h+=`</div>`;
  document.getElementById('mainContent').innerHTML=h;
  document.getElementById('globalStats').innerHTML=`
    <span class="stat">标准: ${D.standards.length}</span><span class="stat">节点: ${fmt(D.node_counts.reduce((a,n)=>a+n.count,0))}</span>
    <span class="stat">条款: ${fmt(D.clauses.length)}</span><span class="stat">术语: ${fmt(D.terms.length)}</span>
    <span class="stat">要求: ${fmt(D.requirements.length)}</span><span class="stat">指标: ${fmt(D.indicators.length)}</span>`;
}

function showStandard(code){
  const s=stdMap[code];if(!s)return;
  const chs=chByCode[code]||[];const cls=clausesByCode[code]||[];
  const terms=termsByCode[code]||[];const reqs=reqsByCode[code]||[];
  const inds=indsByCode[code]||[];const mths=methodsByCode[code]||[];
  const objs=objsByCode[code]||[];
  let h=`<button class="back-btn" onclick="showHome()">← 返回首页</button>`;
  h+=`<h2>${esc(s.code)} — ${esc(s.title)}</h2>`;
  h+=`<div style="display:flex;gap:10px;flex-wrap:wrap;margin:12px 0">`;
  ['industry'].forEach(k=>{if(s[k])h+=`<span style="background:#eee;padding:4px 10px;border-radius:4px">${k}:${esc(s[k])}</span>`});
  h+=`<span>章节:${s.chapters}</span><span>条款:${s.clauses}</span><span>术语:${s.terms||0}</span><span>要求:${s.requirements||0}</span><span>指标:${s.indicators||0}</span>`;
  h+=`</div>`;

  // Chapter tree
  h+=`<h3 style="margin-top:20px">📖 章节结构</h3><div class="tree">`;
  chs.forEach(ch=>{
    h+=`<div class="tree-item" onclick="toggleClauses(this,'${esc(code)}','${esc(ch.number)}')">📁 ${esc(ch.number)} ${esc(ch.title)}</div>`;
    h+=`<div class="hidden" id="clauses-${esc(code)}-${esc(ch.number)}" style="margin-left:20px"></div>`;
  });
  h+=`</div>`;

  // Terms
  if(terms.length){h+=`<h3 style="margin-top:20px">📘 术语 (${terms.length})</h3>`;
    terms.slice(0,20).forEach(t=>{h+=`<div class="clause-detail"><strong>${esc(t.name)}</strong><br><span style="color:#666">${esc(t.definition||'')}</span></div>`});
    if(terms.length>20)h+=`<p>... 及另外 ${terms.length-20} 个术语</p>`;}

  // Requirements
  if(reqs.length){h+=`<h3 style="margin-top:20px">✅ 规范要求 (${reqs.length})</h3>`;
    reqs.slice(0,15).forEach(r=>{h+=`<div class="clause-detail"><span class="rel-badge rel-req">${esc(r.obligation||'shall')}</span> [${esc(r.clause_number)}] ${esc(r.text||'')}</div>`});
    if(reqs.length>15)h+=`<p>... 及另外 ${reqs.length-15} 条</p>`;}

  // Indicators
  if(inds.length){h+=`<h3 style="margin-top:20px">📊 指标参数 (${inds.length})</h3>`;
    inds.slice(0,15).forEach(i=>{h+=`<div class="clause-detail"><span class="rel-badge rel-ind">指标</span> ${esc(i.name)} ${esc(i.operator||'')} ${esc(i.value||'')} ${esc(i.unit||'')}</div>`});}

  // Methods
  if(mths.length){h+=`<h3 style="margin-top:20px">🔧 方法 (${mths.length})</h3>`;
    mths.slice(0,10).forEach(m=>{h+=`<div class="clause-detail"><span class="rel-badge rel-method">方法</span> ${esc(m.name)}</div>`});}

  document.getElementById('mainContent').innerHTML=h;
}

function toggleClauses(el,code,chNum){
  const div=document.getElementById('clauses-'+code+'-'+chNum);
  if(!div)return;
  if(div.classList.contains('hidden')){
    const cls=(clausesByCode[code]||[]).filter(c=>c.number.startsWith(chNum+'.'));
    let h='';cls.forEach(c=>{h+=`<div class="clause-detail"><strong>${esc(c.number)} ${esc(c.title||'')}</strong><br><span style="color:#555">${esc((c.content||'').substring(0,300))}</span></div>`});
    div.innerHTML=h||'<span style="color:#999">无子条款</span>';
    div.classList.remove('hidden');
  }else{div.classList.add('hidden')}
}

function showTopics(){
  let h=`<h2>🏷️ 专题浏览</h2><div class="topic-grid">`;
  Object.entries(TOPIC_KEYWORDS).forEach(([name,kws])=>{
    h+=`<div class="topic-card"><h3>${name}</h3><div id="topic-${name}"></div></div>`;
  });
  h+=`</div>`;
  document.getElementById('mainContent').innerHTML=h;
  Object.entries(TOPIC_KEYWORDS).forEach(([name,kws])=>{
    const terms=D.terms.filter(t=>kws.some(k=>t.name.includes(k)||(t.definition||'').includes(k))).slice(0,15);
    const reqs=D.requirements.filter(r=>kws.some(k=>(r.text||'').includes(k))).slice(0,10);
    const inds=D.indicators.filter(i=>kws.some(k=>(i.name||'').includes(k))).slice(0,10);
    const cls=D.clauses.filter(c=>kws.some(k=>(c.content||'').includes(k))).slice(0,10);
    let th=`<ul>`;
    if(cls.length)th+=`<li><strong>条款 (${cls.length})</strong></li>`+cls.map(c=>`<li style="font-size:.85em">[${esc(c.code)} ${esc(c.number)}] ${esc((c.title||c.content||'').substring(0,80))}</li>`).join('');
    if(terms.length)th+=`<li><strong>术语</strong></li>`+terms.map(t=>`<li style="font-size:.85em">${esc(t.name)}: ${esc((t.definition||'').substring(0,60))}</li>`).join('');
    if(reqs.length)th+=`<li><strong>要求</strong></li>`+reqs.map(r=>`<li style="font-size:.85em">[${esc(r.clause_number)}] ${esc((r.text||'').substring(0,80))}</li>`).join('');
    th+=`</ul>`;
    document.getElementById('topic-'+name).innerHTML=th;
  });
}

function doSearch(q){
  const div=document.getElementById('searchResults');
  if(!q||q.length<2){div.classList.add('hidden');return}
  const ql=q.toLowerCase();const results=SI.filter(si=>si.text.toLowerCase().includes(ql)).slice(0,30);
  if(!results.length){div.classList.add('hidden');return}
  let h='';results.forEach(r=>{h+=`<div class="search-item" onclick="navigateSearch('${esc(r.type)}','${esc(r.code||'')}','${esc(r.number||'')}')">
    <span class="type type-${esc(r.type)}">${esc(r.type)}</span><small>${esc(r.code||'')}</small> ${esc(r.title||r.text||'').substring(0,100)}</div>`});
  div.innerHTML=h;div.classList.remove('hidden');
}
function navigateSearch(type,code,number){
  document.getElementById('searchResults').classList.add('hidden');
  if(type==='标准'&&code)showStandard(code);
  else if(code)showStandard(code);
}

document.getElementById('exportTime').textContent='导出时间: '+D.generated_at;
showHome();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Export browser-viewable knowledge graph")
    ap.add_argument("--output-dir", default="exports/standard_kg_browser",
                    help="Output directory")
    args = ap.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    db = neo4j_config()[3]
    with get_session(db) as sess:
        data = _fetch_graph(sess)

    # Build search index
    search_index = _build_search_index(data)
    data["search_index"] = search_index

    # Save data files
    (output_dir / "graph_data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "search_index.json").write_text(
        json.dumps(search_index, ensure_ascii=False, indent=2), encoding="utf-8")

    # Generate HTML with embedded data
    html = _build_html().replace("__DATA_PLACEHOLDER__",
                                  json.dumps(data, ensure_ascii=False))
    (output_dir / "index.html").write_text(html, encoding="utf-8")

    # Summary
    total_nodes = sum(n["count"] for n in data["node_counts"])
    summary = f"""# 知识图谱浏览器导出报告

生成时间: {data['generated_at']}

## 文件
- **index.html** — 双击浏览器打开，包含完整知识图谱浏览器
- **graph_data.json** — 完整图谱数据
- **search_index.json** — 预构建搜索索引

## 功能
- 首页总览：6 篇标准卡片
- 标准详情：章节树 + 条款内容 + 术语/要求/指标/方法/对象
- 专题浏览：滑坡/暴雨/风险评估/监测
- 全文搜索：术语/要求/条款/指标

## 统计
- {len(data['standards'])} 篇标准
- {total_nodes} 节点
- {len(search_index)} 条搜索索引

## 打开方式
双击 index.html 即可在浏览器中查看。
"""
    (output_dir / "browser_export_summary.md").write_text(summary, encoding="utf-8")

    # ZIP
    zip_path = output_dir.parent / f"{output_dir.name}.zip"
    shutil.make_archive(str(zip_path.with_suffix("")), "zip",
                       output_dir.parent, output_dir.name)

    print(f"导出完成: {output_dir}")
    print(f"  index.html — 双击浏览器打开")
    print(f"  数据: {len(data['standards'])} 标准, {total_nodes} 节点")
    print(f"  搜索索引: {len(search_index)} 条")
    print(f"  ZIP: {zip_path}")


if __name__ == "__main__":
    main()
