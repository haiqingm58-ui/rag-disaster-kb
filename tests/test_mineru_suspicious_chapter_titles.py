"""Tests that suspicious titles are rejected as chapters."""

import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.graph.standard.parser import _is_heading_noise


class TestSuspiciousChapterTitles:
    def test_drill_hole_with_semicolon(self):
        assert _is_heading_noise("钻孔；") is True

    def test_mm_unit_trailing(self):
        assert _is_heading_noise("mm。") is True

    def test_dash_steel_sleeve(self):
        assert _is_heading_noise("——钢套筒；") is True

    def test_long_sentence_with_units(self):
        assert _is_heading_noise("矩形桩的设计宽度，单位为米（m）。") is True

    def test_kpa_unit(self):
        assert _is_heading_noise("20 kPa。") is True

    def test_mpa_unit(self):
        assert _is_heading_noise("保护层厚度不应小于40 mm。") is True

    def test_formula_caption(self):
        assert _is_heading_noise("式中：") is True

    def test_unit_in_parens(self):
        assert _is_heading_noise("单位为米（m）") is True

    def test_see_table(self):
        assert _is_heading_noise("见表 1") is True

    def test_real_chapter_titles_pass(self):
        """Real Chinese standard chapter titles should pass."""
        valid = [
            "范围", "规范性引用文件", "术语和定义", "总则",
            "滑坡稳定性分析与设计安全系数", "设计方案选择",
            "排水工程", "抗滑桩工程", "锚索/锚杆工程",
            "格构锚固工程", "抗滑挡墙工程", "其他防治工程",
            "滑坡防治工程监测", "防治工程分级及荷载标准",
        ]
        for title in valid:
            assert not _is_heading_noise(title), f"'{title}' should be valid"

    def test_empty_short(self):
        assert _is_heading_noise("") is True
        assert _is_heading_noise("a") is True
