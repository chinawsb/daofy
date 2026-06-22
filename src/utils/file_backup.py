"""
文件备份工具 — __history 备份/恢复/列表

提供与 Delphi IDE 兼容的 __history 备份机制。
备份文件命名: 文件名.~版本号~ (如 Unit.pas.~1~)
超过 RETENTION_DAYS 天的旧备份自动清理。
"""

import locale
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

# 多字节 CJK locale 编码集合 — 这些编码的 decode 在遇到非法字节时会报错，
# 可以可靠地用"试解码"方式检测。单字节编码（cp1252, iso-8859-*等）
# 接受任意字节永不报错，不适合此方法。
_MULTIBYTE_LOCALE_ENCODINGS = {
    # 简体中文
    'gbk', 'gb2312', 'gb18030', 'cp936', 'hz',
    # 繁体中文
    'big5', 'big5hkscs', 'cp950',
    # 日文
    'shift_jis', 'cp932', 'ms932', 'euc-jp', 'iso-2022-jp',
    # 韩文
    'euc-kr', 'cp949', 'ks_c_5601_1987', 'iso-2022-kr',
}

# 通用回退链 — 按使用频率排列
_UNIVERSAL_FALLBACK = [
    'utf-8',
    'gbk', 'gb18030',
    'big5',
    'shift_jis', 'cp932',
    'euc-kr', 'cp949',
    'euc-jp',
]


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


def detect_encoding(file_path: str) -> str:
    """
    检测文件编码。

    检测顺序: BOM → UTF-16 启发式 → 系统 locale 编码 → chardet → 通用回退链

    系统 locale 编码优先尝试（如中文 Windows 的 gbk、日文 Windows 的 cp932），
    可覆盖 90%+ 场景而无需启动 chardet。
    仅当 locale 编码无效或为单字节编码（cp1252 等）时才继续到 chardet。

    Args:
        file_path: 文件路径

    Returns:
        编码名称（utf-8 / utf-8-sig / utf-16 / gbk / big5 / shift_jis
        / euc-kr / euc-jp 等）
    """
    try:
        file_size = os.path.getsize(file_path)

        # ── 多点采样 ──
        # 避免 Delphi 文件前部纯 ASCII、后部 CJK 的漏检
        # 采样位置：开头 + 1/3 + 2/3 + 末尾，总上限 256KB
        with open(file_path, 'rb') as f:
            if file_size <= 65536:
                raw_data = f.read(min(file_size, 262144))
            else:
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

                raw_data = b''.join(parts)[:max_total]

        if not raw_data:
            return 'utf-8'

        # ── 1. BOM 检测 ──
        if raw_data.startswith(b'\xff\xfe') or raw_data.startswith(b'\xfe\xff'):
            return 'utf-16'
        if raw_data.startswith(b'\xef\xbb\xbf'):
            return 'utf-8-sig'

        # ── 2. 无 BOM UTF-16 启发式检测 ──
        # 三层过滤：长度奇偶性 → 空字节间距分析 → decode 验证
        if len(raw_data) >= 8 and len(raw_data) % 2 == 0:
            # 采样前 4096 字节做空字节分布分析
            sample = raw_data[:min(len(raw_data), 4096)]

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

                # 计算奇偶位 null 分布
                odd_nulls = sum(1 for p in null_positions if p % 2 == 1)
                even_nulls = len(null_positions) - odd_nulls

                # UTF-16-LE: null 集中在奇数位，间距 ≈ 2，分布整齐
                if (odd_nulls > even_nulls * 3
                        and median_gap <= 2.5
                        and gap_consistency < 3.0):
                    try:
                        raw_data.decode('utf-16-le')
                        return 'utf-16-le'
                    except (UnicodeDecodeError, ValueError):
                        pass

                # UTF-16-BE: null 集中在偶数位
                if (even_nulls > odd_nulls * 3
                        and median_gap <= 2.5
                        and gap_consistency < 3.0):
                    try:
                        raw_data.decode('utf-16-be')
                        return 'utf-16-be'
                    except (UnicodeDecodeError, ValueError):
                        pass

        # ── 3. 系统 locale 编码检测（不立即返回）──
        # 在 CJK Windows 上，locale 编码就是开发者常用的编码，优先尝试。
        # 但仅对含非 ASCII 字节的文件生效：纯 ASCII 文件在 utf-8 和 locale
        # 编码下表现完全相同，一律视作 utf-8 更合理。
        locale_guess = None
        has_non_ascii = any(b > 127 for b in raw_data)
        if has_non_ascii:
            locale_enc = locale.getpreferredencoding().lower()
            locale_enc_norm = _normalize_charset_name(locale_enc)
            if locale_enc_norm in _MULTIBYTE_LOCALE_ENCODINGS:
                try:
                    raw_data.decode(locale_enc_norm)
                    # 解码成功，记录 locale 候选，但不立即返回
                    # 因为跨 CJK 场景（中文 Windows + Big5 文件）可能误判
                    locale_guess = locale_enc_norm
                except UnicodeDecodeError:
                    pass

        # ── 4. chardet 概率检测 ──
        chardet_guess = None
        try:
            import chardet
            result = chardet.detect(raw_data)
            enc = result.get('encoding')
            conf = result.get('confidence', 0)
            if enc and conf > 0.7:
                enc = _normalize_charset_name(enc)
                return enc
            if enc and conf > 0:
                # 低置信度也记录为候选（用于跨 CJK 场景）
                chardet_guess = _normalize_charset_name(enc)
                # 仅接受多字节 CJK 编码的建议；单字节编码（cp125*, iso-8859-* 等）
                # 接受所有字节永不报错，会导致误判
                _cjk_multibyte = {'big5', 'shift_jis', 'cp932', 'euc-kr', 'cp949',
                                  'euc-jp', 'iso-2022-jp', 'iso-2022-kr'}
                if chardet_guess not in _cjk_multibyte and chardet_guess != 'gbk':
                    chardet_guess = None
        except Exception:
            logger.debug("chardet 检测失败，降级到通用回退链")

        # ── 5. 候选裁决 ──
        # 如有 locale_guess 和 chardet_guess 且不一致，优先 chardet（概率分析更可靠）
        # 先验证 chardet_guess 确实能解码
        if chardet_guess:
            try:
                raw_data.decode(chardet_guess)
                if locale_guess and chardet_guess != locale_guess:
                    # chardet 于 locale 不一致 → 偏好 chardet
                    return chardet_guess
                # chardet 与 locale 一致，或仅 chardet 存在
                return chardet_guess
            except UnicodeDecodeError:
                pass  # chardet 建议无法解码，忽略

        if locale_guess:
            return locale_guess

        # ── 6. 通用回退链 ──
        for enc in _UNIVERSAL_FALLBACK:
            try:
                raw_data.decode(enc)
                return enc
            except UnicodeDecodeError:
                continue

        return 'utf-8'

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
