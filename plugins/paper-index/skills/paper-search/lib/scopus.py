# -*- coding: utf-8 -*-
"""Scopus Search API client — standard library only.

The key is read only from the environment variable `ELS_API_KEY` (an institutional token, if any, from
`ELS_INST_TOKEN`) and sent only in the `X-ELS-APIKey` header. It never goes into the URL query string,
a command-line argument, the config or any output, and error text is scrubbed of it (`_scrub`).
Rules for handling the key: `SKILL.md` "G-0. Handling the API key — no exceptions".

Authentication reference: https://dev.elsevier.com/tecdoc_api_authentication.html
"""
import json, os, re, socket, urllib.error, urllib.parse, urllib.request

from .textnorm import norm_text

BASE = "https://api.elsevier.com/content/search/scopus"
ENV_KEY = "ELS_API_KEY"
ENV_TOKEN = "ELS_INST_TOKEN"

# The one source of the page size. It is the default of the config `scopus.count` · `scopus.page_size`,
# and the size used again when the key refuses a larger page.
# Elsevier's documented per-view limits are VIEW_MAX, but the real limit is set by the key's service level —
# depending on the level, even STANDARD gives HTTP 400 (TOO_MANY) above 25.
PAGE_SIZE = 25
VIEW_MAX = {"STANDARD": 200, "COMPLETE": 25}     # https://dev.elsevier.com/api_key_settings.html
PAGE_CAP = 5000       # pagination limit — start + count cannot exceed this
TOO_MANY = "Exceeds the maximum number allowed"  # 400 INVALID_INPUT "... for the service level"

# The `scopus` section of the config file — known keys and defaults. settings() warns about unknown keys.
SETTINGS = {"count": PAGE_SIZE, "page_size": PAGE_SIZE, "view": None, "sort": None}


class ScopusError(RuntimeError):
    pass


class NoKey(ScopusError):
    pass


class NoNetwork(ScopusError):
    pass


def _scrub(text, key):
    """Remove the key from a string, in case it would otherwise leave the tool."""
    if key and text:
        text = text.replace(key, "***")
    return text


def get_key():
    k = (os.environ.get(ENV_KEY) or "").strip()
    if not k:
        raise NoKey(
            f"Environment variable {ENV_KEY} is not set.\n"
            "  Windows: Start menu → 'Edit environment variables for your account' → User variables → New\n"
            f"           Variable name {ENV_KEY} / Variable value = your Scopus API key\n"
            "           (if you have an institutional token, add " + ENV_TOKEN + " the same way)\n"
            "  Close and reopen the terminal and the app completely for the setting to take effect."
        )
    return k


def _get(url, key, timeout):
    """One GET. On success (body, quota meta); on failure an exception carrying the code."""
    headers = {
        "X-ELS-APIKey": key,          # the key goes in the header only
        "Accept": "application/json",
        "User-Agent": "paper-index-tool/1.0",
    }
    tok = (os.environ.get(ENV_TOKEN) or "").strip()
    if tok:
        headers["X-ELS-Insttoken"] = tok

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "ignore")
            meta = {
                "quota_limit": r.headers.get("X-RateLimit-Limit"),
                "quota_remaining": r.headers.get("X-RateLimit-Remaining"),
                "quota_reset": r.headers.get("X-RateLimit-Reset"),
            }
            return body, meta
    except urllib.error.HTTPError as e:
        detail = _scrub(e.read().decode("utf-8", "ignore")[:400], key)
        if e.code == 401:
            err = ScopusError("401 authentication failed — the API key is wrong or has no access to this API.\n" + detail)
        elif e.code == 403:
            err = ScopusError("403 forbidden — outside the institution's subscription, or an institutional token is needed.\n" + detail)
        elif e.code == 429:
            err = ScopusError("429 quota exceeded — retry after " + str(e.headers.get("X-RateLimit-Reset")) + ".\n" + detail)
        else:
            err = ScopusError(f"HTTP {e.code}\n{detail}")
        err.code = e.code
        raise err
    except (urllib.error.URLError, socket.timeout, socket.gaierror) as e:
        raise NoNetwork(
            "Cannot connect to api.elsevier.com.\n"
            "  An agent shell (sandbox) has restricted outbound access, so Scopus cannot be called from here.\n"
            f"  Cause: {e}"
        )


