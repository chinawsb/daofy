"""
文件备份工具 — __history 备份/恢复/列表

提供与 Delphi IDE 兼容的 __history 备份机制。
备份文件命名: 文件名.~版本号~ (如 Unit.pas.~1~)
超过 RETENTION_DAYS 天的旧备份自动清理。
"""

import os
import shutil
import statistics
import time
from typing import Optional, List, Dict
from .logger import get_logger

logger = get_logger(__name__)

# 备份保留策略：超过此数量且超出保留天数的最旧备份自动清理
MAX_BACKUPS = 20
RETENTION_DAYS = 7

# 大文件拷贝缓冲区大小 (1MB) — shutil.copyfileobj 默认为 16KB
# 64x 缓冲区 = 同等 I/O 下 64 倍更少的系统调用
_COPY_BUF_SIZE = 1024 * 1024

# 全文编码检测上限：超过此大小（不可能是源码文本）时退化到多点采样，
# 避免一次性读入数百 MB 造成内存峰值
_MAX_FULL_DETECT_BYTES = 32 * 1024 * 1024

# UTF-16 无 BOM 启发式分析窗口：空字节分布是结构特征（与内容无关），
# 取前 1MB 足够判定，避免超大文件构建百万级空字节位置列表
_UTF16_ANALYSIS_WINDOW = 1024 * 1024

# chardet 低置信度时仅接受的多字节 CJK 编码；单字节编码（cp1252 等）
# 接受任意字节永不报错，会误判，故不接受
_CHARDET_MULTIBYTE = {
    'big5', 'shift_jis', 'cp932', 'euc-kr', 'cp949',
    'euc-jp', 'iso-2022-jp', 'iso-2022-kr',
}


def _fast_copy(src: str, dst: str) -> None:
    """
    使用大缓冲区快速拷贝文件（带元数据保留）。

    shutil.copy2 内部使用 shutil.copyfileobj 的 16KB 默认缓冲区，
    对于大文件会产生大量系统调用。此函数使用 1MB 缓冲区将
    系统调用次数降低 64 倍。

    Args:
        src: 源文件路径
        dst: 目标文件路径
    """
    with open(src, 'rb') as fsrc:
        with open(dst, 'wb') as fdst:
            shutil.copyfileobj(fsrc, fdst, _COPY_BUF_SIZE)
    shutil.copystat(src, dst)


def _normalize_charset_name(enc: str) -> str:
    """归一化字符集名为项目标准名称"""
    # chardet 返回名: GB2312, Shift_JIS, EUC-KR, ISO-2022-JP, Big5...
    # locale 返回名: cp1252, gbk, big5, cp932, cp949...
    # 统一转为小写 + 去横线后查表
    key = enc.lower().replace('-', '')
    norms = {
        'utf8': 'utf-8',
        'utf8sig': 'utf-8-sig',
        'utf16le': 'utf-16-le',
        'utf16be': 'utf-16-be',
        'utf16': 'utf-16',
        'ascii': 'utf-8',
        'latin1': 'utf-8',
        'iso88591': 'utf-8',
        'gb2312': 'gbk',
        'gb18030': 'gbk',   # GB18030 是 GBK 的超集，统一归为 gbk
        'cp936': 'gbk',
        'hzgb2312': 'gbk',
        'big5hkscs': 'big5',
        'cp950': 'big5',
        'ms932': 'cp932',
        'shiftjis': 'shift_jis',
        'euckr': 'euc-kr',
        'cp949': 'cp949',
        'ksc56011987': 'cp949',  # ks_c_5601_1987 去横线+去下划线后
        'eucjp': 'euc-jp',
        'iso2022jp': 'iso-2022-jp',
        'iso2022kr': 'iso-2022-kr',
    }
    if key in norms:
        return norms[key]
    # 再去掉下划线试一次（兼容带下划线的格式）
    key_flat = key.replace('_', '')
    if key_flat in norms:
        return norms[key_flat]
    return key


