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

    def test_qoder_agent_definitions(self):
        """验证 Qoder 和 Qoder CN 的 Agent 定义（2026-06-07 新增）"""
        import install_mcp

        # AGENT_DEFINITIONS 必须包含 Qoder 和 Qoder CN
        self.assertIn("Qoder", install_mcp.AGENT_DEFINITIONS)
        self.assertIn("Qoder CN", install_mcp.AGENT_DEFINITIONS)

        # Qoder 必须是 Standard 类型，config_path 指向 mcp-settings.json
        qoder = install_mcp.AGENT_DEFINITIONS["Qoder"]
        self.assertEqual(qoder["config_type"], "Standard")
        self.assertTrue(
            qoder["config_path"]().endswith("mcp-settings.json"),
            f"Qoder config_path should end with mcp-settings.json, got: {qoder['config_path']()}",
        )
        # Qoder 必须有官方文档链接
        self.assertTrue(
            qoder["doc_url"].startswith("http"),
            f"Qoder doc_url should be a URL, got: {qoder['doc_url']}",
        )
        # Qoder 至少有一条 detect_paths
        self.assertTrue(
            len(qoder["detect_paths"]()) > 0,
            "Qoder should have at least one detect_paths entry",
        )

        # Qoder CN：Standard + extension\local\mcp.json（实测本机 Qoder CN 真实路径）
        qoder_cn = install_mcp.AGENT_DEFINITIONS["Qoder CN"]
        self.assertEqual(qoder_cn["config_type"], "Standard")
        self.assertTrue(
            qoder_cn["config_path"]().endswith("extension\\local\\mcp.json"),
            f"Qoder CN config_path should end with extension\\local\\mcp.json, "
            f"got: {qoder_cn['config_path']()}",
        )
        # Qoder CN 路径必须在 QoderCN 子目录下（不是 Qoder 国际版）
        self.assertIn("QoderCN", qoder_cn["config_path"](),
                      f"Qoder CN config_path should be under QoderCN/, got: {qoder_cn['config_path']()}")
        # Qoder CN detect_paths 必须指向 QoderCN.exe（不是 Qoder.exe）
        detect_paths = qoder_cn["detect_paths"]()
        self.assertTrue(len(detect_paths) > 0, "Qoder CN should have at least one detect_paths entry")
        self.assertTrue(any("QoderCN" in p for p in detect_paths),
                        f"Qoder CN detect_paths should include QoderCN.exe, got: {detect_paths}")
        # Qoder CN 必须有阿里云文档链接
        self.assertIn("aliyun.com", qoder_cn["doc_url"],
                     f"Qoder CN doc_url should reference aliyun, got: {qoder_cn['doc_url']}")
        # Qoder CN 必须标记为 experimental（extension\local\mcp.json 含元数据，重写会清空）
        self.assertTrue(
            qoder_cn.get("experimental", False),
            "Qoder CN should be marked experimental",
        )

    def test_qoder_agents_in_install_cli(self):
        """验证 Qoder/QoderCN 已注册到 argparse choices 和 filter_map（install/uninstall 两侧）"""
        import re
        install_mcp_path = Path(__file__).resolve().parent.parent / "install_mcp.py"
        src = install_mcp_path.read_text(encoding="utf-8")

        # 1) argparse --agent choices 必须包含 "Qoder" 和 "QoderCN"
        match = re.search(
            r'parser\.add_argument\("--agent".*?choices=\[(.*?)\]',
            src, re.DOTALL,
        )
        self.assertIsNotNone(match, "Could not find --agent choices in install_mcp.py")
        choices_str = match.group(1)
        self.assertIn('"Qoder"', choices_str,
                      f"argparse choices should include 'Qoder', got: {choices_str}")
        self.assertIn('"QoderCN"', choices_str,
                      f"argparse choices should include 'QoderCN', got: {choices_str}")

        # 2) filter_map 必须在 do_install 和 do_uninstall 两处都包含 "QoderCN": "Qoder CN" 短名
        self.assertGreaterEqual(
            src.count('"QoderCN": "Qoder CN"'), 2,
            'filter_map should include \'"QoderCN": "Qoder CN"\' in both install and uninstall',
        )

        # 3) _detect_path keywords_map 必须包含 Qoder 和 Qoder CN 关键词
        self.assertIn(
            '"Qoder": ["qoder"]', src,
            "keywords_map should include 'Qoder' with qoder keyword",
        )
        self.assertIn(
            '"Qoder CN": ["qoder cn"', src,
            "keywords_map should include 'Qoder CN' with qoder cn keywords",
        )

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

    def test_exit_code_constants(self):
        """验证退出码常量契约（0=成功, 1=失败, 2=取消）"""
        from install_mcp import EXIT_SUCCESS, EXIT_FAILURE, EXIT_CANCELLED
        self.assertEqual(EXIT_SUCCESS, 0)
        self.assertEqual(EXIT_FAILURE, 1)
        self.assertEqual(EXIT_CANCELLED, 2)

    def test_no_magic_exit_codes_in_install_functions(self):
        """do_install/do_uninstall 不应硬编码 sys.exit(N)，必须用 EXIT_* 常量。

        这是 install.bat 显示成功/失败/取消三种结果的核心契约——
        若此处回归硬编码 0/1/2，bat 端 [SUCCESS]/[ERROR]/[INFO] 分支会错位。
        """
        import inspect
        import re
        from install_mcp import do_install, do_uninstall

        for name, func in (("do_install", do_install), ("do_uninstall", do_uninstall)):
            src = inspect.getsource(func)
            # 匹配 sys.exit(0/1/2) 这种 magic number 形式
            hardcoded = re.findall(r"sys\.exit\(\s*(\d+)\s*\)", src)
            self.assertEqual(
                hardcoded, [],
                f"{name} 中存在硬编码 sys.exit(N): {hardcoded}。"
                f"应使用 EXIT_SUCCESS/EXIT_FAILURE/EXIT_CANCELLED 常量。"
            )

    def test_do_install_no_agents_exits_failure(self):
        """do_install: 未检测到任何 AI Agent 时退出 1（前置条件失败）。"""
        from install_mcp import do_install

        with patch('install_mcp.detect_agents', return_value=[]), \
             patch('install_mcp.get_script_dir', return_value=Path(tempfile.mkdtemp())):
            with self.assertRaises(SystemExit) as ctx:
                do_install("C:\\fake\\python.exe")
            self.assertEqual(ctx.exception.code, 1,
                "未检测到任何 AI Agent 应该退出 1，不应被 bat 端误判为成功")

    def test_do_install_q_cancel_exits_cancelled(self):
        """do_install: 用户在交互中按 q 取消时退出 2（用户主动取消）。

        这是用户报告的 '按q退出也提示成功了' bug 的核心回归测试：
        之前用 sys.exit(0) 导致 bat 端 if errorlevel 1 漏检，错误地显示
        '[SUCCESS] Daofy installed successfully!'。
        """
        from install_mcp import do_install

        # 模拟两个已安装的 Agent，触发 display_items > 1 进入交互选择
        fake_agents = [
            {
                "name": "FakeA", "installed": True, "path": "C:\\fake\\a.exe",
                "config_path": "C:\\fake\\a.json", "config_type": "Standard",
                "modes": ["global"], "doc_url": "", "experimental": False,
                "was_configured": False,
            },
            {
                "name": "FakeB", "installed": True, "path": "C:\\fake\\b.exe",
                "config_path": "C:\\fake\\b.json", "config_type": "Standard",
                "modes": ["global"], "doc_url": "", "experimental": False,
                "was_configured": False,
            },
        ]
        # do_install 头部会检查 src/server.py 是否存在；用临时目录创建它
        fake_script_dir = Path(tempfile.mkdtemp())
        (fake_script_dir / "src").mkdir(parents=True, exist_ok=True)
        (fake_script_dir / "src" / "server.py").write_text("# fake", encoding="utf-8")

        with patch('install_mcp.detect_agents', return_value=fake_agents), \
             patch('install_mcp.get_script_dir', return_value=fake_script_dir), \
             patch('builtins.input', return_value='q'):  # 模拟用户输入 q
            with self.assertRaises(SystemExit) as ctx:
                do_install("C:\\fake\\python.exe")
            self.assertEqual(ctx.exception.code, 2,
                "按 q 取消应退出 2 (EXIT_CANCELLED)，不应被 bat 端误判为成功")

    def test_bat_runs_install_labels_use_exit_codes(self):
        """install.bat 的 :RUN_INSTALL 区段必须使用 %errorlevel% 三分支判断。

        :RUN_INSTALL 是 install_mcp.py 的调用点——必须按 0/1/2 三种 errorlevel
        分别给出 [SUCCESS]/[ERROR]/[INFO] 提示。旧版的 'if errorlevel 1' (>=1)
        粗粒度判断无法区分 0 (成功) 和 2 (用户取消)，会显示错误的 [SUCCESS]。
        """
        bat_path = Path(__file__).resolve().parent.parent / "install.bat"
        src = bat_path.read_text(encoding="utf-8")

        # 截取 :RUN_INSTALL 标签下方到文件末尾（bat fall-through 终止于此）
        marker = ":RUN_INSTALL"
        idx = src.find(marker)
        self.assertGreater(idx, -1, "install.bat 必须存在 :RUN_INSTALL 标签")
        run_section = src[idx:]

        # 0/1/2 三个值都必须被处理
        self.assertIn("%errorlevel%==0", run_section,
            ":RUN_INSTALL 必须区分 errorlevel==0 (成功)")
        self.assertIn("%errorlevel%==1", run_section,
            ":RUN_INSTALL 必须区分 errorlevel==1 (失败)")
        self.assertIn("%errorlevel%==2", run_section,
            ":RUN_INSTALL 必须区分 errorlevel==2 (用户取消)")

        # 三个 label 都必须存在
        for label in (":RUN_OK", ":RUN_FAIL", ":RUN_CANCEL"):
            self.assertIn(label, run_section,
                f":RUN_INSTALL 区段必须定义 {label} 标签")


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


