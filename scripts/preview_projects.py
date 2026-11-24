#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""자매 프로젝트의 추적 파일 **사본**에 정본 도구를 돌려, 배포 전에 무엇이 바뀌는지 봅니다. 원본에는 쓰지 않습니다.

    python -X utf8 scripts/preview_projects.py <프로젝트> [<프로젝트> ...]
        [--set tracker.record_index_exclude='["archive/"]' ...]   사본의 project.json 에 넣을 값(JSON)
        [--with-manuscript]                                     원고 폴더도 복사해 check_numbers까지 돌림
        [--focus chN]                                           그 장의 포커스 진단 개수
        [--keep]                                                임시 폴더를 남김 (경로를 출력)
        [--diff]                                                바뀐 생성 파일의 unified diff 를 출력
        [--grammar]                                             grammar_baseline 시나리오도 원고 사본에 돌림(tests/grammar_scenarios.py)

하는 일 — 임시 폴더에 추적 파일 · 완료기록 · 설정 · 훅 · 도구를 복사하고, `managed_files.json` 대로 정본 파일을
덮은 뒤 `index_records.py` 와 `tidy_tracker.py --apply`(두 번 — 두 번째는 바뀌지 않아야 함)를 돌리고
원본과 견줍니다. 바뀐 파일 · 줄끝 · 크기 · 색인 §1 과 목록 §3 의 행 수를 보고합니다.

