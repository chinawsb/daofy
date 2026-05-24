"""测试 .dpk contains / requires 同步功能"""

import os
import tempfile

import pytest

from src.tools.dproj_tool import (
    _dpk_contains_entries,
    _dpk_add_contains,
    _dpk_remove_contains,
    _dpk_requires_entries,
    _dpk_add_requires,
    _dpk_remove_requires,
    _get_dpk_path_from_dproj,
)


# ============================================================
# 基础解析
# ============================================================


def test_dpk_parse():
    """完整 dpk 文件解析"""
    dpk = _make_dpk("""package TestPackage;
{$R *.res}

requires
  rtl,
  vcl;

contains
  Unit1 in 'Source\\Unit1.pas',
  Unit2 in 'Source\\Unit2.pas';

end.
""")

    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 2
    assert entries[0][1] == "Unit1"
    assert entries[0][2] == "Source\\Unit1.pas"
    assert entries[1][1] == "Unit2"

    req = _dpk_requires_entries(dpk)
    assert len(req) == 2
    assert req[0][1] == "rtl"
    assert req[1][1] == "vcl"


# ============================================================
# 添加 contains 条目 — _dpk_add_contains
# ============================================================


def test_add_contains_to_existing():
    """向已有 contains 节末尾添加条目"""
    dpk = _make_dpk("""package TestPackage;
{$R *.res}

requires
  rtl;

contains
  Unit1 in 'Unit1.pas';

end.
""")

    bak = _dpk_add_contains(dpk, r"Source\Unit3.pas", "Unit3")
    assert bak is not None

    content = open(dpk, encoding="utf-8-sig").read()
    assert "Unit3 in 'Source\\Unit3.pas'" in content

    # 检查分隔符：Unit1 行从 ";" 变为 ","
    assert "Unit1 in 'Unit1.pas'," in content
    # 新条目以 ";" 结尾（最后一条）
    assert "Unit3 in 'Source\\Unit3.pas';" in content


def test_add_contains_duplicate_returns_none():
    """重复添加应返回 None"""
    dpk = _make_dpk("""package TestPackage;

contains
  Unit1 in 'Unit1.pas';

end.
""")

    bak1 = _dpk_add_contains(dpk, r"Source\Unit3.pas", "Unit3")
    assert bak1 is not None

    bak2 = _dpk_add_contains(dpk, r"Source\Unit3.pas", "Unit3")
    assert bak2 is None


def test_add_contains_no_contains_section():
    """没有 contains 节时自动创建"""
    dpk = _make_dpk("""package TestPackage;
{$R *.res}

requires
  rtl;

end.
""")

    bak = _dpk_add_contains(dpk, "Unit1.pas", "Unit1")
    assert bak is not None

    content = open(dpk, encoding="utf-8-sig").read()
    assert "contains" in content.lower()
    assert "Unit1 in 'Unit1.pas';" in content


# ============================================================
# 删除 contains 条目 — _dpk_remove_contains
# ============================================================


def test_remove_middle_entry():
    """删除中间条目，分隔符自动保留正确"""
    dpk = _make_dpk("""package TestPackage;

contains
  Unit1 in 'Unit1.pas',
  Unit2 in 'Unit2.pas',
  Unit3 in 'Unit3.pas';

end.
""")

    bak = _dpk_remove_contains(dpk, "Unit2.pas")
    assert bak is not None

    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 2
    assert entries[0][1] == "Unit1"
    assert entries[1][1] == "Unit3"

    content = open(dpk, encoding="utf-8-sig").read()
    # Unit1 现在不是最后一条，保留 ","
    assert "Unit1 in 'Unit1.pas'," in content
    # Unit3 是最后一条，必须是 ";"
    assert "Unit3 in 'Unit3.pas';" in content


def test_remove_last_entry_fixes_separator():
    """删除最后一条，前一条的逗号应改为分号"""
    dpk = _make_dpk("""package TestPackage;

contains
  Unit1 in 'Unit1.pas',
  Unit2 in 'Unit2.pas',
  Unit3 in 'Unit3.pas';

end.
""")

    _dpk_remove_contains(dpk, "Unit3.pas")

    content = open(dpk, encoding="utf-8-sig").read()
    # Unit2 现在是最后一条，必须用 ";"
    assert "Unit2 in 'Unit2.pas';" in content


def test_remove_first_entry():
    """删除第一条"""
    dpk = _make_dpk("""package TestPackage;

contains
  Unit1 in 'Unit1.pas',
  Unit2 in 'Unit2.pas',
  Unit3 in 'Unit3.pas';

end.
""")

    _dpk_remove_contains(dpk, "Unit1.pas")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 2
    assert entries[0][1] == "Unit2"
    assert entries[1][1] == "Unit3"
    # Unit3 仍然是最后一条，保持 ";"
    content = open(dpk, encoding="utf-8-sig").read()
    assert "Unit3 in 'Unit3.pas';" in content


def test_remove_only_entry():
    """删除唯一条目"""
    dpk = _make_dpk("""package TestPackage;

contains
  Unit1 in 'Unit1.pas';

end.
""")

    bak = _dpk_remove_contains(dpk, "Unit1.pas")
    assert bak is not None
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 0
    # contains 节仍保留（无条目），不报错即可


def test_remove_not_found_returns_none():
    """删除不存在的条目"""
    dpk = _make_dpk("""package TestPackage;

contains
  Unit1 in 'Unit1.pas';

end.
""")

    bak = _dpk_remove_contains(dpk, "NonExistent.pas")
    assert bak is None


