# -*- coding: utf-8 -*-
r"""grammar_baseline.py — baseline of the pre-submission grammar check. Code picks out the paragraphs changed since the check.

Fingerprints of the text Claude actually reviewed are recorded in a baseline file, and only the units of the current manuscript that are missing from the
baseline (changed or new paragraphs) are shown. This tool works out what changed and compares with the source; the model only checks the grammar of the units
it picks. Rules: plugin document `manuscript-workflow/references/revision-protocol.md` "Pre-submission grammar check"; the settings key `grammar`: `project-config.md`.

Usage  (`<py>` is this computer's Python 3 — `python` on Windows, `python3` on macOS)
    <py> -X utf8 tools/grammar_baseline.py init --confirm "<user's words>"   only when there is no baseline file — records every unit in scope (once, at the very start)
    <py> -X utf8 tools/grammar_baseline.py changed [--out [<packet>]]       units missing from the baseline — id · file · line · full text · avoid-list hits.
                                                                --out alone makes the packet at `grammar_packets/<time>_<computer>.json` next to the baseline file
    <py> -X utf8 tools/grammar_baseline.py clean --packet <packet> --ids <id> …          records units with no findings (the packet's fingerprints only)
    <py> -X utf8 tools/grammar_baseline.py clean --packet <packet> --all-except [<id> …] records the packet except those ids
    <py> -X utf8 tools/grammar_baseline.py resolve --packet <packet> --id <id> --keep    records a unit with findings that was decided to stay as it is
    <py> -X utf8 tools/grammar_baseline.py resolve --packet <packet> --id <id> --replace <original> <revision> [<original> <revision> …]
                                                                a unit decided to be changed — records only when the replaced text equals a unit of the current manuscript
    <py> -X utf8 tools/grammar_baseline.py verify <candidate file>             whether the originals of a candidate table appear verbatim at their location (file · L<number>)
    <py> -X utf8 tools/grammar_baseline.py status                         per source: units in scope · recorded · left
    common  --dir <project root>    --baseline <baseline file> (default `.manuscript/grammar_baseline.jsonl` — for tests and for keeping the first baseline)

Units   md          blocks separated by blank lines. Blocks starting with an excluded prefix (`grammar.exclude_prefixes`, default `@NOTE`) are left out
        lines       non-empty lines inside the configured regions. A region runs from a line that matches the start regex up to, **not including**, the first
                    line from the **next** line on that matches the end regex. If the end marker is not found, a warning is given and the file is read to the end
        json-values one string value (keys are not units). Values under keys that start with `_` are description fields and are left out, with everything below them
Fingerprint  SHA-256 of the normalized text — NFC · LF line endings · leading and trailing whitespace removed, inner whitespace kept. File and location are not part of it —
        comparison is by content, so a paragraph that only moved does not show up, a reverted paragraph drops out, and a new paragraph shows up. The id is its first 12 characters.
Baseline `.manuscript/grammar_baseline.jsonl` — one mark per line (`fingerprint` · `how` (init | clean | keep | replace) · `time` · `computer` · `file`,
        and `phrase` for init). Only appended to, never deleted from. A lost mark only makes its unit come back as "changed"; nothing is missed.
        Lines written before 0.14 use Korean keys; both spellings are read (`_config.BASELINE_KEYS` · `PACKET_KEYS`).
Packet  JSON made exclusively by `changed --out` — the text shown and its fingerprints. clean and resolve --keep record **only the packet's fingerprints** and do not
        reread the manuscript, so a paragraph someone edited during the check comes back on the list. Without a path the packet goes to `grammar_packets/`
        next to the baseline file. Delete a packet once every unit is decided — the next changed picks undecided units again, so deleting it at any time loses nothing.
Settings optional key `grammar` in `.manuscript/project.json` — `sources` (sources added to the default scope · `file` relative to the root) · `exclude_prefixes` ·
        `avoid_lists` (avoid lists · relative to the root). Without the key the scope is the `chapters` files of `manuscript.source_dir` (except the references file).
        Unknown keys, unknown kinds, region markers not found, missing files and zero units give warnings. Keys that start with `_` are comments.
Exit    0 OK · 1 something left, or a mismatch · 2 argument or settings error
Writes  only the baseline file (init · clean · resolve) and packets (changed --out). The manuscript is only read. The baseline file is not a shared sync file —
        the sync check reports conflict copies, and a lost mark only makes its unit come back.
"""
import argparse
import datetime
import difflib
import hashlib
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import (load as _load_cfg, nfc, _utf8_console, split_cells, unescape_cell,   # noqa: E402  — _config first (finder for NFD-named modules)
                     TABLE_ROW_RE, TABLE_SEP_RE, row_like_id,
                     BASELINE_KEYS, PACKET_KEYS, PACKET_FORMAT as _PACKET_FORMATS, english_keys, LEGACY_GRAMMAR as _LEGACY_GRAMMAR)   # format tokens — both spellings read, English written
from _sync import computer_id, find_project_root                                   # noqa: E402
import _location                                                                         # noqa: E402

