# -*- coding: utf-8 -*-
"""Restoring the full text of PDFs whose font encoding is off.

When an embedded font has no ToUnicode CMap, pdftotext returns text with every character shifted.
The glyph order of a subset font is regular, so shifting the code points back by a fixed amount makes it readable.
One document can mix several subsets, so the best offset is chosen per line, then per token.

Limits — passages where subsets mix are not fully restored, and case information can be lost.
The restored text is for searching; always cite from the source PDF.
"""
import re, subprocess

KS = [0, 0x12, 0x13, 0x17, 0x18, 0x1d, 0x1f, 0x21, 0x2f, 0x33, 0x37, 0x38, 0x3c]
VOW = set("aeiouAEIOU")
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

COMMON = re.compile(
    r"\b(THE|AND|OF|IN|FOR|WITH|THIS|THAT|WAS|WERE|ARE|IS|TO|ON|BY|AS|AT|BE|FROM|"
    r"RESULTS|FIGURE|TABLE|PROCESS|STRUCTURE|MATERIAL|MEASURED|OBSERVED|SHOWN|"
    r"TEMPERATURE|INTERFACE|SUBSTRATE|RELIABILITY|ANALYSIS|SAMPLE|METHOD)\b")
STOPWORDS = {"the", "and", "of", "in", "for", "with", "this", "that", "are", "was", "were",
             "is", "to", "on", "by", "as", "at", "be", "from"}
EN = re.compile(r"\b(the|and|of|in|for|with|this|that|are|was|were|is|to|on|by|as|at|be|from)\b", re.I)


def shift(s, k):
    return "".join(chr(ord(c) + k) if 0x21 <= ord(c) <= 0x7e - k else c for c in s)


def score(t):
    return len(COMMON.findall(t.upper()))


def _wordscore(w):
    a = [c for c in w if c.isalpha()]
    if len(a) < 2:
        return 0
    v = sum(1 for c in a if c in VOW) / len(a)
    ok = sum(1 for c in w if c.isalnum() or c in ".,-()/%°") / len(w)
    pen = 0.4 if not (0.15 <= v <= 0.62) else 0
    return ok - pen + (0.3 if w.lower() in STOPWORDS else 0)


def decode_text(raw):
    out = []
    for line in raw.split("\n"):
        cand = [(shift(line, k), k) for k in KS]
        best = max(cand, key=lambda x: score(x[0]))
        if score(best[0]) >= 2:
            out.append(best[0])
            continue
        toks = line.split(" ")
        out.append(" ".join(
            shift(t, max(KS, key=lambda k: _wordscore(shift(t, k)))) if t.strip() else t
            for t in toks))
    return "\n".join(out)


def decode_pdf(path, pdftotext="pdftotext"):
    raw = subprocess.run([pdftotext, "-q", path, "-"],
                         capture_output=True).stdout.decode("utf-8", "ignore")
    # Control characters sometimes take the place of spaces, so turn them into spaces first.
    raw = CTRL.sub(" ", raw)
    return decode_text(raw)


def density(t):
    w = len(t.split())
    return (len(EN.findall(t)) / w) if w else 0.0


def looks_broken(t, min_chars=3000, threshold=0.02):
    return len(t) >= min_chars and density(t) < threshold
