#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""papertool — PDF 문헌 라이브러리 인덱싱·전문 검색 도구.

라이브러리 폴더는 **읽기만** 합니다. 인덱스와 전문 캐시는 별도 폴더에 사본으로 만듭니다.

    papertool.py init <라이브러리경로> [--index-dir DIR] [--preset NAME] [--name NAME]
    papertool.py index [--limit N]        전문 추출 + 메타데이터 + 태그 + 인덱스 생성
    papertool.py reindex                  새 파일만 추가 (기존 수동 보정 보존)
    papertool.py resync                   파일명이 바뀌었을 때 경로 재매칭
    papertool.py repair                   인코딩이 깨진 PDF 전문 복원
    papertool.py tags-auto [--top 20]     코퍼스에서 태그 프리셋 초안 생성
    papertool.py search <말> [<말> ...]    전문 검색 (보유 문헌)
    papertool.py doctor                   상태 점검 (누락·중복·깨짐)

    papertool.py scopus "<질의>"           Scopus 검색(초록 포함) + 보유 문헌 대조. --all 로 전량 수신
    papertool.py scopus-sift <파일.json>   받아 둔 결과를 정규식으로 거름 (오프라인, API 호출 없음)
    papertool.py scopus-merge <파일.json>  저장된 Scopus 결과를 보유 문헌과 대조 (오프라인)
    papertool.py scopus-tidy              옛 판(0.9 이하)이 만든 실행 파일(.bat/.query.txt)을 보관함으로 정리
    papertool.py scopus "<질의>" --fetch-oa   검색·대조 뒤 미보유 OA 논문만 임시 폴더(_oa_inbox)에 받아 전문 텍스트까지
    papertool.py oa-fetch <파일.json>      저장된 결과의 OA 논문만 받음 (라이브러리에는 쓰지 않음)

검색 옵션:  --or  --tag TAG  --year 2019-2026  -n 5  -c 200

