r"""원고 프로젝트 설정 로더 — `.manuscript/project.json`

도구가 프로젝트에 적응하는 데 쓰는 값(챕터 목록, 추적 파일 이름, 트리거)을 한 곳에서 읽습니다.
**설정 파일이 없으면 기본값을 씁니다.** 기존 동작과 같으므로, 이 파일을 넣지 않은 프로젝트에서도
도구가 그대로 돕니다.

    from _config import load
    cfg = load()
    cfg.chapters          -> [(1, 'ch1.md'), ...]
    cfg.tracker_files     -> ['수정필요_목록.md', ...]
    cfg.triggers          -> ['지금', ...]

다른 논문에서 쓰려면 `.manuscript/project.json` 만 만들면 됩니다. 도구는 고치지 않습니다.
(2026-09-01 에 `.writing/` 에서 이름을 바꿨습니다 — 원고 전용임이 이름에 드러나게. 옛 경로도 읽습니다.)
"""

import importlib.abc, importlib.util, io, json, os, re, sys, unicodedata


def nfc(s):
    """유니코드 정규화 NFC — 파일 이름 · 경로 · 줄을 **비교하거나 키로 쓸 때** 거칩니다.
    맥(구글드라이브 미러 · HFS+)은 한글 이름을 NFD 로 저장해 `os.listdir` 가 돌려주는 이름이 설정 · 본문의 NFC 문자열과 다릅니다.
    파일을 **열** 때는 어느 쪽이든 됩니다(APFS · HFS+ 는 정규화에 둔감) — 다른 것은 문자열 비교뿐입니다."""
    return unicodedata.normalize('NFC', s) if isinstance(s, str) else s


class _NFCFinder(importlib.abc.MetaPathFinder):
    """NFD 로 저장된 한글 이름 모듈을 import 할 수 있게 하는 마지막 순위 finder.

    Python 의 FileFinder 는 폴더 목록을 문자열 그대로 캐시해 대조하므로 `from _위치 import …` 는 NFD 이름의 `_위치.py` 를 못 찾아
    ModuleNotFoundError 가 됩니다(맥 구글드라이브 미러에서 확인 · 도구 README 「방법 메모」). 기본 finder 가 실패한 **한글 이름**에 한해
    이 파일이 든 폴더와 sys.path 의 폴더에서 NFC 로 같은 이름의 .py 를 찾아 경로로 적재합니다. ASCII 이름은 건드리지 않습니다.
    `_config` 를 먼저 import 하는 도구는 고치지 않아도 됩니다 — 그래서 한글 이름 모듈을 쓰는 도구는 `_config` 부터 import 합니다."""

    def find_spec(self, fullname, path=None, target=None):
        if path is not None or '.' in fullname or fullname.isascii():
            return None
        want = nfc(fullname)
        seen = set()
        for d in [os.path.dirname(os.path.abspath(__file__))] + [p for p in sys.path if isinstance(p, str) and p]:
            d = os.path.abspath(d)
            if d in seen:
                continue
            seen.add(d)
            try:
                names = os.listdir(d)
            except OSError:
                continue
            for f in names:
                stem, ext = os.path.splitext(f)
                if ext == '.py' and nfc(stem) == want:
                    return importlib.util.spec_from_file_location(fullname, os.path.join(d, f))
        return None


if not any(isinstance(f, _NFCFinder) for f in sys.meta_path):
    sys.meta_path.append(_NFCFinder())


def _콘솔_UTF8():
    """Windows 기본 콘솔(cp949)은 '—' 같은 문자를 못 써서 출력 도중 죽습니다.
    어느 셸에서 돌려도 되도록 표준 출력을 UTF-8 로 맞춥니다.
    `PYTHONIOENCODING` 을 앞에 붙일 필요가 없어집니다."""
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass

CONFIG_REL = os.path.join('.manuscript', 'project.json')
CONFIG_REL_OLD = os.path.join('.writing', 'project.json')   # 2026-09-01 이전 이름 — 폴백

