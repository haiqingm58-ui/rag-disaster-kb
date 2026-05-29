"""PDF to Markdown conversion with parser fallback reporting."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader

from config import MARKDOWN_DIR, MINERU_BACKEND, MINERU_ENABLE_FORMULA, MINERU_ENABLE_TABLE


def _mineru_command() -> str | None:
    command = shutil.which("mineru")
    if command:
        return command

    venv_command = Path(sys.executable).parent / "mineru"
    if venv_command.exists():
        return str(venv_command)
    return None


def _safe_markdown_name(pdf_path: str) -> Path:
    stem = Path(pdf_path).stem.replace("/", "_").replace(" ", "_")
    return MARKDOWN_DIR / f"{stem}.md"


def _convert_with_mineru(pdf_path: str) -> tuple[str, dict]:
    mineru_cmd = _mineru_command()
    if not mineru_cmd:
        raise FileNotFoundError("未找到 MinerU 命令")

    tmpdir = tempfile.mkdtemp(prefix="mineru_md_")
    try:
        subprocess.run(
            [
                mineru_cmd,
                "-p", pdf_path,
                "-o", tmpdir,
                "-b", MINERU_BACKEND,
                "-f", str(MINERU_ENABLE_FORMULA).lower(),
                "-t", str(MINERU_ENABLE_TABLE).lower(),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        output_dir = Path(tmpdir) / Path(pdf_path).stem
        md_files = list(output_dir.glob("*.md"))
        if not md_files:
            raise FileNotFoundError(f"MinerU 未生成 Markdown 文件：{output_dir}")
        return md_files[0].read_text(encoding="utf-8"), {"parser": "MinerU"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _convert_with_pymupdf4llm(pdf_path: str) -> tuple[str, dict]:
    try:
        import pymupdf4llm
    except ImportError as exc:
        raise ImportError("未安装 pymupdf4llm") from exc

    markdown = pymupdf4llm.to_markdown(pdf_path)
    return markdown, {"parser": "pymupdf4llm"}


def _convert_with_pypdf(pdf_path: str) -> tuple[str, dict]:
    docs = PyPDFLoader(pdf_path).load()
    parts = []
    for idx, doc in enumerate(docs, 1):
        parts.append(f"\n\n<!-- page: {idx} -->\n\n")
        parts.append(doc.page_content)
    return "\n".join(parts), {"parser": "PyPDFLoader"}


def convert_pdf_to_markdown(pdf_path: str) -> tuple[Path, dict]:
    """Convert a PDF to persisted Markdown and return (path, report)."""
    report = {
        "pdf_to_markdown": False,
        "parser": "",
        "mineru_available": _mineru_command() is not None,
        "mineru_attempted": False,
        "mineru_failed": False,
        "mineru_error": "",
        "fallback_used": False,
        "markdown_path": "",
    }

    converters = []
    if report["mineru_available"]:
        converters.append(("MinerU", _convert_with_mineru))
    converters.extend([
        ("pymupdf4llm", _convert_with_pymupdf4llm),
        ("PyPDFLoader", _convert_with_pypdf),
    ])

    errors = []
    markdown = ""
    for name, converter in converters:
        if name == "MinerU":
            report["mineru_attempted"] = True
        try:
            markdown, converter_report = converter(pdf_path)
            report["parser"] = converter_report["parser"]
            report["fallback_used"] = name != "MinerU"
            break
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            if name == "MinerU":
                report["mineru_failed"] = True
                report["mineru_error"] = str(exc)
    else:
        raise RuntimeError("PDF 转 Markdown 失败：" + "；".join(errors))

    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _safe_markdown_name(pdf_path)
    out_path.write_text(markdown, encoding="utf-8")
    report["pdf_to_markdown"] = True
    report["markdown_path"] = str(out_path)
    return out_path, report
