import xml.etree.ElementTree as ET

import pytest

from src.tools.dproj_tool import dproj_tool
from src.tools.project import handle_project


MSBUILD_NS = "http://schemas.microsoft.com/developer/msbuild/2003"


def _tag(name: str) -> str:
    return f"{{{MSBUILD_NS}}}{name}"


def _property_group_conditions(project_path) -> set[str]:
    root = ET.parse(project_path).getroot()
    return {pg.get("Condition", "") for pg in root.findall(_tag("PropertyGroup"))}


def _header_text(project_path, name: str) -> str:
    root = ET.parse(project_path).getroot()
    header = root.find(_tag("PropertyGroup"))
    assert header is not None
    elem = header.find(_tag(name))
    assert elem is not None
    return elem.text or ""


@pytest.mark.asyncio
async def test_project_create_target_platform_win64_reaches_dproj_tool(tmp_path):
    project_path = tmp_path / "App64.dproj"

    result = await handle_project(
        action="create",
        project_path=str(project_path),
        main_source="App64.dpr",
        project_version="22.0",
        target_platform="win64",
    )

    assert result.isError is False
    assert _header_text(project_path, "Platform") == "Win64"
    assert _header_text(project_path, "TargetedPlatforms") == "2"
    assert "'$(Base_Win64)'!=''" in _property_group_conditions(project_path)


@pytest.mark.asyncio
async def test_dproj_tool_create_platform_alias_is_normalized(tmp_path):
    project_path = tmp_path / "Direct64.dproj"

    result = await dproj_tool(
        action="create",
        project_path=str(project_path),
        main_source="Direct64.dpr",
        project_version="22.0",
        platform="win64",
    )

    assert result.isError is False
    assert _header_text(project_path, "Platform") == "Win64"
    assert _header_text(project_path, "TargetedPlatforms") == "2"
