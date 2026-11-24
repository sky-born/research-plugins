"""grammar_baseline.py 시나리오 — 프로젝트 폴더 하나를 받아 도구의 약속을 차례로 확인합니다.

원고 문장 · 개수를 박지 않습니다. 그 프로젝트의 설정과 파일에서 고칠 단위를 골라 바꾸고, 도구의 출력과 종료 코드로 확인합니다.
단위 고르기(빈 줄 블록 · 구간 줄 · JSON 값)는 도구와 따로 다시 구현해 교차 확인이 되게 합니다.
합성 표본(test_grammar_baseline.py)과 실제 프로젝트 사본(scripts/preview_projects.py --grammar)이 같은 함수를 씁니다.
시나리오는 프로젝트 사본에만 씁니다.

도구 파일 — 정본 `new-manuscript/tools/` 의 네 파일을 프로젝트의 `tools/` 로 복사해 돌립니다.
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
TOOL_FILES = [_T / n for n in ('grammar_baseline.py', '_config.py', '_location.py', '_sync.py')]
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
    """폴더 안 모든 파일의 (경로, 내용 해시) — 읽기 전용 약속을 확인합니다."""
    out = {}
    for p in sorted(root.rglob('*')):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
        elif p.is_dir():
            out[p.relative_to(root).as_posix() + '/'] = ''
    return out


def find_real(root: Path, rel: str):
    """NFC 로 대조해 실제 경로를 찾습니다(도구와 따로 구현)."""
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
    """시험할 프로젝트 사본 하나. tool_dir 를 주면 도구를 프로젝트 밖에 두고 --dir 로 돌립니다."""

    def __init__(self, root: Path, state_home: Path, tool_dir: Path | None = None):
        self.root = Path(root)
        self.state = Path(state_home)
        self.tool_dir = Path(tool_dir) if tool_dir else self.root / 'tools'
        self.log = []

    # ---- 도구
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
            '종료 코드 %d (기대 %s): %s\n%s%s' % (r.returncode, codes, ' '.join(map(str, args)), r.stdout, r.stderr)
        return r

    # ---- 설정 · 원본
    @property
    def cfg_path(self):
        return self.root / '.manuscript' / 'project.json'

    def cfg(self):
        return json.loads(self.cfg_path.read_text(encoding='utf-8-sig'))

    def set_cfg(self, raw):
        self.cfg_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def sources(self):
        """[(루트 기준 경로, kind, regions)] — 기본 범위(장 파일, 참고문헌 제외) + grammar.sources. 있는 파일만."""
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

    # ---- 파일 읽고 쓰기(줄끝 · BOM 보존)
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
        assert n == 1, '%s 에 대상이 %d번: %r' % (rel, n, old[:60])
        self.write(rel, text.replace(old, new, 1), nl, bom)

    def blocks(self, rel, exclude=('@',)):
        """[(시작 줄, 블록 글)] — 빈 줄로 나뉜 블록 가운데 exclude 로 시작하지 않는 것."""
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
        """고쳐 볼 문단 n 개 — `@` 로 시작하지 않고 여섯 낱말 이상, 파일 안에서 한 번 · 범위 전체에서 한 번, 백틱 · `|` 없음."""
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
        assert n is None or len(out) >= n, '고칠 문단을 %d개 찾지 못했습니다' % n
        return out

    # ---- 도구 출력 읽기
    @staticmethod
    def listed(out):
        """changed 출력 → [(id, 위치 글)]"""
        return re.findall(r'^\[([0-9a-f]{12})\] (.+)$', out, re.M)

    def baseline(self):
        return find_real(self.root, BASELINE_REL)

    def baseline_bytes(self):
        p = self.baseline()
        return p.read_bytes() if p else None


def insert_token(block, token):
    """블록 끝 문장부호 앞에 낱말 하나를 넣습니다(없으면 끝에)."""
    b = block.rstrip()
    if b and b[-1] in '.:;)':
        return b[:-1] + ' ' + token + b[-1] + block[len(b):]
    return b + ' ' + token + block[len(b):]


# ================================================================ 시나리오
# 모두 init 된 프로젝트(기준 = 지금 원고)에서 시작해, 끝나면 원고를 처음대로 되돌립니다(기준은 늘어날 수 있음).

def s_init_clean_and_refuse(p: Proj):
    p.run('changed')                                                         # init 직후 0
    before = p.baseline_bytes()
    r = p.run('init', '--confirm', '두 번째', codes=(2,))
    assert '이미 있습니다' in r.stdout
    assert p.baseline_bytes() == before
    st = p.run('status')
    assert re.search(r'합계\s+\S*\s*(\d+)\s+\1\s+0', st.stdout), st.stdout
    return 'init 뒤 changed 0 · init 다시 거절(기준 바이트 그대로) · status 남음 0'


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
    return '고친 문단만 나옴(id · 파일 · 줄 일치) · 되돌리면 0 — %s L%d' % (f, line)


def s_reorder(p: Proj):
    picks = None
    for f in p.md_files():
        try:
            picks = p.eligible(2, rel=f)
            break
        except AssertionError:
            continue
    assert picks, '같은 파일에서 문단 둘을 찾지 못했습니다'
    (f, _l1, a), (_f, _l2, b) = picks
    text, nl, bom = p.read(f)
    mark = '\0SWAP\0'
    t2 = text.replace(a, mark, 1).replace(b, a, 1).replace(mark, b, 1)
    p.write(f, t2, nl, bom)
    p.run('changed')
    p.write(f, text, nl, bom)
    return '같은 파일의 두 문단 순서를 바꿔도 0 — %s' % f


def s_new_paragraph(p: Proj):
    f, _line, b = p.eligible(1)[0]
    added = 'ZZNEW This sentence is a new paragraph added for the test of the baseline tool.'
    p.replace_once(f, b, b + '\n\n' + added)
    r = p.run('changed', codes=(1,))
    got = p.listed(r.stdout)
    assert len(got) == 1 and got[0][0] == fp(added)[:12], got
    p.replace_once(f, b + '\n\n' + added, b)
    p.run('changed')
    return '새 문단 하나만 나옴 · 지우면 0'


def s_note_only(p: Proj):
    for f in p.md_files():
        notes = [(l, b) for l, b in p.blocks(f, exclude=('\0',)) if b.lstrip().startswith('@NOTE')]
        body, _nl, _bom = p.read(f)
        notes = [(l, b) for l, b in notes if body.count(b) == 1]
        if notes:
            _l, b = notes[0]
            p.replace_once(f, b, b + ' (시험 메모 추가)')
            p.run('changed')
            p.replace_once(f, b + ' (시험 메모 추가)', b)
            how = '있던 @NOTE 고침'
            break
    else:
        f, _line, b = p.eligible(1)[0]
        note = '@NOTE 시험 메모 — 범위 밖이어야 함'
        p.replace_once(f, b, b + '\n\n' + note)
        p.run('changed')
        p.replace_once(f, b + '\n\n' + note, b)
        how = '@NOTE 블록 새로 넣음'
    p.run('changed')
    return '@NOTE 만 바뀌면 0 (%s — %s)' % (how, f)


def s_clean_race(p: Proj, work: Path):
    f, line, b = p.eligible(1)[0]
    a1 = insert_token(b, 'ZZONE')
    p.replace_once(f, b, a1)
    pk = work / 'packet_race.json'
    p.run('changed', '--out', pk, codes=(1,))
    a2 = insert_token(a1, 'ZZTWO')                                           # 점검하는 사이에 누가 또 고침
    p.replace_once(f, a1, a2)
    r = p.run('clean', '--packet', pk, '--all-except')
    assert '찍음 1' in r.stdout, r.stdout
    r = p.run('changed', codes=(1,))
    assert p.listed(r.stdout) == [(fp(a2)[:12], '%s L%d' % (f, line))], p.listed(r.stdout)
    p.replace_once(f, a2, a1)                                                # 묶음의 글로 돌리면 찍힌 것이라 0
    p.run('changed')
    p.replace_once(f, a1, b)
    p.run('changed')
    r = p.run('changed', '--out', pk, codes=(0,))                            # 바뀐 것 없음 — 묶음을 만들지 않음 · 기존 묶음 그대로
    assert '만들지 않았습니다' in r.stdout
    return 'clean 은 묶음의 지문만 찍음 — 그사이 또 고친 문단은 다시 나옴 · 묶음의 글로 돌리면 0'


def s_partial_stamp(p: Proj, work: Path):
    """판정 전인 단위는 남는다 — 둘을 고쳐 하나만 clean 하면 다른 하나만 남고, 그것을 두 짝 replace 로 찍으면 0."""
    (fa, _la, a), (fb, _lb, b) = p.eligible(2)
    a1 = insert_token(insert_token(a, 'ZZERRA'), 'ZZERRB')
    b1 = insert_token(b, 'ZZCLEAN')
    p.replace_once(fa, a, a1)
    p.replace_once(fb, b, b1)
    pk = work / 'packet_partial.json'
    r = p.run('changed', '--out', pk, codes=(1,))
    assert {i for i, _w in p.listed(r.stdout)} == {fp(a1)[:12], fp(b1)[:12]}, p.listed(r.stdout)
    r = p.run('clean', '--packet', pk, '--all-except', fp(a1)[:12])
    assert '찍음 1' in r.stdout, r.stdout
    r = p.run('changed', codes=(1,))
    assert [i for i, _w in p.listed(r.stdout)] == [fp(a1)[:12]], p.listed(r.stdout)        # 판정 전인 A 만 남음
    a2 = a1.replace('ZZERRA', 'ZZFIXA', 1).replace('ZZERRB', 'ZZFIXB', 1)
    p.replace_once(fa, a1, a2)
    r = p.run('resolve', '--packet', pk, '--id', fp(a1)[:12], '--replace', 'ZZERRA', 'ZZFIXA', 'ZZERRB', 'ZZFIXB')
    assert fp(a2)[:12] in r.stdout, r.stdout
    p.run('changed')
    fc, _lc, cc = next(x for x in p.eligible(None) if 'ZZ' not in x[2])        # 아직 손대지 않은 셋째 단위
    c1 = insert_token(cc, 'ZZIDS')
    p.replace_once(fc, cc, c1)
    pk2 = work / 'packet_ids.json'
    p.run('changed', '--out', pk2, codes=(1,))
    r = p.run('clean', '--packet', pk2, '--ids', fp(c1)[:12])
    assert '찍음 1' in r.stdout, r.stdout
    p.run('changed')
    p.replace_once(fa, a2, a)
    p.replace_once(fb, b1, b)
    p.replace_once(fc, c1, cc)
    p.run('changed')
    return '둘을 고쳐 --all-except A 로 하나만 찍으면 A 만 남음 · A 를 두 짝 --replace 로 찍으면 0 · --ids 로 찍으면 0'


def s_replace_pass(p: Proj, work: Path):
    f, line, b = p.eligible(1)[0]
    b1 = insert_token(b, 'ZZERR')
    p.replace_once(f, b, b1)
    pk = work / 'packet_pass.json'
    p.run('changed', '--out', pk, codes=(1,))
    b2 = b1.replace('ZZERR', 'ZZFIX', 1)
    p.replace_once(f, b1, b2)                                                # 승인된 수정을 반영
    r = p.run('resolve', '--packet', pk, '--id', fp(b1)[:12], '--replace', 'ZZERR', 'ZZFIX')
    assert '찍음' in r.stdout and fp(b2)[:12] in r.stdout, r.stdout
    p.run('changed')
    lines = p.baseline().read_text(encoding='utf-8').splitlines()
    last = json.loads(lines[-1])
    assert last['how'] == 'replace' and last['지문'] == fp(b2) and last['파일'] == f, last
    p.replace_once(f, b2, b)
    p.run('changed')
    return 'resolve --replace 통과 — 치환 결과 = 지금 원고 → 그 지문을 replace 로 찍음'


def s_replace_mismatch(p: Proj, work: Path):
    f, _line, b = p.eligible(1)[0]
    c1 = insert_token(b, 'ZZERR')
    p.replace_once(f, b, c1)
    pk = work / 'packet_mismatch.json'
    p.run('changed', '--out', pk, codes=(1,))
    c2 = c1.replace('ZZERR', 'ZZOTHER', 1)                                   # 판정과 다른 수정이 들어감
    p.replace_once(f, c1, c2)
    before = p.baseline_bytes()
    r = p.run('resolve', '--packet', pk, '--id', fp(c1)[:12], '--replace', 'ZZERR', 'ZZFIX', codes=(1,))
    assert '찍지 않았습니다' in r.stdout and '[-' in r.stdout and 'ZZOTHER' in r.stdout, r.stdout
    assert p.baseline_bytes() == before
    r = p.run('resolve', '--packet', pk, '--id', fp(c1)[:12], '--replace', 'ZZNOPE', 'x', codes=(2,))
    assert '정확히 한 번' in r.stdout
    assert p.baseline_bytes() == before
    p.replace_once(f, c2, b)
    p.run('changed')
    return 'resolve --replace 불일치 — 찍지 않고 차이를 보이며 1 · 원문이 묶음에 없으면 2 · 기준 바이트 그대로'


def s_keep(p: Proj, work: Path):
    f, _line, b = p.eligible(1)[0]
    k1 = insert_token(b, 'ZZKEEP')
    p.replace_once(f, b, k1)
    pk = work / 'packet_keep.json'
    p.run('changed', '--out', pk, codes=(1,))
    r = p.run('resolve', '--packet', pk, '--id', fp(k1)[:8], '--keep')     # id 앞 8자도 됨
    assert '찍음' in r.stdout
    p.run('changed')
    last = json.loads(p.baseline().read_text(encoding='utf-8').splitlines()[-1])
    assert last['how'] == 'keep' and last['지문'] == fp(k1)
    p.replace_once(f, k1, b)
    p.run('changed')
    return 'resolve --keep 은 묶음의 지문을 keep 으로 찍음'


def s_line_endings(p: Proj):
    f = p.md_files()[0]
    text, nl, bom = p.read(f)
    other = '\n' if nl == '\r\n' else '\r\n'
    p.write(f, text, other, bom)
    p.run('changed')
    p.write(f, text, nl, bom)
    return '줄끝만 바꾼 같은 글은 같은 지문 — %s (%s → %s)' % (f, 'CRLF' if nl == '\r\n' else 'LF', 'LF' if nl == '\r\n' else 'CRLF')


def _regions(lines, regions):
    """도구와 따로 구현한 구간 — 시작 줄부터, 다음 줄부터 찾은 끝 줄 앞까지."""
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
    """(설명 칸 값 집합, 나머지 값 집합) — `_` 로 시작하는 키 아래 문자열은 설명 칸(도구와 따로 구현)."""
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
            assert inside, '%s 구간이 비어 있습니다' % f
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
                p.run('changed')                                                  # 구간 밖은 단위가 아님
            p.write(f, text, nl, bom)
            p.run('changed')
            done.append('lines %s L%d 나옴 · 구간 밖 줄은 0' % (f, k + 1))
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
                p.run('changed')                                                  # 키는 단위가 아님
                p.write(f, text, nl, bom)
            if notes:
                n = notes[0]
                p.write(f, text.replace(n.group(), n.group()[:-1] + ' ZZNOTE"', 1), nl, bom)
                p.run('changed')                                                  # `_` 키 아래 값은 단위가 아님
                p.write(f, text, nl, bom)
            p.run('changed')
            done.append('json %s L%d 값 나옴 · 키만 바꾸면 0%s' % (f, line, ' · `_` 키 값을 바꾸면 0' if notes else ''))
    return ' · '.join(done) or '해당 없음(lines · json-values 원본 없음)'


def s_packet_default(p: Proj):
    """경로 없는 changed --out — 기준 파일 옆 grammar_packets/<시각>_<컴퓨터>.json · status 가 남은 묶음을 알림 · 그 묶음으로 찍으면 0."""
    d = p.baseline().parent / 'grammar_packets'
    had = d.is_dir()
    before = set(os.listdir(d)) if had else set()
    f, _line, b = p.eligible(1)[0]
    b1 = insert_token(b, 'ZZPACK')
    p.replace_once(f, b, b1)
    r = p.run('changed', '--out', codes=(1,))
    new = sorted(set(os.listdir(d)) - before)
    assert len(new) == 1 and re.fullmatch(r'\d{8}-\d{6}_[0-9A-Za-z가-힣-]+\.json', nfc(new[0])), new     # 공백 없음 — 충돌 사본 이름과 겹치지 않게
    assert ('grammar_packets/' + nfc(new[0])) in nfc(r.stdout).replace('\\', '/'), r.stdout
    st = p.run('status', codes=(1,))
    assert '묶음 %d개가' % (len(before) + 1) in st.stdout, st.stdout
    p.run('clean', '--packet', d / new[0], '--all-except')
    p.run('changed')
    (d / new[0]).unlink()
    if not had:
        d.rmdir()
    p.replace_once(f, b1, b)
    p.run('changed')
    return '경로 없는 --out — 기준 옆 grammar_packets/%s · status 가 남은 묶음 알림 · 그 묶음으로 찍으면 0' % new[0]


def s_nfd_names(p: Proj):
    done = []
    base = p.baseline()
    nfd = base.with_name(unicodedata.normalize('NFD', base.name))
    os.rename(base, nfd)
    try:
        if not (base.parent / nfc(base.name)).exists():                       # NTFS — NFC · NFD 이름이 다른 파일
            done.append('기준 파일 이름을 NFD 로')
        p.run('changed')
        r = p.run('init', '--confirm', 'x', codes=(2,))
        assert '이미 있습니다' in r.stdout
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
        done.append('원본 `%s` 를 NFD 로 — status 같음' % f)
        break
    return ' · '.join(done) + ' · changed 0 · init 거절'


def s_warnings(p: Proj):
    raw = p.cfg()
    orig = json.dumps(raw, ensure_ascii=False)
    md0 = p.md_files()[0]
    first = next(l for l in p.read(md0)[0].split('\n') if l.strip())
    g = raw.setdefault('grammar', {})
    g['zzunknown'] = 1
    g.setdefault('sources', [])
    g['sources'] = g['sources'] + [
        {'file': 'zz_없는_파일.md'},
        {'file': md0, 'kind': 'zzkind'},
        {'file': md0, 'kind': 'lines', 'regions': [{'start': '^ZZ_NO_SUCH_START', 'end': '^ZZ'}]},
        {'file': md0, 'kind': 'lines', 'regions': [{'start': '^' + re.escape(first), 'end': '^ZZ_NO_END'}], 'zzkey': 1},
    ]
    p.set_cfg(raw)
    try:
        out = p.run('status', codes=(0, 1)).stdout
        for want in ('모르는 키 `zzunknown`', '`zz_없는_파일.md` 가 없습니다', 'kind `zzkind`', '구간 시작 표지 `^ZZ_NO_SUCH_START`',
                     '구간 끝 표지 `^ZZ_NO_END`', '모르는 키 `zzkey`', '단위가 0개'):
            assert want in out, (want, out)
        raw2 = json.loads(orig)
        raw2.setdefault('grammar', {})['sources'] = [{'file': md0, 'kind': 'lines', 'regions': [{'start': 1}]}]
        p.set_cfg(raw2)
        out = p.run('status', codes=(2,)).stdout
        assert 'start' in out
    finally:
        p.set_cfg(json.loads(orig))
    p.run('changed')
    return '모르는 키 · 모르는 kind · 없는 파일 · 구간 시작 · 끝 표지 없음 · 0 단위 경고 · 구간 형식 오류는 2'


def s_verify(p: Proj, work: Path):
    f, line, b = p.eligible(1, one_line=True)[0]
    words = b.split()
    frag = ' '.join(words[1:6])
    head2, tail2 = ' '.join(words[1:3]), ' '.join(words[4:6])
    text, _nl, _bom = p.read(f)
    lines = text.split('\n')
    other = next(i + 1 for i, l in enumerate(lines) if l.strip() and frag not in l)
    name = f.rsplit('/', 1)[-1]
    cand = work / '후보_시험.md'
    rows = ['| ID | 위치 | 원문 → 수정문 | 이유 |', '|---|---|---|---|',
            '| G1 | `%s` L%d | `%s` → `x` | 맞음 |' % (name, line, frag),
            '| G2 | `%s` L%d | `%s` → `x` | 다른 줄 |' % (name, other, frag),
            '| G3 | 아래 2곳 | `%s` → `x` | 위치 없음 |' % frag,
            '| G4 | `%s` L%d | `%s … %s` → `x` | 생략 |' % (name, line, head2, tail2)]
    cand.write_text('\n'.join(rows + ['| **G5** | `%s` L%d | `%s` → `x` | 강조된 ID |' % (name, line, frag)]) + '\n',
                    encoding='utf-8')
    r = p.run('verify', cand, codes=(1,))
    assert '`G5` 행처럼 보이나' in r.stdout, r.stdout
    st = dict(re.findall(r'^[ !] (G\d)\s+(\S+(?: \S+)?)', r.stdout, re.M))
    assert st.get('G1') == '일치' and st.get('G2') == '불일치' and st.get('G3', '').startswith('대조') and st.get('G4') == '일치', \
        (st, r.stdout)
    hint = next(l for l in r.stdout.splitlines() if '적힌 줄에 없음' in l)
    assert re.search(r'\bL%d\b' % line, hint) and '에 있음' in hint, r.stdout
    cand2 = work / '후보_시험_통과.md'
    cand2.write_text('\n'.join(rows[:3] + rows[5:]) + '\n', encoding='utf-8')
    p.run('verify', cand2)
    return 'verify — 맞는 줄 일치 · 다른 줄 불일치(있는 줄 안내) · 위치 없음 대조 못 함 · 생략(…) 일치 · 통과 파일 0'


def s_readonly(project: Path, state: Path, outside: Path, candidates: Path | None = None):
    """§5 의 쓰임 — 도구를 프로젝트 밖에 두고 --dir · --baseline 으로만 읽습니다. 프로젝트 바이트가 그대로인지."""
    before = tree_hash(project)
    q = Proj(project, state, tool_dir=outside / 'tools')
    q.install()
    base = outside / '기준_보관' / 'grammar_baseline.jsonl'
    common = ['--dir', project, '--baseline', base]
    q.run(*common, 'status', codes=(1,), cwd=outside)
    q.run(*common, 'init', '--confirm', '시험 문구', cwd=outside)
    q.run(*common, 'changed', cwd=outside)
    q.run(*common, 'status', cwd=outside)
    if candidates is not None:
        q.run(*common, 'verify', candidates, codes=(0, 1), cwd=outside)
    q.run('changed', '--dir', project, '--baseline', base, cwd=outside)      # 공통 옵션은 명령 뒤에도
    after = tree_hash(project)
    assert before == after, sorted(set(before.items()) ^ set(after.items()))[:10]
    n = len(base.read_text(encoding='utf-8').splitlines())
    first = json.loads(base.read_text(encoding='utf-8').splitlines()[0])
    assert first['how'] == 'init' and first['문구'] == '시험 문구'
    assert b'\r' not in base.read_bytes()
    return q, '프로젝트 밖 도구 + --dir · --baseline — init · status · changed · verify 뒤 프로젝트 파일 %d개 바이트 그대로 · 기준 %d줄(LF)' \
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
    """init 된 프로젝트에서 시나리오 하나를 돌립니다. 원고가 처음과 같아졌는지도 봅니다.
    work — 묶음 · 후보 파일을 둘 폴더. 부르는 쪽이 정하고 지웁니다(실제 사본이면 사본과 같은 작업 폴더 안)."""
    p = Proj(project, state)
    p.install()
    work.mkdir(parents=True, exist_ok=True)
    if p.baseline() is None:
        p.run('init', '--confirm', '시험 기준')
    src_before = {f: p.read(f) for f, _k, _r in p.sources()}
    msg = fn(p, work) if needs_work else fn(p)
    for f, v in src_before.items():
        assert p.read(f) == v, '%s 가 처음과 다릅니다' % f
    return p, msg
