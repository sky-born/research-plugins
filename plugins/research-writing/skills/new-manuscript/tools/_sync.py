# -*- coding: utf-8 -*-
r"""_sync.py — sync guard for the shared files. Check · snapshot · restore · write guard · replace-once helper.

When several computers work on the same manuscript project in a cloud-sync folder (Google Drive and the like), a version written on top of a
mirror that has not caught up is uploaded later and silently overwrites another computer's work. This module prevents, catches and reverts
that **in code** — it spends no model tokens. The rules are in the plugin document `manuscript-workflow/references/tracker-workflow.md`
"Sync — several computers write the shared files".

    from _sync import Sync, replace_once
    s = Sync(cfg)                        # cfg is _config.load()
    s.session_start()                    # session start — checks · boundary snapshot · status line
    s.guard('Edit', 'tracker_pending.md')    # right before a write — reason string to block, or None
    s.after_write('tracker_pending.md')     # right after a write — snapshot · fingerprint · record of "written lines"
    s.session_end()                      # session end — boundary snapshot · retention cleanup
    s.accept_warn()                      # reset the baseline when there are only WARNs — None if an ERROR is open (only ack closes it)
    replace_once(path, old, new)         # replaces only when the target occurs exactly once, keeping line endings, with snapshots

Checks (level · when) — the cause is inferred; the damage is detected exactly, through invariants.
    S1 freshness             WARN   start · update_tools     the latest change to the shared files is older than stale_days
    S2 record continuity     ERROR  start · write            gap in the completion record numbers (except known_gaps) — still catching up
    S3 reference integrity   ERROR  start · write            a source item that a generated file points to is missing (record index → E file · list → open-item ID — only the ID positions of the generated blocks, _config.list_block_ids)
                             WARN   start · write            the shape of a generated list block could not be read, so the ID comparison is skipped
                             WARN   start                    a hand-edited file points to an E number above the highest E
    S4 generation stamp      INFO   start                    the stamp of a generated file differs from the source and the source changed **after** generation (forward) — "to do": regenerate. Not a sync problem
                             WARN   start                    the source went back to an old version this computer saw · content differs with no edit after the stamp · an existing record changed · records shrank
                             ERROR  start                    the source went back to an old version and its mtime is also earlier than the generated file — overwrite
    S5 conflict copies       WARN   start (all) · write (folder)   sync conflict copies (`x 2.md` · `x (1).md` · conflicted copy)
    S6 loss report           WARN   start · --damage         survival of the lines this computer wrote is below survival_pct
    S7 ID monotonicity       ERROR  start · write            an open-item · archive · proposal · literature ID this computer saw has disappeared
    S8 drive                 INFO   start                    whether the sync program's process is running
    S9 format                ERROR  start · write            the tracker files mix English and pre-0.14 Korean anchors (`_config.project_format`) — Drive catching up, or an old tool wrote
                             INFO   start                    the project still uses the Korean anchors — migrate with `update_tools.py --apply`
State lives **outside** the sync folder, per computer, in `~/.claude/sync-state/<project id>/` (`SYNC_STATE_HOME` overrides it — for tests).
The project id is `<name slug>-<root path hash8>` (project_id — defined in that one place). The root path is hashed **after NFC normalization**, so the
hook (NFC path on standard input) and tools run from a shell (NFD path from the macOS file system) use the same folder. Folders made under the old
definition (no normalization, up to 0.11.3) are renamed, or merged into the new folder, when first met (_adopt_legacy_state).
After a write, the "written lines" difference is taken against **the version this computer saw right before writing** (hash in `seen.json` → the snapshot of
that hash) — the latest snapshot by time may be an old version from another computer.
Snapshots go to local storage (`snap/` in the same place) on every write, and to the drive (`sync.snapshot_dir`) at session boundaries and around batch tools.
The name `<UTC>_<computer>_<path(/→__)>_<hash8><ext>` differs every time, so another computer cannot overwrite it, and the same hash is not made twice.
Retention (session start and end) — per file the latest `snapshot_min` are always kept; this computer's snapshots older than `snapshot_days` (twice that locally)
or beyond `snapshot_max` (local `snapshot_max_local`) are deleted oldest first, and other computers' snapshots older than `snapshot_days_others` are deleted. A file that does not change keeps one.
File names, paths and lines are NFC-normalized when compared or used as keys (`_config.nfc`) — NFD names from a macOS mirror and NFC names in settings and text count as the same file.
"""
import datetime
import errno
import hashlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import (load as _load_cfg, CONFIG_REL, CONFIG_REL_OLD, DEFAULTS, nfc,                  # noqa: E402  — nfc: names, paths and lines are compared in NFC
                     TABLE_ROW_RE_M, table_problems, describe_table_problem,              # table row grammar lives in _config.py only (same as the tidy tool and the hook)
                     list_block_ids, id_key,                                              # ID positions of the list and ID order: same definitions as the tidy tool
                     allocation_scope, id_stem,                                           # scope of tool-assigned numbers — same definition as new_pending.py
                     STAMP_RE, STAMP_WORDS, project_format, is_anchor_line)                               # format tokens — stamps in either spelling, the project's format

UTC_FMT = '%Y%m%dT%H%M%SZ'
SNAP_RE = re.compile(r'^(\d{8}T\d{6}Z)_([^_]+)_(.+)_([0-9a-f]{8})(\.[^.]*)?$')
STAMP_LINE = '<!-- %s %%s -->' % STAMP_WORDS[0]    # written in English; STAMP_RE reads both spellings
ROW_ID_RE = TABLE_ROW_RE_M      # row IDs collected by S7 — same definition as the tidy tool's row regex
E_REF_RE = re.compile(r'(?<![\w/\\])E(\d+)(?!\d)')
MIN_LINE = 8          # shorter lines are not counted as "written lines" — separators, empty cells and the like
MAX_LINES_PER_FILE = 3000


# ---------------------------------------------------------------- small shared helpers
def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def utc_stamp(dt=None):
    return (dt or utc_now()).strftime(UTC_FMT)


def parse_utc(s):
    return datetime.datetime.strptime(s, UTC_FMT).replace(tzinfo=datetime.timezone.utc)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def norm_sha(data):
    """Hash with line endings normalized to LF — the same content gives the same hash whatever the computer's line endings."""
    return sha(data.replace(b'\r\n', b'\n'))


def _slug(s):
    s = re.sub(r'[^0-9A-Za-z가-힣_-]+', '-', nfc(s)).strip('-')
    return s[:24] or 'project'


def computer_id():
    """Computer identifier — first line of `<state base folder>/computer_id`, else the hostname. `_` is the separator of the name scheme, so it becomes `-`."""
    p = os.path.join(state_home(), 'computer_id')
    name = ''
    if os.path.isfile(p):
        try:
            name = _read_bytes(p).decode('utf-8', errors='replace').strip().split('\n')[0]
        except OSError:
            name = ''
    if not name:
        name = os.environ.get('COMPUTERNAME') or socket.gethostname() or 'unknown'
    return re.sub(r'[^0-9A-Za-z가-힣-]+', '-', nfc(name)).strip('-')[:32] or 'unknown'


def state_home():
    """State base folder — outside the sync folder. Tests pass a temporary folder via `SYNC_STATE_HOME`."""
    env = os.environ.get('SYNC_STATE_HOME')
    if env:
        return os.path.abspath(env)
    home = os.environ.get('USERPROFILE') or os.path.expanduser('~')
    return os.path.join(home, '.claude', 'sync-state')


def _root_key(root, form='NFC'):
    """Root path string used in the state folder id — absolute path, normcase, `/` separators, then Unicode normalization (form).
    form=None means no normalization (the definition up to 0.11.3) — used only to find old folders."""
    key = os.path.normcase(os.path.abspath(root)).replace('\\', '/')
    return unicodedata.normalize(form, key) if form else key


def project_id(name, root, form='NFC'):
    """State folder name `<name slug>-<root path hash8>` — defined here only. The root path is hashed after NFC normalization, so the hook (NFC path
    on standard input) and tools run from a shell (NFD path from the macOS file system) use the same folder (measured on macOS — when they differ, `--ack` does not reach the hook)."""
    return '%s-%s' % (_slug(name), sha(_root_key(root, form).encode('utf-8'))[:8])


def legacy_project_ids(name, root):
    """Folder names the old definition (no normalization) may have made — only those that differ from the current one. If the root is NFC, the old
    definition gives the same result as now, so only the NFD form remains; if the root is NFD, that form is itself the old folder. Empty list for ASCII paths."""
    cur = project_id(name, root)
    return [p for p in dict.fromkeys(project_id(name, root, f) for f in (None, 'NFD')) if p != cur]


