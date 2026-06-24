"""Schema/doc consistency regression tests.

Verifies that tool descriptions, CODING_RULES, and server schema
agree on command semantics (async/sync, rget vs rinspect, etc.).
"""
import sys, os, re, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ── Helper: find CODING_RULES.mdc ──
RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "CODING_RULES.mdc")


def _read_rules() -> str:
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return f.read()


class TestDocConsistency:
    """Ensure tool docs / CODING_RULES / server schema agree."""

    def test_rinspect_not_for_value_reading_in_tool_docs(self):
        """tool_docs.py: rinspect should NOT be described as 'read property value'."""
        from tool_docs import TOOL_HELP_DOCS
        auto = TOOL_HELP_DOCS.get("automate_delphi", {})
        modes = auto.get("modes", {})
        gui = modes.get("gui", {})
        cmds = gui.get("commands_by_phase", {})
        for phase in ("perception", "verification"):
            desc = cmds.get(phase, {}).get("cmds", {}).get("rinspect", "")
            assert "成员发现" in desc, f"rinspect in {phase} should mention member discovery: {desc}"
            assert "非属性值" in desc or "非值" in desc, f"rinspect in {phase} should clarify not for values: {desc}"

    def test_rget_is_sync_in_all_docs(self):
        """rget should be sync across all doc sources."""
        from tool_docs import TOOL_HELP_DOCS
        auto = TOOL_HELP_DOCS.get("automate_delphi", {})
        modes = auto.get("modes", {})
        gui = modes.get("gui", {})
        proto = gui.get("protocol", {})
        async_cmds = proto.get("async_cmds", "")
        assert "rget" not in async_cmds, f"rget should NOT be in async_cmds: {async_cmds}"
        sync_cmds = proto.get("sync_cmds", "")
        assert "rget" in sync_cmds, f"rget should be in sync_cmds: {sync_cmds}"

    def test_coding_rules_no_rinspect_for_values(self):
        """CODING_RULES should NOT use rinspect for value verification anywhere."""
        rules = _read_rules()
        for bad in ['rinspect(Text)', 'rinspect(Enabled)', 'rinspect(Caption)']:
            assert bad not in rules, f"A0 matrix uses {bad}"
        assert 'rinspect 检查 ' not in rules, "H4: rinspect for value check"
        assert 'rinspect 验证 ' not in rules, "H4: rinspect for value verify"
        assert 'rinspect 确认 ' not in rules, "A0/HDPI: rinspect for value confirm"
        assert 'rinspect 读' not in rules, "rinspect for value reading"
        # Full scan
        lines = rules.split("\n")
        for i, line in enumerate(lines):
            s = line.strip()
            if any(kw in s for kw in ["成员发现", "RTTI 结构", 'cmd="rinspect"']):
                continue
            # Skip table-format lines (| ... |) that describe rinspect, not suggest usage
            if s.startswith("|") and s.endswith("|"):
                continue
            if "rinspect" in s and any(kw in s for kw in ["检查", "验证", "读", "确认"]):
                # "读" in "读取" is not "读" as a command for value reading
                if "读" in kw and "读取" in s:
                    continue
                assert False, f"L{i+1}: rinspect used for value checking: {s}"

    def test_coding_rules_async_list_updated(self):
        """CODING_RULES async command list should match runtime."""
        rules = _read_rules()
        # The _async_{reqId}.json pattern should NOT appear
        assert "_async_" not in rules, "CODING_RULES should not reference _async_*.json"
        # Should mention peekresult
        assert "peekresult" in rules, "CODING_RULES should mention peekresult"

    def test_server_schema_async_list_complete(self):
        """server.py script description should list all async cmds."""
        from pathlib import Path
        server_py = Path(__file__).parent.parent / "src" / "server.py"
        content = server_py.read_text("utf-8")
        idx = content.find("click/rclick/dblclick/hover/move/drag/type/key")
        assert idx > 0, "Async command list not found in server.py"
        for cmd in ["rcall", "rset", "type"]:
            assert cmd in content[idx:idx+200], f"Async cmd '{cmd}' missing from server.py schema"

    def test_server_schema_mentions_sync_dialog_commands(self):
        """server.py schema should classify dialog scan/close commands as sync."""
        from pathlib import Path
        server_py = Path(__file__).parent.parent / "src" / "server.py"
        content = server_py.read_text("utf-8")
        assert "sync(goto/capture/waitfor/wait/dumpstate/listwnd/dlgscan/msgscan/msgclose/dlgfile/snapdir/exit/rget/rinspect)" in content

    def test_rinspect_is_sync_in_all_docs(self):
        """rinspect should be sync across all doc sources (matches Pascal IsAsyncCmd)."""
        from tool_docs import TOOL_HELP_DOCS
        auto = TOOL_HELP_DOCS.get("automate_delphi", {})
        modes = auto.get("modes", {})
        gui = modes.get("gui", {})
        proto = gui.get("protocol", {})
        async_cmds = proto.get("async_cmds", "")
        assert "rinspect" not in async_cmds, f"rinspect should NOT be in async_cmds: {async_cmds}"
        sync_cmds = proto.get("sync_cmds", "")
        assert "rinspect" in sync_cmds, f"rinspect should be in sync_cmds: {sync_cmds}"
