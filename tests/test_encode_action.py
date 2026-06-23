# -*- coding: utf-8 -*-
"""
测试 delphi_file(action="encode") — 文件编码转换

覆盖场景:
  - utf-8 → utf-8-sig (添加 BOM)
  - utf-8-sig → utf-8 (去除 BOM)
  - utf-8 → gbk (编码转换)
  - gbk → utf-8 (反向转换)
  - utf-8 → utf-16 (跨编码族)
  - 预览模式 (preview=true)
  - 不存在的文件
  - 不支持的文件类型
  - 无效的目标编码
  - from_encoding 显式指定
"""

import os
import tempfile
import sys
import pytest

# 添加项目根到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tools.file_tool import handle_encode


def _make_temp_pas(content: str, encoding: str = "utf-8") -> str:
    """创建临时 .pas 文件，返回路径"""
    fd, path = tempfile.mkstemp(suffix=".pas")
    os.close(fd)
    with open(path, "w", encoding=encoding) as f:
        f.write(content)
    return path


def _read_file(path: str) -> tuple[str, str]:
    """读取文件内容并返回 (content, encoding)"""
    from src.utils.file_backup import detect_encoding
    enc = detect_encoding(path)
    with open(path, "r", encoding=enc) as f:
        return f.read(), enc


def _read_raw(path: str) -> bytes:
    """读取文件原始字节"""
    with open(path, "rb") as f:
        return f.read()


