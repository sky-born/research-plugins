# -*- coding: utf-8 -*-
r"""새 원고 프로젝트를 만듭니다 — 도구·설정·추적 파일 뼈대를 한 번에.

사용:  (`<py>` 는 이 컴퓨터의 Python 3 — 윈도 `python` · 맥 `python3`)
    <py> -X utf8 init_manuscript.py <대상폴더> --name "논문 이름" [옵션]

옵션:
    --kind journal|dissertation      기본 journal
    --source-dir manuscript_src      원고 md 폴더 이름 (기본값은 설정 기본값과 같음)
    --chapters intro.md results.md   챕터 파일. 생략하면 --chapter-count 로 ch1..chN
    --chapter-count 4
    --references bib.md
    --build-script build.py          없으면 빌드 참조 점검을 건너뜁니다
    --triggers "지금,해당 절 작업 시,..."
    --force                          이미 있는 파일도 덮어씁니다 (기본은 건너뜀)

이미 있는 파일은 **건너뜁니다.** 두 번 돌려도 안전합니다.
폴더 · 파일 이름은 `tools/_config.py` 의 DEFAULTS 를 따르고, 만든 `.manuscript/project.json` 에 그대로 적습니다.
"""

import argparse
import io
import json
import os
import shutil
import sys

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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools'))
from _config import DEFAULTS  # noqa: E402  — 이름의 기본값은 이 한 곳

# 템플릿에 넣는 이름 — 만든 설정과 같은 값
N = dict(DEFAULTS['tracker'], tools=DEFAULTS['tools_dir'])
# 프로젝트에 복사해 관리하는 파일 목록의 원본은 managed_files.json 하나입니다 —
# 갱신 도구(update_tools.py)와 해시 생성기(scripts/tool_hashes.py)도 같은 파일을 읽습니다.
MANAGED = json.load(io.open(os.path.join(HERE, 'managed_files.json'), encoding='utf-8'))['files']
HOOKS_SRC = os.path.join(HERE, 'hooks')
# .claude/settings.json — 완료 기록 E*.md 와 생성 색인을 Write 도구로 덮어쓰는 것을 막는 PreToolUse 훅.
# hooks/settings.example.json 과 같은 내용입니다. 이미 settings.json 이 있으면 건너뛰고 안내만 냅니다.
SETTINGS_JSON = io.open(os.path.join(HOOKS_SRC, 'settings.example.json'), encoding='utf-8').read() \
    if os.path.isfile(os.path.join(HOOKS_SRC, 'settings.example.json')) else ''

DEFAULT_TRIGGERS = list(DEFAULTS['tracker']['triggers'])


def w(path, text, force, made, skipped):
    if os.path.exists(path) and not force:
        skipped.append(path)
        return
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    io.open(path, 'w', encoding='utf-8', newline='').write(text)
    made.append(path)


def tracker_index(name, triggers):
    tl = ' · '.join('`%s`' % t for t in triggers)
    return """# 수정 필요 목록 — {name}

세션 간 인수인계 색인입니다. **매 세션 시작 시 이 파일 하나만 통독합니다.**
미결 항목 본문은 `{pending}`, 완료 기록은 `{record_index}` 에 있습니다.

**§2~§6 은 `{tools}/tidy_tracker.py` 가 생성합니다. 손으로 고치지 마십시오.**

## 1. 기재 규칙

- 새 항목은 `<py> -X utf8 {tools}/new_pending.py <행 파일>` 로 `{pending}` 의 분류 표 맨 아래에 등록합니다 — 행의 ID 자리를
  `D?` 처럼 `글자?` 로 적으면 도구가 번호를 정합니다(플러그인 `tracker-workflow.md` 「동시 편집」). 번호를 골라 손으로 넣지 않습니다.
- `위치` 는 파일과 절을 함께 적습니다 — 루트 기준 경로를 백틱에, 절은 그 바로 뒤. 위치 표가 이 값으로 만들어집니다
  (문법은 플러그인 `tracker-workflow.md` 「대상 · 위치 문법」).
- `트리거` 는 아래 값 중 하나만 씁니다. 다른 값을 쓰면 정리 도구가 경고합니다.

  {tl}

- 상태 값에 `필요`·`대기` 가 있으면 미결입니다. `반영` 은 사용자 확정 전이므로 목록에 남깁니다.
- **ID 는 재사용하지 않습니다.**

## 2. 상시 — 환경 제약

<!-- 상시F -->
| ID | 항목 | 상태 | 비고 |
|---|---|---|---|
<!-- /상시F -->

## 3. 위치 표 — 이 절을 손대면 이 항목을 엽니다

<!-- 위치표 -->

<!-- /위치표 -->

## 4. 트리거 표 — 이 조건이 풀리면 이 항목을 꺼냅니다

<!-- 트리거표 -->

<!-- /트리거표 -->

## 5. 지금 손댈 수 있는 항목

<!-- 지금 -->

<!-- /지금 -->

## 6. 지금 작업 중인 장

<!-- 포커스 -->

<!-- /포커스 -->
""".format(name=name, tl=tl, **N)


