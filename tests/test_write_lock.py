"""Write lock · save order of the tidy tool · new open-item number tool · the hook's refusal of hand-registered IDs and its waiting — checked with synthetic fixtures.

These are the devices that let a write go through while other sessions are open (`tracker-workflow.md` "Concurrent edits").
  · The lock is held only while writing — two processes block each other, killing the holder releases it automatically, and the same process may take it again.
  · The tidy tool goes "lock → read → compute → full check → save" — if any file changed after reading, nothing is saved and it tries once more.
  · A new open-item number is assigned by the tool inside the lock — runs started together never get the same number, and an archived number is not reused.
  · The hook refuses only a hand-written row with a new ID (out-of-scope letters, already known IDs and branch numbers pass), and it only waits for the lock without blocking.
  · A save waits out a reader that holds the file open (Windows refuses the replace meanwhile), and a failed save leaves no temporary file.
Fixtures are in the OS temp folder and the state is in a temp folder under `SYNC_STATE_HOME` (the fixture helper of test_sync_guard is used as it is).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_sync_guard import Fixture, PY, TOOLS, HOOK  # noqa: E402  — SYNC_STATE_HOME is set there too

import _config  # noqa: E402
import _sync  # noqa: E402

HOLD_PATH = ("import sys, time; sys.path.insert(0, sys.argv[1]); import _config, _sync as S; "
             "l = S.WriteLock(sys.argv[2], 'holding-session', 5).acquire(); print(l.state, flush=True); time.sleep(120)")
HOLD_PROJECT = ("import sys, time; sys.path.insert(0, sys.argv[1]); import _config, _sync as S; "
                "l = S.Sync(_config.load(sys.argv[2])).write_lock('holding-session', 5).acquire(); print(l.state, flush=True); time.sleep(120)")
TRY_PATH = ("import sys; sys.path.insert(0, sys.argv[1]); import _config, _sync as S; "
            "l = S.WriteLock(sys.argv[2], 'trying', float(sys.argv[3])).acquire(); print(l.state); print(l.who()); l.release()")

# Load the tidy tool inside the project and slip another session's write in between reading and saving (once — first attempt only · always — every attempt).
TIDY_DRIVER = r"""
import io, sys
sys.path.insert(0, 'tools')
import _config
import tidy_tracker as T
mode, n = sys.argv[1], {'run': 0}
orig = T.Tidy.run
def run(self):
    n['run'] += 1
    if mode == 'always' or (mode == 'once' and n['run'] == 1):
        with io.open('tracker_proposals.md', 'a', encoding='utf-8') as f:
            f.write('\na line another session added after reading %d\n' % n['run'])
    return orig(self)
