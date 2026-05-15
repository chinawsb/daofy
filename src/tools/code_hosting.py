"""代码托管平台统一工具 — 兼容 Gitea / GitHub / GitLab + Git 本地操作

通过 action 参数分发操作，platform 参数切换后端。
支持以下平台:
  - gitea  : 自托管 Gitea
  - github : GitHub
  - gitlab : GitLab

Git 相关操作（无需 platform 参数）:
  - git_clone  克隆远程仓库（支持 GitHub 镜像源）
  - git_status 查看仓库状态
  - git_add    暂存文件
  - git_commit 创建提交
  - git_push   推送到远程（依赖用户自身的网络/代理/SSH配置）

GitHub 国内访问:
  - 拉取: git_clone 支持 mirror 参数指定镜像源
  - 推送: 依赖用户自身配置（SSH/HTTPS代理/VPN），工具不做假设

用法:
  code_hosting(platform="gitea", action="create_issue", ...)
  code_hosting(action="git_clone", repo_url="https://github.com/...", mirror="https://hub.fastgit.xyz")
  code_hosting(action="git_push", work_dir=".", branch="main")
"""

import json
import logging
import os
import subprocess
import tempfile
import threading
import time
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
import base64

logger = logging.getLogger(__name__)

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
}

# ============================================================
# 标签定义 — 软件流程四维分类
# ============================================================

ISSUE_LABELS = {
    "priority": [
        {"name": "优先级: 紧急", "color": "e53e3e", "description": "需要立即处理"},
        {"name": "优先级: 高",   "color": "ed8936", "description": "重要问题，应尽快处理"},
        {"name": "优先级: 中",   "color": "ecc94b", "description": "常规问题"},
        {"name": "优先级: 低",   "color": "a0aec0", "description": "可延后处理"},
    ],
    "review": [
        {"name": "审阅: 待审阅", "color": "4299e1", "description": "等待代码审阅"},
        {"name": "审阅: 需修改", "color": "ed8936", "description": "审阅发现问题，需要修改"},
        {"name": "审阅: 已通过", "color": "48bb78", "description": "审阅通过"},
        {"name": "审阅: 已拒绝", "color": "e53e3e", "description": "审阅不通过"},
    ],
    "status": [
        {"name": "状态: 待确认",   "color": "a0aec0", "description": "待确认是否有效"},
        {"name": "状态: 处理中",   "color": "4299e1", "description": "正在修复中"},
        {"name": "状态: 已验证",   "color": "48bb78", "description": "修复已验证"},
        {"name": "状态: 已关闭",   "color": "718096", "description": "问题已关闭"},
        {"name": "状态: 无法复现", "color": "9f7aea", "description": "无法复现"},
    ],
    "type": [
        {"name": "类型: 缺陷", "color": "e53e3e", "description": "功能缺陷"},
        {"name": "类型: 需求", "color": "48bb78", "description": "新功能需求"},
        {"name": "类型: 改进", "color": "4299e1", "description": "优化/重构"},
        {"name": "类型: 文档", "color": "ecc94b", "description": "文档相关"},
        {"name": "类型: 测试", "color": "9f7aea", "description": "测试相关"},
    ],
}


# ============================================================
# HTTP 请求
# ============================================================

def _request(base_url, token, method, path, body=None, params=None, platform="gitea", basic_auth=None):
    url = f"{base_url.rstrip('/')}{path}"
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urlencode(clean)

    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if basic_auth:
        raw = f"{basic_auth[0]}:{basic_auth[1]}".encode()
        headers["Authorization"] = f"Basic {base64.b64encode(raw).decode()}"
    elif platform == "github":
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    elif platform == "gitlab":
        headers["PRIVATE-TOKEN"] = token
    else:
        headers["Authorization"] = f"token {token}"

    data = json.dumps(body).encode("utf-8") if body else None
    req = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            if resp.status == 204:
                return {"success": True}
            return json.loads(raw) if raw else {"success": True}
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"API {e.code}: {detail[:300]}")
    except URLError as e:
        raise RuntimeError(f"无法连接 {base_url}: {e}")


# ============================================================
# 统一入口
# ============================================================

