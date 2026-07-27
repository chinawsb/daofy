#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DprojParser tests"""

import sys
import tempfile
import shutil
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.dproj_parser import DprojParser
from src.tools.compile_file import _get_search_paths_from_dproj

GUID = "{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}"

# Use chr(36) to avoid PowerShell $ variable interpolation issues
D = chr(36)

XML = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">\n'
    '  <PropertyGroup>\n'
    '    <ProjectGuid>' + GUID + '</ProjectGuid>\n'
    '    <MainSource>Unit1</MainSource>\n'
    '    <ProjectVersion>22.0</ProjectVersion>\n'
    '  </PropertyGroup>\n'
    '  <PropertyGroup Condition="' + "'" + D + "(Config)'=='Debug'" + '">\n'
    '    <DCC_Define>DEBUG;TEST</DCC_Define>\n'
    '    <DCC_Output>DebugOut</DCC_Output>\n'
    '    <DCC_UnitSearchPath>units;shared</DCC_UnitSearchPath>\n'
    '  </PropertyGroup>\n'
    '  <PropertyGroup Condition="' + "'" + D + "(Config)'=='Release'" + '">\n'
    '    <DCC_Define>RELEASE</DCC_Define>\n'
    '  </PropertyGroup>\n'
    '  <PropertyGroup>\n'
    '    <PreBuildEvent>"echo Pre"</PreBuildEvent>\n'
    '    <PostBuildEvent>"echo Post"</PostBuildEvent>\n'
    '  </PropertyGroup>\n'
    '  <ItemGroup>\n'
    '    <DelphiCompile Include="Unit1.pas" />\n'
    '    <DelphiCompile Include="Unit2.pas" />\n'
    '  </ItemGroup>\n'
    '</Project>\n'
)


def _w(d):
    p = Path(d) / "t.dproj"
    p.write_text(XML, encoding='utf-8')
    return str(p)


def test_parse():
    d = tempfile.mkdtemp()
    try:
        assert DprojParser(_w(d)).parse()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_info():
    d = tempfile.mkdtemp()
    try:
        p = DprojParser(_w(d))
        p.parse()
        assert p.get_project_info().get("project_guid") == GUID
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_version():
    d = tempfile.mkdtemp()
    try:
        p = DprojParser(_w(d))
        p.parse()
        assert p.get_project_version() == "22.0"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_mainsource():
    d = tempfile.mkdtemp()
    try:
        p = DprojParser(_w(d))
        p.parse()
        assert p.get_main_source() == "Unit1"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_events():
    d = tempfile.mkdtemp()
    try:
        p = DprojParser(_w(d))
        p.parse()
        ev = p.get_build_events()
        assert "Pre" in ev.get("pre_build", "")
        assert "Post" in ev.get("post_build", "")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_compile_file_keeps_dproj_unit_search_paths():
    """Project search paths must survive dproj parsing for single-file compile."""
    d = tempfile.mkdtemp()
    try:
        dproj_path = _w(d)
        paths = _get_search_paths_from_dproj(dproj_path, platform=None)
        assert str((Path(d) / "units").resolve()) in paths
        assert str((Path(d) / "shared").resolve()) in paths
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_invalid():
    d = tempfile.mkdtemp()
    try:
        p = Path(d) / "b.dproj"
        p.write_text("bad", encoding='utf-8')
        assert not DprojParser(str(p)).parse()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_missing():
    d = tempfile.mkdtemp()
    try:
        assert not DprojParser(str(Path(d) / "x.dproj")).parse()
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
