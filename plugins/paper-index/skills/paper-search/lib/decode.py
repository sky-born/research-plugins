# -*- coding: utf-8 -*-
"""폰트 인코딩이 어긋난 PDF의 전문 복원.

임베디드 폰트에 ToUnicode CMap이 없으면 pdftotext 결과가 글자가 밀린 문자열로 나옵니다.
서브셋 폰트의 글리프 순서가 일정해서, 코드포인트를 일정량 되돌리면 읽을 수 있습니다.
문서 하나에 서브셋이 여러 개 섞여 있을 수 있어 줄 단위 → 토큰 단위로 최적 오프셋을 고릅니다.

한계 — 서브셋이 섞인 구간은 완전히 복원되지 않습니다. 대소문자 정보가 사라지기도 합니다.
복원본은 검색용이며, 인용은 반드시 원본 PDF를 보고 합니다.
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
    # 제어문자가 공백 자리를 차지하는 경우가 있어 먼저 공백으로 바꿉니다.
    raw = CTRL.sub(" ", raw)
    return decode_text(raw)


def density(t):
    w = len(t.split())
    return (len(EN.findall(t)) / w) if w else 0.0


def looks_broken(t, min_chars=3000, threshold=0.02):
    return len(t) >= min_chars and density(t) < threshold
