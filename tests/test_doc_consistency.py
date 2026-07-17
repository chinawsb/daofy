"""Schema/doc consistency regression tests.

Verifies that tool descriptions, CODING_RULES, and server schema
agree on command semantics (async/sync, rget vs rinspect, etc.).
"""
import sys, os, re, json
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ── Helper: find built-in coding rules resource ──
ROOT = Path(__file__).parent.parent


def test_server_log_argument_redaction_redacts_nested_env():
    """Tool-call logging must not expose temporary env values."""
    from server import _redact_sensitive_arguments

    redacted = _redact_sensitive_arguments({
        "env": {"DEEPSEEK_API_KEY": "secret-value"},
        "script": {
            "test_name": "llm",
            "environment": {"OTHER_KEY": "other-secret"},
            "steps": [{"cmd": "listwnd"}],
        },
    })

    assert redacted["env"] == {"count": 1, "names": ["DEEPSEEK_API_KEY"]}
    assert redacted["script"]["environment"] == {"count": 1, "names": ["OTHER_KEY"]}
    assert "secret-value" not in json.dumps(redacted, ensure_ascii=False)
    assert "other-secret" not in json.dumps(redacted, ensure_ascii=False)


def _resource_markdown_files() -> list[Path]:
    roots = [
        ROOT / "src" / "resources" / "coding-rules",
        ROOT / "src" / "resources" / "automation",
    ]
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(sorted(root.rglob("*.md")))
    return files


