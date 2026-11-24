# -*- coding: utf-8 -*-
"""PDF 전문 추출 — 원본 폴더는 읽기만 합니다."""
import os, subprocess

from .textnorm import norm_text


def txtname(rel):
    return rel.replace("\\", "/").replace("/", "__")[:-4] + ".txt"


def scan(library):
    """라이브러리 안의 PDF 상대경로 목록."""
    out = []
    for dp, _, fns in os.walk(library):
        for fn in sorted(fns):
            if fn.lower().endswith(".pdf"):
                out.append(os.path.relpath(os.path.join(dp, fn), library).replace("\\", "/"))
    return sorted(out)


def extract_missing(cfg, ft_dir, limit=None, timeout=25, verbose=True):
    """캐시가 없는 PDF만 추출합니다. limit 을 주면 그만큼만 처리하고 남은 수를 돌려줍니다.

    한 번에 다 돌리면 오래 걸리는 환경(에이전트 셸의 호출 타임아웃 등)을 위해
    나눠 실행할 수 있게 만들었습니다.
    """
    os.makedirs(ft_dir, exist_ok=True)
    todo = [rel for rel in scan(cfg["library"])
            if not os.path.exists(os.path.join(ft_dir, txtname(rel)))]
    done, failed = 0, []
    for rel in todo:
        if limit is not None and done >= limit:
            break
        src = os.path.join(cfg["library"], rel)
        dst = os.path.join(ft_dir, txtname(rel))
        try:
            r = subprocess.run([cfg["pdftotext"], "-q", src, dst], timeout=timeout)
            if r.returncode != 0 and not os.path.exists(dst):
                failed.append(rel)
        except Exception:
            failed.append(rel)
        done += 1
        if verbose and done % 25 == 0:
            print(f"  ... {done}/{len(todo)}")
    return dict(done=done, remaining=max(0, len(todo) - done), failed=failed, total=len(todo))


def read_cache(ft_dir, rel):
    """캐시 전문을 글자 정규화해 돌려줍니다(메타데이터 · 태깅용). 캐시 파일 자체는 그대로 둡니다."""
    p = os.path.join(ft_dir, txtname(rel))
    if not os.path.exists(p):
        return ""
    return norm_text(open(p, encoding="utf-8", errors="ignore").read())


def prune_orphans(ft_dir, keep):
    """인덱스에 없는 캐시를 _obsolete/ 로 옮깁니다 (삭제하지 않습니다)."""
    import shutil
    obs = os.path.join(ft_dir, "_obsolete")
    os.makedirs(obs, exist_ok=True)
    n = 0
    for f in os.listdir(ft_dir):
        if f.endswith(".txt") and f not in keep:
            try:
                shutil.move(os.path.join(ft_dir, f), os.path.join(obs, f))
                n += 1
            except Exception:
                pass
    return n