def tracker_pending():
    head = """# 수정 필요 — 미결 항목 본문

찾는 절차는 두 단계입니다. **통독하지 말고 색인에서 ID 를 얻어 그 항목만 읽습니다.**

    1) {index} 의 위치 표에서   <파일> <절>  ->  D3 · H1
    2) 이 파일에서 그 행만 읽습니다

## 이 파일의 규약

- 한 항목은 표의 한 행입니다. 긴 설명이 필요하면 표 아래에 `### <ID> 상세` 로 붙입니다.
- **ID 는 재사용하지 않습니다.** 새 항목의 번호는 `{tools}/new_pending.py` 가 정하고, 완료된 항목은 `{archive}` 로 옮깁니다.
- 상태가 `완료`·`종결` 이 되면 정리 도구가 이관합니다.
""".format(**N)
    titles = {
        'A': 'A. 확정 대기 — 외부 조건이 정해져야 손댈 수 있는 항목',
        'B': 'B. 후속 장·절 확정 시 함께 고쳐야 할 항목',
        'C': 'C. 서식 확인 필요',
        'D': 'D. 문체·일관성 — 최종 교차 점검 대상',
    }
    body = []
    for cls in ['A', 'B', 'C', 'D']:
        body.append("""
## {t}

| ID | 항목 | 위치 | 트리거 | 상태 | 비고 |
|---|---|---|---|---|---|

<!-- 이관목록:{c} -->
<!-- /이관목록:{c} -->
""".format(t=titles[cls], c=cls))
    return head + ''.join(body)


ARCHIVE = """# 이관한 완료 항목

미결 표에서 완료·종결로 넘어온 항목입니다. **원 ID 를 그대로 씁니다.**
본문 기록은 `{records_dir}/E<번호>.md` 에 있고, 색인은 `{record_index}` 입니다.

<!-- 본문:이관 -->
| ID | 항목 | 위치 | 상태 | 비고 |
|---|---|---|---|---|
<!-- /본문:이관 -->
""".format(**N)

RECORDS_README = """# 완료 기록 — 형식 규약

**항목 하나에 파일 하나입니다.** 파일 이름은 `E<번호>.md`.

    # E<번호> — 제목

    **완료일** YYYY-MM-DD
    **대상** 고친 파일과 절
    **상태** 반영 (확정 대기) | 확정 | 종결

    ## 발단
    ...

- `대상` 은 색인의 역색인이 됩니다 — 고친 파일을 **루트 기준 전체 경로로 백틱에** 적고, 절(`③` · `¶2` · `§3.2.1` · `Figure 3`)은
  그 경로 **바로 뒤**에 둡니다. 파일 없이 범위만 적을 때는 `전체` 처럼 한 낱말로. 문법은 플러그인 `tracker-workflow.md` 「대상 · 위치 문법」.
- `상태` 를 `확정` 으로 적으려면 **사용자가 확정을 선언한 문구를 인용할 수 있어야 합니다.**
  "반영해줘" 나 "이대로 가자" 는 반영 지시이지 확정 선언이 아닙니다.
- **확정된 항목은 고치지 않고 새 번호로 대체합니다.**
- **새 항목은 `<py> {tools}/new_record.py <본문파일>` 로 만듭니다.** 본문 첫 줄을 `# E? — 제목` 으로 쓰면
  도구가 다음 빈 번호를 원자적으로 잡아 `E?` 를 바꿔 넣습니다. 번호를 손으로 세어 Write 로 만들지 않습니다 —
  이미 있는 `E*.md` 에 대한 Write 는 `.claude/settings.json` 의 훅이 거부합니다.
- 항목을 늘리거나 고친 뒤 `<py> {tools}/index_records.py` 로 색인을 다시 만듭니다.
- 위 `<py>` 는 이 컴퓨터의 Python 3 실행기입니다 — 윈도 `python` · 맥 `python3`.
""".format(**N)

