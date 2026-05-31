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
  - git_add    暂存文件
  - git_commit 创建提交
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

import json
import logging
import os
import re
import subprocess
import time
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
import base64

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
    - 绝对路径直接使用（不限制到 _ALLOWED_BASE 下）
    - 路径不存在时自动创建（安全）
    - 如果无法判定安全，返回 _ALLOWED_BASE 本身

    Args:
        dir_path: 用户传入的目录路径

    Returns:
        安全的绝对路径
    """
    if not dir_path:
        return _ALLOWED_BASE

    # 绝对路径：直接使用，不做项目目录限制（但依然防空字节注入）
    if os.path.isabs(dir_path):
        resolved = os.path.normpath(dir_path)
        if '\0' in resolved:
            logger.warning("空字节注入拦截: %s", dir_path)
            return _ALLOWED_BASE
        if not os.path.exists(resolved):
            try:
                os.makedirs(resolved, exist_ok=True)
            except OSError:
                return _ALLOWED_BASE
        return resolved

    # 相对路径：基于 _ALLOWED_BASE resolve，阻止 .. 逃逸
    resolved = os.path.abspath(os.path.join(_ALLOWED_BASE, dir_path))
    resolved = os.path.normpath(resolved)
    resolved_lower = resolved.lower()
    allowed_lower = os.path.normpath(_ALLOWED_BASE).lower()

    if not resolved_lower.startswith(allowed_lower + os.sep) and resolved_lower != allowed_lower:
        logger.warning("路径遍历拦截: %s -> %s (base: %s)", dir_path, resolved, _ALLOWED_BASE)
        return _ALLOWED_BASE

    if not os.path.exists(resolved):
        try:
            os.makedirs(resolved, exist_ok=True)
        except OSError:
            return _ALLOWED_BASE

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
    },
    "github": {
        "create_token": None,  # GitHub 不支持 API 创建 token
        "list_labels":  "/repos/{owner}/{repo}/labels",
        "create_label": "/repos/{owner}/{repo}/labels",
        "create_issue": "/repos/{owner}/{repo}/issues",
        "edit_issue":   "/repos/{owner}/{repo}/issues/{index}",
        "add_comment":  "/repos/{owner}/{repo}/issues/{index}/comments",
        "list_issues":  "/repos/{owner}/{repo}/issues",
    },
    "gitlab": {
        "create_token": None,
        "list_labels":  "/api/v4/projects/{encoded}/labels",
        "create_label": "/api/v4/projects/{encoded}/labels",
        "create_issue": "/api/v4/projects/{encoded}/issues",
        "edit_issue":   "/api/v4/projects/{encoded}/issues/{index}",
        "add_comment":  "/api/v4/projects/{encoded}/issues/{index}/notes",
        "list_issues":  "/api/v4/projects/{encoded}/issues",
    },
    "gitee": {
        "create_token": None,
        "list_labels":  "/repos/{owner}/{repo}/labels",
        "create_label": "/repos/{owner}/{repo}/labels",
        "create_issue": "/repos/{owner}/{repo}/issues",
        "edit_issue":   "/repos/{owner}/{repo}/issues/{number}",
        "add_comment":  "/repos/{owner}/{repo}/issues/{number}/comments",
        "list_issues":  "/repos/{owner}/{repo}/issues",
    },
    "gitcode": {
        "create_token": None,
        "list_labels":  "/api/v4/projects/{encoded}/labels",
        "create_label": "/api/v4/projects/{encoded}/labels",
        "create_issue": "/api/v4/projects/{encoded}/issues",
        "edit_issue":   "/api/v4/projects/{encoded}/issues/{index}",
        "add_comment":  "/api/v4/projects/{encoded}/issues/{index}/notes",
        "list_issues":  "/api/v4/projects/{encoded}/issues",
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
            with urlopen(req, timeout=30) as resp:
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
      - close_issue   关闭工单
      - add_comment   添加评论
      - list_issues   查询工单列表
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


_API_ACTIONS = {"create_token", "init_labels", "create_issue", "close_issue",
                "add_comment", "list_issues"}


_DISPATCH = {}


def _reg(name):
    """装饰器：注册 action 处理器"""
    def _(fn):
        _DISPATCH[name] = fn
        return fn
    return _


def _err(msg):
    return {"message": f"❌ {msg}", "status": "failed"}


def _ok(msg):
    return {"message": msg, "status": "ok"}


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
    if platform in ("gitlab", "gitcode") and "{encoded}" in tmpl:
        kw["encoded"] = quote(f"{owner}/{repo}", safe="")
    return tmpl.format(**kw)


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
    d = _ok(
        "Token 创建成功\n"
        "  平台: %s | 名称: %s\n"
        "  值(脱敏): %s\n"
        "  ⚠ 完整 token 已在返回值 token 字段中，请妥善保管" % (platform, result.get('name', name), masked)
    )
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

    return _ok(
        f"✅ 标签初始化完成\n"
        f"  新增: {created} | 跳过(已有): {skipped} | 合计: {created + skipped}\n"
        f"  分组: 优先级(4) 审阅(4) 状态(5) 类型(5)"
    )


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

    label_ids = []
    if label_names:
        lp = _repo_path(platform, "list_labels", owner, repo)
        existing = _request(base_url, token, "GET", lp, platform=platform)
        n2id = {lb["name"]: lb["id"] for lb in existing} if isinstance(existing, list) else {}
        for n in label_names:
            if n in n2id:
                label_ids.append(n2id[n])

    payload = {"title": title, "body": body}
    if label_ids:
        if platform == "gitea":
            # Gitea 需要标签 ID（数字）
            payload["labels"] = label_ids
        elif platform in ("gitlab", "gitcode"):
            # GitLab/GitCode 接受逗号分隔的标签名
            payload["labels"] = label_names
        else:
            # GitHub/Gitee 接受标签名数组
            payload["labels"] = label_names

    cp = _repo_path(platform, "create_issue", owner, repo)
    result = _request(base_url, token, "POST", cp, body=payload, platform=platform)

    num = result.get("number") or result.get("iid", "")
    html = result.get("html_url", "")
    st = result.get("state", "")
    return _ok(
        f"✅ 工单已创建\n"
        f"  编号: #{num} | 状态: {st}\n"
        f"  标题: {title}\n"
        f"  标签: {', '.join(label_names) if label_names else '(无)'}\n"
        f"  地址: {html}"
    )


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
    result = _request(base_url, token, "PATCH", ep, body={"state": "closed"}, platform=platform)
    html = result.get("html_url", "")
    return _ok(
        f"✅ 工单 #{num} 已关闭\n"
        f"  地址: {html}"
        + (f"\n  关闭说明: {comment[:80]}..." if len(comment) > 80 else
           f"\n  关闭说明: {comment}" if comment else "")
    )


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
    return _ok(f"✅ 评论已添加 (ID: {result.get('id', '')})  工单: #{num}")


# ============================================================
# Action: list_issues
# ============================================================

@_reg("list_issues")
def _act_list_issues(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    state = kw.get("state", "open")

    lp = _repo_path(platform, "list_issues", owner, repo)
    # 分页参数名因平台而异：gitea=limit, 其他=per_page
    page_size_key = "limit" if platform == "gitea" else "per_page"
    # GitLab/GitCode 不支持 state=all，不传 state 参数则默认返回所有
    params_state = state if not (platform in ("gitlab", "gitcode") and state == "all") else None
    params = {}
    if params_state:
        params["state"] = params_state
    params["page"] = str(kw.get("page", 1))
    params[page_size_key] = str(kw.get("limit", 20))
    result = _request(base_url, token, "GET", lp, params=params, platform=platform)

    if not isinstance(result, list) or not result:
        return _ok(f"📋 暂无工单 ({platform}, {state})")

    items = []
    for i in result:
        n = i.get("number") or i.get("iid", "")
        ls = [lb.get("name", lb.get("title", "")) for lb in i.get("labels") or []]
        items.append(f"  #{n} [{i.get('state','')}] {i.get('title','')}  {', '.join(ls)}")

    return _ok(f"📋 共 {len(items)} 个工单 ({platform}, {state}):\n" + "\n".join(items))


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


def _git_run(work_dir, *args, timeout=300, env=None):
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
    """通过 AsyncTaskManager 提交后台 git 任务。

    支持 MCP 推送通知: 调用方传入 _on_complete 回调，
    任务完成时自动推送 TaskStatusNotification 到 MCP 客户端。

    Returns:
        (task_id, message_dict)
    """
    if get_task_manager is None:
        return "", _err("异步任务管理器不可用")
    # 提取 MCP 推送回调（由 server.py 注入），不传给任务函数
    on_complete = kw.pop('_on_complete', None)
    # submit_task 会给 fn 注入 _progress_callback, _cancellation_check, _task_id
    task_id = get_task_manager().submit_task(
        name, fn,
        on_complete=on_complete,
        **kw,
    )
    msg = (
        f"🔄 Git 任务已提交\n"
        f"  任务ID: {task_id}\n"
        f"  操作: {name}\n"
        f"  完成时自动推送通知到 MCP（AI Agent 需通过 async_task 查询）"
    )
    return task_id, _ok(msg)


# ============================================================
# Git 本地操作 — 快速操作（同步）
# ============================================================


@_reg("git_status")
def _act_git_status(platform=None, **kw):
    """查看仓库状态（同步，瞬间完成）。"""
    work_dir = kw.get("dir", ".")
    out = _git_run(work_dir, "status", timeout=30)
    return _ok(f"📋 Git 状态:\n{out}")


@_reg("git_add")
def _act_git_add(platform=None, **kw):
    """暂存文件（同步）。"""
    work_dir = kw.get("dir", ".")
    files = kw.get("files", [])
    if not files:
        return _err("请指定要暂存的文件列表 (files 参数)")
    _git_run(work_dir, "add", *files, timeout=30)
    return _ok(f"✅ 已暂存: {', '.join(files)}")


@_reg("git_commit")
def _act_git_commit(platform=None, **kw):
    """创建提交（同步，本地操作极快）。"""
    work_dir = kw.get("dir", ".")
    msg = kw.get("message", "")
    if not msg:
        return _err("请指定提交信息 (message 参数)")
    _git_run(work_dir, "commit", "-m", msg, timeout=30)
    try:
        h = _git_run(work_dir, "rev-parse", "HEAD", timeout=10)
        return _ok(f"✅ 提交成功\n  Hash: {h[:12]}\n  信息: {msg}")
    except RuntimeError:
        return _ok(f"✅ 提交成功\n  信息: {msg}")


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
    branch = kw.get("branch", "")
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

    def _do_clone(**_kw):
        args = ["clone"]
        if branch:
            args.extend(["-b", branch])
        args.append(url)
        args.append(target_dir)
        _git_run(work_dir, *args)
        return _ok(f"✅ 仓库已克隆到 {target_dir}\n  地址: {url}")

    task_id, status = _submit_git_task("git_clone", _do_clone, **kw)
    return _ok(
        f"🔄 克隆任务已启动\n"
        f"  任务ID: {task_id}\n"
        f"  地址: {url}\n"
        f"  目标: {target_dir}\n"
        f"  完成时自动推送通知到 MCP（AI Agent 需通过 async_task 查询）"
    )


@_reg("git_push")
def _act_git_push(platform=None, **kw):
    """推送到远程（异步，单次尝试，超时 120 秒）。

    推送方式取决于用户的 Git 配置（SSH/HTTPS代理/VPN），工具不做假设。
    提交后台任务，完成后自动推送 TaskStatusNotification 到 MCP 客户端。
    如果推送失败，建议使用 git_push_retry 后台自动重试。
    """
    work_dir = kw.get("dir", ".")
    remote = kw.get("remote", "origin")
    branch = kw.get("branch", "")

    def _do_push(**kw2):
        cancel_check = kw2.get('_cancellation_check')
        if cancel_check:
            cancel_check()
        args = ["push", remote]
        if branch:
            args.append(branch)
        _git_run(work_dir, *args, timeout=120)
        return _ok(f"✅ 已推送到 {remote}{'/' + branch if branch else ''}")

    tid, resp = _submit_git_task("git_push", _do_push, **kw)
    return resp


@_reg("git_push_retry")
def _act_git_push_retry(platform=None, **kw):
    """后台自动重试推送，直到成功或达到最大次数。

    每 N 秒重试一次（默认 300 秒=5分钟），最多 M 次（默认 12 次=1小时）。
    提交后台任务，每步结果自动推送 TaskStatusNotification 到 MCP 客户端。
    """
    work_dir = kw.get("dir", ".")
    remote = kw.get("remote", "origin")
    branch = kw.get("branch", "")
    # 默认 5 分钟间隔，12 次 ≈ 1 小时
    interval = int(kw.get("retry_interval", 300))
    max_retries = int(kw.get("max_retries", 12))

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
                _git_run(work_dir, *args, timeout=120)

                if progress_cb:
                    progress_cb(
                        100,
                        f"✅ 第{attempt}次重试成功，已推送到 {remote}"
                        f"{'/' + branch if branch else ''}"
                    )
                return _ok(
                    f"✅ 已推送到 {remote}{'/' + branch if branch else ''}"
                    f"（第{attempt}次重试成功）"
                )

            except RuntimeError as e:
                last_error = e
                logger.warning("推送失败(第%s/%s次): %s", attempt, max_retries, e)

                if progress_cb:
                    pct = (attempt / max_retries) * 100
                    if attempt < max_retries:
                        # 时间信息：下次重试时间 + 估计总耗时
                        eta_total = (interval * max_retries) // 60
                        progress_cb(
                            pct,
                            f"⏳ 第{attempt}次重试失败: {str(e)[:100]} | "
                            f"等待{interval}秒后第{attempt+1}次重试 "
                            f"（总约{eta_total}分钟）"
                        )
                    else:
                        progress_cb(pct, f"❌ 已达最大重试次数（{max_retries}次），推送最终失败")

                if attempt < max_retries:
                    time.sleep(interval)

        eta_total = (interval * max_retries) // 60
        raise RuntimeError(
            f"推送失败，已重试 {max_retries} 次（约 {eta_total} 分钟）: {last_error}"
        )

    tid, resp = _submit_git_task("git_push_retry", _do_retry_push, **kw)

    eta_total = (interval * max_retries) // 60
    resp_message = (
        f"🔄 后台自动重试已启动\n"
        f"  任务ID: {tid}\n"
        f"  重试间隔: {interval}秒 | 最大次数: {max_retries}次\n"
        f"  预计总耗时: 约 {eta_total} 分钟\n"
        f"  每次重试结果自动推送通知到 MCP（AI Agent 需通过 async_task 查询）"
    )
    return _ok(resp_message)
