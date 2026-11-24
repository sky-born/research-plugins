"""OA staging without network: one DOI is staged once, whatever the result name or the computer.

Each case runs papertool.py in a subprocess (fresh `lib` modules) whose network (`oafetch._get`),
text extractor (`oafetch.to_text`) and sleeps are fakes that record every call.
"""
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "paper-index" / "skills" / "paper-search"
_spec = importlib.util.spec_from_file_location("paper_index_oafetch", SKILL / "lib" / "oafetch.py")
oafetch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oafetch)


def lib_module(name):
    """A module of the skill's `lib` package, loaded under a name of its own so it meets no other `lib`."""
    if "paper_index_lib" not in sys.modules:
        spec = importlib.util.spec_from_file_location("paper_index_lib", SKILL / "lib" / "__init__.py",
                                                      submodule_search_locations=[str(SKILL / "lib")])
        sys.modules["paper_index_lib"] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sys.modules["paper_index_lib"])
    return importlib.import_module("paper_index_lib." + name)

# argv: <skill dir> <spec json> <papertool args...>
# spec: oa = DOIs OpenAlex knows as OA with a direct PDF · pdftotext = whether extraction works
DRIVER = r'''
import json, os, runpy, sys, time, urllib.parse
skill, spec = sys.argv[1], json.loads(sys.argv[2])
sys.path.insert(0, skill)
from lib import oafetch
calls = []
PDF_HOST = "https://fixture.test/pdf/"

def pdf_bytes(doi):                       # same formula as the test module's pdf_bytes
    return (b"%PDF-1.4\n% fixture " + doi.lower().encode() + b"\n").ljust(25000, b"0")

def fake_get(url, accept, timeout):
    if url.startswith(oafetch.OPENALEX):
        doi = urllib.parse.unquote(url[len(oafetch.OPENALEX):]).lower()
        calls.append(["openalex", doi])
        if doi not in spec["oa"]:
            return 404, url, "application/json", b""
        body = {"open_access": {"is_oa": True, "oa_status": "gold"},
                "best_oa_location": {"pdf_url": PDF_HOST + urllib.parse.quote(doi, safe=""),
                                     "landing_page_url": "https://fixture.test/landing"},
                "publication_year": 2020}
        return 200, url, "application/json", json.dumps(body).encode()
    if url.startswith(PDF_HOST):
        doi = urllib.parse.unquote(url[len(PDF_HOST):])
        calls.append(["download", doi])
        return 200, url, "application/pdf", pdf_bytes(doi)
    raise AssertionError("unexpected request " + url)

def fake_to_text(exe, pdf, txt, timeout=60):
    calls.append(["to_text", os.path.basename(pdf)])
    if not spec["pdftotext"]:
        return False
    with open(txt, "w", encoding="utf-8") as f:
        f.write("fixture text of " + os.path.basename(pdf) + "\n")
    return True

oafetch._get = fake_get
oafetch.to_text = fake_to_text
time.sleep = lambda s: None
sys.argv = [os.path.join(skill, "papertool.py")] + sys.argv[3:]
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
finally:
    print("CALLS " + json.dumps(calls))
'''

A = "10.2320/matertrans.M2014202"
B = "10.1007/s00216-007-1594-3"
C = "10.1016/j.fixture.2020.1"          # not open access


def pdf_bytes(doi):
    return (b"%PDF-1.4\n% fixture " + doi.lower().encode() + b"\n").ljust(25000, b"0")


def entry(doi, author, title, oa="1"):
    return {"title": title, "author": author, "doi": doi, "eid": "2-s2.0-" + doi[-6:].replace("/", "x"),
            "openaccess": oa, "year": "2014"}


ENTRIES = [entry(A, "Hashiba H.", "Kinetics of solid-state reactive diffusion in the (Pd-Cu)/Sn system"),
           entry(B, "Lisowski W.", "Microstructural and chemical transformation of thin Ti/Pd layers"),
           entry(C, "Nobody N.", "A subscription paper", oa="0")]


class OaFetchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="oa-fetch-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / "한글 space"
        self.library = self.base / "library"
        self.index = self.base / "index"
        self.library.mkdir(parents=True)
        self.index.mkdir()
        (self.library / "kept.pdf").write_bytes(b"source library file; never written")
        self.config = self.base / "paperindex.config.json"
        self.config.write_text(json.dumps({"library": str(self.library), "index_dir": str(self.index)}),
                               encoding="utf-8")
        self.stg = self.index / "_oa_inbox"
        self.txt = self.stg / "_text"
        self.results = self.index / "_scopus"
        self.library_before = self.listing(self.library)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def listing(folder):
        return sorted((str(p.relative_to(folder)), hashlib.sha256(p.read_bytes()).hexdigest())
                      for p in Path(folder).rglob("*") if p.is_file())

    def write_input(self, fmt, entries, name="in.json"):
        if fmt == "papertool":
            body = {"meta": {"query": "TITLE(fixture)", "total": len(entries)}, "entries": entries}
        elif fmt == "list":
            body = entries
        else:   # raw Scopus response, as launchers of 0.9 and earlier saved it
            body = {"search-results": {"opensearch:totalResults": str(len(entries)), "entry": [
                {"dc:title": e["title"], "dc:creator": e["author"], "prism:doi": e["doi"], "eid": e["eid"],
                 "openaccess": e["openaccess"], "prism:coverDate": e["year"] + "-01-01"} for e in entries]}}
        path = self.base / name
        path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        return path

    def stage(self, name, doi, text=True):
        """What an earlier run (any version, any computer) leaves in the staging folder."""
        self.txt.mkdir(parents=True, exist_ok=True)
        (self.stg / name).write_bytes(pdf_bytes(doi))
        if text:
            (self.txt / oafetch.text_name(doi)).write_text("earlier text of " + name, encoding="utf-8")

    def run_tool(self, *args, oa=(A, B), pdftotext=True):
        spec = {"oa": [d.lower() for d in oa], "pdftotext": pdftotext}
        result = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", "-c", DRIVER, str(SKILL), json.dumps(spec),
             "--config", str(self.config), *map(str, args)],
            cwd=self.base, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(self.library_before, self.listing(self.library))      # source library untouched
        line = [ln for ln in result.stdout.splitlines() if ln.startswith("CALLS ")][-1]
        return result.stdout, json.loads(line[len("CALLS "):])

    def saved(self, name):
        data = json.loads((self.results / f"{name}.json").read_text(encoding="utf-8"))
        return {e["doi"].lower(): e for e in data["entries"]}

    def pdfs(self):
        return sorted(p.name for p in self.stg.glob("*.pdf")) if self.stg.exists() else []

    def manifest(self):
        return json.loads((self.stg / oafetch.MANIFEST).read_text(encoding="utf-8"))

    @staticmethod
    def did(calls, kind):
        return sorted(c[1] for c in calls if c[0] == kind)

    # ------------------------------------------------------------ cases
    def test_rerun_under_another_name_reuses_the_staged_pdf(self):
        for fmt in ("papertool", "list", "scopus-raw"):
            with self.subTest(fmt=fmt):
                shutil.rmtree(self.index)
                self.index.mkdir()
                src = self.write_input(fmt, ENTRIES)
                out, calls = self.run_tool("scopus-merge", src, "--fetch-oa", "--name", "sweep", "-q")
                self.assertEqual(sorted([A.lower(), B.lower()]), self.did(calls, "download"))
                first, texts = self.saved("sweep"), self.listing(self.txt)
                self.assertEqual(2, len(self.pdfs()))
                book = self.manifest()["files"]
                self.assertEqual({A.lower(), B.lower()}, set(book))
                self.assertEqual(first[A.lower()]["oa_file"], book[A.lower()]["file"])
                self.assertTrue(book[A.lower()]["md5"] and book[A.lower()]["fetched"])

                for run in (("scopus-merge", src, "--fetch-oa", "--name", "sweep_lab", "-q"),
                            ("oa-fetch", src, "--name", "second_query")):
                    out, calls = self.run_tool(*run)
                    self.assertEqual([], self.did(calls, "download"), out)
                    self.assertNotIn(A.lower(), self.did(calls, "openalex"))
                    self.assertIn("Already staged: 2 papers", out)
                    again = self.saved(run[run.index("--name") + 1])
                    for d in (A.lower(), B.lower()):
                        self.assertEqual(first[d]["oa_file"], again[d]["oa_file"])
                        self.assertEqual(first[d]["oa_text"], again[d]["oa_text"])
                        self.assertEqual("gold", again[d]["oa_status"])
                    self.assertEqual(2, len(self.pdfs()))                       # no <name>_1.pdf
                    self.assertEqual(texts, self.listing(self.txt))             # texts not rewritten

    def test_staging_from_an_old_version_is_found_through_result_json(self):
        # Version 0.9.1 writes no manifest. A has a text; B was fetched where pdftotext was missing (oa_text "").
        self.stage("Old-name for A.pdf", A)
        self.stage("Old-name for B.pdf", B, text=False)
        self.results.mkdir()
        old = [dict(ENTRIES[0], oa_file="Old-name for A.pdf", oa_text="_text/" + oafetch.text_name(A),
                    oa_url="https://fixture.test/a.pdf", oa_status="bronze", oa_checked="2026-10-08"),
               dict(ENTRIES[1], oa_file="Old-name for B.pdf", oa_text="")]
        (self.results / "pd_rich_sweep.json").write_text(
            json.dumps({"meta": {"query": "q"}, "entries": old}, ensure_ascii=False), encoding="utf-8")
        src = self.write_input("papertool", ENTRIES)
        out, calls = self.run_tool("oa-fetch", src, "--name", "pd_rich_sweep_lab")
        self.assertEqual([], self.did(calls, "download"), out)
        self.assertEqual([C.lower()], self.did(calls, "openalex"))
        self.assertEqual(["Old-name for B.pdf"], self.did(calls, "to_text"))   # text made, nothing fetched
        got = self.saved("pd_rich_sweep_lab")
        self.assertEqual("Old-name for A.pdf", got[A.lower()]["oa_file"])
        self.assertEqual("bronze", got[A.lower()]["oa_status"])
        self.assertEqual("Old-name for B.pdf", got[B.lower()]["oa_file"])
        self.assertEqual("_text/" + oafetch.text_name(B), got[B.lower()]["oa_text"])
        self.assertEqual(["Old-name for A.pdf", "Old-name for B.pdf"], self.pdfs())
        book = self.manifest()["files"]                                       # adopted into the manifest
        self.assertEqual("Old-name for B.pdf", book[B.lower()]["file"])
        self.assertNotIn("md5", book[A.lower()])
        self.assertIn("got a newly made full text", out)

    def test_a_file_two_old_results_claim_for_different_dois_is_not_used(self):
        self.stage("Shared.pdf", A, text=False)
        self.results.mkdir()
        old = [dict(ENTRIES[0], oa_file="Shared.pdf"), dict(ENTRIES[1], oa_file="Shared.pdf")]
        (self.results / "old.json").write_text(json.dumps(old), encoding="utf-8")
        src = self.write_input("list", ENTRIES[:2])
        out, calls = self.run_tool("oa-fetch", src, "--name", "new", pdftotext=False)
        self.assertEqual(sorted([A.lower(), B.lower()]), self.did(calls, "download"))
        got = self.saved("new")
        self.assertEqual("Shared.pdf", got[A.lower()]["oa_file"])            # identical bytes: reused
        self.assertNotEqual("Shared.pdf", got[B.lower()]["oa_file"])

    def test_text_alone_counts_as_staged(self):
        self.txt.mkdir(parents=True)
        (self.txt / oafetch.text_name(A)).write_text("text of a PDF moved to the library", encoding="utf-8")
        src = self.write_input("papertool", [dict(ENTRIES[0], abstract="An abstract.")])  # md per-entry part
        out, calls = self.run_tool("oa-fetch", src, "--name", "t")
        self.assertEqual([], calls)
        got = self.saved("t")[A.lower()]
        self.assertNotIn("oa_file", got)
        self.assertEqual("_text/" + oafetch.text_name(A), got["oa_text"])
        self.assertEqual(oafetch.TEXT_ONLY_NOTE, got["oa_note"])
        self.assertEqual([], self.pdfs())
        self.assertIn("OA full text:", (self.results / "t.md").read_text(encoding="utf-8"))

    def test_identical_download_does_not_make_a_copy(self):
        name = oafetch.filename_for(ENTRIES[0])
        self.stage(name, A, text=False)          # unrecorded, no text: only the bytes can tell
        src = self.write_input("papertool", ENTRIES[:1])
        out, calls = self.run_tool("oa-fetch", src, "--name", "t", pdftotext=False)
        self.assertEqual([A.lower()], self.did(calls, "download"))
        self.assertEqual([name], self.pdfs())
        self.assertEqual(name, self.saved("t")[A.lower()]["oa_file"])
        self.assertEqual(name, self.manifest()["files"][A.lower()]["file"])
        self.assertIn("so no copy was made", out)

    def test_same_name_with_other_content_is_kept_apart(self):
        name = oafetch.filename_for(ENTRIES[0])
        self.stage(name, "10.9999/another-paper", text=False)
        src = self.write_input("papertool", ENTRIES[:1])
        out, calls = self.run_tool("oa-fetch", src, "--name", "t")
        self.assertEqual([A.lower()], self.did(calls, "download"))
        self.assertEqual(sorted([name, name[:-4] + "_1.pdf"]), self.pdfs())
        self.assertEqual(name[:-4] + "_1.pdf", self.saved("t")[A.lower()]["oa_file"])

    def test_same_doi_twice_in_one_input_is_fetched_once(self):
        src = self.write_input("list", [ENTRIES[0], dict(ENTRIES[0], eid="2-s2.0-dup")])
        out, calls = self.run_tool("oa-fetch", src, "--name", "t")
        self.assertEqual([A.lower()], self.did(calls, "download"))
        self.assertEqual(1, len(self.pdfs()))

    def test_owned_text_still_moves_to_obsolete(self):
        rows = [{"id": "P001", "title": ENTRIES[1]["title"], "doi": B, "rel": "kept.pdf"}]
        (self.index / "papers_index.json").write_text(json.dumps(rows), encoding="utf-8")
        self.stage("Lisowski-staged.pdf", B)
        src = self.write_input("papertool", ENTRIES[:2])
        out, calls = self.run_tool("oa-fetch", src, "--name", "t")
        self.assertEqual([A.lower()], self.did(calls, "download"))
        self.assertTrue((self.txt / "_obsolete" / oafetch.text_name(B)).is_file())
        self.assertFalse((self.txt / oafetch.text_name(B)).exists())
        self.assertIn("papers now in the library to _text/_obsolete/", out)

    def test_unreadable_or_unknown_manifest_is_left_alone(self):
        for body in ("{ broken", json.dumps({"format": oafetch.MANIFEST_FORMAT, "version": 2, "files": {}})):
            with self.subTest(body=body[:12]):
                shutil.rmtree(self.index)
                self.index.mkdir()
                self.stage("Hashiba-staged.pdf", A)
                (self.stg / oafetch.MANIFEST).write_text(body, encoding="utf-8")
                src = self.write_input("papertool", ENTRIES)
                out, calls = self.run_tool("oa-fetch", src, "--name", "t")
                self.assertIn("Not using the fetch manifest", out)
                self.assertEqual([B.lower()], self.did(calls, "download"))     # A still found by its text
                self.assertEqual(body, (self.stg / oafetch.MANIFEST).read_text(encoding="utf-8"))

    def test_manifest_line_whose_file_was_replaced_is_ignored(self):
        self.stage("Same.pdf", B, text=False)
        self.stg.joinpath(oafetch.MANIFEST).write_text(json.dumps({
            "format": oafetch.MANIFEST_FORMAT, "version": oafetch.MANIFEST_VERSION, "files": {
                A.lower(): {"file": "Same.pdf", "text": "", "bytes": 12345},          # stale: size differs
                B.lower(): {"file": "Same.pdf", "text": "", "bytes": len(pdf_bytes(B))}}}), encoding="utf-8")
        src = self.write_input("papertool", ENTRIES[:2])
        out, calls = self.run_tool("oa-fetch", src, "--name", "t", pdftotext=False)
        self.assertEqual([A.lower()], self.did(calls, "download"))
        got = self.saved("t")
        self.assertEqual("Same.pdf", got[B.lower()]["oa_file"])
        self.assertNotEqual("Same.pdf", got[A.lower()]["oa_file"])


class StagingManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="oa-manifest-")
        self.addCleanup(self.temp.cleanup)
        self.stg = Path(self.temp.name) / "_oa_inbox"
        (self.stg / "_text").mkdir(parents=True)
        self.path = self.stg / oafetch.MANIFEST

    def write(self, files):
        self.path.write_text(json.dumps({"format": oafetch.MANIFEST_FORMAT,
                                         "version": oafetch.MANIFEST_VERSION, "files": files}), encoding="utf-8")

    def test_save_keeps_lines_written_elsewhere_meanwhile(self):
        self.write({"10.1/x": {"file": "x.pdf"}, "10.1/odd": "not a record"})
        logs = []
        st = oafetch.Staging(str(self.stg), str(self.stg / "_text"), log=logs.append)
        self.assertTrue(any("Skipping 1 manifest lines without a file" in m for m in logs))
        st.record("10.1/y", {"file": "y.pdf", "text": ""})
        self.write({"10.1/x": {"file": "x.pdf"}, "10.1/z": {"file": "z.pdf"}, "10.1/odd": "not a record"})
        st.save()
        files = json.loads(self.path.read_text(encoding="utf-8"))["files"]
        self.assertEqual({"10.1/x", "10.1/y", "10.1/z", "10.1/odd"}, set(files))
        self.assertEqual("not a record", files["10.1/odd"])                   # unknown lines are kept
        self.assertEqual([], [p.name for p in self.stg.glob("*.part")])

    def test_nothing_recorded_means_nothing_written(self):
        st = oafetch.Staging(str(self.stg), str(self.stg / "_text"), log=lambda m: None)
        st.save()
        self.assertFalse(self.path.exists())



class StagingFolderTests(unittest.TestCase):
    """The default staging folder is `_oa_inbox` — with no setting and only the old default `_수신` present, that folder is used as is."""
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="oa-staging-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        (self.base / "library").mkdir()
        (self.base / "index").mkdir()
        self.config = lib_module("config")

    def staging(self, extra=None):
        path = self.base / "paperindex.config.json"
        path.write_text(json.dumps(dict({"library": "library", "index_dir": "index"}, **(extra or {}))), encoding="utf-8")
        return Path(self.config.paths(self.config.load(str(path)))["oa_staging"]).name

    def test_default_old_folder_and_explicit_setting(self):
        self.assertEqual("_oa_inbox", self.staging())
        (self.base / "index" / "_수신").mkdir()
        self.assertEqual("_수신", self.staging())
        (self.base / "index" / "_oa_inbox").mkdir()
        self.assertEqual("_oa_inbox", self.staging())
        self.assertEqual("mine", self.staging({"oa_staging": "mine"}))


if __name__ == "__main__":
    unittest.main()