LITERATURE = """# 문헌 — 라이브러리 상태와 참고문헌 대조

## F. 문헌 라이브러리 상시 항목

여기 적은 항목은 정리 도구가 `{index}` §2 로 실어 갑니다.

| ID | 항목 | 상태 | 비고 |
|---|---|---|---|

## G. 참고문헌 전수 대조

인용을 확정하기 전에 이 표를 확인합니다.
**전문과 근거 문장을 직접 확인하기 전에는 확정하지 않습니다.** 초록만 일치하는 것으로는 부족합니다.

| 번호 | 제1저자 | 보유 | 비고 |
|---|---|---|---|
""".format(**N)

PROPOSALS = """# 제안 — 채택 여부 결정 대기

채택하면 대기 파일의 항목으로 옮기거나 바로 반영하고, 버리면 상태를 `종결` 로 적습니다.

| ID | 제안 | 위치 | 트리거 | 상태 | 비고 |
|---|---|---|---|---|---|
"""


def claude_md(name, kind, cfg, markers):
    kind_ko = '학위논문' if kind == 'dissertation' else '저널 원고'
    mk = ' · '.join('`%s`' % m for m in markers)
    return """# 작업 규칙 — {name}

## 프로젝트 정체 — 세션 시작 시 가장 먼저 확인합니다

| 항목 | 값 |
|---|---|
| **프로젝트** | {name} |
| **성격** | {kind_ko} |
| **마커 파일** | {mk} |
| **쓰기 가능** | 이 폴더 하나 |
| **쓰는 스킬** | `manuscript` (진입) · `manuscript-workflow` · `paper-search` |

**형제 폴더의 원고는 이 프로젝트가 아닙니다.** 다른 논문 폴더의 파일을 만들거나 고치지 않고,
그쪽 문장을 가져와 이 원고에 넣지 않습니다. 같은 데이터를 다루더라도 **별개 문서**입니다.

---

## 공통 규칙은 플러그인을 따릅니다

문체·금지 표현, 근거 등급과 헤지, 인용 확정, 수정안 제시와 확정 선언, 미결 항목 추적,
도판 기술 규칙은 **`research-writing` 플러그인의 `manuscript-workflow` 스킬**에 있습니다.
**원고 문장을 고치기 전과 원고·답변서를 내기 전에 `references/revision-protocol.md` 를 읽습니다.**

이 문서에는 **이 원고의 사실만** 적습니다 — 구성, 도메인 근거 한계, 파일 지도, 도판 출처.

## 파일 지도

| 파일 | 역할 |
|---|---|
| `CLAUDE.md` | 이 문서 |
| `AGENTS.md` | Codex 진입 안내. 이 문서를 공통 원본으로 읽습니다 |
| `.manuscript/project.json` | 챕터·파일명·트리거. 도구가 읽습니다 |
| `{index}` | **색인.** 매 세션 통독. §2~§6 은 자동 생성 |
| `{pending}` | 미결 항목 본문 A·B·C·D |
| `{record_index}` | 완료 기록 색인 |
| `{records_dir}/E*.md` | 완료 기록 본문. 항목당 한 파일. **새 항목은 `{tools}/new_record.py` 로 만듭니다** |
| `{src}/` | 원고 md |
| (경로 — 작성하십시오) | 피할 표현 목록. 같은 분야 공용 파일이 있으면 그 경로, 없으면 루트 `avoid_phrases.md` — 규약은 플러그인 `style-guide.md` 「어법」 |
| `{tools}/` | 번호 점검·미결 정리·색인 생성·기록 번호 할당·미결 번호 할당·문법 점검 기준 |
| `.claude/settings.json` · `.claude/hooks/guard_write.py` | 이미 있는 `{records_dir}/E*.md`·`{record_index}` 를 Write 도구로 덮어쓰면 거부하고, 새 미결 ID 행을 손으로 넣는 것도 거부하는 훅 |

## 도구

    <py> -X utf8 {tools}/check_numbers.py                 # 장 하나를 마칠 때마다
    <py> -X utf8 {tools}/tidy_tracker.py --apply          # 승인된 추적 변경을 정리할 때
    <py> -X utf8 {tools}/new_record.py <본문.md>          # 완료 기록을 새 번호에 만들 때 (첫 줄 `# E? — 제목`)
    <py> -X utf8 {tools}/new_pending.py <행.md>           # 새 미결 항목을 다음 번호로 등록할 때 (한 줄 · ID 자리 `D?`)
    <py> -X utf8 {tools}/index_records.py                 # 완료 기록을 늘리거나 고친 뒤
    <py> -X utf8 {tools}/grammar_baseline.py changed --out    # 제출 전 문법 점검 — 기준 뒤 바뀐 단위만 (절차는 revision-protocol.md 「기준」)

**`<py>` 는 이 컴퓨터의 Python 3 실행기입니다 — 윈도 `python` · 맥 `python3`.**
윈도의 `python3` 는 Microsoft Store 스텁이 잡혀 버전조차 내지 못하는 경우가 있고,
맥의 `python` 은 셸 alias 라 스크립트 안에서 풀리지 않습니다. 그래서 이름을 박지 않습니다.
실제 실행 도구·권한을 확인하고, 원고 검토만 요청받았으면 추적 파일도 수정하지 않습니다.

## 구성

**작성하십시오** — 장 구성, 각 장이 무엇을 다루는지, 장 사이 연결 논리.

## 읽기 전용 원본

**작성하십시오** — 이 논문의 원고 원본·실험 원자료·선행 게재본이 어디 있는지.
읽기·텍스트 추출만 하고 파일을 만들거나 고치거나 옮기지 않습니다.
버전이 여럿이면 파일명 버전이 가장 높은 것을 쓰고, `~$` 소유자 파일은 무시합니다.

| 위치 | 내용 | 취급 |
|---|---|---|
| (경로) | (무엇) | 읽기 전용 |

## 이 원고의 문장 규약

**작성하십시오** — 이 원고에만 적용되는 사용자 지시. 예: 세미콜론 금지, 고정 용어.
공통 문체 규약은 플러그인 `references/style-guide.md` 에 있으므로 여기 중복해 적지 않습니다.

## 도메인 근거 한계

**작성하십시오** — 이 원고에서 주장할 수 없는 것, 인용하면 안 되는 출처,
계의 차이로 그대로 옮길 수 없는 결론.
""".format(name=name, kind_ko=kind_ko, src=cfg['manuscript']['source_dir'], mk=mk, **N)


