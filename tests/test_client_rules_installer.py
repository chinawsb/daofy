"""Tests for client-rules auto install (Daofy -> MCP client rules dir)."""

import types

from src.services.client_rules_installer import (
    detect_client,
    install_client_rules,
)


def _params(name: str) -> object:
    return types.SimpleNamespace(
        clientInfo=types.SimpleNamespace(name=name, version="1.0")
    )


def test_detect_client_normalizes_lowercase() -> None:
    assert detect_client(_params("CodeBuddy")) == "codebuddy"
    assert detect_client(_params("Cursor")) == "cursor"
    assert detect_client(None) is None
    assert detect_client(_params("")) is None


def test_installs_to_codebuddy_rules(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    out = install_client_rules(_params("CodeBuddy"))
    assert out["status"] == "installed"
    dest = tmp_path / ".codebuddy" / "rules" / "daofy-delphi.md"
    assert dest.is_file()
    assert "groupproj" in dest.read_text(encoding="utf-8")


def test_installs_cursor_with_frontmatter(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    out = install_client_rules(_params("Cursor"))
    assert out["status"] == "installed"
    dest = tmp_path / ".cursor" / "rules" / "daofy-delphi.md"
    text = dest.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "globs:" in text
    assert "*.groupproj" in text


def test_installs_trae_with_frontmatter(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    out = install_client_rules(_params("Trae"))
    assert out["status"] == "installed"
    dest = tmp_path / ".trae" / "rules" / "daofy-delphi.md"
    text = dest.read_text(encoding="utf-8")
    assert text.startswith("---")
    # Trae 需要 alwaysApply: true 才能始终生效
    assert "alwaysApply: true" in text
    assert "*.groupproj" in text


def test_installs_lingma_plain_markdown(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    out = install_client_rules(_params("Tongyi Lingma"))
    assert out["status"] == "installed"
    dest = tmp_path / ".lingma" / "rules" / "daofy-delphi.md"
    text = dest.read_text(encoding="utf-8")
    # 通义灵码规则类型在 IDE 界面配置，文件不需要 frontmatter
    assert not text.startswith("---")
    assert "groupproj" in text


def test_installs_codearts_as_agents_md(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    out = install_client_rules(_params("Huawei CodeArts"))
    assert out["status"] == "installed"
    # 华为码道明确兼容 AGENTS.md，个人级放在 %USERPROFILE%/.codeartsdoer/
    dest = tmp_path / ".codeartsdoer" / "AGENTS.md"
    assert dest.is_file()
    text = dest.read_text(encoding="utf-8")
    assert not text.startswith("---")  # 纯 markdown，无 frontmatter
    assert "daofy-managed-rule: true" in text  # 含托管标记
    assert "groupproj" in text


def test_idempotent_on_second_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    first = install_client_rules(_params("CodeBuddy"))
    assert first["status"] == "installed"
    second = install_client_rules(_params("CodeBuddy"))
    assert second["status"] == "current"


def test_user_edited_file_is_skipped(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    install_client_rules(_params("CodeBuddy"))
    dest = tmp_path / ".codebuddy" / "rules" / "daofy-delphi.md"
    # 模拟用户改动（manifest 未记录此 hash，且非 daofy-managed 标记）
    dest.write_text("# user custom rules\n", encoding="utf-8")
    out = install_client_rules(_params("CodeBuddy"))
    assert out["status"] == "skipped"
    assert dest.read_text(encoding="utf-8") == "# user custom rules\n"


def test_unknown_client_is_skipped(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    out = install_client_rules(_params("SomeRandomIDE"))
    assert out["status"] == "no_match"


def test_disabled_via_env(monkeypatch) -> None:
    monkeypatch.setenv("DAOFY_CLIENT_RULES_INSTALL", "0")
    out = install_client_rules(_params("CodeBuddy"))
    assert out["status"] == "disabled"
