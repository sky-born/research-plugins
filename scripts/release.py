#!/usr/bin/env python3
"""Check, version-bump and publish this marketplace.

    python scripts/release.py check
        Every pre-release check. Changes nothing.
    python scripts/release.py bump <plugin> <patch|minor|major|X.Y.Z>
        Raise the plugin's version and regenerate the files derived from it.
    python scripts/release.py publish -m "subject" [-m "body paragraph"]
        check -> commit -> push -> one {name}--v{version} tag per released plugin.

Plugins are served by relative path, so the `version` in a plugin's
.claude-plugin/plugin.json is its release version: other computers see a new
release only when that value changes. `check` stops when a plugin's files
changed since the baseline but its version did not.

Standard library only; runs the same on Windows, macOS and Linux.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cli_common import (REPO_ROOT, Stop, claude_version, find_claude, git, git_ok, info, lines,  # noqa: E402
                        marketplace, ok, plugin_version, read_json, run, show, step, utf8_console, warn)
from sync_codex_manifests import SEMVER, synchronize  # noqa: E402
from validate_shared_plugins import validate  # noqa: E402


SUBJECT_LIMIT = 72
# Fenced blocks whose text is prose (a tree with descriptions, a diagram) may differ between
# README translations. Every other fenced block must match once comments are removed.
TRANSLATED_FENCES = {"", "mermaid"}
FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
HEADING = re.compile(r"^(#{1,6})\s+(.*\S)")
LINK = re.compile(r"\]\(([^)\s]+)\)")
README_VARIANT = re.compile(r"README(\.[A-Za-z0-9_-]+)?\.md")


@dataclass
class Bump:
    name: str
    old: str        # "" when the plugin is new at the baseline
    new: str


# ------------------------------------------------------------------ versions

def core(version: str) -> tuple[int, int, int] | None:
    match = SEMVER.fullmatch(version)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3))) if match else None


def version_increased(old: str, new: str) -> bool:
    before, after = core(old), core(new)
    if before is None or after is None:
        return new != old
    return after > before or (after == before and new != old)


def next_version(current: str, part: str) -> str:
    if core(part):
        if not version_increased(current, part):
            raise Stop(f"{part} is not higher than the current version {current}")
        return part
    numbers = core(current)
    if numbers is None:
        raise Stop(f"current version {current!r} is not semver; pass the new version explicitly")
    major, minor, patch = numbers
    return {"major": f"{major + 1}.0.0", "minor": f"{major}.{minor + 1}.0", "patch": f"{major}.{minor}.{patch + 1}"}[part]


# ------------------------------------------------------------------ README translations

def outline(text: str) -> tuple[list[tuple[int, str]], list[tuple[str, list[str]]], list[str], bool]:
    """Headings, fenced blocks and link targets of a Markdown file, plus whether a fence is left open."""
    headings: list[tuple[int, str]] = []
    fences: list[tuple[str, list[str]]] = []
    links: list[str] = []
    marker, language, body = "", "", []
    for line in text.splitlines():
        fence = FENCE.match(line)
        if marker:
            if fence and fence.group(1).startswith(marker) and not fence.group(2).strip():
                fences.append((language, body))
                marker = ""
            else:
                body.append(line)
            continue
        if fence:
            marker, language, body = fence.group(1), fence.group(2).strip().lower(), []
            continue
        heading = HEADING.match(line)
        if heading:
            headings.append((len(heading.group(1)), heading.group(2)))
        links.extend(LINK.findall(line))
    return headings, fences, links, bool(marker)


def code_lines(body: list[str]) -> list[str]:
    """A fenced block without comments and blank lines, with <placeholders> emptied - what a translation must keep."""
    kept = (re.sub(r"<[^<>\n]*>", "<>", re.sub(r"(^|\s)#.*$", "", line)).strip() for line in body)
    return [line for line in kept if line]


def link_targets(links: list[str]) -> list[str]:
    targets = (link.split("#", 1)[0] for link in links)
    return sorted(target for target in targets if target and not README_VARIANT.fullmatch(target))


def compare_readmes(base_name: str, base: str, other_name: str, other: str) -> list[str]:
    problems: list[str] = []
    b_head, b_fence, b_link, b_open = outline(base)
    o_head, o_fence, o_link, o_open = outline(other)
    for name, is_open in ((base_name, b_open), (other_name, o_open)):
        if is_open:
            problems.append(f"{name}: a code fence is never closed")
    if [level for level, _ in b_head] != [level for level, _ in o_head]:
        at = next((i for i, (x, y) in enumerate(zip(b_head, o_head)) if x[0] != y[0]), min(len(b_head), len(o_head)))
        here = b_head[at][1] if at < len(b_head) else "(end)"
        there = o_head[at][1] if at < len(o_head) else "(end)"
        problems.append(f"{other_name}: heading structure differs from {base_name} at heading {at + 1} "
                        f"({len(o_head)} vs {len(b_head)} headings): {there!r} vs {here!r}")
    if [language for language, _ in b_fence] != [language for language, _ in o_fence]:
        problems.append(f"{other_name}: code blocks differ from {base_name} in number or language "
                        f"({len(o_fence)} vs {len(b_fence)})")
    else:
        for number, ((language, b_body), (_, o_body)) in enumerate(zip(b_fence, o_fence), 1):
            if language not in TRANSLATED_FENCES and code_lines(b_body) != code_lines(o_body):
                problems.append(f"{other_name}: code block {number} ({language}) differs from {base_name}")
    if link_targets(b_link) != link_targets(o_link):
        only_base = sorted(set(link_targets(b_link)) - set(link_targets(o_link)))
        only_other = sorted(set(link_targets(o_link)) - set(link_targets(b_link)))
        problems.append(f"{other_name}: link targets differ from {base_name}"
                        + (f"; only in {base_name}: {only_base}" if only_base else "")
                        + (f"; only in {other_name}: {only_other}" if only_other else ""))
    return problems


def readme_parity(root: Path) -> tuple[list[str], int]:
    """Compare every README.<lang>.md with the README.md beside it. Returns (problems, pairs checked)."""
    problems: list[str] = []
    pairs = 0
    folders = [root] + sorted(path for path in (root / "plugins").glob("*") if path.is_dir())
    for folder in folders:
        base = folder / "README.md"
        for other in sorted(folder.glob("README.*.md")):
            if not base.is_file():
                problems.append(f"{other.relative_to(root).as_posix()}: no README.md beside it")
                continue
            pairs += 1
            problems += compare_readmes(base.relative_to(root).as_posix(), base.read_text(encoding="utf-8"),
                                        other.relative_to(root).as_posix(), other.read_text(encoding="utf-8"))
    return problems, pairs


# ------------------------------------------------------------------ changes since the baseline

def changed_paths(root: Path, baseline: str) -> list[str]:
    tracked = git(root, "diff", "--name-only", baseline, "--", ".").splitlines()
    untracked = git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted({path for path in tracked + untracked if path})


def plugin_changes(root: Path, baseline: str, plugins: list[str], changed: list[str]) -> tuple[list[Bump], list[tuple[str, str, list[str]]]]:
    bumped: list[Bump] = []
    stale: list[tuple[str, str, list[str]]] = []
    for name in plugins:
        touched = [path for path in changed if path.startswith(f"plugins/{name}/")]
        if not touched:
            continue
        manifest = f"plugins/{name}/.claude-plugin/plugin.json"
        new = plugin_version(root, name)
        at_baseline = run(["git", "show", f"{baseline}:{manifest}"], cwd=root, check=False)
        old = ""
        if at_baseline.returncode == 0:
            match = re.search(r'"version"\s*:\s*"([^"]+)"', at_baseline.stdout)
            old = match.group(1) if match else ""
        if not old or version_increased(old, new):
            bumped.append(Bump(name, old, new))
        else:
            stale.append((name, old, touched))
    return bumped, stale


def changelog_problems(root: Path, bumped: list[Bump]) -> list[str]:
    """Each released version needs an entry with at least one bullet under its plugin's heading."""
    path = root / "CHANGELOG.md"
    if not path.is_file():
        return []
    sections: dict[str, str] = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"^##\s+(.*\S)", line)
        if heading and not line.startswith("###"):
            current = heading.group(1).strip("`")
            sections[current] = ""
        elif current is not None:
            sections[current] += line + "\n"
    problems = []
    for bump in bumped:
        entry = re.search(rf"^###\s+{re.escape(bump.new)}(?![0-9A-Za-z.+-]).*\n(?P<body>(?:(?!###\s).*\n?)*)",
                          sections.get(bump.name, ""), flags=re.MULTILINE)
        if not entry or not re.search(r"^\s*[-*]\s+\S", entry.group("body"), flags=re.MULTILINE):
            problems.append(f"CHANGELOG.md: add '### {bump.new}' with at least one bullet under '## {bump.name}'")
    return problems


