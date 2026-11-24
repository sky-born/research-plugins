# 원고 프로젝트 설정 — `.manuscript/project.json`

로더는 옛 경로 `.writing/` 도 읽지만 새 프로젝트는 `.manuscript/` 로 만듭니다.

도구가 프로젝트에 적응하는 데 쓰는 값을 한 파일에 모읍니다.
**챕터 개수, 파일 이름, 폴더 구조, 트리거 값이 프로젝트마다 다르기 때문**입니다.

`templates/project.example.json` 을 복사해 값만 바꾸면 됩니다.
`new-manuscript/tools/_config.py`가 이 파일을 읽는 로더이며 초기화 때 프로젝트의 도구 폴더(`tools_dir`)로 복사됩니다.

## 무엇이 들어가나

| 키 | 쓰는 도구 | 없으면 |
|---|---|---|
| `tools_dir` | 훅 · `update_tools` · 도구의 안내 문구 | `tools`. 관리 도구를 두는 폴더(루트 바로 아래) |
| `manuscript.source_dir` | 번호 점검, 빌드 | `manuscript_src`, 없으면 프로젝트 루트 |
| `manuscript.chapters` | 번호 점검, 빌드 | `ch1.md` ~ `ch4.md` |
| `manuscript.references` | 번호 점검 | `references.md` |
| `manuscript.build_script` | 번호 점검 | `build_tpl.py`. **없는 프로젝트면 그 점검을 건너뜁니다** |
| `tracker.*` | 미결 항목 정리·색인 | `tracker_index.md` · `tracker_pending.md` · `tracker_records_index.md` · `tracker_literature.md` · `tracker_proposals.md` · `records/` · `records/archive.md`. 다섯 파일(`index` · `pending` · `record_index` · `literature` · `proposals`)은 루트 기준 경로라 하위 폴더(`tracking/tracker_index.md`)도 됩니다 — 도구 · 훅은 이 값만 보고, 옮기면 `markers` 도 함께 바꿉니다 |
| `tracker.triggers` | 정리 도구 | 공통 다섯 — `지금` · `해당 절 작업 시` · `사용자 판단` · `자료 확보 후` · `최종 제출 직전`. 일정에 걸린 값은 프로젝트가 더합니다. **목록에 없는 값을 쓰면 경고합니다** |
| `tracker.movable_prefixes` | 정리 도구 · 동기화 점검(S7) | `["A","B","C","D"]`. 대기 파일의 절 글자 — 절 제목 `## X.` 와 행 ID 의 머리글자. 글자를 줄여도 옛 ID 의 글자는 목록에 남깁니다(`tracker-workflow.md` 「미결 표의 분류 글자」) |
| `tracker.section_markers` | 위치 문법(정리 · 색인 · 새 기록 검사) | 빈 목록. 프로젝트만의 절 표기(정규식 목록) |
| `tracker.record_index_exclude` | 완료 색인 | 빈 목록. 완료 색인 §1 에서 뺄 파일 · 폴더의 글롭(루트 기준, 폴더는 끝 `/`) |
| `tracker.checkpoint` | 동기화 점검 | 없음. 인수인계 파일(루트 기준) — 공용 파일로 스냅샷하되, 갈아쓰는 문서라 손실 보고에서 뺍니다 |
| `sync.*` | 동기화 점검 · 훅 · 정리 · 색인 · 새항목 · `update_tools` | 전부 기본값으로 돕니다. `shared_extra`(공용 파일 추가 글롭) · `snapshot_dir`(`archive/tracker_backup`) · `conflict_patterns` · `exclude` · `stale_days`(2) · `snapshot_days`(30) · `snapshot_days_others`(90) · `snapshot_min`(10) · `snapshot_max`(20) · `snapshot_max_local`(100) · `ack_hours`(4) · `known_gaps` · `rewrite_ok` · `survival_pct`(70). 뜻은 `tracker-workflow.md` 「동기화」 |
| `manuscript.output_pattern` | 완료 색인, 초기화 | 없음. 빌드 산출물 이름 글롭(`원고_v*.docx`) — 완료 색인에서 뺍니다 |
| `grammar.*` | grammar_baseline | 범위는 `manuscript.source_dir` 의 `chapters`(참고문헌 파일 제외). `sources`(기본 범위에 **더하는** 원본) · `exclude_prefixes`(`["@NOTE"]`) · `avoid_lists`(없음). 아래 「`grammar`」 |
| `markers` | `manuscript` 진입 스킬과 프로젝트 로컬 스킬의 가드 | — |
| `procedure` | `manuscript` 진입 스킬 | **그 단계를 건너뜁니다** |

**설정 파일이 없어도 도구는 돕니다.** 기본값이 들어갑니다.

