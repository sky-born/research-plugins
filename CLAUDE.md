# 작업 규칙 — research-plugins

Claude Code·Codex 공통 스킬 마켓플레이스의 **소스 저장소**입니다.
이 폴더를 열고 작업할 때 지킬 것을 적습니다. 설치·사용법은 `README.md` 에 있습니다.

| 항목 | 값 |
|---|---|
| 저장소 | `sky-born/research-plugins` (GitHub, 공개) |
| 마켓플레이스 이름 | `research-plugins` |
| 담긴 플러그인 | `.claude-plugin/marketplace.json` 의 `plugins` 가 목록의 원본입니다 |
| 배포 | `python scripts/release.py` (`check` · `try` · `bump` · `publish`) |
| 설치 · 갱신 | `python bootstrap/bootstrap.py` (`install` · `update` · `status`) |

**원고 내용을 이 저장소에 넣지 않습니다.** 여기 들어가는 것은 어느 논문에도 통하는 공통 규칙과
도구뿐입니다. 특정 논문의 사실·경로·수치는 그 프로젝트의 `CLAUDE.md` 로 갑니다.

## 두 앱의 공통 원본

- `plugins/<이름>/skills/`가 Claude Code·Codex의 공통 원본입니다. 앱별 본문 사본을 만들지 않습니다.
- 프로젝트 규칙은 현재 앱의 `AGENTS.md`/`CLAUDE.md`와 명시된 절차 파일을 실제로 읽습니다.
  다른 앱 전용 문서가 자동 로딩됐다고 가정하지 않습니다.
- `.claude-plugin/plugin.json`의 이름·버전·설명을 원본으로 삼습니다.
  `python scripts/sync_codex_manifests.py`가 `.codex-plugin/plugin.json`과
  `.agents/plugins/marketplace.json`을 생성합니다. 생성물은 손으로 수정하지 않습니다.
- `python scripts/release.py check` 한 번이 파일 이름(ASCII) · 공개 검사(개인 정보) · 공통 구성 · 해시 목록 · Claude 매니페스트 ·
  버전 규칙 · 시험을 모두 검증합니다. 원격 fetch도 수행하고, 아무것도 바꾸지 않습니다.
- 설치·갱신은 두 앱 모두 `python bootstrap/bootstrap.py install` / `update`입니다.
  Codex의 배포 전 작업 클론 시험에만 `--app codex --local`을 사용합니다. 설치된 캐시를 직접 고치지 않습니다.
- 사용자 승인·쓰기 범위·원본 보호는 앱별 등록 정보로 완화하지 않습니다.
  실제 파일 접근과 실행기·도구 유무를 확인하고 해당 환경에 맞는 실행 방식만 선택합니다.

---

## 0. 클론이 셋입니다 — 어느 것을 열었는지부터 확인합니다

**고칠 수 있는 것은 작업 클론 하나뿐입니다.** 나머지 둘은 Claude Code 가 관리하며,
거기 고친 것은 다음 갱신에 조용히 사라집니다.

| 클론 | 무엇 | 취급 |
|---|---|---|
| **작업 클론** | `git clone` 으로 내가 만든 것 | **여기서만 고칩니다** |
| 마켓플레이스 캐시 | `claude plugin marketplace add` 가 만든 clone | 읽기만. `marketplace update` 가 덮어씁니다 |
| 플러그인 설치본 | `claude plugin install` 이 푼 버전별 사본 | 읽기만. 설치된 버전을 확인할 때 씁니다 |

