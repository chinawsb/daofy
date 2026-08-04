# -*- coding: utf-8 -*-
"""测试知识库构建/重建的三项修复：

1. 长驻服务缓存失效：服务启动时未安装编译器，delphi_versions 缓存为空，
   get_library_paths() 应重新检测注册表而非直接返回 []（避免 build 空跑成功）。
2. 孤立代理项清理：编码误判产生的 lone surrogate 在写入 zvec 前被清理，
   防止 "expected STRING, got str" 崩溃。
3. rebuild 删除旧库：Windows 下打开的集合句柄会让 rmtree 静默失败，
   rmtree 前必须先 col.close()。
"""

import contextlib
import io
import sys
import types
from pathlib import Path
from unittest import mock

from src.constants import REG_KEY_EMBARCADERO_BDS, REG_KEY_EMBARCADERO_STUDIO
from src.services.knowledge_base import delphi_chunker
from src.services.knowledge_base.delphi_chunker import _sanitize_unicode, chunk_delphi_file


# ──────────────────────────────────────────────────────────────
# Fix #1: 长驻服务缓存失效 → 重新检测 Delphi 版本
# ──────────────────────────────────────────────────────────────

class TestRediscoverDelphiVersions:
    """服务启动后新装编译器，get_library_paths 应重新检测版本"""

    def test_empty_cache_retriggers_detection(self, tmp_path):
        from src.services.knowledge_base.thirdparty_knowledge_base import (
            ThirdPartyKnowledgeBase,
        )

        kb = ThirdPartyKnowledgeBase(kb_dir=str(tmp_path / "kb"))
        kb.delphi_versions = []  # 模拟服务启动时尚未安装编译器

        calls = {"n": 0}

        def fake_detect():
            calls["n"] += 1
            kb.delphi_versions = []  # 仍未检测到
            return []

        with mock.patch.object(kb, "detect_delphi_versions", side_effect=fake_detect):
            paths = kb.get_library_paths()

        assert paths == []
        # 缓存为空时必须重新检测一次，而不是直接记住"无编译器"
        assert calls["n"] == 1

    def test_detection_finds_versions_after_install(self, tmp_path):
        from src.services.knowledge_base.thirdparty_knowledge_base import (
            ThirdPartyKnowledgeBase,
        )

        kb = ThirdPartyKnowledgeBase(kb_dir=str(tmp_path / "kb"))
        kb.delphi_versions = []  # 启动时无编译器

        def fake_detect():
            # 本次重新检测发现了新安装的 Delphi
            kb.delphi_versions = [{"version": "37.0", "name": "Delphi 37", "root_dir": "C:/Program Files/Embarcadero/Studio/23.0"}]
            return kb.delphi_versions

        # 注册表读取路径用 mock 兜底，聚焦"重新检测"行为
        with mock.patch.object(kb, "detect_delphi_versions", side_effect=fake_detect), \
                mock.patch.object(kb, "get_latest_version",
                                  side_effect=lambda: kb.delphi_versions[0]), \
                mock.patch.object(kb, "_load_environment_variables", return_value={}), \
                mock.patch.object(kb, "_read_library_paths", return_value=[]), \
                mock.patch.object(kb, "_is_delphi_system_path", return_value=False):
            paths = kb.get_library_paths()

        assert isinstance(paths, list)
        assert kb.delphi_versions  # 重新检测后缓存已更新


# ──────────────────────────────────────────────────────────────
# Fix #2: 孤立代理项清理
# ──────────────────────────────────────────────────────────────

