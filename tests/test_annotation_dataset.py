"""Tests for annotation datasets and preparation scripts."""

import json
import os
import sys
from pathlib import Path


ANNOTATIONS_DIR = Path(__file__).parent.parent / "data" / "annotations"
NER_SAMPLE = ANNOTATIONS_DIR / "ner_sample.jsonl"
RE_SAMPLE = ANNOTATIONS_DIR / "re_sample.jsonl"


class TestNERSampleData:
    def test_file_exists(self):
        assert NER_SAMPLE.exists(), f"NER sample not found at {NER_SAMPLE}"

    def test_valid_jsonl(self):
        with open(NER_SAMPLE, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                assert "text" in data, f"Line {line_no}: missing text"
                assert "tokens" in data, f"Line {line_no}: missing tokens"
                assert "labels" in data, f"Line {line_no}: missing labels"

    def test_tokens_labels_same_length(self):
        with open(NER_SAMPLE, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                assert len(data["tokens"]) == len(data["labels"]), \
                    f"Line {line_no}: length mismatch {len(data['tokens'])} vs {len(data['labels'])}"

    def test_labels_are_valid_bio(self):
        from src.graph.standard.ner.label_schema import BIO_LABELS
        with open(NER_SAMPLE, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                for i, label in enumerate(data["labels"]):
                    assert label in BIO_LABELS, \
                        f"Line {line_no}, token {i}: invalid label '{label}'"


class TestRESampleData:
    def test_file_exists(self):
        assert RE_SAMPLE.exists(), f"RE sample not found at {RE_SAMPLE}"

    def test_valid_jsonl(self):
        with open(RE_SAMPLE, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                assert "text" in data, f"Line {line_no}: missing text"
                assert "spo_list" in data, f"Line {line_no}: missing spo_list"

    def test_predicates_are_valid(self):
        from src.graph.standard.re.relation_schema import RELATION_TYPES
        with open(RE_SAMPLE, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                for i, spo in enumerate(data["spo_list"]):
                    assert spo["predicate"] in RELATION_TYPES, \
                        f"Line {line_no}, spo {i}: invalid predicate '{spo['predicate']}'"

    def test_spo_has_required_fields(self):
        with open(RE_SAMPLE, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                for i, spo in enumerate(data["spo_list"]):
                    assert "subject" in spo, f"Line {line_no}, spo {i}: missing subject"
                    assert "predicate" in spo, f"Line {line_no}, spo {i}: missing predicate"
                    assert "object" in spo, f"Line {line_no}, spo {i}: missing object"


class TestPrepareNERScript:
    def test_validate_passes(self):
        """Run prepare_ner_dataset.py --validate-only and check exit code."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/prepare_ner_dataset.py", "--validate-only"],
            capture_output=True, text=True, cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0, f"NER validate failed: {result.stderr}"

    def test_label_to_id_output(self):
        """Check label_to_id is consistent between schema and script output."""
        from src.graph.standard.ner.label_schema import label_to_id
        assert "O" in label_to_id
        assert label_to_id["O"] == 0


class TestPrepareREScript:
    def test_validate_passes(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/prepare_re_dataset.py", "--validate-only"],
            capture_output=True, text=True, cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0, f"RE validate failed: {result.stderr}"

    def test_relation_to_id_output(self):
        from src.graph.standard.re.relation_schema import relation_to_id
        assert "HAS_CHAPTER" in relation_to_id
        assert relation_to_id["HAS_CHAPTER"] == 0
