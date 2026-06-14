"""
技能文件分发脚本

从权威源 .opencode/skills/delphi-rtti-bridge/SKILL.md
自动生成各平台所需格式（Claude Code、Cursor、Windsurf）。

用法:
    python scripts/build-skills.py           # 分发所有平台
    python scripts/build-skills.py --platform claude-code  # 只分发指定平台
    python scripts/build-skills.py --check    # 只检查不写入
"""

import argparse
import os
import shutil
import sys

SKILL_SOURCE = ".opencode/skills/delphi-rtti-bridge"
REFS_SOURCE = os.path.join(SKILL_SOURCE, "references")

PLATFORMS = {
    "claude-code": {
        "dir": ".claude/skills/delphi-rtti-bridge",
        "files": {
            "SKILL.md": "SKILL.md",
        },
    },
    "cursor": {
        "dir": ".cursor/rules",
        "files": {
            "SKILL.md": "delphi-rtti-bridge.mdc",
        },
    },
    "windsurf": {
        "dir": ".",
        "files": {
            "SKILL.md": ".windsurfrules",
        },
    },
}


def distribute_single(platform: str, dry_run: bool = False) -> bool:
    """分发到单个平台。"""
    if platform not in PLATFORMS:
        print(f"  ✗ 未知平台: {platform}")
        return False

    cfg = PLATFORMS[platform]
    target_dir = cfg["dir"]

    if dry_run:
        print(f"  → {platform}: 将写入 {target_dir}/")
        for src_rel, dst_name in cfg["files"].items():
            src_path = os.path.join(SKILL_SOURCE, src_rel)
            dst_path = os.path.join(target_dir, dst_name)
            print(f"    {src_path} → {dst_path}")
        return True

    os.makedirs(target_dir, exist_ok=True)

    for src_rel, dst_name in cfg["files"].items():
        src_path = os.path.join(SKILL_SOURCE, src_rel)
        dst_path = os.path.join(target_dir, dst_name)

        if not os.path.isfile(src_path):
            print(f"  ✗ 源文件不存在: {src_path}")
            continue

        shutil.copy2(src_path, dst_path)
        print(f"  ✓ {platform} → {dst_path}")

    # 也复制 references/ 目录到目标（仅 claude-code）
    if platform == "claude-code":
        refs_target = os.path.join(target_dir, "references")
        if os.path.isdir(REFS_SOURCE):
            os.makedirs(refs_target, exist_ok=True)
            for fname in os.listdir(REFS_SOURCE):
                src = os.path.join(REFS_SOURCE, fname)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(refs_target, fname))
                    print(f"  ✓ {platform} refs → {refs_target}/{fname}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="分发 Delphi RTTI Bridge 技能文件到各平台"
    )
    parser.add_argument(
        "--platform", "-p",
        choices=list(PLATFORMS.keys()) + ["all"],
        default="all",
        help="目标平台（默认 all）",
    )
    parser.add_argument(
        "--check", "-c",
        action="store_true",
        help="仅预览不写入",
    )
    args = parser.parse_args()

    print(f"{'[预览] ' if args.check else ''}分发 delphi-rtti-bridge 技能:")

    platforms = list(PLATFORMS.keys()) if args.platform == "all" else [args.platform]
    success = all(distribute_single(p, dry_run=args.check) for p in platforms)

    if args.check:
        print("\n预览完成，使用 --check 不带参数实际写入")
    else:
        print(f"\n{'全部完成' if success else '部分失败'}")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
