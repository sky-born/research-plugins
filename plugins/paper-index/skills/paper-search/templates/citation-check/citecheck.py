#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract the citations from a manuscript and match them against the literature index.

    python3 citecheck.py [--config citecheck.config.json] [--out result.md]

What it does
    1. Extracts citations from the manuscript file(s) with regexes
    2. Matches each citation against papers_index.json (first author + title similarity)
    3. Sorts them into owned / missing / unclear and prints tables

What it does not do
    - It does not build reference-list entries. The format differs by field and journal.
    - It does not apply the matches to the manuscript. A person decides.

Change only the citation format in the config and it works for other projects as is.
"""
import argparse, difflib, glob, json, os, re, sys, unicodedata


def norm(s):
    # Unfold PDF ligatures left in index titles (Eﬀect · solidiﬁcation) before comparing. This template is copied into
    # projects, so it applies NFKC itself instead of importing the plugin's lib/textnorm — the comparison keeps only
    # letters and digits, so the difference is about fractions (¼) only.
    return re.sub(r"[^a-z0-9가-힣]", "", unicodedata.normalize("NFKC", s or "").lower())


def load_cfg(path):
    if not os.path.exists(path):
        sys.exit(f"Config not found: {path}\n  Copy config.example.json and edit it.")
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
    # the same citation appearing several times counts once
    seen, uniq = set(), []
    for c in cites:
        k = (c["num"], norm(c["author"]), norm(c["title"])[:40])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    return uniq


def match(cite, rows, threshold=0.62):
    """Pick the entry with the highest title similarity among those with the same first author."""
    a = norm(cite["author"])
    t = norm(cite["title"])
    cand = [r for r in rows if a and norm(r.get("author", "")).startswith(a[:5])] or rows
    # A citation with an author but no title — if there is only one candidate, take it, with lower confidence.
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
        sys.exit(f"Index not found: {idx}")
    rows = json.load(open(idx, encoding="utf-8"))

    cites = collect(cfg, base)
    th = cfg.get("threshold", 0.62)
    for c in cites:
        r, s = match(c, rows, th)
        c["score"] = round(s, 2)
        c["hit"] = r

    # If a citation with the same number was matched somewhere with its title, share that result.
    # (From the second time on, the text often leaves the title out, as in `[1 Liu]`.)
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

    L = ["# Citations ↔ owned papers", "",
         f"Citations taken from the manuscript: **{len(cites)}** · owned {len(have)} · needs checking {len(vague)} · missing {len(miss)}",
         "",
         "> The matching is an **estimate** from the first author and title similarity. "
         "Check the original PDF before confirming a citation.",
         "", "---", "", f"## Owned ({len(have)})", "",
         "| Citation | Match | Title | File |", "|---|---|---|---|"]
    for c in have:
        L.append(f"| `{c['raw'][:44]}` | {c['hit']['id']} | {c['hit']['title'][:60]} | `{c['hit']['rel']}` |")
    L += ["", f"## Needs checking — weak match ({len(vague)})", "",
          "| Citation | Candidate | Similarity | Title |", "|---|---|---|---|"]
    for c in vague:
        L.append(f"| `{c['raw'][:44]}` | {c['hit']['id']} | {c['score']} | {c['hit']['title'][:55]} |")
    L += ["", f"## Missing — not in the library ({len(miss)})", "",
          "| Citation | Author | Title | Manuscript |", "|---|---|---|---|"]
    for c in miss:
        L.append(f"| `{c['raw'][:44]}` | {c['author']} | {c['title'][:50]} | {c['file']} |")
    out = "\n".join(L) + "\n"

    if a.out:
        open(a.out, "w", encoding="utf-8").write(out)
        print(f"Saved: {a.out}")
    else:
        print(out)
    print(f"\nCitations {len(cites)} · owned {len(have)} · to check {len(vague)} · missing {len(miss)}")


if __name__ == "__main__":
    main()
