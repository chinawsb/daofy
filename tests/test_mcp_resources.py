import hashlib
import json
from pathlib import Path

import pytest
from mcp import types
from mcp.server.lowlevel.server import Server
from pydantic import AnyUrl

from src.mcp_resources import (
    PublicResourceSpec,
    available_public_resources,
    build_public_resource_index,
    get_public_resource_metadata,
    get_public_resource_text,
    resolve_resource_path,
)

PROJECT_ROOT = Path(__file__).parent.parent


def test_public_resource_index_lists_stable_automation_uris() -> None:
    index = build_public_resource_index()

    assert "delphi://resources" not in index
    assert "delphi://coding-rules" in index
    assert "delphi://automation/workflow" in index
    assert "delphi://automation/script-generation-workflow" in index
    assert "`src/resources/coding-rules/index.md`" in index
    assert "`src/resources/coding-rules/testing/automation/reference/script-generation-workflow.md`" in index
    assert "SHA-256" in index
    assert "Version" in index
    assert "Updated" in index
    assert "1.14.0" in index
    assert "2026-07-17" in index
    assert "client-specific hidden directories" in index


def test_reads_packaged_automation_resource() -> None:
    mime_type, text = get_public_resource_text("delphi://automation/script-generation-workflow")

    assert mime_type == "text/markdown"
    assert "# 脚本生成工作流" in text
    assert "MCP resource URI: `delphi://automation/script-generation-workflow`" in text
    assert "automate_delphi" in text


def test_server_resource_list_exposes_registry_resources() -> None:
    from src.server import _build_mcp_resource_list

    resources = _build_mcp_resource_list(PROJECT_ROOT)
    uris = {str(resource.uri) for resource in resources}

    assert "delphi://resources" in uris
    assert "delphi://coding-rules" in uris
    assert "delphi://automation/workflow" in uris
    assert "delphi://automation/script-generation-workflow" in uris
    assert "delphi://health" in uris


def test_server_reads_resource_index() -> None:
    from src.server import _read_mcp_resource

    result = _read_mcp_resource("delphi://resources", PROJECT_ROOT)
    content = result.contents[0]

    assert str(content.uri) == "delphi://resources"
    assert content.mimeType == "text/markdown"
    assert "delphi://coding-rules" in content.text
    assert "SHA-256" in content.text


def test_server_reads_coding_rules_resource() -> None:
    from src.server import _read_mcp_resource

    result = _read_mcp_resource("delphi://coding-rules", PROJECT_ROOT)
    content = result.contents[0]

    assert str(content.uri) == "delphi://coding-rules"
    assert content.mimeType == "text/markdown"
    assert "# 编码规则导航" in content.text


def test_server_reads_anyurl_resource_uri() -> None:
    from src.server import _read_mcp_resource

    result = _read_mcp_resource(AnyUrl("delphi://automation/workflow"), PROJECT_ROOT)
    content = result.contents[0]

    assert str(content.uri) == "delphi://automation/workflow"
    assert content.mimeType == "text/markdown"
    assert "# Delphi 自动化测试工作流" in content.text


def test_server_read_resource_contents_matches_mcp_lowlevel_shape() -> None:
    from src.server import _read_mcp_resource_contents

    contents = _read_mcp_resource_contents(
        AnyUrl("delphi://automation/script-schema"),
        PROJECT_ROOT,
    )

    assert len(contents) == 1
    assert contents[0].mime_type == "text/markdown"
    assert "# 自动化脚本格式规范" in contents[0].content


async def test_server_read_resource_handler_accepts_lowlevel_contents() -> None:
    from src.server import _read_mcp_resource_contents

    server = Server("resource-shape-test")

    @server.read_resource()
    async def read_resource(uri: AnyUrl):
        return _read_mcp_resource_contents(uri, PROJECT_ROOT)

    handler = server.request_handlers[types.ReadResourceRequest]
    request = types.ReadResourceRequest(
        params=types.ReadResourceRequestParams(
            uri=AnyUrl("delphi://automation/script-schema"),
        )
    )

    response = await handler(request)
    result = response.root
    content = result.contents[0]

    assert str(content.uri) == "delphi://automation/script-schema"
    assert content.mimeType == "text/markdown"
    assert "# 自动化脚本格式规范" in content.text


