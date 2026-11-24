# -*- coding: utf-8 -*-
"""Scopus Search API 클라이언트 — 표준 라이브러리만 씁니다.

**API 키는 코드·설정·출력 어디에도 저장하지 않습니다.**
환경변수 `ELS_API_KEY` 에서만 읽고, `X-ELS-APIKey` 헤더로만 보냅니다.
URL 쿼리스트링이나 명령줄 인자에 키를 넣지 않습니다 — 그러면 셸 기록·프록시 로그·
에러 메시지에 남습니다. 기관 토큰이 있으면 `ELS_INST_TOKEN` 을 함께 씁니다.

인증 방식 참고: https://dev.elsevier.com/tecdoc_api_authentication.html
"""
import json, os, re, socket, urllib.error, urllib.parse, urllib.request

from .textnorm import norm_text

BASE = "https://api.elsevier.com/content/search/scopus"
ENV_KEY = "ELS_API_KEY"
ENV_TOKEN = "ELS_INST_TOKEN"

# 한 페이지 크기의 원본입니다. 설정 `scopus.count` · `scopus.page_size` 의 기본값이고,
# 키가 더 큰 페이지를 거부하면 이 크기로 다시 받습니다.
# Elsevier 문서의 view 별 상한은 VIEW_MAX 이지만 실제 상한은 키의 서비스 등급이 정합니다 —
# 등급에 따라 STANDARD 도 25 를 넘기면 HTTP 400 (TOO_MANY) 이 납니다.
PAGE_SIZE = 25
VIEW_MAX = {"STANDARD": 200, "COMPLETE": 25}     # https://dev.elsevier.com/api_key_settings.html
PAGE_CAP = 5000       # 페이지네이션 상한 — start + count 가 이 값을 넘을 수 없습니다
TOO_MANY = "Exceeds the maximum number allowed"  # 400 INVALID_INPUT "... for the service level"

# 설정 파일의 `scopus` 절 — 아는 키와 기본값. 모르는 키는 settings() 가 경고합니다.
SETTINGS = {"count": PAGE_SIZE, "page_size": PAGE_SIZE, "view": None, "sort": None}


class ScopusError(RuntimeError):
    pass


class NoKey(ScopusError):
    pass


class NoNetwork(ScopusError):
    pass


def _scrub(text, key):
    """혹시라도 키가 섞인 문자열이 밖으로 나가지 않게 지웁니다."""
    if key and text:
        text = text.replace(key, "***")
    return text


def get_key():
    k = (os.environ.get(ENV_KEY) or "").strip()
    if not k:
        raise NoKey(
            f"환경변수 {ENV_KEY} 가 없습니다.\n"
            "  Windows: 시작 메뉴 → '계정의 환경 변수 편집' → 사용자 변수 → 새로 만들기\n"
            f"           변수 이름 {ENV_KEY} / 변수 값 = 발급받은 Scopus API 키\n"
            "           (기관 토큰이 있으면 " + ENV_TOKEN + " 도 같은 방식으로 추가)\n"
            "  설정한 뒤 터미널·앱을 완전히 껐다 켜야 반영됩니다."
        )
    return k


