#!/usr/bin/env python3
"""Prepare RE training data from annotated JSONL samples.

Usage:
  python scripts/prepare_re_dataset.py
  python scripts/prepare_re_dataset.py --input data/annotations/re_sample.jsonl --output data/annotations/re_ready.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.standard.re.relation_schema import relation_to_id, RELATION_TYPES

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def validate_sample(sample: dict, line_no: int) -> list[str]:
    """Validate a single RE annotation sample. Returns list of error messages."""
    errors = []
    if "text" not in sample:
        errors.append(f"Line {line_no}: missing 'text' field")
    if "spo_list" not in sample:
        errors.append(f"Line {line_no}: missing 'spo_list' field")
        return errors

    for i, spo in enumerate(sample["spo_list"]):
        if "subject" not in spo:
            errors.append(f"Line {line_no}, spo {i}: missing 'subject'")
        if "predicate" not in spo:
            errors.append(f"Line {line_no}, spo {i}: missing 'predicate'")
        if "object" not in spo:
            errors.append(f"Line {line_no}, spo {i}: missing 'object'")

        pred = spo.get("predicate", "")
        if pred and pred not in relation_to_id:
            errors.append(
                f"Line {line_no}, spo {i}: unknown predicate '{pred}'. "
                f"Valid: {RELATION_TYPES}"
            )

    return errors


def convert_to_training_format(samples: list[dict]) -> list[dict]:
    """Convert samples to training-ready format with relation IDs."""
    result = []
    for sample in samples:
        spo_with_ids = []
        for spo in sample["spo_list"]:
            spo_with_ids.append({
                "subject": spo["subject"],
                "predicate_id": relation_to_id.get(spo["predicate"], -1),
                "predicate": spo["predicate"],
                "object": spo["object"],
            })
        result.append({
            "text": sample["text"],
            "spo_list": spo_with_ids,
        })
    return result


def main():
    ap = argparse.ArgumentParser(description="Prepare RE training dataset")
    ap.add_argument("--input", default="data/annotations/re_sample.jsonl",
                    help="Input JSONL file")
    ap.add_argument("--output", default="data/annotations/re_ready.json",
                    help="Output JSON file")
    ap.add_argument("--validate-only", action="store_true",
                    help="Only validate, don't convert")

    args = ap.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        sys.exit(1)

    # Load
    samples = []
    errors = []
    with open(input_path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                sample = json.loads(line)
                samples.append(sample)
                sample_errors = validate_sample(sample, line_no)
                errors.extend(sample_errors)
            except json.JSONDecodeError as exc:
                errors.append(f"Line {line_no}: JSON parse error: {exc}")

    logger.info("Loaded %d samples from %s", len(samples), input_path)

    if errors:
        logger.error("Validation errors (%d):", len(errors))
        for err in errors:
            logger.error("  %s", err)
        sys.exit(1)

    logger.info("Validation passed: %d samples", len(samples))

    # Statistics
    total_spos = sum(len(s["spo_list"]) for s in samples)
    relation_counts: dict[str, int] = {}
    for sample in samples:
        for spo in sample["spo_list"]:
            pred = spo["predicate"]
            relation_counts[pred] = relation_counts.get(pred, 0) + 1

    logger.info("Total SPO triples: %d", total_spos)
    logger.info("Relation distribution:")
    for rel, count in sorted(relation_counts.items(), key=lambda x: -x[1]):
        logger.info("  %s: %d", rel, count)

    if args.validate_only:
        logger.info("Validate-only mode; skipping output")
        return

    # Convert
    ready = convert_to_training_format(samples)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "relation_to_id": relation_to_id,
            "relation_types": RELATION_TYPES,
            "samples": ready,
        }, f, ensure_ascii=False, indent=2)

    logger.info("Output written to %s (%d samples, %d triples)",
                output_path, len(ready), total_spos)


if __name__ == "__main__":
    main()
