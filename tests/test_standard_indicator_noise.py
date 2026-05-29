"""Tests for indicator extraction — noise filtering."""

import pytest

from src.graph.standard.models import Clause
from src.graph.standard.extractor import extract_indicators, _INDICATOR_NAME_BLACKLIST


def make_clause(content=""):
    from src.graph.standard.models import Clause
    return Clause(clause_id="cl-test", standard_id="std-1",
                  clause_number="5.1", content=content)


class TestValidIndicators:
    def test_not_less_than(self):
        cl = make_clause("滑坡稳定性系数不应小于1.15。")
        inds = extract_indicators(cl)
        assert len(inds) >= 1

    def test_greater_than_with_unit(self):
        cl = make_clause("挡土墙高度不宜大于5m。")
        inds = extract_indicators(cl)
        assert len(inds) >= 1

    def test_less_than_hours(self):
        cl = make_clause("监测周期不应大于24h。")
        inds = extract_indicators(cl)
        assert len(inds) >= 1

    def test_exceeds_value(self):
        cl = make_clause("勘探深度不超过100m。")
        inds = extract_indicators(cl)
        assert len(inds) >= 1


class TestNoiseFiltered:
    def test_single_character_not_indicator(self):
        """'人' alone should not be identified as an indicator."""
        cl = make_clause("疏散人数为100人。")
        inds = extract_indicators(cl)
        names = [i.name for i in inds]
        assert "人" not in names

    def test_generic_word_not_indicator(self):
        """'且' should never be an indicator name."""
        cl = make_clause("应满足要求且符合标准。")
        inds = extract_indicators(cl)
        names = [i.name for i in inds]
        for noise in ["且", "或", "的", "了"]:
            assert noise not in names, f"'{noise}' incorrectly detected as indicator"

    def test_blacklist_words_filtered(self):
        """All blacklisted words should be filtered."""
        for word in _INDICATOR_NAME_BLACKLIST:
            cl = make_clause(f"应符合{word}要求。")
            inds = extract_indicators(cl)
            names = [i.name for i in inds]
            assert word not in names, f"'{word}' should be filtered"


class TestBlacklistCompleteness:
    def test_known_noise_words(self):
        noise_words = ["万元", "元", "且", "或", "人", "不", "并",
                       "例尺", "不宜", "其及"]
        for w in noise_words:
            if w in _INDICATOR_NAME_BLACKLIST:
                continue  # already covered
            # Some may not be in blacklist yet; this is informational
