#!/usr/bin/env python3
"""updater 模块单元测试 — PyPI 版本检查 + 智能路由 + 错误分类"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestFetchPypiVersion(unittest.TestCase):
    """测试 fetch_pypi_version() 函数"""

    @patch("src.utils.updater._retry_urlopen")
    def test_pypi_success_official(self, mock_urlopen):
        """从 PyPI 官方获取版本成功"""
        from src.utils.updater import fetch_pypi_version

        pypi_data = {"info": {"version": "2026.07.17"}}
        mock_urlopen.return_value = json.dumps(pypi_data).encode("utf-8")

        result = fetch_pypi_version()

        self.assertEqual(result, "2026.07.17")
        # 应该先尝试官方 PyPI
        call_url = mock_urlopen.call_args[0][0]
        self.assertIn("pypi.org", call_url)

    @patch("src.utils.updater._retry_urlopen")
    def test_pypi_success_mirror_fallback(self, mock_urlopen):
        """官方 PyPI 失败，回退到镜像成功"""
        from src.utils.updater import fetch_pypi_version

        call_count = [0]

        def side_effect(url, **kwargs):
            call_count[0] += 1
            if "pypi.org" in url:
                raise ConnectionError("官方 PyPI 不可达")
            # 镜像成功
            return json.dumps({"info": {"version": "2026.07.18"}}).encode("utf-8")

        mock_urlopen.side_effect = side_effect

        result = fetch_pypi_version()

        self.assertEqual(result, "2026.07.18")
        self.assertGreater(call_count[0], 1, "应该尝试了多个镜像")

    @patch("src.utils.updater._retry_urlopen")
    def test_pypi_all_mirrors_fail(self, mock_urlopen):
        """所有 PyPI 镜像均失败"""
        from src.utils.updater import fetch_pypi_version

        mock_urlopen.side_effect = ConnectionError("网络不可达")

        result = fetch_pypi_version()

        self.assertIsNone(result)

    @patch("src.utils.updater._retry_urlopen")
    def test_pypi_invalid_json(self, mock_urlopen):
        """PyPI 返回无效 JSON"""
        from src.utils.updater import fetch_pypi_version

        mock_urlopen.return_value = b"not json"

        result = fetch_pypi_version()

        self.assertIsNone(result)

    @patch("src.utils.updater._retry_urlopen")
    def test_pypi_missing_version_field(self, mock_urlopen):
        """PyPI 返回数据缺少 version 字段"""
        from src.utils.updater import fetch_pypi_version

        mock_urlopen.return_value = json.dumps({"info": {}}).encode("utf-8")

        result = fetch_pypi_version()

        self.assertIsNone(result)


class TestCategorizeRequestError(unittest.TestCase):
    """测试 _categorize_request_error() 错误分类"""

    def test_rate_limit_403(self):
        """GitHub 403 rate limit"""
        from src.utils.updater import _categorize_request_error

        err = Exception("HTTP Error 403: rate limit exceeded")
        result = _categorize_request_error(err)
        self.assertIn("受限", result)

    def test_timeout_error(self):
        """网络超时"""
        from src.utils.updater import _categorize_request_error

        err = TimeoutError("timed out")
        result = _categorize_request_error(err)
        self.assertIn("超时", result)

    def test_dns_error(self):
        """DNS 解析失败"""
        from src.utils.updater import _categorize_request_error

        err = Exception("getaddrinfo failed: name or service not known")
        result = _categorize_request_error(err)
        self.assertIn("DNS", result)

    def test_ssl_error(self):
        """SSL/代理问题"""
        from src.utils.updater import _categorize_request_error

        err = Exception("SSL: certificate verify failed")
        result = _categorize_request_error(err)
        self.assertIn("代理", result)

    def test_generic_error(self):
        """通用错误"""
        from src.utils.updater import _categorize_request_error

        err = Exception("something went wrong")
        result = _categorize_request_error(err)
        self.assertIn("请求失败", result)


class TestCheckForUpdateRouting(unittest.TestCase):
    """测试 check_for_update() 的安装方式路由逻辑"""

    @patch("src.utils.updater.is_pip_installation", return_value=True)
    @patch("src.utils.updater.fetch_pypi_version", return_value="2026.07.20")
    @patch("src.utils.updater.get_current_version", return_value="2026.07.17")
    def test_pip_installation_uses_pypi(self, mock_ver, mock_pypi, mock_pip):
        """pip 安装 → 优先查询 PyPI"""
        from src.utils.updater import check_for_update

        result = check_for_update()

        self.assertIsNotNone(result)
        self.assertEqual(result["latest"], "2026.07.20")
        self.assertEqual(result["source"], "pypi")
        self.assertTrue(result["update_available"])
        mock_pypi.assert_called_once()

    @patch("src.utils.updater.is_pip_installation", return_value=True)
    @patch("src.utils.updater.fetch_pypi_version", return_value=None)
    @patch("src.utils.updater.get_latest_version", return_value="2026.07.20")
    @patch("src.utils.updater.get_current_version", return_value="2026.07.17")
    def test_pip_fallback_to_github(self, mock_ver, mock_gh, mock_pypi, mock_pip):
        """pip 安装 + PyPI 失败 → 回退到 GitHub"""
        from src.utils.updater import check_for_update

        result = check_for_update()

        self.assertIsNotNone(result)
        self.assertEqual(result["latest"], "2026.07.20")
        self.assertEqual(result["source"], "github")
        mock_pypi.assert_called_once()
        mock_gh.assert_called_once()

    @patch("src.utils.updater.is_pip_installation", return_value=False)
    @patch("src.utils.updater.get_latest_version", return_value="2026.07.20")
    @patch("src.utils.updater.get_current_version", return_value="2026.07.17")
    def test_git_installation_uses_github(self, mock_ver, mock_gh, mock_pip):
        """git 安装 → 查询 GitHub"""
        from src.utils.updater import check_for_update

        result = check_for_update()

        self.assertIsNotNone(result)
        self.assertEqual(result["latest"], "2026.07.20")
        self.assertEqual(result["source"], "github")
        mock_gh.assert_called_once()

    @patch("src.utils.updater.is_pip_installation", return_value=True)
    @patch("src.utils.updater.fetch_pypi_version", return_value=None)
    @patch("src.utils.updater.get_latest_version", return_value=None)
    @patch("src.utils.updater.get_current_version", return_value="2026.07.17")
    def test_all_sources_fail_returns_none(self, mock_ver, mock_gh, mock_pypi, mock_pip):
        """所有版本源均失败 → 返回 None"""
        from src.utils.updater import check_for_update

        result = check_for_update()

        self.assertIsNone(result)

    @patch("src.utils.updater.is_pip_installation", return_value=True)
    @patch("src.utils.updater.fetch_pypi_version", return_value="2026.07.17")
    @patch("src.utils.updater.get_current_version", return_value="2026.07.17")
    def test_already_latest(self, mock_ver, mock_pypi, mock_pip):
        """已是最新版本"""
        from src.utils.updater import check_for_update

        result = check_for_update()

        self.assertIsNotNone(result)
        self.assertFalse(result["update_available"])
        self.assertEqual(result["source"], "pypi")

    @patch("src.utils.updater.is_pip_installation", return_value=True)
    @patch("src.utils.updater.fetch_pypi_version", return_value="v2026.07.20")
    @patch("src.utils.updater.get_current_version", return_value="2026.07.17")
    def test_v_prefix_stripped(self, mock_ver, mock_pypi, mock_pip):
        """版本号 v 前缀被正确去除"""
        from src.utils.updater import check_for_update

        result = check_for_update()

        self.assertIsNotNone(result)
        self.assertEqual(result["latest"], "2026.07.20")


class TestMirrorUrls(unittest.TestCase):
    """测试 GITHUB_MIRRORS 配置"""

    def test_mirrors_include_new_domains(self):
        """镜像列表包含新增的域名"""
        from src.utils.updater import GITHUB_MIRRORS

        self.assertIn("", GITHUB_MIRRORS)
        self.assertIn("https://ghproxy.com", GITHUB_MIRRORS)
        self.assertIn("https://ghproxy.net", GITHUB_MIRRORS)

    def test_pypi_mirrors_configured(self):
        """PyPI 镜像列表已配置"""
        from src.utils.updater import PYPI_MIRRORS

        self.assertIn("", PYPI_MIRRORS)
        self.assertTrue(len(PYPI_MIRRORS) >= 2, "应至少有官方 + 1 个镜像")

    @patch("src.utils.updater._retry_urlopen")
    def test_build_mirror_urls_dedup(self, mock_urlopen):
        """镜像 URL 构建去重"""
        from src.utils.updater import _build_mirror_urls

        urls = _build_mirror_urls("https://api.github.com/repos/test/releases/latest")
        # 应有多个 URL（原始 + 镜像）
        self.assertGreater(len(urls), 1)
        # 无重复
        self.assertEqual(len(urls), len(set(urls)))


class TestPypiConstants(unittest.TestCase):
    """测试 PyPI 常量配置"""

    def test_pypi_package_name(self):
        """PyPI 包名正确"""
        from src.utils.updater import PYPI_PACKAGE
        self.assertEqual(PYPI_PACKAGE, "daofy-for-delphi")

    def test_pypi_json_url(self):
        """PyPI JSON API URL 正确"""
        from src.utils.updater import PYPI_JSON_URL
        self.assertEqual(PYPI_JSON_URL, "https://pypi.org/pypi/daofy-for-delphi/json")


if __name__ == "__main__":
    unittest.main()
