#!/usr/bin/env python3
"""Helpers shared by scripts/release.py and bootstrap/bootstrap.py.

Standard library only. Nothing here is specific to one marketplace: names come from
.claude-plugin/marketplace.json and the repository address from the git remote.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]

# Where the desktop app keeps its own Claude Code binary when `claude` is not on PATH.
# Each pattern is relative to the named base folder; the newest version found wins.
# Add a line when a new layout is seen - an unknown layout is reported, not guessed.
APP_BUNDLE_GLOBS: tuple[tuple[str, str], ...] = (
    ("home", "Library/Application Support/Claude/claude-code/*/claude.app/Contents/MacOS/claude"),
    ("localappdata", "Claude-Data/*/claude-code/*/*/claude.exe"),
)
# The same for the Codex desktop app's `codex`. Its folders are hashes, so the newest file wins.
CODEX_BUNDLE_GLOBS: tuple[tuple[str, str], ...] = (
    ("localappdata", "OpenAI/Codex/bin/*/codex.exe"),
)


class Stop(Exception):
    """A check failed or a command could not run. The message is printed and the script exits 1."""


def utf8_console() -> None:
    """Keep non-ASCII paths and commit subjects from crashing a legacy Windows console."""
    for stream in (sys.stdout, sys.stderr):
        try:
            # line buffering keeps this script's lines in order with a child's when output is piped
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except (AttributeError, ValueError, OSError):
            pass


def step(title: str) -> None:
    print(f"\n== {title}")


def ok(message: str) -> None:
    print(f"   [ok]   {message}")


def warn(message: str) -> None:
    print(f"   [warn] {message}")


def info(message: str) -> None:
    print(f"          {message}")


def show(command: Sequence[str]) -> str:
    return subprocess.list2cmdline([str(part) for part in command])


def run(command: Sequence[str], *, cwd: Path | None = None, check: bool = True, capture: bool = True,
        env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run a command. A non-zero exit is never treated as "probably fine": with check it raises Stop."""
    try:
        result = subprocess.run([str(part) for part in command], cwd=cwd, env=env, text=True,
                                encoding="utf-8", errors="replace",
                                stdout=subprocess.PIPE if capture else None,
                                stderr=subprocess.STDOUT if capture else None)
    except OSError as error:
        raise Stop(f"could not start: {show(command)}\n{error}") from error
    if check and result.returncode != 0:
        tail = "\n".join((result.stdout or "").strip().splitlines()[-20:])
        raise Stop(f"exit {result.returncode}: {show(command)}" + (f"\n{tail}" if tail else ""))
    return result


def git(root: Path, *args: str, check: bool = True) -> str:
    """Captured stdout of a git command run in `root`, with paths left unquoted."""
    return run(["git", "-c", "core.quotepath=false", *args], cwd=root, check=check).stdout.strip()


def git_ok(root: Path, *args: str) -> bool:
    return run(["git", *args], cwd=root, check=False).returncode == 0


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise Stop(f"{path}: expected a JSON object")
    return value


def marketplace(root: Path) -> tuple[str, list[str]]:
    """Marketplace name and plugin names - the single list every script reads."""
    path = root / ".claude-plugin" / "marketplace.json"
    if not path.is_file():
        raise Stop(f"{path} not found. Run this from a marketplace repository.")
    data = read_json(path)
    name = data.get("name")
    plugins = [entry.get("name") for entry in data.get("plugins") or [] if isinstance(entry, dict)]
    if not isinstance(name, str) or not name or not plugins or not all(isinstance(p, str) and p for p in plugins):
        raise Stop(f"{path}: needs a name and at least one named plugin")
    return name, plugins


def plugin_version(root: Path, plugin: str) -> str:
    version = read_json(root / "plugins" / plugin / ".claude-plugin" / "plugin.json").get("version")
    if not isinstance(version, str) or not version:
        raise Stop(f"plugins/{plugin}/.claude-plugin/plugin.json has no version")
    return version


GITHUB_REMOTE = re.compile(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
                           r"(?P<slug>[^/\s]+/[^/\s]+?)(?:\.git)?/?")


