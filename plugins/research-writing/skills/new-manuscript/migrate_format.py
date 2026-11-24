# -*- coding: utf-8 -*-
r"""migrate_format.py — moves the tracker anchors of a manuscript project from the pre-0.14 Korean spellings to English.

`update_tools.py` calls it — the preview in its check mode, the rewrite in `--apply` (after the tool copies are current, before
the generated files are rebuilt). The rewrite runs only through `update_tools.py --apply`, so English anchors never meet older
tool copies. Alone it only previews:

    <py> -X utf8 migrate_format.py <project>            preview — per file: lines to change, unknown column names

What it rewrites — only the positions the tools own, in the tracker files (index · pending · archive · proposals · literature ·
record index): whole block-marker lines, generated-stamp lines, and the known column names of `| ID |` header rows.
What stays — unknown column names (reported), history (records `E*.md`, archive rows, the grammar baseline), values (status
and trigger cells), headings and prose, `project.json`. The tools read the Korean spellings of all of these forever.
Idempotent — a second run changes nothing. The rewrite refuses while the sync check has an open ERROR other than S9 (mixed
anchors — the one condition it removes), takes the write lock, keeps a drive snapshot of each file before and after, refuses
(writes nothing more) when a file changed between reading and writing, and afterwards drops only the recorded S9 findings.
Exit — 0 nothing to do or done · 1 preview found changes · 2 project or settings error · 3 refused by an open sync ERROR ·
4 lock not taken or a file changed — run again.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools'))
import _config                                      # noqa: E402  — the format tokens of this plugin copy
from _config import BLOCKS, COLUMNS, STAMP_WORDS, split_cells, _norm   # noqa: E402

# Korean marker name (with a class letter where the token has `{}`) → English name
_KO_MARKERS = [(re.compile('^' + re.escape(ko).replace(r'\{\}', '([A-Z]{1,2})') + '$'), en) for en, ko in BLOCKS.values()]
_MARKER_LINE = re.compile(r'^<!-- (/?)(.+?) -->(\s*)$')
_KO_STAMP = '<!-- %s ' % STAMP_WORDS[1]
_EN_STAMP = '<!-- %s ' % STAMP_WORDS[0]
_KO_COLUMNS = dict((_norm(ko), en) for en, ko in COLUMNS.values())


class Stale(Exception):
    """A file changed between the preview and the rewrite."""


def _marker(line):
    m = _MARKER_LINE.match(line)
    if not m:
        return None
    for rx, en in _KO_MARKERS:
        k = rx.match(m.group(2))
        if k:
            return '<!-- %s%s -->%s' % (m.group(1), en.format(*k.groups()), m.group(3))
    return None


def _header(line):
    """(new line or None, [unknown names]) for an `| ID |` header row."""
    cells = split_cells(line)
    if not cells or cells[0] != 'ID':
        return None, []
    out, changed, unknown = [], False, []
    for c in cells:
        en = _KO_COLUMNS.get(_norm(c))
        if en:
            out.append(en)
            changed = True
        else:
            out.append(c)
            if c != 'ID' and not _config.column_key(c):
                unknown.append(c)
    return ('| ' + ' | '.join(out) + ' |' if changed else None), unknown


def rewrite(text):
    """(new text, [(line number, old, new)], [(line number, unknown column name)]) — the anchor rewrite of one file's text.
    Line endings are kept (CRLF files stay CRLF); code fences are skipped."""
    eol = '\r\n' if '\r\n' in text else '\n'
    lines = text.split(eol)
    changes, unknown, fence = [], [], False
    for i, line in enumerate(lines):
        if line.startswith('```'):
            fence = not fence
            continue
        if fence:
            continue
        new = _marker(line)
        if new is None and line.startswith(_KO_STAMP):
            new = _EN_STAMP + line[len(_KO_STAMP):]
        if new is None and line.startswith('|'):
            new, unk = _header(line)
            unknown += [(i + 1, u) for u in unk]
        if new is not None and new != line:
            changes.append((i + 1, line, new))
            lines[i] = new
    return eol.join(lines), changes, unknown


def plan(cfg):
    """[(file relative to the root, real path, old bytes, new text, changes, unknown names)] for the tracker files that exist."""
    out = []
    for rel in _config.tracker_anchor_files(cfg):
        path = os.path.join(cfg.root, *rel.split('/'))
        if not os.path.isfile(path):
            continue
        with io.open(path, 'rb') as f:
            raw = f.read()
        new, changes, unknown = rewrite(raw.decode('utf-8'))
        out.append((rel, path, raw, new, changes, unknown))
    return out


def report(plans, show=3):
    """Lines for people — what the rewrite would change and what it leaves."""
    L = []
    total = sum(len(p[4]) for p in plans)
    for rel, _path, _raw, _new, changes, unknown in plans:
        if not changes and not unknown:
            continue
        L.append('  %-32s %d lines to change%s' % (rel, len(changes), (' · unknown column names kept: %d' % len(unknown)) if unknown else ''))
        for n, old, new in changes[:show]:
            L.append('      %d: %s  →  %s' % (n, old.strip()[:60], new.strip()[:60]))
        if len(changes) > show:
            L.append('      … %d more' % (len(changes) - show))
        for n, name in unknown[:show]:
            L.append('      %d: kept `%s`' % (n, name))
    L.insert(0, 'Format migration — %d anchor lines to change' % total if total else 'Format migration — nothing to change')
    if total:
        L.append('  Not touched: completion records, archive rows, status and trigger values, headings and prose, the grammar baseline, '
                 'project.json — the tools read both spellings.')
    return L


def apply(cfg, plans, sync):
    """Writes the planned files inside the caller's write lock. Raises Stale (and writes nothing more) if a file changed since the plan."""
    from _sync import _atomic_write
    written = []
    for rel, path, raw, new, changes, _unknown in plans:
        if not changes:
            continue
        with io.open(path, 'rb') as f:
            if f.read() != raw:
                raise Stale(rel)
        sync.snapshot(rel, drive=True)          # the pre-migration version, on the drive too — the way back
        sync.before_write(rel)
        _atomic_write(path, new.encode('utf-8'))
        sync.after_write(rel)
        sync.snapshot(rel, drive=True)
        written.append(rel)
    return written


