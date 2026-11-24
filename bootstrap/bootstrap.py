#!/usr/bin/env python3
"""Register this marketplace and install or update its plugins on this computer.

    python bootstrap/bootstrap.py install     first time on a computer or account
    python bootstrap/bootstrap.py update      after a new release
    python bootstrap/bootstrap.py status      what is registered and installed here

`install` and `update` are the same idempotent operation: register the marketplace
if it is missing, refresh it, install each listed plugin that is missing and update
each one that is present. Both names exist so the command reads naturally.

The marketplace name and plugin list are read from .claude-plugin/marketplace.json
and the address from this clone's git remote, so adding a plugin needs no edit here.
Only the apps' own plugin commands are run: no settings file or app cache is edited.

Updates are never automatic. Run `update` on each computer after a release, then
reopen the session.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cli_common import (Stop, claude_version, find_claude, find_codex, info, json_output, marketplace, ok,  # noqa: E402
                        plugin_version, remote_source, remote_url, run, same_remote, show, step, utf8_console, warn)


# ------------------------------------------------------------------ plans (pure)

def claude_commands(name: str, plugins: list[str], source: str, registered: bool, installed: set[str]) -> list[list[str]]:
    """The claude sub-commands that bring this computer up to date, given what is already there."""
    commands = [["plugin", "marketplace", "update", name] if registered
                else ["plugin", "marketplace", "add", source, "--scope", "user"]]
    for plugin in plugins:
        plugin_id = f"{plugin}@{name}"
        commands.append(["plugin", "update", plugin_id] if plugin_id in installed
                        else ["plugin", "install", plugin_id, "--scope", "user"])
    return commands


def codex_commands(action: str, name: str, plugins: list[str], source: str, *, local: bool, ref: str) -> list[list[str]]:
    listing = ["plugin", "list", "--marketplace", name, "--json"]
    if action == "status":
        return [listing]
    add = ["plugin", "marketplace", "add", source] + ([] if local else ["--ref", ref])
    commands = [add] + ([] if local else [["plugin", "marketplace", "upgrade", name]])
    commands += [["plugin", "add", f"{plugin}@{name}"] for plugin in plugins]
    return commands + [listing]


# ------------------------------------------------------------------ Claude Code

def claude_state(claude: str, name: str) -> tuple[dict | None, dict[str, dict]]:
    """(marketplace entry or None, installed plugins of this marketplace by id) as the CLI reports them."""
    markets = json_output([claude, "plugin", "marketplace", "list", "--json"])
    plugins = json_output([claude, "plugin", "list", "--json"])
    if not isinstance(markets, list) or not isinstance(plugins, list):
        raise Stop("claude plugin list --json printed an unexpected shape; update this script for the new CLI output")
    registered = next((m for m in markets if isinstance(m, dict) and m.get("name") == name), None)
    installed = {p["id"]: p for p in plugins
                 if isinstance(p, dict) and str(p.get("id", "")).endswith(f"@{name}")}
    return registered, installed


def describe_source(entry: dict) -> str:
    return str(entry.get("repo") or entry.get("url") or entry.get("path") or entry.get("source") or "?")


def check_access(url: str) -> None:
    """Fail early, with the fix, when the remote cannot be read without a login prompt."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    if run(["git", "ls-remote", "--exit-code", url, "HEAD"], check=False, env=env).returncode != 0:
        raise Stop(f"cannot read {url} without a prompt.\n"
                   "          If the repository is private, store credentials once and run this again:\n"
                   f"            git clone {url}        (sign in when asked), or\n"
                   "            gh auth login && gh auth setup-git")
    ok(f"{url} is readable without a prompt")


def report_versions(name: str, plugins: list[str], installed: dict[str, dict]) -> None:
    for plugin in plugins:
        here = plugin_version(ROOT, plugin)
        entry = installed.get(f"{plugin}@{name}")
        if entry is None:
            warn(f"{plugin}: not installed (this clone has {here})")
        elif entry.get("version") == here:
            ok(f"{plugin} {here}" + ("" if entry.get("enabled", True) else " (disabled)"))
        else:
            warn(f"{plugin}: installed {entry.get('version')}, this clone has {here} "
                 "- a release that is not pushed yet, or an update that is still to run")


