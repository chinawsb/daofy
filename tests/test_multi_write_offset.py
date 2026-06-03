"""
Test multi-write offset tracking correctness.

Simulates AI Agent workflow:
  1. Read file -> record line numbers
  2. First partial write -> record offset
  3. Adjust line numbers by offset, second partial write -> verify correct position
  4. Third partial write -> verify accumulated offsets
"""
import os
import re
import tempfile
import shutil
import pytest
from pathlib import Path

project_root = Path(__file__).parent.parent
import sys
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.tools.file_tool import handle_read, handle_write, handle_format


def _make_file(path: str, content: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _assert_success(result: dict):
    assert result.get("status") == "success", f"expected success, got: {result}"


def _extract_offset(msg: str) -> int:
    m = re.search(r'\u504f\u79fb\u91cf:\s*([+-]?\d+)', msg)
    return int(m.group(1)) if m else 0


def _extract_range(msg: str) -> tuple:
    m = re.search(r'0-indexed \[(\d+),\s*(\d+)\)', msg)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (0, 0)


class TestMultiWriteOffset:

    @pytest.fixture
    def tmp_dir(self):
        d = tempfile.mkdtemp()
        yield d
        shutil.rmtree(d, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_two_writes_sequential(self, tmp_dir):
        """Replace middle, then later part. Verify write targets correct lines."""
        file_path = os.path.join(tmp_dir, "seq_test.pas")
        _make_file(file_path, "\n".join(f"L{i}" for i in range(10)) + "\n")

        # First: replace [3,5) = L3,L4 -> X1,X2,X3 (ins 3, del 2, offset=+1)
        r1 = await handle_write({
            "file_path": file_path,
            "content": "X1\nX2\nX3\n",
            "start_line": 3, "end_line": 5,
            "backup": False,
        })
        _assert_success(r1)
        offset1 = _extract_offset(r1["message"])
        assert offset1 == 1, f"first write offset should be +1, got: {offset1}"

        with open(file_path, "r") as f:
            lines = [l.rstrip('\n\r') for l in f.readlines()]
        assert lines[3] == "X1", f"line 4 should be X1, got: {lines[3]}"
        assert lines[4] == "X2", f"line 5 should be X2, got: {lines[4]}"
        assert lines[5] == "X3", f"line 6 should be X3, got: {lines[5]}"
        assert len(lines) == 11, f"should be 11 lines, got: {len(lines)}"

        # Second: replace [8,10) (lines 9,10 in current 11-line file)
        r2 = await handle_write({
            "file_path": file_path,
            "content": "Y1\nY2\n",
            "start_line": 8, "end_line": 10,
            "backup": False,
        })
        _assert_success(r2)

        with open(file_path, "r") as f:
            lines = [l.rstrip('\n\r') for l in f.readlines()]
        assert lines[8] == "Y1", f"line 9 should be Y1, got: {lines[8]}"
        assert lines[9] == "Y2", f"line 10 should be Y2, got: {lines[9]}"
        assert len(lines) == 11, f"final should be 11 lines, got: {len(lines)}"

    @pytest.mark.asyncio
    async def test_three_writes_accumulated_offset(self, tmp_dir):
        """Three sequential partial writes verify correct final content."""
        file_path = os.path.join(tmp_dir, "accum_test.pas")
        _make_file(file_path, "\n".join(f"L{i}" for i in range(10)) + "\n")

        # 1) Replace [2,4) (L2,L3) -> A1,A2,A3 (ins 3, del 2, offset=+1)
        r1 = await handle_write({
            "file_path": file_path,
            "content": "A1\nA2\nA3\n",
            "start_line": 2, "end_line": 4,
            "backup": False,
        })
        _assert_success(r1)
        assert _extract_offset(r1["message"]) == 1

        # 2) Replace [4,7) (3 lines) -> B1 (ins 1, del 3, offset=-2)
        r2 = await handle_write({
            "file_path": file_path,
            "content": "B1\n",
            "start_line": 4, "end_line": 7,
            "backup": False,
        })
        _assert_success(r2)
        assert _extract_offset(r2["message"]) == -2

        # 3) Replace [3,5) -> C1,C2 (ins 2, del 2, offset=0)
        r3 = await handle_write({
            "file_path": file_path,
            "content": "C1\nC2\n",
            "start_line": 3, "end_line": 5,
            "backup": False,
        })
        _assert_success(r3)
        assert _extract_offset(r3["message"]) == 0

        # Trace (0-indexed):
        # Initial:  L0 L1 [L2 L3] L4 L5 L6 L7 L8 L9
        # Write1 [2,4): L0 L1 A1 A2 A3 L4 L5 L6 L7 L8 L9  (+1)
        # Write2 [4,7): L0 L1 A1 A2 B1 L6 L7 L8 L9          (-2,  indexes 4=A3,5=L4,6=L5)
        # Write3 [3,5): L0 L1 A1 C1 C2 L6 L7 L8 L9          (0,   indexes 3=A2,4=B1)
        with open(file_path, "r") as f:
            lines = [l.rstrip('\n\r') for l in f.readlines()]
        expected = ["L0", "L1", "A1", "C1", "C2", "L6", "L7", "L8", "L9"]
        assert lines == expected, f"Expected {expected}, got {lines}"
        assert len(lines) == 9, f"final should be 9 lines, got: {len(lines)}"

    @pytest.mark.asyncio
    async def test_auto_format_offset_correction(self, tmp_dir):
        """
        auto_format=True: offset should be based on ACTUAL file after pasfmt.
        Pasfmt mock adds 1 extra line during formatting.
        """
        file_path = os.path.join(tmp_dir, "fmt_correct.pas")
        _make_file(file_path, "unit  Test; \ninterface\n\nimplementation\n\nend.\n")

        from src.tools import pasfmt as _pasfmt_mod

        async def mock_fmt_add_line(**kw):
            fp = kw.get("file_path")
            if fp and os.path.isfile(fp):
                with open(fp, 'r', encoding='utf-8') as f:
                    content = f.read()
                content = content.replace(
                    "implementation\n\n",
                    "implementation\n\n\n"
                )
                with open(fp, 'w', encoding='utf-8') as f:
                    f.write(content)
                return {"status": "success", "formatted": True, "message": "ok"}
            return {"formatted": False}

        from unittest.mock import patch
        with patch("src.tools.file_tool.pasfmt.format_file", new=mock_fmt_add_line):
            # Replace [1,3) -> X1,X2 (2 lines for 2 lines, raw offset=0)
            # But mock pasfmt adds 1 line -> actual offset=+1
            r = await handle_write({
                "file_path": file_path,
                "content": "X1\nX2\n",
                "start_line": 1, "end_line": 3,
                "backup": False,
                "auto_format": True,
            })
            _assert_success(r)
            msg = r["message"]
            offset = _extract_offset(msg)

            # Offset should be +1 (pasfmt added 1 line), NOT 0
            assert offset == 1, (
                f"auto_format offset should be +1 (pasfmt added 1 line), "
                f"got: {offset}. msg: {msg}"
            )

    @pytest.mark.asyncio
    async def test_format_action_returns_offset(self, tmp_dir):
        """
        Format action should return offset info when file lines change.
        """
        file_path = os.path.join(tmp_dir, "fmt_offset_return.pas")
        _make_file(file_path, "unit  Test;\ninterface\n\nimplementation\n\nend.\n")

        from src.tools import pasfmt as _pasfmt_mod

        async def mock_fmt_add_lines(**kw):
            fp = kw.get("file_path")
            if fp and os.path.isfile(fp):
                with open(fp, 'r', encoding='utf-8') as f:
                    content = f.read()
                content = content.replace(
                    "implementation", "\n\nimplementation"
                )
                with open(fp, 'w', encoding='utf-8') as f:
                    f.write(content)
                return {"status": "success", "formatted": True, "message": "ok"}
            return {"formatted": False}

        from unittest.mock import patch
        with patch("src.tools.file_tool.pasfmt.format_file", new=mock_fmt_add_lines):
            r = await handle_format({
                "file_path": file_path,
                "mode": "file",
                "backup": False,
            })
            _assert_success(r)
            msg = r["message"]
            assert "\u504f\u79fb\u91cf" in msg or "offset" in msg.lower(), \
                f"format should return offset info: {msg}"
