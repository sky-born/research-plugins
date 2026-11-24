# 실행 환경·기존 인덱스 전환·검증

## 같은 원본을 각 앱에서 실행

스킬 본문과 `papertool.py`·`lib/`·참조 파일은 하나의 공통 원본입니다. 등록은 Claude Code의
플러그인과 Codex의 설치 절차로 나뉩니다. 설치·갱신은 저장소 루트의
안내를 따르고, 설치된 사본이나 다른 앱의 캐시를 직접 수정하지 않습니다.

1. 앱이 알려 준 이 `SKILL.md`의 실제 디렉토리를 확인합니다.
2. 해당 디렉토리의 `papertool.py`·`lib/`가 함께 있는지 확인합니다.
3. 실행할 Python 3와 `pdftotext`를 확인합니다. Python 명령 이름, 설치 경로, 셸, 네트워크,
   환경변수, 연결된 폴더는 컴퓨터·세션별 사실입니다. 설치된 것만 사용합니다.
4. 프로젝트 `AGENTS.md`·`CLAUDE.md`에서 원본과 인덱스의 경로·검색 범위를 읽습니다.
   어느 파일도 자동으로 로딩되었다고 가정하지 않습니다. 앱의 상위 지침과 사용자 요청을 우선합니다.

PowerShell 예시 (`<...>`는 확인한 경로로 교체합니다):

```powershell
$PaperTool = Join-Path '<등록된 paper-search 디렉토리>' 'papertool.py'
$PaperConfig = '<확인한 paperindex.config.json>'
Get-Command python,python3,py,pdftotext -ErrorAction SilentlyContinue
python -X utf8 "$PaperTool" --help
python -X utf8 "$PaperTool" --config "$PaperConfig" doctor
python -X utf8 "$PaperTool" --config "$PaperConfig" search --depth quick 'keyword'
```

Bash 예시 (`python3`가 실제 Python 3로 확인된 경우):

```bash
TOOL='<등록된 paper-search 디렉토리>/papertool.py'
PAPER_CONFIG='<확인한 paperindex.config.json>'
command -v python3
command -v pdftotext
python3 -X utf8 "$TOOL" --help
python3 -X utf8 "$TOOL" --config "$PAPER_CONFIG" doctor
```

`pdftotext`가 PATH에 없다면 설치된 실행 파일 경로를 config의 `pdftotext`에 등록할 수 있습니다.
실행기를 못 찾았다고 임의의 시스템 설정을 고치지 않습니다. 도구의 `search`는 기존 캐시만으로도
동작하지만 PDF 추출에는 `pdftotext`가 필요합니다. 쉘별 `$변수`·줄 이어쓰기 문법을 그대로 섞지 않습니다.

## 기존 인덱스 전환

| 형식 | 파일 | 처리 |
|---|---|---|
| 이전 Codex `research-pdf-library` | `manifest.json`, `corpus.txt`, 개별 추출 텍스트 | 원래 위치에 보존. 기존 조회에 사용 가능 |
| 공통 `paper-search` | `paperindex.config.json`, `papers_index.{json,md,csv}`, `_fulltext/` | 검증된 기존 설정을 재사용하거나 별도 위치에서 새로 구축 |

두 형식의 메타데이터·캐시 구조는 다릅니다. 파일 이름만 바꾸거나 새 도구를 기존 인덱스 폴더에
덮어 실행하는 것은 마이그레이션이 아닙니다. `corpus.txt`를 새 config로 자동 대체하지 않습니다.
스킬 설치·업데이트도 실제 PDF 인덱스를 다시 만들거나 이전 캐시를 삭제하는 권한이 아닙니다.

새 구축이 필요하면 기존 인덱스와 원본 밖의 비어 있는 출력 폴더를 정하고, 기존 config를 읽은 뒤
새 config 파일명을 사용합니다. `init`은 기존 config를 덮어쓸 수 있으므로 같은 이름을 재사용하지 않습니다.
프리셋을 수정할 때는 프로젝트 소유 경로에 저장하고 config로 지정합니다. 설치된 `presets/`는 수정하지 않습니다.