AGENTS_MD = """# 원고 프로젝트 — Codex 진입 안내

이 프로젝트의 공통 규칙 원본은 같은 폴더의 `CLAUDE.md`입니다.
작업을 시작할 때 실제 파일을 읽고 프로젝트 정체·파일 지도·읽기 전용 경계를 확인합니다.
공통 원고 규칙을 이 파일에 복사하지 않습니다.

1. 현재 호스트에 적용되는 지침 우선순위와 사용자의 최신 지시를 따릅니다.
2. `manuscript` 스킬로 `.manuscript/project.json`의 마커를 확인합니다.
3. `procedure`가 있으면 프로젝트 루트 기준으로 해석해 해당 문서를 직접 읽습니다.
   Claude 로컬 스킬 경로여도 Codex에 등록돼 있다고 가정하지 않습니다.
4. 문장을 쓰거나 고치기 전과 원고·답변서를 내기 전에 `manuscript-workflow`의 관련 참조 문서를 읽습니다.
5. 현재 제공되는 도구로 작업하며, 검토 요청은 읽기 전용으로 진행합니다.
   승인된 변경은 지정된 원본에만 적용하고 저장 뒤 다시 읽어 검증합니다.
"""


def main():
    ap = argparse.ArgumentParser(description='새 원고 프로젝트를 만듭니다.')
    ap.add_argument('dir')
    ap.add_argument('--name', required=True)
    ap.add_argument('--kind', default='journal', choices=['journal', 'dissertation'])
    ap.add_argument('--source-dir', default=DEFAULTS['manuscript']['source_dir'])
    ap.add_argument('--chapters', nargs='*')
    ap.add_argument('--chapter-count', type=int, default=2)
    ap.add_argument('--references', default='references.md')
    ap.add_argument('--build-script', default='')
    ap.add_argument('--triggers', default='')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()

    root = os.path.abspath(a.dir)
    files = a.chapters or ['ch%d.md' % i for i in range(1, a.chapter_count + 1)]
    triggers = [t.strip() for t in a.triggers.split(',') if t.strip()] or DEFAULT_TRIGGERS
    if '지금' not in triggers:
        triggers.insert(0, '지금')

    tools_dir = DEFAULTS['tools_dir']
    cfg = {
        'project': a.name,
        'kind': a.kind,
        'tools_dir': tools_dir,
        'manuscript': {
            'source_dir': a.source_dir,
            'chapters': [{'n': i + 1, 'file': f} for i, f in enumerate(files)],
            'references': a.references,
            'figure_dir': 'fig_src',
        },
        'tracker': {
            **{k: DEFAULTS['tracker'][k] for k in ('index', 'pending', 'record_index', 'literature', 'proposals',
                                                    'records_dir', 'archive')},
            'record_prefix': 'E',
            'movable_prefixes': ['A', 'B', 'C', 'D'],
            'index_size_limit_kb': 40,
            'triggers': triggers,
            'section_markers': [],
            'record_index_exclude': [],
        },
    }
    if a.build_script:
        cfg['manuscript']['build_script'] = a.build_script

    markers = [N['index'], a.source_dir + '/' + (a.build_script or files[0])]
    cfg['markers'] = markers

    made, skipped = [], []

    # 관리 파일(managed_files.json 의 도구 · 훅)을 그 목록대로 복사합니다.
    # 훅의 등록은 .claude/settings.json 입니다.
    for item in MANAGED:
        src = os.path.join(HERE, *item['src'].split('/'))
        if not os.path.isfile(src):
            sys.exit('관리 파일 원본이 없습니다: %s' % src)
        dst = os.path.join(root, *item['dst'].replace('{tools_dir}', tools_dir).split('/'))
        if os.path.exists(dst) and not a.force:
            skipped.append(dst)
            continue
        if not os.path.isdir(os.path.dirname(dst)):
            os.makedirs(os.path.dirname(dst))
        shutil.copy2(src, dst)
        made.append(dst)
    settings_path = os.path.join(root, '.claude', 'settings.json')
    if SETTINGS_JSON:
        w(settings_path, SETTINGS_JSON, a.force, made, skipped)
        if os.path.isfile(settings_path) and 'guard_write.py' not in io.open(settings_path, encoding='utf-8').read():
            print('  ! .claude/settings.json 이 이미 있는데 guard_write 훅이 없습니다 — '
                  'hooks/settings.example.json 의 hooks 블록을 합쳐 넣으십시오.')

    w(os.path.join(root, '.manuscript', 'project.json'),
      json.dumps(cfg, ensure_ascii=False, indent=2) + '\n', a.force, made, skipped)
    at = lambda rel: os.path.join(root, *rel.split('/'))      # noqa: E731
    w(at(N['index']), tracker_index(a.name, triggers), a.force, made, skipped)
    w(at(N['pending']), tracker_pending(), a.force, made, skipped)
    w(at(N['literature']), LITERATURE, a.force, made, skipped)
    w(at(N['proposals']), PROPOSALS, a.force, made, skipped)
    w(at(N['records_dir'] + '/README.md'), RECORDS_README, a.force, made, skipped)
    w(at(N['archive']), ARCHIVE, a.force, made, skipped)
    w(os.path.join(root, 'CLAUDE.md'), claude_md(a.name, a.kind, cfg, markers), a.force, made, skipped)
    w(os.path.join(root, 'AGENTS.md'), AGENTS_MD, a.force, made, skipped)

    for i, f in enumerate(files, 1):
        w(os.path.join(root, a.source_dir, f),
          '@H1 Chapter %d\n\n**작성하십시오.**\n' % i, a.force, made, skipped)
    w(os.path.join(root, a.source_dir, a.references),
      '@H1 References\n\n@REF 1. Author, A. Title of the article. Abbrev. J. 1, 1-10 (2026).\n',
      a.force, made, skipped)

    # 완료 기록 색인은 도구가 만듭니다 — 형식의 정본이 거기 있기 때문입니다.
    # 정리 도구가 색인 파일의 존재를 전제로 하므로 초기화 시점에 한 번 돌려 둡니다.
    idx = at(N['record_index'])
    if not os.path.exists(idx) or a.force:
        import subprocess
        r = subprocess.call([sys.executable, os.path.join(root, tools_dir, 'index_records.py')],
                            cwd=root)
        if r == 0 and os.path.exists(idx):
            made.append(idx)
        else:
            print('  ! 색인 생성에 실패했습니다. %s/index_records.py 를 직접 돌려 보십시오.' % tools_dir)

    print('프로젝트  %s  (%s)' % (a.name, a.kind))
    print('위치      %s' % root)
    print('만든 파일 %d개' % len(made))
    for p in made:
        print('   + %s' % os.path.relpath(p, root))
    if skipped:
        print('건너뜀    %d개 (이미 있음. 덮어쓰려면 --force)' % len(skipped))
        for p in skipped:
            print('   . %s' % os.path.relpath(p, root))
    print('')
    py = sys.executable or 'python'
    print('다음 —')
    print('   "%s" -X utf8 %s/check_numbers.py' % (py, tools_dir))
    print('   "%s" -X utf8 %s/tidy_tracker.py' % (py, tools_dir))


if __name__ == '__main__':
    main()
