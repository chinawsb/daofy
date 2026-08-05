"""Release packaging — replicates the documented AGENTS.md release process.

Usage: python scripts/release-pack.py <version>   e.g. python scripts/release-pack.py v2026.08.05

Steps:
1. Collect files from git index (git ls-files, no path quoting), excluding:
   .arts/, .coverage, config/history.json, src/config/compilers.json,
   .gitignore, tools/daudit/
2. Copy them into releases/daofy-for-delphi-<ver>/
3. Create .tar / .7z (from the tar) / .zip archives under releases/
4. Remove the staging directory
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SEVEN_ZIP = ROOT / "tools" / "7z" / "7z.exe"
EXCLUDES = (
    r"^\.arts/",
    r"^\.coverage$",
    r"^config/history\.json$",
    r"^src/config/compilers\.json$",
    r"^\.gitignore$",
    r"^tools/daudit/",
)


def git_ls_files() -> list[str]:
    """List tracked files with raw (unquoted) paths for non-ASCII names."""
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    ver = sys.argv[1]
    if not ver.startswith("v"):
        ver = "v" + ver

    release_dir = ROOT / "releases"
    stage = release_dir / f"daofy-for-delphi-{ver}"
    tar_path = release_dir / f"daofy-for-delphi-{ver}.tar"
    seven_path = release_dir / f"daofy-for-delphi-{ver}.7z"
    zip_path = release_dir / f"daofy-for-delphi-{ver}.zip"

    if not SEVEN_ZIP.exists():
        print(f"ERROR: 7z not found at {SEVEN_ZIP}")
        return 1

    # 1. collect
    files = git_ls_files()
    kept = [f for f in files if not any(re.match(pat, f) for pat in EXCLUDES)]
    print(f"tracked files: {len(files)}, after exclusions: {len(kept)}")

    # 2. copy
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    copied = 0
    for rel in kept:
        src = ROOT / rel
        if not src.is_file():
            print(f"  WARN: missing in working tree: {rel}")
            continue
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    print(f"copied: {copied}")

    # 3. archive: tar, 7z(from tar), zip(from stage)
    def run_7z(*args: str) -> None:
        print("  7z", " ".join(args))
        subprocess.run([str(SEVEN_ZIP), *args], cwd=ROOT, check=True)

    # 归档 stage 内容（非外层目录）: 与 AGENTS.md 文档流程一致，文件位于归档根目录
    run_7z("a", "-ttar", str(tar_path), str(stage) + "\\*")
    run_7z("a", "-t7z", str(seven_path), str(tar_path), "-mx=9", "-m0=LZMA2")
    run_7z("a", "-tzip", str(zip_path), str(stage) + "\\*", "-mx=9")

    # 4. cleanup
    shutil.rmtree(stage)
    for p in (tar_path, seven_path, zip_path):
        print(f"  {p.name}: {p.stat().st_size / 1024 / 1024:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
