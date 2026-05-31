import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_github_pages_files_exist():
    assert (DOCS / "index.html").exists()
    assert (DOCS / "data" / "graph_data.json").exists()
    assert (DOCS / "data" / "search_index.json").exists()
    assert (DOCS / "assets" / "style.css").exists()
    assert (DOCS / "assets" / "app.js").exists()


def test_index_contains_required_sections():
    html = read_text(DOCS / "index.html")
    for text in ["图谱模式", "标准总览", "单篇标准", "专题图谱", "搜索"]:
        assert text in html


def test_docs_do_not_contain_sensitive_strings():
    patterns = [
        r"\.env",
        r"DEEPSEEK_API_KEY",
        r"DeepSeek",
        r"sk-[A-Za-z0-9_-]+",
        r"NEO4J_PASSWORD",
        r"/Users/",
        r"C:\\Users",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in DOCS.rglob("*") if path.is_file())
    for pattern in patterns:
        assert not re.search(pattern, combined), pattern


def test_default_node_limits_are_enforced_in_app():
    app = read_text(DOCS / "assets" / "app.js")
    assert ".slice(0, 119)" in app
    assert ".slice(0, 79)" in app
    assert "最多展示 120 个节点" in read_text(DOCS / "index.html")
    assert "最多展示 80 个节点" in read_text(DOCS / "index.html")


def test_six_standard_titles_are_available():
    data = json.loads((DOCS / "data" / "graph_data.json").read_text(encoding="utf-8"))
    standards = {item["code"]: item["title"] for item in data["standards"]}
    expected = {
        "GB/T 32864-2016": "滑坡防治工程勘查规范",
        "GB/T 38509-2020": "滑坡防治设计规范",
        "T/CAGHP 002-2018": "地质灾害防治基本术语",
        "GB/T 4012-2021": "地质灾害危险性评估规范",
        "GB/T 33680-2017": "暴雨灾害等级",
        "GB/T 44011.1-2024": "自然灾害综合风险评估技术规范 第1部分 房屋建筑",
    }
    for code, title in expected.items():
        assert standards[code] == title
