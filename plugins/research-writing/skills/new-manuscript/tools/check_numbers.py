# -*- coding: utf-8 -*-
r"""번호 전수 점검 — Figure · Table · 참고문헌

각 장의 본문 수정을 마칠 때마다 한 번 돌립니다. 고치지 않고 **진단만** 합니다.

사용법  (`<py>` 는 이 컴퓨터의 Python 3 — 윈도 `python` · 맥 `python3`)
    <py> tools/check_numbers.py                 # 설정의 원고 폴더(manuscript.source_dir)를 기준으로 점검 (기본)
    <py> tools/check_numbers.py <원고 폴더 경로>

셸이 폴더에 닿지 않는 동기화 미러에서는
`ch1~4.md`, `references.md`, `build_tpl.py`, 이 파일을 스테이징해 사본에 대해 돌립니다.

점검 항목
  1. 캡션 번호가 장별로 1부터 빠짐없이 이어지는지
  2. 본문 최초 인용 순서가 캡션 번호 순서와 같은지 (어긋나면 번호를 맞바꾸거나 문장 순서를 바꿈)
  3. 캡션은 있으나 본문에서 인용되지 않은 도판·표, 반대로 캡션 없는 번호를 인용한 곳
  4. 장 사이 상호참조와 build_tpl.py 안(Appendix·목차)의 참조
  5. 참고문헌 키의 중복·결번·임시번호(N*), 목록에 없는 번호를 인용한 곳, 인용되지 않은 항목
  6. 본문 최초 등장 순서가 목록 번호 순서를 거스르는 지점 (§8 통합 번호 체계)
  7. 빌드가 renumber 로 낼 산출물 번호 미리보기 — 결번이 사라지는지 확인

번호 방식은 `.manuscript/project.json` 의 `kind` 가 정합니다 (2026-09-14 신설).
  kind = "journal"   평면 번호. 원고 전체에서 Figure 1, Figure 2 … 로 이어집니다.
                     참고문헌도 단일 목록이며 최초 등장 순서 = 번호 순서를 검사합니다.
  그 밖(학위논문)     장-번호. 장마다 Figure 3-1 부터 다시 셉니다. 종전 동작 그대로입니다.

표기는 `Figure 1` 과 `Fig. 1` 을 **둘 다** 받습니다 (`Figs. 1 and 2` 포함).
저널 양식이 어느 쪽을 요구하든 원고의 글자만 바꾸면 되고 이 도구는 고치지 않습니다.
"""
import re, sys, os, collections

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


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import load as _load_cfg, FIG_TAB_WORDS, FIG_TAB_NUM_FLAT, FIG_TAB_NUM_CHAPTER  # noqa: E402

_CFG = _load_cfg()
HERE = sys.argv[1] if len(sys.argv) > 1 else _CFG.source_dir
FILES = _CFG.chapters                           # .manuscript/project.json 이 정합니다
REFS_FILE = _CFG.references
BUILD_SCRIPT = _CFG.build_script
SHOW_NOTES = False                     # build_tpl.py 기본값과 같게 둡니다
CITE_PAT = re.compile(r'\[(N?\d+)(?:\s[^\]]*)?\]')

# 2026-09-14 — 저널 원고 지원. 번호 방식은 설정의 `kind` 가 정합니다(파일 머리 참조).
JOURNAL = (_CFG.kind == 'journal')
_NUM = FIG_TAB_NUM_FLAT if JOURNAL else FIG_TAB_NUM_CHAPTER   # 평면 번호 / 장-번호 — 표지 정의는 _config.py 한 곳
_HEAD = FIG_TAB_WORDS                                        # Figure 1 · Fig. 1 · Figs. 1 · Table 1
CAP_PAT = re.compile(r'@(FIG|TAB)\s+(\S+)\s*\|\s*' + _HEAD + r'\s+(%s)\.' % _NUM)
XREF_PAT = re.compile(r'(' + _HEAD + r')\s+(%s)(?:\s+and\s+(%s))?' % (_NUM, _NUM))
problems = []


def path(f):
    return os.path.join(HERE, f)


def blocks(f):
    src = open(path(f), encoding='utf8').read()
    for b in re.split(r'\n\s*\n', src):
        yield re.sub(r'\s*\n\s*', ' ', b.strip())


def printable(b):
    return not (b.startswith('@REF ') or (b.startswith('@NOTE ') and not SHOW_NOTES))


def xrefs(b):
    """한 블록의 도판·표 참조를 등장 순서로 돌려줍니다. `Figures 3-5 and 3-6` 형태 포함."""
    out = []
    for m in XREF_PAT.finditer(b):
        kind = 'FIG' if m.group(1).startswith('Fig') else 'TAB'
        out.append((kind, m.group(2)))
        if m.group(3):
            out.append((kind, m.group(3)))
    return out


