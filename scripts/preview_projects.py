#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the canonical tools on a **copy** of a sibling project's tracker files to see what a release would change. Never writes to the original.

    python -X utf8 scripts/preview_projects.py <project> [<project> ...]
        [--set tracker.record_index_exclude='["archive/"]' ...]   value (JSON) to put in the copy's project.json
        [--with-manuscript]                                     also copy the manuscript folder and run check_numbers
        [--focus chN]                                           focus diagnostics count for that chapter
        [--keep]                                                keep the temporary folder (prints its path)
        [--diff]                                                print a unified diff of changed generated files
        [--grammar]                                             also run the grammar_baseline scenarios on a manuscript copy (tests/grammar_scenarios.py)
        [--state-from <sync-state folder>]                      after the run, check the copy as another computer would — with a copy of that state

What it does — copies tracker files · records · settings · hooks · tools to a temporary folder, overwrites them with the
canonical files listed in `managed_files.json`, runs `update_tools.py --apply` on the copy (the command a user runs — it migrates the
tracker anchors and rebuilds; a following `migrate_format.py` preview must find nothing), runs `index_records.py` and `tidy_tracker.py --apply` (twice — the second
run must change nothing) and compares with the original. Reports the format before and after · the migration plan · changed files ·
line endings · sizes · row counts of index §1 and list §3. With `--state-from`, a copy of a computer's sync state for the project
(`~/.claude/sync-state/<id>`) is placed under the copy's project id and `check_sync.py` runs with it — what that computer's session
start would report after Drive delivers the migrated files.

--grammar — copies only the grammar-check scope the settings name (after `--set`: chapter files · `grammar.sources` ·
`grammar.avoid_lists`) to a temporary folder of its own. Paths outside the root (`../avoid_phrases/…`) keep the same relative place
from the copy's root. Shows the scope with the canonical `grammar_baseline.py` (status), runs the scenarios in turn, then checks
that the original files' bytes are unchanged.
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
    """The settings file as it is, plus old default names (0.12 or earlier) it does not write — the copy runs with these values."""
    for rel in ('.manuscript/project.json', '.writing/project.json'):
        p = project / rel
        if p.is_file():
            raw = json.loads(p.read_text(encoding='utf-8'))
            pins = _config.legacy_pins(str(project), raw)
            if pins:
                print(f'The settings do not write the old default names — adding them to the copy\'s settings: {", ".join(pins)}')
            return _config._merge(raw, pins)
    raise SystemExit(f'No settings file: {project}')


def load_raw(project: Path) -> dict:
    for rel in ('.manuscript/project.json', '.writing/project.json'):
        if (project / rel).is_file():
            return json.loads((project / rel).read_text(encoding='utf-8'))
    return {}


def names(cfg: dict) -> dict:
    """Settings merged with the defaults — for reading names."""
    return _config._merge(_config.DEFAULTS, cfg)


def copy_tree(src: Path, dst: Path):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__'), dirs_exist_ok=True)


def block_rows(text: str, start: str, end: str) -> int:
    """Table rows between the markers (or headings) — the two header lines are not counted."""
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
    # per-computer state of the sync guard goes to the preview's temporary folder, not the real home — the copy's ID and fingerprint never touch the real project's state
    env = dict(os.environ)
    env.setdefault('SYNC_STATE_HOME', str(Path(tempfile.gettempdir()) / 'preview-sync-state'))
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def preview_grammar(project: Path, sets: list[tuple[str, object]], keep: bool) -> int:
    sys.path.insert(0, str(REPO_ROOT / 'tests'))
    import grammar_scenarios as S                    # the same scenarios as the synthetic-sample tests

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
    root = tmp.joinpath(*(['_'] * depth), project.name)   # so paths outside the root (`../`) also land inside the temporary folder
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
        print(f'grammar_baseline preview  {project}')
        print(f'temporary folder {tmp}')
        if missing:
            print('  ! scope files missing from the original: ' + ' · '.join(missing))
        q = S.Proj(root, state)
        q.install()
        st = q.run('status', codes=None)
        print('--- status (no baseline — exit %d)' % st.returncode)
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
            print('  FAIL original bytes changed: ' + ' · '.join(changed))
        else:
            print(f'--- original {len(before)} files byte-identical')
        return rc
    finally:
        if keep:
            print(f'kept the temporary folder: {tmp}')
        else:
            shutil.rmtree(tmp, ignore_errors=True)


