"""Distribute Codex/Claude/Cursor skill files from authoritative sources."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SKILLS_ROOT = Path(".opencode/skills")
DEFAULT_SKILL = "delphi-rtti-bridge"

RESOURCE_BACKED_SKILLS = {
    "delphi-automation-workflow": {
        "skill": Path("src/resources/automation/workflow.md"),
        "references": {
            "script-generation-workflow.md": Path("src/resources/automation/script-generation-workflow.md"),
            "script-schema.md": Path("src/resources/automation/script-schema.md"),
            "report-schema.md": Path("src/resources/automation/report-schema.md"),
            "repair-loop.md": Path("src/resources/automation/repair-loop.md"),
            "inline-unit.md": Path("src/resources/automation/inline-unit.md"),
        },
    },
}

PLATFORMS = {
    "opencode": {
        "dir": ".opencode/skills/{skill}",
        "skill_file": "SKILL.md",
        "copy_refs": True,
    },
    "claude-code": {
        "dir": ".claude/skills/{skill}",
        "skill_file": "SKILL.md",
        "copy_refs": True,
    },
    "cursor": {
        "dir": ".cursor/rules",
        "skill_file": "{skill}.mdc",
        "copy_refs": False,
    },
    "windsurf": {
        "dir": ".",
        "skill_file": ".windsurfrules",
        "copy_refs": False,
    },
}


def _skill_source_path(skill: str) -> Path:
    """Return the authoritative skill file for a skill."""
    resource_spec = RESOURCE_BACKED_SKILLS.get(skill)
    if resource_spec:
        return resource_spec["skill"]
    return SKILLS_ROOT / skill / "SKILL.md"


def _reference_sources(skill: str) -> dict[str, Path]:
    """Return authoritative reference files for a skill."""
    resource_spec = RESOURCE_BACKED_SKILLS.get(skill)
    if resource_spec:
        return resource_spec["references"]

    refs_dir = SKILLS_ROOT / skill / "references"
    if not refs_dir.is_dir():
        return {}
    return {
        path.name: path
        for path in sorted(refs_dir.iterdir())
        if path.is_file()
    }


def _copy_file(src_path: Path, dst_path: Path, dry_run: bool) -> bool:
    """Copy one file or print the planned copy."""
    if not src_path.is_file():
        print(f"  x missing source: {src_path}")
        return False
    if dry_run:
        print(f"    {src_path} -> {dst_path}")
        return True

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_bytes(src_path.read_bytes())
    print(f"  ok {dst_path}")
    return True


def distribute_single(skill: str, platform: str, dry_run: bool = False) -> bool:
    """Distribute one skill to one platform."""
    if platform not in PLATFORMS:
        print(f"  x unknown platform: {platform}")
        return False

    cfg = PLATFORMS[platform]
    target_dir = Path(cfg["dir"].format(skill=skill))
    skill_source = _skill_source_path(skill)
    target_skill = target_dir / cfg["skill_file"].format(skill=skill)

    if dry_run:
        print(f"  -> {platform}: {target_dir}/")

    success = _copy_file(skill_source, target_skill, dry_run)

    if cfg["copy_refs"]:
        refs_target = target_dir / "references"
        for fname, src_path in _reference_sources(skill).items():
            success = _copy_file(src_path, refs_target / fname, dry_run) and success

    return success


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Distribute skill files to client-specific locations."
    )
    parser.add_argument(
        "--platform",
        "-p",
        choices=list(PLATFORMS.keys()) + ["all"],
        default="all",
        help="Target platform.",
    )
    parser.add_argument(
        "--skill",
        "-s",
        default=DEFAULT_SKILL,
        help=f"Skill name. Default: {DEFAULT_SKILL}.",
    )
    parser.add_argument(
        "--check",
        "-c",
        action="store_true",
        help="Preview copies without writing.",
    )
    args = parser.parse_args()

    prefix = "[check] " if args.check else ""
    print(f"{prefix}distribute {args.skill}:")

    platforms = list(PLATFORMS) if args.platform == "all" else [args.platform]
    success = all(distribute_single(args.skill, platform, args.check) for platform in platforms)

    print("\nall done" if success else "\ncompleted with errors")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