지금 연 폴더가 어느 것인지는 위치로 판별합니다. `.claude\plugins\` 아래면 작업 클론이 아닙니다.

```bash
git rev-parse --show-toplevel     # 이 경로가 .claude/plugins/ 아래면 손대지 마십시오
```

작업 클론의 위치는 컴퓨터마다 다릅니다 — 저장소 밖 환경 기록(§3)을 봅니다. 없으면 새로 만듭니다.

```powershell
git clone https://github.com/sky-born/research-plugins "$env:USERPROFILE\dev\research-plugins"
```

**클라우드 동기화 폴더(구글드라이브·OneDrive) 안에 작업 클론을 두지 않습니다.**
동기화가 `.git` 을 반쯤 덮어써 저장소를 깨뜨립니다. 컴퓨터마다 각자 클론하고, 동기화는 GitHub 이 합니다.

**다른 컴퓨터의 작업 클론에 커밋되지 않은 변경이 남아 있을 수 있습니다.**
작업을 시작할 때 `git status` 와 `git log --oneline -1` 을 보고, 원격과 어긋나면 먼저 정리합니다.

---

## 1. 고쳤으면 배포까지가 한 작업입니다

**파일만 고치고 끝내면 아무 컴퓨터에도 반영되지 않습니다.** 자동 갱신이 돌지 않기 때문입니다(§4).
아래 다섯을 한 묶음으로 봅니다.

1. 파일 수정
2. **그 플러그인의 `.claude-plugin/plugin.json` 의 `version` 을 올립니다** —
   `python scripts/release.py bump <플러그인> patch|minor|major` 가 Codex 등록 파일과 해시 목록까지 함께 다시 만듭니다
3. `python scripts/release.py try <폴더>`
4. `python scripts/release.py publish` 로 검증·커밋·push·태그
5. 반영이 필요한 컴퓨터에서 갱신 명령을 칩니다 (§4)

2번이 이 저장소의 유일한 배포 신호입니다. 플러그인이 상대 경로(`./plugins/...`)로 배포되므로
`plugin.json` 의 `version` 값이 곧 배포 버전이고, 이 값이 바뀌어야 다른 컴퓨터가 새 버전으로 봅니다.
파일만 고치고 버전을 그대로 두면 다른 컴퓨터는 옛 버전을 계속 씁니다.
`release.py` 가 이것을 검사하고, 버전이 그대로면 중단합니다.

```text
python scripts/release.py check
python scripts/release.py publish -m "무엇을 고쳤는지 (72자 이내)"
```

**커밋·push 는 사용자 지시가 있을 때만 합니다.** 수정까지 하고 멈춰 보고합니다.

**push 하면 GitHub Actions(`.github/workflows/check.yml`)가 Windows · macOS · Linux 에서 같은 `check` 를 돌립니다.**
러너에는 `claude` 가 없어 `--skip-claude` 로 돌므로, `claude plugin validate` 는 배포하는 컴퓨터에서만 확인됩니다.

**커밋 제목은 72자 이내**로 `<플러그인> v<버전>: 한 줄 요약` 처럼 쓰고, 바뀐 점은 `CHANGELOG.md` 의 그 플러그인 절
맨 위에 `### <버전> — <날짜>` 로 적습니다. `check` 는 올린 버전의 항목이 없으면 중단하고, `publish` 는 제목이 길면 경고합니다.
**경위와 날짜는 문서 본문이 아니라 `CHANGELOG.md` 에 둡니다.**

**README 는 두 파일입니다** — `README.md`(영어)와 `README.ko.md`(한국어). 한쪽을 고치면 다른 쪽도 함께 고칩니다.
`check` 가 두 파일의 제목 구조 · 코드 블록(주석과 `<자리표시>` 는 빼고) · 링크 대상이 같은지 검사합니다.
이 문서 · 스킬 본문 · 플러그인 README 는 한국어로 둡니다.

**스크립트의 도움말(`--help`)에는 필요한 최소한만 담습니다.**

**배포 전 검증** — `python scripts/release.py check` 가 공통 구성 · 해시 목록 · Claude 매니페스트 · 버전 규칙 · 시험
(합성 표본: 저널 · 학위논문 × 옛 · 새 형식의 추적 파일)을 돌립니다. 여기에 들어 있지 않은 것은 §1 의 `try` 와
**`python -X utf8 scripts/preview_projects.py <자매 프로젝트> …`** 입니다
(실제 프로젝트의 추적 파일 **사본**에 새 도구를 돌려 예고한 차이와 같은지 — 원본에는 쓰지 않음. `grammar_baseline.py` 를 고쳤으면 `--grammar` 로
원고 사본에 grammar_baseline 시나리오도 돌림 — 설정에 `grammar` 키가 없는 프로젝트는 `--set grammar=<JSON>`). 관리 파일
(`new-manuscript/managed_files.json` 의 목록)을 `bump` 뒤에 더 고쳤으면 `python -X utf8 scripts/tool_hashes.py` 로 해시 목록을 다시 만들어
함께 커밋합니다 — `check` 가 최신인지 검사합니다. 기존 프로젝트의 사본은 배포 뒤 `new-manuscript/update_tools.py` 로 맞춥니다.

플러그인을 더하거나 없앨 때는 `README.md` 「새 플러그인 추가하기」를 따릅니다 —
`marketplace.json` 의 `plugins` 배열과 `renames` 표입니다. 설치 스크립트는 그 목록을 읽으므로 따로 맞출 곳이 없습니다.

---

## 2. 문서를 쓸 때 — 환경 사실을 본문에 박지 않습니다

**이 저장소의 문서는 여러 컴퓨터에서 읽고 고칩니다.** 지금 앉은 컴퓨터의 경로나 측정값을
본문에 그대로 적으면 다른 컴퓨터에서 거짓이 되고, 거기서 고치면 반대 방향으로 거짓이 됩니다.

**규칙 본문은 `research-writing` 의 `references/environment.md` 「환경 사실과 불변 사실을 갈라 씁니다」에 있습니다.**
여기서는 이 저장소에 적용되는 형태만 적습니다.

- **불변 사실**(명령 이름, 절차와 순서, 버전 규칙, 개념)은 본문에 그대로 씁니다.
- **환경 사실**(경로, 드라이브 문자, `$HOME` 값, 실행기 이름, 자격증명 유무, 주입된 환경변수)은
  본문에 값을 적지 않습니다. **탐색 명령으로 바꾸거나, 안 되면 저장소 밖 환경 기록(§3)에 한 줄로** 넣습니다.
