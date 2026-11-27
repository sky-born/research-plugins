# -*- coding: utf-8 -*-
"""Re-match index paths after file names change.

Reference managers (ReadCube, Zotero and others) add and remove suffixes such as `_1`, `_2`, or
download everything again when switching to the cloud. Each time, all index paths go out of step.

Matching runs in three steps.
  0) Unchanged paths — every entry whose file is still there keeps it first, so an entry whose file is gone never
     takes the file of an entry that is still there.
  1) Name normalization — among the files left, strip suffixes and supplement markers, then compare the first
     34 characters. Most renames are resolved here.
  2) Content comparison — for the rest, compare the start of the cached text. This works only while the old cache and
     the new file's extraction come from the same extractor.

An entry whose path changed keeps its own cache under the new name (`carry` in the result; `extract.carry` moves it).
"""
import os, re
from . import extract, textio


def norm_key(rel, n=34):
    rel = textio.nfc(rel)
    d = os.path.dirname(rel)
    b = os.path.splitext(os.path.basename(rel))[0]
    b = re.sub(r"_\d+$", "", b)
    sup = "_supplement" in b
    b = re.sub(r"_supplement.*$", "", b)
    b = re.sub(r"[^0-9a-z%s]" % textio.HANGUL, "", b.lower())[:n]
    return d + "|" + b + ("#SUP" if sup else "")      # the marker goes after the cut, so a long name keeps it


def resync(rows, cfg, ft_dir, verbose=True):
    """Re-match `rows` to the library. Returns rows (kept, paths updated), dropped, collided, new (files no entry has),
    carry ((row, old txt) for each kept entry whose cache name changed) and shared (rows matched by a name key that
    several files or entries share — worth checking against their PDFs)."""
    cur = extract.scan(cfg["library"])
    curset = set(cur)
    curmap = {}
    for rel in cur:
        curmap.setdefault(norm_key(rel), []).append(rel)

    matched, leftover, used = {}, [], set()
    for r in rows:
        if r["rel"] in curset:
            matched[id(r)] = r["rel"]
            used.add(r["rel"])
    waiting = [r for r in rows if id(r) not in matched]
    keys = {id(r): norm_key(r["rel"]) for r in waiting}
    rowcount = {}
    for k in keys.values():
        rowcount[k] = rowcount.get(k, 0) + 1
    shared_ids = set()
    for r in waiting:
        k = keys[id(r)]
        cand = [x for x in curmap.get(k, []) if x not in used]
        if len(cand) == 1:
            matched[id(r)] = cand[0]
            used.add(cand[0])
            if len(curmap[k]) > 1 or rowcount[k] > 1:
                shared_ids.add(id(r))
        else:
            leftover.append(r)

    # step 2: content comparison
    if leftover:
        free = [x for x in cur if x not in used]
        newtext = {}
        for rel in free:
            p = extract.cache(ft_dir, rel)
            if not os.path.exists(p):
                p = os.path.join(ft_dir, extract.txtname(rel))
                try:
                    extract.run_extractor(cfg["pdftotext"], extract.source(cfg["library"], rel), p, timeout=60)
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
                matched[id(r)] = hit
                used.add(hit)
            else:
                still.append(r)
        leftover = still

    out, dropped, old_txt = [], [], {}
    for r in rows:
        rel = matched.get(id(r))
        if not rel:
            dropped.append(r)
            continue
        old_txt[id(r)] = r.get("txt", "")
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

    carry = [(r, old_txt[id(r)]) for r in deduped if old_txt[id(r)] and old_txt[id(r)] != r["txt"]]
    shared = [r for r in deduped if id(r) in shared_ids]
    newfiles = [x for x in cur if x not in seen]
    return dict(rows=deduped, dropped=dropped, collided=collided, new=newfiles, carry=carry, shared=shared)
