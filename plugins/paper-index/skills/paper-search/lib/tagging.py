# -*- coding: utf-8 -*-
"""Topic tagging — a preset (hand-made rules) by default, otherwise generated from the corpus.

Preset format (presets/*.json):

    {
      "name": "solder-thesis",
      "description": "...",
      "tags": {
        "tag name": ["regex1", "regex2", ...],
        ...
      },
      "renamed": {                      (optional)
        "old tag name": "tag name",
        ...
      }
    }

The regexes ignore case and run on the full text + title; when the total number of matches passes
the threshold, the tag is assigned. The tag order becomes the order of the by-topic section of the index.

`renamed` keeps a renamed tag working in an existing index: the next `index` / `reindex` rewrites the old name
in every row to the new one (legacy.migrate_rows), and `search --tag` accepts either name (tag_aliases).
"""
import collections, json, os, re

from . import legacy

UNTAGGED = "untagged"


def compile_preset(preset):
    return {k: [re.compile(p, re.I) for p in v] for k, v in preset["tags"].items()}


def tag_aliases(preset):
    """Old tag name -> current name: the preset's `renamed` plus the tool's own old spellings (legacy.LEGACY_TAGS).

    Returns (aliases, warnings). A chain (a -> b -> c) resolves to its last name. A pair is dropped with a warning
    when its new name is not a string, when its old name is still a tag of the preset, or when it loops; a new name
    that is not a tag of the preset is kept, with a warning.
    """
    preset = preset or {}
    raw = preset.get("renamed") or {}
    out, warns = dict(legacy.LEGACY_TAGS), []
    if not isinstance(raw, dict):
        return out, [f"Preset `renamed` is not an object ({type(raw).__name__}) — ignored."]
    tags = set(preset.get("tags") or {})
    pairs = {}
    for old, new in raw.items():
        if not isinstance(new, str) or not new:
            warns.append(f"Preset `renamed`: {old!r} -> {new!r} is not a tag name — ignored.")
        elif old in tags:
            warns.append(f"Preset `renamed`: {old!r} is still a tag of the preset — ignored.")
        else:
            pairs[old] = new
    for old, new in pairs.items():
        seen = {old}
        while new in pairs and new not in seen:
            seen.add(new)
            new = pairs[new]
        if new in seen:
            warns.append(f"Preset `renamed`: {old!r} leads back to itself — ignored.")
            continue
        if tags and new not in tags:
            warns.append(f"Preset `renamed`: {old!r} -> {new!r}, which is not a tag of the preset.")
        out[old] = new
    return out, warns


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


# ---------------------------------------------------------------- automatic generation

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
    """Pick frequent technical terms from the corpus as tag candidates.

    Document frequency (df) is used: a term that appears across many documents is a better axis
    for classification than a word that appears many times in one document.
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
    # two-word phrases first, then longer words
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
        "description": "Draft tags generated from document frequency in the corpus. Refine them by hand before use.",
        "auto_generated": True,
        "tags": tags,
    }


def save_preset(preset, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    json.dump(preset, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