# ---------------------------------------------------------------- 공유 정의 — 같은 개념은 여기 한 곳에
# 도판 · 표 표지. 번호점검은 kind 에 따라 평면 · 장-번호 중 하나만 받고, 위치 문법(_위치.py)은 둘 다 받습니다.
FIG_TAB_WORDS = r'(?:Figs?\.|Figures?|Tables?)'
FIG_TAB_NUM_FLAT = r'\d+'
FIG_TAB_NUM_CHAPTER = r'\d+-\d+'
FIG_TAB_NUM_ANY = r'\d+(?:-\d+)?'

# 상태 어휘. 정리 도구(이관 판정 · 상태 값 점검)와 색인 도구(상태 머리)가 함께 씁니다.
STATE_HEADS = ('반영 (확정 대기)', '부분 확정', '확정', '종결', '기록', '보류', '진행', '반영', '완료')
STATE_KNOWN = ('대기', '진행', '보류', '완료', '종결', '반영', '상시', '갱신')
STATE_CLOSED = ('완료', '종결')
STATE_OPEN_HINTS = ('필요', '대기')
STATE_PENDING_PREFIX = '반영'

# 추적 표의 행 문법. 정리 도구(행 읽기 · 이관 · 포커스) · 동기화(S7 ID 모음 · replace_once 의 표 검사) · 훅(쓰기 뒤 경고)이
# 같은 정의를 씁니다 — `| ID | … |` 한 줄이 항목 하나이고 셀 안의 `|` 는 `\|` 입니다(규약은 tracker-workflow.md 「표 행 형식」).
TABLE_ID = r'[A-Z]{1,2}\d+(?:-\d+)?'                                        # 행 ID — 글자 1–2 + 번호(-가지 번호)
TABLE_ROW_RE = re.compile(r'^\|\s*(' + TABLE_ID + r')\s*\|')                 # 한 줄에 match
TABLE_ROW_RE_M = re.compile(r'^\|\s*(' + TABLE_ID + r')\s*\|', re.M)         # 파일 전체에 findall
TABLE_SEP_RE = re.compile(r'^\|\s*:?-{3,}')                                  # 머리 아래 구분선 `|---|`
_TABLE_BREAK_RE = re.compile(r'^(?:<|#|>|[-*+] |\d+[.)] |```|---|\*\*\*)')  # 표를 끝내는 블록의 시작 — 고아 줄이 아닙니다
_CELL_SPLIT_RE = re.compile(r'(?<!\\)\|')
TABLE_PROBLEM_TEXT = {
    'orphan': '행 바로 아래에 표가 아닌 줄 — 행이 두 줄로 쪼개진 것. 위 행 끝에 합치거나(한 항목은 한 줄) 지우십시오',
    'cells': '셀 수가 머리와 다름 — 셀 안의 `|` 는 `\\|` 로 적습니다',
    'tail': '행 끝에 `|` 가 없음',
}


def split_cells(line):
    """'| a | b \\| c |' -> ['a', 'b \\| c'] — 셀 안의 `\\|` 는 경계가 아니고 그대로 둡니다(표 밖에 옮겨 적을 때는 unescape_cell)."""
    t = line.strip()
    if t.startswith('|'):
        t = t[1:]
    if t.endswith('|') and not t.endswith('\\|'):
        t = t[:-1]
    return [c.strip() for c in _CELL_SPLIT_RE.split(t)]


def unescape_cell(cell):
    """셀 값을 표 밖(문단)에 옮겨 적을 때 — `\\|` 를 `|` 로."""
    return cell.replace('\\|', '|')


