"""代码托管平台统一工具 — 兼容 Gitea / GitHub / GitLab / Gitee / GitCode + Git 本地操作

通过 action 参数分发操作，platform 参数切换后端。
支持以下平台:
  - gitea   : 自托管 Gitea
  - github  : GitHub (github.com)
  - gitlab  : GitLab CE/EE (gitlab.com)
  - gitee   : Gitee 码云 (gitee.com) — API v5，GitHub 兼容风格
  - gitcode : GitCode (gitcode.net) — GitLab 兼容风格

API 认证方式:
  平台      | 认证头                          | base_url 示例
  ----------|---------------------------------|------------------------
  gitea     | Authorization: token {token}     | https://your-gitea.com
  github    | Authorization: Bearer {token}    | https://api.github.com
  gitlab    | PRIVATE-TOKEN: {token}           | https://gitlab.com
  gitee     | Authorization: Bearer {token}    | https://gitee.com/api/v5
  gitcode   | PRIVATE-TOKEN: {token}           | https://gitcode.net

Git 相关操作（无需 platform 参数）:
  - git_clone  克隆远程仓库（支持 GitHub 镜像源）
  - git_status 查看仓库状态
  - git_diff   查看工作区/暂存区差异
  - git_show   查看提交或对象内容
  - git_log    查看提交历史
  - git_add    暂存文件
  - git_commit 创建提交
  - git_fetch  拉取远程引用
  - git_pull   拉取并合并远程分支
  - git_branch / git_switch / git_merge / git_restore / git_unstage / git_stash / git_tag
  - git_push   推送到远程（依赖用户自身的网络/代理/SSH配置）

GitHub / Gitee 国内访问:
  - 拉取: git_clone 支持 mirror 参数指定镜像源
  - 推送: 依赖用户自身配置（SSH/HTTPS代理/VPN），工具不做假设

用法:
  code_hosting(platform="gitee", action="create_issue", ...)
  code_hosting(platform="gitcode", action="list_issues", ...)
  code_hosting(action="git_clone", repo_url="https://github.com/...", mirror="https://hub.fastgit.xyz")
  code_hosting(action="git_push", dir=".", branch="main")
"""

import base64
import logging
import os
import re
import subprocess
import time
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from ..constants import (
    MAX_RETRIES_GIT_PUSH,
    RETRY_INTERVAL_GIT_PUSH,
    TIMEOUT_GIT_FETCH_PULL,
    TIMEOUT_GIT_LOCAL_SLOW,
    TIMEOUT_GIT_PUSH,
    TIMEOUT_GIT_QUICK,
    TIMEOUT_GIT_REMOTE_SYNC,
    TIMEOUT_GIT_REV_PARSE,
    TIMEOUT_NETWORK_REQUEST,
)

# 复用项目已有的异步任务管理器
try:
    from ..services.knowledge_base.async_task_manager import get_task_manager
except ImportError:
    get_task_manager = None

logger = logging.getLogger(__name__)

# ============================================================
# 路径安全 — 阻止目录遍历
# ============================================================

_ALLOWED_BASE = os.path.abspath(".")  # 默认：当前工作目录


def _resolve_safe_dir(dir_path: str) -> str:
    """解析用户传入的目录路径，阻止路径遍历攻击。

    规则：
    - 相对路径基于 _ALLOWED_BASE（当前工作目录）resolve，防止 .. 逃逸
    - 绝对路径允许指向现有本地仓库/目录，但不会自动创建
    - 相对路径不存在时自动创建，便于 git_clone 等操作
    - 如果无法判定安全，抛出明确错误，避免回退到当前仓库误操作

    Args:
        dir_path: 用户传入的目录路径

    Returns:
        安全的绝对路径
    """
    if not dir_path:
        return _ALLOWED_BASE

    if '\0' in dir_path:
        raise ValueError("dir 参数包含非法字符")

    # 绝对路径：支持已有本地仓库/目录，但不静默创建任意系统路径
    if os.path.isabs(dir_path):
        resolved = os.path.normpath(dir_path)
        if not os.path.exists(resolved):
            raise ValueError(f"dir 绝对路径不存在: {resolved}")
        if not os.path.isdir(resolved):
            raise ValueError(f"dir 不是目录: {resolved}")
        return resolved

    # 相对路径：基于 _ALLOWED_BASE resolve，阻止 .. 逃逸
    resolved = os.path.abspath(os.path.join(_ALLOWED_BASE, dir_path))
    resolved = os.path.normpath(resolved)
    resolved_lower = resolved.lower()
    allowed_lower = os.path.normpath(_ALLOWED_BASE).lower()

    if not resolved_lower.startswith(allowed_lower + os.sep) and resolved_lower != allowed_lower:
        logger.warning("路径遍历拦截: %s -> %s (base: %s)", dir_path, resolved, _ALLOWED_BASE)
        raise ValueError("dir 参数不能逃逸当前工作目录")

    if not os.path.exists(resolved):
        try:
            os.makedirs(resolved, exist_ok=True)
        except OSError as exc:
            raise ValueError(f"无法创建 dir 目录: {resolved}") from exc
    if not os.path.isdir(resolved):
        raise ValueError(f"dir 不是目录: {resolved}")

    return resolved


# ============================================================
# 平台 API 路径模板
# ============================================================

