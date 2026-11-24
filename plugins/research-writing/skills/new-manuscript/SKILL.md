---
name: new-manuscript
description: 새 논문·원고 프로젝트를 만듭니다. 도구(번호 점검·미결 항목 정리·완료 기록 색인·기록 번호 할당·위치 문법·문법 점검 기준), 기존 프로젝트의 도구를 정본에 맞추는 갱신 도구(update_tools.py), 완료 기록 덮어쓰기를 막는 Claude Code 훅, 설정(.manuscript/project.json), 추적 파일 뼈대, 공통 CLAUDE.md 와 Codex용 AGENTS.md 진입 안내를 한 번에 생성합니다. "새 논문 시작", "프로젝트 만들어줘", "논문 폴더 세팅", "새 원고 준비" 같은 요청에 사용합니다. 이미 있는 프로젝트에는 쓰지 않습니다.
---

# 새 원고 프로젝트 만들기

`init_manuscript.py` 가 폴더 하나를 **작업 가능한 상태**로 만듭니다.
사용자가 파일을 손으로 만들 일이 없어야 합니다.

## 먼저 확인합니다

**대상 폴더에 이미 `수정필요_목록.md` 나 `.manuscript/project.json`(구 `.writing/`) 이 있으면 기존 프로젝트입니다.**
초기화하지 말고 그 사실을 알립니다. (스크립트도 이미 있는 파일은 건너뛰지만, 먼저 확인하는 편이 낫습니다.)

## 물어볼 것 — 모르면 묻고, 알면 묻지 않습니다

| 값 | 기본 | 비고 |
|---|---|---|
| 폴더 위치 | — | **반드시 확인합니다.** 형제 프로젝트 옆에 두는 것이 보통입니다 |
| 논문 이름 | — | `--name`. 한글 가능 |
| 종류 | `journal` | 학위논문이면 `--kind dissertation` |
| 장 구성 | `ch1.md` `ch2.md` | `--chapters intro.md methods.md results.md` 또는 `--chapter-count 4` |
| 원고 폴더 | `manuscript` | 학위논문 관례를 따르려면 `--source-dir 초안_소스` |
| 참고문헌 | `references.md` | `--references bib.md` |
| 빌드 스크립트 | 없음 | 학교 서식으로 빌드한다면 `--build-script build_tpl.py`. 스크립트를 만들 때는 [build-technical.md](../manuscript-workflow/references/build-technical.md) 를 따릅니다 |

**대화를 길게 끌지 않습니다.** 사용자가 "ENIG 후속 연구 새로 시작하자" 정도만 말해도
폴더 위치와 장 구성만 확인하고 나머지는 기본값으로 진행합니다.

## 실행

```text
python -X utf8 "<이 스킬 폴더>/init_manuscript.py" "<대상폴더>" --name "논문 이름" --kind journal --source-dir manuscript --chapters intro.md methods.md results.md --references bib.md
```

`<이 스킬 폴더>`는 **현재 읽은 `SKILL.md`의 부모 폴더**입니다. 그 안의 `init_manuscript.py`와
`tools/`가 실제로 있는지 확인합니다. Claude·Codex의 설치 위치를 추측하거나 다른 버전을 고르지 않습니다.
`python`은 현재 환경에서 확인한 Python 3 실행기를 사용합니다
([실행 환경 확인](../manuscript-workflow/references/environment.md)).

**이미 있는 파일은 건너뜁니다.** 두 번 돌려도 기존 내용을 보존합니다. `--force`는 덮어쓰기
옵션이므로 사용자가 기존 파일의 교체를 명시적으로 요청한 경우에만 사용합니다.

## 만들어지는 것

```
<프로젝트>/
  CLAUDE.md                  공통 정체성 블록 + 파일 지도. 구성·도메인 한계는 비워 둡니다
  AGENTS.md                  Codex 진입 안내. CLAUDE.md와 공통 절차를 읽도록 연결합니다
  .manuscript/project.json   챕터·파일명·트리거. 도구가 읽습니다
  .claude/settings.json      Pre · PostToolUse 훅 등록(Edit · Write · Bash) — 완료기록 덮어쓰기 거부 · 새 미결 ID 손 등록 거부 · 동기화 가드 · 쓰기 후 스냅샷
  .claude/hooks/guard_write.py  그 훅의 본체 (hooks/ 에서 복사). 플러그인 설치본의 hooks/hooks.json 도 같은 본체를 등록합니다
  도구/                       _config.py · _위치.py · _동기화.py · 번호점검.py · 수정필요_정리.py · 완료기록_색인.py · 완료기록_새항목.py · 미결_새항목.py · 동기화_점검.py · 문법기준.py
  수정필요_목록.md             색인 (자동 생성 구간의 마커 포함)
  수정필요_대기.md             미결 항목 표 — 기본 A·B·C·D(글자는 프로젝트가 정함)
  수정필요_색인.md             완료 기록 색인 (빈 상태)
  수정필요_문헌.md             F·G 표
  수정필요_제안.md             H 표
  완료기록/                   README.md (형식 규약) · 이관_DB.md
  <원고폴더>/                 챕터 md 뼈대 + 참고문헌
```

