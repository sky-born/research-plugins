# Changelog

플러그인별 배포 이력입니다. 새 판을 배포할 때 그 플러그인 절의 맨 위에 `### <버전> — <날짜>` 와 바뀐 점을 적습니다.
`python scripts/release.py check` 가 올린 버전의 항목이 있는지 검사합니다.
공개 저장소로 옮기기 전의 커밋과 태그는 이 저장소에 없습니다. 아래에 적힌 것이 그 전 이력의 전부입니다.

## research-writing

### 0.13.1 — 2026-11-24

- `update_tools.py` — 새 이름과 옛 이름의 도구 사본이 둘 다 있을 때, 옛 사본이 손으로 고친 것이면 지우지 않고 `--force` 로만
  백업한 뒤 지움(전에는 백업 없이 지웠음)

### 0.13.0 — 2026-11-24

- 관리 도구 아홉의 파일 이름을 영어로 — `_동기화.py` → `_sync.py` · `_위치.py` → `_location.py` · `동기화_점검.py` → `check_sync.py` ·
  `번호점검.py` → `check_numbers.py` · `문법기준.py` → `grammar_baseline.py` · `수정필요_정리.py` → `tidy_tracker.py` ·
  `완료기록_색인.py` → `index_records.py` · `완료기록_새항목.py` → `new_record.py` · `미결_새항목.py` → `new_pending.py`
- 새 프로젝트의 기본 이름을 영어로 — 도구 폴더 `tools/`(새 설정 키 `tools_dir`) · 원고 폴더 `manuscript_src/` · 추적 파일 `tracker_*.md` ·
  기록 폴더 `records/`(이관 `records/archive.md`) · 스냅샷 `archive/tracker_backup/` · 도구 백업 `.manuscript/tools_backup/` ·
  문법 기준 `.manuscript/grammar_baseline.jsonl`(묶음 `grammar_packets/`)
- 0.12 이하가 만든 프로젝트 — 옛 이름(한글)을 설정에 적으면 그대로 돕니다. 적지 않은 채 옛 이름만 있으면 도구는 멈추고 훅은 설정 파일
  말고는 쓰기를 막으며, 둘 다 적을 값을 보입니다. `update_tools.py` 도 같은 값을 보이고 적기 전에는 적용하지 않으며, 적은 뒤 `--apply` 가
  옛 이름의 도구 사본을 새 이름으로 옮깁니다. 문법 기준 파일은 옛 이름만 있으면 그대로 씁니다
- 도구 · 훅 · 초기화에 박혀 있던 이름을 `_config.py` 의 기본값 한 곳에서 읽게 함
- 같은 프로젝트를 여러 컴퓨터가 쓰면 함께 갱신합니다 — 0.12 이하의 훅은 새 이름의 도구 사본을 찾지 못해 미결 번호 손 등록 검사를 건너뜁니다

### 0.12.2 — 2026-11-24

- 공개 저장소 `sky-born/research-plugins` 로 옮김 — README 의 설치 줄과 매니페스트의 저장소 주소를 새 주소로

### 0.12.1 — 2026-11-23

- 플러그인 `README.md` 추가 — 설치 한 줄, 필요한 것(Windows 의 훅은 Git Bash 가 있어야 돎), 스킬 · 훅 · 프로젝트 도구 요약
- `plugin.json` 의 키워드에 `scaffold` 추가 (마켓플레이스 항목에만 있던 것)

## paper-index

### 0.11.0 — 2026-11-24

- OA 임시 폴더(`oa_staging`)의 기본값을 `_수신` 에서 `_oa_inbox` 로 — 설정에 `oa_staging` 이 없고 옛 `_수신` 폴더만 있으면 그 폴더를
  그대로 씁니다. 설정에 적어 둔 값은 그대로 따릅니다

### 0.10.2 — 2026-11-24

- 공개 저장소 `sky-born/research-plugins` 로 옮김 — README 의 설치 줄과 매니페스트의 저장소 주소를 새 주소로

### 0.10.1 — 2026-11-23

- 프리셋 `solder-thesis.json` 의 설명을 예시 프리셋으로 고침 (태그 규칙은 그대로)

### 0.10.0 — 2026-11-23

- Scopus 를 부르는 구현을 `lib/scopus.py` 하나로 줄임 — `scopus_search.ps1` 과, 더블클릭용 실행 파일을 만들던 `make_launcher.py` 를 없앰.
  직접 호출이 막힌 환경에서는 키가 설정된 컴퓨터의 터미널에서 같은 `papertool.py scopus` 명령을 실행
