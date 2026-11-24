# -*- coding: utf-8 -*-
"""오픈액세스 논문 받기 — 검색 결과 중 OA 인 것만 임시 폴더에 받아 전문 텍스트를 만듭니다.

**라이브러리에는 쓰지 않습니다.** 받은 PDF 는 설정 `oa_staging`(기본 `<index_dir>/_수신`)에,
전문 텍스트는 그 아래 `_text/` 에 둡니다. 임시 폴더는 인덱스 대상이 아닙니다.
라이브러리로 옮기는 것은 사용자가 자기 문헌 관리 프로그램으로 합니다. 옮겨서 `reindex` 가
편입하면, 다음 실행 때 짝이 되는 `_text` 를 `_text/_obsolete/` 로 치웁니다 (지우지 않습니다).

OA 판정은 둘을 함께 봅니다 — Scopus 의 `openaccess` 플래그, 그리고 OpenAlex 의
`best_oa_location`(리포지터리 사본까지 잡힙니다). **내려받는 주소는 OpenAlex 가 알려 준 것만 씁니다.**
구독 논문은 건드리지 않습니다. 요청은 도구 이름을 밝힌 User-Agent 로 보내고 간격을 둡니다.

한 DOI 는 한 번만 받습니다 (v0.9.2)
    결과 이름(`--name`)이나 질의가 달라도, 다른 컴퓨터가 받은 것이어도 임시 폴더에 이미 있으면
    OpenAlex 에 다시 묻지도 받지도 않고 항목에 oa_file · oa_text 만 채웁니다. 판정은 `_settle` 한 곳입니다.
      PDF   ① 수신 목록 `_manifest.json` ② 항목 자신의 oa_file ③ `_scopus/` 결과 JSON 들에 남은
            oa_file(수신 목록 이전 판이 받은 것). 파일이 지금 임시 폴더에 있어야 하고, ②③ 은 다른 DOI 도
            제 것이라고 적은 파일이면 쓰지 않습니다.
      전문  `_text/<DOI>.txt` 가 있으면 PDF 를 못 찾아도 받은 것으로 칩니다 (라이브러리로 옮긴 뒤 등).
    PDF 는 있는데 전문 텍스트가 없으면 받지 않고 텍스트만 만듭니다. 있는 텍스트는 덮어쓰지 않습니다.
    판정을 빠져나와 새로 받은 PDF 도 임시 폴더의 PDF 와 내용(크기 · md5)이 같으면 사본(<이름>_N.pdf)을
    만들지 않고 그 파일을 씁니다.

수신 목록 `<oa_staging>/_manifest.json`
    {"format": "paper-index/oa-staging", "version": 1,
     "files": {"<소문자 DOI>": {"file": "<임시 폴더 기준 PDF 상대경로>", "text": "_text/<DOI>.txt 또는 ''",
                               "bytes": 123, "md5": "…", "url": "…", "oa_status": "…", "fetched": "YYYY-MM-DD"}}}
    file 만 필수입니다. md5 · fetched 는 이 도구가 받은 줄에만 있고, ③ 에서 옮겨 적은 줄에는 없습니다.
    bytes 가 지금 파일 크기와 다르면 다른 파일로 바뀐 것으로 보고 그 줄을 쓰지 않습니다.
    쓸 때마다 디스크의 목록을 다시 읽어 합칩니다 — 다른 컴퓨터가 동기화로 보탠 줄 · 모르는 줄을 지우지 않습니다.
    읽을 수 없거나 모르는 형식(다른 format · version)이면 경고하고, 그 실행에서는 읽지도 쓰지도 않습니다.

항목에 남기는 필드
    oa_checked   OpenAlex 를 조회한 날 (ISO). 30일 안에는 다시 묻지 않습니다 (--recheck 로 강제)
    oa_status    gold / hybrid / green / bronze … 또는 scopus (플래그만 있을 때)
    oa_url       PDF 직접 주소, 없으면 OA 랜딩 주소
    oa_file      임시 폴더 기준 PDF 상대경로 — 받았다는 표시. 파일이 지금 임시 폴더에 있을 때만 둡니다
    oa_text      전문 텍스트 상대경로
    oa_note      받지 못한 이유, 또는 PDF 없이 전문 텍스트만 있다는 안내
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

UA = "paper-index-tool/1.0 (open-access fetch)"
OPENALEX = "https://api.openalex.org/works/doi:"
MIN_PDF_BYTES = 20_000
DEFAULT_LIMIT = 30          # 한 번에 받는 상한
DELAY = (3.0, 5.0)          # 다운로드 사이 간격(초)
LOOKUP_DELAY = 0.25         # OpenAlex 조회 사이 간격(초)
RECHECK_DAYS = 30           # OA 아님으로 판정한 항목을 다시 묻는 주기
MANIFEST = "_manifest.json"                                 # 수신 목록 — 형식은 모듈 설명
MANIFEST_FORMAT, MANIFEST_VERSION = "paper-index/oa-staging", 1
TEXT_ONLY_NOTE = "PDF 는 임시 폴더에 없고 전문 텍스트만 있음 — 라이브러리로 옮겼거나 지웠으면 정상입니다"


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
        raise NoNetwork(f"{urllib.parse.urlsplit(url).hostname} 에 연결할 수 없습니다: {e}")


def openalex(doi, timeout=20):
    """OpenAlex 가 아는 OA 위치. 모르는 DOI 면 None."""
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
    """PDF 바이트를 돌려줍니다. PDF 가 아니면 (None, 이유)."""
    st, _, ctype, body = _get(url, "application/pdf,*/*;q=0.8", timeout)
    if st != 200:
        return None, f"HTTP {st}"
    if body[:4] != b"%PDF":
        return None, f"PDF 아님 ({(ctype or '?').split(';')[0]}, {len(body)} B)"
    if len(body) < MIN_PDF_BYTES:
        return None, f"너무 작음 ({len(body)} B)"
    return body, ""


def _safe(s):
    s = re.sub(r'[\\/:*?"<>|]', " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


def filename_for(e):
    """라이브러리 관례 — <저자 성>-<제목 앞 56자>.pdf"""
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
    """임시 폴더 기준 상대경로를 비교용으로 — 구분자 · 대소문자(Windows)를 맞춥니다."""
    return os.path.normcase(os.path.normpath(rel))


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _replace(tmp, dst, tries=3):
    """os.replace — 동기화 프로그램이 대상을 잠깐 잡고 있으면(Windows PermissionError) 잠시 뒤 다시 합니다."""
    for i in range(tries):
        try:
            os.replace(tmp, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(2)


def _result_records(results_dir, log=print):
    """수신 목록 이전 판이 받은 기록 — 결과 JSON 들에 남은 oa_file. {DOI: [{"file", "url", "oa_status"}, …]}

    papertool 이 저장한 형식({"meta", "entries"})과 항목 목록(list)을 읽습니다. 문자열 "oa_file" 이 없는
    파일은 해석하지 않습니다. 읽을 수 없는 파일은 이름을 알리고 뺍니다."""
    out, bad = {}, []
    if not results_dir or not os.path.isdir(results_dir):
        return out
    for fn in sorted(os.listdir(results_dir)):
        p = os.path.join(results_dir, fn)
        if not fn.lower().endswith(".json") or not os.path.isfile(p):
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
        log(f"  ※ 결과 파일 {len(bad)}개를 읽지 못해 받은 기록에서 뺐습니다: " + ", ".join(bad[:5])
            + (" …" if len(bad) > 5 else ""))
    return out


class Staging:
    """임시 폴더에 무엇을 받아 두었나 — 수신 목록(`_manifest.json`)과, 목록 이전 판이 결과 JSON 에 남긴 기록."""

    def __init__(self, stg, txt_dir, results_dir="", log=print):
        self.stg, self.txt_dir, self.results_dir, self.log = stg, txt_dir, results_dir, log
        self.path = os.path.join(stg, MANIFEST)
        self.files, self.added = {}, {}          # 쓸 수 있는 줄 {DOI: 기록} · 이번 실행에 보탠 줄
        self._legacy = None                       # {DOI: [기록]} — 필요할 때 한 번 읽습니다
        self._legacy_owners = {}                  # {파일 키: {DOI}}
        raw, why = self._read()
        self.usable = raw is not None
        if why:
            log(f"  ※ 수신 목록을 쓰지 않습니다 — {why}: {self.path}\n"
                "    이번 실행은 전문 텍스트와 결과 JSON 의 기록으로만 판정하고, 목록은 고치지 않습니다.")
        bad = 0
        for doi, rec in (raw or {}).items():
            if isinstance(rec, dict) and isinstance(rec.get("file"), str) and rec["file"]:
                self.files[_norm_doi(doi)] = rec
            else:
                bad += 1
        if bad:
            log(f"  ※ 수신 목록에서 file 이 없는 줄 {bad}개를 건너뜁니다 (지우지는 않습니다): {self.path}")

    def _read(self):
        """(디스크 목록의 files dict, 쓰지 않는 이유). 파일이 없으면 ({}, "")."""
        if not os.path.exists(self.path):
            return {}, ""
        try:
            with open(self.path, encoding="utf-8-sig") as f:
                d = json.load(f)
        except (OSError, ValueError) as ex:
            return None, f"읽을 수 없음 ({ex})"
        if not (isinstance(d, dict) and d.get("format") == MANIFEST_FORMAT
                and d.get("version") == MANIFEST_VERSION and isinstance(d.get("files"), dict)):
            got = (d.get("format"), d.get("version")) if isinstance(d, dict) else (type(d).__name__, None)
            return None, "모르는 형식 (format {!r} · version {!r})".format(*got)
        return d["files"], ""

    def _ok(self, rel):
        return os.path.isfile(os.path.join(self.stg, rel))

    def _rec_ok(self, rec):
        """목록의 줄이 지금도 맞는가 — 파일이 있고, 적힌 크기와 같습니다."""
        p = os.path.join(self.stg, rec["file"])
        if not os.path.isfile(p):
            return False
        n = rec.get("bytes")
        return not (isinstance(n, int) and n > 0 and os.path.getsize(p) != n)

    def _owners(self, rel):
        """이 파일을 제 것이라고 적은 DOI 들 — 수신 목록(지금도 맞는 줄)과 결과 JSON."""
        k = _key(rel)
        out = {d for d, r in self.files.items() if _key(r["file"]) == k and self._rec_ok(r)}
        return out | self._legacy_owners.get(k, set())

    def _unmapped(self):
        """임시 폴더의 PDF 가운데 수신 목록에 없는 것 — 이것이 있을 때만 결과 JSON 을 읽습니다."""
        mapped = {_key(r["file"]) for r in self.files.values() if self._rec_ok(r)}
        try:
            names = os.listdir(self.stg)
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
        """결과 JSON 의 기록 가운데 임시 폴더에 지금 있고 주인이 하나뿐인 것을 목록에 옮겨 적습니다."""
        for d, recs in sorted(self._legacy.items()):
            cur = self.files.get(d)
            if cur and self._rec_ok(cur):
                continue
            for r in recs:
                if self._ok(r["file"]) and self._owners(r["file"]) <= {d}:
                    self.remember(d, r["file"], r)
                    break

    def pdf_for(self, e):
        """이 항목의 DOI 로 받아 둔 PDF — (상대경로, 기록). 지금 임시 폴더에 없으면 ("", 남은 기록 또는 None).

        PDF 가 없어도 기록을 돌려주는 것은 url · oa_status 를 채우기 위해서입니다."""
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
        """내용(md5)이 같은 PDF 가 임시 폴더에 이미 있으면 그 이름. 크기가 같은 파일만 읽습니다."""
        try:
            names = sorted(os.listdir(self.stg))
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
        """받아 둔 PDF 를 목록에 적습니다 — 이미 같은 줄이 있으면 그대로 둡니다. text 가 None 이면 있는 것을 찾습니다."""
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
        """이번 실행에 보탠 줄을 디스크의 목록에 합쳐 씁니다. 목록을 못 읽은 실행이면 쓰지 않습니다."""
        if not self.usable or not self.added:
            return
        raw, why = self._read()                       # 그사이 다른 컴퓨터가 보탠 줄을 살립니다
        if raw is None:
            self.usable = False
            self.log(f"  ※ 수신 목록이 그사이 {why} — 고치지 않습니다: {self.path}")
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
            self.log(f"  ※ 수신 목록을 쓰지 못했습니다 ({ex}) — 받은 기록은 결과 JSON 에 남습니다: {self.path}")


def _settle(e, st, txt_dir, pdftotext):
    """이미 받아 둔 DOI 면 항목에 oa_file · oa_text 를 채우고 (True, 전문을 새로 만들었나). 아니면 (False, False).

    PDF 는 있는데 전문 텍스트가 없으면 여기서 만듭니다 — 다시 받지 않습니다. 있는 텍스트는 그대로 둡니다.
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
    """미보유 항목 가운데 OA 인 것을 받습니다. 항목 dict 에 oa_* 필드를 채우고 요약을 돌려줍니다.

    이미 받아 둔 DOI 는 다시 받지 않습니다(`_settle`). NoNetwork 는 그대로 올립니다 — 호출 쪽이 안내를
    내고 결과 저장은 계속합니다. P["scopus"] 가 있으면 그 폴더의 결과 JSON 에서 옛 수신 기록을 찾습니다.
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
                    log(f"  전문 텍스트 만듦 (이미 받아 둔 PDF): {e['oa_file']}")
                continue
            for k in ("oa_file", "oa_text"):          # 임시 폴더에 없는 것을 받았다고 적어 두지 않습니다
                e.pop(k, None)
            if not recheck and not e.get("oa_url") and _recently_checked(e, today):
                continue
            if got >= limit:
                left += 1
                continue
            doi = e["doi"]
            checked += 1
            info = openalex(doi)                     # NoNetwork 는 여기서 올라갑니다
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
                e["oa_note"] = "OA 이지만 PDF 직접 주소가 없음 — 링크로 직접 받으십시오"
                failed.append((doi, e["oa_note"]))
                continue

            if got:
                time.sleep(random.uniform(*DELAY))
            try:
                data, why = download(pdf_url)
            except NoNetwork as ex:
                data, why = None, str(ex)
            if data is None:
                # 출판사가 비브라우저 요청을 막는 경우(Springer·MDPI 등)가 흔합니다.
                # 사용자가 클릭할 수 있게 랜딩 주소를 남기고 다음으로 넘어갑니다.
                e["oa_note"] = f"다운로드 실패: {why} — 링크로 직접 받으십시오"
                e["oa_url"] = info.get("landing") or pdf_url
                failed.append((doi, e["oa_note"]))
                continue

            if not e.get("year") and info.get("year"):
                e["year"] = info["year"]
            digest = hashlib.md5(data).hexdigest()
            same = st.same_content(len(data), digest)
            if same:                                 # 내용이 같은 파일이 이미 있으면 사본을 만들지 않습니다
                dest = os.path.join(stg, same)
                reused += 1
            else:
                dest = _unique(stg, filename_for(e))
                tmp = dest + ".part"
                with open(tmp, "wb") as f:
                    f.write(data)
                _replace(tmp, dest)
            txt = os.path.join(txt_dir, text_name(doi))
            ok = os.path.exists(txt) or to_text(pdftotext, dest, txt)    # 있는 텍스트는 덮어쓰지 않습니다
            e["oa_file"] = _rel(dest, stg)
            e["oa_text"] = _rel(txt, stg) if ok else ""
            e.pop("oa_note", None)
            st.record(_norm_doi(doi), {"file": e["oa_file"], "text": e["oa_text"], "bytes": len(data),
                                       "md5": digest, "url": pdf_url, "oa_status": e["oa_status"],
                                       "fetched": today.isoformat()})
            st.save()                                # 받을 때마다 — 도중에 끊겨도 받은 것은 남습니다
            got += 1
            if verbose:
                log(f"  OA 수신 {got}: {os.path.basename(dest)}  ({len(data):,} B"
                    + (", 같은 내용의 기존 파일을 씀" if same else "")
                    + ("" if ok else ", 전문 텍스트 추출 실패") + ")")
    finally:
        st.save()

    pruned = prune_text(txt_dir, owned)
    return dict(checked=checked, oa=n_oa, downloaded=got, reused=reused, already=already, text_made=made,
                failed=failed, pruned=pruned, staging=stg, text_dir=txt_dir, limit_hit=left > 0)


def prune_text(txt_dir, owned_dois):
    """이미 라이브러리에 편입된 DOI 의 전문 텍스트를 _obsolete/ 로 치웁니다 (삭제하지 않습니다)."""
    if not os.path.isdir(txt_dir) or not owned_dois:
        return 0
    import shutil
    names = {text_name(d) for d in owned_dois}
    obs = os.path.join(txt_dir, "_obsolete")
    n = 0
    for f in os.listdir(txt_dir):
        if f.endswith(".txt") and f in names:
            os.makedirs(obs, exist_ok=True)
            try:
                shutil.move(os.path.join(txt_dir, f), os.path.join(obs, f))
                n += 1
            except OSError:
                pass
    return n