class TestSanitizeUnicode:
    """lone surrogate 必须在进入 zvec 前被清理"""

    def test_direct_sanitize(self):
        text = "unit A;\n// \ud800 bad \udfff end"
        clean = _sanitize_unicode(text)
        # 结果不再包含代理项码点
        assert all(not (0xD800 <= ord(c) <= 0xDFFF) for c in clean)
        # 且可安全编码为 UTF-8
        clean.encode("utf-8")
        # 正常文本保持不变
        assert _sanitize_unicode("unit A;\nnormal text") == "unit A;\nnormal text"

    def test_chunk_delphi_file_sanitizes_surrogates(self):
        """即使读取路径引入了孤立代理项，chunk 输出也必须可安全编码"""
        raw = "unit BadEnc;\n\ninterface\n\nimplementation\nend.\n//\ud800 tail"

        fake_file = io.StringIO(raw)
        with mock.patch("builtins.open", return_value=fake_file), \
                mock.patch.object(delphi_chunker, "detect_encoding", return_value="utf-8"):
            chunks = chunk_delphi_file("dummy.pas")

        assert chunks
        for c in chunks:
            assert all(not (0xD800 <= ord(ch) <= 0xDFFF) for ch in c["chunk_text"])
            c["chunk_text"].encode("utf-8")


# ──────────────────────────────────────────────────────────────
# Fix #3: rebuild 前先关闭集合，再 rmtree
# ──────────────────────────────────────────────────────────────

class _FakeDoc:
    """真实的 Doc 占位：保存 id/fields，供断言检查插入内容。"""

    def __init__(self, id=None, fields=None):
        self.id = id
        self.fields = fields or {}


def _make_fake_zvec(fake_col):
    """构造一个最小可用的假 zvec 模块（避免依赖真实 zvec 安装）"""
    mod = types.ModuleType("zvec")
    mod.open = mock.Mock(return_value=fake_col)
    mod.create_and_open = mock.Mock(return_value=fake_col)
    mod.CollectionSchema = mock.Mock()
    mod.FieldSchema = mock.Mock()
    mod.FtsIndexParam = mock.Mock()
    mod.InvertIndexParam = mock.Mock()
    mod.DataType = mock.Mock(STRING="STRING", INT32="INT32")
    mod.Doc = _FakeDoc
    return mod


def _assert_close_before_rmtree(events, rmtree_patch, close_patch):
    """校验 close 调用先于 rmtree 调用"""
    close_patch.assert_called_once()
    close_index = events.index("close")
    rmtree_indexes = [i for i, e in enumerate(events) if e == "rmtree"]
    assert rmtree_indexes, "rebuild 必须调用 rmtree 删除旧库"
    assert close_index < rmtree_indexes[0], (
        "必须先 col.close() 释放句柄再 rmtree，否则 Windows 下删除静默失败"
    )


FAKE_CHUNK = {
    "entity_name": "TTest",
    "chunk_type": "class",
    "base_class": "TObject",
    "unit_name": "TestUnit",
    "uses_list": [],
    "chunk_text": "type TTest = class end;",
    "start_line": 1,
    "end_line": 2,
    "file_path": "dummy.pas",
}


