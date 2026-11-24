# -*- coding: utf-8 -*-
r"""_동기화.py — 공용 파일 동기화 안전장치. 점검 · 스냅샷 · 복구 · 쓰기 가드 · 1회 치환 도우미.

여러 컴퓨터가 클라우드 동기화 폴더(구글드라이브 등)에서 같은 원고 프로젝트를 쓰면, 따라잡지 못한 미러 위에 쓴 판이
나중에 올라가 다른 컴퓨터의 작업을 조용히 덮습니다. 이 모듈은 그것을 **코드로** 막고 · 잡고 · 되돌립니다 — 모델 토큰은 쓰지
않습니다. 규약은 플러그인 문서 `manuscript-workflow/references/tracker-workflow.md` 「동기화」에 있습니다.

    from _동기화 import Sync, replace_once
    s = Sync(cfg)                        # cfg 는 _config.load()
    s.session_start()                    # 세션 시작 — 점검 · 경계 스냅샷 · 상태 한 줄
    s.guard('Edit', '수정필요_대기.md')    # 쓰기 직전 — 막을 사유 문자열 또는 None
    s.after_write('수정필요_대기.md')     # 쓰기 직후 — 스냅샷 · 지문 · 「쓴 줄」 기록
    s.session_end()                      # 세션 끝 — 경계 스냅샷 · 보존 정리
    s.accept_warn()                      # WARN 만 있을 때 기준 재설정 — 열린 ERROR 가 있으면 None(닫는 길은 ack 뿐)
    replace_once(path, old, new)         # 대상이 정확히 1회일 때만 바꾸고 줄끝 · 스냅샷까지

점검(등급 · 시점) — 가해 쪽은 추정, 피해 쪽은 불변식으로 정확히.
    S1 신선도      WARN   시작 · update_tools   공용 파일의 최근 변경이 stale_days 넘게 지남
    S2 E 연속      ERROR  시작 · 쓰기            완료기록 번호에 빈칸(known_gaps 제외) — 따라잡는 중
    S3 참조 무결   ERROR  시작 · 쓰기            생성물이 가리키는 원본 항목이 없음(색인 → E 파일 · 목록 → 미결 ID — 생성 블록의 ID 자리만, _config.list_block_ids)
                   WARN   시작 · 쓰기            목록 생성 블록의 모양을 읽지 못해 ID 대조를 건너뜀
                   WARN   시작                   손편집 파일이 가리키는 E 번호가 최대 E 보다 큼
    S4 생성 스탬프 INFO   시작                   생성물의 스탬프가 원본과 다른데 원본이 생성 **뒤에** 바뀜(순방향) — 재생성 안내 「할 일」. 동기화 문제 아님
                   WARN   시작                   원본이 이 컴퓨터가 본 옛 판으로 되돌아감 · 스탬프 뒤 편집이 없는데 내용이 다름 · 기존 기록이 바뀜 · 기록이 줆
                   ERROR  시작                   원본이 옛 판으로 역행했고 수정 시각도 생성물보다 앞 — 덮어쓰기
    S5 충돌 사본   WARN   시작(전체) · 쓰기(폴더) 동기화 충돌 사본(`x 2.md` · `x (1).md` · conflicted copy)
    S6 손실 보고   WARN   시작 · --damage        이 컴퓨터가 쓴 줄의 생존율이 survival_pct 아래
    S7 ID 단조     ERROR  시작 · 쓰기            이 컴퓨터가 본 미결 · 이관 · 제안 · 문헌 ID 가 사라짐
    S8 드라이브    INFO   시작                   동기화 프로그램 프로세스 유무
상태는 동기화 폴더 **밖** `~/.claude/sync-state/<프로젝트 id>/` 에 컴퓨터별로 둡니다(`SYNC_STATE_HOME` 으로 바꿀 수 있음 — 시험용).
프로젝트 id 는 `<이름 슬러그>-<루트 경로 해시8>`(project_id — 정의는 그 한 곳) — 루트 경로를 **NFC 로 맞춘 뒤** 해시하므로 훅(표준 입력의
NFC 경로)과 셸에서 돌린 도구(맥 파일 시스템의 NFD 경로)가 같은 폴더를 씁니다. 옛 정의(정규화 없음 · 0.11.3 까지)로 생긴 폴더는 처음
만날 때 새 이름으로 옮기거나 새 폴더에 합칩니다(_adopt_legacy_state).
쓰기 뒤 「쓴 줄」의 차이는 **이 컴퓨터가 쓰기 직전에 본 판**(`seen.json` 의 해시 → 그 해시의 스냅샷)과 견줍니다 — 시각상 마지막 스냅샷은 다른 컴퓨터의 옛 판일 수 있습니다.
스냅샷은 쓰기마다 로컬(같은 곳 `snap/`)에, 세션 경계와 일괄 도구 전후에 드라이브(`sync.snapshot_dir`)에 둡니다.
이름 `<UTC>_<컴퓨터>_<경로(/→__)>_<해시8><확장자>` 는 매번 달라 다른 컴퓨터가 덮을 수 없고, 같은 해시는 다시 만들지 않습니다.
보존(세션 시작 · 끝) — 파일마다 최근 `snapshot_min` 개는 늘 남기고, 자기 컴퓨터 것은 `snapshot_days`(로컬 2배) 지났거나 `snapshot_max`
(로컬 `snapshot_max_local`)를 넘는 것을 오래된 순으로, 다른 컴퓨터 것은 `snapshot_days_others` 지난 것을 지웁니다. 바뀌지 않는 파일은 하나씩만 남습니다.
파일 이름 · 경로 · 줄은 비교하거나 키로 쓸 때 NFC 로 맞춥니다(`_config.nfc`) — 맥 미러의 NFD 이름이 설정 · 본문의 NFC 와 섞여도 같은 파일로 봅니다.
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
from _config import (load as _load_cfg, CONFIG_REL, CONFIG_REL_OLD, nfc,                  # noqa: E402  — nfc: 이름 · 경로 · 줄의 비교는 NFC 로
                     TABLE_ROW_RE_M, table_problems, describe_table_problem,              # 표 행 문법은 _config.py 한 곳(정리 도구 · 훅과 같음)
                     list_block_ids, id_key,                                              # 목록의 ID 자리 · ID 정렬도 정리 도구와 같은 정의
                     allocation_scope, id_stem)                                           # 번호를 도구가 정하는 범위 — 미결_새항목.py 와 같은 정의

UTC_FMT = '%Y%m%dT%H%M%SZ'
SNAP_RE = re.compile(r'^(\d{8}T\d{6}Z)_([^_]+)_(.+)_([0-9a-f]{8})(\.[^.]*)?$')
STAMP_RE = re.compile(r'^<!-- 생성스탬프 (.*?) -->\s*$', re.M)
ROW_ID_RE = TABLE_ROW_RE_M      # S7 가 모으는 행 ID — 정리 도구의 행 정규식과 같은 정의
E_REF_RE = re.compile(r'(?<![\w/\\])E(\d+)(?!\d)')
MIN_LINE = 8          # 이보다 짧은 줄은 「쓴 줄」로 세지 않습니다 — 구분선 · 빈 셀 같은 것
MAX_LINES_PER_FILE = 3000


# ---------------------------------------------------------------- 공용 작은 도구
def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def utc_stamp(dt=None):
    return (dt or utc_now()).strftime(UTC_FMT)


def parse_utc(s):
    return datetime.datetime.strptime(s, UTC_FMT).replace(tzinfo=datetime.timezone.utc)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def norm_sha(data):
    """줄끝을 LF 로 정규화한 해시 — 컴퓨터마다 줄끝이 달라도 같은 내용이면 같게."""
    return sha(data.replace(b'\r\n', b'\n'))


def _slug(s):
    s = re.sub(r'[^0-9A-Za-z가-힣_-]+', '-', nfc(s)).strip('-')
    return s[:24] or 'project'


def computer_id():
    """컴퓨터 식별자 — `<상태 기준 폴더>/computer_id` 첫 줄, 없으면 hostname. `_` 는 이름 규약의 구분자라 `-` 로 바꿉니다."""
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
    """상태 기준 폴더 — 동기화 폴더 밖. 시험은 `SYNC_STATE_HOME` 으로 임시 폴더를 줍니다."""
    env = os.environ.get('SYNC_STATE_HOME')
    if env:
        return os.path.abspath(env)
    home = os.environ.get('USERPROFILE') or os.path.expanduser('~')
    return os.path.join(home, '.claude', 'sync-state')


def _root_key(root, form='NFC'):
    """상태 폴더 id 에 넣는 루트 경로 문자열 — 절대 경로 · normcase · `/` 구분자, 그리고 유니코드 정규화(form).
    form=None 은 정규화 없음(0.11.3 까지의 정의) — 옛 폴더를 찾을 때만 씁니다."""
    key = os.path.normcase(os.path.abspath(root)).replace('\\', '/')
    return unicodedata.normalize(form, key) if form else key


def project_id(name, root, form='NFC'):
    """상태 폴더 이름 `<이름 슬러그>-<루트 경로 해시8>` — 정의는 여기 한 곳. 루트 경로를 NFC 로 맞춘 뒤 해시하므로 훅(표준 입력의
    NFC 경로)과 셸에서 돌린 도구(맥 파일 시스템의 NFD 경로)가 같은 폴더를 씁니다(2026-11-06 맥 실측 — 갈리면 `--ack` 가 훅에 닿지 않음)."""
    return '%s-%s' % (_slug(name), sha(_root_key(root, form).encode('utf-8'))[:8])


def legacy_project_ids(name, root):
    """옛 정의(정규화 없음)로 생겼을 수 있는 폴더 이름 — 지금 정의와 다른 것만. 루트가 NFC 면 옛 정의의 결과가 지금과 같아 NFD 쪽만
    남고, 루트가 NFD 면 그 자체가 옛 폴더입니다. ASCII 경로에서는 빈 목록."""
    cur = project_id(name, root)
    return [p for p in dict.fromkeys(project_id(name, root, f) for f in (None, 'NFD')) if p != cur]


def find_project_root(start):
    """start(파일 또는 폴더)에서 위로 올라가며 설정 파일이 있는 폴더를 찾습니다. 없으면 None."""
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
    """루트 기준 상대 경로(`/` 구분 · NFC). 두 경로의 정규화 형이 달라도(훅의 NFC · 맥 파일 시스템의 NFD) 맞게 — 둘 다 NFC 로 맞춘 뒤 relpath."""
    return nfc(os.path.relpath(nfc(os.path.abspath(path)), nfc(os.path.abspath(root))).replace(os.sep, '/'))


def _line_table(data):
    """줄 해시 → 미리보기(40자). 공백만 다른 줄은 같은 줄로 봅니다."""
    out = {}
    text = data.decode('utf-8', errors='replace')
    for line in text.split('\n'):
        t = nfc(line.strip())
        if len(t) < MIN_LINE:
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
    """상태 JSON 둘을 하나로 — new 가 더 최근에 쓰인 파일. 파일마다 규칙이 다릅니다(합치기는 멱등)."""
    if name == 'written.json':                        # {파일: {줄 해시: [utc, 미리보기]}} — 파일 · 줄 모두 합집합, 겹치면 new
        out = {}
        for reg in (old, new):
            for rel, lines in (reg or {}).items():
                if isinstance(lines, dict):
                    out.setdefault(rel, {}).update(lines)
        return out
    if name == 'ids.json':                            # {ID: 처음 본 utc} — 합집합, 더 이른 시각
        out = dict(old or {})
        for k, v in (new or {}).items():
            out[k] = min(out[k], v) if isinstance(out.get(k), str) and isinstance(v, str) else v
        return out
    if name == 'records_max.json':                    # 이 컴퓨터가 본 최대 번호 — 큰 쪽
        a, b = (old or {}), (new or {})
        return b if int(b.get('max', 0)) >= int(a.get('max', 0)) else a
    if name == 'alerts.json':                         # findings 는 new 의 것(점검마다 다시 적힘), acked 는 합집합(겹치면 new)
        out = dict(old or {})
        out.update(new or {})
        acked = dict((old or {}).get('acked') or {})
        acked.update((new or {}).get('acked') or {})
        out['acked'] = acked
        return out
    if name == 'ack_log.json':                        # 목록 — 이어 붙여 utc 순, 중복 제거, 최근 200
        seen, out = set(), []
        for e in sorted(list(old or []) + list(new or []), key=lambda e: str((e or {}).get('utc', ''))):
            k = json.dumps(e, sort_keys=True, ensure_ascii=False)
            if k not in seen:
                seen.add(k)
                out.append(e)
        return out[-200:]
    if isinstance(new, dict) and isinstance(old, dict):   # seen.json · fingerprints.json · 그 밖의 사전 — 빈 자리는 old, 겹치면 new
        out = dict(old)
        out.update(new)
        return out
    return new


def _merge_state_dir(src, dst):
    """옛 상태 폴더 src 를 dst 에 합친 뒤 src 를 지웁니다 — 하위 폴더(snap · hook_seen)의 파일은 dst 에 없는 것만 옮기고(이름이 UTC · 컴퓨터 ·
    해시라 같은 이름은 같은 내용), JSON 은 _merge_state_json, 그 밖의 파일은 없는 것만 옮깁니다. 중간에 실패하면 OSError 를 내고 src 를 남깁니다."""
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


# ---------------------------------------------------------------- 본체
class Sync(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.root = os.path.abspath(cfg.root)
        self.t = cfg.raw.get('tracker') or {}
        self.s = cfg.raw.get('sync') or {}
        self.pid = project_id(cfg.name, self.root)          # 루트 경로는 NFC 로 맞춰 해시 — 훅(NFC) · 셸(맥 NFD)이 같은 폴더
        self.state = os.path.join(state_home(), self.pid)
        self.me = computer_id()
        self._adopt_legacy_state()

    def _adopt_legacy_state(self):
        """옛 정의(정규화 없음 · 0.11.3 까지)가 만든 상태 폴더를 거둬들입니다 — 맥에서 훅(NFC 경로)과 셸(NFD 경로)이 다른 폴더를 써서
        `--ack` 가 훅에 닿지 않던 결함. 새 폴더가 없으면 옛 폴더의 이름만 바꾸고, 둘 다 있으면 옛 것을 새 것에 합친 뒤 지웁니다. 실패하면
        옛 폴더를 그대로 두고 알리며 다음 Sync 가 다시 시도합니다(합치기는 멱등). 옛 폴더가 없으면 isdir 한두 번이 전부입니다."""
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
                sys.stderr.write('_동기화: 옛 상태 폴더 %s 를 %s 로 옮기지 못했습니다(%s) — 다음에 다시 시도합니다\n' % (old, self.pid, e))

    # ---- 설정 값 -------------------------------------------------
    def opt(self, key, default=None):
        v = self.s.get(key)
        return default if v is None else v

    @property
    def snapshot_dir(self):
        return os.path.join(self.root, *str(self.opt('snapshot_dir', '보관/추적_백업')).split('/'))

    @property
    def local_snap_dir(self):
        return os.path.join(self.state, 'snap')

    # ---- 파일 집합 -----------------------------------------------
    def _path(self, rel):
        """rel(루트 기준 · NFC)의 실제 경로. 그대로 없으면 NFD 이름으로, 그래도 없으면 그 폴더에서 NFC 로 같은 이름을 찾습니다 —
        맥 미러에서 만든 NFD 이름의 파일이 윈도(NTFS 는 정규화에 민감)로 넘어와도 같은 파일로 다룹니다."""
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
        """[(번호, 상대경로)] — 완료기록 E*.md"""
        d = os.path.join(self.root, self.t.get('records_dir', '완료기록'))
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
        """공용 파일 — 설정에서 유도. 추적 파일 · 인수인계 · 완료기록 · 원고 md · sync.shared_extra. 실재하는 파일만."""
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
        rd = self.t.get('records_dir', '완료기록').replace('\\', '/').rstrip('/') + '/'
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

    # ---- 상태 ---------------------------------------------------
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

    # ---- 생성 스탬프 ---------------------------------------------
    def stamp_for_index(self, texts):
        """목록의 스탬프 줄. texts — {원본 상대경로: 그 파일의 저장될 내용(str 또는 bytes)}. 결정적(시각 없음)."""
        parts = []
        for rel in sorted(texts):
            data = texts[rel]
            if isinstance(data, str):
                data = data.encode('utf-8')
            parts.append('%s=%s' % (rel, norm_sha(data)[:16]))
        return '<!-- 생성스탬프 ' + ' '.join(parts) + ' -->'

    def records_fingerprint(self, upto=None):
        """(개수, 최대 번호, 해시16). upto — 그 번호까지만(S4 가 「스탬프 때 있던 기록이 그대로인가」를 볼 때)."""
        recs = [(n, r) for n, r in self.records() if upto is None or n <= upto]
        h = hashlib.sha256()
        for n, r in recs:
            h.update(('%d:%s;' % (n, norm_sha(self.read(r))[:8])).encode('ascii'))
        return len(recs), (max(n for n, _ in recs) if recs else 0), h.hexdigest()[:16]

    def stamp_for_records(self):
        n, mx, hx = self.records_fingerprint()
        return '<!-- 생성스탬프 %s/ n=%d max=%d sha=%s -->' % (self.t.get('records_dir', '완료기록').replace('\\', '/').rstrip('/'), n, mx, hx)

    @staticmethod
    def parse_stamp(text):
        m = STAMP_RE.search(text)
        return m.group(1) if m else None

    # ---- 점검 ---------------------------------------------------
    def check(self, scope='start', target=None):
        """scope — 'start'(전부) · 'write'(싼 것 — S2 S3생성물 S5폴더 S7) · 'tools'(update_tools — S1 S2 S5)."""
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
        return F

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
            return [Finding('WARN', 'S1', 'S1', '공용 파일이 하나도 없습니다 — 설정(tracker · manuscript.source_dir)을 확인하십시오')]
        days = (time.time() - best[0]) / 86400.0
        limit = float(self.opt('stale_days', 2))
        if days > limit:
            return [Finding('WARN', 'S1', 'S1', '공용 파일의 최근 변경이 %.1f일 전(%s) — 미러가 낡았거나 작업 공백. 드라이브가 최신인지 확인하십시오'
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
                             '완료기록 번호에 빈칸 %d개 — 따라잡는 중이거나 손상' % len(gaps),
                             ['%s%d' % (prefix, g) for g in gaps]))
        seen_max = self.max_record_seen()
        if seen_max and max(have) < seen_max:        # 빈칸 없이 끝만 잘린 경우 — 다음 번호가 겹치는 ID 재사용의 길
            F.append(Finding('ERROR', 'S2', 'S2:max:%d<%d' % (max(have), seen_max),
                             '완료기록 최대 번호(%s%d)가 이 컴퓨터가 본 %s%d 보다 뒤입니다 — 최신 기록이 덜 내려왔거나 지워짐'
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
        """지금 파일들(대기 · 이관 · 제안 · 문헌)의 행 ID 와 이 컴퓨터가 본 ID 등록의 합 — 새 번호 배정(미결_새항목.py)과 손 등록 판정의 기준."""
        return self._id_universe() | set(self._load('ids.json', {}))

    def hand_added_ids(self, rel, text):
        """text(쓰려는 글)의 표 행 가운데 **도구가 번호를 정하는 범위인데 어디에도 없던 새 ID** — 손 등록. 훅이 이것으로 거부합니다.
        범위는 `_config.allocation_scope`(파일 · 글자)이고 그 밖은 빈 목록입니다. 가지 번호(`D35-1`)는 줄기(`D35`)가 있으면 새 ID 가
        아닙니다. 지웠던 행을 되살리거나 행을 옮기는 것은 이미 아는 ID 라 걸리지 않습니다."""
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
        # 생성물 → 원본: 색인 §2 의 E 행
        ri = self.tracker_rel('record_index')
        if ri and self._exists(ri) and recs:
            text = self.read(ri).decode('utf-8', errors='replace')
            listed = {int(m) for m in re.findall(r'^\|\s*%s(\d+)\s*\|' % re.escape(prefix), text, re.M)}
            missing = sorted(listed - set(recs))
            if missing:
                F.append(Finding('ERROR', 'S3', 'S3:index:' + ','.join(str(m) for m in missing[:20]),
                                 '완료 색인이 가리키는 기록 파일 %d개가 없습니다 — 미러가 따라잡는 중' % len(missing),
                                 ['%s%d' % (prefix, m) for m in missing]))
        # 생성물 → 원본: 목록의 미결 ID — 생성 블록의 ID 자리(표의 ID 셀 · 포커스 항목 머리)만 셉니다. 포커스의 비고 사본 같은 본문에는
        # 다른 문서의 라벨(반영계획의 D4 · 다른 프로젝트의 A40)이 섞여 있어 미결 ID 로 읽으면 오탐입니다.
        idx = self.tracker_rel('index')
        if idx and self._exists(idx):
            text = self.read(idx).decode('utf-8', errors='replace')
            by_block, unknown = list_block_ids(text)
            refs = {i for ids in by_block.values() for i in ids}
            if refs:
                missing = sorted(refs - self._id_universe(), key=id_key)
                if missing:
                    F.append(Finding('ERROR', 'S3', 'S3:list:' + ','.join(missing[:20]),
                                     '목록이 가리키는 미결 항목 %d개가 대기 · 이관 · 제안에 없습니다' % len(missing), missing))
            if unknown:
                F.append(Finding('WARN', 'S3', 'S3:list:format:' + ','.join(unknown),
                                 '%s 의 생성 블록(%s)에서 ID 자리를 읽지 못해 미결 ID 대조를 건너뜁니다 — 옛 판이거나 손으로 고친 것. '
                                 '정리 도구 `--apply` 로 다시 만드십시오' % (idx, ' · '.join(unknown))))
        # 손편집 파일 → 최대 E 보다 큰 참조 (경로 안 · `../` 가 앞에 있는 것은 뺌)
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
                    F.append(Finding('WARN', 'S3', 'S3:%s' % r, '%s 가 아직 없는 기록을 가리킵니다(최대 %s%d) — 기록 파일이 덜 내려왔을 수 있음'
                                     % (r, prefix, mx), ['%s%d' % (prefix, n) for n in sorted(big)]))
        return F

    # ---- S4 — 스탬프가 다를 때 「어느 쪽이 나중인가」 -------------------
    S4_ORDER = ('forward', 'revert', 'suspect', 'regress')
    S4_LEVEL = {'forward': 'INFO', 'revert': 'WARN', 'suspect': 'WARN', 'regress': 'ERROR'}

    def _history_keys(self, rel, wanted):
        """rel 의 스냅샷(로컬 + 드라이브)에서 wanted(정규화 해시16 집합)에 든 판이 **처음 보인** 순서 키 — {해시16: 키}(그 판이 쓰인 시각).
        먼저 이름의 해시8 로 맞춰 보고(줄끝이 LF 인 판은 정규화 해시와 같음), 못 찾은 것만 새것부터 내용을 읽어 맞춥니다."""
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
        """생성물 gen_rel 이 원본 src_rel 의 h_stamp 판에서 만들어졌는데 지금 원본은 h_cur 판 — 어느 쪽이 나중인가.
        순서는 이 컴퓨터의 스냅샷 기록으로, 그것이 모자라면 원본 · 생성물의 수정 시각(동기화 서비스가 보존)으로 가립니다.
        돌려주는 것 — (종류, 설명). forward 원본이 뒤에 바뀜(재생성만 하면 됨) · regress 원본이 옛 판으로 돌아갔고 수정 시각도 앞(덮어쓰기)
        · revert 옛 판 내용인데 수정 시각은 뒤(되돌렸거나 덮어쓰기) · suspect 스탬프 뒤 편집이 없는데 내용이 다름(옛 판이 덮었거나 생성물만 먼저 옴)."""
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
                return 'forward', '%s 의 %s 편집' % (src_rel, when(tc))
            kind = 'revert' if src_newer else 'regress'
            return kind, '%s 가 이 컴퓨터가 %s 에 본 옛 판으로 돌아갔습니다(생성물은 %s 판에서)' % (src_rel, when(tc), when(ts))
        if src_newer:
            return 'forward', '%s 의 뒤 편집%s' % (src_rel, '' if tc else '(이 컴퓨터가 모르는 판)')
        return 'suspect', '%s 는 생성 뒤 바뀐 적이 없는데 내용이 다릅니다%s' % (src_rel, '' if ts else ' · 생성물의 판을 이 컴퓨터가 모름')

    def s4(self):
        F = []
        idx = self.tracker_rel('index')
        if idx and self._exists(idx):
            text = self.read(idx).decode('utf-8', errors='replace')
            st = self.parse_stamp(text)
            if st is None:
                F.append(Finding('INFO', 'S4', 'S4:index:none', '%s 에 생성 스탬프가 없습니다(옛 생성물) — 정리 도구를 한 번 돌리면 생깁니다' % idx))
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
                    if old is None:                       # 생성 때 없던 원본 파일 — 다시 만들면 됩니다
                        kinds.append('forward'); notes.append('%s 가 생성 뒤 생김' % r)
                        continue
                    kind, note = self._stamp_direction(idx, r, old, cur)
                    kinds.append(kind); notes.append(note)
                if kinds:
                    worst = max(kinds, key=self.S4_ORDER.index)
                    detail = ' · '.join(notes)
                    if worst == 'forward':
                        msg = '%s 가 원본보다 낡음(%s) — 세션 끝에 `수정필요_정리.py --apply` 로 다시 만듭니다. 동기화 문제 아님' % (idx, detail)
                    elif worst == 'revert':
                        msg = '%s — 되돌린 것이면 정상, 아니면 덮어쓰기 의심. 정리 도구로 다시 만들기 전에 확인하십시오' % detail
                    elif worst == 'suspect':
                        msg = '%s 가 지금의 원본이 아닌 판에서 만들어짐 — %s. 옛 판이 새 판을 덮었거나 생성물만 먼저 내려옴. 드라이브 상태를 확인하십시오' % (idx, detail)
                    else:
                        msg = '%s — 덮어쓰기. `--restore <파일>` 로 되돌리거나 확인 뒤 `--ack`' % detail
                    F.append(Finding(self.S4_LEVEL[worst], 'S4', 'S4:index:' + {'forward': 'stale'}.get(worst, worst), msg))
        ri = self.tracker_rel('record_index')
        recs = self.records()
        if ri and self._exists(ri) and recs:
            text = self.read(ri).decode('utf-8', errors='replace')
            st = self.parse_stamp(text)
            prefix = self.t.get('record_prefix', 'E')
            if st is None:
                F.append(Finding('INFO', 'S4', 'S4:records:none', '%s 에 생성 스탬프가 없습니다(옛 생성물) — 색인 도구를 한 번 돌리면 생깁니다' % ri))
            elif self.stamp_for_records() != '<!-- 생성스탬프 %s -->' % st:
                n, mx, hx = self.records_fingerprint()
                m = re.search(r'n=(\d+) max=(\d+) sha=([0-9a-f]{16})', st)
                if not m:
                    F.append(Finding('WARN', 'S4', 'S4:records', '%s 의 스탬프 형식을 읽을 수 없습니다 — 색인 도구로 다시 만드십시오' % ri))
                else:
                    n0, mx0, hx0 = int(m.group(1)), int(m.group(2)), m.group(3)
                    if n < n0 or mx < mx0:
                        F.append(Finding('WARN', 'S4', 'S4:records:shrunk',
                                         '완료기록이 색인을 만들 때(%d건 · 최대 %s%d)보다 줄었습니다(%d건 · 최대 %s%d) — 덜 내려왔거나 지워짐'
                                         % (n0, prefix, mx0, n, prefix, mx)))
                    elif self.records_fingerprint(upto=mx0)[2] == hx0:
                        new = ['%s%d' % (prefix, k) for k, _ in recs if k > mx0]
                        F.append(Finding('INFO', 'S4', 'S4:records:stale',
                                         '%s 가 완료기록 폴더보다 낡음(새 기록 %s) — `완료기록_색인.py` 로 다시 만듭니다. 동기화 문제 아님'
                                         % (ri, ' '.join(new[:8]) + (' …' if len(new) > 8 else ''))))
                    else:
                        F.append(Finding('WARN', 'S4', 'S4:records:changed',
                                         '색인을 만들 때 있던 기록(%s%d 까지) 가운데 내용이 바뀐 것이 있습니다 — 확정 기록은 고치지 않는 규칙 · 덮어쓰기 확인'
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
                            same = '(바이트 동일)' if _read_bytes(base_path) == _read_bytes(os.path.join(dp, f)) else '(다름)'
                        except OSError:
                            same = ''
                    hits.append((rel + same).strip())
                    break
        if hits:
            return [Finding('WARN', 'S5', 'S5:' + ';'.join(sorted(hits))[:200], '동기화 충돌 사본 %d개 — 어느 쪽이 맞는지 확인한 뒤 지우십시오' % len(hits), sorted(hits))]
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
            lost = [h for h in lines if h not in union]
            surv = 100.0 * (len(lines) - len(lost)) / len(lines)
            # 평소(시작 점검)는 기준 아래만 경고하고, --damage(verbose)는 사라진 줄이 하나라도 있으면 전부 보입니다
            if (surv < pct) or (verbose and lost):
                previews = [lines[h][1] if isinstance(lines[h], list) else '' for h in lost]
                gone = '' if self._exists(r) else ' · 파일 자체가 없음'
                F.append(Finding('WARN', 'S6', 'S6:%s' % r,
                                 '%s — 이 컴퓨터가 쓴 줄 %d개 중 %d개가 어디에도 없습니다(생존 %.0f %%)%s' % (r, len(lines), len(lost), surv, gone),
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
                            '이 컴퓨터가 본 항목 ID %d개가 대기 · 이관 · 제안 · 문헌 어디에도 없습니다 — 덮어쓰기 의심' % len(lost), lost)]
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
            return [Finding('INFO', 'S8', 'S8', '구글드라이브 프로세스 있음')]
        return [Finding('WARN' if drive_like else 'INFO', 'S8', 'S8', '구글드라이브 프로세스가 보이지 않습니다 — 동기화가 멈춰 있을 수 있음')]

    # ---- 스냅샷 ---------------------------------------------------
    @staticmethod
    def _snap_name(rel, comp, digest, when=None):
        stem, ext = os.path.splitext(nfc(rel.replace('\\', '/')))
        return '%s_%s_%s_%s%s' % (utc_stamp(when), nfc(comp), stem.replace('/', '__'), digest[:8], ext)

    @staticmethod
    def _snap_key(s):
        """이름의 UTC(초)가 같으면 파일의 수정 시각으로 순서를 가립니다 — 같은 초에 두 판이 생길 수 있습니다."""
        try:
            return (s[0], os.stat(s[5]).st_mtime_ns)
        except OSError:
            return (s[0], 0)

    @classmethod
    def _list_snaps(cls, folder):
        """[(utc, 컴퓨터, 경로 stem, 해시8, 확장자, 파일경로)] — 오래된 것부터"""
        out = []
        if not os.path.isdir(folder):
            return out
        for f in os.listdir(folder):
            m = SNAP_RE.match(f)
            if m:                                    # 컴퓨터 · 경로 stem 은 NFC 로 — 맥 미러의 NFD 이름과 섞여도 같은 파일로 묶이게
                out.append((m.group(1), nfc(m.group(2)), nfc(m.group(3)), m.group(4), m.group(5) or '', os.path.join(folder, f)))
        return sorted(out, key=cls._snap_key)

    def snapshot(self, rel, drive=False, flush=True):
        """현재 판을 로컬(항상)과 드라이브(drive=True)에 남깁니다. 같은 해시가 이미 있으면 만들지 않습니다. 만든 경로 목록.
        지금 본 판의 해시를 「이 컴퓨터가 마지막으로 본 판」(seen.json)으로 적습니다 — 쓰기 뒤 차이 계산의 기준입니다."""
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
        """시각상 마지막 스냅샷 — 컴퓨터를 가리지 않으므로 **쓰기 전 판의 기준으로 쓰지 않습니다**(다른 컴퓨터의 옛 판이 더 늦게 찍혀 있을 수 있음)."""
        for s in reversed(self.snapshots_of(rel)):
            if exclude_digest and s[3] == exclude_digest[:8]:
                continue
            try:
                return _read_bytes(s[5])
            except OSError:
                continue
        return None

    # ---- 이 컴퓨터가 마지막으로 본 판 --------------------------------
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
        """그 해시의 스냅샷 내용 — 어느 컴퓨터가 만든 것이든 내용이 같으므로 이름의 해시8 로 찾고 전체 해시로 확인합니다."""
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
        """쓰기 직후 「쓰기 전 판」 — ① 이 컴퓨터가 마지막으로 본 판(before_write · 세션 경계 · 직전 after_write 가 적음)의 스냅샷,
        ② 그것을 모르면 **이 컴퓨터가 만든** 스냅샷 가운데 가장 최근. 다른 컴퓨터의 스냅샷을 시각만 보고 쓰지 않습니다 —
        맥의 옛 판이 더 늦게 찍혀 있으면 지운 줄이 등록에 남아 S6 가 오탐합니다. 모르면 None(처음 쓰는 파일)."""
        seen = self._seen().get(rel)
        if seen and seen != post_digest:
            data = self._snapshot_bytes_by_digest(rel, seen)
            if data is not None:
                return data
        # 직전 판을 모르거나, 쓰기 전 훅이 이미 바뀐 내용을 본 경우(seen == 지금 판) — 이 컴퓨터의 스냅샷 가운데 지금 판이 아닌 가장 최근.
        # 이미 등록된 줄을 다시 견줘도 결과는 같습니다(지운 줄은 빠져 있고 넣은 줄은 이미 있음).
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
        """스냅샷 보존 정리 — 파일(경로 stem)마다 최근 `snapshot_min` 개는 늘 남기고, 그 밖에서
        ① 자기 컴퓨터 것은 `snapshot_days`(로컬은 2배) 지났거나 개수가 `snapshot_max`(로컬 `snapshot_max_local`)를 넘는 것을 오래된 순으로,
        ② 다른 컴퓨터 것은 `snapshot_days_others` 지난 것을 지웁니다. 미확인 ERROR 가 있으면 지우지 않습니다. 세션 시작 · 끝에 돕니다."""
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
                old = lst[:-keep] if len(lst) > keep else []          # 최근 keep 개는 손대지 않음
                over = max(0, sum(1 for s in lst if s[1] == self.me) - cap)
                for s in old:                                          # 오래된 것부터
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
        """스냅샷으로 되돌립니다. at — 'YYYY-MM-DD HH:MM'(지역 시각) 이하의 가장 최근, digest — 해시 앞 8자리. 되돌리기 전 현재 판도 남깁니다."""
        rel = nfc(rel.replace('\\', '/'))
        snaps = self.snapshots_of(rel)
        if not snaps:
            raise SystemExit('스냅샷이 없습니다: %s' % rel)
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
            raise SystemExit('조건에 맞는 스냅샷이 없습니다: %s (%d개 있음)' % (rel, len(snaps)))
        self.snapshot(rel, drive=True)
        data = _read_bytes(pick[5])
        _atomic_write(self._path(rel), data)
        self.after_write(rel)
        return pick

    # ---- 지문 · 쓴 줄 · ID 등록 -----------------------------------
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
        """쓰기 직전 — 지금 판을 로컬에 남겨 뒤의 차이 계산에 씁니다."""
        if self.is_shared(rel):
            self.snapshot(rel)

    def after_write(self, rel):
        """쓰기 직후 — 로컬 스냅샷 · 지문 · 「이 컴퓨터가 쓴 줄」 갱신(지운 줄은 등록에서 빼고 넣은 줄은 더함)."""
        rel = nfc(rel.replace('\\', '/'))
        if not self.is_shared(rel):
            return
        try:
            post = self.read(rel)
        except OSError:
            return
        pre = self._pre_bytes(rel, sha(post))      # 이 컴퓨터가 쓰기 직전에 본 판 — 시각상 마지막 스냅샷이 아님
        self.snapshot(rel)                          # 지금 판을 남기고 「마지막으로 본 판」을 지금 판으로
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
        """셸 도구(Bash · PowerShell) 뒤 — 지문이 바뀐 공용 파일만 after_write. 명령을 해석하지 않습니다."""
        changed = self.changed_since_fingerprints()
        for r in changed:
            self.after_write(r)
        return changed

    def table_report(self, rels):
        """쓰기 뒤 — 추적 파일(목록 · 대기 · 이관 · 제안 · 문헌)에 남은 표 결함을 [(rel, 설명)] 로. 훅이 그 턴에 알리는 데 씁니다."""
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
        """이 컴퓨터가 본 최대 번호 — 늘어나기만 합니다(줄어드는 것은 S2 가 잡음)."""
        recs = self.records()
        if recs and max(n for n, _ in recs) >= self.max_record_seen():
            self._save('records_max.json', {'max': max(n for n, _ in recs), 'utc': utc_stamp()})

    def remember_records_reset(self):
        """사용자 확인 뒤 — 지금 폴더의 최대 번호를 그대로 받아들입니다."""
        recs = self.records()
        self._save('records_max.json', {'max': max(n for n, _ in recs) if recs else 0, 'utc': utc_stamp()})

    # ---- 경고 상태 · 확인 -----------------------------------------
    def _alerts(self):
        return self._load('alerts.json', {'findings': [], 'acked': {}})

    def record_alerts(self, findings):
        a = self._alerts()
        errs = [f.as_dict() for f in findings if f.level == 'ERROR']
        a['findings'] = errs
        a['utc'] = utc_stamp()
        self._save('alerts.json', a)

    def ack_of(self, key, alerts=None):
        """key 의 유효한 확인 기록({'utc', 'text'}) — `ack_hours` 안이면 그 기록, 아니면 None. 확인이 유효한지는 여기 한 곳에서 정합니다."""
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
        """확인되지 않은 ERROR 목록(Finding)."""
        a = self._alerts()
        return [Finding.from_dict(d) for d in a.get('findings', []) if self.ack_of(d['key'], a) is None]

    def blocking(self, target=None):
        """쓰기를 막을 ERROR — 기록된 것 가운데 미확인, 없으면 싼 검사(write)를 새로 해 기록하고 그 가운데 미확인.
        확인은 key(검사 코드 + 대상 번호 · ID) 단위로 `ack_hours` 동안 유효합니다 — 같은 조건이 생성물 · 폴더에 그대로 남아 있어도 다시 막지
        않고(남은 조건을 지울 정리 도구까지 막으면 교착), 조건이 달라지면(key 가 다르면) 막습니다. 가드 · 일괄 도구 · 세션 끝이 이것을 씁니다."""
        open_ = self.unacked()
        if open_:
            return open_
        fresh = [f for f in self.check('write', target=target) if f.level == 'ERROR']
        if not fresh:
            return []
        self.record_alerts(fresh)
        return self.unacked()

    def ack(self, text):
        """사용자 확인을 기록합니다 — 지금 열린 ERROR 전부. 사라진 ID · 줄은 「정당한 삭제」로 받아들여 등록에서 뺍니다(_rebaseline).
        ERROR 를 닫는 길은 이것뿐이라 사용자 문구 없이 돌리지 않습니다. WARN 만 받아들일 때는 accept_warn()."""
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
        """WARN 수용 — 확인 안 된 ERROR 가 없을 때만 기준(S6 쓴 줄 등록 · S4 본 기록 · S7 본 ID)을 지금 상태에 맞춥니다.
        ERROR 는 건드리지 않습니다. 열린 ERROR 가 있으면 None 을 돌려주고 아무것도 바꾸지 않습니다(닫는 길은 ack 뿐)."""
        if self.blocking():
            return None
        self._rebaseline(utc_stamp(), 'WARN 수용', [])
        return True

    def _rebaseline(self, now, text, keys):
        """사라진 ID · 줄을 정당한 삭제로 받아들여 등록에서 빼고, 본 기록 기준을 다시 잡고, ack_log 에 남깁니다. ack · accept_warn 이 함께 씁니다."""
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
        """쓰기 직전 판정 — 막을 사유 또는 None. 판정은 blocking() — 확인된 key 는 ack_hours 동안 다시 막지 않습니다."""
        rel = nfc(rel.replace('\\', '/')) if rel else rel
        open_ = self.blocking(target=rel)
        if not open_:
            return None
        lines = ['동기화 점검에 확인되지 않은 ERROR 가 있어 공용 파일 쓰기를 막습니다(%s%s).' % (tool, (' → ' + rel) if rel else '')]
        lines += ['  ! ' + f.line() for f in open_]
        lines.append('  사용자에게 위 경고를 보이고 확인을 받은 뒤 `<py> -X utf8 도구/동기화_점검.py --ack "<사용자 문구>"` 를 돌리십시오. '
                     '덮인 파일은 `--restore <파일>` 로 되돌립니다.')
        return '\n'.join(lines)

    # ---- 세션 경계 --------------------------------------------------
    def status_line(self, findings):
        recs = self.records()
        prefix = self.t.get('record_prefix', 'E')
        mx = ('%s%d' % (prefix, max(n for n, _ in recs))) if recs else '기록 없음'
        best = self.latest_change()
        when = datetime.datetime.fromtimestamp(best[0]).strftime('%Y-%m-%d %H:%M') if best else '—'
        days = ((time.time() - best[0]) / 86400.0) if best else 0
        last = self.last_drive_snapshot()
        last_s = ('%s %s' % (last[1], parse_utc(last[0]).astimezone().strftime('%m-%d %H:%M'))) if last else '없음'
        a = self._alerts()
        errs = [f for f in findings if f.level == 'ERROR']
        if any(self.ack_of(f.key, a) is None for f in errs):
            worst = 'ERROR'
        elif errs:
            worst = 'ERROR(확인됨)'
        else:
            worst = 'WARN' if any(f.level == 'WARN' for f in findings) else 'OK'
        return '동기화 %s · %s · 최근 변경 %s (%.1f일 전) · 드라이브 스냅샷 마지막 %s · 이 컴퓨터 %s' % (worst, mx, when, days, last_s, self.me)

    def last_drive_snapshot(self):
        snaps = self._list_snaps(self.snapshot_dir)
        return snaps[-1] if snaps else None

    def session_start(self, snapshot=True):
        findings = self.check('start')
        self.record_alerts(findings)
        if not self.unacked():                # 확인된 ERROR 만 남았으면 지금 상태를 기준으로 받아들입니다(ack 가 이미 등록을 맞춤)
            self.remember_ids()
            self.remember_records()
        if snapshot:
            self.snapshot_all(drive=True)
            self.refresh_fingerprints()
            self.prune()                      # 세션 끝에만 지우면 정리 도구를 안 돌린 세션이 이어질 때 쌓입니다
        return findings

    def session_end(self):
        self.snapshot_all(drive=True)
        self.refresh_fingerprints()
        findings = [f for f in self.check('write') if f.level == 'ERROR']
        if findings:
            self.record_alerts(findings)
            findings = self.unacked()         # 확인된 key 는 「ERROR 남음」으로 다시 알리지 않습니다 — blocking() 과 같은 판정
        if not findings:
            self.remember_ids()
            self.remember_records()
        removed = self.prune()
        return findings, removed

    # ---- 쓰기 잠금 ------------------------------------------------
    def write_lock(self, tool='', wait=None):
        """공용 파일을 읽고 다시 쓰는 동안만 잡는 잠금(WriteLock) — `with sync.write_lock('도구 이름') as lock:` · 못 잡으면 lock.busy."""
        return WriteLock(os.path.join(self.state, LOCK_NAME), tool, _lock_wait(LOCK_WAIT_TOOL) if wait is None else wait)

    def wait_write_lock(self, wait=None):
        """쓰기 직전(훅) — 잠금이 풀릴 때까지 기다립니다. 풀렸으면 True, wait 초가 지나도 잡혀 있으면 False.
        막지는 않습니다 — 부르는 쪽이 어느 쪽이든 통과시키고, 그 틈은 도구의 저장 전 검사가 받칩니다."""
        lock = self.write_lock(None, _lock_wait(LOCK_WAIT_HOOK) if wait is None else wait).acquire()
        free = not lock.busy
        lock.release()
        return free

    def hook_seen(self, marker):
        """같은 도구 호출을 두 훅(설치본 · 프로젝트)이 중복 처리하지 않게 — 처음 보면 False 를 돌려주고 표시합니다."""
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


# ---------------------------------------------------------------- 쓰기 잠금
LOCK_NAME = 'write.lock'
LOCK_WAIT_TOOL = 10.0     # 도구가 잠금을 기다리는 시간(초) — 도구 한 번은 1초 안팎입니다
LOCK_WAIT_HOOK = 6.0      # 훅이 기다리는 시간(초) — 훅 제한 시간보다 짧아야 합니다
LOCK_POLL = 0.05
_LOCKS_HELD = {}          # 이 프로세스가 쥔 잠금 {경로: [파일, 횟수]} — 같은 프로세스가 다시 잡으면 횟수만 늘립니다


def _lock_wait(default):
    """기다리는 시간(초) — 시험은 `SYNC_LOCK_WAIT` 로 줄입니다(`SYNC_STATE_HOME` 과 같은 쓰임)."""
    try:
        return float(os.environ['SYNC_LOCK_WAIT'])
    except (KeyError, ValueError):
        return default


def _os_lock(f):
    """파일 f 에 운영체제 잠금을 겁니다(기다리지 않음). 다른 프로세스가 쥐고 있으면 BlockingIOError."""
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
            raise BlockingIOError(e.errno or errno.EAGAIN, '잠금을 다른 프로세스가 쥐고 있습니다')
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
    """공용 파일을 **읽고 다시 쓰는 동안만** 잡는 잠금 — 프로젝트 하나 · 컴퓨터 하나에 하나(`<상태 폴더>/write.lock`, 동기화 폴더 밖).
    운영체제 잠금이라 쥔 프로세스가 죽으면 저절로 풀립니다 — 남는 잠금이 없고 풀어 줄 사람도 필요 없습니다. 세션 단위로 잡지 않습니다.

        with sync.write_lock('수정필요_정리') as lock:
            if lock.busy:                  # wait 초 안에 못 잡음 — 쓰지 않고 lock.busy_message() 를 알립니다
                ...
            (읽기 → 계산 → 읽은 뒤 바뀌었는지 검사 → 저장)

    state — 'held' 잡음 · 'busy' 다른 프로세스가 쥐고 있어 wait 초 안에 못 잡음 · 'off' 잠금 장치 자체가 실패(상태 폴더에 못 씀 ·
    잠금을 지원하지 않는 파일 시스템) — 막지 않고 잠금 없이 진행합니다. 어느 경우에도 도구의 저장 전 검사가 바닥을 받칩니다.
    같은 프로세스가 다시 잡는 것은 됩니다(횟수만 셈). **잠금을 쥔 채, 잠금을 잡는 다른 도구를 자식 프로세스로 부르지 않습니다** — 서로 기다립니다.
    막지 못하는 것 — Edit · Write 자체(훅은 Edit 보다 먼저 끝나 잠금을 쥘 수 없어, 직전에 풀리기를 기다릴 뿐입니다) · 편집기 손편집 ·
    훅이 없는 앱 · 다른 컴퓨터 · 잠금을 모르는 옛 판의 도구."""

    def __init__(self, path, tool='', wait=LOCK_WAIT_TOOL):
        self.path = path
        self.tool = tool              # None 이면 쥔 쪽 정보를 남기지 않습니다(훅의 기다림)
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
        sys.stderr.write('쓰기 잠금을 쓸 수 없어 잠금 없이 진행합니다(저장 전 검사는 그대로): %r\n' % (e,))
        return self

    def acquire(self):
        ent = _LOCKS_HELD.get(self._key)
        if ent:                       # 이 프로세스가 이미 쥐고 있음
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
            except Exception as e:    # 잠금을 지원하지 않는 파일 시스템 등 — 장치의 결함이 쓰기를 막지 않게
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
        """잠금을 쥔 쪽의 한 줄 설명(못 잡았을 때 알림용). 모르면 빈 문자열."""
        try:
            d = json.loads(_read_bytes(self.path + '.info').decode('utf-8'))
            return '%s (PID %s · %s 부터)' % (d.get('tool') or '?', d.get('pid'), d.get('utc'))
        except Exception:
            return ''

    def busy_message(self):
        w = self.who()
        return ('다른 도구가 공용 파일을 쓰는 중이라 %g초 안에 잠금을 잡지 못했습니다%s — 쓰지 않았습니다. 다시 돌리면 됩니다.'
                % (self.wait, (' · 쥔 쪽: ' + w) if w else ''))


# ---------------------------------------------------------------- 1회 치환 도우미
def replace_once(path, old, new, encoding='utf-8', check_tables=True):
    """`old` 가 파일에 **정확히 1회**일 때만 `new` 로 바꿉니다. 줄끝(CRLF/LF)을 보존하고, 프로젝트 안이면 쓰기 전후 스냅샷 · 지문 ·
    「쓴 줄」 기록까지 합니다. 0회 · 2회 이상이면 ValueError — 이것이 낙관적 동시성 검사입니다(앞서 본 문구가 그대로 있어야 함).
    `.md` 에서 치환이 표 결함(쪼개진 행 · 셀 수 · 끝 `|` — _config.table_problems)을 **늘리면** 쓰지 않고 ValueError 입니다.
    이미 있던 결함은 stderr 경고만. 알고 하는 치환은 check_tables=False. 돌려주는 것 — {'path', 'crlf', 'delta', 'count'}.
    프로젝트 안이면 읽기 → 쓰기 동안 쓰기 잠금(WriteLock)을 잡습니다. 못 잡아도 치환은 합니다 — 1회 검사가 스스로 받칩니다."""
    path = os.path.abspath(path)
    root = find_project_root(path)
    lock = None
    if root:
        try:
            lock = Sync(_load_cfg(root)).write_lock('replace_once').acquire()
            if lock.busy:
                sys.stderr.write('replace_once: ' + lock.busy_message().replace('쓰지 않았습니다. 다시 돌리면 됩니다.', '잠금 없이 치환합니다.') + '\n')
        except Exception:        # 안전장치의 결함이 치환 자체를 막지 않게
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
        raise ValueError('대상 문자열이 %d회 있습니다(정확히 1회여야 함): %s' % (cnt, path))
    sync = None
    if root:
        try:
            sync = Sync(_load_cfg(root))
            sync.before_write(_rel(root, path))
        except Exception:        # 안전장치의 결함이 치환 자체를 막지 않게
            sync = None
    out = b.replace(ob, nb)
    assert out.count(b'\r\n') == b.count(b'\r\n') + (nb.count(b'\r\n') - ob.count(b'\r\n')), '줄바꿈 수가 어긋남'
    if check_tables and path.lower().endswith('.md'):
        before = table_problems(b.decode(encoding, 'replace'))
        after = table_problems(out.decode(encoding, 'replace'))
        grew = [c for c in ('orphan', 'cells', 'tail')
                if sum(1 for x in after if x[1] == c) > sum(1 for x in before if x[1] == c)]
        if grew:
            raise ValueError('치환이 표 행을 깨뜨려 쓰지 않았습니다(한 항목은 한 줄 · 셀 안의 | 는 \\|) — %s: %s'
                             % (path, ' · '.join(describe_table_problem(x) for x in after if x[1] in grew)[:600]))
        if after:
            sys.stderr.write('replace_once: %s 에 이미 있던 표 결함 %d건(이 치환과 무관) — %s\n'
                             % (path, len(after), ' · '.join(describe_table_problem(x) for x in after[:3])))
    _atomic_write(path, out)
    if sync is not None:
        try:
            sync.after_write(_rel(root, path))
        except Exception:
            pass
    return {'path': path, 'crlf': crlf, 'delta': len(out) - len(b), 'count': cnt}


def refuse_if_alert(sync, writing, tool_name):
    """일괄 도구의 진입 검사 — writing(파일을 쓸 참)이면 미확인 ERROR 에서 False(거부). 진단만이면 경고를 보이고 True.
    판정은 Sync.blocking() — 확인된 key 는 ack_hours 동안 다시 막지 않으므로, 확인 뒤에는 남은 조건을 다시 만드는 정리 도구가 돕니다."""
    open_ = sync.blocking()
    if not open_:
        return True
    print('! 동기화 점검 ERROR — %s%s' % (tool_name, ' 를 중단합니다. 확인 뒤 `동기화_점검.py --ack` 를 돌리십시오.' if writing else ' 는 진단만 합니다.'))
    for f in open_:
        print('  ! ' + f.line())
    return not writing