def _read_sample_for_detection(f, file_size: int) -> bytes:
    """
    超大文件（>32MB）多点采样：开头 + 1/3 + 2/3 + 末尾，总上限 256KB。

    Args:
        f: 已打开的二进制文件句柄（位于文件头）
        file_size: 文件总字节数

    Returns:
        采样字节串
    """
    chunk = 16384
    max_total = 262144
    parts = []
    total_read = 0

    # 开头
    parts.append(f.read(chunk))
    total_read += chunk

    # 1/3 处
    f.seek(max(0, file_size // 3 - chunk // 2))
    d = f.read(chunk)
    parts.append(d)
    total_read += len(d)

    if total_read < max_total:
        # 2/3 处
        f.seek(max(0, file_size * 2 // 3 - chunk // 2))
        d = f.read(chunk)
        parts.append(d)
        total_read += len(d)

    if total_read < max_total:
        # 末尾
        f.seek(max(0, file_size - chunk))
        d = f.read(chunk)
        parts.append(d)
        total_read += len(d)

    return b''.join(parts)[:max_total]


def _chardet_fallback(raw_data: bytes) -> Optional[str]:
    """
    chardet 兜底检测：仅当全文 UTF-8 与 GBK 均解码失败时调用。

    高置信度(>0.7)直接采纳（归一化后）；低置信度仅接受多字节 CJK 编码
    （big5/shift_jis/euc-kr 等），避免单字节编码误判。

    Args:
        raw_data: 文件原始字节

    Returns:
        归一化编码名；无法识别返回 None
    """
    try:
        import chardet
        result = chardet.detect(raw_data)
        enc = result.get('encoding')
        conf = result.get('confidence', 0)
        if not enc or conf <= 0:
            return None
        norm = _normalize_charset_name(enc)
        if conf > 0.7:
            return norm
        if norm in _CHARDET_MULTIBYTE:
            return norm
    except Exception:
        logger.debug("chardet 检测失败，降级到默认编码 gbk")
    return None


def detect_encoding(file_path: str) -> str:
    """
    检测文件编码。

    检测顺序: BOM → 无 BOM UTF-16 启发式 → 全文 UTF-8 → 全文 GBK → chardet 兜底

    - BOM 检测: UTF-8 BOM → utf-8-sig; UTF-16 BOM → utf-16
    - 无 BOM UTF-16 启发式: 空字节分布（前 1MB 窗口）+ 全文 decode 验证
    - 无 BOM 文本判定（全文检测，不再用 4K/多点采样）:
      全文存在合法 UTF-8 序列 → utf-8（无 BOM）；否则全文可解 GBK → gbk
    - chardet 兜底: UTF-8 与 GBK 均解码失败（编码异常/二进制/罕见多字节编码）
      时识别 big5/shift_jis/euc-kr 等；仍失败默认 gbk

    注: 全文判定后，多数 Big5/Shift-JIS/EUC-KR 文件因可作 GBK 解码而判为
    gbk（大陆场景预期行为）；chardet 仅在 UTF-8/GBK 双失败时兜底参与。

    Args:
        file_path: 文件路径

    Returns:
        编码名称（utf-8 / utf-8-sig / utf-16 / utf-16-le / utf-16-be
        / gbk / big5 / shift_jis / euc-kr / euc-jp 等）
    """
    try:
        file_size = os.path.getsize(file_path)

        # ── 全文读取 ──
        # 前部采样（4K/多点）对"前部纯 ASCII、后部 CJK"的文件不安全，
        # 一律读全文件判定；仅超 32MB 的非源码文件退化到多点采样。
        with open(file_path, 'rb') as f:
            if file_size <= _MAX_FULL_DETECT_BYTES:
                raw_data = f.read()
            else:
                raw_data = _read_sample_for_detection(f, file_size)

        if not raw_data:
            return 'utf-8'

        # ── 1. BOM 检测 ──
        if raw_data.startswith(b'\xff\xfe') or raw_data.startswith(b'\xfe\xff'):
            return 'utf-16'
        if raw_data.startswith(b'\xef\xbb\xbf'):
            return 'utf-8-sig'

        # ── 2. 无 BOM UTF-16 启发式检测 ──
        # 前置原因: ASCII 型 UTF-16 无 BOM 文件（"u\0n\0i\0t\0..."）可作
        # UTF-8 解出（含 NUL），必须先于 UTF-8 判定，否则会被误判为 utf-8。
        # 空字节分布是结构特征，前 1MB 窗口足够；decode 用全文验证。
        if len(raw_data) >= 8 and len(raw_data) % 2 == 0:
            sample = raw_data[:min(len(raw_data), _UTF16_ANALYSIS_WINDOW)]

            # 找出所有 null 字节的位置
            null_positions = [i for i, b in enumerate(sample) if b == 0]

            if len(null_positions) >= 4:
                # 计算相邻 null 字节的间距
                gaps = [null_positions[i + 1] - null_positions[i]
                        for i in range(len(null_positions) - 1)]

                median_gap = statistics.median(gaps)
                gap_range = max(gaps) - min(gaps)
                mean_gap = statistics.mean(gaps)
                # 间距一致性：越小越整齐。UTF-16 的 null 间距集中在 2 附近
                gap_consistency = gap_range / mean_gap if mean_gap > 0 else 0
                # 小间隙占比：容忍被 CJK 段打断的间隙（如 "unit Test;\n// 中文..."）
                # 文本类编码（utf-8/gbk/big5 等）几乎不含 NUL，null 密集且
                # 集中在单一奇偶位的数据几乎必是 UTF-16，故放宽一致性条件安全。
                small_gap_ratio = (
                    sum(1 for g in gaps if g <= 3) / len(gaps)
                    if gaps else 0.0
                )

                # 计算奇偶位 null 分布
                odd_nulls = sum(1 for p in null_positions if p % 2 == 1)
                even_nulls = len(null_positions) - odd_nulls

                # UTF-16-LE: null 集中在奇数位，间距 ≈ 2，分布整齐
                if (odd_nulls > even_nulls * 3
                        and median_gap <= 2.5
                        and (gap_consistency < 3.0 or small_gap_ratio >= 0.75)):
                    try:
                        raw_data.decode('utf-16-le')
                        return 'utf-16-le'
                    except (UnicodeDecodeError, ValueError):
                        pass

                # UTF-16-BE: null 集中在偶数位
                if (even_nulls > odd_nulls * 3
                        and median_gap <= 2.5
                        and (gap_consistency < 3.0 or small_gap_ratio >= 0.75)):
                    try:
                        raw_data.decode('utf-16-be')
                        return 'utf-16-be'
                    except (UnicodeDecodeError, ValueError):
                        pass

        # ── 3. 全文 UTF-8 判定：存在合法 UTF-8 序列 → UTF-8 无 BOM ──
        try:
            raw_data.decode('utf-8')
            return 'utf-8'
        except UnicodeDecodeError:
            pass

        # ── 4. 全文 GBK 判定：非 UTF-8 → GBK ──
        try:
            raw_data.decode('gbk')
            return 'gbk'
        except UnicodeDecodeError:
            pass

        # ── 5. chardet 兜底 ──
        # UTF-8 与 GBK 均解码失败（编码异常/二进制/罕见多字节编码）时才触发；
        # 仍失败默认 gbk。
        guess = _chardet_fallback(raw_data)
        if guess:
            return guess

        return 'gbk'

    except Exception as e:
        logger.warning(f"检测文件编码失败: {e}，使用默认编码 utf-8")
        return 'utf-8'


def _prune_backups(history_dir: str, base_name: str) -> None:
    """
    按策略清理旧备份：超过 MAX_BACKUPS 个时，清理超出部分中超过 RETENTION_DAYS 天的。
    不足 MAX_BACKUPS 个时全部保留。

    Args:
        history_dir: __history 目录路径
        base_name: 文件名（如 Unit.pas）
    """
    try:
        # 收集所有合法备份，按版本号降序排列
        backups = []
        for f in os.listdir(history_dir):
            if not (f.startswith(f"{base_name}.~") and f.endswith("~")):
                continue
            try:
                ver = int(f[len(base_name) + 2:-1])
                path = os.path.join(history_dir, f)
                mtime = os.path.getmtime(path)
                backups.append((ver, path, mtime))
            except (ValueError, IndexError, OSError):
                continue

        if len(backups) <= MAX_BACKUPS:
            return

        # 按版本号降序，保留最新的 MAX_BACKUPS 个
        backups.sort(key=lambda x: x[0], reverse=True)
        protected = set(backups[:MAX_BACKUPS])
        cutoff = time.time() - RETENTION_DAYS * 86400

        for ver, path, mtime in backups[MAX_BACKUPS:]:
            if mtime < cutoff:
                try:
                    os.remove(path)
                    logger.debug(f"清理过期备份: {path} (版本 {ver}, {RETENTION_DAYS}天前)")
                except OSError:
                    pass
    except Exception as e:
        logger.warning(f"清理旧备份失败: {e}")


def create_backup(file_path: str) -> Optional[str]:
    """
    创建 __history 备份文件。

    在源文件所在目录下创建 __history 子目录，生成带递增版本号的备份。
    版本号格式: 文件名.~N~ (与 Delphi IDE 兼容)

    Args:
        file_path: 源文件路径

    Returns:
        备份文件路径，失败返回 None
    """
    try:
        if not os.path.isfile(file_path):
            logger.warning(f"备份失败，文件不存在: {file_path}")
            return None

        file_dir = os.path.dirname(os.path.abspath(file_path))
        history_dir = os.path.join(file_dir, "__history")
        os.makedirs(history_dir, exist_ok=True)

        base_name = os.path.basename(file_path)

        # 查找现有备份，确定新版本号
        backup_files = [
            f for f in os.listdir(history_dir)
            if f.startswith(f"{base_name}.~") and f.endswith("~")
        ]

        max_version = 0
        for backup_file in backup_files:
            try:
                version_str = backup_file[len(base_name) + 2:-1]  # 去掉 "文件名.~" 和 "~"
                version = int(version_str)
                if version > max_version:
                    max_version = version
            except (ValueError, IndexError):
                continue

        # 递增版本号；若目标路径已被占用（如因垃圾文件导致版本冲突）则继续递增
        new_version = max_version + 1
        while True:
            backup_path = os.path.join(history_dir, f"{base_name}.~{new_version}~")
            if not os.path.exists(backup_path):
                break
            new_version += 1

        _fast_copy(file_path, backup_path)
        logger.info(f"创建备份文件: {backup_path}")

        # 清理超出上限的旧备份
        _prune_backups(history_dir, base_name)

        return backup_path

    except Exception as e:
        logger.warning(f"创建备份文件失败: {e}")
        return None


def list_backups(file_path: str) -> List[Dict]:
    """
    列出指定文件的所有备份版本。

    Args:
        file_path: 源文件路径

    Returns:
        备份版本列表，每个元素包含 version, path, size, mtime 字段。
        按版本号降序排列（最新的在前）。
    """
    file_dir = os.path.dirname(os.path.abspath(file_path))
    history_dir = os.path.join(file_dir, "__history")

    if not os.path.isdir(history_dir):
        return []

    base_name = os.path.basename(file_path)
    backups = []

    for f in os.listdir(history_dir):
        if not (f.startswith(f"{base_name}.~") and f.endswith("~")):
            continue

        full_path = os.path.join(history_dir, f)
        try:
            version_str = f[len(base_name) + 2:-1]
            version = int(version_str)
            stat = os.stat(full_path)
            backups.append({
                "version": version,
                "path": full_path,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            })
        except (ValueError, OSError):
            continue

    backups.sort(key=lambda x: x["version"], reverse=True)
    return backups


def restore_backup(file_path: str, version: Optional[int] = None) -> Optional[str]:
    """
    从 __history 恢复文件到指定版本。

    Args:
        file_path: 源文件路径
        version: 版本号，不传则使用最新版本

    Returns:
        恢复的备份文件路径，失败返回 None
    """
    backups = list_backups(file_path)
    if not backups:
        logger.warning(f"恢复失败，没有找到备份文件: {file_path}")
        return None

    if version is not None:
        target = next((b for b in backups if b["version"] == version), None)
        if not target:
            logger.warning(f"恢复失败，未找到版本 {version}，可用版本: {[b['version'] for b in backups]}")
            return None
    else:
        target = backups[0]  # 最新版本

    try:
        # 恢复前先备份当前文件（安全网）
        create_backup(file_path)

        _fast_copy(target["path"], file_path)
        logger.info(f"已从备份恢复: {target['path']} → {file_path}")
        return target["path"]

    except Exception as e:
        logger.error(f"恢复备份失败: {e}")
        return None
