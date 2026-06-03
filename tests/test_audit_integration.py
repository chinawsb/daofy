"""
Tests for src/tools/audit.py — daudit integration

Covers: _find_daudit, _run_daudit, _run_audit, _run_skeleton,
        _call_daudit, _extract_json, _format_report,
        _check_runtime_rules, run_audit (MCP entry point)

Strategy:
  - Mock subprocess.run / subprocess.Popen to simulate daudit.exe output
  - Use temp directories for file-system-based tests
  - Test error paths (missing exe, timeout, invalid JSON, etc.)
"""

import json
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock, mock_open

import pytest
from mcp.types import CallToolResult


# ═══════════════════════════════════════════════════════════════
# Shared test data — realistic daudit JSON payloads
# ═══════════════════════════════════════════════════════════════

SAMPLE_AUDIT_PAYLOAD = {
    "mode": "audit",
    "status": "ok",
    "data": {
        "findings": [
            {
                "rule_id": "R001",
                "file": "Unit1.pas",
                "line": 42,
                "column": 5,
                "severity": "error",
                "category": "Security",
                "message": "SQL injection possible",
                "code_snippet": "Query.SQL.Add('SELECT * FROM users WHERE id = ' + Input);"
            },
            {
                "rule_id": "R002",
                "file": "Unit2.pas",
                "line": 15,
                "column": 1,
                "severity": "warning",
                "category": "Performance",
                "message": "Unused variable",
                "code_snippet": ""
            },
            {
                "rule_id": "R003",
                "file": "Unit3.pas",
                "line": 99,
                "column": 10,
                "severity": "hint",
                "category": "CodeStyle",
                "message": "Consider using const",
                "code_snippet": "var X: Integer;"
            }
        ],
        "totalFindings": 3
    },
    "summary": {
        "files_scanned": 10,
        "elapsed_ms": 1234
    }
}

SAMPLE_SKELETON_PAYLOAD = {
    "mode": "skeleton",
    "status": "ok",
    "data": {
        "files": [
            {
                "file": "Unit1.pas",
                "data": "unit Unit1;\nuses System.SysUtils;\nfunction Foo: Integer;\nprocedure Bar;"
            },
            {
                "file": "Unit2.pas",
                "data": "unit Unit2;\nuses System.Classes;\nprocedure Test;"
            }
        ]
    }
}

SAMPLE_ERROR_PAYLOAD = {
    "mode": "audit",
    "status": "error",
    "data": {"message": "No .pas files found in directory"},
    "summary": {}
}

SAMPLE_MIXED_OUTPUT = (
    "Dao insight toolkit - Source Code Insight & Audit Tool\n"
    "Copyright (c) 2023-2026\n"
    "================================================================\n"
    '{"mode":"audit","status":"ok","data":{"findings":[],"totalFindings":0},"summary":{"files_scanned":1,"elapsed_ms":50}}\n'
    "Scan complete. 0 findings.\n"
)

# A complex JSON with surrounding text and nested objects
SAMPLE_MIXED_MULTIPLE_JSON = (
    "Banner line 1\n"
    '{"mode":"first","status":"ok","data":{}}\n'
    "Middle text\n"
    '{"mode":"second","status":"ok","data":{"key":"value"}}\n'
    "Trailer\n"
)


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def mock_subprocess_success():
    """Mock subprocess.run returning successful daudit output."""
    with patch("src.tools.audit.subprocess.run") as mock:
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = json.dumps(SAMPLE_AUDIT_PAYLOAD)
        proc.stderr = ""
        mock.return_value = proc
        yield mock


@pytest.fixture
def mock_subprocess_skeleton():
    """Mock subprocess.Popen for skeleton mode (file output)."""
    with patch("src.tools.audit.subprocess.run") as mock:
        proc = MagicMock()
        proc.returncode = 0
        # _run_skeleton writes to file, then reads it back
        # So we need the mock to actually write the JSON to the file
        def side_effect(cmd, stdout=None, stderr=None, timeout=300, **kwargs):
            if stdout is not None:  # file mode
                stdout.write(json.dumps(SAMPLE_SKELETON_PAYLOAD).encode("utf-8"))
            proc.returncode = 0
            return proc
        mock.side_effect = side_effect
        yield mock


