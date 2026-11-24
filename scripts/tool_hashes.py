#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정본 관리 파일의 이력 해시 목록(tool_hashes.json)을 git 이력과 작업 트리에서 만듭니다.

    python -X utf8 scripts/tool_hashes.py            new-manuscript/tool_hashes.json 을 다시 씁니다
    python -X utf8 scripts/tool_hashes.py --check    파일이 최신인지만 봅니다 (시험 · 배포 전 검증)

관리 대상은 `skills/new-manuscript/managed_files.json`(손으로 유지하는 원본)이고, 이 파일은 거기서 생성됩니다.
해시는 줄끝을 LF 로 정규화한 sha256 이며 `update_tools.py` 가 같은 정의로 프로젝트 사본을 판정합니다.
항목마다 그 내용이 현재였던 판(그 커밋의 plugin.json version)을 모두 적습니다 — 저장소의 모든 커밋을 오래된 것부터
걸으며 파일 내용(이름 변경을 따라감)과 판을 함께 봅니다. 설치본은 git 저장소가 아니므로 이 파일을 플러그인 폴더 안에 커밋합니다.

이 저장소의 이력에 나오지 않는 판의 항목은 이미 적힌 것을 그대로 이어받습니다 — 이력 없이 새로 시작한 저장소나 얕은 복제에서도
옛 판의 해시가 사라지지 않고, `--check` 도 통과합니다. 이력에 나오는 판은 지금처럼 이력에서만 만듭니다.
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
    # core.quotepath=false — 한글 경로를 따옴표 · 팔진수로 바꾸지 않게 (name-only 출력을 그대로 경로로 씁니다)
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
    covered = set(ver_of.values()) | {cur_ver}      # 이 저장소의 이력이 아는 판 — 이 판들의 항목은 이력에서만 만듭니다
    try:
        recorded = json.loads(OUT.read_text(encoding='utf-8')).get('files', {}) if OUT.is_file() else {}
    except ValueError:
        recorded = {}
    files: dict[str, dict[str, list[str]]] = {}
    for item in manifest['files']:
        rel = (SKILL / item['src']).relative_to(REPO_ROOT).as_posix()
        rels = [rel] + ([rel.rsplit('/', 1)[0] + '/' + item['old']] if item.get('old') else [])
        # 그 파일을 건드린 커밋과 그때의 경로(이름 변경을 따라감 · 옛 이름의 이력도 — 이름 변경을 커밋하기 전에도 같은 결과)
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
        for c in commits:                       # 오래된 것부터 — 건드리지 않은 커밋에서는 내용이 그대로입니다
            if c in touch:
                try:
                    h = norm_hash(git('show', f'{c}:{touch[c]}'))
                except subprocess.CalledProcessError:
                    h = None                    # 그 커밋에서 지워짐
            if h and ver_of[c] != '?':
                table.setdefault(h, set()).add(ver_of[c])
        p = SKILL / item['src']                 # 작업 트리 — 아직 커밋되지 않은 현재 내용
        if p.is_file():
            table.setdefault(norm_hash(p.read_bytes()), set()).add(cur_ver)
        keys = [item['src']] + ([item['src'].rsplit('/', 1)[0] + '/' + item['old']] if item.get('old') else [])
        for old_hash, versions in (kv for k in keys for kv in recorded.get(k, {}).items()):   # 이력 밖의 판은 적힌 것을 이어받음(옛 이름 포함)
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
            print(f'없음: {OUT}'); return 1
        if OUT.read_text(encoding='utf-8') != text:
            print(f'낡음: {OUT.relative_to(REPO_ROOT)} — python -X utf8 scripts/tool_hashes.py 로 다시 만드십시오'); return 1
        print('tool_hashes.json 최신'); return 0
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    n = sum(len(v) for v in data['files'].values())
    print(f'{OUT.relative_to(REPO_ROOT)} — 파일 {len(data["files"])}개, 해시 {n}개')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
