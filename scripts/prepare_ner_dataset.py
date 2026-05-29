#!/usr/bin/env python3
"""Prepare NER training data from annotated JSONL samples.

Usage:
  python scripts/prepare_ner_dataset.py
  python scripts/prepare_ner_dataset.py --input data/annotations/ner_sample.jsonl --output data/annotations/ner_ready.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.standard.ner.label_schema import label_to_id, ENTITY_TYPES

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def validate_sample(sample: dict, line_no: int) -> list[str]:
    """Validate a single NER annotation sample. Returns list of error messages."""
    errors = []
    if "text" not in sample:
        errors.append(f"Line {line_no}: missing 'text' field")
    if "tokens" not in sample:
        errors.append(f"Line {line_no}: missing 'tokens' field")
    if "labels" not in sample:
        errors.append(f"Line {line_no}: missing 'labels' field")
        return errors

    tokens = sample["tokens"]
    labels = sample["labels"]

    if len(tokens) != len(labels):
        errors.append(
            f"Line {line_no}: token/label length mismatch "
            f"({len(tokens)} tokens vs {len(labels)} labels)"
        )

    for i, label in enumerate(labels):
        if label not in label_to_id:
            errors.append(
                f"Line {line_no}, token {i}: unknown label '{label}'"
            )

    return errors


def convert_to_training_format(samples: list[dict]) -> list[dict]:
    """Convert samples to format ready for training (token IDs + label IDs)."""
    result = []
    for sample in samples:
        label_ids = [label_to_id.get(l, label_to_id["O"]) for l in sample["labels"]]
        result.append({
            "text": sample["text"],
            "tokens": sample["tokens"],
            "label_ids": label_ids,
        })
    return result


def main():
    ap = argparse.ArgumentParser(description="Prepare NER training dataset")
    ap.add_argument("--input", default="data/annotations/ner_sample.jsonl",
                    help="Input JSONL file (default: data/annotations/ner_sample.jsonl)")
    ap.add_argument("--output", default="data/annotations/ner_ready.json",
                    help="Output JSON file (default: data/annotations/ner_ready.json)")
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
    label_counts: dict[str, int] = {}
    for sample in samples:
        for label in sample["labels"]:
            label_counts[label] = label_counts.get(label, 0) + 1

    logger.info("Label distribution:")
    for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
        if count > 0:
            logger.info("  %s: %d", label, count)

    # Entity type stats
    entity_spans = 0
    for sample in samples:
        for label in sample["labels"]:
            if label.startswith("B-"):
                entity_spans += 1
    logger.info("Total entity spans: %d", entity_spans)

    if args.validate_only:
        logger.info("Validate-only mode; skipping output")
        return

    # Convert
    ready = convert_to_training_format(samples)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "label_to_id": label_to_id,
            "entity_types": ENTITY_TYPES,
            "samples": ready,
        }, f, ensure_ascii=False, indent=2)

    logger.info("Output written to %s (%d samples)", output_path, len(ready))
    logger.info("label_to_id mapping: %s", dict(list(label_to_id.items())[:5]))


if __name__ == "__main__":
    main()