print('=' * 72)
print('1. Figure · Table 번호')
print('=' * 72)
def collect(f):
    """파일 하나의 캡션 선언과 본문 참조를 등장 순서로 돌려줍니다."""
    decl, refs = [], []
    for b in blocks(f):
        m = CAP_PAT.match(b)
        if m:
            decl.append((m.group(1), m.group(3), m.group(2)))
            # 2026-09-14 — 캡션 블록은 본문 인용으로 세지 않습니다. 종전에는 캡션이
            # 제 번호를 스스로 인용한 것으로 잡혀 '미인용' 검출이 늘 비어 있었습니다.
            continue
        if printable(b):
            refs += xrefs(b)
    return decl, refs


def check(tag, decl, refs, pre):
    """한 묶음의 번호를 봅니다 — 저널이면 원고 전체, 학위논문이면 한 장.
    pre 가 None 이면 평면 번호(1, 2, …), 아니면 장-번호(3-1, 3-2, …)입니다."""
    for kind, label in (('FIG', 'Figure'), ('TAB', 'Table')):
        d = [n for k, n, _ in decl if k == kind]
        if not d:
            continue
        want = ([str(i) for i in range(1, len(d) + 1)] if pre is None
                else [f'{pre}-{i}' for i in range(1, len(d) + 1)])
        ok = d == want
        print(f'  {tag} {label:6s} 캡션 {len(d)}건  {"OK" if ok else "번호 불연속"}  {d}')
        if not ok:
            problems.append(f'{tag} {label} 캡션 번호 불연속 {d}')
        first = []
        for k, n in refs:
            if k == kind and n not in first:
                first.append(n)
        inch = first if pre is None else [n for n in first if n.startswith(f'{pre}-')]
        if inch != [n for n in d if n in inch]:
            print(f'      ! 최초 인용 순서 {inch}  ≠  캡션 순서 {d}')
            problems.append(f'{tag} {label} 최초 인용 순서 어긋남')
        miss = [n for n in d if n not in first]
        if miss:
            print(f'      ! 본문에서 인용되지 않음 {miss}')
            problems.append(f'{tag} {label} 미인용 {miss}')
        ghost = [n for n in inch if n not in d]
        if ghost:
            print(f'      ! 캡션이 없는 번호를 인용 {ghost}')
            problems.append(f'{tag} {label} 캡션없는 인용 {ghost}')


gathered = [(ch, f) + collect(f) for ch, f in FILES]
if JOURNAL:
    # 저널 원고 — 번호가 원고 전체에서 하나로 이어집니다.
    check('원고 전체',
          [d for _, _, dd, _ in gathered for d in dd],
          [r for _, _, _, rr in gathered for r in rr], None)
    empty = [f for _, f, dd, _ in gathered if not dd]
    if empty:
        print(f'  (캡션 선언이 아직 없는 파일 — {", ".join(empty)})')
else:
    for ch, f, dd, rr in gathered:
        check(f'ch{ch}', dd, rr, ch)

print()
print('=' * 72)
print('2. 장 사이 상호참조와 build_tpl.py 안의 참조')
print('=' * 72)
declared = set()
for ch, f in FILES:
    for b in blocks(f):
        m = CAP_PAT.match(b)
        if m:
            declared.add((m.group(1), m.group(3)))
if JOURNAL:
    # 평면 번호에는 '타 장 참조' 개념이 없습니다 — 1절이 원고 전체를 한 번에 봤습니다.
    print('  (저널 원고 — 번호가 원고 전체에서 하나이므로 장 사이 참조 점검은 건너뜁니다)')
else:
    for ch, f in FILES:
        cross = []
        for b in blocks(f):
            if not printable(b):
                continue
            for kind, n in xrefs(b):
                if not n.startswith(f'{ch}-') and (kind, n) not in cross:
                    cross.append((kind, n))
        for kind, n in cross:
            mark = '' if (kind, n) in declared else '   ← 그런 캡션이 없습니다'
            print(f'  ch{ch} → {kind} {n}{mark}')
            if mark:
                problems.append(f'ch{ch} 타 장 참조 {kind} {n} 캡션 없음')
# 빌드 스크립트는 프로젝트마다 있을 수도, 없을 수도 있습니다 (저널 원고에는 보통 없습니다).
_bt_path = path(BUILD_SCRIPT)
if os.path.isfile(_bt_path):
    bt = open(_bt_path, encoding='utf8').read()
    for m in re.finditer(_HEAD + r"\s+(%s)" % _NUM, bt):
        kind = 'FIG' if m.group(0).startswith('Fig') else 'TAB'
        ln = bt[:m.start()].count('\n') + 1
        mark = '' if (kind, m.group(1)) in declared else '   ← 그런 캡션이 없습니다'
        print(f'  {BUILD_SCRIPT}:{ln} → {m.group(0)}{mark}')
        if mark:
            problems.append(f'{BUILD_SCRIPT}:{ln} 참조 {m.group(0)} 캡션 없음')
