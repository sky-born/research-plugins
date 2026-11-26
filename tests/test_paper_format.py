"""English on-disk values, and the old Korean spellings paper-index keeps reading (lib/legacy.py).

Unit checks load the skill's `lib` package under a name of its own. CLI checks run papertool.py in a subprocess
on fixtures — no network, and no PDF extractor except the stand-in described in the repair test.
Korean strings below are fixtures of the old on-disk format, or hand-written values that must stay untouched.
"""
import ast
import datetime
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unicodedata
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "paper-index" / "skills" / "paper-search"
HANGUL = re.compile("[가-힣]")


def lib_module(name):
    """A module of the skill's `lib` package, loaded under a name of its own so it meets no other `lib`."""
    if "paper_index_lib" not in sys.modules:
        spec = importlib.util.spec_from_file_location("paper_index_lib", SKILL / "lib" / "__init__.py",
                                                      submodule_search_locations=[str(SKILL / "lib")])
        sys.modules["paper_index_lib"] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sys.modules["paper_index_lib"])
    return importlib.import_module("paper_index_lib." + name)


def module_constants(path):
    """Module-level literal assignments of a script, read without running it."""
    out = {}
    for node in ast.parse(Path(path).read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError):
                pass
    return out


legacy, tagging, meta, config, oafetch = (lib_module(n) for n in ("legacy", "tagging", "meta", "config", "oafetch"))
PT = module_constants(SKILL / "papertool.py")
NOTE_BROKEN, NOTE_FAIL = PT["NOTE_BROKEN"], PT["NOTE_FAIL"]
PRESET = json.loads((SKILL / "presets" / "solder-thesis.json").read_text(encoding="utf-8"))

# The old on-disk format, spelled out here rather than taken from lib/legacy.py so each side checks the other.
OLD_UNTAGGED = "기타(미분류)"
OLD_TERNARY = "Sn-Bi-In 삼원계"
OLD_REFLOW = "리플로우·공정"
OLD_BROKEN = ("※ PDF 폰트 인코딩 결함. 전문 캐시는 복원본입니다. "
              "일부 구간의 글자가 어긋나므로 인용 전 원본 PDF 확인 필수")
OLD_FAIL = "※ PDF 텍스트 레이어 손상 — 전문 검색 불가. 원본 재다운로드 또는 OCR 필요"
OLD_SPRINGER = "Springer (기타)"
OLD_NATURE = "Nature 계열"
# Values a person wrote or edited by hand — they stay as they are.
HAND_NOTE = "DOI 는 원문 표지에서 손으로 넣었습니다."
HAND_TAG = "내 태그"
KOREAN_TITLE = "솔더 접합부 연구"


