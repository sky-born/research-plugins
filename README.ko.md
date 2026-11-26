# research-plugins

[English](README.md) | 한국어

학술 논문 집필 규칙과 PDF 문헌 검색 플러그인입니다. Claude Code · Codex 가 같은 스킬을 씁니다.
이 저장소 하나로 버전 관리해, **여러 컴퓨터 · 여러 계정이 같은 버전을 쓰게** 합니다.
AI 코딩 도구(Claude Code · Codex)를 활용해 개발합니다.

| 항목 | 값 |
|---|---|
| 마켓플레이스 이름 | `research-plugins` |
| 저장소 | `sky-born/research-plugins` |
| 플러그인 | `research-writing` · `paper-index` |
| 갱신 방식 | 수동 — [갱신하기](#갱신하기) |
| 이 저장소를 고칠 때 | [`CLAUDE.md`](CLAUDE.md) — 클론 구분 · 배포 절차 |

**바로 가기** — [담긴 플러그인](#담긴-플러그인) · [설치하기](#설치하기) · [갱신하기](#갱신하기) · [저장소 구조](#저장소-구조) · [고치고 배포하기](#고치고-배포하기) · [새 플러그인 추가하기](#새-플러그인-추가하기) · [push 자격증명](#push-자격증명) · [문제 해결](#문제-해결)

---

## 담긴 플러그인

| 플러그인 | 스킬 | 하는 일 | Claude Code 호출 |
|---|---|---|---|
| `research-writing` | `manuscript` | 원고 작업 세션의 진입점 — 열린 폴더가 어떤 원고 프로젝트인지 판정 | `/research-writing:manuscript` |
| | `manuscript-workflow` | 집필 공통 규칙 — 문체 · 근거 등급 · 인용 · 수정안 프로토콜 · 미결 추적 | `/research-writing:manuscript-workflow` |
| | `new-manuscript` | 새 원고 프로젝트를 도구 · 설정 · 추적 파일까지 한 번에 생성 | `/research-writing:new-manuscript` |
| `paper-index` | `paper-search` | PDF 문헌 인덱싱 · 전문 검색 · Scopus 결과와 보유 문헌 대조 | `/paper-index:paper-search` |

Codex 에서는 스킬 선택기에 보이는 같은 이름의 스킬을 고릅니다.
스킬 본문과 도구, 도구가 프로젝트에 만드는 모든 파일은 영어입니다. research-writing 0.14 이전에 만든 프로젝트의 한국어 표기도 도구가 계속 읽습니다.
앱마다 호출 문법은 달라도 **읽는 본문과 실행 도구는 같습니다** ([공통 원본과 앱별 등록](#공통-원본과-앱별-등록)).

---

## 설치하기

새 컴퓨터 · 새 계정에서 한 번만 합니다. GitHub 로그인은 필요 없습니다.
Claude Code 와 Codex 가 같은 명령을 씁니다 — 스크립트가 그 컴퓨터에 있는 앱을 찾아 각각 등록 · 설치합니다.

**Windows (PowerShell)**

```powershell
git clone https://github.com/sky-born/research-plugins "$env:USERPROFILE\dev\research-plugins"
python "$env:USERPROFILE\dev\research-plugins\bootstrap\bootstrap.py" install
```

**macOS · Linux**

```bash
git clone https://github.com/sky-born/research-plugins ~/dev/research-plugins
python3 ~/dev/research-plugins/bootstrap/bootstrap.py install
```

끝나면 앱의 세션을 다시 엽니다. 내려받은 폴더는 이 저장소를 고칠 때 쓰는 **작업 클론**이기도 합니다 ([클론이 셋입니다](#클론이-셋입니다)).

| 옵션 | 뜻 |
|---|---|
| `--app claude` · `--app codex` · `--app all` | 한 앱만, 또는 둘 다(하나라도 없으면 실패). 생략하면 그 컴퓨터에 있는 앱 전부 |
| `--dry-run` | 실행할 명령만 출력 |
| `--claude <경로>` | `claude` 실행 파일을 직접 지정 |
| `--codex <경로>` | `codex` 실행 파일을 직접 지정 |
| `--ref <태그 또는 커밋>` | Codex 전용 — 기본 `main` 대신 특정 배포 태그 · 커밋을 고정 |
| `--local` | Codex 전용 · 배포 전 시험용 — GitHub 대신 지금 작업 클론을 등록 (그 폴더를 옮기지 않습니다) |

> [!WARNING]
> Windows 에서는 Git Bash 가 아니라 PowerShell 쪽을 씁니다.
> Git Bash 의 `$HOME` 이 사용자 프로필이 아닌 컴퓨터가 있어 `~/dev` · `~/.claude` 가 엉뚱한 곳으로 풀립니다.
> Git Bash 에서 경로를 다뤄야 하면 `$USERPROFILE` 을 씁니다 ([`CLAUDE.md`](CLAUDE.md) §3).

<details>
<summary>부트스트랩이 하는 일</summary>

1. 앱의 실행 파일을 찾습니다. `claude` 는 `--claude` → 환경변수 `CLAUDE_CODE_EXECPATH`(세션 안에서 돌 때) → PATH → 데스크톱 앱에 들어 있는 것 순서로, `codex` 는 `--codex` → PATH → Codex 데스크톱 앱에 들어 있는 것(Windows 는 `%LOCALAPPDATA%` 아래, macOS 는 `/Applications` 또는 `~/Applications` 의 앱) 순서로 찾습니다.
2. 마켓플레이스 이름과 플러그인 목록을 `.claude-plugin/marketplace.json` 에서, 저장소 주소를 작업 클론의 `git remote` 에서 읽습니다.
3. 저장소에 **로그인 창 없이** 접근되는지 확인합니다. 안 되면 여기서 멈추고 해결 방법을 알려 줍니다.
4. 마켓플레이스가 등록돼 있지 않으면 `claude plugin marketplace add`, 있으면 `claude plugin marketplace update` 를 실행합니다.
5. 플러그인마다 없으면 `claude plugin install`, 있으면 `claude plugin update` 를 실행합니다.
6. 설치된 버전을 작업 클론의 버전과 견주어 출력합니다.

설정 파일은 직접 고치지 않습니다. 4 · 5 의 명령이 사용자 설정 `.claude/settings.json` 에 아래 두 키를 씁니다.

```json
{
  "extraKnownMarketplaces": {
    "research-plugins": {
      "source": { "source": "github", "repo": "sky-born/research-plugins" }
    }
  },
  "enabledPlugins": {
    "paper-index@research-plugins": true,
    "research-writing@research-plugins": true
  }
}
```

두 키 모두 사용자 설정에 들어가므로 **모든 프로젝트에 적용**됩니다.
Codex 쪽은 Codex 의 공식 마켓플레이스 등록 · 설치 명령만 호출합니다.

</details>

<details>
<summary>부트스트랩 없이 수동으로</summary>

```text
/plugin marketplace add sky-born/research-plugins
/plugin install paper-index@research-plugins
/plugin install research-writing@research-plugins
```

</details>

<details>
<summary>Codex — 로컬 시험 등록에서 GitHub 로 되돌릴 때</summary>

Codex 는 같은 마켓플레이스 이름의 소스가 바뀌어도 자동으로 덮어쓰지 않습니다. 아래 두 명령을 순서대로 실행합니다.

```text
codex plugin marketplace remove research-plugins
python bootstrap/bootstrap.py install --app codex
```

</details>

---

## 갱신하기

> [!IMPORTANT]
> **갱신은 자동이 아닙니다.** 새 버전을 배포한 뒤, 반영이 필요한 컴퓨터마다 아래를 직접 실행하고 **세션을 다시 엽니다.**

작업 클론에서 실행합니다. 두 앱 모두 이 두 줄입니다.

```text
git pull
python bootstrap/bootstrap.py update
```

Python 실행기 이름은 그 컴퓨터에서 확인한 `python` 또는 `python3` 를 씁니다.
지금 무엇이 등록 · 설치돼 있는지는 `python bootstrap/bootstrap.py status` 가 보여 줍니다.

<details>
<summary>스크립트 없이 직접</summary>

```bash
claude plugin marketplace update research-plugins
claude plugin update research-writing@research-plugins
claude plugin update paper-index@research-plugins
```

- `update` 는 바뀐 플러그인만 실행하면 됩니다.
- **`install` 이 아니라 `update` 입니다.** 이미 설치된 플러그인에 `install` 을 실행하면 `already installed` 만 내고 버전을 올리지 않습니다.
- Codex 는 `codex plugin marketplace upgrade research-plugins` 뒤 플러그인마다 `codex plugin add <플러그인>@research-plugins` 입니다.

</details>

<details>
<summary>왜 자동으로 내려오지 않는가</summary>

원인이 둘이고, 둘 다 이 저장소가 고칠 수 있는 것이 아닙니다.

- **개인 마켓플레이스는 자동 갱신 기본값이 꺼짐입니다.** 공식 마켓플레이스가 아니면 `autoUpdate` 를 따로 켜지 않는 한 꺼져 있습니다.
- **데스크톱 앱은 CLI 프로세스에 `DISABLE_AUTOUPDATER` 를 넣습니다.** 이 값이 있으면 플러그인 자동 갱신 단계가 통째로 건너뛰어집니다.

자동화는 하지 않기로 했습니다. 켜려면 `autoUpdate: true` 와 환경변수 `FORCE_AUTOUPDATE_PLUGINS` 를 함께 넣어야 하는데,
후자는 데스크톱 앱이 넣는 값을 거스르는 것이라 앱이 바뀔 때마다 다시 확인해야 합니다. 위 명령을 필요할 때 실행하는 편이 유지비가 낮습니다.

</details>

---

## 저장소 구조

```
research-plugins/
├── README.md                        설치 · 사용법 (영어)
├── README.ko.md                     같은 내용의 한국어본 (이 문서)
├── CLAUDE.md                        이 저장소를 고칠 때의 작업 규칙
├── AGENTS.md                        Codex 용 진입 안내 (CLAUDE.md 를 가리킴)
├── CHANGELOG.md                     플러그인별 배포 이력
├── LICENSE                          MIT
├── .github/workflows/
│   └── check.yml                    push 마다 Windows · macOS · Linux 에서 `release.py check` 실행
├── .claude-plugin/
│   └── marketplace.json             마켓플레이스 정의 — 플러그인 목록의 원본
├── .agents/plugins/
│   └── marketplace.json             Codex 용 등록 파일 (생성물)
├── bootstrap/
│   └── bootstrap.py                 두 앱의 등록 · 설치 · 갱신 · 상태 (install · update · status)
├── shared/
│   └── textio.py                    플러그인에 복사해 쓰는 한 벌의 정의 (이름은 NFC · 한글 범위)
├── scripts/
│   ├── release.py                   검사 · 세션 시험 · 버전 올림 · 배포 (check · try · bump · publish)
│   ├── cli_common.py                위 두 스크립트가 함께 쓰는 도우미
│   ├── sync_codex_manifests.py      plugin.json 에서 나오는 생성물 만들기 · 어긋남 검사
│   ├── sync_shared.py               shared/ 모듈을 플러그인에 복사 · 어긋남 검사
│   ├── validate_shared_plugins.py   두 앱의 공통 배포 구성 검증
│   ├── tool_hashes.py               관리 파일 해시 목록 생성
│   ├── check_public.py              올릴 내용에서 개인 정보를 찾음
│   └── preview_projects.py          실제 프로젝트의 사본에 새 도구를 미리 적용
├── tests/                           배포 전 시험 (unittest)
└── plugins/
    ├── research-writing/
    │   ├── .claude-plugin/plugin.json   이름 · 버전 · 설명의 원본
    │   ├── .codex-plugin/plugin.json    Codex 용 (생성물)
    │   ├── README.md · README.ko.md
    │   ├── hooks/hooks.json             원고 프로젝트의 공용 파일 보호 훅
    │   └── skills/
    │       ├── manuscript/              SKILL.md
    │       ├── manuscript-workflow/     SKILL.md · references/ · templates/
    │       └── new-manuscript/          SKILL.md · init_manuscript.py · update_tools.py · tools/ · hooks/
    └── paper-index/
        ├── .claude-plugin/plugin.json
        ├── .codex-plugin/plugin.json    Codex 용 (생성물)
        ├── README.md · README.ko.md
        └── skills/paper-search/         SKILL.md · papertool.py · lib/ · presets/ · references/ · templates/
```

### 클론이 셋입니다

같은 저장소의 사본이 한 컴퓨터에 셋 생깁니다. **고칠 수 있는 것은 작업 클론 하나뿐입니다.**

```mermaid
flowchart LR
    W["작업 클론<br>여기서만 고칩니다"]
    G[("GitHub<br>저장소")]
    C["마켓플레이스 캐시<br>읽기만"]
    I["플러그인 설치본<br>버전별 사본 · 읽기만"]
    S(["Claude Code 세션"])
    W -- "release.py publish<br>커밋 · push · 태그" --> G
    G -- "claude plugin<br>marketplace update" --> C
    C -- "claude plugin update" --> I
    I -- "세션 다시 열기" --> S
```

| 클론 | 무엇 | 취급 |
|---|---|---|
| **작업 클론** | `git clone` 으로 직접 만든 것 | **여기서만 고칩니다** |
| 마켓플레이스 캐시 | `claude plugin marketplace add` 가 만든 것 | 읽기만 — `marketplace update` 가 덮어씁니다 |
| 플러그인 설치본 | `claude plugin install` 이 푼 버전별 사본 | 읽기만 — 설치된 버전을 확인할 때 봅니다 |

실제 경로는 컴퓨터마다 다르고 이 저장소에는 적지 않습니다. 지금 컴퓨터의 상태는 `python bootstrap/bootstrap.py status` 가 보여 줍니다 ([`CLAUDE.md`](CLAUDE.md) §3).

### 공통 원본과 앱별 등록

`plugins/<플러그인>/skills/` 의 지침 · 참조 문서 · 도구가 **두 앱이 쓰는 같은 원본**입니다.
Claude 용과 Codex 용으로 스킬 내용을 복사해 관리하지 않습니다.

| 구분 | Claude Code | Codex |
|---|---|---|
| 마켓플레이스 | `.claude-plugin/marketplace.json` | `.agents/plugins/marketplace.json` (생성물) |
| 플러그인 등록 | `.claude-plugin/plugin.json` | `.codex-plugin/plugin.json` (생성물) |
| 스킬 · 도구 | `plugins/<이름>/skills/` | 같은 폴더 |
| 버전 원본 | `.claude-plugin/plugin.json` 의 `version` | 원본에서 생성하고 일치 여부를 검증 |

플러그인의 이름 · 버전 · 설명 · 작성자 · 라이선스 · 키워드는 `plugin.json` 한 곳에만 적습니다.
Codex 용 파일과, `.claude-plugin/marketplace.json` 의 플러그인 항목에 있는 같은 필드는 거기서 생성합니다.
생성물은 손으로 고치지 않습니다.

```text
python scripts/sync_codex_manifests.py            # 생성물 다시 만들기
python scripts/sync_codex_manifests.py --check    # 어긋남만 확인
python scripts/validate_shared_plugins.py         # 공통 배포 구성 검증
```

---

## 고치고 배포하기

> [!WARNING]
> **작업 클론은 클라우드 동기화 폴더(구글드라이브 · OneDrive) 밖에 둡니다.**
> 동기화가 `.git` 을 반쯤 덮어써 저장소를 깨뜨릴 수 있습니다. 컴퓨터마다 각자 클론하고, 동기화는 GitHub 이 합니다.

### 버전 규칙

> [!IMPORTANT]
> **플러그인을 고쳤으면 그 플러그인의 `.claude-plugin/plugin.json` 의 `version` 을 올립니다.**
> 이 값이 배포 버전이고, 바뀌어야 다른 컴퓨터가 새 버전으로 봅니다. 파일만 고치고 버전을 그대로 두면 다른 컴퓨터는 옛 버전을 계속 씁니다.

- 이 저장소의 플러그인은 상대 경로(`./plugins/...`)로 배포되고, 버전은 `plugin.json` 에 적은 값으로 고정됩니다.
- `marketplace.json` 의 플러그인 항목에는 `version` 을 적지 않습니다. 두 곳에 다 적으면 Claude Code 는 경고 없이 `plugin.json` 쪽을 씁니다. 한 곳에만 둡니다.
- `scripts/release.py` 가 이 규칙을 검사하고, 버전이 그대로면 중단합니다.

### 절차

작업 클론에서 실행합니다. Windows · macOS · Linux 에서 같은 명령입니다.

```text
git pull

# 1) 파일 수정
# 2) 버전 올리기 - plugin.json, 생성물, 해시 목록을 한 번에
python scripts/release.py bump <플러그인> patch

# 3) CHANGELOG.md 의 그 플러그인 절에 "### <버전> - <날짜>" 와 바뀐 점 적기

# 4) 검사만 먼저
python scripts/release.py check
python scripts/release.py try <폴더>

# 5) 배포
python scripts/release.py publish -m "paper-index v0.10.0: short summary"
```

배포한 뒤에는 컴퓨터마다 [갱신하기](#갱신하기)의 명령을 실행합니다.
`check` 가 돌리지 않는 검증은 실제 프로젝트 사본 미리보기(`preview_projects.py`) 하나이고, [`CLAUDE.md`](CLAUDE.md) §1 에 있습니다.

`check` 가 순서대로 하는 일:

1. 기준선의 원격을 `git fetch` 하고 기준선 `origin/main` 확인, 파일 이름이 모두 ASCII 인지 확인 — 아니면 **중단**
2. 파일 · 경로 · 올릴 커밋 · 다음 커밋의 작성자 정보에서 개인 정보를 찾음 (`check_public.py`) — 걸리면 **중단**. 개인 금지어는 저장소 밖 목록에서 읽습니다(`--deny-list` · `RESEARCH_PLUGINS_DENYLIST` · 클론의 `git config research-plugins.denylist <file>`). 목록이 없으면 일반 패턴만 보고 경고합니다
3. 두 앱의 공통 배포 구성과 생성물이 원본과 같은지 검증 (`validate_shared_plugins.py`), 관리 파일 해시 목록이 최신인지 확인 (`tool_hashes.py --check`). 100줄이 넘는 스킬 참조 문서는 머리 목차가 머리글과 맞아야 함. 한국어는 데이터로만 — Markdown 본문(`README.<언어>.md` 번역본 제외) · 파이썬 주석 · 이름 · 설명문에서 코드 표기 밖이면 **중단**하고, 플러그인 · 스크립트 코드의 한국어 문자열은 옛 표기 표(`LEGACY*`)나 `가-힣` 문자 범위에만 둘 수 있음. `shared/` 모듈의 사본이 원본과 같아야 하고(`sync_shared.py --check`), 텍스트 경계 규칙을 지켜야 함 — 인코딩 명시, 이름과 한글 범위는 설치 단위의 텍스트 모듈을 거침([`CLAUDE.md`](CLAUDE.md) §5)
4. `claude plugin validate` 로 마켓플레이스 · 플러그인 매니페스트 검증 — 쓴 실행 파일과 판을 출력합니다
5. 기준선과 비교해 **바뀐 플러그인**을 판정하고, 그 플러그인마다 `version` 이 올라갔는지 확인 — 아니면 **중단**
6. 올린 버전마다 `CHANGELOG.md` 에 항목이 있고 플러그인 아닌 절이 없는지 확인 — 아니면 **중단**
7. 시험 전체 (`tests/`)

push 할 때마다 GitHub Actions(`.github/workflows/check.yml`)가 Windows · macOS · Linux 에서 같은 `check` 를 돌립니다. `claude plugin validate` 단계만 빠집니다.

`publish` 는 같은 검사를 통과한 뒤 커밋 → `git push` → 플러그인별 `{이름}--v{버전}` 태그 생성 · push 를 합니다.
태그는 그 플러그인 폴더를 마지막으로 고친 커밋에 붙습니다.

| 옵션 | 뜻 |
|---|---|
| `-m "..."` | 커밋 제목(72자 이내). 보통 제목만으로 충분함. 한 번 더 쓰면 목적(왜)을 적은 짧은 한 문장 — 플러그인의 바뀐 점은 `CHANGELOG.md` 에. `Co-Authored-By` 같은 꼬리표가 있으면 중단. 생략하면 바뀐 플러그인과 버전으로 자동 작성 |
| `--no-push` | 커밋 · 태그까지만 (`publish`) |
| `--no-tag` | 태그를 만들지 않음 (`publish`) |
| `--skip-tests` | 시험을 돌리지 않음 — 돌리지 않았다고 출력합니다 |
| `--skip-claude` | `claude plugin validate` 를 돌리지 않음 — `claude` 가 없는 GitHub Actions 실행용 |
| `--claude <경로>` | `claude` 실행 파일을 직접 지정 |
| `--baseline <ref>` | 비교 기준 (기본 `origin/main`) |

---

## 새 플러그인 추가하기

```
plugins/<이름>/
├── .claude-plugin/plugin.json      name · version · description · author · license
└── skills/<스킬이름>/SKILL.md
```

`commands/` · `agents/` · `hooks/` 도 같은 층위에 둘 수 있습니다. 만든 뒤 아래 셋을 합니다.

1. `.claude-plugin/marketplace.json` 의 `plugins` 배열에 항목 추가

   ```json
   {
     "name": "<이름>",
     "source": "./plugins/<이름>",
     "category": "research",
     "strict": true
   }
   ```

2. `python scripts/sync_codex_manifests.py` 실행 — Codex 등록 파일을 만들고, 위 항목에 설명 · 작성자 · 라이선스 · 키워드를 `plugin.json` 에서 채웁니다
3. `CHANGELOG.md` 에 `## <이름>` 절과 첫 버전의 항목을 추가한 뒤 `python scripts/release.py publish` 로 배포

설치 스크립트는 플러그인 목록을 `marketplace.json` 에서 읽으므로 따로 고칠 곳이 없습니다.

**플러그인 이름을 바꾸거나 없앨 때**는 `marketplace.json` 의 `renames` 에 남깁니다.
다른 컴퓨터의 설정에 있는 옛 이름이 새 이름으로 옮겨집니다. 이 표는 지우지 않고 쌓아 둡니다.
없앤 플러그인의 절은 `CHANGELOG.md` 에서도 지웁니다 — 플러그인이 아닌 절이 있으면 `check` 가 멈춥니다.

```json
"renames": { "old-name": "new-name", "removed-name": null }
```

---

## push 자격증명

설치 · 갱신에는 로그인이 필요 없습니다. push(`release.py publish`)할 때만 **그 컴퓨터에 GitHub 자격증명이 저장돼 있어야** 합니다. 둘 중 하나로 저장합니다.

- **Windows** — 처음 push 할 때 Git Credential Manager 로그인 창에서 로그인합니다.
- **`gh` CLI 가 있으면** — `gh auth login` 뒤 `gh auth setup-git`

---

## 문제 해결

| 증상 | 확인할 것 |
|---|---|
| 스킬이 안 보임 | 세션을 다시 엽니다. `python bootstrap/bootstrap.py status` 로 등록 · 설치 여부 확인 |
| 새 버전이 안 옴 | [갱신 명령](#갱신하기)을 실행했는지 → 그 플러그인의 `version` 을 올렸는지 ([버전 규칙](#버전-규칙)) |
| 고친 것이 반영 안 됨 | 작업 클론이 아니라 캐시를 고쳤을 수 있습니다 ([클론이 셋입니다](#클론이-셋입니다)) |
| 마켓플레이스가 없다고 나옴 | `python bootstrap/bootstrap.py install` 을 다시 실행 |
| `claude` 를 못 찾는다고 나옴 | `--claude <경로>` 로 실행 파일을 지정 |
| 마켓플레이스가 다른 주소로 등록돼 있다고 나옴 | 저장소를 옮긴 것입니다. `claude plugin marketplace remove research-plugins` 뒤 `python bootstrap/bootstrap.py install` |
| 매니페스트가 깨짐 | 작업 클론에서 `python scripts/release.py check` |

수동 검증:

```bash
claude plugin validate .
claude plugin validate plugins/paper-index
claude plugin marketplace list
claude plugin list
```
