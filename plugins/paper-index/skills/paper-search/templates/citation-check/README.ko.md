# citation-check — 원고 인용 ↔ 보유 문헌 대조 템플릿

[English](README.md) | 한국어

원고에서 인용 표기를 뽑아 문헌 인덱스와 대조하고, **보유 / 확인필요 / 미보유**로 나눠 보고합니다.

인용 관리는 분야·저널마다 형식이 달라서 도구 본체에 넣지 않았습니다.
대신 **기계적인 부분만 여기에 두고, 형식은 config 로 뺐습니다.** 새 프로젝트에서는
이 폴더를 복사해 `config.example.json` 을 고치는 것으로 시작하십시오.

## 쓰는 법

```bash
cp -r templates/citation-check <프로젝트>/citation-check
cd <프로젝트>/citation-check
cp config.example.json citecheck.config.json
# citecheck.config.json 을 프로젝트에 맞게 수정
python3 citecheck.py --out citation_check.md
```

## 고쳐야 하는 것은 세 가지뿐입니다

| 항목 | 설명 |
|---|---|
| `papers_index` | `papertool.py` 가 만든 `papers_index.json` 경로 |
| `manuscripts` | 원고 파일 glob. 여러 개 가능 |
| `citation_patterns` | 인용 표기 정규식. 이름 있는 그룹 `num` / `author` / `title` 사용 |

형식별 정규식 예시는 `config.example.json` 의 주석에 있습니다.

## 결과 해석

- **보유** — 인덱스에 대응 항목이 있고 유사도가 충분합니다. 그래도 인용 확정 전에는 원본 PDF를 봅니다.
- **확인 필요** — 후보는 있는데 유사도가 낮습니다. 동명이인이거나 제목이 잘렸을 수 있습니다.
- **미보유** — 라이브러리에 없습니다. 전문을 확인하지 않은 인용이므로, 확보하거나 인용을 재검토해야 합니다.

## 한계

- 매칭은 제1저자와 제목 유사도로 하는 **추정**입니다. DOI를 인용에 함께 적어 두면 정확도가 크게 올라갑니다.
- 번호만 쓰는 인용(`[12]`)은 그 자체로 저자·제목 정보가 없습니다. 참고문헌 목록 파일을 함께
  `manuscripts` 에 넣고 목록 항목용 패턴을 추가하십시오.
- 서지 형식(BibTeX, 저널 스타일)은 만들지 않습니다. 문헌관리 프로그램의 일입니다.
