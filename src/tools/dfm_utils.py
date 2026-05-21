"""
DFM 格式转换工具 — 按需编译 Delphi 转换器

使用 Delphi RTL 的 ObjectResourceToText / ObjectTextToResource
在文本 DFM 和二进制 DFM 之间转换。

转换器是一个临时生成的 .dpr，编译后运行即销毁。
"""

import os
import sys
import tempfile
import subprocess
import shutil
from typing import Optional, Dict, Any, Set
from ..utils.logger import get_logger

logger = get_logger(__name__)

# 跟踪通过 ensure_dfm_text 创建的临时目录，供 _cleanup_dfm_temp_dirs 清理
_dfm_temp_dirs: Set[str] = set()


def _cleanup_dfm_temp_dirs():
    """清理 ensure_dfm_text 留下的所有临时目录。在服务关闭时调用。"""
    for d in list(_dfm_temp_dirs):
        try:
            shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass
    _dfm_temp_dirs.clear()


# 全局编译器搜索路径缓存
_compiler_dcc32_path: Optional[str] = None

# 编译好的 dfmconv.exe 缓存路径（避免每次 DFM 转换都重新编译 dcc32）
_cached_dfmconv_exe: Optional[str] = None


def set_compiler_path(path: str):
    """设置 dcc32.exe 路径"""
    global _compiler_dcc32_path
    _compiler_dcc32_path = path


def _get_cached_dfmconv() -> Optional[str]:
    """获取缓存的 dfmconv.exe 路径，存在且有效时返回，否则返回 None"""
    global _cached_dfmconv_exe
    if _cached_dfmconv_exe and os.path.isfile(_cached_dfmconv_exe):
        return _cached_dfmconv_exe
    return None


