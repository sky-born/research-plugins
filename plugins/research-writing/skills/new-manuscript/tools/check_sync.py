# -*- coding: utf-8 -*-
r"""check_sync.py — sync check · snapshot · restore · confirmation for the shared files. The engine is `_sync.py` (same folder).

Usage  (`<py>` is this computer's Python 3 — `python` on Windows, `python3` on macOS)
    <py> -X utf8 tools/check_sync.py                       session start — all checks · boundary snapshot (local + drive) · status line
    <py> -X utf8 tools/check_sync.py --quick               checks only (no snapshot)
    <py> -X utf8 tools/check_sync.py --end                 session end — boundary snapshot · retention cleanup (the tidy tool's --apply calls it)
    <py> -X utf8 tools/check_sync.py --ack "<user's words>"  closes open ERRORs with the user's confirmation — only after showing them to the user and getting it
    <py> -X utf8 tools/check_sync.py --accept-warn         with only WARNs, aligns the baselines (written-line registry · seen records · IDs) with the current state — no words needed ·
                                                           refused (2) while an ERROR is open
    <py> -X utf8 tools/check_sync.py --damage              full loss report — lines this computer wrote that have vanished
    <py> -X utf8 tools/check_sync.py --restore <file> [--at "YYYY-MM-DD HH:MM" | --hash <8 chars>]
                                                           reverts to a snapshot (keeps the current version first)
    <py> -X utf8 tools/check_sync.py --snapshots <file>    list of that file's snapshots
    <py> -X utf8 tools/check_sync.py --guard <file> [--tool Edit]   decision right before a write (called by the hook and tools) — prints the reason and exits 2 when it blocks
    <py> -X utf8 tools/check_sync.py --after-write <file>  post-write processing (called by the hook and tools)
    <py> -X utf8 tools/check_sync.py --after-bash          after Bash — processes only the shared files whose fingerprint changed

Exit codes — 0 OK · 1 WARN or confirmed ERROR (within ack_hours — does not block writes) · 2 unconfirmed ERROR (or --guard blocked) · 3 argument or settings error
With an ERROR, show it to the user and get a confirmation before writing shared files (`--ack`). With only WARNs, treat the files as synced — report the
status line and proceed after aligning the baselines with `--accept-warn`. A "to do" (a generated file older than its source — S4 forward) is the normal state
that only needs regenerating; it is not a sync warning and the exit code is 0. Rules: plugin `tracker-workflow.md` "Sync — several computers write the shared files".
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import load as _load_cfg, _utf8_console  # noqa: E402
from _sync import Sync, find_project_root, parse_utc  # noqa: E402


def _rc(findings, sync=None):
    """2 — unconfirmed ERROR · 1 — confirmed ERROR (within ack_hours) or WARN · 0. Confirmation is decided by Sync.ack_of only."""
    errs = [f for f in findings if f.level == 'ERROR']
    if any(sync is None or sync.ack_of(f.key) is None for f in errs):
        return 2
    return 1 if errs or any(f.level == 'WARN' for f in findings) else 0


def _print(findings, show_info=False, sync=None):
    for f in findings:
        if f.level == 'INFO' and not show_info:
            continue
        ack = sync.ack_of(f.key) if (sync is not None and f.level == 'ERROR') else None
        note = ''
        if ack:
            try:
                when = parse_utc(ack['utc']).astimezone().strftime('%m-%d %H:%M')
            except (KeyError, ValueError):
                when = '?'
            note = '  [confirmed %s — %s]' % (when, str(ack.get('text', ''))[:40])
        print(('  ! ' if f.level != 'INFO' else '  · ') + f.line() + note)


def main(argv=None):
    _utf8_console()
    ap = argparse.ArgumentParser(description='Sync check · snapshot · restore for the shared files')
    ap.add_argument('--dir', help="project root (default: searched from this file's location or the current folder)")
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--end', action='store_true')
    ap.add_argument('--ack', metavar='WORDS')
    ap.add_argument('--accept-warn', action='store_true')
    ap.add_argument('--damage', action='store_true')
    ap.add_argument('--restore', metavar='FILE')
    ap.add_argument('--at', metavar='TIME')
    ap.add_argument('--hash', metavar='HASH8')
    ap.add_argument('--snapshots', metavar='FILE')
    ap.add_argument('--guard', metavar='FILE')
    ap.add_argument('--tool', default='tool')
    ap.add_argument('--after-write', metavar='FILE')
    ap.add_argument('--after-bash', action='store_true')
    ap.add_argument('--verbose', '-v', action='store_true')
    a = ap.parse_args(argv)

    root = a.dir
    if not root:
        here = os.path.dirname(os.path.abspath(__file__))
        root = find_project_root(here) or find_project_root(os.getcwd())
    if not root:
        print('Project settings (.manuscript/project.json) not found — give the root with --dir', file=sys.stderr)
        return 3
    try:
        sync = Sync(_load_cfg(root))
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 3

    if a.guard:
        reason = sync.guard(a.tool, a.guard.replace('\\', '/'))
        if reason:
            print(reason)
            return 2
        return 0
    if a.after_write:
        sync.after_write(a.after_write.replace('\\', '/'))
        return 0
    if a.after_bash:
        ch = sync.after_bash()
        if a.verbose and ch:
            print('Shared files with a changed fingerprint: ' + ' · '.join(ch))
        return 0
    if a.ack is not None:
        if not a.ack.strip():
            print("--ack takes the user's confirmation words verbatim", file=sys.stderr)
            return 3
        n = sync.ack(a.ack.strip())
        print('Confirmation recorded — ERRORs closed: %d · vanished IDs and lines accepted as legitimate deletions (%s)' % (n, sync.me))
        return 0
    if a.accept_warn:
        if sync.accept_warn() is None:
            print('WARN acceptance refused — there are unconfirmed ERRORs. Show them to the user, get a confirmation and close them with `--ack "<words>"`.')
            _print(sync.unacked(), sync=sync)
            return 2
        print('WARN accepted — baselines (written-line registry · seen records · IDs) aligned with the current state (%s). ERRORs untouched' % sync.me)
        return 0
    if a.snapshots:
        snaps = sync.snapshots_of(a.snapshots)
        if not snaps:
            print('No snapshots: %s' % a.snapshots)
            return 1
        for s in snaps:
            where = 'local' if s[5].startswith(sync.local_snap_dir) else 'drive'
            print('  %s  %-16s %s  %s  %s' % (s[0], s[1], s[3], where, os.path.getsize(s[5])))
        return 0
    if a.restore:
        pick = sync.restore(a.restore, at=a.at, digest=a.hash)
        print('Restored: %s ← %s (%s · %s)' % (a.restore, os.path.basename(pick[5]), pick[1], pick[0]))
        return 0
    if a.damage:
        findings = sync.s6(verbose=True)
        if not findings:
            print('No loss — every line this computer wrote is still there')
            return 0
        for f in findings:
            print('! ' + f.msg)
            for pv in f.items:
                print('    - ' + pv)
        return 1
    if a.end:
        findings, removed = sync.session_end()
        print('Session end — drive snapshots updated · retention cleanup deleted %d%s' % (removed, '' if not findings else ' · ERROR left'))
        _print(findings, sync=sync)
        return _rc(findings, sync)

    findings = sync.session_start(snapshot=not a.quick)
    print(sync.status_line(findings))
    _print(findings, show_info=a.verbose, sync=sync)
    if not a.verbose:                     # S4 forward — a to-do, not a sync warning. INFO, but always shown
        for f in findings:
            if f.level == 'INFO' and f.key.endswith(':stale'):
                print('  · to do  ' + f.msg)
    rc = _rc(findings, sync)
    if rc == 2:
        print('  → Show this to the user and get a confirmation before writing shared files. Then `--ack "<words>"`. Overwritten files: `--restore <file>`.')
    elif rc == 1:
        print('  → Report WARNs in the status line and proceed (do not ask). To align the baselines with the current state: `--accept-warn` (refused while an ERROR is open).')
        if any(f.level == 'ERROR' for f in findings):
            print('    A confirmed ERROR does not block writes for `ack_hours` — a changed condition (another number or ID) blocks again.')
    return rc


if __name__ == '__main__':
    sys.exit(main())