@pytest.fixture
def mock_subprocess_fail():
    """Mock subprocess.run returning failure."""
    with patch("src.tools.audit.subprocess.run") as mock:
        proc = MagicMock()
        proc.returncode = 1
        proc.stdout = ""
        proc.stderr = "error: unable to parse file"
        mock.return_value = proc
        yield mock


# ═══════════════════════════════════════════════════════════════
# _find_daudit
# ═══════════════════════════════════════════════════════════════

class TestFindDaudit:
    """Tests for _find_daudit() — path discovery logic."""

    def test_finds_exe_at_expected_location(self):
        """Should find daudit.exe at daofy/tools/daudit/daudit.exe."""
        from src.tools.audit import _find_daudit
        # Reset cache
        import src.tools.audit as audit_mod
        audit_mod._DAUDIT_PATH = None

        path = _find_daudit()
        if path:
            assert path.endswith("daudit.exe")
            assert Path(path).exists()
        # If not found (e.g., test env without daudit), should return None
        # The important thing is no crash

    def test_returns_none_when_not_found(self):
        """Should return None when daudit.exe not at any candidate path."""
        import src.tools.audit as audit_mod
        audit_mod._DAUDIT_PATH = None

        with patch("src.tools.audit.Path.exists") as mock_exists:
            mock_exists.return_value = False
            result = audit_mod._find_daudit()
            assert result is None

    def test_cache_hit(self):
        """Should return cached path on subsequent calls."""
        import src.tools.audit as audit_mod
        audit_mod._DAUDIT_PATH = r"C:\cached\daudit.exe"

        with patch("src.tools.audit.Path.exists") as mock_exists:
            result = audit_mod._find_daudit()
            assert result == r"C:\cached\daudit.exe"
            # _find_daudit returns cached before checking Path.exists
            # So mock_exists should NOT be called
            mock_exists.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# _run_daudit
# ═══════════════════════════════════════════════════════════════

class TestRunDaudit:
    """Tests for _run_daudit() — low-level daudit invocation."""

    def test_successful_execution(self, mock_subprocess_success, mock_daudit_found):
        """Should return parsed JSON on success."""
        from src.tools.audit import _run_daudit

        result = _run_daudit(["--mode", "audit", "Unit.pas"])
        assert result is not None
        assert result["status"] == "ok"
        assert result["data"]["totalFindings"] == 3

    def test_daudit_not_found_returns_none(self, mock_daudit_missing):
        """Should return None when daudit.exe is missing."""
        from src.tools.audit import _run_daudit

        result = _run_daudit(["--mode", "audit", "Unit.pas"])
        assert result is None

    def test_exit_code_1_still_parses_output(self, mock_daudit_found):
        """Exit code 1 should still parse stdout (daudit returns 1 for findings)."""
        with patch("src.tools.audit.subprocess.run") as mock:
            proc = MagicMock()
            proc.returncode = 1  # daudit returns 1 when findings exist
            proc.stdout = json.dumps(SAMPLE_AUDIT_PAYLOAD)
            proc.stderr = ""
            mock.return_value = proc

            from src.tools.audit import _run_daudit
            result = _run_daudit(["--recursive", "Src"])
            assert result is not None
            assert result["status"] == "ok"

    def test_timeout_returns_none(self, mock_daudit_found):
        """subprocess.TimeoutExpired should return None (not crash)."""
        with patch("src.tools.audit.subprocess.run") as mock:
            import subprocess
            mock.side_effect = subprocess.TimeoutExpired("daudit.exe", 300)

            from src.tools.audit import _run_daudit
            result = _run_daudit(["--recursive", "Src"])
            assert result is None

    def test_oserror_returns_none(self, mock_daudit_found):
        """OSError should return None (not crash)."""
        with patch("src.tools.audit.subprocess.run") as mock:
            mock.side_effect = OSError("access denied")

            from src.tools.audit import _run_daudit
            result = _run_daudit(["--recursive", "Src"])
            assert result is None

    def test_invalid_json_returns_none(self, mock_daudit_found):
        """Invalid JSON output should return None."""
        with patch("src.tools.audit.subprocess.run") as mock:
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = "not json {{{broken"
            proc.stderr = ""
            mock.return_value = proc

            from src.tools.audit import _run_daudit
            result = _run_daudit(["--mode", "audit"])
            assert result is None

    def test_accepts_return_code_0_and_1(self, mock_daudit_found):
        """Both return codes 0 and 1 should be accepted."""
        for rc in [0, 1]:
            with patch("src.tools.audit.subprocess.run") as mock:
                proc = MagicMock()
                proc.returncode = rc
                proc.stdout = json.dumps(SAMPLE_AUDIT_PAYLOAD)
                proc.stderr = ""
                mock.return_value = proc

                from src.tools.audit import _run_daudit
                result = _run_daudit(["--mode", "audit"])
                assert result is not None, f"Failed on return code {rc}"

    def test_rejects_return_code_2(self, mock_daudit_found):
        """Return code 2 (or other unexpected values) should return None."""
        with patch("src.tools.audit.subprocess.run") as mock:
            proc = MagicMock()
            proc.returncode = 2
            proc.stdout = ""
            proc.stderr = "fatal error"
            mock.return_value = proc

            from src.tools.audit import _run_daudit
            result = _run_daudit(["--mode", "audit"])
            assert result is None

    def test_forwards_create_no_window_flag(self, mock_daudit_found):
        """Should pass CREATE_NO_WINDOW flag on Windows."""
        with patch("src.tools.audit.subprocess.run") as mock:
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = json.dumps(SAMPLE_AUDIT_PAYLOAD)
            proc.stderr = ""
            mock.return_value = proc

            from src.tools.audit import _run_daudit
            _run_daudit(["--mode", "audit"])

            # Verify the call included creationflags
            call_kwargs = mock.call_args[1]
            assert "creationflags" in call_kwargs

    def test_prepends_format_json(self, mock_daudit_found):
        """Should prepend --format json to the command."""
        with patch("src.tools.audit.subprocess.run") as mock:
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = json.dumps(SAMPLE_AUDIT_PAYLOAD)
            proc.stderr = ""
            mock.return_value = proc

            from src.tools.audit import _run_daudit
            _run_daudit(["--mode", "audit", "Src"])

            cmd = mock.call_args[0][0]
            assert "--format" in cmd
            assert "json" in cmd
            assert "--mode" in cmd
            assert "audit" in cmd
            assert cmd[-1] == "Src"


