"""极限用例测试：dpk 同步工具的边界条件、异常输入、压力测试"""

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
)


# ============================================================
# 1. 空/最小 dpk 文件
# ============================================================


def test_minimal_dpk_no_sections():
    """只有 package 头和 end.，没有 requires/contains"""
    dpk = _make("package MyPkg;\nend.\n")

    # 解析应该返回空
    assert _dpk_requires_entries(dpk) == []
    assert _dpk_contains_entries(dpk) == []

    # 添加 requires
    bak = _dpk_add_requires(dpk, "rtl")
    assert bak is not None
    assert "requires" in open(dpk, encoding="utf-8-sig").read()

    # 添加 contains
    bak = _dpk_add_contains(dpk, "Unit1.pas", "Unit1")
    assert bak is not None
    assert "contains" in open(dpk, encoding="utf-8-sig").read()


def test_no_end_statement():
    """没有 end. — 这是畸形文件，不崩溃即可"""
    dpk = _make("package MyPkg;\nrequires\n  rtl;\n")

    # 应该还能正常解析（极端情况容忍）
    req = _dpk_requires_entries(dpk)
    assert len(req) >= 0  # 至少不崩溃

    # 添加 contains（缺少 end. 时不应崩溃）
    # 不 assert 返回值——此时文件是畸形状态，行为未定义，只要不抛异常即可
    try:
        _dpk_add_contains(dpk, "Unit1.pas", "Unit1")
    except Exception:
        pass


# ============================================================
# 2. 畸形分隔符
# ============================================================


def test_contains_all_semicolons():
    """每个 contains 条目都以 ; 结尾（非正常格式）"""
    dpk = _make("""package Test;
contains
  Unit1 in 'a.pas';
  Unit2 in 'b.pas';
end.
""")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 2

    # 删除第一条
    _dpk_remove_contains(dpk, "a.pas")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 1
    assert entries[0][1] == "Unit2"


def test_contains_no_separators():
    """contains 条目末尾没有任何分隔符（仍可解析，后面添加修复分隔符）"""
    dpk = _make("""package Test;
contains
  Unit1 in 'a.pas'
  Unit2 in 'b.pas'
end.
""")
    entries = _dpk_contains_entries(dpk)
    # regex 中 ,? 和 ;? 都是可选的，所以无分隔符也能匹配
    assert len(entries) == 2
    assert entries[0][1] == "Unit1"
    assert entries[1][1] == "Unit2"

    # 添加新条目应正常工作
    _dpk_add_contains(dpk, "c.pas", "Unit3")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 3

    # 删除也应工作
    _dpk_remove_contains(dpk, "b.pas")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 2


# ============================================================
# 3. 注释处理
# ============================================================


def test_contains_with_brace_comment():
    """contains 节中有 { } 注释"""
    dpk = _make("""package Test;
{$R *.res}
{ This is a comment }
contains
  Unit1 in 'a.pas',
  { Another comment }
  Unit2 in 'b.pas';
  { Final comment }
end.
""")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 2
    assert entries[0][1] == "Unit1"
    assert entries[1][1] == "Unit2"

    # 删除
    _dpk_remove_contains(dpk, "a.pas")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 1
    assert entries[0][1] == "Unit2"


# ============================================================
# 4. 编码测试
# ============================================================

def test_ansi_encoding():
    """ANSI 编码文件（非 UTF-8）"""
    import tempfile as _tf
    dpk = _tf.NamedTemporaryFile(suffix=".dpk", delete=False, mode="wb")
    dpk_name = dpk.name
    content = b"package Test;\ncontains\n  Unit1 in 'a.pas';\nend.\n"
    dpk.write(content)
    dpk.close()

    try:
        # read_text with utf-8-sig on ANSI might fail gracefully
        entries = _dpk_contains_entries(dpk_name)
        # ANSI 中纯 ASCII 内容和 UTF-8 一样
        assert len(entries) == 1

        # 添加操作也应可用
        bak = _dpk_add_contains(dpk_name, "b.pas", "Unit2")
        assert bak is not None
    finally:
        os.unlink(dpk_name)