class TestEncodeAction:
    """Test suite for delphi_file(action='encode')"""

    def test_utf8_to_utf8_sig(self):
        """UTF-8 → UTF-8 with BOM"""
        content = "unit TestUnit;\ninterface\nimplementation\nend.\n"
        path = _make_temp_pas(content, "utf-8")
        try:
            result = await_result(handle_encode({
                "file_path": path,
                "to_encoding": "utf-8-sig",
                "backup": False,
            }))
            assert result["status"] == "success"
            assert "utf-8-sig" in result["message"].lower() or "utf-8-sig" == result["new_encoding"]
            # BOM 检测：utf-8-sig 编码读取时会自动剥离 BOM，检查原始字节
            raw = _read_raw(path)
            assert raw.startswith(b"\xef\xbb\xbf"), f"Expected BOM bytes, got: {raw[:10]}"
            # 编码检测应返回 utf-8-sig
            _, enc = _read_file(path)
            assert enc == "utf-8-sig"
        finally:
            _cleanup(path)

    def test_utf8_sig_to_utf8(self):
        """UTF-8 with BOM → UTF-8 without BOM"""
        content = "unit TestUnit;\ninterface\nimplementation\nend.\n"
        path = _make_temp_pas("\ufeff" + content, "utf-8-sig")
        try:
            result = await_result(handle_encode({
                "file_path": path,
                "to_encoding": "utf-8",
                "backup": False,
            }))
            assert result["status"] == "success"
            read_content, enc = _read_file(path)
            assert enc == "utf-8"
            assert not read_content.startswith("\ufeff")  # BOM removed
            assert read_content.strip() == content.strip()
        finally:
            _cleanup(path)

    def test_utf8_to_gbk(self):
        """UTF-8 with Chinese → GBK"""
        content = "unit TestUnit;\n// 中文注释\nimplementation\nend.\n"
        path = _make_temp_pas(content, "utf-8")
        try:
            result = await_result(handle_encode({
                "file_path": path,
                "to_encoding": "gbk",
                "backup": False,
            }))
            assert result["status"] == "success"
            assert result["new_encoding"].lower() == "gbk" or "gbk" in result["new_encoding"].lower()
            read_content, enc = _read_file(path)
            assert "gbk" in enc.lower()
            assert "中文" in read_content
        finally:
            _cleanup(path)

    def test_gbk_to_utf8(self):
        """GBK → UTF-8"""
        content = "unit TestUnit;\n// 中文注释\nimplementation\nend.\n"
        path = _make_temp_pas(content, "gbk")
        try:
            result = await_result(handle_encode({
                "file_path": path,
                "to_encoding": "utf-8",
                "backup": False,
            }))
            assert result["status"] == "success"
            assert result["new_encoding"] == "utf-8" or "utf-8" in result["new_encoding"]
            read_content, enc = _read_file(path)
            assert enc == "utf-8"
            assert "中文" in read_content
        finally:
            _cleanup(path)

    def test_utf8_to_utf16(self):
        """UTF-8 → UTF-16"""
        content = "unit TestUnit;\ninterface\nimplementation\nend.\n"
        path = _make_temp_pas(content, "utf-8")
        try:
            result = await_result(handle_encode({
                "file_path": path,
                "to_encoding": "utf-16",
                "backup": False,
            }))
            assert result["status"] == "success"
            read_content, enc = _read_file(path)
            assert "utf-16" in enc.lower()
            assert read_content.strip() == content.strip()
        finally:
            _cleanup(path)

    def test_preview_mode(self):
        """预览模式不应修改文件"""
        content = "unit TestUnit;\ninterface\nimplementation\nend.\n"
        path = _make_temp_pas(content, "utf-8")
        try:
            result = await_result(handle_encode({
                "file_path": path,
                "to_encoding": "gbk",
                "preview": True,
                "backup": False,
            }))
            assert result["status"] == "success"
            assert "preview" in result["message"].lower()
            # 文件内容不应改变
            read_content, enc = _read_file(path)
            assert enc == "utf-8"
            assert read_content.strip() == content.strip()
        finally:
            _cleanup(path)

    def test_file_not_found(self):
        """不存在的文件应返回错误"""
        result = await_result(handle_encode({
            "file_path": "/nonexistent/file.pas",
            "to_encoding": "utf-8",
        }))
        assert result["status"] == "failed"

    def test_unsupported_extension(self):
        """不支持的文件类型应返回错误"""
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            result = await_result(handle_encode({
                "file_path": path,
                "to_encoding": "utf-8",
            }))
            assert result["status"] == "failed"
            assert "不支持" in result["message"]
        finally:
            os.unlink(path)

    def test_invalid_target_encoding(self):
        """无效的目标编码应返回错误"""
        content = "unit Test;\nbegin\nend.\n"
        path = _make_temp_pas(content, "utf-8")
        try:
            result = await_result(handle_encode({
                "file_path": path,
                "to_encoding": "invalid-encoding-xyz",
                "backup": False,
            }))
            assert result["status"] == "failed"
            assert "不可识别" in result["message"]
        finally:
            _cleanup(path)

    def test_from_encoding_explicit(self):
        """显式指定 from_encoding"""
        content = "unit Test;\nbegin\nend.\n"
        path = _make_temp_pas(content, "utf-8")
        try:
            result = await_result(handle_encode({
                "file_path": path,
                "from_encoding": "utf-8",
                "to_encoding": "utf-16-le",
                "backup": False,
            }))
            assert result["status"] == "success"
            read_content, enc = _read_file(path)
            assert "utf-16" in enc.lower()
        finally:
            _cleanup(path)

    def test_file_size_in_result(self):
        """返回结果应包含文件大小信息"""
        content = "unit Test;\nbegin\nend.\n"
        path = _make_temp_pas(content, "utf-8")
        try:
            result = await_result(handle_encode({
                "file_path": path,
                "to_encoding": "utf-16",
                "backup": False,
            }))
            assert result["status"] == "success"
            assert result.get("original_size") is not None
            assert result.get("new_size") is not None
        finally:
            _cleanup(path)

    def test_backup_created(self):
        """转换时自动创建备份"""
        content = "unit Test;\nbegin\nend.\n"
        path = _make_temp_pas(content, "utf-8")
        try:
            result = await_result(handle_encode({
                "file_path": path,
                "to_encoding": "utf-8-sig",
                "backup": True,
            }))
            assert result["status"] == "success"
            assert "backup" in result["message"].lower() or result["message"].count("backup") > 0
        finally:
            _cleanup(path)
            # 清理 __history
            history_dir = os.path.join(os.path.dirname(path), "__history")
            if os.path.isdir(history_dir):
                import shutil
                shutil.rmtree(history_dir, ignore_errors=True)