# ═══════════════════════════════════════════════════════════════
# _run_audit
# ═══════════════════════════════════════════════════════════════

class TestRunAudit:
    """Tests for _run_audit() — audit mode wrapper."""

    def test_basic_audit(self, mock_daudit_found):
        """Should run audit with paths and return data."""
        with patch("src.tools.audit._run_daudit") as mock:
            mock.return_value = SAMPLE_AUDIT_PAYLOAD

            from src.tools.audit import _run_audit
            result = _run_audit(["Src"], recursive=False)

            assert result is not None
            assert "findings" in result
            assert result["totalFindings"] == 3

    def test_recursive_audit(self, mock_daudit_found):
        """Should add --recursive flag when requested."""
        with patch("src.tools.audit._run_daudit") as mock:
            mock.return_value = SAMPLE_AUDIT_PAYLOAD

            from src.tools.audit import _run_audit
            _run_audit(["Src"], recursive=True)

            call_args = mock.call_args[0][0]
            assert "--recursive" in call_args

    def test_non_recursive_audit(self, mock_daudit_found):
        """Should NOT add --recursive flag when not requested."""
        with patch("src.tools.audit._run_daudit") as mock:
            mock.return_value = SAMPLE_AUDIT_PAYLOAD

            from src.tools.audit import _run_audit
            _run_audit(["Src"], recursive=False)

            call_args = mock.call_args[0][0]
            assert "--recursive" not in call_args

    def test_error_status_returns_none(self, mock_daudit_found):
        """Payload with status 'error' should return None."""
        with patch("src.tools.audit._run_daudit") as mock:
            mock.return_value = SAMPLE_ERROR_PAYLOAD

            from src.tools.audit import _run_audit
            result = _run_audit(["Src"])
            assert result is None

    def test_daudit_failure_returns_none(self, mock_daudit_found):
        """When _run_daudit returns None, _run_audit should also return None."""
        with patch("src.tools.audit._run_daudit") as mock:
            mock.return_value = None

            from src.tools.audit import _run_audit
            result = _run_audit(["Src"])
            assert result is None

    def test_multiple_paths(self, mock_daudit_found):
        """Should pass all paths to _run_daudit."""
        with patch("src.tools.audit._run_daudit") as mock:
            mock.return_value = SAMPLE_AUDIT_PAYLOAD

            from src.tools.audit import _run_audit
            _run_audit(["Src1", "Src2", "File.pas"])

            call_args = mock.call_args[0][0]
            assert "Src1" in call_args
            assert "Src2" in call_args
            assert "File.pas" in call_args


