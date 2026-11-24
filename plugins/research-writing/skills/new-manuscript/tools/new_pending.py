# -*- coding: utf-8 -*-
r"""new_pending.py — registers a new open item (a letter table of the pending file, or the proposals table) under the next number.

Usage  (`<py>` is this computer's Python 3 — `python` on Windows, `python3` on macOS)
    <py> -X utf8 tools/new_pending.py <row file>

<row file> is one line of UTF-8 text: a table row whose **ID cell is `<letter>?`** — pending `| D? | Item | Location | Trigger | Status | Note |`,
proposals `| H? | Proposal | Location | Trigger | Status | Note |`. The number and order of cells must match the table's header (one item per line · `|` inside a cell is `\|`).
The number this tool assigns replaces `<letter>?`, and every other `<letter>?` in the row gets the same number (for self-references).

Why the tool assigns the number — two sessions in the same folder can pick the same "next number" and put one ID on two items. Edit replaces only
the target string, so both succeed, and the duplicate shows up only later in a tidy-tool warning. This tool rereads the file **inside the write lock**,
assigns the number and inserts the row there and then, so two runs on the same computer never get the same number. The hook (`guard_write.py`) refuses
Edit and Write calls that add a new ID row by hand. **Callers write the number into other documents only after receiving it from the output.**

Number — the letter's highest number + 1. Looks at the rows of the pending, archive, proposals and literature files together with the IDs this computer has
         seen (sync state) — IDs are never reused, so archived numbers are skipped too.
Place  — the bottom of the letter's table. In the pending file, the table of the `## <letter>. …` section; in the proposals file, the table that holds rows of that letter (else the first table).
Scope  — `_config.allocation_scope` (the pending file's category letters · the proposals file's letter). The literature file and branch numbers (`D35-1`) are not handled.
Not covered — another computer getting the same number (the sync check watches for that) · rows inserted directly with Python or Bash.

The next `tidy_tracker.py --apply` brings the location table and trigger table of the list (index file) up to date.

Output  one line on standard output:  D137<TAB>tracker_pending.md  (notes and warnings go to standard error — standard output carries the number line only)
Exit    0 success · 1 row format error · 2 table not found (letter out of scope · no section or table · several tables) · 3 refused by a sync check ERROR ·
        4 could not take the lock (run again) · 5 refused: old-format or mixed anchors (`_config.require_writable_format`)
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import (load, _utf8_console, nfc, NEW_ROW_RE, allocation_scope,                      # noqa: E402
                     TABLE_ROW_RE, TABLE_SEP_RE, split_cells, table_problems, describe_table_problem,
                     BLOCKS, column_key, trigger_key, require_writable_format)

HDR = re.compile(r'^\|\s*ID\s*\|')           # table header — the same shape the tidy tool reads


class Problem(Exception):
    def __init__(self, code, text):
        Exception.__init__(self, text)
        self.code = code


def say(text):
    print(text, file=sys.stderr)


def read_row(path):
    """Row file → (row, letter). It must be a single line apart from blank lines, and its ID cell must be `<letter>?`."""
    try:
        body = io.open(path, encoding='utf-8-sig').read()
    except OSError as e:
        raise Problem(1, 'Could not read the row file: %s' % e)
    rows = [l.rstrip() for l in body.replace('\r\n', '\n').split('\n') if l.strip()]
    if len(rows) != 1:
        raise Problem(1, 'The row file must be one line (one item per line) — it has %d lines' % len(rows))
    row = rows[0].strip()
    m = NEW_ROW_RE.match(row)
    if not m:
        raise Problem(1, "The row's ID cell must be `<letter>?`, as in `| D? | … |` — this tool assigns the number. Now: %r" % row[:60])
    if not row.endswith('|') or row.endswith('\\|'):
        raise Problem(1, 'The row must end with `|`: %r' % row[-30:])
    return row, m.group(1)


def _letter(line):
    m = TABLE_ROW_RE.match(line)
    return re.match(r'[A-Z]+', m.group(1)).group(0) if m else None


def _tables(lines, a, b):
    """Tables in the range [a, b) — [[header index, header cells, [row indexes …]]]. The header is a `| ID | …` line; rows are the ID rows below it up to the
    next header, heading or comment. Blank lines between rows are skipped — some older files separate rows with blank lines."""
    out, cur = [], None
    for i in range(a, b):
        l = lines[i]
        if HDR.match(l):
            cur = [i, split_cells(l), []]
            out.append(cur)
        elif cur is not None:
            if l.startswith('#') or l.startswith('<!--'):
                cur = None
            elif TABLE_ROW_RE.match(l):
                cur[2].append(i)
    return out


def locate(lines, letter, sectioned, label):
    """Line index where the new row goes in the letter's table, and the header cells. sectioned — a file split into `## <letter>. …` sections, like the pending file."""
    a, b = 0, len(lines)
    if sectioned:
        heads = [i for i, l in enumerate(lines) if l.startswith('## ')]
        mine = [i for i in heads if re.match(r'^## %s\. ' % re.escape(letter), lines[i])]
        if not mine:
            raise Problem(2, '%s has no `## %s. …` section — if that category was removed, register under a remaining category letter (removed letters are not reissued)'
                          % (label, letter))
        if len(mine) > 1:
            raise Problem(2, '%s: the `## %s. …` section occurs %d times (it must occur once)' % (label, letter, len(mine)))
        a = mine[0]
        b = min([h for h in heads if h > a] or [len(lines)])
    tabs = _tables(lines, a, b)
    if not tabs:
        raise Problem(2, '%s: no %s table (header `| ID | …`) found' % (label, letter))
    own = [t for t in tabs if any(_letter(lines[i]) == letter for i in t[2])]
    if len(own) > 1:
        raise Problem(2, '%s: %s rows appear in %d tables — cannot tell which table to use (headers at lines %s)'
                      % (label, letter, len(own), ' · '.join(str(t[0] + 1) for t in own)))
    head, cells, rows = own[0] if own else tabs[0]
    if rows:
        return rows[-1] + 1, cells
    if head + 1 < len(lines) and TABLE_SEP_RE.match(lines[head + 1]):
        return head + 2, cells
    raise Problem(2, '%s line %d: no separator (`|---|`) under the table header — fix that first' % (label, head + 1))