## 만든 뒤 반드시 합니다

**1) 도구가 도는지 확인합니다.**

```text
python -X utf8 도구/번호점검.py
python -X utf8 도구/수정필요_정리.py
python -X utf8 도구/동기화_점검.py
```

셋째는 공용 파일 동기화 점검입니다 — 여러 컴퓨터가 클라우드 동기화 폴더에서 같은 프로젝트를 쓸 때의 안전장치
(규약은 [tracker-workflow.md](../manuscript-workflow/references/tracker-workflow.md) 「동기화」). 세션 시작마다 돌립니다.

새 프로젝트에서는 경고가 나오는 것이 정상입니다 — 완료 기록 0건,
미인용 문헌(뼈대의 예시 항목). `수정필요_정리.py`의 종료 코드 `1`은 진단 경고이며, 위의 빈
기록 경고인지 실제 내용을 확인합니다. 누락 파일·실행 오류를 같은 경고로 간주하지 않습니다.
미결 항목 0건은 경고가 아니라 안내입니다 — 표 구조가 정상이면 목록의 표를 빈 상태로 만듭니다.

**2) `CLAUDE.md` 의 빈 절 둘을 채웁니다.**

`## 구성` 과 `## 도메인 근거 한계` 가 `**작성하십시오**` 로 남아 있습니다.
사용자에게 물어 채우거나, 지금 채울 수 없으면 미결 항목으로 등록합니다.

**3) 프로젝트 전용 스킬이 필요한지 판단합니다.**

빌드 절차나 원본 자료 위치처럼 그 논문에만 있는 절차가 많으면
프로젝트 안의 절차 문서로 두고 `.manuscript/project.json`의 `procedure`에 상대 경로를 적습니다.
기존 `.claude/skills/<이름>/SKILL.md`를 그대로 가리켜도 양쪽에서 파일을 직접 읽을 수 있습니다.
앱에서 직접 호출하는 로컬 스킬 등록이 필요하면 해당 앱이 지원하는 프로젝트 등록 방식만 더하고,
**본문은 하나로 유지합니다.** 전역 플러그인에는 넣지 않습니다 — 다른 논문 폴더에서도 발동할 수 있습니다.

**4) 형제 프로젝트와의 경계를 확인합니다.**

새 프로젝트가 기존 프로젝트와 같은 데이터를 다루면, 새 프로젝트의 정체성 블록에 자료 사용
범위와 다른 원고의 읽기 전용 경계를 적습니다. 형제 프로젝트의 지침도 변경할 필요가 있으면
그 파일과 범위에 대한 사용자 지시를 확인합니다. 새 프로젝트 생성 권한으로 형제 문서를 고치지 않습니다.

## 기존 프로젝트의 도구를 정본에 맞출 때 — `update_tools.py`

초기화는 새 프로젝트에만 씁니다. 이미 있는 프로젝트의 `도구/` · 훅이 정본과 다르면(플러그인을 갱신한 뒤) 같은 폴더의
`update_tools.py` 로 맞춥니다. 원본은 **이 파일이 든 플러그인 사본**이고, 관리 대상은 `managed_files.json` 입니다.

```text
python -X utf8 "<이 스킬 폴더>/update_tools.py" "<프로젝트>"            # 판정만 — 같음 · 옛 정본 판 · 로컬 수정 · 없음
python -X utf8 "<이 스킬 폴더>/update_tools.py" "<프로젝트>" --apply    # 옛 정본 판을 바꿈. 로컬 수정판은 --force <파일>, 없는 파일은 --add <파일>
python -X utf8 "<이 스킬 폴더>/update_tools.py" --scan "<상위 폴더>"     # 자매 프로젝트 전체의 상태표
```

설정 파일(`.manuscript/project.json`)은 쓰지 않습니다 — 기본값에 기대는 키를 보고만 하므로, 필요한 값은 사용자에게 보인 뒤 Edit 으로
적습니다. 로컬 수정판을 바꾸기 전 원본은 `.manuscript/도구_백업/<날짜>/` 에 둡니다. 훅 등록이 다르면 `hooks/settings.example.json` 의
`hooks` 블록을 손으로 합칩니다. 배포 전 자매 프로젝트에 무엇이 바뀌는지는 저장소의 `scripts/preview_projects.py` 로 미리 봅니다.

## 공통 규칙

문체·헤지·인용·수정 프로토콜은 [manuscript-workflow](../manuscript-workflow/SKILL.md)를 따릅니다.
`.manuscript/project.json`의 스키마는 [project-config.md](../manuscript-workflow/references/project-config.md)에 있습니다.
