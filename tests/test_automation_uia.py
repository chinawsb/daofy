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