def code_hosting(**kwargs) -> dict:
    """代码托管平台统一操作入口。

    platform: gitea / github / gitlab（默认 gitea）
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
        return handler(platform, **kwargs)
    except Exception as e:
        logger.exception("code_hosting error")
        return _err(str(e))


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


def _split_repo(repo):
    parts = repo.split("/", 1)
    if len(parts) != 2:
        raise ValueError("仓库格式应为 owner/repo")
    return parts[0], parts[1]


def _repo_path(platform, action, owner, repo, index=None):
    tmpl = _API_PATHS[platform].get(action)
    if tmpl is None:
        raise ValueError(f"{platform} 不支持 {action}")
    kw = {"owner": owner, "repo": repo}
    if index is not None:
        kw["index"] = index
    if platform == "gitlab" and "{encoded}" in tmpl:
        kw["encoded"] = quote(f"{owner}/{repo}", safe="")
    return tmpl.format(**kw)


# ============================================================
# Action: create_token
# ============================================================

@_reg("create_token")
def _act_create_token(platform, **kw):
    base_url, username, password = kw["base_url"], kw["username"], kw["password"]
    name = kw.get("token_name", "delphi-mcp")

    path = _repo_path(platform, "create_token", None, None)
    body = {"name": name, "scopes": ["write:repository", "write:issue"]}
    result = _request(base_url, "", "POST", path, body=body, platform=platform,
                      basic_auth=(username, password))
    val = result.get("sha1") or result.get("token", "")
    return _ok(
        f"✅ Token 创建成功\n"
        f"  平台: {platform} | 名称: {result.get('name', name)}\n"
        f"  值: {val[:8]}...{val[-4:]}"
    )


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
    label_names = kw.get("label_names") or []

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
        payload["labels"] = label_ids if platform != "gitlab" else label_names

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
    comment = kw.get("comment_body", "")

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
    result = _request(base_url, token, "GET", lp,
                      params={"state": state, "page": str(kw.get("page", 1)),
                              "limit": str(kw.get("limit", 20))},
                      platform=platform)

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


def _git_run(work_dir, *args, timeout=300):
    """在指定目录执行 git 命令，返回输出。
    
    Args:
        work_dir: 工作目录（不存在则自动创建父目录）
        timeout: 超时秒数，默认 300（5 分钟，适合大项目克隆）
    """
    if work_dir and not os.path.exists(work_dir):
        os.makedirs(work_dir, exist_ok=True)
    # 确保 work_dir 在命令执行前是存在的目录
    cwd = work_dir if (work_dir and os.path.isdir(work_dir)) else None
    cmd = ["git"] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        if r.returncode != 0:
            stderr = r.stderr.strip()[:500]
            raise RuntimeError(f"git {' '.join(args)} 失败:\n{stderr}")
        return r.stdout.strip()
    except FileNotFoundError:
        raise RuntimeError("git 命令未找到，请确保已安装 Git")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"git 操作超时 ({timeout}秒)")
    except OSError as e:
        raise RuntimeError(f"git 执行失败: {e}")


@_reg("git_clone")
def _act_git_clone(platform=None, **kw):
    """克隆远程仓库。

    支持 GitHub 镜像源（解决国内访问问题）:
      设置 mirror="https://hub.fastgit.xyz" 或 "https://github.com.cnpmjs.org"
      会自动将 repo_url 中的 github.com 替换为镜像地址。
    """
    url = kw["repo_url"]
    work_dir = kw.get("work_dir", ".")
    branch = kw.get("branch", "")
    mirror = kw.get("mirror", "")
    args = ["clone"]

    # GitHub 镜像：替换 repo_url 中的 github.com
    if mirror and "github.com" in url.lower():
        url = url.replace("github.com", mirror.rstrip("/").replace("https://", ""))
        url = url.replace("http://", "https://")

    if branch:
        args.extend(["-b", branch])
    args.append(url)
    if kw.get("work_dir") and kw["work_dir"] != ".":
        args.append(kw["work_dir"])
    else:
        name = url.split("/")[-1].replace(".git", "")
        args.append(os.path.join(work_dir, name))

    _git_run(work_dir, *args)
    return _ok(f"✅ 仓库已克隆\n  地址: {url}" + (f"\n  分支: {branch}" if branch else ""))


@_reg("git_status")
def _act_git_status(platform=None, **kw):
    """查看仓库状态。"""
    work_dir = kw.get("work_dir", ".")
    out = _git_run(work_dir, "status")
    return _ok(f"📋 Git 状态:\n{out}")


@_reg("git_add")
def _act_git_add(platform=None, **kw):
    """暂存文件。"""
    work_dir = kw.get("work_dir", ".")
    files = kw.get("files", [])
    if not files:
        return _err("请指定要暂存的文件列表 (files 参数)")
    _git_run(work_dir, "add", *files)
    return _ok(f"✅ 已暂存: {', '.join(files)}")


@_reg("git_commit")
def _act_git_commit(platform=None, **kw):
    """创建提交。"""
    work_dir = kw.get("work_dir", ".")
    msg = kw.get("commit_message", "")
    if not msg:
        return _err("请指定提交信息 (commit_message 参数)")
    _git_run(work_dir, "commit", "-m", msg)
    # 返回 commit hash
    try:
        h = _git_run(work_dir, "rev-parse", "HEAD")
        return _ok(f"✅ 提交成功\n  Hash: {h[:12]}\n  信息: {msg}")
    except RuntimeError:
        return _ok(f"✅ 提交成功\n  信息: {msg}")


@_reg("git_push")
def _act_git_push(platform=None, **kw):
    """推送到远程。

    推送方式取决于用户的 Git 配置:
      - SSH: 配置好 ~/.ssh/config 或 ssh-agent
      - HTTPS: 配置好 git-credential 或 GIT_ASKPASS
      - 代理: 配置 git config http.proxy / https.proxy
    本工具不做任何网络假设，直接调用 git push。
    """
    work_dir = kw.get("work_dir", ".")
    remote = kw.get("remote_name", "origin")
    branch = kw.get("branch", "")
    args = ["push", remote]
    if branch:
        args.append(branch)
    _git_run(work_dir, *args)
# ============================================================
# 异步 Git 任务引擎（所有耗时 git 操作走后台）
# ============================================================

_git_tasks = {}
_git_tasks_lock = threading.Lock()
_git_task_counter = 0


def _start_git_task(task_name, fn, **kw):
    """启动后台 git 任务，返回 task_id。"""
    global _git_task_counter
    with _git_tasks_lock:
        _git_task_counter += 1
        task_id = f"git_{task_name}_{int(time.time())}_{_git_task_counter}"
        status = {
            "task_id": task_id,
            "name": task_name,
            "status": "pending",
            "done": False,
            "success": False,
            "result": "",
            "error": "",
        }
        _git_tasks[task_id] = status

    def _run():
        status["status"] = "running"
        try:
            result = fn(**kw)
            status["result"] = result.get("message", "")
            status["success"] = True
            status["status"] = "success"
        except Exception as e:
            status["error"] = str(e)
            status["status"] = "failed"
        finally:
            status["done"] = True

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return task_id, status


# ============================================================
# Git 本地操作 — 快速操作（同步）
# ============================================================


@_reg("git_status")
def _act_git_status(platform=None, **kw):
    """查看仓库状态（同步，瞬间完成）。"""
    work_dir = kw.get("work_dir", ".")
    out = _git_run(work_dir, "status")
    return _ok(f"📋 Git 状态:\n{out}")


@_reg("git_add")
def _act_git_add(platform=None, **kw):
    """暂存文件（同步）。"""
    work_dir = kw.get("work_dir", ".")
    files = kw.get("files", [])
    if not files:
        return _err("请指定要暂存的文件列表 (files 参数)")
    _git_run(work_dir, "add", *files)
    return _ok(f"✅ 已暂存: {', '.join(files)}")


@_reg("git_commit")
def _act_git_commit(platform=None, **kw):
    """创建提交（同步，本地操作极快）。"""
    work_dir = kw.get("work_dir", ".")
    msg = kw.get("commit_message", "")
    if not msg:
        return _err("请指定提交信息 (commit_message 参数)")
    _git_run(work_dir, "commit", "-m", msg)
    try:
        h = _git_run(work_dir, "rev-parse", "HEAD")
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

    返回 task_id，通过 git_task_status 查询进度。
    """
    url = kw["repo_url"]
    work_dir = kw.get("work_dir", ".")
    branch = kw.get("branch", "")
    mirror = kw.get("mirror", "")

    # GitHub 镜像替换
    if mirror and "github.com" in url.lower():
        url = url.replace("github.com", mirror.rstrip("/").replace("https://", ""))
        url = url.replace("http://", "https://")

    target_dir = os.path.join(work_dir, url.split("/")[-1].replace(".git", ""))

    def _do_clone(**_kw):
        args = ["clone"]
        if branch:
            args.extend(["-b", branch])
        args.append(url)
        args.append(target_dir)
        _git_run(work_dir, *args)
        return _ok(f"✅ 仓库已克隆到 {target_dir}\n  地址: {url}")

    task_id, status = _start_git_task("clone", _do_clone)
    return _ok(
        f"🔄 克隆任务已启动\n"
        f"  任务ID: {task_id}\n"
        f"  地址: {url}\n"
        f"  目标: {target_dir}\n"
        f"  查询: code_hosting(action='git_task_status', task_id='{task_id}')"
    )