class TestRebuildClosesCollection:
    """rebuild 删除旧库前必须先关闭打开的集合"""

    def test_thirdparty_rebuild_closes_before_rmtree(self, tmp_path):
        from src.services.knowledge_base.thirdparty_knowledge_base import (
            ThirdPartyKnowledgeBase,
        )

        kb_dir = tmp_path / "kb"
        kb_dir.mkdir()
        (kb_dir / "manifest.json").write_text("{}", encoding="utf-8")

        kb = ThirdPartyKnowledgeBase(kb_dir=str(kb_dir))
        fake_col = mock.Mock()
        events = []
        fake_col.close.side_effect = lambda: events.append("close")
        fake_zvec = _make_fake_zvec(fake_col)

        with mock.patch.dict(sys.modules, {"zvec": fake_zvec}), \
                mock.patch.object(kb, "get_library_paths",
                                  return_value=["C:/fake/libs"]), \
                mock.patch.object(kb, "_collect_thirdparty_files",
                                  return_value=["C:/fake/libs/x.pas"]), \
                mock.patch("src.services.knowledge_base.delphi_chunker.chunk_file_list",
                           return_value=[FAKE_CHUNK]), \
                mock.patch("shutil.rmtree",
                           side_effect=lambda *a, **k: events.append("rmtree")) as rm_mock:
            result = kb.build_thirdparty_knowledge_base(rebuild=True)

        assert result is True
        _assert_close_before_rmtree(events, rm_mock, fake_col.close)

    def test_rebuild_false_keeps_collection_untouched(self, tmp_path):
        """rebuild=False 且已有有效集合时，不得 close / rmtree / 重建"""
        from src.services.knowledge_base.thirdparty_knowledge_base import (
            ThirdPartyKnowledgeBase,
        )

        kb_dir = tmp_path / "kb"
        kb_dir.mkdir()
        (kb_dir / "manifest.json").write_text("{}", encoding="utf-8")

        kb = ThirdPartyKnowledgeBase(kb_dir=str(kb_dir))
        fake_col = mock.Mock()
        fake_zvec = _make_fake_zvec(fake_col)

        with mock.patch.dict(sys.modules, {"zvec": fake_zvec}), \
                mock.patch.object(kb, "get_library_paths",
                                  return_value=["C:/fake/libs"]), \
                mock.patch.object(kb, "_collect_thirdparty_files",
                                  return_value=["C:/fake/libs/x.pas"]), \
                mock.patch("src.services.knowledge_base.delphi_chunker.chunk_file_list",
                           return_value=[FAKE_CHUNK]), \
                mock.patch("shutil.rmtree") as rm_mock:
            result = kb.build_thirdparty_knowledge_base(rebuild=False)

        assert result is True
        # 增量路径：只 open 已有集合，不 close、不 rmtree、不重建
        fake_zvec.open.assert_called_once()
        fake_zvec.create_and_open.assert_not_called()
        fake_col.close.assert_not_called()
        rm_mock.assert_not_called()

    def test_project_rebuild_closes_before_rmtree(self, tmp_path):
        from src.services.knowledge_base.project_knowledge_base import (
            ProjectKnowledgeBase,
        )

        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / "TestProj.dpr").write_text(
            "program TestProj;\nbegin\nend.", encoding="utf-8"
        )
        kb_dir = project_dir / ".delphi-kb"
        kb_dir.mkdir()
        (kb_dir / "manifest.json").write_text("{}", encoding="utf-8")

        pkb = ProjectKnowledgeBase(str(project_dir / "TestProj.dpr"))
        fake_col = mock.Mock()
        events = []
        fake_col.close.side_effect = lambda: events.append("close")
        fake_zvec = _make_fake_zvec(fake_col)

        with mock.patch.dict(sys.modules, {"zvec": fake_zvec}), \
                mock.patch("src.services.knowledge_base.project_knowledge_base.chunk_file_list",
                           return_value=[FAKE_CHUNK]), \
                mock.patch("shutil.rmtree",
                           side_effect=lambda *a, **k: events.append("rmtree")) as rm_mock:
            result = pkb.build_project_knowledge_base(rebuild=True)

        assert result is True
        _assert_close_before_rmtree(events, rm_mock, fake_col.close)

    def test_zvec_adapter_rebuild_closes_before_rmtree(self, tmp_path):
        from src.services.knowledge_base.zvec_adapter import ZVecKnowledgeBaseAdapter

        kb_dir = tmp_path / "kb"
        kb_dir.mkdir()
        (kb_dir / "manifest.json").write_text("{}", encoding="utf-8")
        (tmp_path / "sample.pas").write_text(
            "unit Sample;\n\ninterface\n\nimplementation\nend.", encoding="utf-8"
        )

        fake_kb = mock.Mock()
        fake_kb.build.return_value = {
            "status": "ok", "files": 1, "classes": 1, "chunks": 1,
            "time_seconds": 0,
        }
        events = []
        fake_kb.close.side_effect = lambda: events.append("close")

        # build 内部会重新 `from .zvec_knowledge_base import ZVecKnowledgeBase`，
        # 需在源模块上 patch，使新旧实例都指向 fake_kb
        with mock.patch(
            "src.services.knowledge_base.zvec_knowledge_base.ZVecKnowledgeBase",
            return_value=fake_kb,
        ):
            adapter = ZVecKnowledgeBaseAdapter(str(kb_dir), source_dirs=[str(tmp_path)])
            assert adapter._zvec is fake_kb
            with mock.patch(
                "shutil.rmtree",
                side_effect=lambda *a, **k: events.append("rmtree"),
            ) as rm_mock:
                result = adapter.build_knowledge_base(rebuild=True)

        assert result is True
        _assert_close_before_rmtree(events, rm_mock, fake_kb.close)


