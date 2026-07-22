"""
Tests for .groupproj parsing in both compile_project and install_package.

Covers two XML formats:
  - <ProjectReference Include="..."> (newer format, used by tutorial)
  - <Projects Include="...">           (XE/XE2 era, used by real-world samples)

Also covers:
  - <BuildOrder> sorting
  - <Dependencies> parsing
  - Deduplication
  - <Platforms> and <Config> extraction
  - Topological sort
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

MSBUILD_NS = "http://schemas.microsoft.com/developer/msbuild/2003"

# ── Fixture XML builders ──────────────────────────────────────────────


def _make_project_reference_groupproj(
    sub_projects: list[str],
    build_order: list[str] | None = None,
    dependencies: dict[str, list[str]] | None = None,
) -> str:
    """Build a .groupproj XML string using <ProjectReference Include="..."> tags."""
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<ProjectGroup xmlns="{MSBUILD_NS}">',
    ]
    for sp in sub_projects:
        lines.extend([
            f'  <ProjectReference Include="{sp}">',
            "    <Project>{00000000-0000-0000-0000-000000000000}</Project>",
            f"    <Name>{Path(sp).stem}</Name>",
            "  </ProjectReference>",
        ])
    # <BuildOrder> has <ProjectReference> WITHOUT Include — for ordering
    if build_order is not None:
        lines.append("  <BuildOrder>")
        for sp in build_order:
            lines.append(f"    <ProjectReference>{sp}</ProjectReference>")
        lines.append("  </BuildOrder>")
    else:
        # Default: include BuildOrder with same order as sub_projects
        lines.append("  <BuildOrder>")
        for sp in sub_projects:
            lines.append(f"    <ProjectReference>{sp}</ProjectReference>")
        lines.append("  </BuildOrder>")
    lines.append("</ProjectGroup>")
    return "\n".join(lines)


def _make_projects_groupproj(
    sub_projects: list[str],
    dependencies: dict[str, list[str]] | None = None,
) -> str:
    """Build a .groupproj XML string using <Projects Include="..."> tags inside <ItemGroup>."""
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<ProjectGroup xmlns="{MSBUILD_NS}">',
        "  <ItemGroup>",
    ]
    for sp in sub_projects:
        deps = dependencies.get(sp, []) if dependencies else []
        if deps:
            lines.append(f'    <Projects Include="{sp}">')
            lines.append(f"      <Dependencies>{';'.join(deps)}</Dependencies>")
            lines.append("    </Projects>")
        else:
            lines.append(f'    <Projects Include="{sp}" />')
    lines.extend([
        "  </ItemGroup>",
        "</ProjectGroup>",
    ])
    return "\n".join(lines)


def _make_groupproj_no_namespace(sub_projects: list[str]) -> str:
    """Build a .groupproj WITHOUT MSBuild namespace (fallback path)."""
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        "<ProjectGroup>",
    ]
    for sp in sub_projects:
        lines.append(f'  <Projects Include="{sp}" />')
    lines.append("</ProjectGroup>")
    return "\n".join(lines)


def _make_groupproj_with_platforms(
    platforms: list[str],
    config: str = "Debug",
    platform_default: str = "Win32",
) -> str:
    """Build a .groupproj with <Platforms> and <Config>/<Platform> nodes."""
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<ProjectGroup xmlns="{MSBUILD_NS}">',
        "  <PropertyGroup>",
        f"    <Config Condition=\"'$(Config)'==''\">{config}</Config>",
        f"    <Platform Condition=\"'$(Platform)'==''\">{platform_default}</Platform>",
        "  </PropertyGroup>",
        "  <ProjectExtensions>",
        "    <Borland.Personality>Delphi.Personality.12</Borland.Personality>",
        "    <Borland.ProjectType>Application</Borland.ProjectType>",
        "    <BorlandProject>",
        "      <Platforms>",
    ]
    for p in platforms:
        lines.append(f'        <Platform value="{p}">True</Platform>')
    lines.extend([
        "      </Platforms>",
        "    </BorlandProject>",
        "  </ProjectExtensions>",
        "</ProjectGroup>",
    ])
    return "\n".join(lines)


def _parse_and_extract(xml_content: str, base_dir: str) -> list[str]:
    """Simulate the groupproj child extraction logic used in both handlers."""
    root = ET.fromstring(xml_content)
    ns = MSBUILD_NS
    children: list[str] = []
    for tag in ("Projects", "ProjectReference"):
        for xpath in (f".//{{{ns}}}{tag}", f".//{tag}"):
            for elem in root.findall(xpath):
                include = elem.get("Include", "")
                if include:
                    resolved = str((Path(base_dir) / include).resolve())
                    if Path(resolved).exists():
                        children.append(resolved)
    return children


# ── Tests ─────────────────────────────────────────────────────────────


class TestExtractChildProjects:
    """Pure XML parsing tests — no async, no compiler needed."""

    def test_project_reference_format(self, tmp_path: Path) -> None:
        """<ProjectReference Include="..."> is parsed correctly."""
        dproj_a = tmp_path / "ChildA.dproj"
        dproj_b = tmp_path / "ChildB.dproj"
        dproj_a.write_text("", encoding="utf-8")
        dproj_b.write_text("", encoding="utf-8")

        xml = _make_project_reference_groupproj(["ChildA.dproj", "ChildB.dproj"])
        result = _parse_and_extract(xml, str(tmp_path))

        assert len(result) == 2
        assert str(dproj_a.resolve()) in result
        assert str(dproj_b.resolve()) in result

    def test_projects_format(self, tmp_path: Path) -> None:
        """<Projects Include="..."> is parsed correctly."""
        dproj_a = tmp_path / "Lib.dproj"
        dproj_a.write_text("", encoding="utf-8")

        xml = _make_projects_groupproj(["Lib.dproj"])
        result = _parse_and_extract(xml, str(tmp_path))

        assert len(result) == 1
        assert str(dproj_a.resolve()) == result[0]

    def test_no_namespace_format(self, tmp_path: Path) -> None:
        """XML without MSBuild namespace still works (fallback path)."""
        dproj = tmp_path / "Legacy.dproj"
        dproj.write_text("", encoding="utf-8")

        xml = _make_groupproj_no_namespace(["Legacy.dproj"])
        result = _parse_and_extract(xml, str(tmp_path))

        assert len(result) == 1
        assert str(dproj.resolve()) == result[0]

    def test_missing_child_project_skipped(self, tmp_path: Path) -> None:
        """Referenced file that doesn't exist is silently skipped."""
        xml = _make_project_reference_groupproj(["Missing.dproj"])
        result = _parse_and_extract(xml, str(tmp_path))
        assert len(result) == 0

    def test_mixed_empty_group_returns_empty(self, tmp_path: Path) -> None:
        """No projects at all → empty result."""
        xml = _make_project_reference_groupproj([])
        result = _parse_and_extract(xml, str(tmp_path))
        assert len(result) == 0

    def test_build_order_projectreference_ignored(self, tmp_path: Path) -> None:
        """<BuildOrder> contains <ProjectReference> without Include → ignored."""
        dproj = tmp_path / "Real.dproj"
        dproj.write_text("", encoding="utf-8")

        xml = _make_project_reference_groupproj(["Real.dproj"])
        result = _parse_and_extract(xml, str(tmp_path))

        # Only 1 child, not 3 (BuildOrder has 2 <ProjectReference> without Include)
        assert len(result) == 1

    def test_mixed_formats_dedup_not_needed(self, tmp_path: Path) -> None:
        """If a project appears in both formats, it's included twice (caller handles)."""
        dproj = tmp_path / "Shared.dproj"
        dproj.write_text("", encoding="utf-8")

        # Manually craft XML that has both formats referencing the same file
        xml = f'''<?xml version="1.0" encoding="utf-8"?>
<ProjectGroup xmlns="{MSBUILD_NS}">
  <ProjectReference Include="Shared.dproj" />
  <ItemGroup>
    <Projects Include="Shared.dproj" />
  </ItemGroup>
</ProjectGroup>'''
        result = _parse_and_extract(xml, str(tmp_path))

        # Both tags match → 2 entries (no dedup at parse level)
        assert len(result) == 2


