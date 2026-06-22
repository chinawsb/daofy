# Code Hosting: Git 和代码托管平台工具

`code_hosting` 是 Daofy 中所有 Git 操作和代码托管平台 API 的统一入口。Agent 必须通过这个工具执行 Git 操作，禁止直接用 shell 调 `git`。

## 支持平台

| 平台 | `platform` | 认证 |
| --- | --- | --- |
| Gitea | `gitea` | `Authorization: token ...` |
| GitHub | `github` | `Authorization: Bearer ...` |
| GitLab | `gitlab` | `PRIVATE-TOKEN` |
| Gitee | `gitee` | `Authorization: Bearer ...` |
| GitCode | `gitcode` | `PRIVATE-TOKEN` |

API 操作通用参数：

- `base_url`: 平台 API 根地址，例如 `https://code.qdac.cc:3000`、`https://api.github.com`。
- `token`: API 访问令牌。`create_token` 例外，使用 `username/password`。
- `repo`: 仓库名，格式为 `owner/repo`；GitLab/GitCode 支持 `group/subgroup/project`。

## Action 速查

| 分组 | Action | 说明 |
| --- | --- | --- |
| Git 只读 | `git_status` | 压缩格式查看仓库状态 |
| Git 只读 | `git_diff` | 查看工作区/暂存区差异 |
| Git 只读 | `git_show` | 查看提交或对象 |
| Git 只读 | `git_log` | 查看提交历史 |
| Git 本地写 | `git_add` | 暂存显式文件列表 |
| Git 本地写 | `git_commit` | 创建提交 |
| Git 远程同步 | `git_fetch` | 拉取远程引用 |
| Git 远程同步 | `git_pull` | 拉取并合并/变基 |
| Git 分支 | `git_branch` | 列出、创建、删除分支 |
| Git 分支 | `git_switch` | 切换或创建并切换分支 |
| Git 分支 | `git_merge` | 合并分支 |
| Git 恢复 | `git_restore` | 恢复显式文件，必须传 `files` |
| Git 恢复 | `git_unstage` | 取消暂存显式文件，必须传 `files` |
| Git 暂存栈 | `git_stash` | `push/list/pop/apply/drop/show` |
| Git 标签 | `git_tag` | 列出、创建、删除标签 |
| Git 异步 | `git_clone` | 后台克隆仓库，支持 GitHub mirror |
| Git 异步 | `git_push` | 后台推送 |
| Git 异步 | `git_push_retry` | 后台自动重试推送 |
| 平台 API | `create_token` | 创建 Gitea token |
| 平台 API | `init_labels` | 初始化内置流程标签 |
| 平台 API | `create_issue` | 创建工单 |
| 平台 API | `get_issue` | 查看工单 |
| 平台 API | `edit_issue` | 修改工单标题/正文/状态/标签 |
| 平台 API | `set_labels` | 设置工单标签，`labels=[]` 表示清空 |
| 平台 API | `close_issue` | 关闭工单，可附带评论 |
| 平台 API | `add_comment` | 添加工单评论 |
| 平台 API | `list_issues` | 查询工单列表 |
| 平台 API | `create_pull` | 创建 PR/MR |
| 平台 API | `get_pull` | 查看 PR/MR |
| 平台 API | `list_pulls` | 查询 PR/MR |
| 平台 API | `edit_pull` | 修改 PR/MR |
| 平台 API | `merge_pull` | 合并 PR/MR |
| 平台 API | `close_pull` | 关闭 PR/MR |
| 平台 API | `reopen_pull` | 重开 PR/MR |
| 平台 API | `create_release` | 创建 Release |
| 平台 API | `get_release` | 查看 Release |
| 平台 API | `list_releases` | 查询 Release |
| 平台 API | `edit_release` | 修改 Release |
| 平台 API | `delete_release` | 删除 Release |

## Git 用法