# ------------------------------------------------------------------ check

def check(args: argparse.Namespace) -> tuple[list[Bump], list[str]]:
    root: Path = args.root.resolve()
    baseline: str = args.baseline

    step("Repository")
    top = git(root, "rev-parse", "--show-toplevel", check=False)
    if not top or Path(top).resolve() != root:
        raise Stop(f"{root} is not the top folder of a git repository")
    _, plugins = marketplace(root)
    ok(str(root))
    if args.no_fetch:
        info("git fetch skipped (--no-fetch)")
    else:
        remote = baseline.split("/", 1)[0]
        if run(["git", "fetch", remote, "--quiet"], cwd=root, check=False).returncode != 0:
            raise Stop(f"git fetch {remote} failed. Check the network and the stored credentials.")
    if not git_ok(root, "rev-parse", "--verify", "--quiet", baseline):
        raise Stop(f"baseline {baseline} not found")
    ok(f"baseline {baseline} = {git(root, 'rev-parse', '--short', baseline)}")
    paths = git(root, "ls-files", "-c", "-o", "--exclude-standard").splitlines()
    non_ascii = [p for p in paths if not p.isascii()]
    if non_ascii:
        raise Stop("file and folder names must be ASCII (the repository is public):\n" + lines(non_ascii))
    ok(f"{len(paths)} file names are ASCII")

    step("Public content")
    public = root / "scripts" / "check_public.py"
    if public.is_file():
        result = run([sys.executable, "-X", "utf8", "-B", public, "--baseline", baseline], cwd=root, check=False)
        report = result.stdout.strip().splitlines()
        if result.returncode != 0:
            raise Stop("personal information would be published:\n" + lines(report))
        (warn if report[0].startswith("no deny list") else ok)(report[0])

    step("Shared distribution")
    errors, skills = validate(root)
    if errors:
        raise Stop("shared distribution is inconsistent:\n" + lines(errors)
                   + "\n          regenerate with: python scripts/sync_codex_manifests.py")
    ok(f"marketplace, plugin manifests and generated metadata agree ({skills} skills)")
    hashes = root / "scripts" / "tool_hashes.py"
    if hashes.is_file():
        result = run([sys.executable, "-X", "utf8", "-B", hashes, "--check"], cwd=root, check=False)
        if result.returncode != 0:
            raise Stop("tool hash list is stale:\n" + lines(result.stdout.strip().splitlines())
                       + "\n          regenerate with: python scripts/tool_hashes.py")
        ok("tool hash list is current")
    problems, pairs = readme_parity(root)
    if problems:
        raise Stop("README translations differ:\n" + lines(problems))
    if pairs:
        ok(f"README translations match in headings, code blocks and link targets ({pairs} pair(s))")

    step("Claude manifests")
    if args.skip_claude:
        warn("claude plugin validate was NOT run (--skip-claude)")
    else:
        claude, source = find_claude(args.claude)
        ok(f"{claude_version(claude)} - {claude} (from {source})")
        for target in [root] + [root / "plugins" / name for name in plugins]:
            result = run([claude, "plugin", "validate", target], cwd=root, check=False)
            if result.returncode != 0:
                raise Stop(f"claude plugin validate failed for {target}:\n{result.stdout.strip()}")
            ok(target.relative_to(root).as_posix() if target != root else "marketplace.json")

    step(f"Changes since {baseline}")
    changed = changed_paths(root, baseline)
    if not changed:
        ok("no file differs from the baseline")
    for path in changed:
        info(path)
    bumped, stale = plugin_changes(root, baseline, plugins, changed)
    for bump in bumped:
        ok(f"{bump.name}  {bump.old or '(new)'} -> {bump.new}")
    if stale:
        report = []
        for name, version, touched in stale:
            report.append(f"{name}: files changed but version is still {version}")
            report += [f"    {path}" for path in touched]
        raise Stop("version not raised:\n" + lines(report)
                   + "\n          raise it with: python scripts/release.py bump <plugin> <patch|minor|major>")
    if changed and not bumped:
        ok("no plugin changed - nothing to version")
    for bump in bumped:          # before anything is committed: a version that already has a tag was released
        conflict = tag_conflict(root, bump)
        if conflict:
            raise Stop(conflict)
    problems = changelog_problems(root, bumped)
    if problems:
        raise Stop("changelog entry missing:\n" + lines(problems))

    step("Tests")
    if args.skip_tests:
        warn("unit tests were NOT run (--skip-tests)")
    elif not (root / "tests").is_dir():
        info("no tests folder")
    else:
        result = run([sys.executable, "-X", "utf8", "-B", "-m", "unittest", "discover", "-s", "tests"],
                     cwd=root, check=False, capture=False)
        if result.returncode != 0:
            raise Stop("unit tests failed")
        ok("unit tests passed")
    return bumped, changed


