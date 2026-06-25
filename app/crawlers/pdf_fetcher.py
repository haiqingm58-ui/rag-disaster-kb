from __future__ import annotations

import io

from app.crawlers.html_fetcher import FetchOptions, HtmlFetcher


class PdfFetcher(HtmlFetcher):
    def __init__(self, options: FetchOptions | None = None) -> None:
        super().__init__(options)

    def fetch_pdf_text(self, url: str) -> str:
        if not self.can_fetch(url):
            raise RuntimeError(f"robots.txt 不允许采集 PDF: {url}")
        import requests

        response = requests.get(url, headers={"User-Agent": self.options.user_agent}, timeout=self.options.timeout)
        response.raise_for_status()
        try:
            from pypdf import PdfReader
        except Exception as exc:
            raise RuntimeError("服务器未安装 pypdf，暂时无法解析 PDF 预警文件。") from exc

        reader = PdfReader(io.BytesIO(response.content))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages).strip()
