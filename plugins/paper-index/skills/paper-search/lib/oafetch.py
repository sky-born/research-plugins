# -*- coding: utf-8 -*-
"""Fetching open-access papers — only the OA ones among the search results go into the staging folder, with full text.

**Nothing is written to the library.** Fetched PDFs go to the config `oa_staging` (default `<index_dir>/_oa_inbox`),
their full text to `_text/` below it. The staging folder is not indexed.
Moving papers into the library is the user's job, with their own reference manager. Once a moved paper is taken in by
`reindex`, the next run moves the matching `_text` file to `_text/_obsolete/` (nothing is deleted).

OA is judged from two sources — the Scopus `openaccess` flag and OpenAlex's
`best_oa_location` (which also finds repository copies). **Only download addresses OpenAlex gave are used.**
Subscription papers are not touched. Requests carry a User-Agent naming the tool and are spaced out.

Each DOI is fetched once
    Whatever the result name (`--name`) or the query, and even if another computer fetched it, a DOI already in the
    staging folder is neither looked up in OpenAlex nor fetched again; only oa_file · oa_text are filled in the entry.
    The decision is made in one place, `_settle`.
      PDF   ① the fetch manifest `_manifest.json` ② the entry's own oa_file ③ oa_file values left in the result
            JSON files in `_scopus/` (fetched by versions before the manifest). The file must be in the staging folder
            now, and ②③ are not used for a file that another DOI also claims.
      text  If `_text/<DOI>.txt` exists, the DOI counts as fetched even when its PDF is not found (e.g. after it moved to the library).
    If the PDF is there but its full text is not, nothing is fetched; only the text is made. Existing text is not overwritten.
    A newly fetched PDF that slips past this decision but has the same content (size · md5) as a PDF in the staging folder
    does not get a copy (<name>_N.pdf); that file is used instead.

Fetch manifest `<oa_staging>/_manifest.json`
    {"format": "paper-index/oa-staging", "version": 1,
     "files": {"<lower-case DOI>": {"file": "<PDF path relative to the staging folder>", "text": "_text/<DOI>.txt or ''",
                               "bytes": 123, "md5": "…", "url": "…", "oa_status": "…", "fetched": "YYYY-MM-DD"}}}
    Only file is required. md5 · fetched exist only on lines for PDFs this tool fetched, not on lines copied over from ③.
    If bytes differs from the current file size, the file has been replaced and that line is not used.
    Every write reads the list on disk again and merges — lines another computer added through sync, and unknown lines, are kept.
    If it cannot be read or has an unknown format (another format · version), the tool warns and neither reads nor writes it in that run.

Fields left on each entry
    oa_checked   date OpenAlex was queried (ISO). Not asked again within 30 days (force with --recheck)
    oa_status    gold / hybrid / green / bronze … or scopus (when only the flag is set)
    oa_url       direct PDF address, otherwise the OA landing page
    oa_file      PDF path relative to the staging folder — marks it as fetched. Set only while the file is in the staging folder
    oa_text      relative path of the full text
    oa_note      why it was not fetched, or a note that only the full text exists, without the PDF
"""
import datetime as _dt
import hashlib
import json
import os
import random
import re
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from . import textio

UA = "paper-index-tool/1.0 (open-access fetch)"
OPENALEX = "https://api.openalex.org/works/doi:"
MIN_PDF_BYTES = 20_000
DEFAULT_LIMIT = 30          # maximum fetched per run
DELAY = (3.0, 5.0)          # pause between downloads (seconds)
LOOKUP_DELAY = 0.25         # pause between OpenAlex lookups (seconds)
RECHECK_DAYS = 30           # how often entries judged not OA are asked again
MANIFEST = "_manifest.json"                                 # fetch manifest — format in the module docstring
MANIFEST_FORMAT, MANIFEST_VERSION = "paper-index/oa-staging", 1
TEXT_ONLY_NOTE = "PDF not in the staging folder, only its full text — normal if it was moved to the library or deleted"


class NoNetwork(RuntimeError):
    pass


def _norm_doi(d):
    return (d or "").strip().lower().rstrip(".")


def is_oa_flag(e):
    return str(e.get("openaccess", "")).strip().lower() in ("1", "true")


