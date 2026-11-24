# -*- coding: utf-8 -*-
r"""grammar_baseline.py — 제출 전 문법 점검의 기준. 점검 뒤 바뀐 문단을 코드가 골라냅니다.

Claude 가 실제로 본 글의 지문을 기준 파일에 찍어 두고, 지금 원고에서 기준에 없는 단위(바뀐 문단 · 새 문단)만 보입니다.
무엇이 바뀌었는지와 원문 대조는 이 도구가 하고, 모델은 뽑힌 단위의 문법만 봅니다. 규약은 플러그인 문서
`manuscript-workflow/references/revision-protocol.md` 「제출 전 문법 점검」, 설정 키 `grammar` 는 `project-config.md`.

사용법  (`<py>` 는 이 컴퓨터의 Python 3 — 윈도 `python` · 맥 `python3`)
    <py> -X utf8 tools/grammar_baseline.py init --confirm "<사용자 문구>"   기준 파일이 없을 때만 — 범위의 모든 단위를 찍음(맨 처음 한 번)
    <py> -X utf8 tools/grammar_baseline.py changed [--out [<묶음>]]       기준에 없는 단위 — id · 파일 · 줄 · 전문 · 피할 표현 표시.
                                                                --out 만 쓰면 묶음을 기준 파일 옆 `grammar_packets/<시각>_<컴퓨터>.json` 에 만듦
    <py> -X utf8 tools/grammar_baseline.py clean --packet <묶음> --ids <id> …          지적이 없는 단위를 찍음(묶음의 지문만)
    <py> -X utf8 tools/grammar_baseline.py clean --packet <묶음> --all-except [<id> …] 묶음에서 그 id 만 빼고 찍음
    <py> -X utf8 tools/grammar_baseline.py resolve --packet <묶음> --id <id> --keep    지적했으나 그대로 두기로 판정된 단위를 찍음
    <py> -X utf8 tools/grammar_baseline.py resolve --packet <묶음> --id <id> --replace <원문> <수정문> [<원문> <수정문> …]
                                                                고치기로 판정된 단위 — 치환 결과가 지금 원고의 한 단위와 같을 때만 찍음
    <py> -X utf8 tools/grammar_baseline.py verify <후보 파일>             후보 표의 원문이 위치(파일 · L<번호>)에 글자 그대로 있는지
    <py> -X utf8 tools/grammar_baseline.py status                         원본별 범위 · 찍힌 · 남은 단위 수
    공통  --dir <프로젝트 루트>    --baseline <기준 파일>(기본 `.manuscript/grammar_baseline.jsonl` — 시험 · 첫 기준 보관용)

단위    md          빈 줄로 나뉜 블록. 제외 접두(`grammar.exclude_prefixes`, 기본 `@NOTE`)로 시작하는 블록은 뺍니다
        lines       설정한 구간 안의 비어 있지 않은 줄. 구간은 시작 정규식에 맞는 줄부터, 그 **다음** 줄부터 찾은 끝 정규식에 맞는
                    줄 **앞**까지입니다(끝 줄은 넣지 않음). 끝 표지를 못 찾으면 경고하고 파일 끝까지 읽습니다
        json-values 문자열 값 하나(키는 단위가 아님). `_` 로 시작하는 키의 값은 그 아래 모두 설명 칸이라 뺍니다
지문    정규화한 글의 SHA-256 — NFC · 줄끝 LF · 앞뒤 공백 제거, 안쪽 공백은 그대로. 파일 · 위치는 넣지 않습니다 — 비교는 내용으로 하므로
        순서만 바뀐 문단은 나오지 않고, 되돌린 문단은 빠지고, 새 문단은 나옵니다. id 는 지문 앞 12자입니다.
기준    `.manuscript/grammar_baseline.jsonl` — 한 줄에 표시 하나(`지문` · `how`(init | clean | keep | replace) · `시각` · `컴퓨터` · `파일`,
        init 은 `문구` 도). 추가만 하고 지우지 않습니다. 표시를 잃으면 그 단위가 다시 「바뀐 단위」로 나올 뿐 놓치지는 않습니다.
묶음    `changed --out` 이 배타적으로 만드는 JSON — 보인 글과 지문. clean · resolve --keep 은 **묶음의 지문만** 찍고 원고를 다시 읽지
        않으므로, 점검하는 사이에 누가 그 문단을 고쳤으면 그 문단은 다시 목록에 올라옵니다. 경로를 주지 않으면 기준 파일 옆
        `grammar_packets/` 에 만듭니다. 다 판정한 묶음은 지웁니다 — 판정 전 단위는 다음 changed 가 다시 뽑으므로 언제 지워도 놓치지 않습니다.
설정    `.manuscript/project.json` 의 선택 키 `grammar` — `sources`(기본 범위에 더하는 원본 · `file` 은 루트 기준) · `exclude_prefixes` ·
        `avoid_lists`(피할 표현 목록 · 루트 기준). 키가 없으면 범위는 `manuscript.source_dir` 의 `chapters` 파일(참고문헌 제외)입니다.
        모르는 키 · 모르는 kind · 못 찾은 구간 표지 · 없는 파일 · 0 단위는 경고합니다. `_` 로 시작하는 키는 주석으로 봅니다.
종료    0 정상 · 1 남은 것 또는 불일치 · 2 인자 · 설정 오류
쓰는 것  기준 파일(init · clean · resolve)과 묶음(changed --out)뿐입니다. 원고는 읽기만 합니다. 기준 파일은 동기화 공용 파일이 아닙니다 —
        충돌 사본은 동기화 점검이 알리고, 표시를 잃으면 그 단위가 다시 나올 뿐입니다.
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
from _config import (load as _load_cfg, nfc, _콘솔_UTF8, split_cells, unescape_cell,   # noqa: E402  — _config 를 먼저(NFD 이름 모듈 finder)
                     TABLE_ROW_RE, TABLE_SEP_RE, row_like_id)
from _sync import computer_id, find_project_root                                   # noqa: E402
import _location                                                                         # noqa: E402

BASELINE_REL = '.manuscript/grammar_baseline.jsonl'
PACKET_DIR = 'grammar_packets'           # 기준 파일 옆 — 경로 없이 changed --out 한 묶음의 자리
# 0.12 이하의 이름 — 새 이름의 기준 파일이 없고 이것만 있으면 그대로 씁니다(묶음 자리도 옛 이름)
LEGACY_BASELINE_REL, LEGACY_PACKET_DIR = '.manuscript/문법기준.jsonl', '문법묶음'
PACKET_FORMAT = '문법기준-묶음/1'
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
    """인자 · 설정 오류 — 종료 코드 2."""


# ---------------------------------------------------------------- 정규화 · 지문
def normalize(text):
    """지문을 낼 글 — NFC · 줄끝 LF · 앞뒤 공백 제거. 안쪽 공백은 그대로 둡니다."""
    return nfc(text.replace('\r\n', '\n').replace('\r', '\n')).strip()


def fingerprint(text):
    return hashlib.sha256(normalize(text).encode('utf-8')).hexdigest()


def now_text():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


# ---------------------------------------------------------------- 경로 — 이름 정규화(NFC · NFD)가 달라도 찾습니다
def find_path(root, rel):
    """루트 기준 경로 rel 의 실제 경로. 폴더 목록을 NFC 로 대조하므로 NFD 로 저장된 이름(맥 미러를 옮긴 사본)도 찾습니다. 없으면 None."""
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
    """절대 · 상대 경로 그대로 있으면 그것, 없으면 같은 폴더에서 NFC 로 같은 이름을 찾습니다. 없으면 None."""
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
    """UTF-8(BOM 허용)로 읽고 줄끝을 LF 로 맞춥니다 — 줄 번호는 물리 줄 그대로입니다."""
    with io.open(path, encoding='utf-8-sig', newline='') as f:
        return f.read().replace('\r\n', '\n').replace('\r', '\n')


# ---------------------------------------------------------------- 설정
class Source(object):
    def __init__(self, file, kind, regions, origin):
        self.file = file                # 루트 기준(`/` · NFC)
        self.kind = kind
        self.regions = regions          # [(start 정규식, end 정규식)] — lines 만
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
        raise UsageError('grammar.%s 는 문자열 목록이어야 합니다' % name)
    return list(v)


def read_settings(cfg, warn):
    g = cfg.raw.get('grammar')
    if g is None:
        g = {}
    if not isinstance(g, dict):
        raise UsageError('grammar 는 객체여야 합니다')
    for k in g:
        if k not in GRAMMAR_KEYS and not k.startswith('_'):
            warn('설정 grammar 에 모르는 키 `%s` — 읽지 않습니다(아는 키: %s)' % (k, ' · '.join(GRAMMAR_KEYS)))
    exclude = _str_list(g['exclude_prefixes'], 'exclude_prefixes') if 'exclude_prefixes' in g else list(DEFAULT_EXCLUDE)
    avoid = _str_list(g['avoid_lists'], 'avoid_lists') if 'avoid_lists' in g else []

    sources = []
    # 기본 범위 — 원고 폴더의 장 파일(참고문헌 파일 제외)
    src = cfg.source_rel
    base = (src + '/') if src and find_path(cfg.root, src) else ''
    for _n, f in cfg.chapters:
        if f == cfg.references:
            continue
        sources.append(Source(nfc(base + f), 'md', [], 'chapters'))
    extra = g.get('sources', [])
    if not isinstance(extra, list):
        raise UsageError('grammar.sources 는 목록이어야 합니다')
    for i, s in enumerate(extra, 1):
        if not isinstance(s, dict) or not isinstance(s.get('file'), str) or not s['file'].strip():
            raise UsageError('grammar.sources 의 %d번째 항목에 `file`(문자열)이 없습니다' % i)
        f = nfc(s['file'].strip().replace('\\', '/'))
        for k in s:
            if k not in SOURCE_KEYS and not k.startswith('_'):
                warn('설정 grammar.sources `%s` 에 모르는 키 `%s` — 읽지 않습니다' % (f, k))
        kind = s.get('kind')
        if kind is None:
            kind = 'md'
            if not f.lower().endswith('.md'):
                warn('설정 grammar.sources `%s` 에 kind 가 없어 md(빈 줄 블록)로 읽습니다' % f)
        if kind not in KINDS:
            warn('설정 grammar.sources `%s` 의 kind `%s` 를 모릅니다(%s) — 이 원본은 읽지 않습니다' % (f, kind, ' · '.join(KINDS)))
            continue
        regions = []
        if 'regions' in s:
            if kind != 'lines':
                warn('설정 grammar.sources `%s` 의 regions 는 lines 에만 씁니다 — 무시합니다' % f)
            else:
                if not isinstance(s['regions'], list):
                    raise UsageError('grammar.sources `%s` 의 regions 는 목록이어야 합니다' % f)
                for r in s['regions']:
                    if not isinstance(r, dict) or not isinstance(r.get('start'), str) or not isinstance(r.get('end'), str):
                        raise UsageError('grammar.sources `%s` 의 구간마다 `start` · `end`(정규식 문자열)가 있어야 합니다' % f)
                    for k in r:
                        if k not in REGION_KEYS and not k.startswith('_'):
                            warn('설정 grammar.sources `%s` 의 구간에 모르는 키 `%s` — 읽지 않습니다' % (f, k))
                    try:
                        regions.append((re.compile(r['start']), re.compile(r['end'])))
                    except re.error as e:
                        raise UsageError('grammar.sources `%s` 의 구간 정규식 오류: %s' % (f, e))
        if kind == 'lines' and not regions:
            warn('설정 grammar.sources `%s` 는 lines 인데 구간(regions)이 없습니다 — 0 단위' % f)
        sources.append(Source(f, kind, regions, 'grammar'))
    # 같은 원본을 두 번 적었으면 한 번만
    seen, uniq = set(), []
    for s in sources:
        if s.key() not in seen:
            seen.add(s.key())
            uniq.append(s)
    return Settings(uniq, exclude, avoid)


# ---------------------------------------------------------------- 단위 뽑기
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
                    stats['glued'].append(start)       # 제외 접두 줄이 문단에 붙어 있음 — 그 줄이 바뀌어도 이 블록이 나옵니다
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
                warn('`%s` L%d 의 구간 끝 표지 `%s` 를 찾지 못했습니다 — 파일 끝까지 읽습니다' % (src.file, i + 1, end_re.pattern))
            for k in range(i, min(j, len(lines))):
                if lines[k].strip():
                    picked.setdefault(k + 1, lines[k])
            i = j
        if not found:
            warn('`%s` 에서 구간 시작 표지 `%s` 를 찾지 못했습니다' % (src.file, start_re.pattern))
    return [Unit(src, n, picked[n]) for n in sorted(picked)]


def _json_strings(v, out):
    """문자열 값 — `_` 로 시작하는 키의 값(그 아래 모두)은 설명 칸이라 넣지 않습니다."""
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
    """[(값, 시작 위치)] — 문자열 값만, 키 아닌 것. 구조를 따라 읽어 `_` 키 아래 값은 뺍니다(같은 글이 다른 자리에 있어도 자리로 가름).
    text 는 json.loads 를 통과한 글이어야 합니다."""
    out, n = [], len(text)

    def skip(i):
        while i < n and text[i] in ' \t\r\n':
            i += 1
        return i

    def string(i):
        m = _JSON_STR.match(text, i)
        if not m:
            raise ValueError('%d 자리에 문자열이 없습니다' % i)
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
                        raise ValueError('%d 자리에 `:` 가 없습니다' % i)
                    i += 1
                    m2 = muted or k.startswith('_')
                i = skip(value(i, m2))
                if text[i] == ',':
                    i += 1
                    continue
                if text[i] == close:
                    return i + 1
                raise ValueError('%d 자리에 `,` · `%s` 가 없습니다' % (i, close))
        m = _JSON_LIT.match(text, i)
        if not m:
            raise ValueError('%d 자리의 값을 읽지 못했습니다' % i)
        return m.end()

    value(0, False)
    return out


def json_units(src, text, warn):
    try:
        data = json.loads(text)
    except ValueError as e:
        warn('`%s` 를 JSON 으로 읽지 못했습니다: %s — 0 단위' % (src.file, e))
        return []
    try:
        spans = _json_value_spans(text)
    except (ValueError, IndexError) as e:
        warn('`%s` 의 문자열 값 자리를 읽지 못했습니다: %s — 0 단위' % (src.file, e))
        return []
    out = [Unit(src, text.count('\n', 0, at) + 1, v) for v, at in spans if normalize(v)]
    expect = []
    _json_strings(data, expect)
    if sorted(v for v, _at in spans) != sorted(expect):
        warn('`%s` 의 문자열 값 위치를 다 읽지 못했습니다(읽은 %d · 실제 %d) — 줄 번호가 틀릴 수 있습니다'
             % (src.file, len(spans), len(expect)))
    return out


def collect(root, settings, warn):
    """[(원본, [단위], 상태)] — 상태 'ok' | 'missing' | 'unreadable'."""
    result = []
    for src in settings.sources:
        stats = {'excluded': 0, 'glued': []}
        path = find_path(root, src.file)
        if path is None or not os.path.isfile(path):
            warn('원본 `%s` 가 없습니다 — 0 단위' % src.file)
            result.append((src, [], 'missing', stats))
            continue
        try:
            text = read_text(path)
        except (OSError, UnicodeDecodeError) as e:
            warn('원본 `%s` 를 읽지 못했습니다: %s — 0 단위' % (src.file, e))
            result.append((src, [], 'unreadable', stats))
            continue
        if src.kind == 'md':
            units = md_units(src, text, settings.exclude, stats)
        elif src.kind == 'lines':
            units = line_units(src, text, warn)
        else:
            units = json_units(src, text, warn)
        if not units:
            warn('원본 `%s` (%s)에서 단위가 0개입니다' % (src.file, src.kind))
        result.append((src, units, 'ok', stats))
    return result


def all_units(collected):
    return [u for _s, us, _st, _x in collected for u in us]


def group_by_fp(units):
    """지문 → [단위 …] (처음 나온 순서). 같은 글이 두 자리에 있으면 한 지문 · 여러 위치입니다."""
    groups = {}
    for u in units:
        groups.setdefault(u.fp, []).append(u)
    return groups


# ---------------------------------------------------------------- 피할 표현
def load_avoid(root, paths, warn):
    out = []
    for p in paths:
        real = find_path(root, p)
        if real is None or not os.path.isfile(real):
            warn('피할 표현 목록 `%s` 가 없습니다' % p)
            continue
        try:
            text = read_text(real)
        except (OSError, UnicodeDecodeError) as e:
            warn('피할 표현 목록 `%s` 를 읽지 못했습니다: %s' % (p, e))
            continue
        n0 = len(out)
        for line in text.split('\n'):
            if not line.startswith('|') or TABLE_SEP_RE.match(line):
                continue
            # 첫 칸의 **첫** 코드 스팬이 표현입니다 — 뒤의 괄호 설명에 든 코드 스팬(`… 앞의 \`of\``)은 표현이 아닙니다
            spans = _CODE_SPAN.findall(split_cells(line)[0])
            s = nfc(unescape_cell(spans[0])).strip() if spans else ''
            if s and (s, p) not in out:
                out.append((s, p))
        if len(out) == n0:
            warn('피할 표현 목록 `%s` 의 표 첫 열에서 코드 스팬을 하나도 읽지 못했습니다' % p)
    return out


def avoid_hits(text, avoid):
    t = text.casefold()
    return [s for s, _p in avoid if s.casefold() in t]


# ---------------------------------------------------------------- 기준 파일
def baseline_path(root, arg):
    """(실제 경로 또는 None, 만들 경로)."""
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
            warn('기준 파일 %d행을 읽지 못했습니다 — 그 표시는 없는 것으로 봅니다' % n)
            continue
        fp = rec.get('지문') if isinstance(rec, dict) else None
        if not isinstance(fp, str) or not _FP_RE.match(fp):
            warn('기준 파일 %d행에 지문이 없거나 형식이 다릅니다 — 그 표시는 없는 것으로 봅니다' % n)
            continue
        how = rec.get('how')
        if how not in HOWS:
            warn('기준 파일 %d행의 how `%s` 를 모릅니다 — 표시로는 셉니다' % (n, how))
        hows[how] = hows.get(how, 0) + 1
        marks.setdefault(fp, rec)
    return marks, hows, n_lines


def mark_record(fp, how, file, extra=None):
    r = {'지문': fp, 'how': how, '시각': now_text(), '컴퓨터': computer_id(), '파일': file}
    if extra:
        r.update(extra)
    return r


def _dump(records):
    return ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records)


def create_exclusive(path, text):
    """없을 때만 만듭니다 — 있으면 FileExistsError. 바이트 그대로(줄끝 LF) 씁니다."""
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0))
    with io.open(fd, 'wb') as f:
        f.write(text.encode('utf-8'))
        f.flush()
        os.fsync(f.fileno())


def append_records(path, records):
    """추가만 합니다. 마지막 줄이 줄바꿈 없이 끝났으면 줄을 바꾼 뒤 붙입니다."""
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


# ---------------------------------------------------------------- 묶음
def write_packet(path, root, base_disp, groups, avoid):
    units = []
    for fp, us in groups.items():
        units.append({'id': fp[:ID_LEN], '지문': fp, '글': us[0].text,
                      '위치': [{'파일': u.file, '줄': u.line} for u in us],
                      '피할': avoid_hits(us[0].text, avoid)})
    data = {'형식': PACKET_FORMAT, '만든 시각': now_text(), '컴퓨터': computer_id(), '루트': nfc(os.path.abspath(root)),
            '기준': base_disp, '단위': units}
    create_exclusive(os.path.abspath(path), json.dumps(data, ensure_ascii=False, indent=1) + '\n')


def read_packet(path, root, base_disp, warn):
    real = locate(path)
    if real is None:
        raise UsageError('묶음 파일이 없습니다: %s' % path)
    try:
        data = json.loads(read_text(real))
    except (OSError, ValueError) as e:
        raise UsageError('묶음 파일을 읽지 못했습니다: %s' % e)
    if not isinstance(data, dict) or data.get('형식') != PACKET_FORMAT or not isinstance(data.get('단위'), list):
        raise UsageError('묶음 형식이 아닙니다(`형식` 이 %s 여야 함): %s' % (PACKET_FORMAT, path))
    for u in data['단위']:
        if not isinstance(u, dict) or not isinstance(u.get('글'), str) or fingerprint(u['글']) != u.get('지문'):
            raise UsageError('묶음의 단위 `%s` 의 글과 지문이 맞지 않습니다 — 묶음을 손으로 고쳤으면 changed --out 으로 다시 만드십시오'
                             % (u.get('id') if isinstance(u, dict) else '?'))
    if nfc(data.get('루트', '')) != nfc(os.path.abspath(root)):
        warn('묶음을 만든 루트(%s)가 지금 루트와 다릅니다 — 지문은 내용 기준이라 그대로 찍습니다' % data.get('루트'))
    if data.get('기준') != base_disp:
        warn('묶음을 만들 때의 기준(%s)이 지금 기준(%s)과 다릅니다' % (data.get('기준'), base_disp))
    return data['단위']


def pick(units, ident):
    ident = ident.strip().lower()
    if len(ident) < MIN_ID_PREFIX:
        raise UsageError('id `%s` 가 너무 짧습니다(%d자 이상)' % (ident, MIN_ID_PREFIX))
    hit = [u for u in units if u['지문'].startswith(ident)]
    if not hit:
        raise UsageError('묶음에 id `%s` 가 없습니다' % ident)
    if len(hit) > 1:
        raise UsageError('id `%s` 가 묶음의 단위 %d개에 맞습니다 — 더 길게 적으십시오' % (ident, len(hit)))
    return hit[0]


# ---------------------------------------------------------------- 보이기
def show_unit(fp, locs, text, hits, out=print):
    where = ' · '.join('%s L%d' % (f, n) for f, n in locs)
    out('[%s] %s' % (fp[:ID_LEN], where))
    for line in text.split('\n'):
        out('    ' + line)
    if hits:
        out('    ! 피할 표현: ' + ' · '.join('`%s`' % h for h in hits))


_TOKEN = re.compile(r'\w+|\s+|[^\w\s]')


def diff_lines(expect, actual, width=6, limit=8):
    """낱말 단위 차이 — `…앞 낱말 [-치환 결과-]{+지금 원고+} 뒤 낱말…`. 줄바꿈은 ⏎ 로 보입니다."""
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
            out.append('(차이가 더 있습니다)')
            break
    return out


# ---------------------------------------------------------------- 명령
class Ctx(object):
    def __init__(self, a):
        self.warnings = []
        root = a.dir
        if root:
            root = os.path.abspath(root)
            if not os.path.isdir(root):
                raise UsageError('프로젝트 폴더가 없습니다: %s' % root)
        else:
            here = os.path.dirname(os.path.abspath(__file__))
            root = find_project_root(here) or find_project_root(os.getcwd())
            if not root:
                raise UsageError('프로젝트 루트(.manuscript/project.json)를 찾지 못했습니다 — --dir 로 주십시오')
        self.root = root
        try:
            self.cfg = _load_cfg(root)
        except SystemExit as e:                       # _config.load 는 읽기 오류를 SystemExit 로 냅니다
            raise UsageError(str(e))
        if find_path(root, '.manuscript/project.json') is None and find_path(root, '.writing/project.json') is None:
            self.warn('설정 파일이 없습니다 — 기본값으로 범위를 정합니다')
        self.settings = read_settings(self.cfg, self.warn)
        self.base_real, self.base_new = baseline_path(root, a.baseline)
        self.base_disp = rel_of(root, self.base_new) if not a.baseline else nfc(os.path.abspath(a.baseline))
        legacy = bool(self.base_real) and nfc(os.path.basename(self.base_real)) == nfc(LEGACY_BASELINE_REL.split('/')[-1])
        self.packet_dir = os.path.join(os.path.dirname(self.base_real or self.base_new), LEGACY_PACKET_DIR if legacy else PACKET_DIR)

    def disp(self, path):
        """루트 안이면 루트 기준 경로, 밖(다른 드라이브 포함)이면 절대 경로."""
        try:
            r = rel_of(self.root, path)
        except ValueError:                            # Windows — 루트와 드라이브가 다르면 상대 경로가 없습니다
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
            raise UsageError('기준 파일이 없습니다: %s — 맨 처음 기준은 사용자 말씀을 받아 `init --confirm "<문구>"` 로 만듭니다'
                             % self.base_disp)
        return read_baseline(self.base_real, self.warn)


def cmd_init(c, a):
    phrase = (a.confirm or '').strip()
    if not phrase:
        raise UsageError('init 에는 사용자 문구가 필요합니다 — --confirm "<사용자 문구>"')
    if c.base_real is not None:
        raise UsageError('기준 파일이 이미 있습니다: %s — init 은 맨 처음 한 번만 합니다(기준은 지우지 않습니다)' % c.base_disp)
    collected = collect(c.root, c.settings, c.warn)
    groups = group_by_fp(all_units(collected))
    if not groups:
        c.flush()
        raise UsageError('범위에서 단위를 하나도 찾지 못했습니다 — 설정(manuscript.chapters · grammar.sources)을 확인하십시오')
    records = [mark_record(fp, 'init', us[0].file, {'문구': phrase}) for fp, us in groups.items()]
    try:
        create_exclusive(c.base_new, _dump(records))
    except FileExistsError:
        raise UsageError('기준 파일이 그사이 생겼습니다: %s — 다시 확인하십시오' % c.base_disp)
    c.flush()
    for src, units, _st, _x in collected:
        print('  %-40s %-11s %4d 단위' % (src.file, src.kind, len(units)))
    print('기준을 만들었습니다: %s — 지문 %d개(단위 %d개) · 문구 「%s」'
          % (c.base_disp, len(groups), sum(len(us) for _s, us, _t, _x in collected), phrase))
    return 0


def cmd_changed(c, a):
    marks, _hows, n_lines = c.need_baseline()
    collected = collect(c.root, c.settings, c.warn)
    units = all_units(collected)
    groups = group_by_fp([u for u in units if u.fp not in marks])
    avoid = load_avoid(c.root, c.settings.avoid_lists, c.warn)
    c.flush()
    print('기준 %s — 표시 %d줄 · 범위 %d 단위 · 기준에 없는 것 %d개'
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
                raise UsageError('묶음 파일이 이미 있습니다: %s — 새 이름을 주십시오(덮어쓰지 않습니다)' % out)
            print('\n묶음: %s (%d개)' % (out if a.out else c.disp(out), len(groups)))
        else:
            print('\n바뀐 단위가 없어 묶음을 만들지 않았습니다')
    return 1 if groups else 0


def _stamp_from_packet(c, units, how):
    marks, _h, _n = c.need_baseline()
    todo, already = [], 0
    for u in units:
        fp = fingerprint(u['글'])                    # 저장된 지문을 믿지 않고 묶음의 글에서 다시 냅니다
        if fp in marks or any(r['지문'] == fp for r in todo):
            already += 1
            continue
        file = (u.get('위치') or [{}])[0].get('파일', '')
        todo.append(mark_record(fp, how, file))
    append_records(c.base_real, todo)
    return todo, already


def cmd_clean(c, a):
    packet = read_packet(a.packet, c.root, c.base_disp, c.warn)
    if a.ids is not None:
        chosen = [pick(packet, i) for i in a.ids]
    else:
        skip = {pick(packet, i)['지문'] for i in a.all_except}
        chosen = [u for u in packet if u['지문'] not in skip]
    todo, already = _stamp_from_packet(c, chosen, 'clean')
    c.flush()
    print('clean — 찍음 %d · 이미 찍힘 %d (묶음 %d개 중 %d개 선택)' % (len(todo), already, len(packet), len(chosen)))
    for r in todo:
        print('  %s  %s' % (r['지문'][:ID_LEN], r['파일']))
    return 0


def cmd_resolve(c, a):
    packet = read_packet(a.packet, c.root, c.base_disp, c.warn)
    u = pick(packet, a.id)
    if a.keep:
        todo, already = _stamp_from_packet(c, [u], 'keep')
        c.flush()
        print('keep — %s %s' % (u['id'], '찍음' if todo else '이미 찍혀 있음'))
        return 0
    pairs = a.replace
    if len(pairs) % 2:
        raise UsageError('--replace 는 <원문> <수정문> 짝으로 줍니다(지금 %d개)' % len(pairs))
    text = u['글']
    for i in range(0, len(pairs), 2):
        old = nfc(pairs[i].replace('\r\n', '\n'))
        new = nfc(pairs[i + 1].replace('\r\n', '\n'))
        n = text.count(old) if old else 0
        if n != 1:
            raise UsageError('원문이 묶음의 글에 정확히 한 번 있어야 합니다 — `%s` 는 %d번' % (pairs[i], n))
        text = text.replace(old, new, 1)
    expect = normalize(text)
    if not expect:
        raise UsageError('치환 결과가 빈 글입니다')
    want = hashlib.sha256(expect.encode('utf-8')).hexdigest()
    marks, _h, _n = c.need_baseline()
    collected = collect(c.root, c.settings, c.warn)
    units = all_units(collected)
    found = [x for x in units if x.fp == want]
    if found:
        if want in marks:
            c.flush()
            print('replace — %s → %s 는 이미 찍혀 있습니다 (%s L%d)' % (u['id'], want[:ID_LEN], found[0].file, found[0].line))
            return 0
        append_records(c.base_real, [mark_record(want, 'replace', found[0].file)])
        c.flush()
        print('replace — %s → %s 찍음 (%s L%d)' % (u['id'], want[:ID_LEN], found[0].file, found[0].line))
        return 0
    # 찍지 않습니다 — 가장 가까운 단위와의 차이를 보입니다
    files = {loc.get('파일') for loc in u.get('위치', [])}
    pool = [x for x in units if x.file in files] or units
    best = sorted(pool, key=lambda x: difflib.SequenceMatcher(None, expect, x.text, autojunk=False).quick_ratio(),
                  reverse=True)[:5]
    best = max(best, key=lambda x: difflib.SequenceMatcher(None, expect, x.text, autojunk=False).ratio()) if best else None
    c.flush()
    print('찍지 않았습니다 — 치환 결과가 지금 원고의 어느 단위와도 글자까지 같지 않습니다 (%s)' % u['id'])
    if best is not None:
        r = difflib.SequenceMatcher(None, expect, best.text, autojunk=False).ratio()
        print('가장 가까운 단위: %s L%d (일치율 %.0f%%) — 차이(치환 결과 → 지금 원고):' % (best.file, best.line, r * 100))
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
    """위치 칸 → [(쓴 이름, 루트 기준 경로 또는 None, 실제 경로 또는 None, [줄 …])]."""
    pat = re.compile(r'`(?P<bt>[^`]+)`|(?<![A-Za-z0-9_])L(?P<ln>\d+)(?:\(\d+곳?\))?|(?P<bare>' + _location.BARE + r')')
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
                    warn_row('파일 없이 줄 번호 L%s' % m.group('ln'))
                else:
                    locs[-1][3].append(int(m.group('ln')))
            elif m.group('bare') is not None and gram._pathlike(m.group('bare')):
                add_file(m.group('bare'))
    scan(cell)
    return locs


def cmd_verify(c, a):
    real = locate(a.candidates)
    if real is None:
        raise UsageError('후보 파일이 없습니다: %s' % a.candidates)
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
                c.warn('후보 %d행은 `%s` 행처럼 보이나 ID 칸을 읽지 못했습니다(강조 · 코드 표시를 걷어 `| %s |` 로) — 대조하지 않습니다'
                       % (n, rid, rid))
            continue
        cells = split_cells(line)
        rid = m.group(1)
        notes, status = [], '일치'
        if len(cells) < 3:
            rows.append((rid, n, '대조 못 함', ['칸이 셋보다 적음']))
            continue

        def warn_row(msg):
            notes.append(msg)

        locs = _parse_locations(cells[1], gram, c.root, warn_row)
        body = cells[2]
        left = body.split('→', 1)[0] if '→' in body else body
        origs = [nfc(unescape_cell(x)) for x in _CODE_SPAN.findall(left)]
        if not locs:
            rows.append((rid, n, '대조 못 함', ['위치에서 파일을 읽지 못함: %s' % cells[1][:60]] + notes))
            continue
        if not origs:
            rows.append((rid, n, '대조 못 함', ['원문 코드 스팬이 없음'] + notes))
            continue
        partial = bool(notes)
        for tok, path, rp, lns in locs:
            if rp is None:
                notes.append('`%s` 파일을 찾지 못함' % tok)
                partial = True
            elif not lns:
                notes.append('`%s` 에 줄 번호가 없어 파일 전체에서 찾음' % tok)
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
                status = '불일치'
                where = []
                for tok, path, rp, lns in locs:
                    if rp is None:
                        continue
                    fl = lines_of(rp)
                    at = [i for i, l in enumerate(fl, 1) if _match_in(l, frags)]
                    where.append('%s %s' % (path, ('L' + ' · L'.join(map(str, at[:5])) + ' 에 있음') if at else '에 없음'))
                notes.append('`%s` — 적힌 줄에 없음 (%s)' % (o[:60] + ('…' if len(o) > 60 else ''), '; '.join(where)))
        if status == '일치' and partial:
            status = '일부 대조'
        loc_txt = ' · '.join('%s %s' % (p or tok, ' '.join('L%d' % x for x in lns)) for tok, p, _r, lns in locs)
        rows.append((rid, n, status, [loc_txt] + notes if status == '일치' else notes))

    c.flush()
    counts = {}
    for rid, n, status, notes in rows:
        counts[status] = counts.get(status, 0) + 1
        mark = '  ' if status == '일치' else '! '
        print('%s%-6s %-8s %s' % (mark, rid, status, notes[0] if notes else ''))
        for x in notes[1:]:
            print('         %s' % x)
    if not rows:
        print('  ! ID 행(`| ID | 위치 | 원문 → 수정문 | … |`)을 하나도 읽지 못했습니다')
    print('요약 — ID 행 %d · %s' % (len(rows), ' · '.join('%s %d' % (k, v) for k, v in counts.items()) or '없음'))
    return 0 if rows and all(r[2] == '일치' for r in rows) else 1


def cmd_status(c, a):
    if c.base_real is None:
        marks, hows, n_lines = {}, {}, 0
        c.warn('기준 파일이 없습니다: %s — 모두 남은 것으로 셉니다' % c.base_disp)
    else:
        marks, hows, n_lines = read_baseline(c.base_real, c.warn)
    collected = collect(c.root, c.settings, c.warn)
    c.flush()
    print('기준 %s — 표시 %d줄%s · 지문 %d개' % (c.base_disp, n_lines,
          (' (' + ' · '.join('%s %d' % (k, v) for k, v in sorted(hows.items(), key=lambda x: str(x[0]))) + ')') if hows else '',
          len(marks)))
    print('  %-40s %-11s %6s %6s %6s' % ('원본', 'kind', '범위', '찍힘', '남음'))
    tot = [0, 0]
    for src, units, st, stats in collected:
        done = sum(1 for u in units if u.fp in marks)
        tot[0] += len(units)
        tot[1] += done
        extra = ''
        if st != 'ok':
            extra = '  (없음)' if st == 'missing' else '  (읽지 못함)'
        elif stats['glued']:
            extra = '  (제외 접두 줄이 붙은 블록 %d: L%s)' % (len(stats['glued']), ' · L'.join(map(str, stats['glued'][:6])))
        print('  %-40s %-11s %6d %6d %6d%s' % (src.file, src.kind, len(units), done, len(units) - done, extra))
    print('  %-40s %-11s %6d %6d %6d' % ('합계', '', tot[0], tot[1], tot[0] - tot[1]))
    print('  (단위는 자리 기준 — 같은 글이 두 자리에 있으면 둘로 셉니다)')
    left = c.leftover_packets()
    if left:
        print('  묶음 %d개가 %s 에 남아 있습니다 — 다 판정한 묶음은 지웁니다(%s)'
              % (len(left), c.disp(c.packet_dir), ' · '.join(left[:3]) + (' …' if len(left) > 3 else '')))
    return 0 if tot[0] == tot[1] and c.base_real is not None else 1


# ---------------------------------------------------------------- 진입
def build_parser():
    # 공통 옵션은 명령 앞 · 뒤 어디에 와도 됩니다. 기본값을 SUPPRESS 로 두어 하위 파서가 앞에 준 값을 None 으로 덮지 않게 합니다.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--dir', default=argparse.SUPPRESS, help='프로젝트 루트(없으면 이 파일의 위치 또는 현재 폴더에서 위로 찾음)')
    common.add_argument('--baseline', default=argparse.SUPPRESS, help='기준 파일 경로(기본 .manuscript/grammar_baseline.jsonl)')
    ap = argparse.ArgumentParser(description='제출 전 문법 점검의 기준 — 바뀐 문단만 골라냅니다', parents=[common])
    sub = ap.add_subparsers(dest='cmd')
    p = sub.add_parser('init', parents=[common], help='맨 처음 기준(사용자 말씀으로 한 번)')
    p.add_argument('--confirm', metavar='문구', required=True)
    p = sub.add_parser('changed', parents=[common], help='기준에 없는 단위')
    p.add_argument('--out', metavar='묶음', nargs='?', const='',
                   help='묶음 파일 — 경로를 빼면 기준 파일 옆 grammar_packets/<시각>_<컴퓨터>.json')
    p = sub.add_parser('clean', parents=[common], help='지적이 없는 단위를 찍음')
    p.add_argument('--packet', metavar='묶음', required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--ids', nargs='+', metavar='id')
    g.add_argument('--all-except', nargs='*', metavar='id')
    p = sub.add_parser('resolve', parents=[common], help='지적이 있었던 단위의 판정을 찍음')
    p.add_argument('--packet', metavar='묶음', required=True)
    p.add_argument('--id', required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--keep', action='store_true')
    g.add_argument('--replace', nargs='+', metavar='글')
    p = sub.add_parser('verify', parents=[common], help='후보 표의 원문을 위치와 대조')
    p.add_argument('candidates', metavar='후보파일')
    sub.add_parser('status', parents=[common], help='원본별 범위 · 찍힌 · 남은 수')
    return ap


def main(argv=None):
    _콘솔_UTF8()
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
        print('오류: %s' % e)
        return 2


if __name__ == '__main__':
    sys.exit(main())