BASELINE_REL = '.manuscript/grammar_baseline.jsonl'
PACKET_DIR = 'grammar_packets'           # next to the baseline file — where changed --out without a path puts the packet
# Names of 0.12 or earlier — used as they are when only these exist and there is no baseline file under the new name (the packet folder keeps the old name too)
LEGACY_BASELINE_REL, LEGACY_PACKET_DIR = _LEGACY_GRAMMAR
PACKET_FORMAT = _PACKET_FORMATS[0]      # written; packets of the old format (_PACKET_FORMATS[1], Korean keys) are still read
KINDS = ('md', 'lines', 'json-values')
HOWS = ('init', 'clean', 'keep', 'replace')
GRAMMAR_KEYS = ('sources', 'exclude_prefixes', 'avoid_lists')
SOURCE_KEYS = ('file', 'kind', 'regions')
REGION_KEYS = ('start', 'end')
DEFAULT_EXCLUDE = ['@NOTE']
ID_LEN = 12
MIN_ID_PREFIX = 4
_CODE_SPAN = re.compile(r'`([^`]+)`')
_JSON_STR = re.compile(r'"(?:[^"\\]|\\.)*"')
_FP_RE = re.compile(r'^[0-9a-f]{64}$')


class UsageError(Exception):
    """Argument or settings error — exit code 2."""


# ---------------------------------------------------------------- normalization · fingerprint
def normalize(text):
    """Text to fingerprint — NFC · LF line endings · leading and trailing whitespace removed. Inner whitespace stays."""
    return nfc(text.replace('\r\n', '\n').replace('\r', '\n')).strip()


def fingerprint(text):
    return hashlib.sha256(normalize(text).encode('utf-8')).hexdigest()


def now_text():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


# ---------------------------------------------------------------- paths — found even when name normalization (NFC · NFD) differs
def find_path(root, rel):
    """Real path of rel relative to the root. Folder listings are compared in NFC, so names stored in NFD (a copy moved from a macOS mirror) are found too. None if missing."""
    rel = rel.replace('\\', '/')
    direct = os.path.join(root, *[s for s in rel.split('/') if s])
    if os.path.exists(direct):
        return direct
    cur = os.path.abspath(root)
    for seg in rel.split('/'):
        if seg in ('', '.'):
            continue
        if seg == '..':
            cur = os.path.dirname(cur)
            continue
        nxt = os.path.join(cur, seg)
        if os.path.exists(nxt):
            cur = nxt
            continue
        try:
            names = os.listdir(cur)
        except OSError:
            return None
        want = nfc(seg)
        hit = [n for n in names if nfc(n) == want]
        if not hit:
            return None
        cur = os.path.join(cur, hit[0])
    return cur


def locate(path):
    """The absolute or relative path as is if it exists; otherwise a name equal in NFC in the same folder. None if missing."""
    p = os.path.abspath(path)
    if os.path.exists(p):
        return p
    d, base = os.path.split(p)
    try:
        names = os.listdir(d)
    except OSError:
        return None
    hit = [n for n in names if nfc(n) == nfc(base)]
    return os.path.join(d, hit[0]) if hit else None


def rel_of(root, path):
    return nfc(os.path.relpath(os.path.abspath(path), os.path.abspath(root)).replace(os.sep, '/'))


def read_text(path):
    """Reads UTF-8 (BOM allowed) and normalizes line endings to LF — line numbers stay those of the physical lines."""
    with io.open(path, encoding='utf-8-sig', newline='') as f:
        return f.read().replace('\r\n', '\n').replace('\r', '\n')


# ---------------------------------------------------------------- settings
class Source(object):
    def __init__(self, file, kind, regions, origin):
        self.file = file                # relative to the root (`/` · NFC)
        self.kind = kind
        self.regions = regions          # [(start regex, end regex)] — lines only
        self.origin = origin            # 'chapters' | 'grammar'

    def key(self):
        return (self.file, self.kind, tuple(r.pattern for pair in self.regions for r in pair))


class Settings(object):
    def __init__(self, sources, exclude, avoid_lists):
        self.sources = sources
        self.exclude = exclude
        self.avoid_lists = avoid_lists


def _str_list(v, name):
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise UsageError('grammar.%s must be a list of strings' % name)
    return list(v)


def read_settings(cfg, warn):
    g = cfg.raw.get('grammar')
    if g is None:
        g = {}
    if not isinstance(g, dict):
        raise UsageError('grammar must be an object')
    for k in g:
        if k not in GRAMMAR_KEYS and not k.startswith('_'):
            warn('Unknown key `%s` in settings grammar — not read (known keys: %s)' % (k, ' · '.join(GRAMMAR_KEYS)))
    exclude = _str_list(g['exclude_prefixes'], 'exclude_prefixes') if 'exclude_prefixes' in g else list(DEFAULT_EXCLUDE)
    avoid = _str_list(g['avoid_lists'], 'avoid_lists') if 'avoid_lists' in g else []

    sources = []
    # default scope — the chapter files of the manuscript folder (except the references file)
    src = cfg.source_rel
    base = (src + '/') if src and find_path(cfg.root, src) else ''
    for _n, f in cfg.chapters:
        if f == cfg.references:
            continue
        sources.append(Source(nfc(base + f), 'md', [], 'chapters'))
    extra = g.get('sources', [])
    if not isinstance(extra, list):
        raise UsageError('grammar.sources must be a list')
    for i, s in enumerate(extra, 1):
        if not isinstance(s, dict) or not isinstance(s.get('file'), str) or not s['file'].strip():
            raise UsageError('grammar.sources entry %d has no `file` (string)' % i)
        f = nfc(s['file'].strip().replace('\\', '/'))
        for k in s:
            if k not in SOURCE_KEYS and not k.startswith('_'):
                warn('Settings grammar.sources `%s`: unknown key `%s` — not read' % (f, k))
        kind = s.get('kind')
        if kind is None:
            kind = 'md'
            if not f.lower().endswith('.md'):
                warn('Settings grammar.sources `%s` has no kind — read as md (blank-line blocks)' % f)
        if kind not in KINDS:
            warn('Settings grammar.sources `%s`: unknown kind `%s` (%s) — this source is not read' % (f, kind, ' · '.join(KINDS)))
            continue
        regions = []
        if 'regions' in s:
            if kind != 'lines':
                warn('Settings grammar.sources `%s`: regions apply to lines only — ignored' % f)
            else:
                if not isinstance(s['regions'], list):
                    raise UsageError('grammar.sources `%s`: regions must be a list' % f)
                for r in s['regions']:
                    if not isinstance(r, dict) or not isinstance(r.get('start'), str) or not isinstance(r.get('end'), str):
                        raise UsageError('grammar.sources `%s`: every region needs `start` and `end` (regex strings)' % f)
                    for k in r:
                        if k not in REGION_KEYS and not k.startswith('_'):
                            warn('Settings grammar.sources `%s`: unknown key `%s` in a region — not read' % (f, k))
                    try:
                        regions.append((re.compile(r['start']), re.compile(r['end'])))
                    except re.error as e:
                        raise UsageError('grammar.sources `%s`: region regex error: %s' % (f, e))
        if kind == 'lines' and not regions:
            warn('Settings grammar.sources `%s` is lines but has no regions — 0 units' % f)
        sources.append(Source(f, kind, regions, 'grammar'))
    # a source listed twice counts once
    seen, uniq = set(), []
    for s in sources:
        if s.key() not in seen:
            seen.add(s.key())
            uniq.append(s)
    return Settings(uniq, exclude, avoid)


