import json
from pathlib import Path

from src.services.agent_skill_installer import (
    MANIFEST_NAME,
    install_daofy_agent_skills,
)


ROOT = Path(__file__).resolve().parents[1]
PACKAGED_DAOFY_SKILL = ROOT / "src" / "resources" / "agent-skills" / "daofy" / "SKILL.md"


def _write_source(root: Path, content: str) -> None:
    skill_dir = root / "daofy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def test_packaged_daofy_skill_frontmatter_starts_at_first_byte() -> None:
    data = PACKAGED_DAOFY_SKILL.read_bytes()

    assert not data.startswith(b"\xef\xbb\xbf")
    assert data.startswith((b"---\n", b"---\r\n"))


def test_packaged_daofy_skill_mentions_trae_run_mcp_wrapper() -> None:
    text = PACKAGED_DAOFY_SKILL.read_text(encoding="utf-8")

    required_terms = [
        "run_mcp",
        "server_name",
        "tool_name",
        "args",
        "服务别名",
        "不是 Daofy 固定值",
        "不要把 `server_name/tool_name` 混进",
    ]
    for term in required_terms:
        assert term in text, f"Packaged Daofy skill missing {term!r}"


def test_installs_daofy_skill(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "dest"
    _write_source(
        source_root,
        "---\nname: daofy\n"
        "description: Daofy routing\n---\n"
        "<!-- daofy-managed-skill: true -->\n"
        "Delphi 文件必须使用 delphi_file。\n",
    )

    result = install_daofy_agent_skills(
        source_root=source_root,
        destination_root=destination_root,
    )

    skill_file = destination_root / "daofy" / "SKILL.md"
    manifest = json.loads(
        (destination_root / "daofy" / MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert result.status == "installed"
    assert result.installed_files == ["SKILL.md"]
    assert "delphi_file" in skill_file.read_text(encoding="utf-8")
    assert "SKILL.md" in manifest["files"]


def test_current_skill_is_noop(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "dest"
    _write_source(
        source_root,
        "---\nname: daofy\ndescription: Daofy routing\n---\n"
        "<!-- daofy-managed-skill: true -->\n"
        "当前版本。\n",
    )

    install_daofy_agent_skills(
        source_root=source_root,
        destination_root=destination_root,
    )
    result = install_daofy_agent_skills(
        source_root=source_root,
        destination_root=destination_root,
    )

    assert result.status == "current"
    assert result.changed is False


def test_updates_when_managed_file_is_unchanged(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "dest"
    _write_source(
        source_root,
        "---\nname: daofy\ndescription: Daofy routing\n---\n"
        "<!-- daofy-managed-skill: true -->\n"
        "旧版本。\n",
    )
    install_daofy_agent_skills(
        source_root=source_root,
        destination_root=destination_root,
    )

    (source_root / "daofy" / "SKILL.md").write_text(
        "---\nname: daofy\ndescription: Daofy routing\n---\n"
        "<!-- daofy-managed-skill: true -->\n"
        "新版本，包含 code_hosting。\n",
        encoding="utf-8",
    )
    result = install_daofy_agent_skills(
        source_root=source_root,
        destination_root=destination_root,
    )

    assert result.status == "updated"
    assert result.updated_files == ["SKILL.md"]
    assert "code_hosting" in (
        destination_root / "daofy" / "SKILL.md"
    ).read_text(encoding="utf-8")


def test_skips_user_modified_managed_file(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "dest"
    _write_source(
        source_root,
        "---\nname: daofy\ndescription: Daofy routing\n---\n"
        "<!-- daofy-managed-skill: true -->\n"
        "旧版本。\n",
    )
    install_daofy_agent_skills(
        source_root=source_root,
        destination_root=destination_root,
    )

    installed = destination_root / "daofy" / "SKILL.md"
    installed.write_text("用户手动修改。\n", encoding="utf-8")
    (source_root / "daofy" / "SKILL.md").write_text(
        "---\nname: daofy\ndescription: Daofy routing\n---\n"
        "<!-- daofy-managed-skill: true -->\n"
        "新版本。\n",
        encoding="utf-8",
    )

    result = install_daofy_agent_skills(
        source_root=source_root,
        destination_root=destination_root,
    )

    assert result.status == "partial"
    assert result.skipped_files == ["SKILL.md"]
    assert installed.read_text(encoding="utf-8") == "用户手动修改。\n"


def test_install_can_be_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DAOFY_AGENT_SKILL_INSTALL", "off")
    source_root = tmp_path / "source"
    destination_root = tmp_path / "dest"
    _write_source(source_root, "unused")

    result = install_daofy_agent_skills(
        source_root=source_root,
        destination_root=destination_root,
    )

    assert result.status == "disabled"
    assert not destination_root.exists()