_API_PATHS = {
    "gitea": {
        "create_token": "/api/v1/users/{username}/tokens",
        "list_labels":  "/api/v1/repos/{owner}/{repo}/labels",
        "create_label": "/api/v1/repos/{owner}/{repo}/labels",
        "create_issue": "/api/v1/repos/{owner}/{repo}/issues",
        "edit_issue":   "/api/v1/repos/{owner}/{repo}/issues/{index}",
        "add_comment":  "/api/v1/repos/{owner}/{repo}/issues/{index}/comments",
        "list_issues":  "/api/v1/repos/{owner}/{repo}/issues",
        "list_pulls":   "/api/v1/repos/{owner}/{repo}/pulls",
        "create_pull":  "/api/v1/repos/{owner}/{repo}/pulls",
        "get_pull":     "/api/v1/repos/{owner}/{repo}/pulls/{index}",
        "edit_pull":    "/api/v1/repos/{owner}/{repo}/pulls/{index}",
        "merge_pull":   "/api/v1/repos/{owner}/{repo}/pulls/{index}/merge",
        "list_releases": "/api/v1/repos/{owner}/{repo}/releases",
        "create_release": "/api/v1/repos/{owner}/{repo}/releases",
        "get_release":  "/api/v1/repos/{owner}/{repo}/releases/{release_id}",
        "get_release_by_tag": "/api/v1/repos/{owner}/{repo}/releases/tags/{tag_name}",
        "edit_release": "/api/v1/repos/{owner}/{repo}/releases/{release_id}",
        "delete_release": "/api/v1/repos/{owner}/{repo}/releases/{release_id}",
    },
    "github": {
        "create_token": None,  # GitHub 不支持 API 创建 token
        "list_labels":  "/repos/{owner}/{repo}/labels",
        "create_label": "/repos/{owner}/{repo}/labels",
        "create_issue": "/repos/{owner}/{repo}/issues",
        "edit_issue":   "/repos/{owner}/{repo}/issues/{index}",
        "add_comment":  "/repos/{owner}/{repo}/issues/{index}/comments",
        "list_issues":  "/repos/{owner}/{repo}/issues",
        "list_pulls":   "/repos/{owner}/{repo}/pulls",
        "create_pull":  "/repos/{owner}/{repo}/pulls",
        "get_pull":     "/repos/{owner}/{repo}/pulls/{index}",
        "edit_pull":    "/repos/{owner}/{repo}/pulls/{index}",
        "merge_pull":   "/repos/{owner}/{repo}/pulls/{index}/merge",
        "list_releases": "/repos/{owner}/{repo}/releases",
        "create_release": "/repos/{owner}/{repo}/releases",
        "get_release":  "/repos/{owner}/{repo}/releases/{release_id}",
        "get_release_by_tag": "/repos/{owner}/{repo}/releases/tags/{tag_name}",
        "edit_release": "/repos/{owner}/{repo}/releases/{release_id}",
        "delete_release": "/repos/{owner}/{repo}/releases/{release_id}",
    },
    "gitlab": {
        "create_token": None,
        "list_labels":  "/api/v4/projects/{encoded}/labels",
        "create_label": "/api/v4/projects/{encoded}/labels",
        "create_issue": "/api/v4/projects/{encoded}/issues",
        "edit_issue":   "/api/v4/projects/{encoded}/issues/{index}",
        "add_comment":  "/api/v4/projects/{encoded}/issues/{index}/notes",
        "list_issues":  "/api/v4/projects/{encoded}/issues",
        "list_pulls":   "/api/v4/projects/{encoded}/merge_requests",
        "create_pull":  "/api/v4/projects/{encoded}/merge_requests",
        "get_pull":     "/api/v4/projects/{encoded}/merge_requests/{index}",
        "edit_pull":    "/api/v4/projects/{encoded}/merge_requests/{index}",
        "merge_pull":   "/api/v4/projects/{encoded}/merge_requests/{index}/merge",
        "list_releases": "/api/v4/projects/{encoded}/releases",
        "create_release": "/api/v4/projects/{encoded}/releases",
        "get_release":  "/api/v4/projects/{encoded}/releases/{tag_name}",
        "get_release_by_tag": "/api/v4/projects/{encoded}/releases/{tag_name}",
        "edit_release": "/api/v4/projects/{encoded}/releases/{tag_name}",
        "delete_release": "/api/v4/projects/{encoded}/releases/{tag_name}",
    },
    "gitee": {
        "create_token": None,
        "list_labels":  "/repos/{owner}/{repo}/labels",
        "create_label": "/repos/{owner}/{repo}/labels",
        "create_issue": "/repos/{owner}/{repo}/issues",
        "edit_issue":   "/repos/{owner}/{repo}/issues/{number}",
        "add_comment":  "/repos/{owner}/{repo}/issues/{number}/comments",
        "list_issues":  "/repos/{owner}/{repo}/issues",
        "list_pulls":   "/repos/{owner}/{repo}/pulls",
        "create_pull":  "/repos/{owner}/{repo}/pulls",
        "get_pull":     "/repos/{owner}/{repo}/pulls/{number}",
        "edit_pull":    "/repos/{owner}/{repo}/pulls/{number}",
        "merge_pull":   "/repos/{owner}/{repo}/pulls/{number}/merge",
        "list_releases": "/repos/{owner}/{repo}/releases",
        "create_release": "/repos/{owner}/{repo}/releases",
        "get_release":  "/repos/{owner}/{repo}/releases/{release_id}",
        "get_release_by_tag": "/repos/{owner}/{repo}/releases/tags/{tag_name}",
        "edit_release": "/repos/{owner}/{repo}/releases/{release_id}",
        "delete_release": "/repos/{owner}/{repo}/releases/{release_id}",
    },
    "gitcode": {
        "create_token": None,
        "list_labels":  "/api/v4/projects/{encoded}/labels",
        "create_label": "/api/v4/projects/{encoded}/labels",
        "create_issue": "/api/v4/projects/{encoded}/issues",
        "edit_issue":   "/api/v4/projects/{encoded}/issues/{index}",
        "add_comment":  "/api/v4/projects/{encoded}/issues/{index}/notes",
        "list_issues":  "/api/v4/projects/{encoded}/issues",
        "list_pulls":   "/api/v4/projects/{encoded}/merge_requests",
        "create_pull":  "/api/v4/projects/{encoded}/merge_requests",
        "get_pull":     "/api/v4/projects/{encoded}/merge_requests/{index}",
        "edit_pull":    "/api/v4/projects/{encoded}/merge_requests/{index}",
        "merge_pull":   "/api/v4/projects/{encoded}/merge_requests/{index}/merge",
        "list_releases": "/api/v4/projects/{encoded}/releases",
        "create_release": "/api/v4/projects/{encoded}/releases",
        "get_release":  "/api/v4/projects/{encoded}/releases/{tag_name}",
        "get_release_by_tag": "/api/v4/projects/{encoded}/releases/{tag_name}",
        "edit_release": "/api/v4/projects/{encoded}/releases/{tag_name}",
        "delete_release": "/api/v4/projects/{encoded}/releases/{tag_name}",
    },
}

# ============================================================
# 标签定义 — 软件流程四维分类
# ============================================================

ISSUE_LABELS = {
    "priority": [
        {"name": "优先级/紧急", "color": "e53e3e", "description": "需要立即处理", "exclusive": True},
        {"name": "优先级/高",   "color": "ed8936", "description": "重要问题，应尽快处理", "exclusive": True},
        {"name": "优先级/中",   "color": "ecc94b", "description": "常规问题", "exclusive": True},
        {"name": "优先级/低",   "color": "a0aec0", "description": "可延后处理", "exclusive": True},
    ],
    "review": [
        {"name": "审阅/待审阅", "color": "4299e1", "description": "等待代码审阅", "exclusive": True},
        {"name": "审阅/需修改", "color": "ed8936", "description": "审阅发现问题，需要修改", "exclusive": True},
        {"name": "审阅/已通过", "color": "48bb78", "description": "审阅通过", "exclusive": True},
        {"name": "审阅/已拒绝", "color": "e53e3e", "description": "审阅不通过", "exclusive": True},
    ],
    "status": [
        {"name": "状态/待确认",   "color": "a0aec0", "description": "待确认是否有效", "exclusive": True},
        {"name": "状态/处理中",   "color": "4299e1", "description": "正在修复中", "exclusive": True},
        {"name": "状态/已验证",   "color": "48bb78", "description": "修复已验证", "exclusive": True},
        {"name": "状态/已关闭",   "color": "718096", "description": "问题已关闭", "exclusive": True},
        {"name": "状态/无法复现", "color": "9f7aea", "description": "无法复现", "exclusive": True},
    ],
    "type": [
        {"name": "类型/缺陷", "color": "e53e3e", "description": "功能缺陷", "exclusive": True},
        {"name": "类型/需求", "color": "48bb78", "description": "新功能需求", "exclusive": True},
        {"name": "类型/改进", "color": "4299e1", "description": "优化/重构", "exclusive": True},
        {"name": "类型/文档", "color": "ecc94b", "description": "文档相关", "exclusive": True},
        {"name": "类型/测试", "color": "9f7aea", "description": "测试相关", "exclusive": True},
    ],
}


# ============================================================
# HTTP 请求（带指数退避重试）
# ============================================================

def _request(base_url, token, method, path, body=None, params=None, platform="gitea", basic_auth=None, _retries=3):
    """发送 HTTP 请求，支持指数退避重试（5xx 和网络错误）。

    注意：_retries 是内部参数，外部调用者不应使用。
    """
    url = f"{base_url.rstrip('/')}{path}"
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urlencode(clean)

    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if basic_auth:
        raw = f"{basic_auth[0]}:{basic_auth[1]}".encode()
        headers["Authorization"] = f"Basic {base64.b64encode(raw).decode()}"
    elif platform in ("github", "gitee"):
        headers["Authorization"] = f"Bearer {token}"
        if platform == "github":
            headers["X-GitHub-Api-Version"] = "2022-11-28"
    elif platform in ("gitlab", "gitcode"):
        headers["PRIVATE-TOKEN"] = token
    else:
        headers["Authorization"] = f"token {token}"

    if not token and not basic_auth:
        raise ValueError("请提供 token 或 basic_auth 认证信息")

    data = json.dumps(body).encode("utf-8") if body else None
    req = Request(url, data=data, headers=headers, method=method)

    last_exception = None
    for attempt in range(_retries):
        try:
            with urlopen(req, timeout=TIMEOUT_NETWORK_REQUEST) as resp:
                raw = resp.read().decode("utf-8")
                if resp.status == 204:
                    return {"success": True}
                return json.loads(raw) if raw else {"success": True}
        except HTTPError as e:
            last_exception = e
            detail = e.read().decode("utf-8", errors="replace") if e.fp else ""
            # 5xx 错误可重试，4xx 不重试
            if e.code >= 500 and attempt < _retries - 1:
                wait = 2 ** attempt
                logger.warning("API %d 错误 (第 %d/%d 次)，%ds 后重试", e.code, attempt + 1, _retries, wait)
                time.sleep(wait)
                continue
            # 脱敏：错误详情中可能包含 token 信息
            safe_detail = detail[:300]
            raise RuntimeError(f"API {e.code}: {safe_detail}")
        except URLError as e:
            last_exception = e
            if attempt < _retries - 1:
                wait = 2 ** attempt
                logger.warning("网络错误 (第 %d/%d 次)，%ds 后重试: %s", attempt + 1, _retries, wait, e)
                time.sleep(wait)
                continue
            raise RuntimeError(f"无法连接 {base_url}: {e}")