# ---------------------------------------------------------------- extracting units
class Unit(object):
    __slots__ = ('source', 'file', 'line', 'text', 'fp')

    def __init__(self, source, line, raw):
        self.source = source
        self.file = source.file
        self.line = line
        self.text = normalize(raw)
        self.fp = hashlib.sha256(self.text.encode('utf-8')).hexdigest()


def md_units(src, text, exclude, stats):
    out, block, start = [], [], 0
    lines = text.split('\n')
    for n, line in enumerate(lines + [''], 1):
        if line.strip():
            if not block:
                start = n
            block.append(line)
            continue
        if block:
            raw = '\n'.join(block)
            head = raw.lstrip()
            if any(head.startswith(p) for p in exclude):
                stats['excluded'] += 1
            else:
                if any(l.lstrip().startswith(p) for l in block[1:] for p in exclude):
                    stats['glued'].append(start)       # an excluded-prefix line is glued to the paragraph — a change to that line also brings up this block
                out.append(Unit(src, start, raw))
            block = []
    return out


def line_units(src, text, warn):
    lines = text.split('\n')
    picked = {}
    for start_re, end_re in src.regions:
        found = False
        i = 0
        while i < len(lines):
            if not start_re.search(lines[i]):
                i += 1
                continue
            found = True
            j = i + 1
            while j < len(lines) and not end_re.search(lines[j]):
                j += 1
            if j >= len(lines):
                warn('`%s` L%d: region end marker `%s` not found — reading to the end of the file' % (src.file, i + 1, end_re.pattern))
            for k in range(i, min(j, len(lines))):
                if lines[k].strip():
                    picked.setdefault(k + 1, lines[k])
            i = j
        if not found:
            warn('`%s`: region start marker `%s` not found' % (src.file, start_re.pattern))
    return [Unit(src, n, picked[n]) for n in sorted(picked)]


def _json_strings(v, out):
    """String values — values under keys that start with `_` (everything below them) are description fields and are left out."""
    if isinstance(v, str):
        out.append(v)
    elif isinstance(v, list):
        for x in v:
            _json_strings(x, out)
    elif isinstance(v, dict):
        for k, x in v.items():
            if not k.startswith('_'):
                _json_strings(x, out)


_JSON_LIT = re.compile(r'-?\d[0-9.eE+-]*|true|false|null')


def _json_value_spans(text):
    """[(value, start offset)] — string values only, not keys. Follows the structure so that values under `_` keys are left out (the same text elsewhere is told apart by its position).
    text must be text that json.loads accepts."""
    out, n = [], len(text)

    def skip(i):
        while i < n and text[i] in ' \t\r\n':
            i += 1
        return i

    def string(i):
        m = _JSON_STR.match(text, i)
        if not m:
            raise ValueError('no string at offset %d' % i)
        return json.loads(m.group()), m.end()

    def value(i, muted):
        i = skip(i)
        c = text[i]
        if c == '"':
            s, j = string(i)
            if not muted:
                out.append((s, i))
            return j
        if c in '{[':
            close = '}' if c == '{' else ']'
            i = skip(i + 1)
            if text[i] == close:
                return i + 1
            while True:
                m2 = muted
                if c == '{':
                    k, i = string(skip(i))
                    i = skip(i)
                    if text[i] != ':':
                        raise ValueError('no `:` at offset %d' % i)
                    i += 1
                    m2 = muted or k.startswith('_')
                i = skip(value(i, m2))
                if text[i] == ',':
                    i += 1
                    continue
                if text[i] == close:
                    return i + 1
                raise ValueError('offset %d: no `,` or `%s`' % (i, close))
        m = _JSON_LIT.match(text, i)
        if not m:
            raise ValueError('could not read the value at offset %d' % i)
        return m.end()

    value(0, False)
    return out