Scopus API 키는 **환경변수 `ELS_API_KEY`** 에서만 읽습니다. 설정 파일이나 명령줄에
적지 마십시오. 기관 토큰이 있으면 `ELS_INST_TOKEN` 을 함께 설정합니다.
"""
import argparse, json, os, re, sys


def _콘솔_UTF8():
    """Windows 기본 콘솔(cp949)은 '—'·'✅' 같은 문자를 못 써서 출력 도중 죽습니다.
    어느 셸에서 돌려도 되도록 표준 출력을 UTF-8 로 맞춥니다.
    `PYTHONIOENCODING` 을 앞에 붙일 필요가 없어집니다."""
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


_콘솔_UTF8()

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from lib import (config, extract, meta, tagging, render, resync as resync_mod,  # noqa: E402
                 searching, decode, wordsplit, scopus as scopus_mod, oafetch)
from lib.textnorm import norm_text  # noqa: E402


def _load(args):
    cfg = config.load(getattr(args, "config", None))
    return cfg, config.paths(cfg)


def _preset(cfg):
    p = config.load_preset(cfg, ROOT)
    if p is None:
        return None, {}, []
    return p, tagging.compile_preset(p), list(p["tags"].keys())


def _require_library(cfg, what):
    """라이브러리 폴더가 없으면 멈춥니다.

    후보가 하나도 실재하지 않는데 그대로 돌면 `doctor` 는 '원본 0편·경로 누락 전부' 를,
    `reindex` 는 엉뚱한 폴더의 파일을 새 문헌으로 보고합니다. 조용히 도는 것보다 멈추는 편이 낫습니다.
    (2026-09-03 노트북에서 21편짜리 잔존 사본을 집어 인덱스를 망친 사고 뒤에 넣었습니다.)"""
    if os.path.isdir(cfg["library"]):
        return
    cands = cfg.get("_library_candidates") or [cfg["library"]]
    lines = [f"라이브러리 폴더를 찾을 수 없어 `{what}` 를 중단합니다.",
             "설정의 library 후보 가운데 실재하는 폴더가 없습니다:"]
    lines += [f"  - {c}" for c in cands]
    lines += ["드라이브가 마운트됐는지 확인하거나, 이 컴퓨터의 경로를 후보에 추가하십시오.",
              f"설정 파일: {cfg.get('_path', '')}"]
    sys.exit("\n".join(lines))


def _library_too_small(cfg, n_lib, n_index):
    """고른 라이브러리의 PDF 수가 인덱스의 절반에도 못 미치면 True — 다른 폴더를 집었거나 동기화가 덜 끝난 신호."""
    return bool(n_index) and n_lib < n_index * 0.5


def _texts(paths, rows, limit=350):
    """어휘 · 태그 초안용 전문 — 글자 정규화(합자 등)를 거친 사본입니다."""
    out = []
    for r in rows[:limit]:
        p = os.path.join(paths["fulltext"], r["txt"])
        if os.path.exists(p):
            out.append(norm_text(open(p, encoding="utf-8", errors="ignore").read()))
    return out


# ------------------------------------------------------------------ commands

def cmd_init(args):
    lib = os.path.abspath(args.library)
    if not os.path.isdir(lib):
        sys.exit(f"라이브러리 폴더가 없습니다: {lib}")
    target = os.path.abspath(args.out or os.path.join(os.getcwd(), "paperindex.config.json"))
    cfg = dict(config.DEFAULT)
    cfg["library"] = lib
    cfg["name"] = args.name or os.path.basename(lib.rstrip("/\\"))
    cfg["index_dir"] = os.path.abspath(args.index_dir or os.path.join(os.path.dirname(target), "index"))
    cfg["preset"] = args.preset or ""
    config.save(cfg, target)
    os.makedirs(cfg["index_dir"], exist_ok=True)
    print(f"설정 생성: {target}")
    print(f"  라이브러리 : {cfg['library']}")
    print(f"  인덱스     : {cfg['index_dir']}")
    print(f"  프리셋     : {cfg['preset'] or '(없음 — tags-auto 로 만들거나 자동 임계 태깅)'}")
    print("\n다음: papertool.py index")


def cmd_index(args):
    cfg, P = _load(args)
    _require_library(cfg, "index")
    os.makedirs(P["fulltext"], exist_ok=True)
    st = extract.extract_missing(cfg, P["fulltext"], limit=args.limit)
    print(f"전문 추출: {st['done']}편 처리, {st['remaining']}편 남음 (전체 대상 {st['total']}편)")
    if st["failed"]:
        print("  추출 실패:", len(st["failed"]))
    if st["remaining"]:
        print("  → 남은 게 있으니 `index` 를 한 번 더 실행하십시오.")
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
    render.write_json(rows, P["json"])
    render.write_csv(rows, P["csv"])
    ng = render.write_md(rows, P["md"], cfg, order)
    moved = extract.prune_orphans(P["fulltext"], {r["txt"] for r in rows} | {"_vocab.json"})
    print(f"인덱스 생성: {len(rows)}편 · 중복 {ng}그룹 · 구 캐시 {moved}개 이동")
    if not compiled:
        print("  ※ 프리셋이 없어 태그가 비어 있습니다. `tags-auto` 로 초안을 만드십시오.")


def cmd_reindex(args):
    cfg, P = _load(args)
    _require_library(cfg, "reindex")
    rows = searching.load_rows(P)
    cur = list(extract.scan(cfg["library"]))
    if _library_too_small(cfg, len(cur), len(rows)) and not getattr(args, "force", False):
        sys.exit(f"라이브러리 원본이 {len(cur)}편인데 인덱스는 {len(rows)}편입니다. "
                 "다른 폴더를 집었거나 동기화가 덜 끝난 것 같습니다.\n"
                 f"라이브러리: {cfg['library']}\n"
                 "정말 이 폴더가 맞으면 `reindex --force` 로 다시 실행하십시오.")
    known = {r["rel"] for r in rows}
    preset, compiled, order = _preset(cfg)
    added = 0
    for rel in cur:
        if rel in known:
            continue
        tp = os.path.join(P["fulltext"], extract.txtname(rel))
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
    render.write_json(rows, P["json"])
    render.write_csv(rows, P["csv"])
    render.write_md(rows, P["md"], cfg, order)
    print(f"신규 {added}편 추가 · 총 {len(rows)}편")
    if added:
        print("  ※ 새 항목의 제목·저널은 자동 추정입니다. 이상하면 papers_index.json 에서 고친 뒤 다시 실행하십시오.")


def cmd_resync(args):
    cfg, P = _load(args)
    _require_library(cfg, "resync")
    rows = searching.load_rows(P)
    if not rows:
        sys.exit("인덱스가 없습니다. 먼저 `index` 를 실행하십시오.")
    res = resync_mod.resync(rows, cfg, P["fulltext"])
    print(f"경로 재매칭 완료 · 유지 {len(res['rows'])}편")
    if res["dropped"]:
        print(f"  원본에서 사라져 제거: {len(res['dropped'])}편")
        for r in res["dropped"][:10]:
            print("   -", r["rel"])
    if res["collided"]:
        print(f"  중복본 삭제로 합쳐진 항목: {len(res['collided'])}편")
    if res["new"]:
        print(f"  인덱스에 없는 새 파일: {len(res['new'])}편 → `reindex` 를 실행하십시오")
    rows = res["rows"]
    preset, compiled, order = _preset(cfg)
    render.assign_ids(rows, cfg["id_prefix"])
    render.write_json(rows, P["json"])
    render.write_csv(rows, P["csv"])
    render.write_md(rows, P["md"], cfg, order)
    moved = extract.prune_orphans(P["fulltext"], {r["txt"] for r in rows} | {"_vocab.json"})
    print(f"  구 캐시 {moved}개를 _obsolete/ 로 이동")


NOTE_BROKEN = ("※ PDF 폰트 인코딩 결함. 전문 캐시는 복원본입니다. "
               "일부 구간의 글자가 어긋나므로 인용 전 원본 PDF 확인 필수")
NOTE_FAIL = "※ PDF 텍스트 레이어 손상 — 전문 검색 불가. 원본 재다운로드 또는 OCR 필요"


def cmd_repair(args):
    cfg, P = _load(args)
    _require_library(cfg, "repair")
    rows = searching.load_rows(P)
    fixed = failed = 0
    targets = []
    for r in rows:
        p = os.path.join(P["fulltext"], r["txt"])
        if not os.path.exists(p):
            continue
        t = open(p, encoding="utf-8", errors="ignore").read()
        if decode.looks_broken(t) or "인코딩" in r.get("note", ""):
            targets.append((r, p, t))
    print(f"복원 대상: {len(targets)}편")
    for r, p, t in targets:
        new = decode.decode_pdf(os.path.join(cfg["library"], r["rel"]), cfg["pdftotext"])
        if decode.density(new) > max(decode.density(t) * 3, 0.05):
            open(p, "w", encoding="utf-8").write(new)
            r["note"] = NOTE_BROKEN
            r["chars"] = len(new)
            fixed += 1
            print(f"  복원 {r['id']} {r['file'][:48]}  밀도 {decode.density(t):.3f}→{decode.density(new):.3f}")
        else:
            r["note"] = NOTE_FAIL
            failed += 1
            print(f"  실패 {r['id']} {r['file'][:48]}")
    if fixed:
        # 붙어 버린 단어 분리
        vocab = wordsplit.load_or_build(P["vocab"], _texts(P, [r for r in rows if "인코딩" not in r.get("note", "")]))
        sp = wordsplit.Splitter(vocab)
        for r, p, _ in targets:
            if r.get("note") == NOTE_BROKEN:
                t = open(p, encoding="utf-8", errors="ignore").read()
                open(p, "w", encoding="utf-8").write(sp.text(t))
    preset, compiled, order = _preset(cfg)
    render.write_json(rows, P["json"])
    render.write_csv(rows, P["csv"])
    render.write_md(rows, P["md"], cfg, order)
    print(f"복원 {fixed} / 실패 {failed}")


def cmd_tags_auto(args):
    cfg, P = _load(args)
    rows = searching.load_rows(P)
    if not rows:
        sys.exit("인덱스가 없습니다. 먼저 `index` 를 실행하십시오.")
    texts = _texts(P, rows, limit=args.sample)
    preset = tagging.auto_preset(texts, name=(cfg.get("name") or "auto"),
                                 top=args.top, min_df=args.min_df)
    out = args.out or os.path.join(P["index_dir"], "tags.auto.json")
    tagging.save_preset(preset, out)
    print(f"태그 초안 {len(preset['tags'])}개 → {out}\n")
    for k in preset["tags"]:
        print("  -", k)
    print("\n손으로 다듬은 뒤 presets/ 로 옮기고 config 의 `preset` 에 파일명을 적으십시오.")
    print("그 다음 `index` 를 다시 실행하면 태그가 반영됩니다.")


# 검색 깊이 프리셋 — 스캔은 전수, 출력만 자릅니다.
#   quick : 표현·용어·문장이 쓰이는지만 확인. 대표 사례 몇 개면 충분한 질문
#   focus : 주장·인용 근거·리뷰어 대응. 제한된 범위의 원문 검증 (기본값)
#   full  : 전수 조사, 부재·신규성 주장 검토. 명시적으로 요청받았을 때만
DEPTH_PRESETS = {
    "quick": dict(max_docs=3,  brief_docs=10, n=1, context=90),
    "focus": dict(max_docs=8,  brief_docs=20, n=3, context=120),
    "full":  dict(max_docs=0,  brief_docs=-1, n=3, context=140),
}
DEFAULT_DEPTH = "focus"


def _depth_opts(args):
    """프리셋을 깔고, 사용자가 명시한 인자만 덮어씁니다."""
    o = dict(DEPTH_PRESETS[args.depth or DEFAULT_DEPTH])
    for k in ("max_docs", "brief_docs", "n", "context"):
        v = getattr(args, k, None)
        if v is not None:
            o[k] = v
    return o


def cmd_search(args):
    cfg, P = _load(args)
    if not os.path.isdir(cfg["library"]):
        print("※ 라이브러리 폴더가 없어 전문 캐시만 검색합니다. 인용 전 원본 PDF 대조는 할 수 없습니다.",
              file=sys.stderr)
    o = _depth_opts(args)
    rows, hits, stats = searching.search(
        P, args.terms, any_of=args.any_of, tag=args.tag, year=args.year,
        snippets=o["n"], context=o["context"], max_docs=o["max_docs"],
        brief_docs=o["brief_docs"], stop_after=args.stop_after or 0,
        count_only=args.count_only)
    if not args.terms:
        for r in rows:
            print(f"{r['id']} [{r.get('year','')}] {r['title']}  <{r['rel']}>")
        print(f"\n총 {len(rows)}편")
        return
    print(searching.format_hits(args.terms, rows, hits, stats))


def _slug(s, n=48):
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "-", s).strip("-").lower()
    return (s[:n] or "query")


def _scopus_dir(P):
    d = P["scopus"]
    os.makedirs(d, exist_ok=True)
    return d


ARCHIVE_DIRNAME = "_실행완료"


def _archive_launchers(P, verbose=True):
    """옛 판(0.9 이하)이 만든 `Scopus검색_*.bat` / `.query.txt` 를 보관함으로 옮깁니다.

    지금 판은 실행 파일을 만들지 않습니다 — 옛 판이 인덱스 폴더에 남긴 것만 다룹니다.
    결과 JSON 이 이미 있는 것만 `_scopus/_실행완료/` 로 옮기고(지우지 않습니다), 결과가 없는 것은 그대로 둡니다.
    """
    import glob, shutil
    d = P["index_dir"]
    arc = os.path.join(_scopus_dir(P), ARCHIVE_DIRNAME)
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
                print(f"  (이동 실패: {os.path.basename(src)} — {e})")

    for bat in sorted(glob.glob(os.path.join(d, "Scopus검색_*.bat"))):
        tag = os.path.splitext(os.path.basename(bat))[0].replace("Scopus검색_", "", 1)
        if not os.path.exists(os.path.join(_scopus_dir(P), tag + ".json")):
            continue                      # 결과가 아직 없으면 남겨 둡니다
        for f in (bat, os.path.splitext(bat)[0] + ".query.txt"):
            if os.path.exists(f):
                move(f)
    # 옛 판이 .bat 옆에 두던 스크립트 사본은, 남은 실행 파일이 없을 때만 함께 치웁니다.
    ps1 = os.path.join(d, "scopus_search.ps1")
    if os.path.exists(ps1) and not glob.glob(os.path.join(d, "Scopus검색_*.bat")):
        move(ps1)
    if moved and verbose:
        print(f"실행 파일 {len(moved)}개를 {ARCHIVE_DIRNAME}/ 로 옮겼습니다: " +
              ", ".join(sorted(set(moved))[:6]) + (" …" if len(moved) > 6 else ""))
    return moved


def _report(entries, meta_, P, name, quiet=False, fetch_oa=False, cfg=None,
            oa_limit=None, recheck=False):
    """Scopus 결과를 보유 문헌과 대조해 저장하고 요약을 찍습니다.

    fetch_oa 이면 대조 뒤 미보유 OA 논문을 임시 폴더에 받고(oafetch) 그 결과(oa_* 필드)까지
    json/md 에 남깁니다. 검색 범위는 그대로이고, 라이브러리에는 쓰지 않습니다."""
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
    print(f"\n저장: {jf}\n      {mf}")
    print(f"검색 {len(merged)}건 · 보유 {own} · 미보유 {len(merged)-own}"
          + (f" · 초록 {nabs}건" if nabs else "")
          + (f" · 전체 적중 {meta_.get('total')}건" if meta_.get("total") else ""))
    if not nabs and merged:
        print("  ※ 초록이 없습니다 — STANDARD 응답(권한 제한)이거나 구버전 도구로 받은 파일입니다.")
    if oa:
        _print_oa(oa)
    if not quiet:
        print()
        print(scopus_mod.to_markdown(merged, meta_))
    return merged


def _fetch_oa(merged, cfg, P, rows, limit, recheck):
    """미보유 OA 논문을 임시 폴더에 받습니다. 네트워크가 막히면 안내만 내고 None."""
    owned = [r.get("doi") for r in rows if r.get("doi")]
    print("\nOA 확인·수신 — OpenAlex 를 조회해 임시 폴더로 받습니다 (라이브러리에는 쓰지 않습니다) …")
    try:
        return oafetch.fetch(merged, cfg or {}, P, limit=limit or oafetch.DEFAULT_LIMIT,
                             owned_dois=owned, recheck=recheck)
    except oafetch.NoNetwork as e:
        print("[OA 수신 불가] " + str(e))
        print("  검색 결과는 그대로 저장합니다. 네트워크가 닿는 컴퓨터에서 `oa-fetch <파일.json>` 을 돌리십시오.")
        return None


def _print_oa(s):
    print(f"OA: 확인 {s['checked']}건 · OA {s['oa']}건 · 수신 {s['downloaded']}편 → {s['staging']}")
    if s["already"]:
        print(f"    이미 받아 둔 {s['already']}편은 다시 받지 않았습니다 (DOI 기준 — 다른 결과 이름 · 다른 컴퓨터가 받은 것 포함)"
              + (f". 그중 {s['text_made']}편은 전문 텍스트를 새로 만들었습니다" if s["text_made"] else ""))
    if s["reused"]:
        print(f"    새로 받은 것 가운데 {s['reused']}편은 내용이 같은 PDF 가 이미 있어 사본을 만들지 않았습니다.")
    if s["downloaded"] or s["already"]:
        print(f"    전문 텍스트: {s['text_dir']}  ← 근거 문장은 여기서 읽습니다")
    for doi, why in s["failed"][:10]:
        print(f"    - {doi}: {why}")
    if len(s["failed"]) > 10:
        print(f"    - … 외 {len(s['failed']) - 10}건 (md 의 항목별 초록에 적혀 있습니다)")
    if s["limit_hit"]:
        print("    ※ 회당 상한에 걸렸습니다. 같은 명령을 다시 실행하면 이어서 받습니다.")
    if s["pruned"]:
        print(f"    편입된 문헌의 전문 텍스트 {s['pruned']}개를 _text/_obsolete/ 로 옮겼습니다.")
    print("    ※ 임시 폴더는 라이브러리가 아닙니다. 남길 PDF 는 문헌 관리 프로그램으로 옮기고 인덱스를 갱신하십시오.")


def _warn_capped(m):
    """키가 요청한 페이지 크기를 거부해 줄여 받았으면 알립니다 (scopus.search 의 `count_asked`)."""
    if m.get("count_asked"):
        print(f"※ Scopus 가 한 페이지 {m['count_asked']}건을 거부했습니다(HTTP 400 — 키의 서비스 등급 상한). "
              f"{m['count']}건씩 받습니다 — 설정 `scopus.page_size` · `--count` 를 그 이하로 두면 이 재요청이 없어집니다.")


def _fetch_all(args, first, meta_, view, sort, page_size=scopus_mod.PAGE_SIZE):
    """--all: 첫 페이지 이후를 마저 받습니다.

    이후 페이지는 첫 응답의 실제 view 로 고정해 COMPLETE 폴백 재시도를 반복하지 않습니다.
    페이지 크기는 설정 `scopus.page_size`(기본 scopus.PAGE_SIZE)를 그 view 의 상한으로 자른 값입니다.
    키가 그 크기를 거부하면 scopus.search 가 기본 크기로 다시 받고, 남은 페이지도 그 크기로 받습니다.
    """
    total = meta_["total"]
    end = min(total, scopus_mod.PAGE_CAP)
    if total > end:
        print(f"※ 전체 {total}건 중 페이지네이션 상한 {end}번째까지만 받습니다. 연도 분할을 고려하십시오.")
    want = end - args.start
    got_view = view or meta_.get("view")
    page = scopus_mod.page_limit(meta_.get("view"), page_size)
    if meta_.get("count_asked"):          # 첫 페이지가 이미 거부돼 줄여 받았으면 그 크기로
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
            print(f"  … {len(out)}/{want}건 수신")
    if len(out) < want:
        print(f"※ {want}건 중 {len(out)}건만 받았습니다 — 중간 페이지가 비었거나 페이지 사이에 중복이 있었습니다. "
              "같은 명령을 다시 돌려 전체 건수를 확인하십시오.")
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
        count = min(count, scopus_mod.page_limit(view, sc["page_size"]))   # 첫 페이지는 COMPLETE 일 수 있음
    try:
        entries, meta_ = scopus_mod.search(args.query, count=count, start=args.start,
                                           view=view, sort=sort)
        _warn_capped(meta_)
        if args.all and min(meta_["total"], scopus_mod.PAGE_CAP) > args.start + len(entries):
            entries, meta_ = _fetch_all(args, entries, meta_, view, sort, sc["page_size"])
    except scopus_mod.NoKey as e:
        print("[Scopus 사용 불가] " + str(e))
        _howto(args, P, name, count)
        return
    except scopus_mod.NoNetwork as e:
        print("[Scopus 사용 불가] " + str(e))
        _howto(args, P, name, count)
        return
    except scopus_mod.ScopusError as e:
        print("[Scopus 오류] " + str(e))
        return
    _report(entries, meta_, P, name, quiet=args.quiet, fetch_oa=args.fetch_oa, cfg=cfg,
            oa_limit=args.oa_limit, recheck=args.recheck)


def _howto(args, P, name, count):
    """직접 호출이 막혔을 때, 키가 설정된 컴퓨터의 터미널에서 돌릴 명령을 안내합니다."""
    out = os.path.join(_scopus_dir(P), name + ".json")
    print("\n─ 키가 설정된 컴퓨터의 터미널에서 아래를 실행한 뒤 결과 파일을 대조하십시오 ─\n")
    print(f'    python -X utf8 "<도구>/papertool.py" scopus "{args.query}" --count {count}'
          + (" --all" if args.all else "") + f' --name "{name}"')
    print("\n  그 다음 (네트워크 없이 가능):")
    print(f'    papertool.py scopus-merge "{out}"')


def _load_result_file(path):
    """papertool 이 저장한 파일 또는 Scopus 원본 응답을 (entries, meta) 로 읽습니다."""
    # utf-8-sig: 다른 도구가 붙인 BOM 을 흡수합니다.
    raw = json.load(open(path, encoding="utf-8-sig"))
    if isinstance(raw, dict) and "entries" in raw:
        return raw["entries"], raw.get("meta", {})
    if isinstance(raw, dict) and "search-results" in raw:        # Scopus 원본 응답
        res = raw["search-results"]
        entries = [scopus_mod.normalize(e) for e in (res.get("entry") or []) if "error" not in e]
        return entries, {"query": "(원본 응답)", "total": int(res.get("opensearch:totalResults", 0) or 0)}
    if isinstance(raw, list):
        return raw, {}
    sys.exit("알 수 없는 형식입니다. Scopus 원본 응답이나 papertool 이 저장한 파일이어야 합니다.")


def cmd_scopus_merge(args):
    cfg, P = _load(args)
    entries, meta_ = _load_result_file(args.file)
    name = args.name or _slug(os.path.splitext(os.path.basename(args.file))[0])
    _report(entries, meta_, P, name, quiet=args.quiet, fetch_oa=args.fetch_oa, cfg=cfg,
            oa_limit=args.oa_limit, recheck=args.recheck)


def cmd_oa_fetch(args):
    """저장된 결과 파일의 미보유 OA 논문만 임시 폴더에 받습니다. Scopus 는 다시 부르지 않습니다."""
    cfg, P = _load(args)
    entries, meta_ = _load_result_file(args.file)
    name = args.name or _slug(os.path.splitext(os.path.basename(args.file))[0])
    _report(entries, meta_, P, name, quiet=True, fetch_oa=True, cfg=cfg,
            oa_limit=args.limit, recheck=args.recheck)


def cmd_scopus_sift(args):
    """받아 둔 결과를 정규식으로 걸러 정밀도를 회복합니다. API 호출이 없습니다.

    원소 기호처럼 대소문자가 의미를 갖는 패턴을 위해 기본이 대소문자 구분입니다.
    """
    cfg, P = _load(args)
    entries, meta_ = _load_result_file(args.file)
    if not (args.require or args.exclude):
        sys.exit("--require 나 --exclude 중 하나는 있어야 합니다.")
    flags = re.IGNORECASE if args.ignore_case else 0
    req = re.compile(args.require, flags) if args.require else None
    exc = re.compile(args.exclude, flags) if args.exclude else None

    def blob(e):
        return " ".join(x for x in (e.get("title"), e.get("abstract"), e.get("keywords")) if x)

    kept = [e for e in entries
            if (not req or req.search(blob(e))) and not (exc and exc.search(blob(e)))]
    print(f"거름: {len(entries)}건 → {len(kept)}건")
    if entries and not any(e.get("abstract") for e in entries):
        print("※ 초록이 없는 파일이라 제목·키워드만 보고 걸렀습니다. 신뢰도가 낮습니다.")
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
        print("치울 실행 파일이 없습니다. (옛 판이 만든 것 가운데 결과 JSON 이 있는 것만 옮깁니다)")


def cmd_doctor(args):
    cfg, P = _load(args)
    _require_library(cfg, "doctor")
    rows = searching.load_rows(P)
    cur = set(extract.scan(cfg["library"]))
    print(f"라이브러리: {cfg['library']}")
    idx = {r["rel"] for r in rows}
    import collections
    c = collections.Counter(r["rel"] for r in rows)
    print(f"원본 {len(cur)}편 / 인덱스 {len(rows)}편 / 캐시 "
          f"{len([f for f in os.listdir(P['fulltext']) if f.endswith('.txt')]) if os.path.isdir(P['fulltext']) else 0}편")
    print("경로 누락(인덱스에만 있음):", len(idx - cur))
    print("인덱스 미포함(원본에만 있음):", len(cur - idx))
    print("중복 매핑:", [k for k, v in c.items() if v > 1] or "없음")
    print("캐시 누락:", [r["id"] for r in rows
                    if not os.path.exists(os.path.join(P["fulltext"], r["txt"]))] or "없음")
    print("전문 500자 미만:", [(r["id"], r["file"][:40]) for r in rows if r.get("chars", 0) < 500] or "없음")
    print("비고 있는 항목:", sum(1 for r in rows if r.get("note")))
    if _library_too_small(cfg, len(cur), len(rows)):
        print("\n※ 원본 편수가 인덱스의 절반에 못 미칩니다. 다른 폴더를 집었거나 동기화가 덜 끝난 것일 수 있습니다.\n"
              "   위 라이브러리 경로가 맞는지 확인한 뒤에 `resync`·`reindex` 를 돌리십시오.")
    if idx - cur:
        print("\n→ 파일명이 바뀐 것 같습니다. `resync` 를 실행하십시오.")
    if cur - idx:
        print("\n→ 새 파일이 있습니다. `reindex` 를 실행하십시오.")


# ------------------------------------------------------------------ main

def _oa_args(p):
    """scopus · scopus-merge 에 붙는 OA 수신 옵션. 검색 범위는 바꾸지 않습니다."""
    p.add_argument("--fetch-oa", dest="fetch_oa", action="store_true",
                   help="대조 뒤 미보유 OA 논문을 임시 폴더(설정 oa_staging, 기본 _oa_inbox)에 받고 전문 텍스트를 만듦")
    p.add_argument("--oa-limit", dest="oa_limit", type=int, default=None,
                   help="한 번에 받을 OA 상한 (기본 30)")
    p.add_argument("--oa-recheck", dest="recheck", action="store_true",
                   help="이전에 OA 아님으로 판정한 항목도 다시 조회")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="설정 파일 경로 (기본: 상위 폴더에서 자동 탐색)")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("init"); p.add_argument("library"); p.add_argument("--index-dir")
    p.add_argument("--preset"); p.add_argument("--name"); p.add_argument("--out")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("index"); p.add_argument("--limit", type=int); p.set_defaults(fn=cmd_index)
    p = sub.add_parser("reindex")
    p.add_argument("--force", action="store_true", help="원본 편수가 인덱스의 절반 미만이어도 진행")
    p.set_defaults(fn=cmd_reindex)
    p = sub.add_parser("resync"); p.set_defaults(fn=cmd_resync)
    p = sub.add_parser("repair"); p.set_defaults(fn=cmd_repair)

    p = sub.add_parser("tags-auto"); p.add_argument("--top", type=int, default=20)
    p.add_argument("--min-df", dest="min_df", type=int, default=4)
    p.add_argument("--sample", type=int, default=350); p.add_argument("--out")
    p.set_defaults(fn=cmd_tags_auto)

    p = sub.add_parser("search", help="전문 검색 (깊이 조절 가능)")
    p.add_argument("terms", nargs="*")
    p.add_argument("--or", dest="any_of", action="store_true")
    p.add_argument("--tag", default=""); p.add_argument("--year", default="")
    p.add_argument("--depth", choices=list(DEPTH_PRESETS), default=DEFAULT_DEPTH,
                   help="quick=대표 사례만 / focus=근거 검증(기본) / full=전수 출력")
    p.add_argument("--count-only", dest="count_only", action="store_true",
                   help="편수·출현 횟수만 셈. 본문 스니펫 없음 (가장 쌈)")
    p.add_argument("--max-docs", dest="max_docs", type=int, default=None,
                   help="본문까지 상세 출력할 문헌 수 (0=무제한). 프리셋을 덮어씀")
    p.add_argument("--brief-docs", dest="brief_docs", type=int, default=None,
                   help="상세 출력 뒤 한 줄 요약으로 덧붙일 문헌 수 (-1=나머지 전부)")
    p.add_argument("--stop-after", dest="stop_after", type=int, default=0,
                   help="N편 적중하면 스캔 자체를 중단 (통계가 하한값이 됨)")
    p.add_argument("-n", type=int, default=None, help="문헌당 스니펫 수")
    p.add_argument("-c", "--context", type=int, default=None, help="스니펫 좌우 문자 수")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("scopus"); p.add_argument("query")
    p.add_argument("--count", type=int); p.add_argument("--start", type=int, default=0)
    p.add_argument("--all", action="store_true",
                   help=f"전체 결과를 페이지네이션으로 끝까지 받음 (한 페이지 {scopus_mod.PAGE_SIZE}건 — "
                        f"설정 scopus.page_size, 상한 {scopus_mod.PAGE_CAP:,}건)")
    p.add_argument("--view", help="기본: COMPLETE(초록 포함)를 시도하고 거부되면 STANDARD 로 폴백")
    p.add_argument("--sort"); p.add_argument("--name")
    p.add_argument("-q", "--quiet", action="store_true")
    _oa_args(p)
    p.set_defaults(fn=cmd_scopus)

    p = sub.add_parser("scopus-sift", help="받아 둔 Scopus 결과를 정규식으로 거름 (오프라인)")
    p.add_argument("file")
    p.add_argument("--require", help="제목·초록·키워드에 이 정규식이 걸리는 항목만 남김 (기본 대소문자 구분)")
    p.add_argument("--exclude", help="이 정규식에 걸리는 항목을 버림")
    p.add_argument("-i", "--ignore-case", dest="ignore_case", action="store_true",
                   help="대소문자 무시 — 원소 기호 패턴에는 쓰지 마십시오")
    p.add_argument("--name"); p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(fn=cmd_scopus_sift)

    p = sub.add_parser("scopus-merge"); p.add_argument("file")
    p.add_argument("--name"); p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("--keep-launcher", action="store_true", help=argparse.SUPPRESS)   # 옛 명령줄 호환 — 아무 일도 하지 않습니다
    _oa_args(p)
    p.set_defaults(fn=cmd_scopus_merge)

    p = sub.add_parser("oa-fetch", help="저장된 Scopus 결과의 미보유 OA 논문만 임시 폴더에 받음 (라이브러리에는 쓰지 않음)")
    p.add_argument("file"); p.add_argument("--name")
    p.add_argument("--limit", type=int, default=None, help="한 번에 받을 상한 (기본 30)")
    p.add_argument("--recheck", action="store_true", help="이전에 OA 아님으로 판정한 항목도 다시 조회")
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
