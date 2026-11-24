#!/usr/bin/env python3
"""Generate everything that is derived from each plugin's .claude-plugin/plugin.json.

plugin.json is the single source of a plugin's name, version, description and other
display fields. From it this writes
  - the Codex registration metadata (.codex-plugin/plugin.json, .agents/plugins/marketplace.json)
  - the display fields of the plugin's entry in .claude-plugin/marketplace.json, which
    older Claude Code versions read when they list a plugin that is not installed yet.

This does not copy or rewrite skills. Both products load plugins/<name>/skills.
Run with --check in CI/release validation; only an explicit run writes outputs.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
# Copied from plugin.json into the plugin's marketplace entry. A key the manifest lacks is left as the entry has it.
DISPLAY_KEYS = ("description", "author", "homepage", "repository", "license", "keywords")
PLUGIN_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MARKETPLACE_NAME = re.compile(r"[A-Za-z0-9_-]+")
SEMVER = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\."
    r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def json_text(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def required_text(value: dict[str, Any], key: str, label: str) -> str:
    text = value.get(key)
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{label}: {key} must be a non-empty string")
    return text


def load_sources(root: Path) -> tuple[dict[str, Any], list[tuple[dict[str, Any], dict[str, Any]]]]:
    marketplace = read_json(root / ".claude-plugin" / "marketplace.json")
    name = required_text(marketplace, "name", "Claude marketplace")
    if not MARKETPLACE_NAME.fullmatch(name):
        raise ValueError(f"Invalid marketplace name: {name}")
    entries = marketplace.get("plugins")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Claude marketplace must list at least one plugin")
    seen: set[str] = set()
    sources = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Claude marketplace plugin entry must be an object")
        name = required_text(entry, "name", "Claude marketplace plugin")
        if not PLUGIN_NAME.fullmatch(name) or len(name) > 64:
            raise ValueError(f"Invalid plugin folder name: {name}")
        if name in seen:
            raise ValueError(f"Duplicate Claude marketplace plugin: {name}")
        seen.add(name)
        if entry.get("source") != f"./plugins/{name}":
            raise ValueError(f"{name}: shared source must be ./plugins/{name}")
        plugin_root = (root / "plugins" / name).resolve()
        if not plugin_root.is_relative_to(root.resolve()):
            raise ValueError(f"{name}: plugin source resolves outside the repository")
        manifest = read_json(plugin_root / ".claude-plugin" / "plugin.json")
        if manifest.get("name") != name:
            raise ValueError(f"{name}: folder, marketplace and Claude manifest names differ")
        version = required_text(manifest, "version", name)
        if not SEMVER.fullmatch(version):
            raise ValueError(f"{name}: version must use strict semver")
        required_text(manifest, "description", name)
        author = manifest.get("author")
        if not isinstance(author, dict):
            raise ValueError(f"{name}: author must be an object")
        required_text(author, "name", name)
        if "skills" in manifest and manifest["skills"] not in ("./skills", "./skills/"):
            raise ValueError(f"{name}: custom Claude skill roots require an explicit shared-layout review")
        sources.append((entry, manifest))
    disk = {p.name for p in (root / "plugins").iterdir() if p.is_dir() and not p.name.startswith(".")}
    if disk != seen:
        raise ValueError(f"Marketplace/folder mismatch: listed={sorted(seen)}, folders={sorted(disk)}")
    return marketplace, sources


def expected_outputs(root: Path) -> dict[Path, dict[str, Any]]:
    marketplace, sources = load_sources(root)
    codex_marketplace: dict[str, Any] = {
        "name": marketplace["name"],
        "interface": {"displayName": " ".join(word.capitalize() for word in marketplace["name"].split("-"))},
        "plugins": [],
    }
    outputs: dict[Path, dict[str, Any]] = {}
    for entry, manifest in sources:
        name = manifest["name"]
        display_name = entry.get("displayName") or " ".join(word.capitalize() for word in name.split("-"))
        category = (entry.get("category") or "Productivity").title()
        codex_manifest = {
            key: manifest[key]
            for key in ("name", "version", "description", "author", "homepage", "repository", "license", "keywords")
            if key in manifest
        }
        if "repository" not in codex_manifest and "repository" in entry:
            codex_manifest["repository"] = entry["repository"]
        codex_manifest["skills"] = "./skills/"
        codex_manifest["interface"] = {
            "displayName": display_name,
            "shortDescription": manifest["description"].split(". ", 1)[0][:100],
            "longDescription": manifest["description"],
            "developerName": manifest["author"]["name"],
            "category": category,
            "capabilities": [],
            "defaultPrompt": [f"{display_name} 스킬로 현재 프로젝트 작업을 도와주세요."],
        }
        outputs[Path("plugins") / name / ".codex-plugin" / "plugin.json"] = codex_manifest
        codex_marketplace["plugins"].append({
            "name": name,
            "source": {"source": "local", "path": f"./plugins/{name}"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": category,
        })
    outputs[Path(".agents") / "plugins" / "marketplace.json"] = codex_marketplace
    claude_marketplace = dict(marketplace)
    claude_marketplace["plugins"] = [
        {**entry, **{key: manifest[key] for key in DISPLAY_KEYS if key in manifest}}
        for entry, manifest in sources
    ]
    outputs[Path(".claude-plugin") / "marketplace.json"] = claude_marketplace
    return outputs


def synchronize(root: Path, *, check: bool) -> list[str]:
    changes = []
    for relative_path, payload in expected_outputs(root).items():
        target = root / relative_path
        expected = json_text(payload)
        if target.is_file() and target.read_text(encoding="utf-8") == expected:
            continue
        changes.append(relative_path.as_posix())
        if not check:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(expected, encoding="utf-8", newline="\n")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Shared marketplace repository root")
    parser.add_argument("--check", action="store_true", help="Report drift without writing any file")
    args = parser.parse_args()
    try:
        changes = synchronize(args.root.resolve(), check=args.check)
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}")
        return 1
    if args.check and changes:
        print("Generated metadata is stale: " + ", ".join(changes))
        print("Run: python -X utf8 scripts/sync_codex_manifests.py")
        return 1
    print(f"Generated metadata {'checked' if args.check else 'synchronized'} ({len(changes)} changed files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
