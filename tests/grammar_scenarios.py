"""grammar_baseline.py scenarios — take one project folder and check the promises of the tool one by one.

No manuscript sentences or counts are hard-coded. Units to edit are picked from the settings and files of that project, changed, and checked by the output and exit code of the tool.
Picking units (blank-line blocks · region lines · JSON values) is implemented again separately from the tool, as a cross-check.
The synthetic fixture (test_grammar_baseline.py) and a copy of a real project (scripts/preview_projects.py --grammar) use the same functions.
Scenarios write only to a project copy.

Tool files — the four files of the canonical `new-manuscript/tools/` are copied into the `tools/` of the project and run from there.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
_T = HERE.parent / 'plugins' / 'research-writing' / 'skills' / 'new-manuscript' / 'tools'
# the tool and the modules every tool imports — the `required` entries of managed_files.json
_MANAGED = json.loads((_T.parent / 'managed_files.json').read_text(encoding='utf-8'))['files']
TOOL_FILES = [_T / 'grammar_baseline.py'] + [_T.parent / item['src'] for item in _MANAGED if item.get('required')]
PY = [sys.executable, '-X', 'utf8', '-B']
BASELINE_REL = '.manuscript/grammar_baseline.jsonl'
DEFAULT_CHAPTERS = ['ch%d.md' % i for i in (1, 2, 3, 4)]


def nfc(s):
    return unicodedata.normalize('NFC', s)


def norm(t):
    return nfc(t.replace('\r\n', '\n').replace('\r', '\n')).strip()


def fp(t):
    return hashlib.sha256(norm(t).encode('utf-8')).hexdigest()


def tree_hash(root: Path):
    """(path, content hash) of every file in a folder — checks the read-only promise."""
    out = {}
    for p in sorted(root.rglob('*')):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
        elif p.is_dir():
            out[p.relative_to(root).as_posix() + '/'] = ''
    return out


def find_real(root: Path, rel: str):
    """Find the actual path by comparing in NFC (implemented separately from the tool)."""
    cur = root
    for seg in rel.replace('\\', '/').split('/'):
        if seg in ('', '.'):
            continue
        if seg == '..':
            cur = cur.parent
            continue
        nxt = cur / seg
        if nxt.exists():
            cur = nxt
            continue
        hit = [n for n in os.listdir(cur)] if cur.is_dir() else []
        hit = [n for n in hit if nfc(n) == nfc(seg)]
        if not hit:
            return None
        cur = cur / hit[0]
    return cur


class Proj(object):
    """One project copy to test. With tool_dir, the tool is kept outside the project and run with --dir."""

    def __init__(self, root: Path, state_home: Path, tool_dir: Path | None = None):
        self.root = Path(root)
        self.state = Path(state_home)
        self.tool_dir = Path(tool_dir) if tool_dir else self.root / 'tools'
        self.log = []

    # ---- tool
    def install(self):
        self.tool_dir.mkdir(parents=True, exist_ok=True)
        for f in TOOL_FILES:
            shutil.copyfile(f, self.tool_dir / f.name)

    def run(self, *args, codes=(0,), cwd=None):
        env = dict(os.environ, SYNC_STATE_HOME=str(self.state), PYTHONIOENCODING='utf-8')
        cmd = PY + [str(self.tool_dir / 'grammar_baseline.py')] + [str(a) for a in args]
        r = subprocess.run(cmd, cwd=str(cwd or self.root), capture_output=True, text=True, encoding='utf-8',
                           errors='replace', env=env, timeout=600)
        self.log.append((args, r.returncode, r.stdout + r.stderr))
        assert codes is None or r.returncode in codes, \
            'exit code %d (expected %s): %s\n%s%s' % (r.returncode, codes, ' '.join(map(str, args)), r.stdout, r.stderr)
        return r

    # ---- settings · sources
    @property
    def cfg_path(self):
        return self.root / '.manuscript' / 'project.json'

    def cfg(self):
        return json.loads(self.cfg_path.read_text(encoding='utf-8-sig'))

    def set_cfg(self, raw):
        self.cfg_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def sources(self):
        """[(path relative to the root, kind, regions)] — the default scope (chapter files, references excluded) + grammar.sources. Existing files only."""
        c = self.cfg()
        m = c.get('manuscript', {})
        src = m.get('source_dir', 'manuscript_src')
        base = (src.strip('/') + '/') if (self.root / src).is_dir() else ''
        refs = m.get('references', 'references.md')
        chapters = [x['file'] for x in m.get('chapters', [{'file': f} for f in DEFAULT_CHAPTERS])]
        out = [(base + f, 'md', []) for f in chapters if f != refs]
        for s in c.get('grammar', {}).get('sources', []):
            out.append((s['file'], s.get('kind', 'md'), s.get('regions', [])))
        seen, res = set(), []
        for f, k, r in out:
            key = (nfc(f), k, json.dumps(r))
            if key in seen or find_real(self.root, f) is None:
                continue
            seen.add(key)
            res.append((nfc(f), k, r))
        return res

    def md_files(self):
        return [f for f, k, _r in self.sources() if k == 'md']

    # ---- reading and writing files (line endings and BOM preserved)
    def read(self, rel):
        data = find_real(self.root, rel).read_bytes()
        bom = data.startswith(b'\xef\xbb\xbf')
        text = data[3 if bom else 0:].decode('utf-8')
        nl = '\r\n' if '\r\n' in text else '\n'
        return text.replace('\r\n', '\n'), nl, bom

    def write(self, rel, text_lf, nl, bom):
        data = text_lf.replace('\n', nl).encode('utf-8')
        find_real(self.root, rel).write_bytes((b'\xef\xbb\xbf' if bom else b'') + data)

    def replace_once(self, rel, old, new):
        text, nl, bom = self.read(rel)
        n = text.count(old)
        assert n == 1, '%s: target occurs %d times: %r' % (rel, n, old[:60])
        self.write(rel, text.replace(old, new, 1), nl, bom)

    def blocks(self, rel, exclude=('@',)):
        """[(start line, block text)] — blocks separated by blank lines that do not start with exclude."""
        text, _nl, _bom = self.read(rel)
        out, cur, start = [], [], 0
        for n, line in enumerate(text.split('\n') + [''], 1):
            if line.strip():
                if not cur:
                    start = n
                cur.append(line)
            elif cur:
                b = '\n'.join(cur)
                if not b.lstrip().startswith(exclude):
                    out.append((start, b))
                cur = []
        return out

    def all_md_texts(self):
        return [norm(b) for f in self.md_files() for _l, b in self.blocks(f, exclude=('\0',))]

    def eligible(self, n=1, rel=None, one_line=False):
        """n paragraphs to edit — not starting with `@`, at least six words, once in the file and once in the whole scope, no backticks or `|`."""
        texts = self.all_md_texts()
        out = []
        for f in ([rel] if rel else self.md_files()):
            body, _nl, _bom = self.read(f)
            for line, b in self.blocks(f):
                if len(b.split()) < 6 or '`' in b or '|' in b or (one_line and '\n' in b):
                    continue
                if body.count(b) != 1 or texts.count(norm(b)) != 1:
                    continue
                out.append((f, line, b))
                if n is not None and len(out) >= n:
                    return out
        assert n is None or len(out) >= n, 'could not find %d paragraphs to edit' % n
        return out

    # ---- reading tool output
    @staticmethod
    def listed(out):
        """changed output → [(id, location text)]"""
        return re.findall(r'^\[([0-9a-f]{12})\] (.+)$', out, re.M)

    def baseline(self):
        return find_real(self.root, BASELINE_REL)

    def baseline_bytes(self):
        p = self.baseline()
        return p.read_bytes() if p else None


def insert_token(block, token):
    """Insert one word before the closing punctuation of a block (at the end if there is none)."""
    b = block.rstrip()
    if b and b[-1] in '.:;)':
        return b[:-1] + ' ' + token + b[-1] + block[len(b):]
    return b + ' ' + token + block[len(b):]


# ================================================================ scenarios
# Every scenario starts from an initialized project (baseline = the current manuscript) and restores the manuscript at the end (the baseline may grow).

def s_init_clean_and_refuse(p: Proj):
    p.run('changed')                                                         # 0 right after init
    before = p.baseline_bytes()
    r = p.run('init', '--confirm', 'second', codes=(2,))
    assert 'already exists' in r.stdout
    assert p.baseline_bytes() == before
    st = p.run('status')
    assert re.search(r'total\s+\S*\s*(\d+)\s+\1\s+0', st.stdout), st.stdout
    return 'changed 0 after init · init refused again (baseline bytes unchanged) · status remaining 0'


def s_edit_then_revert(p: Proj):
    f, line, b = p.eligible(1)[0]
    new = insert_token(b, 'ZZEDIT')
    p.replace_once(f, b, new)
    r = p.run('changed', codes=(1,))
    got = p.listed(r.stdout)
    assert got == [(fp(new)[:12], '%s L%d' % (f, line))], (got, f, line)
    assert 'ZZEDIT' in r.stdout
    p.replace_once(f, new, b)
    p.run('changed')
    return 'only the edited paragraph is listed (id, file and line match) · 0 after reverting — %s L%d' % (f, line)


def s_reorder(p: Proj):
    picks = None
    for f in p.md_files():
        try:
            picks = p.eligible(2, rel=f)
            break
        except AssertionError:
            continue
    assert picks, 'could not find two paragraphs in the same file'
    (f, _l1, a), (_f, _l2, b) = picks
    text, nl, bom = p.read(f)
    mark = '\0SWAP\0'
    t2 = text.replace(a, mark, 1).replace(b, a, 1).replace(mark, b, 1)
    p.write(f, t2, nl, bom)
    p.run('changed')
    p.write(f, text, nl, bom)
    return '0 even when two paragraphs of the same file swap places — %s' % f


def s_new_paragraph(p: Proj):
    f, _line, b = p.eligible(1)[0]
    added = 'ZZNEW This sentence is a new paragraph added for the test of the baseline tool.'
    p.replace_once(f, b, b + '\n\n' + added)
    r = p.run('changed', codes=(1,))
    got = p.listed(r.stdout)
    assert len(got) == 1 and got[0][0] == fp(added)[:12], got
    p.replace_once(f, b + '\n\n' + added, b)
    p.run('changed')
    return 'only the new paragraph is listed · 0 after deleting it'


def s_note_only(p: Proj):
    for f in p.md_files():
        notes = [(l, b) for l, b in p.blocks(f, exclude=('\0',)) if b.lstrip().startswith('@NOTE')]
        body, _nl, _bom = p.read(f)
        notes = [(l, b) for l, b in notes if body.count(b) == 1]
        if notes:
            _l, b = notes[0]
            p.replace_once(f, b, b + ' (test note added)')
            p.run('changed')
            p.replace_once(f, b + ' (test note added)', b)
            how = 'edited an existing @NOTE'
            break
    else:
        f, _line, b = p.eligible(1)[0]
        note = '@NOTE test note — must be out of scope'
        p.replace_once(f, b, b + '\n\n' + note)
        p.run('changed')
        p.replace_once(f, b + '\n\n' + note, b)
        how = 'added a new @NOTE block'
    p.run('changed')
    return '0 when only an @NOTE changes (%s — %s)' % (how, f)


def s_clean_race(p: Proj, work: Path):
    f, line, b = p.eligible(1)[0]
    a1 = insert_token(b, 'ZZONE')
    p.replace_once(f, b, a1)
    pk = work / 'packet_race.json'
    p.run('changed', '--out', pk, codes=(1,))
    a2 = insert_token(a1, 'ZZTWO')                                           # someone edits it again during the check
    p.replace_once(f, a1, a2)
    r = p.run('clean', '--packet', pk, '--all-except')
    assert 'recorded 1' in r.stdout, r.stdout
    r = p.run('changed', codes=(1,))
    assert p.listed(r.stdout) == [(fp(a2)[:12], '%s L%d' % (f, line))], p.listed(r.stdout)
    p.replace_once(f, a2, a1)                                                # back to the text of the packet it counts as recorded, so 0
    p.run('changed')
    p.replace_once(f, a1, b)
    p.run('changed')
    r = p.run('changed', '--out', pk, codes=(0,))                            # nothing changed — no packet is made · the existing packet stays
    assert 'no packet was made' in r.stdout
    return 'clean records only the fingerprints of the packet — a paragraph edited again in between is listed again · 0 with the text of the packet'


def s_partial_stamp(p: Proj, work: Path):
    """A unit not yet decided stays — edit two and clean only one, then only the other remains, and recording it with a two-part replace gives 0."""
    (fa, _la, a), (fb, _lb, b) = p.eligible(2)
    a1 = insert_token(insert_token(a, 'ZZERRA'), 'ZZERRB')
    b1 = insert_token(b, 'ZZCLEAN')
    p.replace_once(fa, a, a1)
    p.replace_once(fb, b, b1)
    pk = work / 'packet_partial.json'
    r = p.run('changed', '--out', pk, codes=(1,))
    assert {i for i, _w in p.listed(r.stdout)} == {fp(a1)[:12], fp(b1)[:12]}, p.listed(r.stdout)
    r = p.run('clean', '--packet', pk, '--all-except', fp(a1)[:12])
    assert 'recorded 1' in r.stdout, r.stdout
    r = p.run('changed', codes=(1,))
    assert [i for i, _w in p.listed(r.stdout)] == [fp(a1)[:12]], p.listed(r.stdout)        # only A, not yet decided, remains
    a2 = a1.replace('ZZERRA', 'ZZFIXA', 1).replace('ZZERRB', 'ZZFIXB', 1)
    p.replace_once(fa, a1, a2)
    r = p.run('resolve', '--packet', pk, '--id', fp(a1)[:12], '--replace', 'ZZERRA', 'ZZFIXA', 'ZZERRB', 'ZZFIXB')
    assert fp(a2)[:12] in r.stdout, r.stdout
    p.run('changed')
    fc, _lc, cc = next(x for x in p.eligible(None) if 'ZZ' not in x[2])        # a third unit not yet touched
    c1 = insert_token(cc, 'ZZIDS')
    p.replace_once(fc, cc, c1)
    pk2 = work / 'packet_ids.json'
    p.run('changed', '--out', pk2, codes=(1,))
    r = p.run('clean', '--packet', pk2, '--ids', fp(c1)[:12])
    assert 'recorded 1' in r.stdout, r.stdout
    p.run('changed')
    p.replace_once(fa, a2, a)
    p.replace_once(fb, b1, b)
    p.replace_once(fc, c1, cc)
    p.run('changed')
    return 'edit two and record only one with --all-except A: only A remains · record A with a two-part --replace: 0 · record with --ids: 0'


def s_replace_pass(p: Proj, work: Path):
    f, line, b = p.eligible(1)[0]
    b1 = insert_token(b, 'ZZERR')
    p.replace_once(f, b, b1)
    pk = work / 'packet_pass.json'
    p.run('changed', '--out', pk, codes=(1,))
    b2 = b1.replace('ZZERR', 'ZZFIX', 1)
    p.replace_once(f, b1, b2)                                                # apply the approved revision
    r = p.run('resolve', '--packet', pk, '--id', fp(b1)[:12], '--replace', 'ZZERR', 'ZZFIX')
    assert 'recorded' in r.stdout and fp(b2)[:12] in r.stdout, r.stdout
    p.run('changed')
    lines = p.baseline().read_text(encoding='utf-8').splitlines()
    last = json.loads(lines[-1])
    assert last['how'] == 'replace' and last['fingerprint'] == fp(b2) and last['file'] == f, last      # new lines use the English keys
    p.replace_once(f, b2, b)
    p.run('changed')
    return 'resolve --replace passes — replaced text = current manuscript → its fingerprint is recorded as replace'


def s_replace_mismatch(p: Proj, work: Path):
    f, _line, b = p.eligible(1)[0]
    c1 = insert_token(b, 'ZZERR')
    p.replace_once(f, b, c1)
    pk = work / 'packet_mismatch.json'
    p.run('changed', '--out', pk, codes=(1,))
    c2 = c1.replace('ZZERR', 'ZZOTHER', 1)                                   # a different revision from the decided one went in
    p.replace_once(f, c1, c2)
    before = p.baseline_bytes()
    r = p.run('resolve', '--packet', pk, '--id', fp(c1)[:12], '--replace', 'ZZERR', 'ZZFIX', codes=(1,))
    assert 'Not recorded' in r.stdout and '[-' in r.stdout and 'ZZOTHER' in r.stdout, r.stdout
    assert p.baseline_bytes() == before
    r = p.run('resolve', '--packet', pk, '--id', fp(c1)[:12], '--replace', 'ZZNOPE', 'x', codes=(2,))
    assert 'exactly once' in r.stdout
    assert p.baseline_bytes() == before
    p.replace_once(f, c2, b)
    p.run('changed')
    return 'resolve --replace mismatch — nothing recorded, the difference shown, 1 · original not in the packet: 2 · baseline bytes unchanged'


def s_keep(p: Proj, work: Path):
    f, _line, b = p.eligible(1)[0]
    k1 = insert_token(b, 'ZZKEEP')
    p.replace_once(f, b, k1)
    pk = work / 'packet_keep.json'
    p.run('changed', '--out', pk, codes=(1,))
    r = p.run('resolve', '--packet', pk, '--id', fp(k1)[:8], '--keep')     # the first 8 characters of an id also work
    assert 'recorded' in r.stdout
    p.run('changed')
    last = json.loads(p.baseline().read_text(encoding='utf-8').splitlines()[-1])
    assert last['how'] == 'keep' and last['fingerprint'] == fp(k1)
    p.replace_once(f, k1, b)
    p.run('changed')
    return 'resolve --keep records the fingerprint of the packet as keep'


def s_line_endings(p: Proj):
    f = p.md_files()[0]
    text, nl, bom = p.read(f)
    other = '\n' if nl == '\r\n' else '\r\n'
    p.write(f, text, other, bom)
    p.run('changed')
    p.write(f, text, nl, bom)
    return 'the same text with only the line endings changed has the same fingerprint — %s (%s → %s)' % (f, 'CRLF' if nl == '\r\n' else 'LF', 'LF' if nl == '\r\n' else 'CRLF')


def _regions(lines, regions):
    """A region implemented separately from the tool — from the start line up to just before the end line, searched from the next line on."""
    keep = set()
    for r in regions:
        s, e = re.compile(r['start']), re.compile(r['end'])
        i = 0
        while i < len(lines):
            if s.search(lines[i]):
                j = i + 1
                while j < len(lines) and not e.search(lines[j]):
                    j += 1
                keep.update(k for k in range(i, j) if lines[k].strip())
                i = j
            else:
                i += 1
    return keep


def _json_split(v, muted=False, out=None):
    """(set of comment-field values, set of the other values) — strings under a key that starts with `_` are comment fields (implemented separately from the tool)."""
    if out is None:
        out = (set(), set())
    if isinstance(v, str):
        out[0 if muted else 1].add(v)
    elif isinstance(v, list):
        for x in v:
            _json_split(x, muted, out)
    elif isinstance(v, dict):
        for k, x in v.items():
            _json_split(x, muted or k.startswith('_'), out)
    return out


def s_lines_and_json(p: Proj):
    done = []
    for f, kind, regions in p.sources():
        if kind == 'lines' and regions:
            text, nl, bom = p.read(f)
            lines = text.split('\n')
            inside = sorted(_regions(lines, regions))
            assert inside, '%s: the region is empty' % f
            k = next((i for i in inside if ("'" in lines[i] or '"' in lines[i]) and text.count(lines[i]) == 1), inside[0])
            old = lines[k]
            lines[k] = old.rstrip() + '  # ZZLINE'
            p.write(f, '\n'.join(lines), nl, bom)
            r = p.run('changed', codes=(1,))
            assert p.listed(r.stdout) == [(fp(lines[k])[:12], '%s L%d' % (f, k + 1))], p.listed(r.stdout)
            lines[k] = old
            outside = [i for i, l in enumerate(lines) if l.strip() and i not in set(inside)]
            if outside:
                o = outside[0]
                lines[o] = lines[o].rstrip() + '  # ZZOUT'
                p.write(f, '\n'.join(lines), nl, bom)
                p.run('changed')                                                  # outside the region is not a unit
            p.write(f, text, nl, bom)
            p.run('changed')
            done.append('lines %s L%d listed · a line outside the region gives 0' % (f, k + 1))
        if kind == 'json-values':
            text, nl, bom = p.read(f)
            muted, live = _json_split(json.loads(text))
            toks = list(re.finditer(r'"(?:[^"\\]|\\.)*"', text))
            is_key = lambda m: text[m.end():].lstrip(' \t\n').startswith(':')                    # noqa: E731
            vals = [m for m in toks if not is_key(m) and text.count(m.group()) == 1
                    and json.loads(m.group()) not in muted and len(json.loads(m.group()).split()) >= 3]
            keys = [m for m in toks if is_key(m) and text.count(m.group()) == 1]
            notes = [m for m in toks if not is_key(m) and text.count(m.group()) == 1
                     and json.loads(m.group()) in muted and json.loads(m.group()) not in live]
            m = vals[0]
            new_tok = m.group()[:-1] + ' ZZJSON"'
            p.write(f, text.replace(m.group(), new_tok, 1), nl, bom)
            r = p.run('changed', codes=(1,))
            line = text.count('\n', 0, m.start()) + 1
            assert p.listed(r.stdout) == [(fp(json.loads(new_tok))[:12], '%s L%d' % (f, line))], p.listed(r.stdout)
            p.write(f, text, nl, bom)
            if keys:
                k = keys[-1]
                p.write(f, text.replace(k.group(), k.group()[:-1] + 'ZZ"', 1), nl, bom)
                p.run('changed')                                                  # a key is not a unit
                p.write(f, text, nl, bom)
            if notes:
                n = notes[0]
                p.write(f, text.replace(n.group(), n.group()[:-1] + ' ZZNOTE"', 1), nl, bom)
                p.run('changed')                                                  # a value under a `_` key is not a unit
                p.write(f, text, nl, bom)
            p.run('changed')
            done.append('json %s L%d value listed · 0 when only a key changes%s' % (f, line, ' · 0 when a `_` key value changes' if notes else ''))
    return ' · '.join(done) or 'not applicable (no lines or json-values source)'


def s_packet_default(p: Proj):
    """changed --out without a path — grammar_packets/<time>_<computer>.json next to the baseline file · status reports the remaining packets · recording with that packet gives 0."""
    d = p.baseline().parent / 'grammar_packets'
    had = d.is_dir()
    before = set(os.listdir(d)) if had else set()
    f, _line, b = p.eligible(1)[0]
    b1 = insert_token(b, 'ZZPACK')
    p.replace_once(f, b, b1)
    r = p.run('changed', '--out', codes=(1,))
    new = sorted(set(os.listdir(d)) - before)
    # no spaces — so it does not collide with conflict-copy names. Hangul is allowed on purpose: the computer name may be Korean
    assert len(new) == 1 and re.fullmatch(r'\d{8}-\d{6}_[0-9A-Za-z가-힣-]+\.json', nfc(new[0])), new
    assert ('grammar_packets/' + nfc(new[0])) in nfc(r.stdout).replace('\\', '/'), r.stdout
    st = p.run('status', codes=(1,))
    assert '%d packet(s) left' % (len(before) + 1) in st.stdout, st.stdout
    p.run('clean', '--packet', d / new[0], '--all-except')
    p.run('changed')
    (d / new[0]).unlink()
    if not had:
        d.rmdir()
    p.replace_once(f, b1, b)
    p.run('changed')
    return '--out without a path — grammar_packets/%s next to the baseline · status reports the remaining packets · recording with that packet gives 0' % new[0]


def s_nfd_names(p: Proj):
    done = []
    base = p.baseline()
    nfd = base.with_name(unicodedata.normalize('NFD', base.name))
    os.rename(base, nfd)
    try:
        if not (base.parent / nfc(base.name)).exists():                       # NTFS — NFC and NFD names are different files
            done.append('baseline file name in NFD')
        p.run('changed')
        r = p.run('init', '--confirm', 'x', codes=(2,))
        assert 'already exists' in r.stdout
    finally:
        os.rename(nfd, base)
    for f, _k, _r in p.sources():
        name = f.rsplit('/', 1)[-1]
        if name.isascii():
            continue
        st0 = p.run('status').stdout
        real = find_real(p.root, f)
        to = real.with_name(unicodedata.normalize('NFD', real.name))
        os.rename(real, to)
        try:
            st1 = p.run('status').stdout
        finally:
            os.rename(to, real)
        row0 = [l for l in st0.splitlines() if l.strip().startswith(f + ' ')]
        row1 = [l for l in st1.splitlines() if l.strip().startswith(f + ' ')]
        assert row0 and row0 == row1, (row0, row1)
        done.append('source `%s` in NFD — status unchanged' % f)
        break
    return ' · '.join(done) + ' · changed 0 · init refused'


def s_warnings(p: Proj):
    raw = p.cfg()
    orig = json.dumps(raw, ensure_ascii=False)
    md0 = p.md_files()[0]
    first = next(l for l in p.read(md0)[0].split('\n') if l.strip())
    g = raw.setdefault('grammar', {})
    g['zzunknown'] = 1
    g.setdefault('sources', [])
    g['sources'] = g['sources'] + [
        {'file': 'zz_missing_file.md'},
        {'file': md0, 'kind': 'zzkind'},
        {'file': md0, 'kind': 'lines', 'regions': [{'start': '^ZZ_NO_SUCH_START', 'end': '^ZZ'}]},
        {'file': md0, 'kind': 'lines', 'regions': [{'start': '^' + re.escape(first), 'end': '^ZZ_NO_END'}], 'zzkey': 1},
    ]
    p.set_cfg(raw)
    try:
        out = p.run('status', codes=(0, 1)).stdout
        for want in ('Unknown key `zzunknown`', 'Source `zz_missing_file.md` is missing', 'unknown kind `zzkind`', 'region start marker `^ZZ_NO_SUCH_START`',
                     'region end marker `^ZZ_NO_END`', 'unknown key `zzkey`', 'has 0 units'):
            assert want in out, (want, out)
        raw2 = json.loads(orig)
        raw2.setdefault('grammar', {})['sources'] = [{'file': md0, 'kind': 'lines', 'regions': [{'start': 1}]}]
        p.set_cfg(raw2)
        out = p.run('status', codes=(2,)).stdout
        assert 'start' in out
    finally:
        p.set_cfg(json.loads(orig))
    p.run('changed')
    return 'unknown key · unknown kind · missing file · region start and end marker not found · 0-unit warning · a malformed region gives 2'


def s_verify(p: Proj, work: Path):
    f, line, b = p.eligible(1, one_line=True)[0]
    words = b.split()
    frag = ' '.join(words[1:6])
    head2, tail2 = ' '.join(words[1:3]), ' '.join(words[4:6])
    text, _nl, _bom = p.read(f)
    lines = text.split('\n')
    other = next(i + 1 for i, l in enumerate(lines) if l.strip() and frag not in l)
    name = f.rsplit('/', 1)[-1]
    cand = work / 'candidates_test.md'
    rows = ['| ID | Location | Original → Revision | Reason |', '|---|---|---|---|',
            '| G1 | `%s` L%d | `%s` → `x` | right |' % (name, line, frag),
            '| G2 | `%s` L%d | `%s` → `x` | another line |' % (name, other, frag),
            '| G3 | two places below | `%s` → `x` | no location |' % frag,
            '| G4 | `%s` L%d | `%s … %s` → `x` | elided |' % (name, line, head2, tail2)]
    cand.write_text('\n'.join(rows + ['| **G5** | `%s` L%d | `%s` → `x` | decorated ID |' % (name, line, frag)]) + '\n',
                    encoding='utf-8')
    r = p.run('verify', cand, codes=(1,))
    assert 'looks like row `G5`' in r.stdout, r.stdout
    st = dict(re.findall(r'^[ !] (G\d)\s+(match|mismatch|not compared|partly compared)\b', r.stdout, re.M))
    assert st.get('G1') == 'match' and st.get('G2') == 'mismatch' and st.get('G3', '').startswith('not compared') and st.get('G4') == 'match', \
        (st, r.stdout)
    hint = next(l for l in r.stdout.splitlines() if 'not on the given lines' in l)
    assert re.search(r'\bL%d\b' % line, hint) and 'found at' in hint, r.stdout
    cand2 = work / 'candidates_test_pass.md'
    cand2.write_text('\n'.join(rows[:3] + rows[5:]) + '\n', encoding='utf-8')
    p.run('verify', cand2)
    return 'verify — the right line matches · another line is a mismatch (the line where it is found is shown) · no location is not compared · an elision (…) matches · a passing file gives 0'


def s_readonly(project: Path, state: Path, outside: Path, candidates: Path | None = None):
    """Use from the pre-submission check — the tool is kept outside the project and reads it only through --dir and --baseline. Checks that the project bytes are unchanged."""
    before = tree_hash(project)
    q = Proj(project, state, tool_dir=outside / 'tools')
    q.install()
    base = outside / 'baseline_store' / 'grammar_baseline.jsonl'
    common = ['--dir', project, '--baseline', base]
    q.run(*common, 'status', codes=(1,), cwd=outside)
    q.run(*common, 'init', '--confirm', 'test phrase', cwd=outside)
    q.run(*common, 'changed', cwd=outside)
    q.run(*common, 'status', cwd=outside)
    if candidates is not None:
        q.run(*common, 'verify', candidates, codes=(0, 1), cwd=outside)
    q.run('changed', '--dir', project, '--baseline', base, cwd=outside)      # common options also work after the command
    after = tree_hash(project)
    assert before == after, sorted(set(before.items()) ^ set(after.items()))[:10]
    n = len(base.read_text(encoding='utf-8').splitlines())
    first = json.loads(base.read_text(encoding='utf-8').splitlines()[0])
    assert first['how'] == 'init' and first['phrase'] == 'test phrase'
    assert b'\r' not in base.read_bytes()
    return q, 'tool outside the project + --dir · --baseline — after init · status · changed · verify, %d project files have unchanged bytes · baseline %d lines (LF)' \
        % (len([k for k in before if not k.endswith('/')]), n)


SCENARIOS = [
    ('init_refuse', s_init_clean_and_refuse, False),
    ('edit_revert', s_edit_then_revert, False),
    ('reorder', s_reorder, False),
    ('new_paragraph', s_new_paragraph, False),
    ('note_only', s_note_only, False),
    ('clean_race', s_clean_race, True),
    ('partial_stamp', s_partial_stamp, True),
    ('replace_pass', s_replace_pass, True),
    ('replace_mismatch', s_replace_mismatch, True),
    ('keep', s_keep, True),
    ('line_endings', s_line_endings, False),
    ('lines_json', s_lines_and_json, False),
    ('packet_default', s_packet_default, False),
    ('nfd_names', s_nfd_names, False),
    ('warnings', s_warnings, False),
    ('verify', s_verify, True),
]


def run_scenario(fn, needs_work, project: Path, state: Path, work: Path):
    """Run one scenario on an initialized project. Also checks that the manuscript is back to what it was.
    work — the folder for packet and candidate files. The caller chooses it and deletes it (for a real copy, inside the same work folder as the copy)."""
    p = Proj(project, state)
    p.install()
    work.mkdir(parents=True, exist_ok=True)
    if p.baseline() is None:
        p.run('init', '--confirm', 'test baseline')
    src_before = {f: p.read(f) for f, _k, _r in p.sources()}
    msg = fn(p, work) if needs_work else fn(p)
    for f, v in src_before.items():
        assert p.read(f) == v, '%s differs from the start' % f
    return p, msg