def json_units(src, text, warn):
    try:
        data = json.loads(text)
    except ValueError as e:
        warn('Could not read `%s` as JSON: %s — 0 units' % (src.file, e))
        return []
    try:
        spans = _json_value_spans(text)
    except (ValueError, IndexError) as e:
        warn('Could not locate the string values of `%s`: %s — 0 units' % (src.file, e))
        return []
    out = [Unit(src, text.count('\n', 0, at) + 1, v) for v, at in spans if normalize(v)]
    expect = []
    _json_strings(data, expect)
    if sorted(v for v, _at in spans) != sorted(expect):
        warn('Could not locate every string value of `%s` (found %d · actual %d) — line numbers may be wrong'
             % (src.file, len(spans), len(expect)))
    return out


def collect(root, settings, warn):
    """[(source, [units], status)] — status 'ok' | 'missing' | 'unreadable'."""
    result = []
    for src in settings.sources:
        stats = {'excluded': 0, 'glued': []}
        path = find_path(root, src.file)
        if path is None or not os.path.isfile(path):
            warn('Source `%s` is missing — 0 units' % src.file)
            result.append((src, [], 'missing', stats))
            continue
        try:
            text = read_text(path)
        except (OSError, UnicodeDecodeError) as e:
            warn('Could not read source `%s`: %s — 0 units' % (src.file, e))
            result.append((src, [], 'unreadable', stats))
            continue
        if src.kind == 'md':
            units = md_units(src, text, settings.exclude, stats)
        elif src.kind == 'lines':
            units = line_units(src, text, warn)
        else:
            units = json_units(src, text, warn)
        if not units:
            warn('Source `%s` (%s) has 0 units' % (src.file, src.kind))
        result.append((src, units, 'ok', stats))
    return result


def all_units(collected):
    return [u for _s, us, _st, _x in collected for u in us]


def group_by_fp(units):
    """Fingerprint → [units …] (in order of first appearance). The same text in two places is one fingerprint with several locations."""
    groups = {}
    for u in units:
        groups.setdefault(u.fp, []).append(u)
    return groups


# ---------------------------------------------------------------- avoid list
def load_avoid(root, paths, warn):
    out = []
    for p in paths:
        real = find_path(root, p)
        if real is None or not os.path.isfile(real):
            warn('Avoid list `%s` is missing' % p)
            continue
        try:
            text = read_text(real)
        except (OSError, UnicodeDecodeError) as e:
            warn('Could not read avoid list `%s`: %s' % (p, e))
            continue
        n0 = len(out)
        for line in text.split('\n'):
            if not line.startswith('|') or TABLE_SEP_RE.match(line):
                continue
            # the **first** code span of the first cell is the expression — code spans in the explanation in brackets after it (`… before \`of\``) are not
            spans = _CODE_SPAN.findall(split_cells(line)[0])
            s = nfc(unescape_cell(spans[0])).strip() if spans else ''
            if s and (s, p) not in out:
                out.append((s, p))
        if len(out) == n0:
            warn('Avoid list `%s`: no code span found in the first column of its table' % p)
    return out


def avoid_hits(text, avoid):
    t = text.casefold()
    return [s for s, _p in avoid if s.casefold() in t]


# ---------------------------------------------------------------- baseline file
def baseline_path(root, arg):
    """(real path or None, path to create)."""
    if arg:
        p = os.path.abspath(arg)
        return locate(p), p
    real = find_path(root, BASELINE_REL)
    old = None if real else find_path(root, LEGACY_BASELINE_REL)
    if old:
        return old, old
    return real, os.path.join(root, *BASELINE_REL.split('/'))


def read_baseline(path, warn):
    marks, hows, n_lines = {}, {}, 0
    with io.open(path, encoding='utf-8-sig', newline='') as f:
        data = f.read()
    for n, line in enumerate(data.replace('\r\n', '\n').split('\n'), 1):
        s = line.strip()
        if not s:
            continue
        n_lines += 1
        try:
            rec = json.loads(s)
        except ValueError:
            warn('Could not read line %d of the baseline file — that mark is treated as missing' % n)
            continue
        rec = english_keys(rec, BASELINE_KEYS)                  # lines written before 0.14 use Korean keys
        fp = rec.get('fingerprint') if isinstance(rec, dict) else None
        if not isinstance(fp, str) or not _FP_RE.match(fp):
            warn('Line %d of the baseline file has no fingerprint or a wrong format — that mark is treated as missing' % n)
            continue
        how = rec.get('how')
        if how not in HOWS:
            warn('Line %d of the baseline file: unknown how `%s` — still counted as a mark' % (n, how))
        hows[how] = hows.get(how, 0) + 1
        marks.setdefault(fp, rec)
    return marks, hows, n_lines


def mark_record(fp, how, file, extra=None):
    r = {'fingerprint': fp, 'how': how, 'time': now_text(), 'computer': computer_id(), 'file': file}
    if extra:
        r.update(extra)
    return r


def _dump(records):
    return ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records)


def create_exclusive(path, text):
    """Creates only when missing — FileExistsError if it exists. Writes the bytes as they are (LF line endings)."""
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0))
    with io.open(fd, 'wb') as f:
        f.write(text.encode('utf-8'))
        f.flush()
        os.fsync(f.fileno())


def append_records(path, records):
    """Only appends. If the last line ends without a line break, adds one first."""
    if not records:
        return
    data = _dump(records).encode('utf-8')
    with io.open(path, 'rb') as f:
        f.seek(0, os.SEEK_END)
        if f.tell() > 0:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b'\n':
                data = b'\n' + data
    with io.open(path, 'ab') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