def claude_app(action: str, args: argparse.Namespace, claude: str) -> None:
    name, plugins = marketplace(ROOT)
    step("Claude Code")
    ok(f"{claude_version(claude)} - {claude}")
    registered, installed = claude_state(claude, name)
    if registered:
        ok(f"marketplace {name} is registered ({describe_source(registered)})")
    else:
        (info if action != "status" else warn)(f"marketplace {name} is not registered")
    if action == "status":
        report_versions(name, plugins, installed)
        return

    url = remote_url(ROOT)
    source = remote_source(url)
    if registered and registered.get("source") != "directory" and not same_remote(describe_source(registered), source):
        # Updating would refresh the other address and install from there. Never do that silently.
        raise Stop(f"marketplace {name} is registered from {describe_source(registered)}, but this clone's remote is {source}.\n"
                   "          If the repository moved, remove the old registration and run this again:\n"
                   f"            {show([claude, 'plugin', 'marketplace', 'remove', name])}")
    commands = [[claude, *command] for command in claude_commands(name, plugins, source, bool(registered), set(installed))]
    if args.dry_run:
        for command in commands:
            info(show(command))
        return
    check_access(url)
    for command in commands:
        info(show(command))
        run(command, capture=False)
    step("Result")
    report_versions(name, plugins, claude_state(claude, name)[1])
    info("Reopen the Claude Code session to load the new version.")


# ------------------------------------------------------------------ Codex

def codex_app(action: str, args: argparse.Namespace, codex: str) -> None:
    name, plugins = marketplace(ROOT)
    step("Codex")
    source = str(ROOT) if args.local else remote_source(remote_url(ROOT))
    commands = [[codex, *command] for command in codex_commands(action, name, plugins, source, local=args.local, ref=args.ref)]
    if args.dry_run:
        for command in commands:
            info(show(command))
        return
    if args.local and action != "status":
        run([sys.executable, "-X", "utf8", "-B", ROOT / "scripts" / "validate_shared_plugins.py"], cwd=ROOT, capture=False)
    for command in commands:
        info(show(command))
        run(command, cwd=ROOT, capture=False)
    if action != "status":
        info("Open a new Codex task to load the new version.")


# ------------------------------------------------------------------ entry

def resolve_apps(args: argparse.Namespace) -> dict[str, str]:
    """Which apps to act on and the executable for each. `auto` takes every app found here."""
    found: dict[str, str] = {}
    missing: dict[str, str] = {}
    if args.app in ("auto", "claude", "all"):
        try:
            found["claude"] = find_claude(args.claude)[0]
        except Stop as error:
            missing["claude"] = str(error)
    if args.app in ("auto", "codex", "all"):
        try:
            found["codex"] = find_codex(args.codex)[0]
        except Stop as error:
            missing["codex"] = str(error)
    if args.app == "auto":
        if not found:
            raise Stop("neither Claude Code nor Codex was found:\n" + "\n".join(f"          {m}" for m in missing.values()))
        for app in missing:
            info(f"{app}: not found on this computer - skipped")
    elif missing:
        raise Stop("\n".join(missing.values()))
    return found


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("install", "update", "status"))
    parser.add_argument("--app", choices=("auto", "claude", "codex", "all"), default="auto",
                        help="auto (default): every app found on this computer; all: both must be present")
    parser.add_argument("--dry-run", action="store_true", help="print the commands without running them")
    parser.add_argument("--claude", help="path to the claude executable (default: CLAUDE_CODE_EXECPATH, PATH, desktop app bundle)")
    parser.add_argument("--codex", help="path to the codex executable (default: PATH, Codex desktop app bundle)")
    parser.add_argument("--local", action="store_true",
                        help="Codex only, for testing before a release: register this working clone instead of the remote")
    parser.add_argument("--ref", default="main", help="Codex only: branch, tag or commit to register (default: main)")
    args = parser.parse_args(argv)
    if (args.local or args.ref != "main") and args.app != "codex":
        parser.error("--local and --ref apply to Codex only; add --app codex")
    try:
        apps = resolve_apps(args)
        if "claude" in apps:
            claude_app(args.action, args, apps["claude"])
        if "codex" in apps:
            codex_app(args.action, args, apps["codex"])
        if args.dry_run:
            step("Done")
            info("dry run - nothing was changed")
        return 0
    except Stop as error:
        print(f"\n   [fail] {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