# ============================================================
# 统一入口
# ============================================================

def code_hosting(**kwargs) -> dict:
    """代码托管平台统一操作入口。

    platform: gitea / github / gitlab / gitee / gitcode（默认 gitea）
    action:
      - create_token  创建访问令牌（仅 Gitea）
      - init_labels   批量初始化四维流程标签
      - create_issue  创建工单
      - get_issue     查看工单
      - edit_issue    修改工单
      - set_labels    设置工单标签
      - create/get/list/edit_pull       PR/MR 操作
      - create/get/list/edit/delete_release  Release 操作
      - close_issue   关闭工单
      - add_comment   添加评论
      - list_issues   查询工单列表
      - git_status/diff/show/log/add/commit/fetch/pull/branch/switch/merge/restore/unstage/stash/tag/push/clone
    """
    platform = kwargs.pop("platform", "gitea").lower()
    action = kwargs.pop("action", "")

    if platform not in _API_PATHS:
        return _err(f"不支持的平台: {platform}，可选: {', '.join(_API_PATHS.keys())}")
    handler = _DISPATCH.get(action)
    if not handler:
        return _err(f"不支持的操作: {action}，可选: {', '.join(_DISPATCH.keys())}")

    try:
        # 前置校验：API 操作必须的参数
        if action in _API_ACTIONS:
            if "base_url" not in kwargs:
                return _err(f"{action} 需要 base_url 参数")
            if action != "create_token" and "token" not in kwargs:
                return _err(f"{action} 需要 token 参数")
        return handler(platform, **kwargs)
    except Exception as e:
        logger.exception("code_hosting error")
        return _err(str(e))


_API_ACTIONS = {
    "create_token",
    "init_labels",
    "create_issue",
    "get_issue",
    "edit_issue",
    "set_labels",
    "create_pull",
    "get_pull",
    "list_pulls",
    "edit_pull",
    "merge_pull",
    "close_pull",
    "reopen_pull",
    "create_release",
    "get_release",
    "list_releases",
    "edit_release",
    "delete_release",
    "close_issue",
    "add_comment",
    "list_issues",
}


_DISPATCH = {}


def _reg(name):
    """装饰器：注册 action 处理器"""
    def _(fn):
        _DISPATCH[name] = fn
        return fn
    return _


def _err(msg):
    return {"message": msg, "status": "failed"}


def _ok(msg):
    return {"message": msg, "status": "ok"}


def _truncate_output(text: str, limit: int = 12000) -> str:
    """Limit command output so MCP responses stay readable."""
    if text is None:
        return ""
    if limit <= 0 or len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n... <truncated {omitted} chars>"


def _split_ref(ref: str) -> list[str]:
    """Split a user-supplied revision range into safe git args."""
    ref = (ref or "").strip()
    if not ref:
        return []
    if re.search(r"[\r\n\0]", ref):
        raise ValueError("ref 参数包含非法字符")
    parts = ref.split()
    if any(part.startswith("-") for part in parts):
        raise ValueError("ref 参数不能是 Git 选项")
    return parts


def _validate_git_arg(name: str, value: str, *, allow_empty: bool = False) -> str:
    """Validate a user-supplied git argument that appears before '--'."""
    value = (value or "").strip()
    if not value:
        if allow_empty:
            return ""
        raise ValueError(f"{name} 参数不能为空")
    if re.search(r"[\r\n\0]", value):
        raise ValueError(f"{name} 参数包含非法字符")
    if value.startswith("-"):
        raise ValueError(f"{name} 参数不能是 Git 选项")
    return value


def _require_files(kw: dict, action: str) -> list[str]:
    """Return explicit file list for workspace-changing commands."""
    files = kw.get("files") or []
    if not files:
        raise ValueError(f"{action} 需要 files 参数，避免误操作整个工作区")
    return _validate_git_paths(files, action)


def _validate_git_paths(files: list[str], action: str) -> list[str]:
    """Validate user-supplied git pathspecs placed after '--'."""
    if isinstance(files, str) or not isinstance(files, (list, tuple)):
        raise ValueError(f"{action} files 参数必须是路径列表")
    result = []
    for file_path in files:
        if file_path is None:
            raise ValueError(f"{action} files 参数不能包含空路径")
        value = str(file_path)
        if not value:
            raise ValueError(f"{action} files 参数不能包含空路径")
        if re.search(r"[\r\n\0]", value):
            raise ValueError(f"{action} files 参数包含非法字符")
        result.append(value)
    return result