def settings(cfg):
    """Merge the config's `scopus` section with the defaults (SETTINGS). Returns (values, list of warnings).

    Unknown keys and unusable values are dropped with a warning — so a typo does not silently become the default.
    Keys starting with `_` count as comments and are skipped.
    """
    raw = cfg.get("scopus") or {}
    out, warn = dict(SETTINGS), []
    if not isinstance(raw, dict):
        return out, [f"Config `scopus` is not an object ({type(raw).__name__}) — ignored; using the defaults."]
    hi = max(VIEW_MAX.values())
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        if k not in SETTINGS:
            warn.append(f"Config `scopus.{k}` is an unknown key — ignored. Known keys: {', '.join(SETTINGS)}")
        elif k in ("count", "page_size") and (isinstance(v, bool) or not isinstance(v, int)
                                              or not 1 <= v <= hi):
            warn.append(f"Config `scopus.{k}` = {v!r} is not an integer in 1–{hi} — using the default {SETTINGS[k]}.")
        elif k in ("view", "sort") and v is not None and not isinstance(v, str):
            warn.append(f"Config `scopus.{k}` = {v!r} is not a string — ignored.")
        else:
            out[k] = v
    return out, warn


def page_limit(view, page_size=PAGE_SIZE):
    """Results per request — the smaller of the configured page size and that view's documented limit.

    With view None, COMPLETE is tried first, so the COMPLETE limit applies."""
    return min(page_size, VIEW_MAX.get(view or "COMPLETE", PAGE_SIZE))


def search(query, count=PAGE_SIZE, start=0, view=None, sort=None, timeout=30):
    """Scopus search. On success returns (list of entries, meta).

    Without a view, COMPLETE (abstract, all authors, author keywords) is tried first; if the key has no access
    (401/403), it falls back to STANDARD. Bibliographic data alone cannot support selection by content,
    so abstracts are fetched by default. The view actually received is kept in the meta `view`.

    If count exceeds the key's service-level limit and HTTP 400 (TOO_MANY) comes back, the same page is fetched
    again with PAGE_SIZE results. The meta `count_asked` then keeps the count first requested — the caller warns
    and uses the smaller size from the next page on.
    """
    key = get_key()
    tries = [view] if view else ["COMPLETE", None]
    asked, i = count, 0
    while True:
        v = tries[i]
        params = {"query": query, "count": str(count), "start": str(start)}
        if v:
            params["view"] = v
        if sort:
            params["sort"] = sort
        url = BASE + "?" + urllib.parse.urlencode(params)
        try:
            body, meta = _get(url, key, timeout)
        except ScopusError as e:
            code = getattr(e, "code", 0)
            if v == "COMPLETE" and view is None and i + 1 < len(tries) and code in (401, 403):
                i += 1
                continue      # give up the abstracts and take bibliographic data only
            if code == 400 and count > PAGE_SIZE and TOO_MANY in str(e):
                count = PAGE_SIZE
                continue      # fetch the same page again at a size the key's service level accepts
            raise
        data = json.loads(body)
        res = data.get("search-results", {})
        meta["total"] = int(res.get("opensearch:totalResults", 0) or 0)
        meta["query"] = query
        meta["start"] = start
        meta["count"] = count
        if count < asked:
            meta["count_asked"] = asked
        meta["view"] = v or "STANDARD"
        return [normalize(e) for e in (res.get("entry") or []) if "error" not in e], meta


def normalize(e):
    """Reshape a Scopus entry so it is easy to match against the index."""
    def g(*keys):
        for k in keys:
            v = e.get(k)
            if v:
                return v
        return ""
    date = g("prism:coverDate", "prism:coverDisplayDate")
    year = (re.findall(r"(19|20)\d{2}", str(date)) and re.search(r"((19|20)\d{2})", str(date)).group(1)) or ""
    # The next three come only with the COMPLETE view. In a STANDARD response they stay empty.
    authors = "; ".join(a.get("authname", "") for a in (e.get("author") or [])
                        if isinstance(a, dict) and a.get("authname"))
    keywords = re.sub(r"\s*\|\s*", "; ", g("authkeywords")).strip()
    return {
        "title": g("dc:title"),
        "author": g("dc:creator"),
        "authors": authors,
        "abstract": (g("dc:description") or "").strip(),
        "keywords": keywords,
        "journal": g("prism:publicationName"),
        "year": year,
        "doi": g("prism:doi"),
        "eid": g("eid"),
        "volume": g("prism:volume"),
        "page": g("prism:pageRange"),
        "cited_by": g("citedby-count"),
        "type": g("subtypeDescription", "subtype"),
        "openaccess": g("openaccess"),
        "url": ("https://doi.org/" + g("prism:doi")) if g("prism:doi") else
               ("https://www.scopus.com/record/display.uri?eid=" + urllib.parse.quote(g("eid")) + "&origin=resultslist"
                if g("eid") else ""),
    }


# ------------------------------------------------------- matching against owned papers

def _norm(s):
    return re.sub(r"[^a-z0-9]", "", norm_text(s or "").lower())   # unfold ligatures in index titles (Eﬀect) before comparing