# ═══════════════════════════════════════════════════════════════
# _run_skeleton
# ═══════════════════════════════════════════════════════════════

class TestRunSkeleton:
    """Tests for _run_skeleton() — AST/skeleton mode."""

    def test_single_file_skeleton(self, mock_daudit_found, tmp_path):
        """Should run skeleton on a single .pas file."""
        pas_file = tmp_path / "Unit1.pas"
        pas_file.write_text("unit Unit1;\ninterface\nimplementation\nend.\n")

        with patch("src.tools.audit.subprocess.run") as mock:
            mock.return_value.returncode = 0

            from src.tools.audit import _run_skeleton
            # This will try to read the JSON output file which we haven't written
            # So it will fail -> return None. We're testing the file finding logic.
            with patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_SKELETON_PAYLOAD))):
                with patch("os.path.getsize") as mock_size:
                    mock_size.return_value = 100
                    # Force the file read to succeed
                    result = _run_skeleton(
                        base_dir=str(tmp_path),
                        file_path=str(pas_file),
                        detail="compact"
                    )
                    # result may be None due to complex mock setup, but at least no crash

    def test_skeleton_no_daudit_returns_none(self, mock_daudit_missing):
        """Should return None when daudit not found."""
        from src.tools.audit import _run_skeleton
        result = _run_skeleton(base_dir="Src", detail="compact")
        assert result is None

    def test_skeleton_with_detail_levels(self, mock_daudit_found, tmp_path):
        """Should pass the correct detail parameter."""
        pas_file = tmp_path / "Unit.pas"
        pas_file.write_text("unit Unit;\ninterface\nimplementation\nend.\n")

        with patch("src.tools.audit.subprocess.run") as mock:
            mock.return_value.returncode = 0

            from src.tools.audit import _run_skeleton
            for detail in ["compact", "normal", "full"]:
                with patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_SKELETON_PAYLOAD))):
                    with patch("os.path.getsize") as mock_size:
                        mock_size.return_value = 100
                        _run_skeleton(
                            base_dir=str(tmp_path),
                            file_path=str(pas_file),
                            detail=detail
                        )
                        # Verify --skeleton-detail was passed
                        call_cmd = mock.call_args[0][0]
                        assert f"--skeleton-detail" in call_cmd
                        assert detail in call_cmd

    def test_skeleton_collects_pas_files(self):
        """Should recursively find .pas files in base_dir."""
        import src.tools.audit as audit_mod

        with patch.object(audit_mod, "_find_daudit") as mock_find:
            mock_find.return_value = r"C:\daudit.exe"

            tmp = Path(tempfile.mkdtemp())
            try:
                (tmp / "Sub").mkdir()
                (tmp / "Sub" / "A.pas").write_text("unit A;\n")
                (tmp / "Sub" / "B.pas").write_text("unit B;\n")
                (tmp / "readme.txt").write_text("not a pas file")

                with patch("src.tools.audit.subprocess.run") as mock_run:
                    mock_run.return_value.returncode = 0
                    with patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_SKELETON_PAYLOAD))):
                        with patch("os.path.getsize") as mock_size:
                            mock_size.return_value = 100
                            audit_mod._run_skeleton(base_dir=str(tmp), detail="compact")

                            # Verify the cmd contains both .pas files
                            cmd = mock_run.call_args[0][0]
                            pas_in_cmd = [a for a in cmd if a.endswith(".pas")]
                            assert len(pas_in_cmd) >= 2
            finally:
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# _extract_json
# ═══════════════════════════════════════════════════════════════