class AliasTableTests(unittest.TestCase):
    def test_english_side_is_what_the_tools_write(self):
        self.assertEqual([tagging.UNTAGGED], list(legacy.LEGACY_TAGS.values()))
        self.assertEqual([NOTE_BROKEN, NOTE_FAIL], list(legacy.LEGACY_NOTES.values()))
        self.assertLessEqual(set(legacy.LEGACY_JOURNALS.values()), {name for _, name in meta.DOI_PUB})
        self.assertIn(oafetch.TEXT_ONLY_NOTE, legacy.LEGACY_OA_NOTES.values())
        self.assertEqual("_done", PT["ARCHIVE_DIRNAME"])
        self.assertEqual("_oa_inbox", config.DEFAULT["oa_staging"])

    def test_old_side_is_the_old_format(self):
        self.assertEqual(OLD_UNTAGGED, *legacy.LEGACY_TAGS)
        self.assertEqual([OLD_BROKEN, OLD_FAIL], list(legacy.LEGACY_NOTES))
        self.assertIn(OLD_SPRINGER, legacy.LEGACY_JOURNALS)
        self.assertIn(OLD_NATURE, legacy.LEGACY_JOURNALS)
        self.assertEqual("Sn-Bi-In ternary", PRESET["renamed"][OLD_TERNARY])

    def test_written_values_are_english(self):
        written = ([name for _, name in meta.DOI_PUB] + [tagging.UNTAGGED, NOTE_BROKEN, NOTE_FAIL, oafetch.TEXT_ONLY_NOTE,
                   PRESET["name"], PRESET["description"], tagging.auto_preset(["solder joint " * 9] * 5)["description"]]
                   + list(PRESET["tags"]))
        for table in (legacy.LEGACY_TAGS, legacy.LEGACY_NOTES, legacy.LEGACY_JOURNALS, legacy.LEGACY_MATCH_BY,
                      legacy.LEGACY_OA_NOTES, legacy.LEGACY_QUERY):
            written += list(table.values())
        self.assertEqual([], [w for w in written if HANGUL.search(w)])

    def test_encoding_note_in_either_spelling(self):
        self.assertTrue(legacy.has_encoding_word(NOTE_BROKEN))
        self.assertTrue(legacy.has_encoding_word(OLD_BROKEN))
        self.assertFalse(legacy.has_encoding_word(NOTE_FAIL))      # a failed restore must not look like a restored one
        self.assertFalse(legacy.has_encoding_word(OLD_FAIL))
        self.assertFalse(legacy.has_encoding_word(HAND_NOTE))

    def test_korean_only_in_legacy_constants_and_regex_ranges(self):
        found = []
        for path in sorted(SKILL.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            allowed = set()
            if path == SKILL / "lib" / "legacy.py":
                for node in tree.body:
                    if isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) and t.id.startswith("LEGACY")
                                                            for t in node.targets):
                        allowed |= {id(n) for n in ast.walk(node.value)}
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and isinstance(node.value, str) and HANGUL.search(node.value)
                        and id(node) not in allowed and "가-힣" not in node.value):
                    found.append(f"{path.relative_to(SKILL)}:{node.lineno}: {node.value[:40]!r}")
        self.assertEqual([], found)

    def test_shipped_preset_renames_cleanly(self):
        aliases, warnings = tagging.tag_aliases(PRESET)
        self.assertEqual([], warnings)
        self.assertFalse(set(PRESET["renamed"]) & set(PRESET["tags"]))
        self.assertLessEqual(set(PRESET["renamed"].values()), set(PRESET["tags"]))
        self.assertEqual(tagging.UNTAGGED, aliases[OLD_UNTAGGED])


class TagAliasTests(unittest.TestCase):
    def test_user_preset_renamed(self):
        preset = {"tags": {"Joints": [], "Live": []},
                  "renamed": {"Old joints": "Joint studies", "Joint studies": "Joints", "Live": "Joints",
                              "Gone": "Nowhere", "Loop a": "Loop b", "Loop b": "Loop a", "Number": 5}}
        aliases, warnings = tagging.tag_aliases(preset)
        self.assertEqual({OLD_UNTAGGED: tagging.UNTAGGED, "Old joints": "Joints", "Joint studies": "Joints",
                          "Gone": "Nowhere"}, aliases)
        text = "\n".join(warnings)
        for word in ("'Live' is still a tag", "'Gone' -> 'Nowhere', which is not a tag", "'Loop a' leads back",
                     "'Loop b' leads back", "'Number' -> 5 is not a tag name"):
            self.assertIn(word, text)
        self.assertEqual(5, len(warnings))

    def test_without_preset_or_with_a_broken_renamed(self):
        self.assertEqual((legacy.LEGACY_TAGS, []), tagging.tag_aliases(None))
        aliases, warnings = tagging.tag_aliases({"tags": {"A": []}, "renamed": ["A"]})
        self.assertEqual(legacy.LEGACY_TAGS, aliases)
        self.assertEqual(1, len(warnings))


class MigrateRowsTests(unittest.TestCase):
    def test_exact_matches_only_and_idempotent(self):
        rows = [{"tags": [OLD_TERNARY, "Sn-Bi-In ternary", OLD_UNTAGGED], "note": OLD_FAIL, "journal": OLD_SPRINGER,
                 "title": "A"},
                {"tags": [HAND_TAG], "note": OLD_FAIL + " (checked)", "journal": "Springer (기타) ", "title": KOREAN_TITLE}]
        res = legacy.migrate_rows(rows, tagging.tag_aliases(PRESET)[0])
        self.assertEqual({("tags", OLD_TERNARY): 1, ("tags", OLD_UNTAGGED): 1, ("note", OLD_FAIL): 1,
                          ("journal", OLD_SPRINGER): 1}, dict(res["converted"]))
        self.assertEqual({"tags": 1, "note": 1, "journal": 1, "title": 1}, dict(res["kept"]))
        self.assertEqual(["Sn-Bi-In ternary", tagging.UNTAGGED], rows[0]["tags"])
        self.assertEqual((NOTE_FAIL, "Springer (other)"), (rows[0]["note"], rows[0]["journal"]))
        before = json.dumps(rows)
        self.assertEqual({}, dict(legacy.migrate_rows(rows, tagging.tag_aliases(PRESET)[0])["converted"]))
        self.assertEqual(before, json.dumps(rows))


class CliCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="paper-format-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.library = self.base / "library"
        self.index = self.base / "index"
        self.library.mkdir()
        (self.index / "_fulltext").mkdir(parents=True)
        self.config = self.base / "paperindex.config.json"
        self.write_config(preset="solder-thesis")

    def write_config(self, **extra):
        self.config.write_text(json.dumps(dict({"library": str(self.library), "index_dir": str(self.index)}, **extra)),
                               encoding="utf-8")

    def row(self, rel, cache="interfacial solder reliability. " * 20, pdf=b"fixture source", **fields):
        (self.library / rel).write_bytes(pdf)
        (self.index / "_fulltext" / (rel[:-4] + ".txt")).write_text(cache, encoding="utf-8")
        r = dict(id="P000", rel=rel, folder="(root)", file=rel, year="2020", author="Kim",
                 title=f"Solder joint study {rel[:-4]}", title_src="pdf", doi="", journal="", chars=len(cache),
                 note="", txt=rel[:-4] + ".txt", tags=["Reflow · process"])
        r.update(fields)
        return r

    def write_index(self, rows):
        self.json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    @property
    def json_path(self):
        return self.index / "papers_index.json"

    def rows(self):
        return {r["rel"]: r for r in json.loads(self.json_path.read_text(encoding="utf-8"))}

    def papertool(self, *args):
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SKILL / "papertool.py"),
                                 "--config", str(self.config), *map(str, args)],
                                cwd=self.base, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return result.stdout

    def listed(self, out):
        return sorted(re.findall(r"<([^>]+)>$", out, re.M))