def table_problems(text):
    """표 결함 — [(줄 번호(1부터), 코드, 그 줄 미리보기)]. 코드의 뜻은 TABLE_PROBLEM_TEXT.

    표는 `|` 로 시작하는 줄의 연속이고 첫 줄이 머리입니다. 빈 줄과 다른 블록(주석 `<!-- -->` · 제목 · 인용 · 목록 · 코드 펜스 · 가로줄)이
    표를 끝냅니다. 그 밖의 줄이 행 바로 아래 붙어 있으면 `orphan` — GFM 은 그 줄을 셀 하나짜리 행으로 그리고 도구는 ID 가 없어
    보지 못하므로, 행이 두 줄로 쪼개진 흔적입니다. 셀 수 · 끝 `|` 는 ID 를 읽을 수 있는 행만 봅니다(문헌의 상세 표처럼 ID 없는
    표는 형식이 자유롭습니다). 코드 펜스 안은 보지 않습니다. 줄끝은 CRLF 여도 됩니다.
    """
    out = []
    hdr_n, prev_row, in_code = None, False, False
    for n, line in enumerate(text.replace('\r\n', '\n').split('\n'), 1):
        if line.startswith('```'):
            in_code, prev_row = not in_code, False
            continue
        if in_code:
            continue
        if line.startswith('|'):
            if not prev_row:
                hdr_n = len(split_cells(line))
            elif not TABLE_SEP_RE.match(line) and TABLE_ROW_RE.match(line):
                if len(split_cells(line)) != hdr_n:
                    out.append((n, 'cells', line.strip()[:60]))
                r = line.rstrip()
                if not r.endswith('|') or r.endswith('\\|'):
                    out.append((n, 'tail', line.strip()[:60]))
            prev_row = True
            continue
        if prev_row and line.strip() and not _TABLE_BREAK_RE.match(line.lstrip()):
            out.append((n, 'orphan', line.strip()[:60]))
        prev_row = False
    return out


def describe_table_problem(prob):
    """(줄 번호, 코드, 미리보기) → 사람이 읽는 한 줄."""
    n, code, preview = prob
    return '%d행 %s: `%s`' % (n, TABLE_PROBLEM_TEXT.get(code, code), preview)


def is_orphan_after(lines, i):
    """lines[i] 가 행일 때, 그 바로 아래 줄이 고아 줄(쪼개진 꼬리)인지."""
    if i + 1 >= len(lines):
        return False
    nxt = lines[i + 1]
    return bool(nxt.strip()) and not nxt.startswith('|') and not _TABLE_BREAK_RE.match(nxt.lstrip())


_ROWISH_STRIP_RE = re.compile(r'[*`~\s]')


def row_like_id(line):
    """`|` 줄의 첫 셀이 ID 로 보이면 그 ID — 강조 · 코드 · 취소선 표시(`**A1**` · `` `A1` `` · `~~A1~~`)를 걷어 TABLE_ID 와 맞을 때. 아니면 None.
    TABLE_ROW_RE 로 읽히는 행도 같은 ID 를 돌려줍니다 — 부르는 쪽이 읽은 행과 견줘 「행처럼 보이는데 행으로 읽지 못한 줄」을 가려냅니다."""
    if not line.startswith('|') or TABLE_SEP_RE.match(line):
        return None
    first = _ROWISH_STRIP_RE.sub('', split_cells(line)[0])
    return first if re.fullmatch(TABLE_ID, first) else None


def id_key(rid):
    """ID 정렬 키 — `A2` < `A12` < `A12-1` < `B1`. 정리 도구(numkey) · 동기화(S3 · S7)가 함께 씁니다."""
    m = re.match(r'^([A-Z]+)(\d+)(?:-(\d+))?$', rid)
    return (m.group(1), int(m.group(2)), int(m.group(3) or 0)) if m else (rid, 0, 0)


# 새 미결 항목의 번호 — 도구(`미결_새항목.py`)가 정합니다. 범위의 정의는 여기 한 곳이고, 도구(배정)와 훅(손 등록 거부)이 함께 씁니다.
PROPOSAL_PREFIX = 'H'                                                        # 제안 파일의 ID 글자
NEW_ROW_RE = re.compile(r'^\|\s*([A-Z]{1,2})\?\s*\|')                        # 번호 자리가 `?` 인 새 행 — `| D? | … |`


def allocation_scope(cfg):
    """{글자: 루트 기준 파일(`/` 구분 · NFC)} — 번호를 도구가 정하는 표. 대기 파일의 분류 글자(tracker.movable_prefixes)와 제안 파일의 글자.
    문헌 파일은 표가 여러 종류라 넣지 않습니다. 이 밖의 파일 · 글자는 도구가 배정하지 않고 훅도 가리지 않습니다."""
    rel = lambda p: nfc(str(p).replace('\\', '/'))                           # noqa: E731
    out = dict((str(l), rel(cfg.pending_file)) for l in cfg.movable)
    out[PROPOSAL_PREFIX] = rel(cfg.proposals_file)
    return out


