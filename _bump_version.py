"""Bump pyproject.toml version from 2026.07.18 to 2026.07.18.1"""
from pathlib import Path

p = Path(__file__).parent / "pyproject.toml"
text = p.read_text(encoding="utf-8")
old = 'version = "2026.07.18"'
new = 'version = "2026.07.18.1"'
assert old in text, f"Could not find '{old}' in pyproject.toml"
text = text.replace(old, new)
p.write_text(text, encoding="utf-8")
print(f"OK: {old} -> {new}")