else:
    print(f'  ({BUILD_SCRIPT} 없음 — 빌드 스크립트 안의 참조 점검은 건너뜁니다)')

print()
print('=' * 72)
print('3. 참고문헌')
print('=' * 72)
refs = []
for b in blocks(REFS_FILE):
    m = re.match(r'@REF\s+(N?\d+)\.\s*(.+)$', b)
    if m:
        refs.append((m.group(1), m.group(2)))
keys = [k for k, _ in refs]
print(f'  @REF 항목 {len(refs)}건')
dup = [k for k, c in collections.Counter(keys).items() if c > 1]
if dup:
    print(f'  ! 중복 키 {dup}')
    problems.append(f'참고문헌 중복 키 {dup}')
nums = sorted(int(k) for k in keys if k.isdigit())
gaps = [n for n in range(nums[0], nums[-1] + 1) if n not in nums] if nums else []
if gaps:
    print(f'  ! 결번 {gaps}')
    problems.append(f'참고문헌 결번 {gaps}')
temp = [k for k in keys if not k.isdigit()]
if temp:
    print(f'  ! 임시 번호 {temp}')
    problems.append(f'참고문헌 임시번호 {temp}')

ref_keys = set(keys)
order, seen, where = [], set(), {}
for ch, f in FILES:
    for b in blocks(f):
        if not printable(b):
            continue
        for m in CITE_PAT.finditer(b):
            k = m.group(1)
            where.setdefault(k, set()).add(ch)
            if k in ref_keys and k not in seen:
                seen.add(k)
                order.append((k, ch))
unknown = sorted(set(where) - ref_keys)
if unknown:
    print(f'  ! 목록에 없는 번호를 인용 {unknown}')
    problems.append(f'미등록 인용 {unknown}')
unused = [k for k in keys if k not in seen]
if unused:
    print(f'  ! 인용되지 않은 항목 {len(unused)}건 {unused}')
    problems.append(f'미인용 문헌 {unused}')
print(f'  본문에서 인용된 문헌 {len(order)}건 / 목록 {len(keys)}건')

# 2026-09-14 — 저널 원고는 단일 목록입니다. Elsevier numeric 계열은 **최초 등장 순서**로
# 번호를 매기므로, 소스 md 의 번호가 그 순서와 같아야 합니다. 장별 목록 검사는 건너뜁니다.
if JOURNAL:
    seq = [k for k, _ in order if k.isdigit()]
    want_seq = [str(i) for i in range(1, len(seq) + 1)]
    if not seq:
        print('  (확정 번호로 인용된 문헌이 아직 없습니다)')
    elif seq == want_seq:
        print(f'  최초 등장 순서 = 목록 번호 순서  OK (1–{len(seq)})')
    else:
        off = next((i for i, (a, b2) in enumerate(zip(seq, want_seq)) if a != b2), 0)
        print(f'  ! 최초 등장 순서가 번호 순서를 거스릅니다 — {off + 1}번째부터. 실제 {seq[:15]}')
        problems.append('참고문헌 최초 등장 순서 어긋남')

# 2026-08-18 — 참고문헌이 장별 목록으로 바뀌었습니다(D15·E118). 산출물 번호는 장마다 1부터
# 다시 매겨지므로, 소스 md 번호의 '최초 등장 역행'은 산출물에 아무 영향이 없어 검사에서 뺐습니다.
# 종전 단일 목록으로 되돌리려면 빌드에서 REFS=single 을 씁니다.
if not JOURNAL:
    per_ch = {}
    for ch, f in FILES:
        seen_ch = set()
        for b in blocks(f):
            if not printable(b):
                continue
            for m in CITE_PAT.finditer(b):
                k = m.group(1)
                if k in ref_keys and k not in seen_ch:
                    seen_ch.add(k)
                    per_ch.setdefault(ch, []).append(k)
    print('  빌드(REFS=perchapter) 산출물 — '
          + ' / '.join(f'Ch.{ch} 1–{len(v)}' for ch, v in sorted(per_ch.items())))
    both = sorted({k for a, va in per_ch.items() for b2, vb in per_ch.items()
                   if a < b2 for k in set(va) & set(vb)}, key=lambda x: (len(x), x))
    if both:
        print(f'  두 장 이상에서 인용되어 장마다 다른 번호를 받는 문헌 {len(both)}건 — '
              + ', '.join(both) + ' (장별 목록에서는 정상입니다)')

print()
print('=' * 72)
if problems:
    print(f'요약 — 확인할 항목 {len(problems)}건')
    for p in problems:
        print('  ·', p)
else:
    print('요약 — 정상입니다. 번호에 어긋난 곳이 없습니다.')
print('=' * 72)
