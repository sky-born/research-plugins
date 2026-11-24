#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Builds the hash list of managed files (tool_hashes.json) from git history and the working tree.

    python -X utf8 scripts/tool_hashes.py            rewrites new-manuscript/tool_hashes.json
    python -X utf8 scripts/tool_hashes.py --check    only checks that the file is current (tests · pre-release check)

The managed files are listed in `skills/new-manuscript/managed_files.json` (the hand-kept source); this file is generated from it.
A hash is the sha256 of the content with line endings normalised to LF; `update_tools.py` judges project copies by the same definition.
Each entry lists every version in which that content was current (the plugin.json version of that commit) — walking all commits
oldest first, following the content (and renames) together with the version. Installs are not git repositories, so this file is
committed inside the plugin folder.

Entries for versions that do not appear in this repository's history are carried over as written — so their hashes survive in a
repository with a fresh history or a shallow clone, and `--check` passes. Versions that appear in the history are built from it only.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN = REPO_ROOT / 'plugins' / 'research-writing'
SKILL = PLUGIN / 'skills' / 'new-manuscript'
MANIFEST = SKILL / 'managed_files.json'
OUT = SKILL / 'tool_hashes.json'
PLUGIN_JSON = 'plugins/research-writing/.claude-plugin/plugin.json'


def norm_hash(data: bytes) -> str:
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def git(*args: str) -> bytes:
    # core.quotepath=false — keeps non-ASCII paths free of quotes and octal escapes (name-only output is used as paths)
    return subprocess.run(['git', '-c', 'core.quotepath=false', *args], cwd=REPO_ROOT, check=True,
                          capture_output=True).stdout


def _verkey(v: str):
    try:
        return tuple(int(x) for x in v.split('.'))
    except ValueError:
        return (0,)


def build() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    cur_ver = json.loads((REPO_ROOT / PLUGIN_JSON).read_text(encoding='utf-8')).get('version', '?')
    commits = git('log', '--reverse', '--format=%H').decode().split()
    ver_of: dict[str, str] = {}
    for c in commits:
        try:
            ver_of[c] = json.loads(git('show', f'{c}:{PLUGIN_JSON}').decode('utf-8')).get('version', '?')
        except (subprocess.CalledProcessError, ValueError):
            ver_of[c] = '?'
    covered = set(ver_of.values()) | {cur_ver}      # versions this repository's history knows — their entries come from the history only
    try:
        recorded = json.loads(OUT.read_text(encoding='utf-8')).get('files', {}) if OUT.is_file() else {}
    except ValueError:
        recorded = {}
    files: dict[str, dict[str, list[str]]] = {}
    for item in manifest['files']:
        rel = (SKILL / item['src']).relative_to(REPO_ROOT).as_posix()
        rels = [rel] + ([rel.rsplit('/', 1)[0] + '/' + item['old']] if item.get('old') else [])
        # commits that touched the file and its path at the time (follows renames, old names included — same result before a rename is committed)
        touch: dict[str, str] = {}
        for r in rels:
            cur = None
            for line in git('log', '--follow', '--name-only', '--format=%H', '--', r).decode().split('\n'):
                line = line.strip()
                if re.fullmatch(r'[0-9a-f]{40}', line):
                    cur = line
                elif line and cur:
                    touch.setdefault(cur, line)
        table: dict[str, set[str]] = {}
        h = None
        for c in commits:                       # oldest first — content is unchanged in commits that did not touch it
            if c in touch:
                try:
                    h = norm_hash(git('show', f'{c}:{touch[c]}'))
                except subprocess.CalledProcessError:
                    h = None                    # deleted in that commit
            if h and ver_of[c] != '?':
                table.setdefault(h, set()).add(ver_of[c])
        p = SKILL / item['src']                 # working tree — current content, not yet committed
        if p.is_file():
            table.setdefault(norm_hash(p.read_bytes()), set()).add(cur_ver)
        keys = [item['src']] + ([item['src'].rsplit('/', 1)[0] + '/' + item['old']] if item.get('old') else [])
        for old_hash, versions in (kv for k in keys for kv in recorded.get(k, {}).items()):   # versions outside the history carry over what is written (old names included)
            outside = [v for v in versions if v not in covered]
            if outside:
                table.setdefault(old_hash, set()).update(outside)
        files[item['src']] = {k: sorted(v, key=_verkey) for k, v in sorted(table.items())}
    return {'_설명': '정본 관리 파일의 내용 해시(줄끝 LF 정규화 sha256) → 그 내용이 현재였던 판. scripts/tool_hashes.py 가 '
                     'managed_files.json 과 git 이력에서 생성합니다. 손으로 고치지 마십시오.',
            'files': files}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    data = build()
    text = json.dumps(data, ensure_ascii=False, indent=1) + '\n'
    if a.check:
        if not OUT.is_file():
            print(f'missing: {OUT}'); return 1
        if OUT.read_text(encoding='utf-8') != text:
            print(f'stale: {OUT.relative_to(REPO_ROOT)} — rebuild with python -X utf8 scripts/tool_hashes.py'); return 1
        print('tool_hashes.json is current'); return 0
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    n = sum(len(v) for v in data['files'].values())
    print(f'{OUT.relative_to(REPO_ROOT)} — {len(data["files"])} files, {n} hashes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
