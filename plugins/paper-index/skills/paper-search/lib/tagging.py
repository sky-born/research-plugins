# -*- coding: utf-8 -*-
"""주제 태깅 — 프리셋(수작업 규칙) 기본, 없으면 코퍼스에서 자동 생성.

프리셋 형식 (presets/*.json):

    {
      "name": "solder-thesis",
      "description": "...",
      "tags": {
        "태그 이름": ["정규식1", "정규식2", ...],
        ...
      }
    }

정규식은 대소문자를 무시하고 전문 + 제목에 적용되며, 적중 횟수 합이 임계값을 넘으면
그 태그를 붙입니다. 태그 순서가 인덱스의 주제별 목차 순서가 됩니다.
"""
import collections, json, os, re

UNTAGGED = "기타(미분류)"


def compile_preset(preset):
    return {k: [re.compile(p, re.I) for p in v] for k, v in preset["tags"].items()}


def tag_one(text, compiled, min_score=4, fallback=2, max_tags=5):
    sc = {}
    for tag, pats in compiled.items():
        s = sum(len(p.findall(text)) for p in pats)
        if s:
            sc[tag] = s
    keep = [t for t, s in sc.items() if s >= min_score]
    if not keep:
        keep = [t for t, s in sc.items() if s >= fallback]
    if not keep:
        keep = [t for t, s in sc.items() if s >= 1]
    keep = sorted(keep, key=lambda t: -sc[t])[:max_tags]
    return keep or [UNTAGGED]


# ---------------------------------------------------------------- 자동 생성

STOP = set("""the and of in for a to is was were are be been being on by with as at from that this these those
it its their our we they he she you i not no all any some can could may might will would shall should must
have has had do does did done using used use uses based obtained observed shown show shows found results result
study studies paper article present presented presents also more most than then thus therefore however but or
if when where which who what how there here both each other another such same different high low higher lower
increase increased increasing decrease decreased between during after before under over about into within
figure fig table eq equation ref refs et al vol no pp doi https http www com org copyright rights reserved
one two three four five six seven eight nine ten first second third new due via per e.g i.e""".split())


BOILERPLATE = re.compile(
    r"\b(journal|proceedings|conference|symposium|transactions|letters|elsevier|springer|wiley|"
    r"ieee|mdpi|acs|rsc|doi|issn|isbn|copyright|reserved|university|department|institute|"
    r"corresponding|author|authors|email|mail|received|accepted|revised|published|"
    r"mater|sci|eng|technol|vol|pp|fig|figs|table|tables|chapter|appendix|"
    r"carried out|et al|open access|creative commons|supporting information|"
    r"room temperature|scanning electron|transmission electron|electron microscope|"
    r"electron microscopy|x ray|shown in|as shown|can be|it is|has been|have been|"
    r"in this|of the|for the|to the|on the|with the|from the)\b", re.I)


def auto_tags(texts, top=20, min_df=4, phrase=True, max_df_ratio=0.35):
    """코퍼스에서 빈도 높은 전문용어를 뽑아 태그 후보를 만듭니다.

    문서빈도(df)를 씁니다. 한 문서에 많이 나오는 단어보다 여러 문서에 걸쳐
    나오는 용어가 분류축으로 쓸 만하기 때문입니다.
    """
    df = collections.Counter()
    for t in texts:
        low = t.lower()
        toks = re.findall(r"[a-z][a-z0-9\-]{2,24}", low)
        uniq = {w for w in toks if w not in STOP and not w.isdigit()}
        if phrase:
            for i in range(len(toks) - 1):
                a, b = toks[i], toks[i + 1]
                if a in STOP or b in STOP:
                    continue
                uniq.add(a + " " + b)
        df.update(uniq)
    n = max(1, len(texts))
    cand = [(w, c) for w, c in df.items()
            if min_df <= c <= n * max_df_ratio and not BOILERPLATE.search(w)]
    # 두 단어 구를 우선하고, 그 다음 긴 단어
    cand.sort(key=lambda x: (-(x[1] * (1.6 if " " in x[0] else 1.0)), -len(x[0])))
    picked, seen = [], set()
    for w, c in cand:
        parts = set(w.split())
        if parts & seen and " " not in w:
            continue
        picked.append((w, c))
        seen |= parts
        if len(picked) >= top:
            break
    return picked


def auto_preset(texts, name="auto", top=20, min_df=4):
    picked = auto_tags(texts, top=top, min_df=min_df)
    tags = {}
    for w, c in picked:
        label = w if " " in w else w
        tags[label] = [re.escape(w).replace(r"\ ", r"[\s\-]?")]
    return {
        "name": name,
        "description": "코퍼스 문서빈도에서 자동 생성한 태그 초안. 손으로 다듬어 쓰십시오.",
        "auto_generated": True,
        "tags": tags,
    }


def save_preset(preset, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    json.dump(preset, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
