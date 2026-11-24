# -*- coding: utf-8 -*-
"""글자 정규화 — 전문 · 제목을 검색어나 다른 제목과 대조하기 전에 거는 한 곳입니다.

PDF 추출(pdftotext)은 fi · fl · ff 를 합자(ﬁ ﬂ ﬀ ﬃ ﬄ)로, µm 의 µ 를 마이크로 기호(U+00B5)로,
℃ 를 한 글자로 남깁니다. 그대로 대조하면 `reflow` 가 `reﬂow` 를, `μm` 이 `µm` 을 놓칩니다.
**캐시 파일(`_fulltext/*.txt`)은 고치지 않고 읽을 때 풉니다.**

규칙
- 글자 단위 NFKC — 합자 · µ → μ · ℃ → °C · 위 · 아래 첨자 숫자 · 전각 · 얇은 공백 · 수학 이탤릭.
- NFKC 를 걸지 않는 것 — 결과가 「공백 + 결합 부호」인 띄어 쓴 발음 부호(´ ¨ ˜ ¯ ˙: `Go¨rlich` 를 두 낱말로
  쪼갬)와 분수(¼ → 1⁄4: 엘제비어 PDF 에서 `=` 자리에 찍힌 글자에 숫자를 끼워 넣음).
- NFKC 보다 먼저 LIG — NFKC 가 건드리지 않는 따옴표 · 대시 · 하이픈 변종 · 보이지 않는 글자와, 도(°) 자리에 찍힌 º.
여러 번 걸어도 결과가 같습니다. 같은 규칙을 원고 프로젝트의 구문 빈도 도구도 씁니다 — 바꿀 때 함께 봅니다.
"""
import unicodedata

LIG = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
       "‘": "'", "’": "'", "“": '"', "”": '"',
       "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-",
       "­": "", " ": " ", "​": "", "�": "", "º": "°"}
_MAP = {}


def _char(ch):
    if ch in LIG:
        return LIG[ch]
    n = unicodedata.normalize("NFKC", ch)
    if n == ch or "⁄" in n or any(unicodedata.combining(x) for x in n):
        return None
    return "".join(LIG.get(x, x) for x in n)


def norm_text(t):
    """합자 · 호환 문자를 풉니다. ASCII 는 그대로 둡니다."""
    if not t:
        return t or ""
    tbl = {}
    for ch in set(t):
        if ch < "\x80":
            continue
        if ch not in _MAP:
            _MAP[ch] = _char(ch)
        if _MAP[ch] is not None:
            tbl[ord(ch)] = _MAP[ch]
    return t.translate(tbl) if tbl else t