# ──────────────────────────────────────────────────────────────
# 集成级验证（Fix #1）：服务启动后新装 Delphi 再 build thirdparty
# ──────────────────────────────────────────────────────────────

class _FakeWinKey:
    """模拟 winreg 键对象，按类型持有注册表数据。"""

    def __init__(self, kind, versions=None, version_key=None, env=None, lib_paths=None):
        self._kind = kind
        self._versions = versions or {}
        self._version_key = version_key
        self._env = env or {}
        self._lib_paths = lib_paths or []

    def EnumKey(self, i):
        if self._kind == "bds_root":
            keys = sorted(self._versions)
            if i >= len(keys):
                raise OSError(i)
            return keys[i]
        if self._kind == "library":
            platforms = ["Win32", "Win64"]
            if i >= len(platforms):
                raise OSError(i)
            return platforms[i]
        raise OSError(i)

    def EnumValue(self, i):
        names = list(self._env)
        if i >= len(names):
            raise OSError(i)
        name = names[i]
        return (name, self._env[name], 1)

    def QueryValueEx(self, name):
        if self._kind == "version" and name == "RootDir":
            return (self._versions[self._version_key]["root_dir"], 1)
        if self._kind == "platform" and name == "Browsing Path":
            return (";".join(self._lib_paths), 1)
        if self._kind == "platform" and name == "Search Path":
            return ("", 1)
        raise OSError(name)

    def CloseKey(self):
        return None

    def open_subkey(self, name):
        if self._kind == "bds_root":
            if name not in self._versions:
                raise OSError(name)
            return _FakeWinKey("version", versions=self._versions, version_key=name)
        if self._kind == "library":
            return _FakeWinKey("platform", lib_paths=self._lib_paths)
        raise OSError(name)


class _FakeRegistry:
    """模拟 winreg 注册表：状态可随时间变化（安装前 → 安装后）。"""

    def __init__(self):
        self._versions = {}

    def install_delphi(self, version_key, name, root_dir, lib_paths):
        """模拟新安装一个 Delphi 版本，Library 路径指向真实库目录。"""
        self._versions[version_key] = {
            "name": name,
            "root_dir": root_dir,
            "lib_paths": [str(p) for p in lib_paths],
            "env": {"BDS": root_dir},
        }

    # ── winreg API（供 mock side_effect 使用）──
    def OpenKey(self, hkey, sub, *args):
        if isinstance(hkey, _FakeWinKey):
            return hkey.open_subkey(sub)
        path = str(sub).replace("/", "\\")
        if path.lower() == REG_KEY_EMBARCADERO_BDS.lower():
            return _FakeWinKey("bds_root", versions=self._versions)
        for ver, data in self._versions.items():
            if path.lower() == (REG_KEY_EMBARCADERO_BDS + "\\" + ver + "\\Library").lower():
                return _FakeWinKey("library", lib_paths=data["lib_paths"])
            if path.lower() == (REG_KEY_EMBARCADERO_STUDIO + "\\" + ver + "\\Library").lower():
                return _FakeWinKey("library", lib_paths=data["lib_paths"])
            if path.lower() == (REG_KEY_EMBARCADERO_BDS + "\\" + ver + "\\Environment Variables").lower():
                return _FakeWinKey("env", env=data["env"])
        raise FileNotFoundError(path)

    def EnumKey(self, key, i):
        return key.EnumKey(i)

    def EnumValue(self, key, i):
        return key.EnumValue(i)

    def QueryValueEx(self, key, name):
        return key.QueryValueEx(name)

    def CloseKey(self, key):
        return key.CloseKey()