def _coerce_bool(value, default: bool = False) -> bool:
    """Coerce bool-like tool arguments."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def _split_repo(repo: str):
    """将 repo 参数字符串分割为 owner + repo。

    注意：
    - GitHub/Gitea: owner/repo（简单分割，无嵌套）
    - GitLab: group/subgroup/project（支持嵌套组）
      _repo_path 对 GitLab 会做 URL 编码（quote(f"{owner}/{repo}", safe="")），
      所以 nested group 场景也能正确处理。这里的 owner 返回的是最上层组名。
    """
    parts = repo.split("/", 1)
    if len(parts) != 2:
        raise ValueError("仓库格式应为 owner/repo (如 chinawsb/daofy)")
    return parts[0], parts[1]


def _repo_path(platform, action, owner, repo, index=None, **extra):
    tmpl = _API_PATHS[platform].get(action)
    if tmpl is None:
        raise ValueError(f"{platform} 不支持 {action}")
    kw = {"owner": owner, "repo": repo}
    if index is not None:
        # Gitee 用 {number}，其他平台用 {index}
        if platform == "gitee":
            kw["number"] = index
        else:
            kw["index"] = index
    kw.update(extra)
    if "release_id" in extra:
        kw["release_id"] = extra["release_id"]
    if "tag_name" in extra:
        kw["tag_name"] = quote(str(extra["tag_name"]), safe="")
    if platform in ("gitlab", "gitcode") and "{encoded}" in tmpl:
        kw["encoded"] = quote(f"{owner}/{repo}", safe="")
    return tmpl.format(**kw)


def _issue_edit_method(platform):
    """Return the issue update method for each platform family."""
    if platform in ("gitlab", "gitcode"):
        return "PUT"
    return "PATCH"


def _state_filter(platform, state):
    """Map public state names to platform filter values."""
    if platform in ("gitlab", "gitcode") and state == "open":
        return "opened"
    if state == "merged" and platform not in ("gitlab", "gitcode"):
        return "closed"
    return state


def _pull_is_merged(item: dict) -> bool:
    """Return whether a PR/MR response represents a merged item."""
    if item.get("merged") is True:
        return True
    if item.get("merged_at"):
        return True
    return item.get("state") == "merged"


def _state_update_payload(platform, state):
    """Map public state names to platform update payload fields."""
    if not state or state == "all":
        return {}
    if state == "merged":
        raise ValueError("state=merged is read-only; use merge_pull")
    if platform in ("gitlab", "gitcode"):
        if state == "closed":
            return {"state_event": "close"}
        if state == "open":
            return {"state_event": "reopen"}
    return {"state": state}


def _validate_issue_state(state):
    """Reject PR/MR-only states for issue actions."""
    if state == "merged":
        raise ValueError("state=merged is only valid for list_pulls; issues use open/closed/all")


def _issue_body_key(platform):
    """Return the issue body field name used by each platform."""
    if platform in ("gitlab", "gitcode"):
        return "description"
    return "body"


def _label_payload(platform, base_url, token, owner, repo, label_names, allow_empty=False):
    """Build issue label payload for different platforms."""
    label_names = list(label_names or [])
    if not label_names:
        if not allow_empty:
            return {}
        return {"labels": ""} if platform in ("gitlab", "gitcode") else {"labels": []}

    if platform != "gitea":
        if platform in ("gitlab", "gitcode"):
            return {"labels": ",".join(label_names)}
        return {"labels": label_names}

    lp = _repo_path(platform, "list_labels", owner, repo)
    existing = _request(base_url, token, "GET", lp, platform=platform)
    n2id = {lb["name"]: lb["id"] for lb in existing} if isinstance(existing, list) else {}
    unknown = [name for name in label_names if name not in n2id]
    if unknown:
        raise ValueError(f"Gitea labels not found: {', '.join(unknown)}")
    return {"labels": [n2id[name] for name in label_names]}


def _html_url(result):
    """Return the public URL field used by each platform."""
    return result.get("html_url", result.get("web_url", result.get("url", "")))


def _label_names(labels):
    """Return label names from platform issue payloads."""
    names = []
    for label in labels or []:
        if isinstance(label, dict):
            names.append(label.get("name", label.get("title", "")))
        else:
            names.append(str(label))
    return [name for name in names if name]


def _pull_number(result, fallback=""):
    """Return PR/MR number from a platform response."""
    return result.get("number") or result.get("iid") or result.get("id") or fallback


def _pull_payload(platform, kw, require_branches=True):
    """Build create/edit PR or MR payload."""
    payload = {}
    if "title" in kw and kw["title"] is not None:
        payload["title"] = kw["title"]
    if "body" in kw and kw["body"] is not None:
        payload["description" if platform in ("gitlab", "gitcode") else "body"] = kw["body"]
    if require_branches or kw.get("source_branch"):
        source_branch = kw.get("source_branch")
        if not source_branch:
            raise ValueError("create_pull 需要 source_branch 参数")
        payload["source_branch" if platform in ("gitlab", "gitcode") else "head"] = source_branch
    if require_branches or kw.get("target_branch"):
        target_branch = kw.get("target_branch")
        if not target_branch:
            raise ValueError("create_pull 需要 target_branch 参数")
        payload["target_branch" if platform in ("gitlab", "gitcode") else "base"] = target_branch
    payload.update(_state_update_payload(platform, kw.get("state")))
    return payload


def _release_key(platform, kw):
    """Return the release path key for release get/edit/delete actions."""
    tag_name = kw.get("tag_name") or kw.get("tag")
    if platform in ("gitlab", "gitcode"):
        if not tag_name:
            raise ValueError("release 操作需要 tag_name 或 tag 参数")
        return {"tag_name": tag_name}
    release_id = kw.get("release_id")
    if release_id is not None:
        return {"release_id": release_id}
    if tag_name:
        return {"tag_name": tag_name}
    raise ValueError("release 操作需要 release_id、tag_name 或 tag 参数")


def _release_payload(platform, kw, require_tag=False):
    """Build release payload for different platforms."""
    payload = {}
    tag_name = kw.get("tag_name") or kw.get("tag")
    if require_tag and not tag_name:
        raise ValueError("create_release 需要 tag_name 或 tag 参数")
    if tag_name:
        payload["tag_name"] = tag_name
    if kw.get("target_commitish") and platform not in ("gitlab", "gitcode"):
        payload["target_commitish"] = kw["target_commitish"]
    if kw.get("ref") and platform in ("gitlab", "gitcode"):
        payload["ref"] = kw["ref"]
    if kw.get("name"):
        payload["name"] = kw["name"]
    if "body" in kw and kw["body"] is not None:
        payload["description" if platform in ("gitlab", "gitcode") else "body"] = kw["body"]
    if "draft" in kw and platform not in ("gitlab", "gitcode"):
        payload["draft"] = _coerce_bool(kw.get("draft"), False)
    if "prerelease" in kw and platform not in ("gitlab", "gitcode"):
        payload["prerelease"] = _coerce_bool(kw.get("prerelease"), False)
    return payload


def _resolve_release_id(base_url, token, platform, owner, repo, key):
    """Resolve a tag-based release key to a numeric release id when needed."""
    if "release_id" in key or platform in ("gitlab", "gitcode"):
        return key
    tag_name = key.get("tag_name")
    if not tag_name:
        return key
    path = _repo_path(platform, "get_release_by_tag", owner, repo, tag_name=tag_name)
    result = _request(base_url, token, "GET", path, platform=platform)
    release_id = result.get("id")
    if release_id is None:
        raise ValueError(f"release not found by tag: {tag_name}")
    return {"release_id": release_id}


# ============================================================
# Action: create_token
# ============================================================

@_reg("create_token")
def _act_create_token(platform, **kw):
    base_url, username, password = kw["base_url"], kw["username"], kw["password"]
    name = kw.get("token_name", "delphi-mcp")

    path = _repo_path(platform, "create_token", None, None, username=username)
    body = {"name": name, "scopes": ["write:repository", "write:issue"]}
    result = _request(base_url, "", "POST", path, body=body, platform=platform,
                      basic_auth=(username, password))
    token_val = result.get("sha1") or result.get("token", "")
    masked = "%s...%s" % (token_val[:8], token_val[-4:]) if len(token_val) > 12 else "***"
    d = _ok("token created | platform: %s | name: %s | masked: %s" % (platform, result.get('name', name), masked))
    d["token"] = token_val
    return d


# ============================================================
# Action: init_labels
# ============================================================

@_reg("init_labels")
def _act_init_labels(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])

    list_path = _repo_path(platform, "list_labels", owner, repo)
    existing = _request(base_url, token, "GET", list_path, platform=platform)
    exist_names = {lb.get("name") for lb in existing} if isinstance(existing, list) else set()

    created = 0
    skipped = 0
    for group in ISSUE_LABELS.values():
        for label in group:
            if label["name"] in exist_names:
                skipped += 1
                continue
            cp = _repo_path(platform, "create_label", owner, repo)
            _request(base_url, token, "POST", cp, body=label, platform=platform)
            created += 1

    return _ok(f"labels initialized | created: {created} | skipped: {skipped} | total: {created + skipped}")


# ============================================================
# Action: create_issue
# ============================================================

@_reg("create_issue")
def _act_create_issue(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    title = kw["title"]
    body = kw.get("body", "")
    label_names = kw.get("labels") or []

    payload = {"title": title}
    if body:
        payload[_issue_body_key(platform)] = body
    payload.update(_label_payload(platform, base_url, token, owner, repo, label_names))

    cp = _repo_path(platform, "create_issue", owner, repo)
    result = _request(base_url, token, "POST", cp, body=payload, platform=platform)

    num = result.get("number") or result.get("iid", "")
    html = _html_url(result)
    st = result.get("state", "")
    return _ok(f"issue #{num} created | state: {st} | title: {title} | labels: {', '.join(label_names) if label_names else 'none'} | url: {html}")


# ============================================================
# Action: get_issue
# ============================================================

@_reg("get_issue")
def _act_get_issue(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    num = kw["issue_number"]

    ep = _repo_path(platform, "edit_issue", owner, repo, index=num)
    result = _request(base_url, token, "GET", ep, platform=platform)
    label_names = _label_names(result.get("labels") or [])
    issue_no = result.get("number") or result.get("iid", num)
    html = result.get("html_url", result.get("web_url", ""))
    return _ok(
        f"issue #{issue_no} [{result.get('state', '')}] {result.get('title', '')}"
        f" | labels: {', '.join(label_names) if label_names else 'none'}"
        f" | url: {html}"
    )


# ============================================================
# Action: edit_issue / set_labels
# ============================================================

def _edit_issue(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    num = kw["issue_number"]

    payload = {}
    if "title" in kw and kw["title"] is not None:
        payload["title"] = kw["title"]
    if "body" in kw and kw["body"] is not None:
        payload[_issue_body_key(platform)] = kw["body"]
    _validate_issue_state(kw.get("state"))
    payload.update(_state_update_payload(platform, kw.get("state")))

    label_names = kw.get("labels")
    if label_names is not None:
        payload.update(
            _label_payload(
                platform,
                base_url,
                token,
                owner,
                repo,
                label_names,
                allow_empty=True,
            )
        )

    if not payload:
        return _err("edit_issue 需要 title/body/state/labels 至少一个参数")

    ep = _repo_path(platform, "edit_issue", owner, repo, index=num)
    result = _request(base_url, token, _issue_edit_method(platform), ep, body=payload, platform=platform)
    issue_no = result.get("number") or result.get("iid", num)
    html = result.get("html_url", result.get("web_url", ""))
    return _ok(f"issue #{issue_no} edited | state: {result.get('state', '')} | url: {html}")


@_reg("edit_issue")
def _act_edit_issue(platform, **kw):
    return _edit_issue(platform, **kw)


@_reg("set_labels")
def _act_set_labels(platform, **kw):
    if "labels" not in kw:
        return _err("set_labels 需要 labels 参数")
    return _edit_issue(platform, **kw)


# ============================================================
# Action: pull request / merge request
# ============================================================

@_reg("create_pull")
def _act_create_pull(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    payload = _pull_payload(platform, kw, require_branches=True)
    if "title" not in payload:
        return _err("create_pull 需要 title 参数")

    path = _repo_path(platform, "create_pull", owner, repo)
    result = _request(base_url, token, "POST", path, body=payload, platform=platform)
    num = _pull_number(result)
    return _ok(f"pull #{num} created | state: {result.get('state', '')} | title: {result.get('title', kw.get('title', ''))} | url: {_html_url(result)}")


@_reg("get_pull")
def _act_get_pull(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    num = kw["pull_number"]

    path = _repo_path(platform, "get_pull", owner, repo, index=num)
    result = _request(base_url, token, "GET", path, platform=platform)
    pull_no = _pull_number(result, num)
    return _ok(f"pull #{pull_no} [{result.get('state', '')}] {result.get('title', '')} | url: {_html_url(result)}")


@_reg("list_pulls")
def _act_list_pulls(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    state = kw.get("state", "open")
    page_size_key = "limit" if platform == "gitea" else "per_page"
    params = {"page": str(kw.get("page", 1)), page_size_key: str(kw.get("limit", 20))}
    if state and state != "all":
        params["state"] = _state_filter(platform, state)

    path = _repo_path(platform, "list_pulls", owner, repo)
    result = _request(base_url, token, "GET", path, params=params, platform=platform)
    if state == "merged" and platform not in ("gitlab", "gitcode") and isinstance(result, list):
        result = [item for item in result if _pull_is_merged(item)]
    if not isinstance(result, list) or not result:
        return _ok(f"no pulls ({platform}, {state})")

    items = [
        f"#{_pull_number(item)} [{item.get('state', '')}] {item.get('title', '')}"
        for item in result
    ]
    return _ok(f"{len(items)} pulls ({platform}, {state}): " + "; ".join(items))


@_reg("edit_pull")
def _act_edit_pull(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    num = kw["pull_number"]
    payload = _pull_payload(platform, kw, require_branches=False)
    if not payload:
        return _err("edit_pull 需要 title/body/state/source_branch/target_branch 至少一个参数")

    path = _repo_path(platform, "edit_pull", owner, repo, index=num)
    result = _request(base_url, token, _issue_edit_method(platform), path, body=payload, platform=platform)
    pull_no = _pull_number(result, num)
    return _ok(f"pull #{pull_no} edited | state: {result.get('state', '')} | url: {_html_url(result)}")


def _change_pull_state(platform, state: str, **kw):
    """Close or reopen a PR/MR through the existing edit endpoint."""
    kw = dict(kw)
    kw["state"] = state
    return _act_edit_pull(platform, **kw)


def _merge_pull_payload(platform, kw):
    """Build merge PR/MR payload with only fields supported by each platform."""
    payload = {}
    message = kw.get("message")
    if message:
        if platform in ("gitlab", "gitcode"):
            payload["merge_commit_message"] = message
        elif platform in ("github", "gitee"):
            payload["commit_title"] = message
        elif platform == "gitea":
            payload["MergeTitleField"] = message
    if platform in ("github", "gitee") and kw.get("body"):
        payload["commit_message"] = kw["body"]
    if platform == "gitea":
        payload.setdefault("Do", "merge")
        if kw.get("body"):
            payload["MergeMessageField"] = kw["body"]
    return payload


def _merge_pull_method(platform):
    """Return the merge endpoint method for each platform."""
    if platform == "gitea":
        return "POST"
    return "PUT"


@_reg("merge_pull")
def _act_merge_pull(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    num = kw["pull_number"]

    path = _repo_path(platform, "merge_pull", owner, repo, index=num)
    result = _request(
        base_url,
        token,
        _merge_pull_method(platform),
        path,
        body=_merge_pull_payload(platform, kw),
        platform=platform,
    )
    pull_no = _pull_number(result, num)
    merged = _pull_is_merged(result) or result.get("merged") is True
    status = "merged" if merged else result.get("state", "merge requested")
    return _ok(f"pull #{pull_no} {status} | url: {_html_url(result)}")


@_reg("close_pull")
def _act_close_pull(platform, **kw):
    return _change_pull_state(platform, "closed", **kw)


@_reg("reopen_pull")
def _act_reopen_pull(platform, **kw):
    return _change_pull_state(platform, "open", **kw)


# ============================================================
# Action: release
# ============================================================

@_reg("create_release")
def _act_create_release(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    payload = _release_payload(platform, kw, require_tag=True)

    path = _repo_path(platform, "create_release", owner, repo)
    result = _request(base_url, token, "POST", path, body=payload, platform=platform)
    release_id = result.get("id", result.get("tag_name", payload.get("tag_name", "")))
    return _ok(f"release {release_id} created | tag: {result.get('tag_name', payload.get('tag_name', ''))} | url: {_html_url(result)}")


@_reg("get_release")
def _act_get_release(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    key = _release_key(platform, kw)

    action = "get_release_by_tag" if "tag_name" in key else "get_release"
    path = _repo_path(platform, action, owner, repo, **key)
    result = _request(base_url, token, "GET", path, platform=platform)
    release_id = result.get("id", result.get("tag_name", key.get("tag_name", key.get("release_id", ""))))
    return _ok(f"release {release_id} | tag: {result.get('tag_name', '')} | name: {result.get('name', '')} | url: {_html_url(result)}")


@_reg("list_releases")
def _act_list_releases(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    page_size_key = "limit" if platform == "gitea" else "per_page"
    params = {"page": str(kw.get("page", 1)), page_size_key: str(kw.get("limit", 20))}

    path = _repo_path(platform, "list_releases", owner, repo)
    result = _request(base_url, token, "GET", path, params=params, platform=platform)
    if not isinstance(result, list) or not result:
        return _ok(f"no releases ({platform})")

    items = [
        f"{item.get('id', item.get('tag_name', ''))} {item.get('tag_name', '')} {item.get('name', '')}".strip()
        for item in result
    ]
    return _ok(f"{len(items)} releases ({platform}): " + "; ".join(items))


@_reg("edit_release")
def _act_edit_release(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    key = _release_key(platform, kw)
    key = _resolve_release_id(base_url, token, platform, owner, repo, key)
    payload = _release_payload(platform, kw, require_tag=False)
    if not payload:
        return _err("edit_release 需要 name/body/draft/prerelease 至少一个参数")

    path = _repo_path(platform, "edit_release", owner, repo, **key)
    result = _request(base_url, token, _issue_edit_method(platform), path, body=payload, platform=platform)
    release_id = result.get("id", result.get("tag_name", key.get("tag_name", key.get("release_id", ""))))
    return _ok(f"release {release_id} edited | tag: {result.get('tag_name', '')} | url: {_html_url(result)}")


@_reg("delete_release")
def _act_delete_release(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    key = _release_key(platform, kw)
    key = _resolve_release_id(base_url, token, platform, owner, repo, key)

    path = _repo_path(platform, "delete_release", owner, repo, **key)
    _request(base_url, token, "DELETE", path, platform=platform)
    release_id = key.get("tag_name", key.get("release_id", ""))
    return _ok(f"release {release_id} deleted")


# ============================================================
# Action: close_issue
# ============================================================

@_reg("close_issue")
def _act_close_issue(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    num = kw["issue_number"]
    # 兼容 comment_body 别名（旧版测试/客户端可能使用）
    comment = kw.get("comment", kw.get("comment_body", ""))

    if comment:
        cpath = _repo_path(platform, "add_comment", owner, repo, index=num)
        _request(base_url, token, "POST", cpath, body={"body": comment}, platform=platform)

    ep = _repo_path(platform, "edit_issue", owner, repo, index=num)
    result = _request(
        base_url,
        token,
        _issue_edit_method(platform),
        ep,
        body=_state_update_payload(platform, "closed"),
        platform=platform,
    )
    html = _html_url(result)
    return _ok(f"issue #{num} closed | url: {html}" + (f" | comment: {comment[:80]}" if comment else ""))


# ============================================================
# Action: add_comment
# ============================================================

@_reg("add_comment")
def _act_add_comment(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    num = kw["issue_number"]
    text = kw["body"]

    cp = _repo_path(platform, "add_comment", owner, repo, index=num)
    result = _request(base_url, token, "POST", cp, body={"body": text}, platform=platform)
    return _ok(f"comment added (id: {result.get('id', '')}) | issue: #{num}")


# ============================================================
# Action: list_issues
# ============================================================

@_reg("list_issues")
def _act_list_issues(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    state = kw.get("state", "open")
    _validate_issue_state(state)

    lp = _repo_path(platform, "list_issues", owner, repo)
    # 分页参数名因平台而异：gitea=limit, 其他=per_page
    page_size_key = "limit" if platform == "gitea" else "per_page"
    # GitLab/GitCode 不支持 state=all，不传 state 参数则默认返回所有
    params_state = _state_filter(platform, state) if not (platform in ("gitlab", "gitcode") and state == "all") else None
    params = {}
    if params_state:
        params["state"] = params_state
    params["page"] = str(kw.get("page", 1))
    params[page_size_key] = str(kw.get("limit", 20))
    result = _request(base_url, token, "GET", lp, params=params, platform=platform)
    if platform == "github" and isinstance(result, list):
        result = [item for item in result if not item.get("pull_request")]

    if not isinstance(result, list) or not result:
        return _ok(f"no issues ({platform}, {state})")

    items = []
    for i in result:
        n = i.get("number") or i.get("iid", "")
        ls = _label_names(i.get("labels") or [])
        items.append(f"#{n} [{i.get('state','')}] {i.get('title','')}{' ' + ','.join(ls) if ls else ''}")

    return _ok(f"{len(items)} issues ({platform}, {state}): " + "; ".join(items))


# ============================================================
# Git 本地操作（无需 platform 参数）
# ============================================================


def _git_human_error(err_text: str, cmd_str: str) -> str:
    """将 Git 原始错误信息转换为用户友好的中文提示。"""
    err_lower = err_text.lower()

    # ── 认证相关 ──
    if re.search(r"could not read (username|password)", err_lower):
        return (
            "需要 Git 认证，但 MCP 环境不支持交互式输入。\n"
            "  解决方式（任选其一）:\n"
            "    1. 配置凭据管理器: git config --global credential.helper manager\n"
            "    2. 使用 SSH 密钥: git remote set-url origin git@github.com:owner/repo.git\n"
            "    3. 在 .netrc 文件中写入凭据\n"
            f"  原始错误: {err_text[:200]}"
        )
    if re.search(r"authentication failed|access denied|invalid username or password|auth fail", err_lower):
        return f"认证失败，请检查用户名/密码或 Token 是否正确:\n  {err_text[:200]}"
    if "permission denied (publickey)" in err_lower:
        return (
            "SSH 认证失败，请检查 SSH 密钥配置:\n"
            "    1. 确认公钥已添加到 Git 平台\n"
            "    2. 确认私钥在本地可用: ssh -T git@github.com\n"
            f"  原始错误: {err_text[:200]}"
        )

    # ── 网络相关 ──
    if re.search(r"could not resolve host|couldn'?t resolve host|name or service not known", err_lower):
        return f"无法解析主机地址，请检查网络连接或代理配置:\n  {err_text[:200]}"
    if re.search(r"connection refused|could not connect to|connect.*timed out|connection timed out", err_lower):
        return f"连接被拒绝或超时，请检查网络/代理/防火墙设置:\n  {err_text[:200]}"

    # ── 仓库问题 ──
    if "repository not found" in err_lower:
        return f"仓库不存在或无权限访问，请检查 repo 地址是否正确:\n  {err_text[:200]}"
    if "not a git repository" in err_lower:
        return f"当前目录不是 Git 仓库（或父目录缺少 .git），请确认 dir 参数指向正确的仓库:\n  {err_text[:200]}"
    if re.search(r"pathspec.*did not match any", err_lower):
        return f"指定的文件路径在仓库中不存在:\n  {err_text[:200]}"
    if re.search(r"unknown switch|unrecognized argument|error: unknown option", err_lower):
        return f"Git 命令参数有误，请检查参数拼写:\n  {err_text[:200]}"

    # ── 大文件/磁盘 ──
    if re.search(r"file too large|large file detected|exceeds github|file size", err_lower):
        return f"文件大小超过限制，请使用 Git LFS 管理大文件:\n  {err_text[:200]}"
    if re.search(r"disk quota|no space left|insufficient disk", err_lower):
        return f"磁盘空间不足:\n  {err_text[:200]}"

    # ── 默认：返回原始错误的前 500 字符
    return err_text[:500]


def _git_run(work_dir, *args, timeout=TIMEOUT_GIT_PUSH, env=None):
    """在指定目录执行 git 命令，返回输出。

    Windows 上使用 utf-8 编码解码输出，避免 gbk 解码报错。

    Args:
        work_dir: 工作目录（自动 resolve 防路径遍历）
        timeout: 超时秒数，默认 300（5 分钟，适合大项目克隆）
        env: 额外环境变量字典（可选），会合并到子进程环境
    """
    safe_dir = _resolve_safe_dir(work_dir) if work_dir else None
    cwd = safe_dir if (safe_dir and os.path.isdir(safe_dir)) else None
    cmd = ["git"] + list(args)

    # 构建子进程环境：继承当前环境 + 强制非交互
    proc_env = os.environ.copy()
    proc_env["GIT_TERMINAL_PROMPT"] = "0"  # 禁止 git 弹出凭证提示
    proc_env["GIT_PAGER"] = ""              # 禁止分页器（如 less）
    proc_env["PAGER"] = ""                  # 全局分页器也禁掉
    proc_env["GIT_EDITOR"] = ":"            # 禁止打开编辑器
    if env:
        proc_env.update(env)

    try:
        r = subprocess.run(
            cmd, capture_output=True, cwd=cwd,
            stdin=subprocess.DEVNULL,        # 防止 git 读 MCP 的 JSON-RPC 管道导致死锁
            timeout=timeout,
            env=proc_env,
        )
        
        # 指定 utf-8 解码，避免 Windows gbk 编码问题
        def _decode(data):
            if isinstance(data, str):
                return data  # 测试 mock 可能传 str，无需解码
            for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
                try:
                    return data.decode(enc)
                except (UnicodeDecodeError, UnicodeError):
                    continue
            return data.decode("utf-8", errors="replace")
        
        stdout = _decode(r.stdout)
        stderr = _decode(r.stderr)
        
        if r.returncode != 0:
            err_text = stderr.strip()[:500]
            cmd_str = ' '.join(args)
            raise RuntimeError(f"git {cmd_str} 失败:\n{_git_human_error(err_text, cmd_str)}")
        return stdout.strip()
    except FileNotFoundError:
        raise RuntimeError("git 命令未找到，请确保已安装 Git")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"git 操作超时 ({timeout}秒)")
    except OSError as e:
        raise RuntimeError(f"git 执行失败: {e}")



# ============================================================
# 异步 Git 任务（复用 AsyncTaskManager）
# ============================================================


def _submit_git_task(name: str, fn, **kw) -> tuple:
    """通过 AsyncTaskManager 提交后台 git 任务。"""
    if get_task_manager is None:
        return "", _err("async task manager not available")
    on_complete = kw.pop('_on_complete', None)
    task_id = get_task_manager().submit_task(
        name, fn,
        on_complete=on_complete,
        **kw,
    )
    resp = _ok(f"task {task_id} | action: {name}")
    resp["task_id"] = task_id
    return task_id, resp


GIT_REMOTE_SYNC_TIMEOUT = TIMEOUT_GIT_REMOTE_SYNC
GIT_REMOTE_ASYNC_TIMEOUT = TIMEOUT_GIT_PUSH


def _run_git_remote_action(action: str, work_dir: str, args: list[str], success_message: str, **kw) -> dict:
    """Run a potentially slow git remote action synchronously or as a task."""
    async_mode = _coerce_bool(kw.get("async_mode", kw.get("async")), False)
    if async_mode:
        def _do_git_remote(**task_kw):
            progress_cb = task_kw.get("_progress_callback")
            cancel_check = task_kw.get("_cancellation_check")
            if cancel_check:
                cancel_check()
            if progress_cb:
                progress_cb(10, f"{action} started")
            raw = _git_run(work_dir, *args, timeout=GIT_REMOTE_ASYNC_TIMEOUT)
            if progress_cb:
                progress_cb(100, f"{action} finished")
            return _ok(raw or success_message)

        task_id, resp = _submit_git_task(action, _do_git_remote, **kw)
        if resp.get("status") != "ok":
            return resp
        result = _ok(f"{action} task {task_id} | use async_task(action=status, task_id=...)")
        result["task_id"] = task_id
        return result

    try:
        raw = _git_run(work_dir, *args, timeout=GIT_REMOTE_SYNC_TIMEOUT)
    except RuntimeError as exc:
        message = str(exc)
        if "超时" in message or "timeout" in message.lower():
            return _err(f"{message}; retry with async_mode=True and query via async_task")
        raise
    return _ok(raw or success_message)


# ============================================================
# Git 本地操作 — 快速操作（同步）
# ============================================================


def _compact_git_status(raw: str) -> str:
    """将 git status --porcelain=v1 -b 输出压缩为一行摘要。"""
    lines = raw.splitlines()
    branch = "?"
    sync = ""
    staged, unstaged, untracked = [], [], []

    for line in lines:
        if not line:
            continue
        if line.startswith("## "):
            header = line[3:].strip()
            if "..." in header:
                branch_part, sync_part = header.split("...", 1)
                branch = branch_part.strip() or "?"
                sync = sync_part.strip()
            else:
                branch = header.strip() or "?"
            continue

        if len(line) < 4:
            continue
        index_status, worktree_status = line[0], line[1]
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if index_status == "?" and worktree_status == "?":
            untracked.append(path)
            continue
        if index_status != " ":
            staged.append(path)
        if worktree_status != " ":
            unstaged.append(path)

    parts = [branch]
    if sync:
        parts.append(sync)
    if not staged and not unstaged and not untracked:
        parts.append("clean")
    if staged:
        parts.append(f"staged({len(staged)}): {' '.join(staged)}")
    if unstaged:
        parts.append(f"modified({len(unstaged)}): {' '.join(unstaged)}")
    if untracked:
        parts.append(f"untracked({len(untracked)}): {' '.join(untracked)}")
    return " | ".join(parts)


@_reg("git_status")
def _act_git_status(platform=None, **kw):
    """查看仓库状态（同步，瞬间完成）。"""
    work_dir = kw.get("dir", ".")
    raw = _git_run(work_dir, "status", "--porcelain=v1", "-b", timeout=TIMEOUT_GIT_QUICK)
    return _ok(_compact_git_status(raw))


@_reg("git_diff")
def _act_git_diff(platform=None, **kw):
    """查看差异（同步，只读）。"""
    work_dir = kw.get("dir", ".")
    staged = _coerce_bool(kw.get("staged"), False)
    stat = _coerce_bool(kw.get("stat"), False)
    name_only = _coerce_bool(kw.get("name_only"), False)
    ref = kw.get("ref", "")
    files = kw.get("files") or []
    limit = int(kw.get("limit", 12000))

    args = ["diff", "--no-ext-diff"]
    if staged:
        args.append("--cached")
    if stat:
        args.append("--stat")
    if name_only:
        args.append("--name-only")
    args.extend(_split_ref(ref))
    if files:
        args.append("--")
        args.extend(files)

    raw = _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
    return _ok(_truncate_output(raw or "(no diff)", limit))


@_reg("git_show")
def _act_git_show(platform=None, **kw):
    """查看提交/对象内容（同步，只读）。"""
    work_dir = kw.get("dir", ".")
    ref = kw.get("ref", "HEAD")
    stat = _coerce_bool(kw.get("stat"), False)
    name_only = _coerce_bool(kw.get("name_only"), False)
    limit = int(kw.get("limit", 12000))

    args = ["show", "--no-ext-diff"]
    if stat:
        args.append("--stat")
    if name_only:
        args.append("--name-only")
    args.extend(_split_ref(ref))

    raw = _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
    return _ok(_truncate_output(raw, limit))


@_reg("git_log")
def _act_git_log(platform=None, **kw):
    """查看提交历史（同步，只读）。"""
    work_dir = kw.get("dir", ".")
    count = int(kw.get("limit", 20))
    ref = kw.get("ref", "")
    files = kw.get("files") or []

    args = ["log", "--oneline", "--decorate", f"-n{count}"]
    args.extend(_split_ref(ref))
    if files:
        args.append("--")
        args.extend(files)

    raw = _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
    return _ok(raw or "(no commits)")


@_reg("git_add")
def _act_git_add(platform=None, **kw):
    """暂存文件（同步）。"""
    work_dir = kw.get("dir", ".")
    files = _validate_git_paths(kw.get("files", []), "git_add")
    if not files:
        return _err("specify files via 'files' parameter")
    _git_run(work_dir, "add", "--", *files, timeout=TIMEOUT_GIT_QUICK)
    return _ok(f"staged: {' '.join(files)}")


@_reg("git_commit")
def _act_git_commit(platform=None, **kw):
    """创建提交（同步，本地操作极快）。"""
    work_dir = kw.get("dir", ".")
    msg = kw.get("message", "")
    if not msg:
        return _err("specify message via 'message' parameter")
    _git_run(work_dir, "commit", "-m", msg, timeout=TIMEOUT_GIT_QUICK)
    try:
        h = _git_run(work_dir, "rev-parse", "HEAD", timeout=TIMEOUT_GIT_REV_PARSE)
        return _ok(f"committed {h[:12]}: {msg}")
    except RuntimeError:
        return _ok(f"committed: {msg}")


@_reg("git_fetch")
def _act_git_fetch(platform=None, **kw):
    """拉取远程引用（同步）。"""
    work_dir = kw.get("dir", ".")
    remote = _validate_git_arg("remote", kw.get("remote", "origin"))
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)
    prune = _coerce_bool(kw.get("prune"), False)

    args = ["fetch"]
    if prune:
        args.append("--prune")
    args.append(remote)
    if branch:
        args.append(branch)
    return _run_git_remote_action(
        "git_fetch",
        work_dir,
        args,
        f"fetched {remote}{'/' + branch if branch else ''}",
        **kw,
    )


@_reg("git_pull")
def _act_git_pull(platform=None, **kw):
    """拉取并合并远程分支（同步）。"""
    work_dir = kw.get("dir", ".")
    remote = _validate_git_arg("remote", kw.get("remote", "origin"))
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)
    rebase = _coerce_bool(kw.get("rebase"), False)
    ff_only = _coerce_bool(kw.get("ff_only"), False)

    args = ["pull"]
    if rebase:
        args.append("--rebase")
    if ff_only:
        args.append("--ff-only")
    args.append(remote)
    if branch:
        args.append(branch)
    return _run_git_remote_action(
        "git_pull",
        work_dir,
        args,
        f"pulled {remote}{'/' + branch if branch else ''}",
        **kw,
    )


@_reg("git_branch")
def _act_git_branch(platform=None, **kw):
    """列出或创建分支（同步）。"""
    work_dir = kw.get("dir", ".")
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)
    start_point = _validate_git_arg("start_point", kw.get("start_point", ""), allow_empty=True)
    delete = _coerce_bool(kw.get("delete"), False)
    remote = _coerce_bool(kw.get("remote_branches"), False)

    if delete:
        if not branch:
            return _err("git_branch delete 需要 branch 参数")
        _git_run(work_dir, "branch", "-d", branch, timeout=TIMEOUT_GIT_QUICK)
        return _ok(f"branch deleted: {branch}")

    if branch:
        args = ["branch", branch]
        if start_point:
            args.append(start_point)
        _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
        return _ok(f"branch created: {branch}{' from ' + start_point if start_point else ''}")

    args = ["branch"]
    if remote:
        args.append("-a")
    raw = _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
    return _ok(raw or "(no branches)")


@_reg("git_switch")
def _act_git_switch(platform=None, **kw):
    """切换或创建分支（同步）。"""
    work_dir = kw.get("dir", ".")
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)
    create = _coerce_bool(kw.get("create"), False)
    start_point = _validate_git_arg("start_point", kw.get("start_point", ""), allow_empty=True)
    if not branch:
        return _err("git_switch 需要 branch 参数")

    args = ["switch"]
    if create:
        args.extend(["-c", branch])
        if start_point:
            args.append(start_point)
    else:
        args.append(branch)
    raw = _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
    return _ok(raw or f"switched to {branch}")


@_reg("git_merge")
def _act_git_merge(platform=None, **kw):
    """合并分支（同步）。默认 no-ff=false，支持 ff_only。"""
    work_dir = kw.get("dir", ".")
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)
    ff_only = _coerce_bool(kw.get("ff_only"), False)
    no_commit = _coerce_bool(kw.get("no_commit"), False)
    if not branch:
        return _err("git_merge 需要 branch 参数")

    args = ["merge"]
    if ff_only:
        args.append("--ff-only")
    if no_commit:
        args.append("--no-commit")
    args.append(branch)
    return _run_git_remote_action(
        "git_merge",
        work_dir,
        args,
        f"merged {branch}",
        **kw,
    )


@_reg("git_restore")
def _act_git_restore(platform=None, **kw):
    """恢复显式文件列表（同步，有破坏性，必须传 files）。"""
    work_dir = kw.get("dir", ".")
    files = _require_files(kw, "git_restore")
    staged = _coerce_bool(kw.get("staged"), False)
    source = _validate_git_arg("source", kw.get("source", ""), allow_empty=True)

    args = ["restore"]
    if staged:
        args.append("--staged")
    if source:
        args.extend(["--source", source])
    args.append("--")
    args.extend(files)
    _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
    return _ok(f"restored: {' '.join(files)}")


@_reg("git_unstage")
def _act_git_unstage(platform=None, **kw):
    """取消暂存显式文件列表（同步，必须传 files）。"""
    work_dir = kw.get("dir", ".")
    files = _require_files(kw, "git_unstage")
    _git_run(work_dir, "restore", "--staged", "--", *files, timeout=TIMEOUT_GIT_QUICK)
    return _ok(f"unstaged: {' '.join(files)}")


@_reg("git_stash")
def _act_git_stash(platform=None, **kw):
    """管理 stash（同步）。"""
    work_dir = kw.get("dir", ".")
    op = kw.get("op", kw.get("stash_action", "push"))
    message = kw.get("message", "")
    files = kw.get("files") or []
    include_untracked = _coerce_bool(kw.get("include_untracked"), False)

    if op == "list":
        raw = _git_run(work_dir, "stash", "list", timeout=TIMEOUT_GIT_QUICK)
        return _ok(raw or "(no stashes)")
    if op in ("pop", "apply", "drop", "show"):
        ref = _validate_git_arg("ref", kw.get("ref", "stash@{0}"))
        args = ["stash", op]
        if op == "show":
            args.append("--stat")
        args.append(ref)
        raw = _git_run(work_dir, *args, timeout=TIMEOUT_GIT_LOCAL_SLOW)
        return _ok(raw or f"stash {op}: {ref}")
    if op != "push":
        return _err("git_stash op 可选: push/list/pop/apply/drop/show")

    args = ["stash", "push"]
    if include_untracked:
        args.append("--include-untracked")
    if message:
        args.extend(["-m", message])
    if files:
        args.append("--")
        args.extend(files)
    raw = _git_run(work_dir, *args, timeout=TIMEOUT_GIT_LOCAL_SLOW)
    return _ok(raw or "stash saved")


@_reg("git_tag")
def _act_git_tag(platform=None, **kw):
    """列出或创建标签（同步）。"""
    work_dir = kw.get("dir", ".")
    tag = _validate_git_arg("tag", kw.get("tag", ""), allow_empty=True)
    ref = _validate_git_arg("ref", kw.get("ref", "HEAD"))
    message = kw.get("message", "")
    delete = _coerce_bool(kw.get("delete"), False)

    if delete:
        if not tag:
            return _err("git_tag delete 需要 tag 参数")
        _git_run(work_dir, "tag", "-d", tag, timeout=TIMEOUT_GIT_QUICK)
        return _ok(f"tag deleted: {tag}")
    if tag:
        args = ["tag"]
        if message:
            args.extend(["-a", tag, ref, "-m", message])
        else:
            args.extend([tag, ref])
        _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
        return _ok(f"tag created: {tag}")
    raw = _git_run(work_dir, "tag", "--list", timeout=TIMEOUT_GIT_QUICK)
    return _ok(raw or "(no tags)")


# ============================================================
# Git 远程操作 — 耗时操作（异步）
# ============================================================


@_reg("git_clone")
def _act_git_clone(platform=None, **kw):
    """克隆远程仓库（异步，大项目可能耗时数分钟）。

    支持 GitHub 镜像源（解决国内访问问题）:
      设置 mirror="https://hub.fastgit.xyz"
      会自动将 repo_url 中的 github.com 替换为镜像地址。

    提交后台任务，完成后自动推送 TaskStatusNotification 到 MCP 客户端。
    """
    url = kw["repo_url"]
    work_dir = kw.get("dir", ".")
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)
    mirror = kw.get("mirror", "")

    # GitHub 镜像替换 — 只替换域名（netloc），不污染路径
    if mirror and "github.com" in url.lower():
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        # 仅当 netloc 包含 github.com 时才替换
        if "github.com" in parsed.netloc.lower():
            mirror_netloc = mirror.rstrip("/").replace("https://", "").replace("http://", "")
            parsed = parsed._replace(netloc=mirror_netloc, scheme="https")
            url = urlunparse(parsed)

    target_dir = os.path.join(work_dir, url.split("/")[-1].replace(".git", ""))
    _resolve_safe_dir(work_dir)

    def _do_clone(**_kw):
        args = ["clone"]
        if branch:
            args.extend(["-b", branch])
        args.append(url)
        args.append(target_dir)
        _git_run(work_dir, *args)
        return _ok(f"cloned to {target_dir}")

    task_id, status = _submit_git_task("git_clone", _do_clone, **kw)
    if status.get("status") != "ok":
        return status
    resp = _ok(f"clone task {task_id} | url: {url} | target: {target_dir}")
    resp["task_id"] = task_id
    return resp


@_reg("git_push")
def _act_git_push(platform=None, **kw):
    """推送到远程（异步，单次尝试）。"""
    work_dir = kw.get("dir", ".")
    remote = _validate_git_arg("remote", kw.get("remote", "origin"))
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)

    def _do_push(**kw2):
        cancel_check = kw2.get('_cancellation_check')
        if cancel_check:
            cancel_check()
        args = ["push", remote]
        if branch:
            args.append(branch)
        _git_run(work_dir, *args, timeout=TIMEOUT_GIT_FETCH_PULL)
        return _ok(f"pushed to {remote}{'/' + branch if branch else ''}")

    tid, resp = _submit_git_task("git_push", _do_push, **kw)
    if resp.get("status") == "ok":
        resp.setdefault("task_id", tid)
    return resp


@_reg("git_push_retry")
def _act_git_push_retry(platform=None, **kw):
    """后台自动重试推送，直到成功或达到最大次数。

    每 N 秒重试一次（默认 300 秒=5分钟），最多 M 次（默认 12 次=1小时）。
    提交后台任务，每步结果自动推送 TaskStatusNotification 到 MCP 客户端。
    """
    work_dir = kw.get("dir", ".")
    remote = _validate_git_arg("remote", kw.get("remote", "origin"))
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)
    # 默认 5 分钟间隔，12 次 ≈ 1 小时
    interval = int(kw.get("retry_interval", RETRY_INTERVAL_GIT_PUSH))
    max_retries = int(kw.get("max_retries", MAX_RETRIES_GIT_PUSH))

    def _do_retry_push(**kw2):
        progress_cb = kw2.get('_progress_callback')
        cancel_check = kw2.get('_cancellation_check')

        last_error = None
        for attempt in range(1, max_retries + 1):
            if cancel_check:
                cancel_check()

            try:
                args = ["push", remote]
                if branch:
                    args.append(branch)
                _git_run(work_dir, *args, timeout=TIMEOUT_GIT_FETCH_PULL)

                if progress_cb:
                    progress_cb(100, f"pushed to {remote} (attempt {attempt})")
                return _ok(f"pushed to {remote}{'/' + branch if branch else ''} (attempt {attempt})")

            except RuntimeError as e:
                last_error = e
                logger.warning("push failed (attempt %s/%s): %s", attempt, max_retries, e)

                if progress_cb:
                    pct = (attempt / max_retries) * 100
                    if attempt < max_retries:
                        eta_total = (interval * max_retries) // 60
                        progress_cb(pct, f"attempt {attempt} failed: {str(e)[:80]} | retry in {interval}s | eta ~{eta_total}min")
                    else:
                        progress_cb(pct, f"max retries ({max_retries}) reached, push failed")

                if attempt < max_retries:
                    time.sleep(interval)

        eta_total = (interval * max_retries) // 60
        raise RuntimeError(f"push failed after {max_retries} retries (~{eta_total}min): {last_error}")

    tid, resp = _submit_git_task("git_push_retry", _do_retry_push, **kw)
    if resp.get("status") != "ok":
        return resp

    eta_total = (interval * max_retries) // 60
    resp_message = f"auto-retry push task {tid} | interval: {interval}s | max: {max_retries} | eta: ~{eta_total}min"
    resp = _ok(resp_message)
    resp["task_id"] = tid
    return resp