def _find_dcc32() -> Optional[str]:
    """查找可用的 dcc32.exe"""
    if _compiler_dcc32_path and os.path.isfile(_compiler_dcc32_path):
        return _compiler_dcc32_path

    # 从 PATH 中查找
    which_cmd = "where" if sys.platform == "win32" else "which"
    try:
        result = subprocess.run(
            [which_cmd, "dcc32.exe" if sys.platform == "win32" else "dcc32"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        if result.returncode == 0:
            path = result.stdout.strip().split('\n')[0].strip()
            if path and os.path.isfile(path):
                return path
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _dfmconv_dpr(cmd: str, in_file: str, out_file: str) -> str:
    """生成 DFM 转换器 .dpr 源码"""
    # 使用原始字符串避免路径转义问题
    return f'''program dfmconv;

{{$APPTYPE CONSOLE}}

uses
  System.Classes,
  System.SysUtils;

var
  ins, outs: TFileStream;
  cmd: string;
  inPath, outPath: string;
begin
  cmd := ParamStr(1);
  inPath := ParamStr(2);
  outPath := ParamStr(3);

  if (cmd = '') or (inPath = '') or (outPath = '') then
  begin
    WriteLn('Usage: dfmconv <to-text|to-binary> <input> <output>');
    Halt(1);
  end;

  ins := TFileStream.Create(inPath, fmOpenRead or fmShareDenyWrite);
  try
    outs := TFileStream.Create(outPath, fmCreate);
    try
      if cmd = 'to-text' then
        ObjectResourceToText(ins, outs)
      else if cmd = 'to-binary' then
        ObjectTextToResource(ins, outs)
      else
      begin
        WriteLn('Unknown command: ', cmd);
        Halt(1);
      end;
    finally
      outs.Free;
    end;
  finally
    ins.Free;
  end;
end.
'''

def _find_library_path(dcc32: str) -> Optional[str]:
    """
    根据 dcc32 路径推导 RTL 库路径。

    Delphi 标准目录结构:
      <root>/bin/dcc32.exe
      <root>/lib/win32/release/  (DCU 文件)

    Args:
        dcc32: dcc32.exe 完整路径

    Returns:
        库路径，未找到返回 None
    """
    dcc_dir = os.path.dirname(os.path.abspath(dcc32))
    # 尝试 bin/../lib/win32/release
    root = os.path.dirname(dcc_dir)  # <Studio版本号>/
    candidates = [
        os.path.join(root, "lib", "win32", "release"),
        os.path.join(root, "lib", "Win32", "Release"),
        os.path.join(root, "lib"),
    ]
    for p in candidates:
        if os.path.isdir(p):
            return p
    return None


def _compile_dfmconv_to(exe_path: str, dcc32: str) -> bool:
    """
    编译 DFM 转换器到指定路径。

    Args:
        exe_path: 目标 exe 路径
        dcc32: dcc32.exe 路径

    Returns:
        是否编译成功
    """
    out_dir = os.path.dirname(exe_path)
    dpr_path = os.path.join(out_dir, "dfmconv.dpr")

    with open(dpr_path, "w", encoding="utf-8") as f:
        f.write(_dfmconv_dpr("to-text", "", ""))

    try:
        lib_path = _find_library_path(dcc32)

        # 先尝试不带库路径（某些环境通过注册表可自动找到）
        cmd = [dcc32, dpr_path, f"-E{out_dir}", "-Q", "-B"]
        logger.info(f"编译 DFM 转换器: {' '.join(cmd)}")
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )

        # 如果失败且有库路径，重试
        first_error = result.stderr if result.returncode != 0 else None
        if result.returncode != 0 and lib_path:
            cmd2 = [dcc32, dpr_path, f"-E{out_dir}", "-Q", "-B", f"-U{lib_path}"]
            logger.info(f"重试编译 DFM 转换器(带-U): {' '.join(cmd2)}")
            result = subprocess.run(
                cmd2, capture_output=True, text=True, timeout=30,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )

        if result.returncode != 0:
            err_detail = result.stderr.strip() or first_error or "未知错误"
            logger.error(f"编译 DFM 转换器失败: {err_detail}")
            return False

        if os.path.isfile(exe_path):
            return True
        logger.error(f"编译后未找到 exe: {exe_path}")
        return False
    except subprocess.TimeoutExpired:
        logger.error("编译 DFM 转换器超时")
        return False
    except Exception as e:
        logger.error(f"编译 DFM 转换器异常: {e}")
        return False


def _ensure_dfmconv() -> Optional[str]:
    """
    确保 DFM 转换器已编译，返回可执行文件路径。

    首次调用时编译并缓存，后续直接返回缓存路径，避免重复编译。

    Returns:
        dfmconv.exe 路径，失败返回 None
    """
    global _cached_dfmconv_exe

    # 1. 检查缓存
    cached = _get_cached_dfmconv()
    if cached:
        return cached

    # 2. 查找 dcc32
    dcc32 = _find_dcc32()
    if not dcc32:
        logger.error("未找到 dcc32.exe，无法编译 DFM 转换器")
        return None

    # 3. 编译到固定缓存路径（系统 temp 下，持续进程生命周期）
    cache_dir = os.path.join(tempfile.gettempdir(), "daofy_dfmconv_cache")
    os.makedirs(cache_dir, exist_ok=True)
    exe_path = os.path.join(cache_dir, "dfmconv.exe")

    if _compile_dfmconv_to(exe_path, dcc32):
        _cached_dfmconv_exe = exe_path
        logger.info(f"DFM 转换器已编译并缓存: {exe_path}")
        return exe_path

    return None


def _compile_dfmconv(tmp_dir: str) -> Optional[str]:
    """
    编译 DFM 转换器（兼容旧接口，直接委托给缓存机制）。

    Args:
        tmp_dir: 临时目录

    Returns:
        exe 路径，失败返回 None
    """
    exe_path = _ensure_dfmconv()
    if exe_path:
        return exe_path
    # 如果缓存失败但 tmp_dir 需要编译结果（回退路径），尝试直接编译到 tmp_dir
    dcc32 = _find_dcc32()
    if not dcc32:
        return None
    fallback_exe = os.path.join(tmp_dir, "dfmconv.exe")
    if _compile_dfmconv_to(fallback_exe, dcc32):
        return fallback_exe
    return None


def _run_dfmconv(exe_path: str, cmd: str, in_file: str, out_file: str) -> bool:
    """运行已编译的 DFM 转换器"""
    try:
        result = subprocess.run(
            [exe_path, cmd, in_file, out_file],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        if result.returncode != 0:
            logger.error(f"DFM 转换失败 ({cmd}): {result.stderr or result.stdout}")
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.error("DFM 转换超时")
        return False
    except Exception as e:
        logger.error(f"DFM 转换异常: {e}")
        return False


def _detect_dfm_format(file_path: str) -> str:
    """
    检测 DFM 文件格式。

    Args:
        file_path: .dfm 文件路径

    Returns:
        "text" 或 "binary"

    Raises:
        FileNotFoundError: 文件不存在
        PermissionError: 无权限读取
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"DFM 文件不存在: {file_path}")
    try:
        with open(file_path, 'rb') as f:
            header = f.read(32)

        # 文本 DFM 以 object 或 inherited 开头（ASCII 可读）
        # 二进制 DFM 开头通常是 FF FF FF FF 或其他非文本标记
        # 先去除 UTF-8 BOM（EF BB BF），避免 BOM 导致 ASCII 解码失败
        if header[:3] == b'\xef\xbb\xbf':
            header = header[3:]
        try:
            text = header.decode('ascii', errors='strict')
            text_stripped = text.strip().lower()
            if text_stripped.startswith('object ') or text_stripped.startswith('inherited '):
                return "text"
            return "binary"
        except (UnicodeDecodeError, ValueError):
            return "binary"
    except (FileNotFoundError, PermissionError):
        raise
    except Exception as e:
        logger.warning(f"检测 DFM 格式失败: {e}")
        return "text"  # 保守默认：无法判断时假设文本格式


async def convert_dfm(in_file: str, out_file: str, to_text: bool = True) -> Dict[str, Any]:
    """
    转换 DFM 文件格式（文本 ↔ 二进制）。

    按需编译一个临时 Delphi 转换器程序，执行转换后清理。

    Args:
        in_file: 输入文件路径
        out_file: 输出文件路径
        to_text: True=二进制→文本, False=文本→二进制

    Returns:
        {"success": bool, "message": str, "source_format": str, "target_format": str}
    """
    source_fmt = "text"
    target_fmt = "binary"
    if to_text:
        source_fmt = "binary"
        target_fmt = "text"

    if not os.path.isfile(in_file):
        return {
            "success": False,
            "message": f"文件不存在: {in_file}",
            "source_format": source_fmt,
            "target_format": target_fmt
        }

    # 检测源格式是否匹配
    actual_format = _detect_dfm_format(in_file)
    if to_text and actual_format != "binary":
        return {
            "success": False,
            "message": f"文件已经是文本格式，无需转换",
            "source_format": "text",
            "target_format": "text"
        }
    if not to_text and actual_format != "text":
        return {
            "success": False,
            "message": f"文件已经是二进制格式，无需转换",
            "source_format": "binary",
            "target_format": "binary"
        }

    # 使用缓存的 DFM 转换器（首次调用时编译一次，后续复用）
    exe_path = _ensure_dfmconv()
    if not exe_path:
        return {
            "success": False,
            "message": "编译 DFM 转换器失败，请检查 Delphi 编译器是否可用",
            "source_format": source_fmt,
            "target_format": target_fmt
        }

    cmd = "to-text" if to_text else "to-binary"
    ok = _run_dfmconv(exe_path, cmd, in_file, out_file)
    if not ok:
        return {
            "success": False,
            "message": f"DFM 转换执行失败 ({cmd})",
            "source_format": source_fmt,
            "target_format": target_fmt
        }

    return {
        "success": True,
        "message": f"DFM 转换成功: {source_fmt} → {target_fmt}",
        "source_format": source_fmt,
        "target_format": target_fmt
    }


async def ensure_dfm_text(file_path: str) -> Optional[str]:
    """
    确保 DFM 文件是文本格式。如果是二进制，转换为文本后返回临时路径。

    Args:
        file_path: .dfm 文件路径

    Returns:
        如果是文本格式，返回原路径；
        如果是二进制且转换成功，返回临时文本文件路径；
        失败返回 None，并清理临时目录

    Note:
        返回的临时路径在进程生命周期内有效。
        服务关闭时自动清理，也可手动调用 _cleanup_dfm_temp_dirs()。
    """
    fmt = _detect_dfm_format(file_path)
    if fmt == "text":
        return file_path

    # 二进制 → 文本
    tmp_dir = tempfile.mkdtemp(prefix="dfmconv_")
    tmp_text = os.path.join(tmp_dir, os.path.basename(file_path) + ".txt")
    result = await convert_dfm(file_path, tmp_text, to_text=True)
    if result["success"]:
        _dfm_temp_dirs.add(tmp_dir)
        return tmp_text
    # 失败时立即清理
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return None


async def ensure_dfm_binary(text_path: str, original_binary_path: str) -> bool:
    """
    将文本 DFM 转回二进制，替换目标文件。

    在 write 场景下使用：Agent 修改了文本 DFM 内容后，
    需要转回原始格式（二进制）保存。

    Args:
        text_path: 修改后的文本 DFM 临时路径
        original_binary_path: 原始二进制 DFM 路径（作为输出目标）

    Returns:
        是否成功
    """
    result = await convert_dfm(text_path, original_binary_path, to_text=False)
    return result["success"]
