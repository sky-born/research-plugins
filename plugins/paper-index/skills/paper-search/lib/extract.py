# -*- coding: utf-8 -*-
"""PDF full-text extraction — the source folder is only read."""
import os, subprocess

from . import textio
from .textnorm import norm_text


def txtname(rel):
    """Cache file name of a library path — made from the NFC key, so every computer writes and looks up the same name."""
    return textio.nfc(rel).replace("\\", "/").replace("/", "__")[:-4] + ".txt"


def scan(library):
    """Relative paths of the PDFs in the library, as NFC keys. Open one with `source(library, rel)`."""
    return [rel for rel, _path in textio.walk(library, ".pdf")]


def source(library, rel):
    """Real path of a library PDF from its key — the name on disk may be stored in another normalization."""
    return textio.resolve(library, rel)


def cache(ft_dir, rel):
    """Real path of a library PDF's cache file (it may not exist)."""
    return textio.resolve(ft_dir, txtname(rel))


def extract_missing(cfg, ft_dir, limit=None, timeout=25, verbose=True):
    """Extract only the PDFs that have no cache. With limit, process that many and return how many are left.

    This lets the work run in parts where one long run is a problem
    (for example the call timeout of an agent shell).
    """
    os.makedirs(ft_dir, exist_ok=True)
    todo = [rel for rel in scan(cfg["library"])
            if not os.path.exists(cache(ft_dir, rel))]
    done, failed = 0, []
    for rel in todo:
        if limit is not None and done >= limit:
            break
        src = source(cfg["library"], rel)
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
    p = cache(ft_dir, rel)
    if not os.path.exists(p):
        return ""
    return norm_text(open(p, encoding="utf-8", errors="ignore").read())


def prune_orphans(ft_dir, keep):
    """Move caches that are not in the index to _obsolete/ (nothing is deleted)."""
    import shutil
    obs = os.path.join(ft_dir, "_obsolete")
    os.makedirs(obs, exist_ok=True)
    n = 0
    keep = {textio.nfc(k) for k in keep}
    for key, f in textio.listdir(ft_dir):
        if key.endswith(".txt") and key not in keep:
            try:
                shutil.move(os.path.join(ft_dir, f), os.path.join(obs, f))
                n += 1
            except Exception:
                pass
    return n