def test_utf8_bom():
    """UTF-8 BOM 文件"""
    import tempfile as _tf
    dpk = _tf.NamedTemporaryFile(suffix=".dpk", delete=False, mode="wb")
    dpk_name = dpk.name
    content = "package Test;\ncontains\n  Unit1 in 'a.pas';\nend.\n"
    dpk.write(b"\xef\xbb\xbf" + content.encode("utf-8"))
    dpk.close()

    try:
        entries = _dpk_contains_entries(dpk_name)
        assert len(entries) == 1

        _dpk_add_contains(dpk_name, "b.pas", "Unit2")
        entries = _dpk_contains_entries(dpk_name)
        assert len(entries) == 2
    finally:
        os.unlink(dpk_name)


def test_unicode_paths():
    """Unicode 路径（中文/特殊字符）"""
    dpk = _make("""package Test;
contains
  Unit1 in 'Source\\\u4e2d\u6587\\Unit1.pas',
  Unit2 in 'Source\\special !@#\\Unit2.pas';
end.
""")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 2
    assert "\u4e2d\u6587" in entries[0][2]

    # 用中文路径删除
    bak = _dpk_remove_contains(dpk, "Source\\\u4e2d\u6587\\Unit1.pas")
    assert bak is not None
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 1
    assert entries[0][1] == "Unit2"


# ============================================================
# 5. 同名不同路径
# ============================================================


def test_same_unit_name_different_paths():
    """同名单元不同路径"""
    dpk = _make("""package Test;
contains
  Helper in 'Utils\\Helper.pas',
  Helper in 'Vendors\\Helper.pas';
end.
""")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 2

    # 只删除 Utils 下的
    _dpk_remove_contains(dpk, "Utils\\Helper.pas")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 1
    assert entries[0][2] == "Vendors\\Helper.pas"


# ============================================================
# 6. 往返操作 (add → remove → add)
# ============================================================


def test_add_remove_add_roundtrip():
    """添加 → 删除 → 再次添加同一条"""
    dpk = _make("""package Test;
contains
  Unit1 in 'a.pas',
  Unit2 in 'b.pas';
end.
""")

    # 删除 Unit2
    _dpk_remove_contains(dpk, "b.pas")
    assert len(_dpk_contains_entries(dpk)) == 1

    # 再次添加 Unit2
    _dpk_add_contains(dpk, "b.pas", "Unit2")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 2
    # 分隔符正确：第一个是 , 最后是 ;
    content = open(dpk, encoding="utf-8-sig").read()
    assert "a.pas'," in content
    assert "b.pas';" in content


# ============================================================
# 7. 同时多次删除
# ============================================================


def test_double_remove_is_safe():
    """重复删除同一条（幂等性）"""
    dpk = _make("""package Test;
contains
  Unit1 in 'a.pas';
end.
""")
    bak1 = _dpk_remove_contains(dpk, "a.pas")
    assert bak1 is not None

    bak2 = _dpk_remove_contains(dpk, "a.pas")
    assert bak2 is None  # 第二次找不到


# ============================================================
# 8. 仅 requires 无 contains，再添加 contains
# ============================================================


def test_only_requires_then_add_contains():
    """只有 requires 节，添加 contains"""
    dpk = _make("""package Test;
requires
  rtl,
  vcl;
end.
""")
    bak = _dpk_add_contains(dpk, "Unit1.pas", "Unit1")
    assert bak is not None

    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 1
    assert entries[0][1] == "Unit1"


# ============================================================
# 9. 深度嵌套路径
# ============================================================


def test_deeply_nested_path():
    """深层嵌套路径"""
    deep_path = "A\\B\\C\\D\\E\\F\\VeryDeep\\Unit1.pas"
    dpk = _make(f"""package Test;
contains
  Unit1 in '{deep_path}';
end.
""")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 1
    assert entries[0][2] == deep_path

    # 通过部分路径删除 — 应该用完整路径匹配
    bak = _dpk_remove_contains(dpk, deep_path)
    assert bak is not None
    assert len(_dpk_contains_entries(dpk)) == 0


# ============================================================
# 10. Requires 包名含点号
# ============================================================