def await_result(coro):
    """Helper: run async function synchronously for tests"""
    import asyncio
    return asyncio.run(coro)


def _cleanup(path: str):
    """Clean up temp file"""
    try:
        if os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════
# chardet 编码检测测试
# ═══════════════════════════════════════════════════════════

class TestChardetEncodingDetection:
    """Test detect_encoding() with chardet for various CJK encodings"""

    def _make_pas_file(self, content: str, encoding: str = "utf-8") -> str:
        """Create a .pas file with given content and encoding"""
        fd, path = tempfile.mkstemp(suffix=".pas")
        os.close(fd)
        with open(path, "w", encoding=encoding) as f:
            f.write(content)
        return path

    def _make_pas_file_raw(self, content: bytes) -> str:
        """Create a .pas file with raw bytes (for non-UTF-8 encodings)"""
        fd, path = tempfile.mkstemp(suffix=".pas")
        os.close(fd)
        with open(path, "wb") as f:
            f.write(content)
        return path

    # ── 1. GBK Chinese ──
    def test_detect_gbk(self):
        """detect_encoding 应识别 GBK 编码的中文"""
        content = "unit TestUnit;\n// 中文测试注释\nimplementation\nend."
        path = self._make_pas_file(content, "gbk")
        try:
            from src.utils.file_backup import detect_encoding
            enc = detect_encoding(path)
            assert enc.lower() in ("gbk", "gb18030"), f"Expected gbk, got {enc}"
        finally:
            _cleanup(path)

    def test_detect_gbk_pascal_raw(self):
        """detect_encoding 应识别完整 GBK 文件（原始字节写入）"""
        import codecs
        content = "unit TestUnit;\n// 数据库连接配置\nimplementation\nend."
        raw_bytes = content.encode("gbk")
        path = self._make_pas_file_raw(raw_bytes)
        try:
            from src.utils.file_backup import detect_encoding
            enc = detect_encoding(path)
            assert enc.lower() in ("gbk", "gb18030"), f"Expected gbk, got {enc}"
        finally:
            _cleanup(path)

    # ── 2. Big5 Traditional Chinese ──
    def test_detect_big5(self):
        """detect_encoding 应识别 Big5 编码的繁体中文"""
        import codecs
        content = (
            "unit TestUnit;\n"
            "// 繁體中文測試 - 專案管理系統 - 資料庫連接設定\n"
            "// 客戶資料維護 - 訂單處理模組 - 報表產生器\n"
            "// 使用者權限管理 - 系統參數設定 - 稽核追蹤\n"
            "implementation\n"
            "end."
        )
        raw_bytes = content.encode("big5")
        path = self._make_pas_file_raw(raw_bytes)
        try:
            from src.utils.file_backup import detect_encoding
            enc = detect_encoding(path)
            assert enc.lower() == "big5", f"Expected big5, got {enc}"
        finally:
            _cleanup(path)

    # ── 3. Shift-JIS Japanese ──
    def test_detect_shift_jis(self):
        """detect_encoding 应识别 Shift-JIS 编码的日文（含 cp932 微软变体）"""
        import codecs
        content = (
            "unit TestUnit;\n"
            "// 日本語コメント - プロジェクト管理システム\n"
            "// データベース接続設定 - 顧客情報管理\n"
            "// 注文処理モジュール - レポート生成\n"
            "// ユーザー権限管理 - システム設定\n"
            "implementation\n"
            "end."
        )
        raw_bytes = content.encode("shift_jis")
        path = self._make_pas_file_raw(raw_bytes)
        try:
            from src.utils.file_backup import detect_encoding
            enc = detect_encoding(path)
            assert enc.lower() in ("shift_jis", "cp932"), f"Expected shift_jis or cp932, got {enc}"
        finally:
            _cleanup(path)

    # ── 4. EUC-KR Korean ──
    def test_detect_euc_kr(self):
        """detect_encoding 应识别 EUC-KR 编码的韩文"""
        import codecs
        content = (
            "unit TestUnit;\n"
            "// 한국어 테스트 - 프로젝트 관리 시스템\n"
            "// 데이터베이스 연결 설정 - 고객 정보 관리\n"
            "// 주문 처리 모듈 - 보고서 생성\n"
            "// 사용자 권한 관리 - 시스템 설정\n"
            "implementation\n"
            "end."
        )
        raw_bytes = content.encode("euc-kr")
        path = self._make_pas_file_raw(raw_bytes)
        try:
            from src.utils.file_backup import detect_encoding
            enc = detect_encoding(path)
            assert enc.lower() in ("euc-kr", "cp949"), f"Expected euc-kr, got {enc}"
        finally:
            _cleanup(path)

    # ── 5. UTF-8 with BOM (utf-8-sig) ──
    def test_detect_utf8_sig(self):
        """detect_encoding 应识别 UTF-8 with BOM"""
        content = "\ufeffunit TestUnit;\ninterface\nimplementation\nend."
        path = self._make_pas_file(content, "utf-8-sig")
        try:
            from src.utils.file_backup import detect_encoding
            enc = detect_encoding(path)
            assert enc == "utf-8-sig", f"Expected utf-8-sig, got {enc}"
        finally:
            _cleanup(path)

    # ── 6. UTF-16 LE with BOM ──
    def test_detect_utf16(self):
        """detect_encoding 应识别 UTF-16 LE with BOM"""
        content = "unit TestUnit;\ninterface\nimplementation\nend."
        path = self._make_pas_file(content, "utf-16")
        try:
            from src.utils.file_backup import detect_encoding
            enc = detect_encoding(path)
            assert "utf-16" in enc.lower(), f"Expected utf-16, got {enc}"
        finally:
            _cleanup(path)

    # ── 7. Pure ASCII → utf-8 ──
    def test_detect_ascii(self):
        """纯 ASCII 文件应检测为 utf-8"""
        content = "unit TestUnit;\ninterface\nuses\n  SysUtils, Classes;\nimplementation\nend."
        path = self._make_pas_file(content, "ascii")
        try:
            from src.utils.file_backup import detect_encoding
            enc = detect_encoding(path)
            assert enc == "utf-8", f"Expected utf-8 for ASCII, got {enc}"
        finally:
            _cleanup(path)

    # ── 8. Empty file → utf-8 ──
    def test_detect_empty(self):
        """空文件应返回 utf-8"""
        fd, path = tempfile.mkstemp(suffix=".pas")
        os.close(fd)
        try:
            from src.utils.file_backup import detect_encoding
            enc = detect_encoding(path)
            assert enc == "utf-8", f"Expected utf-8 for empty file, got {enc}"
        finally:
            _cleanup(path)

    # ── 9. Multi-point sampling: ASCII header + GBK body ──
    def test_detect_multi_sample_gbk(self):
        """多点采样：前 20KB+ 纯 ASCII、后部 GBK，应检测为 GBK
        旧版 detect_encoding 只读前 16KB，会错过后面的 GBK 内容。
        新版多点采样（开头+1/3+2/3+结尾）才能正确检测。
        """
        import codecs
        # 单个 ascii_header 约 0.7KB，重复 30 次得到 ~21KB 纯 ASCII
        ascii_header = (
            "unit ProjectManager;\n"
            "interface\n"
            "uses\n"
            "  Winapi.Windows, Winapi.Messages, System.SysUtils, System.Variants,\n"
            "  System.Classes, Vcl.Graphics, Vcl.Controls, Vcl.Forms, Vcl.Dialogs,\n"
            "  Vcl.StdCtrls, Vcl.ExtCtrls, Vcl.ComCtrls, Vcl.Menus, Vcl.Grids,\n"
            "  Vcl.ImgList, Vcl.ToolWin, Vcl.ActnList, System.Actions,\n"
            "  Data.DB, Data.Win.ADODB, Vcl.DBGrids, Vcl.DBCtrls, Vcl.DBPanels;\n"
            "type\n"
            "  TProjectManagerForm = class(TForm)\n"
            "    btnOpen: TButton;\n"
            "    btnSave: TButton;\n"
            "    btnClose: TButton;\n"
            "    procedure btnOpenClick(Sender: TObject);\n"
            "    procedure btnSaveClick(Sender: TObject);\n"
            "  private\n"
            "    { Private declarations }\n"
            "  public\n"
            "    { Public declarations }\n"
            "  end;\n"
            "var\n"
            "  ProjectManagerForm: TProjectManagerForm;\n"
            "implementation\n"
            "{$R *.dfm}\n"
        )
        # 重复 ~30 次 → ~21KB 纯 ASCII，确保超过旧版 16KB 采样窗口
        large_ascii = ascii_header * 30
        gbk_body = "// 项目文件管理模块 - 中文配置说明 - 连接字符串" * 200

        full_content = large_ascii + gbk_body
        raw_bytes = full_content.encode("gbk")

        # 验证文件确实 > 16KB（旧采样窗口）
        assert len(raw_bytes) > 16384, (
            f"File too small ({len(raw_bytes)} bytes), "
            f"won't test multi-point sampling properly"
        )

        path = self._make_pas_file_raw(raw_bytes)
        try:
            from src.utils.file_backup import detect_encoding
            enc = detect_encoding(path)
            assert enc.lower() in ("gbk", "gb18030"), f"Expected gbk for mixed content, got {enc}"
        finally:
            _cleanup(path)

    # ── 10. GBK → read with encoding param ──
    @pytest.mark.asyncio
    async def test_read_gbk_with_encoding_param(self):
        """传入 encoding='gbk' 应成功读取 GBK 文件"""
        import codecs
        content = "unit TestUnit;\n// 数据库连接配置字符串\nimplementation\nend."
        raw_bytes = content.encode("gbk")
        path = self._make_pas_file_raw(raw_bytes)
        try:
            from src.tools.file_tool import handle_read
            result = await handle_read({
                "file_path": path,
                "encoding": "gbk",
                "start_line": 1,
                "end_line": 10,
            })
            assert result["status"] == "success", f"Read failed: {result['message']}"
            assert "数据库" in result["message"]
        finally:
            _cleanup(path)

    # ── 11. GBK → read WITHOUT encoding param (should auto-detect) ──
    @pytest.mark.asyncio
    async def test_read_gbk_auto_detect(self):
        """不传 encoding 时，chardet 应自动检测 GBK"""
        import codecs
        content = "unit TestUnit;\n// 数据库连接配置字符串\nimplementation\nend."
        raw_bytes = content.encode("gbk")
        path = self._make_pas_file_raw(raw_bytes)
        try:
            from src.tools.file_tool import handle_read
            result = await handle_read({
                "file_path": path,
                "start_line": 1,
                "end_line": 10,
            })
            assert result["status"] == "success", f"Auto-detect failed: {result['message']}"
            assert "数据库" in result["message"]
            assert "gbk" in result.get("encoding", "").lower() or "gbk" in result["message"].lower()
        finally:
            _cleanup(path)

    # ── 12. Big5 → read auto-detect（端到端）──
    @pytest.mark.asyncio
    async def test_read_big5_auto_detect(self):
        """不传 encoding，handle_read 应自动检测 Big5 并正确读取繁体中文内容

        端到端验证链：
        Big5 文件 → detect_encoding() → 'big5'
                        ↓
                  handle_read(file_path=path, 无 encoding 参数)
                        ↓
                  status=success + encoding='big5' + 内容正确
        """
        import codecs
        import locale as _locale
        content = (
            "unit TestUnit;\n"
            "// 繁體中文測試 - 專案管理系統 - 資料庫連接設定\n"
            "// 客戶資料維護 - 訂單處理模組 - 報表產生器\n"
            "// 使用者權限管理 - 系統參數設定 - 稽核追蹤\n"
            "implementation\n"
            "end."
        )
        raw_bytes = content.encode("big5")
        path = self._make_pas_file_raw(raw_bytes)
        try:
            from src.tools.file_tool import handle_read
            result = await handle_read({
                "file_path": path,
                "start_line": 1,
                "end_line": 10,
            })
            # ① 读取成功
            assert result["status"] == "success", (
                f"Big5 auto-detect 失败 (locale={_locale.getpreferredencoding()}): "
                f"{result['message']}"
            )

            # ② 自动检测的编码是 big5（非 gbk）
            result_enc = result.get("encoding", "").lower()
            assert result_enc and "big5" in result_enc or "big5" in result["message"].lower(), (
                f"检测编码为 {result_enc}，期望 big5；"
                f"消息中也未包含 big5: {result['message'][:200]}"
            )

            # ③ 读取的内容正确
            assert "繁體" in result["message"], "繁体中文内容读取异常"
            assert "專案管理" in result["message"], "Big5 编码的专有名词读取异常"
        finally:
            _cleanup(path)

    # ── 13. Shift-JIS → read auto-detect（端到端）──
    @pytest.mark.asyncio
    async def test_read_shift_jis_auto_detect(self):
        """不传 encoding，handle_read 应自动检测 Shift-JIS 并正确读取日文内容"""
        import codecs
        import locale as _locale
        content = (
            "unit TestUnit;\n"
            "// 日本語コメント - プロジェクト管理システム\n"
            "// データベース接続設定 - 顧客情報管理\n"
            "// 注文処理モジュール - レポート生成\n"
            "// ユーザー権限管理 - システム設定\n"
            "implementation\n"
            "end."
        )
        raw_bytes = content.encode("shift_jis")
        path = self._make_pas_file_raw(raw_bytes)
        try:
            from src.tools.file_tool import handle_read
            result = await handle_read({
                "file_path": path,
                "start_line": 1,
                "end_line": 10,
            })
            assert result["status"] == "success", (
                f"Shift-JIS auto-detect 失败 (locale={_locale.getpreferredencoding()}): "
                f"{result['message']}"
            )
            result_enc = result.get("encoding", "").lower()
            assert result_enc and ("shift_jis" in result_enc or "cp932" in result_enc), (
                f"检测编码为 {result_enc}，期望 shift_jis 或 cp932"
            )
            assert "日本語" in result["message"], "日文内容读取异常"
        finally:
            _cleanup(path)

    # ── 14. EUC-KR → read auto-detect（端到端）──
    @pytest.mark.asyncio
    async def test_read_euc_kr_auto_detect(self):
        """不传 encoding，handle_read 应自动检测 EUC-KR 并正确读取韩文内容"""
        import codecs
        import locale as _locale
        content = (
            "unit TestUnit;\n"
            "// 한국어 테스트 - 프로젝트 관리 시스템\n"
            "// 데이터베이스 연결 설정 - 고객 정보 관리\n"
            "// 주문 처리 모듈 - 보고서 생성\n"
            "// 사용자 권한 관리 - 시스템 설정\n"
            "implementation\n"
            "end."
        )
        raw_bytes = content.encode("euc-kr")
        path = self._make_pas_file_raw(raw_bytes)
        try:
            from src.tools.file_tool import handle_read
            result = await handle_read({
                "file_path": path,
                "start_line": 1,
                "end_line": 10,
            })
            assert result["status"] == "success", (
                f"EUC-KR auto-detect 失败 (locale={_locale.getpreferredencoding()}): "
                f"{result['message']}"
            )
            result_enc = result.get("encoding", "").lower()
            assert result_enc and ("euc-kr" in result_enc or "cp949" in result_enc), (
                f"检测编码为 {result_enc}，期望 euc-kr 或 cp949"
            )
            assert "한국어" in result["message"], "韩文内容读取异常"
        finally:
            _cleanup(path)

    # ── 15. Cross-CJK: Big5 on Chinese Windows → should NOT be misdetected as GBK ──
    def test_big5_not_misdetected_as_gbk_on_chinese_windows(self):
        """跨 CJK 场景：中文 Windows (locale=gbk) 上 Big5 文件不应被误判为 GBK"""
        import codecs
        import locale as _locale

        content = (
            "unit TestUnit;\n"
            "// 繁體中文測試 - 專案管理系統 - 資料庫連接設定\n"
            "// 客戶資料維護 - 訂單處理模組 - 報表產生器\n"
            "// 使用者權限管理 - 系統參數設定 - 稽核追蹤\n"
            "implementation\n"
            "end."
        )
        raw_bytes = content.encode("big5")
        path = self._make_pas_file_raw(raw_bytes)
        try:
            from src.utils.file_backup import detect_encoding
            enc = detect_encoding(path)
            assert enc.lower() == "big5", (
                f"Big5 在 locale={_locale.getpreferredencoding()} 上被误判为 {enc}"
            )
            with open(path, "r", encoding=enc) as f:
                text = f.read()
            assert "繁體" in text
        finally:
            _cleanup(path)

    # ── 14. Cross-CJK: Shift-JIS on Chinese Windows → should NOT be misdetected as GBK ──
    def test_shift_jis_not_misdetected_as_gbk_on_chinese_windows(self):
        """跨 CJK 场景：中文 Windows (locale=gbk) 上 Shift-JIS 日文不应被误判为 GBK"""
        import codecs
        import locale as _locale

        content = (
            "unit TestUnit;\n"
            "// 日本語コメント - プロジェクト管理システム\n"
            "// データベース接続設定 - 顧客情報管理\n"
            "// 注文処理モジュール - レポート生成\n"
            "// ユーザー権限管理 - システム設定\n"
            "implementation\n"
            "end."
        )
        raw_bytes = content.encode("shift_jis")
        path = self._make_pas_file_raw(raw_bytes)
        try:
            from src.utils.file_backup import detect_encoding
            enc = detect_encoding(path)
            assert enc.lower() in ("shift_jis", "cp932"), (
                f"Shift-JIS 在 locale={_locale.getpreferredencoding()} 上被误判为 {enc}"
            )
            with open(path, "r", encoding=enc) as f:
                text = f.read()
            assert "日本語" in text
        finally:
            _cleanup(path)

    # ── 15. Cross-CJK: EUC-KR on Chinese Windows → should NOT be misdetected as GBK ──
    def test_euc_kr_not_misdetected_as_gbk_on_chinese_windows(self):
        """跨 CJK 场景：中文 Windows (locale=gbk) 上 EUC-KR 韩文不应被误判为 GBK"""
        import codecs
        import locale as _locale

        content = (
            "unit TestUnit;\n"
            "// 한국어 테스트 - 프로젝트 관리 시스템\n"
            "// 데이터베이스 연결 설정 - 고객 정보 관리\n"
            "// 주문 처리 모듈 - 보고서 생성\n"
            "// 사용자 권한 관리 - 시스템 설정\n"
            "implementation\n"
            "end."
        )
        raw_bytes = content.encode("euc-kr")
        path = self._make_pas_file_raw(raw_bytes)
        try:
            from src.utils.file_backup import detect_encoding
            enc = detect_encoding(path)
            assert enc.lower() in ("euc-kr", "cp949"), (
                f"EUC-KR 在 locale={_locale.getpreferredencoding()} 上被误判为 {enc}"
            )
            with open(path, "r", encoding=enc) as f:
                text = f.read()
            assert "한국어" in text
        finally:
            _cleanup(path)
