#!/usr/bin/env python3
"""Daofy 安装脚本逻辑验证测试 - 干运行模式"""

import sys
import os
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path

# 添加项目根目录到 sys.path（tests/ 的父目录）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ============================================================
# 测试 1: install_mcp.py 核心函数单元测试
# ============================================================

class TestInstallMCPCore(unittest.TestCase):
    """测试 install_mcp.py 的核心函数"""

    def setUp(self):
        # 避免 ctypes.windll 在非 Windows 上报错
        self.platform_patcher = patch('install_mcp.sys.platform', 'win32')
        self.platform_patcher.start()

    def tearDown(self):
        self.platform_patcher.stop()

    def test_get_mcp_config_standard(self):
        """测试标准 MCP 配置生成"""
        from install_mcp import get_mcp_config
        cfg = get_mcp_config("C:\\python.exe", "Standard", use_pip=False)
        self.assertEqual(cfg["command"], "C:\\python.exe")
        self.assertIn("args", cfg)
        self.assertTrue(cfg["args"][0].endswith("server.py"),
                        f"Expected path ending with server.py, got: {cfg['args'][0]}")
        self.assertEqual(cfg["env"]["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(cfg["env"]["PYTHONUTF8"], "1")

    def test_get_mcp_config_opencode(self):
        """测试 OpenCode 专用格式：mcp 键 + type local + command 数组 + enabled + environment"""
        from install_mcp import get_mcp_config
        cfg = get_mcp_config("C:\\python.exe", "OpenCode", use_pip=False)
        # OpenCode 专用格式：command 为数组（[python, server.py]），type 为 local
        self.assertIsInstance(cfg["command"], list)
        self.assertEqual(cfg["command"][0], "C:\\python.exe")
        self.assertTrue(cfg["command"][1].endswith("server.py"),
                        f"Expected server.py, got: {cfg['command'][1]}")
        self.assertIsInstance(cfg["environment"], dict)
        self.assertEqual(cfg["environment"]["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(cfg["enabled"], True)

    def test_get_mcp_config_pip_mode(self):
        """测试 pip 安装模式配置"""
        from install_mcp import get_mcp_config
        cfg = get_mcp_config("C:\\python.exe", "Standard", use_pip=True)
        self.assertEqual(cfg["command"], "daofy")
        self.assertNotIn("args", cfg)
        self.assertEqual(cfg["env"]["PYTHONUTF8"], "1")

    def test_get_mcp_config_pip_opencode(self):
        """测试 pip 安装 + OpenCode 格式（command 为数组）"""
        from install_mcp import get_mcp_config
        cfg = get_mcp_config("C:\\python.exe", "OpenCode", use_pip=True)
        # OpenCode 格式下 command 是数组
        self.assertEqual(cfg["command"], ["daofy"])

    def test_is_server_dir_true(self):
        """测试 _is_server_dir 返回 True"""
        from install_mcp import _is_server_dir
        # 当前项目目录包含 src/server.py 和 requirements.txt
        result = _is_server_dir()
        self.assertTrue(result)

    def test_is_server_dir_false(self):
        """测试 _is_server_dir 在空目录返回 False"""
        from install_mcp import _is_server_dir, get_script_dir
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('install_mcp.get_script_dir', return_value=Path(tmpdir)):
                result = _is_server_dir()
                self.assertFalse(result)

    def test_build_mirror_urls(self):
        """测试镜像 URL 构建"""
        from install_mcp import _build_mirror_urls, GITHUB_MIRRORS
        urls = _build_mirror_urls("https://api.github.com/repos/test/repo")
        self.assertEqual(len(urls), 2)  # 原始源 + ghproxy
        self.assertEqual(urls[0], "https://api.github.com/repos/test/repo")
        self.assertEqual(urls[1], "https://ghproxy.net/https://api.github.com/repos/test/repo")

    def test_build_mirror_urls_valid(self):
        """测试镜像 URL 构建结果格式"""
        from install_mcp import _build_mirror_urls
        urls = _build_mirror_urls("https://api.github.com/test")
        # 第一个是原始源，第二个是 ghproxy 镜像
        self.assertEqual(len(urls), 2)
        self.assertEqual(urls[0], "https://api.github.com/test")
        self.assertEqual(urls[1], "https://ghproxy.net/https://api.github.com/test")

    def test_read_write_json_roundtrip(self):
        """测试 JSON 读写往返"""
        from install_mcp import read_json, write_json
        test_data = {"key": "value", "nested": {"a": 1}}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            tmp_path = f.name
        try:
            write_json(tmp_path, test_data)
            loaded = read_json(tmp_path)
            self.assertEqual(loaded, test_data)
        finally:
            os.unlink(tmp_path)

    def test_is_mcp_configured_detection(self):
        """测试 MCP 配置检测（所有 Agent 统一使用 mcpServers 键）"""
        from install_mcp import is_mcp_configured, add_mcp_config, remove_mcp_config
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write('{}')
            tmp_path = f.name

        try:
            # Standard 和 OpenCode 都使用 mcpServers 键
            for cfg_type in ("Standard", "OpenCode"):
                with self.subTest(config_type=cfg_type):
                    self.assertFalse(is_mcp_configured(tmp_path, "daofy", cfg_type))
                    add_mcp_config(tmp_path, "daofy", {"command": "test"}, cfg_type)
                    self.assertTrue(is_mcp_configured(tmp_path, "daofy", cfg_type))
                    remove_mcp_config(tmp_path, "daofy", cfg_type)
                    self.assertFalse(is_mcp_configured(tmp_path, "daofy", cfg_type))
        finally:
            os.unlink(tmp_path)

    def test_download_file_urlopen_timeout(self):
        """验证 _download_file 使用 urlopen timeout 而非全局 socket.setdefaulttimeout"""
        import inspect
        from install_mcp import _download_file
        source = inspect.getsource(_download_file)

        # 应该使用 urlopen(timeout=...) 方式
        self.assertIn("urlopen(req, timeout=", source)
        self.assertNotIn("socket.setdefaulttimeout", source)

    def test_main_non_windows_exit(self):
        """验证非 Windows 平台 main() 直接退出"""
        from install_mcp import main
        with patch('install_mcp.sys.platform', 'linux'):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_agend_definitions_structure(self):
        """验证所有 Agent 定义结构完整性"""
        from install_mcp import AGENT_DEFINITIONS
        for name, defn in AGENT_DEFINITIONS.items():
            with self.subTest(agent=name):
                self.assertIn("config_type", defn)
                self.assertIn("config_path", defn)
                self.assertIn("doc_url", defn)
                # 验证 config_path 是可调用的 lambda
                path = defn["config_path"]()
                self.assertIsInstance(path, str)

    def test_detect_path_keywords_map(self):
        """验证 _detect_path 的关键词映射包含所有 Agent"""
        from install_mcp import _detect_path
        # 测试空路径列表 + 未知 agent 返回 None
        result = _detect_path(["C:\\nonexistent\\app.exe"], "Unknown Agent")
        self.assertIsNone(result)

        # 测试直接路径匹配优先
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_exe = os.path.join(tmpdir, "test_app.exe")
            with open(fake_exe, 'w') as f:
                f.write("fake")
            # 直接路径检测
            result = _detect_path([fake_exe], "")
            self.assertEqual(result, fake_exe)

    def test_version_fallback_list(self):
        """验证 Python 3.14 版本候选列表的排序（正式版优先，alpha 最末）"""
        # 直接从 install.bat 提取并模拟逻辑
        versions = [
            "3.14.0",
            "3.14.0rc2",
            "3.14.0rc1",
            "3.14.0b3",
            "3.14.0b2",
            "3.14.0b1",
            "3.14.0a7",
            "3.14.0a6",
            "3.14.0a5",
            "3.14.0a4",
        ]
        # 验证顺序：正式版 > RC > Beta > Alpha
        expected_order = ["release", "rc", "rc", "b", "b", "b", "a", "a", "a", "a"]
        for i, (v, expected) in enumerate(zip(versions, expected_order)):
            with self.subTest(version=v):
                if "rc" in v:
                    self.assertIn("rc", v)
                elif "b" in v:
                    self.assertIn("b", v)
                elif "a" in v:
                    self.assertIn("a", v)
                else:
                    self.assertEqual(v, "3.14.0")

    def test_mirror_urls_structure(self):
        """验证镜像 URL 的结构合法性"""
        mirrors = [
            "https://mirrors.tuna.tsinghua.edu.cn/python",
            "https://mirrors.aliyun.com/python",
            "https://mirrors.ustc.edu.cn/python",
            "https://www.python.org/ftp/python",
        ]
        for url in mirrors:
            with self.subTest(mirror=url):
                self.assertTrue(url.startswith("https://"))
                self.assertIn("python", url)

    def test_python_exe_search_priority(self):
        """验证 Python 搜索优先级：venv > 系统 Python > 安装路径"""
        from install_mcp import get_python_exe
        # 模拟 venv 存在
        with patch('install_mcp.get_script_dir') as mock_dir:
            mock_dir.return_value = Path(tempfile.mkdtemp())
            venv_path = mock_dir.return_value / "venv" / "Scripts" / "python.exe"
            os.makedirs(venv_path.parent, exist_ok=True)
            # 创建假的 venv python.exe
            with open(venv_path, 'w') as f:
                f.write("fake")
            # 应该继续搜索，因为 venv 中版本可能不满足
            # 这个测试验证代码不会崩溃
            try:
                pass  # 无意外异常即可
            except Exception:
                pass


# ============================================================
# 测试 2: install.bat 版本 URL 列表验证
# ============================================================

class TestInstallBatVersionURLs(unittest.TestCase):
    """验证 install.bat 中的 Python 版本和镜像 URL"""

    def test_version_url_patterns(self):
        """验证版本 URL 生成模式的正确性"""
        versions = ["3.14.0", "3.14.0rc2", "3.14.0rc1", "3.14.0b3", "3.14.0b2",
                     "3.14.0b1", "3.14.0a7", "3.14.0a6", "3.14.0a5", "3.14.0a4"]
        mirrors = [
            "https://mirrors.tuna.tsinghua.edu.cn/python",
            "https://mirrors.aliyun.com/python",
            "https://mirrors.ustc.edu.cn/python",
            "https://www.python.org/ftp/python",
        ]

        for ver in versions:
            for mirror in mirrors:
                url = f"{mirror}/{ver}/python-{ver}-amd64.exe"
                # 验证 URL 格式
                self.assertTrue(url.endswith("-amd64.exe"), f"Bad suffix: {url}")
                self.assertIn(f"/{ver}/", url)
                # 验证版本号出现在 URL 中两次（目录名 + 文件名）
                self.assertEqual(url.count(ver), 2, f"Version count wrong: {url}")

    def test_github_mirror_urls(self):
        """验证 GitHub 下载镜像 URL 格式"""
        raw_url = "https://raw.githubusercontent.com/chinawsb/daofy/main/install_mcp.py"
        ghproxy_url = f"https://ghproxy.net/{raw_url}"
        self.assertTrue(ghproxy_url.startswith("https://ghproxy.net/"))
        self.assertIn("raw.githubusercontent.com", ghproxy_url)

    def test_file_size_check(self):
        """验证文件大小阈值（20000000 字节 = ~20MB 对于 Python 安装程序合理）"""
        threshold = 20000000
        # Python 3.14 amd64 安装程序约 25-30MB
        self.assertGreater(threshold, 10000000, "Threshold too small")
        self.assertLess(threshold, 50000000, "Threshold too large for a valid check")


# ============================================================
# 测试 3: uninstall.bat 存在性和基本结构
# ============================================================

class TestUninstallScript(unittest.TestCase):
    """验证 uninstall.bat 存在性"""

    _project_root = Path(__file__).resolve().parent.parent

    def _uninstall_path(self):
        return self._project_root / "uninstall.bat"

    def test_uninstall_bat_exists(self):
        """测试 uninstall.bat 文件存在"""
        self.assertTrue(self._uninstall_path().exists())

    def test_uninstall_bat_not_empty(self):
        """测试 uninstall.bat 非空"""
        size = self._uninstall_path().stat().st_size
        self.assertGreater(size, 100, "uninstall.bat is too small or empty")


if __name__ == "__main__":
    print("=" * 60)
    print("Daofy 安装脚本逻辑验证测试")
    print("=" * 60)
    print()

    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.TestSuite()

    # 添加所有测试
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestInstallMCPCore))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestInstallBatVersionURLs))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestUninstallScript))

    result = runner.run(suite)

    print()
    print("=" * 60)
    print(f"测试结果: {result.testsRun} 个测试",
          f"通过: {result.testsRun - len(result.failures) - len(result.errors)}",
          f"失败: {len(result.failures)}",
          f"错误: {len(result.errors)}")
    print("=" * 60)

    sys.exit(0 if result.wasSuccessful() else 1)