# ------------------------------------------------------------------ commands

def cmd_check(args: argparse.Namespace) -> int:
    check(args)
    step("Done")
    info("check only - nothing was changed")
    return 0


def cmd_bump(args: argparse.Namespace) -> int:
    root: Path = args.root.resolve()
    _, plugins = marketplace(root)
    if args.plugin not in plugins:
        raise Stop(f"unknown plugin {args.plugin!r}; marketplace lists: {', '.join(plugins)}")
    manifest = root / "plugins" / args.plugin / ".claude-plugin" / "plugin.json"
    current = plugin_version(root, args.plugin)
    new = next_version(current, args.part)
    text = manifest.read_text(encoding="utf-8")
    text, count = re.subn(r'("version"\s*:\s*")' + re.escape(current) + '(")', rf"\g<1>{new}\g<2>", text, count=1)
    if count != 1:
        raise Stop(f"{manifest}: could not find the version line to rewrite")
    manifest.write_text(text, encoding="utf-8", newline="\n")
    if read_json(manifest).get("version") != new:
        raise Stop(f"{manifest}: version did not become {new}")
    step("Version")
    ok(f"{args.plugin}  {current} -> {new}")
    for path in synchronize(root, check=False):
        ok(f"regenerated {path}")
    hashes = root / "scripts" / "tool_hashes.py"
    if hashes.is_file():
        run([sys.executable, "-X", "utf8", "-B", hashes], cwd=root)
        ok("regenerated the tool hash list")
    if (root / "CHANGELOG.md").is_file():
        info(f"next: add '### {new}' with what changed under '## {args.plugin}' in CHANGELOG.md")
    return 0