def location_rows(text: str) -> int:
    """Rows of the list's location table — the markers in either spelling (`_config.BLOCKS`)."""
    for name in _config.BLOCKS['locations']:
        n = block_rows(text, f'<!-- {name} -->', f'<!-- /{name} -->')
        if n >= 0:
            return n
    return -1


def project_format(root: Path) -> str:
    """'en' · 'ko' · 'mixed' · 'none' with the files behind it — `_config.project_format` on the given folder."""
    try:
        cfg = _config.Config(str(root), names(load_cfg(root)))
        state, per = _config.project_format(cfg)
    except (SystemExit, OSError, ValueError) as e:
        return f'? ({e})'
    return state + ('' if not per else ' — ' + '; '.join(f'{r}: {"+".join(v)}' for r, v in sorted(per.items())))


def other_computer_view(tmp: Path, tools_dir: str, state_from: Path) -> str:
    """check_sync on the copy with a copy of another computer's sync state for the project."""
    sys.path.insert(0, str(SKILL / 'tools'))
    import _sync
    raw = names(load_cfg(tmp))
    base = Path(tempfile.mkdtemp(prefix='preview-other-state-'))
    pid = _sync.project_id(raw.get('project') or tmp.name, str(tmp))
    shutil.copytree(state_from, base / pid, ignore=shutil.ignore_patterns('write.lock*', '*.tmp*'))
    env = dict(os.environ, SYNC_STATE_HOME=str(base))
    go = lambda *extra: subprocess.run(PY + [str(tmp / tools_dir / 'check_sync.py')] + list(extra), cwd=tmp, capture_output=True,   # noqa: E731
                                       text=True, encoding='utf-8', errors='replace', env=env)
    start = go()                                       # what that computer's session start reports
    damage = go('--damage')                            # every lost line — only files present in the copy (the rest were never copied)
    shutil.rmtree(base, ignore_errors=True)
    keep, on = [], False
    for line in (damage.stdout or '').splitlines():
        m = re.match(r'^\s*! (.+?) — of \d+ lines', line)
        if m:
            on = (tmp / m.group(1)).is_file()
        elif not line.startswith('        '):
            on = False
        if on:
            keep.append(line)
    return (f'session start (exit {start.returncode}):\n' + (start.stdout or '') + (start.stderr or '')
            + '\nlost lines in copied files (--damage):\n' + ('\n'.join(keep) or '    none'))


