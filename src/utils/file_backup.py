"""
文件备份工具 — __history 备份/恢复/列表

提供与 Delphi IDE 兼容的 __history 备份机制。
备份文件命名: 文件名.~版本号~ (如 Unit.pas.~1~)
超过 RETENTION_DAYS 天的旧备份自动清理。
"""

import os
import shutil
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


def detect_encoding(file_path: str) -> str:
    """
    检测文件编码。

    检测顺序:
        1. BOM (UTF-16 LE/BE, UTF-8 with BOM)
        2. 无 BOM UTF-16 启发式检测（通过空字节高低位分布判断）
        3. UTF-8 解码尝试
        4. GBK 解码尝试
        5. 回退: UTF-8

    Args:
        file_path: 文件路径

    Returns:
        编码名称: "utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "gbk"
    """
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read(16384)  # 只读前 16KB 做检测，大文件无需全读

        if not raw_data:
            return 'utf-8'

        # ── 1. BOM 检测 ──
        if raw_data.startswith(b'\xff\xfe') or raw_data.startswith(b'\xfe\xff'):
            return 'utf-16'
        elif raw_data.startswith(b'\xef\xbb\xbf'):
            return 'utf-8-sig'

        # ── 2. 无 BOM UTF-16 启发式检测 ──
        # 原理：ASCII 字符在 UTF-16 LE 中编码为 [char, \x00]，
        # 空字节集中出现在奇数位(LE)或偶数位(BE)。
        # 对于中文 UTF-16，高低字节均非空，但连续 ASCII 段会产生密集的空字节模式。
        if len(raw_data) >= 8:
            odd_positions = raw_data[1::2]   # 索引 1,3,5,...
            even_positions = raw_data[0::2]  # 索引 0,2,4,...
            null_odd = sum(1 for b in odd_positions if b == 0)
            null_even = sum(1 for b in even_positions if b == 0)
            total_odd = len(odd_positions)

            # UTF-16 LE: 奇数位空字节占比高（ASCII 高字节为 0x00）
            # 返回 'utf-16-le'（无 BOM 时 Python 需明确指定字节序）
            if null_odd > total_odd * 0.3 and null_even < total_odd * 0.1:
                try:
                    raw_data.decode('utf-16-le')
                    return 'utf-16-le'
                except (UnicodeDecodeError, ValueError):
                    pass

            # UTF-16 BE: 偶数位空字节占比高
            if null_even > total_odd * 0.3 and null_odd < total_odd * 0.1:
                try:
                    raw_data.decode('utf-16-be')
                    return 'utf-16-be'
                except (UnicodeDecodeError, ValueError):
                    pass

        # ── 3. UTF-8 解码尝试 ──
        try:
            raw_data.decode('utf-8')
            return 'utf-8'
        except UnicodeDecodeError:
            pass

        # ── 4. GBK 解码尝试 ──
        try:
            raw_data.decode('gbk')
            return 'gbk'
        except UnicodeDecodeError:
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