class ReindexMigrationTests(CliCase):
    def old_index(self):
        self.write_index([
            self.row("a.pdf", tags=[OLD_TERNARY, OLD_REFLOW], journal=OLD_SPRINGER, note=OLD_FAIL),
            self.row("b.pdf", tags=[OLD_UNTAGGED], note=HAND_NOTE, journal="Journal of Alloys and Compounds"),
            self.row("c.pdf", tags=[HAND_TAG, "Sn-Bi-In ternary", OLD_TERNARY]),
            self.row("d.pdf", note=OLD_BROKEN, journal=OLD_NATURE, title=KOREAN_TITLE, year=""),
            self.row("e.pdf", note=OLD_FAIL + " (확인함)"),          # "(checked)": not an exact match
        ])
        return self.json_path.read_bytes()

    def backups(self):
        folder = self.index / "_backup"
        return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []

    def test_reindex_converts_once_with_one_backup(self):
        original = self.old_index()
        out = self.papertool("reindex")
        self.assertIn("Added 0 new papers", out)
        m = re.search(r"^Converted 8 values written by an older version to English · "
                      r"kept 4 other non-English values as written · backup: (.+)$", out, re.M)
        self.assertTrue(m, out)
        today = datetime.date.today().isoformat()
        self.assertEqual([f"papers_index_{today}.json"], self.backups())
        self.assertEqual(Path(m.group(1)).resolve(), (self.index / "_backup" / f"papers_index_{today}.json").resolve())
        self.assertEqual(original, Path(m.group(1)).read_bytes())

        rows = self.rows()
        self.assertEqual(["Sn-Bi-In ternary", "Reflow · process"], rows["a.pdf"]["tags"])
        self.assertEqual(("Springer (other)", NOTE_FAIL), (rows["a.pdf"]["journal"], rows["a.pdf"]["note"]))
        self.assertEqual([tagging.UNTAGGED], rows["b.pdf"]["tags"])
        self.assertEqual((HAND_NOTE, "Journal of Alloys and Compounds"), (rows["b.pdf"]["note"], rows["b.pdf"]["journal"]))
        self.assertEqual([HAND_TAG, "Sn-Bi-In ternary"], rows["c.pdf"]["tags"])
        self.assertEqual((NOTE_BROKEN, "Nature family", KOREAN_TITLE),
                         (rows["d.pdf"]["note"], rows["d.pdf"]["journal"], rows["d.pdf"]["title"]))
        self.assertEqual(OLD_FAIL + " (확인함)", rows["e.pdf"]["note"])

        converted = self.json_path.read_bytes()
        out = self.papertool("reindex")
        self.assertNotIn("Converted", out)
        self.assertEqual(converted, self.json_path.read_bytes())
        self.assertEqual([f"papers_index_{today}.json"], self.backups())

    def test_backup_never_overwrites(self):
        original = self.old_index()
        today = datetime.date.today().isoformat()
        (self.index / "_backup").mkdir()
        (self.index / "_backup" / f"papers_index_{today}.json").write_bytes(b"an earlier backup")
        self.papertool("reindex")
        self.assertEqual(b"an earlier backup", (self.index / "_backup" / f"papers_index_{today}.json").read_bytes())
        self.assertEqual(original, (self.index / "_backup" / f"papers_index_{today}_1.json").read_bytes())

    def test_search_tag_accepts_old_and_new_names(self):
        self.old_index()
        self.assertEqual(["a.pdf", "c.pdf"], self.listed(self.papertool("search", "--tag", "ternary")))   # before
        self.assertEqual(["b.pdf"], self.listed(self.papertool("search", "--tag", "untagged")))
        self.papertool("reindex")
        self.assertEqual(["a.pdf", "c.pdf"], self.listed(self.papertool("search", "--tag", "삼원계")))     # "ternary"
        self.assertEqual(["a.pdf", "c.pdf"], self.listed(self.papertool("search", "--tag", OLD_TERNARY)))
        self.assertEqual(["b.pdf"], self.listed(self.papertool("search", "--tag", OLD_UNTAGGED)))
        self.assertEqual(["c.pdf"], self.listed(self.papertool("search", "--tag", HAND_TAG)))

    def test_generated_files_are_english(self):
        self.old_index()
        self.papertool("reindex")
        md = (self.index / "papers_index.md").read_text(encoding="utf-8")
        for heading in ("## Contents", "## By topic", "### Sn-Bi-In ternary (2)", "## All papers by year",
                        "### year unknown (1)", "## Duplicate files", "## Needs attention"):
            self.assertIn(heading + "\n", md)
        self.assertIn("· tags: ", md)
        header = (self.index / "papers_index.csv").read_text(encoding="utf-8-sig").splitlines()[0]
        self.assertEqual("ID,year,first author,title,source,DOI,tags,folder,file,full-text cache,note", header)

    def test_user_preset_with_its_own_renamed(self):
        preset = self.base / "my-preset.json"
        preset.write_text(json.dumps({"name": "mine", "tags": {"Interfaces": ["interface"], "Joints": ["joint"]},
                                      "renamed": {"Interface studies": "Interfaces"}}), encoding="utf-8")
        self.write_config(preset=str(preset))
        self.write_index([self.row("x.pdf", tags=["Interface studies", "Joints"]), self.row("y.pdf", tags=["Joints"])])
        self.assertEqual(["x.pdf"], self.listed(self.papertool("search", "--tag", "interfaces")))
        out = self.papertool("reindex")
        self.assertIn("Converted 1 values", out)
        self.assertNotIn("※ Preset", out)
        self.assertEqual(["Interfaces", "Joints"], self.rows()["x.pdf"]["tags"])
        self.assertEqual(["x.pdf"], self.listed(self.papertool("search", "--tag", "interface stud")))


