"""path_guard 单元测试 — MCP 路径参数绝对路径校验。"""

import pytest

from src.utils.path_guard import validate_tool_paths


class TestRelativePathsRejected:
    def test_file_path_relative_rejected(self):
        err = validate_tool_paths("delphi_file", {"file_path": "Unit1.pas"})
        assert err is not None
        assert "file_path" in err
        assert "绝对路径" in err

    def test_project_path_relative_rejected(self):
        err = validate_tool_paths(
            "delphi_project", {"project_path": "App.dproj"}
        )
        assert err is not None
        assert "project_path" in err

    def test_file_path_array_item_relative_rejected(self):
        err = validate_tool_paths(
            "delphi_file", {"file_path": ["C:\\project\\Unit1.pas", "src/Unit2.pas"]}
        )
        assert err is not None
        assert "src/Unit2.pas" in err

    def test_posix_relative_rejected(self):
        err = validate_tool_paths("lazarus_file", {"file_path": "src/unit1.pas"})
        assert err is not None

    def test_relative_output_dir_rejected(self):
        err = validate_tool_paths("ocr", {"output_dir": "out"})
        assert err is not None

    def test_error_message_has_example(self):
        err = validate_tool_paths("delphi_file", {"file_path": "Unit1.pas"})
        assert err is not None
        assert "请使用形如" in err
        assert "Unit1.pas" in err


class TestAbsolutePathsAccepted:
    def test_windows_absolute_file_path(self):
        assert (
            validate_tool_paths(
                "delphi_file", {"file_path": "C:\\project\\Unit1.pas"}
            )
            is None
        )

    @pytest.mark.parametrize(
        "path",
        [
            "C:/project/Unit1.pas",
            "D:\\app\\App.dproj",
            "\\\\server\\share\\Unit1.pas",
            "/home/user/project/Unit1.pas",
        ],
    )
    def test_absolute_path_variants(self, path):
        assert validate_tool_paths("delphi_file", {"file_path": path}) is None

    def test_absolute_array_all_accepted(self):
        assert (
            validate_tool_paths(
                "delphi_file",
                {"file_path": ["C:\\project\\Unit1.pas", "D:\\other\\src"]},
            )
            is None
        )


class TestSkippedFields:
    def test_jsonpath_path_ignored(self):
        assert (
            validate_tool_paths(
                "structured_content",
                {"file_path": "C:\\project\\Form1.dfm", "path": "$.Form.Left"},
            )
            is None
        )

    def test_source_file_project_relative_ignored(self):
        assert (
            validate_tool_paths(
                "delphi_project",
                {"project_path": "C:\\project\\App.dproj", "source_file": "Unit1.pas"},
            )
            is None
        )

    def test_code_hosting_files_ignored(self):
        assert (
            validate_tool_paths(
                "code_hosting", {"files": ["src/main.py", "README.md"]}
            )
            is None
        )

    def test_empty_and_none_ignored(self):
        assert validate_tool_paths("delphi_file", {"file_path": ""}) is None
        assert validate_tool_paths("delphi_file", {"file_path": None}) is None
        assert validate_tool_paths("delphi_file", {}) is None

    def test_unknown_tool_ignored(self):
        assert validate_tool_paths("unknown_tool", {"file_path": "Unit1.pas"}) is None


class TestAutomateDelphiScript:
    def test_script_json_object_ignored(self):
        assert (
            validate_tool_paths(
                "automate_delphi",
                {"app_path": "C:\\app\\App.exe", "script": '{"steps": []}'},
            )
            is None
        )

    def test_script_json_array_ignored(self):
        assert (
            validate_tool_paths(
                "automate_delphi",
                {"app_path": "C:\\app\\App.exe", "script": '[{"cmd": "goto"}]'},
            )
            is None
        )

    def test_script_relative_path_rejected(self):
        err = validate_tool_paths(
            "automate_delphi",
            {"app_path": "C:\\app\\App.exe", "script": "script.json"},
        )
        assert err is not None
        assert "script" in err

    def test_script_absolute_path_accepted(self):
        assert (
            validate_tool_paths(
                "automate_delphi",
                {"app_path": "C:\\app\\App.exe", "script": "C:\\app\\script.json"},
            )
            is None
        )


class TestToolCoverage:
    @pytest.mark.parametrize(
        "tool_name,field",
        [
            ("delphi_project", "project_path"),
            ("delphi_kb", "project_path"),
            ("delphi_kb", "directory"),
            ("manage_component", "target_dfm"),
            ("package", "package_path"),
            ("check_environment", "install_dir"),
            ("automate_delphi", "app_path"),
            ("delphi_rtti", "app_path"),
            ("structured_content", "proto_file"),
            ("generate_copyright", "output_dir"),
            ("ocr", "image_path"),
            ("lazarus_compile", "project_path"),
            ("lazarus_project", "project_path"),
            ("lazarus_file", "file_path"),
            ("lazarus_kb", "file_path"),
        ],
    )
    def test_tool_path_field_enforced(self, tool_name, field):
        err = validate_tool_paths(tool_name, {field: "relative/path.ext"})
        assert err is not None
        assert field in err