def find_project_root(start):
    """Walks up from start (file or folder) to the folder that holds the settings file. None if there is none."""
    p = os.path.abspath(start)
    if os.path.isfile(p):
        p = os.path.dirname(p)
    while True:
        for rel in (CONFIG_REL, CONFIG_REL_OLD):
            if os.path.isfile(os.path.join(p, rel)):
                return p
        up = os.path.dirname(p)
        if up == p:
            return None
        p = up


def _rel(root, path):
    """Path relative to the root (`/`-separated, NFC). Works even when the two paths differ in normalization (the hook's NFC, the macOS file system's NFD) — both are NFC-normalized before relpath."""
    return nfc(os.path.relpath(nfc(os.path.abspath(path)), nfc(os.path.abspath(root))).replace(os.sep, '/'))


def _line_table(data):
    """Line hash → preview (40 characters). Lines that differ only in whitespace count as the same line.
    Anchor lines (block markers, generated stamps, `| ID |` header rows — `_config.is_anchor_line`) are tool-owned structure, not written content."""
    out = {}
    text = data.decode('utf-8', errors='replace')
    for line in text.split('\n'):
        t = nfc(line.strip())
        if len(t) < MIN_LINE or is_anchor_line(t):
            continue
        out[hashlib.sha1(t.encode('utf-8')).hexdigest()[:12]] = t[:40]
    return out


def _read_bytes(path):
    with io.open(path, 'rb') as f:
        return f.read()


def _atomic_write(path, data):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    tmp = path + '.tmp%d' % os.getpid()
    with io.open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _merge_state_json(name, new, old):
    """Merges two state JSON values into one — new is the more recently written file. Each file has its own rule (merging is idempotent)."""
    if name == 'written.json':                        # {file: {line hash: [utc, preview]}} — union of files and lines, new wins on overlap
        out = {}
        for reg in (old, new):
            for rel, lines in (reg or {}).items():
                if isinstance(lines, dict):
                    out.setdefault(rel, {}).update(lines)
        return out
    if name == 'ids.json':                            # {ID: first-seen utc} — union, the earlier time
        out = dict(old or {})
        for k, v in (new or {}).items():
            out[k] = min(out[k], v) if isinstance(out.get(k), str) and isinstance(v, str) else v
        return out
    if name == 'records_max.json':                    # highest number this computer saw — the larger one
        a, b = (old or {}), (new or {})
        return b if int(b.get('max', 0)) >= int(a.get('max', 0)) else a
    if name == 'alerts.json':                         # findings from new (rewritten on every check), acked is the union (new wins on overlap)
        out = dict(old or {})
        out.update(new or {})
        acked = dict((old or {}).get('acked') or {})
        acked.update((new or {}).get('acked') or {})
        out['acked'] = acked
        return out
    if name == 'ack_log.json':                        # list — concatenated in utc order, duplicates removed, latest 200
        seen, out = set(), []
        for e in sorted(list(old or []) + list(new or []), key=lambda e: str((e or {}).get('utc', ''))):
            k = json.dumps(e, sort_keys=True, ensure_ascii=False)
            if k not in seen:
                seen.add(k)
                out.append(e)
        return out[-200:]
    if isinstance(new, dict) and isinstance(old, dict):   # seen.json · fingerprints.json · other dicts — old fills gaps, new wins on overlap
        out = dict(old)
        out.update(new)
        return out
    return new


def _merge_state_dir(src, dst):
    """Merges the old state folder src into dst, then deletes src — files in subfolders (snap, hook_seen) move only when dst lacks them (names are UTC,
    computer and hash, so equal names mean equal content), JSON files go through _merge_state_json, and other files move only when missing. On a failure midway it raises OSError and leaves src."""
    for name in os.listdir(src):
        s, d = os.path.join(src, name), os.path.join(dst, name)
        if os.path.isdir(s):
            if not os.path.isdir(d):
                os.makedirs(d)
            for f in os.listdir(s):
                if not os.path.exists(os.path.join(d, f)):
                    os.replace(os.path.join(s, f), os.path.join(d, f))
            continue
        if not os.path.exists(d):
            os.replace(s, d)
            continue
        if name.endswith('.json'):
            try:
                a = json.loads(_read_bytes(s).decode('utf-8'))
                b = json.loads(_read_bytes(d).decode('utf-8'))
            except (OSError, ValueError):
                continue
            new, old = (b, a) if _mtime(d) >= _mtime(s) else (a, b)
            _atomic_write(d, json.dumps(_merge_state_json(name, new, old), ensure_ascii=False, indent=0).encode('utf-8'))
    shutil.rmtree(src)


class Finding(object):
    def __init__(self, level, code, key, msg, items=None):
        self.level, self.code, self.key, self.msg = level, code, key, msg
        self.items = list(items or [])

    def as_dict(self):
        return {'level': self.level, 'code': self.code, 'key': self.key, 'msg': self.msg, 'items': self.items[:50]}

    @staticmethod
    def from_dict(d):
        return Finding(d['level'], d['code'], d['key'], d['msg'], d.get('items'))

    def line(self):
        extra = ''
        if self.items:
            shown = ' '.join(str(x) for x in self.items[:12])
            extra = ' — ' + shown + (' …' if len(self.items) > 12 else '')
        return '%-5s %s %s%s' % (self.level, self.code, self.msg, extra)