```python
code_hosting(action="git_status", dir=".")

code_hosting(action="git_diff", dir=".", staged=True, stat=True)
code_hosting(action="git_diff", dir=".", files=["src/server.py"])
code_hosting(action="git_show", dir=".", ref="HEAD", stat=True)
code_hosting(action="git_log", dir=".", limit=10, files=["src/tools/code_hosting.py"])

code_hosting(action="git_add", dir=".", files=["src/tools/code_hosting.py"])
code_hosting(action="git_commit", dir=".", message="feat: expand code_hosting git actions")

code_hosting(action="git_fetch", dir=".", remote="origin", branch="main", prune=True)
code_hosting(action="git_pull", dir=".", remote="origin", branch="main", ff_only=True)
code_hosting(action="git_pull", dir=".", remote="origin", branch="main", async_mode=True)

code_hosting(action="git_branch", dir=".")
code_hosting(action="git_branch", dir=".", branch="feature/code-hosting", start_point="main")
code_hosting(action="git_switch", dir=".", branch="feature/code-hosting")
code_hosting(action="git_switch", dir=".", branch="feature/code-hosting", create=True, start_point="main")
code_hosting(action="git_merge", dir=".", branch="feature/code-hosting", ff_only=True)
code_hosting(action="git_merge", dir=".", branch="feature/code-hosting", async_mode=True)

code_hosting(action="git_restore", dir=".", files=["src/server.py"])
code_hosting(action="git_restore", dir=".", source="HEAD", files=["src/server.py"])
code_hosting(action="git_unstage", dir=".", files=["src/server.py"])

code_hosting(action="git_stash", dir=".", message="wip", include_untracked=True)
code_hosting(action="git_stash", dir=".", op="list")
code_hosting(action="git_stash", dir=".", op="pop", ref="stash@{0}")

code_hosting(action="git_tag", dir=".")
code_hosting(action="git_tag", dir=".", tag="v1.2.3", ref="HEAD", message="v1.2.3")
code_hosting(action="git_tag", dir=".", tag="v1.2.3", delete=True)
```

保护规则：

- `git_restore` 和 `git_unstage` 必须传 `files`，避免误恢复整个工作区。
- `git_add/git_restore/git_unstage` 的 `files` 会放在 `--` 之后作为 pathspec，并拒绝空路径、换行和空字节。
- `git_diff/git_show/git_log` 的 `ref` 只能是引用或范围，不能传 `--xxx` 形式的 Git 选项。
- `dir` 相对路径限制在当前工作目录下；绝对路径只允许指向已存在目录，不会自动创建，避免传错路径时回退到当前仓库误操作。
- `git_status` 使用 `git status --porcelain=v1 -b` 解析稳定输出，不依赖 Git 本地化的人类提示文本。
- 远程耗时操作中，`git_clone/git_push/git_push_retry` 走后台任务；`git_fetch/git_pull/git_merge` 默认同步等待较短时间，网络慢或仓库大时传 `async_mode=True` 走后台任务。后台任务响应包含 `task_id` 字段，可直接用于 `async_task(action="status", task_id=...)` 查询进度。

## 克隆和推送

```python
code_hosting(
    action="git_clone",
    repo_url="https://github.com/owner/repo.git",
    dir=".",
)

code_hosting(
    action="git_clone",
    repo_url="https://github.com/owner/repo.git",
    mirror="https://hub.fastgit.xyz",
    dir=".",
)

code_hosting(action="git_push", dir=".", remote="origin", branch="main")
code_hosting(action="git_push_retry", dir=".", remote="origin", branch="main", retry_interval=300, max_retries=12)
```

## 工单 API 用法

```python
code_hosting(
    platform="gitea",
    action="create_issue",
    base_url="https://code.qdac.cc:3000",
    token="...",
    repo="owner/repo",
    title="Fix login crash",
    body="Repro steps and logs",
    labels=["类型/缺陷", "优先级/高"],
)

code_hosting(
    platform="gitea",
    action="get_issue",
    base_url="https://code.qdac.cc:3000",
    token="...",
    repo="owner/repo",
    issue_number=42,
)

code_hosting(
    platform="gitea",
    action="edit_issue",
    base_url="https://code.qdac.cc:3000",
    token="...",
    repo="owner/repo",
    issue_number=42,
    title="Fix login crash on Windows",
    state="open",
)

code_hosting(
    platform="gitea",
    action="set_labels",
    base_url="https://code.qdac.cc:3000",
    token="...",
    repo="owner/repo",
    issue_number=42,
    labels=["状态/处理中"],
)

code_hosting(
    platform="gitea",
    action="add_comment",
    base_url="https://code.qdac.cc:3000",
    token="...",
    repo="owner/repo",
    issue_number=42,
    body="Fixed in commit abc123.",
)

code_hosting(
    platform="gitea",
    action="close_issue",
    base_url="https://code.qdac.cc:3000",
    token="...",
    repo="owner/repo",
    issue_number=42,
    comment="Verified.",
)

code_hosting(
    platform="gitea",
    action="list_issues",
    base_url="https://code.qdac.cc:3000",
    token="...",
    repo="owner/repo",
    state="open",
    limit=20,
)
```

`set_labels(labels=[])` 表示清空标签。Gitea 使用标签 ID，GitHub/Gitee 使用标签名数组，GitLab/GitCode 使用逗号分隔标签名，工具内部会统一转换。
工单正文统一使用入参 `body`，工具会按平台转换字段：GitHub/Gitea/Gitee 使用 `body`，GitLab/GitCode 使用 `description`。
GitHub 的 issues API 会返回 PR 形态条目，`list_issues` 会过滤带 `pull_request` 字段的条目，避免把 PR 当工单展示。

## PR/MR API 用法