def id_stem(rid):
    """가지 번호의 줄기 — `D35-1` → `D35`. 가지가 없으면 그대로."""
    return rid.split('-', 1)[0]


# 목록(색인 파일)의 생성 블록에서 미결 ID 가 놓이는 자리. 정리 도구가 이 모양으로 쓰고, 동기화 S3 · 정리 도구의 자체 점검은 이 자리만 읽습니다 —
# 항목 · 위치 · 비고 같은 본문은 다른 문서의 라벨(반영계획의 결정 번호 `D4`, 다른 프로젝트의 `A40`)을 그대로 옮겨 싣기 때문입니다.
#   위치표   `| 파일 | 절 | ID · ID |`          끝 셀
#   트리거표 `| **조건** | ID · ID (n건) |`     끝 셀
#   지금     `| **ID** | 항목 | 위치 | 상태 |`  첫 셀
#   포커스   `#### ID — 항목`                   항목 머리(그 아래 비고 사본은 읽지 않음)
LIST_BLOCK_RE = re.compile(r'<!-- (위치표|트리거표|지금|포커스) -->(.*?)<!-- /\1 -->', re.S)
LIST_FOCUS_HEAD_RE = re.compile(r'^#### (' + TABLE_ID + r')\s+—', re.M)
_ID_TOKEN_RE = re.compile(r'(?<![\w-])(' + TABLE_ID + r')(?![\w-])')


def list_block_ids(text):
    """목록 text → ({블록 이름: [ID …]}, [모양을 읽지 못한 블록 …]).
    모양을 읽지 못함 — 블록 안에 ID 꼴 글자가 있는데 ID 자리에서는 하나도 읽지 못함(옛 판 · 손편집). 부르는 쪽이 경고합니다."""
    ids, unknown = {}, []
    for m in LIST_BLOCK_RE.finditer(text.replace('\r\n', '\n')):
        name, body = m.group(1), m.group(2)
        if name == '포커스':
            got = LIST_FOCUS_HEAD_RE.findall(body)
        else:
            got = []
            for line in body.split('\n'):
                if not line.startswith('|') or TABLE_SEP_RE.match(line):
                    continue
                cs = split_cells(line)
                got += _ID_TOKEN_RE.findall(cs[0] if name == '지금' else cs[-1])
        ids.setdefault(name, []).extend(got)
        if not got and _ID_TOKEN_RE.search(body):
            unknown.append(name)
    return ids, unknown


def _norm(s):
    """마크다운 강조 · 공백을 걷어낸 비교용 문자열"""
    import re, unicodedata
    return re.sub(r'\s+', '', re.sub(r'\*\*|`', '', unicodedata.normalize('NFC', s)))


def state_is_closed(status):
    """이 상태 값이면 목록에서 완료기록으로 넘깁니다.

    넘기지 않는 것 — `반영 (E61)`(사용자 확정 전) · `완료(육안 확인 필요)`(할 일이 남음) · `대기` `진행` `보류`.
    """
    s = _norm(status)
    if s.startswith(STATE_PENDING_PREFIX):
        return False
    if any(h in s for h in STATE_OPEN_HINTS):
        return False
    return any(c in s for c in STATE_CLOSED)


def state_head(status):
    """긴 상태 문자열의 머리 + 「관련 E…」. 색인 §2 가 씁니다.

    머리는 STATE_HEADS 중 첫 일치 또는 `… 대체됨 E<n>`, 없으면 첫 절(` — ` `(` `「` 앞, 24자까지).
    「관련」은 머리 뒤에 나오는 E 번호를 순서대로 중복 없이 붙입니다.
    """
    import re
    heads = sorted(STATE_HEADS, key=len, reverse=True)
    pat = re.compile(r'^\**\s*(' + '|'.join(re.escape(h) for h in heads) + r'|[^—(「\n]{0,20}?대체됨\s*E\d+)')
    m = pat.match(status)
    if m:
        h, rest = m.group(1).strip('* '), status[m.end():]
    else:
        h = re.split(r' — |\(|「', status)[0].strip('* ')[:24]
        rest = status[len(h):]
    refs = []
    for r in re.findall(r'E\d+', rest):
        if r not in refs and r not in h:
            refs.append(r)
    return h + ((' · 관련 ' + ' '.join(refs)) if refs else '')