# ---------------------------------------------------------------- main
class Sync(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.root = os.path.abspath(cfg.root)
        self.t = cfg.raw.get('tracker') or {}
        self.s = cfg.raw.get('sync') or {}
        self.pid = project_id(cfg.name, self.root)          # root path hashed in NFC — the hook (NFC) and the shell (macOS NFD) share the folder
        self.state = os.path.join(state_home(), self.pid)
        self.me = computer_id()
        self._adopt_legacy_state()

    def _adopt_legacy_state(self):
        """Adopts state folders made under the old definition (no normalization, up to 0.11.3) — under it the hook (NFC path) and the shell (NFD path) on
        macOS use different folders and `--ack` does not reach the hook. If the new folder does not exist, the old folder is renamed; if both exist, the old one
        is merged into the new one and deleted. On failure the old folder stays, a note is printed, and the next Sync tries again (merging is idempotent). Without old folders this costs one or two isdir calls."""
        home = state_home()
        for old in legacy_project_ids(self.cfg.name, self.root):
            src = os.path.join(home, old)
            if not os.path.isdir(src):
                continue
            try:
                if os.path.isdir(self.state):
                    _merge_state_dir(src, self.state)
                else:
                    os.rename(src, self.state)
            except OSError as e:
                sys.stderr.write('_sync: could not move the old state folder %s to %s (%s) — will retry next time\n' % (old, self.pid, e))

    # ---- settings -----------------------------------------------
    def opt(self, key, default=None):
        v = self.s.get(key)
        return default if v is None else v

    @property
    def snapshot_dir(self):
        return os.path.join(self.root, *str(self.opt('snapshot_dir', DEFAULTS['sync']['snapshot_dir'])).split('/'))

    @property
    def local_snap_dir(self):
        return os.path.join(self.state, 'snap')

    # ---- file sets ----------------------------------------------
    def _path(self, rel):
        """Real path of rel (relative to the root, NFC). If it does not exist as is, tries the NFD name, then looks in the folder for a name equal in NFC —
        so a file with an NFD name made on a macOS mirror is still the same file when it reaches Windows (NTFS is normalization-sensitive)."""
        rel = rel.replace('\\', '/')
        p = os.path.join(self.root, *rel.split('/'))
        if os.path.exists(p):
            return p
        q = os.path.join(self.root, *unicodedata.normalize('NFD', rel).split('/'))
        if os.path.exists(q):
            return q
        d, base = os.path.split(p)
        if os.path.isdir(d):
            want = nfc(base)
            for f in os.listdir(d):
                if nfc(f) == want:
                    return os.path.join(d, f)
        return p

    def _exists(self, rel):
        return os.path.isfile(self._path(rel))

    def tracker_rel(self, key):
        v = self.t.get(key)
        return nfc(v.replace('\\', '/')) if v else None

    def generated_files(self):
        return {r for r in (self.tracker_rel('index'), self.tracker_rel('record_index')) if r}

    def rewrite_ok(self):
        out = {str(x).replace('\\', '/') for x in (self.opt('rewrite_ok') or [])}
        cp = self.tracker_rel('checkpoint')
        if cp:
            out.add(cp)
        return out

    def records(self):
        """[(number, relative path)] — completion records E*.md"""
        d = os.path.join(self.root, self.cfg.records_dir)
        prefix = self.t.get('record_prefix', 'E')
        pat = re.compile(r'^%s(\d+)\.md$' % re.escape(prefix))
        out = []
        if os.path.isdir(d):
            for f in os.listdir(d):
                m = pat.match(f)
                if m:
                    out.append((int(m.group(1)), _rel(self.root, os.path.join(d, f))))
        return sorted(out)

    def shared_files(self):
        """Shared files — derived from the settings: tracker files · handover · completion records · manuscript .md · sync.shared_extra. Existing files only."""
        out = []
        for k in ('index', 'pending', 'record_index', 'literature', 'proposals', 'archive', 'checkpoint'):
            r = self.tracker_rel(k)
            if r and self._exists(r) and r not in out:
                out.append(r)
        for _n, r in self.records():
            out.append(r)
        src = (self.cfg.raw.get('manuscript') or {}).get('source_dir') or ''
        sd = os.path.join(self.root, src) if src else None
        if sd and os.path.isdir(sd):
            for dp, dns, fns in os.walk(sd):
                dns[:] = [d for d in dns if not self._excluded(_rel(self.root, os.path.join(dp, d)) + '/')]
                for f in sorted(fns):
                    if f.lower().endswith('.md'):
                        r = _rel(self.root, os.path.join(dp, f))
                        if r not in out:
                            out.append(r)
        import glob as _glob
        for pat in (self.opt('shared_extra') or []):
            for p in sorted(_glob.glob(os.path.join(self.root, *str(pat).split('/')))):
                if os.path.isfile(p):
                    r = _rel(self.root, p)
                    if r not in out:
                        out.append(r)
        return out

    def is_shared(self, rel):
        rel = nfc(rel.replace('\\', '/'))
        if rel in self.shared_files():
            return True
        rd = self.cfg.records_dir.replace('\\', '/').rstrip('/') + '/'
        return rel.startswith(rd) and rel.lower().endswith('.md')

    def _excluded(self, rel):
        rel = nfc(rel)
        for ex in (self.opt('exclude') or []):
            ex = nfc(str(ex).replace('\\', '/'))
            if ex.endswith('/'):
                if rel == ex.rstrip('/') or rel.startswith(ex) or ('/' + ex) in ('/' + rel):
                    return True
            elif rel == ex or rel.endswith('/' + ex):
                return True
        return False

    def read(self, rel):
        return _read_bytes(self._path(rel))

    # ---- state --------------------------------------------------
    def _load(self, name, default):
        p = os.path.join(self.state, name)
        if not os.path.isfile(p):
            return default
        try:
            return json.loads(_read_bytes(p).decode('utf-8'))
        except (OSError, ValueError):
            return default

    def _save(self, name, obj):
        _atomic_write(os.path.join(self.state, name), json.dumps(obj, ensure_ascii=False, indent=0).encode('utf-8'))

    # ---- generation stamp ---------------------------------------
    def stamp_for_index(self, texts):
        """Stamp line of the list. texts — {source relative path: content that file will have when saved (str or bytes)}. Deterministic (no time)."""
        parts = []
        for rel in sorted(texts):
            data = texts[rel]
            if isinstance(data, str):
                data = data.encode('utf-8')
            parts.append('%s=%s' % (rel, norm_sha(data)[:16]))
        return STAMP_LINE % ' '.join(parts)

    def records_fingerprint(self, upto=None):
        """(count, highest number, hash16). upto — only up to that number (when S4 checks whether the records present at stamp time are unchanged)."""
        recs = [(n, r) for n, r in self.records() if upto is None or n <= upto]
        h = hashlib.sha256()
        for n, r in recs:
            h.update(('%d:%s;' % (n, norm_sha(self.read(r))[:8])).encode('ascii'))
        return len(recs), (max(n for n, _ in recs) if recs else 0), h.hexdigest()[:16]

    def stamp_for_records(self):
        n, mx, hx = self.records_fingerprint()
        return STAMP_LINE % ('%s/ n=%d max=%d sha=%s' % (self.cfg.records_dir.replace('\\', '/').rstrip('/'), n, mx, hx))

    @staticmethod
    def parse_stamp(text):
        m = STAMP_RE.search(text)
        return m.group(1) if m else None

    # ---- checks -------------------------------------------------
    def check(self, scope='start', target=None):
        """scope — 'start' (all) · 'write' (the cheap ones — S2, S3 generated files, S5 folder, S7) · 'tools' (update_tools — S1 S2 S5)."""
        F = []
        if scope in ('start', 'tools'):
            F += self.s1()
        F += self.s2()
        if scope != 'tools':
            F += self.s3(hand=(scope == 'start'))
        if scope == 'start':
            F += self.s4()
        F += self.s5(folder_of=target if scope == 'write' else None)
        if scope == 'start':
            F += self.s6()
        if scope != 'tools':
            F += self.s7()
        if scope == 'start':
            F += self.s8()
        if scope != 'tools':                      # not before update_tools — that is where a mixed or old format gets migrated
            F += self.s9(info=(scope == 'start'))
        return F

    def s9(self, info=True):
        """Format of the tracker anchors — mixed is an ERROR (Drive catching up, or a tool from an older plugin wrote here),
        still Korean is INFO (not yet migrated; the writing tools of this version refuse it)."""
        try:
            state, per = project_format(self.cfg)
        except OSError:
            return []
        where = '; '.join('%s: %s' % (r, '+'.join(v)) for r, v in sorted(per.items()))
        if state == 'mixed':
            return [Finding('ERROR', 'S9', 'S9:mixed:' + ','.join(sorted(r for r, v in per.items() if len(v) > 1 or v == ['ko'])),
                            'The tracker files mix English and Korean anchors (%s) — Drive may not have caught up, or a tool from an older '
                            'plugin version wrote here. Check Drive and update the plugin on every computer, then run update_tools.py --apply' % where)]
        if state == 'ko' and info:
            return [Finding('INFO', 'S9', 'S9:ko', 'The tracker files use the pre-0.14 Korean anchors — migrate with update_tools.py '
                            '<project> (preview) and --apply after the user agrees')]
        return []

    def latest_change(self):
        best = None
        for r in self.shared_files():
            try:
                m = os.path.getmtime(self._path(r))
            except OSError:
                continue
            if best is None or m > best[0]:
                best = (m, r)
        return best

    def s1(self):
        best = self.latest_change()
        if not best:
            return [Finding('WARN', 'S1', 'S1', 'No shared files found — check the settings (tracker · manuscript.source_dir)')]
        days = (time.time() - best[0]) / 86400.0
        limit = float(self.opt('stale_days', 2))
        if days > limit:
            return [Finding('WARN', 'S1', 'S1', 'The latest change to the shared files was %.1f days ago (%s) — a stale mirror or a break in work. Check that the drive is up to date'
                            % (days, best[1]))]
        return []

    def s2(self):
        recs = self.records()
        if not recs:
            return []
        have = {n for n, _ in recs}
        known = {int(x) for x in (self.opt('known_gaps') or [])}
        prefix = self.t.get('record_prefix', 'E')
        gaps = [n for n in range(1, max(have) + 1) if n not in have and n not in known]
        F = []
        if gaps:
            F.append(Finding('ERROR', 'S2', 'S2:' + ','.join(str(g) for g in gaps[:20]),
                             'Gaps in the completion record numbers: %d — still catching up, or damage' % len(gaps),
                             ['%s%d' % (prefix, g) for g in gaps]))
        seen_max = self.max_record_seen()
        if seen_max and max(have) < seen_max:        # no gap, but the end is cut off — the next number would reuse an existing ID
            F.append(Finding('ERROR', 'S2', 'S2:max:%d<%d' % (max(have), seen_max),
                             'The highest completion record (%s%d) is behind %s%d, which this computer has seen — the latest records have not arrived yet, or were deleted'
                             % (prefix, max(have), prefix, seen_max)))
        return F

    def _ids_in(self, rels):
        ids = set()
        for r in rels:
            if r and self._exists(r):
                ids |= set(ROW_ID_RE.findall(self.read(r).decode('utf-8', errors='replace')))
        return ids

    def _id_universe(self):
        return self._ids_in([self.tracker_rel(k) for k in ('pending', 'archive', 'proposals', 'literature')])

    def known_ids(self):
        """Row IDs in the current files (pending · archive · proposals · literature) plus the IDs this computer has registered as seen — the basis for assigning new numbers (new_pending.py) and for detecting hand-added IDs."""
        return self._id_universe() | set(self._load('ids.json', {}))

    def hand_added_ids(self, rel, text):
        """Among the table rows of text (what is about to be written), **new IDs in a tool-assigned scope that exist nowhere yet** — hand-added rows. The hook refuses on these.
        The scope is `_config.allocation_scope` (file and letter); outside it the result is an empty list. A branch number (`D35-1`) is not new when its stem (`D35`)
        exists. Restoring a deleted row or moving a row uses a known ID and is not caught."""
        rel = nfc(rel.replace('\\', '/'))
        letters = {l for l, r in allocation_scope(self.cfg).items() if r == rel}
        ids = set(ROW_ID_RE.findall(text or '')) if letters else set()
        if not ids:
            return []
        known = self.known_ids()
        out = []
        for i in ids:
            m = re.match(r'[A-Z]+', i)
            if i in known or not m or m.group(0) not in letters:
                continue
            if id_stem(i) != i and id_stem(i) in known:
                continue
            out.append(i)
        return sorted(out, key=id_key)

    def s3(self, hand=True):
        F = []
        recs = dict((n, r) for n, r in self.records())
        prefix = self.t.get('record_prefix', 'E')
        mx = max(recs) if recs else 0
        # generated → source: E rows of record index §2
        ri = self.tracker_rel('record_index')
        if ri and self._exists(ri) and recs:
            text = self.read(ri).decode('utf-8', errors='replace')
            listed = {int(m) for m in re.findall(r'^\|\s*%s(\d+)\s*\|' % re.escape(prefix), text, re.M)}
            missing = sorted(listed - set(recs))
            if missing:
                F.append(Finding('ERROR', 'S3', 'S3:index:' + ','.join(str(m) for m in missing[:20]),
                                 'Record files that the record index points to are missing: %d — the mirror is catching up' % len(missing),
                                 ['%s%d' % (prefix, m) for m in missing]))
        # generated → source: open-item IDs of the list — counts only the ID positions of the generated blocks (table ID cells, focus item headings). Free text
        # such as the notes copied into the focus contains labels from other documents (decision numbers of a plan, IDs of another project); reading those as open-item IDs gives false alarms.
        idx = self.tracker_rel('index')
        if idx and self._exists(idx):
            text = self.read(idx).decode('utf-8', errors='replace')
            by_block, unknown = list_block_ids(text)
            refs = {i for ids in by_block.values() for i in ids}
            if refs:
                missing = sorted(refs - self._id_universe(), key=id_key)
                if missing:
                    F.append(Finding('ERROR', 'S3', 'S3:list:' + ','.join(missing[:20]),
                                     'Open items that the list points to but that are in none of the pending, archive and proposals files: %d' % len(missing), missing))
            if unknown:
                F.append(Finding('WARN', 'S3', 'S3:list:format:' + ','.join(unknown),
                                 '%s: could not read the ID positions in the generated blocks (%s), so the open-item ID comparison is skipped — an old version or a hand edit. '
                                 'Regenerate them with the tidy tool `--apply`' % (idx, ' · '.join(unknown))))
        # hand-edited files → references above the highest E (skipping those inside paths or preceded by `../`)
        if hand and recs:
            for key in ('pending', 'checkpoint'):
                r = self.tracker_rel(key)
                if not r or not self._exists(r):
                    continue
                text = self.read(r).decode('utf-8', errors='replace')
                big = set()
                for m in E_REF_RE.finditer(text):
                    n = int(m.group(1))
                    if n <= mx or n > mx + 500:
                        continue
                    if '../' in text[max(0, m.start() - 80):m.start()]:
                        continue
                    big.add(n)
                if big:
                    F.append(Finding('WARN', 'S3', 'S3:%s' % r, '%s points to records that do not exist yet (highest %s%d) — record files may not have arrived yet'
                                     % (r, prefix, mx), ['%s%d' % (prefix, n) for n in sorted(big)]))
        return F

    # ---- S4 — when the stamp differs, "which side is later" -----------
    S4_ORDER = ('forward', 'revert', 'suspect', 'regress')
    S4_LEVEL = {'forward': 'INFO', 'revert': 'WARN', 'suspect': 'WARN', 'regress': 'ERROR'}

    def _history_keys(self, rel, wanted):
        """Order keys of the snapshots of rel (local + drive) at which the versions in wanted (set of normalized hash16) **first appear** — {hash16: key} (the time that version was written).
        Matches by the hash8 in the name first (a version with LF line endings has the same normalized hash), then reads the content, newest first, only for those not found."""
        snaps = self.snapshots_of(rel)
        found = {}
        for s in snaps:
            for h in wanted:
                if h not in found and s[3] == h[:8]:
                    found[h] = self._snap_key(s)
        rest = set(wanted) - set(found)
        for s in reversed(snaps):
            if not rest:
                break
            try:
                h = norm_sha(_read_bytes(s[5]))[:16]
            except OSError:
                continue
            if h in rest:
                found[h] = self._snap_key(s)
                rest.discard(h)
        return found

    def _stamp_direction(self, gen_rel, src_rel, h_stamp, h_cur):
        """The generated file gen_rel was made from version h_stamp of the source src_rel, but the source is now version h_cur — which side is later?
        The order comes from this computer's snapshot record; if that is not enough, from the mtimes of the source and the generated file (kept by the sync service).
        Returns (kind, description). forward — the source changed later (just regenerate) · regress — the source went back to an old version and its mtime is earlier too (overwrite)
        · revert — old content but a later mtime (reverted, or overwritten) · suspect — content differs although nothing was edited after the stamp (an old version overwrote it, or only the generated file arrived first)."""
        hist = self._history_keys(src_rel, {h_stamp, h_cur})
        try:
            src_newer = os.path.getmtime(self._path(src_rel)) > os.path.getmtime(self._path(gen_rel))
        except OSError:
            src_newer = True

        def when(k):
            try:
                return parse_utc(k[0]).astimezone().strftime('%m-%d %H:%M')
            except ValueError:
                return k[0]
        ts, tc = hist.get(h_stamp), hist.get(h_cur)
        if ts and tc:
            if tc > ts:
                return 'forward', '%s edited %s' % (src_rel, when(tc))
            kind = 'revert' if src_newer else 'regress'
            return kind, '%s went back to the old version this computer saw at %s (the generated file is from the %s version)' % (src_rel, when(tc), when(ts))
        if src_newer:
            return 'forward', '%s edited later%s' % (src_rel, '' if tc else ' (a version this computer does not know)')
        return 'suspect', '%s has not changed since generation but its content differs%s' % (src_rel, '' if ts else ' · this computer does not know the version the generated file came from')

    def s4(self):
        F = []
        idx = self.tracker_rel('index')
        if idx and self._exists(idx):
            text = self.read(idx).decode('utf-8', errors='replace')
            st = self.parse_stamp(text)
            if st is None:
                F.append(Finding('INFO', 'S4', 'S4:index:none', '%s has no generation stamp (an old generated file) — running the tidy tool once adds it' % idx))
            else:
                stamped = dict(re.findall(r'(\S+)=([0-9a-f]{16})', st))
                kinds, notes = [], []
                for k in ('pending', 'proposals', 'literature'):
                    r = self.tracker_rel(k)
                    if not (r and self._exists(r)):
                        continue
                    cur = norm_sha(self.read(r))[:16]
                    old = stamped.get(r)
                    if old == cur:
                        continue
                    if old is None:                       # a source file that did not exist at generation — just regenerate
                        kinds.append('forward'); notes.append('%s appeared after generation' % r)
                        continue
                    kind, note = self._stamp_direction(idx, r, old, cur)
                    kinds.append(kind); notes.append(note)
                if kinds:
                    worst = max(kinds, key=self.S4_ORDER.index)
                    detail = ' · '.join(notes)
                    if worst == 'forward':
                        msg = '%s is older than its sources (%s) — regenerate it with `tidy_tracker.py --apply` at the end of the session. Not a sync problem' % (idx, detail)
                    elif worst == 'revert':
                        msg = '%s — fine if it was reverted on purpose, otherwise a suspected overwrite. Check before regenerating with the tidy tool' % detail
                    elif worst == 'suspect':
                        msg = '%s was made from a version other than the current source — %s. An old version overwrote a new one, or only the generated file arrived first. Check the drive' % (idx, detail)
                    else:
                        msg = '%s — overwrite. Revert with `--restore <file>`, or `--ack` after checking' % detail
                    F.append(Finding(self.S4_LEVEL[worst], 'S4', 'S4:index:' + {'forward': 'stale'}.get(worst, worst), msg))
        ri = self.tracker_rel('record_index')
        recs = self.records()
        if ri and self._exists(ri) and recs:
            text = self.read(ri).decode('utf-8', errors='replace')
            st = self.parse_stamp(text)
            prefix = self.t.get('record_prefix', 'E')
            if st is None:
                F.append(Finding('INFO', 'S4', 'S4:records:none', '%s has no generation stamp (an old generated file) — running the index tool once adds it' % ri))
            elif self.parse_stamp(self.stamp_for_records()) != st:          # compare contents — the stamp word may be either spelling
                n, mx, hx = self.records_fingerprint()
                m = re.search(r'n=(\d+) max=(\d+) sha=([0-9a-f]{16})', st)
                if not m:
                    F.append(Finding('WARN', 'S4', 'S4:records', 'Cannot read the stamp format of %s — regenerate it with the index tool' % ri))
                else:
                    n0, mx0, hx0 = int(m.group(1)), int(m.group(2)), m.group(3)
                    if n < n0 or mx < mx0:
                        F.append(Finding('WARN', 'S4', 'S4:records:shrunk',
                                         'Completion records shrank from %d (highest %s%d) when the index was made to %d (highest %s%d) — not arrived yet, or deleted'
                                         % (n0, prefix, mx0, n, prefix, mx)))
                    elif self.records_fingerprint(upto=mx0)[2] == hx0:
                        new = ['%s%d' % (prefix, k) for k, _ in recs if k > mx0]
                        F.append(Finding('INFO', 'S4', 'S4:records:stale',
                                         '%s is older than the records folder (new records %s) — regenerate it with `index_records.py`. Not a sync problem'
                                         % (ri, ' '.join(new[:8]) + (' …' if len(new) > 8 else ''))))
                    else:
                        F.append(Finding('WARN', 'S4', 'S4:records:changed',
                                         'Some records that existed when the index was made (up to %s%d) have changed — confirmed records are never edited; check for an overwrite'
                                         % (prefix, mx0)))
        return F

    def _conflict_patterns(self):
        pats = self.opt('conflict_patterns') or [r' \d+$', r' \(\d+\)$', r'conflicted copy']
        return [re.compile(p) for p in pats]

    def s5(self, folder_of=None):
        pats = self._conflict_patterns()
        hits = []
        if folder_of:
            d = os.path.dirname(self._path(folder_of))
            walk = [(d, [], os.listdir(d) if os.path.isdir(d) else [])]
        else:
            walk = os.walk(self.root)
        for dp, dns, fns in walk:
            if not folder_of:
                dns[:] = [x for x in dns if not self._excluded(_rel(self.root, os.path.join(dp, x)) + '/')]
            for f in fns:
                stem, ext = os.path.splitext(f)
                for p in pats:
                    m = p.search(stem)
                    if not m:
                        continue
                    base = stem[:m.start()] + ext
                    base_path = os.path.join(dp, base)
                    if 'conflicted' not in p.pattern and not os.path.isfile(base_path):
                        continue
                    rel = _rel(self.root, os.path.join(dp, f))
                    same = ''
                    if os.path.isfile(base_path):
                        try:
                            same = '(identical bytes)' if _read_bytes(base_path) == _read_bytes(os.path.join(dp, f)) else '(differs)'
                        except OSError:
                            same = ''
                    hits.append((rel + same).strip())
                    break
        if hits:
            return [Finding('WARN', 'S5', 'S5:' + ';'.join(sorted(hits))[:200], 'Sync conflict copies: %d — check which side is right, then delete them' % len(hits), sorted(hits))]
        return []

    def s6(self, verbose=False):
        reg = self._load('written.json', {})
        if not reg:
            return []
        skip = self.generated_files() | self.rewrite_ok()
        union = set()
        for r in self.shared_files():
            if r in skip:
                continue
            union |= set(_line_table(self.read(r)))
        pct = float(self.opt('survival_pct', 70))
        F = []
        for r, lines in sorted(reg.items()):
            if r in skip or not lines or (len(lines) < 5 and not verbose):
                continue
            # entries registered before anchors were left out are skipped by their preview — the format migration rewrites those lines
            lost = [h for h in lines if h not in union and not (isinstance(lines[h], list) and is_anchor_line(lines[h][1]))]
            surv = 100.0 * (len(lines) - len(lost)) / len(lines)
            # normally (start check) warn only below the threshold; --damage (verbose) shows everything once any line is gone
            if (surv < pct) or (verbose and lost):
                previews = [lines[h][1] if isinstance(lines[h], list) else '' for h in lost]
                gone = '' if self._exists(r) else ' · the file itself is missing'
                F.append(Finding('WARN', 'S6', 'S6:%s' % r,
                                 '%s — of %d lines this computer wrote, %d exist nowhere (survival %.0f %%)%s' % (r, len(lines), len(lost), surv, gone),
                                 previews if verbose else previews[:3]))
        return F

    def s7(self):
        seen = self._load('ids.json', {})
        if not seen:
            return []
        cur = self._id_universe()
        lost = sorted((i for i in seen if i not in cur), key=id_key)
        if lost:
            return [Finding('ERROR', 'S7', 'S7:' + ','.join(lost[:30]),
                            'Item IDs this computer saw that are in none of the pending, archive, proposals and literature files: %d — suspected overwrite' % len(lost), lost)]
        return []

    def s8(self):
        try:
            if sys.platform.startswith('win'):
                out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq GoogleDriveFS.exe'], capture_output=True, timeout=5).stdout
                running = b'GoogleDriveFS' in out
            elif sys.platform == 'darwin':
                running = subprocess.run(['pgrep', '-f', 'Google Drive'], capture_output=True, timeout=5).returncode == 0
            else:
                return []
        except (OSError, subprocess.SubprocessError):
            return []
        low = self.root.replace('\\', '/').lower()
        drive_like = 'googledrive' in low or 'cloudstorage' in low or 'google drive' in low or re.match(r'^[g-z]:/', low) is not None
        if running:
            return [Finding('INFO', 'S8', 'S8', 'Google Drive process running')]
        return [Finding('WARN' if drive_like else 'INFO', 'S8', 'S8', 'No Google Drive process found — sync may be stopped')]

    # ---- snapshots ----------------------------------------------
    @staticmethod
    def _snap_name(rel, comp, digest, when=None):
        stem, ext = os.path.splitext(nfc(rel.replace('\\', '/')))
        return '%s_%s_%s_%s%s' % (utc_stamp(when), nfc(comp), stem.replace('/', '__'), digest[:8], ext)

    @staticmethod
    def _snap_key(s):
        """When the UTC (seconds) in the names is equal, the files' mtimes decide the order — two versions can appear within the same second."""
        try:
            return (s[0], os.stat(s[5]).st_mtime_ns)
        except OSError:
            return (s[0], 0)

    @classmethod
    def _list_snaps(cls, folder):
        """[(utc, computer, path stem, hash8, extension, file path)] — oldest first"""
        out = []
        if not os.path.isdir(folder):
            return out
        for f in os.listdir(folder):
            m = SNAP_RE.match(f)
            if m:                                    # computer and path stem in NFC — so NFD names from a macOS mirror group with the same file
                out.append((m.group(1), nfc(m.group(2)), nfc(m.group(3)), m.group(4), m.group(5) or '', os.path.join(folder, f)))
        return sorted(out, key=cls._snap_key)

    def snapshot(self, rel, drive=False, flush=True):
        """Keeps the current version locally (always) and on the drive (drive=True). Not made again if the same hash exists. Returns the paths made.
        Records the hash of the version just seen as "the version this computer saw last" (seen.json) — the baseline for the post-write difference."""
        rel = nfc(rel.replace('\\', '/'))
        try:
            data = self.read(rel)
        except OSError:
            return []
        digest = sha(data)
        self._mark_seen(rel, digest, flush=flush)
        stem = os.path.splitext(rel)[0].replace('/', '__')
        made = []
        for folder in ([self.local_snap_dir] + ([self.snapshot_dir] if drive else [])):
            have = any(s[2] == stem and s[3] == digest[:8] for s in self._list_snaps(folder))
            if have:
                continue
            if not os.path.isdir(folder):
                os.makedirs(folder)
            p = os.path.join(folder, self._snap_name(rel, self.me, digest))
            try:
                fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                continue
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
            made.append(p)
        return made

    def snapshots_of(self, rel):
        stem = os.path.splitext(nfc(rel.replace('\\', '/')))[0].replace('/', '__')
        out = [s for folder in (self.local_snap_dir, self.snapshot_dir) for s in self._list_snaps(folder) if s[2] == stem]
        return sorted(out, key=self._snap_key)

    def latest_snapshot_bytes(self, rel, exclude_digest=None):
        """Latest snapshot by time — it does not distinguish computers, so **do not use it as the pre-write baseline** (an old version from another computer may have a later timestamp)."""
        for s in reversed(self.snapshots_of(rel)):
            if exclude_digest and s[3] == exclude_digest[:8]:
                continue
            try:
                return _read_bytes(s[5])
            except OSError:
                continue
        return None

    # ---- the version this computer saw last ---------------------
    def _seen(self):
        if getattr(self, '_seen_cache', None) is None:
            self._seen_cache = self._load('seen.json', {})
            self._seen_dirty = False
        return self._seen_cache

    def _mark_seen(self, rel, digest, flush=True):
        seen = self._seen()
        if seen.get(rel) != digest:
            seen[rel] = digest
            self._seen_dirty = True
        if flush:
            self._flush_seen()

    def _flush_seen(self):
        if getattr(self, '_seen_dirty', False):
            self._save('seen.json', self._seen())
            self._seen_dirty = False

    def _snapshot_bytes_by_digest(self, rel, digest):
        """Content of the snapshot with that hash — the content is the same whichever computer made it, so it is found by the hash8 in the name and confirmed by the full hash."""
        for s in reversed(self.snapshots_of(rel)):
            if s[3] != digest[:8]:
                continue
            try:
                data = _read_bytes(s[5])
            except OSError:
                continue
            if sha(data) == digest:
                return data
        return None

    def _pre_bytes(self, rel, post_digest):
        """The "pre-write version" right after a write — ① the snapshot of the version this computer saw last (recorded by before_write, session boundaries and the previous after_write);
        ② if that is unknown, the most recent snapshot **made by this computer**. Another computer's snapshot is never chosen by time alone —
        if an old version from another computer has a later timestamp, deleted lines stay registered and S6 raises false alarms. None if unknown (a file written for the first time)."""
        seen = self._seen().get(rel)
        if seen and seen != post_digest:
            data = self._snapshot_bytes_by_digest(rel, seen)
            if data is not None:
                return data
        # The previous version is unknown, or the pre-write hook already saw the changed content (seen == current) — this computer's latest snapshot that is not the current version.
        # Comparing lines that are already registered again gives the same result (deleted lines are gone and added lines are already there).
        for s in reversed(self.snapshots_of(rel)):
            if s[1] == nfc(self.me) and s[3] != post_digest[:8]:
                try:
                    return _read_bytes(s[5])
                except OSError:
                    continue
        return None

    def snapshot_all(self, drive):
        made = []
        for r in self.shared_files():
            made += self.snapshot(r, drive=drive, flush=False)
        self._flush_seen()
        return made

    @staticmethod
    def _rm(path):
        try:
            os.remove(path)
            return True
        except OSError:
            return False

    def prune(self):
        """Snapshot retention — per file (path stem) the latest `snapshot_min` are always kept; of the rest,
        ① this computer's snapshots older than `snapshot_days` (twice that locally) or beyond `snapshot_max` (local `snapshot_max_local`) are deleted oldest first,
        ② other computers' snapshots older than `snapshot_days_others` are deleted. Nothing is deleted while an unconfirmed ERROR is open. Runs at session start and end."""
        if self.unacked():
            return 0
        keep = int(self.opt('snapshot_min', 10))
        days = float(self.opt('snapshot_days', 30))
        others = float(self.opt('snapshot_days_others', 90))
        now = utc_now()
        removed = 0
        for folder, factor, cap in ((self.local_snap_dir, 2.0, int(self.opt('snapshot_max_local', 100))),
                                    (self.snapshot_dir, 1.0, int(self.opt('snapshot_max', 20)))):
            by_stem = {}
            for s in self._list_snaps(folder):
                by_stem.setdefault(s[2], []).append(s)
            for stem, lst in by_stem.items():
                lst.sort(key=self._snap_key)
                old = lst[:-keep] if len(lst) > keep else []          # the latest keep are left untouched
                over = max(0, sum(1 for s in lst if s[1] == self.me) - cap)
                for s in old:                                          # oldest first
                    try:
                        age = now - parse_utc(s[0])
                    except ValueError:
                        continue
                    if s[1] == self.me:
                        if age > datetime.timedelta(days=days * factor) or over > 0:
                            if self._rm(s[5]):
                                removed += 1
                                over = max(0, over - 1)
                    elif age > datetime.timedelta(days=others):
                        if self._rm(s[5]):
                            removed += 1
        seen_dir = os.path.join(self.state, 'hook_seen')
        if os.path.isdir(seen_dir):
            files = sorted(os.listdir(seen_dir), key=lambda f: os.path.getmtime(os.path.join(seen_dir, f)))
            for f in files[:-300]:
                try:
                    os.remove(os.path.join(seen_dir, f))
                except OSError:
                    pass
        return removed

    def restore(self, rel, at=None, digest=None):
        """Reverts to a snapshot. at — the latest at or before 'YYYY-MM-DD HH:MM' (local time); digest — first 8 characters of the hash. The current version is kept before reverting."""
        rel = nfc(rel.replace('\\', '/'))
        snaps = self.snapshots_of(rel)
        if not snaps:
            raise SystemExit('No snapshots: %s' % rel)
        pick = None
        if digest:
            for s in snaps:
                if s[3] == digest[:8]:
                    pick = s
        elif at:
            try:
                local = datetime.datetime.strptime(at, '%Y-%m-%d %H:%M')
            except ValueError:
                local = datetime.datetime.strptime(at, '%Y-%m-%d')
            lim = utc_stamp(local.astimezone(datetime.timezone.utc))
            for s in snaps:
                if s[0] <= lim:
                    pick = s
        else:
            pick = snaps[-1]
        if pick is None:
            raise SystemExit('No snapshot matches: %s (%d exist)' % (rel, len(snaps)))
        self.snapshot(rel, drive=True)
        data = _read_bytes(pick[5])
        _atomic_write(self._path(rel), data)
        self.after_write(rel)
        return pick

    # ---- fingerprints · written lines · ID registry -------------
    def _fingerprint(self, rel):
        st = os.stat(self._path(rel))
        return [st.st_mtime_ns, st.st_size]

    def refresh_fingerprints(self):
        fp = {}
        for r in self.shared_files():
            try:
                fp[r] = self._fingerprint(r)
            except OSError:
                pass
        self._save('fingerprints.json', fp)
        return fp

    def changed_since_fingerprints(self):
        old = self._load('fingerprints.json', {})
        changed = []
        for r in self.shared_files():
            try:
                cur = self._fingerprint(r)
            except OSError:
                continue
            if old.get(r) != cur:
                changed.append(r)
        return changed

    def before_write(self, rel):
        """Right before a write — keeps the current version locally for the later difference."""
        if self.is_shared(rel):
            self.snapshot(rel)

    def after_write(self, rel):
        """Right after a write — local snapshot · fingerprint · update of "lines this computer wrote" (deleted lines leave the registry, added lines join it)."""
        rel = nfc(rel.replace('\\', '/'))
        if not self.is_shared(rel):
            return
        try:
            post = self.read(rel)
        except OSError:
            return
        pre = self._pre_bytes(rel, sha(post))      # the version this computer saw right before writing — not the latest snapshot by time
        self.snapshot(rel)                          # keep the current version and make it "the version seen last"
        if rel not in (self.generated_files() | self.rewrite_ok()):
            reg = self._load('written.json', {})
            mine = reg.get(rel, {})
            pre_t = _line_table(pre) if pre is not None else {}
            post_t = _line_table(post)
            now = utc_stamp()
            for h in set(pre_t) - set(post_t):
                mine.pop(h, None)
            for h in set(post_t) - set(pre_t):
                mine[h] = [now, post_t[h]]
            if len(mine) > MAX_LINES_PER_FILE:
                for h in sorted(mine, key=lambda k: mine[k][0])[:len(mine) - MAX_LINES_PER_FILE]:
                    mine.pop(h, None)
            reg[rel] = mine
            self._save('written.json', reg)
        fp = self._load('fingerprints.json', {})
        try:
            fp[rel] = self._fingerprint(rel)
        except OSError:
            fp.pop(rel, None)
        self._save('fingerprints.json', fp)

    def after_bash(self):
        """After shell tools (Bash · PowerShell) — after_write only for the shared files whose fingerprint changed. The command is not parsed."""
        changed = self.changed_since_fingerprints()
        for r in changed:
            self.after_write(r)
        return changed

    def table_report(self, rels):
        """After a write — table defects left in tracker files (list · pending · archive · proposals · literature) as [(rel, description)]. The hook uses it to report in that turn."""
        tracked = {self.tracker_rel(k) for k in ('index', 'pending', 'archive', 'proposals', 'literature')}
        out = []
        for rel in rels:
            rel = nfc(rel.replace('\\', '/'))
            if rel in tracked and self._exists(rel):
                for prob in table_problems(self.read(rel).decode('utf-8', errors='replace')):
                    out.append((rel, describe_table_problem(prob)))
        return out

    def remember_ids(self):
        seen = self._load('ids.json', {})
        now = utc_stamp()
        for i in self._id_universe():
            seen.setdefault(i, now)
        self._save('ids.json', seen)

    def max_record_seen(self):
        return int(self._load('records_max.json', {}).get('max', 0))

    def remember_records(self):
        """Highest number this computer saw — it only grows (S2 catches it shrinking)."""
        recs = self.records()
        if recs and max(n for n, _ in recs) >= self.max_record_seen():
            self._save('records_max.json', {'max': max(n for n, _ in recs), 'utc': utc_stamp()})

    def remember_records_reset(self):
        """After the user's confirmation — accepts the folder's current highest number as is."""
        recs = self.records()
        self._save('records_max.json', {'max': max(n for n, _ in recs) if recs else 0, 'utc': utc_stamp()})

    # ---- alert state · confirmation ------------------------------
    def _alerts(self):
        return self._load('alerts.json', {'findings': [], 'acked': {}})

    def record_alerts(self, findings):
        a = self._alerts()
        errs = [f.as_dict() for f in findings if f.level == 'ERROR']
        a['findings'] = errs
        a['utc'] = utc_stamp()
        self._save('alerts.json', a)

    def drop_alerts(self, code):
        """Removes the recorded findings of one check — only for the tool that has just removed that condition (the format migration and S9).
        Every other recorded ERROR stays; the next check records the condition again if it is still there."""
        a = self._alerts()
        a['findings'] = [d for d in a.get('findings', []) if d.get('code') != code]
        self._save('alerts.json', a)

    def ack_of(self, key, alerts=None):
        """Valid confirmation record of key ({'utc', 'text'}) — the record if it is within `ack_hours`, otherwise None. Whether a confirmation is valid is decided here only."""
        a = alerts if alerts is not None else self._alerts()
        ack = a.get('acked', {}).get(key)
        if not ack:
            return None
        try:
            if utc_now() - parse_utc(ack['utc']) < datetime.timedelta(hours=float(self.opt('ack_hours', 4))):
                return ack
        except (KeyError, ValueError):
            pass
        return None

    def unacked(self):
        """List of unconfirmed ERRORs (Finding)."""
        a = self._alerts()
        return [Finding.from_dict(d) for d in a.get('findings', []) if self.ack_of(d['key'], a) is None]

    def blocking(self, target=None):
        """ERRORs that block writes — the unconfirmed ones among those recorded; if there are none, runs the cheap checks (write) afresh, records them and returns the unconfirmed ones.
        A confirmation is valid per key (check code + target number or ID) for `ack_hours` — the same condition left in generated files or folders does not block again
        (blocking the tidy tool that would clear it would deadlock), while a different condition (a different key) blocks. The guard, batch tools and session end use this."""
        open_ = self.unacked()
        if open_:
            return open_
        fresh = [f for f in self.check('write', target=target) if f.level == 'ERROR']
        if not fresh:
            return []
        self.record_alerts(fresh)
        return self.unacked()

    def ack(self, text):
        """Records the user's confirmation — for all ERRORs open now. Vanished IDs and lines are accepted as legitimate deletions and removed from the registry (_rebaseline).
        This is the only way to close an ERROR, so it never runs without the user's words. To accept WARNs only, use accept_warn()."""
        a = self._alerts()
        now = utc_stamp()
        n = 0
        for d in a.get('findings', []):
            a.setdefault('acked', {})[d['key']] = {'utc': now, 'text': text}
            n += 1
        self._save('alerts.json', a)
        self._rebaseline(now, text, [d['key'] for d in a.get('findings', [])])
        return n

    def accept_warn(self):
        """Accept WARNs — only when there is no unconfirmed ERROR, aligns the baselines (S6 written-line registry · S4 seen records · S7 seen IDs) with the current state.
        ERRORs are not touched. With an open ERROR it returns None and changes nothing (only ack closes it)."""
        if self.blocking():
            return None
        self._rebaseline(utc_stamp(), 'WARN accepted', [])
        return True

    def _rebaseline(self, now, text, keys):
        """Accepts vanished IDs and lines as legitimate deletions and removes them from the registry, resets the seen-records baseline and logs to ack_log. Shared by ack and accept_warn."""
        cur = self._id_universe()
        seen = self._load('ids.json', {})
        for i in [i for i in seen if i not in cur]:
            seen.pop(i, None)
        self._save('ids.json', seen)
        self.remember_records_reset()
        reg = self._load('written.json', {})
        skip = self.generated_files() | self.rewrite_ok()
        union = set()
        for r in self.shared_files():
            if r not in skip:
                union |= set(_line_table(self.read(r)))
        for r in list(reg):
            reg[r] = {h: v for h, v in reg[r].items() if h in union}
        self._save('written.json', reg)
        log = self._load('ack_log.json', [])
        log.append({'utc': now, 'text': text, 'computer': self.me, 'keys': keys})
        self._save('ack_log.json', log[-200:])

    def guard(self, tool, rel=None):
        """Decision right before a write — a reason to block, or None. Decided by blocking() — a confirmed key does not block again for ack_hours."""
        rel = nfc(rel.replace('\\', '/')) if rel else rel
        open_ = self.blocking(target=rel)
        if not open_:
            return None
        lines = ['The sync check has unconfirmed ERRORs, so writes to shared files are blocked (%s%s).' % (tool, (' → ' + rel) if rel else '')]
        lines += ['  ! ' + f.line() for f in open_]
        lines.append('  Show the user the warnings above and get their confirmation, then run `<py> -X utf8 %s --ack "<what the user said>"`. ' % self.cfg.tool('check_sync.py') +
                     'Revert an overwritten file with `--restore <file>`.')
        return '\n'.join(lines)

    # ---- session boundaries ---------------------------------------
    def status_line(self, findings):
        recs = self.records()
        prefix = self.t.get('record_prefix', 'E')
        mx = ('%s%d' % (prefix, max(n for n, _ in recs))) if recs else 'no records'
        best = self.latest_change()
        when = datetime.datetime.fromtimestamp(best[0]).strftime('%Y-%m-%d %H:%M') if best else '—'
        days = ((time.time() - best[0]) / 86400.0) if best else 0
        last = self.last_drive_snapshot()
        last_s = ('%s %s' % (last[1], parse_utc(last[0]).astimezone().strftime('%m-%d %H:%M'))) if last else 'none'
        a = self._alerts()
        errs = [f for f in findings if f.level == 'ERROR']
        if any(self.ack_of(f.key, a) is None for f in errs):
            worst = 'ERROR'
        elif errs:
            worst = 'ERROR (confirmed)'
        else:
            worst = 'WARN' if any(f.level == 'WARN' for f in findings) else 'OK'
        return 'Sync %s · %s · last change %s (%.1f days ago) · last drive snapshot %s · this computer %s' % (worst, mx, when, days, last_s, self.me)

    def last_drive_snapshot(self):
        snaps = self._list_snaps(self.snapshot_dir)
        return snaps[-1] if snaps else None

    def session_start(self, snapshot=True):
        findings = self.check('start')
        self.record_alerts(findings)
        if not self.unacked():                # with only confirmed ERRORs left, accept the current state as the baseline (ack has already aligned the registry)
            self.remember_ids()
            self.remember_records()
        if snapshot:
            self.snapshot_all(drive=True)
            self.refresh_fingerprints()
            self.prune()                      # pruning only at session end lets snapshots pile up across sessions that never run the tidy tool
        return findings

    def session_end(self):
        self.snapshot_all(drive=True)
        self.refresh_fingerprints()
        findings = [f for f in self.check('write') if f.level == 'ERROR']
        if findings:
            self.record_alerts(findings)
            findings = self.unacked()         # confirmed keys are not reported again as "ERROR left" — same decision as blocking()
        if not findings:
            self.remember_ids()
            self.remember_records()
        removed = self.prune()
        return findings, removed

    # ---- write lock ----------------------------------------------
    def write_lock(self, tool='', wait=None):
        """Lock held only while shared files are read and rewritten (WriteLock) — `with sync.write_lock('tool name') as lock:` · lock.busy if it could not be taken."""
        return WriteLock(os.path.join(self.state, LOCK_NAME), tool, _lock_wait(LOCK_WAIT_TOOL) if wait is None else wait)

    def wait_write_lock(self, wait=None):
        """Right before a write (hook) — waits until the lock is free. True if it is free, False if it is still held after wait seconds.
        Does not block — the caller lets the write through either way; the tool's pre-save check covers that gap."""
        lock = self.write_lock(None, _lock_wait(LOCK_WAIT_HOOK) if wait is None else wait).acquire()
        free = not lock.busy
        lock.release()
        return free

    def hook_seen(self, marker):
        """Keeps the two hooks (installed copy and project copy) from handling the same tool call twice — returns False on first sight and marks it."""
        d = os.path.join(self.state, 'hook_seen')
        if not os.path.isdir(d):
            os.makedirs(d)
        p = os.path.join(d, re.sub(r'[^0-9A-Za-z_-]+', '-', marker)[:120])
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return True
        os.close(fd)
        return False


# ---------------------------------------------------------------- write lock
LOCK_NAME = 'write.lock'
LOCK_WAIT_TOOL = 10.0     # seconds a tool waits for the lock — one tool run takes about a second
LOCK_WAIT_HOOK = 6.0      # seconds the hook waits — must be shorter than the hook timeout
LOCK_POLL = 0.05
_LOCKS_HELD = {}          # locks held by this process {path: [file, count]} — taking it again in the same process only raises the count


def _lock_wait(default):
    """Wait time (seconds) — tests shorten it via `SYNC_LOCK_WAIT` (used like `SYNC_STATE_HOME`)."""
    try:
        return float(os.environ['SYNC_LOCK_WAIT'])
    except (KeyError, ValueError):
        return default


def _os_lock(f):
    """Takes an operating-system lock on file f (no waiting). BlockingIOError if another process holds it."""
    try:
        if os.name == 'nt':
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        if isinstance(e, BlockingIOError) or e.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            raise BlockingIOError(e.errno or errno.EAGAIN, 'another process holds the lock')
        raise


def _os_unlock(f):
    if os.name == 'nt':
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


class WriteLock(object):
    """Lock held **only while shared files are read and rewritten** — one per project and computer (`<state folder>/write.lock`, outside the sync folder).
    It is an operating-system lock, so it is released by itself when the holding process dies — no stale locks, and nobody needs to release one. It is not held per session.

        with sync.write_lock('tidy_tracker') as lock:
            if lock.busy:                  # not taken within wait seconds — do not write; report lock.busy_message()
                ...
            (read → compute → check whether anything changed since reading → save)

    state — 'held' taken · 'busy' another process holds it and it was not taken within wait seconds · 'off' the lock mechanism itself failed (cannot write the
    state folder, or the file system does not support locks) — proceeds without a lock rather than blocking. In every case the tool's pre-save check is the floor.
    The same process may take it again (it only counts). **While holding the lock, do not call another lock-taking tool as a child process** — they wait for each other.
    Not covered — Edit and Write themselves (the hook finishes before the Edit, so it cannot hold the lock; it only waits for a release just before) · manual edits in an editor ·
    apps without hooks · other computers · old tool versions that do not know the lock."""

    def __init__(self, path, tool='', wait=LOCK_WAIT_TOOL):
        self.path = path
        self.tool = tool              # None leaves no holder info (the hook's wait)
        self.wait = wait
        self.state = None
        self._key = os.path.normcase(os.path.abspath(path))

    @property
    def held(self):
        return self.state == 'held'

    @property
    def busy(self):
        return self.state == 'busy'

    def _off(self, e):
        self.state = 'off'
        sys.stderr.write('Write lock unavailable; proceeding without it (the pre-save check still applies): %r\n' % (e,))
        return self

    def acquire(self):
        ent = _LOCKS_HELD.get(self._key)
        if ent:                       # this process already holds it
            ent[1] += 1
            self.state = 'held'
            return self
        try:
            d = os.path.dirname(self.path)
            if d and not os.path.isdir(d):
                os.makedirs(d)
            f = io.open(self.path, 'a+b')
        except OSError as e:
            return self._off(e)
        deadline = time.monotonic() + max(0.0, self.wait or 0.0)
        while True:
            try:
                _os_lock(f)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    f.close()
                    self.state = 'busy'
                    return self
                time.sleep(LOCK_POLL)
            except Exception as e:    # e.g. a file system without lock support — a fault in the mechanism must not block writes
                f.close()
                return self._off(e)
        _LOCKS_HELD[self._key] = [f, 1]
        self.state = 'held'
        if self.tool:
            try:
                _atomic_write(self.path + '.info', json.dumps(
                    {'tool': self.tool, 'pid': os.getpid(), 'utc': utc_stamp()}, ensure_ascii=False).encode('utf-8'))
            except OSError:
                pass
        return self

    def release(self):
        if self.state != 'held':
            self.state = None
            return
        self.state = None
        ent = _LOCKS_HELD.get(self._key)
        if not ent:
            return
        ent[1] -= 1
        if ent[1] > 0:
            return
        del _LOCKS_HELD[self._key]
        for step in (_os_unlock, lambda f: f.close()):
            try:
                step(ent[0])
            except Exception:
                pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
        return False

    def who(self):
        """One-line description of the holder (for the busy notice). Empty string if unknown."""
        try:
            d = json.loads(_read_bytes(self.path + '.info').decode('utf-8'))
            return '%s (PID %s · since %s)' % (d.get('tool') or '?', d.get('pid'), d.get('utc'))
        except Exception:
            return ''

    def busy_message(self):
        w = self.who()
        return ('Another tool is writing the shared files, so the lock was not taken within %gs%s — nothing was written. Run again.'
                % (self.wait, (' · held by: ' + w) if w else ''))


# ---------------------------------------------------------------- replace-once helper
def replace_once(path, old, new, encoding='utf-8', check_tables=True):
    """Replaces `old` with `new` only when `old` occurs **exactly once** in the file. Keeps the line endings (CRLF/LF), and inside a project also takes the
    before/after snapshots, fingerprint and "written lines" record. Zero or several occurrences raise ValueError — this is the optimistic concurrency check (the text seen earlier must still be there).
    In `.md` files, a replacement that **adds** table defects (split rows · cell count · trailing `|` — _config.table_problems) is not written and raises ValueError.
    Defects that were already there only give a stderr warning. For a deliberate replacement pass check_tables=False. Returns {'path', 'crlf', 'delta', 'count'}.
    Inside a project the write lock (WriteLock) is held from read to write. If it cannot be taken, the replacement still happens — the once-check covers it."""
    path = os.path.abspath(path)
    root = find_project_root(path)
    lock = None
    if root:
        try:
            lock = Sync(_load_cfg(root)).write_lock('replace_once').acquire()
            if lock.busy:
                sys.stderr.write('replace_once: ' + lock.busy_message().replace('nothing was written. Run again.', 'replacing without the lock.') + '\n')
        except Exception:        # a fault in the guard must not block the replacement itself
            lock = None
    try:
        return _replace_once(path, old, new, encoding, check_tables, root)
    finally:
        if lock is not None:
            lock.release()


def _replace_once(path, old, new, encoding, check_tables, root):
    b = _read_bytes(path)
    crlf = b'\r\n' in b and b.count(b'\r\n') >= b.count(b'\n') // 2
    o, n = old, new
    if crlf:
        o, n = o.replace('\r\n', '\n').replace('\n', '\r\n'), n.replace('\r\n', '\n').replace('\n', '\r\n')
    ob, nb = o.encode(encoding), n.encode(encoding)
    cnt = b.count(ob)
    if cnt != 1:
        raise ValueError('The target string occurs %d times (it must occur exactly once): %s' % (cnt, path))
    sync = None
    if root:
        try:
            sync = Sync(_load_cfg(root))
            sync.before_write(_rel(root, path))
        except Exception:        # a fault in the guard must not block the replacement itself
            sync = None
    out = b.replace(ob, nb)
    assert out.count(b'\r\n') == b.count(b'\r\n') + (nb.count(b'\r\n') - ob.count(b'\r\n')), 'line break count mismatch'
    if check_tables and path.lower().endswith('.md'):
        before = table_problems(b.decode(encoding, 'replace'))
        after = table_problems(out.decode(encoding, 'replace'))
        grew = [c for c in ('orphan', 'cells', 'tail')
                if sum(1 for x in after if x[1] == c) > sum(1 for x in before if x[1] == c)]
        if grew:
            raise ValueError('Not written: the replacement breaks table rows (one item per line · write | inside a cell as \\|) — %s: %s'
                             % (path, ' · '.join(describe_table_problem(x) for x in after if x[1] in grew)[:600]))
        if after:
            sys.stderr.write('replace_once: %s already had %d table defects (unrelated to this replacement) — %s\n'
                             % (path, len(after), ' · '.join(describe_table_problem(x) for x in after[:3])))
    _atomic_write(path, out)
    if sync is not None:
        try:
            sync.after_write(_rel(root, path))
        except Exception:
            pass
    return {'path': path, 'crlf': crlf, 'delta': len(out) - len(b), 'count': cnt}


def refuse_if_alert(sync, writing, tool_name):
    """Entry check of batch tools — when writing (about to write files), returns False (refuse) on an unconfirmed ERROR. When only diagnosing, shows the warning and returns True.
    Decided by Sync.blocking() — a confirmed key does not block again for ack_hours, so after confirmation the tidy tool that rebuilds the remaining condition runs."""
    open_ = sync.blocking()
    if not open_:
        return True
    print('! Sync check ERROR — %s%s' % (tool_name, ' stopped. After confirmation, run `check_sync.py --ack`.' if writing else ' only diagnoses.'))
    for f in open_:
        print('  ! ' + f.line())
    return not writing
