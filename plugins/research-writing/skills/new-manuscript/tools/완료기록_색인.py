# -*- coding: utf-8 -*-
r"""완료기록_색인.py — 완료 기록(항목당 한 파일)에서 색인을 생성합니다.

사용법  (`<py>` 는 이 컴퓨터의 Python 3 — 윈도 `python` · 맥 `python3`)
    <py> 도구/완료기록_색인.py            수정필요_색인.md 재생성 (평소)
    <py> 도구/완료기록_색인.py --검사     옛 기록의 `대상` 가운데 문법이 확인하지 못한 것을 보여 줌 (파일은 건드리지 않음)

스크립트는 `도구\` 안에 있고 대상 파일은 그 상위(프로젝트 루트)에서 찾습니다.
항목마다 머리에 **완료일** · **대상** · **상태** 줄이 있어야 합니다 — 형식은 `완료기록/README.md`,
`대상` 의 문법은 `_위치.py`. `대상` 이 없는 기록은 경고하고 절별 역색인에서 빠집니다.
"""
import os, re, sys, io

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


def _루트():
    """이 스크립트는 `도구\\` 안에 있고, 대상 파일은 그 상위(프로젝트 루트)에 있습니다.
    루트에 그대로 두고 돌려도 같게 동작합니다."""
    d = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(d) if os.path.basename(d) == '도구' else d


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import load as _load_cfg          # noqa: E402

# 폴더·파일 이름은 `.manuscript/project.json` 이 정합니다. 없으면 기본값이 쓰입니다.
_CFG = _load_cfg()
HERE = _루트()
OUT = os.path.join(HERE, _CFG.records_dir)

# ---------------------------------------------------------------- 색인 생성
IDX = os.path.join(HERE, _CFG.record_index_file)
from _위치 import Grammar, Excluder, section_key   # noqa: E402  — 「파일 · 절」 문법은 _위치.py 한 곳
from _config import state_head                     # noqa: E402  — 상태 어휘는 _config.py 한 곳
from _동기화 import Sync, refuse_if_alert           # noqa: E402  — 동기화 안전장치는 _동기화.py 한 곳

_SYNC = None


def _sync():
    global _SYNC
    if _SYNC is None:
        _SYNC = Sync(_CFG)
    return _SYNC


def read_entries():
    """완료기록/E*.md 를 읽어 (번호, ID, 제목, 완료일, 대상, 상태, 줄수) 목록으로."""
    out = []
    if not os.path.isdir(OUT):
        return out
    for f in os.listdir(OUT):
        m = re.match(r'^E(\d+)\.md$', f)
        if not m:
            continue
        s = io.open(os.path.join(OUT, f), encoding='utf-8').read()
        head = s.split('\n')[0].lstrip('# ').strip()
        eid, title = (head.split('—', 1) + [''])[:2]
        g = lambda k: (re.search(r'\*\*%s\*\*\s*(.+)' % k, s) or [None, ''])[1].strip()
        out.append((int(m.group(1)), eid.strip(), title.strip(),
                    g('완료일'), g('대상'), g('상태'), len(s.split('\n'))))
    return sorted(out)


def warnings_for(ents):
    """사람이 볼 경고 목록. 파일은 건드리지 않습니다."""
    w = []
    miss = [e[1] for e in ents if not e[4] or e[4] == '(미기재)']
    if miss:
        w.append('완료기록: 대상 미기재 %d건 — %s' % (len(miss), ', '.join(miss)))
    nums = [e[0] for e in ents]
    if nums:
        gap = ['E%d' % n for n in range(1, max(nums) + 1) if n not in set(nums)]
        if gap:
            w.append('완료기록: E 결번 %s' % gap)
    return w


def parse_entries(ents):
    """항목마다 `대상` 을 (파일, 절) 로 가릅니다.

    돌려주는 것 — (문법, 역색인 {루트 기준 경로: {절: [E…]}}, 파일 없는 글 {글: [E…]},
    제외 파일만 건드린 E 목록, 확인하지 못한 이름 [(E, 이름)], 파일 없이 나온 절 표기 [(E, [절…])]).
    제외(설정의 추적 파일 · `record_index_exclude` · `output_pattern`)는 이 색인에서만 적용합니다.
    """
    g, ex = Grammar(_CFG), Excluder(_CFG)
    idx, free, only_excl, asis, orphans = {}, {}, [], [], []
    for n, eid, title, date, tgt, st, ln in ents:
        p = g.parse(tgt)
        asis += [(eid, a) for a in p.unresolved]
        if p.orphans:
            orphans.append((eid, p.orphans))
        if not p.files:
            free.setdefault(p.free_text or '(미기재)', []).append(eid)
            continue
        kept = [(path, secs) for path, secs in p.files.items() if not ex.hit(path, p.written.get(path))]
        if not kept:
            only_excl.append(eid)
            continue
        for path, secs in kept:
            d = idx.setdefault(path, {})
            for s in (secs or ['']):
                d.setdefault(s, []).append(eid)
    return g, idx, free, only_excl, asis, orphans


