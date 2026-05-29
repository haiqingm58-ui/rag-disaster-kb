import logging
from pathlib import Path
from typing import List

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    CHUNK_SEPARATORS,
)
from src.ingestion.pdf_to_markdown import convert_pdf_to_markdown

logger = logging.getLogger(__name__)


class DocumentLoadError(Exception):
    """Document parsing failed with parser diagnostics attached."""

    def __init__(self, message: str, report: dict):
        super().__init__(message)
        self.report = report


def load_file_with_report(file_path: str) -> tuple[List[Document], dict]:
    """Load a file and report parser/fallback details for UI messages."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    report = {
        "file": str(path),
        "loader": "",
        "mineru_available": False,
        "mineru_attempted": False,
        "mineru_failed": False,
        "mineru_error": "",
        "fallback_used": False,
        "success": False,
        "pdf_to_markdown": False,
        "markdown_path": "",
    }

    if suffix == ".pdf":
        try:
            md_path, md_report = convert_pdf_to_markdown(str(path))
            report.update(md_report)
            docs = TextLoader(str(md_path), encoding="utf-8").load()
            for doc in docs:
                doc.metadata.update({
                    "source": str(path),
                    "markdown_path": str(md_path),
                    "parser": md_report.get("parser", ""),
                })
            report.update({"loader": md_report.get("parser", "Markdown"), "success": True})
            return docs, report
        except Exception as e:
            report.update({"success": False, "final_error": str(e)})
            raise DocumentLoadError("PDF 解析失败：PDF 转 Markdown 和降级解析均未成功", report) from e

    if suffix in (".txt", ".md"):
        try:
            docs = TextLoader(str(path), encoding="utf-8").load()
            report.update({"loader": "TextLoader", "success": True})
            return docs, report
        except Exception as e:
            report.update({"loader": "TextLoader", "success": False, "final_error": str(e)})
            raise DocumentLoadError("文本文件解析失败", report) from e

    raise ValueError(f"不支持的文件格式: {suffix}，仅支持 PDF/TXT/MD")


def load_file(file_path: str) -> List[Document]:
    """Load a single file (PDF/TXT/MD) and return a list of Documents."""
    docs, _ = load_file_with_report(file_path)
    return docs


def chunk_documents(
    documents: List[Document],
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> List[Document]:
    """Split documents into chunks with Chinese-aware separators."""
    recursive_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=CHUNK_SEPARATORS,
    )
    chunks: list[Document] = []
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("#", "标题1"),
            ("##", "标题2"),
            ("###", "标题3"),
            ("####", "标题4"),
        ],
        strip_headers=False,
    )

    for doc in documents:
        source = str(doc.metadata.get("source", "")).lower()
        is_markdown = source.endswith(".md") or bool(doc.metadata.get("markdown_path"))
        if not is_markdown:
            chunks.extend(recursive_splitter.split_documents([doc]))
            continue

        try:
            md_docs = markdown_splitter.split_text(doc.page_content)
            for md_doc in md_docs:
                md_doc.metadata.update(doc.metadata)
            chunks.extend(recursive_splitter.split_documents(md_docs))
        except Exception:
            chunks.extend(recursive_splitter.split_documents([doc]))
    return chunks


def load_and_chunk(file_path: str) -> List[Document]:
    """Load a file and split it into chunks in one step."""
    docs = load_file(file_path)
    chunks = chunk_documents(docs)
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = i
    return chunks


def load_and_chunk_with_report(file_path: str) -> tuple[List[Document], dict]:
    """Load and split a file, returning parser diagnostics for Streamlit."""
    docs, report = load_file_with_report(file_path)
    chunks = chunk_documents(docs)
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = i
    report["chunk_count"] = len(chunks)
    return chunks, report
