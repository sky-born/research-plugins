# -*- coding: utf-8 -*-
r"""index_records.py — builds the record index from the completion records (one file per item).

Usage  (`<py>` is this computer's Python 3 — `python` on Windows, `python3` on macOS)
    <py> tools/index_records.py            regenerates the record index (the usual run)
    <py> tools/index_records.py --check-targets  shows the targets of old records that the syntax could not confirm (changes no file)

The script lives in the tools folder and reads folder and file names from `.manuscript/project.json` (default `records/` · `tracker_records_index.md`).
Every item needs `**Completed**` · `**Target**` · `**Status**` lines at its head — the format is in the records folder's `README.md`,
the target syntax in `_location.py`. Records made before 0.14 spell the labels in Korean; both spellings are read (`_config.FIELDS`).
A record without a target gives a warning and is left out of the reverse index by section.
The index is written in English and refused in a project whose tracker anchors are still Korean or mixed (exit 5).
"""
import os, re, sys, io

def _utf8_console():
    """The default Windows console (cp949) cannot print characters such as '—' and dies mid-output.
    Switches standard output to UTF-8 so the tool runs from any shell,
    without a `PYTHONIOENCODING` prefix."""
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


_utf8_console()


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import load as _load_cfg, project_root          # noqa: E402

# Folder and file names come from `.manuscript/project.json`; without it the defaults apply.
_CFG = _load_cfg()
HERE = project_root()
OUT = os.path.join(HERE, _CFG.records_dir)
BS = lambda p: str(p).replace('/', '\\')       # noqa: E731  — path notation in generated text (the same characters on every operating system)

# ---------------------------------------------------------------- building the index
IDX = os.path.join(HERE, _CFG.record_index_file)
from _location import Grammar, Excluder, section_key   # noqa: E402  — the "file · section" syntax lives in _location.py only
from _config import (state_head, field_pattern, PLACEHOLDERS, COLUMNS, tok,      # noqa: E402  — the status vocabulary and the format tokens live in _config.py only
                     require_writable_format, LEGACY_FLAGS as _LEGACY_FLAGS)
NOT_GIVEN = tok(PLACEHOLDERS['not_given'])
_NOT_GIVEN_ANY = set(PLACEHOLDERS['not_given'])
from _sync import Sync, refuse_if_alert           # noqa: E402  — the sync guard lives in _sync.py only

_SYNC = None


def _sync():
    global _SYNC
    if _SYNC is None:
        _SYNC = Sync(_CFG)
    return _SYNC


def read_entries():
    """Reads the records folder's E*.md into a list of (number, ID, title, completed, target, status, line count).
    The field labels are read in either spelling (`_config.FIELDS`)."""
    out = []
    if not os.path.isdir(OUT):
        return out
    for f in os.listdir(OUT):
        m = re.match(r'^E(\d+)\.md$', f)
        if not m:
            continue
        s = io.open(os.path.join(OUT, f), encoding='utf-8').read()
        head = s.split('\n')[0].lstrip('# ').strip()
        eid, title = (head.split('—', 1) + [''])[:2]
        g = lambda k: (re.search(field_pattern(k) + r'\s*(.+)', s) or [None, ''])[1].strip()   # noqa: E731
        out.append((int(m.group(1)), eid.strip(), title.strip(),
                    g('completed'), g('target'), g('status'), len(s.split('\n'))))
    return sorted(out)


def warnings_for(ents):
    """Warnings for people to read. Changes no file."""
    w = []
    miss = [e[1] for e in ents if not e[4] or e[4] in _NOT_GIVEN_ANY]
    if miss:
        w.append('completion records: %d without a target (`**Target**`) — %s' % (len(miss), ', '.join(miss)))
    nums = [e[0] for e in ents]
    if nums:
        gap = ['E%d' % n for n in range(1, max(nums) + 1) if n not in set(nums)]
        if gap:
            w.append('completion records: missing E numbers %s' % gap)
    return w


def parse_entries(ents):
    """Splits the target of every item into (file, section).

    Returns (grammar, reverse index {path relative to the root: {section: [E…]}}, text without a file {text: [E…]},
    E list that touched only excluded files, names not confirmed [(E, name)], section markers without a file [(E, [section…])]).
    Exclusion (the tracker files in the settings · `record_index_exclude` · `output_pattern`) applies to this index only.
    """
    g, ex = Grammar(_CFG), Excluder(_CFG)
    idx, free, only_excl, asis, orphans = {}, {}, [], [], []
    for n, eid, title, date, tgt, st, ln in ents:
        p = g.parse(tgt)
        asis += [(eid, a) for a in p.unresolved]
        if p.orphans:
            orphans.append((eid, p.orphans))
        if not p.files:
            free.setdefault(p.free_text or NOT_GIVEN, []).append(eid)
            continue
        kept = [(path, secs) for path, secs in p.files.items() if not ex.hit(path, p.written.get(path))]
        if not kept:
            only_excl.append(eid)
            continue
        for path, secs in kept:
            d = idx.setdefault(path, {})
            for s in (secs or ['']):
                d.setdefault(s, []).append(eid)
    return g, idx, free, only_excl, asis, orphans