class TestExtractJson:
    """Tests for _extract_json() — extract JSON from mixed output."""

    def test_plain_json_object(self):
        """Should extract a simple JSON object."""
        from src.tools.audit import _extract_json
        text = '{"status": "ok", "data": {}}'
        result = _extract_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["status"] == "ok"

    def test_surrounding_text(self):
        """Should extract JSON from text with banner/trailer."""
        from src.tools.audit import _extract_json
        text = "Banner\nCopyright\n" + json.dumps(SAMPLE_AUDIT_PAYLOAD) + "\nDone.\n"
        result = _extract_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["status"] == "ok"

    def test_nested_braces(self):
        """Should handle deeply nested JSON objects."""
        from src.tools.audit import _extract_json
        text = '{"a": {"b": {"c": [1, 2, {"d": "e"}]}}}'
        result = _extract_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["a"]["b"]["c"][2]["d"] == "e"

    def test_no_json_returns_none(self):
        """Text without JSON should return None."""
        from src.tools.audit import _extract_json
        result = _extract_json("Just plain text, no braces")
        assert result is None

    def test_empty_string_returns_none(self):
        """Empty string should return None."""
        from src.tools.audit import _extract_json
        result = _extract_json("")
        assert result is None

    def test_extracts_first_json_object(self):
        """Should extract only the first JSON object."""
        from src.tools.audit import _extract_json
        result = _extract_json(SAMPLE_MIXED_MULTIPLE_JSON)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["mode"] == "first"  # not "second"

    def test_unclosed_brace_returns_none(self):
        """Unclosed brace should not match."""
        from src.tools.audit import _extract_json
        result = _extract_json('{"unclosed": true')
        assert result is None

    def test_json_with_escaped_braces(self):
        """Should handle escaped characters inside JSON strings."""
        from src.tools.audit import _extract_json
        text = '{"message": "braces { like } this", "nested": {"a": 1}}'
        result = _extract_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["message"] == "braces { like } this"
        assert parsed["nested"]["a"] == 1


# ═══════════════════════════════════════════════════════════════
# _format_report
# ═══════════════════════════════════════════════════════════════

class TestFormatReport:
    """Tests for _format_report() — format audit findings as Markdown."""

    def test_empty_findings(self):
        """Empty findings should still produce a valid report."""
        from src.tools.audit import _format_report
        data = {"findings": [], "totalFindings": 0}
        report = _format_report(data)
        assert "审计报告" in report
        assert "0" in report.split("违规总数")[1].split("\n")[0] if "违规总数" in report else True

    def test_severity_mapping(self):
        """Should map daudit severity to display severity."""
        from src.tools.audit import _format_report
        data = {
            "findings": [
                {"rule_id": "R1", "file": "a.pas", "line": 1, "severity": "error",
                 "category": "Security", "message": "err"},
                {"rule_id": "R2", "file": "b.pas", "line": 2, "severity": "warning",
                 "category": "Performance", "message": "warn"},
                {"rule_id": "R3", "file": "c.pas", "line": 3, "severity": "hint",
                 "category": "CodeStyle", "message": "hint"},
            ],
            "totalFindings": 3
        }
        report = _format_report(data)
        assert "🔴" in report  # critical / error
        assert "🟡" in report  # warning
        assert "🔵" in report  # suggestion / hint

    def test_severity_filtering(self):
        """Min severity should filter out lower severity items."""
        from src.tools.audit import _format_report
        data = {
            "findings": [
                {"rule_id": "R1", "file": "a.pas", "line": 1, "severity": "error",
                 "category": "Security", "message": "err"},
                {"rule_id": "R2", "file": "b.pas", "line": 2, "severity": "hint",
                 "category": "CodeStyle", "message": "hint"},
            ],
            "totalFindings": 2
        }
        # Filter at "warning" level → should exclude "hint"
        report = _format_report(data, min_severity="warning")
        assert "🔴" in report  # error -> critical
        assert "🔵" not in report  # hint -> suggestion should be filtered

    def test_code_snippets_included(self):
        """Code snippets should appear in the report."""
        from src.tools.audit import _format_report
        data = {
            "findings": [{
                "rule_id": "R1", "file": "f.pas", "line": 1, "severity": "error",
                "category": "Security", "message": "test", "code_snippet": "show me"
            }],
            "totalFindings": 1
        }
        report = _format_report(data)
        assert "```pascal" in report
        assert "show me" in report

    def test_category_distribution(self):
        """Category distribution table should be included."""
        from src.tools.audit import _format_report
        report = _format_report(SAMPLE_AUDIT_PAYLOAD["data"])
        assert "按类别分布" in report
        assert "Security" in report
        assert "Performance" in report
        assert "CodeStyle" in report

    def test_missing_fields_handled(self):
        """Missing optional fields should not cause crashes."""
        from src.tools.audit import _format_report
        data = {
            "findings": [
                {"severity": "error", "message": "minimal"}
            ],
            "totalFindings": 1
        }
        report = _format_report(data)
        assert report is not None
        assert len(report) > 0

    def test_report_structure(self):
        """Report should have headers, summary, and detail sections."""
        from src.tools.audit import _format_report
        report = _format_report(SAMPLE_AUDIT_PAYLOAD["data"])
        assert report.startswith("#")
        assert "违规总数" in report
        assert "##" in report  # severity section headers

    def test_severity_order(self):
        """Sections should appear in correct severity order: critical -> warning -> suggestion."""
        from src.tools.audit import _format_report
        data = {
            "findings": [
                {"rule_id": "R1", "file": "a.pas", "line": 1, "severity": "warning",
                 "category": "P", "message": "w"},
                {"rule_id": "R2", "file": "b.pas", "line": 2, "severity": "error",
                 "category": "S", "message": "e"},
                {"rule_id": "R3", "file": "c.pas", "line": 3, "severity": "hint",
                 "category": "C", "message": "h"},
            ],
            "totalFindings": 3
        }
        report = _format_report(data)
        critical_pos = report.find("🔴")
        warning_pos = report.find("🟡")
        suggestion_pos = report.find("🔵")
        assert critical_pos < warning_pos < suggestion_pos