def migrate(project, do_apply):
    """(exit code, report lines, written files)."""
    cfg = _config.load(project)
    plans = plan(cfg)
    lines = report(plans)
    if not any(p[4] for p in plans):
        return 0, lines, []
    if not do_apply:
        return 1, lines, []
    from _sync import Sync
    sync = Sync(cfg)
    # The sync guard, as for every writing tool — except S9, the mixed anchors this rewrite removes. Any other open ERROR (a gap in
    # the records, a lost ID, an overwrite) is shown to the user and confirmed first; the rewrite must not bury its evidence.
    others = [f for f in sync.blocking() if f.code != 'S9']
    if others:
        return 3, lines + ['! Not migrated — the sync check has open ERRORs. Show them to the user, close them with check_sync.py '
                           '--ack "<the user\'s words>", then run again:'] + ['    ' + f.line() for f in others], []
    with sync.write_lock('migrate_format') as lock:
        if lock.busy:
            return 4, lines + ['! ' + lock.busy_message()], []
        try:
            written = apply(cfg, plan(cfg), sync)          # planned again inside the lock — the files as they are now
        except Stale as e:
            return 4, lines + ['! Not finished — %s changed while migrating. Run again (the migration is idempotent).' % e], []
    sync.drop_alerts('S9')                                 # the condition is gone; the next check records it again if not
    return 0, lines, written


def main(argv):
    _config._utf8_console()
    args = argv[1:]
    if '--apply' in args:
        print('The rewrite runs through update_tools.py <project> --apply, which makes the tool copies current first.')
        return 2
    if len(args) != 1 or args[0] in ('-h', '--help'):
        print(__doc__)
        return 2
    project = os.path.abspath(args[0])
    if not os.path.isdir(project):
        print('No project folder: %s' % project)
        return 2
    rc, lines, _written = migrate(project, False)
    print('\n'.join(lines))
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv))
