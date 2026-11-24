#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""원고의 인용 표기를 뽑아 문헌 인덱스와 대조합니다.

    python3 citecheck.py [--config citecheck.config.json] [--out 결과.md]

무엇을 하는가
    1. 원고 파일(들)에서 인용 표기를 정규식으로 추출
    2. 각 인용을 papers_index.json 과 대조 (제1저자 + 제목 유사도)
    3. 보유 / 미보유 / 모호 로 분류해 표로 출력

무엇을 하지 않는가
    - 참고문헌 서지 형식을 만들지 않습니다. 형식은 분야·저널마다 다릅니다.
    - 매칭 결과를 원고에 자동 반영하지 않습니다. 판단은 사람이 합니다.

인용 표기 형식만 config 에서 바꾸면 다른 프로젝트에도 그대로 쓸 수 있습니다.
"""
import argparse, difflib, glob, json, os, re, sys, unicodedata


def norm(s):
    # 색인 제목에 남은 PDF 합자(Eﬀect · solidiﬁcation)를 풀고 비교합니다. 이 템플릿은 프로젝트에 복사해 쓰므로
    # 플러그인 lib/textnorm 을 가져오지 않고 NFKC 를 직접 겁니다 — 영숫자만 남기는 비교라 차이는 분수(¼) 정도입니다.
    return re.sub(r"[^a-z0-9가-힣]", "", unicodedata.normalize("NFKC", s or "").lower())


def load_cfg(path):
    if not os.path.exists(path):
        sys.exit(f"설정이 없습니다: {path}\n  config.example.json 을 복사해 고치십시오.")
    return json.load(open(path, encoding="utf-8"))


def collect(cfg, base):
    pats = [re.compile(p) for p in cfg["citation_patterns"]]
    cites = []
    for g in cfg["manuscripts"]:
        for f in sorted(glob.glob(os.path.join(base, g), recursive=True)):
            text = open(f, encoding="utf-8", errors="ignore").read()
            for pat in pats:
                for m in pat.finditer(text):
                    d = m.groupdict()
                    cites.append(dict(
                        raw=m.group(0),
                        num=(d.get("num") or "").strip(),
                        author=(d.get("author") or "").strip(),
                        title=(d.get("title") or "").strip(),
                        file=os.path.relpath(f, base),
                    ))
    # 같은 인용이 여러 번 나오면 하나로
    seen, uniq = set(), []
    for c in cites:
        k = (c["num"], norm(c["author"]), norm(c["title"])[:40])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    return uniq


def match(cite, rows, threshold=0.62):
    """제1저자가 같은 항목 중 제목 유사도가 가장 높은 것을 고릅니다."""
    a = norm(cite["author"])
    t = norm(cite["title"])
    cand = [r for r in rows if a and norm(r.get("author", "")).startswith(a[:5])] or rows
    # 제목 없이 저자만 있는 인용 — 후보가 하나뿐이면 그것으로 보되 확신은 낮춥니다.
    if not t:
        return (cand[0], threshold) if a and len(cand) == 1 else (None, 0.0)
    best, score = None, 0.0
    for r in cand:
        s = difflib.SequenceMatcher(None, t, norm(r["title"])[:len(t) + 20]).ratio() if t else 0.0
        if a and norm(r.get("author", "")).startswith(a[:5]):
            s += 0.15
        if s > score:
            best, score = r, s
    return (best, score) if score >= threshold else (None, score)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="citecheck.config.json")
    ap.add_argument("--out")
    a = ap.parse_args()
    cfg = load_cfg(a.config)
    base = os.path.dirname(os.path.abspath(a.config))
    idx = cfg["papers_index"]
    if not os.path.isabs(idx):
        idx = os.path.normpath(os.path.join(base, idx))
    if not os.path.exists(idx):
        sys.exit(f"인덱스가 없습니다: {idx}")
    rows = json.load(open(idx, encoding="utf-8"))

    cites = collect(cfg, base)
    th = cfg.get("threshold", 0.62)
    for c in cites:
        r, s = match(c, rows, th)
        c["score"] = round(s, 2)
        c["hit"] = r

    # 같은 번호의 인용이 어딘가에서 제목까지 붙어 매칭됐다면 그 결과를 공유합니다.
    # (본문에서 두 번째부터는 `[1 Liu]` 처럼 제목을 생략하는 경우가 많습니다.)
    best_by_num = {}
    for c in cites:
        if c["num"] and c["hit"]:
            b = best_by_num.get(c["num"])
            if not b or c["score"] > b["score"]:
                best_by_num[c["num"]] = c
    merged, seen_num = [], set()
    for c in cites:
        if c["num"] and c["num"] in best_by_num:
            if c["num"] in seen_num:
                continue
            seen_num.add(c["num"])
            merged.append(best_by_num[c["num"]])
        else:
            merged.append(c)
    cites = merged

    have, miss, vague = [], [], []
    for c in cites:
        if c["hit"] and c["score"] >= th + 0.12:
            have.append(c)
        elif c["hit"]:
            vague.append(c)
        else:
            miss.append(c)

    L = ["# 인용 ↔ 보유 문헌 대조", "",
         f"원고에서 뽑은 인용 **{len(cites)}건** · 보유 {len(have)} · 확인필요 {len(vague)} · 미보유 {len(miss)}",
         "",
         "> 매칭은 제1저자와 제목 유사도로 한 **추정**입니다. 인용을 확정하기 전에 원본 PDF를 확인하십시오.",
         "", "---", "", f"## 보유 ({len(have)}건)", "",
         "| 인용 | 매칭 | 제목 | 파일 |", "|---|---|---|---|"]
    for c in have:
        L.append(f"| `{c['raw'][:44]}` | {c['hit']['id']} | {c['hit']['title'][:60]} | `{c['hit']['rel']}` |")
    L += ["", f"## 확인 필요 — 매칭이 약함 ({len(vague)}건)", "",
          "| 인용 | 후보 | 유사도 | 제목 |", "|---|---|---|---|"]
    for c in vague:
        L.append(f"| `{c['raw'][:44]}` | {c['hit']['id']} | {c['score']} | {c['hit']['title'][:55]} |")
    L += ["", f"## 미보유 — 라이브러리에 없음 ({len(miss)}건)", "",
          "| 인용 | 저자 | 제목 | 원고 |", "|---|---|---|---|"]
    for c in miss:
        L.append(f"| `{c['raw'][:44]}` | {c['author']} | {c['title'][:50]} | {c['file']} |")
    out = "\n".join(L) + "\n"

    if a.out:
        open(a.out, "w", encoding="utf-8").write(out)
        print(f"저장: {a.out}")
    else:
        print(out)
    print(f"\n인용 {len(cites)}건 · 보유 {len(have)} · 확인필요 {len(vague)} · 미보유 {len(miss)}")


if __name__ == "__main__":
    main()