def _get(url, key, timeout):
    """한 번의 GET. 성공하면 (본문, 할당량 메타), 실패하면 코드가 붙은 예외."""
    headers = {
        "X-ELS-APIKey": key,          # 키는 헤더로만
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
            err = ScopusError("401 인증 실패 — API 키가 잘못됐거나 이 API에 권한이 없습니다.\n" + detail)
        elif e.code == 403:
            err = ScopusError("403 권한 없음 — 기관 구독 범위 밖이거나 기관 토큰이 필요합니다.\n" + detail)
        elif e.code == 429:
            err = ScopusError("429 할당량 초과 — " + str(e.headers.get("X-RateLimit-Reset")) + " 이후 재시도.\n" + detail)
        else:
            err = ScopusError(f"HTTP {e.code}\n{detail}")
        err.code = e.code
        raise err
    except (urllib.error.URLError, socket.timeout, socket.gaierror) as e:
        raise NoNetwork(
            "api.elsevier.com 에 연결할 수 없습니다.\n"
            "  에이전트 셸(샌드박스)은 외부 접속이 제한돼 있어 여기서는 Scopus를 호출할 수 없습니다.\n"
            f"  원인: {e}"
        )


def settings(cfg):
    """설정의 `scopus` 절을 기본값(SETTINGS)과 합칩니다. (값, 경고 목록) 을 돌려줍니다.

    모르는 키나 쓸 수 없는 값은 버리고 경고합니다 — 오타가 조용히 기본값이 되지 않게.
    `_` 로 시작하는 키는 주석으로 보고 넘어갑니다.
    """
    raw = cfg.get("scopus") or {}
    out, warn = dict(SETTINGS), []
    if not isinstance(raw, dict):
        return out, [f"설정 `scopus` 가 객체가 아닙니다({type(raw).__name__}) — 무시하고 기본값을 씁니다."]
    hi = max(VIEW_MAX.values())
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        if k not in SETTINGS:
            warn.append(f"설정 `scopus.{k}` 는 모르는 키입니다 — 무시합니다. 아는 키: {', '.join(SETTINGS)}")
        elif k in ("count", "page_size") and (isinstance(v, bool) or not isinstance(v, int)
                                              or not 1 <= v <= hi):
            warn.append(f"설정 `scopus.{k}` = {v!r} 는 1–{hi} 의 정수가 아닙니다 — 기본값 {SETTINGS[k]} 를 씁니다.")
        elif k in ("view", "sort") and v is not None and not isinstance(v, str):
            warn.append(f"설정 `scopus.{k}` = {v!r} 는 문자열이 아닙니다 — 무시합니다.")
        else:
            out[k] = v
    return out, warn


def page_limit(view, page_size=PAGE_SIZE):
    """한 번에 요청할 건수 — 설정한 페이지 크기와 그 view 의 문서상 상한 중 작은 쪽.

    view 가 None 이면 COMPLETE 를 먼저 시도하므로 COMPLETE 상한을 따릅니다."""
    return min(page_size, VIEW_MAX.get(view or "COMPLETE", PAGE_SIZE))


def search(query, count=PAGE_SIZE, start=0, view=None, sort=None, timeout=30):
    """Scopus 검색. 성공하면 (엔트리 목록, 메타) 를 돌려줍니다.

    view 를 지정하지 않으면 COMPLETE(초록·전체 저자·저자 키워드 포함)를 먼저 시도하고,
    키에 권한이 없으면(401/403) STANDARD 로 물러납니다. 서지만으로는 내용 기반 선별이
    안 되기 때문에 초록을 기본으로 받습니다. 실제로 받은 view 는 메타의 `view` 에 남습니다.

    count 가 키의 서비스 등급 상한을 넘어 HTTP 400(TOO_MANY)이 나면 같은 페이지를 PAGE_SIZE 건으로
    다시 받습니다. 그때 메타의 `count_asked` 에 처음 요청한 건수가 남습니다 — 부르는 쪽이 경고하고
    다음 페이지부터 크기를 줄입니다.
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
                continue      # 초록은 포기하고 서지만 받습니다
            if code == 400 and count > PAGE_SIZE and TOO_MANY in str(e):
                count = PAGE_SIZE
                continue      # 키의 서비스 등급이 받는 크기로 같은 페이지를 다시 받습니다
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
    """Scopus 엔트리를 인덱스와 대조하기 쉬운 형태로 정리합니다."""
    def g(*keys):
        for k in keys:
            v = e.get(k)
            if v:
                return v
        return ""
    date = g("prism:coverDate", "prism:coverDisplayDate")
    year = (re.findall(r"(19|20)\d{2}", str(date)) and re.search(r"((19|20)\d{2})", str(date)).group(1)) or ""
    # 아래 셋은 COMPLETE view 에서만 옵니다. STANDARD 응답이면 빈 값으로 남습니다.
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


# ------------------------------------------------------- 보유 문헌과 대조

def _norm(s):
    return re.sub(r"[^a-z0-9]", "", norm_text(s or "").lower())   # 색인 제목의 합자(Eﬀect)를 풀고 비교


def match_against_index(entries, rows, threshold=0.86):
    """Scopus 결과가 이미 라이브러리에 있는지 표시합니다.

    DOI가 같으면 확정, 아니면 제목 유사도로 판정합니다.
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
            hit, how = by_doi[d], "DOI 일치"
        else:
            t = _norm(e.get("title"))
            best, score = None, 0.0
            if t:
                for tn, r in titles:
                    s = difflib.SequenceMatcher(None, t, tn).ratio()
                    if s > score:
                        best, score = r, s
            if best and score >= threshold:
                hit, how = best, f"제목 유사 {score:.2f}"
        e = dict(e)
        e["owned"] = bool(hit)
        e["owned_id"] = hit["id"] if hit else ""
        e["owned_rel"] = hit["rel"] if hit else ""
        e["match_by"] = how
        out.append(e)
    return out


def doi_link(doi):
    """DOI 를 클릭 링크로. 캠퍼스 IP 에서는 이 링크가 바로 전문으로 갑니다."""
    doi = (doi or "").strip()
    if not doi:
        return ""
    return f"[{doi}](https://doi.org/{urllib.parse.quote(doi, safe='/:')})"


def oa_mark(e):
    """OA ✔ = 임시 폴더에 받아 둠 · OA = 오픈액세스로 확인됨 · — = 아니거나 미확인"""
    if e.get("oa_file"):
        return "OA ✔"
    if str(e.get("openaccess", "")).strip().lower() in ("1", "true") or e.get("oa_url"):
        return "OA"
    return "—"


def to_markdown(entries, meta=None, title="Scopus 검색 결과"):
    L = [f"# {title}", ""]
    if meta:
        L.append(f"질의 `{meta.get('query','')}` · 전체 {meta.get('total','?')}건 중 "
                 f"{meta.get('start',0)+1}–{meta.get('start',0)+len(entries)}번 표시"
                 + (f" · view {meta['view']}" if meta.get("view") else ""))
        if meta.get("quota_remaining"):
            L.append(f"남은 호출 할당량 {meta['quota_remaining']} / {meta.get('quota_limit','?')}")
        L.append("")
    owned = [e for e in entries if e.get("owned")]
    new = [e for e in entries if not e.get("owned")]
    if any("owned" in e for e in entries):
        L.append(f"**보유 {len(owned)}건 · 미보유 {len(new)}건**")
        L.append("")
    n_oa = sum(1 for e in entries if not e.get("owned") and oa_mark(e) != "—")
    n_got = sum(1 for e in entries if e.get("oa_file"))
    if n_oa or n_got:
        L.append(f"미보유 중 OA {n_oa}건 · 임시 폴더에 받아 둔 것 {n_got}건 (`OA ✔`)")
        L.append("")
    L += ["| # | 보유 | OA | 저자 | 연도 | 제목 | 저널 | 피인용 | DOI |",
          "|---|---|---|---|---|---|---|---|---|"]
    for i, e in enumerate(entries, 1):
        mark = f"✅ {e.get('owned_id','')}" if e.get("owned") else "—"
        L.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            i, mark, oa_mark(e), e.get("author", "")[:22], e.get("year", ""),
            (e.get("title", "") or "")[:78].replace("|", "/"),
            (e.get("journal", "") or "")[:34].replace("|", "/"),
            e.get("cited_by", ""), doi_link(e.get("doi", ""))))

    # 초록이 있으면(COMPLETE view) 항목별로 덧붙입니다 — 서지만 보고 고르지 않도록.
    if any(e.get("abstract") for e in entries):
        L += ["", "## 항목별 초록", ""]
        for i, e in enumerate(entries, 1):
            mark = f"보유 ✅ {e.get('owned_id','')}" if e.get("owned") else "미보유"
            L.append(f"### {i}. {e.get('title','')} ({e.get('year','')})")
            who = e.get("authors") or e.get("author", "")
            src = " · ".join(x for x in (who, e.get("journal", ""), doi_link(e.get("doi", ""))) if x)
            L.append(f"{src} · [{mark}]")
            if e.get("oa_file"):
                L.append(f"OA 수신: `{e['oa_file']}` · 전문 텍스트: `{e.get('oa_text') or '(추출 실패)'}`")
            elif e.get("oa_text"):
                L.append(f"OA 전문 텍스트: `{e['oa_text']}`" + (f" · {e['oa_note']}" if e.get("oa_note") else ""))
            elif e.get("oa_note"):
                L.append(f"OA: {e['oa_note']}")
            L.append("")
            L.append((e.get("abstract") or "").strip() or "(초록 없음)")
            if e.get("keywords"):
                L.append("")
                L.append("저자 키워드: " + e["keywords"])
            L.append("")
    return "\n".join(L) + "\n"