def preview(project: Path, sets: list[tuple[str, object]], with_manuscript: bool, focus: str | None,
            keep: bool, show_diff: bool, state_from: str | None = None) -> int:
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
                (tmp / f).parent.mkdir(parents=True, exist_ok=True)     # even when tracker files sit in a subfolder
                shutil.copy2(project / f, tmp / f)
        for d in (records_dir, '.manuscript', '.writing', '.claude', tools_dir):
            if (project / d).is_dir():
                copy_tree(project / d, tmp / d)
        src_dir = cfg.get('manuscript', {}).get('source_dir')
        if with_manuscript and src_dir and (project / src_dir).is_dir():
            copy_tree(project / src_dir, tmp / src_dir)
        # overwrite with the canonical files
        for item in manifest['files']:
            s = SKILL / item['src']; d = tmp / item['dst'].replace('{tools_dir}', tools_dir)
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(s, d)
            old_name = _config.LEGACY_TOOL_NAMES.get(item['src'])
            if old_name:
                (d.parent / old_name).unlink(missing_ok=True)          # remove old-name copies, as update_tools --apply does
        # put settings values (copy only) — --set and old names the settings do not write
        if sets or cfg != load_raw(project):
            cfg_path = tmp / '.manuscript' / 'project.json'
            if not cfg_path.is_file():
                cfg_path = tmp / '.writing' / 'project.json'
            raw = cfg
            for k, v in sets:
                set_key(raw, k, v)
            cfg_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

        print('=' * 78)
        print(f'preview  {project}')
        print(f'temporary folder {tmp}')
        print(f'--- format of the original: {project_format(project)}')
        logs = []
        rc, out = run(PY + [str(SKILL / 'update_tools.py'), str(tmp), '--apply'], tmp); logs.append(('update_tools.py --apply', rc, out))
        rc, out = run(PY + [str(SKILL / 'migrate_format.py'), str(tmp)], tmp); logs.append(('migrate_format.py (after — preview)', rc, out))
        rc, out = run(PY + [str(tmp / tools_dir / 'index_records.py')], tmp); logs.append(('index_records.py', rc, out))
        rc, out = run(PY + [str(tmp / tools_dir / 'tidy_tracker.py'), '--apply'], tmp); logs.append(('tidy_tracker.py --apply', rc, out))
        snap = {f: (tmp / f).read_bytes() for f in tracker_files if (tmp / f).is_file()}
        rc, out = run(PY + [str(tmp / tools_dir / 'tidy_tracker.py'), '--apply'], tmp); logs.append(('tidy_tracker.py --apply (2nd run)', rc, out))
        idem = all((tmp / f).read_bytes() == b for f, b in snap.items())
        if with_manuscript:
            rc, out = run(PY + [str(tmp / tools_dir / 'check_numbers.py')], tmp); logs.append(('check_numbers.py', rc, out))
        if focus:
            rc, out = run(PY + [str(tmp / tools_dir / 'tidy_tracker.py'), '--focus', focus], tmp); logs.append((f'--focus {focus} (diagnostics)', rc, out))
        for name, rc, out in logs:
            print(f'--- {name}  (exit {rc})')
            keep_lines = 45 if name.startswith('update_tools.py --apply') else 12
            print('\n'.join('    ' + l for l in out.rstrip().split('\n')[-keep_lines:]))
        print(f'--- same after two runs: {"yes" if idem else "no — not idempotent"}')
        print(f'--- format of the copy now: {project_format(tmp)}')
        if state_from:
            print('--- check_sync as the computer whose state was copied')
            print('\n'.join('    ' + l for l in other_computer_view(tmp, tools_dir, Path(state_from)).rstrip().split('\n')))

        print('--- differences from the original')
        for f in tracker_files:
            a, b = project / f, tmp / f
            if not a.is_file() or not b.is_file():
                continue
            ab, bb = a.read_bytes(), b.read_bytes()
            eol = lambda x: 'CRLF' if b'\r\n' in x else 'LF'
            if ab == bb:
                print(f'    {f:24s} same'); continue
            at, bt = ab.decode('utf-8', 'replace'), bb.decode('utf-8', 'replace')
            note = []
            if eol(ab) != eol(bb):
                note.append(f'line endings {eol(ab)} → {eol(bb)}')
            note.append(f'{len(at):,} → {len(bt):,} chars')
            r1 = block_rows(at, '## 1.', '## 2.'); r2 = block_rows(bt, '## 1.', '## 2.')
            if r1 >= 0 and f == t.get('record_index'):
                note.append(f'§1 {r1} → {r2} rows')
            r1, r2 = location_rows(at), location_rows(bt)
            if r1 >= 0:
                note.append(f'§3 {r1} → {r2} rows')
            print(f'    {f:24s} changed — ' + ' · '.join(note))
            if show_diff:
                for l in difflib.unified_diff(at.replace('\r\n', '\n').split('\n'), bt.replace('\r\n', '\n').split('\n'),
                                              f'original/{f}', f'copy/{f}', lineterm='', n=1):
                    print('        ' + l)
        return 0
    finally:
        if keep:
            print(f'kept the temporary folder: {tmp}')
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
    ap.add_argument('--state-from', metavar='DIR')
    a = ap.parse_args()
    sets = []
    for s in a.set:
        k, _, v = s.partition('=')
        sets.append((k.strip(), json.loads(v)))
    rc = 0
    for p in a.projects:
        rc |= preview(Path(p).resolve(), sets, a.with_manuscript, a.focus, a.keep, a.diff, a.state_from)
        if a.grammar:
            rc |= preview_grammar(Path(p).resolve(), sets, a.keep)
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
