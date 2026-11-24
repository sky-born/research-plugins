"""Table row format (_config.table_problems · split_cells) — split rows · `\\|` cells · archive table separator · replace_once blocking · hook notice. Checked with synthetic fixtures.

Scenarios: the Bash tool turns `'\\n'` in a command string into a line break, so a row is split
over two lines; only the row is archived and the tail stays in the pending file; the first archiving erases the separator of the archive table; a note that contains `\\|` is cut off in the focus block.
Fixtures are built in the OS temp folder and the per-computer state also goes to a temp folder (`SYNC_STATE_HOME`). No research files are touched.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "research-writing" / "skills" / "new-manuscript"
TOOLS = SKILL / "tools"
HOOK = SKILL / "hooks" / "guard_write.py"
INITIALIZER = SKILL / "init_manuscript.py"
PY = [sys.executable, "-X", "utf8", "-B"]

os.environ.setdefault("SYNC_STATE_HOME", tempfile.mkdtemp(prefix="table-rows-state-"))   # do not override the state folder of a suite imported earlier
STATE = Path(os.environ["SYNC_STATE_HOME"])

sys.path.insert(0, str(TOOLS))
import _config  # noqa: E402
import _sync  # noqa: E402

HDR_PEND = "| ID | Item | Location | Trigger | Status | Note |\n|---|---|---|---|---|---|\n"
HDR_PRO = "| ID | Proposal | Location | Trigger | Status | Note |\n|---|---|---|---|---|---|\n"
HDR_ARCH = "| ID | Item | Location | Status | Note |"
SEP_ARCH = "|---|---|---|---|---|"


def run(cmd, cwd, codes=(0,), inp=None):
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", timeout=120, input=inp)
    assert r.returncode in codes, f"{cmd}\nrc={r.returncode}\n{r.stdout}\n{r.stderr}"
    assert "Traceback" not in r.stderr, r.stderr
    return r


def hook(mode, payload, cwd):
    return run(PY + [str(HOOK), mode], cwd, inp=json.dumps(payload))


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = Path(tempfile.mkdtemp(prefix="table-rows-"))

    def project(self, name: str) -> Path:
        p = self.scratch / name
        run(PY + [str(INITIALIZER), str(p), "--name", "Table row sample " + name, "--kind", "journal",
                  "--source-dir", "manuscript", "--chapters", "intro.md", "results.md", "--references", "references.md"],
            self.scratch)
        return p

    @staticmethod
    def trig(p: Path) -> str:
        return json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8"))["tracker"]["triggers"][1]

    def add_rows(self, path: Path, hdr: str, rows: str):
        text = path.read_text(encoding="utf-8")
        self.assertIn(hdr, text)
        path.write_text(text.replace(hdr, hdr + rows, 1), encoding="utf-8", newline="\n")

    @staticmethod
    def tidy(p: Path, *args, codes=(0, 1)):
        return run(PY + [str(p / "tools" / "tidy_tracker.py"), *args], p, codes=codes)

    @staticmethod
    def edit_payload(p: Path, rel: str, tid: str):
        return {"tool_name": "Edit", "tool_input": {"file_path": str(p / rel), "old_string": "a", "new_string": "b"},
                "cwd": str(p), "tool_use_id": tid}


# ---------------------------------------------------------------- grammar — defined in one place
class GrammarTests(unittest.TestCase):
    def test_split_cells_keeps_escaped_pipe(self):
        self.assertEqual(_config.split_cells("| A1 | value \\| two | end |"), ["A1", "value \\| two", "end"])
        self.assertEqual(_config.split_cells("|a|b|"), ["a", "b"])
        self.assertEqual(_config.split_cells("| A1 | ends with \\|"), ["A1", "ends with \\|"], "a trailing \\| is not a closing pipe")
        self.assertEqual(_config.unescape_cell("x \\| y"), "x | y")

    def test_row_regex_is_shared_by_sync_and_tidy(self):
        self.assertIs(_sync.ROW_ID_RE, _config.TABLE_ROW_RE_M)
        for ok in ("| A70 | x |", "| AB1-2 | x |", "|D14|x|"):
            self.assertTrue(_config.TABLE_ROW_RE.match(ok), ok)
        for no in ("| ID | Item |", "| P006·P007 | x |", "|---|---|", " | A1 | x |"):
            self.assertFalse(_config.TABLE_ROW_RE.match(no), no)

    def test_table_problems_finds_split_rows_and_skips_breakers(self):
        text = "\n".join([
            "| ID | Item | Status |",                 # 1 header
            "|---|---|---|",                           # 2
            "| A1 | first | done |",                   # 3
            "'` and hash it, then S4 … tail |",        # 4 orphan — a split-off tail
            "| A2 | second | waiting |",               # 5
            " **2026-09-02 (E221)** — tail |",         # 6 orphan — with a leading space
            "| A3 | third | waiting |",                # 7
            "<!-- /archived-list:A -->",               # 8 a comment ends the table
            "",                                        # 9
            "### A3 details",                          # 10
            "| ID | Item | Status |",                 # 11 a new table
            "| A4 | cells | four | here |",            # 12 cells
            "| A5 | no closing pipe",                  # 13 cells + tail
            "| P006·P007 | row without an ID |",       # 14 no ID — not checked
            "- a list line",                           # 15 a list ends the table
            "```",                                     # 16
            "| x |",                                   # 17 inside a code fence
            "a tail inside the fence",                 # 18
            "```",                                     # 19
            "| ID | a |",                              # 20
            "| A6 | b |",                              # 21
            "> quotation",                             # 22 a quotation ends the table
            "| ID | a |",                              # 23
            "| A7 | c |",                              # 24
            "# Heading",                               # 25
            "", ])
        got = [(n, c) for n, c, _p in _config.table_problems(text)]
        self.assertEqual(got, [(4, "orphan"), (6, "orphan"), (12, "cells"), (13, "cells"), (13, "tail")])
        self.assertEqual([(n, c) for n, c, _p in _config.table_problems(text.replace("\n", "\r\n"))], got, "the same with CRLF")
        self.assertEqual(_config.table_problems("| ID | a |\n|---|---|\n| A1 | b \\| c |\n\ntext\n"), [], "\\| is not a cell boundary")
        self.assertIn("line 4", _config.describe_table_problem((4, "orphan", "tail")))
        # old-format data: a Korean marker (pre-0.14 spelling) ends a table the same way
        old_marker = "<!-- /%s -->" % _config.BLOCKS["archived_list"][1].format("A")
        self.assertEqual(_config.table_problems("| ID | a |\n|---|---|\n| A1 | b |\n" + old_marker + "\n"), [])


# ---------------------------------------------------------------- tidy tool — warning · archiving held · separator
class TidyTests(Fixture):
    def test_warns_split_row_holds_migration_and_restores_separator(self):
        p = self.project("split-row")
        trig = self.trig(p)
        pend, arch = p / "tracker_pending.md", p / "records" / "archive.md"
        tail = "'` and hash it, then the tail — what is left |"
        self.add_rows(pend, HDR_PEND,
                      f"| A1 | closed | `manuscript/results.md` ③ | {trig} | done (2026-10-06) | note |\n"
                      f"{tail}\n"
                      f"| A2 | open | `manuscript/intro.md` ¶1 | {trig} | waiting | |\n")
        # imitates a separator that went missing from the archive table
        arch.write_text(arch.read_text(encoding="utf-8").replace(SEP_ARCH + "\n", "", 1), encoding="utf-8", newline="\n")
        self.assertNotIn(SEP_ARCH, arch.read_text(encoding="utf-8"))
        n = pend.read_text(encoding="utf-8").split("\n").index(tail) + 1

        r = self.tidy(p)                                                   # diagnosis only
        self.assertIn("pending: table row format", r.stdout)
        self.assertIn(f"line {n}", r.stdout)
        self.assertIn("A1: a non-table line (line ", r.stdout)
        self.assertIn("archiving is held", r.stdout)
        self.assertIn("restored the separator", r.stdout)
        self.assertIn("archive.md", r.stdout.split("Files that would change", 1)[1])
        self.assertNotIn(SEP_ARCH, arch.read_text(encoding="utf-8"), "a diagnosis alone does not write")
        self.assertIn("| A1 |", pend.read_text(encoding="utf-8"))

        r = self.tidy(p, "--apply")
        self.assertIn("archiving is held", r.stdout)
        self.assertIn("| A1 |", pend.read_text(encoding="utf-8"), "a split completed row is not moved")
        self.assertIn(tail, pend.read_text(encoding="utf-8"))
        lines = arch.read_text(encoding="utf-8").split("\n")
        self.assertEqual(lines[lines.index(HDR_ARCH) + 1], SEP_ARCH, "the separator is restored right below the header")
        self.assertNotIn("| A1 |", arch.read_text(encoding="utf-8"))

        # once the tail is joined to the row it is archived — the separator stays and the row goes below it
        _sync.replace_once(str(pend), f"| note |\n{tail}", f"| note {tail}")
        r = self.tidy(p, "--apply")
        self.assertNotIn("table row format", r.stdout)
        self.assertNotIn("held", r.stdout)
        self.assertNotIn("| A1 |", pend.read_text(encoding="utf-8"))
        text = arch.read_text(encoding="utf-8")
        lines = text.split("\n")
        i = lines.index(HDR_ARCH)
        self.assertEqual(lines[i + 1], SEP_ARCH)
        self.assertTrue(lines[i + 2].startswith("| A1 |"), lines[i + 2])
        self.assertIn("what is left |", lines[i + 2])
        self.assertIn(f"(trigger: {trig}) note", lines[i + 2], "the trigger is kept in the note of the archived row")
        self.assertEqual(text.count(SEP_ARCH), 1)
        before = arch.read_bytes()
        self.tidy(p, "--apply")
        self.assertEqual(before, arch.read_bytes(), "two runs must give the same result")
        self.assertEqual(_config.table_problems(text), [])

    def test_skips_migration_when_archive_holds_a_stray_line(self):
        p = self.project("archive-tail")
        trig = self.trig(p)
        pend, arch = p / "tracker_pending.md", p / "records" / "archive.md"
        self.add_rows(pend, HDR_PEND, f"| A1 | closed | `manuscript/results.md` ③ | {trig} | done (2026-10-06) | |\n")
        arch.write_text(arch.read_text(encoding="utf-8").replace(
            SEP_ARCH + "\n", SEP_ARCH + "\n| B1 | archived earlier | x | done | note |\na line with only a tail |\n", 1),
            encoding="utf-8", newline="\n")
        r = self.tidy(p, "--apply")
        self.assertIn("archiving is skipped", r.stdout)
        self.assertIn("archive: table row format", r.stdout)
        self.assertIn("| A1 |", pend.read_text(encoding="utf-8"), "nothing is moved until the archive table is fixed")
        self.assertIn("a line with only a tail |", arch.read_text(encoding="utf-8"), "the archive table is not rewritten, so the line is not erased")
        self.assertNotIn("Nothing to archive", r.stdout)

    def test_focus_copies_cell_with_escaped_pipe_in_full(self):
        p = self.project("focus-pipe")
        trig = self.trig(p)
        self.add_rows(p / "tracker_proposals.md", HDR_PRO,
                      f"| H1 | supplementary material | `manuscript/results.md` ③ | {trig} | waiting | before `@FIG a.png \\| caption` after, last words |\n")
        r = self.tidy(p, "--focus", "ch2", "--apply")
        listing = (p / "tracker_index.md").read_text(encoding="utf-8")
        focus = listing.split("<!-- focus -->", 1)[1].split("<!-- /focus -->", 1)[0]
        self.assertIn("#### H1 ", focus)
        self.assertIn("before `@FIG a.png | caption` after, last words", focus, "the part after \\| is not cut off and shows as | in the paragraph")
        self.assertNotIn("table row format", r.stdout)
        table = listing.split("<!-- location-table -->", 1)[1].split("<!-- /location-table -->", 1)[0]
        self.assertIn("| `results.md` | ③ | H1 |", table)


# ---------------------------------------------------------------- writing side — replace_once
class ReplaceOnceTests(Fixture):
    def test_blocks_edit_that_splits_a_row_and_passes_escaped_pipe(self):
        p = self.project("replace-blocked")
        trig = self.trig(p)
        pend = p / "tracker_pending.md"
        self.add_rows(pend, HDR_PEND, f"| A1 | open | `manuscript/results.md` ③ | {trig} | waiting | note |\n")
        before = pend.read_bytes()
        with self.assertRaises(ValueError) as cm:
            _sync.replace_once(str(pend), "| waiting | note |", "| waiting | note\ntail |")
        self.assertIn("table rows", str(cm.exception))
        self.assertEqual(before, pend.read_bytes(), "when blocked, the file stays as it is")
        with self.assertRaises(ValueError):
            _sync.replace_once(str(pend), "| waiting | note |", "| waiting | note | one more cell |")      # cell count
        with self.assertRaises(ValueError):
            _sync.replace_once(str(pend), "| waiting | note |", "| waiting | note")                        # trailing pipe
        _sync.replace_once(str(pend), "| waiting | note |", "| waiting | note \\| added |")               # a pipe inside a cell is \\|
        self.assertEqual(_config.table_problems(pend.read_text(encoding="utf-8")), [])
        _sync.replace_once(str(pend), "| waiting | note \\| added |", "| waiting | note\ntail |", check_tables=False)
        self.assertEqual(sorted(c for _n, c, _p in _config.table_problems(pend.read_text(encoding="utf-8"))),
                         ["orphan", "tail"], "a deliberate replacement passes — a row without a trailing pipe + a tail")

    def test_existing_problem_only_warns(self):
        p = self.project("replace-warns")
        trig = self.trig(p)
        pend = p / "tracker_pending.md"
        self.add_rows(pend, HDR_PEND, f"| A1 | open | `manuscript/results.md` ③ | {trig} | waiting | |\na tail that was already there |\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out = _sync.replace_once(str(pend), "| A1 | open |", "| A1 | open (fixed) |")
        self.assertEqual(out["count"], 1)
        self.assertIn("already had", err.getvalue())
        self.assertIn("open (fixed)", pend.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- hook — notice in the same turn after a write
class HookTests(Fixture):
    def test_post_hook_reports_broken_rows_in_tracker_files_only(self):
        p = self.project("hook-notice")
        trig = self.trig(p)
        pend = p / "tracker_pending.md"
        run(PY + [str(p / "tools" / "check_sync.py")], p, codes=(0, 1))          # fingerprint baseline
        good = f"| A1 | open | `manuscript/results.md` ③ | {trig} | waiting | note |\n"
        self.add_rows(pend, HDR_PEND, good + "split tail |\n")
        r = hook("post", self.edit_payload(p, "tracker_pending.md", "e1"), p)
        out = json.loads(r.stdout)
        self.assertIn("Table rows", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("tracker_pending.md", out["systemMessage"])
        self.assertIn("split tail", out["systemMessage"])
        # once fixed, it is quiet
        pend.write_text(pend.read_text(encoding="utf-8").replace("split tail |\n", ""), encoding="utf-8", newline="\n")
        r = hook("post", self.edit_payload(p, "tracker_pending.md", "e2"), p)
        self.assertEqual(r.stdout.strip(), "")
        # shell tool path — finds the tracker file whose fingerprint changed and gives the same notice. PowerShell is treated like Bash
        pend.write_text(pend.read_text(encoding="utf-8").replace(good, good + "split tail again |\n"), encoding="utf-8", newline="\n")
        r = hook("post", {"tool_name": "PowerShell", "tool_input": {"command": "python x.py"}, "cwd": str(p), "tool_use_id": "ps1"}, p)
        self.assertIn("split tail again", json.loads(r.stdout)["systemMessage"])
        r = hook("post", {"tool_name": "PowerShell", "tool_input": {"command": "python x.py"}, "cwd": str(p), "tool_use_id": "ps2"}, p)
        self.assertEqual(r.stdout.strip(), "", "no second notice when the fingerprint is unchanged")
        # a shared file that is not a tracker file (the manuscript) is not checked for tables
        res = p / "manuscript" / "results.md"
        res.write_text("@H1 Results\n\n| a | b |\n|---|---|\n| A1 | x |\nA sentence below the table — left alone in the manuscript.\n", encoding="utf-8")
        r = hook("post", self.edit_payload(p, "manuscript/results.md", "e3"), p)
        self.assertEqual(r.stdout.strip(), "")

    def test_pre_hook_accepts_powershell_without_alerts(self):
        p = self.project("hook-ps")
        r = hook("pre", {"tool_name": "PowerShell", "tool_input": {"command": "Get-Content tracker_pending.md"}, "cwd": str(p), "tool_use_id": "pp1"}, p)
        self.assertEqual(r.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