DEFAULTS = {
    "manuscript": {
        "source_dir": "초안_소스",
        "chapters": [{"n": i, "file": "ch%d.md" % i} for i in (1, 2, 3, 4)],
        "references": "references.md",
        "build_script": "build_tpl.py",
        "figure_dir": "fig_src",
    },
    "tracker": {
        "index": "수정필요_목록.md",
        "pending": "수정필요_대기.md",
        "record_index": "수정필요_색인.md",
        "literature": "수정필요_문헌.md",
        "proposals": "수정필요_제안.md",
        "records_dir": "완료기록",
        "archive": "완료기록/이관_DB.md",
        "record_prefix": "E",
        "movable_prefixes": ["A", "B", "C", "D"],
        "index_size_limit_kb": 40,
        # 공통 다섯 — 심사 · 투고 일정에 걸린 값은 프로젝트의 project.json(tracker.triggers)이 더합니다
        "triggers": ["지금", "해당 절 작업 시", "사용자 판단", "자료 확보 후", "최종 제출 직전"],
        # 위치 문법(_위치.py) — 프로젝트가 더하는 절 표기(정규식 목록)와 완료 색인 §1 에서 뺄 파일(글롭 목록)
        "section_markers": [],
        "record_index_exclude": [],
        # 인수인계(현재 상태) 파일 — 갈아쓰는 문서라 동기화 손실 보고(S6)에서 뺍니다. 없으면 빈 문자열
        "checkpoint": "",
    },
    # 공용 파일 동기화 안전장치(_동기화.py) — 값의 뜻은 tracker-workflow.md 「동기화」. 핵심 검사는 이 기본값만으로도 돕니다.
    "sync": {
        "shared_extra": [],                        # 추적 파일 · 완료기록 · 원고 md 말고도 공용인 파일(루트 기준 글롭)
        "snapshot_dir": "보관/추적_백업",            # 드라이브 쪽 스냅샷 폴더(루트 기준)
        "conflict_patterns": [" \\d+$", " \\(\\d+\\)$", "conflicted copy"],   # 충돌 사본 이름(확장자 뺀 이름에 대조)
        "exclude": [".git/", "__pycache__/", "node_modules/", "보관/", ".manuscript/도구_백업/"],
        "stale_days": 2,
        "snapshot_days": 30,                       # 자기 컴퓨터 스냅샷의 보존 기간(드라이브 — 로컬은 2배)
        "snapshot_days_others": 90,                # 다른 컴퓨터가 만든 스냅샷을 지울 수 있는 나이
        "snapshot_min": 10,                        # 파일마다 늘 남기는 최근 개수
        "snapshot_max": 20,                        # 파일마다 자기 컴퓨터 스냅샷의 개수 상한(드라이브)
        "snapshot_max_local": 100,                 # 같은 상한(로컬 — 쓰기마다 남기므로 더 큼)
        "ack_hours": 4,
        "known_gaps": [],                          # 완료기록 번호 가운데 원래 비어 있는 것
        "rewrite_ok": [],                          # 갈아쓰는 문서 — 손실 보고에서 뺌(checkpoint 는 자동)
        "survival_pct": 70,
    },
}


def project_root(start=None):
    """`도구/` 안에서 불리면 그 상위를, 아니면 주어진 폴더를 프로젝트 루트로 봅니다."""
    if start:
        return os.path.abspath(start)
    d = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(d) if os.path.basename(d) == '도구' else d


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


