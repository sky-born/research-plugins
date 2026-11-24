"""Character normalization (paper-index 0.9.3): PDF ligatures and compatibility characters are unfolded
before full text, queries and index titles are compared — the cache files themselves stay as extracted.

The `lib` package runs in a subprocess (fresh modules, like the other paper-index tests); the citation-check
template is standalone and is loaded in-process.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "paper-index" / "skills" / "paper-search"

DRIVER = r'''
import json, os, sys
skill, work = sys.argv[1], sys.argv[2]
sys.path.insert(0, skill)
from lib import textnorm, searching, extract, scopus, render
N = textnorm.norm_text
out = {}
samples = {
    "lig": "reﬂow ﬁeld eﬀect oﬃce baﬄe",
    "micro": "5 µm", "celsius": "85 ℃", "sup": "x²", "sub": "Ni₃Sn₄",
    "diaeresis": "Go¨rlich", "fraction": "x ¼ 5",
    "nbhyphen": "needle‑like", "zwsp": "of ​voids", "ordinal": "85 ºC",
    "softhyphen": "inter­metallic", "nbsp": "a b", "endash": "Sn–Bi–In",
    "ascii": "plain ASCII text",
}
out["norm"] = {k: N(v) for k, v in samples.items()}
mixed = "".join(samples.values())
out["idempotent"] = N(N(mixed)) == N(mixed)
out["empty"] = [N(""), N(None)]

ft = os.path.join(work, "_fulltext")
os.makedirs(ft)
texts = {"a.txt": "In the early stage of reﬂow, a 5 µm layer formed.",
         "b.txt": "During reflow the 3 μm layer grew.",
         "c.txt": "Flux-free bonding of Sn–Bi–In."}
for name, t in texts.items():
    open(os.path.join(ft, name), "w", encoding="utf-8").write(t)
rows = [{"id": "P%03d" % i, "txt": n, "tags": [], "year": "2020", "title": n, "rel": n}
        for i, n in enumerate(sorted(texts), 1)]
json.dump(rows, open(os.path.join(work, "papers_index.json"), "w", encoding="utf-8"))
paths = {"json": os.path.join(work, "papers_index.json"), "fulltext": ft}

def count(term):
    return searching.search(paths, [term], count_only=True)[2]["matched"]

out["search"] = {t: count(t) for t in ["reflow", "reﬂow", "early stage of reflow",
                                         "µm", "μm", "Sn-Bi-In", "Sn–Bi–In"]}
_, hits, _ = searching.search(paths, ["early stage of reflow"])
out["snippet"] = hits[0][3][0] if hits else ""

raw = open(os.path.join(ft, "a.txt"), "rb").read()
out["read_cache"] = extract.read_cache(ft, "a.pdf")
out["cache_unchanged"] = open(os.path.join(ft, "a.txt"), "rb").read() == raw

idx = [{"id": "P1", "title": "Eﬀect of thermal aging on the solidiﬁcation of Sn-Ni alloys", "rel": "x.pdf"}]
ent = [{"title": "Effect of thermal aging on the solidification of Sn-Ni alloys", "doi": ""}]
m = scopus.match_against_index(ent, idx)[0]
out["scopus"] = [m["owned"], m["match_by"]]
out["render"] = render._norm("Eﬀect of reﬂow") == render._norm("Effect of reflow")
print(json.dumps(out, ensure_ascii=False))
'''


def run_driver():
    with tempfile.TemporaryDirectory() as work:
        r = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", DRIVER, str(SKILL), work],
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)


class TextNormTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = run_driver()

    def test_ligatures_and_compat_chars_unfold(self):
        n = self.out["norm"]
        self.assertEqual(n["lig"], "reflow field effect office baffle")
        self.assertEqual(n["micro"], "5 μm")
        self.assertEqual(n["celsius"], "85 °C")
        self.assertEqual(n["sup"], "x2")
        self.assertEqual(n["sub"], "Ni3Sn4")
        self.assertEqual(n["nbhyphen"], "needle-like")
        self.assertEqual(n["zwsp"], "of voids")
        self.assertEqual(n["ordinal"], "85 °C")
        self.assertEqual(n["softhyphen"], "intermetallic")
        self.assertEqual(n["nbsp"], "a b")
        self.assertEqual(n["endash"], "Sn-Bi-In")
        self.assertEqual(n["ascii"], "plain ASCII text")

    def test_spacing_diacritics_and_fractions_stay(self):
        # NFKC would turn these into "space + combining mark" or insert digits (1⁄4)
        self.assertEqual(self.out["norm"]["diaeresis"], "Go¨rlich")
        self.assertEqual(self.out["norm"]["fraction"], "x ¼ 5")

    def test_idempotent_and_empty(self):
        self.assertTrue(self.out["idempotent"])
        self.assertEqual(self.out["empty"], ["", ""])

    def test_search_matches_ligature_text_and_queries(self):
        s = self.out["search"]
        self.assertEqual(s["reflow"], 2)
        self.assertEqual(s["reﬂow"], 2)
        self.assertEqual(s["early stage of reflow"], 1)
        self.assertEqual(s["µm"], 2)
        self.assertEqual(s["μm"], 2)
        self.assertEqual(s["Sn-Bi-In"], 1)
        self.assertEqual(s["Sn–Bi–In"], 1)
        self.assertIn("early stage of reflow", self.out["snippet"])

    def test_read_cache_normalizes_without_touching_file(self):
        self.assertIn("reflow", self.out["read_cache"])
        self.assertNotIn("ﬂ", self.out["read_cache"])
        self.assertTrue(self.out["cache_unchanged"])

    def test_title_comparisons(self):
        owned, how = self.out["scopus"]
        self.assertTrue(owned)
        self.assertEqual(how, "제목 유사 1.00")
        self.assertTrue(self.out["render"])

    def test_citation_check_template(self):
        spec = importlib.util.spec_from_file_location(
            "paper_index_citecheck", SKILL / "templates" / "citation-check" / "citecheck.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.norm("Eﬀect of reﬂow"), mod.norm("Effect of reflow"))


if __name__ == "__main__":
    unittest.main()
