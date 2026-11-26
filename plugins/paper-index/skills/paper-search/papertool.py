#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""papertool — index a PDF library and search its full text.

The library folder is **only read**. The index and the full-text cache are written as copies to a separate folder.

    papertool.py init <library path> [--index-dir DIR] [--preset NAME] [--name NAME]
    papertool.py index [--limit N]        extract full text + metadata + tags, build the index
    papertool.py reindex                  add new files only (keeps manual corrections)
    papertool.py resync                   re-match paths after file names change
    papertool.py repair                   restore the full text of PDFs with broken encoding
    papertool.py tags-auto [--top 20]     draft a tag preset from the corpus
    papertool.py search <term> [<term> ...]   full-text search (owned papers)
    papertool.py doctor                   health check (missing, duplicate, broken)

    papertool.py scopus "<query>"          Scopus search (with abstracts) + match against owned papers. --all fetches every result
    papertool.py scopus-sift <file.json>   filter saved results with a regex (offline, no API call)
    papertool.py scopus-merge <file.json>  match saved Scopus results against owned papers (offline)
    papertool.py scopus-tidy              archive launcher files (.bat/.query.txt) made by versions 0.9 and earlier
    papertool.py scopus "<query>" --fetch-oa   after search and matching, fetch missing OA papers into the staging folder (_oa_inbox) and extract their full text
    papertool.py oa-fetch <file.json>      fetch only the OA papers in saved results (never writes to the library)

Search options:  --or  --tag TAG  --year 2019-2026  -n 5  -c 200

The Scopus API key is read only from the environment variable `ELS_API_KEY`, and an institutional token,
if there is one, from `ELS_INST_TOKEN`. Rules for handling the key: `SKILL.md` "G-0. Handling the API key — no exceptions".
"""
import argparse, json, os, re, sys


def _utf8_console():
    """The default Windows console (cp949) cannot print characters such as '—' or '✅' and crashes mid-output.
    Set standard output to UTF-8 so the tool runs in any shell
    without a `PYTHONIOENCODING` prefix."""
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


_utf8_console()

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from lib import (config, extract, meta, tagging, render, resync as resync_mod,  # noqa: E402
                 searching, decode, wordsplit, scopus as scopus_mod, oafetch, legacy, textio)
from lib.textnorm import norm_text  # noqa: E402


def _load(args):
    cfg = config.load(getattr(args, "config", None))
    return cfg, config.paths(cfg)


def _preset(cfg):
    p = config.load_preset(cfg, ROOT)
    if p is None:
        return None, {}, []
    return p, tagging.compile_preset(p), list(p["tags"].keys())


def _write_index(rows, P, cfg, order, preset):
    """Write papers_index.{json,csv,md}; returns the number of duplicate groups.

    Values older versions wrote in Korean (legacy) and tag names the preset's `renamed` retires are first rewritten
    in the rows — exact matches only. If any changed, the file on disk is copied to `_backup/` once before it is
    overwritten (a failed copy stops here, before any write). With nothing to change there is no backup, and only
    warnings about the preset's `renamed` are printed."""
    aliases, warns = tagging.tag_aliases(preset)
    for w in warns:
        print("※ " + w)
    res = legacy.migrate_rows(rows, aliases)
    n = sum(res["converted"].values())
    if n:
        kept = sum(res["kept"].values())
        where = (" · backup: " + render.backup_copy(P["json"], P["backup"])) if os.path.exists(P["json"]) else ""
        print(f"Converted {n} values written by an older version to English · "
              f"kept {kept} other non-English values as written{where}")
    render.write_json(rows, P["json"])
    render.write_csv(rows, P["csv"])
    return render.write_md(rows, P["md"], cfg, order)


def _require_library(cfg, what):
    """Stop if the library folder does not exist.

    If no candidate exists and the command runs anyway, `doctor` reports '0 source papers, every path missing'
    and `reindex` reports files from the wrong folder as new papers. Stopping is better than running silently."""
    if os.path.isdir(cfg["library"]):
        return
    cands = cfg.get("_library_candidates") or [cfg["library"]]
    lines = [f"Library folder not found; stopping `{what}`.",
             "None of the library candidates in the config exists:"]
    lines += [f"  - {c}" for c in cands]
    lines += ["Check that the drive is mounted, or add this computer's path to the candidates.",
              f"Config file: {cfg.get('_path', '')}"]
    sys.exit("\n".join(lines))