def _get(url, accept, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.geturl(), r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        ctype = e.headers.get("Content-Type", "") if e.headers else ""
        return e.code, url, ctype, b""
    except (urllib.error.URLError, socket.timeout, socket.gaierror) as e:
        raise NoNetwork(f"cannot connect to {urllib.parse.urlsplit(url).hostname}: {e}")


def openalex(doi, timeout=20):
    """The OA location OpenAlex knows. None for a DOI it does not know."""
    st, _, _, body = _get(OPENALEX + urllib.parse.quote(doi, safe="/:"), "application/json", timeout)
    if st != 200 or not body:
        return None
    try:
        d = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return None
    loc = d.get("best_oa_location") or {}
    oa = d.get("open_access") or {}
    return {
        "is_oa": bool(oa.get("is_oa")),
        "oa_status": oa.get("oa_status") or "",
        "pdf_url": loc.get("pdf_url") or "",
        "landing": loc.get("landing_page_url") or oa.get("oa_url") or "",
        "year": str(d.get("publication_year") or ""),
    }


def download(url, timeout=60):
    """Return the PDF bytes. If it is not a PDF, (None, reason)."""
    st, _, ctype, body = _get(url, "application/pdf,*/*;q=0.8", timeout)
    if st != 200:
        return None, f"HTTP {st}"
    if body[:4] != b"%PDF":
        return None, f"not a PDF ({(ctype or '?').split(';')[0]}, {len(body)} B)"
    if len(body) < MIN_PDF_BYTES:
        return None, f"too small ({len(body)} B)"
    return body, ""


def _safe(s):
    s = re.sub(r'[\\/:*?"<>|]', " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


def filename_for(e):
    """Library convention — <author surname>-<first 56 characters of the title>.pdf"""
    surname = _safe((e.get("author") or "Unknown").split()[0].strip(",;")) or "Unknown"
    title = _safe(e.get("title") or e.get("doi") or "untitled")
    return f"{surname}-{title[:56].rstrip()}.pdf"


def text_name(doi):
    return re.sub(r"[^\w.-]", "_", _norm_doi(doi)) + ".txt"


def _unique(folder, name):
    base, ext = os.path.splitext(name)
    p, n = os.path.join(folder, name), 0
    while os.path.exists(p):
        n += 1
        p = os.path.join(folder, f"{base}_{n}{ext}")
    return p


def to_text(pdftotext, pdf, txt, timeout=60):
    try:
        r = subprocess.run([pdftotext, "-q", pdf, txt], timeout=timeout)
        return r.returncode == 0 or os.path.exists(txt)
    except Exception:
        return False


def _rel(path, stg):
    return os.path.relpath(path, stg).replace("\\", "/")


def _key(rel):
    """A path relative to the staging folder, made comparable — Unicode form, separators and case (Windows) aligned."""
    return os.path.normcase(os.path.normpath(textio.nfc(rel)))


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _replace(tmp, dst, tries=3):
    """os.replace — if a sync program briefly holds the target (Windows PermissionError), try again a moment later."""
    for i in range(tries):
        try:
            os.replace(tmp, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(2)


def _result_records(results_dir, log=print):
    """Records of PDFs fetched by versions before the manifest — oa_file values left in result JSON files. {DOI: [{"file", "url", "oa_status"}, …]}

    Reads the format papertool saves ({"meta", "entries"}) and plain entry lists. Files without the string "oa_file"
    are not parsed. Unreadable files are named and left out."""
    out, bad = {}, []
    if not results_dir or not os.path.isdir(results_dir):
        return out
    for key, fn in textio.listdir(results_dir):
        p = os.path.join(results_dir, fn)
        if not key.lower().endswith(".json") or not os.path.isfile(p):
            continue
        try:
            with open(p, "rb") as f:
                raw = f.read()
            if b'"oa_file"' not in raw:
                continue
            d = json.loads(raw.decode("utf-8-sig"))
        except (OSError, ValueError):
            bad.append(fn)
            continue
        ents = d.get("entries") if isinstance(d, dict) else d
        if not isinstance(ents, list):
            bad.append(fn)
            continue
        for e in ents:
            if isinstance(e, dict) and e.get("doi") and isinstance(e.get("oa_file"), str) and e["oa_file"]:
                out.setdefault(_norm_doi(e["doi"]), []).append(
                    {"file": e["oa_file"], "url": e.get("oa_url") or "", "oa_status": e.get("oa_status") or ""})
    if bad:
        log(f"  ※ Could not read {len(bad)} result files; left them out of the fetch records: " + ", ".join(bad[:5])
            + (" …" if len(bad) > 5 else ""))
    return out


class Staging:
    """What has been fetched into the staging folder — the fetch manifest (`_manifest.json`) and the records versions before the manifest left in result JSON."""

    def __init__(self, stg, txt_dir, results_dir="", log=print):
        self.stg, self.txt_dir, self.results_dir, self.log = stg, txt_dir, results_dir, log
        self.path = os.path.join(stg, MANIFEST)
        self.files, self.added = {}, {}          # usable lines {DOI: record} · lines added in this run
        self._legacy = None                       # {DOI: [records]} — read once, when needed
        self._legacy_owners = {}                  # {file key: {DOI}}
        raw, why = self._read()
        self.usable = raw is not None
        if why:
            log(f"  ※ Not using the fetch manifest — {why}: {self.path}\n"
                "    This run decides from the full-text files and the records in the result JSON only, and leaves the manifest unchanged.")
        bad = 0
        for doi, rec in (raw or {}).items():
            if isinstance(rec, dict) and isinstance(rec.get("file"), str) and rec["file"]:
                self.files[_norm_doi(doi)] = rec
            else:
                bad += 1
        if bad:
            log(f"  ※ Skipping {bad} manifest lines without a file (they are not deleted): {self.path}")

    def _read(self):
        """(the files dict of the list on disk, reason for not using it). With no file, ({}, "")."""
        if not os.path.exists(self.path):
            return {}, ""
        try:
            with open(self.path, encoding="utf-8-sig") as f:
                d = json.load(f)
        except (OSError, ValueError) as ex:
            return None, f"unreadable ({ex})"
        if not (isinstance(d, dict) and d.get("format") == MANIFEST_FORMAT
                and d.get("version") == MANIFEST_VERSION and isinstance(d.get("files"), dict)):
            got = (d.get("format"), d.get("version")) if isinstance(d, dict) else (type(d).__name__, None)
            return None, "unknown format (format {!r} · version {!r})".format(*got)
        return d["files"], ""

    def _ok(self, rel):
        return os.path.isfile(os.path.join(self.stg, rel))

    def _rec_ok(self, rec):
        """Does the line still hold — the file exists and has the recorded size."""
        p = os.path.join(self.stg, rec["file"])
        if not os.path.isfile(p):
            return False
        n = rec.get("bytes")
        return not (isinstance(n, int) and n > 0 and os.path.getsize(p) != n)

    def _owners(self, rel):
        """The DOIs that claim this file — in the manifest (lines that still hold) and in result JSON."""
        k = _key(rel)
        out = {d for d, r in self.files.items() if _key(r["file"]) == k and self._rec_ok(r)}
        return out | self._legacy_owners.get(k, set())

    def _unmapped(self):
        """PDFs in the staging folder that are not in the manifest — result JSON is read only when there are some."""
        mapped = {_key(r["file"]) for r in self.files.values() if self._rec_ok(r)}
        try:
            names = [n for _k, n in textio.listdir(self.stg)]
        except OSError:
            return []
        return [n for n in names if n.lower().endswith(".pdf") and _key(n) not in mapped and self._ok(n)]

    def _legacy_for(self, doi):
        if self._legacy is None:
            self._legacy = {}
            if self._unmapped():
                self._legacy = _result_records(self.results_dir, self.log)
                for d, recs in self._legacy.items():
                    for r in recs:
                        self._legacy_owners.setdefault(_key(r["file"]), set()).add(d)
                self._adopt_legacy()
        return self._legacy.get(doi, [])

    def _adopt_legacy(self):
        """Copy into the manifest the result-JSON records whose file is in the staging folder now and has a single owner."""
        for d, recs in sorted(self._legacy.items()):
            cur = self.files.get(d)
            if cur and self._rec_ok(cur):
                continue
            for r in recs:
                if self._ok(r["file"]) and self._owners(r["file"]) <= {d}:
                    self.remember(d, r["file"], r)
                    break

    def pdf_for(self, e):
        """The PDF fetched for this entry's DOI — (relative path, record). If it is not in the staging folder now, ("", remaining record or None).

        A record is returned even without a PDF so that url · oa_status can be filled."""
        doi = _norm_doi(e.get("doi"))
        rec = self.files.get(doi)
        if rec and self._rec_ok(rec):
            return rec["file"], rec
        cands = [{"file": e["oa_file"], "url": e.get("oa_url") or "", "oa_status": e.get("oa_status") or ""}
                 ] if isinstance(e.get("oa_file"), str) and e["oa_file"] else []
        cands += self._legacy_for(doi)
        for r in cands:
            if self._ok(r["file"]) and self._owners(r["file"]) <= {doi}:
                return r["file"], r
        return "", rec or (cands[0] if cands else None)

    def same_content(self, size, digest):
        """The name of a PDF with the same content (md5) already in the staging folder. Only files of the same size are read."""
        try:
            names = [n for _k, n in textio.listdir(self.stg)]
        except OSError:
            return ""
        for n in names:
            p = os.path.join(self.stg, n)
            if (n.lower().endswith(".pdf") and os.path.isfile(p) and os.path.getsize(p) == size
                    and _md5(p) == digest):
                return n
        return ""

    def record(self, doi, rec):
        self.files[doi] = self.added[doi] = rec

    def remember(self, doi, rel, src=None, text=None):
        """Write a fetched PDF into the manifest — an identical line is left as is. With text None, look for an existing text."""
        if text is None:
            t = os.path.join(self.txt_dir, text_name(doi))
            text = _rel(t, self.stg) if os.path.isfile(t) else ""
        cur = self.files.get(doi)
        same = bool(cur) and _key(cur["file"]) == _key(rel)
        if same and cur.get("text", "") == text:
            return
        rec = dict(cur) if same else {}
        rec.update(file=rel, text=text)
        rec.setdefault("bytes", os.path.getsize(os.path.join(self.stg, rel)))
        for k in ("url", "oa_status"):
            if not rec.get(k) and (src or {}).get(k):
                rec[k] = src[k]
        self.record(doi, rec)

    def save(self):
        """Merge the lines added in this run into the list on disk. A run that could not read the list does not write it."""
        if not self.usable or not self.added:
            return
        raw, why = self._read()                       # keep lines another computer added meanwhile
        if raw is None:
            self.usable = False
            self.log(f"  ※ The fetch manifest became {why} meanwhile — leaving it unchanged: {self.path}")
            return
        files = dict(raw)
        files.update(self.added)
        body = json.dumps({"format": MANIFEST_FORMAT, "version": MANIFEST_VERSION,
                           "files": dict(sorted(files.items()))}, ensure_ascii=False, indent=1) + "\n"
        fd, tmp = tempfile.mkstemp(prefix="_manifest.", suffix=".part", dir=self.stg)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(body)
            _replace(tmp, self.path)
        except OSError as ex:
            try:
                os.remove(tmp)
            except OSError:
                pass
            self.log(f"  ※ Could not write the fetch manifest ({ex}) — the fetch records stay in the result JSON: {self.path}")


def _settle(e, st, txt_dir, pdftotext):
    """For a DOI already fetched, fill oa_file · oa_text in the entry and return (True, whether the full text was newly made). Otherwise (False, False).

    If the PDF is there but its full text is not, the text is made here — nothing is fetched again. Existing text is left as is.
    """
    doi = _norm_doi(e["doi"])
    rel, rec = st.pdf_for(e)
    txt = os.path.join(txt_dir, text_name(doi))
    made = bool(rel) and not os.path.exists(txt) and to_text(pdftotext, os.path.join(st.stg, rel), txt)
    if not rel and not os.path.isfile(txt):
        return False, False
    text_rel = _rel(txt, st.stg) if os.path.isfile(txt) else ""
    e["oa_text"] = text_rel
    for k, src in (("oa_url", "url"), ("oa_status", "oa_status")):
        if not e.get(k) and (rec or {}).get(src):
            e[k] = rec[src]
    if rel:
        e["oa_file"] = rel
        e.pop("oa_note", None)
        st.remember(doi, rel, rec, text_rel)
    else:
        e.pop("oa_file", None)
        e["oa_note"] = TEXT_ONLY_NOTE
    return True, bool(made)


def _recently_checked(e, today):
    chk = e.get("oa_checked")
    if not chk:
        return False
    try:
        return (today - _dt.date.fromisoformat(chk)).days < RECHECK_DAYS
    except ValueError:
        return False


def fetch(entries, cfg, P, limit=DEFAULT_LIMIT, owned_dois=(), recheck=False, verbose=True, log=print):
    """Fetch the OA papers among the missing entries. Fills the oa_* fields of the entry dicts and returns a summary.

    DOIs already fetched are not fetched again (`_settle`). NoNetwork is raised as is — the caller prints a note
    and goes on saving the results. If P["scopus"] is set, old fetch records are looked up in the result JSON there.
    """
    stg, txt_dir = P["oa_staging"], P["oa_text"]
    os.makedirs(txt_dir, exist_ok=True)
    pdftotext = cfg.get("pdftotext") or "pdftotext"
    owned = {_norm_doi(d) for d in owned_dois if d}
    today = _dt.date.today()
    st = Staging(stg, txt_dir, P.get("scopus", ""), log=log)

    got, reused, failed, checked, n_oa, already, made, left = 0, 0, [], 0, 0, 0, 0, 0
    try:
        for e in entries:
            if e.get("owned") or not e.get("doi"):
                continue
            staged, new_text = _settle(e, st, txt_dir, pdftotext)
            if staged:
                already += 1
                made += new_text
                if new_text and verbose:
                    log(f"  full text made (PDF already staged): {e['oa_file']}")
                continue
            for k in ("oa_file", "oa_text"):          # do not record as fetched what is not in the staging folder
                e.pop(k, None)
            if not recheck and not e.get("oa_url") and _recently_checked(e, today):
                continue
            if got >= limit:
                left += 1
                continue
            doi = e["doi"]
            checked += 1
            info = openalex(doi)                     # NoNetwork is raised here
            e["oa_checked"] = today.isoformat()
            time.sleep(LOOKUP_DELAY)

            oa = bool(info and (info["is_oa"] or info["pdf_url"])) or is_oa_flag(e)
            if not oa:
                continue
            n_oa += 1
            info = info or {}
            e["oa_status"] = info.get("oa_status") or ("scopus" if is_oa_flag(e) else "")
            e["oa_url"] = info.get("pdf_url") or info.get("landing") or ""
            pdf_url = info.get("pdf_url")
            if not pdf_url:
                e["oa_note"] = "OA, but no direct PDF address — download it from the link"
                failed.append((doi, e["oa_note"]))
                continue

            if got:
                time.sleep(random.uniform(*DELAY))
            try:
                data, why = download(pdf_url)
            except NoNetwork as ex:
                data, why = None, str(ex)
            if data is None:
                # Publishers often block non-browser requests (Springer, MDPI and others).
                # Keep the landing address so the user can click it, and go on to the next.
                e["oa_note"] = f"download failed: {why} — download it from the link"
                e["oa_url"] = info.get("landing") or pdf_url
                failed.append((doi, e["oa_note"]))
                continue

            if not e.get("year") and info.get("year"):
                e["year"] = info["year"]
            digest = hashlib.md5(data).hexdigest()
            same = st.same_content(len(data), digest)
            if same:                                 # a file with the same content exists: no copy
                dest = os.path.join(stg, same)
                reused += 1
            else:
                dest = _unique(stg, filename_for(e))
                tmp = dest + ".part"
                with open(tmp, "wb") as f:
                    f.write(data)
                _replace(tmp, dest)
            txt = os.path.join(txt_dir, text_name(doi))
            ok = os.path.exists(txt) or to_text(pdftotext, dest, txt)    # existing text is not overwritten
            e["oa_file"] = _rel(dest, stg)
            e["oa_text"] = _rel(txt, stg) if ok else ""
            e.pop("oa_note", None)
            st.record(_norm_doi(doi), {"file": e["oa_file"], "text": e["oa_text"], "bytes": len(data),
                                       "md5": digest, "url": pdf_url, "oa_status": e["oa_status"],
                                       "fetched": today.isoformat()})
            st.save()                                # after every fetch — what was fetched survives an interruption
            got += 1
            if verbose:
                log(f"  OA fetched {got}: {os.path.basename(dest)}  ({len(data):,} B"
                    + (", used the existing file with the same content" if same else "")
                    + ("" if ok else ", full-text extraction failed") + ")")
    finally:
        st.save()

    pruned = prune_text(txt_dir, owned)
    return dict(checked=checked, oa=n_oa, downloaded=got, reused=reused, already=already, text_made=made,
                failed=failed, pruned=pruned, staging=stg, text_dir=txt_dir, limit_hit=left > 0)


def prune_text(txt_dir, owned_dois):
    """Move the full text of DOIs now in the library to _obsolete/ (nothing is deleted)."""
    if not os.path.isdir(txt_dir) or not owned_dois:
        return 0
    import shutil
    names = {text_name(d) for d in owned_dois}
    obs = os.path.join(txt_dir, "_obsolete")
    n = 0
    for key, f in textio.listdir(txt_dir):
        if key.endswith(".txt") and key in names:
            os.makedirs(obs, exist_ok=True)
            try:
                shutil.move(os.path.join(txt_dir, f), os.path.join(obs, f))
                n += 1
            except OSError:
                pass
    return n
