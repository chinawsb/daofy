"""
自动更新模块 — 版本检测 / GitHub+PyPI Release 查询 / git pull 更新

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin

功能:
  - get_current_version()       读取当前版本（metadata→pyproject.toml→环境变量）
  - fetch_latest_release()      查询 GitHub 最新 Release（带镜像回退）
  - fetch_pypi_version()        查询 PyPI 最新版本（pip 安装专用，无需认证）
  - compare_versions(a, b)      比较 YYYY.MM.DD 版本号
  - check_for_update()          智能版本检查（pip→PyPI，git→GitHub）
  - check_for_update_retry()    ⭐ 异步自动重试版本检查（后台运行，可取消）
  - is_git_installation()       判断是否为 git 源码安装
  - is_pip_installation()       判断是否为 pip 安装
  - git_pull_update()           执行 git pull 更新
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time as _time
import urllib.error
import urllib.request
from importlib.metadata import version as _get_installed_version, PackageNotFoundError
from pathlib import Path
from typing import Optional

from ..constants import (
    TIMEOUT_SUBPROCESS_SHORT,
    TIMEOUT_UPDATER_GIT_PULL,
)

logger = logging.getLogger(__name__)

# ============================================================
# 仓库信息
# ============================================================
RELEASE_REPO = "chinawsb/daofy"
RELEASE_API = f"https://api.github.com/repos/{RELEASE_REPO}/releases/latest"

# GitHub 国内镜像代理
GITHUB_MIRRORS: list[str] = [
    "",  # 原始源（优先尝试）
    "https://ghproxy.com",  # ghproxy 新域名
    "https://ghproxy.net",  # ghproxy 旧域名
]

# PyPI 包信息
PYPI_PACKAGE = "daofy-for-delphi"
PYPI_JSON_URL = f"https://pypi.org/pypi/{PYPI_PACKAGE}/json"

# PyPI 国内镜像
PYPI_MIRRORS: list[str] = [
    "",  # PyPI 官方
    "https://pypi.tuna.tsinghua.edu.cn",  # 清华镜像
    "https://mirrors.aliyun.com/pypi",  # 阿里云镜像
]

# 单次请求参数
MAX_RETRY = 3
RETRY_DELAY = 2  # 秒
REQUEST_TIMEOUT = 15  # 秒

# 后台自动重试参数（check_for_update_retry）
RETRY_INTERVAL = 300     # 两次重试间隔（5分钟）
MAX_RETRIES = 12          # 最大重试次数（≈1小时）
ETA_MINUTES = (RETRY_INTERVAL * MAX_RETRIES) // 60  # 约60分钟


# ============================================================
# 版本工具
# ============================================================

def _get_project_root() -> Path:
    """获取项目根目录（pyproject.toml 所在目录）。"""
    # 当前文件在 src/utils/updater.py，向上两级
    return Path(__file__).resolve().parent.parent.parent


def get_current_version() -> str:
    """读取当前版本号。

    优先级：
    1. DAOFY_VERSION 环境变量
    2. importlib.metadata（pip 安装场景）
    3. pyproject.toml 文件（源码运行兜底）

    Returns:
        版本号字符串，如 "2026.07.18.1"；读取失败返回 "0.0.0"。
    """
    # 1. 环境变量
    env_ver = os.environ.get("DAOFY_VERSION")
    if env_ver:
        return env_ver

    # 2. importlib.metadata — pip 安装后的标准方式
    try:
        return _get_installed_version(PYPI_PACKAGE)
    except PackageNotFoundError:
        pass

    # 3. 读取 pyproject.toml（源码运行兜底）
    pyproject_path = _get_project_root() / "pyproject.toml"
    try:
        with open(pyproject_path, "r", encoding="utf-8") as f:
            for line in f:
                line_stripped = line.strip()
                if line_stripped.startswith("version ="):
                    parts = line_stripped.split("=", 1)
                    if len(parts) == 2:
                        ver = parts[1].strip().strip('"').strip("'")
                        if ver:
                            return ver
        logger.debug("pyproject.toml 中未找到 version 字段")
    except Exception as e:
        logger.warning("读取版本号失败: %s", e)

    return os.environ.get("DAOFY_VERSION", "0.0.0")


def compare_versions(a: str, b: str) -> int:
    """比较两个 YYYY.MM.DD 版本号。

    Args:
        a: 版本号 A
        b: 版本号 B

    Returns:
        1  if a > b
        0  if a == b
        -1 if a < b
    """
    try:
        parts_a = [int(x) for x in a.split(".")]
        parts_b = [int(x) for x in b.split(".")]
        # 补齐到相同长度
        max_len = max(len(parts_a), len(parts_b))
        parts_a += [0] * (max_len - len(parts_a))
        parts_b += [0] * (max_len - len(parts_b))
        for pa, pb in zip(parts_a, parts_b):
            if pa > pb:
                return 1
            if pa < pb:
                return -1
        return 0
    except (ValueError, AttributeError):
        logger.warning(f"版本号格式异常: a={a!r}, b={b!r}，回退字符串比较")
        # 回退：字符串比较
        if a > b:
            return 1
        if a < b:
            return -1
        return 0


# ============================================================
# GitHub API 查询（复用 install_mcp.py 的镜像回退模式）
# ============================================================

def _build_mirror_urls(url: str) -> list[str]:
    """将 GitHub URL 扩展为多镜像 URL 列表（原始源 + 国内代理）。"""
    urls: list[str] = []
    for m in GITHUB_MIRRORS:
        if not m:
            urls.append(url)
        else:
            urls.append(f"{m}/{url}")
    # 去重（保留顺序）
    seen: set[str] = set()
    result: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


def _retry_urlopen(
    url: str,
    headers: Optional[dict] = None,
    timeout: int = REQUEST_TIMEOUT,
    max_retry: int = MAX_RETRY,
) -> bytes:
    """带重试的 urllib 请求。"""
    last_err: Optional[Exception] = None
    for attempt in range(1, max_retry + 1):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < max_retry:
                wait = RETRY_DELAY * min(attempt, 5)
                logger.debug(f"请求失败(第{attempt}次): {e}，{wait}秒后重试...")
                import time
                time.sleep(wait)
    raise last_err  # type: ignore[misc]


# ============================================================
# 公开 API
# ============================================================

def fetch_latest_release(timeout: int = REQUEST_TIMEOUT) -> Optional[dict]:
    """查询 GitHub 最新 Release 信息。

    Args:
        timeout: 单次请求超时秒数

    Returns:
        dict 包含 tag_name, html_url, body 等字段；失败返回 None。
    """
    api_urls = _build_mirror_urls(RELEASE_API)
    last_err: Optional[Exception] = None
    for api_url in api_urls:
        try:
            data = json.loads(
                _retry_urlopen(
                    api_url,
                    headers={"User-Agent": "daofy-updater"},
                    timeout=timeout,
                ).decode("utf-8")
            )
            return data
        except urllib.error.HTTPError as e:
            last_err = e
            # 分类 HTTP 错误
            if e.code == 403:
                logger.warning("GitHub API 访问受限(403): %s — 可能是网络问题或 rate limit", api_url)
            elif e.code == 404:
                logger.warning("GitHub Release 不存在(404): %s", api_url)
            else:
                logger.debug("从镜像获取 Release 信息失败: %s — HTTP %d", api_url, e.code)
            continue
        except Exception as e:
            last_err = e
            logger.debug("从镜像获取 Release 信息失败: %s — %s", api_url, _categorize_request_error(e))
            continue
    if last_err:
        error_hint = _categorize_request_error(last_err)
        logger.warning("所有镜像获取 Release 信息均失败: %s", error_hint)
    return None


def get_latest_version() -> Optional[str]:
    """查询 GitHub 最新 Release 版本号。

    Returns:
        版本号字符串（如 "2026.06.15"），失败返回 None。
    """
    data = fetch_latest_release()
    if data:
        return data.get("tag_name")
    return None


def _categorize_request_error(err: Exception) -> str:
    """将请求错误分类为用户友好的中文提示。

    Args:
        err: 异常对象

    Returns:
        用户友好的错误描述
    """
    err_str = str(err).lower()

    # Rate limit (GitHub 403)
    if "403" in err_str or "rate limit" in err_str or "abuse" in err_str:
        return "GitHub API 访问受限（可能是网络问题或请求过于频繁）"

    # 网络连接问题
    if any(kw in err_str for kw in (
        "timed out", "timeout", "connection refused",
        "connection reset", "connection abort",
    )):
        return "网络连接超时或被拒绝，请检查网络连接"

    # DNS 解析失败
    if any(kw in err_str for kw in (
        "resolve", "name or service not known",
        "getaddrinfo", "nodename nor servname",
    )):
        return "无法解析主机地址，请检查 DNS 或网络连接"

    # 被墙/代理失败
    if any(kw in err_str for kw in (
        "ssl", "certificate", "eof", "connection reset by peer",
    )):
        return "网络连接异常（可能是代理或防火墙问题）"

    # 默认
    return f"请求失败: {err}"


def fetch_pypi_version(timeout: int = REQUEST_TIMEOUT) -> Optional[str]:
    """查询 PyPI 最新版本号（无需认证，国内可访问）。

    Args:
        timeout: 单次请求超时秒数

    Returns:
        版本号字符串（如 "2026.07.17"），失败返回 None。
    """
    for mirror in PYPI_MIRRORS:
        try:
            if mirror:
                url = f"{mirror}/pypi/{PYPI_PACKAGE}/json"
            else:
                url = PYPI_JSON_URL
            data = json.loads(
                _retry_urlopen(
                    url,
                    headers={"User-Agent": "daofy-updater"},
                    timeout=timeout,
                ).decode("utf-8")
            )
            version = data.get("info", {}).get("version")
            if version:
                logger.debug("从 PyPI 获取版本成功: %s (mirror: %s)", version, mirror or "official")
                return version
        except Exception as e:
            logger.debug("从 PyPI 获取版本失败: %s — %s", url, e)
            continue
    logger.warning("所有 PyPI 镜像获取版本均失败")
    return None


def check_for_update() -> Optional[dict]:
    """检查是否有新版本可用。

    根据安装方式自动选择版本源：
    - pip 安装 → 优先查询 PyPI（无需认证，国内可访问）
    - git 安装 → 查询 GitHub Release

    Returns:
        dict 包含 current, latest, update_available, release_url, source；
        查询失败返回 None。
    """
    current = get_current_version()
    latest = None
    source = "github"  # 默认来源

    # pip 安装：优先查询 PyPI（无需认证，无 rate limit）
    if is_pip_installation():
        latest = fetch_pypi_version()
        if latest:
            source = "pypi"
            logger.debug("pip 安装: 从 PyPI 获取版本 %s", latest)
        else:
            # PyPI 失败，回退到 GitHub
            logger.info("PyPI 查询失败，回退到 GitHub")
            latest = get_latest_version()
    else:
        # git 安装或未知：查询 GitHub
        latest = get_latest_version()

    if latest is None:
        return None

    # 去除版本号前的 v 前缀（如果有）
    latest_clean = latest.lstrip("vV")

    available = compare_versions(latest_clean, current) > 0

    result = {
        "current": current,
        "latest": latest_clean,
        "update_available": available,
        "source": source,
        "release_url": f"https://github.com/{RELEASE_REPO}/releases/tag/{latest}",
    }
    return result


# ============================================================
# 安装方式检测
# ============================================================

# ============================================================
# 异步自动重试版本检查（类似 code_hosting git_push_retry 模式）
# ============================================================

# 全局缓存 — 最近一次成功的结果
_update_cache: Optional[dict] = None
_update_cache_time: float = 0.0
_UPDATE_CACHE_TTL = 3600  # 1 小时缓存


def _get_cached_result() -> Optional[dict]:
    """获取缓存的版本检查结果（TTL 内有效）。"""
    if _update_cache is not None:
        elapsed = _time.monotonic() - _update_cache_time
        if elapsed < _UPDATE_CACHE_TTL:
            return _update_cache
    return None


def get_cached_update_result() -> Optional[dict]:
    """公开版 — 获取缓存的版本检查结果。

    Returns:
        缓存的版本检查结果 dict，或 None（无缓存/已过期）。
    """
    return _get_cached_result()


def _set_cached_result(result: Optional[dict]) -> None:
    """设置版本检查缓存。"""
    global _update_cache, _update_cache_time
    _update_cache = result
    _update_cache_time = _time.monotonic()


def check_for_update_retry(**kwargs) -> dict:
    """异步自动重试版本检查 — 后台线程运行，支持进度回调和取消。

    遵循 code_hosting git_push_retry 模式。
    通过 AsyncTaskManager 提交到后台线程，自动重试直到成功或达到最大次数。

    Args:
        **kwargs: 由 AsyncTaskManager 注入的回调参数：
            _progress_callback: 进度回调函数
            _cancellation_check: 取消检查函数
            _task_id: 任务 ID

    Returns:
        dict: 版本检查结果（与 check_for_update 格式一致），全部重试失败时返回 error dict。
    """
    progress_cb = kwargs.get('_progress_callback')
    cancel_check = kwargs.get('_cancellation_check')

    last_error: Optional[str] = None

    for attempt in range(1, MAX_RETRIES + 1):
        # 检查取消
        if cancel_check:
            try:
                cancel_check()
            except Exception:
                return {"error": "版本检查任务已取消", "status": "cancelled"}

        # 先检查缓存是否有效
        cached = _get_cached_result()
        if cached is not None:
            if progress_cb:
                progress_cb(100, f"使用缓存版本信息（{cached.get('current', '?')}）")
            logger.info("版本检查命中缓存")
            return cached

        # 报告进度
        pct = (attempt / MAX_RETRIES) * 100
        if progress_cb:
            if attempt == 1:
                progress_cb(pct, "正在检查版本更新...")
            else:
                eta_remaining = ((MAX_RETRIES - attempt + 1) * RETRY_INTERVAL) // 60
                progress_cb(
                    pct,
                    f"版本检查第 {attempt}/{MAX_RETRIES} 次尝试"
                    f"{'，失败后等待重试' if last_error else ''}"
                    f"{'，预计还需 ~' + str(eta_remaining) + 'min' if eta_remaining > 0 else ''}"
                )

        # 执行版本检查
        try:
            result = check_for_update()
        except Exception as e:
            result = None
            last_error = str(e)
            logger.warning(f"版本检查异常(第{attempt}次): {e}")

        if result is not None:
            # 成功：缓存结果并返回
            _set_cached_result(result)
            if progress_cb:
                if result.get("update_available"):
                    progress_cb(100, f"发现新版本 v{result['latest']}（当前 v{result['current']}）")
                else:
                    progress_cb(100, f"已是最新版本: v{result['current']}")
            logger.info(
                "版本检查成功: %s (第%d次尝试)",
                "有更新" if result.get("update_available") else "已是最新",
                attempt,
            )
            return result

        last_error = "所有镜像获取 Release 信息均失败"

        # 还有重试次数：等待后重试
        if attempt < MAX_RETRIES:
            wait = RETRY_INTERVAL
            logger.info(f"版本检查失败(第{attempt}次)，{wait}秒后自动重试...")
            if progress_cb:
                eta_total = (RETRY_INTERVAL * MAX_RETRIES) // 60
                progress_cb(
                    pct,
                    f"第 {attempt}/{MAX_RETRIES} 次失败，{wait}秒后重试"
                    f" | 预计最长 ~{eta_total}min"
                )
            _time.sleep(wait)

    # 全部重试失败
    error_msg = f"版本检查失败（{MAX_RETRIES}次重试，约{ETA_MINUTES}分钟）: {last_error}"
    logger.error(error_msg)
    return {
        "error": error_msg,
        "status": "failed",
        "attempts": MAX_RETRIES,
    }


def is_git_installation() -> bool:
    """检测当前是否为 git 源码安装（存在 .git 目录且有 git 命令）。"""
    git_dir = _get_project_root() / ".git"
    if not git_dir.exists():
        return False
    # 检查 git 命令是否可用
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["where", "git"],
                capture_output=True, timeout=TIMEOUT_SUBPROCESS_SHORT, check=True,
            )
        else:
            subprocess.run(
                ["which", "git"],
                capture_output=True, timeout=TIMEOUT_SUBPROCESS_SHORT, check=True,
            )
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def is_pip_installation() -> bool:
    """检测是否为 pip 安装（site-packages 中）。"""
    # 如果当前文件在 site-packages 路径下，则是 pip 安装
    module_path = Path(__file__).resolve()
    return "site-packages" in module_path.parts


# ============================================================
# git pull 更新（同步版 — 用于后台线程）
# ============================================================

def git_pull_update_sync() -> dict:
    """同步执行 git pull 更新（用于 AsyncTaskManager 后台线程）。

    Returns:
        dict 包含 success, updated, message, output。
    """
    project_root = _get_project_root()
    try:
        logger.info("正在执行 git pull 更新（同步）...")
        proc_env = os.environ.copy()
        proc_env["GIT_TERMINAL_PROMPT"] = "0"
        result = subprocess.run(
            ["git", "pull"],
            cwd=str(project_root),
            capture_output=True,
            timeout=TIMEOUT_UPDATER_GIT_PULL,
            env=proc_env,
        )
        stdout_text = result.stdout.decode("utf-8", errors="replace").strip()
        stderr_text = result.stderr.decode("utf-8", errors="replace").strip()

        if result.returncode == 0:
            if "Already up to date" in stdout_text:
                return {
                    "success": True,
                    "updated": False,
                    "message": "已经是最新版本，无需更新。",
                    "output": stdout_text,
                }
            return {
                "success": True,
                "updated": True,
                "message": "更新成功！请重启 Daofy 或 AI Agent 使新版本生效。",
                "output": stdout_text,
            }
        else:
            error_msg = stderr_text or stdout_text
            return {
                "success": False,
                "updated": False,
                "message": f"git pull 失败: {error_msg}",
                "output": error_msg,
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "updated": False,
            "message": "git pull 超时（>60秒），请检查网络连接后重试。",
            "output": "",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "updated": False,
            "message": "未找到 git 命令，请安装 Git 后重试。",
            "output": "",
        }
    except Exception as e:
        logger.error(f"git pull 异常: {e}", exc_info=True)
        return {
            "success": False,
            "updated": False,
            "message": f"更新失败: {e}",
            "output": str(e),
        }


# ============================================================
# 后台自动重试 git pull 更新（类似 code_hosting git_push_retry）
# ============================================================

# 更新重试参数
UPDATE_RETRY_INTERVAL = 60       # 两次重试间隔（60秒）
UPDATE_MAX_RETRIES = 10           # 最大重试次数（≈10分钟）


def _do_retry_update(**kwargs) -> dict:
    """后台自动重试 git pull 更新 — 支持进度回调和取消。

    遵循 code_hosting git_push_retry 模式。
    通过 AsyncTaskManager 提交到后台线程，自动重试直到成功或达到最大次数。

    Args:
        **kwargs: 由 AsyncTaskManager 注入的回调参数：
            _progress_callback: 进度回调函数
            _cancellation_check: 取消检查函数
            _task_id: 任务 ID

    Returns:
        dict: git pull 更新结果。
    """
    progress_cb = kwargs.get('_progress_callback')
    cancel_check = kwargs.get('_cancellation_check')

    last_error: Optional[str] = None

    for attempt in range(1, UPDATE_MAX_RETRIES + 1):
        # 检查取消
        if cancel_check:
            try:
                cancel_check()
            except Exception:
                return {"error": "更新任务已取消", "status": "cancelled"}

        # 报告进度
        pct = (attempt / UPDATE_MAX_RETRIES) * 100
        if progress_cb:
            if attempt == 1:
                progress_cb(pct, "正在执行 git pull 更新...")
            else:
                progress_cb(
                    pct,
                    f"git pull 第 {attempt}/{UPDATE_MAX_RETRIES} 次尝试"
                    f"{'，失败后等待重试' if last_error else ''}"
                )

        # 执行 git pull
        try:
            result = git_pull_update_sync()
        except Exception as e:
            result = None
            last_error = str(e)
            logger.warning(f"git pull 异常(第{attempt}次): {e}")

        if result is not None and result.get("success"):
            if progress_cb:
                if result.get("updated"):
                    progress_cb(100, f"更新成功！请重启 Daofy 使新版本生效。")
                else:
                    progress_cb(100, "已经是最新版本，无需更新。")
            logger.info("git pull 更新成功 (第%d次尝试)", attempt)
            return result

        if result is not None:
            last_error = result.get("message", "未知错误")

        # 还有重试次数：等待后重试
        if attempt < UPDATE_MAX_RETRIES:
            wait = UPDATE_RETRY_INTERVAL
            logger.info(f"git pull 失败(第{attempt}次)，{wait}秒后自动重试...")
            if progress_cb:
                eta_total = (UPDATE_RETRY_INTERVAL * UPDATE_MAX_RETRIES) // 60
                progress_cb(
                    pct,
                    f"第 {attempt}/{UPDATE_MAX_RETRIES} 次失败，{wait}秒后重试"
                    f" | 预计最长 ~{eta_total}min"
                )
            _time.sleep(wait)

    # 全部重试失败
    error_msg = f"git pull 更新失败（{UPDATE_MAX_RETRIES}次重试）: {last_error}"
    logger.error(error_msg)
    return {"success": False, "updated": False, "message": error_msg, "status": "failed"}


# ============================================================
# git pull 更新（异步版 — 用于直接 await 调用）
# ============================================================

async def git_pull_update() -> dict:
    """执行 git pull 更新代码。

    Returns:
        dict 包含 success, message, output。
    """
    project_root = _get_project_root()
    try:
        logger.info("正在执行 git pull 更新...")
        proc = await asyncio.create_subprocess_exec(
            "git", "pull",
            cwd=str(project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=TIMEOUT_UPDATER_GIT_PULL,
        )

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode == 0:
            # 检测是否有实际更新
            if "Already up to date" in stdout_text:
                return {
                    "success": True,
                    "updated": False,
                    "message": "已经是最新版本，无需更新。",
                    "output": stdout_text,
                }
            return {
                "success": True,
                "updated": True,
                "message": "更新成功！请重启 Daofy 或 AI Agent 使新版本生效。",
                "output": stdout_text,
            }
        else:
            error_msg = stderr_text or stdout_text
            return {
                "success": False,
                "updated": False,
                "message": f"git pull 失败: {error_msg}",
                "output": error_msg,
            }
    except asyncio.TimeoutError:
        return {
            "success": False,
            "updated": False,
            "message": "git pull 超时（>60秒），请检查网络连接后重试。",
            "output": "",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "updated": False,
            "message": "未找到 git 命令，请安装 Git 后重试。",
            "output": "",
        }
    except Exception as e:
        logger.error(f"git pull 异常: {e}", exc_info=True)
        return {
            "success": False,
            "updated": False,
            "message": f"更新失败: {e}",
            "output": str(e),
        }
