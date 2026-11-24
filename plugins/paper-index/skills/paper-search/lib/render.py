# -*- coding: utf-8 -*-
"""인덱스 산출물 생성 — papers_index.{json,md,csv}"""
import collections, csv, datetime, difflib, json, os, re

from .textnorm import norm_text


def _norm(s):
    return re.sub(r"[^a-z0-9가-힣]", "", norm_text(s).lower())   # 색인 제목의 합자(Eﬀect)를 풀고 비교


def duplicate_groups(rows, ratio=0.93):
    """중복 후보를 블로킹으로 좁힌 뒤 유사도를 잽니다.

    전수 비교(O(n^2) SequenceMatcher)는 수백 편만 되어도 느려집니다.
    같은 DOI, 또는 정규화 제목의 앞 12자가 같은 것끼리만 비교합니다.
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


def write_csv(rows, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ID", "연도", "제1저자", "제목", "출처", "DOI", "태그", "폴더", "파일명", "전문캐시", "비고"])
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
        o += f" · 태그: {', '.join(r['tags'][:3])}"
    if r.get("note"):
        o += f"  \n  {r['note']}"
    return o


def write_md(rows, path, cfg, tag_order):
    today = datetime.date.today().isoformat()
    groups = duplicate_groups(rows)
    name = cfg.get("name") or os.path.basename(cfg["library"].rstrip("/\\"))
    L = [f"# 문헌 인덱스 — {name}", "",
         f"생성일 {today} · 총 **{len(rows)}편** · 원본 `{cfg['library']}` (**읽기 전용**)", "",
         "전문(full text)은 `_fulltext/`에 `.txt`로 캐시되어 있습니다. "
         "키워드 검색은 `papertool.py search` 또는 `_fulltext/` grep 이 가장 빠릅니다.", "",
         "> 제목·저자·저널은 PDF 본문에서 자동 추출한 값입니다. **인용 확정 전에 원본 PDF로 대조하십시오.**", "",
         "---", "", "## 목차", "",
         "- [주제별](#주제별)", "- [연도별 전체 목록](#연도별-전체-목록)",
         "- [중복 파일](#중복-파일)", "- [주의 필요 항목](#주의-필요-항목)", "", "---", "", "## 주제별", ""]
    byt = collections.defaultdict(list)
    for r in rows:
        for t in r["tags"]:
            byt[t].append(r)
    order = [t for t in tag_order if t in byt] + [t for t in byt if t not in tag_order]
    for t in order:
        lst = sorted(byt[t], key=lambda r: (r.get("year") or "0000"))
        L += [f"### {t} ({len(lst)}편)", ""] + [_line(r) for r in lst] + [""]

    L += ["---", "", "## 연도별 전체 목록", ""]
    byy = collections.defaultdict(list)
    for r in rows:
        byy[r.get("year") or "연도미상"].append(r)
    for y in sorted(byy, key=lambda x: (x == "연도미상", x)):
        L += [f"### {y} ({len(byy[y])}편)", ""] + \
             [_line(r, True) for r in sorted(byy[y], key=lambda r: (r.get("author") or "").lower())] + [""]

    L += ["---", "", "## 중복 파일", "",
          "같은 논문이 여러 파일로 저장되어 있습니다. 인용 시 대표 ID 하나만 쓰십시오.", "",
          "| 대표 | 중복 | 제목 |", "|---|---|---|"]
    for g in groups:
        L.append(f"| `{g[0]['id']}` | {', '.join('`' + x['id'] + '`' for x in g[1:])} | {g[0]['title'][:80]} |")

    L += ["", "---", "", "## 주의 필요 항목", "",
          "파일명이 내용과 다르거나, 전문 추출에 문제가 있는 항목입니다. "
          "**파일명을 근거로 인용하면 오인용이 됩니다.**", "",
          "| ID | 파일명 | 제목(내용 기준) | 비고 |", "|---|---|---|---|"]
    for r in rows:
        if r.get("note"):
            L.append(f"| {r['id']} | `{r['file']}` | {r['title'][:70]} | {r['note']} |")
    L.append("")
    open(path, "w", encoding="utf-8").write("\n".join(L))
    return len(groups)