# ---------------------------------------------------------------- packets
def write_packet(path, root, base_disp, groups, avoid):
    units = []
    for fp, us in groups.items():
        units.append({'id': fp[:ID_LEN], 'fingerprint': fp, 'text': us[0].text,
                      'locations': [{'file': u.file, 'line': u.line} for u in us],
                      'avoid': avoid_hits(us[0].text, avoid)})
    data = {'format': PACKET_FORMAT, 'created': now_text(), 'computer': computer_id(), 'root': nfc(os.path.abspath(root)),
            'baseline': base_disp, 'units': units}
    create_exclusive(os.path.abspath(path), json.dumps(data, ensure_ascii=False, indent=1) + '\n')


def read_packet(path, root, base_disp, warn):
    real = locate(path)
    if real is None:
        raise UsageError('Packet file missing: %s' % path)
    try:
        data = json.loads(read_text(real))
    except (OSError, ValueError) as e:
        raise UsageError('Could not read the packet file: %s' % e)
    data = english_keys(data, PACKET_KEYS)                      # packets made before 0.14 use Korean keys
    if not isinstance(data, dict) or data.get('format') not in _PACKET_FORMATS or not isinstance(data.get('units'), list):
        raise UsageError('Not a packet (`format` must be %s): %s' % (PACKET_FORMAT, path))
    for u in data['units']:
        if not isinstance(u, dict) or not isinstance(u.get('text'), str) or fingerprint(u['text']) != u.get('fingerprint'):
            raise UsageError('Text and fingerprint of packet unit `%s` do not match — if the packet was edited by hand, make it again with changed --out'
                             % (u.get('id') if isinstance(u, dict) else '?'))
    if nfc(data.get('root', '')) != nfc(os.path.abspath(root)):
        warn('The packet was made under another root (%s) — fingerprints are content-based, so they are recorded anyway' % data.get('root'))
    if data.get('baseline') != base_disp:
        warn('The packet was made against the baseline %s; the current baseline is %s' % (data.get('baseline'), base_disp))
    return data['units']


def pick(units, ident):
    ident = ident.strip().lower()
    if len(ident) < MIN_ID_PREFIX:
        raise UsageError('id `%s` is too short (at least %d characters)' % (ident, MIN_ID_PREFIX))
    hit = [u for u in units if u['fingerprint'].startswith(ident)]
    if not hit:
        raise UsageError('id `%s` is not in the packet' % ident)
    if len(hit) > 1:
        raise UsageError('id `%s` matches %d units of the packet — give more characters' % (ident, len(hit)))
    return hit[0]


# ---------------------------------------------------------------- display
def show_unit(fp, locs, text, hits, out=print):
    where = ' · '.join('%s L%d' % (f, n) for f, n in locs)
    out('[%s] %s' % (fp[:ID_LEN], where))
    for line in text.split('\n'):
        out('    ' + line)
    if hits:
        out('    ! avoid list: ' + ' · '.join('`%s`' % h for h in hits))


_TOKEN = re.compile(r'\w+|\s+|[^\w\s]')


def diff_lines(expect, actual, width=6, limit=8):
    """Word-level difference — `…previous words [-replaced text-]{+current manuscript+} next words…`. Line breaks show as ⏎."""
    a, b = _TOKEN.findall(expect), _TOKEN.findall(actual)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out = []
    show = lambda toks: ''.join(toks).replace('\n', '⏎')                      # noqa: E731
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        out.append('…%s[-%s-]{+%s+}%s…' % (show(a[max(0, i1 - width):i1]), show(a[i1:i2]), show(b[j1:j2]),
                                           show(a[i2:i2 + width])))
        if len(out) >= limit:
            out.append('(more differences)')
            break
    return out


# ---------------------------------------------------------------- commands
class Ctx(object):
    def __init__(self, a):
        self.warnings = []
        root = a.dir
        if root:
            root = os.path.abspath(root)
            if not os.path.isdir(root):
                raise UsageError('Project folder missing: %s' % root)
        else:
            here = os.path.dirname(os.path.abspath(__file__))
            root = find_project_root(here) or find_project_root(os.getcwd())
            if not root:
                raise UsageError('Project root (.manuscript/project.json) not found — give it with --dir')
        self.root = root
        try:
            self.cfg = _load_cfg(root)
        except SystemExit as e:                       # _config.load raises read errors as SystemExit
            raise UsageError(str(e))
        if find_path(root, '.manuscript/project.json') is None and find_path(root, '.writing/project.json') is None:
            self.warn('No settings file — the scope comes from the defaults')
        self.settings = read_settings(self.cfg, self.warn)
        self.base_real, self.base_new = baseline_path(root, a.baseline)
        self.base_disp = rel_of(root, self.base_new) if not a.baseline else nfc(os.path.abspath(a.baseline))
        legacy = bool(self.base_real) and nfc(os.path.basename(self.base_real)) == nfc(LEGACY_BASELINE_REL.split('/')[-1])
        self.packet_dir = os.path.join(os.path.dirname(self.base_real or self.base_new), LEGACY_PACKET_DIR if legacy else PACKET_DIR)

    def disp(self, path):
        """Path relative to the root if inside it; the absolute path if outside (including another drive)."""
        try:
            r = rel_of(self.root, path)
        except ValueError:                            # Windows — no relative path across drives
            return nfc(os.path.abspath(path))
        return r if not r.startswith('..') else nfc(os.path.abspath(path))

    def default_packet(self):
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        return os.path.join(self.packet_dir, '%s_%s.json' % (stamp, computer_id()))

    def leftover_packets(self):
        try:
            return sorted(f for f in os.listdir(self.packet_dir) if f.lower().endswith('.json'))
        except OSError:
            return []

    def warn(self, msg):
        if msg not in self.warnings:
            self.warnings.append(msg)

    def flush(self):
        for w in self.warnings:
            print('  ! ' + w)
        self.warnings = []

    def need_baseline(self):
        if self.base_real is None:
            raise UsageError('No baseline file: %s — the first baseline is made with `init --confirm "<words>"` once the user says so'
                             % self.base_disp)
        return read_baseline(self.base_real, self.warn)