```python
code_hosting(
    platform="github",
    action="create_pull",
    base_url="https://api.github.com",
    token="...",
    repo="owner/repo",
    title="Fix login crash",
    body="Summary and test notes",
    source_branch="fix/login-crash",
    target_branch="main",
)

code_hosting(
    platform="gitlab",
    action="create_pull",
    base_url="https://gitlab.com",
    token="...",
    repo="group/project",
    title="Fix login crash",
    body="Summary and test notes",
    source_branch="fix/login-crash",
    target_branch="main",
)

code_hosting(
    platform="github",
    action="list_pulls",
    base_url="https://api.github.com",
    token="...",
    repo="owner/repo",
    state="open",
    limit=20,
)

code_hosting(
    platform="github",
    action="list_pulls",
    base_url="https://api.github.com",
    token="...",
    repo="owner/repo",
    state="merged",
    limit=20,
)

code_hosting(
    platform="github",
    action="get_pull",
    base_url="https://api.github.com",
    token="...",
    repo="owner/repo",
    pull_number=12,
)

code_hosting(
    platform="gitlab",
    action="edit_pull",
    base_url="https://gitlab.com",
    token="...",
    repo="group/project",
    pull_number=12,
    title="Updated MR title",
)

code_hosting(
    platform="github",
    action="merge_pull",
    base_url="https://api.github.com",
    token="...",
    repo="owner/repo",
    pull_number=12,
    message="Merge PR",
)

code_hosting(
    platform="github",
    action="close_pull",
    base_url="https://api.github.com",
    token="...",
    repo="owner/repo",
    pull_number=12,
)

code_hosting(
    platform="gitlab",
    action="reopen_pull",
    base_url="https://gitlab.com",
    token="...",
    repo="group/project",
    pull_number=12,
)
```

GitHub/Gitea/Gitee 使用 `head/base/body` 字段，GitLab/GitCode 使用 `source_branch/target_branch/description` 字段，工具内部统一转换。
`state="merged"` 只用于 `list_pulls` 过滤；要合并 PR/MR 使用 `merge_pull`，不要用 `edit_pull(state="merged")`。

## Release API 用法

```python
code_hosting(
    platform="github",
    action="create_release",
    base_url="https://api.github.com",
    token="...",
    repo="owner/repo",
    tag_name="v1.2.3",
    name="v1.2.3",
    body="Release notes",
    draft=False,
    prerelease=False,
)

code_hosting(
    platform="gitlab",
    action="create_release",
    base_url="https://gitlab.com",
    token="...",
    repo="group/project",
    tag_name="v1.2.3",
    ref="main",
    name="v1.2.3",
    body="Release notes",
)

code_hosting(
    platform="github",
    action="get_release",
    base_url="https://api.github.com",
    token="...",
    repo="owner/repo",
    tag_name="v1.2.3",
)

code_hosting(
    platform="gitlab",
    action="get_release",
    base_url="https://gitlab.com",
    token="...",
    repo="group/project",
    tag_name="v1.2.3",
)

code_hosting(
    platform="github",
    action="edit_release",
    base_url="https://api.github.com",
    token="...",
    repo="owner/repo",
    release_id=99,
    name="v1.2.3",
    body="Updated notes",
)

code_hosting(
    platform="github",
    action="delete_release",
    base_url="https://api.github.com",
    token="...",
    repo="owner/repo",
    tag_name="v1.2.3",
)
```

`get_release/edit_release/delete_release` 支持通过 `release_id` 或 `tag_name` 定位 Release。GitHub/Gitea/Gitee 传入 `tag_name` 时，工具会先查 `/releases/tags/{tag}` 并解析出 `release_id` 后再修改或删除。

`delete_release` 只删除代码托管平台上的 Release 对象，不会删除 Git tag。需要删除标签时，另行调用 `git_tag`：

```python
code_hosting(action="git_tag", dir=".", tag="v1.2.3", delete=True)
```

## 标签和 Token

```python
code_hosting(
    platform="gitea",
    action="create_token",
    base_url="https://code.qdac.cc:3000",
    username="alice",
    password="...",
    token_name="daofy-agent",
)

code_hosting(
    platform="gitea",
    action="init_labels",
    base_url="https://code.qdac.cc:3000",
    token="...",
    repo="owner/repo",
)
```

`create_token` 目前只支持 Gitea。GitHub/GitLab/Gitee/GitCode 的 token 需要在平台侧创建后传入。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| Git 认证失败 | 配置 SSH key、credential manager 或 HTTPS token；工具禁用交互式输入 |
| `git_restore` 失败 | 确认 `files` 指向仓库内真实文件 |
| `git_push` 网络不稳定 | 使用 `git_push_retry` 后台重试 |
| API 报 401/403 | 检查 `token` 权限和 `base_url` 是否指向 API 根地址 |
| GitHub 克隆慢 | `git_clone` 可传 `mirror`；推送仍依赖用户本机网络/代理配置 |
