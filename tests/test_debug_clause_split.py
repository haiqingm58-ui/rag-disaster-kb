"""Tests for debug_clause_split script."""

import subprocess
import sys
from pathlib import Path


MINERU_DIR = ("/Users/georisklab02/Documents/Codex/2026-05-29/mineru/"
              "converted_markdown/GBT+38509-2020滑坡防治设计规范")


class TestDebugScript:
    def test_script_runs(self):
        """Debug script should run without errors."""
        result = subprocess.run(
            [sys.executable, "scripts/debug_clause_split.py",
             "--input", MINERU_DIR, "--code", "GB/T 38509-2020"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Chapters" in result.stdout
        assert "Clause" in result.stdout