**0.12 이하가 만든 프로젝트는 한글 기본 이름(`도구/` · `수정필요_*.md` · `완료기록/` 등 — 값은 `_config.LEGACY_DEFAULTS`)을 씁니다.**
그 이름을 설정에 적어 두면 그대로 돕니다. 적지 않은 채 옛 이름만 디스크에 있으면 도구는 멈추고 훅은 설정 파일 말고는 쓰기를 막으며,
둘 다 설정에 더할 값을 보입니다 — `update_tools.py` 도 같은 값을 보이고 적기 전에는 적용하지 않습니다.

## `grammar` — 제출 전 문법 점검의 범위

`tools/grammar_baseline.py` 가 읽습니다(규약은 `revision-protocol.md` 「제출 전 문법 점검」). **키가 없으면 범위는 원고 폴더의 장 파일입니다** —
초록 · 빌드 스크립트 안의 글 · 목차용 짧은 제목처럼 장 파일 밖에 있는 영문만 `sources` 로 더합니다.

| 키 | 값 |
|---|---|
| `sources` | 원본 목록. 항목마다 `file`(**루트 기준** 경로) · `kind` · (lines 면) `regions` |
| `exclude_prefixes` | md 블록에서 뺄 머리글자. 기본 `["@NOTE"]` |
| `avoid_lists` | 피할 표현 목록(루트 기준 경로 목록). 표 첫 칸의 첫 코드 스팬이 바뀐 단위에 들어 있으면 표시합니다(대소문자 무시) |

| `kind` | 단위 |
|---|---|
| `md`(기본) | 빈 줄로 나뉜 블록 하나. `exclude_prefixes` 로 시작하는 블록은 뺍니다 — 메모가 문단에 빈 줄 없이 붙어 있으면 문단과 한 단위입니다 |
| `lines` | `regions` 의 구간 안에서 비어 있지 않은 줄 하나. 구간은 `start` 정규식에 맞는 줄부터, 그 다음 줄부터 찾은 `end` 정규식에 맞는 줄 **앞**까지입니다(끝 줄은 넣지 않음). 맞는 곳이 여럿이면 모두 |
| `json-values` | 문자열 값 하나(키는 아님). `_` 로 시작하는 키의 값은 그 아래 모두 설명 칸이라 뺍니다 |

지문은 정규화(NFC · 줄끝 LF · 앞뒤 공백 제거)한 글의 SHA-256 이고 파일 · 위치를 넣지 않습니다 — 순서만 바뀐 단위는 다시 나오지 않습니다.
**모르는 키 · 모르는 `kind` · 찾지 못한 구간 표지 · 없는 파일 · 0 단위는 경고합니다.** `_` 로 시작하는 키는 주석으로 봅니다.
`kind` 를 적지 않은 `.md` 밖의 파일은 md 로 읽고 경고합니다.

## `markers` 와 `procedure` — 진입 스킬이 쓰는 두 값

`manuscript` 스킬은 어느 폴더에서든 불릴 수 있어 **가드가 먼저입니다.**

- **`markers`** — 이 파일들이 **모두 실재해야** 초기화된 프로젝트로 봅니다. 하나라도 없으면
  기준 루트와 누락을 먼저 확인하며, 기존 프로젝트에 초기화를 자동 실행하지 않습니다.
  그 프로젝트에만 있는 파일을 고릅니다.
- **`procedure`** — 그 논문의 상세 절차 문서. **프로젝트 루트 기준 상대 경로**입니다.
  프로젝트 로컬 스킬이면 `.claude/skills/<이름>/SKILL.md` 등을 그대로 가리키거나, 공통 절차
  문서의 경로를 적습니다. **Claude·Codex 모두 그 파일을 직접 읽으며** 같은 이름의 스킬이
  자동 등록됐다고 가정하지 않습니다. **키가 없으면 적용되는 프로젝트 지침과 추적 색인으로
  진행합니다.** 명시한 경로의 파일이 없으면 누락을 보고하고 필수 보호 절차를 추측하지 않습니다.

`AGENTS.md`가 다른 원고 소스 폴더를 기준 루트로 지정하는 연결 프로젝트라면, 먼저 그 지침의
상대 경로와 마커를 확인하고 대상 루트의 이 설정을 읽습니다. 도구 실행 위치도 대상 루트입니다.

**논문별 절차를 플러그인에 넣지 않습니다.** 파일 구조와 제약이 논문마다 다르므로
진입 로직만 공통이고, 내용은 각 프로젝트가 갖습니다.

## 이 파일에 넣지 않는 것 — 경계

