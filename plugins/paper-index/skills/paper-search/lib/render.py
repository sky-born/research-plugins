# -*- coding: utf-8 -*-
"""Writing the index files — papers_index.{json,md,csv}"""
import collections, csv, datetime, difflib, json, os, re

from . import textio
from .textnorm import norm_text

YEAR_UNKNOWN = "year unknown"


def _norm(s):
    # NFC first so Hangul stays in the key; unfold ligatures in index titles (Eﬀect) before comparing
    return re.sub(r"[^a-z0-9%s]" % textio.HANGUL, "", norm_text(textio.nfc(s)).lower())


def duplicate_groups(rows, ratio=0.93):
    """Narrow duplicate candidates by blocking, then measure similarity.

    Comparing every pair (O(n^2) SequenceMatcher) gets slow with only a few hundred papers.
    Only entries with the same DOI, or the same first 12 characters of the normalized title, are compared.
    """
    buckets = collections.defaultdict(list)
    for r in rows:
        n = _norm(r["title"])
        if r.get("doi"):
            buckets["doi:" + r["doi"].lower()].append(r)
        buckets["t:" + n[:12]].append(r)

    pairs = set()
    for key, lst in buckets.items():
        if len(lst) < 2 or len(lst) > 60:
            continue
        for i, a in enumerate(lst):
            for b in lst[i + 1:]:
                same = (a.get("doi") and a["doi"] == b.get("doi")) or \
                       difflib.SequenceMatcher(None, _norm(a["title"]), _norm(b["title"])).ratio() > ratio
                if same:
                    pairs.add(tuple(sorted((a["id"], b["id"]))))

    adj = collections.defaultdict(set)
    for x, y in pairs:
        adj[x].add(y)
        adj[y].add(x)
    byid = {r["id"]: r for r in rows}
    seen, groups = set(), []
    for r in rows:
        if r["id"] in seen or r["id"] not in adj:
            continue
        stack, comp = [r["id"]], []
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.append(byid[cur])
            stack.extend(adj[cur] - seen)
        if len(comp) > 1:
            comp.sort(key=lambda x: x["id"])
            groups.append(comp)
    return groups


def assign_ids(rows, prefix="P"):
    rows.sort(key=lambda r: (r.get("year") or "0000", (r.get("author") or "").lower(),
                             r["file"].lower()))
    width = max(3, len(str(len(rows))))
    for i, r in enumerate(rows, 1):
        r["id"] = f"{prefix}{i:0{width}d}"
    return rows


def write_json(rows, path):
    json.dump(rows, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def backup_copy(path, folder):
    """Copy `path` byte for byte into `folder` as <stem>_<YYYY-MM-DD><ext>. Never overwrites: a name already
    taken gets _1, _2, ... (exclusive creation). Returns the new path; raises OSError if it cannot be written."""
    os.makedirs(folder, exist_ok=True)
    stem, ext = os.path.splitext(os.path.basename(path))
    data = open(path, "rb").read()
    base = f"{stem}_{datetime.date.today().isoformat()}"
    for i in range(1000):
        target = os.path.join(folder, base + (f"_{i}" if i else "") + ext)
        try:
            with open(target, "xb") as f:
                f.write(data)
            return target
        except FileExistsError:
            continue
    raise OSError(f"No free backup name for {base}{ext} in {folder}")


def write_csv(rows, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ID", "year", "first author", "title", "source", "DOI", "tags", "folder", "file",
                    "full-text cache", "note"])
        for r in rows:
            w.writerow([r["id"], r["year"], r["author"], r["title"], r["journal"], r["doi"],
                        "; ".join(r["tags"]), r["folder"], r["file"], r["txt"], r.get("note", "")])


def _line(r, with_tags=False):
    meta = " · ".join([x for x in [r.get("author"), r.get("year"), r.get("journal")] if x])
    o = f"- `{r['id']}` **{r['title']}**"
    if meta:
        o += f"  \n  {meta}"
    if r.get("doi"):
        o += f" · doi:{r['doi']}"
    o += f"  \n  `{r['rel']}`"
    if with_tags:
        o += f" · tags: {', '.join(r['tags'][:3])}"
    if r.get("note"):
        o += f"  \n  {r['note']}"
    return o


def write_md(rows, path, cfg, tag_order):
    today = datetime.date.today().isoformat()
    groups = duplicate_groups(rows)
    name = cfg.get("name") or os.path.basename(cfg["library"].rstrip("/\\"))
    L = [f"# Literature index — {name}", "",
         f"Generated {today} · **{len(rows)} papers** · source `{cfg['library']}` (**read-only**)", "",
         "The full text is cached as `.txt` files in `_fulltext/`. "
         "For keyword searches, `papertool.py search` or a grep of `_fulltext/` is fastest.", "",
         "> Titles, authors and journals are extracted automatically from the PDF text. "
         "**Check them against the original PDF before confirming a citation.**", "",
         "---", "", "## Contents", "",
         "- [By topic](#by-topic)", "- [All papers by year](#all-papers-by-year)",
         "- [Duplicate files](#duplicate-files)", "- [Needs attention](#needs-attention)", "", "---", "", "## By topic", ""]
    byt = collections.defaultdict(list)
    for r in rows:
        for t in r["tags"]:
            byt[t].append(r)
    order = [t for t in tag_order if t in byt] + [t for t in byt if t not in tag_order]
    for t in order:
        lst = sorted(byt[t], key=lambda r: (r.get("year") or "0000"))
        L += [f"### {t} ({len(lst)})", ""] + [_line(r) for r in lst] + [""]

    L += ["---", "", "## All papers by year", ""]
    byy = collections.defaultdict(list)
    for r in rows:
        byy[r.get("year") or YEAR_UNKNOWN].append(r)
    for y in sorted(byy, key=lambda x: (x == YEAR_UNKNOWN, x)):
        L += [f"### {y} ({len(byy[y])})", ""] + \
             [_line(r, True) for r in sorted(byy[y], key=lambda r: (r.get("author") or "").lower())] + [""]

    L += ["---", "", "## Duplicate files", "",
          "The same paper is saved as several files. When citing, use only the main ID.", "",
          "| Main | Duplicates | Title |", "|---|---|---|"]
    for g in groups:
        L.append(f"| `{g[0]['id']}` | {', '.join('`' + x['id'] + '`' for x in g[1:])} | {g[0]['title'][:80]} |")

    L += ["", "---", "", "## Needs attention", "",
          "Entries whose file name does not match the content, or whose full-text extraction has a problem. "
          "**Citing on the strength of the file name leads to a wrong citation.**", "",
          "| ID | File | Title (from the content) | Note |", "|---|---|---|---|"]
    for r in rows:
        if r.get("note"):
            L.append(f"| {r['id']} | `{r['file']}` | {r['title'][:70]} | {r['note']} |")
    L.append("")
    open(path, "w", encoding="utf-8").write("\n".join(L))
    return len(groups)
