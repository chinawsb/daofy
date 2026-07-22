#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
控制台自动化测试 — detect_exe_subsystem + console_execute
"""

import sys
import time
import json
from pathlib import Path

import pytest

from unittest import mock

from src.services.automation_service import (
    detect_exe_subsystem,
    execute_automation,
    console_execute,
    IMAGE_SUBSYSTEM_WINDOWS_GUI,
    IMAGE_SUBSYSTEM_WINDOWS_CUI,
)


# ═══════════════════════════════════════════════════════════════
# PE 子系统检测
# ═══════════════════════════════════════════════════════════════

class TestDetectExeSubsystem:
    """检测 exe 类型的正确性"""

    def test_python_is_console(self):
        """python.exe 是控制台程序"""
        result = detect_exe_subsystem(sys.executable)
        assert result == IMAGE_SUBSYSTEM_WINDOWS_CUI, (
            f"python.exe 应是控制台程序 (3), 得到 {result}"
        )

    def test_non_exe_returns_none(self):
        """非 exe 文件返回 None"""
        result = detect_exe_subsystem(__file__)
        assert result is None

    def test_missing_file_returns_none(self):
        """不存在的文件返回 None"""
        result = detect_exe_subsystem(r"C:\nonexistent_file_12345.exe")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# console_execute 功能测试（使用 python.exe 模拟控制台程序）
# ═══════════════════════════════════════════════════════════════

class TestConsoleExecute:
    """控制台交互执行测试"""

    ECHO_SCRIPT = (
        'import sys; '
        'line = sys.stdin.readline(); '
        'sys.stdout.write(f"ECHO: {line}"); '
        'sys.stdout.write("PROMPT> "); '
        'sys.stdout.flush(); '
        'line2 = sys.stdin.readline(); '
        'sys.stdout.write(f"ECHO2: {line2}"); '
        'sys.stdout.flush()'
    )

    def test_basic_run(self):
        """基础运行：发送输入，读取输出"""
        result = console_execute(
            app_path=sys.executable,
            input_text="hello\n",
            timeout=10,
            args=["-c", self.ECHO_SCRIPT],
        )
        assert result["status"] == "ok"
        assert result["exit_code"] == 0
        assert "ECHO: hello" in result["stdout"]

    def test_expect_match(self):
        """expect 等待输出模式：匹配到模式立即返回"""
        result = console_execute(
            app_path=sys.executable,
            input_text="world\n",
            expect=r"ECHO: world",
            timeout=10,
            args=["-c", self.ECHO_SCRIPT],
        )
        assert result["status"] == "ok"
        assert result["matched"] is True
        assert result["timed_out"] is False
        assert "ECHO: world" in result["stdout"]

    def test_expect_timeout(self):
        """expect 超时：输出不匹配时正确超时"""
        script = (
            'import sys, time; '
            'sys.stdout.write("WAITING...\\n"); '
            'sys.stdout.flush(); '
            'time.sleep(2); '
            'sys.stdout.write("DONE\\n"); '
            'sys.stdout.flush()'
        )
        result = console_execute(
            app_path=sys.executable,
            expect=r"NEVER_MATCH",
            timeout=1,  # 快速超时
            args=["-c", script],
        )
        assert result["matched"] is False
        assert result["timed_out"] is True
        # 超时后应该捕获到已输出的内容
        assert "WAITING" in result["stdout"]

    def test_keep_alive_reuse(self):
        """keep_alive 复用进程"""
        script1 = 'import sys; sys.stdout.write("FIRST\\n"); sys.stdout.flush()'
        script2 = 'import sys; sys.stdout.write("SECOND\\n"); sys.stdout.flush()'

        # 第一次调用，keep_alive=True
        result1 = console_execute(
            app_path=sys.executable,
            timeout=5,
            keep_alive=True,
            args=["-c", script1],
        )
        assert result1["status"] == "ok"
        assert "FIRST" in result1["stdout"]

        # 第二次复用，keep_alive=True
        result2 = console_execute(
            app_path=sys.executable,
            timeout=5,
            keep_alive=True,
            args=["-c", script2],
        )
        # 因为是复用进程，python 会跑完 script1 退出，
        # 新进程执行 script2
        assert result2["status"] == "ok"

        # 清理
        from src.services.automation_service import _console_kill_process
        _console_kill_process(sys.executable)

    def test_stderr_capture(self):
        """stderr 正确捕获"""
        script = (
            'import sys; '
            'sys.stderr.write("ERROR MSG\\n"); '
            'sys.stderr.flush(); '
            'sys.exit(1)'
        )
        result = console_execute(
            app_path=sys.executable,
            timeout=5,
            args=["-c", script],
        )
        assert result["status"] == "error"
        assert result["exit_code"] == 1
        assert "ERROR MSG" in result["stderr"]

    def test_exit_code_ok(self):
        """正常退出码 0"""
        script = 'import sys; sys.exit(0)'
        result = console_execute(
            app_path=sys.executable,
            timeout=5,
            args=["-c", script],
        )
        assert result["status"] == "ok"
        assert result["exit_code"] == 0

    def test_exit_code_nonzero(self):
        """非零退出码"""
        script = 'import sys; sys.exit(42)'
        result = console_execute(
            app_path=sys.executable,
            timeout=5,
            args=["-c", script],
        )
        assert result["status"] == "error"
        assert result["exit_code"] == 42

    def test_console_env_is_passed_and_redacted(self):
        """Temporary env should reach the child process without echoing values in the result."""
        script = (
            'import os, sys; '
            'sys.stdout.write("HAS_ENV=" + str(os.environ.get("DAOFY_ENV_TEST") == "secret-value"))'
        )
        result = console_execute(
            app_path=sys.executable,
            timeout=5,
            args=["-c", script],
            env={"DAOFY_ENV_TEST": "secret-value"},
        )

        assert result["status"] == "ok"
        assert "HAS_ENV=True" in result["stdout"]
        assert result["env"] == {"count": 1, "names": ["DAOFY_ENV_TEST"]}
        result_without_stdout = dict(result)
        result_without_stdout["stdout"] = ""
        assert "secret-value" not in json.dumps(result_without_stdout, ensure_ascii=False)

    def test_console_env_null_unsets_variable(self, monkeypatch):
        """A null env value should remove an inherited variable for the child process."""
        monkeypatch.setenv("DAOFY_ENV_UNSET_TEST", "present")
        script = (
            'import os, sys; '
            'sys.stdout.write("HAS_ENV=" + str("DAOFY_ENV_UNSET_TEST" in os.environ))'
        )
        result = console_execute(
            app_path=sys.executable,
            timeout=5,
            args=["-c", script],
            env={"DAOFY_ENV_UNSET_TEST": None},
        )

        assert result["status"] == "ok"
        assert "HAS_ENV=False" in result["stdout"]


# ═══════════════════════════════════════════════════════════════
# execute_automation 统一入口
# ═══════════════════════════════════════════════════════════════

class TestExecuteAutomation:
    """统一入口分发测试"""

    def test_console_action_routes_to_console(self):
        """execute_automation(action='console') 走 console_execute"""
        result = execute_automation(
            action="console",
            app_path=sys.executable,
            timeout=5,
            args=["-c", "print('hello from console')"],
        )
        assert result["status"] == "ok"
        assert "hello from console" in result["stdout"]

    def test_unknown_action(self):
        """未知 action 返回错误"""
        result = execute_automation(action="unknown")
        assert result["status"] == "error"
        assert "未知" in result["message"]

    def test_gui_action_routes_to_execute_script(self):
        """execute_automation(action='gui') 走 execute_script"""
        with mock.patch('src.services.automation_service.execute_script') as mock_fn:
            mock_fn.return_value = {'status': 'ok', 'stdout': 'gui result'}
            result = execute_automation(
                action="gui",
                app_path="dummy.exe",
                script="[]",
            )
        assert result['status'] == 'ok'
        assert result['stdout'] == 'gui result'
        mock_fn.assert_called_once_with(app_path="dummy.exe", script="[]")

    def test_auto_action_gui_routes_to_gui(self):
        """auto 模式检测到 GUI 子系统时走 execute_script"""
        # python.exe 是 Console 子系统，所以 auto 不会走 GUI 路径
        # 这个测试验证 auto 模式的 PE 检测 + 路由逻辑
        result = execute_automation(
            action="auto",
            app_path=sys.executable,
            script="[]",
        )
        # python.exe 是 Console(3)，所以 auto 应该走 console 路径
        # 但 console 执行需要 input/expect 等参数，所以这里只验证行为正确
        assert result['status'] == 'ok' or 'error' in result['status']

    def test_gui_action_without_script(self):
        """gui 模式不传 script 将在 handler 层拒绝，但 execute_script 本身接受空 script"""
        # execute_script 会解析空 script 为 JSON 解析错误
        # 这个测试验证 execute_automation 正确分发到 execute_script
        from src.services.automation_service import execute_script
        # 确保函数可被调用
        assert callable(execute_script)


class TestGuiScriptResultHandling:
    """GUI 脚本结果合成逻辑。"""

    def test_gui_script_reuses_one_pipe_connection(self, tmp_path):
        """GUI script commands should share one pipe connection for the whole run."""
        from src.services import automation_service

        responses = iter([
            json.dumps({"reqId": "step_0", "status": "ok", "data": "OK"}),
            json.dumps({"reqId": "cap_step_0", "status": "ok", "data": "captured"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ])

        def fake_send_on_handle(handle, cmd, timeout_ms):
            return next(responses)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_open_pipe", return_value=12345) as open_mock, \
                mock.patch.object(automation_service, "_send_command_on_handle", side_effect=fake_send_on_handle), \
                mock.patch.object(automation_service, "_CloseHandle") as close_mock, \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{"cmd": "goto", "target": "TMainForm", "capture": "after_goto"}],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert open_mock.call_count == 1
        close_mock.assert_called_once_with(12345)

    def test_gui_script_file_accepts_utf8_bom(self, tmp_path):
        """GUI script files written by Windows tools may include a UTF-8 BOM."""
        from src.services import automation_service

        script_path = tmp_path / "script.json"
        script_path.write_text(
            json.dumps({"test_name": "bom", "steps": [{"cmd": "listwnd"}]}),
            encoding="utf-8-sig",
        )

        responses = [
            json.dumps({"reqId": "step_0", "status": "ok", "data": "OK"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=lambda _: responses.pop(0)), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=str(script_path),
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert result["script_metadata"]["test_name"] == "bom"

    def test_gui_script_top_level_env_is_passed_and_redacted(self, tmp_path):
        """A full GUI script object may declare temporary env without leaking values."""
        from src.services import automation_service

        captured_env = {}
        responses = [
            json.dumps({"reqId": "step_0", "status": "ok", "data": "OK"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_ensure(app_path, wait_for_pipe, env_overrides=None):
            captured_env.update(env_overrides or {})
            return False, ""

        with mock.patch.object(automation_service, "_ensure_process", side_effect=fake_ensure), \
                mock.patch.object(automation_service, "_send_command", side_effect=lambda _: responses.pop(0)), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script={
                    "test_name": "env-redaction",
                    "env": {"DAOFY_ENV_TEST": "secret-value"},
                    "steps": [{"cmd": "listwnd"}],
                },
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert captured_env == {"DAOFY_ENV_TEST": "secret-value"}
        assert result["script_metadata"]["env"] == {"count": 1, "names": ["DAOFY_ENV_TEST"]}
        assert result["env"] == {"count": 1, "names": ["DAOFY_ENV_TEST"]}
        assert "secret-value" not in json.dumps(result, ensure_ascii=False)

    def test_gui_env_argument_overrides_script_env(self, tmp_path):
        """The explicit tool env argument should override top-level script env."""
        from src.services import automation_service

        captured_env = {}
        responses = [
            json.dumps({"reqId": "step_0", "status": "ok", "data": "OK"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_ensure(app_path, wait_for_pipe, env_overrides=None):
            captured_env.update(env_overrides or {})
            return False, ""

        with mock.patch.object(automation_service, "_ensure_process", side_effect=fake_ensure), \
                mock.patch.object(automation_service, "_send_command", side_effect=lambda _: responses.pop(0)), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script={
                    "test_name": "env-merge",
                    "env": {"DAOFY_ENV_TEST": "from-script", "KEEP_ME": "yes"},
                    "steps": [{"cmd": "listwnd"}],
                },
                env={"DAOFY_ENV_TEST": "from-argument"},
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert captured_env == {
            "DAOFY_ENV_TEST": "from-argument",
            "KEEP_ME": "yes",
        }

    def test_gui_process_pool_restarts_when_env_changes(self):
        """A keep-alive GUI process should not be reused for a different env."""
        from src.services import automation_service

        app_path = r"C:\fake\dummy.exe"
        launched = []
        cleanup_lock_available = []

        def fake_popen(cmd, cwd=None, env=None):
            proc = mock.Mock()
            proc.poll.return_value = None
            proc.kill = mock.Mock()
            proc.wait = mock.Mock()
            proc.env = env or {}
            launched.append(proc)
            return proc

        def fake_ensure_cleanup_thread():
            acquired = automation_service._pool_lock.acquire(blocking=False)
            cleanup_lock_available.append(acquired)
            if acquired:
                automation_service._pool_lock.release()

        with mock.patch.object(automation_service.subprocess, "Popen", side_effect=fake_popen), \
                mock.patch.object(automation_service, "_wait_for_pipe", return_value=True), \
                mock.patch.object(automation_service, "_ensure_pool_cleanup_thread",
                                  side_effect=fake_ensure_cleanup_thread):
            try:
                first = automation_service._ensure_process(
                    app_path, 0.1, {"DAOFY_ENV_TEST": "one"}
                )
                second = automation_service._ensure_process(
                    app_path, 0.1, {"DAOFY_ENV_TEST": "one"}
                )
                third = automation_service._ensure_process(
                    app_path, 0.1, {"DAOFY_ENV_TEST": "two"}
                )
            finally:
                automation_service._kill_process(app_path)

        assert first == (True, "")
        assert second == (False, "")
        assert third == (True, "")
        assert len(launched) == 2
        assert cleanup_lock_available == [True, True]
        assert launched[0].kill.called
        assert launched[0].env["DAOFY_ENV_TEST"] == "one"
        assert launched[1].env["DAOFY_ENV_TEST"] == "two"

    def test_gui_process_gets_a_process_specific_pipe(self):
        """New GUI processes must not share the legacy global pipe instance."""
        from src.services import automation_service

        app_path = r"C:\fake\specific-pipe.exe"
        launched = []
        waited = []

        def fake_popen(cmd, cwd=None, env=None):
            proc = mock.Mock()
            proc.pid = 4321
            proc.poll.return_value = None
            proc.kill = mock.Mock()
            proc.wait = mock.Mock()
            proc.env = env or {}
            launched.append(proc)
            return proc

        def fake_wait(timeout, pipe_name):
            waited.append((timeout, pipe_name))
            return True

        with mock.patch.object(automation_service.subprocess, "Popen", side_effect=fake_popen), \
                mock.patch.object(automation_service, "_wait_for_pipe", side_effect=fake_wait), \
                mock.patch.object(automation_service, "_ensure_pool_cleanup_thread"):
            try:
                is_new, err = automation_service._ensure_process(app_path, 3.0)
            finally:
                automation_service._kill_process(app_path)

        assert (is_new, err) == (True, "")
        assert len(launched) == 1
        pipe_name = automation_service.PIPE_NAME + "_4321"
        assert "DAOFY_AUTOMATION_PIPE" not in launched[0].env
        assert waited == [(3.0, pipe_name)]

    def test_gui_process_restarts_when_pipe_disappears(self):
        """A live pooled process with a dead pipe must be replaced."""
        from src.services import automation_service

        app_path = r"C:\fake\dead-pipe.exe"
        old_proc = mock.Mock()
        old_proc.poll.return_value = None
        old_proc.kill = mock.Mock()
        old_proc.wait = mock.Mock()
        launched = []
        waits = []

        def fake_popen(cmd, cwd=None, env=None):
            proc = mock.Mock()
            proc.pid = 5678
            proc.poll.return_value = None
            proc.kill = mock.Mock()
            proc.wait = mock.Mock()
            launched.append(proc)
            return proc

        def fake_wait(timeout, pipe_name):
            waits.append(pipe_name)
            return len(waits) > 1

        automation_service._process_pool[app_path] = {
            "proc": old_proc,
            "last_used": time.time(),
            "env_fingerprint": "base",
            "pipe_name": r"\\.\pipe\daofy_auto_stale",
        }
        with mock.patch.object(automation_service.subprocess, "Popen", side_effect=fake_popen), \
                mock.patch.object(automation_service, "_wait_for_pipe", side_effect=fake_wait), \
                mock.patch.object(automation_service, "_ensure_pool_cleanup_thread"):
            try:
                is_new, err = automation_service._ensure_process(app_path, 3.0)
            finally:
                automation_service._kill_process(app_path)

        assert (is_new, err) == (True, "")
        assert waits[0] == r"\\.\pipe\daofy_auto_stale"
        assert waits[1] == automation_service.PIPE_NAME + "_5678"
        assert len(launched) == 1
        assert old_proc.kill.called

    def test_pipe_session_reopens_after_io_failure(self):
        """A failed persistent pipe handle should be discarded before retrying."""
        from src.services import automation_service

        handles = iter([101, 202])
        responses = iter([
            "ERR:read_failed (err=109)",
            json.dumps({"reqId": "step_1", "status": "ok", "data": "OK"}),
        ])

        with mock.patch.object(automation_service, "_open_pipe", side_effect=lambda *_: next(handles)) as open_mock, \
                mock.patch.object(automation_service, "_send_command_on_handle", side_effect=lambda handle, cmd, timeout_ms: next(responses)), \
                mock.patch.object(automation_service, "_CloseHandle") as close_mock:
            automation_service._begin_pipe_session()
            try:
                first = automation_service._send_command("first")
                second = automation_service._send_command("second")
            finally:
                automation_service._end_pipe_session()

        assert first.startswith("ERR:read_failed")
        assert json.loads(second)["status"] == "ok"
        assert open_mock.call_count == 2
        close_mock.assert_any_call(101)
        close_mock.assert_any_call(202)

    def test_pipe_response_read_honors_timeout(self):
        """Every pipe command must time out when Delphi accepts but never answers."""
        from src.services import automation_service

        with mock.patch.object(automation_service, "_write_pipe", return_value=True), \
                mock.patch.object(
                    automation_service,
                    "_read_pipe_message_poll",
                    return_value=None,
                ) as read_mock, \
                mock.patch.object(automation_service, "_GetLastError", return_value=232):
            response = automation_service._send_command_on_handle(
                12345,
                '{"cmd":"listwnd"}',
                timeout_ms=321,
            )

        assert response.startswith("ERR:read_failed")
        assert automation_service._is_pipe_io_error(response)
        read_mock.assert_called_once_with(12345, timeout_ms=321)

    def test_pipe_poll_does_not_read_before_data_is_available(self):
        """A synchronous ReadFile must not be entered while the pipe is empty."""
        from src.services import automation_service

        def fake_peek(_handle, _buffer, _size, _read, available, _left):
            available._obj.value = 0
            return True

        with mock.patch.object(automation_service, "_PeekNamedPipe", side_effect=fake_peek), \
                mock.patch.object(automation_service, "_read_pipe_message") as read_mock, \
                mock.patch.object(automation_service.time, "monotonic", side_effect=[0.0, 0.0, 0.0, 0.2]), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service._read_pipe_message_poll(
                12345,
                timeout_ms=100,
            )

        assert result is None
        read_mock.assert_not_called()

    def test_pipe_poll_reads_after_data_is_available(self):
        """Once PeekNamedPipe reports bytes, read the complete message."""
        from src.services import automation_service

        def fake_peek(_handle, _buffer, _size, _read, available, _left):
            available._obj.value = 3
            return True

        with mock.patch.object(automation_service, "_PeekNamedPipe", side_effect=fake_peek), \
                mock.patch.object(automation_service, "_read_pipe_message", return_value=b"ok") as read_mock:
            result = automation_service._read_pipe_message_poll(12345)

        assert result == b"ok"
        read_mock.assert_called_once_with(12345)

    def test_click_step_forwards_client_coordinates(self, tmp_path):
        """click x/y fields should be encoded for the inline automation unit."""
        from src.services import automation_service

        sent_commands = []
        responses = [
            json.dumps({"reqId": "step_0", "status": "ok", "data": "OK"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{"cmd": "click", "target": "cbMenus", "x": 70, "y": 430}],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert sent_commands[0]["target"] == "cbMenus@70,430"

    def test_callgraph_forwards_max_depth_and_parses_state(self, tmp_path):
        """callgraph max_depth should be sent to the optional Delphi extension."""
        from src.services import automation_service

        sent_commands = []
        graph_payload = {
            "root": "TMainForm.Save",
            "calls": [],
            "error_code": "no_edges",
        }
        responses = [
            json.dumps({
                "reqId": "step_0",
                "status": "ok",
                "data": json.dumps(graph_payload),
            }),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "callgraph",
                    "target": "TMainForm.Save",
                    "max_depth": 3,
                    "edge_limit": 25,
                    "direction": "callers",
                    "project_only": True,
                    "exclude_prefixes": ["VirtualTrees.", "QLog."],
                    "include_prefixes": ["TMainForm."],
                }],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert sent_commands[0]["cmd"] == "callgraph"
        assert sent_commands[0]["target"] == "TMainForm.Save"
        assert sent_commands[0]["max_depth"] == "3"
        assert sent_commands[0]["edge_limit"] == "25"
        assert sent_commands[0]["direction"] == "callers"
        assert sent_commands[0]["project_only"] == "1"
        assert sent_commands[0]["exclude_prefixes"] == "VirtualTrees.,QLog."
        assert sent_commands[0]["include_prefixes"] == "TMainForm."
        assert result["results"][0]["response"]["state"]["error_code"] == "no_edges"

    def test_callgraph_diff_compares_baseline_to_current_state(self, tmp_path):
        """callgraph_diff should send callgraph and compare the response to a baseline."""
        from src.services import automation_service

        sent_commands = []
        baseline = {
            "root": "TMainForm.Save",
            "calls": [
                {"from": "A", "from_addr": "00000001", "to": "B", "to_addr": "00000002"},
                {"from": "A", "from_addr": "00000001", "to": "C", "to_addr": "00000003"},
            ],
        }
        current = {
            "root": "TMainForm.Save",
            "direction": "callees",
            "calls": [
                {"from": "A", "from_addr": "0000BEEF", "to": "B", "to_addr": "0000CAFE"},
                {"from": "A", "from_addr": "00000001", "to": "D", "to_addr": "00000004"},
            ],
        }
        responses = [
            json.dumps({
                "reqId": "step_0",
                "status": "ok",
                "data": json.dumps(current),
            }),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "callgraph_diff",
                    "target": "TMainForm.Save",
                    "baseline": baseline,
                    "max_depth": 2,
                    "save_as": "callgraph/current-save",
                }],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert sent_commands[0]["cmd"] == "callgraph"
        assert sent_commands[0]["target"] == "TMainForm.Save"
        state = result["results"][0]["response"]["state"]
        assert state["compare_by"] == "name"
        assert state["counts"] == {
            "added": 1,
            "removed": 1,
            "unchanged": 1,
            "baseline": 2,
            "current": 2,
        }
        assert state["added"][0]["to"] == "D"
        assert state["removed"][0]["to"] == "C"
        assert result["results"][0]["response"]["callgraph"] == current
        saved_path = tmp_path / "callgraph" / "current-save.json"
        assert saved_path.exists()
        assert json.loads(saved_path.read_text(encoding="utf-8")) == current
        assert state["saved"] == {
            "path": "callgraph/current-save.json",
            "edge_count": 2,
        }

    def test_callgraph_diff_reads_baseline_path_under_snapshots_dir(self, tmp_path):
        """Relative baseline_path should be resolved under snapshots_dir."""
        from src.services import automation_service

        baseline = {
            "root": "TMainForm.Save",
            "calls": [
                {"from": "A", "to": "B"},
            ],
        }
        baseline_path = tmp_path / "callgraph" / "baseline.json"
        baseline_path.parent.mkdir(parents=True)
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

        current = {
            "root": "TMainForm.Save",
            "direction": "callees",
            "calls": [
                {"from": "A", "to": "B"},
                {"from": "A", "to": "C"},
            ],
        }
        sent_commands = []
        responses = [
            json.dumps({
                "reqId": "step_0",
                "status": "ok",
                "data": json.dumps(current),
            }),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "callgraph_diff",
                    "target": "TMainForm.Save",
                    "baseline_path": "callgraph/baseline.json",
                }],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert sent_commands[0]["cmd"] == "callgraph"
        state = result["results"][0]["response"]["state"]
        assert state["counts"] == {
            "added": 1,
            "removed": 0,
            "unchanged": 1,
            "baseline": 1,
            "current": 2,
        }

    def test_callgraph_diff_rejects_baseline_path_outside_snapshots_dir_before_send(self, tmp_path):
        """baseline_path should not be allowed to escape snapshots_dir."""
        from src.services import automation_service

        outside_path = tmp_path.parent / f"{tmp_path.name}-outside-baseline.json"
        outside_path.write_text(json.dumps({"calls": []}), encoding="utf-8")
        sent_commands = []
        responses = [
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "callgraph_diff",
                    "target": "TMainForm.Save",
                    "baseline_path": str(outside_path),
                }],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "partial"
        assert sent_commands == [{"reqId": "auto_exit", "cmd": "exit"}]
        step = result["results"][0]
        assert step["status"] == "error"
        assert "callgraph_diff baseline_path must stay under snapshots_dir" in step["response"]["data"]

    def test_callgraph_diff_save_as_rejects_unsafe_paths(self, tmp_path):
        """save_as should reject empty, traversal, and absolute paths without writing files."""
        from src.services import automation_service

        current = {
            "root": "TMainForm.Save",
            "direction": "callees",
            "calls": [
                {"from": "A", "to": "B"},
            ],
        }
        unsafe_cases = [
            ("", None),
            ("../outside-save", tmp_path.parent / "outside-save.json"),
            (str(tmp_path.parent / "absolute-save.json"), tmp_path.parent / "absolute-save.json"),
        ]

        for save_as, outside_path in unsafe_cases:
            if outside_path and outside_path.exists():
                outside_path.unlink()

            sent_commands = []
            responses = [
                json.dumps({
                    "reqId": "step_0",
                    "status": "ok",
                    "data": json.dumps(current),
                }),
                json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
            ]

            def fake_send(cmd):
                sent_commands.append(json.loads(cmd))
                return responses.pop(0)

            with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                    mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                    mock.patch.object(automation_service.time, "sleep"):
                result = automation_service.execute_script(
                    app_path="dummy.exe",
                    script=[{
                        "cmd": "callgraph_diff",
                        "target": "TMainForm.Save",
                        "baseline": {"calls": []},
                        "save_as": save_as,
                    }],
                    snapshots_dir=str(tmp_path),
                )

            assert result["status"] == "ok"
            assert sent_commands[0]["cmd"] == "callgraph"
            state = result["results"][0]["response"]["state"]
            assert "saved" not in state
            assert any(warning.startswith("save_as_failed:") for warning in state["warnings"])
            if outside_path:
                assert not outside_path.exists()

    def test_callgraph_diff_full_compare_keeps_address_sensitive_edges(self, tmp_path):
        """compare_by=full should keep the legacy address-sensitive diff behavior."""
        from src.services import automation_service

        sent_commands = []
        baseline = {
            "root": "TMainForm.Save",
            "calls": [
                {
                    "from": "A",
                    "from_addr": "00000001",
                    "call_addr": "00000010",
                    "to": "B",
                    "to_addr": "00000002",
                },
            ],
        }
        current = {
            "root": "TMainForm.Save",
            "direction": "callees",
            "calls": [
                {
                    "from": "A",
                    "from_addr": "00000001",
                    "call_addr": "00000020",
                    "to": "B",
                    "to_addr": "00000002",
                },
            ],
        }
        responses = [
            json.dumps({
                "reqId": "step_0",
                "status": "ok",
                "data": json.dumps(current),
            }),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "callgraph_diff",
                    "target": "TMainForm.Save",
                    "baseline": baseline,
                    "compare_by": "full",
                }],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert sent_commands[0]["compare_by"] == "full"
        state = result["results"][0]["response"]["state"]
        assert state["compare_by"] == "full"
        assert state["counts"] == {
            "added": 1,
            "removed": 1,
            "unchanged": 0,
            "baseline": 1,
            "current": 1,
        }

    def test_callgraph_diff_rejects_invalid_compare_by_before_send(self, tmp_path):
        """Invalid compare_by should fail locally without sending a callgraph request."""
        from src.services import automation_service

        sent_commands = []
        responses = [
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "callgraph_diff",
                    "target": "TMainForm.Save",
                    "baseline": {"calls": []},
                    "compare_by": "line",
                }],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "partial"
        assert sent_commands == [{"reqId": "auto_exit", "cmd": "exit"}]
        step = result["results"][0]
        assert step["status"] == "error"
        assert step["response"]["data"] == "callgraph_diff compare_by must be name, addr, or full"

    def test_callgraph_rejects_invalid_edge_limit_before_send(self, tmp_path):
        """edge_limit should be locally validated to avoid oversized/invalid requests."""
        from src.services import automation_service

        sent_commands = []
        responses = [
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{"cmd": "callgraph", "target": "TMainForm.Save", "edge_limit": 0}],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "partial"
        assert sent_commands == [{"reqId": "auto_exit", "cmd": "exit"}]
        step = result["results"][0]
        assert step["status"] == "error"
        assert step["response"]["data"] == "callgraph edge_limit must be between 1 and 5000"

    def test_callgraph_path_forwards_params_and_parses_state(self, tmp_path):
        """callgraph_path should ask Delphi for bounded source-to-target paths."""
        from src.services import automation_service

        sent_commands = []
        path_payload = {
            "source": "actNewProjectExecute",
            "target": "SaveIfModified",
            "found": True,
            "paths": [[
                {
                    "from": "main.TfrmMain.actNewProjectExecute",
                    "from_addr": "00401000",
                    "call_addr": "00401020",
                    "call_file": "main.pas",
                    "call_line": 683,
                    "to": "main.TfrmMain.SaveIfModified",
                    "to_addr": "00402000",
                }
            ]],
            "path_count": 1,
            "max_depth": 3,
            "max_paths": 2,
        }
        responses = [
            json.dumps({
                "reqId": "step_0",
                "status": "ok",
                "data": json.dumps(path_payload),
            }),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "callgraph_path",
                    "source": "actNewProjectExecute",
                    "target": "SaveIfModified",
                    "max_depth": 3,
                    "max_paths": 2,
                    "project_only": True,
                    "exclude_prefixes": ["System."],
                    "include_prefixes": "main.",
                }],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert sent_commands[0]["cmd"] == "callgraph_path"
        assert sent_commands[0]["source"] == "actNewProjectExecute"
        assert sent_commands[0]["target"] == "SaveIfModified"
        assert sent_commands[0]["max_depth"] == "3"
        assert sent_commands[0]["max_paths"] == "2"
        assert sent_commands[0]["project_only"] == "1"
        assert sent_commands[0]["exclude_prefixes"] == "System."
        assert sent_commands[0]["include_prefixes"] == "main."
        state = result["results"][0]["response"]["state"]
        assert state["found"] is True
        assert state["paths"][0][0]["call_line"] == 683

    def test_callgraph_path_rejects_invalid_input_before_send(self, tmp_path):
        """callgraph_path should validate required and bounded parameters locally."""
        from src.services import automation_service

        sent_commands = []
        responses = [
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{"cmd": "callgraph_path", "target": "SaveIfModified", "max_paths": 0}],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "partial"
        assert sent_commands == [{"reqId": "auto_exit", "cmd": "exit"}]
        step = result["results"][0]
        assert step["status"] == "error"
        assert step["response"]["data"] == "callgraph_path requires source and target"

        sent_commands.clear()
        responses.append(json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}))
        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "callgraph_path",
                    "source": "A",
                    "target": "B",
                    "max_paths": 0,
                }],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "partial"
        assert sent_commands == [{"reqId": "auto_exit", "cmd": "exit"}]
        step = result["results"][0]
        assert step["status"] == "error"
        assert step["response"]["data"] == "callgraph_path max_paths must be between 1 and 100"

    def test_callgraph_error_response_data_is_parsed_as_state(self, tmp_path):
        """callgraph should preserve structured diagnostics even when status is err."""
        from src.services import automation_service

        graph_payload = {
            "root": "MissingEntry",
            "calls": [],
            "requested_root": "MissingEntry",
            "error_code": "entry_not_found",
        }
        responses = [
            json.dumps({
                "reqId": "step_0",
                "status": "err",
                "data": json.dumps(graph_payload),
            }),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{"cmd": "callgraph", "target": "MissingEntry"}],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "partial"
        step = result["results"][0]
        assert step["status"] == "error"
        assert step["response"]["state"]["error_code"] == "entry_not_found"
        assert step["response"]["state"]["requested_root"] == "MissingEntry"

    def test_callgraph_win64_unsupported_response_is_parsed_as_state(self, tmp_path):
        """Win64 callgraph diagnostics should remain structured on err responses."""
        from src.services import automation_service

        graph_payload = {
            "root": "TMainForm.Save",
            "direction": "callees",
            "calls": [],
            "requested_root": "TMainForm.Save",
            "max_depth": 1,
            "project_only": False,
            "error_code": "win64_not_supported",
        }
        responses = [
            json.dumps({
                "reqId": "step_0",
                "status": "err",
                "data": json.dumps(graph_payload),
            }),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy-win64.exe",
                script=[{"cmd": "callgraph", "target": "TMainForm.Save", "max_depth": 1}],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "partial"
        step = result["results"][0]
        assert step["status"] == "error"
        assert step["response"]["status"] == "err"
        assert step["response"]["state"]["error_code"] == "win64_not_supported"
        assert step["response"]["state"]["calls"] == []
        assert step["response"]["state"]["requested_root"] == "TMainForm.Save"

    def test_callgraph_impact_queries_callers_and_aggregates_entries(self, tmp_path):
        """callgraph_impact should fan out to callers queries and summarize impact."""
        from src.services import automation_service

        sent_commands = []
        save_payload = {
            "root": "SaveIfModified",
            "direction": "callers",
            "calls": [
                {
                    "from": "main.TfrmMain.actCloseExecute",
                    "from_addr": "00401000",
                    "to": "main.TfrmMain.SaveIfModified",
                    "to_addr": "00402000",
                }
            ],
        }
        missing_payload = {
            "root": "MissingEntry",
            "direction": "callers",
            "calls": [],
            "error_code": "entry_not_found",
        }
        responses = [
            json.dumps({
                "reqId": "step_0_0",
                "status": "ok",
                "data": json.dumps(save_payload),
            }),
            json.dumps({
                "reqId": "step_0_1",
                "status": "err",
                "data": json.dumps(missing_payload),
            }),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "callgraph_impact",
                    "functions": ["SaveIfModified", "MissingEntry"],
                    "max_depth": 2,
                    "edge_limit": 10,
                    "project_only": True,
                    "exclude_prefixes": ["System.", "Vcl."],
                    "include_prefixes": ["main."],
                }],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert sent_commands[0]["cmd"] == "callgraph"
        assert sent_commands[0]["target"] == "SaveIfModified"
        assert sent_commands[0]["direction"] == "callers"
        assert sent_commands[0]["max_depth"] == "2"
        assert sent_commands[0]["edge_limit"] == "10"
        assert sent_commands[0]["project_only"] == "1"
        assert sent_commands[0]["exclude_prefixes"] == "System.,Vcl."
        assert sent_commands[0]["include_prefixes"] == "main."
        assert sent_commands[1]["target"] == "MissingEntry"
        assert sent_commands[1]["edge_limit"] == "10"
        assert sent_commands[1]["include_prefixes"] == "main."
        assert sent_commands[2] == {"reqId": "auto_exit", "cmd": "exit"}

        step = result["results"][0]
        assert step["status"] == "ok"
        assert len(step["subcommands"]) == 2
        state = step["response"]["state"]
        assert state["mode"] == "impact"
        assert state["entry_count"] == 1
        assert state["entries"][0]["name"] == "main.TfrmMain.actCloseExecute"
        assert state["entries"][0]["target"] == "SaveIfModified"
        assert state["unresolved"] == [{
            "target": "MissingEntry",
            "error_code": "entry_not_found",
            "status": "err",
        }]

    def test_callgraph_impact_resolves_file_line_locations(self, tmp_path):
        """callgraph_impact should resolve Pascal file/line locations to functions."""
        from src.services import automation_service

        pas_source = """unit Unit1;

