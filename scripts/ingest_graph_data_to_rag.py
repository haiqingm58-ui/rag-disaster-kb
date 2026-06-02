#!/usr/bin/env python3
"""Import GitHub Pages graph JSON into the RAG Chroma database.

The GitHub Pages site is backed by docs/data/graph_data.json and
docs/data/search_index.json. This script converts the structured graph nodes
into retrievable LangChain documents and stores them in COLLECTION_DOCS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.documents import Document

from config import COLLECTION_DOCS
from src.vectorstore.chroma_store import (
    add_documents_with_ids,
    delete_by_source,
    source_chunk_count,
)


DEFAULT_SOURCE = "github_pages_graph"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _stable_id(prefix: str, item: dict[str, Any]) -> str:
    raw = (
        item.get("id")
        or item.get("standard_id")
        or "|".join(
            _text(item.get(k))
            for k in ("code", "number", "clause_number", "name", "title", "text", "value", "unit")
        )
    )
    digest = hashlib.sha1(f"{prefix}|{raw}".encode("utf-8")).hexdigest()[:16]
    safe_raw = "".join(ch if ch.isalnum() or ch in "._:-" else "_" for ch in _text(raw))[:80]
    return f"{DEFAULT_SOURCE}:{prefix}:{safe_raw or digest}:{digest}"


def _metadata(source: str, node_type: str, item: dict[str, Any]) -> dict[str, str | int | float | bool]:
    metadata: dict[str, str | int | float | bool] = {
        "source": source,
        "filename": "GitHub Pages 静态知识图谱",
        "source_url": "https://haiqingm58-ui.github.io/rag-disaster-kb/",
        "node_type": node_type,
        "code": _text(item.get("code")),
        "title": _text(item.get("title") or item.get("name")),
    }
    for key in ("number", "clause_number", "id", "standard_id", "industry", "obligation", "unit"):
        value = item.get(key)
        if value not in ("", None):
            metadata[key] = _text(value)
    return metadata


def _doc(node_type: str, item: dict[str, Any], body: str, source: str) -> Document | None:
    body = "\n".join(line.strip() for line in body.splitlines() if line.strip())
    if not body:
        return None
    return Document(page_content=body, metadata=_metadata(source, node_type, item))


def _build_documents(graph: dict[str, Any], source: str) -> tuple[list[Document], list[str]]:
    docs: list[Document] = []
    ids: list[str] = []

    def add(node_type: str, item: dict[str, Any], body: str) -> None:
        document = _doc(node_type, item, body, source)
        if not document:
            return
        docs.append(document)
        ids.append(_stable_id(node_type, item))

    for item in graph.get("standards", []) or []:
        add(
            "标准",
            item,
            (
                f"【标准】{_text(item.get('code'))} {_text(item.get('title'))}\n"
                f"行业: {_text(item.get('industry'))}\n"
                f"来源文件: {_text(item.get('source_file'))}\n"
                f"章节数: {_text(item.get('chapters'))}; 条款数: {_text(item.get('clauses'))}; "
                f"术语数: {_text(item.get('terms'))}; 要求数: {_text(item.get('requirements'))}; "
                f"指标数: {_text(item.get('indicators'))}; 方法数: {_text(item.get('methods'))}"
            ),
        )

    for item in graph.get("chapters", []) or []:
        add(
            "章节",
            item,
            f"【章节】{_text(item.get('code'))} 第{_text(item.get('number'))}章 {_text(item.get('title'))}",
        )

    for item in graph.get("clauses", []) or []:
        add(
            "条款",
            item,
            (
                f"【条款】{_text(item.get('code'))} {_text(item.get('number'))} {_text(item.get('title'))}\n"
                f"{_text(item.get('content'))}"
            ),
        )

    for item in graph.get("terms", []) or []:
        add(
            "术语",
            item,
            (
                f"【术语】{_text(item.get('code'))} {_text(item.get('name'))}\n"
                f"定义: {_text(item.get('definition'))}"
            ),
        )

    for item in graph.get("requirements", []) or []:
        add(
            "要求",
            item,
            (
                f"【规范要求】{_text(item.get('code'))} 条款 {_text(item.get('clause_number'))}\n"
                f"约束: {_text(item.get('obligation'))}\n"
                f"{_text(item.get('text'))}"
            ),
        )

    for item in graph.get("indicators", []) or []:
        add(
            "指标",
            item,
            (
                f"【指标参数】{_text(item.get('code'))} 条款 {_text(item.get('clause_number'))}\n"
                f"{_text(item.get('name'))}: {_text(item.get('operator'))} "
                f"{_text(item.get('value'))}{_text(item.get('unit'))}"
            ),
        )

    for item in graph.get("methods", []) or []:
        add(
            "方法",
            item,
            (
                f"【方法】{_text(item.get('code'))} 条款 {_text(item.get('clause_number'))}\n"
                f"{_text(item.get('name'))}: {_text(item.get('description'))}"
            ),
        )

    # Deduplicate IDs defensively while preserving order.
    unique_docs: list[Document] = []
    unique_ids: list[str] = []
    seen: set[str] = set()
    for doc, doc_id in zip(docs, ids):
        if doc_id in seen:
            continue
        seen.add(doc_id)
        unique_docs.append(doc)
        unique_ids.append(doc_id)
    return unique_docs, unique_ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Import docs/data graph JSON into Chroma RAG DB")
    parser.add_argument("--graph-data", default="docs/data/graph_data.json", help="Path to graph_data.json")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Source marker used in Chroma metadata")
    parser.add_argument("--batch-size", type=int, default=100, help="Number of chunks to add per Chroma write")
    parser.add_argument("--no-delete", action="store_true", help="Do not delete existing chunks for this source first")
    parser.add_argument("--dry-run", action="store_true", help="Only build and count documents; do not write Chroma")
    args = parser.parse_args()

    graph_path = Path(args.graph_data)
    if not graph_path.exists():
        raise SystemExit(f"graph_data.json not found: {graph_path}")

    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    docs, ids = _build_documents(graph, args.source)
    print(f"Built {len(docs)} graph RAG documents from {graph_path}")

    if args.dry_run:
        by_type: dict[str, int] = {}
        for doc in docs:
            node_type = str(doc.metadata.get("node_type", ""))
            by_type[node_type] = by_type.get(node_type, 0) + 1
        print(json.dumps(by_type, ensure_ascii=False, indent=2))
        return

    if not args.no_delete:
        deleted = delete_by_source(COLLECTION_DOCS, args.source)
        print(f"Deleted {deleted} existing chunks from source={args.source}")

    batch_size = max(1, args.batch_size)
    for start in range(0, len(docs), batch_size):
        end = min(start + batch_size, len(docs))
        add_documents_with_ids(docs[start:end], ids[start:end], COLLECTION_DOCS)
        print(f"Imported batch {start + 1}-{end}/{len(docs)}")
    count = source_chunk_count(COLLECTION_DOCS, args.source)
    print(f"Imported {len(docs)} chunks into collection={COLLECTION_DOCS}; source count now {count}")


if __name__ == "__main__":
    main()
