# paper-index

PDF 문헌 라이브러리를 인덱싱하고 전문(full text)을 검색하는 도구입니다.
분야에 매이지 않으며, 라이브러리 경로와 태그 프리셋만 바꾸면 어디에나 붙습니다.

**원본 라이브러리는 읽기만 합니다.** 인덱스와 전문 캐시는 별도 폴더에 사본으로 만듭니다.

## 왜 이렇게 만들었나

문헌관리 프로그램(ReadCube, Zotero 등)은 검색이 제목·초록에 머물거나, 클라우드 전환·재다운로드
때마다 파일명을 통째로 바꿔 놓습니다. 이 도구는 그 두 가지를 정면으로 다룹니다.

- **전문을 캐시해 두고 거기서 찾습니다.** 초록에 없는 근거 문장도 잡힙니다.
- **파일명이 바뀌어도 내용으로 다시 맞춥니다** (`resync`).
- **폰트 인코딩이 깨져 글자가 밀린 PDF도 복원합니다** (`repair`).

## 설치

Claude Code 2.1.275 이상에서는 이 한 줄로 마켓플레이스 등록과 설치가 함께 됩니다.

```
/plugin install paper-index --marketplace sky-born/research-plugins
```

그 아래 판과 Codex, 여러 컴퓨터의 갱신은 저장소 루트의 [README](../../README.md)를 따릅니다.
Claude Code·Codex가 같은 `skills/paper-search/` 원본을 사용합니다. 스킬과 도구를 각각 복사해 따로 관리하지 않습니다.

파이썬 3와 `pdftotext`(poppler-utils)만 있으면 됩니다. 별도 파이썬 패키지를 쓰지 않습니다.
이 문서의 `python3`은 예시입니다. 현재 환경에서 확인한 `python`·`python3`·`py -3` 또는 앱이
제공한 Python 경로로 바꿉니다. Windows에서는 `-X utf8`을 붙이고 경로를 인용합니다.
실행 도구 위치는 앱이 등록한 `paper-search/SKILL.md`의 디렉토리를 기준으로 찾습니다.
자세한 실행 예시는 [환경·전환·검증 안내](skills/paper-search/references/portability.md)를 봅니다.

```bash
# Ubuntu/Debian
sudo apt install poppler-utils
# macOS
brew install poppler
```

## 시작하기

```bash
cd <새 프로젝트 폴더>
python3 <도구경로>/papertool.py init "/path/to/PDF Library" --name "내 라이브러리"
python3 <도구경로>/papertool.py index          # 전문 추출 + 인덱스 생성
python3 <도구경로>/papertool.py tags-auto      # 태그 초안 뽑기 (프리셋이 없을 때)
python3 <도구경로>/papertool.py search "키워드"
```

`init` 이 만든 `paperindex.config.json` 이 설정 전부입니다. 이후 명령은 현재 폴더에서
위로 올라가며 이 파일을 자동으로 찾습니다.
여러 설정이나 공용 설정이 있으면 `--config "<확인한 설정>"`을 하위 명령 **앞**에 명시합니다.

기존 Codex `research-pdf-library`의 `manifest.json`·`corpus.txt`는 다른 인덱스 형식입니다.
**기존 캐시·설정을 자동 변환하거나 덮어쓰지 않습니다.** 이미 검증된 `paperindex.config.json`은
재사용할 수 있습니다. 새 구축이 필요하면 원본과 기존 인덱스 밖의 별도 출력 폴더를 사용합니다.
스킬 설치·업데이트는 실제 PDF 인덱스 재구축을 수행하지 않습니다.

## 명령

| 명령 | 하는 일 |
|---|---|
| `init <라이브러리>` | 설정 파일 생성 |
| `index [--limit N]` | 전문 추출 → 메타데이터 → 태그 → `papers_index.{json,md,csv}` 생성 |
| `reindex` | 새 파일만 추가. **기존 수동 보정은 보존** |
| `resync` | 파일명이 바뀌었을 때 경로 재매칭 (이름 정규화 → 내용 대조) |
| `repair` | 인코딩이 깨진 PDF 전문 복원 |
| `tags-auto` | 코퍼스 문서빈도에서 태그 프리셋 초안 생성 |
| `search <말> ...` | 전문 검색 (보유 문헌). **깊이 조절 가능** |
| `doctor` | 누락·중복·깨짐 점검 |
| `scopus "<질의>"` | Scopus 검색 + 보유 문헌 자동 대조 |
| `scopus-merge <파일>` | 저장된 Scopus 결과를 보유 문헌과 대조 (네트워크 불필요) |
| `oa-fetch <파일>` | 저장된 Scopus 결과의 **미보유 오픈액세스** 논문을 임시 폴더(`_수신`)에 받고 전문 텍스트 생성. `scopus`·`scopus-merge` 에 `--fetch-oa` 로 이어 붙일 수도 있습니다. 라이브러리에는 쓰지 않습니다 |
| `scopus-tidy` | 0.9 이하 판이 인덱스 폴더에 만든 실행 파일을 `_scopus/_실행완료/` 로 정리 |

