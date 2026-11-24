#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""추적 파일 정리·검사 도구. 파일 이름은 `.manuscript/project.json` 을 따르고, 아래는 기본값입니다.

    tracker_index.md          색인·규칙·상시 제약. 매 세션 통독. §3~§5 는 이 도구가 생성
    tracker_pending.md        미결 항목 본문 A·B·C·D. 색인에서 ID 를 얻어 그 항목만 읽습니다
    tracker_records_index.md  완료 기록 색인 — tools/index_records.py 가 생성
    records/E*.md             완료 기록 본문. 항목당 한 파일
    records/archive.md        D·B 에서 이관한 완료 항목
    tracker_literature.md     문헌 라이브러리 F, 참고문헌 대조 G
    tracker_proposals.md      채택 여부 결정 대기 제안 H

§3 위치 표·§4 트리거 표·§5 지금 손댈 수 있는 항목은 전부 이 도구가 본문에서 만듭니다.

세션을 마칠 때 돌립니다. 완료된 항목을 대기 파일에서 완료기록으로 넘기고,
색인 파일이 매 세션 읽어도 부담 없는 크기로 남게 유지합니다.

사용법  (`<py>` 는 이 컴퓨터의 Python 3 — 윈도 `python` · 맥 `python3`)
    <py> tools/tidy_tracker.py                 진단만. 파일을 고치지 않습니다
    <py> tools/tidy_tracker.py --apply         고칠 수 있는 것을 반영합니다
    <py> tools/tidy_tracker.py --dir <경로>    파일이 있는 폴더 지정
                                               (기본: 도구 폴더의 상위 = 프로젝트 루트)

G 드라이브 미러처럼 셸이 폴더에 닿지 않는 환경에서는(F11) 네 파일을 스테이징한
사본에 대해 돌린 뒤 되돌려 씁니다.

돌려도 안전합니다 — 두 번 돌리면 두 번째는 아무것도 바꾸지 않습니다(멱등).

`--apply` 의 순서는 「잠금 → 읽기 → 계산 → 읽은 뒤 바뀌었는지 전체 검사 → 저장」입니다. 다른 세션이 열려 있어도 돌립니다 —
잠금(`_sync.WriteLock`)은 이 한 번의 실행 동안만 잡고, 읽은 뒤 바뀐 파일이 하나라도 있으면 **아무것도 저장하지 않고** 처음부터
한 번 더 읽어 시도합니다(일부만 저장하면 이관하던 행이 대기 · 이관 어디에도 없게 됩니다). 완료 색인은 기록 파일에서 통째로 다시
만드는 파일이라 계산 도중에 바로 씁니다.

종료 코드 — 0 정상 · 1 확인 필요(경고) · 2 인자 · 파일 없음 · 3 동기화 점검 ERROR 로 거부 ·
            4 저장 거부(잠금을 못 잡았거나 두 번 모두 읽은 뒤 파일이 바뀜) — 다시 돌리면 됩니다.
