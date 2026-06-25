from app.crawlers.parsers.common import parse_detail, parse_list


def test_parse_sample_html_list_and_detail():
    html = """
    <html><body>
      <a href="/warning/1.html">湖南省地质灾害气象风险黄色预警</a>
      <a href="/other.html">普通新闻</a>
    </body></html>
    """

    items = parse_list(html, "https://example.org/list/")

    assert len(items) == 1
    assert items[0].url == "https://example.org/warning/1.html"

    detail = parse_detail("<h1>长沙市山洪灾害风险预警</h1><p>长沙县有山洪风险。</p>", items[0], "https://example.org")

    assert detail["title"] == "长沙市山洪灾害风险预警"
    assert "长沙县" in detail["raw_text"]