검색 옵션: `--or` (OR 검색) · `--tag ENIG` · `--year 2019-2026` · `-n 5` (스니펫 수) · `-c 200` (문맥 길이).
검색어는 정규식이며 대소문자를 무시합니다. 전문 · 검색어 · 색인 제목은 대조 전에 글자 정규화(PDF 합자 `ﬂ` → `fl` · `µ` → `μ` · `℃` → `°C`,
`lib/textnorm.py`)를 거칩니다 — 캐시 파일은 고치지 않습니다(v0.9.3).

`doctor`는 파일 경로·편수 점검입니다. **같은 상대경로의 PDF 내용 변경을 자동 감지하지 않으므로**
기존 캐시의 최신성을 보장하지 않습니다. 별도 `verify_index.py`는 전체 원본의 크기·mtime·SHA-256,
인덱스 매핑·활성 캐시를 검사하고 새 JSON 기록만 만듭니다. 구축·갱신 전후의 원본 비교와 변경 없는
두 번째 실행 검증에 사용합니다. 상세 절차와 한계는 [전체 검증 안내](skills/paper-search/references/portability.md#구축갱신-후-전체-검증)에 있습니다.

### 검색 깊이

스캔은 항상 전수로 돌아 통계(적중 편수·출현 횟수)는 정확하고, **출력만** 깊이에 따라 잘립니다.

| 옵션 | 출력 | 쓰는 곳 |
|---|---|---|
| `--count-only` | 통계 한 줄 | "이 표현 자주 쓰니?" |
| `--depth quick` | 상세 3편 + 목록 10편 | 용어·표현·문장 확인 |
| `--depth focus` (기본) | 상세 8편 + 목록 20편 | 주장·인용 근거 검증 |
| `--depth full` | 적중 전부 | 전수 조사, "보고된 바 없다" 검토 |

`--max-docs N` · `--brief-docs N` · `-n` · `-c` 로 프리셋의 개별 항목만 덮어쓸 수 있습니다.
`--stop-after N` 은 스캔 자체를 조기에 끊습니다 (통계가 하한값이 되므로 빈도 보고에는 쓰지 않습니다).

## 설정 (`paperindex.config.json`)

```jsonc
{
  "name": "내 라이브러리",
  "library": [                      // 후보를 여러 개 적으면 존재하는 첫 경로를 씁니다
    "C:\\Users\\me\\Documents\\Papers",
    "/mnt/papers"
  ],
  "index_dir": ".",                 // '.' 이면 이 파일이 있는 폴더
  "preset": "solder-thesis.json",   // presets/ 에서 찾습니다. 비우면 태그 없음
  "min_tag_score": 4,               // 태그 부여 임계값
  "max_tags": 5,
  "oa_staging": "_수신",            // --fetch-oa 가 OA PDF 를 받아 두는 임시 폴더 (index_dir 기준). 라이브러리 아님
  "scopus": {                       // 선택 — 빼면 아래 기본값. 모르는 키·값은 경고하고 무시합니다
    "count": 25,                    // scopus 한 번에 받을 건수 (--count 가 덮어씀)
    "page_size": 25,                // --all 의 페이지 크기. 키가 큰 페이지를 받을 때만 올립니다 (최대 200)
    "view": null,                   // 기본: COMPLETE 를 시도하고 거부되면 STANDARD (--view 가 덮어씀)
    "sort": null                    // Scopus 정렬 값 (--sort 가 덮어씀)
  }
}
```

`library` 를 리스트로 둘 수 있는 건, 같은 폴더가 환경에 따라 다른 경로로 보이기 때문입니다
(호스트의 Windows 경로 / 에이전트 셸의 마운트 경로).

## 태그 — 프리셋과 자동 생성

태그는 검색을 좁히는 축입니다. 두 가지 방법을 함께 씁니다.

1. **프리셋** (`presets/*.json`) — 분야 지식을 넣어 손으로 짠 규칙. 개념 단위로 묶여 정확합니다.
   `presets/solder-thesis.json` 이 예시입니다 (저온 솔더·계면반응·전자패키징, 20개 태그).
2. **자동 생성** (`tags-auto`) — 라이브러리 전문에서 문서빈도가 높은 전문용어를 뽑아 초안을 만듭니다.

새 분야에서는 **자동 생성으로 초안을 뽑고 손본 뒤 프리셋으로 저장**하는 흐름을 권합니다.

```bash
papertool.py tags-auto --top 20        # index/tags.auto.json 생성
#  → 손으로 다듬어 presets/mydomain.json 으로 저장
#  → config 의 preset 을 "mydomain.json" 으로 바꾸고 index 재실행
```

프리셋 형식:

```jsonc
{
  "name": "mydomain",
  "description": "...",
  "tags": {
    "태그 이름": ["정규식1", "정규식2"],
    ...
  }
}
```

정규식 적중 횟수 합이 `min_tag_score` 를 넘으면 태그가 붙습니다. `tags` 의 순서가
인덱스 문서의 주제별 목차 순서가 됩니다.

## 파일명이 바뀌었을 때

```bash
papertool.py doctor     # "경로 누락"이 잡히면
papertool.py resync     # 이름 정규화 → 내용 대조로 다시 맞춤
papertool.py reindex    # 새로 생긴 파일 추가
```

`resync` 는 파일명이 아니라 **캐시 텍스트의 앞부분**으로 동일 문서를 판정합니다.
매칭 안 된 항목은 원본에서 삭제된 것으로 보고 인덱스에서 뺍니다. 쓰이지 않는 캐시는
지우지 않고 `_fulltext/_obsolete/` 로 옮깁니다.

## 인코딩이 깨진 PDF

일부 학회 PDF는 임베디드 폰트에 ToUnicode CMap이 없어 추출 결과가 글자가 밀린 문자열로 나옵니다.
`repair` 가 자동으로 찾아 코드포인트를 되돌리고, 붙어 버린 단어는 **같은 라이브러리에서 뽑은 어휘**로
분리합니다(`lib/wordsplit.py` — 별도 사전이 필요 없습니다).

복원본은 검색용입니다. 서브셋 폰트가 섞인 구간은 완전히 복원되지 않으니 **인용은 원본 PDF로** 합니다.

## Scopus 연동 (선택)

보유 문헌 검색만으로는 "내가 놓친 논문"을 알 수 없습니다. Scopus Search API를 붙이면
색인 전체를 훑은 뒤 **보유/미보유를 자동으로 갈라** 줍니다.

### API 키 설정 — 환경변수에만 둡니다

키를 설정 파일이나 코드에 적지 마십시오. 이 도구는 환경변수에서만 읽습니다.

**Windows**

1. 시작 메뉴에서 **계정의 환경 변수 편집** 검색
2. **사용자 변수** → **새로 만들기**
3. 변수 이름 `ELS_API_KEY`, 변수 값에 발급받은 키
4. 기관 토큰을 따로 받았다면 `ELS_INST_TOKEN` 도 같은 방식으로 추가
5. 터미널·앱을 **완전히 종료했다가** 다시 실행

**macOS / Linux** — `~/.zshrc` 또는 `~/.bashrc` 에 `export ELS_API_KEY="..."`

`ELS_API_KEY` / `ELS_INST_TOKEN` 은 Elsevier 계열 도구가 공통으로 쓰는 이름입니다.
스크립트는 키를 URL이나 명령줄에 넣지 않고 `X-ELS-APIKey` 헤더로만 보냅니다
([Elsevier 인증 문서](https://dev.elsevier.com/tecdoc_api_authentication.html)).

> **한계를 알고 쓰십시오.** 사용자 환경변수는 Git·채팅 노출은 막아 주지만 암호화 저장소가
> 아닙니다. 같은 사용자 권한으로 실행되는 다른 프로세스는 읽을 수 있습니다.

### 쓰는 법

```bash
papertool.py scopus "TITLE-ABS-KEY({Sn-Bi-In} AND solder) AND PUBYEAR > 2015" --count 25
```

결과는 `<인덱스>/_scopus/<이름>.{json,md}` 에 저장되고, 보유 문헌과 대조한 표가 함께 나옵니다.
표의 DOI 는 클릭 링크(`https://doi.org/…`)이고 `OA` 열이 붙습니다.

`--fetch-oa` 를 붙이면 **검색 범위는 그대로 두고** 미보유 오픈액세스 논문만 OpenAlex 로 찾아
임시 폴더(`oa_staging`, 기본 `_수신`)에 받고 `_수신/_text/` 에 전문 텍스트를 만듭니다 (`OA ✔`).
저장된 결과에 나중에 하려면 `oa-fetch <파일.json>`. 임시 폴더는 라이브러리가 아니므로, 남길 PDF 는
문헌 관리 프로그램으로 옮긴 뒤 `reindex` 하십시오. 구독 논문은 받지 않습니다.
**같은 DOI 는 한 번만 받습니다** — 결과 이름(`--name`)이나 질의가 달라도, 다른 컴퓨터가 받아 둔 것이어도
임시 폴더에 있으면 다시 받지 않고 그 파일을 가리킵니다. 무엇을 받았는지는 임시 폴더의 수신 목록
`_manifest.json`(DOI → 파일)에 남습니다. 판정 순서와 목록 형식은 `lib/oafetch.py` 머리말에 있습니다.

### 네트워크가 막힌 환경에서

에이전트 샌드박스처럼 외부 접속이 제한된 곳에서는 호출이 안 됩니다. 그럴 때 `scopus` 명령은
**크래시하지 않고** 키가 설정된 컴퓨터의 터미널에서 실행할 한 줄을 안내합니다. 거기서 같은 명령으로
결과 파일을 만들어 두면 `scopus-merge <파일>` 로 대조하는 것은 네트워크 없이도 됩니다.
Scopus 를 부르는 구현은 `lib/scopus.py` 하나입니다.

### 자주 쓰는 Scopus 질의 문법

| 목적 | 예 |
|---|---|
| 제목·초록·키워드 | `TITLE-ABS-KEY(solder AND reliability)` |
| 정확한 구 | `TITLE-ABS-KEY({flux-driven ripening})` |
| 저자 | `AUTHOR-NAME(Tu, K.N.)` |
| 저널 | `SRCTITLE("Journal of Alloys and Compounds")` |
| 연도 | `PUBYEAR > 2018`, `PUBYEAR IS 2024` |
| DOI | `DOI(10.1234/example.2024.001)` |

**한 페이지 크기.** 한 번에 받는 건수의 상한은 view 와 키의 서비스 등급이 정합니다. Elsevier 문서상
COMPLETE 25 · STANDARD 200 이지만, 등급에 따라 STANDARD 도 25 를 넘기면 HTTP 400
`Exceeds the maximum number allowed for the service level` 이 납니다. 그래서 도구는 25 를 기본으로 쓰고
(설정 `scopus.count` · `scopus.page_size`), 이 400 이 나면 같은 페이지를 25건으로 다시 받고 경고합니다.
`page_size` 는 키가 큰 페이지를 받는 것을 확인한 뒤에만 올립니다. 전체를 받으려면 `--all`
(5,000건까지 — 넘으면 연도 분할), 일부만 넘기려면 `--start` 를 씁니다.

## 인용 대조 (선택)

`templates/citation-check/` 에 원고의 인용 표기를 인덱스와 대조하는 템플릿이 있습니다.
인용 형식만 config로 바꾸면 어느 프로젝트에서든 씁니다. 자세한 건 그쪽 README를 보십시오.

## 한계 — 반드시 알고 쓸 것

- **제목·저자·저널은 자동 추출값입니다.** 인용 확정 전에 원본 PDF로 대조하십시오.
- **파일명과 내용이 다른 파일이 흔합니다.** 파일명만 보고 인용하면 오인용이 됩니다.
  `papers_index.md` 의 §주의 필요 항목을 확인하십시오.
- 저자는 제1저자 성(姓)만 기록합니다. 공저자는 원본에서 확인하십시오.
- 논문 ID(`P001`~)는 인덱스를 재생성할 때마다 연도·저자순으로 **다시 매겨집니다.**
- 전문 캐시는 사본입니다. 인용 출처로 `.txt` 를 적지 마십시오.

## 폴더 구조

```
skills/paper-search/
  papertool.py                 CLI 엔트리
  verify_index.py              원본 snapshot·인덱스 검증 (원본/인덱스 읽기 전용)
  lib/                         config · extract · meta · tagging · decode · wordsplit · render · resync · searching · scopus · oafetch
  presets/solder-thesis.json   저온 솔더·계면반응 분야 프리셋
  templates/citation-check/    원고 인용 대조 템플릿
  SKILL.md                     에이전트용 사용 지침 (플러그인으로 배포됨)
```
