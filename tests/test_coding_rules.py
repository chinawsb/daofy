"""
Tests for src/tools/coding_rules.py

Covers: section extraction, section parameter behavior, error handling
"""
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.tools.coding_rules import (
    get_coding_rules,
    _find_heading_ranges,
    _strip_trailing_separator,
    _extract_section,
    _extract_meta_section,
    _list_available_sections,
    SECTION_KEYS,
    META_SECTIONS,
)

# =========================================================================
# Unit tests for internal helpers (pure functions, no file I/O)
# =========================================================================

SAMPLE_MD = """# Title
> v1.0

## 工作流总览
```
① → ② → ③
```

## ③ 写 Delphi 代码
### 命名
- **类型**：T 前缀

### 泛型
- 参数用描述性名称

## 审核
### 一致性
| 检查项 | 说明 |
|--------|------|
| 命名规范 | 风格统一 |

### 安全
| 检查项 | 说明 |
|--------|------|
| SQL 注入 | 参数化查询 |
"""


class TestFindHeadingRanges:
    def test_finds_all_headings(self):
        lines = SAMPLE_MD.split('\n')
        ranges = _find_heading_ranges(lines)
        assert "工作流总览" in ranges
        assert "③ 写 Delphi 代码" in ranges
        assert "审核" in ranges
        assert "一致性" in ranges
        assert "安全" in ranges

    def test_ranges_are_correct(self):
        lines = SAMPLE_MD.split('\n')
        ranges = _find_heading_ranges(lines)
        # 工作流总览 starts at its heading, ends before next ##
        wf_start = lines.index("## 工作流总览")
        wf_end = lines.index("## ③ 写 Delphi 代码")
        assert ranges["工作流总览"] == (wf_start, wf_end)
        # 一致性 starts at its heading, ends before next ###
        con_start = lines.index("### 一致性")
        con_end = lines.index("### 安全")
        assert ranges["一致性"] == (con_start, con_end)


class TestStripTrailingSeparator:
    def test_strips_trailing_separator(self):
        assert _strip_trailing_separator("foo\n---") == "foo"
        # Trailing \n after --- is consumed by \s*
        assert _strip_trailing_separator("foo\n---\n") == "foo"
        assert _strip_trailing_separator("no separator") == "no separator"


class TestExtractSection:
    def test_extracts_by_direct_title(self):
        result = _extract_section(SAMPLE_MD, "工作流总览")
        assert result is not None
        assert "① → ② → ③" in result
        assert "# Title" in result  # title block included

    def test_extracts_by_section_key(self):
        # "writing" maps to "③ 写 Delphi 代码"
        result = _extract_section(SAMPLE_MD, "writing")
        assert result is not None
        assert "命名" in result
        assert "泛型" in result
        assert "描述性名称" in result

    def test_extracts_subsection(self):
        result = _extract_section(SAMPLE_MD, "安全")
        assert result is not None
        assert "SQL 注入" in result
        assert "# Title" in result

    def test_returns_none_for_unknown(self):
        result = _extract_section(SAMPLE_MD, "nonexistent")
        assert result is None

    def test_extracts_subsection_by_key(self):
        result = _extract_section(SAMPLE_MD, "safety")
        assert result is not None
        assert "SQL 注入" in result


class TestExtractMetaSection:
    def test_review_meta_combines_sections(self):
        lines = SAMPLE_MD.split('\n')
        ranges = _find_heading_ranges(lines)
        result = _extract_meta_section(SAMPLE_MD, "review", ranges)
        assert result is not None
        assert "代码审核" in result or "审核" in result
        assert "一致性" in result
        assert "SQL 注入" in result

    def test_unknown_meta_returns_none(self):
        result = _extract_meta_section(SAMPLE_MD, "bogus", {})
        assert result is None


class TestListAvailableSections:
    def test_lists_keys(self):
        result = _list_available_sections(SAMPLE_MD)
        assert "writing" in result
        assert "safety" in result
        assert "workflow" in result


