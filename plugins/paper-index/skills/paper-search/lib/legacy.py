# -*- coding: utf-8 -*-
"""Values that older versions wrote to disk in Korean, and the English values that replace them.

The tools write only English and keep reading the old values, with no end date. This module is the only place in
paper-index code that holds them: every Korean string lives in a module-level `LEGACY_*` constant here, with a
comment giving its literal meaning (the release check allows Korean nowhere else, apart from Hangul ranges in regexes).
Where a pair's English side is also defined by the module that writes it (tagging.UNTAGGED, papertool.NOTE_BROKEN /
NOTE_FAIL, meta.DOI_PUB, oafetch.TEXT_ONLY_NOTE), tests/test_paper_format.py checks that the two agree.

Rewritten in papers_index.json by `migrate_rows` (exact matches only) when `index` / `reindex` writes it:
    LEGACY_TAGS       tag names the tool assigns; a preset adds its own `renamed` pairs (tagging.tag_aliases)
    LEGACY_NOTES      notes `repair` writes
    LEGACY_JOURNALS   journal names guessed from a DOI prefix
Read as aliases, never rewritten:
    LEGACY_ENCODING_WORD    the word `repair` looks for in a note, besides "encoding"
    LEGACY_ARCHIVE_DIR      launcher archive folder under `_scopus/` (now papertool.ARCHIVE_DIRNAME) — kept if it exists
    LEGACY_OA_STAGING       OA staging folder (now config.DEFAULT["oa_staging"]) — used when the config sets none
                            and only this folder exists
    LEGACY_LAUNCHER_PREFIX  name prefix of the launcher files versions 0.9 and earlier left in the index folder
Kept as written in Scopus result files under `_scopus/`; no code compares them, so they are on record only
(tests check their old-format fixtures against them):
    LEGACY_MATCH_BY, LEGACY_OA_NOTES, LEGACY_QUERY   — templates; `{name}` marks a variable part
"""
import collections, re

from . import textio

LEGACY_TAGS = {
    "기타(미분류)": "untagged",                          # "other (unclassified)"
}

LEGACY_NOTES = {
    # "PDF font encoding defect. The full-text cache is a restored copy. Characters are off in some passages,
    # so checking the original PDF before citing is required"
    "※ PDF 폰트 인코딩 결함. 전문 캐시는 복원본입니다. 일부 구간의 글자가 어긋나므로 인용 전 원본 PDF 확인 필수":
        "※ PDF font-encoding defect. The full-text cache is a restored copy. "
        "Some passages have shifted characters, so check the original PDF before citing",
    # "PDF text layer damaged — full-text search impossible. Original must be downloaded again or OCRed"
    "※ PDF 텍스트 레이어 손상 — 전문 검색 불가. 원본 재다운로드 또는 OCR 필요":
        "※ PDF text layer damaged — full-text search impossible. Download the original again or run OCR",
}

LEGACY_JOURNALS = {
    "Elsevier (기타)": "Elsevier (other)",              # "(other)"
    "Springer (기타)": "Springer (other)",              # "(other)"
    "MDPI (기타)": "MDPI (other)",                      # "(other)"
    "IEEE (기타)": "IEEE (other)",                      # "(other)"
    "Physical Review (기타)": "Physical Review (other)",  # "(other)"
    "AIP (J. Appl. Phys. 등)": "AIP (J. Appl. Phys. etc.)",  # "etc."
    "Nature 계열": "Nature family",                     # "family"
    "CRC Press (단행본)": "CRC Press (book)",            # "(monograph)"
}

LEGACY_ENCODING_WORD = "인코딩"                          # "encoding"
LEGACY_ARCHIVE_DIR = "_실행완료"                          # "_run done"
LEGACY_OA_STAGING = "_수신"                              # "_received"
LEGACY_LAUNCHER_PREFIX = "Scopus검색_"                   # "Scopus search_"

LEGACY_MATCH_BY = {
    "DOI 일치": "DOI match",                             # "DOI match"
    "제목 유사 {score}": "title similarity {score}",       # "title similar 0.91"
}

LEGACY_OA_NOTES = {
    # "OA, but no direct PDF address — download it yourself from the link"
    "OA 이지만 PDF 직접 주소가 없음 — 링크로 직접 받으십시오":
        "OA, but no direct PDF address — download it from the link",
    # "download failed: <reason> — download it yourself from the link"
    "다운로드 실패: {why} — 링크로 직접 받으십시오": "download failed: {why} — download it from the link",
    "PDF 아님 ({type}, {size} B)": "not a PDF ({type}, {size} B)",          # a <reason>: "not a PDF"
    "너무 작음 ({size} B)": "too small ({size} B)",                         # a <reason>: "too small"
    "{host} 에 연결할 수 없습니다: {error}": "cannot connect to {host}: {error}",  # a <reason>: "cannot connect to"
    # "the PDF is not in the staging folder, only the full text — normal if it was moved to the library or deleted"
    "PDF 는 임시 폴더에 없고 전문 텍스트만 있음 — 라이브러리로 옮겼거나 지웠으면 정상입니다":
        "PDF not in the staging folder, only its full text — normal if it was moved to the library or deleted",
}

LEGACY_QUERY = {
    "(원본 응답)": "(raw response)",                      # "(original response)": query of a raw Scopus response
}

HANGUL = re.compile("[%s]" % textio.HANGUL)


def has_encoding_word(note):
    """True if a note says the PDF's font encoding is off — in either spelling."""
    return any(w in (note or "") for w in ("encoding", LEGACY_ENCODING_WORD))


def migrate_rows(rows, tag_map=None):
    """Rewrite old spellings in index rows to English, in place. Only a value exactly equal to an old spelling changes.

    tag_map: {old tag name: current name} — normally tagging.tag_aliases(preset); LEGACY_TAGS is always included.
    Returns {"converted": Counter{(field, old value): count}, "kept": Counter{field: count}}. `kept` counts the values
    that still contain Korean afterwards — hand-written notes, hand-edited tags, Korean titles or file names — none of
    which is touched.
    """
    tag_map = {**LEGACY_TAGS, **(tag_map or {})}
    converted, kept = collections.Counter(), collections.Counter()
    for r in rows:
        tags = r.get("tags")
        if isinstance(tags, list):
            hit = [t for t in tags if isinstance(t, str) and t in tag_map]
            if hit:
                new = []
                for t in tags:
                    t = tag_map.get(t, t) if isinstance(t, str) else t
                    if t not in new:                 # a row may already carry the new name
                        new.append(t)
                r["tags"] = new
                converted.update(("tags", t) for t in hit)
        for field, table in (("note", LEGACY_NOTES), ("journal", LEGACY_JOURNALS)):
            v = r.get(field)
            if isinstance(v, str) and v in table:
                r[field] = table[v]
                converted[(field, v)] += 1
        for field, v in r.items():
            kept[field] += sum(1 for x in (v if isinstance(v, list) else [v])
                               if isinstance(x, str) and HANGUL.search(x))
    return {"converted": converted, "kept": +kept}