def release_commit(root: Path, plugin: str) -> str:
    """The commit a version tag belongs on: the last one that changed the plugin's folder."""
    commit = git(root, "log", "-1", "--format=%H", "--", f"plugins/{plugin}")
    if not commit:
        raise Stop(f"no commit touches plugins/{plugin}")
    return commit


def tagged_commit(root: Path, tag: str) -> str:
    return git(root, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}", check=False)


def tag_conflict(root: Path, bump: Bump) -> str:
    """Why this version cannot be released, if its tag already sits on other content."""
    tag = f"{bump.name}--v{bump.new}"
    existing = tagged_commit(root, tag)
    if not existing:
        return ""
    if git(root, "status", "--porcelain", "--", f"plugins/{bump.name}"):
        return f"tag {tag} already exists on {existing[:7]} but plugins/{bump.name} has uncommitted changes - raise the version"
    commit = release_commit(root, bump.name)
    if existing != commit:
        return f"tag {tag} already exists on {existing[:7]}, not on {commit[:7]} - raise the version"
    return ""


def tag_release(root: Path, bump: Bump, *, push: bool, remote: str) -> None:
    tag = f"{bump.name}--v{bump.new}"
    commit = release_commit(root, bump.name)
    existing = tagged_commit(root, tag)
    if existing and existing != commit:
        raise Stop(f"tag {tag} already exists on {existing[:7]}, not on {commit[:7]} - raise the version")
    if existing:
        ok(f"{tag} already exists on {commit[:7]}")
    else:
        run(["git", "tag", "-a", tag, "-m", f"{bump.name} {bump.new}", commit], cwd=root)
        ok(f"{tag} -> {commit[:7]}")
    if push:
        run(["git", "push", remote, f"refs/tags/{tag}"], cwd=root)
        ok(f"{tag} pushed to {remote}")