def _library_too_small(cfg, n_lib, n_index):
    """True if the chosen library has fewer than half as many PDFs as the index — a sign of a wrong folder or an unfinished sync."""
    return bool(n_index) and n_lib < n_index * 0.5


def _texts(paths, rows, limit=350):
    """Full text for the vocabulary and the tag draft — a copy with characters normalized (ligatures etc.)."""
    out = []
    for r in rows[:limit]:
        p = textio.resolve(paths["fulltext"], r["txt"])
        if os.path.exists(p):
            out.append(norm_text(open(p, encoding="utf-8", errors="ignore").read()))
    return out


# ------------------------------------------------------------------ commands

def cmd_init(args):
    lib = os.path.abspath(args.library)
    if not os.path.isdir(lib):
        sys.exit(f"Library folder not found: {lib}")
    target = os.path.abspath(args.out or os.path.join(os.getcwd(), "paperindex.config.json"))
    cfg = dict(config.DEFAULT)
    cfg["library"] = lib
    cfg["name"] = args.name or os.path.basename(lib.rstrip("/\\"))
    cfg["index_dir"] = os.path.abspath(args.index_dir or os.path.join(os.path.dirname(target), "index"))
    cfg["preset"] = args.preset or ""
    config.save(cfg, target)
    os.makedirs(cfg["index_dir"], exist_ok=True)
    print(f"Config created: {target}")
    print(f"  library : {cfg['library']}")
    print(f"  index   : {cfg['index_dir']}")
    print(f"  preset  : {cfg['preset'] or '(none — draft one with tags-auto, or use automatic threshold tagging)'}")
    print("\nNext: papertool.py index")


def cmd_index(args):
    cfg, P = _load(args)
    _require_library(cfg, "index")
    os.makedirs(P["fulltext"], exist_ok=True)
    st = extract.extract_missing(cfg, P["fulltext"], limit=args.limit)
    print(f"Full-text extraction: {st['done']} processed, {st['remaining']} left ({st['total']} to extract in total)")
    if st["failed"]:
        print("  extraction failed:", len(st["failed"]))
    if st["remaining"]:
        print("  → Some are left. Run `index` again.")
        return

    preset, compiled, order = _preset(cfg)
    rows = []
    for rel in extract.scan(cfg["library"]):
        body = extract.read_cache(P["fulltext"], rel)
        r = meta.build(rel, os.path.basename(rel), os.path.dirname(rel) or "(root)", body)
        r["txt"] = extract.txtname(rel)
        r["tags"] = (tagging.tag_one(r["title"] + "\n" + body, compiled,
                                     cfg["min_tag_score"], cfg["min_tag_score_fallback"],
                                     cfg["max_tags"]) if compiled else [tagging.UNTAGGED])
        rows.append(r)
    render.assign_ids(rows, cfg["id_prefix"])
    ng = _write_index(rows, P, cfg, order, preset)
    moved = extract.prune_orphans(P["fulltext"], {r["txt"] for r in rows} | {"_vocab.json"})
    print(f"Index built: {len(rows)} papers · {ng} duplicate groups · {moved} old cache files moved")
    if not compiled:
        print("  ※ No preset, so the tags are empty. Draft one with `tags-auto`.")


def cmd_reindex(args):
    cfg, P = _load(args)
    _require_library(cfg, "reindex")
    rows = searching.load_rows(P)
    cur = list(extract.scan(cfg["library"]))
    if _library_too_small(cfg, len(cur), len(rows)) and not getattr(args, "force", False):
        sys.exit(f"The library has {len(cur)} source papers but the index has {len(rows)}. "
                 "The wrong folder may have been picked, or the sync may be unfinished.\n"
                 f"Library: {cfg['library']}\n"
                 "If this folder is right, run `reindex --force`.")
    known = {r["rel"] for r in rows}
    preset, compiled, order = _preset(cfg)
    added = 0
    for rel in cur:
        if rel in known:
            continue
        tp = extract.cache(P["fulltext"], rel)
        if not os.path.exists(tp):
            extract.extract_missing(cfg, P["fulltext"], limit=None, verbose=False)
        body = extract.read_cache(P["fulltext"], rel)
        r = meta.build(rel, os.path.basename(rel), os.path.dirname(rel) or "(root)", body)
        r["txt"] = extract.txtname(rel)
        r["tags"] = (tagging.tag_one(r["title"] + "\n" + body, compiled,
                                     cfg["min_tag_score"], cfg["min_tag_score_fallback"],
                                     cfg["max_tags"]) if compiled else [tagging.UNTAGGED])
        rows.append(r)
        added += 1
    render.assign_ids(rows, cfg["id_prefix"])
    _write_index(rows, P, cfg, order, preset)
    print(f"Added {added} new papers · {len(rows)} papers in total")
    if added:
        print("  ※ Titles and journals of new entries are automatic guesses. If one looks wrong, fix it in papers_index.json and run again.")