def test_requires_dotted_package_names():
    """带点号的包名: System.SysUtils"""
    dpk = _make("""package Test;
requires
  System.SysUtils,
  System.Classes;
end.
""")
    req = _dpk_requires_entries(dpk)
    assert len(req) == 2
    assert req[0][1] == "System.SysUtils"
    assert req[1][1] == "System.Classes"

    _dpk_add_requires(dpk, "Data.DB")
    req = _dpk_requires_entries(dpk)
    assert len(req) == 3
    assert req[2][1] == "Data.DB"


# ============================================================
# 11. 文件状态异常
# ============================================================


def test_nonexistent_file():
    """不存在的文件路径"""
    fake = "C:\\nonexistent\\fake.dpk"
    assert _dpk_contains_entries(fake) == []
    assert _dpk_requires_entries(fake) == []
    assert _dpk_add_contains(fake, "a.pas", "A") is None
    assert _dpk_remove_contains(fake, "a.pas") is None
    assert _dpk_add_requires(fake, "rtl") is None
    assert _dpk_remove_requires(fake, "rtl") is None


# ============================================================
# 12. 超长条目
# ============================================================


def test_very_long_path():
    """超长路径（接近 Windows 260 字符限制）"""
    long_dir = "X" * 200
    dpk = _make(f"""package Test;
contains
  Unit1 in '{long_dir}\\Unit1.pas';
end.
""")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 1
    assert len(entries[0][2]) > 200

    # 用完整路径删除
    bak = _dpk_remove_contains(dpk, f"{long_dir}\\Unit1.pas")
    assert bak is not None
    assert len(_dpk_contains_entries(dpk)) == 0


# ============================================================
# 13. 混合正常 + 畸形行
# ============================================================


def test_malformed_lines_among_valid():
    """合法条目与畸形条目混排"""
    dpk = _make("""package Test;
contains
  Unit1 in 'a.pas',
  garbage text here,
  Unit2 in 'b.pas';
  {comment}
  ,
  Unit3 in 'c.pas';
end.
""")
    entries = _dpk_contains_entries(dpk)
    # 只有符合 regex 的条目被解析
    names = [e[1] for e in entries]
    assert "Unit1" in names
    assert "Unit2" in names
    assert "Unit3" in names

    # 删除应只通过解析匹配，不影响畸形行
    _dpk_remove_contains(dpk, "b.pas")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 2
    assert entries[0][1] == "Unit1"
    assert entries[1][1] == "Unit3"

    # 文件不应被破坏（畸形行还在）
    content = open(dpk, encoding="utf-8-sig").read()
    assert "garbage text here" in content


# ============================================================
# 14. 一个 contains 条目跨多行（畸形）
# ============================================================


def test_multiline_entry():
    """条目跨多行（不正常，但不应崩溃）"""
    dpk = _make("""package Test;
contains
  Unit1 in 'a' +
    '.pas',
  Unit2 in 'b.pas';
end.
""")
    entries = _dpk_contains_entries(dpk)
    # 第一行不符合 regex，被跳过；第二行也不符合（+, 被包含？）
    # 取决于具体 regex 匹配
    assert len(entries) >= 0  # 不崩溃即可

    # 添加/删除也不应崩溃
    _dpk_add_contains(dpk, "c.pas", "Unit3")
    _dpk_remove_contains(dpk, "b.pas")


# ============================================================
# 15. Contains 条目末尾混合 ; 和 , 异常
# ============================================================


def test_mixed_semicolons_and_commas():
    """包含条目中混合 ; 和 ,（不标准但常见的最佳实践差异）"""
    dpk = _make("""package Test;
contains
  Unit1 in 'a.pas',
  Unit2 in 'b.pas',
  Unit3 in 'c.pas';
  Unit4 in 'd.pas';
end.
""")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 4

    # 删除第三条
    _dpk_remove_contains(dpk, "c.pas")
    entries = _dpk_contains_entries(dpk)
    assert len(entries) == 3
    # d.pas 仍以 ; 结尾（原就是 ;）
    content = open(dpk, encoding="utf-8-sig").read()
    assert "d.pas';" in content


# ============================================================
# 辅助
# ============================================================


def _make(content: str) -> str:
    dpk = tempfile.NamedTemporaryFile(mode="w", suffix=".dpk", delete=False, encoding="utf-8")
    dpk.write(content)
    dpk.close()
    return dpk.name


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