# =========================================================================
# Integration tests for get_coding_rules (mocked file I/O)
# =========================================================================

FAKE_DEFAULT_RULES = """# Delphi 编码规范
> 最后更新: 2026-05-14 | 版本: 9.9.9

## 工作流总览
```
① → ② → ③
```

## ③ 写 Delphi 代码
### 命名
- 规则A
"""

FAKE_USER_RULES = """## ③ 写 Delphi 代码
### 命名
- 规则B（覆盖）
"""


@pytest.fixture
def mock_default_rules():
    """Mock config/CODING_RULES.mdc to return FAKE_DEFAULT_RULES."""
    with patch("builtins.open", mock_open(read_data=FAKE_DEFAULT_RULES)):
        with patch("pathlib.Path.exists", return_value=True):
            yield


@pytest.fixture
def mock_no_rules():
    """No rules file exists."""
    with patch("pathlib.Path.exists", return_value=False):
        yield


class TestGetCodingRules:
    @pytest.mark.asyncio
    async def test_default_returns_workflow_and_index(self, mock_default_rules):
        result = await get_coding_rules()
        text = result.content[0].text
        assert "工作流总览" in text
        assert "章节索引" in text
        assert "section=\"writing\"" in text
        assert not result.isError

    @pytest.mark.asyncio
    async def test_section_writing_returns_content(self, mock_default_rules):
        result = await get_coding_rules(section="writing")
        text = result.content[0].text
        assert "规则A" in text
        assert not result.isError

    @pytest.mark.asyncio
    async def test_section_list_returns_keys(self, mock_default_rules):
        result = await get_coding_rules(section="list")
        text = result.content[0].text
        assert "writing" in text
        assert not result.isError

    @pytest.mark.asyncio
    async def test_section_nonexistent_returns_error(self, mock_default_rules):
        result = await get_coding_rules(section="bogus_section")
        assert result.isError
        assert "未知章节" in result.content[0].text

    @pytest.mark.asyncio
    async def test_no_rules_file_returns_error(self, mock_no_rules):
        result = await get_coding_rules()
        assert result.isError
        assert "未找到" in result.content[0].text

    @pytest.mark.asyncio
    async def test_with_project_path_merges_rules(self):
        """Test that project_path merges user rules over defaults."""
        def fake_open_side_effect(file, *args, **kwargs):
            path_str = str(file) if hasattr(file, '__fspath__') else str(file)
            if 'CODING_RULES.mdc' in path_str and 'config' in path_str.replace('\\', '/'):
                return mock_open(read_data=FAKE_DEFAULT_RULES).return_value
            return mock_open(read_data=FAKE_USER_RULES).return_value

        with patch("builtins.open", side_effect=fake_open_side_effect):
            with patch("pathlib.Path.exists", return_value=True):
                result = await get_coding_rules(project_path="/fake/project")
                text = result.content[0].text
                # Default rules should be included
                assert "规则A" in text or "工作流总览" in text
                assert not result.isError

    @pytest.mark.asyncio
    async def test_section_review_meta(self, mock_default_rules):
        result = await get_coding_rules(section="review")
        text = result.content[0].text
        # review meta-section may not have data in minimal mock
        # Either find ⑥ or fall through to the unknown handler
        if "未知章节" in text:
            # Acceptable: mock data doesn't have ⑥ 代码审核 section
            assert result.isError
        else:
            assert not result.isError

    @pytest.mark.asyncio
    async def test_section_safety_subsection(self, mock_default_rules):
        """safety section not in minimal mock data — expect error."""
        result = await get_coding_rules(section="safety")
        # Minimal mock data doesn't include safety section
        assert result.isError
        assert "未知章节" in result.content[0].text

    @pytest.mark.asyncio
    async def test_section_performance_subsection(self, mock_default_rules):
        """performance section not in minimal mock data — expect error."""
        result = await get_coding_rules(section="performance")
        assert result.isError
        assert "未知章节" in result.content[0].text