# ── New parser tests ──────────────────────────────────────────────────


class TestGroupprojParser:
    """Tests for the new parse_groupproj() function."""

    def test_build_order_sorting(self, tmp_path: Path) -> None:
        """
        <BuildOrder> defines compilation order.
        Projects should be sorted according to BuildOrder.
        """
        # Create projects in REVERSE order (App before Lib)
        app = tmp_path / "App.dproj"
        lib = tmp_path / "Lib.dproj"
        app.write_text("", encoding="utf-8")
        lib.write_text("", encoding="utf-8")

        # BuildOrder says: Lib first, then App
        xml = _make_project_reference_groupproj(
            ["App.dproj", "Lib.dproj"],  # XML order: App first
            build_order=["Lib.dproj", "App.dproj"],  # BuildOrder: Lib first
        )
        groupproj = tmp_path / "ProjectGroup.groupproj"
        groupproj.write_text(xml, encoding="utf-8")

        from src.utils.groupproj_parser import parse_groupproj
        info = parse_groupproj(groupproj)

        # Should be sorted: Lib first, then App
        assert len(info.child_projects) == 2
        assert info.child_projects[0].name == "Lib.dproj"
        assert info.child_projects[1].name == "App.dproj"
        assert info.build_order == ["Lib.dproj", "App.dproj"]

    def test_deduplication(self, tmp_path: Path) -> None:
        """
        Same project in both <Projects> and <ProjectReference> should be deduplicated.
        """
        dproj = tmp_path / "Shared.dproj"
        dproj.write_text("", encoding="utf-8")

        # Craft XML with both formats
        xml = f'''<?xml version="1.0" encoding="utf-8"?>
<ProjectGroup xmlns="{MSBUILD_NS}">
  <ProjectReference Include="Shared.dproj" />
  <ItemGroup>
    <Projects Include="Shared.dproj" />
  </ItemGroup>
  <BuildOrder>
    <ProjectReference>Shared.dproj</ProjectReference>
  </BuildOrder>
</ProjectGroup>'''
        groupproj = tmp_path / "ProjectGroup.groupproj"
        groupproj.write_text(xml, encoding="utf-8")

        from src.utils.groupproj_parser import parse_groupproj
        info = parse_groupproj(groupproj)

        # Should be deduplicated to 1
        assert len(info.child_projects) == 1
        assert info.child_projects[0].name == "Shared.dproj"

    def test_dependencies_parsing(self, tmp_path: Path) -> None:
        """
        <Dependencies> in <Projects> should be parsed.
        """
        lib = tmp_path / "Lib.dproj"
        app = tmp_path / "App.dproj"
        lib.write_text("", encoding="utf-8")
        app.write_text("", encoding="utf-8")

        xml = _make_projects_groupproj(
            ["Lib.dproj", "App.dproj"],
            dependencies={"App.dproj": ["Lib.dproj"]},
        )
        groupproj = tmp_path / "ProjectGroup.groupproj"
        groupproj.write_text(xml, encoding="utf-8")

        from src.utils.groupproj_parser import parse_groupproj
        info = parse_groupproj(groupproj)

        assert "App.dproj" in info.dependencies
        assert info.dependencies["App.dproj"] == ["Lib.dproj"]

    def test_platforms_extraction(self, tmp_path: Path) -> None:
        """
        <Platforms> in <ProjectExtensions> should be extracted.
        """
        xml = _make_groupproj_with_platforms(
            ["Win32", "Win64"],
            config="Release",
            platform_default="Win64",
        )
        groupproj = tmp_path / "ProjectGroup.groupproj"
        groupproj.write_text(xml, encoding="utf-8")

        from src.utils.groupproj_parser import (
            parse_groupproj,
            get_platform_for_project,
            get_config_for_project,
        )
        info = parse_groupproj(groupproj)

        assert info.supported_platforms == ["Win32", "Win64"]
        assert info.default_config == "Release"
        assert info.default_platform == "Win64"
        assert get_platform_for_project(info) == "win64"
        assert get_config_for_project(info) == "Release"

    def test_project_guid_extraction(self, tmp_path: Path) -> None:
        """
        <ProjectGuid> in <PropertyGroup> should be extracted.
        """
        xml = f'''<?xml version="1.0" encoding="utf-8"?>
<ProjectGroup xmlns="{MSBUILD_NS}">
  <PropertyGroup>
    <ProjectGuid>{{12345678-ABCD-EF01-2345-6789ABCDEF01}}</ProjectGuid>
  </PropertyGroup>
</ProjectGroup>'''
        groupproj = tmp_path / "ProjectGroup.groupproj"
        groupproj.write_text(xml, encoding="utf-8")

        from src.utils.groupproj_parser import parse_groupproj
        info = parse_groupproj(groupproj)

        assert info.project_guid == "{12345678-ABCD-EF01-2345-6789ABCDEF01}"

    def test_build_order_with_missing_project(self, tmp_path: Path) -> None:
        """
        <BuildOrder> referencing non-existent project should be ignored.
        """
        lib = tmp_path / "Lib.dproj"
        lib.write_text("", encoding="utf-8")

        xml = _make_project_reference_groupproj(
            ["Lib.dproj"],
            build_order=["Missing.dproj", "Lib.dproj"],
        )
        groupproj = tmp_path / "ProjectGroup.groupproj"
        groupproj.write_text(xml, encoding="utf-8")

        from src.utils.groupproj_parser import parse_groupproj
        info = parse_groupproj(groupproj)

        # Only Lib.dproj exists
        assert len(info.child_projects) == 1
        assert info.child_projects[0].name == "Lib.dproj"
        # BuildOrder preserved as-is (including missing project)
        assert info.build_order == ["Missing.dproj", "Lib.dproj"]

    def test_topological_sort_with_dependencies(self, tmp_path: Path) -> None:
        """
        topological_sort() should order projects based on <Dependencies>.
        """
        lib = tmp_path / "Lib.dproj"
        app = tmp_path / "App.dproj"
        lib.write_text("", encoding="utf-8")
        app.write_text("", encoding="utf-8")

        xml = _make_projects_groupproj(
            ["App.dproj", "Lib.dproj"],  # XML order: App first
            dependencies={"App.dproj": ["Lib.dproj"]},  # App depends on Lib
        )
        groupproj = tmp_path / "ProjectGroup.groupproj"
        groupproj.write_text(xml, encoding="utf-8")

        from src.utils.groupproj_parser import parse_groupproj, topological_sort
        info = parse_groupproj(groupproj)
        sorted_projects = topological_sort(info)

        # Lib should come before App
        assert len(sorted_projects) == 2
        assert sorted_projects[0].name == "Lib.dproj"
        assert sorted_projects[1].name == "App.dproj"

    def test_no_build_order_keeps_original_order(self, tmp_path: Path) -> None:
        """
        Without <BuildOrder>, projects should keep original XML order.
        """
        app = tmp_path / "App.dproj"
        lib = tmp_path / "Lib.dproj"
        app.write_text("", encoding="utf-8")
        lib.write_text("", encoding="utf-8")

        # No BuildOrder
        xml = f'''<?xml version="1.0" encoding="utf-8"?>
<ProjectGroup xmlns="{MSBUILD_NS}">
  <ProjectReference Include="App.dproj" />
  <ProjectReference Include="Lib.dproj" />
</ProjectGroup>'''
        groupproj = tmp_path / "ProjectGroup.groupproj"
        groupproj.write_text(xml, encoding="utf-8")

        from src.utils.groupproj_parser import parse_groupproj
        info = parse_groupproj(groupproj)

        # Should keep XML order
        assert info.child_projects[0].name == "App.dproj"
        assert info.child_projects[1].name == "Lib.dproj"


