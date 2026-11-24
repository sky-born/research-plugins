"""Fixture-only CLI checks. No live library, PDF extractor, or network is used."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "paper-index" / "skills" / "paper-search"


class PaperPortabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="paper-portability-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / "한글 space"
        self.library = self.base / "library"
        self.index = self.base / "index"
        self.library.mkdir(parents=True)
        (self.index / "_fulltext").mkdir(parents=True)
        self.source = self.library / "article.pdf"
        # Deliberately not an actual PDF: extraction is outside this test's scope.
        self.source.write_bytes(b"fixture source; must not be written by CLI")
        self.cache = self.index / "_fulltext" / "article.txt"
        self.cache.write_text("A fixture paper\nResearcher\n2024\n" + "interfacial solder reliability. " * 30,
                              encoding="utf-8")
        self.config = self.base / "paperindex.config.json"
        self.config.write_text(json.dumps({"library": str(self.library), "index_dir": str(self.index)}),
                               encoding="utf-8")

    def run_cli(self, script, *args, expected=0):
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SKILL / script),
                                 "--config", str(self.config), *map(str, args)],
                                cwd=self.base, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result

    def snapshot(self, name):
        path = self.base / name
        self.run_cli("verify_index.py", "snapshot", "--out", path)
        return path

    def build(self):
        self.run_cli("papertool.py", "index")

    def verify(self, before, name="after.json", expected=0, extra=()):
        output = self.base / name
        self.run_cli("verify_index.py", "verify", "--before", before, "--out", output,
                     *extra, expected=expected)
        return json.loads(output.read_text(encoding="utf-8"))

    def test_cached_index_search_and_unchanged_rerun(self):
        original = hashlib.sha256(self.source.read_bytes()).hexdigest()
        before = self.snapshot("before.json")
        self.build()
        first = self.verify(before)
        self.assertTrue(first["sources_unchanged"])
        self.assertEqual((1, 1), (first["source_count"], first["index_count"]))
        result = self.run_cli("papertool.py", "search", "--count-only", "interfacial")
        self.assertIn("적중 1편", result.stdout)
        self.assertIn("총 출현 30회", result.stdout)
        rerun = self.snapshot("rerun-before.json")
        self.assertIn("신규 0편", self.run_cli("papertool.py", "reindex").stdout)
        final = self.verify(rerun, "rerun-after.json", extra=("--require-index-unchanged",))
        self.assertTrue(final["ok"])
        self.assertTrue(final["index_unchanged"])
        self.assertEqual(original, hashlib.sha256(self.source.read_bytes()).hexdigest())

    def test_same_size_and_mtime_source_change_detected_by_hash(self):
        self.build()
        before = self.snapshot("before.json")
        stat = self.source.stat()
        self.source.write_bytes(b"X" * stat.st_size)
        os.utime(self.source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        after = self.verify(before, expected=1)
        self.assertEqual(["article.pdf"], after["source_changes"])

    def test_missing_cache_is_reported(self):
        self.build()
        before = self.snapshot("before.json")
        self.cache.unlink()
        after = self.verify(before, expected=1)
        self.assertTrue(any("Missing cache" in item for item in after["issues"]))

    def test_changed_cache_fails_unchanged_rerun(self):
        self.build()
        before = self.snapshot("before.json")
        self.cache.write_text("changed cached text " * 100, encoding="utf-8")
        after = self.verify(before, expected=1, extra=("--require-index-unchanged",))
        self.assertTrue(after["sources_unchanged"])
        self.assertFalse(after["index_unchanged"])

    def test_reports_do_not_overwrite_or_enter_source(self):
        before = self.snapshot("before.json")
        original = before.read_bytes()
        self.run_cli("verify_index.py", "snapshot", "--out", before, expected=1)
        self.assertEqual(original, before.read_bytes())
        forbidden = self.library / "report.json"
        self.run_cli("verify_index.py", "snapshot", "--out", forbidden, expected=1)
        self.assertFalse(forbidden.exists())

    def test_overlapping_source_and_index_is_rejected(self):
        self.config.write_text(json.dumps({"library": str(self.library),
                                           "index_dir": str(self.library / "index")}), encoding="utf-8")
        forbidden = self.base / "bad.json"
        result = self.run_cli("verify_index.py", "snapshot", "--out", forbidden, expected=1)
        self.assertIn("must be separate", result.stderr)
        self.assertFalse(forbidden.exists())

    def test_duplicate_cache_mapping_is_reported(self):
        self.build()
        before = self.snapshot("before.json")
        index_path = self.index / "papers_index.json"
        rows = json.loads(index_path.read_text(encoding="utf-8"))
        rows.append(dict(rows[0]))
        index_path.write_text(json.dumps(rows), encoding="utf-8")
        after = self.verify(before, expected=1)
        self.assertTrue(any("Shared cache" in item for item in after["issues"]))
        self.assertTrue(any("Duplicate source" in item for item in after["issues"]))


if __name__ == "__main__":
    unittest.main()