def test_remove_not_found_no_backup():
    """未找到时不应创建备份文件"""
    import os as _os
    dpk = _make_dpk("""package TestPackage;
{$R *.res}

contains
  Unit1 in 'Unit1.pas';

end.
""")
    history_dir = _os.path.join(_os.path.dirname(dpk), "__history")
    count_before = len(_os.listdir(history_dir)) if _os.path.isdir(history_dir) else 0

    bak = _dpk_remove_contains(dpk, "NonExistent.pas")
    assert bak is None

    count_after = len(_os.listdir(history_dir)) if _os.path.isdir(history_dir) else 0
    assert count_after == count_before, "不应创建备份文件"


def test_remove_with_path_normalization():
    """路径格式不敏感（/ vs \\）"""
    dpk = _make_dpk("""package TestPackage;

contains
  Unit1 in 'Source\\Unit1.pas';

end.
""")

    bak = _dpk_remove_contains(dpk, "Source/Unit1.pas")
    assert bak is not None, "正斜杠应匹配反斜杠路径"


def test_remove_correct_line_matching():
    """同名不同路径不误删"""
    dpk = _make_dpk("""package TestPackage;

contains
  Helper in 'Utils\\Helper.pas',
  Helper in 'Other\\Helper.pas';

end.
""")

    _dpk_remove_contains(dpk, "Utils\\Helper.pas")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 1
    assert entries[0][2] == "Other\\Helper.pas"


# ============================================================
# 添加 requires 条目 — _dpk_add_requires
# ============================================================


def test_add_requires_single_entry():
    """向单条目 requires 添加，新条目以分号结尾"""
    dpk = _make_dpk("""package TestPackage;

requires
  rtl;

end.
""")

    bak = _dpk_add_requires(dpk, "vcl")
    assert bak is not None

    content = open(dpk, encoding="utf-8-sig").read()
    assert "vcl;" in content, f"vcl 应以分号结尾:\n{content}"
    # rtl 行从分号改为逗号
    assert "rtl," in content


def test_add_requires_with_following_contains():
    """有 contains 时添加 requires，最后一条须以分号结尾"""
    dpk = _make_dpk("""package TestPackage;

requires
  rtl;

contains
  Unit1 in 'Unit1.pas';

end.
""")

    _dpk_add_requires(dpk, "vcl")
    content = open(dpk, encoding="utf-8-sig").read()
    assert "vcl;" in content, f"vcl 应以分号结尾:\n{content}"


def test_add_requires_duplicate_returns_none():
    """重复添加返回 None"""
    dpk = _make_dpk("""package TestPackage;

requires
  rtl;

end.
""")

    _dpk_add_requires(dpk, "vcl")
    bak = _dpk_add_requires(dpk, "vcl")
    assert bak is None


def test_add_requires_no_section():
    """没有 requires 节时自动创建"""
    dpk = _make_dpk("""package TestPackage;

end.
""")

    bak = _dpk_add_requires(dpk, "rtl")
    assert bak is not None

    content = open(dpk, encoding="utf-8-sig").read()
    assert "requires" in content.lower()
    assert "rtl;" in content


# ============================================================
# 删除 requires 条目 — _dpk_remove_requires
# ============================================================


def test_remove_requires():
    """删除 requires 条目"""
    dpk = _make_dpk("""package TestPackage;

requires
  rtl,
  vcl;

end.
""")

    bak = _dpk_remove_requires(dpk, "vcl")
    assert bak is not None
    entries = _dpk_requires_entries(dpk)
    assert len(entries) == 1
    assert entries[0][1] == "rtl"


def test_remove_requires_not_found():
    """删除不存在的 requires 条目"""
    dpk = _make_dpk("""package TestPackage;

requires
  rtl;

end.
""")

    bak = _dpk_remove_requires(dpk, "nonexistent")
    assert bak is None


# ============================================================
# _get_dpk_path_from_dproj
# ============================================================


def test_get_dpk_path_from_dproj():
    """从 Package 的 .dproj 解析 .dpk 路径"""
    import tempfile as _tf
    tmpdir = _tf.mkdtemp()

    dpk_path = os.path.join(tmpdir, "MyPackage.dpk")
    with open(dpk_path, "w") as f:
        f.write("package MyPackage;\nend.\n")

    dproj_path = os.path.join(tmpdir, "MyPackage.dproj")
    with open(dproj_path, "w", encoding="utf-8") as f:
        f.write("""<?xml version="1.0" encoding="utf-8"?>
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <AppType>Package</AppType>
    <MainSource>MyPackage.dpk</MainSource>
  </PropertyGroup>
</Project>
""")

    result = _get_dpk_path_from_dproj(dproj_path)
    assert result is not None
    assert result.lower() == dpk_path.lower()


def test_get_dpk_path_from_dproj_not_package():
    """非 Package 项目返回 None"""
    import tempfile as _tf
    tmpdir = _tf.mkdtemp()

    dproj_path = os.path.join(tmpdir, "MyApp.dproj")
    with open(dproj_path, "w", encoding="utf-8") as f:
        f.write("""<?xml version="1.0" encoding="utf-8"?>
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <AppType>Application</AppType>
    <MainSource>MyApp.dpr</MainSource>
  </PropertyGroup>
</Project>
""")

    result = _get_dpk_path_from_dproj(dproj_path)
    assert result is None


# ============================================================
# 辅助工具
# ============================================================


def _make_dpk(content: str) -> str:
    """创建临时 .dpk 文件，返回路径"""
    dpk = tempfile.NamedTemporaryFile(mode="w", suffix=".dpk", delete=False, encoding="utf-8")
    dpk.write(content)
    dpk.close()
    return dpk.name


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
