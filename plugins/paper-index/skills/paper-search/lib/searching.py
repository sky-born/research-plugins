# -*- coding: utf-8 -*-
"""Full-text search — what is actually searched is `_fulltext/*.txt`.

The search **depth** is adjustable. Pouring out every matching paper with its text costs far more
than scanning the whole library, so the default is
**scan everything + limit the output**.

- The scan covers everything by default → the counts of matching papers and occurrences are exact
- Only the output is cut to the top N papers → the rest get one line each, after that only a count
- With `stop_after` the scan itself stops early (for very large libraries;
  the statistics then become lower bounds, and the output says so)

Full text and query terms both go through `textnorm.norm_text` before comparison — `reflow` also finds the PDF ligature `reﬂow`.
"""
import json, os, re

from .textnorm import norm_text


def load_rows(paths):
    if not os.path.exists(paths["json"]):
        return []
    return json.load(open(paths["json"], encoding="utf-8"))


def _flat(path):
    return re.sub(r"\s+", " ", norm_text(open(path, encoding="utf-8", errors="ignore").read()))


def _snippets(path, pats, limit, context):
    """Extract snippets only for the papers to be shown (lazy extraction)."""
    if limit <= 0:
        return []
    flat = _flat(path)
    out, shown = [], 0
    for pt in pats:
        for m in pt.finditer(flat):
            s = max(0, m.start() - context)
            e = min(len(flat), m.end() + context)
            out.append(flat[s:e])
            shown += 1
            if shown >= limit:
                return out
    return out


def _tag_filter(rows, tag, aliases):
    """Rows with a tag that contains `tag` (ignoring case), under its own name or any name it was renamed from or to."""
    q = tag.lower()
    back = {}
    for old, new in (aliases or {}).items():
        back.setdefault(new, set()).add(old)

    def names(t):
        cur = (aliases or {}).get(t, t)
        return {t, cur} | back.get(cur, set())
    return [r for r in rows if any(q in n.lower() for t in r["tags"] for n in names(t))]


def search(paths, terms, any_of=False, tag="", year="", snippets=3, context=120,
           max_docs=0, brief_docs=12, stop_after=0, count_only=False, tag_aliases=None):
    """Returns (rows, hits, stats).

    tag_aliases: {old tag name: current name} (tagging.tag_aliases) — `tag` matches either name
    max_docs   : papers printed in detail with snippets (0 = no limit)
    brief_docs : papers listed one line each after the detailed ones (-1 = all the rest)
    stop_after : stop scanning after this many matches (0 = to the end — exact statistics)
    count_only : count papers and occurrences only; no snippets
    """
    rows = load_rows(paths)
    if tag:
        rows = _tag_filter(rows, tag, tag_aliases)
    if year:
        m = re.match(r"(\d{4})(?:-(\d{4}))?$", year)
        if m:
            lo, hi = m.group(1), m.group(2) or m.group(1)
            rows = [r for r in rows if r.get("year") and lo <= r["year"] <= hi]
    if not terms:
        return rows, [], {}

    pats = [re.compile(norm_text(t), re.I) for t in terms]
    matched = []
    scanned = 0
    stopped = False
    for r in rows:
        p = os.path.join(paths["fulltext"], r["txt"])
        if not os.path.exists(p):
            continue
        scanned += 1
        counts = [len(pt.findall(_flat(p))) for pt in pats]
        ok = any(counts) if any_of else all(counts)
        if ok:
            matched.append((sum(counts), r, counts, p))
            if stop_after and len(matched) >= stop_after:
                stopped = True
                break
    matched.sort(key=lambda x: -x[0])

    stats = {
        "scanned": scanned,
        "matched": len(matched),
        "occurrences": sum(m[0] for m in matched),
        "stopped_early": stopped,
        "count_only": bool(count_only),
        "brief": [],
        "hidden": 0,
    }

    if count_only:
        return rows, [], stats

    n_full = len(matched) if not max_docs else min(max_docs, len(matched))
    hits = [(total, r, counts, _snippets(p, pats, snippets, context))
            for total, r, counts, p in matched[:n_full]]
    rest = matched[n_full:]
    n_brief = len(rest) if brief_docs < 0 else min(brief_docs, len(rest))
    stats["brief"] = [(t, r, c) for t, r, c, _ in rest[:n_brief]]
    stats["hidden"] = len(rest) - n_brief
    return rows, hits, stats


def _trim(s, n=64):
    s = (s or "").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def format_hits(terms, rows, hits, stats=None):
    stats = stats or {}
    out = []
    for total, r, counts, snip in hits:
        out.append("=" * 100)
        out.append(f"{r['id']} [{r.get('year','')}] {r['title']}")
        out.append(f"    {r.get('author') or '-'} · {r.get('journal') or '-'}" +
                   (f" · doi:{r['doi']}" if r.get("doi") else ""))
        out.append(f"    file: {r['rel']}")
        out.append("    hits: " + ", ".join(f"{t}={c}" for t, c in zip(terms, counts)))
        if r.get("note"):
            out.append(f"    ※ {r['note']}")
        for s in snip:
            out.append(f"      … {s} …")

    brief = stats.get("brief") or []
    if brief:
        out.append("-" * 100)
        out.append(f"The next {len(brief)} papers are listed only (no snippets)")
        for total, r, counts in brief:
            out.append(f"  {r['id']} [{r.get('year','') or '----'}] {total:>4}x  {_trim(r['title'])}")

    out.append("=" * 100)
    if not stats:
        out.append(f"Matched {len(hits)} papers (of {len(rows)} searched)")
        return "\n".join(out)

    matched, scanned = stats.get("matched", 0), stats.get("scanned", len(rows))
    pct = f" ({matched * 100 // scanned}%)" if scanned else ""
    if stats.get("stopped_early"):
        out.append(f"Of {len(rows)} papers, scanned {scanned} · matched {matched} · "
                   f"{stats.get('occurrences', 0)} occurrences in total"
                   "  [stopped early — there are more matches than this]")
    else:
        out.append(f"Searched {scanned} papers · matched {matched} of them{pct} · "
                   f"{stats.get('occurrences', 0)} occurrences in total")

    if matched == 0:
        out.append("No matches. Spelling variants (hyphens, spaces, subscripts) or the limits of phrase search may be the cause; "
                   "split the terms into single words and try once more.")
    elif stats.get("count_only"):
        out.append("Counts only (no text opened). For evidence sentences, run again with `--depth focus`.")
    else:
        hidden = stats.get("hidden", 0)
        parts = [f"detail: {len(hits)} papers"]
        if brief:
            parts.append(f"list: {len(brief)} papers")
        if hidden:
            parts.append(f"not shown: {hidden} papers")
        out.append(" · ".join(parts) +
                   ("   → to see more, `--depth full` (or `--max-docs N`)" if hidden or brief else ""))
    return "\n".join(out)