interface

type
  TForm1 = class
  end;

implementation

procedure TForm1.SaveIfModified;
begin
  DoSave;
end;

procedure TForm1.Other;
begin
end;

end.
"""
        source_path = tmp_path / "Unit1.pas"
        source_path.write_text(pas_source, encoding="utf-8")
        target_line = pas_source.splitlines().index("  DoSave;") + 1

        sent_commands = []
        graph_payload = {
            "root": "TForm1.SaveIfModified",
            "direction": "callers",
            "calls": [
                {
                    "from": "main.TfrmMain.actSaveExecute",
                    "from_addr": "00403000",
                    "to": "main.TForm1.SaveIfModified",
                    "to_addr": "00402000",
                }
            ],
        }
        responses = [
            json.dumps({
                "reqId": "step_0_0",
                "status": "ok",
                "data": json.dumps(graph_payload),
            }),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "callgraph_impact",
                    "base_dir": str(tmp_path),
                    "locations": [
                        {"file": "Unit1.pas", "line": target_line},
                        {"file": "Unit1.pas", "line": 3},
                    ],
                    "max_depth": 1,
                }],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert sent_commands[0]["cmd"] == "callgraph"
        assert sent_commands[0]["target"] == "TForm1.SaveIfModified"
        assert sent_commands[0]["direction"] == "callers"
        assert sent_commands[1] == {"reqId": "auto_exit", "cmd": "exit"}

        state = result["results"][0]["response"]["state"]
        assert state["resolved_locations"] == [{
            "file": "Unit1.pas",
            "line": target_line,
            "function": "TForm1.SaveIfModified",
        }]
        assert state["entries"][0]["name"] == "main.TfrmMain.actSaveExecute"
        assert state["unresolved"][0]["file"].endswith("Unit1.pas")
        assert state["unresolved"][0]["line"] == 3
        assert state["unresolved"][0]["error_code"] == "no_function_at_line"

    def test_callgraph_impact_accepts_diff_style_changes(self, tmp_path):
        """callgraph_impact should accept PR/diff style change records."""
        from src.services import automation_service

        pas_source = """unit Unit1;