--grammar — 설정(`--set` 반영 뒤)이 가리키는 문법 점검 범위(장 파일 · `grammar.sources` · `grammar.avoid_lists`)만 따로 임시 폴더에
복사합니다. 루트 밖 경로(`../avoid_phrases/…`)는 사본 루트에서 같은 상대 위치에 둡니다. 정본 `grammar_baseline.py` 로 범위를 보이고(status)
시나리오를 차례로 돌린 뒤, 원본 파일의 바이트가 그대로인지 확인합니다.
"""
from __future__ import annotations

import argparse
import difflib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / 'plugins' / 'research-writing' / 'skills' / 'new-manuscript'
PY = [sys.executable, '-X', 'utf8', '-B']
sys.path.insert(0, str(SKILL / 'tools'))
import _config  # noqa: E402


def load_cfg(project: Path) -> dict:
    """설정 파일 그대로에, 설정에 적지 않은 옛 기본 이름(0.12 이하)을 더한 것 — 사본은 이 값으로 돕니다."""
    for rel in ('.manuscript/project.json', '.writing/project.json'):
        p = project / rel
        if p.is_file():
            raw = json.loads(p.read_text(encoding='utf-8'))
            pins = _config.legacy_pins(str(project), raw)
            if pins:
                print(f'옛 기본 이름을 설정에 적지 않은 프로젝트입니다 — 사본의 설정에 적고 돌립니다: {", ".join(pins)}')
            return _config._merge(raw, pins)
    raise SystemExit(f'설정 파일이 없습니다: {project}')


def load_raw(project: Path) -> dict:
    for rel in ('.manuscript/project.json', '.writing/project.json'):
        if (project / rel).is_file():
            return json.loads((project / rel).read_text(encoding='utf-8'))
    return {}


def names(cfg: dict) -> dict:
    """기본값과 합친 설정 — 이름을 읽을 때."""
    return _config._merge(_config.DEFAULTS, cfg)


def copy_tree(src: Path, dst: Path):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__'), dirs_exist_ok=True)


def block_rows(text: str, start: str, end: str) -> int:
    """마커(또는 제목) 사이의 표 행 수 — 헤더 두 줄은 빼고 셉니다."""
    try:
        a = text.index(start); b = text.index(end, a)
    except ValueError:
        return -1
    rows = [l for l in text[a:b].split('\n') if l.startswith('|')]
    return max(len(rows) - 2, 0)


def set_key(cfg: dict, dotted: str, value):
    keys = dotted.split('.')
    d = cfg
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def run(cmd, cwd: Path):
    # 동기화 안전장치의 컴퓨터별 상태는 실제 홈이 아니라 미리보기용 임시 폴더에 — 사본의 ID · 지문이 실제 프로젝트 상태를 더럽히지 않게
    env = dict(os.environ)
    env.setdefault('SYNC_STATE_HOME', str(Path(tempfile.gettempdir()) / 'preview-sync-state'))
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def preview_grammar(project: Path, sets: list[tuple[str, object]], keep: bool) -> int:
    sys.path.insert(0, str(REPO_ROOT / 'tests'))
    import grammar_scenarios as S                    # 합성 표본 시험과 같은 시나리오

    raw = load_cfg(project)
    for k, v in sets:
        set_key(raw, k, v)
    m = raw.get('manuscript', {})
    src = names(raw)['manuscript']['source_dir']
    refs = m.get('references', 'references.md')
    files = [src.strip('/') + '/' + c['file'] for c in m.get('chapters', []) if c['file'] != refs]
    g = raw.get('grammar') or {}
    files += [s_['file'] for s_ in g.get('sources', [])] + list(g.get('avoid_lists', []))
    rels = []
    for f in files:
        f = f.replace('\\', '/')
        if f not in rels:
            rels.append(f)
    depth = max([len([x for x in r.split('/') if x == '..']) for r in rels] + [0])

    tmp = Path(tempfile.mkdtemp(prefix='preview-grammar-' + project.name + '-'))
    root = tmp.joinpath(*(['_'] * depth), project.name)   # 루트 밖 경로(`../`)도 임시 폴더 안에 놓이게
    state, work, outside = tmp / 'state', tmp / 'work', tmp / 'outside'
    rc = 0
    try:
        before, missing = {}, []
        for r in rels:
            real = S.find_real(project, r)
            if real is None or not real.is_file():
                missing.append(r)
                continue
            dst = Path(os.path.normpath(root / r))
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(real, dst)
            before[real] = real.read_bytes()
        (root / src).mkdir(parents=True, exist_ok=True)
        (root / '.manuscript').mkdir(parents=True, exist_ok=True)
        (root / '.manuscript' / 'project.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

        print('=' * 78)
        print(f'grammar_baseline 미리보기  {project}')
        print(f'임시 폴더 {tmp}')
        if missing:
            print('  ! 원본에 없는 범위 파일: ' + ' · '.join(missing))
        q = S.Proj(root, state)
        q.install()
        st = q.run('status', codes=None)
        print('--- status (기준 없음 — 종료 %d)' % st.returncode)
        print('\n'.join('    ' + l for l in st.stdout.rstrip().split('\n')))
        for name, fn, needs_work in S.SCENARIOS:
            try:
                _p, msg = S.run_scenario(fn, needs_work, root, state, work)
                print(f'  ok   {name:16s} {msg}')
            except AssertionError as e:
                rc = 1
                print(f'  FAIL {name:16s} {str(e)[:600]}')
        try:
            _q, msg = S.s_readonly(root, state, outside)
            print(f'  ok   {"readonly":16s} {msg}')
        except AssertionError as e:
            rc = 1
            print(f'  FAIL {"readonly":16s} {str(e)[:600]}')
        changed = [str(k) for k, b in before.items() if k.read_bytes() != b]
        if changed:
            rc = 1
            print('  FAIL 원본 바이트가 바뀌었습니다: ' + ' · '.join(changed))
        else:
            print(f'--- 원본 {len(before)}개 파일 바이트 그대로')
        return rc
    finally:
        if keep:
            print(f'임시 폴더를 남겼습니다: {tmp}')
        else:
            shutil.rmtree(tmp, ignore_errors=True)


def preview(project: Path, sets: list[tuple[str, object]], with_manuscript: bool, focus: str | None,
            keep: bool, show_diff: bool) -> int:
    cfg = load_cfg(project)
    eff = names(cfg)
    t = eff['tracker']
    tracker_files = [t[k] for k in ('index', 'pending', 'record_index', 'literature', 'proposals')]
    records_dir, tools_dir = t['records_dir'], eff['tools_dir']
    manifest = json.loads((SKILL / 'managed_files.json').read_text(encoding='utf-8'))

    tmp = Path(tempfile.mkdtemp(prefix='preview-' + project.name + '-'))
    try:
        for f in tracker_files:
            if (project / f).is_file():
                (tmp / f).parent.mkdir(parents=True, exist_ok=True)     # 추적 파일이 하위 폴더(`추적/`)에 있어도
                shutil.copy2(project / f, tmp / f)
        for d in (records_dir, '.manuscript', '.writing', '.claude', tools_dir):
            if (project / d).is_dir():
                copy_tree(project / d, tmp / d)
        src_dir = cfg.get('manuscript', {}).get('source_dir')
        if with_manuscript and src_dir and (project / src_dir).is_dir():
            copy_tree(project / src_dir, tmp / src_dir)
        # 정본으로 덮기
        for item in manifest['files']:
            s = SKILL / item['src']; d = tmp / item['dst'].replace('{tools_dir}', tools_dir)
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(s, d)
            if item.get('old'):
                (d.parent / item['old']).unlink(missing_ok=True)          # update_tools --apply 가 하듯 옛 이름 사본은 지움
        # 설정 값 넣기 (사본에만) — --set 과, 설정에 적지 않은 옛 이름
        if sets or cfg != load_raw(project):
            cfg_path = tmp / '.manuscript' / 'project.json'
            if not cfg_path.is_file():
                cfg_path = tmp / '.writing' / 'project.json'
            raw = cfg
            for k, v in sets:
                set_key(raw, k, v)
            cfg_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

        print('=' * 78)
        print(f'미리보기  {project}')
        print(f'임시 폴더 {tmp}')
        logs = []
        rc, out = run(PY + [str(tmp / tools_dir / 'index_records.py')], tmp); logs.append(('index_records.py', rc, out))
        rc, out = run(PY + [str(tmp / tools_dir / 'tidy_tracker.py'), '--apply'], tmp); logs.append(('tidy_tracker.py --apply', rc, out))
        snap = {f: (tmp / f).read_bytes() for f in tracker_files if (tmp / f).is_file()}
        rc, out = run(PY + [str(tmp / tools_dir / 'tidy_tracker.py'), '--apply'], tmp); logs.append(('tidy_tracker.py --apply (2회)', rc, out))
        idem = all((tmp / f).read_bytes() == b for f, b in snap.items())
        if with_manuscript:
            rc, out = run(PY + [str(tmp / tools_dir / 'check_numbers.py')], tmp); logs.append(('check_numbers.py', rc, out))
        if focus:
            rc, out = run(PY + [str(tmp / tools_dir / 'tidy_tracker.py'), '--focus', focus], tmp); logs.append((f'--focus {focus} (진단)', rc, out))
        for name, rc, out in logs:
            print(f'--- {name}  (종료 {rc})')
            print('\n'.join('    ' + l for l in out.rstrip().split('\n')[-12:]))
        print(f'--- 두 번 돌려도 같음: {"예" if idem else "아니오 — 멱등이 아닙니다"}')

        print('--- 원본과의 차이')
        for f in tracker_files:
            a, b = project / f, tmp / f
            if not a.is_file() or not b.is_file():
                continue
            ab, bb = a.read_bytes(), b.read_bytes()
            eol = lambda x: 'CRLF' if b'\r\n' in x else 'LF'
            if ab == bb:
                print(f'    {f:24s} 같음'); continue
            at, bt = ab.decode('utf-8', 'replace'), bb.decode('utf-8', 'replace')
            note = []
            if eol(ab) != eol(bb):
                note.append(f'줄끝 {eol(ab)} → {eol(bb)}')
            note.append(f'{len(at):,} → {len(bt):,} 자')
            r1 = block_rows(at, '## 1.', '## 2.'); r2 = block_rows(bt, '## 1.', '## 2.')
            if r1 >= 0 and f == t.get('record_index'):
                note.append(f'§1 {r1} → {r2} 행')
            r1 = block_rows(at, '<!-- 위치표 -->', '<!-- /위치표 -->'); r2 = block_rows(bt, '<!-- 위치표 -->', '<!-- /위치표 -->')
            if r1 >= 0:
                note.append(f'§3 {r1} → {r2} 행')
            print(f'    {f:24s} 바뀜 — ' + ' · '.join(note))
            if show_diff:
                for l in difflib.unified_diff(at.replace('\r\n', '\n').split('\n'), bt.replace('\r\n', '\n').split('\n'),
                                              f'원본/{f}', f'사본/{f}', lineterm='', n=1):
                    print('        ' + l)
        return 0
    finally:
        if keep:
            print(f'임시 폴더를 남겼습니다: {tmp}')
        else:
            shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('projects', nargs='+')
    ap.add_argument('--set', action='append', default=[], metavar='KEY=JSON')
    ap.add_argument('--with-manuscript', action='store_true')
    ap.add_argument('--focus')
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('--diff', action='store_true')
    ap.add_argument('--grammar', action='store_true')
    a = ap.parse_args()
    sets = []
    for s in a.set:
        k, _, v = s.partition('=')
        sets.append((k.strip(), json.loads(v)))
    rc = 0
    for p in a.projects:
        rc |= preview(Path(p).resolve(), sets, a.with_manuscript, a.focus, a.keep, a.diff)
        if a.grammar:
            rc |= preview_grammar(Path(p).resolve(), sets, a.keep)
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
