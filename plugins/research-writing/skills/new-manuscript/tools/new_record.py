# -*- coding: utf-8 -*-
r"""new_record.py — creates a completion record file atomically under the next free number.

Usage
    python tools/new_record.py <body file> [--no-index]

<body file> is UTF-8 text whose **first line is `# E? — <title>`**. The number this tool assigns replaces `E?`,
and every other `E?` in the body gets the same number (for self-references).
The body needs `**Completed**`·`**Target**`·`**Status**` lines — if one is missing, the file is still created with a warning
(the pre-0.14 Korean labels are accepted too — `_config.FIELDS`). A project whose tracker anchors are still Korean or mixed is refused (exit 5).
The target becomes the reverse index of the record index, so it is checked with the location syntax (`_location.py`) on creation — no file, or section
markers only, gives a warning; names whose folder cannot be confirmed give a note; the file is created either way. Rules: `tracker-workflow.md`
"Target and location syntax — the location table and the reverse index are built from it".

Why the tool assigns the number — two sessions in the same folder can pick the same "next number", and one record then overwrites
the other. This tool creates the file with `O_CREAT|O_EXCL`, so an existing file makes it fail and move on to the next number.
**Callers write the number into other documents only after receiving it from the output.** Writing the number first and creating the file later
is forbidden — if creation fails, every reference already written has to be traced back.

After creating the record it **also regenerates the record index (`index_records.py`)** — the index depends only on the record files, so it can be
brought up to date at once, and the sync check (S4) at the next session start then does not report an outdated index. `--no-index` turns this off (when making several records in a row).

Output  one line on standard output:  E316<TAB>records/E316.md  (notes from the index rebuild go to standard error — standard output carries the number line only)
Exit    0 success · 1 body format or read error · 2 could not secure a number · 3 refused by a sync check ERROR ·
        5 refused: old-format or mixed anchors

The script lives in the tools folder and reads the records folder and prefix from `.manuscript/project.json` (`_config.py`).
"""
import io
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import load, _utf8_console, FIELDS, field_pattern, tok, require_writable_format  # noqa: E402

MAX_TRIES = 100
REQUIRED = ('completed', 'target', 'status')       # keys of _config.FIELDS — either spelling of the label counts


def _rebuild_index(root):
    """Regenerates the record index — runs `index_records.py` from the same folder as a separate process (so module-level state does not mix)."""
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index_records.py')
    r = subprocess.run([sys.executable, '-X', 'utf8', tool], cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace')
    # standard output keeps the "one number line" contract; the index tool's output goes to standard error
    for line in (r.stdout + r.stderr).splitlines():
        if line.strip():
            print('  ' + line, file=sys.stderr)
    if r.returncode != 0:
        print('  ! could not regenerate the index (rc=%d) — run `index_records.py` separately' % r.returncode, file=sys.stderr)
    return r.returncode


def main(argv):
    _utf8_console()
    rebuild = '--no-index' not in argv[1:]
    args = [a for a in argv[1:] if a != '--no-index']
    if len(args) != 1 or args[0] in ('-h', '--help'):
        print(__doc__)
        return 1
    try:
        body = io.open(args[0], encoding='utf-8-sig').read()
    except OSError as e:
        print('Could not read the body file: %s' % e)
        return 1

    cfg = load()
    require_writable_format(cfg, 'new_record')          # English anchors only — an old or mixed project is migrated first
    from _sync import Sync, refuse_if_alert
    sync = Sync(cfg)
    if not refuse_if_alert(sync, True, 'new_record'):
        return 3
    prefix = cfg.raw['tracker'].get('record_prefix', 'E')
    holder = re.compile(r'\b%s\?' % re.escape(prefix))
    first = body.split('\n', 1)[0].rstrip('\r')
    if not re.match(r'^# %s\?\s*[—-]\s*\S' % re.escape(prefix), first):
        print("The first line must have the form '# %s? — <title>'. Now: %r" % (prefix, first[:80]))
        return 1
    for key in REQUIRED:
        if not re.search(field_pattern(key), body):
            print('  ! no **%s** line — the index and tidy tools will warn' % tok(FIELDS[key]))
    m = re.search(field_pattern('target') + r'\s*(.+)', body)
    if m:
        # What cannot be fixed later is checked on creation — confirmed records are never edited, so the index tool does not warn on every run.
        from _location import Grammar
        p = Grammar(cfg).parse(m.group(1).strip())
        if p.empty or (not p.files and p.orphans):
            print('  ! cannot parse the target — write the path relative to the root in backticks, and sections right after the path: %r'
                  % m.group(1).strip()[:80])
        elif p.unresolved:
            print('  · names not confirmed (indexed as written): ' + ' · '.join(p.unresolved))

    rec_dir = os.path.join(cfg.root, cfg.records_dir)
    if not os.path.isdir(rec_dir):
        os.makedirs(rec_dir)
    pat = re.compile(r'^%s(\d+)\.md$' % re.escape(prefix))
    nums = [int(m.group(1)) for f in os.listdir(rec_dir) for m in [pat.match(f)] if m]
    n = (max(nums) if nums else 0) + 1
    seen_max = sync.max_record_seen()
    if n <= seen_max:
        # If the folder's highest number is below what this computer has seen, the mirror has not caught up — picking a number now would collide with another computer's record.
        print('No number assigned — this computer has seen up to %s%d but the folder\'s highest is %s%d. The latest records may not have arrived yet; '
              'run again after sync finishes (if the user has confirmed: `%s --ack "<words>"`).'
              % (prefix, seen_max, prefix, n - 1, cfg.tool('check_sync.py')))
        return 2

    for _ in range(MAX_TRIES):
        path = os.path.join(rec_dir, '%s%d.md' % (prefix, n))
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            n += 1
            continue
        with io.open(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(holder.sub('%s%d' % (prefix, n), body))
        rel = os.path.relpath(path, cfg.root).replace(os.sep, '/')
        sync.after_write(rel)
        sync.remember_records()
        print('%s%d\t%s' % (prefix, n, rel), flush=True)
        if rebuild:
            _rebuild_index(cfg.root)      # the record already exists even if this fails, so 0 — only a note
        return 0

    print('Could not secure a number (%d tries)' % MAX_TRIES)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