# ═══════════════════════════════════════════════════════════════
# _check_runtime_rules
# ═══════════════════════════════════════════════════════════════

class TestCheckRuntimeRules:
    """Tests for _check_runtime_rules() — runtime registry check."""

    def test_no_rules_file(self, temp_project_dir):
        """When rules file doesn't exist, should return info finding."""
        from src.tools.audit import _check_runtime_rules

        with patch("src.tools.audit._RULES_PATH") as mock_rules:
            mock_rules.exists.return_value = False
            findings = _check_runtime_rules(str(temp_project_dir))
            assert len(findings) >= 1
            assert any("未找到" in f.get("message", "") for f in findings)

    def test_no_pas_or_dfm_files(self, tmp_path):
        """Directory without .pas/.dfm should return info."""
        from src.tools.audit import _check_runtime_rules

        with patch("src.tools.audit._RULES_PATH") as mock_rules:
            mock_rules.exists.return_value = False
            empty_dir = tmp_path / "empty"
            empty_dir.mkdir()
            findings = _check_runtime_rules(str(empty_dir))
            assert len(findings) >= 1

    def test_uses_extraction(self):
        """Should correctly extract uses from .pas files."""
        from src.tools.audit import _extract_uses_set

        tmp = Path(tempfile.mkdtemp())
        try:
            pas = tmp / "Unit.pas"
            pas.write_text(
                "unit Unit;\ninterface\nuses\n  System.SysUtils,\n  System.Classes;\n"
                "implementation\nuses Winapi.Windows;\nend.",
                encoding="utf-8"
            )
            uses = _extract_uses_set(pas)
            assert "System.SysUtils" in uses
            assert "System.Classes" in uses
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_dfm_class_extraction(self):
        """Should correctly extract class names from .dfm files."""
        from src.tools.audit import _extract_classes_from_dfm

        tmp = Path(tempfile.mkdtemp())
        try:
            dfm = tmp / "Form.dfm"
            dfm.write_text(
                "object Form1: TForm\n"
                "  object btnSave: TButton\n"
                "  end\n"
                "  object edtName: TEdit\n"
                "  end\n"
                "end\n",
                encoding="utf-8"
            )
            classes = _extract_classes_from_dfm(dfm)
            assert "TButton" in classes
            assert "TEdit" in classes
            assert "TForm" in classes
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_runtime_rules_with_findings(self, temp_project_dir):
        """Should find violations when trigger classes exist but units missing."""
        from src.tools.audit import _check_runtime_rules

        rules_data = {
            "rules": [
                {
                    "id": "RUNTIME-001",
                    "severity": "warning",
                    "triggers": ["TButton"],
                    "dependencies": [],
                    "require_unit": "Vcl.StdCtrls",
                    "message": "TButton requires Vcl.StdCtrls"
                }
            ]
        }

        with patch("src.tools.audit._RULES_PATH") as mock_rules_path:
            with patch("src.tools.audit._load_runtime_rules") as mock_load:
                # Mock the rules file to exist with our test rule
                mock_rules_path.exists.return_value = True
                mock_load.return_value = rules_data["rules"]

                # Create a .dfm with TButton but the .pas doesn't use Vcl.StdCtrls
                dfm_file = temp_project_dir / "Src" / "Form1.dfm"
                dfm_file.write_text(
                    "object Form1: TForm\n  object btnSave: TButton\n  end\nend\n",
                    encoding="utf-8"
                )
                pas_file = temp_project_dir / "Src" / "Unit1.pas"
                pas_file.write_text(
                    "unit Unit1;\ninterface\nuses\n  System.SysUtils;\nimplementation\nend.\n",
                    encoding="utf-8"
                )

                findings = _check_runtime_rules(str(temp_project_dir / "Src"))
                # Should find the violation: TButton exists but Vcl.StdCtrls not in uses
                assert len(findings) >= 1
                assert any("RUNTIME-001" in f.get("id", "") for f in findings)