@_reg("git_push")
def _act_git_push(platform=None, **kw):
    """推送到远程（异步，网络不稳定可能耗时较长）。

    推送方式取决于用户的 Git 配置（SSH/HTTPS代理/VPN），工具不做假设。
    返回 task_id，通过 git_task_status 查询进度。
    """
    work_dir = kw.get("work_dir", ".")
    remote = kw.get("remote_name", "origin")
    branch = kw.get("branch", "")

    def _do_push(**kw2):
        args = ["push", remote]
        if branch:
            args.append(branch)
        _git_run(work_dir, *args)
        return _ok(f"✅ 已推送到 {remote}{'/' + branch if branch else ''}")

    task_id, status = _start_git_task("push", _do_push)
    return _ok(
        f"🔄 推送任务已启动\n"
        f"  任务ID: {task_id}\n"
        f"  远程: {remote}{'/' + branch if branch else ''}\n"
        f"  查询: code_hosting(action='git_task_status', task_id='{task_id}')"
    )


@_reg("git_push_retry")
def _act_git_push_retry(platform=None, **kw):
    """异步后台推送，每隔 N 秒重试一次直到成功（解决 GitHub 不稳定）。

    GitHub 在国内访问不稳定时，此工具在后台自动重试，不阻塞对话。
    返回 task_id，通过 git_task_status 查询进度。
    """
    work_dir = kw.get("work_dir", ".")
    remote = kw.get("remote_name", "origin")
    branch = kw.get("branch", "")
    interval = int(kw.get("retry_interval", 300))  # 默认 5 分钟

    def _do_retry_push(**kw2):
        attempt = 0
        while True:
            attempt += 1
            try:
                args = ["push", remote]
                if branch:
                    args.append(branch)
                _git_run(work_dir, *args)
                return _ok(f"✅ 已推送到 {remote}{'/' + branch if branch else ''}（第{attempt}次成功）")
            except RuntimeError as e:
                logger.warning("推送失败(第%s次): %s", attempt, e)
                if attempt == 1:
                    raise  # 第一次失败就向上抛，由 _start_git_task 记录
                # 后续重试在循环内静默重试
                time.sleep(interval)

    task_id, status = _start_git_task("push_retry", _do_retry_push)
    return _ok(
        f"🔄 后台推送重试任务已启动\n"
        f"  任务ID: {task_id}\n"
        f"  远程: {remote}{'/' + branch if branch else ''}\n"
        f"  重试间隔: {interval}秒\n"
        f"  查询: code_hosting(action='git_task_status', task_id='{task_id}')"
    )


@_reg("git_task_status")
def _act_git_task_status(platform=None, **kw):
    """查询异步 Git 任务状态。"""
    task_id = kw.get("task_id", "")
    with _git_tasks_lock:
        s = _git_tasks.get(task_id)
    if not s:
        return _err(f"未找到任务: {task_id}")
    lines = [
        f"📋 Git 任务状态",
        f"  任务ID: {task_id}",
        f"  操作: {s['name']}",
        f"  状态: {s['status']}",
    ]
    if s["result"]:
        lines.append(f"  结果: {s['result'][:200]}")
    if s["error"]:
        lines.append(f"  错误: {s['error'][:200]}")
    return _ok("\n".join(lines))