@contextlib.contextmanager
def _patched_winreg(registry):
    """把 winreg 模块函数替换为 _FakeRegistry 驱动，保留真实注册表读取代码路径。"""
    patches = [
        mock.patch("winreg.OpenKey", side_effect=registry.OpenKey),
        mock.patch("winreg.EnumKey", side_effect=registry.EnumKey),
        mock.patch("winreg.EnumValue", side_effect=registry.EnumValue),
        mock.patch("winreg.QueryValueEx", side_effect=registry.QueryValueEx),
        mock.patch("winreg.CloseKey", side_effect=registry.CloseKey),
    ]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()


class TestLongResidentServiceIntegration:
    """集成级：服务在安装编译器前启动，之后新装 Delphi 再 build thirdparty。"""

    def test_build_picks_up_newly_installed_delphi(self, tmp_path):
        from src.services.knowledge_base import thirdparty_knowledge_base as tkb
        from src.services.knowledge_base.thirdparty_knowledge_base import (
            ThirdPartyKnowledgeBase,
        )

        # 真实第三方库目录：安装后注册表 Library 路径指向它
        lib_dir = tmp_path / "libs"
        lib_dir.mkdir()
        (lib_dir / "MyLib.pas").write_text(
            "unit MyLib;\n\ninterface\n\ntype\n  TMyLib = class\n  private\n"
            "    FCount: Integer;\n  public\n    function GetCount: Integer;\n"
            "  end;\n\nimplementation\n\nfunction TMyLib.GetCount: Integer;\n"
            "begin\n  Result := FCount;\nend;\n\nend.\n",
            encoding="utf-8",
        )

        registry = _FakeRegistry()

        # ① 服务启动：注册表无任何 Delphi → 版本缓存为空
        with _patched_winreg(registry):
            kb = ThirdPartyKnowledgeBase(kb_dir=str(tmp_path / "kb"))
        assert kb.delphi_versions == []

        # ② 新装 Delphi：注册表新增版本 + Library 路径指向真实库目录
        registry.install_delphi(
            "37.0", "Delphi 37", str(tmp_path / "Studio" / "23.0"), [str(lib_dir)]
        )

        # ③ 长驻服务直接 build thirdparty：应重新检测注册表并真正入库
        fake_col = mock.Mock()
        fake_zvec = _make_fake_zvec(fake_col)

        def fake_create_and_open(path, schema=None):
            # 模拟真实 zvec：重建集合时会创建 KB 目录
            Path(path).mkdir(parents=True, exist_ok=True)
            return fake_col

        fake_zvec.create_and_open.side_effect = fake_create_and_open
        with _patched_winreg(registry), \
                mock.patch.dict(sys.modules, {"zvec": fake_zvec}), \
                mock.patch.object(tkb, "get_catalog_repository_paths", return_value=[]), \
                mock.patch.object(tkb, "expand_delphi_path_macros",
                                  side_effect=lambda p, version=None: p):
            result = kb.build_thirdparty_knowledge_base(rebuild=True)

        assert result is True
        # 全链路真实执行：重新检测 → 扫描真实目录 → 切块 → 入库。
        # （修复前：get_library_paths 返回 []，build 空跑成功，不会走到入库。）
        assert kb.delphi_versions, "build 后版本缓存应更新为新安装的 Delphi"
        fake_zvec.create_and_open.assert_called_once()
        fake_col.insert.assert_called_once()
        inserted = fake_col.insert.call_args.args[0]
        assert inserted, "必须真正插入切块文档（空跑成功即修复前 bug）"
        assert any("TMyLib" in d.fields["chunk_text"] for d in inserted)
        # 再次取路径：新安装的库目录已被识别并持久化
        with _patched_winreg(registry), \
                mock.patch.object(tkb, "get_catalog_repository_paths", return_value=[]), \
                mock.patch.object(tkb, "expand_delphi_path_macros",
                                  side_effect=lambda p, version=None: p):
            paths = kb.get_library_paths()
        assert str(lib_dir.resolve()) in paths
