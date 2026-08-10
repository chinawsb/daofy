from src.services import automation_service as service


class _FakeOle32:
    def CoInitializeEx(self, *_args):
        return 0

    def CoUninitialize(self):
        return 0


class _FakeWindll:
    ole32 = _FakeOle32()


class _FakeValuePattern:
    def __init__(self):
        self.value = None

    def SetValue(self, value):
        self.value = value


class _FakeControl:
    Name = "File name:"
    ClassName = "Edit"

    def __init__(self):
        self.pattern = _FakeValuePattern()

    def Exists(self):
        return True

    def GetValuePattern(self):
        return self.pattern


class _FakeUIA:
    def __init__(self):
        self.control = _FakeControl()
        self.requested = None

    def Control(self, **kwargs):
        self.requested = kwargs
        return self.control


class _FakePatternIds:
    SelectionItemPattern = 10010


class _FakeSelectionItemPattern:
    def __init__(self):
        self.selected = False

    def Select(self):
        self.selected = True


class _FakeFailingSelectionItemPattern:
    def Select(self):
        raise OSError("UIA provider rejected SelectionItem.Select")


class _FakeTreeItemControl:
    def __init__(self):
        self.pattern = _FakeSelectionItemPattern()
        self.requested_pattern = None
        self.clicked = False

    def Exists(self):
        return True

    def GetPattern(self, pattern_id):
        self.requested_pattern = pattern_id
        return self.pattern

    def Click(self):
        self.clicked = True


class _FakeTreeControl:
    def __init__(self):
        self.item = _FakeTreeItemControl()
        self.requested = None

    def Exists(self):
        return True

    def Control(self, **kwargs):
        self.requested = kwargs
        return self.item


class _FakeSelectionUIA:
    PatternId = _FakePatternIds

    def __init__(self):
        self.control = _FakeTreeControl()
        self.requested = None

    def Control(self, **kwargs):
        self.requested = kwargs
        return self.control


def test_uia_set_uses_value_pattern(monkeypatch):
    fake_uia = _FakeUIA()
    monkeypatch.setattr(service, "_UIA_AVAILABLE", True)
    monkeypatch.setattr(service, "_UIA_MODULE", fake_uia)
    monkeypatch.setattr(service.ctypes, "windll", _FakeWindll(), raising=False)

    resp, step_ok, ok = service._execute_uia_step(
        {"cmd": "uiaset", "target": "File name:", "text": r"C:\data\import.xlsx"},
        {"cmd": "uiaset", "target": "File name:"},
        "step_0",
    )

    assert ok
    assert step_ok
    assert resp["status"] == "ok"
    assert resp["data"] == "set: File name:"
    assert fake_uia.requested == {"Name": "File name:", "searchDepth": 8}
    assert fake_uia.control.pattern.value == r"C:\data\import.xlsx"


def test_uia_select_uses_generic_selection_item_pattern(monkeypatch):
    fake_uia = _FakeSelectionUIA()
    monkeypatch.setattr(service, "_UIA_AVAILABLE", True)
    monkeypatch.setattr(service, "_UIA_MODULE", fake_uia)
    monkeypatch.setattr(service.ctypes, "windll", _FakeWindll(), raising=False)

    resp, step_ok, ok = service._execute_uia_step(
        {"cmd": "uia.select", "target": "SessionTree", "item": "Node 2"},
        {"cmd": "uia.select", "target": "SessionTree"},
        "step_0",
    )

    assert ok
    assert step_ok
    assert resp["status"] == "ok"
    assert resp["data"] == "selected: Node 2 in SessionTree"
    assert fake_uia.requested == {"Name": "SessionTree", "searchDepth": 8}
    assert fake_uia.control.requested == {"Name": "Node 2", "searchDepth": 8}
    assert fake_uia.control.item.requested_pattern == 10010
    assert fake_uia.control.item.pattern.selected
    assert not fake_uia.control.item.clicked


def test_uia_select_falls_back_to_click_when_pattern_fails(monkeypatch):
    fake_uia = _FakeSelectionUIA()
    fake_uia.control.item.pattern = _FakeFailingSelectionItemPattern()
    monkeypatch.setattr(service, "_UIA_AVAILABLE", True)
    monkeypatch.setattr(service, "_UIA_MODULE", fake_uia)
    monkeypatch.setattr(service.ctypes, "windll", _FakeWindll(), raising=False)

    resp, step_ok, ok = service._execute_uia_step(
        {"cmd": "uia.select", "target": "SessionTree", "item": "Node 2"},
        {"cmd": "uia.select", "target": "SessionTree"},
        "step_0",
    )

    assert ok
    assert step_ok
    assert resp["status"] == "ok"
    assert resp["data"] == "clicked to select: Node 2"
    assert fake_uia.control.item.clicked
