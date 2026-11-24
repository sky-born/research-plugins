# -*- coding: utf-8 -*-
"""PDF full-text extraction — the source folder is only read."""
import os, subprocess

from .textnorm import norm_text


def txtname(rel):
    return rel.replace("\\", "/").replace("/", "__")[:-4] + ".txt"


def scan(library):
    """Relative paths of the PDFs in the library."""
    out = []
    for dp, _, fns in os.walk(library):
        for fn in sorted(fns):
            if fn.lower().endswith(".pdf"):
                out.append(os.path.relpath(os.path.join(dp, fn), library).replace("\\", "/"))
    return sorted(out)


def extract_missing(cfg, ft_dir, limit=None, timeout=25, verbose=True):
    """Extract only the PDFs that have no cache. With limit, process that many and return how many are left.

    This lets the work run in parts where one long run is a problem
    (for example the call timeout of an agent shell).
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
    """Return the cached full text with characters normalized (for metadata and tagging). The cache file itself is left as is."""
    p = os.path.join(ft_dir, txtname(rel))
    if not os.path.exists(p):
        return ""
    return norm_text(open(p, encoding="utf-8", errors="ignore").read())


def prune_orphans(ft_dir, keep):
    """Move caches that are not in the index to _obsolete/ (nothing is deleted)."""
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
