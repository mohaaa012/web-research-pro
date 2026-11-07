#!/usr/bin/env python3
"""Build dist/web-research-pro.skill — the zip you can upload to claude.ai
(Settings → Capabilities → Skills) or unzip into ~/.claude/skills/.

Usage: python3 tools/package_skill.py [output_dir]
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "web-research-pro"
EXCLUDE_DIRS = {"__pycache__", "evals", ".pytest_cache"}
ALLOWED_KEYS = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}


def check_frontmatter() -> None:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        sys.exit("SKILL.md has no frontmatter")
    keys = {line.split(":", 1)[0].strip() for line in match.group(1).splitlines() if re.match(r"^[a-z-]+:", line)}
    unknown = keys - ALLOWED_KEYS
    if unknown:
        sys.exit(f"frontmatter keys not accepted by claude.ai uploads: {sorted(unknown)}")
    desc = re.search(r"^description: (.*)$", match.group(1), re.M).group(1)
    if len(desc) > 1024 or "<" in desc or ">" in desc:
        sys.exit("description must be at most 1024 characters, without angle brackets")


def main() -> int:
    check_frontmatter()
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "web-research-pro.skill"
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(SKILL.rglob("*")):
            rel = path.relative_to(SKILL.parent)
            if path.is_dir() or any(part in EXCLUDE_DIRS for part in rel.parts) or path.suffix == ".pyc":
                continue
            zf.write(path, rel.as_posix())
            count += 1
    print(f"built {target} ({count} files, {target.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
