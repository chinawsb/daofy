#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 OutputParser — src/utils/parser.py

覆盖:
  - parse: 标准 Error/Warning/Fatal 格式解析
  - parse_errors: 仅提取错误
  - parse_warnings: 仅提取警告
  - has_errors / has_warnings: 快速检测
  - extract_error_summary: 错误摘要生成
  - 边界: 空输出、混合输出、无行号 Fatal、超过 5 个错误
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest

from src.utils.parser import OutputParser
from src.models.compile_result import CompileMessage


# ============================================================
# parse — 标准格式
# ============================================================

class TestParse:

    def test_parse_error(self):
        p = OutputParser()
        msgs = p.parse("Error: Unit1.pas(10,5): Undeclared identifier 'Foo'")
        assert len(msgs) == 1
        assert msgs[0].message_type == "error"
        assert msgs[0].file_path == "Unit1.pas"
        assert msgs[0].line == 10
        assert msgs[0].column == 5
        assert "Undeclared" in msgs[0].message

    def test_parse_warning(self):
        p = OutputParser()
        msgs = p.parse("Warning: Unit2.pas(20,3): Variable 'X' is never used")
        assert len(msgs) == 1
        assert msgs[0].message_type == "warning"

    def test_parse_fatal_with_location(self):
        p = OutputParser()
        msgs = p.parse("Fatal: Project.dpr(1,1): File not found 'Missing.pas'")
        assert len(msgs) == 1
        assert msgs[0].message_type == "error"

    def test_parse_fatal_no_location(self):
        p = OutputParser()
        msgs = p.parse("Fatal: Could not compile used unit 'Unit1.pas'")
        assert len(msgs) == 1
        assert msgs[0].message_type == "error"
        assert msgs[0].file_path == ""
        assert msgs[0].line == 0
        assert msgs[0].column == 0

    def test_parse_mixed_output(self):
        p = OutputParser()
        output = (
            "Warning: A.pas(1,1): W1\n"
            "Error: B.pas(2,2): E1\n"
            "Some other line\n"
            "Fatal: C.pas(3,3): F1\n"
        )
        msgs = p.parse(output)
        assert len(msgs) == 3
        assert msgs[0].message_type == "warning"
        assert msgs[1].message_type == "error"
        assert msgs[2].message_type == "error"

    def test_parse_empty_output(self):
        p = OutputParser()
        assert p.parse("") == []

    def test_parse_blank_lines_only(self):
        p = OutputParser()
        assert p.parse("\n\n  \n") == []

    def test_parse_non_matching_lines_ignored(self):
        p = OutputParser()
        assert p.parse("Building Project1.dpr\nCompiling Unit1.pas\n") == []


# ============================================================
# parse_errors / parse_warnings
# ============================================================

class TestParseFiltered:

    def test_parse_errors_only(self):
        p = OutputParser()
        output = (
            "Warning: A.pas(1,1): W1\n"
            "Error: B.pas(2,2): E1\n"
            "Error: C.pas(3,3): E2\n"
        )
        errors = p.parse_errors(output)
        assert len(errors) == 2
        assert all(m.message_type == "error" for m in errors)

    def test_parse_warnings_only(self):
        p = OutputParser()
        output = (
            "Warning: A.pas(1,1): W1\n"
            "Warning: B.pas(2,2): W2\n"
            "Error: C.pas(3,3): E1\n"
        )
        warnings = p.parse_warnings(output)
        assert len(warnings) == 2
        assert all(m.message_type == "warning" for m in warnings)

    def test_no_errors(self):
        p = OutputParser()
        assert p.parse_errors("Warning: A.pas(1,1): W1") == []

    def test_no_warnings(self):
        p = OutputParser()
        assert p.parse_warnings("Error: A.pas(1,1): E1") == []


# ============================================================
# has_errors / has_warnings
# ============================================================

class TestHasErrorsWarnings:

    def test_has_errors_true(self):
        p = OutputParser()
        assert p.has_errors("Error: A.pas(1,1): E1")
        assert p.has_errors("Fatal: something bad")

    def test_has_errors_false(self):
        p = OutputParser()
        assert not p.has_errors("Warning: A.pas(1,1): W1")
        assert not p.has_errors("")
        assert not p.has_errors("Building...")

    def test_has_warnings_true(self):
        p = OutputParser()
        assert p.has_warnings("Warning: A.pas(1,1): W1")

    def test_has_warnings_false(self):
        p = OutputParser()
        assert not p.has_warnings("Error: A.pas(1,1): E1")
        assert not p.has_warnings("")


# ============================================================
# extract_error_summary
# ============================================================

class TestExtractErrorSummary:

    def test_summary_with_errors(self):
        p = OutputParser()
        output = "Error: A.pas(1,1): E1\nError: B.pas(2,2): E2"
        summary = p.extract_error_summary(output)
        assert "E1" in summary
        assert "E2" in summary

    def test_summary_no_errors(self):
        p = OutputParser()
        assert p.extract_error_summary("") == "无错误"

    def test_summary_truncates_at_5(self):
        p = OutputParser()
        lines = [f"Error: A.pas({i},{i}): E{i}" for i in range(1, 8)]
        output = "\n".join(lines)
        summary = p.extract_error_summary(output)
        assert "还有 2 个错误" in summary

    def test_summary_fatal_no_filepath(self):
        p = OutputParser()
        output = "Fatal: Could not compile used unit 'X.pas'"
        summary = p.extract_error_summary(output)
        assert "Could not compile" in summary