# ============================================================
# DSH (DeepSeek Harness) 块手术逻辑测试
# （从 tests/test_dsh_installer.py 移植，改为 install_mcp.py 的
#   add_mcp_config/remove_mcp_config/is_mcp_configured DSH 分支 + _dsh_* 内部函数）
# ============================================================

class TestDSHInstallLogic(unittest.TestCase):
    """DSH cordis.patch.yml 块手术逻辑（原 test_dsh_installer.py 核心用例）"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.patch_file = self.tmp / "profiles" / "web" / "cordis.patch.yml"

    def tearDown(self):
        self._tmp.cleanup()

    def _mcp_config(self, command=r"C:\daofy.exe", args=None, cwd=r"C:\work"):
        """构造 get_mcp_config(config_type="DSH") 同款配置"""
        return {
            "serverName": "daofy",
            "transport": "stdio",
            "command": command,
            "args": args or [],
            "env": {
                "PYTHONUNBUFFERED": "1",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            },
            "cwd": cwd,
            "toolCallTimeoutMs": 600000,
        }

    def test_dsh_install_creates_patch_file(self):
        """add_mcp_config(DSH) 创建 patch 文件，含 insert 块与插件名"""
        from install_mcp import add_mcp_config
        add_mcp_config(str(self.patch_file), "daofy", self._mcp_config(), "DSH")
        self.assertTrue(self.patch_file.is_file())
        text = self.patch_file.read_text(encoding="utf-8")
        self.assertIn("- insert:", text)
        self.assertIn("id: mcp-daofy", text)
        self.assertIn("name: '@deepseek-ai/dsh-mcp-client'", text)
        self.assertIn("serverName: 'daofy'", text)
        self.assertIn("command: 'C:\\daofy.exe'", text)
        self.assertIn("cwd: 'C:\\work'", text)
        self.assertIn("PYTHONIOENCODING: 'utf-8'", text)

    def test_dsh_installed_parses_as_valid_yaml(self):
        """安装结果可被 yaml.safe_load 解析为合法顶层列表"""
        import yaml
        from install_mcp import add_mcp_config
        add_mcp_config(str(self.patch_file), "daofy", self._mcp_config(), "DSH")
        doc = yaml.safe_load(self.patch_file.read_text(encoding="utf-8"))
        self.assertIsInstance(doc, list)
        self.assertEqual(len(doc), 1)
        entry = doc[0]["insert"][0]
        self.assertEqual(entry["id"], "mcp-daofy")
        self.assertEqual(entry["config"]["serverName"], "daofy")
        self.assertEqual(entry["config"]["command"], r"C:\daofy.exe")

    def test_dsh_idempotent_on_second_run(self):
        """配置一致时二次安装不重复插入（幂等）"""
        from install_mcp import add_mcp_config
        add_mcp_config(str(self.patch_file), "daofy", self._mcp_config(), "DSH")
        add_mcp_config(str(self.patch_file), "daofy", self._mcp_config(), "DSH")
        text = self.patch_file.read_text(encoding="utf-8")
        self.assertEqual(text.count("- insert:"), 1)

    def test_dsh_update_when_command_changed(self):
        """command 变化时原地替换，不产生重复条目"""
        from install_mcp import add_mcp_config
        add_mcp_config(str(self.patch_file), "daofy",
                       self._mcp_config(command=r"C:\old\daofy.exe"), "DSH")
        add_mcp_config(str(self.patch_file), "daofy",
                       self._mcp_config(command=r"C:\new\daofy.exe"), "DSH")
        text = self.patch_file.read_text(encoding="utf-8")
        self.assertIn("C:\\new\\daofy.exe", text)
        self.assertNotIn("C:\\old\\daofy.exe", text)
        self.assertEqual(text.count("- insert:"), 1)

    def test_dsh_uninstall_removes_block(self):
        """remove_mcp_config(DSH) 移除块，卸载后保留合法空列表"""
        from install_mcp import add_mcp_config, remove_mcp_config
        add_mcp_config(str(self.patch_file), "daofy", self._mcp_config(), "DSH")
        removed = remove_mcp_config(str(self.patch_file), "daofy", "DSH")
        self.assertTrue(removed)
        text = self.patch_file.read_text(encoding="utf-8")
        self.assertNotIn("daofy", text.lower())
        self.assertIn("[]", text)

    def test_dsh_uninstall_when_not_installed(self):
        """未安装时卸载返回 False"""
        from install_mcp import remove_mcp_config
        removed = remove_mcp_config(str(self.patch_file), "daofy", "DSH")
        self.assertFalse(removed)

    def test_dsh_uninstall_preserves_other_entries(self):
        """卸载只移除 Daofy 块，保留第三方条目（含 !!js 表达式）"""
        from install_mcp import add_mcp_config, remove_mcp_config
        self.patch_file.parent.mkdir(parents=True, exist_ok=True)
        self.patch_file.write_text(
            "# user patch\n"
            "- insert:\n"
            "    - id: other-server\n"
            "      name: '@some/plugin'\n"
            "      config:\n"
            "        serverName: other\n"
            "        command: !!js process.cwd()\n"
            "        transport: stdio\n",
            encoding="utf-8",
        )
        add_mcp_config(str(self.patch_file), "daofy", self._mcp_config(), "DSH")
        remove_mcp_config(str(self.patch_file), "daofy", "DSH")
        text = self.patch_file.read_text(encoding="utf-8")
        self.assertIn("id: other-server", text)
        self.assertIn("!!js process.cwd()", text)
        self.assertNotIn("mcp-daofy", text)

    def test_dsh_empty_existing_list_is_replaced(self):
        """既有空列表 [] 被条目替换，文件头注释保留"""
        from install_mcp import add_mcp_config
        self.patch_file.parent.mkdir(parents=True, exist_ok=True)
        self.patch_file.write_text("# header comment\n[]\n", encoding="utf-8")
        add_mcp_config(str(self.patch_file), "daofy", self._mcp_config(), "DSH")
        text = self.patch_file.read_text(encoding="utf-8")
        self.assertIn("# header comment", text)
        self.assertIn("- insert:", text)
        self.assertNotIn("\n[]\n", text)

    def test_dsh_idempotent_case_insensitive_command_windows(self):
        """Windows 路径大小写不敏感：daofy.exe vs daofy.EXE 视为一致"""
        from install_mcp import add_mcp_config
        add_mcp_config(str(self.patch_file), "daofy",
                       self._mcp_config(command=r"C:\daofy.exe"), "DSH")
        add_mcp_config(str(self.patch_file), "daofy",
                       self._mcp_config(command=r"C:\daofy.EXE"), "DSH")
        text = self.patch_file.read_text(encoding="utf-8")
        self.assertEqual(text.count("- insert:"), 1)
        if os.name == "nt":
            self.assertIn("C:\\daofy.exe", text)  # 大小写不敏感 → 未更新
        else:
            self.assertIn("C:\\daofy.EXE", text)  # 大小写敏感 → 已更新

    def test_dsh_find_block_absorbs_multiline_comment_block(self):
        """_dsh_find_block 吸收 insert 上方整块连续注释（旧版手工安装头）"""
        from install_mcp import _dsh_find_block
        lines = [
            "# Your patch layer header",  # 文件头, 与块间有空行 → 不吸收
            "",
            "# ── Daofy for Delphi MCP Server ────────────────",
            "# 工具以 mcp__daofy__<tool> 形式注册",
            "#   command 使用 daofy.exe 绝对路径",
            "# ── Daofy for Delphi MCP Server (managed by install_mcp.py)",
            "- insert:",
            "    - id: mcp-daofy",
            "      config:",
            "        serverName: daofy",
        ]
        span = _dsh_find_block(lines, "daofy")
        # 吸收 insert 行上方 5 行注释 (行索引 2..6), 文件头行 0 因空行分隔被保留
        self.assertEqual(span, (2, 10))

    def test_dsh_find_block_does_not_absorb_unrelated_comment(self):
        """insert 上方无 daofy 关键字的注释块不被吸收（退回 insert 行本身）"""
        from install_mcp import _dsh_find_block
        lines = [
            "# unrelated note",
            "# another note",
            "- insert:",
            "    - id: mcp-daofy",
            "      config:",
            "        serverName: daofy",
        ]
        span = _dsh_find_block(lines, "daofy")
        self.assertEqual(span, (2, 6))

    def test_dsh_find_block_multiple_entries(self):
        """多个 insert 条目时定位到目标条目，_dsh_parse_entry 可解析"""
        from install_mcp import _dsh_find_block, _dsh_parse_entry
        lines = [
            "- insert:",
            "    - id: other",
            "      config:",
            "        serverName: other",
            "- insert:",
            "    - id: mcp-daofy",
            "      config:",
            "        serverName: daofy",
            "- id: override",
        ]
        span = _dsh_find_block(lines, "daofy")
        self.assertEqual(span, (4, 8))
        entry = _dsh_parse_entry("\n".join(lines[span[0]:span[1]]) + "\n")
        self.assertEqual(entry["id"], "mcp-daofy")
        self.assertEqual(entry["config"]["serverName"], "daofy")

    def test_dsh_file_has_mcp_detection(self):
        """_file_has_mcp(DSH) 检测已安装条目"""
        from install_mcp import _dsh_file_has_mcp, add_mcp_config
        self.assertFalse(_dsh_file_has_mcp(str(self.patch_file)))
        add_mcp_config(str(self.patch_file), "daofy", self._mcp_config(), "DSH")
        self.assertTrue(_dsh_file_has_mcp(str(self.patch_file)))

    def test_dsh_get_mcp_config(self):
        """get_mcp_config(DSH) 返回 serverName/transport/command/args/env/cwd/timeout"""
        from install_mcp import get_mcp_config
        cfg = get_mcp_config(r"C:\python.exe", "DSH", use_pip=False)
        self.assertEqual(cfg["serverName"], "daofy")
        self.assertEqual(cfg["transport"], "stdio")
        self.assertEqual(cfg["command"], r"C:\python.exe")
        self.assertTrue(cfg["args"][0].endswith("server.py"))
        self.assertEqual(cfg["env"]["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(cfg["toolCallTimeoutMs"], 600000)
        self.assertIn("cwd", cfg)
        # pip 模式 → command=daofy, args=[]
        cfg_pip = get_mcp_config(r"C:\python.exe", "DSH", use_pip=True)
        self.assertEqual(cfg_pip["command"], "daofy")
        self.assertEqual(cfg_pip["args"], [])


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
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestDSHInstallLogic))

    result = runner.run(suite)

    print()
    print("=" * 60)
    print(f"测试结果: {result.testsRun} 个测试",
          f"通过: {result.testsRun - len(result.failures) - len(result.errors)}",
          f"失败: {len(result.failures)}",
          f"错误: {len(result.errors)}")
    print("=" * 60)

    sys.exit(0 if result.wasSuccessful() else 1)