def cmd_init(c, a):
    phrase = (a.confirm or '').strip()
    if not phrase:
        raise UsageError('init needs the user\'s words — --confirm "<user\'s words>"')
    if c.base_real is not None:
        raise UsageError('The baseline file already exists: %s — init runs only once, at the start (the baseline is never deleted)' % c.base_disp)
    collected = collect(c.root, c.settings, c.warn)
    groups = group_by_fp(all_units(collected))
    if not groups:
        c.flush()
        raise UsageError('No units found in scope — check the settings (manuscript.chapters · grammar.sources)')
    records = [mark_record(fp, 'init', us[0].file, {'phrase': phrase}) for fp, us in groups.items()]
    try:
        create_exclusive(c.base_new, _dump(records))
    except FileExistsError:
        raise UsageError('The baseline file appeared in the meantime: %s — check again' % c.base_disp)
    c.flush()
    for src, units, _st, _x in collected:
        print('  %-40s %-11s %4d units' % (src.file, src.kind, len(units)))
    print('Baseline created: %s — %d fingerprints (%d units) · words "%s"'
          % (c.base_disp, len(groups), sum(len(us) for _s, us, _t, _x in collected), phrase))
    return 0


def cmd_changed(c, a):
    marks, _hows, n_lines = c.need_baseline()
    collected = collect(c.root, c.settings, c.warn)
    units = all_units(collected)
    groups = group_by_fp([u for u in units if u.fp not in marks])
    avoid = load_avoid(c.root, c.settings.avoid_lists, c.warn)
    c.flush()
    print('Baseline %s — %d mark lines · %d units in scope · %d not in the baseline'
          % (c.base_disp, n_lines, len(units), len(groups)))
    for fp, us in groups.items():
        print()
        show_unit(fp, [(u.file, u.line) for u in us], us[0].text, avoid_hits(us[0].text, avoid))
    if a.out is not None:
        if groups:
            out = a.out or c.default_packet()
            try:
                write_packet(out, c.root, c.base_disp, groups, avoid)
            except FileExistsError:
                raise UsageError('The packet file already exists: %s — give a new name (it is never overwritten)' % out)
            print('\nPacket: %s (%d)' % (out if a.out else c.disp(out), len(groups)))
        else:
            print('\nNo changed units, so no packet was made')
    return 1 if groups else 0


def _stamp_from_packet(c, units, how):
    marks, _h, _n = c.need_baseline()
    todo, already = [], 0
    for u in units:
        fp = fingerprint(u['text'])                  # recomputed from the packet text instead of trusting the stored fingerprint
        if fp in marks or any(r['fingerprint'] == fp for r in todo):
            already += 1
            continue
        file = (u.get('locations') or [{}])[0].get('file', '')
        todo.append(mark_record(fp, how, file))
    append_records(c.base_real, todo)
    return todo, already


def cmd_clean(c, a):
    packet = read_packet(a.packet, c.root, c.base_disp, c.warn)
    if a.ids is not None:
        chosen = [pick(packet, i) for i in a.ids]
    else:
        skip = {pick(packet, i)['fingerprint'] for i in a.all_except}
        chosen = [u for u in packet if u['fingerprint'] not in skip]
    todo, already = _stamp_from_packet(c, chosen, 'clean')
    c.flush()
    print('clean — recorded %d · already recorded %d (of %d in the packet, %d chosen)' % (len(todo), already, len(packet), len(chosen)))
    for r in todo:
        print('  %s  %s' % (r['fingerprint'][:ID_LEN], r['file']))
    return 0


def cmd_resolve(c, a):
    packet = read_packet(a.packet, c.root, c.base_disp, c.warn)
    u = pick(packet, a.id)
    if a.keep:
        todo, already = _stamp_from_packet(c, [u], 'keep')
        c.flush()
        print('keep — %s %s' % (u['id'], 'recorded' if todo else 'already recorded'))
        return 0
    pairs = a.replace
    if len(pairs) % 2:
        raise UsageError('--replace takes <original> <revision> pairs (got %d)' % len(pairs))
    text = u['text']
    for i in range(0, len(pairs), 2):
        old = nfc(pairs[i].replace('\r\n', '\n'))
        new = nfc(pairs[i + 1].replace('\r\n', '\n'))
        n = text.count(old) if old else 0
        if n != 1:
            raise UsageError('Each original must occur exactly once in the packet text — `%s` occurs %d times' % (pairs[i], n))
        text = text.replace(old, new, 1)
    expect = normalize(text)
    if not expect:
        raise UsageError('The replaced text is empty')
    want = hashlib.sha256(expect.encode('utf-8')).hexdigest()
    marks, _h, _n = c.need_baseline()
    collected = collect(c.root, c.settings, c.warn)
    units = all_units(collected)
    found = [x for x in units if x.fp == want]
    if found:
        if want in marks:
            c.flush()
            print('replace — %s → %s is already recorded (%s L%d)' % (u['id'], want[:ID_LEN], found[0].file, found[0].line))
            return 0
        append_records(c.base_real, [mark_record(want, 'replace', found[0].file)])
        c.flush()
        print('replace — %s → %s recorded (%s L%d)' % (u['id'], want[:ID_LEN], found[0].file, found[0].line))
        return 0
    # not recorded — show the difference from the closest unit
    files = {loc.get('file') for loc in u.get('locations', [])}
    pool = [x for x in units if x.file in files] or units
    best = sorted(pool, key=lambda x: difflib.SequenceMatcher(None, expect, x.text, autojunk=False).quick_ratio(),
                  reverse=True)[:5]
    best = max(best, key=lambda x: difflib.SequenceMatcher(None, expect, x.text, autojunk=False).ratio()) if best else None
    c.flush()
    print('Not recorded — the replaced text does not equal any unit of the current manuscript character for character (%s)' % u['id'])
    if best is not None:
        r = difflib.SequenceMatcher(None, expect, best.text, autojunk=False).ratio()
        print('Closest unit: %s L%d (%.0f%% match) — difference (replaced text → current manuscript):' % (best.file, best.line, r * 100))
        for d in diff_lines(expect, best.text):
            print('    ' + d)
    return 1