def _read_rules() -> str:
    return "\n\n".join(path.read_text(encoding="utf-8") for path in _resource_markdown_files())


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
        for i, line in enumerate(rules.split("\n")):
            s = line.strip()
            if any(kw in s for kw in ["成员发现", "RTTI 结构", 'cmd="rinspect"']):
                continue
            if any(kw in s for kw in ["不要用 `rinspect`", "不要用 rinspect", "非属性值"]):
                continue
            # Skip table-format lines (| ... |) that describe rinspect, not suggest usage
            if s.startswith("|") and s.endswith("|"):
                continue
            value_words = ["检查", "验证", "读", "确认", "BoundsRect", "left", "top", "width", "height"]
            if "rinspect" in s and any(kw in s for kw in value_words):
                assert False, f"L{i+1}: rinspect used for value checking: {s}"

    def test_coding_rules_async_list_updated(self):
        """CODING_RULES async command list should match runtime."""
        rules = _read_rules()
        # The _async_{reqId}.json pattern should NOT appear
        assert "_async_" not in rules, "CODING_RULES should not reference _async_*.json"
        # Should mention peekresult
        assert "peekresult" in rules, "CODING_RULES should mention peekresult"

    def test_automation_assert_field_is_not_documented_or_read(self):
        """Automation scripts should expose only assert_expr, not a second assert field."""
        scanned_files = _resource_markdown_files() + [
            ROOT / "src" / "services" / "automation_service.py",
        ]
        forbidden = [
            "legacy `assert`",
            "or `assert`",
            "`assert` 仅作旧脚本兼容",
            "step.get('assert')",
        ]
        for path in scanned_files:
            content = path.read_text(encoding="utf-8")
            for text in forbidden:
                assert text not in content, f"{path} still references {text}"

    def test_automation_script_samples_do_not_use_assert_field(self):
        """Sample scripts and skill resources must not teach the unsupported assert field."""
        root = Path(__file__).parent.parent
        scanned_roots = [
            root / "src" / "resources",
            root / ".opencode" / "skills" / "delphi-automation-workflow",
            root / ".claude" / "skills" / "delphi-automation-workflow",
            root / ".cursor" / "rules",
            root / "tests" / "scripts",
        ]

        for base in scanned_roots:
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.suffix.lower() not in {".md", ".mdc", ".json"}:
                    continue
                content = path.read_text(encoding="utf-8")
                assert '"assert":' not in content, f"{path} still uses unsupported assert field"

    def test_black_box_docs_forbid_direct_rtti_execution(self):
        """Black-box script docs must not recommend rcall/rset execution."""
        ref_dir = ROOT / "src" / "resources" / "coding-rules" / "testing" / "automation" / "reference"
        workflow = (
            ref_dir / "workflow.md"
        ).read_text(encoding="utf-8")
        script_workflow = (
            ref_dir / "script-generation-workflow.md"
        ).read_text(encoding="utf-8")
        script_schema = (
            ref_dir / "script-schema.md"
        ).read_text(encoding="utf-8")
        coding_rules = "\n\n".join(
            f.read_text(encoding="utf-8")
            for f in sorted((ROOT / "src" / "resources" / "coding-rules").rglob("*.md"))
        )

        for content in (workflow, script_workflow, script_schema, coding_rules):
            assert "Black-box" in content or "黑盒" in content
            assert "black-box" in content.lower() or "黑盒" in content
            assert "rcall" in content

        assert (
            "Black-box execution steps must not use `rcall`, `rset`" in workflow
            or "黑盒执行步骤不得使用 `rcall`、`rset`" in workflow
        )
        assert (
            "For black-box tests, do not use `rcall`, `rset`" in script_workflow
            or ("黑盒测试说明" in script_workflow and "不得使用 RTTI 写命令" in script_workflow)
        )
        assert (
            "Black-box `execute` steps must not use `rcall`, `rset`" in script_schema
            or "黑盒 `execute` 步骤不得使用 `rcall`、`rset`" in script_schema
        )
        assert "直接执行业务逻辑（首选）" not in coding_rules
        assert "首选，不依赖 UI" not in coding_rules

    def test_automation_docs_store_cases_under_project_tests_by_type(self):
        """Automation docs should save reusable cases under Tests/<test type>."""
        ref_dir = ROOT / "src" / "resources" / "coding-rules" / "testing" / "automation" / "reference"
        scanned_files = [
            ref_dir / "workflow.md",
            ref_dir / "script-generation-workflow.md",
            ref_dir / "script-schema.md",
            ROOT / ".opencode" / "skills" / "delphi-automation-workflow" / "SKILL.md",
            ROOT / ".claude" / "skills" / "delphi-automation-workflow" / "SKILL.md",
            ROOT / ".cursor" / "rules" / "delphi-automation-workflow.mdc",
        ]

        for path in scanned_files:
            content = path.read_text(encoding="utf-8")
            assert "Tests\\<测试类型>" in content or "Tests/<测试类型>" in content
            assert "tests/scripts/" not in content

    def test_server_schema_async_list_complete(self):
        """tool_docs.py protocol should list all async cmds (migrated from server.py schema in Phase 3)."""
        from tool_docs import TOOL_HELP_DOCS
        auto = TOOL_HELP_DOCS.get("automate_delphi", {})
        proto = auto.get("modes", {}).get("gui", {}).get("protocol", {})
        async_cmds = proto.get("async_cmds", "")
        assert async_cmds, "async_cmds not found in tool_docs.py protocol"
        for cmd in ["rcall", "rset", "type"]:
            assert cmd in async_cmds, f"Async cmd '{cmd}' missing from async_cmds: {async_cmds}"

    def test_server_schema_mentions_sync_dialog_commands(self):
        """tool_docs.py protocol should classify dialog scan/close commands as sync (migrated from server.py schema in Phase 3)."""
        from tool_docs import TOOL_HELP_DOCS
        auto = TOOL_HELP_DOCS.get("automate_delphi", {})
        proto = auto.get("modes", {}).get("gui", {}).get("protocol", {})
        sync_cmds = proto.get("sync_cmds", "")
        assert sync_cmds, "sync_cmds not found in tool_docs.py protocol"
        for cmd in ["goto", "capture", "waitfor", "dlgscan", "msgscan", "msgclose", "rget", "rinspect"]:
            assert cmd in sync_cmds, f"Sync cmd '{cmd}' missing from sync_cmds: {sync_cmds}"
        # Verify callgraph commands are also classified as sync
        assert "callgraph" in sync_cmds

    def test_automation_script_shape_is_documented_across_runtime_docs(self):
        """The documented full script object must match execute_script support (migrated from server.py schema in Phase 3)."""
        from tool_docs import TOOL_HELP_DOCS

        auto_docs = TOOL_HELP_DOCS.get("automate_delphi", {})
        gui_docs = auto_docs.get("modes", {}).get("gui", {})

        script_shape = gui_docs.get("script_shape", "")
        assert "完整脚本对象" in script_shape, f"script_shape missing '完整脚本对象': {script_shape}"
        assert "script_metadata" in script_shape, f"script_shape missing 'script_metadata': {script_shape}"

        # Verify automation_service.py documents the script shape parsing
        from pathlib import Path
        auto_svc = (Path(__file__).parent.parent / "src" / "services" / "automation_service.py").read_text(encoding="utf-8")
        assert "步骤列表或包含 steps 的对象" in auto_svc, "automation_service.py missing script shape documentation"

    def test_delphi_file_docs_forbid_default_editors(self):
        """Delphi edit docs must explicitly block direct agent write tools."""
        from tool_docs import TOOL_HELP_DOCS, TOOL_SHORT_DESC

        scanned_files = [
            ROOT / "AGENTS.md",
            ROOT / "src" / "resources" / "coding-rules" / "delphi" / "delphi-file-rules.md",
        ]
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in scanned_files
        )
        delphi_docs = TOOL_HELP_DOCS.get("delphi_file", {})
        combined += "\n" + json.dumps(delphi_docs, ensure_ascii=False)
        combined += "\n" + TOOL_SHORT_DESC["delphi_file"]

        required_terms = [
            "delphi_file",
            "apply_patch",
            "PowerShell",
            "Python",
            ".pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx",
            "edit guard",
        ]
        for term in required_terms:
            assert term in combined, f"Delphi edit docs missing {term!r}"

    def test_delphi_file_docs_explain_trae_run_mcp_wrapper(self):
        """delphi_file help must separate Trae wrapper params from tool params."""
        from tool_docs import TOOL_HELP_DOCS

        delphi_docs = TOOL_HELP_DOCS.get("delphi_file", {})
        combined = json.dumps(delphi_docs, ensure_ascii=False)

        required_terms = [
            "run_mcp",
            "server_name",
            "tool_name",
            "args",
            "服务别名",
            "不是 Daofy 固定值",
            "不要把 server_name/tool_name 混进",
        ]
        for term in required_terms:
            assert term in combined, f"delphi_file docs missing Trae wrapper term {term!r}"

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

    def test_coding_rule_section_references_are_valid(self):
        """All documented get_coding_rules(section=...) examples must resolve to known keys or aliases."""
        from src.tools.coding_rules import SECTION_ALIASES, SECTION_KEYS, META_SECTIONS

        known = set(SECTION_KEYS) | set(META_SECTIONS) | set(SECTION_ALIASES) | {"list"}
        for path in _resource_markdown_files():
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r'get_coding_rules\(section="([^"]+)"', text):
                section = match.group(1)
                assert section in known, f"{path}:{text[:match.start()].count(chr(10)) + 1}: unknown section {section}"

    def test_resource_markdown_path_references_exist(self):
        """Plain .md paths in resource docs should not point to old split-file names."""
        patterns = [
            re.compile(r'\[[^\]]+\]\(([^)]+\.md)(?:#[^)]+)?\)'),
            re.compile(r'(?<![\w/.-])((?:\.\./|\./|coding-rules/|automation/|debugging/|src/resources/)[\w./-]+\.md)'),
        ]
        for path in _resource_markdown_files():
            text = path.read_text(encoding="utf-8")
            for pattern in patterns:
                for match in pattern.finditer(text):
                    href = match.group(1).strip("`").split("#", 1)[0]
                    if href.startswith("src/resources/"):
                        candidates = [ROOT / href]
                    elif href.startswith("coding-rules/"):
                        candidates = [ROOT / "src" / "resources" / href]
                    elif href.startswith(("automation/", "debugging/")):
                        resources = ROOT / "src" / "resources"
                        candidates = [
                            path.parent / href,
                            resources / "coding-rules" / href,
                            resources / "coding-rules" / "shared" / href,
                            resources / href,
                        ]
                    else:
                        candidates = [path.parent / href]
                    line = text[:match.start()].count("\n") + 1
                    assert any(candidate.exists() for candidate in candidates), f"{path}:{line}: missing {href}"
