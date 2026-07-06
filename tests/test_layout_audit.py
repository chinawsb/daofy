import json
from pathlib import Path

import pytest
from mcp.types import CallToolResult

from src.tools.layout_audit import audit_dfm_layout_text, run_layout_audit


BAD_LAYOUT_DFM = """object Form1: TForm1
  ClientWidth = 320
  ClientHeight = 180
  object LabelName: TLabel
    Left = 10
    Top = 4
    Width = 60
    Height = 17
  end
  object EditName: TEdit
    Left = 92
    Top = 10
    Width = 140
    Height = 21
    TabOrder = 2
  end
  object EditPhone: TEdit
    Left = 98
    Top = 42
    Width = 140
    Height = 21
    TabOrder = 1
  end
  object EditEmail: TEdit
    Left = 92
    Top = 74
    Width = 140
    Height = 21
    TabOrder = 0
  end
  object ButtonA: TButton
    Left = 16
    Top = 120
    Width = 80
    Height = 25
  end
  object ButtonB: TButton
    Left = 60
    Top = 130
    Width = 80
    Height = 25
  end
  object EditOverflow: TEdit
    Left = 280
    Top = 150
    Width = 80
    Height = 21
    TabOrder = 3
  end
end
"""


CLEAN_LAYOUT_DFM = """object Form1: TForm1
  ClientWidth = 320
  ClientHeight = 180
  object LabelName: TLabel
    Left = 24
    Top = 12
    Width = 60
    Height = 21
  end
  object EditName: TEdit
    Left = 92
    Top = 12
    Width = 160
    Height = 21
    TabOrder = 0
  end
  object LabelPhone: TLabel
    Left = 24
    Top = 44
    Width = 60
    Height = 21
  end
  object EditPhone: TEdit
    Left = 92
    Top = 44
    Width = 160
    Height = 21
    TabOrder = 1
  end
  object LabelEmail: TLabel
    Left = 24
    Top = 76
    Width = 60
    Height = 21
  end
  object EditEmail: TEdit
    Left = 92
    Top = 76
    Width = 160
    Height = 21
    TabOrder = 2
  end
end
"""


CUSTOM_CLASS_LAYOUT_DFM = """object Form1: TForm1
  ClientWidth = 360
  ClientHeight = 180
  object CaptionName: TAcmeStaticText
    Left = 10
    Top = 5
    Width = 30
    Height = 20
  end
  object FieldName: TAcmeFancyPicker
    Left = 90
    Top = 12
    Width = 180
    Height = 22
    TabOrder = 2
  end
  object CaptionPhone: TAcmeStaticText
    Left = 10
    Top = 45
    Width = 30
    Height = 20
  end
  object FieldPhone: TAcmeFancyPicker
    Left = 96
    Top = 45
    Width = 180
    Height = 22
    TabOrder = 1
  end
  object CaptionMail: TAcmeStaticText
    Left = 10
    Top = 77
    Width = 30
    Height = 20
  end
  object FieldMail: TAcmeFancyPicker
    Left = 90
    Top = 77
    Width = 180
    Height = 22
    TabOrder = 0
  end
end
"""


def test_audit_dfm_layout_text_reports_core_layout_findings() -> None:
    findings = audit_dfm_layout_text(BAD_LAYOUT_DFM, "BadForm.dfm")
    rule_ids = {finding.rule_id for finding in findings}

    assert "LAYOUT-001" in rule_ids
    assert "LAYOUT-002" in rule_ids
    assert "LAYOUT-003" in rule_ids
    assert "LAYOUT-005" in rule_ids
    assert "LAYOUT-006" in rule_ids
    assert "LAYOUT-007" in rule_ids


def test_audit_dfm_layout_text_accepts_clean_form() -> None:
    findings = audit_dfm_layout_text(CLEAN_LAYOUT_DFM, "CleanForm.dfm")

    assert findings == []


def test_audit_dfm_layout_text_uses_geometry_for_custom_classes() -> None:
    findings = audit_dfm_layout_text(CUSTOM_CLASS_LAYOUT_DFM, "CustomForm.dfm")
    rule_ids = {finding.rule_id for finding in findings}
    messages = "\n".join(finding.message for finding in findings)

    assert "LAYOUT-003" in rule_ids
    assert "LAYOUT-005" in rule_ids
    assert "LAYOUT-006" in rule_ids
    assert "LAYOUT-007" in rule_ids
    assert "TEdit" not in messages
    assert "TLabel" not in messages


@pytest.mark.asyncio
async def test_run_layout_audit_json_output(tmp_path: Path) -> None:
    dfm_path = tmp_path / "BadForm.dfm"
    dfm_path.write_text(BAD_LAYOUT_DFM, encoding="utf-8")

    result = await run_layout_audit({
        "file_path": str(dfm_path),
        "output_format": "json",
    })

    assert isinstance(result, CallToolResult)
    assert not result.isError
    payload = json.loads(result.content[0].text)
    assert payload["summary"]["total"] >= 6
    assert any(item["rule_id"] == "LAYOUT-001" for item in payload["findings"])


@pytest.mark.asyncio
async def test_run_layout_audit_requires_path() -> None:
    result = await run_layout_audit({})

    assert result.isError
    assert "layout" in result.content[0].text


@pytest.mark.asyncio
async def test_run_audit_dispatches_layout_action(tmp_path: Path) -> None:
    from src.tools.audit import run_audit

    dfm_path = tmp_path / "BadForm.dfm"
    dfm_path.write_text(BAD_LAYOUT_DFM, encoding="utf-8")

    result = await run_audit({
        "action": "layout",
        "file_path": str(dfm_path),
    })

    assert isinstance(result, CallToolResult)
    assert not result.isError
    assert "UI 布局审计报告" in result.content[0].text
    assert "LAYOUT-001" in result.content[0].text


@pytest.mark.asyncio
async def test_project_tool_dispatches_layout_action(tmp_path: Path) -> None:
    from src.tools.project import handle_project

    dfm_path = tmp_path / "BadForm.dfm"
    dfm_path.write_text(BAD_LAYOUT_DFM, encoding="utf-8")

    result = await handle_project(action="layout", file_path=str(dfm_path))

    assert isinstance(result, CallToolResult)
    assert not result.isError
    assert "LAYOUT-001" in result.content[0].text
