#!/usr/bin/env python3
"""Rule-based smoke evaluation for the disaster RAG system."""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingestion.disaster_api import sync_current_events
from src.rag.chain import answer, get_llm
from src.rag.retriever import retrieve_all


SOURCE_LABELS = {
    "document": "[文档]",
    "realtime": "[实时]",
    "general": "[通用]",
}


def _source_ok(expected: str, docs, response: str) -> bool:
    label = SOURCE_LABELS.get(expected)
    if expected == "general":
        return label in response
    return any(d.metadata.get("source_label") == label for d in docs)


def _check_keywords(response: str, item: dict) -> tuple[bool, list[str]]:
    """Multi-mode keyword check.

    Returns (all_ok, missing_labels) where missing_labels is a list of
    human-readable descriptions of what was missing.
    """
    missing = []

    # must_include — all keywords must appear (legacy, strict)
    for kw in item.get("must_include", []):
        if kw not in response:
            missing.append(kw)

    # must_include_any — at least one keyword from the flat list
    any_list = item.get("must_include_any", [])
    if any_list:
        if not any(kw in response for kw in any_list):
            missing.append("[{}] 任一".format(" / ".join(any_list)))

    # must_include_any_group — at least one from each synonym group
    for group in item.get("must_include_any_group", []):
        if not any(kw in response for kw in group):
            missing.append("[" + " / ".join(group) + "]")

    return (len(missing) == 0), missing


def evaluate_question(item: dict, llm) -> dict:
    started_at = time.perf_counter()
    question = item["question"]
    expected = item.get("expected_source_type", "")

    docs = retrieve_all(question, enable_docs=True, enable_events=True, llm=llm)
    response = answer(question, docs)
    elapsed_seconds = time.perf_counter() - started_at

    kw_ok, kw_missing = _check_keywords(response, item)

    checks = {
        "non_empty": bool(response.strip()),
        "has_source": bool(docs) or "[通用]" in response,
        "source_type": _source_ok(expected, docs, response),
        "keywords": kw_ok,
    }
    passed = all(checks.values())
    return {
        "question": question,
        "passed": passed,
        "checks": checks,
        "missing_keywords": kw_missing,
        "source_count": len(docs),
        "response": response,
        "expected_source_type": expected,
        "elapsed_seconds": elapsed_seconds,
    }


