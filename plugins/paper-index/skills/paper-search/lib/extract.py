# -*- coding: utf-8 -*-
"""PDF full-text extraction — the source folder is only read."""
import os, shutil, subprocess

from . import textio
from .textnorm import norm_text

# The tools read the extractor's output as UTF-8. xpdf's pdftotext writes Latin-1 unless told, and the non-ASCII
# letters (Greek, accents) were then lost; poppler's writes UTF-8 by default and takes the same option.
OUTPUT_ENCODING = ("-enc", "UTF-8")


def run_extractor(exe, pdf, out, timeout=None):
    """Extract the text of a PDF into the file `out` — the one command line for text that the tools keep and read."""
    return subprocess.run([exe, "-q", *OUTPUT_ENCODING, pdf, out], timeout=timeout)


def raw_output(exe, pdf):
    """The extractor's output in its own default encoding, for the shift restoration of `repair` (lib/decode.py).
    The restoration is tuned on it: asked for UTF-8, xpdf also writes the control characters that stand for shifted
    glyphs, and restorations come out weaker."""
    return subprocess.run([exe, "-q", pdf, "-"], capture_output=True).stdout.decode("utf-8", "ignore")


def has_extractor(exe):
    """True if the configured pdftotext can be found (a name on PATH or a path)."""
    return shutil.which(exe) is not None


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
    if todo and not has_extractor(cfg["pdftotext"]):
        return dict(done=0, remaining=len(todo), failed=[], total=len(todo), extracted=[], no_extractor=True)
    done, failed = 0, []
    for rel in todo:
        if limit is not None and done >= limit:
            break
        src = source(cfg["library"], rel)
        dst = os.path.join(ft_dir, txtname(rel))
        try:
            r = run_extractor(cfg["pdftotext"], src, dst, timeout=timeout)
            if r.returncode != 0 and not os.path.exists(dst):
                failed.append(rel)
        except Exception:
            failed.append(rel)
        done += 1
        if verbose and done % 25 == 0:
            print(f"  ... {done}/{len(todo)}")
    extracted = [rel for rel in todo[:done] if rel not in failed]
    return dict(done=done, remaining=max(0, len(todo) - done), failed=failed, total=len(todo),
                extracted=extracted, no_extractor=False)


def read_cache(ft_dir, rel):
    """Return the cached full text with characters normalized (for metadata and tagging). The cache file itself is left as is."""
    p = cache(ft_dir, rel)
    if not os.path.exists(p):
        return ""
    return norm_text(open(p, encoding="utf-8", errors="ignore").read())


def _to_obsolete(ft_dir, path):
    obs = os.path.join(ft_dir, "_obsolete")
    os.makedirs(obs, exist_ok=True)
    shutil.move(path, os.path.join(obs, os.path.basename(path)))


def prune_orphans(ft_dir, keep):
    """Move caches that are not in the index to _obsolete/ (nothing is deleted)."""
    os.makedirs(os.path.join(ft_dir, "_obsolete"), exist_ok=True)
    n = 0
    keep = {textio.nfc(k) for k in keep}
    for key, f in textio.listdir(ft_dir):
        if key.endswith(".txt") and key not in keep:
            try:
                _to_obsolete(ft_dir, os.path.join(ft_dir, f))
                n += 1
            except Exception:
                pass
    return n


def carry(ft_dir, old_txt, new_txt):
    """Give an entry's cache the name of its renamed file. Returns "moved", "missing" (no old cache) or "failed: …".

    The entry's own cache is kept because its `chars` and notes came from it and it may hold a `repair` restoration.
    A cache already under the new name can only have been extracted from the new file just now; it goes to
    _obsolete/. When only the case or the normalization of the name changed, the two names are one file on Windows
    and macOS, and the file is just renamed."""
    src = textio.resolve(ft_dir, old_txt)
    if not os.path.exists(src):
        return "missing"
    dst = os.path.join(ft_dir, textio.nfc(new_txt))
    try:
        if os.path.exists(dst):
            if os.path.samefile(src, dst):
                tmp = dst + ".carry"
                os.replace(src, tmp)
                src = tmp
            else:
                _to_obsolete(ft_dir, dst)
        os.replace(src, dst)
        return "moved"
    except OSError as e:
        return f"failed: {e}"
