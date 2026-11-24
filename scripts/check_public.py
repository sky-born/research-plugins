#!/usr/bin/env python3
"""Look for personal information in what this repository would publish.

    python scripts/check_public.py [--deny-list FILE] [--baseline origin/main]

Scans every file that `git add -A` would include (tracked and untracked, not ignored),
their paths, the author and committer of commits not yet on the baseline, and the
identity the next commit will use. Generic patterns live here. Personal terms (names,
project names, identifiers of the owner's own papers) are read from a deny list kept
outside the repository: --deny-list FILE, the RESEARCH_PLUGINS_DENYLIST environment
variable, or `git config research-plugins.denylist FILE` in this clone (kept per computer,
never committed). One term per line, `#` starts a comment, matching ignores case.

Found values are never printed - only the kind, a masked sample and where.
Exit 0 clean, 1 something found, 2 usage error. Without a deny list only the generic
patterns run, and the report says so.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DENY_ENV = "RESEARCH_PLUGINS_DENYLIST"
DENY_GIT = "research-plugins.denylist"

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
ALLOWED_EMAIL = re.compile(r"(?i)(.*@users\.noreply\.github\.com|noreply@github\.com|noreply@anthropic\.com|git@github\.com"
                           r"|.*@example\.(com|org|net)|.*@[a-z0-9.-]+\.(example|invalid|test|localhost))$")
PATTERNS = {
    "user folder": re.compile(r"(?i)\b[a-z]:[\\/]+users[\\/]+(?![<%$])([^\\/\s\"'`<>|*]+)"),
    "home folder": re.compile(r"(?<![\w.])(?:/[A-Za-z])?/(?:Users|home)/(?![<$])([^/\s\"'`<>|*]+)"),   # 앞의 한 글자 폴더는 Git Bash 의 드라이브 표기
    "secret": re.compile(r"\b(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}"
                         r"|xox[baprs]-[A-Za-z0-9-]{10,})\b"),
    "secret assignment": re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*[\"']([A-Za-z0-9_\-]{16,})[\"']"),
}
GENERIC_FOLDERS = {"public", "default", "all users", "runner", "example", "name", "username", "you", "me"}


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=REPO_ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def mask(value: str) -> str:
    return f"{value[:1]}…({len(value)})"


def load_deny(path: str | None) -> tuple[list[str], str]:
    path = path or os.environ.get(DENY_ENV) or git("config", DENY_GIT, check=False).strip()
    if not path:
        return [], f"no deny list (--deny-list, {DENY_ENV} or git config {DENY_GIT}) - personal terms were NOT checked"
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"deny list not found: {p}")
    terms = [t.split("#", 1)[0].strip() for t in p.read_text(encoding="utf-8").splitlines()]
    terms = [t for t in terms if t]
    if not terms:
        raise SystemExit(f"deny list is empty: {p}")
    return terms, f"deny list: {len(terms)} term(s)"


def findings(text: str, deny: list[str]) -> list[tuple[str, str]]:
    out = []
    for m in EMAIL.finditer(text):
        if not ALLOWED_EMAIL.fullmatch(m.group(0)):
            out.append(("email", m.group(0)))
    for kind, rx in PATTERNS.items():
        for m in rx.finditer(text):
            value = m.group(1) if rx.groups else m.group(0)
            if kind.endswith("folder") and value.lower() in GENERIC_FOLDERS:
                continue
            out.append((kind, value))
    low = text.lower()
    for term in deny:
        n = low.count(term.lower())
        out += [("deny list", term)] * n
    return out


def candidate_files() -> list[str]:
    files = git("ls-files", "-c", "-o", "--exclude-standard").splitlines()
    return sorted({f for f in files if f and (REPO_ROOT / f).is_file()})


def scan(deny: list[str], baseline: str) -> dict[str, Counter]:
    hits: dict[str, Counter] = defaultdict(Counter)
    samples: dict[str, Counter] = defaultdict(Counter)

    def note(where: str, found: list[tuple[str, str]]):
        for kind, value in found:
            hits[kind][where] += 1
            samples[kind][mask(value)] += 1

    for name in candidate_files():
        note(f"path {name}", findings(name, deny))
        try:
            text = (REPO_ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        note(name, findings(text, deny))
    if git("rev-parse", "--verify", "--quiet", baseline, check=False).strip():
        for line in git("log", "--format=%h%x00%an%x00%ae%x00%cn%x00%ce", f"{baseline}..HEAD").splitlines():
            sha, *who = line.split("\x00")
            note(f"commit {sha}", findings(" ".join(who), deny))
    identity = " ".join(git("config", key, check=False).strip() for key in ("user.name", "user.email"))
    note("next commit identity (git config)", findings(identity, deny))
    return hits, samples


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--deny-list", help=f"file of personal terms, outside the repository (default: ${DENY_ENV})")
    ap.add_argument("--baseline", default="origin/main", help="commits after this ref are checked (default: origin/main)")
    a = ap.parse_args(argv)
    deny, deny_note = load_deny(a.deny_list)
    hits, samples = scan(deny, a.baseline)
    print(deny_note)
    if not hits:
        print("nothing personal found")
        return 0
    for kind, where in hits.items():
        print(f"{kind}: {sum(where.values())} in {len(where)} place(s) - samples {', '.join(v for v, _ in samples[kind].most_common(5))}")
        for place, n in where.most_common(10):
            print(f"    {place} ({n})")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