def render_index():
    """색인 본문을 문자열로 만듭니다. 쓰지 않습니다 — (본문, 항목, 역색인) 을 돌려줍니다."""
    ents = read_entries()
    if not ents:
        return None, [], {}
    g, idx, free, only_excl, asis, orphans = parse_entries(ents)
    L = ['# 완료 기록 색인 — %s' % _CFG.name,
         _sync().stamp_for_records(),             # 생성 스탬프 — 어느 완료기록 묶음에서 만들어졌는지(동기화 점검 S4 가 대조)
         '',
         '**완료 기록을 찾을 때 이 파일만 엽니다.** 항목 본문은 `완료기록\\E<번호>.md` 한 파일씩입니다.',
         '이 파일은 `도구\\완료기록_색인.py` 가 생성합니다 — 손으로 고치지 마십시오.', '',
         '이 색인을 다시 만들 때 — `<py> 도구/완료기록_색인.py`',
         '`<py>` 는 이 컴퓨터의 Python 3 입니다 — 윈도 `python` · 맥 `python3`.', '',
         '읽는 순서 — ① 아래 **절별 역색인**에서 손댈 파일과 절을 찾아 ID를 얻고 ② `완료기록\\E<번호>.md` 하나만 읽습니다.',
         '', '---', '', '## 1. 절별 역색인', '',
         '절 · 도판 번호는 그 기록을 쓸 때의 번호입니다. `—` 는 절을 적지 않은 기록입니다.', '',
         '| 파일 | 절 | 항목 |', '|---|---|---|']
    for path in sorted(idx, key=lambda p: g.sort_key(p)):
        for s in sorted(idx[path], key=section_key):
            L.append('| `%s` | %s | %s |' % (g.display(path), s or '—', ' · '.join(idx[path][s])))
    for t in sorted(free):
        L.append('| %s | — | %s |' % (t, ' · '.join(free[t])))
    if only_excl:
        L.append('| (제외 파일만) | — | %s |' % ' · '.join(only_excl))
    L += ['', '---', '', '## 2. ID 색인', '',
          '| ID | 항목 | 완료일 | 상태 |', '|---|---|---|---|']
    for n, eid, title, date, tgt, st, ln in ents:
        L.append('| %s | %s | %s | %s |' % (eid, title, date, state_head(st)))
    L += ['', '---', '', '## 3. D·B 에서 이관한 항목', '',
          '본문은 `완료기록\\이관_DB.md` 에 있습니다.', '']
    mig = os.path.join(OUT, '이관_DB.md')
    if os.path.exists(mig):
        s = io.open(mig, encoding='utf-8').read()
        ids = re.findall(r'^\|\s*([A-Z]\d+)\s*\|', s, re.M)
        L.append('수록 항목 %d건 — %s' % (len(ids), ' · '.join(ids)))
    L.append('')
    return '\n'.join(L) + '\n', ents, idx


def check():
    """`--검사` — 옛 기록의 `대상` 가운데 문법이 확인하지 못한 것을 보여 줍니다. 파일은 건드리지 않습니다.
    실행마다 경고하지 않는 까닭 — 확정된 기록은 고치지 않으므로 영구 소음이 됩니다."""
    ents = read_entries()
    if not ents:
        print('완료 기록이 없습니다.'); return 0
    g, idx, free, only_excl, asis, orphans = parse_entries(ents)
    print('확인하지 못한 이름(쓴 그대로 색인됨) %d건' % len(asis))
    for eid, a in asis:
        print('  %s\t%s' % (eid, a))
    print('파일 없이 나온 절 표기(색인에서 빠짐) %d건' % len(orphans))
    for eid, secs in orphans:
        print('  %s\t%s' % (eid, ' · '.join(secs)))
    print('파일 없는 글로 색인된 기록 %d건 — %s' % (len(free), ' · '.join('%s: %s' % (t, ' '.join(v)) for t, v in free.items())))
    print('제외 파일만 건드린 기록 %d건 — %s' % (len(only_excl), ' · '.join(only_excl)))
    return 0


EMPTY_INDEX = '''# 완료 기록 색인

**완료 기록을 찾을 때 이 파일만 엽니다.** 항목 본문은 완료기록 폴더에 한 파일씩입니다.
이 파일은 완료기록_색인.py 가 생성합니다 - 손으로 고치지 마십시오.

아직 완료 기록이 없습니다. 첫 항목을 만든 뒤 이 도구를 다시 돌리십시오.
'''


def build_index():
    if not refuse_if_alert(_sync(), True, '완료기록_색인'):
        return 3
    with _sync().write_lock('완료기록_색인') as lock:     # 기록 읽기 → 색인 쓰기를 한 묶음으로 — 정리 도구 · 다른 색인 실행과 엇갈리지 않게
        if lock.busy:                                   # 색인은 기록 파일에서 통째로 다시 만드는 파일이라, 못 만들어도 다음 실행이 맞춥니다
            print('! ' + lock.busy_message())
            return 4
        return _build_index_locked()


def _build_index_locked():
    text, ents, bysec = render_index()
    if text is None:
        # 새 프로젝트라 완료 기록이 아직 없는 경우 — 빈 색인을 만들어 두고 정상 종료합니다.
        # 정리 도구가 색인 파일의 존재를 전제로 하기 때문입니다.
        if os.path.isdir(OUT):
            io.open(IDX, 'w', encoding='utf-8', newline='').write(EMPTY_INDEX)
            print('색인 생성 — 완료 기록이 아직 없습니다 (항목 0건)')
            return 0
        print('완료기록 폴더가 없습니다. 먼저 만드십시오.'); return 1
    _sync().before_write(_CFG.record_index_file.replace('\\', '/'))
    io.open(IDX, 'w', encoding='utf-8', newline='').write(text)
    _sync().after_write(_CFG.record_index_file.replace('\\', '/'))
    print('수정필요_색인.md 재생성 — 항목 %d건, 파일 %d개 · 행 %d개'
          % (len(ents), len(bysec), sum(len(v) for v in bysec.values())))
    for w in warnings_for(ents):
        print('  ! ' + w)
    return 0


if __name__ == '__main__':
    if '--검사' in sys.argv:
        sys.exit(check())
    sys.exit(build_index())