- **환경 기록의 기존 줄을 지우지 않습니다.** 다른 컴퓨터용이며, 지금 컴퓨터에서 맞지 않는다는 것이
  그 줄이 틀렸다는 뜻이 아닙니다.
- **측정한 값에는 어디서 쟀는지와 날짜를 붙입니다.** 재 보지 않은 컴퓨터는 **미확인**으로 둡니다.
  추정으로 칸을 채우지 않습니다.

---

## 3. 환경 사실은 저장소 밖에 둡니다

**이 저장소에는 컴퓨터별 값(사용자 폴더, 작업 클론 위치, 실행기 경로와 판, 자격증명 보관 방식)을 적지 않습니다.**
각자 저장소 밖의 환경 기록에 두고, 새 컴퓨터가 생기면 거기에 줄을 추가합니다.
저장소 주인의 기록은 개인 작업 폴더의 공통 규칙 문서가 가리키는 `마켓플레이스_환경.md` 입니다.
그 기록이 보이지 않는 세션에서는 값을 추정하지 않고 아래 방법으로 확인합니다.

| 알고 싶은 것 | 확인하는 법 |
|---|---|
| 지금 연 폴더가 작업 클론인지 | `git rev-parse --show-toplevel` — `.claude/plugins/` 아래면 아닙니다 (§0) |
| `claude` 실행 파일과 판, 등록된 마켓플레이스, 설치된 버전 | `python bootstrap/bootstrap.py status` |
| 저장소에 로그인 창 없이 접근되는지 | `GIT_TERMINAL_PROMPT=0 git ls-remote <저장소 주소> HEAD` |
| 플러그인 설치본 폴더 (Git Bash) | `ls -d "$USERPROFILE/.claude/plugins/cache/<마켓플레이스 이름>/"*/*/` |
| 공개 검사의 개인 금지어 목록 | `git config research-plugins.denylist` — 없으면 `check` 가 일반 패턴만 보고 경고합니다 |

어느 컴퓨터에서나 지킬 것:

- **Git Bash 에서 `~` 를 쓰지 마십시오.** `$HOME` 이 사용자 프로필이 아닌 컴퓨터가 있어 `~/.claude/...` 가 없는 경로로 풀립니다.
  `$HOME` 이 프로필과 같은 컴퓨터에서는 우연히 통하므로, 한 컴퓨터에서만 확인하면 문제가 드러나지 않습니다.
  어디서나 도는 표기는 `$USERPROFILE`(PowerShell 에서는 `$env:USERPROFILE`)입니다.
- **배포 · 설치 스크립트는 Python 이라 세 운영체제에서 같은 명령입니다.** 스크립트는 자기를 실행한 Python 과,
  `--claude` → `CLAUDE_CODE_EXECPATH` → PATH → 데스크톱 앱에 든 실행 파일 순으로 찾은 `claude` 를, `codex` 도
  `--codex` → PATH → Codex 앱에 든 실행 파일 순으로 찾아 씁니다.
- **macOS 에서는 `python3` 로 부릅니다.** `python` 이 셸 alias 인 컴퓨터에서는 스크립트 안에서 풀리지 않습니다.
- **claude.ai 업로드본(`My Uploads`)이 남아 있으면 같은 이름의 CLI 설치본을 가립니다(§4).** 업로드본은 지웁니다.

---

## 4. 갱신은 수동입니다 — 자동으로 내려오지 않습니다

**등록·설치해 두면 새 버전이 알아서 온다는 서술은 사실이 아닙니다.** 이유와 명령은 `README.md` 「갱신하기」 한 곳에
있습니다. 여기에는 이 저장소를 고칠 때 지킬 것만 적습니다.

- **배포한 뒤에는 반영이 필요한 컴퓨터마다 `python bootstrap/bootstrap.py update` 를 실행하고 세션을 다시 엽니다.**
  스크립트가 설치된 플러그인에는 `update` 를, 없는 플러그인에는 `install` 을 골라 부릅니다.
- **자동화를 다시 시도하지 마십시오** (사용자 판단). 켜려면 `settings.json` 에 `autoUpdate: true` 와
  `FORCE_AUTOUPDATE_PLUGINS` 를 함께 넣어야 하는데, 후자는 데스크톱 앱이 주입하는 값을 거스르는 것이라
  앱이 갱신될 때마다 다시 확인해야 하고, 켠 뒤 검증도 다음 세션에서야 됩니다.

**업로드본(`My Uploads`)이 남아 있으면 같은 이름의 CLI 설치본을 가립니다** — 업로드본이 `rpm` 에 있는 동안 스킬 목록이
옛 판에 머물고, 업로드본 폴더가 사라지면 CLI 설치본으로 바뀝니다. 업로드본은 지웁니다.
어느 세션에 무엇이 붙었는지는 `cat "$APPDATA/Claude/local-agent-mode-sessions"/*/*/rpm/manifest.json` 이 답합니다.