def _format_seconds(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m{remainder:04.1f}s"


def _preview(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars] + "..."


def _failure_reasons(result: dict) -> list[str]:
    checks = result.get("checks", {})
    reasons = []

    if result.get("error"):
        reasons.append(f"运行异常: {result['error']}")
    if not checks.get("non_empty", True):
        reasons.append("回答为空")
    if not checks.get("has_source", True):
        reasons.append("没有返回来源")
    if not checks.get("source_type", True):
        expected = result.get("expected_source_type") or "未指定"
        reasons.append(f"来源类型不匹配，期望 {expected}")
    if not checks.get("keywords", True):
        missing = result.get("missing_keywords", [])
        if missing:
            reasons.append(f"缺失关键词/组: {', '.join(missing)}")
        else:
            reasons.append("关键词检查未通过")

    return reasons


def _select_questions(all_questions: list[dict], start: int, limit: int | None) -> tuple[list[tuple[int, dict]], int]:
    start_index = max(start, 1) - 1
    end_index = None if not limit else start_index + limit
    selected = all_questions[start_index:end_index]
    numbered = [(start_index + offset + 1, item) for offset, item in enumerate(selected)]
    return numbered, len(all_questions)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(ROOT / "tests" / "eval_questions.json"))
    parser.add_argument("--limit", type=int, default=None, help="只评测 N 条，0 表示全部")
    parser.add_argument("--start", type=int, default=1, help="从第 N 题开始评测，默认 1")
    parser.add_argument("--skip-sync", action="store_true", help="跳过实时事件同步")
    parser.add_argument("--fast", action="store_true", help="快速评测模式：默认 limit=5、跳过同步、预览 120 字")
    parser.add_argument("--timeout", type=float, default=60.0, help="单题耗时提示阈值，单位秒，默认 60")
    parser.add_argument("--preview-chars", type=int, default=None, help="回答预览长度，默认 200；--fast 默认 120")
    args = parser.parse_args()

    effective_limit = args.limit
    if args.fast and effective_limit is None:
        effective_limit = 5
    preview_chars = args.preview_chars if args.preview_chars is not None else (120 if args.fast else 200)
    skip_sync = args.skip_sync or args.fast

    if args.start < 1:
        print("--start 必须大于等于 1", file=sys.stderr)
        return 2
    if effective_limit is not None and effective_limit < 0:
        print("--limit 必须大于等于 0", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("--timeout 必须大于 0", file=sys.stderr)
        return 2
    if preview_chars <= 0:
        print("--preview-chars 必须大于 0", file=sys.stderr)
        return 2

    all_questions = json.loads(Path(args.file).read_text(encoding="utf-8"))
    questions, total_available = _select_questions(all_questions, args.start, effective_limit)

    total_started_at = time.perf_counter()

    if not skip_sync:
        print("同步实时事件到向量库...")
        sync_result = sync_current_events(force_refresh=False)
        print(
            f"事件 {sync_result['total_events']} 条，新增 {sync_result['new_events']} 条，"
            f"跳过重复 {sync_result['skipped_duplicates']} 条。"
        )

    llm = get_llm()
    passed = 0
    failures = []
    for offset, (question_number, item) in enumerate(questions, 1):
        question_started_at = time.perf_counter()
        try:
            result = evaluate_question(item, llm)
        except Exception as exc:  # Keep batch evaluation usable when one question fails.
            elapsed_seconds = time.perf_counter() - question_started_at
            result = {
                "question": item.get("question", ""),
                "passed": False,
                "checks": {
                    "non_empty": False,
                    "has_source": False,
                    "source_type": False,
                    "keywords": False,
                },
                "missing_keywords": [],
                "source_count": 0,
                "response": "",
                "expected_source_type": item.get("expected_source_type", ""),
                "elapsed_seconds": elapsed_seconds,
                "error": str(exc),
            }

        passed += int(result["passed"])
        status = "PASS" if result["passed"] else "FAIL"
        elapsed = result.get("elapsed_seconds", 0.0)
        reasons = _failure_reasons(result)
        if reasons:
            failures.append(
                {
                    "number": question_number,
                    "question": result["question"],
                    "reasons": reasons,
                }
            )

        print(f"\n[题 {question_number}/{total_available} | {offset}/{len(questions)}] {status} {result['question']}")
        print(f"  来源数: {result['source_count']}")
        print(f"  本题耗时: {_format_seconds(elapsed)}")
        if elapsed > args.timeout:
            print(f"  耗时提示: 超过 --timeout {_format_seconds(args.timeout)}")
        print(f"  检查: {result['checks']}")
        if reasons:
            print(f"  失败原因: {'；'.join(reasons)}")
        print(f"  回答预览: {_preview(result['response'], preview_chars)}")

    rate = passed / len(questions) if questions else 0
    total_elapsed = time.perf_counter() - total_started_at
    average_elapsed = total_elapsed / len(questions) if questions else 0

    print("\n评测汇总")
    print(f"  总题数: {len(questions)}")
    print(f"  通过题数: {passed}")
    print(f"  失败题数: {len(questions) - passed}")
    print(f"  通过率: {passed}/{len(questions)} = {rate:.1%}")
    print(f"  总耗时: {_format_seconds(total_elapsed)}")
    print(f"  平均每题耗时: {_format_seconds(average_elapsed)}")
    if failures:
        print("  失败题目列表:")
        for failure in failures:
            print(f"    - 题 {failure['number']}: {failure['question']}（{'；'.join(failure['reasons'])}）")
    else:
        print("  失败题目列表: 无")

    return 0 if passed == len(questions) else 1


if __name__ == "__main__":
    raise SystemExit(main())