T.Tidy.run = run
sys.argv = ['tidy_tracker.py', '--apply']
rc = T.main()
print('RC=%d RUNS=%d' % (rc, n['run']))
"""


def run(cmd, cwd, codes=(0,), inp=None, wait=None):
    env = dict(os.environ)
    if wait is not None:
        env["SYNC_LOCK_WAIT"] = str(wait)
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", timeout=120, input=inp, env=env)
    assert r.returncode in codes, f"{cmd}\nrc={r.returncode}\n{r.stdout}\n{r.stderr}"
    return r


def hook(payload, cwd, wait=None):
    return run(PY + [str(HOOK), "pre"], cwd, inp=json.dumps(payload), wait=wait)


def holder(script, target):
    p = subprocess.Popen(PY + ["-c", script, str(TOOLS), str(target)], stdout=subprocess.PIPE, text=True, encoding="utf-8")
    assert p.stdout.readline().strip() == "held"
    return p


def stop(p):
    p.kill()
    p.wait()
    p.stdout.close()


def tool(p: Path, name: str):
    return str(p / "tools" / name)


def pending_row(letter, text, state="waiting"):
    return f"| {letter}? | **{text}** | `manuscript/results.md` ③ | now | {state} | {text} — note line of {letter}? |"


def edit(p: Path, rel: str, new: str, tid: str, tool_name="Edit"):
    ti = {"file_path": str(p / rel)}
    if tool_name == "Write":
        ti["content"] = new
    elif tool_name == "MultiEdit":
        ti["edits"] = [{"old_string": "a", "new_string": "b"}, {"old_string": "c", "new_string": new}]
    else:
        ti.update(old_string="a", new_string=new)
    return {"tool_name": tool_name, "tool_input": ti, "cwd": str(p), "tool_use_id": tid}


class SaveWaitsOutAReader(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="replace-retry-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = self.dir / "tracker_pending.md"
        self.path.write_bytes(b"old\n")

    def refuse(self, times):
        """os.replace refused `times` times the way Windows refuses it while a reader holds the file; sleeps are skipped."""
        real, calls = os.replace, []

        def fake(src, dst):
            calls.append(dst)
            if len(calls) <= times:
                raise PermissionError(13, "Access is denied", str(dst))
            return real(src, dst)
        for mod, name, value in ((_sync.os, "replace", fake), (_sync.time, "sleep", lambda s: None)):
            self.addCleanup(setattr, mod, name, getattr(mod, name))
            setattr(mod, name, value)
        return calls

    def leftovers(self):
        return sorted(p.name for p in self.dir.iterdir() if p.name != "tracker_pending.md")

    def test_refused_a_few_times_then_saved(self):
        calls = self.refuse(2)
        _sync._atomic_write(str(self.path), b"new\n")
        self.assertEqual(3, len(calls))
        self.assertEqual(b"new\n", self.path.read_bytes())
        self.assertEqual([], self.leftovers())

    def test_refused_every_time_raises_and_leaves_nothing(self):
        calls = self.refuse(10 ** 6)
        with self.assertRaises(PermissionError):
            _sync._atomic_write(str(self.path), b"new\n")
        self.assertEqual(_sync.REPLACE_TRIES, len(calls))
        self.assertEqual(b"old\n", self.path.read_bytes())
        self.assertEqual([], self.leftovers())

    def test_a_real_reader_holding_the_file(self):
        reader = open(self.path, "rb")                    # on Windows the replace is refused while this is open
        threading.Timer(0.3, reader.close).start()
        _sync._atomic_write(str(self.path), b"new\n")
        reader.close()
        self.assertEqual(b"new\n", self.path.read_bytes())
        self.assertEqual([], self.leftovers())


class LockItself(unittest.TestCase):
    def setUp(self):
        self.path = str(Path(tempfile.mkdtemp(prefix="write-lock-")) / "state" / "write.lock")

    def attempt(self, wait):
        t = time.monotonic()
        r = run(PY + ["-c", TRY_PATH, str(TOOLS), self.path, str(wait)], TOOLS)
        out = r.stdout.split("\n")
        return out[0].strip(), out[1].strip(), time.monotonic() - t

    def test_second_process_is_busy_and_sees_who_holds(self):
        self.assertEqual(self.attempt(0.5)[0], "held")                 # when nobody holds it
        a = holder(HOLD_PATH, self.path)
        try:
            state, who, dt = self.attempt(1)
            self.assertEqual(state, "busy")
            self.assertIn("holding-session", who)
            self.assertGreater(dt, 0.9)
            self.assertEqual(self.attempt(0)[0], "busy")               # wait 0 — decided at once
        finally:
            stop(a)

    def test_killed_holder_leaves_no_lock_behind(self):
        a = holder(HOLD_PATH, self.path)
        b = subprocess.Popen(PY + ["-c", TRY_PATH, str(TOOLS), self.path, "20"], stdout=subprocess.PIPE, text=True, encoding="utf-8")
        time.sleep(0.8)
        stop(a)                                                        # forced kill — the code that would release it does not run
        out = b.communicate(timeout=60)[0]
        self.assertEqual(out.split("\n")[0].strip(), "held")           # the waiting side takes over
        self.assertEqual(self.attempt(0.5)[0], "held")

    def test_same_process_may_take_it_twice(self):
        outer = _sync.WriteLock(self.path, "outer", 1).acquire()
        inner = _sync.WriteLock(self.path, "inner", 1).acquire()
        self.assertTrue(outer.held and inner.held)
        inner.release()
        self.assertEqual(self.attempt(0.3)[0], "busy")                 # releasing the inner one still leaves it locked from the outer one
        outer.release()
        self.assertEqual(self.attempt(0.3)[0], "held")

    def test_broken_lock_folder_does_not_block(self):
        blocker = Path(self.path).parent.parent / "a-file"
        blocker.write_text("x", encoding="utf-8")
        lock = _sync.WriteLock(str(blocker / "sub" / "write.lock"), "y", 0.2).acquire()
        self.assertEqual(lock.state, "off")                            # does not block — proceeds without a lock
        self.assertFalse(lock.busy)
        lock.release()


class TidySaves(Fixture):
    @staticmethod
    def closed_row(p: Path, rid: str):
        pend = p / "tracker_pending.md"
        lines = pend.read_text(encoding="utf-8").split("\n")
        idx = next(i for i, l in enumerate(lines) if l.startswith("## A"))
        hdr = next(i for i in range(idx, len(lines)) if lines[i].startswith("|---"))
        lines.insert(hdr + 1, f"| {rid} | **finished item** | `manuscript/results.md` ③ | now | done (2026-11-01) | a row to archive — a note long enough |")
        pend.write_text("\n".join(lines), encoding="utf-8")

    def test_apply_refuses_while_locked_but_diagnosis_still_runs(self):
        p = self.project("tidy-locked")
        self.closed_row(p, "A7")
        before = (p / "tracker_pending.md").read_bytes()
        a = holder(HOLD_PROJECT, p)
        try:
            r = run(PY + [tool(p, "tidy_tracker.py"), "--apply"], p, codes=(4,), wait=0.4)
            self.assertIn("holding-session", r.stdout)
            self.assertIn("Run again.", r.stdout)
            self.assertEqual((p / "tracker_pending.md").read_bytes(), before)
            run(PY + [tool(p, "tidy_tracker.py")], p, codes=(0, 1), wait=0.4)      # a diagnosis needs no lock
        finally:
            stop(a)
        run(PY + [tool(p, "tidy_tracker.py"), "--apply"], p, codes=(0, 1))
        self.assertNotIn("| A7 |", (p / "tracker_pending.md").read_text(encoding="utf-8"))
        self.assertIn("| A7 |", (p / "records" / "archive.md").read_text(encoding="utf-8"))

    def test_changed_after_reading_once_means_read_again_then_save(self):
        p = self.project("tidy-retry")
        self.closed_row(p, "A7")
        r = run(PY + ["-c", TIDY_DRIVER, "once"], p)
        self.assertIn("reading everything again without saving", r.stdout)
        self.assertIn("RUNS=2", r.stdout)
        self.assertNotIn("RC=4", r.stdout)
        self.assertNotIn("| A7 |", (p / "tracker_pending.md").read_text(encoding="utf-8"))
        self.assertIn("| A7 |", (p / "records" / "archive.md").read_text(encoding="utf-8"))
        self.assertIn("added after reading 1", (p / "tracker_proposals.md").read_text(encoding="utf-8"))     # the other session's line stays

    def test_changed_after_both_reads_saves_nothing_at_all(self):
        p = self.project("tidy-gives-up")
        self.closed_row(p, "A7")
        pend, rec, idx = (p / "tracker_pending.md").read_bytes(), (p / "records" / "archive.md").read_bytes(), (p / "tracker_index.md").read_bytes()
        r = run(PY + ["-c", TIDY_DRIVER, "always"], p)
        self.assertIn("RC=4 RUNS=2", r.stdout)
        self.assertIn("Not saved", r.stdout)
        self.assertEqual((p / "tracker_pending.md").read_bytes(), pend)        # saving only part would leave A7 in neither file
        self.assertEqual((p / "records" / "archive.md").read_bytes(), rec)
        self.assertEqual((p / "tracker_index.md").read_bytes(), idx)
        run(PY + [tool(p, "tidy_tracker.py"), "--apply"], p, codes=(0, 1))                 # running again works
        self.assertIn("| A7 |", (p / "records" / "archive.md").read_text(encoding="utf-8"))


class NewPendingId(Fixture):
    def register(self, p: Path, row: str, codes=(0,), wait=None, name="row.md"):
        f = self.scratch / (p.name + "_" + name)
        f.write_text(row + "\n", encoding="utf-8")
        return run(PY + [tool(p, "new_pending.py"), str(f)], p, codes=codes, wait=wait)

    def test_next_number_goes_past_existing_and_archived_ids(self):
        p = self.project("numbers")
        r = self.register(p, pending_row("A", "first item"))
        self.assertEqual(r.stdout.strip(), "A1\ttracker_pending.md")
        text = (p / "tracker_pending.md").read_text(encoding="utf-8")
        self.assertIn("| A1 | **first item** |", text)
        self.assertIn("note line of A1 |", text)                             # the `A?` inside the row gets the same number
        self.add_row(p, "A5", "an old item added by hand")
        self.assertEqual(self.register(p, pending_row("A", "next")).stdout.split("\t")[0], "A6")
        # even after A6 is closed and archived, its number is not reused
        pend = p / "tracker_pending.md"
        pend.write_text(pend.read_text(encoding="utf-8").replace("| now | waiting | next", "| now | done (2026-11-01) | next"), encoding="utf-8")
        run(PY + [tool(p, "tidy_tracker.py"), "--apply"], p, codes=(0, 1))
        self.assertNotIn("| A6 |", pend.read_text(encoding="utf-8"))
        self.assertEqual(self.register(p, pending_row("A", "after archiving")).stdout.split("\t")[0], "A7")
        lines = pend.read_text(encoding="utf-8").split("\n")
        a = next(i for i, l in enumerate(lines) if l.startswith("| A7 |"))
        self.assertTrue(lines[a - 1].startswith("| A"), lines[a - 1])          # at the bottom of the table, before the archive-list block
        self.assertEqual(_config.table_problems("\n".join(lines)), [])
        run(PY + [tool(p, "tidy_tracker.py"), "--apply"], p, codes=(0,))       # the tidy tool reads it as it is

    def test_proposals_and_other_letters_in_a_dissertation_project(self):
        p = self.project("dissertation", kind="dissertation")
        hdr = next(l for l in (p / "tracker_proposals.md").read_text(encoding="utf-8").split("\n") if l.startswith("| ID |"))
        names = _config.split_cells(hdr)
        cells = ["H?"] + ["proposal text — a cell long enough"] * (len(names) - 1)
        trig = next((j for j, c in enumerate(names) if _config.column_key(c) == "trigger"), None)
        if trig is not None:
            cells[trig] = "now"
        r = self.register(p, "| " + " | ".join(cells) + " |")
        self.assertEqual(r.stdout.strip(), "H1\ttracker_proposals.md")
        self.assertIn("| H1 |", (p / "tracker_proposals.md").read_text(encoding="utf-8"))
        self.assertEqual(self.register(p, pending_row("D", "style")).stdout.strip(), "D1\ttracker_pending.md")
        self.assertEqual(self.register(p, pending_row("D", "style two")).stdout.split("\t")[0], "D2")
        self.assertEqual(self.register(p, pending_row("B", "follow-up")).stdout.split("\t")[0], "B1")

    def test_bad_rows_and_letters_outside_the_scope_change_nothing(self):
        p = self.project("refusals")
        before = {f: (p / f).read_bytes() for f in ("tracker_pending.md", "tracker_proposals.md", "tracker_literature.md")}
        self.assertIn("outside the scope this tool numbers", self.register(p, pending_row("F", "literature"), codes=(2,)).stderr)
        self.assertIn("outside the scope this tool numbers", self.register(p, pending_row("Z", "unknown letter"), codes=(2,)).stderr)
        self.assertIn("Cell count differs", self.register(p, "| A? | a row short of cells | now |", codes=(1,)).stderr)
        self.assertIn("<letter>?", self.register(p, pending_row("A", "number by hand").replace("| A? |", "| A9 |", 1), codes=(1,)).stderr)
        self.assertIn("must be one line", self.register(p, pending_row("A", "one") + "\n" + pending_row("A", "two"), codes=(1,)).stderr)
        r = self.register(p, pending_row("A", "unknown trigger").replace("| now |", "| someday |"))
        self.assertIn("trigger value", r.stderr)                                       # only a warning — the row is registered
        before["tracker_pending.md"] = None
        for f, b in before.items():
            if b is not None:
                self.assertEqual((p / f).read_bytes(), b, f)

    def test_rows_spaced_by_blank_lines_and_crlf_files(self):
        p = self.project("spaced-rows")
        pend = p / "tracker_pending.md"
        self.add_row(p, "C3", "one")
        self.add_row(p, "C8", "two")                                            # add_row puts rows in section A, so they are moved to section C and spaced with blank lines
        lines = [l for l in pend.read_text(encoding="utf-8").split("\n") if not l.startswith(("| C3 |", "| C8 |"))]
        c = next(i for i, l in enumerate(lines) if l.startswith("## C"))
        sep = next(i for i in range(c, len(lines)) if lines[i].startswith("|---"))
        row = "| {0} | **older item** | `manuscript/results.md` ③ | now | waiting | {0} note — a line long enough |"
        lines[sep + 1:sep + 1] = ["", row.format("C3"), "", row.format("C8"), ""]
        pend.write_bytes("\r\n".join(lines).encode("utf-8"))                   # a CRLF file
        run(PY + [tool(p, "check_sync.py"), "--accept-warn"], p, codes=(0, 1, 2))
        r = self.register(p, pending_row("C", "new item"))
        self.assertEqual(r.stdout.split("\t")[0], "C9")
        raw = pend.read_bytes()
        self.assertEqual(raw.count(b"\r\n"), raw.count(b"\n"))                 # line endings preserved
        out = raw.decode("utf-8").split("\r\n")
        i = next(k for k, l in enumerate(out) if l.startswith("| C9 |"))
        self.assertTrue(out[i - 1].startswith("| C8 |"))                       # right below the last row
        self.assertLess(i, next(k for k, l in enumerate(out) if l.startswith("<!-- archived-list:C")))

    def test_runs_started_together_get_distinct_numbers(self):
        p = self.project("together")
        procs = []
        for k in range(6):
            f = self.scratch / f"together_{k}.md"
            f.write_text(pending_row("B", f"concurrent item {k}") + "\n", encoding="utf-8")
            procs.append(subprocess.Popen(PY + [tool(p, "new_pending.py"), str(f)], cwd=str(p), stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True, encoding="utf-8"))
        outs = [q.communicate(timeout=120) for q in procs]
        self.assertEqual([q.returncode for q in procs], [0] * 6, outs)
        ids = sorted(o[0].split("\t")[0] for o in outs)
        self.assertEqual(ids, ["B%d" % n for n in range(1, 7)])                # no duplicate numbers
        text = (p / "tracker_pending.md").read_text(encoding="utf-8")
        self.assertEqual(sum(1 for l in text.split("\n") if l.startswith("| B")), 6)
        self.assertEqual(_config.table_problems(text), [])
        for k in range(6):
            self.assertIn(f"concurrent item {k}", text)

    def test_busy_lock_means_no_number(self):
        p = self.project("number-locked")
        before = (p / "tracker_pending.md").read_bytes()
        a = holder(HOLD_PROJECT, p)
        try:
            r = self.register(p, pending_row("A", "not added"), codes=(4,), wait=0.4)
            self.assertEqual(r.stdout.strip(), "")
            self.assertIn("Run again.", r.stderr)
            self.assertEqual((p / "tracker_pending.md").read_bytes(), before)
        finally:
            stop(a)
        self.assertEqual(self.register(p, pending_row("A", "added")).stdout.split("\t")[0], "A1")


class HookNewIdsAndWait(Fixture):
    ROW = "| {0} | **added by hand** | `manuscript/results.md` ③ | now | waiting | a row added by hand — a note long enough |"

    def test_new_id_by_hand_is_denied_for_edit_write_and_multiedit(self):
        p = self.project("hand-added")
        self.add_row(p, "A1", "an existing item")
        whole = (p / "tracker_pending.md").read_text(encoding="utf-8")
        for n, (name, new) in enumerate([("Edit", "line before\n" + self.ROW.format("A9")), ("Write", whole + "\n" + self.ROW.format("A9")),
                                         ("MultiEdit", self.ROW.format("A9")), ("Edit", self.ROW.format("A9-1"))]):
            out = hook(edit(p, "tracker_pending.md", new, f"deny-{n}", name), p).stdout
            self.assertIn("deny", out, name)
            msg = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
            self.assertIn("new_pending.py", msg)
            self.assertIn("A?", msg)
        hrow = "| H4 | proposal | `manuscript/results.md` | waiting | basis |"
        self.assertIn("deny", hook(edit(p, "tracker_proposals.md", hrow, "deny-h"), p).stdout)

    def test_known_ids_branches_and_other_tables_pass(self):
        p = self.project("passes")
        self.add_row(p, "A1", "an existing item")
        ok = [("tracker_pending.md", self.ROW.format("A1")),                      # edits an existing row
              ("tracker_pending.md", self.ROW.format("A1-1")),                    # a branch number — the stem exists
              ("tracker_pending.md", "| P006 | file name | content |"),                  # a letter outside the scope
              ("tracker_pending.md", "Only the note changes — the text A9 in a sentence is not a row"),
              ("tracker_literature.md", "| F7 | literature item | `x` | waiting | note |"),     # a file outside the scope
              ("records/archive.md", self.ROW.format("A9"))]                   # the archive table is written by the tidy tool
        for n, (rel, new) in enumerate(ok):
            self.assertEqual(hook(edit(p, rel, new, f"pass-{n}"), p).stdout.strip(), "", (rel, new))
        # restoring a deleted row — an ID this computer has seen, so not a new ID
        pend = p / "tracker_pending.md"
        run(PY + [tool(p, "check_sync.py"), "--quick"], p, codes=(0, 1, 2))
        _sync.Sync(_config.load(str(p))).remember_ids()
        pend.write_text("\n".join(l for l in pend.read_text(encoding="utf-8").split("\n") if not l.startswith("| A1 |")), encoding="utf-8")
        sync = _sync.Sync(_config.load(str(p)))
        self.assertEqual(sync.hand_added_ids("tracker_pending.md", self.ROW.format("A1")), [])
        self.assertEqual(sync.hand_added_ids("tracker_pending.md", self.ROW.format("A2") + "\n" + self.ROW.format("B3")), ["A2", "B3"])

    def test_project_without_the_tool_is_not_denied(self):
        p = self.project("no-tool")
        os.remove(tool(p, "new_pending.py"))                                    # a project whose tool copies were not updated — blocking would leave no way to add a row
        self.assertEqual(hook(edit(p, "tracker_pending.md", self.ROW.format("A9"), "no-tool"), p).stdout.strip(), "")

    def test_edit_waits_for_the_lock_and_is_never_blocked_by_it(self):
        p = self.project("hook-waits")
        a = holder(HOLD_PROJECT, p)
        try:
            t = time.monotonic()
            h = hook(edit(p, "tracker_pending.md", "one note line", "wait-1"), p, wait=0.6)
            self.assertGreater(time.monotonic() - t, 0.5)                       # it waited for the lock to be released
            self.assertEqual(h.stdout.strip(), "")                             # and still did not block
            self.assertIn("the write lock was not released", h.stderr)
        finally:
            stop(a)
        h = hook(edit(p, "tracker_pending.md", "one note line", "wait-2"), p, wait=0.6)
        self.assertEqual(h.stdout.strip(), "")
        self.assertNotIn("the write lock was not released", h.stderr)


class OtherWriters(Fixture):
    def test_replace_once_inside_a_held_lock_and_when_another_holds_it(self):
        p = self.project("replace-locked")
        self.add_row(p, "A1", "replace target")
        pend = p / "tracker_pending.md"
        sync = _sync.Sync(_config.load(str(p)))
        with sync.write_lock("test") as lock:                                   # the same process takes it again — they do not wait for each other
            self.assertTrue(lock.held)
            _sync.replace_once(str(pend), "**replace target**", "**replaced once**")
        self.assertIn("**replaced once**", pend.read_text(encoding="utf-8"))
        a = holder(HOLD_PROJECT, p)
        os.environ["SYNC_LOCK_WAIT"] = "0.3"
        try:
            _sync.replace_once(str(pend), "**replaced once**", "**replaced twice**")       # the replacement is made even if the lock cannot be taken — the single-match check backs it up
        finally:
            del os.environ["SYNC_LOCK_WAIT"]
            stop(a)
        self.assertIn("**replaced twice**", pend.read_text(encoding="utf-8"))

    def test_index_tool_refuses_when_busy_but_a_new_record_is_still_made(self):
        p = self.project("index-locked")
        body = p / "body_new.md"
        body.write_text("# E? — a record made while locked\n\n**Completed** 2026-11-01\n**Target** `manuscript/results.md` ③\n**Status** confirmed\n\n"
                        "Body sentence — a line long enough.\n", encoding="utf-8")
        a = holder(HOLD_PROJECT, p)
        try:
            run(PY + [tool(p, "index_records.py")], p, codes=(4,), wait=0.3)
            r = run(PY + [tool(p, "new_record.py"), str(body)], p, wait=0.3)   # the numbering tool does not take the lock
            self.assertEqual(r.stdout.strip(), "E4\trecords/E4.md")
            self.assertIn("could not regenerate the index", r.stderr)
        finally:
            stop(a)
        run(PY + [tool(p, "index_records.py")], p)
        self.assertIn("| E4 |", (p / "tracker_records_index.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
