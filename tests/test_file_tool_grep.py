#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 delphi_file grep 模式 — 单文件/批量搜索与替换。
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path
import pytest

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.tools.file_tool import (
    handle_file_tool,
    handle_grep,
    _glob_files,
    _resolve_grep_targets,
    _grep_search_fulltext,
    _grep_search,
    _grep_replace,
    _is_dfm_file,
    _mark_dirty,
    _clear_dirty,
)


# ============================================================
# Helpers
# ============================================================

def _make_file(path: str, content: str = "unit Test;\nbegin\nend.\n",
               encoding: str = "utf-8") -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding=encoding) as f:
        f.write(content)
    return path


def _make_pas_file(path: str, content: str = None) -> str:
    if content is None:
        content = """unit TestUnit;

interface

uses
  SysUtils, Classes;

type
  TMyClass = class
  private
    FName: string;
  public
    procedure DoSomething;
  end;

  TOtherClass = class
  public
    procedure DoOther;
  end;

implementation

procedure TMyClass.DoSomething;
begin
  // do something
end;

procedure TOtherClass.DoOther;
begin
  // do other thing
end;

end.
"""
    return _make_file(path, content)


# ============================================================
# _glob_files
# ============================================================

class TestGlobFiles:
    def test_glob_basic(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            a = _make_file(os.path.join(tmp_dir, "a.pas"), "unit a;")
            b = _make_file(os.path.join(tmp_dir, "b.pas"), "unit b;")
            _make_file(os.path.join(tmp_dir, "c.dfm"), "object")
            result = _glob_files(tmp_dir, include="*.pas")
            assert len(result) == 2
            assert a in result
            assert b in result
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_glob_recursive(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            _make_file(os.path.join(tmp_dir, "root.pas"), "unit root;")
            sub = os.path.join(tmp_dir, "sub")
            _make_file(os.path.join(sub, "deep.pas"), "unit deep;")
            result = _glob_files(tmp_dir, include="**/*.pas")
            assert len(result) == 2
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_glob_exclude(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            _make_file(os.path.join(tmp_dir, "keep.pas"), "unit keep;")
            _make_file(os.path.join(tmp_dir, "skip.pas"), "unit skip;")
            result = _glob_files(tmp_dir, include="*.pas", exclude="skip.pas")
            assert len(result) == 1
            assert "skip.pas" not in result[0]
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_glob_no_match(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            _make_file(os.path.join(tmp_dir, "a.txt"), "text")
            result = _glob_files(tmp_dir, include="*.pas")
            assert result == []
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_glob_nonexistent_dir(self):
        result = _glob_files(r"C:\nonexistent_dir_xyz_12345", include="*.pas")
        assert result == []


# ============================================================
# _resolve_grep_targets
# ============================================================

class TestResolveGrepTargets:
    def test_file_path(self):
        targets, err = _resolve_grep_targets({"file_path": "test.pas"})
        assert err is None
        assert targets == ["test.pas"]

    def test_files(self):
        targets, err = _resolve_grep_targets({"files": ["a.pas", "b.pas"]})
        assert err is None
        assert targets == ["a.pas", "b.pas"]

    def test_files_empty(self):
        targets, err = _resolve_grep_targets({"files": []})
        assert err is not None
        assert targets is None

    def test_path(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            _make_file(os.path.join(tmp_dir, "a.pas"), "unit a;")
            _make_file(os.path.join(tmp_dir, "b.pas"), "unit b;")
            targets, err = _resolve_grep_targets({"path": tmp_dir, "include": "*.pas"})
            assert err is None
            assert len(targets) == 2
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_path_no_match(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            _make_file(os.path.join(tmp_dir, "a.txt"), "text")
            targets, err = _resolve_grep_targets({"path": tmp_dir, "include": "*.pas"})
            assert err is not None
            assert targets is None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_no_target(self):
        targets, err = _resolve_grep_targets({})
        assert err is not None
        assert "file_path" in err

    def test_file_path_priority(self):
        """file_path 优先于 files 和 path"""
        targets, err = _resolve_grep_targets({
            "file_path": "a.pas",
            "files": ["b.pas", "c.pas"],
            "path": "/tmp",
        })
        assert err is None
        assert targets == ["a.pas"]


# ============================================================
# handle_grep — 向后兼容（单文件+单 pattern）
# ============================================================

@pytest.mark.asyncio
class TestGrepSingleFileBackwardCompat:
    """确保旧版调用模式的行为完全不变。"""

    async def test_grep_no_file_path(self):
        result = await handle_file_tool({"action": "grep"})
        assert result.get("status") == "failed"
        assert "pattern" in result.get("message", "")

    async def test_grep_no_pattern(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False)
        tmp.write("unit Test;\nbegin\nend.\n")
        tmp.close()
        try:
            result = await handle_file_tool({"action": "grep", "file_path": tmp.name})
            assert result.get("status") == "failed"
            assert "pattern" in result.get("message", "")
        finally:
            os.unlink(tmp.name)

    async def test_grep_simple_search(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False,
                                          encoding="utf-8")
        tmp.write("procedure Test;\nbegin\n  ShowMessage('hello');\nend;\n")
        tmp.close()
        try:
            result = await handle_file_tool({
                "action": "grep",
                "file_path": tmp.name,
                "pattern": "ShowMessage",
            })
            assert result.get("status") == "success"
            assert result.get("total", 0) >= 1
            assert "output" in result
        finally:
            os.unlink(tmp.name)

    async def test_grep_with_context(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False,
                                          encoding="utf-8")
        tmp.write("line1\nline2\ntarget\nline3\nline4\n")
        tmp.close()
        try:
            result = await handle_file_tool({
                "action": "grep",
                "file_path": tmp.name,
                "pattern": "target",
                "context": 1,
            })
            assert result.get("status") == "success"
            assert result.get("total", 0) == 1
            matches = result.get("matches", [])
            assert len(matches) == 1
            # context=1 gives 3 lines (1 before + target + 1 after)
            assert len(matches[0]) >= 3
        finally:
            os.unlink(tmp.name)

    async def test_grep_replace_dry_run(self):
        content = "unit Test;\nbegin\n  OldName;\nend;\n"
        tmp = tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False,
                                          encoding="utf-8")
        tmp.write(content)
        tmp.close()
        try:
            result = await handle_file_tool({
                "action": "grep",
                "file_path": tmp.name,
                "pattern": "OldName",
                "replace": "NewName",
                "dry_run": True,
            })
            assert result.get("status") == "success"
            assert result.get("replaced", 0) >= 1
            assert result.get("dry_run") is True
            # File content should NOT have changed
            with open(tmp.name, "r") as f:
                assert "OldName" in f.read()
        finally:
            os.unlink(tmp.name)

    async def test_grep_replace_live(self):
        content = "unit Test;\nbegin\n  OldName;\nend;\n"
        tmp = tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False,
                                          encoding="utf-8")
        tmp.write(content)
        tmp.close()
        try:
            result = await handle_file_tool({
                "action": "grep",
                "file_path": tmp.name,
                "pattern": "OldName",
                "replace": "NewName",
                "dry_run": False,
            })
            assert result.get("status") == "success"
            assert result.get("replaced", 0) >= 1
            # File content should have changed
            with open(tmp.name, "r") as f:
                new_content = f.read()
            assert "NewName" in new_content
            assert "OldName" not in new_content
        finally:
            os.unlink(tmp.name)

    async def test_grep_case_insensitive(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False,
                                          encoding="utf-8")
        tmp.write("procedure Test;\nbegin\n  showmessage('hi');\nend;\n")
        tmp.close()
        try:
            result = await handle_file_tool({
                "action": "grep",
                "file_path": tmp.name,
                "pattern": "/ShowMessage/i",
            })
            assert result.get("status") == "success"
            assert result.get("total", 0) >= 1
        finally:
            os.unlink(tmp.name)

    async def test_grep_with_filter(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False,
                                          encoding="utf-8")
        tmp.write("TMyClass = class\nTMyRecord = record\n")
        tmp.close()
        try:
            result = await handle_file_tool({
                "action": "grep",
                "file_path": tmp.name,
                "pattern": "TMy",
                "filter_pattern": "class",
            })
            assert result.get("status") == "success"
            assert result.get("total", 0) == 1
        finally:
            os.unlink(tmp.name)

    async def test_grep_with_exclude(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False,
                                          encoding="utf-8")
        tmp.write("TMyClass = class\nTMyRecord = record\n")
        tmp.close()
        try:
            result = await handle_file_tool({
                "action": "grep",
                "file_path": tmp.name,
                "pattern": "TMy",
                "exclude_pattern": "record",
            })
            assert result.get("status") == "success"
            assert result.get("total", 0) == 1
        finally:
            os.unlink(tmp.name)

    async def test_grep_fulltext_multiline(self):
        content = "procedure Test;\nbegin\n  // start\n  call;\n  // end\nend;\n"
        tmp = tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False,
                                          encoding="utf-8")
        tmp.write(content)
        tmp.close()
        try:
            result = await handle_file_tool({
                "action": "grep",
                "file_path": tmp.name,
                "pattern": "/begin[\\s\\S]*?end;/s",
            })
            assert result.get("status") == "success"
            assert result.get("total", 0) >= 1
        finally:
            os.unlink(tmp.name)


# ============================================================
# handle_grep — 批量模式
# ============================================================

@pytest.mark.asyncio
class TestGrepBatch:
    """测试目录递归和文件列表批量搜索。"""

    async def test_batch_path_search(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            _make_pas_file(os.path.join(tmp_dir, "Unit1.pas"))
            _make_pas_file(os.path.join(tmp_dir, "Unit2.pas"),
                           "unit Unit2;\ninterface\ntype\n  TMyClass = class\nend;\n")
            result = await handle_file_tool({
                "action": "grep",
                "path": tmp_dir,
                "include": "*.pas",
                "pattern": "TMyClass",
            })
            assert result.get("status") == "success"
            assert result.get("file_count", 0) >= 2
            assert result.get("total_matches", 0) >= 2
            files = result.get("files", {})
            assert len(files) >= 2
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def test_batch_path_no_match(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            _make_pas_file(os.path.join(tmp_dir, "Unit1.pas"))
            result = await handle_file_tool({
                "action": "grep",
                "path": tmp_dir,
                "include": "*.pas",
                "pattern": "NonExistentSymbolXYZ",
            })
            assert result.get("status") == "success"
            assert result.get("file_count", 0) == 0
            assert result.get("total_matches", 0) == 0
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def test_batch_files_search(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            f1 = _make_pas_file(os.path.join(tmp_dir, "A.pas"))
            f2 = _make_pas_file(os.path.join(tmp_dir, "B.pas"),
                                "unit B;\ninterface\ntype\n  TMyClass = class\nend;\n")
            result = await handle_file_tool({
                "action": "grep",
                "files": [f1, f2],
                "pattern": "TMyClass",
            })
            assert result.get("status") == "success"
            assert result.get("file_count", 0) >= 1
            assert result.get("total_matches", 0) >= 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def test_batch_path_recursive(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            _make_pas_file(os.path.join(tmp_dir, "Root.pas"))
            sub_dir = os.path.join(tmp_dir, "sub")
            _make_pas_file(os.path.join(sub_dir, "Deep.pas"))
            result = await handle_file_tool({
                "action": "grep",
                "path": tmp_dir,
                "include": "**/*.pas",
                "pattern": "TMyClass",
            })
            assert result.get("status") == "success"
            assert result.get("file_count", 0) >= 2
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def test_batch_path_with_include_filter(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            _make_pas_file(os.path.join(tmp_dir, "keep.pas"))
            _make_file(os.path.join(tmp_dir, "skip.txt"),
                       "TMyClass = something")
            result = await handle_file_tool({
                "action": "grep",
                "path": tmp_dir,
                "include": "*.pas",
                "pattern": "TMyClass",
            })
            assert result.get("status") == "success"
            # path 模式走 batch 输出，使用 total_matches
            assert result.get("file_count", 0) == 1
            assert result.get("total_matches", 0) >= 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def test_batch_path_exclude(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            _make_pas_file(os.path.join(tmp_dir, "keep.pas"))
            _make_pas_file(os.path.join(tmp_dir, "generated.pas"))
            result = await handle_file_tool({
                "action": "grep",
                "path": tmp_dir,
                "include": "*.pas",
                "exclude": "generated.pas",
                "pattern": "TMyClass",
            })
            assert result.get("status") == "success"
            files = result.get("files", {})
            # 确保 generated.pas 不在结果中
            for fname in files:
                assert "generated" not in fname
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def test_batch_replace_dry_run(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            f1 = _make_pas_file(os.path.join(tmp_dir, "Unit1.pas"))
            f2 = _make_pas_file(os.path.join(tmp_dir, "Unit2.pas"),
                                "unit B;\ninterface\ntype\n  TMyClass = class\nend;\n")
            result = await handle_file_tool({
                "action": "grep",
                "files": [f1, f2],
                "pattern": "TMyClass",
                "replace": "TNewClass",
                "dry_run": True,
            })
            assert result.get("status") == "success"
            assert result.get("total_matches", 0) >= 2
            # File should NOT have changed
            with open(f1, "r") as f:
                assert "TMyClass" in f.read()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def test_batch_path_with_dfm_skip(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            _make_pas_file(os.path.join(tmp_dir, "main.pas"))
            _make_file(os.path.join(tmp_dir, "form.dfm"),
                       "object Form1: TForm\nend")
            # 搜一个 pas 中存在的词，DFM 文件自动跳过
            result = await handle_file_tool({
                "action": "grep",
                "path": tmp_dir,
                "include": "*",
                "pattern": "TMyClass",
            })
            # DFM 文件会被静默跳过，pas 文件正常搜索
            assert result.get("status") == "success"
            assert result.get("file_count", 0) == 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def test_batch_path_not_found(self):
        result = await handle_file_tool({
            "action": "grep",
            "path": r"C:\nonexistent_dir_xyz_54321",
            "pattern": "test",
        })
        assert result.get("status") == "failed"


# ============================================================
# handle_grep — 多 pattern 模式
# ============================================================

@pytest.mark.asyncio
class TestGrepMultiPattern:
    async def test_multi_pattern_single_file(self):
        content = """unit Test;
interface
type
  TFirstClass = class
  end;
  TSecondClass = class
  end;
implementation
end.
"""
        tmp = tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False,
                                          encoding="utf-8")
        tmp.write(content)
        tmp.close()
        try:
                result = await handle_file_tool({
                    "action": "grep",
                    "file_path": tmp.name,
                    "patterns": ["TFirstClass", "TSecondClass"],
                })
                assert result.get("status") == "success"
                # 多 pattern 走 batch 输出
                assert result.get("total_matches", 0) >= 2
                assert result.get("file_count", 0) == 1
        finally:
            os.unlink(tmp.name)

    async def test_multi_pattern_with_shared_flag(self):
        content = "SHOWMESSAGE\nshowmessage\nShowMessage\n"
        tmp = tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False,
                                          encoding="utf-8")
        tmp.write(content)
        tmp.close()
        try:
                result = await handle_file_tool({
                    "action": "grep",
                    "file_path": tmp.name,
                    "patterns": ["/showmessage/i"],
                })
                assert result.get("status") == "success"
                # 单文件多 pattern 走 batch 输出
                assert result.get("total_matches", 0) == 3
        finally:
            os.unlink(tmp.name)

    async def test_multi_pattern_and_batch(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            _make_pas_file(os.path.join(tmp_dir, "A.pas"))
            _make_pas_file(os.path.join(tmp_dir, "B.pas"))
            result = await handle_file_tool({
                "action": "grep",
                "path": tmp_dir,
                "include": "*.pas",
                "patterns": ["TMyClass", "TOtherClass"],
            })
            assert result.get("status") == "success"
            assert result.get("file_count", 0) >= 2
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def test_multi_pattern_no_match(self):
        content = "unit Test;\nbegin\nend.\n"
        tmp = tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False,
                                          encoding="utf-8")
        tmp.write(content)
        tmp.close()
        try:
            result = await handle_file_tool({
                "action": "grep",
                "file_path": tmp.name,
                "patterns": ["NonExistent1", "NonExistent2"],
            })
            assert result.get("status") == "success"
            assert result.get("total", 0) == 0
        finally:
            os.unlink(tmp.name)


# ============================================================
# handle_grep — 参数校验边界
# ============================================================

@pytest.mark.asyncio
class TestGrepEdgeCases:
    async def test_no_target(self):
        result = await handle_file_tool({
            "action": "grep",
            "pattern": "test",
        })
        assert result.get("status") == "failed"

    async def test_both_pattern_and_patterns(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False)
        tmp.write("unit Test;\n")
        tmp.close()
        try:
            result = await handle_file_tool({
                "action": "grep",
                "file_path": tmp.name,
                "pattern": "Test",
                "patterns": ["Test", "Foo"],
            })
            assert result.get("status") == "failed"
            assert "不能同时" in result.get("message", "")
        finally:
            os.unlink(tmp.name)

    async def test_file_not_found(self):
        result = await handle_file_tool({
            "action": "grep",
            "file_path": r"C:\non_existent_file_99999.pas",
            "pattern": "test",
        })
        assert result.get("status") == "failed"

    async def test_dfm_rejected(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".dfm", mode="w", delete=False)
        tmp.write("object Form1: TForm\nend")
        tmp.close()
        try:
            result = await handle_file_tool({
                "action": "grep",
                "file_path": tmp.name,
                "pattern": "TForm",
            })
            assert result.get("status") == "failed"
            assert "DFM" in result.get("message", "")
        finally:
            os.unlink(tmp.name)

    async def test_invalid_regex(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False)
        tmp.write("unit Test;\n")
        tmp.close()
        try:
            result = await handle_file_tool({
                "action": "grep",
                "file_path": tmp.name,
                "pattern": "[invalid",
            })
            assert result.get("status") == "failed"
        finally:
            os.unlink(tmp.name)

    async def test_empty_files_array(self):
        result = await handle_file_tool({
            "action": "grep",
            "files": [],
            "pattern": "test",
        })
        assert result.get("status") == "failed"

    async def test_output_format_batch(self):
        """批量模式的 output 字段格式正确"""
        tmp_dir = tempfile.mkdtemp()
        try:
            _make_file(os.path.join(tmp_dir, "a.pas"),
                       "unit a;\nTMyClass = class\nend;\n")
            _make_file(os.path.join(tmp_dir, "b.pas"),
                       "unit b;\nTMyClass = class\nend;\n")
            result = await handle_file_tool({
                "action": "grep",
                "path": tmp_dir,
                "include": "*.pas",
                "pattern": "TMyClass",
            })
            # output 必须包含文件信息
            output = result.get("output", "")
            assert "批量搜索" in output
            assert "a.pas" in output or os.path.join(tmp_dir, "a.pas") in output
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
