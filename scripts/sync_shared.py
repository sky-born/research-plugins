#!/usr/bin/env python3
"""Copy the canonical shared modules into the install units that use them.

A plugin is installed on its own and project tool copies sit in each project, so one install unit cannot import
from another. A module they all need is kept once under shared/ and copied byte for byte into each unit; the copies
are never edited by hand. Run with --check in CI/release validation; only an explicit run writes outputs.
"""

from __future__ import annotations

import argparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
# canonical file -> its copies, relative to the repository root
COPIES = {
    "shared/textio.py": (
        "plugins/paper-index/skills/paper-search/lib/textio.py",
        "plugins/research-writing/skills/new-manuscript/tools/_textio.py",
    ),
}


def copy_targets() -> list[str]:
    """Every copy path, relative to the repository root — the files other checks treat as generated."""
    return [dst for targets in COPIES.values() for dst in targets]


def synchronize(root: Path, check: bool) -> list[str]:
    """Copies that differ from their canonical file (or are missing). Without check, rewrites them."""
    changes = []
    for src, targets in COPIES.items():
        body = (root / src).read_bytes()
        for dst in targets:
            target = root / dst
            if target.is_file() and target.read_bytes() == body:
                continue
            changes.append(dst)
            if not check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Repository root")
    parser.add_argument("--check", action="store_true", help="Report drift without writing any file")
    args = parser.parse_args()
    try:
        changes = synchronize(args.root.resolve(), check=args.check)
    except OSError as error:
        print(f"ERROR: {error}")
        return 1
    if args.check and changes:
        print("Shared module copies are stale: " + ", ".join(changes))
        print("Run: python -X utf8 scripts/sync_shared.py")
        return 1
    print(f"Shared module copies {'checked' if args.check else 'synchronized'} ({len(changes)} changed files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