class RepairTests(CliCase):
    def test_repair_finds_encoding_notes_in_either_spelling(self):
        # Stand-in extractor: `pdftotext` is this Python, and each fixture "PDF" is a Python script that prints
        # well-formed English, so `repair` (which runs `<pdftotext> -q <file> -`) gets text it can restore.
        self.write_config(pdftotext=sys.executable)
        script = b'print("The results of the analysis show that the solder and the substrate form a stable interface. " * 40)\n'
        gibberish = "xq zv " * 50
        self.write_index([self.row(rel, cache=gibberish, pdf=script, note=note) for rel, note in
                          (("r1.pdf", OLD_BROKEN), ("r2.pdf", NOTE_BROKEN), ("r3.pdf", NOTE_FAIL), ("r4.pdf", OLD_FAIL))])
        out = self.papertool("repair")
        self.assertIn("To restore: 2 papers", out)
        self.assertIn("restored 2 / failed 0", out)
        rows = self.rows()
        self.assertEqual([NOTE_BROKEN, NOTE_BROKEN, NOTE_FAIL, OLD_FAIL],
                         [rows[r]["note"] for r in ("r1.pdf", "r2.pdf", "r3.pdf", "r4.pdf")])


class ScopusHistoryTests(CliCase):
    def test_old_archive_folder_is_reused(self):
        scopus = self.index / "_scopus"
        (scopus / "_실행완료").mkdir(parents=True)                  # the archive folder of older versions ("_run done")
        for name in ("Scopus검색_x.bat", "Scopus검색_x.query.txt"):
            (self.index / name).write_text("old launcher", encoding="utf-8")
        (scopus / "x.json").write_text('{"entries": []}', encoding="utf-8")
        out = self.papertool("scopus-tidy")
        self.assertIn("to _실행완료/", out)
        self.assertEqual(["Scopus검색_x.bat", "Scopus검색_x.query.txt"], sorted(p.name for p in (scopus / "_실행완료").iterdir()))
        self.assertFalse((scopus / "_done").exists())

    def test_old_result_file_is_read_and_kept(self):
        self.write_index([self.row("owned.pdf", doi="10.1000/owned", title="An owned paper on solder joints")])
        old_note = "OA 이지만 PDF 직접 주소가 없음 — 링크로 직접 받으십시오"        # "OA, but no direct PDF address"
        old = self.base / "old_result.json"
        old.write_text(json.dumps({"meta": {"query": "TITLE(solder)", "total": 2}, "entries": [
            {"title": "An owned paper on solder joints", "doi": "10.1000/owned", "owned": True, "match_by": "DOI 일치"},
            {"title": "A missing paper", "doi": "10.1000/missing", "owned": False, "match_by": "",
             "oa_note": old_note, "abstract": "An abstract."}]}, ensure_ascii=False), encoding="utf-8")
        self.assertIn(old_note, legacy.LEGACY_OA_NOTES)                 # the fixture is the old format on record
        self.assertIn("DOI 일치", legacy.LEGACY_MATCH_BY)
        before = old.read_bytes()
        self.papertool("scopus-merge", old, "--name", "merged", "-q")
        self.assertEqual(before, old.read_bytes())
        merged = json.loads((self.index / "_scopus" / "merged.json").read_text(encoding="utf-8"))["entries"]
        self.assertEqual(["DOI match", ""], [e["match_by"] for e in merged])
        self.assertEqual(old_note, merged[1]["oa_note"])                # result values are kept as written
        md = (self.index / "_scopus" / "merged.md").read_text(encoding="utf-8")
        for text in ("**Owned 1 · missing 1**", "## Per-entry abstracts", "| # | Owned | OA |", f"OA: {old_note}"):
            self.assertIn(text, md)
        self.assertIn("Filtered: 2 → 1 kept", self.papertool("scopus-sift", old, "--require", "missing", "-q"))

    def test_raw_response_query_label(self):
        self.write_index([self.row("owned.pdf")])
        raw = self.base / "raw.json"
        raw.write_text(json.dumps({"search-results": {"opensearch:totalResults": "1", "entry": [
            {"dc:title": "A raw entry", "prism:doi": "10.1000/raw"}]}}), encoding="utf-8")
        self.papertool("scopus-merge", raw, "--name", "raw", "-q")
        saved = json.loads((self.index / "_scopus" / "raw.json").read_text(encoding="utf-8"))
        self.assertEqual("(raw response)", saved["meta"]["query"])
        self.assertEqual("(raw response)", legacy.LEGACY_QUERY["(원본 응답)"])   # the label older versions wrote


def nfd(s):
    return unicodedata.normalize("NFD", s)