"""

import argparse, datetime, os, re, sys, unicodedata

def _콘솔_UTF8():
    """Windows 기본 콘솔(cp949)은 '—' 같은 문자를 못 써서 출력 도중 죽습니다.
    어느 셸에서 돌려도 되도록 표준 출력을 UTF-8 로 맞춥니다.
    `PYTHONIOENCODING` 을 앞에 붙일 필요가 없어집니다."""
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


_콘솔_UTF8()


HDR = re.compile(r'^\|\s*ID\s*\|')
# 완료기록 §3 본문은 2026-08-16부터 표가 아니라 소제목입니다.
# 내용 열이 최장 5,232자여서 표로 렌더하면 마지막 열이 화면 밖으로 밀렸습니다.
HEAD = re.compile(r'^###\s+([A-Z][0-9]+(?:-[0-9]+)?)\s+—\s+(.*)$')
DATE = re.compile(r'^\*\*완료일\*\*\s*(.*)$')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import (load as _load_cfg, project_root, state_is_closed, STATE_KNOWN,                       # noqa: E402  — 상태 어휘는 _config.py 한 곳
                     TABLE_ROW_RE as ROW, TABLE_SEP_RE, split_cells as cells, unescape_cell,    # 표 행 문법도 _config.py 한 곳 —
                     table_problems, describe_table_problem, is_orphan_after, row_like_id,      # 동기화(S7 · replace_once) · 훅과 같은 정의
                     id_key as numkey, list_block_ids)                                          # ID 정렬 · 목록의 ID 자리 — 동기화 S3 과 같은 정의
from _location import Grammar, section_key                                 # noqa: E402  — 위치 문법은 _location.py 한 곳
from _sync import Sync, refuse_if_alert                                # noqa: E402  — 동기화 안전장치는 _sync.py 한 곳

# 파일 이름·트리거 값은 `.manuscript/project.json` 이 정합니다. 없으면 기본값이 쓰입니다.
_CFG = _load_cfg()
FILES = _CFG.tracker_files
TRIGGERS = _CFG.triggers        # 표의 묶음 순서도 이 순서입니다
REC = _CFG.archive              # 이관분
REC_SHOW = REC.replace('/', '\\')  # 생성 문구 속 표기 — 운영체제와 무관하게 같은 글자
HOT_LIMIT = _CFG.index_limit    # 목록 파일이 이 크기를 넘으면 구조를 다시 살펴봅니다
MOVABLE = _CFG.movable          # 목록에서 완료기록으로 넘길지 판정할 때 쓰는 분류


# ---------------------------------------------------------------- 유틸
def norm(s):
    """마크다운 강조·공백을 걷어낸 비교용 문자열"""
    return re.sub(r'\s+', '', re.sub(r'\*\*|`', '', unicodedata.normalize('NFC', s)))


def strip_md(s):
    return re.sub(r'\s+', ' ', re.sub(r'\*\*|`', '', s)).strip()


# numkey(i) — ID 정렬 키. _config.id_key 의 별칭입니다(동기화 S3 · S7 과 같은 정의).
# cells(line) — '| a | b \| c |' -> ['a', 'b \| c']. _config.split_cells 의 별칭입니다(셀 안의 `\|` 는 경계가 아님).


def is_closed(status):
    """이 상태 값이면 목록에서 완료기록으로 넘깁니다. 판정 어휘는 `_config.py`(색인 도구와 공유)에 있습니다."""
    return state_is_closed(status)


RC_REFUSED = 4      # 저장 거부 — 잠금을 못 잡았거나, 읽은 뒤 파일이 바뀜. 다시 돌리면 됩니다


class StaleFile(Exception):
    """읽은 뒤 남이 고친 파일. 다른 창에서 직접 편집 중일 때 덮어쓰지 않기 위한 것입니다."""


class Doc:
    def __init__(self, path):
        self.path = path
        self.orig = open(path, encoding='utf-8').read()
        self.lines = self.orig.split('\n')
        self.mtime = os.path.getmtime(path)

    def dirty(self):
        return '\n'.join(self.lines) != self.orig

    def stale(self):
        """읽은 뒤 파일이 바뀌었으면 True. 내용까지 대조해 mtime 만 튄 경우는 걸러냅니다."""
        if os.path.getmtime(self.path) == self.mtime:
            return False
        return open(self.path, encoding='utf-8').read() != self.orig

    def save(self):
        if self.stale():
            raise StaleFile(self.path)
        open(self.path, 'w', encoding='utf-8', newline='').write('\n'.join(self.lines).rstrip() + '\n')

    def block(self, name):
        """<!-- name --> ... <!-- /name --> 의 (시작, 끝) 인덱스. 끝은 닫는 줄 자체."""
        try:
            a = self.lines.index(f'<!-- {name} -->')
            b = self.lines.index(f'<!-- /{name} -->')
        except ValueError:
            return None
        return a, b

    def set_block(self, name, body):
        """블록 안을 body(리스트)로 교체. 바뀌었으면 True"""
        bl = self.block(name)
        if bl is None:
            return None
        a, b = bl
        if self.lines[a + 1:b] == body:
            return False
        self.lines[a + 1:b] = body
        return True

    def sections(self):
        """'## X. ...' 제목별 (제목, 시작, 끝) 목록"""
        out, cur = [], None
        for i, l in enumerate(self.lines):
            if l.startswith('## '):
                if cur:
                    out.append(cur + (i,))
                cur = (l, i)
        if cur:
            out.append(cur + (len(self.lines),))
        return out


def table_rows(lines, a, b):
    """구간 안의 (인덱스, ID, 셀목록, 컬럼명목록)"""
    hdr = None
    out = []
    for i in range(a, b):
        l = lines[i]
        if HDR.match(l):
            hdr = cells(l)
        m = ROW.match(l)
        if m and hdr:
            out.append((i, m.group(1), cells(l), hdr))
    return out


def entries(lines, a, b):
    """소제목 형식 항목의 (인덱스, ID, 제목, 완료일)

    `### E47 — 제목` 다음에 오는 `**완료일** 2026-08-05` 를 함께 읽습니다.
    제목 안에 `—` 가 더 있어도 첫 구분자만 쓰므로 그대로 보존됩니다.
    """
    out = []
    for i in range(a, b):
        m = HEAD.match(lines[i])
        if not m:
            continue
        date = ''
        for j in range(i + 1, min(i + 6, b)):
            if HEAD.match(lines[j]):
                break
            d = DATE.match(lines[j])
            if d:
                date = d.group(1).strip()
                break
        out.append((i, m.group(1), m.group(2).strip(), date))
    return out


def cls_of(rid):
    return re.match(r'^[A-Z]+', rid).group(0)


# 위치 키는 `_location.py` 의 문법이 정합니다 — 완료 색인 §1 · 여기 §3 위치 표 · 포커스가 같은 정의를 씁니다.
_GRAMMAR = None


def grammar():
    global _GRAMMAR
    if _GRAMMAR is None:
        _GRAMMAR = Grammar(_CFG)
    return _GRAMMAR


def loc_rows(cell):
    """`위치` 칸을 [(루트 기준 경로, 절, 파일인가), ...] 로. 파일 없는 글은 (글, '', False), 빈 칸은 ('(위치 미기재)', '', False).

    제외는 적용하지 않습니다 — 미결의 위치는 실제 수정 지점이라 추적 파일을 적은 항목도 그대로 둡니다.
    둘째 반환값은 해석 결과(경고 판정에 씁니다).
    """
    p = grammar().parse(cell)
    out = []
    if p.files:
        for path, secs in p.files.items():
            for s in (secs or ['']):
                out.append((path, s, True))
    elif p.free_text:
        out.append((p.free_text, '', False))
    else:
        out.append(('(위치 미기재)', '', False))
    return out, p


def loc_bad(p):
    """고칠 수 있는 위치의 해석 실패 — 빈 칸이거나, 절 · 식별자 표기만 있고 붙일 파일이 없을 때."""
    return p.empty or (not p.files and bool(p.orphans))


def loc_sort(row):
    path, sec = row[0], row[1]
    return grammar().sort_key(path, sec)


def col(hdr, name, default=None):
    for j, h in enumerate(hdr):
        if norm(h) == norm(name):
            return j
    return default


# 표마다 열 이름이 다릅니다 — 대기(`항목`·`비고`), 제안(`제안`·`근거`).
def col_any(hdr, names, fallback=None):
    for nm in names:
        j = col(hdr, nm)
        if j is not None:
            return j
    return fallback


# ---------------------------------------------------------------- 본체
class Tidy:
    def __init__(self, d, apply_, focus=None, sync=None):
        self.apply = apply_
        self.focus = focus          # 'ch3' / 'off' / None(그대로 둠)
        self.d = d
        self.hot = Doc(os.path.join(d, _CFG.index_file))
        self.pend = Doc(os.path.join(d, _CFG.pending_file))
        self.rec = Doc(os.path.join(d, REC))
        self.lit = Doc(os.path.join(d, _CFG.literature_file))
        self.pro = Doc(os.path.join(d, _CFG.proposals_file))
        self.notes, self.warns, self.acts = [], [], []
        self._open_state = None     # (미결 행, 건너뛸 까닭) — _rows_or_gaps 가 한 실행에 한 번 정합니다
        self.stale = []             # 저장 전 검사에서 걸린 파일 — 읽은 뒤 남이 고침
        self.sync = sync or Sync(_CFG)
        for f in FILES + [REC]:                    # 쓰기 직전 판을 로컬 스냅샷으로 — 뒤의 차이 계산 · 복구용(같은 해시면 안 만듦)
            self.sync.before_write(f.replace('\\', '/'))

    def warn(self, s):
        self.warns.append(s)

    def act(self, s):
        self.acts.append(s)

    # --- 1) 완료·종결 항목을 목록 → 완료기록 §4 ---
    def migrate(self):
        blk = self.rec.block('본문:이관')
        if blk is None:
            self.warn('완료기록에 `<!-- 본문:이관 -->` 블록이 없습니다. 이관을 건너뜁니다.')
            return
        a, b = blk
        dest_hdr = cells(self.rec.lines[a + 1])
        # 머리 아래 구분선 — 옛 판의 첫 이관이 행 자리와 함께 지웠던 것을 복원합니다(없으면 Markdown 표로 그려지지 않음)
        if not (a + 2 < b and TABLE_SEP_RE.match(self.rec.lines[a + 2])):
            self.rec.lines.insert(a + 2, '|' + '---|' * len(dest_hdr))
            a, b = self.rec.block('본문:이관')
            self.act(f'{REC} 이관 표의 머리 아래 구분선 복원')
        # 행이 아닌 줄(쪼개진 꼬리 등)이 표 안에 있으면 다시 쓰다가 지워집니다 — 이관을 건너뛰고 먼저 고치게 합니다
        stray = [(i + 1, l) for i, l in enumerate(self.rec.lines[a + 3:b], a + 3) if l.strip() and not ROW.match(l)]
        if stray:
            self.warn(f'{REC} 이관 표 안에 행이 아닌 줄이 있어 이관을 건너뜁니다 — 먼저 고치십시오: '
                      + ' · '.join(f'{n}행 `{l.strip()[:40]}`' for n, l in stray[:5]))
        existing = [l for l in self.rec.lines[a + 1:b] if ROW.match(l)]
        moved_by_cls, drop, held = {}, [], []

        for title, s, e in ([] if stray else self.pend.sections()):
            m = re.match(r'^## ([A-Z])\. ', title)
            if not m or m.group(1) not in MOVABLE:
                continue
            cls = m.group(1)
            for i, rid, cs, hdr in table_rows(self.pend.lines, s, e):
                si = col(hdr, '상태')
                if si is None or si >= len(cs) or not is_closed(cs[si]):
                    continue
                if is_orphan_after(self.pend.lines, i):      # 행이 두 줄로 쪼개져 있음 — 옮기면 꼬리만 대기 파일에 남습니다
                    held.append(rid)
                    self.warn(f'대기 {rid}: 행 바로 아래 {i + 2}행에 표가 아닌 줄이 붙어 있어 이관을 보류합니다 — '
                              f'행에 합치거나 지운 뒤 다시 돌리십시오: `{self.pend.lines[i + 1].strip()[:40]}`')
                    continue
                # 원본 표의 컬럼을 §4 스키마(ID·항목·위치·상태·비고)로 맞춥니다
                out = []
                for name in dest_hdr:
                    j = col(hdr, name)
                    out.append(cs[j] if j is not None and j < len(cs) else '')
                ti = col(hdr, '트리거')
                bi = col(dest_hdr, '비고')
                if ti is not None and ti < len(cs) and cs[ti] and bi is not None:
                    out[bi] = (f'(트리거: {cs[ti]}) ' + out[bi]).strip()
                existing.append('| ' + ' | '.join(out) + ' |')
                moved_by_cls.setdefault(cls, []).append(rid)
                drop.append(i)

        if not drop:
            if not stray and not held:
                self.notes.append('이관 대상 없음 — 대기 파일에 완료·종결 항목이 남아 있지 않습니다.')
        else:
            for cls, ids in sorted(moved_by_cls.items()):
                self.act(f'{cls} 표에서 완료·종결 {len(ids)}건을 완료기록 §4로 이관: ' + ' · '.join(ids))
            if self.apply:
                for i in sorted(drop, reverse=True):
                    del self.pend.lines[i]
                a, b = self.rec.block('본문:이관')
                self.rec.lines[a + 3:b] = sorted(                 # 머리 · 구분선은 두고 행만 다시 씁니다
                    existing, key=lambda l: numkey(ROW.match(l).group(1)))

        # 이관 목록 줄 갱신 (블록이 있는 분류만)
        a, b = self.rec.block('본문:이관')
        now = [ROW.match(l).group(1) for l in self.rec.lines[a:b] if ROW.match(l)]
        for cls in MOVABLE:
            if self.pend.block(f'이관목록:{cls}') is None:
                if cls in moved_by_cls:
                    self.warn(f'대기 {cls} 표에 `<!-- 이관목록:{cls} -->` 블록이 없어 '
                              f'{" · ".join(moved_by_cls[cls])} 를 어디로 옮겼는지 흔적이 남지 않았습니다. '
                              f'{cls} 표 아래에 블록을 만들고 다시 돌리십시오.')
                continue
            ids = sorted([i for i in now if i.startswith(cls)], key=numkey)
            if not ids:
                body = [f'> 완료·종결로 `{REC_SHOW}` 로 옮긴 {cls} 항목은 아직 없습니다.']
            else:
                body = [f'> 완료·종결된 {cls} 항목 {len(ids)}건은 `{REC_SHOW}` 로 옮겼습니다 —',
                        '> **' + ' · '.join(ids) + '**.']
            r = self.pend.set_block(f'이관목록:{cls}', body)
            if r:
                self.act(f'{cls} 이관 목록 줄 갱신 ({len(ids)}건)')

    # --- 2) 완료기록 색인 재생성 (완료기록\E*.md → 수정필요_색인.md) ---
    _idx_mod = None

    def 색인모듈(self):
        """색인 규칙은 `index_records.py` 한 곳에만 둡니다. 여기서는 불러 씁니다."""
        if Tidy._idx_mod is None:
            import importlib.util
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index_records.py')
            if not os.path.exists(p):
                return None
            spec = importlib.util.spec_from_file_location('index_records', p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            Tidy._idx_mod = m
        return Tidy._idx_mod

    def reindex(self):
        m = self.색인모듈()
        if m is None:
            self.warn(f'{_CFG.tool("index_records.py")} 가 없어 색인을 다시 만들지 못했습니다.')
            return
        text, ents, _ = m.render_index()
        if text is None:
            self.warn(f'{_CFG.records_dir}/E*.md 를 찾을 수 없습니다. 색인 재생성을 건너뜁니다.')
            return
        cur = open(m.IDX, encoding='utf-8').read() if os.path.exists(m.IDX) else ''
        if cur == text:
            self.notes.append(f'{_CFG.record_index_file} 최신 — 완료기록 {len(ents)}건')
            return
        self.act(f'{_CFG.record_index_file} 재생성 (완료기록 {len(ents)}건)')
        if self.apply:
            open(m.IDX, 'w', encoding='utf-8', newline='').write(text)
            self.sync.after_write(_CFG.record_index_file.replace('\\', '/'))

    # --- 3) 상시 F 항목을 문헌 → 목록으로 동기화 ---
    def sync_f(self):
        blk = self.hot.block('상시F')
        if blk is None:
            self.warn('목록에 `<!-- 상시F -->` 블록이 없습니다. 동기화를 건너뜁니다.')
            return
        a, b = blk
        want_ids = [ROW.match(l).group(1) for l in self.hot.lines[a:b] if ROW.match(l)]
        src = {}
        for title, s, e in self.lit.sections():
            if title.startswith('## F.'):
                for i, rid, _, _ in table_rows(self.lit.lines, s, e):
                    src[rid] = self.lit.lines[i]
        miss = [i for i in want_ids if i not in src]
        if miss:
            self.warn(f'상시 F 항목 {miss} 가 `{_CFG.literature_file}` §F에 없습니다.')
            return
        # 표 헤더 두 줄을 그대로 두고 그 아래만 갈아 끼웁니다.
        # 블록이 비어 있으면 a+2 가 닫는 줄(b)이 되므로 b 를 넘지 않게 자릅니다 —
        # 넘기면 닫는 마커가 본문으로 복사돼 실행할 때마다 하나씩 늘어납니다.
        head = self.hot.lines[a + 1:min(a + 3, b)]
        body = head + [src[i] for i in want_ids]
        r = self.hot.set_block('상시F', body)
        if r:
            self.act(f'상시 환경 제약 {want_ids} 를 문헌 파일 기준으로 동기화')

    # --- 4) 검사만 ---
    def audit(self):
        # 표 행 형식 — 쪼개진 행(고아 줄) · 셀 수 · 끝 `|`. 문법은 _config.table_problems 한 곳(replace_once · 훅과 같음)
        for doc, label in [(self.pend, '대기'), (self.pro, '제안'), (self.lit, '문헌'), (self.rec, '이관_DB')]:
            for prob in table_problems('\n'.join(doc.lines)):
                self.warn(f'{label}: 표 행 형식 — ' + describe_table_problem(prob))
        # 행처럼 보이는데 미결 행으로 읽지 못한 줄 — 목록에도 동기화 대조(S3 · S7)에도 실리지 않습니다(정의는 _unread_rows)
        for label, n, preview in self._unread_rows():
            self.warn(f'{label}: {n}행 행처럼 보이지만 미결 행으로 읽지 못함 — 분류 절(`## X.`) · 제안 파일의 `| ID |` 표 안에 '
                      f'ID 를 꾸밈 없이(`| A1 |`) 적으십시오: `{preview}`')

        # ID 중복·결번
        for doc, label in [(self.rec, '이관_DB'), (self.pend, '대기'),
                           (self.lit, '문헌'), (self.pro, '제안')]:
            seen = {}
            # 이관_DB.md 는 `## ` 절이 없는 한 장짜리 표입니다 — 파일 전체를 봅니다
            spans = [('', 0, len(doc.lines))] if doc is self.rec else doc.sections()
            for title, s, e in spans:
                if title.startswith('## 2.'):      # 개번 대응표는 항목 표가 아닙니다
                    continue
                for i, rid, cs, hdr in table_rows(doc.lines, s, e):
                    if len(cs) < 4:                 # 색인표(3열)는 제외
                        continue
                    seen.setdefault(rid, []).append(i + 1)
                for i, rid, _t, _d in entries(doc.lines, s, e):   # 소제목 형식 항목
                    seen.setdefault(rid, []).append(i + 1)
            dup = {k: v for k, v in seen.items() if len(v) > 1}
            if dup:
                self.warn(f'{label}: ID 중복 ' + ', '.join(f'{k}({v}행)' for k, v in dup.items()))

        # 완료기록 항목 파일 — 대상 미기재·E 결번 (규칙은 index_records.py 에 있습니다)
        m = self.색인모듈()
        if m is not None:
            for w in m.warnings_for(m.read_entries()):
                self.warn(w)

        # H 위치 표 ↔ H 항목
        hids = {r[1] for r in table_rows(self.pro.lines, 0, len(self.pro.lines))
                if r[1].startswith('H')}
        for doc, label in [(self.pro, '제안')]:
            bl = doc.block('H위치')
            if bl is None:
                continue
            a, b = bl
            listed = set(re.findall(r'\bH\d+\b', '\n'.join(doc.lines[a:b])))
            if hids - listed:
                self.warn(f'{label} 위치 표에 빠진 제안: {sorted(hids - listed, key=numkey)}')
            if listed - hids:
                self.warn(f'{label} 위치 표에 없는 제안이 적혀 있습니다: {sorted(listed - hids, key=numkey)}')

        # 상태·트리거 값 점검
        want = {norm(t) for t in TRIGGERS}
        for title, s, e in self.pend.sections():
            m = re.match(r'^## ([A-Z])\. ', title)
            if not m:
                continue
            for i, rid, cs, hdr in table_rows(self.pend.lines, s, e):
                si = col(hdr, '상태')
                if si is not None and si < len(cs):
                    v = norm(cs[si])
                    if not v:
                        self.warn(f'대기 {rid}: 상태 값이 비어 있습니다 ({i+1}행)')
                    elif not any(k in v for k in STATE_KNOWN):
                        self.warn(f'대기 {rid}: 알 수 없는 상태 값 `{cs[si]}` ({i+1}행)')
                ti = col(hdr, '트리거')
                if ti is None:
                    self.warn(f'대기 {cls_of(rid)} 표에 `트리거` 열이 없습니다 ({i+1}행)')
                elif ti >= len(cs) or not norm(cs[ti]):
                    self.warn(f'대기 {rid}: 트리거 값이 비어 있습니다 ({i+1}행)')
                elif norm(cs[ti]) not in want:
                    self.warn(f'대기 {rid}: 알 수 없는 트리거 `{cs[ti]}` ({i+1}행). '
                              f'쓸 수 있는 값 — ' + ' · '.join(TRIGGERS))

    # --- 4.5) §3 위치 표 · §4 트리거 표 · §5 지금 손댈 수 있는 항목 재생성 ---
    def _open_spans(self):
        """미결 행을 읽는 곳 — [(문서, 이름, 시작, 끝, 받는 ID 글자)]. 행 읽기(_open_rows)와 읽기 점검(_unread_rows · _read_gaps)이 같은 곳을 봅니다.
        대기 파일은 분류 글자(movable_prefixes)의 `## X.` 절, 제안 파일은 `## ` 절이 없는 한 장짜리 표라 파일 전체(H)입니다."""
        out = []
        for title, s, e in self.pend.sections():
            m = re.match(r'^## ([A-Z])[.\s]', title)
            if m and m.group(1) in MOVABLE:
                out.append((self.pend, '대기', s, e, tuple(MOVABLE)))
        out.append((self.pro, '제안', 0, len(self.pro.lines), ('H',)))
        return out

    def _open_rows(self):
        """미결 항목 전체. (ID, 항목, 위치, 트리거, 상태) 튜플.

        대기 파일의 A·B·C·D 와 제안 파일의 H 를 함께 봅니다(읽는 곳은 _open_spans).
        H 는 이관하지 않고 버리면 상태만 `종결` 로 적으므로(제안 파일 머리) 완료·종결 H 는 뺍니다.
        상태 열이 없는 H 는 모두 미결로 봅니다. A·B·C·D 는 거르지 않습니다 —
        완료·종결은 `--apply` 때 migrate() 가 먼저 옮깁니다.
        """
        rows = []
        for doc, _label, s, e, only in self._open_spans():
            for i, rid, cs, hdr in table_rows(doc.lines, s, e):
                if not rid.startswith(only):
                    continue
                def cell(j):
                    return cs[j] if j is not None and 0 <= j < len(cs) else ''
                if doc is self.pro and is_closed(cell(col(hdr, '상태'))):
                    continue
                rows.append((rid,
                             strip_md(cell(col_any(hdr, ['항목', '제안'], 1))),
                             cell(col(hdr, '위치', 2)),
                             strip_md(cell(col(hdr, '트리거'))),
                             strip_md(cell(col(hdr, '상태')))))
        return rows

    def _unread_rows(self):
        """행처럼 보이는데 미결 행으로 읽지 못한 줄 — [(이름, 줄 번호(1부터), 미리보기)].
        첫 셀이 ID 꼴(_config.row_like_id)이고 그 파일이 받는 글자로 시작하는데 _open_spans 의 표 행으로 읽히지 않은 `|` 줄입니다 —
        읽는 곳 밖(분류 절이 아닌 절) · `| ID |` 머리 앞의 행, 꾸밈이 붙은 ID(`| **A1** |`). 코드 펜스 안은 보지 않습니다(table_problems 와 같음)."""
        spans = self._open_spans()
        out = []
        for doc, label, only in [(self.pend, '대기', tuple(MOVABLE)), (self.pro, '제안', ('H',))]:
            read = {r[0] for d, _l, s, e, _o in spans if d is doc for r in table_rows(doc.lines, s, e)}
            in_code = False
            for i, line in enumerate(doc.lines):
                if line.startswith('```'):
                    in_code = not in_code
                    continue
                rid = None if in_code else row_like_id(line)
                if rid and rid.startswith(only) and i not in read:
                    out.append((label, i + 1, line.strip()[:40]))
        return out

    def _read_gaps(self):
        """미결 행을 다 읽었다고 볼 수 없는 까닭 — [짧은 문장]. 빈 목록이면 읽은 행이 전부입니다.

        미결이 0건일 때 목록의 생성 블록을 비울지(대기 · 제안 파일의 표 구조는 정상인데 열린 행이 정말 0건 — 마지막 행을 지웠거나 모두 이관됨)
        그대로 둘지(행을 읽지 못함 — 읽기 실패로 남은 항목을 지우지 않음) 가릅니다. 표 구조가 정상이란 — 대기 파일에 분류 절이 있고, 대기의
        분류 절과 제안 파일에 `| ID |` 머리가 있으며, 행처럼 보이는데 읽지 못한 줄도 읽는 곳의 표 결함(_config.table_problems)도 없는 것입니다.
        """
        spans = self._open_spans()
        gaps = []
        if not any(d is self.pend for d, *_ in spans):
            gaps.append('대기 파일에 분류 절(`## X.` — X 는 %s)이 없음' % ' · '.join(MOVABLE))
        for doc, label, where in [(self.pend, '대기', '분류 절'), (self.pro, '제안', '파일')]:
            mine = [(s, e) for d, _l, s, e, _o in spans if d is doc]
            if mine and not any(HDR.match(doc.lines[i]) for s, e in mine for i in range(s, e)):
                gaps.append(f'{label} {where}에 `| ID |` 표 머리가 없음')
        unread = self._unread_rows()
        if unread:
            gaps.append('행처럼 보이는데 읽지 못한 줄 — ' + ' · '.join(f'{l} {n}행' for l, n, _p in unread[:5])
                        + (' …' if len(unread) > 5 else ''))
        bad = [f'{label} {s + n}행' for doc, label, s, e, _o in spans
               for n, _code, _p in table_problems('\n'.join(doc.lines[s:e]))]
        if bad:
            gaps.append('표 행 형식 결함 — ' + ' · '.join(bad[:5]) + (' …' if len(bad) > 5 else ''))
        return gaps

    def _rows_or_gaps(self):
        """(미결 행, 건너뛸 까닭). 까닭은 미결이 0건일 때만 봅니다 — 까닭이 있으면 읽기 실패로 보고 목록을 그대로 둡니다.
        표 재생성 · 포커스 · 생성 스탬프가 같은 판정을 씁니다(migrate 뒤 한 번)."""
        if self._open_state is None:
            rows = self._open_rows()
            self._open_state = (rows, [] if rows else self._read_gaps())
        return self._open_state

    def regen_tables(self):
        rows, gaps = self._rows_or_gaps()
        if gaps:
            self.warn('미결 항목을 하나도 읽지 못했습니다 — 행을 다 읽었다고 볼 수 없어 목록의 생성 블록(§3–§6)과 생성 스탬프를 그대로 둡니다'
                      '(읽기 실패로 남은 항목을 지우지 않음). 고친 뒤 다시 돌리십시오: ' + ' · '.join(gaps))
            return
        if not rows:
            self.notes.append('미결 항목 0건 — 대기 · 제안 파일의 표 구조가 정상이라 목록의 표를 빈 상태로 다시 만듭니다.')

        # §3 위치 표 — (파일, 절) 한 행. 키는 _location.py 문법(완료 색인 §1 과 같은 정의)
        g = grammar()
        bucket = {}
        for rid, _t, loc, _g, _st in rows:
            keys, p = loc_rows(loc)
            if loc_bad(p):
                self.warn(f'{rid}: 위치를 해석할 수 없습니다 — 파일(루트 기준 경로를 백틱에)과 절을 적으십시오: '
                          f'`{strip_md(loc)[:60]}`')
            for k in keys:
                bucket.setdefault(k, []).append(rid)
        body = ['| 파일 | 절 | 걸린 항목 |', '|---|---|---|']
        for path, sec, is_file in sorted(bucket, key=loc_sort):
            ids = sorted(set(bucket[(path, sec, is_file)]), key=numkey)
            name = f'`{g.display(path)}`' if is_file else path        # 파일 없는 글 · 미기재는 백틱 없이 (색인 §1 과 같게)
            body.append(f'| {name} | {sec or "—"} | ' + ' · '.join(ids) + ' |')
        r = self.hot.set_block('위치표', body)
        if r is None:
            self.warn('목록에 `<!-- 위치표 -->` 블록이 없습니다.')
        elif r:
            self.act(f'§3 위치 표 재생성 ({len(bucket)}곳)')

        # §4 트리거 표
        tb = {}
        for rid, _t, _l, trig, _st in rows:
            if not trig or norm(trig) == norm('지금'):
                continue
            tb.setdefault(trig, []).append(rid)
        order = {norm(t): n for n, t in enumerate(TRIGGERS)}
        body = ['| 조건이 풀리면 | 꺼낼 항목 |', '|---|---|']
        for k in sorted(tb, key=lambda x: (order.get(norm(x), 99), x)):
            ids = sorted(set(tb[k]), key=numkey)
            body.append(f'| **{k}** | ' + ' · '.join(ids) + f' ({len(ids)}건) |')
        r = self.hot.set_block('트리거표', body)
        if r is None:
            self.warn('목록에 `<!-- 트리거표 -->` 블록이 없습니다.')
        elif r:
            self.act(f'§4 트리거 표 재생성 ({sum(len(v) for v in tb.values())}건)')

        # §5 지금 손댈 수 있는 항목
        now = [(rid, t, loc, st) for rid, t, loc, g, st in rows
               if norm(g) == norm('지금')]
        if not rows:
            body = ['> 미결 항목이 없습니다 — 대기 · 제안 파일에 열린 행이 0건입니다.']
        elif not now:
            body = ['> 트리거가 풀린 항목이 없습니다. 미결 항목은 모두 조건을 기다리는 중입니다 (§4).']
        else:
            body = ['| ID | 항목 | 위치 | 상태 |', '|---|---|---|---|']
            for rid, t, loc, st in sorted(now, key=lambda x: numkey(x[0])):
                body.append(f'| **{rid}** | {t} | {loc} | {st} |')
            body.append('')
            body.append(f'> 본문은 `{_CFG.pending_file}` 의 같은 ID 행에 있습니다.')
        r = self.hot.set_block('지금', body)
        if r is None:
            self.warn('목록에 `<!-- 지금 -->` 블록이 없습니다.')
        elif r:
            self.act(f'§5 지금 손댈 수 있는 항목 재생성 ({len(now)}건)')

        # 위치 표에 H 가 빠지지 않았는지 — ID 자리(끝 셀)만 읽습니다(_config.list_block_ids · 동기화 S3 과 같은 정의)
        hids = {r0 for r0, *_ in rows if r0.startswith('H')}
        if self.hot.block('위치표') and hids:
            listed = {i for i in list_block_ids('\n'.join(self.hot.lines))[0].get('위치표', []) if i.startswith('H')}
            if hids - listed:
                self.warn(f'§3 위치 표에서 빠진 제안: {sorted(hids - listed, key=numkey)}')

    # --- 4.7) §6 지금 작업 중인 장 ---
    def _focus_target(self):
        """인자로 받은 값이 우선. 없으면 §6 블록에 적힌 값을 그대로 씁니다."""
        if self.focus:
            return None if self.focus in ('off', 'none', '없음') else self.focus
        bl = self.hot.block('포커스')
        if bl is None:
            return None
        a, b = bl
        m = re.search(r'\*\*작업 중인 장\*\*\s+(ch\d+)', '\n'.join(self.hot.lines[a:b]))
        return m.group(1) if m else None

    def regen_focus(self):
        bl = self.hot.block('포커스')
        if bl is None:
            if self.focus:
                self.warn('목록에 `<!-- 포커스 -->` 블록이 없습니다. §6을 만들고 다시 돌리십시오.')
            return
        target = self._focus_target()
        if target is None:
            body = ['> 지금 지정된 장이 없습니다. 한 장을 붙잡고 작업할 때 켜십시오 —',
                    f'> `<py> {_CFG.tool("tidy_tracker.py")} --focus ch3 --apply`',
                    '>   (`<py>` 는 이 컴퓨터의 Python 3 — 윈도 `python` · 맥 `python3`)',
                    '>',
                    '> 그 장에 걸린 미결 항목·제안의 **본문**이 여기 복사돼, 대기 파일을 열지 않아도 됩니다.']
            r = self.hot.set_block('포커스', body)
            if r:
                self.act('§6 포커스 해제')
            return

        # `ch1` 은 project.json 이 그 장에 매핑한 파일(예: intro.md)입니다. 위치 문법이 해석한 파일이
        # 그 장 파일과 **같을 때만** 싣습니다 — 접두어 맞춤이 아니므로 노트 파일이나 `manuscript/` 접두어에 흔들리지 않습니다.
        n = int(target[2:])
        files = [f for c, f in _CFG.chapters if c == n]
        src = _CFG.source_rel
        targets = {(src + '/' + f) if src else f for f in files} | set(files)

        def hits(loc):
            return [(p, s) for p, s, is_file in loc_rows(loc)[0] if is_file and p in targets]

        all_rows, gaps = self._rows_or_gaps()
        if gaps:            # 행을 읽지 못함 — 사본을 비우지 않고 둡니다(경고는 regen_tables 가 냄)
            return
        rows = [r for r in all_rows if hits(r[2])]
        rows.sort(key=lambda r: (min((section_key(s) for _p, s in hits(r[2])), default=(9,)), numkey(r[0])))
        today = datetime.date.today().isoformat()
        body = [f'**작업 중인 장** {target} — {today} 설정 · {len(rows)}건',
                f'> 끄기 `<py> {_CFG.tool("tidy_tracker.py")} --focus off --apply`',
                '>   (`<py>` 는 이 컴퓨터의 Python 3 — 윈도 `python` · 맥 `python3`)',
                '>',
                f'> **아래는 `{_CFG.pending_file}`·`{_CFG.proposals_file}` 의 사본입니다.** 고치려면 원본을 고치십시오 —',
                '> 이 블록은 정리 스크립트가 매번 다시 만들므로 여기서 고친 것은 지워집니다.',
                '']
        for rid, title, loc, trig, st in rows:
            body.append(f'#### {rid} — {title}')
            meta = ' · '.join(x for x in [strip_md(loc), trig, st] if x)
            body.append(f'`{meta}`' if meta else '')
            body.append('')
            body.append(self._note_of(rid))
            body.append('')
        r = self.hot.set_block('포커스', body)
        if r:
            self.act(f'§6 포커스 — {target} 항목 {len(rows)}건 실음')

    def _note_of(self, rid):
        for doc in (self.pend, self.pro):
            spans = doc.sections() if doc is self.pend else [('', 0, len(doc.lines))]
            for _t, s, e in spans:
                for i, r0, cs, hdr in table_rows(doc.lines, s, e):
                    if r0 != rid:
                        continue
                    j = col_any(hdr, ['비고', '근거'], len(hdr) - 1)
                    return unescape_cell(cs[j]) if j is not None and 0 <= j < len(cs) else ''   # 문단에 옮기므로 `\|` → `|`
        return ''

    # --- 5) 크기 ---
    def sizes(self):
        print('\n크기')
        d = os.path.join(self.d, _CFG.records_dir)
        if os.path.isdir(d):
            n = sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d)
                    if os.path.isfile(os.path.join(d, f)))
            c = len([f for f in os.listdir(d) if re.fullmatch(r'E\d+\.md', f)])
            label = '%s\\ (E %d건)' % (_CFG.records_dir, c)
            print(f'  {label:24s} {n/1024:7.1f} KB')
        for f in FILES:
            p = os.path.join(self.d, f)
            n = os.path.getsize(p) if os.path.exists(p) else 0
            flag = ''
            if f == _CFG.index_file and n > HOT_LIMIT:      # 이름이 아니라 설정 경로로 — tracker 가 하위 폴더를 가리켜도 경고가 나게
                flag = f'  ← {HOT_LIMIT//1024} KB 초과. 매번 읽는 파일이니 구조를 다시 살펴보십시오'
            print(f'  {f:24s} {n/1024:7.1f} KB{flag}')

    # --- 4.8) 생성 스탬프 — 목록이 어느 원본(대기 · 제안 · 문헌)에서 만들어졌는지. 동기화 점검 S4 가 대조합니다 ---
    def stamp(self):
        if self._rows_or_gaps()[1]:
            # 행을 읽지 못해 생성 블록을 다시 만들지 않았으면 스탬프도 그대로 둡니다 — 지금 원본에서 만든 목록이 아니므로,
            # 새 스탬프를 찍으면 동기화 점검 S4 가 「목록 최신」으로 보아 낡은 목록을 가립니다.
            return
        texts = {}
        for doc, rel in [(self.pend, _CFG.pending_file), (self.pro, _CFG.proposals_file), (self.lit, _CFG.literature_file)]:
            # 이 실행 뒤 디스크에 있을 바이트를 해시합니다 — 바뀐 파일은 save() 가 쓸 정규화본, 안 바뀐 파일은 원문 그대로.
            # 끝 빈 줄만 다른 손편집 파일은 저장되지 않으므로, 정규화본을 해시하면 동기화 S4 와 어긋납니다.
            norm = '\n'.join(doc.lines).rstrip() + '\n'
            texts[rel.replace('\\', '/')] = norm if doc.dirty() else doc.orig
        line = self.sync.stamp_for_index(texts)
        idx = next((i for i, l in enumerate(self.hot.lines) if l.startswith('<!-- 생성스탬프 ')), None)
        if idx is None:
            self.hot.lines.insert(1, line)
            self.act('목록에 생성 스탬프 추가')
        elif self.hot.lines[idx] != line:
            self.hot.lines[idx] = line
            self.act('목록의 생성 스탬프 갱신')

    def docs(self):
        """이 도구가 읽고 쓰는 다섯 파일 — (Doc, 보고에 쓰는 이름)."""
        return [(self.hot, _CFG.index_file), (self.pend, _CFG.pending_file), (self.rec, REC),
                (self.lit, _CFG.literature_file), (self.pro, _CFG.proposals_file)]

    def run(self):
        if not refuse_if_alert(self.sync, self.apply, 'tidy_tracker'):
            return 3
        self.migrate()
        self.reindex()
        self.sync_f()
        self.regen_tables()
        self.regen_focus()
        self.stamp()
        self.audit()

        # 저장 전 전체 검사 — 쓸 것이 있는데 읽은 뒤 바뀐 파일이 하나라도 있으면 아무것도 저장하지 않습니다.
        # 고친 파일만이 아니라 다섯 파일 모두를 봅니다 — 안 고친 원본이 바뀌었어도 그것으로 만든 목록은 낡은 것입니다.
        if self.apply and any(doc.dirty() for doc, _n in self.docs()):
            self.stale = [name for doc, name in self.docs() if doc.stale()]
            if self.stale:
                return RC_REFUSED

        print('=' * 68)
        print('수정필요 목록 정리 — ' + ('반영' if self.apply else '진단만 (--apply 로 반영)'))
        print('=' * 68)
        if self.acts:
            print('\n할 일' if not self.apply else '\n반영함')
            for a in self.acts:
                print('  ·', a)
        for n in self.notes:
            print('  ·', n)
        if self.warns:
            print('\n확인 필요 — 사람이 판단해야 합니다')
            for w in self.warns:
                print('  !', w)
        if not self.acts and not self.warns:
            print('\n정상입니다. 고칠 것도, 확인할 것도 없습니다.')

        changed, blocked = [], []
        for doc, name in self.docs():
            if doc.dirty():
                changed.append(name)
                if self.apply:
                    try:
                        doc.save()
                    except StaleFile:
                        blocked.append(name)
        if blocked:
            print('\n! 저장하지 않았습니다 — 읽은 뒤 남이 고친 파일이 있습니다: '
                  + ', '.join(blocked))
            print('  검사와 저장 사이에 바뀐 것입니다. 다시 돌리면 됩니다.')
            self.warns.append(f'동시 편집 감지 — {", ".join(blocked)} 을 덮어쓰지 않았습니다')
            changed = [c for c in changed if c not in blocked]
        if self.apply:
            for name in changed:
                self.sync.after_write(name.replace('\\', '/'))
            findings, removed = self.sync.session_end()       # 세션 끝 — 드라이브 스냅샷 · 보존 정리
            print('\n동기화 — 세션 경계 스냅샷 갱신 · 보존 정리 %d개 삭제%s' % (removed, ' · ERROR 남음(확인 필요)' if findings else ''))
            for f in findings:
                print('  ! ' + f.line())
        self.sizes()          # 저장한 뒤에 재야 실제 크기가 나옵니다
        if changed:
            print(('\n기록함: ' if self.apply else '\n바뀔 파일 (--apply 필요): ') + ', '.join(changed))
        return 1 if self.warns else 0


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--apply', action='store_true', help='진단만 하지 않고 파일에 반영합니다')
    ap.add_argument('--dir', default=project_root())
    ap.add_argument('--focus', metavar='ch3|off',
                    help='한 장을 붙잡고 작업할 때. 그 장에 걸린 항목 본문을 목록 §6 에 싣습니다')
    a = ap.parse_args()
    if a.focus and not re.fullmatch(r'ch\d+|off|none|없음', a.focus):
        print(f'--focus 값은 ch<장 번호>(설정의 chapters) 또는 off 입니다 (받은 값: {a.focus})', file=sys.stderr)
        return 2
    for f in FILES + [REC]:
        if not os.path.exists(os.path.join(a.dir, f)):
            print(f'없음: {os.path.join(a.dir, f)}', file=sys.stderr)
            return 2
    sync = Sync(_CFG)
    if not a.apply:
        return Tidy(a.dir, False, a.focus, sync).run()
    with sync.write_lock('tidy_tracker') as lock:
        if lock.busy:
            print('! ' + lock.busy_message())
            return RC_REFUSED
        stale = []
        for attempt in (1, 2):
            t = Tidy(a.dir, True, a.focus, sync)          # 잠금을 잡은 뒤에 읽습니다
            rc = t.run()
            if not t.stale:
                return rc
            stale = t.stale
            if attempt == 1:
                print('읽은 뒤 바뀐 파일이 있어 저장하지 않고 처음부터 다시 읽습니다 — ' + ', '.join(stale))
        print('! 저장하지 않았습니다 — 두 번 모두 읽은 뒤 파일이 바뀌었습니다: ' + ', '.join(stale))
        print('  다른 세션이 같은 파일을 쓰는 중입니다. 다시 돌리면 됩니다.')
        return RC_REFUSED


if __name__ == '__main__':
    sys.exit(main())