def cmd_resync(args):
    cfg, P = _load(args)
    _require_library(cfg, "resync")
    rows = searching.load_rows(P)
    if not rows:
        sys.exit("No index. Run `index` first.")
    res = resync_mod.resync(rows, cfg, P["fulltext"])
    print(f"Paths re-matched · {len(res['rows'])} papers kept")
    if res["dropped"]:
        print(f"  removed, gone from the source: {len(res['dropped'])} papers")
        for r in res["dropped"][:10]:
            print("   -", r["rel"])
    if res["collided"]:
        print(f"  entries merged because a duplicate file was deleted: {len(res['collided'])} papers")
    if res["new"]:
        print(f"  new files not in the index: {len(res['new'])} papers → run `reindex`")
    rows = res["rows"]
    preset, compiled, order = _preset(cfg)
    render.assign_ids(rows, cfg["id_prefix"])
    render.write_json(rows, P["json"])
    render.write_csv(rows, P["csv"])
    render.write_md(rows, P["md"], cfg, order)
    moved = extract.prune_orphans(P["fulltext"], {r["txt"] for r in rows} | {"_vocab.json"})
    print(f"  moved {moved} old cache files to _obsolete/")


# Old spellings of both notes: legacy.LEGACY_NOTES. `repair` finds encoding notes by a word (legacy.has_encoding_word),
# so NOTE_BROKEN must contain "encoding" and NOTE_FAIL must not.
NOTE_BROKEN = ("※ PDF font-encoding defect. The full-text cache is a restored copy. "
               "Some passages have shifted characters, so check the original PDF before citing")
NOTE_FAIL = "※ PDF text layer damaged — full-text search impossible. Download the original again or run OCR"


def cmd_repair(args):
    cfg, P = _load(args)
    _require_library(cfg, "repair")
    rows = searching.load_rows(P)
    fixed = failed = 0
    targets = []
    for r in rows:
        p = textio.resolve(P["fulltext"], r["txt"])
        if not os.path.exists(p):
            continue
        t = open(p, encoding="utf-8", errors="ignore").read()
        if decode.looks_broken(t) or legacy.has_encoding_word(r.get("note", "")):
            targets.append((r, p, t))
    print(f"To restore: {len(targets)} papers")
    for r, p, t in targets:
        new = decode.decode_pdf(extract.source(cfg["library"], r["rel"]), cfg["pdftotext"])
        if decode.density(new) > max(decode.density(t) * 3, 0.05):
            open(p, "w", encoding="utf-8").write(new)
            r["note"] = NOTE_BROKEN
            r["chars"] = len(new)
            fixed += 1
            print(f"  restored {r['id']} {r['file'][:48]}  density {decode.density(t):.3f}→{decode.density(new):.3f}")
        else:
            r["note"] = NOTE_FAIL
            failed += 1
            print(f"  failed {r['id']} {r['file'][:48]}")
    if fixed:
        # split words that ran together
        vocab = wordsplit.load_or_build(P["vocab"], _texts(P, [r for r in rows
                                                              if not legacy.has_encoding_word(r.get("note", ""))]))
        sp = wordsplit.Splitter(vocab)
        for r, p, _ in targets:
            if legacy.LEGACY_NOTES.get(r.get("note"), r.get("note")) == NOTE_BROKEN:      # either spelling
                t = open(p, encoding="utf-8", errors="ignore").read()
                open(p, "w", encoding="utf-8").write(sp.text(t))
    preset, compiled, order = _preset(cfg)
    render.write_json(rows, P["json"])
    render.write_csv(rows, P["csv"])
    render.write_md(rows, P["md"], cfg, order)
    print(f"restored {fixed} / failed {failed}")


def cmd_tags_auto(args):
    cfg, P = _load(args)
    rows = searching.load_rows(P)
    if not rows:
        sys.exit("No index. Run `index` first.")
    texts = _texts(P, rows, limit=args.sample)
    preset = tagging.auto_preset(texts, name=(cfg.get("name") or "auto"),
                                 top=args.top, min_df=args.min_df)
    out = args.out or os.path.join(P["index_dir"], "tags.auto.json")
    tagging.save_preset(preset, out)
    print(f"Draft tags: {len(preset['tags'])} → {out}\n")
    for k in preset["tags"]:
        print("  -", k)
    print("\nEdit them by hand, move the file to presets/, and put its file name in the config's `preset`.")
    print("Then run `index` again to apply the tags.")