def remote_source(url: str) -> str:
    """What to hand to `marketplace add`: owner/repo for a GitHub remote, else the URL itself."""
    match = GITHUB_REMOTE.fullmatch(url.strip())
    return match.group("slug") if match else url.strip()


def same_remote(first: str, second: str) -> bool:
    """Whether two ways of writing a repository address mean the same place (owner/repo, URL, .git, letter case)."""
    def canonical(value: str) -> str:
        return re.sub(r"(\.git)?/*$", "", remote_source(value)).lower()
    return canonical(first) == canonical(second)


def remote_url(root: Path, remote: str = "origin") -> str:
    url = git(root, "remote", "get-url", remote, check=False)
    if not url:
        raise Stop(f"git remote '{remote}' is not set in {root}; the marketplace address is read from it")
    return url


def _version_key(path: Path) -> tuple[int, ...]:
    for part in reversed(path.parts):
        if re.fullmatch(r"\d+(?:\.\d+)+", part):
            return tuple(int(number) for number in part.split("."))
    return (0,)


def _bundle_candidates(env: Mapping[str, str], globs: Sequence[tuple[str, str]] = APP_BUNDLE_GLOBS) -> list[Path]:
    bases = {"home": Path.home(), "localappdata": Path(env["LOCALAPPDATA"]) if env.get("LOCALAPPDATA") else None}
    found: list[Path] = []
    for base_name, pattern in globs:
        base = bases.get(base_name)
        if base and base.is_dir():
            found.extend(path for path in base.glob(pattern) if path.is_file())
    return sorted(found, key=lambda path: (_version_key(path), path.stat().st_mtime), reverse=True)


def find_claude(explicit: str | None = None, env: Mapping[str, str] | None = None) -> tuple[str, str]:
    """Locate the Claude Code CLI. Returns (path, where it came from).

    Order: --claude, then CLAUDE_CODE_EXECPATH (set inside a Claude Code session), then PATH,
    then the desktop app's bundled binary. Not finding one stops the run - validation is never
    skipped silently.
    """
    env = os.environ if env is None else env
    if explicit:
        if not Path(explicit).is_file():
            raise Stop(f"--claude {explicit}: no such file")
        return explicit, "--claude"
    session = env.get("CLAUDE_CODE_EXECPATH")
    if session and Path(session).is_file():
        return session, "CLAUDE_CODE_EXECPATH"
    on_path = shutil.which("claude")
    if on_path:
        return on_path, "PATH"
    bundles = _bundle_candidates(env)
    if bundles:
        return str(bundles[0]), "desktop app bundle"
    raise Stop("Claude Code CLI not found (looked at --claude, CLAUDE_CODE_EXECPATH, PATH and the desktop "
               "app bundle). Pass --claude <path to the claude executable>.")


def find_codex(explicit: str | None = None, env: Mapping[str, str] | None = None) -> tuple[str, str]:
    """Locate the Codex CLI the same way: --codex, then PATH, then the Codex desktop app's bundled binary."""
    env = os.environ if env is None else env
    if explicit:
        if not Path(explicit).is_file():
            raise Stop(f"--codex {explicit}: no such file")
        return explicit, "--codex"
    on_path = shutil.which("codex")
    if on_path:
        return on_path, "PATH"
    bundles = _bundle_candidates(env, CODEX_BUNDLE_GLOBS)
    if bundles:
        return str(bundles[0]), "desktop app bundle"
    raise Stop("Codex CLI not found (looked at --codex, PATH and the desktop app bundle). "
               "Pass --codex <path to the codex executable>.")


def claude_version(path: str) -> str:
    return run([path, "--version"]).stdout.strip().splitlines()[0]


def json_output(command: Sequence[str], *, cwd: Path | None = None) -> Any:
    """Parse the JSON a CLI prints. Unreadable output stops the run instead of counting as empty."""
    result = subprocess.run([str(part) for part in command], cwd=cwd, text=True, encoding="utf-8",
                            errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise Stop(f"exit {result.returncode}: {show(command)}\n{(result.stderr or result.stdout).strip()[-800:]}")
    try:
        return json.loads(result.stdout)
    except ValueError as error:
        raise Stop(f"{show(command)} did not print JSON: {error}") from error


def lines(values: Iterable[str]) -> str:
    return "\n".join(f"          {value}" for value in values)
