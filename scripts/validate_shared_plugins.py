#!/usr/bin/env python3
"""Read-only validation of the shared Claude/Codex distribution contract.

Uses only the Python standard library. This checks metadata drift and shared
paths, not every product-specific schema or the scientific quality of a skill.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sync_codex_manifests import REPO_ROOT, load_sources, read_json, synchronize


def validate(root: Path) -> tuple[list[str], int]:
    errors: list[str] = []
    skill_count = 0
    try:
        _, sources = load_sources(root)
        stale = synchronize(root, check=True)
    except (OSError, ValueError) as error:
        return [str(error)], 0
    if stale:
        errors.append("Generated metadata is stale: " + ", ".join(stale))
    names: set[str] = set()
    for entry, manifest in sources:
        plugin_root = root / entry["source"]
        skills_root = plugin_root / "skills"
        try:
            codex = read_json(plugin_root / ".codex-plugin" / "plugin.json")
        except (OSError, ValueError) as error:
            errors.append(str(error))
            continue
        if (plugin_root / codex.get("skills", "")).resolve() != skills_root.resolve():
            errors.append(f"{manifest['name']}: both products must use the same skills directory")
        skills = sorted(skills_root.glob("*/SKILL.md"))
        if not skills:
            errors.append(f"{manifest['name']}: no skills found")
        for folder in skills_root.iterdir() if skills_root.is_dir() else []:
            if folder.is_dir() and not folder.name.startswith(".") and not (folder / "SKILL.md").is_file():
                errors.append(f"{manifest['name']}/{folder.name}: missing SKILL.md")
        for skill in skills:
            skill_count += 1
            if not skill.resolve().is_relative_to(plugin_root.resolve()):
                errors.append(f"{skill}: skill resolves outside the plugin")
            skill_name = skill.parent.name
            if skill_name in names:
                errors.append(f"Duplicate skill folder name across plugins: {skill_name}")
            names.add(skill_name)
            contents = skill.read_text(encoding="utf-8")
            if not contents.startswith("---\n") or "\n---" not in contents[4:]:
                errors.append(f"{skill}: missing YAML frontmatter")
    return errors, skill_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    errors, skill_count = validate(args.root.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print("Regenerate metadata with: python -X utf8 scripts/sync_codex_manifests.py")
        return 1
    print(f"Shared distribution validated: generated metadata matches; {skill_count} shared skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