# ---- verify
def _match_in(line, frags):
    k = 0
    for f in frags:
        j = line.find(f, k)
        if j < 0:
            return False
        k = j + len(f)
    return True


def _parse_locations(cell, gram, root, warn_row):
    """Location cell → [(written name, path relative to the root or None, real path or None, [lines …])]."""
    pat = re.compile(r'`(?P<bt>[^`]+)`|(?<![A-Za-z0-9_])L(?P<ln>\d+)(?:\(\d+[^\d)]{0,8}\))?|(?P<bare>' + _location.BARE + r')')   # `L12(3)` — any short count word after the number
    locs = []

    def add_file(tok):
        path, kind = gram.resolve(tok)
        real = find_path(root, path) if kind not in ('glob',) else None
        if real is None and gram.src:
            alt = gram.src + '/' + gram._clean(tok)
            real = find_path(root, alt)
            if real is not None:
                path = alt
        if real is not None and not os.path.isfile(real):
            real = None
        locs.append([tok, path if real else None, real, []])

    def scan(s):
        for m in pat.finditer(s):
            if m.group('bt') is not None:
                head, _, rest = m.group('bt').strip().partition(' ')
                if gram._pathlike(head):
                    add_file(head)
                    if rest.strip():
                        scan(rest)
                else:
                    scan(m.group('bt'))
            elif m.group('ln') is not None:
                if not locs:
                    warn_row('line number L%s without a file' % m.group('ln'))
                else:
                    locs[-1][3].append(int(m.group('ln')))
            elif m.group('bare') is not None and gram._pathlike(m.group('bare')):
                add_file(m.group('bare'))
    scan(cell)
    return locs


def cmd_verify(c, a):
    real = locate(a.candidates)
    if real is None:
        raise UsageError('Candidate file missing: %s' % a.candidates)
    text = read_text(real)
    gram = _location.Grammar(c.cfg)
    cache = {}

    def lines_of(path):
        if path not in cache:
            cache[path] = [nfc(x) for x in read_text(path).split('\n')]
        return cache[path]

    rows = []
    for n, line in enumerate(text.split('\n'), 1):
        m = TABLE_ROW_RE.match(line)
        if not m:
            rid = row_like_id(line)
            if rid:
                c.warn('Candidate line %d looks like row `%s` but its ID cell could not be read (strip emphasis and code marks: `| %s |`) — not compared'
                       % (n, rid, rid))
            continue
        cells = split_cells(line)
        rid = m.group(1)
        notes, status = [], 'match'
        if len(cells) < 3:
            rows.append((rid, n, 'not compared', ['fewer than three cells']))
            continue

        def warn_row(msg):
            notes.append(msg)

        locs = _parse_locations(cells[1], gram, c.root, warn_row)
        body = cells[2]
        left = body.split('→', 1)[0] if '→' in body else body
        origs = [nfc(unescape_cell(x)) for x in _CODE_SPAN.findall(left)]
        if not locs:
            rows.append((rid, n, 'not compared', ['no file read from the location: %s' % cells[1][:60]] + notes))
            continue
        if not origs:
            rows.append((rid, n, 'not compared', ['no code span with the original'] + notes))
            continue
        partial = bool(notes)
        for tok, path, rp, lns in locs:
            if rp is None:
                notes.append('file `%s` not found' % tok)
                partial = True
            elif not lns:
                notes.append('`%s` has no line number — searched the whole file' % tok)
                partial = True
        for o in origs:
            frags = [f.strip() for f in o.split('…') if f.strip()]
            hit = False
            for tok, path, rp, lns in locs:
                if rp is None:
                    continue
                fl = lines_of(rp)
                cand = lns if lns else range(1, len(fl) + 1)
                if any(1 <= ln <= len(fl) and _match_in(fl[ln - 1], frags) for ln in cand):
                    hit = True
                    break
            if not hit:
                status = 'mismatch'
                where = []
                for tok, path, rp, lns in locs:
                    if rp is None:
                        continue
                    fl = lines_of(rp)
                    at = [i for i, l in enumerate(fl, 1) if _match_in(l, frags)]
                    where.append('%s %s' % (path, ('found at L' + ' · L'.join(map(str, at[:5])) + '') if at else 'not found'))
                notes.append('`%s` — not on the given lines (%s)' % (o[:60] + ('…' if len(o) > 60 else ''), '; '.join(where)))
        if status == 'match' and partial:
            status = 'partly compared'
        loc_txt = ' · '.join('%s %s' % (p or tok, ' '.join('L%d' % x for x in lns)) for tok, p, _r, lns in locs)
        rows.append((rid, n, status, [loc_txt] + notes if status == 'match' else notes))

    c.flush()
    counts = {}
    for rid, n, status, notes in rows:
        counts[status] = counts.get(status, 0) + 1
        mark = '  ' if status == 'match' else '! '
        print('%s%-6s %-8s %s' % (mark, rid, status, notes[0] if notes else ''))
        for x in notes[1:]:
            print('         %s' % x)
    if not rows:
        print('  ! no ID rows (`| ID | location | original → revision | … |`) could be read')
    print('Summary — ID rows: %d · %s' % (len(rows), ' · '.join('%s %d' % (k, v) for k, v in counts.items()) or 'none'))
    return 0 if rows and all(r[2] == 'match' for r in rows) else 1