`reindex`는 새 상대경로만 추가합니다. **같은 경로의 내용 변경을 SHA-256으로 감지하는 기능은
현재 없습니다.** 이전 검증 기록과 원본이 달라졌다면 기존 전문 캐시의 최신성을 확인할 수 없습니다.
기존 수동 보정과 캐시를 보존한 채 별도 재구축을 계획하며, 필요한 출력 변경 범위가 불명확하면
먼저 그 범위를 확정합니다. `doctor`의 경로·편수 확인만으로 내용 최신성을 단정하지 않습니다.

## 구축·갱신 후 전체 검증

`verify_index.py`는 Python 표준 라이브러리만 사용합니다. 원본·인덱스는 읽기만 하고 지정한 새 JSON
기록만 만듭니다. 기존 기록을 덮어쓰지 않으며 원본/설치 스킬 내부로 보고서를 쓰지 않습니다.
원본과 인덱스/OA 임시 폴더가 중첩되면 중단합니다. 모든 PDF의 상대경로·크기·mtime·SHA-256을
기록하므로 큰 라이브러리에서는 시간이 걸립니다. 일반 검색 때마다 이 절차를 반복하지 않습니다.

1. 원본 동기화가 안정된 것을 확인하고 **작업 전 snapshot**을 원본 밖 작업 폴더에 저장합니다.
2. 필요한 `index`·`reindex`·`resync`·`repair`를 수행합니다. `repair` 대상은 추출 캐시입니다.
3. `doctor`로 경로를 확인한 다음 `verify`로 전체 원본 집합, 인덱스 매핑, 활성 캐시 존재·비어 있음,
   중복 매핑, 짧은 전문·비고 항목을 점검하고 작업 전후 원본 기록을 대조합니다.
4. 원본 변경이 없을 때 다시 snapshot을 만들고 같은 갱신 명령을 한 번 더 실행합니다.
   새 구축의 `index`는 추가 추출 0편, `reindex`는 신규 0편이어야 합니다.
   `verify --require-index-unchanged`로 활성 JSON/텍스트 캐시의 내용도 동일한지 확인합니다.
5. 관련 검색을 한 번 실행하고 대표 근거를 원본 PDF에서 대조합니다. 모든 오류와
   `extraction_exceptions`를 보고합니다. 추출 예외가 있으면 전 문헌 전문 검증 완료라고 말하지 않습니다.

아래는 새 기록 이름을 사용하는 PowerShell 예시입니다. 실제 갱신 명령은 원본 상태에 맞춰 선택합니다.

```powershell
$PaperCheck = Join-Path (Split-Path "$PaperTool") 'verify_index.py'
python -X utf8 "$PaperCheck" --config "$PaperConfig" snapshot --out '<작업폴더>/source-before.json'
python -X utf8 "$PaperTool" --config "$PaperConfig" reindex
python -X utf8 "$PaperCheck" --config "$PaperConfig" verify --before '<작업폴더>/source-before.json' --out '<작업폴더>/source-after.json'
python -X utf8 "$PaperCheck" --config "$PaperConfig" snapshot --out '<작업폴더>/rerun-before.json'
python -X utf8 "$PaperTool" --config "$PaperConfig" reindex
python -X utf8 "$PaperCheck" --config "$PaperConfig" verify --before '<작업폴더>/rerun-before.json' --require-index-unchanged --out '<작업폴더>/rerun-after.json'
```

도구 시험이 통과했다는 사실과 **실제 문헌 라이브러리 전체의 원본 불변 검증**은 구분합니다.
두 snapshot이 같은 것은 그 사이에 감지된 원본 변경이 없다는 뜻입니다. 구축 전부터 오래된 캐시가
있었다면 그 캐시가 최신이라는 증거는 아닙니다. 최종 보고에는 실제 검사 범위·명령·입출력 경로·
전체 편수·예외·두 번째 실행 결과와 원본 쓰기 작업을 발행하지 않았다는 사실을 함께 기록합니다.