**`project.json` 은 도구가 읽는 값만 담습니다.** 도구가 쓰지 않는 값을 넣으면 두 곳에서
관리해야 하는 죽은 키가 됩니다. 아래는 프로젝트마다 다르지만 **여기 두지 않습니다.**

| 프로젝트마다 다른 것 | 어디에 두나 |
|---|---|
| 서식 원본(학교 배포본·저널 템플릿)과 그것을 찾는 규칙 | 빌드 스크립트와 그 프로젝트의 `CLAUDE.md` |
| 도판 원본 폴더와 도판–파일 대응표 | 그 프로젝트의 `CLAUDE.md`, 대응표는 별도 `INDEX.md` |
| 실험 원자료·저널 원고 원본의 읽기 전용 경로 | 그 프로젝트의 `CLAUDE.md`, 여러 프로젝트가 공유하면 상위 `CLAUDE.md` |
| 도메인 근거 한계, 인용 금지 목록 | 그 프로젝트의 `CLAUDE.md` — **플러그인이나 상위로 올리지 않습니다** |
| 세션 진행 절차(최신 산출물 감지·재빌드·검증) | 그 프로젝트의 절차 문서(`procedure`) |

**추적 체계를 쓰지 않는 원고 프로젝트에는 이 파일이 없어도 됩니다.** `manuscript` 진입 스킬이
그 폴더의 프로젝트 지침(`CLAUDE.md`·`AGENTS.md`)에 명시된 정체·파일 지도로 판정하고 초기화를 권하지 않습니다.

## 트리거는 프로젝트마다 다릅니다

학위논문은 `심사위원 확정 후` · `졸업 시기 확정 후` 가 필요하고, 저널 원고는
`리뷰어 응답 후` 같은 값이 필요합니다. **자유 문자열로 두면 표가 만들어지지 않으므로**
프로젝트마다 목록을 정해 여기 적습니다.

## 새 프로젝트는 `new-manuscript` 스킬이 만듭니다

**손으로 만들지 않습니다.** `new-manuscript` 스킬의 `init_manuscript.py` 가 관리 파일(도구 아홉 · 훅)·설정·
추적 파일 뼈대·공통 원본 `CLAUDE.md`·얇은 Codex 진입 안내 `AGENTS.md`를 한 번에 생성합니다.

```bash
python <플러그인>/skills/new-manuscript/init_manuscript.py <대상폴더> --name "논문 이름"     --chapters intro.md results.md --references bib.md
```

**이미 있는 파일은 건너뜁니다.** 두 번 돌려도 안전합니다.

도구의 정본은 `skills/new-manuscript/tools/` 에 있고, 초기화 때 각 프로젝트의 도구 폴더로
**복사**됩니다. 프로젝트가 독립적으로 돌고, 필요하면 그 프로젝트에서만 손볼 수 있습니다.
관리 대상 목록의 원본은 `new-manuscript/managed_files.json` 하나입니다. **정본이 바뀌면 각 프로젝트 사본은
`new-manuscript/update_tools.py` 로 맞춥니다** — `--check`(판정) · `--apply`(교체 — 로컬 수정판은 `--force`, 없는 파일은 `--add`) ·
`--scan <폴더>`(자매 프로젝트 전체). 원본은 그 도구가 든 플러그인 사본이고, 정본 이력의 해시(`tool_hashes.json`)로 옛 판을 알아봅니다.
0.12 이하의 한글 이름 사본(`managed_files.json` 의 `old`)은 `--apply` 가 새 이름으로 옮깁니다.

```
tools/_config.py            설정 로더 · 공유 정의(도판 표지 · 상태 어휘) — 그대로 씁니다
tools/_location.py          「파일 · 절」 위치 문법 — 색인 · 위치 표 · 포커스 · 새 기록 검사가 함께 씁니다
tools/check_numbers.py      Figure·Table·참고문헌 번호 전수 대조
tools/tidy_tracker.py       미결 항목 이관·색인 생성
tools/index_records.py      완료 기록 역색인 생성 (`--검사` 로 옛 기록의 확인 못 한 이름)
tools/new_record.py         완료 기록 번호 할당 · 대상 검사 · 색인 재생성(`--no-index` 로 끔)
tools/new_pending.py        새 미결 항목 번호 할당 — 대기 글자 표 · 제안 표(쓰기 잠금 안에서 다시 읽어 정함)
tools/_sync.py              공용 파일 동기화 안전장치 본체 — 검사 · 스냅샷 · 쓰기 잠금 · `replace_once`
tools/check_sync.py         세션 시작 점검 · `--ack` · `--restore` · `--snapshots`
tools/grammar_baseline.py   제출 전 문법 점검의 기준 — 바뀐 단위만 골라냄(changed) · 본 단위를 찍음(clean · resolve) · 후보 원문 대조(verify)
```
