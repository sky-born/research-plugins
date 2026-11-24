# research-writing

학술 논문 · 학위논문 집필의 공통 작업 규칙과, 원고 프로젝트를 만들고 지키는 도구입니다.
어느 논문에도 통하는 규칙만 담습니다. 특정 논문의 사실 · 경로 · 수치는 그 프로젝트의 문서에 둡니다.

## 설치

Claude Code 2.1.275 이상에서는 이 한 줄로 마켓플레이스 등록과 설치가 함께 됩니다.

```
/plugin install research-writing --marketplace sky-born/research-plugins
```

그 아래 판과 Codex, 여러 컴퓨터의 갱신은 저장소 루트의 [README](../../README.md)를 따릅니다.
Claude Code · Codex 가 같은 `skills/` 원본을 사용합니다.

## 필요한 것

- Python 3 (표준 라이브러리만 씁니다). Windows 는 `python`, macOS · Linux 는 `python3` 로 부릅니다.
- **Windows 에서는 Git for Windows(Git Bash).** 훅 명령이 bash 문법이라, Git Bash 가 없으면 훅이 돌지 않습니다.

## 스킬

| 스킬 | 하는 일 |
|---|---|
| `manuscript` | 원고 작업 세션의 진입점. 열린 폴더가 어떤 원고 프로젝트인지 판정하고 그 프로젝트의 절차로 넘깁니다 |
| `manuscript-workflow` | 집필 공통 규칙 — 문체와 금지 표현, 근거 등급별 헤지, 인용 확정, 수정안 제시와 확정 선언, 미결 항목 추적, 도판 기술 |
| `new-manuscript` | 새 원고 프로젝트를 도구 · 설정(`.manuscript/project.json`) · 추적 파일 뼈대까지 한 번에 만들고, 기존 프로젝트의 도구 사본을 정본에 맞춥니다 |

세부 규약은 `skills/manuscript-workflow/references/` 에 주제별로 있습니다
(`style-guide` · `evidence-hedging` · `citation-rules` · `revision-protocol` · `tracker-workflow` · `figure-technical` · `build-technical` · `project-config` · `environment`).

## 훅

`hooks/hooks.json` 이 Edit · Write · Bash · PowerShell 앞뒤로 `skills/new-manuscript/hooks/guard_write.py` 를 부릅니다.
원고 프로젝트(`.manuscript/project.json` 이 있는 폴더) 안에서만 일하고, 다른 폴더에서는 바로 끝납니다.

- 이미 있는 완료 기록과 생성 색인을 덮어쓰는 쓰기를 거부합니다.
- 번호 도구를 거치지 않은 새 미결 ID 등록을 거부합니다.
- 공용 파일을 쓰기 전에 동기화 상태를 확인하고, 쓴 뒤 스냅샷을 남깁니다.
- 추적 표에 깨진 행이 남으면 그 턴에 알립니다(막지 않습니다).

규약은 `skills/manuscript-workflow/references/tracker-workflow.md` 의 「동기화」에 있습니다.

## 프로젝트에 들어가는 도구

`new-manuscript` 가 프로젝트의 `도구/` 폴더에 사본을 넣습니다. 목록의 원본은 `skills/new-manuscript/managed_files.json` 이고,
사본이 정본과 같은 판인지는 `update_tools.py` 가 `tool_hashes.json` 으로 판정합니다.

| 도구 | 하는 일 |
|---|---|
| `번호점검.py` | Figure · Table · 참고문헌 번호의 전수 점검 (진단만) |
| `수정필요_정리.py` | 미결 항목 목록 파일의 정리 · 검사 |
| `미결_새항목.py` · `완료기록_새항목.py` | 새 미결 항목 · 완료 기록을 다음 번호로 등록 |
| `완료기록_색인.py` | 완료 기록에서 색인 생성 |
| `문법기준.py` | 제출 전 문법 점검의 기준 — 점검 뒤 바뀐 문단만 골라냄 |
| `동기화_점검.py` | 공용 파일의 동기화 점검 · 스냅샷 · 복구 |
