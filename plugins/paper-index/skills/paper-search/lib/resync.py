# -*- coding: utf-8 -*-
"""Re-match index paths after file names change.

Reference managers (ReadCube, Zotero and others) add and remove suffixes such as `_1`, `_2`, or
download everything again when switching to the cloud. Each time, all index paths go out of step.

Matching runs in two steps.
  1) Name normalization — strip suffixes and supplement markers, then compare the first 34 characters. Most are resolved here.
  2) Content comparison — for the rest, compare the start of the cached text. The decision rests on content, not the file name.
"""
import os, re
from . import extract, textio


def norm_key(rel, n=34):
    rel = textio.nfc(rel)
    d = os.path.dirname(rel)
    b = os.path.splitext(os.path.basename(rel))[0]
    b = re.sub(r"_\d+$", "", b)
    b = re.sub(r"_supplement.*$", "#SUP", b)
    b = re.sub(r"[^0-9a-z%s#]" % textio.HANGUL, "", b.lower())[:n]
    return d + "|" + b


def resync(rows, cfg, ft_dir, verbose=True):
    cur = extract.scan(cfg["library"])
    curset = set(cur)
    curmap = {}
    for rel in cur:
        curmap.setdefault(norm_key(rel), []).append(rel)

    matched, leftover, used = {}, [], set()
    for r in rows:
        if r["rel"] in curset:
            matched[r["id"]] = r["rel"]
            used.add(r["rel"])
            continue
        cand = [x for x in curmap.get(norm_key(r["rel"]), []) if x not in used]
        if len(cand) == 1:
            matched[r["id"]] = cand[0]
            used.add(cand[0])
        else:
            leftover.append(r)

    # step 2: content comparison
    if leftover:
        free = [x for x in cur if x not in used]
        newtext = {}
        for rel in free:
            p = extract.cache(ft_dir, rel)
            if not os.path.exists(p):
                import subprocess
                p = os.path.join(ft_dir, extract.txtname(rel))
                try:
                    subprocess.run([cfg["pdftotext"], "-q",
                                    extract.source(cfg["library"], rel), p], timeout=60)
                except Exception:
                    pass
            newtext[rel] = (open(p, encoding="utf-8", errors="ignore").read()[:1200]
                            if os.path.exists(p) else "")
        still = []
        for r in leftover:
            p = textio.resolve(ft_dir, r["txt"])
            old = open(p, encoding="utf-8", errors="ignore").read()[:1200] if os.path.exists(p) else ""
            hit = None
            if old.strip():
                for rel, nt in newtext.items():
                    if rel in used or not nt.strip():
                        continue
                    if old == nt:
                        hit = rel
                        break
            if hit:
                matched[r["id"]] = hit
                used.add(hit)
            else:
                still.append(r)
        leftover = still

    out, dropped = [], []
    for r in rows:
        rel = matched.get(r["id"])
        if not rel:
            dropped.append(r)
            continue
        r["rel"] = rel
        r["folder"] = os.path.dirname(rel) or "(root)"
        r["file"] = os.path.basename(rel)
        r["txt"] = extract.txtname(rel)
        y = os.path.dirname(rel)
        if re.fullmatch(r"(19|20)\d{2}", y):
            r["year"] = y
        out.append(r)

    # two entries on the same file mean a duplicate file was deleted
    seen, deduped, collided = set(), [], []
    for r in out:
        if r["rel"] in seen:
            collided.append(r)
            continue
        seen.add(r["rel"])
        deduped.append(r)

    newfiles = [x for x in cur if x not in seen]
    return dict(rows=deduped, dropped=dropped, collided=collided, new=newfiles)
