# -*- coding: utf-8 -*-
"""전문 검색 — 실제 검색 대상은 `_fulltext/*.txt` 입니다.

검색 **깊이(depth)** 를 조절할 수 있습니다. 라이브러리 전체를 훑는 비용보다
적중한 문헌을 전부 본문과 함께 쏟아내는 비용이 훨씬 크기 때문에,
기본 동작은 **전수 스캔 + 제한 출력** 입니다.

- 스캔은 기본적으로 전체를 돕니다 → 적중 편수·출현 횟수 통계가 정확합니다
- 출력만 상위 N편으로 자릅니다   → 나머지는 한 줄 요약, 그 뒤는 편수만
- `stop_after` 를 주면 스캔 자체를 조기에 끊습니다 (초대형 라이브러리용,
  대신 통계가 하한값이 되므로 그렇다고 표시합니다)

전문과 검색어는 모두 `textnorm.norm_text` 를 거쳐 대조합니다 — `reflow` 가 PDF 합자 `reﬂow` 도 찾습니다.
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
    """표시할 문헌에 대해서만 스니펫을 뽑습니다 (지연 추출)."""
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


def search(paths, terms, any_of=False, tag="", year="", snippets=3, context=120,
           max_docs=0, brief_docs=12, stop_after=0, count_only=False):
    """반환: (rows, hits, stats)

    max_docs   : 본문 스니펫까지 상세 출력할 문헌 수 (0 = 무제한)
    brief_docs : 상세 출력 뒤에 한 줄 요약으로 덧붙일 문헌 수 (-1 = 나머지 전부)
    stop_after : 이만큼 적중하면 스캔 중단 (0 = 끝까지 — 통계 정확)
    count_only : 편수·횟수만 세고 스니펫은 뽑지 않음
    """
    rows = load_rows(paths)
    if tag:
        rows = [r for r in rows if any(tag.lower() in t.lower() for t in r["tags"])]
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
        out.append(f"    파일: {r['rel']}")
        out.append("    적중: " + ", ".join(f"{t}={c}" for t, c in zip(terms, counts)))
        if r.get("note"):
            out.append(f"    ※ {r['note']}")
        for s in snip:
            out.append(f"      … {s} …")

    brief = stats.get("brief") or []
    if brief:
        out.append("-" * 100)
        out.append(f"이하 {len(brief)}편은 목록만 (본문 스니펫 생략)")
        for total, r, counts in brief:
            out.append(f"  {r['id']} [{r.get('year','') or '----'}] {total:>4}회  {_trim(r['title'])}")

    out.append("=" * 100)
    if not stats:
        out.append(f"총 {len(hits)}편 적중 (검색 대상 {len(rows)}편)")
        return "\n".join(out)

    matched, scanned = stats.get("matched", 0), stats.get("scanned", len(rows))
    pct = f" ({matched * 100 // scanned}%)" if scanned else ""
    if stats.get("stopped_early"):
        out.append(f"검색 대상 {len(rows)}편 중 {scanned}편까지 스캔 · 적중 {matched}편 · "
                   f"총 출현 {stats.get('occurrences', 0)}회"
                   "  [조기 중단 — 실제 적중은 이보다 많습니다]")
    else:
        out.append(f"검색 대상 {scanned}편 · 적중 {matched}편{pct} · "
                   f"총 출현 {stats.get('occurrences', 0)}회")

    if matched == 0:
        out.append("0건입니다. 표기 변형(하이픈·공백·아래첨자)이나 구(句) 검색 한계일 수 있으니 "
                   "단어를 쪼개 한 번 더 시도해 보십시오.")
    elif stats.get("count_only"):
        out.append("빈도만 셈 (본문 미개봉). 근거 문장이 필요하면 `--depth focus` 로 다시 돌리십시오.")
    else:
        hidden = stats.get("hidden", 0)
        parts = [f"상세 {len(hits)}편"]
        if brief:
            parts.append(f"목록 {len(brief)}편")
        if hidden:
            parts.append(f"미표시 {hidden}편")
        out.append(" · ".join(parts) +
                   ("   → 더 보려면 `--depth full` (또는 `--max-docs N`)" if hidden or brief else ""))
    return "\n".join(out)
