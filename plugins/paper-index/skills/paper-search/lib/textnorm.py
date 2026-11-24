# -*- coding: utf-8 -*-
"""Character normalization — the one place applied before full text or titles are compared with queries or other titles.

PDF extraction (pdftotext) leaves fi · fl · ff as ligatures (ﬁ ﬂ ﬀ ﬃ ﬄ), the µ of µm as the micro sign (U+00B5),
and ℃ as a single character. Compared as is, `reflow` misses `reﬂow` and `μm` misses `µm`.
**The cache files (`_fulltext/*.txt`) are not changed; the text is unfolded when read.**

Rules
- NFKC per character — ligatures · µ → μ · ℃ → °C · superscript and subscript digits · full-width forms · thin spaces · math italics.
- Not given NFKC — spacing diacritics whose result is "space + combining mark" (´ ¨ ˜ ¯ ˙: it splits `Go¨rlich`
  into two words) and fractions (¼ → 1⁄4: it inserts digits into the character Elsevier PDFs print where `=` belongs).
- LIG before NFKC — quotes, dashes, hyphen variants and invisible characters NFKC leaves alone, and º printed where the degree sign (°) belongs.
Applying it several times gives the same result. Manuscript projects' phrase-frequency tool uses the same rules — check it when changing them.
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
    """Unfold ligatures and compatibility characters. ASCII is left as is."""
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
