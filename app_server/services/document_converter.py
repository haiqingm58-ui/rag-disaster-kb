from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app_server.settings import settings
from config import MARKDOWN_DIR, UPLOADS_DIR


SUPPORTED_SUFFIXES = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md"}
SUPPORTED_SUFFIX_LABEL = "PDF、DOCX、PPTX、XLSX、TXT、MD"
ALLOWED_MIME_TYPES = {
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
}
GENERIC_MIME_TYPES = {"", "application/octet-stream", "binary/octet-stream"}


class DocumentConversionError(ValueError):
    """Raised for upload validation or Markdown conversion failures."""


@dataclass(frozen=True)
class ConversionResult:
    markdown_path: Path
    markdown_text: str
    report: dict[str, Any]


def safe_upload_filename(name: str | None) -> str:
    filename = Path(name or "upload.txt").name.strip()
    if not filename or filename in {".", ".."} or "\x00" in filename:
        raise DocumentConversionError("文件名不合法，请重新选择文件。")
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise DocumentConversionError(f"仅支持 {SUPPORTED_SUFFIX_LABEL} 文件。")
    return filename.replace("/", "_").replace("\\", "_")


def validate_upload_metadata(file: UploadFile, filename: str) -> None:
    suffix = Path(filename).suffix.lower()
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in GENERIC_MIME_TYPES and content_type not in ALLOWED_MIME_TYPES[suffix]:
        raise DocumentConversionError(f"文件类型不匹配：{suffix} 不支持 {content_type}。")

    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size <= 0:
        raise DocumentConversionError("文件为空，请重新选择文件。")
    if size > settings.max_upload_bytes:
        raise DocumentConversionError(f"文件过大，最大允许 {settings.max_upload_mb}MB。")


def ensure_within_dir(path: Path, base_dir: Path) -> Path:
    resolved = path.resolve()
    base = base_dir.resolve()
    if not str(resolved).startswith(str(base) + "/") and resolved != base:
        raise DocumentConversionError("文件路径不合法，请重新上传。")
    return resolved


def markdown_output_path(document_id: str, filename: str) -> Path:
    stem = Path(filename).stem.replace(" ", "_")[:120] or "document"
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
    return ensure_within_dir(MARKDOWN_DIR / f"{document_id}_{stem}.md", MARKDOWN_DIR)


def convert_to_markdown(source_path: Path, filename: str, document_id: str) -> ConversionResult:
    source = ensure_within_dir(source_path, UPLOADS_DIR)
    suffix = source.suffix.lower()
    output_path = markdown_output_path(document_id, filename)

    try:
        if suffix in {".txt", ".md"}:
            markdown_text = source.read_text(encoding="utf-8", errors="ignore")
            converter_name = "plain-text"
        else:
            markdown_text = _markitdown_convert(source)
            converter_name = "markitdown"
    except DocumentConversionError:
        raise
    except Exception as exc:
        raise DocumentConversionError(f"文档转换为 Markdown 失败，请检查文件是否完整或格式是否受支持。") from exc

    if not markdown_text.strip():
        raise DocumentConversionError("文档转换后没有可用文本，请检查文件内容。")

    output_path.write_text(markdown_text, encoding="utf-8")
    report = {
        "converter": converter_name,
        "converted_to_markdown": True,
        "original_path": str(source),
        "markdown_path": str(output_path),
        "source_suffix": suffix,
    }
    return ConversionResult(markdown_path=output_path, markdown_text=markdown_text, report=report)


def _markitdown_convert(source: Path) -> str:
    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise DocumentConversionError("MarkItDown 依赖未安装，请先安装 markitdown[pdf,docx,pptx,xlsx]。") from exc

    converter = MarkItDown(enable_plugins=False)
    if hasattr(converter, "convert_local"):
        result = converter.convert_local(str(source))
    else:
        result = converter.convert(str(source))

    markdown = getattr(result, "text_content", None) or getattr(result, "markdown", None)
    if markdown is None:
        markdown = str(result)
    return str(markdown)