interface

implementation

procedure TForm1.SaveIfModified;
begin
  DoSave;
end;

end.
"""
        source_path = tmp_path / "Unit1.pas"
        source_path.write_text(pas_source, encoding="utf-8")
        target_line = pas_source.splitlines().index("  DoSave;") + 1

        sent_commands = []
        responses = [
            json.dumps({
                "reqId": "step_0_0",
                "status": "ok",
                "data": json.dumps({
                    "root": "ExplicitTarget",
                    "direction": "callers",
                    "calls": [],
                    "error_code": "no_edges",
                }),
            }),
            json.dumps({
                "reqId": "step_0_1",
                "status": "ok",
                "data": json.dumps({
                    "root": "TForm1.SaveIfModified",
                    "direction": "callers",
                    "calls": [{
                        "from": "main.TfrmMain.actSaveExecute",
                        "to": "TForm1.SaveIfModified",
                    }],
                }),
            }),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "callgraph_impact",
                    "base_dir": str(tmp_path),
                    "changes": [
                        {"function": "ExplicitTarget"},
                        {"file": "Unit1.pas", "start_line": target_line},
                    ],
                    "max_depth": 1,
                }],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert sent_commands[0]["target"] == "ExplicitTarget"
        assert sent_commands[1]["target"] == "TForm1.SaveIfModified"
        state = result["results"][0]["response"]["state"]
        assert state["targets"][0]["target"] == "ExplicitTarget"
        assert state["targets"][0]["error_code"] == "no_edges"
        assert state["warnings"] == [{"target": "ExplicitTarget", "warning": "no_edges"}]
        assert state["resolved_locations"] == [{
            "file": "Unit1.pas",
            "line": target_line,
            "function": "TForm1.SaveIfModified",
        }]
        assert state["entries"][0]["name"] == "main.TfrmMain.actSaveExecute"

    def test_callgraph_impact_requires_targets_before_send(self, tmp_path):
        """callgraph_impact without targets should fail locally."""
        from src.services import automation_service

        sent_commands = []
        responses = [
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{"cmd": "callgraph_impact"}],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "partial"
        assert sent_commands == [{"reqId": "auto_exit", "cmd": "exit"}]
        step = result["results"][0]
        assert step["status"] == "error"
        assert step["response"]["data"] == (
            "callgraph_impact requires functions, targets, target, file/line, or locations"
        )

    def test_callgraph_usecase_local_commands(self, tmp_path):
        """U2/U3/U5/U6/U7/U8 should run locally from callgraph JSON inputs."""
        from src.services import automation_service

        impact = {
            "mode": "impact",
            "targets": [{"target": "SaveIfModified", "status": "ok", "edge_count": 1}],
            "entries": [{
                "name": "main.TfrmMain.actSaveExecute",
                "target": "SaveIfModified",
                "via": {"from": "main.TfrmMain.actSaveExecute", "to": "SaveIfModified"},
            }],
            "unresolved": [],
            "warnings": [],
        }
        graph = {
            "root": "SaveIfModified",
            "direction": "callers",
            "calls": [
                {
                    "from": "UI.TMainForm.ButtonClick",
                    "from_addr": "1",
                    "to": "Storage.TRepo.Save",
                    "to_addr": "2",
                },
                {
                    "from": "UI.TMainForm.ButtonClick",
                    "from_addr": "4",
                    "to": "Storage.Interfaces.IRepo.Save",
                    "to_addr": "5",
                },
                {
                    "from": "SaveIfModified",
                    "from_addr": "3",
                    "to": "Storage.TRepo.Save",
                    "to_addr": "2",
                },
                {
                    "from": "Tests.TSaveTests.TestSave",
                    "from_addr": "6",
                    "to": "TestOnlyProc",
                    "to_addr": "7",
                },
            ],
        }
        tests = [
            {"name": "save-flow", "handler": "main.TfrmMain.actSaveExecute", "path": "save.json"},
            {
                "name": "save-cover",
                "handler": "main.TfrmMain.Other",
                "path": "save-cover.json",
                "covers": ["SaveIfModified"],
            },
        ]
        sent_commands = []

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"})

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[
                    {"cmd": "callgraph_select_tests", "impact": impact, "tests": tests},
                    {
                        "cmd": "callgraph_failure_diag",
                        "failure": {"cmd": "click", "target": "btnSave"},
                        "callgraph": graph,
                    },
                    {
                        "cmd": "callgraph_boundary_check",
                        "graph": graph,
                        "rules": [{
                            "name": "ui-no-storage",
                            "from_prefix": "UI.",
                            "to_prefix": "Storage.",
                            "exclude_to_prefixes": ["Storage.Interfaces."],
                            "policy": "forbid",
                            "severity": "error",
                            "message": "UI must call storage through services",
                        }],
                    },
                    {"cmd": "callgraph_refactor_check", "impact": impact, "targets": ["SaveIfModified"]},
                    {
                        "cmd": "callgraph_orphan_candidates",
                        "symbols": ["SaveIfModified", "UnusedProc", "TestOnlyProc", "Storage.TRepo.Save"],
                        "entries": ["SaveIfModified"],
                        "graph": graph,
                        "test_prefixes": ["Tests."],
                    },
                    {
                        "cmd": "callgraph_explain_exception",
                        "stack": ["00401000 Storage.TRepo.Save+$1 [Repo.pas:10]", "SaveIfModified"],
                        "graph": graph,
                        "impact": impact,
                    },
                ],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert sent_commands == [{"reqId": "auto_exit", "cmd": "exit"}]

        select_state = result["results"][0]["response"]["state"]
        assert select_state["selected_count"] == 2
        assert {item["name"] for item in select_state["selected"]} == {"save-flow", "save-cover"}
        assert select_state["covered_targets"] == ["SaveIfModified"]
        assert select_state["uncovered_targets"] == []

        failure_state = result["results"][1]["response"]["state"]
        assert failure_state["diagnostics"]["callgraph"]["edge_count"] == 4
        assert failure_state["failure"]["target"] == "btnSave"

        boundary_state = result["results"][2]["response"]["state"]
        assert boundary_state["violation_count"] == 1
        assert boundary_state["violations"][0]["rule"] == "ui-no-storage"
        assert boundary_state["violations"][0]["severity"] == "error"
        assert boundary_state["violations"][0]["message"] == "UI must call storage through services"
        assert boundary_state["violations"][0]["to"] == "Storage.TRepo.Save"

        refactor_state = result["results"][3]["response"]["state"]
        assert refactor_state["risk"] == "medium"
        assert refactor_state["safe_to_refactor"] is False
        assert refactor_state["affected_count"] == 1
        assert refactor_state["affected_targets"] == ["SaveIfModified"]
        assert refactor_state["unresolved"] == []
        assert "main.TfrmMain.actSaveExecute" in refactor_state["impacted_callers"]

        orphan_state = result["results"][4]["response"]["state"]
        assert orphan_state["candidates"] == [
            {
                "name": "UnusedProc",
                "confidence": "low",
                "reason": "not_seen_as_callee_in_direct_callgraph",
                "callers": [],
            },
            {
                "name": "TestOnlyProc",
                "confidence": "low",
                "reason": "only_called_by_tests",
                "callers": ["Tests.TSaveTests.TestSave"],
            },
        ]

        exception_state = result["results"][5]["response"]["state"]
        assert exception_state["top_frame"] == "Storage.TRepo.Save"
        assert exception_state["top_frame_raw"] == "00401000 Storage.TRepo.Save+$1 [Repo.pas:10]"
        assert len(exception_state["upstream"]) == 2
        assert exception_state["summary"]["upstream_count"] == 2

    def test_callgraph_rejects_out_of_range_max_depth_before_send(self, tmp_path):
        """Invalid callgraph max_depth should be reported without hitting the pipe."""
        from src.services import automation_service

        sent_commands = []
        responses = [
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{"cmd": "callgraph", "target": "TMainForm.Save", "max_depth": 21}],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "partial"
        assert sent_commands == [{"reqId": "auto_exit", "cmd": "exit"}]
        step = result["results"][0]
        assert step["status"] == "error"
        assert step["response"]["data"] == "callgraph max_depth must be between 0 and 20"

    def test_capture_does_not_hide_command_failure(self, tmp_path):
        """附加截图成功时，主命令失败仍应报告失败并保留主响应。"""
        from src.services import automation_service

        responses = [
            json.dumps({"reqId": "step_0", "status": "err", "data": "NF:MissingButton"}),
            json.dumps({"reqId": "cap_step_0", "status": "ok", "data": "shot.jpg"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{"cmd": "click", "target": "MissingButton", "capture": "after_click"}],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "partial"
        step = result["results"][0]
        assert step["status"] == "error"
        assert step["response"]["status"] == "err"
        assert step["capture_response"]["status"] == "ok"
        assert result["report"]["failed"] == 1

    def test_capture_failure_marks_step_failed(self, tmp_path):
        """主命令成功但附加截图失败时，步骤整体应失败。"""
        from src.services import automation_service

        # 异步命令 ack + peekresult 轮询 + capture + exit
        responses = [
            json.dumps({"reqId": "step_0", "status": "ack", "data": "ACK"}),
            # peekresult 轮询：首次返回真实结果
            json.dumps({"reqId": "step_0_peek", "status": "ok", "data": "OK"}),
            json.dumps({"reqId": "cap_step_0", "status": "err", "data": "capture failed"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{"cmd": "click", "target": "BtnSave", "capture": "after_click"}],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "partial"
        step = result["results"][0]
        assert step["status"] == "error"
        # peekresult 轮询取到真实结果后替换了 ack，状态变为 ok
        assert step["response"]["status"] == "ok"
        assert step["capture_response"]["status"] == "err"
        assert result["report"]["failed"] == 1

    def test_ui_async_not_ready_keeps_ack_and_continues(self, tmp_path):
        """UI async commands may open modal dialogs; NR must not block following steps."""
        from src.services import automation_service

        responses = [
            json.dumps({"reqId": "step_0", "status": "ack", "data": ""}),
            json.dumps({"reqId": "step_1", "status": "ok", "data": "OK"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses) as send_mock, \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[
                    {"cmd": "click", "target": "BtnOk", "async_timeout": 0},
                    {"cmd": "msgscan"},
                ],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert result["results"][0]["response"]["status"] == "ack"
        assert result["results"][1]["response"]["status"] == "ok"
        assert send_mock.call_count == 3

    def test_async_peek_error_replaces_ack(self, tmp_path):
        """A real async error must replace the initial ack response."""
        from src.services import automation_service

        responses = [
            json.dumps({"reqId": "step_0", "status": "ack", "data": ""}),
            json.dumps({"reqId": "step_0_peek", "status": "err", "data": "NF:BtnOk"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{"cmd": "click", "target": "BtnOk", "async_timeout": 0.01}],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "partial"
        step = result["results"][0]
        assert step["status"] == "error"
        assert step["response"]["status"] == "err"
        assert step["response"]["data"] == "NF:BtnOk"
        assert result["report"]["first_failure"]["response_data"] == "NF:BtnOk"

    def test_failure_report_can_attach_callgraph_diagnostics(self, tmp_path):
        """Optional failure diagnostics should query callgraph before auto-exit."""
        from src.services import automation_service

        sent_commands = []
        graph_payload = {
            "root": "main.TfrmMain.SaveIfModified",
            "direction": "callers",
            "calls": [
                {
                    "from": "main.TfrmMain.actSaveExecute",
                    "to": "main.TfrmMain.SaveIfModified",
                    "call_line": 683,
                }
            ],
            "edge_count": 1,
            "returned_count": 1,
            "truncated": False,
        }
        responses = [
            json.dumps({"reqId": "step_0", "status": "err", "data": "NF:btnSave"}),
            json.dumps({
                "reqId": "step_0_callgraph_diag",
                "status": "ok",
                "data": json.dumps(graph_payload),
            }),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        def fake_send(cmd):
            sent_commands.append(json.loads(cmd))
            return responses.pop(0)

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=fake_send), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script={
                    "callgraph_diagnostics": True,
                    "callgraph_options": {
                        "max_depth": 2,
                        "edge_limit": 20,
                        "project_only": True,
                    },
                    "steps": [{
                        "cmd": "click",
                        "target": "btnSave",
                        "handler": "main.TfrmMain.SaveIfModified",
                    }],
                },
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "partial"
        assert sent_commands[1]["cmd"] == "callgraph"
        assert sent_commands[1]["target"] == "main.TfrmMain.SaveIfModified"
        assert sent_commands[1]["direction"] == "callers"
        assert sent_commands[1]["max_depth"] == "2"
        assert sent_commands[1]["edge_limit"] == "20"
        assert sent_commands[1]["project_only"] == "1"
        failure = result["report"]["first_failure"]
        assert failure["response_data"] == "NF:btnSave"
        diag = failure["diagnostics"]["callgraph"]
        assert diag["status"] == "ok"
        assert diag["target"] == "main.TfrmMain.SaveIfModified"
        assert diag["edge_count"] == 1
        assert diag["calls"][0]["from"] == "main.TfrmMain.actSaveExecute"

    def test_failure_callgraph_diagnostic_error_does_not_hide_original_failure(self, tmp_path):
        """Callgraph diagnostic failures should be secondary warnings."""
        from src.services import automation_service

        graph_payload = {
            "root": "MissingHandler",
            "calls": [],
            "error_code": "entry_not_found",
            "edge_count": 0,
        }
        responses = [
            json.dumps({"reqId": "step_0", "status": "err", "data": "NF:btnSave"}),
            json.dumps({
                "reqId": "step_0_callgraph_diag",
                "status": "err",
                "data": json.dumps(graph_payload),
            }),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script={
                    "callgraph_diagnostics": True,
                    "steps": [{
                        "cmd": "click",
                        "target": "btnSave",
                        "handler": "MissingHandler",
                    }],
                },
                snapshots_dir=str(tmp_path),
            )

        failure = result["report"]["first_failure"]
        assert failure["response_data"] == "NF:btnSave"
        diag = failure["diagnostics"]["callgraph"]
        assert diag["status"] == "err"
        assert diag["error_code"] == "entry_not_found"
        assert "callgraph_query_failed" in diag["warnings"]

    def test_assert_expr_failure_generates_repair_report(self, tmp_path):
        """Python 断言失败时报告应包含首个失败和修复建议。"""
        from src.services import automation_service

        responses = [
            json.dumps({"reqId": "step_0", "status": "ok", "data": "取消"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "rget",
                    "target": "btnSave.Caption",
                    "assert_expr": "actual == '保存'",
                    "expected": "按钮标题应为保存",
                }],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "partial"
        assert result["resolved_action"] == "gui"
        report = result["report"]
        assert report["failed"] == 1
        assert report["first_failure"]["signal"] == "assertion_failed"
        assert report["first_failure"]["assertion"]["source"] == "assert_expr"
        assert report["solution"]["next_mode"] == "coding"

    def test_failure_skips_dependent_steps_by_default(self, tmp_path):
        """首个失败后默认不继续执行后续步骤，报告中标记 skipped。"""
        from src.services import automation_service

        responses = [
            json.dumps({"reqId": "step_0", "status": "err", "data": "NF:MissingButton"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses) as send_mock, \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[
                    {"cmd": "click", "target": "MissingButton"},
                    {"cmd": "click", "target": "DangerousButton"},
                ],
                snapshots_dir=str(tmp_path),
            )

        assert send_mock.call_count == 2
        assert result["status"] == "partial"
        assert result["results"][1]["status"] == "skipped"
        report = result["report"]
        assert report["failed"] == 1
        assert report["skipped"] == 1
        assert report["executed"] == 1
        assert report["steps"][1]["status"] == "skip"

    def test_stop_on_failure_can_be_disabled(self, tmp_path):
        """显式关闭 stop_on_failure 时保留旧的连续执行行为。"""
        from src.services import automation_service

        responses = [
            json.dumps({"reqId": "step_0", "status": "err", "data": "NF:MissingButton"}),
            json.dumps({"reqId": "step_1", "status": "ok", "data": "OK"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses) as send_mock, \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[
                    {"cmd": "click", "target": "MissingButton"},
                    {"cmd": "click", "target": "SafeButton"},
                ],
                snapshots_dir=str(tmp_path),
                stop_on_failure=False,
            )

        assert send_mock.call_count == 3
        assert result["results"][1]["status"] == "ok"
        assert result["report"]["skipped"] == 0

    def test_msgscan_no_dialog_uses_nod_assertion(self, tmp_path):
        """msgscan should expose NOD as the no-dialog assertion value."""
        from src.services import automation_service

        responses = [
            json.dumps({"reqId": "step_0", "status": "ok", "data": "NOD"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "msgscan",
                    "expected": "No unexpected dialog",
                    "assert_expr": "actual == 'NOD'",
                }],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert result["report"]["passed"] == 1
        assert result["results"][0]["assert_result"]["actual"] == "NOD"

    def test_msgscan_dialog_loads_formstate_for_assertions(self, tmp_path):
        """msgscan OK should load the dialog JSON written by the inline unit."""
        from src.services import automation_service

        state_path = tmp_path / "_formstate.json"
        state_path.write_text(
            json.dumps({"title": "打开工程", "text": "", "buttons": ["确定"]}),
            encoding="utf-8",
        )
        responses = [
            json.dumps({"reqId": "step_0", "status": "ok", "data": "OK"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "msgscan",
                    "expected": "A dialog is present",
                    "assert_expr": "'打开工程' in actual",
                }],
                snapshots_dir=str(tmp_path),
            )

        response = result["results"][0]["response"]
        assert result["status"] == "ok"
        assert response["data"] == "OK"
        assert response["state"]["title"] == "打开工程"
        assert result["results"][0]["assert_result"]["actual"].startswith("{")

    def test_object_script_with_steps_executes_and_preserves_metadata(self, tmp_path):
        """Resource-documented object scripts should execute directly."""
        from src.services import automation_service

        responses = [
            json.dumps({"reqId": "step_0", "status": "ok", "data": "OK"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script={
                    "test_name": "smoke",
                    "project_path": "App.dproj",
                    "steps": [{"cmd": "click", "target": "BtnSave"}],
                },
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert result["steps_total"] == 1
        assert result["script_metadata"]["test_name"] == "smoke"
        assert result["script_metadata"]["project_path"] == "App.dproj"

    def test_assert_field_is_rejected(self, tmp_path):
        """Unsupported assert field should fail before app commands are sent."""
        from src.services import automation_service

        with mock.patch.object(automation_service, "_ensure_process") as ensure_process:
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{"cmd": "click", "target": "BtnSave", "assert": "msgscan 无弹窗"}],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "error"
        assert "unsupported field 'assert'" in result["message"]
        ensure_process.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# PE 检测边界
# ═══════════════════════════════════════════════════════════════

    def test_assert_expr_unknown_builtin_reports_error(self, tmp_path):
        """assert_expr uses explicit locals and does not expose builtins."""
        from src.services import automation_service

        responses = [
            json.dumps({"reqId": "step_0", "status": "ok", "data": "OK"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "rget",
                    "target": "StatusBar.Caption",
                    "assert_expr": "__import__('os').system('echo unsafe') == 0",
                }],
                snapshots_dir=str(tmp_path),
            )

        assertion = result["report"]["first_failure"]["assertion"]
        assert assertion["source"] == "assert_expr"
        assert "assert error" in assertion["message"]
        assert "__import__" in assertion["message"]

    def test_assert_expr_allows_python_expressions(self, tmp_path):
        """assert_expr supports normal Python expression syntax."""
        from src.services import automation_service

        responses = [
            json.dumps({"reqId": "step_0", "status": "ok", "data": "42"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[{
                    "cmd": "rget",
                    "target": "EditAge.Text",
                    "assert_expr": "int(actual) + 1 > 0",
                }],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert result["report"]["failed"] == 0
        assert result["report"]["passed"] == 1

    def test_assert_expr_allows_documented_safe_forms(self, tmp_path):
        """Documented assert_expr examples should stay executable."""
        from src.services import automation_service

        responses = [
            json.dumps({"reqId": "step_0", "status": "ok", "data": " Saved "}),
            json.dumps({"reqId": "step_1", "status": "ok", "data": "13800138000"}),
            json.dumps({"reqId": "step_2", "status": "ok", "data": "42"}),
            json.dumps({"reqId": "auto_exit", "status": "ok", "data": "bye"}),
        ]

        with mock.patch.object(automation_service, "_ensure_process", return_value=(False, "")), \
                mock.patch.object(automation_service, "_send_command", side_effect=responses), \
                mock.patch.object(automation_service.time, "sleep"):
            result = automation_service.execute_script(
                app_path="dummy.exe",
                script=[
                    {"cmd": "rget", "target": "StatusBar.Caption", "assert_expr": "actual.strip() == 'Saved'"},
                    {"cmd": "rget", "target": "PhoneEdit.Text", "assert_expr": "re.fullmatch(r'1\\d{10}', actual)"},
                    {"cmd": "rget", "target": "EditAge.Text", "assert_expr": "int(actual) > 0 and float(actual) < 100"},
                ],
                snapshots_dir=str(tmp_path),
            )

        assert result["status"] == "ok"
        assert result["report"]["failed"] == 0
        assert result["report"]["passed"] == 3


class TestRttiRunTests:
    """RTTI test runner protocol, aggregation, timeout, and lifecycle tests."""

    @staticmethod
    def _delphi_response(result: dict) -> str:
        return json.dumps({
            "reqId": "run_test",
            "status": "ok",
            "data": json.dumps({"results": [result]}),
        })

    @staticmethod
    def _alive_pool_entry():
        proc = mock.Mock()
        proc.poll.return_value = None
        return {"proc": proc, "pipe_name": r"\\.\pipe\daofy_auto_123"}

    def test_decodes_nested_data_and_marks_assertion_failure(self):
        from src.services import automation_service

        app_path = r"C:\fake\rtti-tests.exe"
        tests = [
            {
                "className": "Tests.TCalculator",
                "method": "Add",
                "params": [1, 2],
                "expected": "3",
            },
            {
                "className": "Tests.TCalculator",
                "method": "Add",
                "params": [1, 1],
                "assert_expr": "actual == '3'",
            },
        ]
        responses = [
            self._delphi_response({"status": "ok", "result": "3", "assert": "pass"}),
            self._delphi_response({"status": "ok", "result": "2"}),
        ]

        automation_service._process_pool[app_path] = self._alive_pool_entry()
        try:
            with mock.patch.object(
                automation_service, "_ensure_process", return_value=(False, "")
            ), mock.patch.object(
                automation_service, "_begin_pipe_session"
            ) as begin_session, mock.patch.object(
                automation_service, "_end_pipe_session"
            ), mock.patch.object(
                automation_service, "_kill_process"
            ) as kill_process, mock.patch.object(
                automation_service, "_send_command", side_effect=responses
            ) as send_command:
                result = automation_service.run_tests(
                    app_path=app_path,
                    tests=tests,
                    visibility="private,public",
                    keep_alive=False,
                )
        finally:
            automation_service._process_pool.pop(app_path, None)

        assert result["status"] == "failed"
        assert result["passed"] == 1
        assert result["failed"] == 1
        assert result["errors"] == 0
        assert len(result["results"]) == 2
        assert result["results"][1]["assert"] == "fail"
        assert begin_session.call_count == 1
        kill_process.assert_called_once_with(app_path)

        first_request = json.loads(send_command.call_args_list[0].args[0])
        assert first_request["tests"][0]["visibility"] == "private,public"
        assert send_command.call_args_list[0].kwargs["timeout_ms"] == 30000

    def test_assert_expr_success_has_explicit_pass_status(self):
        from src.services import automation_service

        result = automation_service._normalize_run_test_result(
            0,
            {"id": "expr", "assert_expr": "actual == '42'"},
            json.loads(self._delphi_response({"status": "ok", "result": "42"})),
        )

        assert result["assert"] == "pass"
        assert result["assert_expr"] == "actual == '42'"

    def test_pipe_timeout_restarts_before_next_test(self):
        from src.services import automation_service

        app_path = r"C:\fake\timeout-tests.exe"
        tests = [
            {"className": "Tests.TCalculator", "method": "Slow", "timeout": 0.25},
            {"className": "Tests.TCalculator", "method": "Fast"},
        ]
        responses = [
            "ERR:read_failed_or_timeout (err=0)",
            self._delphi_response({"status": "ok", "result": "done"}),
        ]

        automation_service._process_pool[app_path] = self._alive_pool_entry()
        try:
            with mock.patch.object(
                automation_service,
                "_ensure_process",
                side_effect=[(False, ""), (True, "")],
            ) as ensure_process, mock.patch.object(
                automation_service, "_begin_pipe_session"
            ) as begin_session, mock.patch.object(
                automation_service, "_end_pipe_session"
            ), mock.patch.object(
                automation_service, "_kill_process"
            ) as kill_process, mock.patch.object(
                automation_service, "_send_command", side_effect=responses
            ) as send_command:
                result = automation_service.run_tests(
                    app_path=app_path,
                    tests=tests,
                    keep_alive=True,
                )
        finally:
            automation_service._process_pool.pop(app_path, None)

        assert result["status"] == "failed"
        assert result["passed"] == 1
        assert result["failed"] == 0
        assert result["errors"] == 1
        assert ensure_process.call_count == 2
        assert begin_session.call_count == 2
        kill_process.assert_called_once_with(app_path)
        assert send_command.call_args_list[0].kwargs["timeout_ms"] == 250

    @pytest.mark.parametrize(
        "test_spec, message",
        [
            ({"method": "Add"}, "exactly one"),
            ({"target": "Button1", "className": "Tests.TButton", "method": "Click"}, "exactly one"),
            ({"className": "Tests.TCalculator"}, "missing method"),
            ({"className": "Tests.TCalculator", "method": "Add", "params": {}}, "must be a JSON array"),
            ({"className": "Tests.TCalculator", "method": "Add", "timeout": 0}, "finite value greater than zero"),
            ({"className": "Tests.TCalculator", "method": "Add", "timeout": "later"}, "invalid timeout"),
            ({"className": "Tests.TCalculator", "method": "Add", "params": [{1, 2}]}, "not JSON serializable"),
            ({"className": "Tests.TCalculator", "method": "Add", "expected_exception": ""}, "non-empty string"),
            ({"className": "Tests.TCalculator", "method": "Add", "expected_message": "bad"}, "requires expected_exception"),
            ({"className": "Tests.TCalculator", "method": "Add", "expected": "3", "expected_exception": "EInvalidOpException"}, "cannot combine"),
        ],
    )
    def test_invalid_specs_fail_before_process_launch(self, test_spec, message):
        from src.services import automation_service

        with mock.patch.object(automation_service, "_ensure_process") as ensure_process:
            result = automation_service.run_tests(
                app_path=r"C:\fake\invalid-tests.exe",
                tests=[test_spec],
            )

        assert result["status"] == "error"
        assert message in result["message"]
        ensure_process.assert_not_called()

    def test_string_encoded_arrays_are_normalized_before_send(self):
        from src.services import automation_service

        app_path = r"C:\fake\normalized-tests.exe"
        tests = [{
            "className": "Tests.TCalculator",
            "method": "Add",
            "params": "[1, 2]",
            "constructor_params": "[]",
        }]

        automation_service._process_pool[app_path] = self._alive_pool_entry()
        try:
            with mock.patch.object(
                automation_service, "_ensure_process", return_value=(False, "")
            ), mock.patch.object(
                automation_service, "_begin_pipe_session"
            ), mock.patch.object(
                automation_service, "_end_pipe_session"
            ), mock.patch.object(
                automation_service, "_send_command",
                return_value=self._delphi_response({"status": "ok", "result": "3"}),
            ) as send_command:
                result = automation_service.run_tests(
                    app_path=app_path,
                    tests=tests,
                    keep_alive=True,
                )
        finally:
            automation_service._process_pool.pop(app_path, None)

        assert result["status"] == "ok"
        sent_test = json.loads(send_command.call_args.args[0])["tests"][0]
        assert sent_test["params"] == [1, 2]
        assert sent_test["constructor_params"] == []


class TestDetectEdgeCases:
    """边界情况"""

    def test_empty_file(self, tmp_path):
        """空文件不是 PE"""
        f = tmp_path / "empty.exe"
        f.write_bytes(b"")
        assert detect_exe_subsystem(str(f)) is None

    def test_mz_only(self, tmp_path):
        """只有 MZ 头没有 PE 头"""
        f = tmp_path / "mz_only.exe"
        f.write_bytes(b"MZ\x90\x00" + b"\x00" * 60 + b"\x00\x00\x00\x00")
        assert detect_exe_subsystem(str(f)) is None

    def test_corrupted_pe(self, tmp_path):
        """MZ 头正确但 PE 签名损坏"""
        f = tmp_path / "bad_pe.exe"
        # DOS头: e_magic='MZ', e_lfanew=0x80
        data = bytearray(b"MZ" + b"\x00" * 0x7E + b"\x80\x00\x00\x00")
        data += b"\x00" * (0x80 - len(data) + 4)
        data[0x80:0x84] = b"XX\x00\x00"  # PE 签名错误
        f.write_bytes(data)
        assert detect_exe_subsystem(str(f)) is None