# Search depth presets — the scan always covers everything; only the output is cut.
#   quick : only whether an expression, term or sentence is used. Questions a few representative cases answer
#   focus : claims, citation evidence, reviewer replies. Checking the original text within a limited scope (default)
#   full  : exhaustive survey, checking claims of absence or novelty. Only when explicitly asked
DEPTH_PRESETS = {
    "quick": dict(max_docs=3,  brief_docs=10, n=1, context=90),
    "focus": dict(max_docs=8,  brief_docs=20, n=3, context=120),
    "full":  dict(max_docs=0,  brief_docs=-1, n=3, context=140),
}
DEFAULT_DEPTH = "focus"


def _depth_opts(args):
    """Start from the preset and override only the arguments the user gave."""
    o = dict(DEPTH_PRESETS[args.depth or DEFAULT_DEPTH])
    for k in ("max_docs", "brief_docs", "n", "context"):
        v = getattr(args, k, None)
        if v is not None:
            o[k] = v
    return o


def cmd_search(args):
    cfg, P = _load(args)
    if not os.path.isdir(cfg["library"]):
        print("※ Library folder not found; searching the full-text cache only. Checking against the source PDFs before citing is not possible.",
              file=sys.stderr)
    o = _depth_opts(args)
    aliases = tagging.tag_aliases(config.load_preset(cfg, ROOT))[0] if args.tag else None
    rows, hits, stats = searching.search(
        P, args.terms, any_of=args.any_of, tag=args.tag, year=args.year,
        snippets=o["n"], context=o["context"], max_docs=o["max_docs"],
        brief_docs=o["brief_docs"], stop_after=args.stop_after or 0,
        count_only=args.count_only, tag_aliases=aliases)
    if not args.terms:
        for r in rows:
            print(f"{r['id']} [{r.get('year','')}] {r['title']}  <{r['rel']}>")
        print(f"\n{len(rows)} papers in total")
        return
    print(searching.format_hits(args.terms, rows, hits, stats))


def _slug(s, n=48):
    s = re.sub(r"[^0-9A-Za-z%s]+" % textio.HANGUL, "-", textio.nfc(s)).strip("-").lower()
    return (s[:n] or "query")


def _scopus_dir(P):
    d = P["scopus"]
    os.makedirs(d, exist_ok=True)
    return d


ARCHIVE_DIRNAME = "_done"


def _archive_dir(P):
    """The launcher archive folder under `_scopus/` — the old name (legacy.LEGACY_ARCHIVE_DIR) if that folder exists."""
    old = os.path.join(_scopus_dir(P), legacy.LEGACY_ARCHIVE_DIR)
    return old if os.path.isdir(old) else os.path.join(_scopus_dir(P), ARCHIVE_DIRNAME)


def _archive_launchers(P, verbose=True):
    """Move the launcher files (legacy.LEGACY_LAUNCHER_PREFIX + `*.bat` / `.query.txt`) made by versions 0.9 and earlier to the archive folder.

    The current version makes no launcher files — this handles only those old versions left in the index folder.
    Only those whose result JSON already exists move to the archive folder (`_archive_dir`; nothing is deleted);
    those without a result stay.
    """
    import shutil
    d = P["index_dir"]
    arc = _archive_dir(P)
    prefix = legacy.LEGACY_LAUNCHER_PREFIX
    moved = []

    def move(src):
        os.makedirs(arc, exist_ok=True)
        dst = os.path.join(arc, os.path.basename(src))
        try:
            if os.path.exists(dst):
                os.remove(dst)
            shutil.move(src, dst)
            moved.append(os.path.basename(src))
        except OSError as e:
            if verbose:
                print(f"  (move failed: {os.path.basename(src)} — {e})")

    for bat in textio.glob(os.path.join(d, prefix + "*.bat")):
        tag = os.path.splitext(textio.nfc(os.path.basename(bat)))[0].replace(prefix, "", 1)
        if not os.path.exists(os.path.join(_scopus_dir(P), tag + ".json")):
            continue                      # no result yet: leave it
        for f in (bat, os.path.splitext(bat)[0] + ".query.txt"):
            if os.path.exists(f):
                move(f)
    # The script copy that old versions kept beside the .bat files moves only when no launcher is left.
    ps1 = os.path.join(d, "scopus_search.ps1")
    if os.path.exists(ps1) and not textio.glob(os.path.join(d, prefix + "*.bat")):
        move(ps1)
    if moved and verbose:
        print(f"Moved {len(moved)} launcher files to {os.path.basename(arc)}/: " +
              ", ".join(sorted(set(moved))[:6]) + (" …" if len(moved) > 6 else ""))
    return moved


