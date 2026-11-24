# -*- coding: utf-8 -*-
"""코퍼스 어휘 기반 최대일치 단어 분리.

인코딩이 깨진 PDF를 복원하면 단어 사이 공백이 사라져 붙는 경우가 있습니다.
사전을 따로 두는 대신 **같은 라이브러리의 정상 문서들에서 어휘를 뽑아** 씁니다.
분야 용어가 자동으로 포함되므로 일반 영어사전보다 잘 맞습니다.
"""
import json, math, os, re, collections


def build_vocab(texts, min_count=3, limit=350):
    v = collections.Counter()
    for i, t in enumerate(texts):
        if i >= limit:
            break
        v.update(w.lower() for w in re.findall(r"[A-Za-z]{2,20}", t[:80000]))
    return {w: c for w, c in v.items() if c >= min_count}


class Splitter:
    def __init__(self, vocab):
        tot = sum(vocab.values()) or 1
        self.cost = {w: math.log(tot / c) for w, c in vocab.items()}
        self.maxw = max((len(w) for w in vocab), default=1)

    def __call__(self, s):
        if len(s) < 9 or not s.isalpha():
            return s
        low = s.lower()
        n = len(low)
        best = [0.0] + [float("inf")] * n
        back = [0] * (n + 1)
        for i in range(1, n + 1):
            for j in range(max(0, i - self.maxw), i):
                w = low[j:i]
                c = self.cost.get(w)
                if c is None:
                    c = 22.0 if i - j == 1 else None
                elif i - j == 1 and w not in "ai":
                    c = 22.0
                if c is None:
                    continue
                if best[j] + c < best[i]:
                    best[i] = best[j] + c
                    back[i] = j
        if best[n] == float("inf"):
            return s
        out = []
        i = n
        while i > 0:
            j = back[i]
            out.append(s[j:i])
            i = j
        return " ".join(reversed(out))

    def text(self, t):
        return re.sub(r"[A-Za-z]{9,}", lambda m: self(m.group(0)), t)


def load_or_build(vocab_path, texts):
    if os.path.exists(vocab_path):
        return json.load(open(vocab_path, encoding="utf-8"))
    v = build_vocab(texts)
    os.makedirs(os.path.dirname(vocab_path), exist_ok=True)
    json.dump(v, open(vocab_path, "w", encoding="utf-8"), ensure_ascii=False)
    return v