def next_number(known, letter):
    pat = re.compile(r'^%s(\d+)(?:-\d+)?$' % re.escape(letter))
    nums = [int(m.group(1)) for i in known for m in [pat.match(i)] if m]
    return (max(nums) if nums else 0) + 1


def register(cfg, sync, row, letter):
    """Called inside the lock — reads the file now, assigns the number and inserts the row. (ID, file relative to the root)."""
    from _sync import _read_bytes, _atomic_write
    scope = allocation_scope(cfg)
    if letter not in scope:
        raise Problem(2, 'Letter %s is outside the scope this tool numbers — allowed letters: %s (the literature file and branch numbers by hand)'
                      % (letter, ' · '.join(sorted(scope))))
    rel = scope[letter]
    pending = nfc(str(cfg.pending_file).replace('\\', '/'))
    path = os.path.join(cfg.root, *rel.split('/'))
    try:
        raw = _read_bytes(path)
    except OSError as e:
        raise Problem(2, 'Could not read %s: %s' % (rel, e))
    crlf = b'\r\n' in raw and raw.count(b'\r\n') >= raw.count(b'\n') // 2
    eol = '\r\n' if crlf else '\n'
    text = raw.decode('utf-8')
    lines = text.split(eol)
    at, hdr = locate(lines, letter, rel == pending, rel)
    cells = split_cells(row)
    if len(cells) != len(hdr):
        raise Problem(1, 'Cell count differs from the table — row %d cells, table %d cells: | %s |' % (len(cells), len(hdr), ' | '.join(hdr)))
    ti = next((j for j, h in enumerate(hdr) if column_key(h) == 'trigger'), None)     # either spelling of the column name
    if ti is not None:
        trig = cells[ti].strip()
        if trigger_key(trig) not in {trigger_key(t) for t in cfg.triggers}:
            say('  ! trigger value %r is not in the settings (tracker.triggers) — the tidy tool will warn' % trig)

    new_id = '%s%d' % (letter, next_number(sync.known_ids(), letter))
    line = re.sub(r'(?<![\w-])%s\?' % re.escape(letter), new_id, row)
    lines.insert(at, line)
    out = eol.join(lines)
    before, after = table_problems(text), table_problems(out)
    grew = [c for c in ('orphan', 'cells', 'tail')
            if sum(1 for x in after if x[1] == c) > sum(1 for x in before if x[1] == c)]
    if grew:
        raise Problem(1, 'Not inserted: the row would break the table — %s'
                      % ' · '.join(describe_table_problem(x) for x in after if x[1] in grew)[:400])
    sync.before_write(rel)
    _atomic_write(path, out.encode('utf-8'))
    sync.after_write(rel)
    sync.remember_ids()
    marks = ['<!-- %s -->' % s.format(letter) for s in BLOCKS['hand_locations']]
    found = next((m for m in marks if m in lines), None)
    if found:      # a file with a hand-kept location table (the proposals' `<!-- H-locations -->`) — the tidy tool warns about missing IDs
        say('  %s has a hand-kept location table (`%s`) — add %s to it too' % (rel, found, new_id))
    return new_id, rel


def main(argv):
    _utf8_console()
    args = argv[1:]
    if len(args) != 1 or args[0] in ('-h', '--help'):
        print(__doc__)
        return 1
    try:
        row, letter = read_row(args[0])
        cfg = load()
        require_writable_format(cfg, 'new_pending')        # English anchors only — an old or mixed project is migrated first
        from _sync import Sync, refuse_if_alert
        sync = Sync(cfg)
        if not refuse_if_alert(sync, True, 'new_pending'):
            return 3
        with sync.write_lock('new_pending') as lock:
            if lock.busy:
                say('! ' + lock.busy_message())
                return 4
            new_id, rel = register(cfg, sync, row, letter)
    except Problem as e:
        say('Not registered — %s' % e)
        return e.code
    print('%s\t%s' % (new_id, rel), flush=True)
    say('  The next `tidy_tracker.py --apply` updates the location and trigger tables of the index file')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
