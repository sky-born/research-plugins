"""Scopus paging without network: a fake transport stands in for api.elsevier.com.

Each case runs papertool.py in a subprocess (fresh `lib` modules) whose `lib.scopus._get`
is replaced by a fake that enforces one key's page-size limits and records every request.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "paper-index" / "skills" / "paper-search"

# argv: <skill dir> <key spec json> <papertool args...>
# key spec: complete = COMPLETE view allowed · standard_max = STANDARD page limit · total = hits
DRIVER = r'''
import json, os, runpy, sys, urllib.parse
skill, spec = sys.argv[1], json.loads(sys.argv[2])
sys.path.insert(0, skill)
from lib import scopus
calls = []

def fail(code, status, text):
    err = scopus.ScopusError("HTTP %d\n%s" % (code, json.dumps(
        {"service-error": {"status": {"statusCode": status, "statusText": text}}})))
    err.code = code
    raise err

def fake_get(url, key, timeout):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    view, start, count = q.get("view", [""])[0], int(q["start"][0]), int(q["count"][0])
    calls.append([view, start, count])
    if view == "COMPLETE" and not spec["complete"]:
        fail(401, "AUTHORIZATION_ERROR", "The requestor is not authorized to access the requested view")
    if count > (25 if view == "COMPLETE" else spec["standard_max"]):
        fail(400, "INVALID_INPUT", "Exceeds the maximum number allowed for the service level")
    total = spec["total"]
    entries = [{"eid": "2-s2.0-%d" % i, "dc:title": "Fixture paper %d" % i}
               for i in range(start, min(start + count, total))]
    body = {"search-results": {"opensearch:totalResults": str(total),
                               "entry": entries or [{"error": "Result set was empty"}]}}
    return json.dumps(body), {"quota_limit": None, "quota_remaining": None, "quota_reset": None}

scopus._get = fake_get
sys.argv = [os.path.join(skill, "papertool.py")] + sys.argv[3:]
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
finally:
    print("CALLS " + json.dumps(calls))
'''

# Like the key that exposed the bug: no COMPLETE view, STANDARD pages up to 25 only.
KEY_25 = {"complete": False, "standard_max": 25, "total": 82}


class ScopusPagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="scopus-paging-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        (self.base / "library").mkdir()
        self.config = self.base / "paperindex.config.json"
        self.write_config()

    def write_config(self, scopus=None):
        cfg = {"library": str(self.base / "library"), "index_dir": str(self.base / "index")}
        if scopus is not None:
            cfg["scopus"] = scopus
        self.config.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    def run_scopus(self, spec, *args):
        env = dict(os.environ, ELS_API_KEY="fixture-key")   # never the real key; _get is fake anyway
        env.pop("ELS_INST_TOKEN", None)
        result = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", "-c", DRIVER, str(SKILL), json.dumps(spec),
             "--config", str(self.config), "scopus", "TITLE-ABS-KEY(fixture)", "--name", "t", "-q", *args],
            cwd=self.base, text=True, encoding="utf-8", capture_output=True, env=env)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        line = [ln for ln in result.stdout.splitlines() if ln.startswith("CALLS ")][-1]
        calls = json.loads(line[len("CALLS "):])
        saved = self.base / "index" / "_scopus" / "t.json"
        entries = json.loads(saved.read_text(encoding="utf-8"))["entries"] if saved.exists() else None
        return result.stdout, calls, entries

    @staticmethod
    def eids(entries):
        return [e["eid"] for e in entries]

    def test_all_never_asks_more_than_the_default_page(self):
        out, calls, entries = self.run_scopus(KEY_25, "--all")
        self.assertEqual([f"2-s2.0-{i}" for i in range(82)], self.eids(entries))
        self.assertEqual("COMPLETE", calls[0][0])                  # abstracts are tried first
        self.assertTrue(all(c[2] <= 25 for c in calls), calls)    # no request the key refuses
        self.assertNotIn("HTTP 400", out)
        self.assertNotIn("건만 받았습니다", out)

    def test_page_size_above_the_key_limit_falls_back_and_warns_once(self):
        self.write_config({"page_size": 200})
        out, calls, entries = self.run_scopus(KEY_25, "--all")
        self.assertEqual([f"2-s2.0-{i}" for i in range(82)], self.eids(entries))
        self.assertEqual(1, sum(1 for c in calls if c[2] > 25), calls)   # refused once, then 25s
        self.assertEqual(1, out.count("HTTP 400"))

    def test_configured_large_pages_when_the_key_allows_them(self):
        self.write_config({"page_size": 200})
        spec = {"complete": False, "standard_max": 200, "total": 450}
        out, calls, entries = self.run_scopus(spec, "--all")
        self.assertEqual(450, len(set(self.eids(entries))))
        self.assertEqual([["COMPLETE", 0, 25], ["", 0, 25], ["STANDARD", 25, 200],
                          ["STANDARD", 225, 200], ["STANDARD", 425, 25]], calls)

    def test_complete_pages_stay_at_25(self):
        self.write_config({"page_size": 200})
        spec = {"complete": True, "standard_max": 200, "total": 60}
        out, calls, entries = self.run_scopus(spec, "--all")
        self.assertEqual(60, len(set(self.eids(entries))))
        self.assertTrue(all(c[0] == "COMPLETE" and c[2] <= 25 for c in calls), calls)

    def test_single_page_count_above_the_limit_is_retried_at_25(self):
        out, calls, entries = self.run_scopus(KEY_25, "--count", "100")
        self.assertEqual(25, len(entries))
        self.assertEqual(["", 0, 25], calls[-1])
        self.assertIn("HTTP 400", out)

    def test_unknown_or_invalid_scopus_settings_warn_and_use_defaults(self):
        self.write_config({"pagesize": 200, "page_size": "200", "_주석": "comment keys are skipped"})
        out, calls, entries = self.run_scopus(KEY_25, "--all")
        self.assertIn("scopus.pagesize", out)
        self.assertIn("scopus.page_size", out)
        self.assertNotIn("_주석", out)
        self.assertEqual(82, len(entries))
        self.assertTrue(all(c[2] <= 25 for c in calls), calls)

    def test_all_from_an_offset_stops_at_the_last_result(self):
        out, calls, entries = self.run_scopus(KEY_25, "--all", "--start", "50")
        self.assertEqual([f"2-s2.0-{i}" for i in range(50, 82)], self.eids(entries))
        self.assertTrue(all(c[1] + c[2] <= 82 for c in calls), calls)   # nothing past the end
        self.assertNotIn("건만 받았습니다", out)

    def papertool(self, *args, env=None):
        result = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", str(SKILL / "papertool.py"), "--config", str(self.config), *args],
            cwd=self.base, text=True, encoding="utf-8", capture_output=True, env=env)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return result.stdout

    def test_blocked_call_points_to_the_one_python_command(self):
        env = dict(os.environ)
        env.pop("ELS_API_KEY", None)                       # no key: the tool explains what to run where
        out = self.papertool("scopus", "TITLE-ABS-KEY(fixture)", "--name", "t", env=env)
        self.assertIn('papertool.py" scopus "TITLE-ABS-KEY(fixture)"', out)
        self.assertIn("scopus-merge", out)
        self.assertNotIn(".ps1", out)
        self.assertNotIn("powershell", out.lower())

    def test_tidy_archives_launchers_left_by_older_versions(self):
        index = self.base / "index"
        (index / "_scopus").mkdir(parents=True)
        for name in ("Scopus검색_done.bat", "Scopus검색_done.query.txt", "Scopus검색_pending.bat", "scopus_search.ps1"):
            (index / name).write_text("old launcher", encoding="utf-8")
        (index / "_scopus" / "done.json").write_text('{"entries": []}', encoding="utf-8")
        self.papertool("scopus-tidy")
        archive = index / "_scopus" / "_실행완료"
        self.assertEqual(["Scopus검색_done.bat", "Scopus검색_done.query.txt"], sorted(p.name for p in archive.iterdir()))
        self.assertTrue((index / "Scopus검색_pending.bat").exists())      # no result yet: left alone
        self.assertTrue((index / "scopus_search.ps1").exists())            # still beside the pending one
        self.assertIn("치울 실행 파일이 없습니다", self.papertool("scopus-tidy"))

    def test_merge_accepts_the_retired_keep_launcher_flag(self):
        saved = self.base / "in.json"
        saved.write_text(json.dumps({"meta": {"query": "q"}, "entries": [{"eid": "2-s2.0-1", "title": "Fixture"}]}),
                         encoding="utf-8")
        self.papertool("scopus-merge", str(saved), "--name", "m", "-q", "--keep-launcher")
        self.assertTrue((self.base / "index" / "_scopus" / "m.json").exists())


if __name__ == "__main__":
    unittest.main()