def render_index():
    """Builds the index text as a string. Writes nothing — returns (text, items, reverse index)."""
    ents = read_entries()
    if not ents:
        return None, [], {}
    g, idx, free, only_excl, asis, orphans = parse_entries(ents)
    C = lambda k: tok(COLUMNS[k])                 # noqa: E731  — written column names
    L = ['# Record index — %s' % _CFG.name,
         _sync().stamp_for_records(),             # generation stamp — the set of completion records it was made from (sync check S4 compares it)
         '',
         '**Open only this file to find a completion record.** Each item\'s body is one file, `%s\\E<number>.md`.' % BS(_CFG.records_dir),
         'This file is generated by `%s` — do not edit it by hand.' % BS(_CFG.tool('index_records.py')), '',
         'To rebuild this index — `<py> %s`' % _CFG.tool('index_records.py'),
         '`<py>` is this computer\'s Python 3 — `python` on Windows, `python3` on macOS.', '',
         'Reading order — ① find the file and section you will touch in the **reverse index by section** below and get the IDs, '
         '② read only `%s\\E<number>.md`.' % BS(_CFG.records_dir),
         '', '---', '', '## 1. Reverse index by section', '',
         'Section and figure numbers are those at the time the record was written. `—` marks a record that names no section.', '',
         '| %s | %s | %s |' % (C('file'), C('section'), C('item')), '|---|---|---|']
    for path in sorted(idx, key=lambda p: g.sort_key(p)):
        for s in sorted(idx[path], key=section_key):
            L.append('| `%s` | %s | %s |' % (g.display(path), s or '—', ' · '.join(idx[path][s])))
    for t in sorted(free):
        L.append('| %s | — | %s |' % (t, ' · '.join(free[t])))
    if only_excl:
        L.append('| %s | — | %s |' % (tok(PLACEHOLDERS['excluded_only']), ' · '.join(only_excl)))
    L += ['', '---', '', '## 2. ID index', '',
          '| ID | %s | %s | %s |' % (C('item'), C('completed'), C('status')), '|---|---|---|---|']
    for n, eid, title, date, tgt, st, ln in ents:
        L.append('| %s | %s | %s | %s |' % (eid, title, date, state_head(st)))
    L += ['', '---', '', '## 3. Items archived from D·B', '',
          'The bodies are in `%s`.' % BS(_CFG.archive), '']
    mig = os.path.join(HERE, _CFG.archive)
    if os.path.exists(mig):
        s = io.open(mig, encoding='utf-8').read()
        ids = re.findall(r'^\|\s*([A-Z]\d+)\s*\|', s, re.M)
        L.append('%d items — %s' % (len(ids), ' · '.join(ids)))
    L.append('')
    return '\n'.join(L) + '\n', ents, idx


def check():
    """`--check-targets` — shows the targets of old records that the syntax could not confirm. Changes no file.
    Why it does not warn on every run — confirmed records are never edited, so the warnings would be permanent noise."""
    ents = read_entries()
    if not ents:
        print('No completion records.'); return 0
    g, idx, free, only_excl, asis, orphans = parse_entries(ents)
    print('Names not confirmed (indexed as written): %d' % len(asis))
    for eid, a in asis:
        print('  %s\t%s' % (eid, a))
    print('Section markers without a file (left out of the index): %d' % len(orphans))
    for eid, secs in orphans:
        print('  %s\t%s' % (eid, ' · '.join(secs)))
    print('Records indexed as text without a file: %d — %s' % (len(free), ' · '.join('%s: %s' % (t, ' '.join(v)) for t, v in free.items())))
    print('Records that touched only excluded files: %d — %s' % (len(only_excl), ' · '.join(only_excl)))
    return 0


EMPTY_INDEX = '''# Record index

**Open only this file to find a completion record.** Each item's body is one file in the records folder.
This file is generated by index_records.py - do not edit it by hand.

No completion records yet. Run this tool again after making the first one.
'''


def build_index():
    require_writable_format(_CFG, 'index_records')       # English anchors only — an old or mixed project is migrated first
    if not refuse_if_alert(_sync(), True, 'index_records'):
        return 3
    with _sync().write_lock('index_records') as lock:     # reading records → writing the index as one unit — so it does not interleave with the tidy tool or another index run
        if lock.busy:                                   # the index is rebuilt wholesale from the record files, so if it is not built now the next run catches up
            print('! ' + lock.busy_message())
            return 4
        return _build_index_locked()


def _build_index_locked():
    text, ents, bysec = render_index()
    if text is None:
        # A new project without completion records yet — writes an empty index and exits normally,
        # because the tidy tool expects the index file to exist.
        if os.path.isdir(OUT):
            io.open(IDX, 'w', encoding='utf-8', newline='').write(EMPTY_INDEX)
            print('Index created — no completion records yet (0 items)')
            return 0
        print('Records folder %s is missing. Create it first.' % _CFG.records_dir); return 1
    _sync().before_write(_CFG.record_index_file.replace('\\', '/'))
    io.open(IDX, 'w', encoding='utf-8', newline='').write(text)
    _sync().after_write(_CFG.record_index_file.replace('\\', '/'))
    print('%s regenerated — items %d, files %d · rows %d'
          % (_CFG.record_index_file, len(ents), len(bysec), sum(len(v) for v in bysec.values())))
    for w in warnings_for(ents):
        print('  ! ' + w)
    return 0


if __name__ == '__main__':
    if any(_LEGACY_FLAGS.get(a, a) == '--check-targets' for a in sys.argv[1:]):   # the old name of the flag is accepted too
        sys.exit(check())
    sys.exit(build_index())