def match_against_index(entries, rows, threshold=0.86):
    """Mark whether each Scopus result is already in the library.

    The same DOI settles it; otherwise title similarity decides.
    """
    import difflib
    by_doi = {}
    for r in rows:
        if r.get("doi"):
            by_doi.setdefault(r["doi"].lower().rstrip("."), r)
    titles = [(_norm(r["title"]), r) for r in rows]

    out = []
    for e in entries:
        hit, how = None, ""
        d = (e.get("doi") or "").lower().rstrip(".")
        if d and d in by_doi:
            hit, how = by_doi[d], "DOI match"
        else:
            t = _norm(e.get("title"))
            best, score = None, 0.0
            if t:
                for tn, r in titles:
                    s = difflib.SequenceMatcher(None, t, tn).ratio()
                    if s > score:
                        best, score = r, s
            if best and score >= threshold:
                hit, how = best, f"title similarity {score:.2f}"
        e = dict(e)
        e["owned"] = bool(hit)
        e["owned_id"] = hit["id"] if hit else ""
        e["owned_rel"] = hit["rel"] if hit else ""
        e["match_by"] = how
        out.append(e)
    return out


def doi_link(doi):
    """Turn a DOI into a clickable link. From a campus IP this link leads straight to the full text."""
    doi = (doi or "").strip()
    if not doi:
        return ""
    return f"[{doi}](https://doi.org/{urllib.parse.quote(doi, safe='/:')})"


def oa_mark(e):
    """OA ✔ = fetched into the staging folder · OA = confirmed open access · — = not, or not checked"""
    if e.get("oa_file"):
        return "OA ✔"
    if str(e.get("openaccess", "")).strip().lower() in ("1", "true") or e.get("oa_url"):
        return "OA"
    return "—"


def to_markdown(entries, meta=None, title="Scopus search results"):
    L = [f"# {title}", ""]
    if meta:
        L.append(f"Query `{meta.get('query','')}` · showing {meta.get('start',0)+1}–{meta.get('start',0)+len(entries)}"
                 f" of {meta.get('total','?')}"
                 + (f" · view {meta['view']}" if meta.get("view") else ""))
        if meta.get("quota_remaining"):
            L.append(f"Remaining call quota {meta['quota_remaining']} / {meta.get('quota_limit','?')}")
        L.append("")
    owned = [e for e in entries if e.get("owned")]
    new = [e for e in entries if not e.get("owned")]
    if any("owned" in e for e in entries):
        L.append(f"**Owned {len(owned)} · missing {len(new)}**")
        L.append("")
    n_oa = sum(1 for e in entries if not e.get("owned") and oa_mark(e) != "—")
    n_got = sum(1 for e in entries if e.get("oa_file"))
    if n_oa or n_got:
        L.append(f"Of the missing, OA {n_oa} · fetched into the staging folder {n_got} (`OA ✔`)")
        L.append("")
    L += ["| # | Owned | OA | Author | Year | Title | Journal | Cited by | DOI |",
          "|---|---|---|---|---|---|---|---|---|"]
    for i, e in enumerate(entries, 1):
        mark = f"✅ {e.get('owned_id','')}" if e.get("owned") else "—"
        L.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            i, mark, oa_mark(e), e.get("author", "")[:22], e.get("year", ""),
            (e.get("title", "") or "")[:78].replace("|", "/"),
            (e.get("journal", "") or "")[:34].replace("|", "/"),
            e.get("cited_by", ""), doi_link(e.get("doi", ""))))

    # With abstracts (COMPLETE view), add them per entry — so selection does not rest on bibliographic data alone.
    if any(e.get("abstract") for e in entries):
        L += ["", "## Per-entry abstracts", ""]
        for i, e in enumerate(entries, 1):
            mark = f"owned ✅ {e.get('owned_id','')}" if e.get("owned") else "missing"
            L.append(f"### {i}. {e.get('title','')} ({e.get('year','')})")
            who = e.get("authors") or e.get("author", "")
            src = " · ".join(x for x in (who, e.get("journal", ""), doi_link(e.get("doi", ""))) if x)
            L.append(f"{src} · [{mark}]")
            if e.get("oa_file"):
                L.append(f"OA fetched: `{e['oa_file']}` · full text: `{e.get('oa_text') or '(extraction failed)'}`")
            elif e.get("oa_text"):
                L.append(f"OA full text: `{e['oa_text']}`" + (f" · {e['oa_note']}" if e.get("oa_note") else ""))
            elif e.get("oa_note"):
                L.append(f"OA: {e['oa_note']}")
            L.append("")
            L.append((e.get("abstract") or "").strip() or "(no abstract)")
            if e.get("keywords"):
                L.append("")
                L.append("Author keywords: " + e["keywords"])
            L.append("")
    return "\n".join(L) + "\n"