class TestCompileGroupProject:
    """Integration-style tests via _compile_group_project (with mocked compiler)."""

    @pytest.mark.asyncio
    async def test_project_reference_extracted(self, tmp_path: Path, monkeypatch) -> None:
        """_compile_group_project parses <ProjectReference> correctly."""
        # Create sub-project .dproj files so they exist
        proj1 = tmp_path / "LibUtils.dproj"
        proj2 = tmp_path / "MainApp.dproj"
        proj1.write_text("", encoding="utf-8")
        proj2.write_text("", encoding="utf-8")

        # Create a .groupproj using the tutorial format
        groupproj = tmp_path / "ProjectGroup.groupproj"
        groupproj.write_text(_make_project_reference_groupproj(["LibUtils.dproj", "MainApp.dproj"]), encoding="utf-8")

        # Mock the compiler service
        from src.tools.compile_project import _compile_group_project
        from src.tools.compile_project import _compiler_service
        from src.models.compile_request import CompileOptions, TargetPlatform

        child_calls: list[str] = []

        class FakeCompileResult:
            status = SimpleNamespace(value="success")
            errors = []
            warnings = []
            output_file = ""
            log = ""
            duration = 0

        class FakeService:
            async def compile_project(self, request):
                child_calls.append(request.project_path)
                return FakeCompileResult()

        # Inject mock
        monkeypatch.setattr("src.tools.compile_project._compiler_service", FakeService())

        result = await _compile_group_project(
            project_path=str(groupproj),
            target_platform="win32",
            build_configuration="Debug",
            timeout=120,
        )

        assert not result.isError
        assert len(child_calls) == 2
        assert str(proj1.resolve()) in child_calls
        assert str(proj2.resolve()) in child_calls

    @pytest.mark.asyncio
    async def test_error_on_missing_groupproj(self, tmp_path: Path, monkeypatch) -> None:
        """Non-existent .groupproj returns an error."""
        from src.tools.compile_project import _compile_group_project

        monkeypatch.setattr("src.tools.compile_project._compiler_service", SimpleNamespace())

        result = await _compile_group_project(
            project_path=str(tmp_path / "nonexistent.groupproj"),
            target_platform="win32",
            build_configuration="Debug",
            timeout=120,
        )

        assert result.isError
        assert "不存在" in result.content[0].text

    @pytest.mark.asyncio
    async def test_error_on_empty_groupproj(self, tmp_path: Path, monkeypatch) -> None:
        """A .groupproj with no sub-projects returns an error."""
        groupproj = tmp_path / "empty.groupproj"
        groupproj.write_text(_make_project_reference_groupproj([]), encoding="utf-8")

        from src.tools.compile_project import _compile_group_project

        monkeypatch.setattr("src.tools.compile_project._compiler_service", SimpleNamespace())

        result = await _compile_group_project(
            project_path=str(groupproj),
            target_platform="win32",
            build_configuration="Debug",
            timeout=120,
        )

        assert result.isError
        assert "未找到" in result.content[0].text

    @pytest.mark.asyncio
    async def test_error_on_bad_xml(self, tmp_path: Path, monkeypatch) -> None:
        """Malformed XML returns a parse error."""
        groupproj = tmp_path / "bad.groupproj"
        groupproj.write_text("this is not xml", encoding="utf-8")

        from src.tools.compile_project import _compile_group_project

        monkeypatch.setattr("src.tools.compile_project._compiler_service", SimpleNamespace())

        result = await _compile_group_project(
            project_path=str(groupproj),
            target_platform="win32",
            build_configuration="Debug",
            timeout=120,
        )

        assert result.isError
        assert "解析" in result.content[0].text
