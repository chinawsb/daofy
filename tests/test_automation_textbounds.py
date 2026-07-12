#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""textbounds 命令的命令构建与响应反序列化测试。

覆盖 Python 端逻辑：
- 命令构建：step → req 字段（text/mode/include_invisible）
- 响应反序列化：resp_json['data']（JSON 字符串）→ resp_json['state']（dict）
- 错误响应不设置 state
"""

import json

import pytest

from src.services import automation_service as service


class _FakePipe:
    """模拟 _send_command，按 cmd_str 内容返回不同响应。"""

    def __init__(self):
        self.sent = []
        self.responses = {}

    def __call__(self, cmd_str, timeout_ms=None):
        self.sent.append(cmd_str)
        parsed = json.loads(cmd_str)
        cmd = parsed.get('cmd', '')
        key = (cmd, parsed.get('target', ''))
        if key in self.responses:
            return self.responses[key]
        if cmd in self.responses:
            return self.responses[cmd]
        return '{"status":"err","data":"no_mock"}'


def _setup(monkeypatch, fake_pipe):
    """注入模拟依赖。"""
    monkeypatch.setattr(service, '_ensure_process', lambda *a, **kw: (True, None))
    monkeypatch.setattr(service, '_begin_pipe_session', lambda: None)
    monkeypatch.setattr(service, '_send_command', fake_pipe)
    monkeypatch.setattr(service, 'POLL_INTERVAL_AUTOMATION', 0)


def _run_textbounds(monkeypatch, step, resp_data):
    """运行单个 textbounds 步骤，返回 (req_parsed, result)。"""
    fake = _FakePipe()
    fake.responses['snapdir'] = '{"status":"ok","data":"OK"}'
    fake.responses[('textbounds', step.get('target', ''))] = json.dumps(
        {'status': 'ok', 'data': resp_data}, ensure_ascii=False
    )
    _setup(monkeypatch, fake)

    result = service.execute_script(
        'fake_app.exe',
        {'steps': [step]},
        snapshots_dir='.',
        wait_for_pipe=0.1,
    )

    # 找到 textbounds 的 sent 命令（跳过 snapdir init）
    tb_cmd = None
    for sent in fake.sent:
        parsed = json.loads(sent)
        if parsed.get('cmd') == 'textbounds':
            tb_cmd = parsed
            break

    step_result = result.get('results', [{}])[0]
    return tb_cmd, step_result


# ═══════════════════════════════════════════════════════════════
# 命令构建测试
# ═══════════════════════════════════════════════════════════════

class TestTextBoundsCommandBuild:
    """验证 textbounds 步骤的 req 字段构建。"""

    def test_text_field_separate_from_target(self, monkeypatch):
        """text 字段单独提供时，req 应包含 text 字段。"""
        step = {
            'cmd': 'textbounds',
            'target': 'Panel1',
            'text': '保存',
            'mode': 'paint',
        }
        req, _ = _run_textbounds(monkeypatch, step, '{"x":1,"y":2,"width":3,"height":4}')

        assert req is not None
        assert req['target'] == 'Panel1'
        assert req['text'] == '保存'
        assert req['mode'] == 'paint'

    def test_default_mode_is_auto(self, monkeypatch):
        """未指定 mode 时，默认 auto。"""
        step = {'cmd': 'textbounds', 'target': 'ListBox1@打开'}
        req, _ = _run_textbounds(monkeypatch, step, '{"x":1,"y":2,"width":3,"height":4}')

        assert req is not None
        assert req['mode'] == 'auto'

    def test_include_invisible_default_false(self, monkeypatch):
        """未指定 include_invisible 时，默认 'false'。"""
        step = {'cmd': 'textbounds', 'target': 'ListBox1@打开'}
        req, _ = _run_textbounds(monkeypatch, step, '{"x":1,"y":2,"width":3,"height":4}')

        assert req is not None
        assert req['include_invisible'] == 'false'

    def test_include_invisible_true(self, monkeypatch):
        """include_invisible=True 时，req 应为 'true'。"""
        step = {
            'cmd': 'textbounds',
            'target': 'ListBox1@打开',
            'include_invisible': True,
        }
        req, _ = _run_textbounds(monkeypatch, step, '{"x":1,"y":2,"width":3,"height":4}')

        assert req is not None
        assert req['include_invisible'] == 'true'

    def test_no_text_field_when_absent(self, monkeypatch):
        """未提供 text 字段时，req 不含 text 键（target@text 旧式由 Delphi 端解析）。"""
        step = {'cmd': 'textbounds', 'target': 'ListBox1@打开'}
        req, _ = _run_textbounds(monkeypatch, step, '{"x":1,"y":2,"width":3,"height":4}')

        assert req is not None
        assert 'text' not in req


# ═══════════════════════════════════════════════════════════════
# 响应反序列化测试
# ═══════════════════════════════════════════════════════════════

class TestTextBoundsStateDeserialization:
    """验证 textbounds 响应自动反序列化到 state 字段。"""

    def test_simple_json_deserialized_to_state(self, monkeypatch):
        """type-bound 简单 JSON 响应应反序列化到 state。"""
        step = {'cmd': 'textbounds', 'target': 'ListBox1@打开'}
        resp_data = '{"x":10,"y":20,"width":100,"height":16}'
        _, step_result = _run_textbounds(monkeypatch, step, resp_data)

        response = step_result['response']
        assert response['status'] == 'ok'
        assert response['data'] == resp_data
        assert response['state'] == {'x': 10, 'y': 20, 'width': 100, 'height': 16}

    def test_rich_json_with_visibility_deserialized(self, monkeypatch):
        """paint-hook 富 JSON（含 visible_state/clipped）应完整反序列化。"""
        step = {'cmd': 'textbounds', 'target': 'Panel1', 'text': '保存', 'mode': 'paint'}
        rich = (
            '{"x":5,"y":5,"width":80,"height":20,'
            '"visible_state":"full","clipped":false,"api":"ExtTextOutW"}'
        )
        _, step_result = _run_textbounds(monkeypatch, step, rich)

        state = step_result['response']['state']
        assert state['x'] == 5
        assert state['y'] == 5
        assert state['width'] == 80
        assert state['height'] == 20
        assert state['visible_state'] == 'full'
        assert state['clipped'] is False
        assert state['api'] == 'ExtTextOutW'

    def test_rich_json_with_clip_rect_deserialized(self, monkeypatch):
        """paint-hook 富 JSON（含 clip 矩形）应完整反序列化。"""
        step = {'cmd': 'textbounds', 'target': 'Memo1', 'text': '长文本...', 'mode': 'paint'}
        rich = (
            '{"x":0,"y":0,"width":200,"height":16,'
            '"visible_state":"partial","clipped":true,'
            '"clip_x":0,"clip_y":0,"clip_width":100,"clip_height":16,'
            '"visible_x":0,"visible_y":0,"visible_width":100,"visible_height":16,'
            '"api":"DrawTextExW"}'
        )
        _, step_result = _run_textbounds(monkeypatch, step, rich)

        state = step_result['response']['state']
        assert state['visible_state'] == 'partial'
        assert state['clipped'] is True
        assert state['clip_width'] == 100
        assert state['visible_width'] == 100
        assert state['api'] == 'DrawTextExW'

    def test_gdip_api_tag_preserved(self, monkeypatch):
        """GDI+ 来源的记录 api 字段应为 GdipDrawString。"""
        step = {'cmd': 'textbounds', 'target': 'FmxLabel1', 'text': 'Hello', 'mode': 'paint'}
        rich = (
            '{"x":0,"y":0,"width":50,"height":20,'
            '"visible_state":"full","clipped":false,"api":"GdipDrawString"}'
        )
        _, step_result = _run_textbounds(monkeypatch, step, rich)

        assert step_result['response']['state']['api'] == 'GdipDrawString'


# ═══════════════════════════════════════════════════════════════
# 错误响应测试
# ═══════════════════════════════════════════════════════════════

class TestTextBoundsErrorResponse:
    """验证错误响应不设置 state 字段。"""

    def test_txt_not_found_no_state(self, monkeypatch):
        """TXT_NF 错误响应不应反序列化到 state。"""
        fake = _FakePipe()
        fake.responses['snapdir'] = '{"status":"ok","data":"OK"}'
        fake.responses[('textbounds', 'ListBox1@不存在')] = (
            '{"status":"err","data":"TXT_NF"}'
        )
        _setup(monkeypatch, fake)

        result = service.execute_script(
            'fake_app.exe',
            {'steps': [{'cmd': 'textbounds', 'target': 'ListBox1@不存在'}]},
            snapshots_dir='.',
            wait_for_pipe=0.1,
        )

        response = result['results'][0]['response']
        assert response['status'] == 'err'
        assert response['data'] == 'TXT_NF'
        assert 'state' not in response

    def test_paint_not_found_no_state(self, monkeypatch):
        """PAINT_NF 错误响应不应反序列化到 state。"""
        fake = _FakePipe()
        fake.responses['snapdir'] = '{"status":"ok","data":"OK"}'
        fake.responses[('textbounds', 'CustomCtl@文本')] = (
            '{"status":"err","data":"PAINT_NF"}'
        )
        _setup(monkeypatch, fake)

        result = service.execute_script(
            'fake_app.exe',
            {'steps': [
                {'cmd': 'textbounds', 'target': 'CustomCtl@文本', 'mode': 'paint'},
            ]},
            snapshots_dir='.',
            wait_for_pipe=0.1,
        )

        response = result['results'][0]['response']
        assert response['status'] == 'err'
        assert response['data'] == 'PAINT_NF'
        assert 'state' not in response