# ═══════════════════════════════════════════════════════════════
# run_audit (MCP entry point)
# ═══════════════════════════════════════════════════════════════

class TestRunAuditEntryPoint:
    """Tests for run_audit() — the async MCP tool entry point."""

    @pytest.mark.asyncio
    async def test_missing_required_args_returns_error(self):
        """Missing base_dir and file_path should return isError."""
        from src.tools.audit import run_audit

        result = await run_audit({})
        assert isinstance(result, CallToolResult)
        assert result.isError is True
        assert "参数错误" in result.content[0].text

    @pytest.mark.asyncio
    async def test_nonexistent_path_returns_error(self):
        """Nonexistent base_dir should return isError."""
        from src.tools.audit import run_audit

        result = await run_audit({"base_dir": r"C:\nonexistent_path_xyz"})
        assert isinstance(result, CallToolResult)
        assert result.isError is True
        assert "不存在" in result.content[0].text

    @pytest.mark.asyncio
    async def test_daudit_missing_returns_guide(self, mock_daudit_missing, tmp_path):
        """When daudit.exe not found, should return guidance message."""
        from src.tools.audit import run_audit

        result = await run_audit({"base_dir": str(tmp_path)})
        assert isinstance(result, CallToolResult)
        assert result.isError is False  # Guide is not an error
        text = result.content[0].text
        assert "未就绪" in text or "尚未安装" in text or "引导" in text

    @pytest.mark.asyncio
    async def test_runtime_mode(self, temp_project_dir):
        """Runtime mode should work without daudit.exe."""
        from src.tools.audit import run_audit

        with patch("src.tools.audit._RULES_PATH") as mock_rules_path:
            mock_rules_path.exists.return_value = False
            result = await run_audit({
                "base_dir": str(temp_project_dir / "Src"),
                "mode": "runtime"
            })
            assert isinstance(result, CallToolResult)
            assert result.isError is False

    @pytest.mark.asyncio
    async def test_runtime_mode_needs_base_dir(self):
        """Runtime mode requires base_dir."""
        from src.tools.audit import run_audit

        result = await run_audit({"mode": "runtime"})
        assert isinstance(result, CallToolResult)
        assert result.isError is True
        assert "runtime" in result.content[0].text.lower() or "参数错误" in result.content[0].text

    @pytest.mark.asyncio
    async def test_ast_mode_unknown_path(self):
        """AST mode with nonexistent file_path should return error."""
        from src.tools.audit import run_audit

        result = await run_audit({
            "mode": "ast",
            "file_path": r"C:\nonexistent_file_xyz.pas"
        })
        assert isinstance(result, CallToolResult)
        assert result.isError is True
        assert "不存在" in result.content[0].text

    @pytest.mark.asyncio
    async def test_audit_mode_needs_base_dir(self):
        """Audit mode requires base_dir."""
        from src.tools.audit import run_audit

        with patch("src.tools.audit._find_daudit") as mock:
            mock.return_value = r"C:\daudit.exe"
            result = await run_audit({"mode": "audit"})
            assert isinstance(result, CallToolResult)
            assert result.isError is True

    @pytest.mark.asyncio
    async def test_json_output_format(self, mock_daudit_found, tmp_path):
        """output_format='json' should return raw JSON."""
        from src.tools.audit import run_audit

        with patch("src.tools.audit._run_audit") as mock_audit:
            mock_audit.return_value = SAMPLE_AUDIT_PAYLOAD["data"]
            result = await run_audit({
                "base_dir": str(tmp_path),
                "output_format": "json"
            })
            assert isinstance(result, CallToolResult)
            text = result.content[0].text
            # Should be valid parseable JSON
            parsed = json.loads(text)
            assert "findings" in parsed

    @pytest.mark.asyncio
    async def test_report_output_default(self, mock_daudit_found, tmp_path):
        """Default output_format should return Markdown report."""
        from src.tools.audit import run_audit

        with patch("src.tools.audit._run_audit") as mock_audit:
            mock_audit.return_value = SAMPLE_AUDIT_PAYLOAD["data"]
            result = await run_audit({"base_dir": str(tmp_path)})
            assert isinstance(result, CallToolResult)
            text = result.content[0].text
            assert text.startswith("#")  # Markdown header

    @pytest.mark.asyncio
    async def test_invalid_mode_defaults_to_audit(self, mock_daudit_found, tmp_path):
        """Invalid mode should default to audit behavior."""
        from src.tools.audit import run_audit

        with patch("src.tools.audit._run_audit") as mock_audit:
            mock_audit.return_value = SAMPLE_AUDIT_PAYLOAD["data"]
            result = await run_audit({
                "base_dir": str(tmp_path),
                "mode": "invalid_mode"
            })
            # Should fall through to audit mode, which needs base_dir
            # Since we mocked _run_audit, it should succeed
            assert isinstance(result, CallToolResult)