class Config(object):
    def __init__(self, root, raw):
        self.root = root
        self.raw = raw
        self.name = raw.get('project', os.path.basename(root))
        self.kind = raw.get('kind', 'manuscript')
        self._m = raw['manuscript']
        self._t = raw['tracker']

    # ---- 원고
    @property
    def source_dir(self):
        p = os.path.join(self.root, self._m['source_dir'])
        return p if os.path.isdir(p) else self.root

    @property
    def source_rel(self):
        """원고 폴더의 루트 기준 이름(`/` 구분, 끝 `/` 없음). 위치 문법이 표시 · 해석에 씁니다."""
        return str(self._m['source_dir']).replace('\\', '/').strip('/')

    @property
    def output_pattern(self):
        """빌드 산출물 이름 글롭(예: `원고_v*.docx`). 없으면 None — 완료 색인이 그 파일을 뺄 때 씁니다."""
        return self._m.get('output_pattern') or None

    @property
    def chapters(self):
        """[(번호, 파일명), ...] — 번호점검·빌드가 쓰는 형태"""
        return [(c['n'], c['file']) for c in self._m['chapters']]

    @property
    def references(self):
        return self._m['references']

    @property
    def build_script(self):
        return self._m['build_script']

    # ---- 추적
    @property
    def tracker_files(self):
        """정리 도구가 다루는 다섯 파일. 순서는 기존 동작과 같게 유지합니다."""
        t = self._t
        return [t['index'], t['pending'], t['record_index'], t['literature'], t['proposals']]

    @property
    def index_file(self):
        return self._t['index']

    @property
    def pending_file(self):
        return self._t['pending']

    @property
    def record_index_file(self):
        return self._t['record_index']

    @property
    def literature_file(self):
        return self._t['literature']

    @property
    def proposals_file(self):
        return self._t['proposals']

    @property
    def records_dir(self):
        return self._t['records_dir']

    @property
    def archive(self):
        return os.path.join(*self._t['archive'].split('/'))

    @property
    def triggers(self):
        return list(self._t['triggers'])

    @property
    def movable(self):
        return list(self._t['movable_prefixes'])

    @property
    def index_limit(self):
        return int(self._t['index_size_limit_kb']) * 1024

    @property
    def section_markers(self):
        """프로젝트가 더하는 절 표기 — 정규식 문자열 목록. 기본은 빈 목록입니다."""
        return list(self._t.get('section_markers') or [])

    @property
    def record_index_exclude(self):
        """완료 색인 §1 에서 뺄 파일 · 폴더의 글롭 목록(루트 기준, 폴더는 끝 `/`). 기본은 빈 목록입니다."""
        return list(self._t.get('record_index_exclude') or [])

    @property
    def checkpoint(self):
        """인수인계 파일(루트 기준). 없으면 None."""
        return (self._t.get('checkpoint') or None)

    # ---- 동기화
    @property
    def sync(self):
        """동기화 안전장치 설정(기본값과 합쳐진 dict). 뜻은 tracker-workflow.md 「동기화」."""
        return dict(self.raw.get('sync') or {})

    def __getitem__(self, k):
        return self.raw[k]


def load(root=None):
    root = project_root(root)
    path = os.path.join(root, CONFIG_REL)
    if not os.path.isfile(path):
        old = os.path.join(root, CONFIG_REL_OLD)
        if os.path.isfile(old):
            path = old
    raw = {}
    if os.path.isfile(path):
        try:
            with io.open(path, encoding='utf-8') as f:
                raw = json.load(f)
        except ValueError as e:
            raise SystemExit('%s 를 읽지 못했습니다: %s' % (CONFIG_REL, e))
    return Config(root, _merge(DEFAULTS, raw))


if __name__ == '__main__':
    _콘솔_UTF8()
    c = load()
    print('project    :', c.name, '(%s)' % c.kind)
    print('root       :', c.root)
    print('source_dir :', c.source_dir)
    print('chapters   :', c.chapters)
    print('references :', c.references)
    print('tracker    :', c.tracker_files)
    print('records    :', c.records_dir, '/ archive:', c.archive)
    print('triggers   :', len(c.triggers), '개')
    print('movable    :', c.movable, '/ limit:', c.index_limit)
