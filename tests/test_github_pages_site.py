import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_github_pages_required_files_exist():
    assert (DOCS / "index.html").exists()
    assert (DOCS / ".nojekyll").exists()
    assert (DOCS / "data" / "graph_data.json").exists()
    assert (DOCS / "data" / "search_index.json").exists()
    assert (DOCS / "assets" / "style.css").exists()
    assert (DOCS / "assets" / "app.js").exists()


def test_index_is_clear_github_pages_entry():
    html = read_text(DOCS / "index.html")
    required = [
        "\u5730\u8d28\u707e\u5bb3\u884c\u4e1a\u6807\u51c6\u77e5\u8bc6\u56fe\u8c31",
        "\u5982\u4f55\u4f7f\u7528",
        "\u56fe\u8c31\u6a21\u5f0f",
        "\u6807\u51c6\u603b\u89c8",
        "\u5355\u7bc7\u6807\u51c6",
        "\u4e13\u9898\u56fe\u8c31",
        "\u641c\u7d22",
        "\u76f8\u5173\u6761\u6b3e\u5217\u8868",
    ]
    for text in required:
        assert text in html


def test_index_uses_relative_static_assets():
    html = read_text(DOCS / "index.html")
    assert 'href="assets/style.css"' in html
    assert 'src="assets/app.js"' in html
    assert 'src="data/graph_data.json"' in html
    assert 'src="data/search_index.json"' in html
    assert "http://" not in html
    assert "https://" not in html


def test_docs_do_not_contain_sensitive_strings():
    patterns = [
        r"\.env",
        r"API\s*Key",
        r"DEEPSEEK_API_KEY",
        r"DeepSeek",
        r"sk-[A-Za-z0-9_-]+",
        r"NEO4J_PASSWORD",
        r"/Users/",
        r"C:\\Users",
    ]
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in DOCS.rglob("*")
        if path.is_file()
    )
    for pattern in patterns:
        assert not re.search(pattern, combined), pattern


def test_app_has_expected_structure_and_default_limits():
    app = read_text(DOCS / "assets" / "app.js")
    for fn in [
        "loadData",
        "renderHome",
        "renderSchema",
        "renderStandards",
        "renderStandardDetail",
        "renderChapterDetail",
        "renderClauseDetail",
        "renderTopic",
        "performSearch",
    ]:
        assert f"function {fn}" in app
    assert ".slice(0, 120)" in app
    assert ".slice(0, 79)" in app
    assert "graphDataFrame" in read_text(DOCS / "index.html")
    assert "<script id=\"graphData\"" not in read_text(DOCS / "index.html")


def test_experience_copy_and_search_features_exist():
    app = read_text(DOCS / "assets" / "app.js")
    for text in [
        "\u6ed1\u5761",
        "\u66b4\u96e8",
        "\u98ce\u9669\u8bc4\u4f30",
        "\u76d1\u6d4b",
        "\u6297\u6ed1\u6869",
        "\u590d\u5236\u6761\u6b3e\u539f\u6587",
        "\u590d\u5236\u4e3a Markdown",
        "highlightText",
        "navigator.clipboard.writeText",
    ]:
        assert text in app


def test_six_standard_titles_are_available():
    data = json.loads((DOCS / "data" / "graph_data.json").read_text(encoding="utf-8"))
    standards = {item["code"]: item["title"] for item in data["standards"]}
    expected = {
        "GB/T 32864-2016": "\u6ed1\u5761\u9632\u6cbb\u5de5\u7a0b\u52d8\u67e5\u89c4\u8303",
        "GB/T 38509-2020": "\u6ed1\u5761\u9632\u6cbb\u8bbe\u8ba1\u89c4\u8303",
        "T/CAGHP 002-2018": "\u5730\u8d28\u707e\u5bb3\u9632\u6cbb\u57fa\u672c\u672f\u8bed",
        "GB/T 4012-2021": "\u5730\u8d28\u707e\u5bb3\u5371\u9669\u6027\u8bc4\u4f30\u89c4\u8303",
        "GB/T 33680-2017": "\u66b4\u96e8\u707e\u5bb3\u7b49\u7ea7",
        "GB/T 44011.1-2024": "\u81ea\u7136\u707e\u5bb3\u7efc\u5408\u98ce\u9669\u8bc4\u4f30\u6280\u672f\u89c4\u8303 \u7b2c1\u90e8\u5206 \u623f\u5c4b\u5efa\u7b51",
    }
    for code, title in expected.items():
        assert standards[code] == title
