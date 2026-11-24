# -*- coding: utf-8 -*-
"""파일명이 바뀌었을 때 인덱스 경로를 다시 맞춥니다.

문헌관리 프로그램(ReadCube, Zotero 등)은 `_1`, `_2` 같은 접미사를 붙였다 떼거나
클라우드 전환 시 전체를 다시 내려받습니다. 그때마다 인덱스 경로가 통째로 어긋납니다.

2단계로 맞춥니다.
  1) 이름 정규화 — 접미사·supplement 표식을 걷어낸 뒤 앞 34자를 비교. 대부분 여기서 해결됩니다.
  2) 내용 대조 — 남은 것은 캐시 텍스트 앞부분을 비교합니다. 파일명이 아니라 내용으로 판단합니다.
"""
import os, re
from . import extract


def norm_key(rel, n=34):
    d = os.path.dirname(rel)
    b = os.path.splitext(os.path.basename(rel))[0]
    b = re.sub(r"_\d+$", "", b)
    b = re.sub(r"_supplement.*$", "#SUP", b)
    b = re.sub(r"[^0-9a-z가-힣#]", "", b.lower())[:n]
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

    # 2단계: 내용 대조
    if leftover:
        free = [x for x in cur if x not in used]
        newtext = {}
        for rel in free:
            p = os.path.join(ft_dir, extract.txtname(rel))
            if not os.path.exists(p):
                import subprocess
                try:
                    subprocess.run([cfg["pdftotext"], "-q",
                                    os.path.join(cfg["library"], rel), p], timeout=60)
                except Exception:
                    pass
            newtext[rel] = (open(p, encoding="utf-8", errors="ignore").read()[:1200]
                            if os.path.exists(p) else "")
        still = []
        for r in leftover:
            p = os.path.join(ft_dir, r["txt"])
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

    # 같은 파일에 두 항목이 붙으면 중복본이 삭제된 것
    seen, deduped, collided = set(), [], []
    for r in out:
        if r["rel"] in seen:
            collided.append(r)
            continue
        seen.add(r["rel"])
        deduped.append(r)

    newfiles = [x for x in cur if x not in seen]
    return dict(rows=deduped, dropped=dropped, collided=collided, new=newfiles)