def test_server_reads_health_resource_with_non_negative_uptime() -> None:
    import src.server as server_module

    server_module._server_start_time = server_module.time.monotonic()

    result = server_module._read_mcp_resource("delphi://health", PROJECT_ROOT)
    content = result.contents[0]
    health = json.loads(content.text)

    assert str(content.uri) == "delphi://health"
    assert content.mimeType == "application/json"
    assert health["uptime_seconds"] >= 0
    assert health["edit_guard"]["enabled"] is True
    assert "recent_unauthorized_count" in health["edit_guard"]


def test_server_health_accepts_legacy_epoch_start_time() -> None:
    import src.server as server_module

    server_module._server_start_time = server_module.time.time()

    result = server_module._read_mcp_resource("delphi://health", PROJECT_ROOT)
    content = result.contents[0]
    health = json.loads(content.text)

    assert health["uptime_seconds"] >= 0


def test_experimental_task_support_is_feature_detected() -> None:
    import src.server as server_module

    class LegacyServer:
        pass

    class DisabledServer:
        _experimental_handlers = None

    class ExperimentalHandlers:
        task_support = object()

    class CurrentServer:
        _experimental_handlers = ExperimentalHandlers()

    assert server_module._get_experimental_task_support(LegacyServer()) is None
    assert server_module._get_experimental_task_support(DisabledServer()) is None
    assert (
        server_module._get_experimental_task_support(CurrentServer())
        is CurrentServer._experimental_handlers.task_support
    )


def test_server_unknown_resource_raises_value_error() -> None:
    from src.server import _read_mcp_resource

    with pytest.raises(ValueError):
        _read_mcp_resource("delphi://automation/missing", PROJECT_ROOT)


def test_public_resource_metadata_matches_file_content() -> None:
    metadata = get_public_resource_metadata("delphi://coding-rules")
    data = metadata.path.read_bytes()

    assert metadata.source == "src/resources/coding-rules/index.md"
    assert metadata.byte_size == len(data)
    assert metadata.sha256 == hashlib.sha256(data).hexdigest()
    assert metadata.version == "1.14.0"
    assert metadata.updated == "2026-07-17"


def test_skill_front_matter_name_is_not_resource_version() -> None:
    metadata = get_public_resource_metadata("delphi://automation/workflow")

    assert metadata.version == ""
    assert metadata.updated == ""


def test_known_resource_without_backing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        get_public_resource_text("delphi://automation/workflow", root=tmp_path)


def test_unknown_resource_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_public_resource_text("delphi://automation/missing")


def test_resolve_resource_path_uses_first_existing_fallback(tmp_path: Path) -> None:
    second = tmp_path / "second.md"
    second.write_text("second", encoding="utf-8")
    spec = PublicResourceSpec(
        uri="delphi://test",
        name="test",
        title="Test",
        description="Test resource",
        mime_type="text/markdown",
        relative_paths=("first.md", "second.md"),
    )

    assert resolve_resource_path(spec, root=tmp_path) == second


def test_available_resources_are_file_backed() -> None:
    resources = available_public_resources()
    uris = {resource.uri for resource in resources}

    assert "delphi://automation/script-schema" in uris
    assert all(resolve_resource_path(resource) is not None for resource in resources)


def test_public_resources_use_server_resource_directory_only() -> None:
    for resource in available_public_resources():
        for relative_path in resource.relative_paths:
            normalized = relative_path.replace("\\", "/")
            assert normalized.startswith("src/resources/")
            assert not normalized.startswith((".opencode/", ".claude/", ".cursor/", "docs/"))


def test_server_read_resource_does_not_mask_unknown_automation_uri() -> None:
    server_source = (PROJECT_ROOT / "src" / "server.py").read_text(encoding="utf-8")

    assert 'text=f"未知资源: {uri}"' not in server_source
    assert 'raise ValueError(f"未知资源: {uri}")' in server_source