def cmd_publish(args: argparse.Namespace) -> int:
    root: Path = args.root.resolve()
    remote = args.baseline.split("/", 1)[0]
    bumped, changed = check(args)
    if not changed:
        step("Done")
        info("nothing to release")
        return 0

    messages = list(args.message or [])
    if not messages:
        messages = [", ".join(f"{bump.name} v{bump.new}" for bump in bumped) or "Update docs and scripts"]
    if len(messages[0]) > SUBJECT_LIMIT:
        warn(f"commit subject is {len(messages[0])} characters; keep it within {SUBJECT_LIMIT} "
             "and put the detail in the body or CHANGELOG.md")

    step("Commit")
    if not git(root, "status", "--porcelain"):
        ok("working tree is clean - nothing to commit")
    else:
        run(["git", "add", "-A"], cwd=root)
        commit = ["git", "commit"]
        for message in messages:
            commit += ["-m", message]
        run(commit, cwd=root)
        ok(messages[0])

    step("Push")
    if args.no_push:
        info(f"skipped (--no-push): {show(['git', 'push', remote, 'HEAD'])}")
    else:
        run(["git", "push", remote, "HEAD"], cwd=root)
        ok(f"pushed to {remote}")

    if bumped:
        step("Tags")
        if args.no_tag:
            info("skipped (--no-tag)")
        else:
            for bump in bumped:
                tag_release(root, bump, push=not args.no_push, remote=remote)

    step("Done")
    info("Updates are manual. On each computer that should get this release:")
    info("  python bootstrap/bootstrap.py update")
    info("then reopen the session.")
    return 0


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root (default: this clone)")
        p.add_argument("--baseline", default="origin/main", help="ref to compare against (default: origin/main)")
        p.add_argument("--claude", help="path to the claude executable (default: CLAUDE_CODE_EXECPATH, then PATH)")
        p.add_argument("--skip-claude", action="store_true", help="do not run claude plugin validate (for CI runners without the CLI)")
        p.add_argument("--skip-tests", action="store_true", help="do not run the unit tests")
        p.add_argument("--no-fetch", action="store_true", help="do not fetch the baseline's remote first")

    p = sub.add_parser("check", help="run every pre-release check; change nothing")
    common(p)
    p.set_defaults(run=cmd_check)

    p = sub.add_parser("bump", help="raise a plugin's version and regenerate derived files")
    p.add_argument("plugin")
    p.add_argument("part", help="patch, minor, major, or an explicit X.Y.Z")
    p.add_argument("--root", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    p.set_defaults(run=cmd_bump)

    p = sub.add_parser("publish", help="check, commit, push and tag")
    common(p)
    p.add_argument("-m", "--message", action="append",
                   help=f"commit subject (up to {SUBJECT_LIMIT} characters); repeat for body paragraphs")
    p.add_argument("--no-push", action="store_true", help="commit and tag locally only")
    p.add_argument("--no-tag", action="store_true", help="do not create tags")
    p.set_defaults(run=cmd_publish)

    args = parser.parse_args(argv)
    if getattr(args, "part", None) and not (args.part in ("patch", "minor", "major") or core(args.part)):
        parser.error("part must be patch, minor, major or an explicit X.Y.Z")
    try:
        return args.run(args)
    except Stop as error:
        print(f"\n   [fail] {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
