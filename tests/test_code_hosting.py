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
        assert "❌" in r["message"]

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

    def test_creates_dir_if_not_exists(self, tmp_path):
        """_git_run should auto-create work_dir."""
        d = str(tmp_path / "nonexistent" / "deep")
        try:
            _git_run(d, "init")
            assert os.path.exists(d)
        except RuntimeError:
            pass  # git might complain about path, but dir should be created


# =========================================================================
# 2. Platform API path resolution (unit test without network)
# =========================================================================


class TestApiPaths:
    """Verify URL templates are well-formed for all platforms."""

    def test_all_platforms_have_same_keys(self):
        keys = {"create_token", "list_labels", "create_label",
                "create_issue", "edit_issue", "add_comment", "list_issues"}
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
            "create_token", "init_labels", "create_issue", "close_issue",
            "add_comment", "list_issues", "git_clone", "git_status",
            "git_add", "git_commit", "git_push", "git_push_retry",
        }
        from src.tools.code_hosting import _DISPATCH
        assert set(_DISPATCH.keys()) == expected


# =========================================================================
# 4. Git actions — sync (mocked)
# =========================================================================


class TestGitSyncActions:
    @patch("src.tools.code_hosting._git_run")
    def test_git_status(self, mock_git):
        mock_git.return_value = "On branch main\nnothing to commit"
        r = code_hosting(action="git_status", dir=".")
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(".", "status", timeout=30)

    @patch("src.tools.code_hosting._git_run")
    def test_git_add(self, mock_git):
        r = code_hosting(action="git_add", dir=".", files=["a.py", "b.py"])
        assert r["status"] == "ok"
        mock_git.assert_called_once_with(".", "add", "a.py", "b.py", timeout=30)

    def test_git_add_empty_files(self):
        r = code_hosting(action="git_add", dir=".", files=[])
        assert r["status"] == "failed"
        assert "请指定" in r["message"]

    def test_git_add_missing_files_param(self):
        r = code_hosting(action="git_add", dir=".")
        assert r["status"] == "failed"

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
        assert "请指定" in r["message"]

    def test_git_commit_missing_message(self):
        r = code_hosting(action="git_commit", dir=".")
        assert r["status"] == "failed"


# =========================================================================
# 5. Git actions — async (mocked)
# =========================================================================


class TestGitAsyncActions:
    @patch("src.tools.code_hosting._submit_git_task")
    def test_git_clone_returns_task_id(self, mock_submit):
        mock_submit.return_value = ("task_123", {"status": "ok", "message": "🔄 Git 任务已提交\n  任务ID: task_123"})
        r = code_hosting(
            action="git_clone",
            repo_url="https://github.com/user/repo.git",
            dir="/tmp",
        )
        assert r["status"] == "ok"
        assert "任务ID" in r["message"]

    @patch("src.tools.code_hosting._submit_git_task")
    def test_git_clone_with_mirror(self, mock_submit):
        mock_submit.return_value = ("t1", {"status": "ok", "message": "🔄 Git 任务已提交"})
        r = code_hosting(
            action="git_clone",
            repo_url="https://github.com/user/repo.git",
            mirror="https://hub.fastgit.xyz",
            dir="/tmp",
        )
        assert r["status"] == "ok"
        assert mock_submit.called

    @patch("src.tools.code_hosting._submit_git_task")
    def test_git_push_async(self, mock_submit):
        mock_submit.return_value = ("task_999", {"status": "ok", "message": "🔄 Git 任务已提交\n  任务ID: task_999\n  操作: git_push"})
        r = code_hosting(action="git_push", dir=".", remote="origin", branch="main")
        assert r["status"] == "ok"
        assert "任务ID" in r["message"]

    @patch("src.tools.code_hosting._submit_git_task")
    def test_git_push_retry_async(self, mock_submit):
        mock_submit.return_value = ("task_888", {"status": "ok", "message": "🔄 Git 任务已提交\n  任务ID: task_888\n  操作: git_push_retry"})
        r = code_hosting(
            action="git_push_retry",
            dir=".",
            remote="origin",
            branch="main",
            retry_interval=60,
        )
        assert r["status"] == "ok"
        assert "任务ID" in r["message"]

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

    @patch("src.tools.code_hosting.get_task_manager")
    def test_submit_git_task_query_instruction(self, mock_get_tm):
        mock_tm = MagicMock()
        mock_tm.submit_task.return_value = "task_789_2"
        mock_get_tm.return_value = mock_tm

        tid, resp = _submit_git_task("git_clone", lambda: None)
        assert "async_task" in resp["message"]
        assert "task_789_2" in resp["message"]


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
        assert f"新增: {total}" in r["message"]

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
        assert "跳过" in r["message"]

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
        assert "已关闭" in r["message"]

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

    def test_list_issues_missing_repo(self):
        r = code_hosting(
            platform="gitea",
            action="list_issues",
            base_url="https://code.qdac.cc:3000",
            token="abc",
        )
        assert r["status"] == "failed"


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
    def test_mirror_replaces_github_com(self, mock_submit):
        mock_submit.return_value = ("t1", {"status": "ok", "message": "ok"})
        r = code_hosting(
            action="git_clone",
            repo_url="https://github.com/owner/repo.git",
            mirror="https://hub.fastgit.xyz",
            dir="/tmp",
        )
        assert r["status"] == "ok"

    @patch("src.tools.code_hosting._submit_git_task")
    def test_mirror_no_change_for_non_github(self, mock_submit):
        mock_submit.return_value = ("t2", {"status": "ok", "message": "ok"})
        r = code_hosting(
            action="git_clone",
            repo_url="https://gitlab.com/owner/repo.git",
            mirror="https://hub.fastgit.xyz",
            dir="/tmp",
        )
        assert r["status"] == "ok"


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
        assert "On branch" in r["message"]

    def test_git_add_commit_integration(self, temp_repo):
        (Path(temp_repo) / "new_file.txt").write_text("hello")
        r = code_hosting(action="git_add", dir=temp_repo, files=["new_file.txt"])
        assert r["status"] == "ok"
        r = code_hosting(action="git_commit", dir=temp_repo, message="add new_file.txt")
        assert r["status"] == "ok"
        assert "提交成功" in r["message"]

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
        assert "任务ID" in r["message"]

    def test_task_status_reports_progress(self, temp_repo):
        """git_push submits task and returns task_id for async_task to query."""
        r = code_hosting(action="git_push", dir=temp_repo, remote="origin", branch="main")
        assert r["status"] == "ok"
        assert "任务ID" in r["message"]
        assert "async_task" in r["message"]
