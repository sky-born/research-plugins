# -*- coding: utf-8 -*-
"""Loading the config — library path, index path and preset, managed in one place."""
import json, os, sys

from . import textio
from .legacy import LEGACY_OA_STAGING   # default of 0.10 and earlier — used when the config has no oa_staging and only this folder exists

DEFAULT = {
    "name": "",                 # library name (for reports)
    "library": "",              # source PDF folder (treated as read-only)
    "index_dir": "",            # folder for the index and caches
    "preset": "",               # presets/*.json file name (empty: automatic tagging)
    "id_prefix": "P",
    "pdftotext": "pdftotext",
    "min_tag_score": 4,         # threshold for assigning a tag (first pass)
    "min_tag_score_fallback": 2,
    "max_tags": 5,
    "oa_staging": "_oa_inbox",  # staging folder for OA papers (relative to index_dir). Not the library
}

CONFIG_NAMES = ("paperindex.config.json", "config.json")


def find_config(start=None):
    """Look for the config file from the working folder upward."""
    d = os.path.abspath(start or os.getcwd())
    while True:
        for n in CONFIG_NAMES:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load(path=None, start=None):
    p = path or find_config(start)
    if not p:
        sys.exit("Config file not found. Create one with `papertool.py init <library path>`.")
    cfg = dict(DEFAULT)
    raw = json.load(open(p, encoding="utf-8"))
    cfg.update(raw)
    cfg["_oa_staging_set"] = "oa_staging" in raw
    base = os.path.dirname(os.path.abspath(p))

    def resolve(v, want_dir=True):
        """Use a string as is; for a list, use the first path that exists.

        When the same library shows up under different paths in different environments (e.g. a Windows path
        on the host and a mount path in the agent shell), list several candidates.
        """
        cands = v if isinstance(v, list) else [v]
        out = []
        for c in cands:
            if not c:
                continue
            c = c if os.path.isabs(c) else os.path.normpath(os.path.join(base, c))
            out.append(c)
        for c in out:
            if (os.path.isdir(c) if want_dir else os.path.exists(c)):
                return c
        # No candidate exists — the agent shell's mount path changes every session,
        # so look for a folder of the same name under the mount points (the name may be stored in either normalization).
        for c in out:
            bname = os.path.basename(c.rstrip("/\\").replace("\\", "/"))
            if not bname:
                continue
            for pat in (f"/sessions/*/mnt/{bname}", f"/mnt/{bname}", f"/workspace/{bname}"):
                hit = textio.glob(pat)
                if hit:
                    return hit[0]
        return out[0] if out else ""

    _raw_lib = cfg["library"]
    cfg["library"] = resolve(_raw_lib)
    # Keep which candidates there were and whether the chosen one exists, so the commands can decide
    cfg["_library_candidates"] = [
        (c if os.path.isabs(c) else os.path.normpath(os.path.join(base, c)))
        for c in (_raw_lib if isinstance(_raw_lib, list) else [_raw_lib]) if c]
    cfg["_library_found"] = os.path.isdir(cfg["library"])
    cfg["index_dir"] = resolve(cfg["index_dir"]) or base
    cfg["_path"] = p
    cfg["_base"] = base
    if not cfg["library"]:
        sys.exit(f"{p}: `library` is empty.")
    if not cfg["index_dir"]:
        cfg["index_dir"] = os.path.join(base, "index")
    return cfg


def save(cfg, path):
    out = {k: v for k, v in cfg.items() if not k.startswith("_")}
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def paths(cfg):
    d = cfg["index_dir"]
    stg = cfg.get("oa_staging") or DEFAULT["oa_staging"]
    stg = stg if os.path.isabs(stg) else os.path.join(d, stg)
    legacy = os.path.join(d, LEGACY_OA_STAGING)
    if not cfg.get("_oa_staging_set") and not os.path.isdir(stg) and os.path.isdir(legacy):
        stg = legacy
    return {
        "index_dir": d,
        "fulltext": os.path.join(d, "_fulltext"),
        "obsolete": os.path.join(d, "_fulltext", "_obsolete"),
        "json": os.path.join(d, "papers_index.json"),
        "md": os.path.join(d, "papers_index.md"),
        "csv": os.path.join(d, "papers_index.csv"),
        "backup": os.path.join(d, "_backup"),       # copies of papers_index.json taken before old spellings are rewritten
        "vocab": os.path.join(d, "_fulltext", "_vocab.json"),
        "scopus": os.path.join(d, "_scopus"),        # Scopus results json · md (oafetch also reads old fetch records here)
        "oa_staging": stg,                          # OA staging (not the library, not indexed)
        "oa_text": os.path.join(stg, "_text"),      # full text of fetched OA papers
    }


def load_preset(cfg, tool_root):
    """Read the preset file. None if there is none (falls back to automatic tagging)."""
    name = cfg.get("preset") or ""
    if not name:
        return None
    for cand in (name,
                 os.path.join(cfg["_base"], name),
                 os.path.join(tool_root, "presets", name),
                 os.path.join(tool_root, "presets", name + ".json")):
        if os.path.exists(cand):
            return json.load(open(cand, encoding="utf-8"))
    # a preset generated automatically in the index folder
    auto = os.path.join(cfg["index_dir"], "tags.auto.json")
    if os.path.exists(auto):
        return json.load(open(auto, encoding="utf-8"))
    return None