def cmd_status(c, a):
    if c.base_real is None:
        marks, hows, n_lines = {}, {}, 0
        c.warn('No baseline file: %s — everything counts as left' % c.base_disp)
    else:
        marks, hows, n_lines = read_baseline(c.base_real, c.warn)
    collected = collect(c.root, c.settings, c.warn)
    c.flush()
    print('Baseline %s — %d mark lines%s · %d fingerprints' % (c.base_disp, n_lines,
          (' (' + ' · '.join('%s %d' % (k, v) for k, v in sorted(hows.items(), key=lambda x: str(x[0]))) + ')') if hows else '',
          len(marks)))
    print('  %-40s %-11s %6s %6s %6s' % ('source', 'kind', 'scope', 'done', 'left'))
    tot = [0, 0]
    for src, units, st, stats in collected:
        done = sum(1 for u in units if u.fp in marks)
        tot[0] += len(units)
        tot[1] += done
        extra = ''
        if st != 'ok':
            extra = '  (missing)' if st == 'missing' else '  (unreadable)'
        elif stats['glued']:
            extra = '  (blocks with a glued excluded-prefix line %d: L%s)' % (len(stats['glued']), ' · L'.join(map(str, stats['glued'][:6])))
        print('  %-40s %-11s %6d %6d %6d%s' % (src.file, src.kind, len(units), done, len(units) - done, extra))
    print('  %-40s %-11s %6d %6d %6d' % ('total', '', tot[0], tot[1], tot[0] - tot[1]))
    print('  (units count by position — the same text in two places counts twice)')
    left = c.leftover_packets()
    if left:
        print('  %d packet(s) left in %s — delete a packet once every unit is decided (%s)'
              % (len(left), c.disp(c.packet_dir), ' · '.join(left[:3]) + (' …' if len(left) > 3 else '')))
    return 0 if tot[0] == tot[1] and c.base_real is not None else 1


# ---------------------------------------------------------------- entry
def build_parser():
    # Common options may come before or after the command. Defaults are SUPPRESS so that a subparser does not overwrite a value given earlier with None.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--dir', default=argparse.SUPPRESS, help="project root (default: searched upward from this file's location or the current folder)")
    common.add_argument('--baseline', default=argparse.SUPPRESS, help='baseline file path (default .manuscript/grammar_baseline.jsonl)')
    ap = argparse.ArgumentParser(description='Baseline of the pre-submission grammar check — picks out only the changed paragraphs', parents=[common])
    sub = ap.add_subparsers(dest='cmd')
    p = sub.add_parser('init', parents=[common], help="first baseline (once, on the user's word)")
    p.add_argument('--confirm', metavar='WORDS', required=True)
    p = sub.add_parser('changed', parents=[common], help='units missing from the baseline')
    p.add_argument('--out', metavar='PACKET', nargs='?', const='',
                   help='packet file — without a path: grammar_packets/<time>_<computer>.json next to the baseline file')
    p = sub.add_parser('clean', parents=[common], help='record units with no findings')
    p.add_argument('--packet', metavar='PACKET', required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--ids', nargs='+', metavar='id')
    g.add_argument('--all-except', nargs='*', metavar='id')
    p = sub.add_parser('resolve', parents=[common], help='record the decision on a unit that had findings')
    p.add_argument('--packet', metavar='PACKET', required=True)
    p.add_argument('--id', required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--keep', action='store_true')
    g.add_argument('--replace', nargs='+', metavar='TEXT')
    p = sub.add_parser('verify', parents=[common], help='compare the originals of a candidate table with their locations')
    p.add_argument('candidates', metavar='CANDIDATES')
    sub.add_parser('status', parents=[common], help='per source: units in scope · recorded · left')
    return ap


def main(argv=None):
    _utf8_console()
    ap = build_parser()
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code not in (0, None) else 0
    a.dir = getattr(a, 'dir', None)
    a.baseline = getattr(a, 'baseline', None)
    if not a.cmd:
        ap.print_help()
        return 2
    c = None
    try:
        c = Ctx(a)
        return {'init': cmd_init, 'changed': cmd_changed, 'clean': cmd_clean, 'resolve': cmd_resolve,
                'verify': cmd_verify, 'status': cmd_status}[a.cmd](c, a)
    except UsageError as e:
        if c is not None:
            c.flush()
        print('Error: %s' % e)
        return 2


if __name__ == '__main__':
    sys.exit(main())