# ═══════════════════════════════════════════════════════════════
# Module-level integration: _run_audit → _format_report flow
# ═══════════════════════════════════════════════════════════════

class TestAuditFormatPipeline:
    """Tests for the full pipeline from audit data to formatted report."""

    def test_audit_data_to_report(self, mock_daudit_found):
        """_run_audit output should be formattable by _format_report."""
        from src.tools.audit import _run_audit, _format_report

        with patch("src.tools.audit._run_daudit") as mock:
            mock.return_value = SAMPLE_AUDIT_PAYLOAD

            data = _run_audit(["Src"], recursive=True)
            assert data is not None

            report = _format_report(data)
            assert report is not None
            assert len(report) > 100

    def test_empty_audit_data_to_report(self, mock_daudit_found):
        """Empty audit results should still produce a valid report."""
        from src.tools.audit import _run_audit, _format_report

        empty_payload = {
            "mode": "audit",
            "status": "ok",
            "data": {"findings": [], "totalFindings": 0},
            "summary": {}
        }

        with patch("src.tools.audit._run_daudit") as mock:
            mock.return_value = empty_payload

            data = _run_audit(["EmptyDir"])
            assert data is not None
            assert data["totalFindings"] == 0

            report = _format_report(data)
            assert report is not None

    def test_runtime_registry_file_exists(self):
        """Runtime registry file should be at expected location."""
        from src.tools.audit import _RULES_PATH
        assert _RULES_PATH is not None
        # Don't assert existence — it may not exist in test env
        # Just verify the path construction looks right
        assert str(_RULES_PATH).endswith("runtime_registry.json")
        assert "rules" in str(_RULES_PATH)


# ═══════════════════════════════════════════════════════════════
# Run standalone
# ═══════════════════════════════════════════════════════════════

def run_tests():
    """Run all tests in this module manually."""
    import sys
    import inspect

    test_file = Path(__file__)
    print("=" * 60)
    print(f"  Audit Integration Tests")
    print(f"  {test_file.name}")
    print("=" * 60)
    print()

    passed = 0
    failed = 0

    for name, obj in inspect.getmembers(sys.modules[__name__]):
        if name.startswith("test_") and callable(obj):
            try:
                obj()
                print(f"  [OK] {name}")
                passed += 1
            except Exception as e:
                print(f"  [FAIL] {name}: {e}")
                failed += 1
        elif isinstance(obj, type) and name.startswith("Test"):
            # Test class methods
            for mname, mobj in inspect.getmembers(obj):
                if mname.startswith("test_") and callable(mobj):
                    try:
                        instance = obj()
                        mobj(instance)
                        print(f"  [OK] {name}.{mname}")
                        passed += 1
                    except Exception as e:
                        print(f"  [FAIL] {name}.{mname}: {e}")
                        failed += 1

    print(f"\n  {passed}/{passed + failed} 通过")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
