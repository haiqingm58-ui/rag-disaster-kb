"""Tests for check_standard_file.py — no Neo4j connection needed."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_standard_file import check_file


PROJECT_ROOT = Path(__file__).parent.parent


class TestCheckFileMd:
    def test_existing_md_file(self, tmp_path):
        """Check that a simple .md file passes the check."""
        md_file = tmp_path / "test_standard.md"
        md_file.write_text("""# 1 总则
第一条内容。

# 2 术语
## 2.1 地质灾害
指自然因素引发的危害人民生命财产安全的地质现象。

# 3 基本规定
## 3.1 评估要求
滑坡稳定性系数不应小于1.15。应采用定性与定量相结合的方法。
""", encoding="utf-8")

        result = check_file(
            md_file, title="测试标准", code="TEST-001", industry="test",
        )
        assert result["read_ok"] is True
        assert result["text_length"] > 0
        assert result["chapters"] >= 1
        assert result["clauses"] >= 1
        assert result["error"] == ""

    def test_empty_file(self, tmp_path):
        """Empty file should produce an error."""
        empty_file = tmp_path / "empty.md"
        empty_file.write_text("", encoding="utf-8")

        result = check_file(empty_file, title="test", code="T", industry="t")
        assert result["read_ok"] is True
        assert result["error"] != ""

    def test_nonexistent_file(self):
        result = check_file(
            Path("/nonexistent/path/file.pdf"),
            title="test", code="T", industry="t",
        )
        assert result["exists"] is False
        assert "不存在" in result["error"]

    def test_file_with_requirements(self, tmp_path):
        """File with '应' sentences should extract requirements."""
        md_file = tmp_path / "with_reqs.md"
        md_file.write_text("""# 1 基本规定
## 1.1 要求
评估应采用定性与定量相结合的方法。宜进行现场验证。可参考附录A。

## 1.2 指标
安全系数不应小于1.15。挡土墙高度不宜大于5m。
""", encoding="utf-8")

        result = check_file(md_file, title="test", code="T", industry="t")
        assert result["error"] == ""
        assert result["requirements"] >= 1
        assert result["indicators"] >= 1


class TestCheckFileTxt:
    def test_plain_text(self, tmp_path):
        txt_file = tmp_path / "standard.txt"
        txt_file.write_text("""3 技术规范
3.1 监测要求
监测周期不应大于7天。监测数据应归档保存。

3.2 评估方法
宜采用极限平衡法和数值模拟进行边坡稳定性分析。
""", encoding="utf-8")

        result = check_file(txt_file, title="测试", code="TXT-01", industry="geo")
        assert result["read_ok"] is True
        assert result["clauses"] >= 1
        assert result["methods"] >= 1


class TestCheckFileScript:
    def test_cli_md_file(self):
        """Run check_standard_file.py against an existing .md file."""
        # Create a temporary markdown file
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8",
        ) as f:
            f.write("""# 1 总则
第一条内容。

# 2 术语
## 2.1 测试术语
测试术语的定义。

# 3 规定
## 3.1 要求
应采用定量方法。安全系数不应小于1.15。
""")
            tmp_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, "scripts/check_standard_file.py",
                 "--file", tmp_path],
                capture_output=True, text=True,
                cwd=PROJECT_ROOT,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            output = result.stdout
            assert "条款数量" in output
            assert "抽取要求" in output
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_cli_save_intermediate_flag(self):
        """--save-intermediate should not crash on md files."""
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8",
        ) as f:
            f.write("# 1 测试\n## 1.1 条款\n应采用方法。\n")
            tmp_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, "scripts/check_standard_file.py",
                 "--file", tmp_path, "--save-intermediate"],
                capture_output=True, text=True,
                cwd=PROJECT_ROOT,
            )
            assert result.returncode == 0
        finally:
            Path(tmp_path).unlink(missing_ok=True)
