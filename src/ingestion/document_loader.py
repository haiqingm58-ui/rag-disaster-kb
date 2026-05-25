import subprocess
import tempfile
import shutil
import logging
import sys
from pathlib import Path
from typing import List

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    CHUNK_SEPARATORS,
    MINERU_BACKEND,
    MINERU_ENABLE_FORMULA,
    MINERU_ENABLE_TABLE,
)

logger = logging.getLogger(__name__)


class DocumentLoadError(Exception):
    """Document parsing failed with parser diagnostics attached."""

    def __init__(self, message: str, report: dict):
        super().__init__(message)
        self.report = report


def _mineru_command() -> str | None:
    """Find MinerU in PATH or next to the current Python executable."""
    command = shutil.which("mineru")
    if command:
        return command

    venv_command = Path(sys.executable).parent / "mineru"
    if venv_command.exists():
        return str(venv_command)

    return None


def _pdf_to_markdown(pdf_path: str, work_dir: str) -> Path:
    """Convert a PDF to clean Markdown using MinerU CLI."""
    mineru_cmd = _mineru_command()
    if not mineru_cmd:
        raise FileNotFoundError("未找到 MinerU 命令")

    subprocess.run(
        [
            mineru_cmd,
            "-p", pdf_path,
            "-o", work_dir,
            "-b", MINERU_BACKEND,
            "-f", str(MINERU_ENABLE_FORMULA).lower(),
            "-t", str(MINERU_ENABLE_TABLE).lower(),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    output_dir = Path(work_dir) / Path(pdf_path).stem
    md_files = list(output_dir.glob("*.md"))
    if md_files:
        return md_files[0]
    raise FileNotFoundError(f"MinerU 未生成 Markdown 文件: {output_dir}")


def _pdf_with_mineru(pdf_path: str) -> List[Document]:
    """Load a PDF by converting it to Markdown via MinerU, then chunking."""
    tmpdir = tempfile.mkdtemp(prefix="mineru_")
    try:
        md_path = _pdf_to_markdown(pdf_path, tmpdir)
        loader = TextLoader(str(md_path), encoding="utf-8")
        docs = loader.load()
        for doc in docs:
            doc.metadata["source"] = pdf_path
        return docs
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _mineru_available() -> bool:
    return _mineru_command() is not None


def load_file_with_report(file_path: str) -> tuple[List[Document], dict]:
    """Load a file and report parser/fallback details for UI messages."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    report = {
        "file": str(path),
        "loader": "",
        "mineru_available": _mineru_available(),
        "mineru_attempted": False,
        "mineru_failed": False,
        "mineru_error": "",
        "fallback_used": False,
        "success": False,
    }

    if suffix == ".pdf":
        if report["mineru_available"]:
            report["mineru_attempted"] = True
            try:
                docs = _pdf_with_mineru(str(path))
                report.update({"loader": "MinerU", "success": True})
                return docs, report
            except Exception as e:
                report.update({
                    "mineru_failed": True,
                    "mineru_error": str(e),
                    "fallback_used": True,
                })
                logger.warning("MinerU 解析失败，降级使用 PyPDF: %s", e)
        try:
            docs = PyPDFLoader(str(path)).load()
            report.update({"loader": "PyPDF", "success": True})
            return docs, report
        except Exception as e:
            report.update({"loader": "PyPDF", "success": False, "final_error": str(e)})
            raise DocumentLoadError("PDF 解析失败：MinerU 不可用或失败，PyPDF 也未能成功解析", report) from e

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
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=CHUNK_SEPARATORS,
    )
    return splitter.split_documents(documents)


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