def _report(entries, meta_, P, name, quiet=False, fetch_oa=False, cfg=None,
            oa_limit=None, recheck=False):
    """Match Scopus results against owned papers, save them and print a summary.

    With fetch_oa, after matching, fetch missing OA papers into the staging folder (oafetch) and also keep
    that result (the oa_* fields) in the json/md. The search scope is unchanged, and nothing is written to the library."""
    rows = searching.load_rows(P)
    merged = scopus_mod.match_against_index(entries, rows) if rows else entries
    oa = _fetch_oa(merged, cfg, P, rows, oa_limit, recheck) if fetch_oa else None
    d = _scopus_dir(P)
    jf = os.path.join(d, name + ".json")
    mf = os.path.join(d, name + ".md")
    json.dump({"meta": meta_, "entries": merged}, open(jf, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    open(mf, "w", encoding="utf-8").write(
        scopus_mod.to_markdown(merged, meta_, title=f"Scopus — {meta_.get('query','')}"))
    own = sum(1 for e in merged if e.get("owned"))
    nabs = sum(1 for e in merged if e.get("abstract"))
    print(f"\nSaved: {jf}\n       {mf}")
    print(f"Results {len(merged)} · owned {own} · missing {len(merged)-own}"
          + (f" · {nabs} with abstracts" if nabs else "")
          + (f" · {meta_.get('total')} hits in total" if meta_.get("total") else ""))
    if not nabs and merged:
        print("  ※ No abstracts — a STANDARD response (limited access) or a file fetched by an old version of the tool.")
    if oa:
        _print_oa(oa)
    if not quiet:
        print()
        print(scopus_mod.to_markdown(merged, meta_))
    return merged


def _fetch_oa(merged, cfg, P, rows, limit, recheck):
    """Fetch missing OA papers into the staging folder. If the network is blocked, print a note and return None."""
    owned = [r.get("doi") for r in rows if r.get("doi")]
    print("\nOA check and fetch — querying OpenAlex and saving into the staging folder (nothing is written to the library) …")
    try:
        return oafetch.fetch(merged, cfg or {}, P, limit=limit or oafetch.DEFAULT_LIMIT,
                             owned_dois=owned, recheck=recheck)
    except oafetch.NoNetwork as e:
        print("[OA fetch unavailable] " + str(e))
        print("  The search results are saved as usual. Run `oa-fetch <file.json>` on a computer that can reach the network.")
        return None


def _print_oa(s):
    print(f"OA: {s['checked']} checked · {s['oa']} OA · {s['downloaded']} fetched → {s['staging']}")
    if s["already"]:
        print(f"    Already staged: {s['already']} papers, not fetched again (by DOI — including those under another result name or from another computer)"
              + (f". Of these, {s['text_made']} got a newly made full text" if s["text_made"] else ""))
    if s["reused"]:
        print(f"    Of the newly fetched, {s['reused']} had the same content as a PDF already there, so no copy was made.")
    if s["downloaded"] or s["already"]:
        print(f"    Full text: {s['text_dir']}  ← read the evidence sentences here")
    for doi, why in s["failed"][:10]:
        print(f"    - {doi}: {why}")
    if len(s["failed"]) > 10:
        print(f"    - … and {len(s['failed']) - 10} more (listed with the per-entry abstracts in the md)")
    if s["limit_hit"]:
        print("    ※ The per-run limit was reached. Run the same command again to continue.")
    if s["pruned"]:
        print(f"    Moved the full text of {s['pruned']} papers now in the library to _text/_obsolete/.")
    print("    ※ The staging folder is not the library. Move PDFs you want to keep with your reference manager and update the index.")


def _warn_capped(m):
    """Tell the user if the key refused the requested page size and a smaller one was used (`count_asked` from scopus.search)."""
    if m.get("count_asked"):
        print(f"※ Scopus refused {m['count_asked']} results per page (HTTP 400 — the key's service-level limit). "
              f"Fetching {m['count']} at a time — set `scopus.page_size` · `--count` to that or less to avoid this retry.")


def _fetch_all(args, first, meta_, view, sort, page_size=scopus_mod.PAGE_SIZE):
    """--all: fetch the pages after the first.

    Later pages use the view the first response actually returned, so the COMPLETE fallback is not retried on every page.
    The page size is the config `scopus.page_size` (default scopus.PAGE_SIZE) capped at that view's limit.
    If the key refuses that size, scopus.search fetches again at the default size, and the remaining pages use that size.
    """
    total = meta_["total"]
    end = min(total, scopus_mod.PAGE_CAP)
    if total > end:
        print(f"※ Of {total} results, only those up to number {end} (the pagination limit) are fetched. Consider splitting by year.")
    want = end - args.start
    got_view = view or meta_.get("view")
    page = scopus_mod.page_limit(meta_.get("view"), page_size)
    if meta_.get("count_asked"):          # the first page was already refused and fetched smaller: keep that size
        page = min(page, meta_["count"])

    out, seen = [], set()
    for e in first:
        key = e.get("eid") or e.get("doi") or id(e)
        if key not in seen:
            seen.add(key)
            out.append(e)
    start = args.start + len(first)
    while start < end:
        more, m = scopus_mod.search(args.query, count=min(page, end - start),
                                    start=start, view=got_view, sort=sort)
        if m.get("count_asked"):
            _warn_capped(m)
            page = m["count"]
        if not more:
            break
        start += len(more)
        for e in more:
            key = e.get("eid") or e.get("doi") or id(e)
            if key not in seen:
                seen.add(key)
                out.append(e)
        if len(out) % 100 < page and start < end:
            print(f"  … {len(out)}/{want} received")
    if len(out) < want:
        print(f"※ Of {want} expected, only {len(out)} arrived — a page in between was empty, or pages overlapped. "
              "Run the same command again to check the total.")
    meta_ = dict(meta_)
    meta_["count"] = len(out)
    return out, meta_


def cmd_scopus(args):
    cfg, P = _load(args)
    sc, warns = scopus_mod.settings(cfg)
    for w in warns:
        print("※ " + w)
    count = args.count or sc["count"]
    view = args.view or sc["view"]
    sort = args.sort or sc["sort"]
    name = args.name or _slug(args.query)
    if args.all:
        count = min(count, scopus_mod.page_limit(view, sc["page_size"]))   # the first page may be COMPLETE
    try:
        entries, meta_ = scopus_mod.search(args.query, count=count, start=args.start,
                                           view=view, sort=sort)
        _warn_capped(meta_)
        if args.all and min(meta_["total"], scopus_mod.PAGE_CAP) > args.start + len(entries):
            entries, meta_ = _fetch_all(args, entries, meta_, view, sort, sc["page_size"])
    except scopus_mod.NoKey as e:
        print("[Scopus unavailable] " + str(e))
        _howto(args, P, name, count)
        return
    except scopus_mod.NoNetwork as e:
        print("[Scopus unavailable] " + str(e))
        _howto(args, P, name, count)
        return
    except scopus_mod.ScopusError as e:
        print("[Scopus error] " + str(e))
        return
    _report(entries, meta_, P, name, quiet=args.quiet, fetch_oa=args.fetch_oa, cfg=cfg,
            oa_limit=args.oa_limit, recheck=args.recheck)


def _howto(args, P, name, count):
    """When direct calls are blocked, show the command to run in a terminal on a computer that has the key."""
    out = os.path.join(_scopus_dir(P), name + ".json")
    print("\n─ Run the following in a terminal on a computer that has the key, then match the result file ─\n")
    print(f'    python -X utf8 "<tool>/papertool.py" scopus "{args.query}" --count {count}'
          + (" --all" if args.all else "") + f' --name "{name}"')
    print("\n  Then (works without a network):")
    print(f'    papertool.py scopus-merge "{out}"')


def _load_result_file(path):
    """Read a file papertool saved, or a raw Scopus response, as (entries, meta)."""
    # utf-8-sig: absorbs a BOM added by another tool.
    raw = json.load(open(path, encoding="utf-8-sig"))
    if isinstance(raw, dict) and "entries" in raw:
        return raw["entries"], raw.get("meta", {})
    if isinstance(raw, dict) and "search-results" in raw:        # raw Scopus response
        res = raw["search-results"]
        entries = [scopus_mod.normalize(e) for e in (res.get("entry") or []) if "error" not in e]
        return entries, {"query": "(raw response)", "total": int(res.get("opensearch:totalResults", 0) or 0)}
    if isinstance(raw, list):
        return raw, {}
    sys.exit("Unknown format. Expected a raw Scopus response or a file papertool saved.")


def cmd_scopus_merge(args):
    cfg, P = _load(args)
    entries, meta_ = _load_result_file(args.file)
    name = args.name or _slug(os.path.splitext(os.path.basename(args.file))[0])
    _report(entries, meta_, P, name, quiet=args.quiet, fetch_oa=args.fetch_oa, cfg=cfg,
            oa_limit=args.oa_limit, recheck=args.recheck)


def cmd_oa_fetch(args):
    """Fetch only the missing OA papers in a saved result file into the staging folder. Scopus is not called again."""
    cfg, P = _load(args)
    entries, meta_ = _load_result_file(args.file)
    name = args.name or _slug(os.path.splitext(os.path.basename(args.file))[0])
    _report(entries, meta_, P, name, quiet=True, fetch_oa=True, cfg=cfg,
            oa_limit=args.limit, recheck=args.recheck)


def cmd_scopus_sift(args):
    """Filter saved results with a regex to recover precision. No API call.

    Case-sensitive by default, for patterns where case carries meaning, such as element symbols.
    """
    cfg, P = _load(args)
    entries, meta_ = _load_result_file(args.file)
    if not (args.require or args.exclude):
        sys.exit("Give --require or --exclude (at least one).")
    flags = re.IGNORECASE if args.ignore_case else 0
    req = re.compile(args.require, flags) if args.require else None
    exc = re.compile(args.exclude, flags) if args.exclude else None

    def blob(e):
        return " ".join(x for x in (e.get("title"), e.get("abstract"), e.get("keywords")) if x)

    kept = [e for e in entries
            if (not req or req.search(blob(e))) and not (exc and exc.search(blob(e)))]
    print(f"Filtered: {len(entries)} → {len(kept)} kept")
    if entries and not any(e.get("abstract") for e in entries):
        print("※ The file has no abstracts, so only titles and keywords were filtered. Low reliability.")
    meta_ = dict(meta_)
    meta_["sift"] = {"source": os.path.basename(args.file), "before": len(entries),
                     "require": args.require or "", "exclude": args.exclude or "",
                     "ignore_case": bool(args.ignore_case)}
    name = args.name or _slug(os.path.splitext(os.path.basename(args.file))[0]) + "-sift"
    _report(kept, meta_, P, name, quiet=args.quiet)


def cmd_scopus_tidy(args):
    cfg, P = _load(args)
    moved = _archive_launchers(P)
    if not moved:
        print("No launcher files to tidy. (Only those made by old versions whose result JSON exists are moved)")


def cmd_doctor(args):
    cfg, P = _load(args)
    _require_library(cfg, "doctor")
    rows = searching.load_rows(P)
    cur = set(extract.scan(cfg["library"]))
    print(f"Library: {cfg['library']}")
    idx = {r["rel"] for r in rows}
    import collections
    c = collections.Counter(r["rel"] for r in rows)
    print(f"Papers: {len(cur)} source / {len(rows)} indexed / "
          f"{len([k for k, _f in textio.listdir(P['fulltext']) if k.endswith('.txt')]) if os.path.isdir(P['fulltext']) else 0} cached")
    print("Paths missing (only in the index):", len(idx - cur))
    print("Not in the index (only in the source):", len(cur - idx))
    print("Duplicate mappings:", [k for k, v in c.items() if v > 1] or "none")
    print("Missing cache:", [r["id"] for r in rows
                    if not os.path.exists(textio.resolve(P["fulltext"], r["txt"]))] or "none")
    print("Full text under 500 characters:", [(r["id"], r["file"][:40]) for r in rows if r.get("chars", 0) < 500] or "none")
    print("Entries with a note:", sum(1 for r in rows if r.get("note")))
    if _library_too_small(cfg, len(cur), len(rows)):
        print("\n※ The source has fewer than half as many papers as the index. The wrong folder may have been picked, or the sync may be unfinished.\n"
              "   Check that the library path above is right before running `resync` or `reindex`.")
    if idx - cur:
        print("\n→ File names seem to have changed. Run `resync`.")
    if cur - idx:
        print("\n→ There are new files. Run `reindex`.")


# ------------------------------------------------------------------ main

def _oa_args(p):
    """OA fetch options for scopus and scopus-merge. They do not change the search scope."""
    p.add_argument("--fetch-oa", dest="fetch_oa", action="store_true",
                   help="after matching, fetch missing OA papers into the staging folder (config oa_staging, default _oa_inbox) and extract their full text")
    p.add_argument("--oa-limit", dest="oa_limit", type=int, default=None,
                   help="maximum OA papers fetched per run (default 30)")
    p.add_argument("--oa-recheck", dest="recheck", action="store_true",
                   help="query again entries judged not OA before")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="config file path (default: searched for upward from the current folder)")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("init"); p.add_argument("library"); p.add_argument("--index-dir")
    p.add_argument("--preset"); p.add_argument("--name"); p.add_argument("--out")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("index"); p.add_argument("--limit", type=int); p.set_defaults(fn=cmd_index)
    p = sub.add_parser("reindex")
    p.add_argument("--force", action="store_true", help="go ahead even if the source has fewer than half as many papers as the index")
    p.set_defaults(fn=cmd_reindex)
    p = sub.add_parser("resync"); p.set_defaults(fn=cmd_resync)
    p = sub.add_parser("repair"); p.set_defaults(fn=cmd_repair)

    p = sub.add_parser("tags-auto"); p.add_argument("--top", type=int, default=20)
    p.add_argument("--min-df", dest="min_df", type=int, default=4)
    p.add_argument("--sample", type=int, default=350); p.add_argument("--out")
    p.set_defaults(fn=cmd_tags_auto)

    p = sub.add_parser("search", help="full-text search (adjustable depth)")
    p.add_argument("terms", nargs="*")
    p.add_argument("--or", dest="any_of", action="store_true")
    p.add_argument("--tag", default=""); p.add_argument("--year", default="")
    p.add_argument("--depth", choices=list(DEPTH_PRESETS), default=DEFAULT_DEPTH,
                   help="quick=representative cases only / focus=evidence check (default) / full=print everything")
    p.add_argument("--count-only", dest="count_only", action="store_true",
                   help="count papers and occurrences only, no snippets (cheapest)")
    p.add_argument("--max-docs", dest="max_docs", type=int, default=None,
                   help="papers printed in detail with snippets (0=no limit); overrides the preset")
    p.add_argument("--brief-docs", dest="brief_docs", type=int, default=None,
                   help="papers listed one line each after the detailed ones (-1=all the rest)")
    p.add_argument("--stop-after", dest="stop_after", type=int, default=0,
                   help="stop scanning after N papers match (the statistics become lower bounds)")
    p.add_argument("-n", type=int, default=None, help="snippets per paper")
    p.add_argument("-c", "--context", type=int, default=None, help="characters on each side of a snippet")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("scopus"); p.add_argument("query")
    p.add_argument("--count", type=int); p.add_argument("--start", type=int, default=0)
    p.add_argument("--all", action="store_true",
                   help=f"fetch every result through pagination ({scopus_mod.PAGE_SIZE} per page — "
                        f"config scopus.page_size, limit {scopus_mod.PAGE_CAP:,})")
    p.add_argument("--view", help="default: try COMPLETE (with abstracts) and fall back to STANDARD if refused")
    p.add_argument("--sort"); p.add_argument("--name")
    p.add_argument("-q", "--quiet", action="store_true")
    _oa_args(p)
    p.set_defaults(fn=cmd_scopus)

    p = sub.add_parser("scopus-sift", help="filter saved Scopus results with a regex (offline)")
    p.add_argument("file")
    p.add_argument("--require", help="keep only entries whose title, abstract or keywords match this regex (case-sensitive by default)")
    p.add_argument("--exclude", help="drop entries that match this regex")
    p.add_argument("-i", "--ignore-case", dest="ignore_case", action="store_true",
                   help="ignore case — do not use for element-symbol patterns")
    p.add_argument("--name"); p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(fn=cmd_scopus_sift)

    p = sub.add_parser("scopus-merge"); p.add_argument("file")
    p.add_argument("--name"); p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("--keep-launcher", action="store_true", help=argparse.SUPPRESS)   # accepted for old command lines — does nothing
    _oa_args(p)
    p.set_defaults(fn=cmd_scopus_merge)

    p = sub.add_parser("oa-fetch", help="fetch only the missing OA papers in saved Scopus results into the staging folder (never writes to the library)")
    p.add_argument("file"); p.add_argument("--name")
    p.add_argument("--limit", type=int, default=None, help="maximum fetched per run (default 30)")
    p.add_argument("--recheck", action="store_true", help="query again entries judged not OA before")
    p.set_defaults(fn=cmd_oa_fetch)

    p = sub.add_parser("scopus-tidy"); p.set_defaults(fn=cmd_scopus_tidy)

    p = sub.add_parser("doctor"); p.set_defaults(fn=cmd_doctor)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return
    args.fn(args)


if __name__ == "__main__":
    main()
