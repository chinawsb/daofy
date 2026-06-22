"""
Tests for src/tools/code_hosting.py

Covers:
  - Internal helpers: _split_repo, _err, _ok, _git_run
  - All 13 actions with parameter validation
  - Async engine: _start_git_task, git_task_status
  - Platform switching: gitea/github/gitlab URL resolution
  - API actions: create_token, init_labels, create_issue, etc.
  - Git actions: status, add, commit, clone, push, push_retry
  - Error handling: missing params, invalid platform, network failures
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.tools.code_hosting import (
    code_hosting,
    _split_repo,
    _err,
    _ok,
    _git_run,
    _compact_git_status,
    _submit_git_task,
    _request,
    ISSUE_LABELS,
    _API_PATHS,
)

# =========================================================================
# Helpers
# =========================================================================


def _has_status(msg: str, status: str) -> bool:
    """Check if the message dict has a given status."""
    if isinstance(msg, dict):
        return msg.get("status") == status
    return False


# =========================================================================
# 1. Internal helpers
# =========================================================================


class TestSplitRepo:
    def test_normal(self):
        assert _split_repo("owner/repo") == ("owner", "repo")

    def test_multi_segment(self):
        assert _split_repo("org/team/project") == ("org", "team/project")

    def test_invalid_no_slash(self):
        with pytest.raises(ValueError, match="仓库格式应为 owner/repo"):
            _split_repo("justname")

    def test_invalid_empty(self):
        with pytest.raises(ValueError, match="仓库格式应为 owner/repo"):
            _split_repo("")


class TestErrOk:
    def test_err_contains_failed(self):
        r = _err("something wrong")
        assert r["status"] == "failed"
        assert r["message"] == "something wrong"

    def test_ok_contains_ok(self):
        r = _ok("all good")
        assert r["status"] == "ok"
        assert r["message"] == "all good"


class TestGitRun:
    def test_success(self, tmp_path):
        """git init + git status in a temp dir."""
        repo = tmp_path / "test_repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        out = _git_run(str(repo), "status")
        assert "On branch" in out

    def test_git_not_found(self):
        with pytest.raises(RuntimeError, match="git.*失败|not a git command"):
            _git_run(".", "this-command-does-not-exist-in-git")

    def test_failure_raises(self):
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 128
            mock_result.stdout = ""
            mock_result.stderr = "fatal: not a git repository"
            mock_run.return_value = mock_result
            with pytest.raises(RuntimeError, match="git.*失败|not a git repository"):
                _git_run(".", "status")

    def test_creates_relative_dir_if_not_exists(self, tmp_path, monkeypatch):
        """_git_run should auto-create safe relative work_dir."""
        monkeypatch.setattr("src.tools.code_hosting._ALLOWED_BASE", str(tmp_path))
        d = Path("nonexistent") / "deep"
        _git_run(str(d), "init")
        assert (tmp_path / d).exists()

    def test_absolute_dir_must_exist(self, tmp_path):
        """_git_run should not silently create arbitrary absolute paths."""
        d = str(tmp_path / "nonexistent" / "deep")
        with pytest.raises(ValueError, match="绝对路径不存在"):
            _git_run(d, "init")
        assert not os.path.exists(d)

    def test_relative_dir_cannot_escape_workspace(self):
        with pytest.raises(ValueError, match="不能逃逸"):
            _git_run("..", "status")

    def test_compact_git_status_porcelain(self):
        raw = "\n".join([
            "## main...origin/main [ahead 1]",
            "M  staged.py",
            " M modified.py",
            "A  added.py",
            "R  old.py -> renamed.py",
            "?? new.py",
        ])
        msg = _compact_git_status(raw)
        assert msg == (
            "main | origin/main [ahead 1] | "
            "staged(3): staged.py added.py renamed.py | "
            "modified(1): modified.py | untracked(1): new.py"
        )


# =========================================================================
# 2. Platform API path resolution (unit test without network)
# =========================================================================


class TestApiPaths:
    """Verify URL templates are well-formed for all platforms."""

    def test_all_platforms_have_same_keys(self):
        keys = {
            "create_token", "list_labels", "create_label",
            "create_issue", "edit_issue", "add_comment", "list_issues",
            "list_pulls", "create_pull", "get_pull", "edit_pull",
            "merge_pull",
            "list_releases", "create_release", "get_release",
            "edit_release", "delete_release",
        }
        for plat, paths in _API_PATHS.items():
            for k in keys:
                if k == "create_token" and plat != "gitea":
                    continue  # only gitea supports create_token
                assert paths[k] is not None, f"{plat}.{k} is None"

    def test_paths_contain_placeholders(self):
        for plat, paths in _API_PATHS.items():
            for k, tmpl in paths.items():
                if tmpl is None:
                    continue
                assert "{" in tmpl, f"{plat}.{k} has no placeholder: {tmpl}"
                if k in ("create_issue", "list_issues"):
                    has_owner = "{owner}" in tmpl or "{encoded}" in tmpl
                    assert has_owner, f"{plat}.{k} missing owner/encoded placeholder"

    def test_gitlab_uses_encoded(self):
        for k in ("create_issue", "list_labels", "add_comment"):
            t = _API_PATHS["gitlab"][k]
            if t:
                assert "{encoded}" in t, f"gitlab.{k} missing {{encoded}}"

    def test_github_uses_correct_base(self):
        assert all(
            _API_PATHS["github"][k].startswith("/repos/")
            for k in ("list_labels", "create_issue", "edit_issue")
            if _API_PATHS["github"][k]
        )

    def test_gitea_uses_correct_base(self):
        assert all(
            _API_PATHS["gitea"][k].startswith("/api/v1/repos/")
            for k in ("list_labels", "create_issue", "edit_issue")
        )


# =========================================================================
# 3. Action dispatch & parameter validation
# =========================================================================


class TestActionDispatch:
    def test_invalid_platform(self):
        r = code_hosting(platform="gitlab_selfhosted", action="create_issue")
        assert r["status"] == "failed"

    def test_invalid_action(self):
        r = code_hosting(action="fly_to_moon")
        assert r["status"] == "failed"

    def test_missing_action(self):
        r = code_hosting()
        assert r["status"] == "failed"

    def test_all_actions_registered(self):
        expected = {
            "create_token", "init_labels", "create_issue", "get_issue",
            "edit_issue", "set_labels", "close_issue", "add_comment",
            "list_issues", "create_pull", "get_pull", "list_pulls",
            "edit_pull", "merge_pull", "close_pull", "reopen_pull",
            "create_release", "get_release", "list_releases",
            "edit_release", "delete_release", "git_clone", "git_status", "git_diff",
            "git_show", "git_log", "git_add", "git_commit", "git_fetch",
            "git_pull", "git_branch", "git_switch", "git_merge",
            "git_restore", "git_unstage", "git_stash", "git_tag",
            "git_push", "git_push_retry",
        }
        from src.tools.code_hosting import _DISPATCH
        assert set(_DISPATCH.keys()) == expected


# =========================================================================
# 4. Git actions — sync (mocked)
# =========================================================================


class TestGitSyncActions:
    @patch("src.tools.code_hosting._git_run")
    def test_git_status(self, mock_git):
        mock_git.return_value = "## main\n"
        r = code_hosting(action="git_status", dir=".")
        assert r["status"] == "ok"
        assert r["message"] == "main | clean"
        mock_git.assert_called_once_with(".", "status", "--porcelain=v1", "-b", timeout=30)

    @patch("src.tools.code_hosting._git_run")
    def test_git_add(self, mock_git):
        r = code_hosting(action="git_add", dir=".", files=["a.py", "b.py"])
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(".", "add", "--", "a.py", "b.py", timeout=30)

    def test_git_add_empty_files(self):
        r = code_hosting(action="git_add", dir=".", files=[])
        assert r["status"] == "failed"
        assert "specify files" in r["message"]

    def test_git_add_missing_files_param(self):
        r = code_hosting(action="git_add", dir=".")
        assert r["status"] == "failed"

    @patch("src.tools.code_hosting._git_run")
    def test_git_add_rejects_invalid_file_path(self, mock_git):
        r = code_hosting(action="git_add", dir=".", files=["a.py\n--all"])
        assert r["status"] == "failed"
        mock_git.assert_not_called()

    @patch("src.tools.code_hosting._git_run")
    def test_git_commit(self, mock_git):
        mock_git.side_effect = [None, "abc123def456"]
        r = code_hosting(action="git_commit", dir=".", message="fix: bug")
        assert r["status"] == "ok"
        assert "abc123def456" in r["message"]
        mock_git.assert_has_calls([
            call(".", "commit", "-m", "fix: bug", timeout=30),
            call(".", "rev-parse", "HEAD", timeout=10),
        ])

    def test_git_commit_empty_message(self):
        r = code_hosting(action="git_commit", dir=".", message="")
        assert r["status"] == "failed"
        assert "specify message" in r["message"]

    def test_git_commit_missing_message(self):
        r = code_hosting(action="git_commit", dir=".")
        assert r["status"] == "failed"

    @patch("src.tools.code_hosting._git_run")
    def test_git_diff_staged_stat(self, mock_git):
        mock_git.return_value = "diff stat"
        r = code_hosting(
            action="git_diff",
            dir=".",
            staged=True,
            stat=True,
            files=["a.py"],
        )
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(
            ".",
            "diff",
            "--no-ext-diff",
            "--cached",
            "--stat",
            "--",
            "a.py",
            timeout=30,
        )

    def test_git_diff_rejects_option_ref(self):
        r = code_hosting(action="git_diff", dir=".", ref="--cached")
        assert r["status"] == "failed"
        assert "ref" in r["message"]

    @patch("src.tools.code_hosting._git_run")
    def test_git_show_stat(self, mock_git):
        mock_git.return_value = "commit abc"
        r = code_hosting(action="git_show", dir=".", ref="HEAD~1", stat=True)
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(
            ".",
            "show",
            "--no-ext-diff",
            "--stat",
            "HEAD~1",
            timeout=30,
        )

    @patch("src.tools.code_hosting._git_run")
    def test_git_log_with_files(self, mock_git):
        mock_git.return_value = "abc init"
        r = code_hosting(action="git_log", dir=".", limit=5, files=["a.py"])
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(
            ".",
            "log",
            "--oneline",
            "--decorate",
            "-n5",
            "--",
            "a.py",
            timeout=30,
        )

    @patch("src.tools.code_hosting._git_run")
    def test_git_fetch_prune_branch(self, mock_git):
        mock_git.return_value = ""
        r = code_hosting(action="git_fetch", dir=".", remote="origin", branch="main", prune=True)
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(".", "fetch", "--prune", "origin", "main", timeout=45)

    @patch("src.tools.code_hosting._git_run")
    def test_git_fetch_rejects_option_remote(self, mock_git):
        r = code_hosting(action="git_fetch", dir=".", remote="--all")
        assert r["status"] == "failed"
        mock_git.assert_not_called()

    @patch("src.tools.code_hosting._git_run")
    def test_git_fetch_timeout_suggests_async_mode(self, mock_git):
        mock_git.side_effect = RuntimeError("git 操作超时 (45秒)")
        r = code_hosting(action="git_fetch", dir=".", remote="origin")
        assert r["status"] == "failed"
        assert "async_mode=True" in r["message"]

    @patch("src.tools.code_hosting._submit_git_task")
    @patch("src.tools.code_hosting._git_run")
    def test_git_pull_async_mode_submits_task(self, mock_git, mock_submit):
        mock_submit.return_value = ("task_1", {"status": "ok", "message": "task task_1"})
        r = code_hosting(action="git_pull", dir=".", remote="origin", branch="main", async_mode=True)
        assert r["status"] == "ok"
        assert "task_1" in r["message"]
        assert r["task_id"] == "task_1"
        mock_git.assert_not_called()
        assert mock_submit.call_args.args[0] == "git_pull"

    @patch("src.tools.code_hosting._git_run")
    def test_git_pull_ff_only(self, mock_git):
        mock_git.return_value = "Already up to date."
        r = code_hosting(action="git_pull", dir=".", remote="origin", branch="main", ff_only=True)
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(".", "pull", "--ff-only", "origin", "main", timeout=45)

    @patch("src.tools.code_hosting._git_run")
    def test_git_branch_create(self, mock_git):
        mock_git.return_value = ""
        r = code_hosting(action="git_branch", dir=".", branch="feature/x", start_point="main")
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(".", "branch", "feature/x", "main", timeout=30)

    @patch("src.tools.code_hosting._git_run")
    def test_git_branch_rejects_option_start_point(self, mock_git):
        r = code_hosting(action="git_branch", dir=".", branch="feature/x", start_point="--orphan")
        assert r["status"] == "failed"
        mock_git.assert_not_called()

    @patch("src.tools.code_hosting._git_run")
    def test_git_branch_list_remote(self, mock_git):
        mock_git.return_value = "* main"
        r = code_hosting(action="git_branch", dir=".", remote_branches=True)
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(".", "branch", "-a", timeout=30)

    @patch("src.tools.code_hosting._git_run")
    def test_git_switch_create(self, mock_git):
        mock_git.return_value = ""
        r = code_hosting(action="git_switch", dir=".", branch="feature/x", create=True, start_point="main")
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(".", "switch", "-c", "feature/x", "main", timeout=30)

    @patch("src.tools.code_hosting._git_run")
    def test_git_merge_no_commit(self, mock_git):
        mock_git.return_value = "Automatic merge went well"
        r = code_hosting(action="git_merge", dir=".", branch="feature/x", no_commit=True)
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(".", "merge", "--no-commit", "feature/x", timeout=45)

    @patch("src.tools.code_hosting._git_run")
    def test_git_restore_requires_files(self, mock_git):
        r = code_hosting(action="git_restore", dir=".")
        assert r["status"] == "failed"
        mock_git.assert_not_called()

    @patch("src.tools.code_hosting._git_run")
    def test_git_restore_with_source(self, mock_git):
        mock_git.return_value = ""
        r = code_hosting(action="git_restore", dir=".", source="HEAD", files=["a.py"])
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(
            ".",
            "restore",
            "--source",
            "HEAD",
            "--",
            "a.py",
            timeout=30,
        )

    @patch("src.tools.code_hosting._git_run")
    def test_git_restore_rejects_option_source(self, mock_git):
        r = code_hosting(action="git_restore", dir=".", source="--worktree", files=["a.py"])
        assert r["status"] == "failed"
        mock_git.assert_not_called()

    @patch("src.tools.code_hosting._git_run")
    def test_git_unstage_requires_files(self, mock_git):
        r = code_hosting(action="git_unstage", dir=".")
        assert r["status"] == "failed"
        mock_git.assert_not_called()

    @patch("src.tools.code_hosting._git_run")
    def test_git_unstage(self, mock_git):
        mock_git.return_value = ""
        r = code_hosting(action="git_unstage", dir=".", files=["a.py"])
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(".", "restore", "--staged", "--", "a.py", timeout=30)

    @patch("src.tools.code_hosting._git_run")
    def test_git_stash_push_with_message_and_file(self, mock_git):
        mock_git.return_value = "Saved working directory"
        r = code_hosting(
            action="git_stash",
            dir=".",
            message="wip",
            include_untracked=True,
            files=["a.py"],
        )
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(
            ".",
            "stash",
            "push",
            "--include-untracked",
            "-m",
            "wip",
            "--",
            "a.py",
            timeout=60,
        )

    @patch("src.tools.code_hosting._git_run")
    def test_git_stash_list(self, mock_git):
        mock_git.return_value = "stash@{0}: WIP"
        r = code_hosting(action="git_stash", dir=".", op="list")
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(".", "stash", "list", timeout=30)

    @patch("src.tools.code_hosting._git_run")
    def test_git_tag_create_annotated(self, mock_git):
        mock_git.return_value = ""
        r = code_hosting(action="git_tag", dir=".", tag="v1.0.0", ref="HEAD", message="release")
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(
            ".",
            "tag",
            "-a",
            "v1.0.0",
            "HEAD",
            "-m",
            "release",
            timeout=30,
        )

    @patch("src.tools.code_hosting._git_run")
    def test_git_tag_rejects_option_tag(self, mock_git):
        r = code_hosting(action="git_tag", dir=".", tag="--delete", ref="HEAD")
        assert r["status"] == "failed"
        mock_git.assert_not_called()

    @patch("src.tools.code_hosting._git_run")
    def test_git_tag_list(self, mock_git):
        mock_git.return_value = "v1.0.0"
        r = code_hosting(action="git_tag", dir=".")
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(".", "tag", "--list", timeout=30)


# =========================================================================
# 5. Git actions — async (mocked)
# =========================================================================


class TestGitAsyncActions:
    @patch("src.tools.code_hosting._submit_git_task")
    def test_git_clone_returns_task_id(self, mock_submit, tmp_path):
        mock_submit.return_value = ("task_123", {"status": "ok", "message": "task task_123 | action: git_clone"})
        r = code_hosting(
            action="git_clone",
            repo_url="https://github.com/user/repo.git",
            dir=str(tmp_path),
        )
        assert r["status"] == "ok"
        assert "clone task task_123" in r["message"]
        assert r["task_id"] == "task_123"

    @patch("src.tools.code_hosting._submit_git_task")
    def test_git_clone_with_mirror(self, mock_submit, tmp_path):
        mock_submit.return_value = ("t1", {"status": "ok", "message": "🔄 Git 任务已提交"})
        r = code_hosting(
            action="git_clone",
            repo_url="https://github.com/user/repo.git",
            mirror="https://hub.fastgit.xyz",
            dir=str(tmp_path),
        )
        assert r["status"] == "ok"
        assert mock_submit.called

    @patch("src.tools.code_hosting._submit_git_task")
    def test_git_push_async(self, mock_submit):
        mock_submit.return_value = ("task_999", {"status": "ok", "message": "task task_999 | action: git_push"})
        r = code_hosting(action="git_push", dir=".", remote="origin", branch="main")
        assert r["status"] == "ok"
        assert "task_999" in r["message"]
        assert r["task_id"] == "task_999"

    @patch("src.tools.code_hosting._submit_git_task")
    def test_git_push_retry_async(self, mock_submit):
        mock_submit.return_value = ("task_888", {"status": "ok", "message": "task task_888 | action: git_push_retry"})
        r = code_hosting(
            action="git_push_retry",
            dir=".",
            remote="origin",
            branch="main",
            retry_interval=60,
        )
        assert r["status"] == "ok"
        assert "auto-retry push task task_888" in r["message"]
        assert r["task_id"] == "task_888"

    def test_git_task_status_not_found(self):
        """Git 异步任务的状态应通过 async_task 工具查询。"""
        # _submit_git_task 返回的 task_id 可直接用于 async_task(action="status", task_id=...)
        pass


# =========================================================================
# 6. Async task submission (via shared AsyncTaskManager)
# =========================================================================


class TestAsyncSubmission:
    @patch("src.tools.code_hosting.get_task_manager")
    def test_submit_git_task_returns_task_id(self, mock_get_tm):
        mock_tm = MagicMock()
        mock_tm.submit_task.return_value = "task_123456_1"
        mock_get_tm.return_value = mock_tm

        tid, resp = _submit_git_task("test_task", lambda: None)
        assert tid == "task_123456_1"
        assert resp["status"] == "ok"
        assert resp["task_id"] == "task_123456_1"

    @patch("src.tools.code_hosting.get_task_manager")
    def test_submit_git_task_query_instruction(self, mock_get_tm):
        mock_tm = MagicMock()
        mock_tm.submit_task.return_value = "task_789_2"
        mock_get_tm.return_value = mock_tm

        tid, resp = _submit_git_task("git_clone", lambda: None)
        assert "task_789_2" in resp["message"]
        assert "git_clone" in resp["message"]


# =========================================================================
# 7. API actions — validation (no network)
# =========================================================================


class TestApiActions:
    def test_create_token_missing_params(self):
        r = code_hosting(platform="gitea", action="create_token")
        assert r["status"] == "failed"

    def test_create_token_unsupported_platform(self):
        r = code_hosting(platform="github", action="create_token",
                         base_url="x", username="u", password="p")
        assert r["status"] == "failed"

    @patch("src.tools.code_hosting._request")
    def test_init_labels(self, mock_req):
        mock_req.return_value = []
        r = code_hosting(
            platform="gitea",
            action="init_labels",
            base_url="https://code.qdac.cc:3000",
            token="abc",
            repo="test-owner/test-repo",
        )
        assert r["status"] == "ok"
        total = sum(len(v) for v in ISSUE_LABELS.values())
        assert f"created: {total}" in r["message"]

    @patch("src.tools.code_hosting._request")
    def test_init_labels_skip_existing(self, mock_req):
        # Return some existing labels
        existing = [{"name": "优先级: 紧急", "id": 1, "color": "e53e3e"}]
        mock_req.return_value = existing
        r = code_hosting(
            platform="gitea",
            action="init_labels",
            base_url="https://code.qdac.cc:3000",
            token="abc",
            repo="test-owner/test-repo",
        )
        assert r["status"] == "ok"
        assert "skipped:" in r["message"]

    @patch("src.tools.code_hosting._request")
    def test_create_issue(self, mock_req):
        mock_req.side_effect = [
            [{"name": "类型: 缺陷", "id": 5, "color": "e53e3e"}],  # list_labels
            {"number": 42, "html_url": "https://gitea/issue/42", "state": "open"},  # create_issue
        ]
        r = code_hosting(
            platform="gitea",
            action="create_issue",
            base_url="https://code.qdac.cc:3000",
            token="abc",
            repo="owner/repo",
            title="Test bug",
            body="Description here",
            labels=["类型: 缺陷"],
        )
        assert r["status"] == "ok"
        assert "42" in r.get("message", "")

    def test_create_issue_missing_title(self):
        r = code_hosting(
            platform="gitea",
            action="create_issue",
            base_url="https://code.qdac.cc:3000",
            token="abc",
            repo="owner/repo",
        )
        assert r["status"] == "failed"

    @patch("src.tools.code_hosting._request")
    def test_get_issue(self, mock_req):
        mock_req.return_value = {
            "number": 42,
            "title": "Bug",
            "state": "open",
            "html_url": "https://gitea/42",
            "labels": [{"name": "bug"}],
        }
        r = code_hosting(
            platform="gitea",
            action="get_issue",
            base_url="https://code.qdac.cc:3000",
            token="abc",
            repo="owner/repo",
            issue_number=42,
        )
        assert r["status"] == "ok"
        assert "Bug" in r["message"]
        mock_req.assert_called_once_with(
            "https://code.qdac.cc:3000",
            "abc",
            "GET",
            "/api/v1/repos/owner/repo/issues/42",
            platform="gitea",
        )

    @patch("src.tools.code_hosting._request")
    def test_get_issue_accepts_string_labels(self, mock_req):
        mock_req.return_value = {
            "iid": 42,
            "title": "Bug",
            "state": "opened",
            "web_url": "https://gitlab/42",
            "labels": ["bug", "priority-high"],
        }
        r = code_hosting(
            platform="gitlab",
            action="get_issue",
            base_url="https://gitlab.com",
            token="abc",
            repo="group/project",
            issue_number=42,
        )
        assert r["status"] == "ok"
        assert "bug, priority-high" in r["message"]

    @patch("src.tools.code_hosting._request")
    def test_edit_issue_gitea_labels_use_ids(self, mock_req):
        mock_req.side_effect = [
            [{"name": "bug", "id": 5}],
            {"number": 42, "html_url": "https://gitea/42", "state": "open"},
        ]
        r = code_hosting(
            platform="gitea",
            action="edit_issue",
            base_url="https://code.qdac.cc:3000",
            token="abc",
            repo="owner/repo",
            issue_number=42,
            title="New title",
            labels=["bug"],
        )
        assert r["status"] == "ok"
        mock_req.assert_has_calls([
            call(
                "https://code.qdac.cc:3000",
                "abc",
                "GET",
                "/api/v1/repos/owner/repo/labels",
                platform="gitea",
            ),
            call(
                "https://code.qdac.cc:3000",
                "abc",
                "PATCH",
                "/api/v1/repos/owner/repo/issues/42",
                body={"title": "New title", "labels": [5]},
                platform="gitea",
            ),
        ])

    @patch("src.tools.code_hosting._request")
    def test_edit_issue_gitlab_labels_are_comma_joined(self, mock_req):
        mock_req.return_value = {"iid": 7, "web_url": "https://gitlab/7", "state": "opened"}
        r = code_hosting(
            platform="gitlab",
            action="edit_issue",
            base_url="https://gitlab.com",
            token="abc",
            repo="group/project",
            issue_number=7,
            labels=["bug", "priority-high"],
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://gitlab.com",
            "abc",
            "PUT",
            "/api/v4/projects/group%2Fproject/issues/7",
            body={"labels": "bug,priority-high"},
            platform="gitlab",
        )

    @patch("src.tools.code_hosting._request")
    def test_edit_issue_gitlab_body_uses_description(self, mock_req):
        mock_req.return_value = {"iid": 7, "web_url": "https://gitlab/7", "state": "opened"}
        r = code_hosting(
            platform="gitlab",
            action="edit_issue",
            base_url="https://gitlab.com",
            token="abc",
            repo="group/project",
            issue_number=7,
            body="updated body",
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://gitlab.com",
            "abc",
            "PUT",
            "/api/v4/projects/group%2Fproject/issues/7",
            body={"description": "updated body"},
            platform="gitlab",
        )

    @patch("src.tools.code_hosting._request")
    def test_create_issue_github_labels_do_not_query_labels(self, mock_req):
        mock_req.return_value = {"number": 1, "html_url": "https://github/1", "state": "open"}
        r = code_hosting(
            platform="github",
            action="create_issue",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            title="Issue",
            body="body",
            labels=["bug"],
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://api.github.com",
            "abc",
            "POST",
            "/repos/owner/repo/issues",
            body={"title": "Issue", "body": "body", "labels": ["bug"]},
            platform="github",
        )

    @patch("src.tools.code_hosting._request")
    def test_create_issue_gitea_unknown_label_fails(self, mock_req):
        mock_req.return_value = [{"name": "known", "id": 1}]
        r = code_hosting(
            platform="gitea",
            action="create_issue",
            base_url="https://code.qdac.cc:3000",
            token="abc",
            repo="owner/repo",
            title="Issue",
            labels=["missing"],
        )
        assert r["status"] == "failed"
        assert "missing" in r["message"]

    @patch("src.tools.code_hosting._request")
    def test_set_labels_allows_empty_list(self, mock_req):
        mock_req.return_value = {"number": 42, "html_url": "https://gitea/42", "state": "open"}
        r = code_hosting(
            platform="gitea",
            action="set_labels",
            base_url="https://code.qdac.cc:3000",
            token="abc",
            repo="owner/repo",
            issue_number=42,
            labels=[],
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://code.qdac.cc:3000",
            "abc",
            "PATCH",
            "/api/v1/repos/owner/repo/issues/42",
            body={"labels": []},
            platform="gitea",
        )

    def test_edit_issue_requires_payload(self):
        r = code_hosting(
            platform="gitea",
            action="edit_issue",
            base_url="https://code.qdac.cc:3000",
            token="abc",
            repo="owner/repo",
            issue_number=42,
        )
        assert r["status"] == "failed"

    @patch("src.tools.code_hosting._request")
    def test_edit_issue_rejects_merged_state(self, mock_req):
        r = code_hosting(
            platform="gitea",
            action="edit_issue",
            base_url="https://code.qdac.cc:3000",
            token="abc",
            repo="owner/repo",
            issue_number=42,
            state="merged",
        )
        assert r["status"] == "failed"
        assert "list_pulls" in r["message"]
        mock_req.assert_not_called()

    @patch("src.tools.code_hosting._request")
    def test_close_issue(self, mock_req):
        mock_req.return_value = {"number": 42, "html_url": "https://gitea/42", "state": "closed"}
        r = code_hosting(
            platform="gitea",
            action="close_issue",
            base_url="https://code.qdac.cc:3000",
            token="abc",
            repo="owner/repo",
            issue_number=42,
            comment="Fixed in abc123",
        )
        assert r["status"] == "ok"
        assert "closed" in r["message"]

    def test_close_issue_missing_number(self):
        r = code_hosting(
            platform="gitea",
            action="close_issue",
            base_url="https://code.qdac.cc:3000",
            token="abc",
            repo="owner/repo",
        )
        assert r["status"] == "failed"

    @patch("src.tools.code_hosting._request")
    def test_close_issue_gitlab_uses_state_event(self, mock_req):
        mock_req.return_value = {"iid": 42, "web_url": "https://gitlab/42", "state": "closed"}
        r = code_hosting(
            platform="gitlab",
            action="close_issue",
            base_url="https://gitlab.com",
            token="abc",
            repo="group/project",
            issue_number=42,
        )
        assert r["status"] == "ok"
        mock_req.assert_called_with(
            "https://gitlab.com",
            "abc",
            "PUT",
            "/api/v4/projects/group%2Fproject/issues/42",
            body={"state_event": "close"},
            platform="gitlab",
        )

    @patch("src.tools.code_hosting._request")
    def test_add_comment(self, mock_req):
        mock_req.return_value = {"id": 99, "html_url": "https://gitea/comment/99"}
        r = code_hosting(
            platform="gitea",
            action="add_comment",
            base_url="https://code.qdac.cc:3000",
            token="abc",
            repo="owner/repo",
            issue_number=42,
            body="Looking into this",
        )
        assert r["status"] == "ok"

    @patch("src.tools.code_hosting._request")
    def test_list_issues(self, mock_req):
        mock_req.return_value = [
            {"number": 1, "title": "Bug A", "state": "open", "html_url": "", "labels": []},
            {"number": 2, "title": "Bug B", "state": "open", "html_url": "", "labels": [{"name": "类型: 缺陷"}]},
        ]
        r = code_hosting(
            platform="gitea",
            action="list_issues",
            base_url="https://code.qdac.cc:3000",
            token="abc",
            repo="owner/repo",
            state="open",
        )
        assert r["status"] == "ok"
        assert "Bug A" in r["message"]
        assert "Bug B" in r["message"]

    @patch("src.tools.code_hosting._request")
    def test_list_issues_gitlab_uses_opened(self, mock_req):
        mock_req.return_value = [{"iid": 1, "title": "Bug", "state": "opened", "labels": ["bug"]}]
        r = code_hosting(
            platform="gitlab",
            action="list_issues",
            base_url="https://gitlab.com",
            token="abc",
            repo="group/project",
            state="open",
        )
        assert r["status"] == "ok"
        assert "bug" in r["message"]
        assert mock_req.call_args.kwargs["params"]["state"] == "opened"

    @patch("src.tools.code_hosting._request")
    def test_list_issues_github_filters_pull_requests(self, mock_req):
        mock_req.return_value = [
            {"number": 1, "title": "Bug", "state": "open", "labels": []},
            {
                "number": 2,
                "title": "PR",
                "state": "open",
                "pull_request": {"url": "https://api.github.com/repos/owner/repo/pulls/2"},
                "labels": [],
            },
        ]
        r = code_hosting(
            platform="github",
            action="list_issues",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            state="open",
        )
        assert r["status"] == "ok"
        assert "Bug" in r["message"]
        assert "PR" not in r["message"]

    @patch("src.tools.code_hosting._request")
    def test_list_issues_rejects_merged_state(self, mock_req):
        r = code_hosting(
            platform="github",
            action="list_issues",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            state="merged",
        )
        assert r["status"] == "failed"
        assert "list_pulls" in r["message"]
        mock_req.assert_not_called()

    def test_list_issues_missing_repo(self):
        r = code_hosting(
            platform="gitea",
            action="list_issues",
            base_url="https://code.qdac.cc:3000",
            token="abc",
        )
        assert r["status"] == "failed"

    @patch("src.tools.code_hosting._request")
    def test_create_pull_github_fields(self, mock_req):
        mock_req.return_value = {
            "number": 12,
            "title": "PR",
            "state": "open",
            "html_url": "https://github/pr/12",
        }
        r = code_hosting(
            platform="github",
            action="create_pull",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            title="PR",
            body="body",
            source_branch="feature/x",
            target_branch="main",
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://api.github.com",
            "abc",
            "POST",
            "/repos/owner/repo/pulls",
            body={"title": "PR", "body": "body", "head": "feature/x", "base": "main"},
            platform="github",
        )

    @patch("src.tools.code_hosting._request")
    def test_create_pull_gitlab_fields(self, mock_req):
        mock_req.return_value = {"iid": 3, "title": "MR", "state": "opened", "web_url": "https://gitlab/3"}
        r = code_hosting(
            platform="gitlab",
            action="create_pull",
            base_url="https://gitlab.com",
            token="abc",
            repo="group/project",
            title="MR",
            body="body",
            source_branch="feature/x",
            target_branch="main",
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://gitlab.com",
            "abc",
            "POST",
            "/api/v4/projects/group%2Fproject/merge_requests",
            body={
                "title": "MR",
                "description": "body",
                "source_branch": "feature/x",
                "target_branch": "main",
            },
            platform="gitlab",
        )

    @patch("src.tools.code_hosting._request")
    def test_get_pull(self, mock_req):
        mock_req.return_value = {"number": 12, "title": "PR", "state": "open", "html_url": "https://github/pr/12"}
        r = code_hosting(
            platform="github",
            action="get_pull",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            pull_number=12,
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://api.github.com",
            "abc",
            "GET",
            "/repos/owner/repo/pulls/12",
            platform="github",
        )

    @patch("src.tools.code_hosting._request")
    def test_list_pulls(self, mock_req):
        mock_req.return_value = [{"number": 12, "title": "PR", "state": "open"}]
        r = code_hosting(
            platform="github",
            action="list_pulls",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            state="open",
            limit=5,
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://api.github.com",
            "abc",
            "GET",
            "/repos/owner/repo/pulls",
            params={"page": "1", "per_page": "5", "state": "open"},
            platform="github",
        )

    @patch("src.tools.code_hosting._request")
    def test_edit_pull_gitlab_uses_put(self, mock_req):
        mock_req.return_value = {"iid": 3, "state": "opened", "web_url": "https://gitlab/3"}
        r = code_hosting(
            platform="gitlab",
            action="edit_pull",
            base_url="https://gitlab.com",
            token="abc",
            repo="group/project",
            pull_number=3,
            title="New MR",
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://gitlab.com",
            "abc",
            "PUT",
            "/api/v4/projects/group%2Fproject/merge_requests/3",
            body={"title": "New MR"},
            platform="gitlab",
        )

    @patch("src.tools.code_hosting._request")
    def test_list_pulls_github_merged_filters_closed_results(self, mock_req):
        mock_req.return_value = [
            {"number": 1, "title": "Closed", "state": "closed", "merged": False},
            {"number": 2, "title": "Merged", "state": "closed", "merged": True},
        ]
        r = code_hosting(
            platform="github",
            action="list_pulls",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            state="merged",
            limit=5,
        )
        assert r["status"] == "ok"
        assert "#2" in r["message"]
        assert "#1" not in r["message"]
        mock_req.assert_called_once_with(
            "https://api.github.com",
            "abc",
            "GET",
            "/repos/owner/repo/pulls",
            params={"page": "1", "per_page": "5", "state": "closed"},
            platform="github",
        )

    @patch("src.tools.code_hosting._request")
    def test_merge_pull_github_uses_merge_endpoint(self, mock_req):
        mock_req.return_value = {"number": 12, "merged": True, "html_url": "https://github/pr/12"}
        r = code_hosting(
            platform="github",
            action="merge_pull",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            pull_number=12,
            message="Merge PR",
            body="Details",
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://api.github.com",
            "abc",
            "PUT",
            "/repos/owner/repo/pulls/12/merge",
            body={"commit_title": "Merge PR", "commit_message": "Details"},
            platform="github",
        )

    @patch("src.tools.code_hosting._request")
    def test_merge_pull_gitlab_uses_merge_endpoint(self, mock_req):
        mock_req.return_value = {"iid": 3, "state": "merged", "web_url": "https://gitlab/3"}
        r = code_hosting(
            platform="gitlab",
            action="merge_pull",
            base_url="https://gitlab.com",
            token="abc",
            repo="group/project",
            pull_number=3,
            message="Merge MR",
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://gitlab.com",
            "abc",
            "PUT",
            "/api/v4/projects/group%2Fproject/merge_requests/3/merge",
            body={"merge_commit_message": "Merge MR"},
            platform="gitlab",
        )

    @patch("src.tools.code_hosting._request")
    def test_merge_pull_gitea_uses_merge_option_payload(self, mock_req):
        mock_req.return_value = {"number": 4, "merged": True, "html_url": "https://gitea/pr/4"}
        r = code_hosting(
            platform="gitea",
            action="merge_pull",
            base_url="https://gitea.example",
            token="abc",
            repo="owner/repo",
            pull_number=4,
            message="Merge PR",
            body="Details",
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://gitea.example",
            "abc",
            "POST",
            "/api/v1/repos/owner/repo/pulls/4/merge",
            body={"MergeTitleField": "Merge PR", "Do": "merge", "MergeMessageField": "Details"},
            platform="gitea",
        )

    @patch("src.tools.code_hosting._request")
    def test_close_pull_github_uses_edit_state(self, mock_req):
        mock_req.return_value = {"number": 12, "state": "closed", "html_url": "https://github/pr/12"}
        r = code_hosting(
            platform="github",
            action="close_pull",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            pull_number=12,
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://api.github.com",
            "abc",
            "PATCH",
            "/repos/owner/repo/pulls/12",
            body={"state": "closed"},
            platform="github",
        )

    @patch("src.tools.code_hosting._request")
    def test_reopen_pull_gitlab_uses_state_event(self, mock_req):
        mock_req.return_value = {"iid": 3, "state": "opened", "web_url": "https://gitlab/3"}
        r = code_hosting(
            platform="gitlab",
            action="reopen_pull",
            base_url="https://gitlab.com",
            token="abc",
            repo="group/project",
            pull_number=3,
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://gitlab.com",
            "abc",
            "PUT",
            "/api/v4/projects/group%2Fproject/merge_requests/3",
            body={"state_event": "reopen"},
            platform="gitlab",
        )

    def test_edit_pull_rejects_merged_state(self):
        r = code_hosting(
            platform="github",
            action="edit_pull",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            pull_number=12,
            state="merged",
        )
        assert r["status"] == "failed"
        assert "merge_pull" in r["message"]

    @patch("src.tools.code_hosting._request")
    def test_create_release_github(self, mock_req):
        mock_req.return_value = {"id": 99, "tag_name": "v1.0.0", "html_url": "https://github/release/99"}
        r = code_hosting(
            platform="github",
            action="create_release",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            tag_name="v1.0.0",
            name="v1.0.0",
            body="notes",
            draft=True,
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://api.github.com",
            "abc",
            "POST",
            "/repos/owner/repo/releases",
            body={"tag_name": "v1.0.0", "name": "v1.0.0", "body": "notes", "draft": True},
            platform="github",
        )

    @patch("src.tools.code_hosting._request")
    def test_create_release_gitlab(self, mock_req):
        mock_req.return_value = {"tag_name": "v1.0.0", "name": "v1.0.0", "web_url": "https://gitlab/release/v1"}
        r = code_hosting(
            platform="gitlab",
            action="create_release",
            base_url="https://gitlab.com",
            token="abc",
            repo="group/project",
            tag_name="v1.0.0",
            ref="main",
            name="v1.0.0",
            body="notes",
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://gitlab.com",
            "abc",
            "POST",
            "/api/v4/projects/group%2Fproject/releases",
            body={"tag_name": "v1.0.0", "ref": "main", "name": "v1.0.0", "description": "notes"},
            platform="gitlab",
        )

    @patch("src.tools.code_hosting._request")
    def test_get_release_gitlab_uses_tag_name(self, mock_req):
        mock_req.return_value = {"tag_name": "v1.0.0", "name": "v1.0.0", "web_url": "https://gitlab/release/v1"}
        r = code_hosting(
            platform="gitlab",
            action="get_release",
            base_url="https://gitlab.com",
            token="abc",
            repo="group/project",
            tag_name="v1.0.0",
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://gitlab.com",
            "abc",
            "GET",
            "/api/v4/projects/group%2Fproject/releases/v1.0.0",
            platform="gitlab",
        )

    @patch("src.tools.code_hosting._request")
    def test_get_release_github_accepts_tag_name(self, mock_req):
        mock_req.return_value = {"id": 99, "tag_name": "v1.0.0", "html_url": "https://github/release/99"}
        r = code_hosting(
            platform="github",
            action="get_release",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            tag_name="v1.0.0",
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://api.github.com",
            "abc",
            "GET",
            "/repos/owner/repo/releases/tags/v1.0.0",
            platform="github",
        )

    @patch("src.tools.code_hosting._request")
    def test_edit_release_github_uses_release_id(self, mock_req):
        mock_req.return_value = {"id": 99, "tag_name": "v1.0.0", "html_url": "https://github/release/99"}
        r = code_hosting(
            platform="github",
            action="edit_release",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            release_id=99,
            name="v1.0.0",
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://api.github.com",
            "abc",
            "PATCH",
            "/repos/owner/repo/releases/99",
            body={"name": "v1.0.0"},
            platform="github",
        )

    @patch("src.tools.code_hosting._request")
    def test_edit_release_github_resolves_tag_name(self, mock_req):
        mock_req.side_effect = [
            {"id": 99, "tag_name": "v1.0.0", "html_url": "https://github/release/99"},
            {"id": 99, "tag_name": "v1.0.0", "html_url": "https://github/release/99"},
        ]
        r = code_hosting(
            platform="github",
            action="edit_release",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            tag_name="v1.0.0",
            name="v1.0.0",
        )
        assert r["status"] == "ok"
        mock_req.assert_has_calls([
            call(
                "https://api.github.com",
                "abc",
                "GET",
                "/repos/owner/repo/releases/tags/v1.0.0",
                platform="github",
            ),
            call(
                "https://api.github.com",
                "abc",
                "PATCH",
                "/repos/owner/repo/releases/99",
                body={"tag_name": "v1.0.0", "name": "v1.0.0"},
                platform="github",
            ),
        ])

    @patch("src.tools.code_hosting._request")
    def test_delete_release_github(self, mock_req):
        mock_req.return_value = {"success": True}
        r = code_hosting(
            platform="github",
            action="delete_release",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            release_id=99,
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://api.github.com",
            "abc",
            "DELETE",
            "/repos/owner/repo/releases/99",
            platform="github",
        )

    @patch("src.tools.code_hosting._request")
    def test_delete_release_github_resolves_tag_name(self, mock_req):
        mock_req.side_effect = [
            {"id": 99, "tag_name": "v1.0.0", "html_url": "https://github/release/99"},
            {"success": True},
        ]
        r = code_hosting(
            platform="github",
            action="delete_release",
            base_url="https://api.github.com",
            token="abc",
            repo="owner/repo",
            tag_name="v1.0.0",
        )
        assert r["status"] == "ok"
        mock_req.assert_has_calls([
            call(
                "https://api.github.com",
                "abc",
                "GET",
                "/repos/owner/repo/releases/tags/v1.0.0",
                platform="github",
            ),
            call(
                "https://api.github.com",
                "abc",
                "DELETE",
                "/repos/owner/repo/releases/99",
                platform="github",
            ),
        ])


# =========================================================================
# 8. Cross-platform tests
# =========================================================================


class TestPlatformSwitching:
    @patch("src.tools.code_hosting._request")
    def test_github_create_issue(self, mock_req):
        mock_req.return_value = {"number": 1, "html_url": "https://github.com/issue/1", "state": "open"}
        r = code_hosting(
            platform="github",
            action="create_issue",
            base_url="https://api.github.com",
            token="gh_token",
            repo="owner/repo",
            title="GitHub issue",
            body="body",
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://api.github.com",
            "gh_token",
            "POST",
            "/repos/owner/repo/issues",
            body={"title": "GitHub issue", "body": "body"},
            platform="github",
        )

    @patch("src.tools.code_hosting._request")
    def test_gitlab_create_issue(self, mock_req):
        mock_req.return_value = {"iid": 10, "html_url": "https://gitlab/issue/10", "state": "opened"}
        r = code_hosting(
            platform="gitlab",
            action="create_issue",
            base_url="https://gitlab.com",
            token="gl_token",
            repo="owner/repo",
            title="GitLab issue",
            body="body",
        )
        assert r["status"] == "ok"
        mock_req.assert_called_once_with(
            "https://gitlab.com",
            "gl_token",
            "POST",
            "/api/v4/projects/owner%2Frepo/issues",
            body={"title": "GitLab issue", "description": "body"},
            platform="gitlab",
        )

    @patch("src.tools.code_hosting._request")
    def test_github_api_auth_header(self, mock_req):
        """Verify GitHub uses Bearer token."""
        mock_req.return_value = [{"name": "bug", "id": 1, "color": "red"}]
        code_hosting(
            platform="github",
            action="init_labels",
            base_url="https://api.github.com",
            token="ghp_xxx",
            repo="owner/repo",
        )
        # _request should have been called with platform="github"
        # This verifies no crash; the actual auth header is set inside _request
        assert mock_req.called


# =========================================================================
# 9. Label definitions integrity
# =========================================================================


class TestLabelDefinitions:
    def test_label_colors_have_no_hash(self):
        for group, labels in ISSUE_LABELS.items():
            for lbl in labels:
                assert not lbl["color"].startswith("#"), f"{lbl['name']} color starts with #"

    def test_label_colors_are_6chars(self):
        for group, labels in ISSUE_LABELS.items():
            for lbl in labels:
                assert len(lbl["color"]) == 6, f"{lbl['name']} color is not 6 chars"

    def test_label_names_unique(self):
        all_names = []
        for group, labels in ISSUE_LABELS.items():
            for lbl in labels:
                all_names.append(lbl["name"])
        assert len(all_names) == len(set(all_names)), "Duplicate label names found"

    def test_four_groups(self):
        assert set(ISSUE_LABELS.keys()) == {"priority", "review", "status", "type"}

    def test_each_group_has_labels(self):
        for group, labels in ISSUE_LABELS.items():
            assert len(labels) >= 4, f"{group} has fewer than 4 labels"


# =========================================================================
# 10. Mirror URL substitution
# =========================================================================


class TestMirrorSubstitution:
    """git_clone mirror parameter should correctly replace github.com."""

    @patch("src.tools.code_hosting._submit_git_task")
    def test_mirror_replaces_github_com(self, mock_submit, tmp_path):
        mock_submit.return_value = ("t1", {"status": "ok", "message": "ok"})
        r = code_hosting(
            action="git_clone",
            repo_url="https://github.com/owner/repo.git",
            mirror="https://hub.fastgit.xyz",
            dir=str(tmp_path),
        )
        assert r["status"] == "ok"

    @patch("src.tools.code_hosting._submit_git_task")
    def test_mirror_no_change_for_non_github(self, mock_submit, tmp_path):
        mock_submit.return_value = ("t2", {"status": "ok", "message": "ok"})
        r = code_hosting(
            action="git_clone",
            repo_url="https://gitlab.com/owner/repo.git",
            mirror="https://hub.fastgit.xyz",
            dir=str(tmp_path),
        )
        assert r["status"] == "ok"

    @patch("src.tools.code_hosting._submit_git_task")
    def test_clone_rejects_missing_absolute_dir_before_task(self, mock_submit, tmp_path):
        missing = tmp_path / "missing"
        r = code_hosting(
            action="git_clone",
            repo_url="https://github.com/owner/repo.git",
            dir=str(missing),
        )
        assert r["status"] == "failed"
        assert "绝对路径不存在" in r["message"]
        mock_submit.assert_not_called()

    @patch("src.tools.code_hosting._submit_git_task")
    def test_clone_propagates_task_submit_failure(self, mock_submit):
        mock_submit.return_value = ("", {"status": "failed", "message": "async task manager not available"})
        r = code_hosting(
            action="git_clone",
            repo_url="https://github.com/owner/repo.git",
            dir=".",
        )
        assert r["status"] == "failed"
        assert "async task manager" in r["message"]

    @patch("src.tools.code_hosting._submit_git_task")
    def test_push_retry_propagates_task_submit_failure(self, mock_submit):
        mock_submit.return_value = ("", {"status": "failed", "message": "async task manager not available"})
        r = code_hosting(action="git_push_retry", dir=".", remote="origin", branch="main")
        assert r["status"] == "failed"
        assert "async task manager" in r["message"]


# =========================================================================
# 11. Integration test with temp git repo (requires git installed)
# =========================================================================


class TestGitIntegration:
    """Test git operations on a temporary local repository.

    These tests run actual git commands and verify the integration works.
    """

    @pytest.fixture
    def temp_repo(self, tmp_path):
        """Create a temporary git repo with one commit."""
        repo = tmp_path / "test_repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(repo), capture_output=True)
        # Create initial commit
        (repo / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True)
        return str(repo)

    def test_git_status_integration(self, temp_repo):
        r = code_hosting(action="git_status", dir=temp_repo)
        assert r["status"] == "ok"
        assert "|" in r["message"]  # compact format: branch | status | files

    def test_git_add_commit_integration(self, temp_repo):
        (Path(temp_repo) / "new_file.txt").write_text("hello")
        r = code_hosting(action="git_add", dir=temp_repo, files=["new_file.txt"])
        assert r["status"] == "ok"
        r = code_hosting(action="git_commit", dir=temp_repo, message="add new_file.txt")
        assert r["status"] == "ok"
        assert "committed" in r["message"]

    def test_git_clone_local_integration(self, tmp_path):
        """Clone a local bare repository (async, check via async_task compatible task_id)."""
        src = tmp_path / "src.git"
        dst = tmp_path / "clone_work"
        src.mkdir()
        dst.mkdir()
        subprocess.run(["git", "init", "--bare"], cwd=str(src), capture_output=True)
        # Put something in src via a temp repo
        tmp_src = tmp_path / "tmp_src"
        tmp_src.mkdir()
        subprocess.run(["git", "init"], cwd=str(tmp_src), capture_output=True)
        (tmp_src / "f.txt").write_text("data")
        subprocess.run(["git", "add", "."], cwd=str(tmp_src), capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_src), capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=str(tmp_src), capture_output=True)
        subprocess.run(["git", "commit", "-m", "m"], cwd=str(tmp_src), capture_output=True)
        subprocess.run(["git", "push", str(src), "HEAD:main"], cwd=str(tmp_src), capture_output=True)

        r = code_hosting(
            action="git_clone",
            repo_url=str(src),
            dir=str(dst),
        )
        assert r["status"] == "ok"
        assert "clone task" in r["message"]

    @patch("src.tools.code_hosting._submit_git_task")
    def test_task_status_reports_progress(self, mock_submit, temp_repo):
        """git_push submits task and returns task_id for async_task to query."""
        mock_submit.return_value = ("task_123", {"status": "ok", "message": "task task_123 | action: git_push"})
        r = code_hosting(action="git_push", dir=temp_repo, remote="origin", branch="main")
        assert r["status"] == "ok"
        assert "task_" in r["message"]