# Stand-in extractor (see the repair test): called as `<python> -q <pdf> <out>` it runs the fixture "PDF", a script
# that writes its text to <out>, or prints it when <out> is "-".
STAND_IN = (b'import sys\nt = "The solder and the substrate form a stable interface after reflow. " * 40\n'
            b'o = sys.argv[1] if len(sys.argv) > 1 else "-"\n'
            b'print(t) if o == "-" else open(o, "w", encoding="utf-8").write(t)\n')


class UnicodeNameTests(CliCase):
    """A library whose Korean names are stored in NFD (a macOS Drive mirror) against an index written in NFC.
    The names are made at run time; on Linux and NTFS an NFD file does not open by its NFC name."""
    DIR, PDF = "2026", "가나다문헌_1.pdf"

    def setUp(self):
        super().setUp()
        self.write_config(preset="solder-thesis", pdftotext=sys.executable)
        rel = self.DIR + "/" + self.PDF
        (self.library / self.DIR).mkdir()
        (self.library / self.DIR / nfd(self.PDF)).write_bytes(STAND_IN)
        (self.library / "plain.pdf").write_bytes(STAND_IN)
        self.korean = self.row_for(rel)
        self.write_index([self.korean, self.row_for("plain.pdf")])

    def row_for(self, rel, **fields):
        txt = rel[:-4].replace("/", "__") + ".txt"
        body = "interfacial solder reliability after reflow. " * 20
        (self.index / "_fulltext" / txt).write_text(body, encoding="utf-8")
        r = dict(id="P000", rel=rel, folder=os.path.dirname(rel) or "(root)", file=os.path.basename(rel), year="2026",
                 author="Kim", title="Solder joint study", title_src="pdf", doi="", journal="", chars=len(body),
                 note="", txt=txt, tags=["Reflow · process"])
        r.update(fields)
        return r

    def test_doctor_counts_the_same_file_once(self):
        out = self.papertool("doctor")
        self.assertIn("Paths missing (only in the index): 0", out)
        self.assertIn("Not in the index (only in the source): 0", out)
        self.assertIn("Missing cache: none", out)

    def test_reindex_and_resync_add_nothing(self):
        self.assertIn("Added 0 new papers", self.papertool("reindex"))
        out = self.papertool("resync")
        self.assertNotIn("removed", out)
        self.assertNotIn("new files", out)
        self.assertEqual({self.DIR + "/" + self.PDF, "plain.pdf"}, set(self.rows()))

    def test_new_nfd_file_gets_one_entry_and_an_nfc_cache_name(self):
        new = "새문헌.pdf"
        (self.library / self.DIR / nfd(new)).write_bytes(STAND_IN)
        self.assertIn("Added 1 new papers", self.papertool("reindex"))
        self.assertIn(self.DIR + "/" + new, self.rows())
        cache = self.DIR + "__" + new[:-4] + ".txt"
        self.assertIn(cache, os.listdir(self.index / "_fulltext"))      # written under the NFC name
        self.assertIn("Added 0 new papers", self.papertool("reindex"))

    def test_repair_opens_the_nfd_source(self):
        broken = dict(self.korean, note=NOTE_BROKEN)
        (self.index / "_fulltext" / broken["txt"]).write_text("xq zv " * 50, encoding="utf-8")
        self.write_index([broken, self.row_for("plain.pdf")])
        self.assertIn("restored 1 / failed 0", self.papertool("repair"))

    def test_verify_index_sees_one_mapping(self):
        out = self.base / "snapshot.json"
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SKILL / "verify_index.py"), "--config",
                                 str(self.config), "snapshot", "--out", str(out)],
                                cwd=self.base, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        issues = json.loads(out.read_text(encoding="utf-8"))["issues"]
        self.assertEqual([], [i for i in issues if "source" in i.lower() or "cache" in i.lower()])

    def test_keys_keep_hangul_from_nfd_names(self):
        resync, render = lib_module("resync"), lib_module("render")
        self.assertEqual(resync.norm_key(self.DIR + "/" + self.PDF), resync.norm_key(nfd(self.DIR + "/" + self.PDF)))
        self.assertIn("가나다문헌", resync.norm_key(nfd(self.PDF)))
        self.assertEqual(render._norm("가나 다라"), render._norm(nfd("가나 다라")))


if __name__ == "__main__":
    unittest.main()