def test_coding_rules_resource_is_preferred() -> None:
    coding_rules = next(
        resource for resource in available_public_resources()
        if resource.uri == "delphi://coding-rules"
    )

    assert resolve_resource_path(coding_rules) == PROJECT_ROOT / "src" / "resources" / "coding-rules" / "index.md"


def test_automation_skill_mirrors_match_resource_sources() -> None:
    mirrors = [
        (
            "src/resources/coding-rules/testing/automation/reference/workflow.md",
            ".opencode/skills/delphi-automation-workflow/SKILL.md",
            ".claude/skills/delphi-automation-workflow/SKILL.md",
            ".cursor/rules/delphi-automation-workflow.mdc",
            ".windsurfrules",
        ),
        (
            "src/resources/coding-rules/testing/automation/reference/script-generation-workflow.md",
            ".opencode/skills/delphi-automation-workflow/references/script-generation-workflow.md",
            ".claude/skills/delphi-automation-workflow/references/script-generation-workflow.md",
        ),
        (
            "src/resources/coding-rules/testing/automation/reference/script-schema.md",
            ".opencode/skills/delphi-automation-workflow/references/script-schema.md",
            ".claude/skills/delphi-automation-workflow/references/script-schema.md",
        ),
        (
            "src/resources/coding-rules/testing/automation/reference/report-schema.md",
            ".opencode/skills/delphi-automation-workflow/references/report-schema.md",
            ".claude/skills/delphi-automation-workflow/references/report-schema.md",
        ),
        (
            "src/resources/coding-rules/testing/automation/reference/repair-loop.md",
            ".opencode/skills/delphi-automation-workflow/references/repair-loop.md",
            ".claude/skills/delphi-automation-workflow/references/repair-loop.md",
        ),
        (
            "src/resources/coding-rules/testing/automation/reference/inline-unit.md",
            ".opencode/skills/delphi-automation-workflow/references/inline-unit.md",
            ".claude/skills/delphi-automation-workflow/references/inline-unit.md",
        ),
    ]

    for group in mirrors:
        source = (PROJECT_ROOT / group[0]).read_text(encoding="utf-8")
        for mirror in group[1:]:
            assert (PROJECT_ROOT / mirror).read_text(encoding="utf-8") == source


def test_inline_automation_units_expose_deterministic_failure_codes() -> None:
    vcl_source = (
        PROJECT_ROOT / "tools" / "auto" / "Vcl.DaofyAutomation.pas"
    ).read_text(encoding="utf-8")
    fmx_source = (
        PROJECT_ROOT / "tools" / "auto" / "Fmx.DaofyAutomation.pas"
    ).read_text(encoding="utf-8-sig")
    base_source = (
        PROJECT_ROOT / "tools" / "auto" / "DaofyAutomation.Base.pas"
    ).read_text(encoding="utf-8")

    assert "Found: Boolean;" in vcl_source
    assert "WriteResp(ReqId, 'err', 'NF:' + Target)" in vcl_source
    click_source = vcl_source.split(
        "function TAutomationProcessor.HandleCmdClick", maxsplit=1
    )[1].split("{ ── key ── }", maxsplit=1)[0]
    assert "Ctrl := TControl(Obj);" in vcl_source
    assert "Ctrl.ClientToScreen(Point(Ctrl.Width div 2, Ctrl.Height div 2))" in vcl_source
    assert "WC := TWinControl(FindNamedControl(CtrlName));" not in click_source
    assert "Found: Boolean;" in fmx_source
    assert "WriteResp(ReqId, 'err', 'NF:' + Target)" in fmx_source
    assert "WriteResp(ReqId, 'ok', DoMsgScan)" in base_source
    assert "WriteResp(ReqId, 'ok', 'scanned')" not in base_source
    assert "class function FindProcessDialog" in base_source
    assert "GetWindowThreadProcessId(Result, @WindowPID)" in base_source
    assert "WindowPID = GetCurrentProcessId" in base_source
    assert "FindWindowW('#32770', nil)" not in base_source
    assert "FindWindowW('#32770', nil)" not in vcl_source
    assert "FindWindowW('#32770', nil)" not in fmx_source
