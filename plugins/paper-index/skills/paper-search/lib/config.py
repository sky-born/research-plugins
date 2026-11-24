# -*- coding: utf-8 -*-
"""설정 로드 — 라이브러리 경로·인덱스 경로·프리셋을 한 곳에서 관리."""
import json, os, sys

DEFAULT = {
    "name": "",                 # 라이브러리 이름 (보고용)
    "library": "",              # PDF 원본 폴더 (읽기 전용으로 취급)
    "index_dir": "",            # 인덱스·캐시를 쓸 폴더
    "preset": "",               # presets/*.json 파일명 (없으면 자동 태깅)
    "id_prefix": "P",
    "pdftotext": "pdftotext",
    "min_tag_score": 4,         # 태그 부여 임계값 (1차)
    "min_tag_score_fallback": 2,
    "max_tags": 5,
    "oa_staging": "_수신",       # OA 논문을 임시로 받아 두는 폴더 (index_dir 기준 상대경로). 라이브러리가 아닙니다
}

CONFIG_NAMES = ("paperindex.config.json", "config.json")


def find_config(start=None):
    """작업 폴더 → 상위로 올라가며 설정 파일을 찾습니다."""
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
        sys.exit("설정 파일을 찾을 수 없습니다. `papertool.py init <라이브러리경로>` 로 만드십시오.")
    cfg = dict(DEFAULT)
    cfg.update(json.load(open(p, encoding="utf-8")))
    base = os.path.dirname(os.path.abspath(p))

    def resolve(v, want_dir=True):
        """문자열이면 그대로, 리스트면 실제로 존재하는 첫 경로를 씁니다.

        같은 라이브러리가 환경에 따라 다른 경로로 보일 때(예: 호스트의 Windows 경로와
        에이전트 셸의 마운트 경로) 후보를 여러 개 적어 두면 됩니다.
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
        # 어느 후보도 없으면 — 에이전트 셸의 마운트 경로는 세션마다 바뀌므로
        # 같은 이름의 폴더를 마운트 지점에서 찾아 봅니다.
        import glob
        for c in out:
            bname = os.path.basename(c.rstrip("/\\").replace("\\", "/"))
            if not bname:
                continue
            for pat in (f"/sessions/*/mnt/{bname}", f"/mnt/{bname}", f"/workspace/{bname}"):
                hit = sorted(glob.glob(pat))
                if hit:
                    return hit[0]
        return out[0] if out else ""

    _raw_lib = cfg["library"]
    cfg["library"] = resolve(_raw_lib)
    # 어느 후보를 골랐는지, 실재하는지 명령 쪽에서 판단할 수 있게 남깁니다 (v0.7.2)
    cfg["_library_candidates"] = [
        (c if os.path.isabs(c) else os.path.normpath(os.path.join(base, c)))
        for c in (_raw_lib if isinstance(_raw_lib, list) else [_raw_lib]) if c]
    cfg["_library_found"] = os.path.isdir(cfg["library"])
    cfg["index_dir"] = resolve(cfg["index_dir"]) or base
    cfg["_path"] = p
    cfg["_base"] = base
    if not cfg["library"]:
        sys.exit(f"{p}: `library` 가 비어 있습니다.")
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
    return {
        "index_dir": d,
        "fulltext": os.path.join(d, "_fulltext"),
        "obsolete": os.path.join(d, "_fulltext", "_obsolete"),
        "json": os.path.join(d, "papers_index.json"),
        "md": os.path.join(d, "papers_index.md"),
        "csv": os.path.join(d, "papers_index.csv"),
        "vocab": os.path.join(d, "_fulltext", "_vocab.json"),
        "scopus": os.path.join(d, "_scopus"),        # Scopus 결과 json · md (oafetch 가 옛 수신 기록도 여기서 읽음)
        "oa_staging": stg,                          # OA 임시 보관 (라이브러리 아님, 인덱스 대상 아님)
        "oa_text": os.path.join(stg, "_text"),      # 받은 OA 의 전문 텍스트
    }


def load_preset(cfg, tool_root):
    """프리셋 파일을 읽습니다. 없으면 None (자동 태깅으로 넘어감)."""
    name = cfg.get("preset") or ""
    if not name:
        return None
    for cand in (name,
                 os.path.join(cfg["_base"], name),
                 os.path.join(tool_root, "presets", name),
                 os.path.join(tool_root, "presets", name + ".json")):
        if os.path.exists(cand):
            return json.load(open(cand, encoding="utf-8"))
    # 인덱스 폴더에 자동 생성된 프리셋
    auto = os.path.join(cfg["index_dir"], "tags.auto.json")
    if os.path.exists(auto):
        return json.load(open(auto, encoding="utf-8"))
    return None