- `scopus-merge` 가 실행 파일을 자동으로 치우지 않음. `--keep-launcher` 는 받기만 하고 아무 일도 하지 않음
- `scopus-tidy` 는 0.9 이하 판이 인덱스 폴더에 남긴 실행 파일 정리용으로 남김
- `README.md` 의 옛 이름(`paper-index-tool`)을 고치고 설치 한 줄을 추가

## 저장소 — 플러그인 밖

### 2026-11-24 — macOS 에서 앱에 든 codex · claude 찾기

- `bootstrap.py` 가 macOS 에서도 앱에 든 `codex` 를 찾음 — `/Applications` · `~/Applications` 의 앱 가운데
  `Contents/Resources/codex-cli/bin/codex` 가 든 것(앱 이름은 가리지 않음). 전에는 Windows 위치만 보아 PATH 에 없으면 건너뜀
- `bootstrap.py` · `release.py` 가 맥 데스크톱 앱에 든 `claude` 를 `claude-code/<판>/<해시>/claude.app` 배치에서도 찾음 —
  세션 밖에서 PATH 에 `claude` 가 없으면 찾지 못하던 것. `claude-code/<판>/claude.app` 배치도 계속 찾음

### 2026-11-24 — codex 찾기 · 공개 검사 보강

- `bootstrap.py` 가 `codex` 를 `--codex` → PATH → Codex 데스크톱 앱에 든 실행 파일(Windows) 순으로 찾음 — PATH 에 없어도 됨
- `check_public.py` 가 Git Bash 표기의 사용자 폴더 경로(드라이브 글자 폴더 아래 `Users`)도 찾음

### 2026-11-24 — 배포 전 세션 시험

- `scripts/release.py try <폴더>` 추가 — 작업 클론의 플러그인으로 그 폴더에서 세션을 엶. 플러그인마다 `--plugin-dir` 를 줌
- `check` 가 `SKILL.md` 머리말의 `name` · `description` 을 검사 — `description` 이 없으면 Claude Code 가 그 스킬을 스킬 목록에서 뺌

### 2026-11-24 — 공개 전 검사

- `scripts/check_public.py` 추가 — 올릴 파일 · 경로 · 커밋의 작성자 정보에서 이메일 · 사용자 폴더 경로 · 비밀값과 저장소 밖 금지어 목록의
  낱말을 찾습니다(값은 가려서 보고). `release.py check` 가 돌리고, 걸리면 멈춥니다
- `release.py check` 가 파일 이름이 ASCII 가 아니면 멈춤
- `scripts/tool_hashes.py` 가 `managed_files.json` 의 옛 이름(`old`)의 이력과 기록도 이어받음

### 2026-11-24 — 공개

- 공개 저장소 `sky-born/research-plugins` 로 옮김. 그 전의 커밋과 태그는 옮기지 않음
- 마켓플레이스 등록 이름을 `personal-marketplace` 에서 `research-plugins` 로 바꿈 — 옛 이름으로 등록한 컴퓨터는 옛 등록을 지우고 다시 설치

### 2026-11-23

- 배포 · 설치 스크립트를 Python 으로 옮김 — `scripts/release.py`(`check` · `bump` · `publish`), `bootstrap/bootstrap.py`(`install` · `update` · `status`).
  `release.ps1` · `bootstrap.ps1` · `bootstrap.sh` · `codex.py` 를 없앰
- 설치 스크립트가 플러그인 목록을 `marketplace.json` 에서, 저장소 주소를 `git remote` 에서 읽음. 설정 파일을 직접 고치지 않음
- 마켓플레이스 항목의 표시 필드(설명 · 작성자 · 라이선스 · 키워드)를 `plugin.json` 에서 생성 — 두 곳에 따로 적다가 어긋났던 것을 맞춤
- `CHANGELOG.md` · `LICENSE` 추가, 커밋 제목은 72자 이내로
- `README.md` 를 영어로 쓰고 한국어본을 `README.ko.md` 로 둠. `check` 가 두 파일의 구조가 같은지 검사
- GitHub Actions(`.github/workflows/check.yml`)로 push 마다 Windows · macOS · Linux 에서 `release.py check` 실행
- 컴퓨터별 환경 기록을 저장소 밖으로 옮김 — `CLAUDE.md` §3 에는 확인하는 방법과 어디서나 지킬 것만 남김
- `tool_hashes.py` 가 이 저장소의 이력에 없는 판의 해시를 이어받음 — 이력 없이 새로 시작한 저장소에서도 `check` 가 통과
- `bootstrap.py` 가 마켓플레이스가 다른 주소로 등록돼 있으면 갱신하지 않고 멈춤
- 시험 파일과 README 에서 개인 경로와 프로젝트 이름을 뺌. README 의 비공개 관련 문장을 공개 뒤에도 맞는 표현으로 고침
