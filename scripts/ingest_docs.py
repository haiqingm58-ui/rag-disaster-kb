#!/usr/bin/env python3
"""CLI: 批量导入本地文档到知识库"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.document_loader import load_and_chunk
from src.vectorstore.chroma_store import add_documents
from config import COLLECTION_DOCS


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/ingest_docs.py <文件或目录路径> [文件或目录...]")
        print("支持格式: PDF, TXT, MD")
        sys.exit(1)

    input_paths = sys.argv[1:]
    all_paths = []

    for p in input_paths:
        p = Path(p)
        if p.is_dir():
            for ext in [".pdf", ".txt", ".md"]:
                all_paths.extend(p.rglob(f"*{ext}"))
        elif p.is_file():
            all_paths.append(p)
        else:
            print(f"⚠️  路径不存在: {p}")

    if not all_paths:
        print("未找到可导入的文件")
        sys.exit(0)

    total_chunks = 0
    for i, fp in enumerate(all_paths, 1):
        print(f"[{i}/{len(all_paths)}] 导入: {fp.name}")
        try:
            chunks = load_and_chunk(str(fp))
            add_documents(chunks, COLLECTION_DOCS)
            total_chunks += len(chunks)
            print(f"   ✓ 已添加 {len(chunks)} 个片段")
        except Exception as e:
            print(f"   ✗ 失败: {e}")

    print(f"\n✅ 完成！共导入 {len(all_paths)} 个文件，{total_chunks} 个片段")


if __name__ == "__main__":
    main()
