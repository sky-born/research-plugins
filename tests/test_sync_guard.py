"""Sync guard (_sync.py · check_sync.py · guard_write.py pre/post · update_tools S10) — checked with synthetic fixtures.

Fixtures are built in the OS temp folder and the per-computer state also goes to a temp folder (`SYNC_STATE_HOME`). No research files are touched.
Scenarios: gaps (S2) · references (S3) · stamps (S4) · conflict copies (S5) · loss report (S6) · monotonic IDs (S7) · freshness (S1) ·
guard · confirmation · restore · single replacement · Bash fingerprint · update_tools refusal · retention pruning.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "research-writing"
SKILL = PLUGIN / "skills" / "new-manuscript"
TOOLS = SKILL / "tools"
HOOK = SKILL / "hooks" / "guard_write.py"
INITIALIZER = SKILL / "init_manuscript.py"
UPDATE = SKILL / "update_tools.py"
PY = [sys.executable, "-X", "utf8", "-B"]

# setdefault — test_write_lock and test_project_names import this module a second time (as `test_sync_guard`); overwriting the variable
# then would point the tools at another folder than the STATE the tests read, and one process running several suites shares one folder.
os.environ.setdefault("SYNC_STATE_HOME", tempfile.mkdtemp(prefix="sync-guard-state-"))
STATE = Path(os.environ["SYNC_STATE_HOME"])

sys.path.insert(0, str(TOOLS))
import _config  # noqa: E402
import _sync  # noqa: E402


def run(cmd, cwd, codes=(0,), inp=None):
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", timeout=120, input=inp)
    assert r.returncode in codes, f"{cmd}\nrc={r.returncode}\n{r.stdout}\n{r.stderr}"
    return r


def hook(mode, payload, cwd):
    return run(PY + [str(HOOK), mode], cwd, inp=json.dumps(payload))


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = Path(tempfile.mkdtemp(prefix="sync-guard-"))

    def project(self, name: str, records=3, with_checkpoint=True, kind="journal") -> Path:
        p = self.scratch / name
        run(PY + [str(INITIALIZER), str(p), "--name", "Sync sample " + name, "--kind", kind,
                  "--source-dir", "manuscript", "--chapters", "intro.md", "results.md", "--references", "references.md"],
            self.scratch)
        if with_checkpoint:
            (p / "notes").mkdir(exist_ok=True)
            (p / "notes" / "CHECKPOINT.md").write_text("# Handover\n\nUpdated 2026-10-01\n", encoding="utf-8")
            cfg = json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8"))
            cfg["tracker"]["checkpoint"] = "notes/CHECKPOINT.md"
            (p / ".manuscript" / "project.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for i in range(1, records + 1):
            body = p / f"body{i}.md"
            body.write_text(f"# E? — sample record {i}\n\n**Completed** 2026-10-01\n**Target** `manuscript/results.md` ③\n**Status** confirmed\n\n"
                            f"Body sentence {i} — a line long enough for the survival check.\n", encoding="utf-8")
            run(PY + [str(p / "tools" / "new_record.py"), str(body)], p)
        run(PY + [str(p / "tools" / "tidy_tracker.py"), "--apply"], p, codes=(0, 1))
        run(PY + [str(p / "tools" / "index_records.py")], p)
        return p

    @staticmethod
    def check(p: Path, *args, codes=(0, 1, 2)):
        return run(PY + [str(p / "tools" / "check_sync.py"), *args], p, codes=codes)

    @staticmethod
    def add_row(p: Path, rid: str, text: str):
        pend = p / "tracker_pending.md"
        lines = pend.read_text(encoding="utf-8").split("\n")
        idx = next(i for i, l in enumerate(lines) if l.startswith("## A"))
        hdr = next(i for i in range(idx, len(lines)) if lines[i].startswith("|---"))
        lines.insert(hdr + 1, f"| {rid} | **{text}** | `manuscript/results.md` ③ | now | waiting | {text} — a note line, long enough |")
        pend.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def edit_payload(p: Path, rel: str, tid: str):
        return {"tool_name": "Edit", "tool_input": {"file_path": str(p / rel), "old_string": "a", "new_string": "b"},
                "cwd": str(p), "tool_use_id": tid}


# ---------------------------------------------------------------- healthy project · stamps · idempotence
class HealthyProject(Fixture):
    def test_stamp_hashes_the_file_as_left_on_disk(self):
        """A pending file with two trailing blank lines (hand edit; the tidy tool does not save it) is still stamped with the hash of the bytes on disk — no false S4 WARN."""
        p = self.project("trailing-blank")
        pend = p / "tracker_pending.md"
        self.add_row(p, "A1", "to do now")                                   # a reason for the list to be rebuilt
        pend.write_bytes(pend.read_bytes() + b"\n")                           # two trailing blank lines — a change the tidy tool does not save, not a dirty file
        before = pend.read_bytes()
        run(PY + [str(p / "tools" / "tidy_tracker.py"), "--apply"], p, codes=(0, 1))
        self.assertEqual(pend.read_bytes(), before, "if the tidy tool rewrites the pending file, the premise of this test no longer holds")
        self.assertTrue(before.endswith(b"\n\n"))
        idx = (p / "tracker_index.md").read_text(encoding="utf-8").split("\n")[1]
        stamped = idx.split("tracker_pending.md=", 1)[1][:16]
        self.assertEqual(stamped, _sync.norm_sha(before)[:16], "the stamp must be the hash of the version on disk")
        r = self.check(p, codes=(0,))
        self.assertIn("Sync OK", r.stdout)
        self.assertNotIn("S4", r.stdout)

    def test_fresh_project_is_ok_and_generated_files_carry_stamps(self):
        p = self.project("healthy")
        r = self.check(p, "-v", codes=(0,))
        self.assertIn("Sync OK", r.stdout)
        self.assertIn("E3", r.stdout.split("\n")[0])
        idx = (p / "tracker_index.md").read_text(encoding="utf-8").split("\n")
        rec = (p / "tracker_records_index.md").read_text(encoding="utf-8").split("\n")
        self.assertTrue(idx[1].startswith("<!-- generated-stamp ") and " tracker_pending.md=" in idx[1], idx[:3])
        self.assertTrue(rec[1].startswith("<!-- generated-stamp records/ n=3 max=3 sha="), rec[:3])
        # snapshots — one per shared file in the drive folder, naming convention, the same hash is not made again
        snaps = sorted(os.listdir(p / "archive" / "tracker_backup"))
        self.assertTrue(snaps and all(_sync.SNAP_RE.match(s) for s in snaps), snaps[:3])
        n = len(snaps)
        self.check(p, codes=(0,))
        self.assertEqual(len(os.listdir(p / "archive" / "tracker_backup")), n)
        # tidy tool twice — tracker files unchanged (the stamp is deterministic)
        before = {f: digest(p / f) for f in ("tracker_index.md", "tracker_pending.md", "tracker_records_index.md")}
        run(PY + [str(p / "tools" / "tidy_tracker.py"), "--apply"], p, codes=(0, 1))
        after = {f: digest(p / f) for f in before}
        self.assertEqual(before, after)

    def test_defaults_only_project_runs_core_checks(self):
        # a project in the old format, with no sync or checkpoint in its settings, runs on the defaults alone
        p = self.project("defaults-only", with_checkpoint=False)
        cfg = _config.load(str(p))
        self.assertIsNone(cfg.checkpoint)
        s = _sync.Sync(cfg)
        self.assertEqual(s.opt("stale_days", 2), 2)
        self.assertEqual([f.level for f in s.check("start") if f.level == "ERROR"], [])
        self.assertIn("tracker_pending.md", s.shared_files())
        self.assertIn("manuscript/results.md", s.shared_files())


# ---------------------------------------------------------------- stale side — catching up · stale
class StaleMirror(Fixture):
    def test_record_gap_is_error_and_blocks_tools_and_hook(self):
        p = self.project("gap")
        (p / "records" / "E2.md").rename(self.scratch / "gap_E2.bak")
        r = self.check(p, "--quick", codes=(2,))
        self.assertIn("ERROR S2", r.stdout)
        self.assertIn("ERROR S3", r.stdout)            # the index points at an E2 that does not exist
        self.assertIn("E2", r.stdout)
        # hook — blocks an Edit of a shared file (JSON deny), does not block a file that is not shared
        h = hook("pre", self.edit_payload(p, "tracker_pending.md", "t1"), p)
        self.assertIn('"permissionDecision": "deny"', h.stdout)
        h2 = hook("pre", self.edit_payload(p, "body1.md", "t2"), p)
        self.assertEqual(h2.stdout.strip(), "")
        # batch tools — refused (3)
        run(PY + [str(p / "tools" / "tidy_tracker.py"), "--apply"], p, codes=(3,))
        run(PY + [str(p / "tools" / "index_records.py")], p, codes=(3,))
        run(PY + [str(p / "tools" / "new_record.py"), str(p / "body1.md")], p, codes=(3,))
        # diagnosis only (no write) passes
        run(PY + [str(p / "tools" / "tidy_tracker.py")], p, codes=(0, 1))
        # once it is back: healthy, the hook passes
        (self.scratch / "gap_E2.bak").rename(p / "records" / "E2.md")
        self.check(p, "--quick", codes=(0,))
        h3 = hook("pre", self.edit_payload(p, "tracker_pending.md", "t3"), p)
        self.assertEqual(h3.stdout.strip(), "")

    def test_truncated_top_is_error_and_new_record_refuses_reuse(self):
        p = self.project("truncated")
        (p / "records" / "E3.md").rename(self.scratch / "truncated_E3.bak")
        (p / "tracker_records_index.md").write_text("# Index\n", encoding="utf-8")     # the index looks like an old version too
        r = self.check(p, "--quick", codes=(2,))
        self.assertIn("S2:max", r.stdout) if "S2:max" in r.stdout else self.assertIn("is behind", r.stdout)
        # a new item does not take E3 again
        r2 = run(PY + [str(p / "tools" / "new_record.py"), str(p / "body1.md")], p, codes=(2, 3))
        self.assertFalse((p / "records" / "E3.md").exists())
        (self.scratch / "truncated_E3.bak").rename(p / "records" / "E3.md")

    def test_known_gaps_are_not_errors(self):
        p = self.project("known-gaps", records=1)
        # skip E2 and keep only E3 — a number that was always missing in an old project
        (p / "records" / "E3.md").write_text((p / "records" / "E1.md").read_text(encoding="utf-8").replace("E1", "E3"), encoding="utf-8")
        r = self.check(p, "--quick")
        self.assertIn("ERROR S2", r.stdout)
        cfg_p = p / ".manuscript" / "project.json"
        cfg = json.loads(cfg_p.read_text(encoding="utf-8"))
        cfg["sync"] = {"known_gaps": [2]}
        cfg_p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.check(p, "--ack", "test: old missing number", codes=(0,))
        r = self.check(p, "--quick")
        self.assertNotIn("ERROR S2", r.stdout)

    def test_stale_days_warns(self):
        p = self.project("stale")
        s = _sync.Sync(_config.load(str(p)))
        old = time.time() - 3 * 86400
        for rel in s.shared_files():
            os.utime(p / rel, (old, old))
        r = self.check(p, "--quick", codes=(1,))
        self.assertIn("WARN  S1", r.stdout)
        self.assertIn("days ago", r.stdout)
        self.assertIn("--accept-warn", r.stdout)                  # the guidance is proceed · accept — not a request for confirmation
        self.assertNotIn("get their confirmation", r.stdout)
        self.assertNotIn("get a confirmation", r.stdout)
        # S10 — a WARN (S1) alone does not refuse a tool update (only an ERROR does)
        r = run(PY + [str(UPDATE), str(p), "--apply"], p, codes=(0, 1))
        self.assertNotIn("applying is refused", r.stdout)
        self.assertIn("Only WARNs, so proceeding", r.stdout)

    def test_update_tools_refuses_apply_on_stale_or_broken_mirror(self):
        p = self.project("update-refused")
        (p / "records" / "E2.md").rename(self.scratch / "update-refused_E2.bak")
        (p / "tools" / "_config.py").write_text("# imitation of an old version\n", encoding="utf-8")   # locally modified copy — a target for --force
        r = run(PY + [str(UPDATE), str(p), "--apply", "--force", "tools/_config.py"], p, codes=(1,))
        self.assertIn("applying is refused", r.stdout)
        self.assertEqual((p / "tools" / "_config.py").read_text(encoding="utf-8"), "# imitation of an old version\n")
        r = run(PY + [str(UPDATE), str(p), "--apply", "--force", "tools/_config.py", "--sync-override"], p, codes=(0, 1))
        self.assertIn("replaced", r.stdout)
        (self.scratch / "update-refused_E2.bak").rename(p / "records" / "E2.md")

    def test_conflict_copies_warn_but_pycache_is_excluded(self):
        p = self.project("conflicts")
        (p / "tools" / "__pycache__").mkdir(exist_ok=True)
        (p / "tools" / "__pycache__" / "x.cpython-313.pyc").write_bytes(b"")
        (p / "tools" / "__pycache__" / "x.cpython-313 2.pyc").write_bytes(b"")
        r = self.check(p, "--quick", codes=(0,))
        self.assertNotIn("S5", r.stdout)
        (p / "tracker_pending 2.md").write_bytes((p / "tracker_pending.md").read_bytes())
        (p / "manuscript" / "intro (1).md").write_text("x", encoding="utf-8")
        (p / "manuscript" / "Figure 2.md").write_text("x", encoding="utf-8")       # there is no original `Figure.md`, so this is not a conflict copy
        r = self.check(p, "--quick", codes=(1,))
        self.assertIn("S5", r.stdout)
        self.assertIn("tracker_pending 2.md(identical bytes)", r.stdout)
        self.assertIn("intro (1).md", r.stdout)
        self.assertNotIn("Figure 2.md", r.stdout)


# ---------------------------------------------------------------- victim side — exact list of losses · restore · confirmation
class VictimSide(Fixture):
    def test_lost_ids_error_then_restore_then_ack(self):
        p = self.project("lost-ids")
        pend = p / "tracker_pending.md"
        base = pend.read_bytes()
        self.add_row(p, "A1", "sample item one")
        self.add_row(p, "A2", "sample item two")
        self.check(p, "--after-write", "tracker_pending.md", codes=(0,))
        self.check(p, "--quick", codes=(0, 1))                 # registers the IDs (an S4 WARN is normal — the list was not regenerated)
        pend.write_bytes(base)                                   # as if another computer overwrote it with an old version
        r = self.check(p, "--quick", codes=(2,))
        self.assertIn("ERROR S7", r.stdout)
        self.assertIn("A1 A2", r.stdout)
        # every write leaves a local snapshot, so it can be restored without the drive web UI
        r = self.check(p, "--snapshots", "tracker_pending.md", codes=(0,))
        self.assertIn("local", r.stdout)
        self.check(p, "--restore", "tracker_pending.md", codes=(0,))
        self.assertIn("| A2 |", pend.read_text(encoding="utf-8"))
        r = self.check(p, "--quick", codes=(0, 1))
        self.assertNotIn("S7", r.stdout)
        # a legitimate deletion is closed by the user's confirmation
        pend.write_bytes(base)
        self.check(p, "--quick", codes=(2,))
        r = self.check(p, "--ack", "user: I deleted A1 and A2", codes=(0,))
        self.assertIn("ERRORs closed: 1", r.stdout)
        self.check(p, "--quick", codes=(0, 1))
        log = json.loads(next(STATE.glob("*lost-ids*/ack_log.json")).read_text(encoding="utf-8"))
        self.assertEqual(log[-1]["text"], "user: I deleted A1 and A2")

    def test_lost_lines_report_only_counts_my_lines(self):
        p = self.project("loss-report")
        res = p / "manuscript" / "results.md"
        res.write_text("@H1 Results\n\n" + "\n".join(f"Sentence {i} written by this computer — a line long enough." for i in range(10)) + "\n", encoding="utf-8")
        hook("pre", self.edit_payload(p, "manuscript/results.md", "w1"), p)
        hook("post", self.edit_payload(p, "manuscript/results.md", "w2"), p)
        # a legitimate large revision by another session — my lines stay and many lines are added → no warning
        with res.open("a", encoding="utf-8") as f:
            f.write("\n".join(f"Sentence {i} added by another computer — a line long enough." for i in range(40)) + "\n")
        r = self.check(p, "--quick", codes=(0, 1))
        self.assertNotIn("S6", r.stdout)
        # overwritten by an old version — my lines vanish → WARN · --damage shows the vanished lines
        res.write_text("@H1 Results\n\nOnly one sentence of the old version — a line long enough.\n", encoding="utf-8")
        r = self.check(p, "--quick", codes=(1, 2))
        self.assertIn("WARN  S6", r.stdout)
        self.assertIn("results.md", r.stdout)
        r = self.check(p, "--damage", codes=(1,))
        self.assertIn("Sentence 0 written by this computer", r.stdout)
        # a document that is rewritten wholesale (checkpoint) is excluded from the loss report
        cp = p / "notes" / "CHECKPOINT.md"
        cp.write_text("# Handover\n\n" + "\n".join(f"State line {i} — a line long enough." for i in range(10)) + "\n", encoding="utf-8")
        hook("post", self.edit_payload(p, "notes/CHECKPOINT.md", "w3"), p)
        cp.write_text("# Handover\n\nRewritten wholesale — a line long enough.\n", encoding="utf-8")
        r = self.check(p, "--damage", codes=(0, 1))
        self.assertNotIn("CHECKPOINT", r.stdout)

    def test_warn_only_is_accepted_without_asking_and_error_still_needs_ack(self):
        p = self.project("warn-accept")
        res = p / "manuscript" / "results.md"
        res.write_text("@H1 Results\n\n" + "\n".join(f"Sentence {i} written by this computer — a line long enough." for i in range(10)) + "\n", encoding="utf-8")
        hook("pre", self.edit_payload(p, "manuscript/results.md", "w1"), p)
        hook("post", self.edit_payload(p, "manuscript/results.md", "w2"), p)
        res.write_text("@H1 Results\n\nOnly one sentence of the old version — a line long enough.\n", encoding="utf-8")
        r = self.check(p, "--quick", codes=(1,))                      # WARNs only — rc 1, the guidance is accept · proceed
        self.assertIn("WARN  S6", r.stdout)
        self.assertIn("--accept-warn", r.stdout)
        self.assertNotIn("get their confirmation", r.stdout)
        self.assertNotIn("get a confirmation", r.stdout)
        r = self.check(p, "--accept-warn", codes=(0,))
        self.assertIn("WARN accepted", r.stdout)
        r = self.check(p, "--quick", codes=(0, 1))
        self.assertNotIn("S6", r.stdout)                              # the baseline is the current state — the same condition does not trigger again
        # with an open ERROR, --accept-warn is refused — the only way to close an ERROR is --ack
        (p / "records" / "E2.md").rename(self.scratch / "warn-accept_E2.bak")
        self.check(p, "--quick", codes=(2,))
        r = self.check(p, "--accept-warn", codes=(2,))
        self.assertIn("refused", r.stdout)
        self.assertIn("S2", r.stdout)
        self.assertTrue(hook("pre", self.edit_payload(p, "manuscript/results.md", "w3"), p), "an ERROR still blocks")
        (self.scratch / "warn-accept_E2.bak").rename(p / "records" / "E2.md")

    def test_bash_post_hook_registers_changed_shared_files_only(self):
        p = self.project("bash-print")
        self.check(p, codes=(0,))                                 # fingerprint baseline
        (p / "manuscript" / "intro.md").write_text("@H1 Intro\n\nA sentence written through Bash — a line long enough.\n", encoding="utf-8")
        (p / "notes" / "memo.md").write_text("a file that is not shared\n", encoding="utf-8")
        hook("post", {"tool_name": "Bash", "tool_input": {"command": "python x.py"}, "cwd": str(p), "tool_use_id": "b1"}, p)
        written = json.loads(next(STATE.glob("*bash-print*/written.json")).read_text(encoding="utf-8"))
        self.assertIn("manuscript/intro.md", written)
        self.assertNotIn("notes/memo.md", written)
        snaps = [s for s in os.listdir(next(STATE.glob("*bash-print*")) / "snap") if "manuscript__intro" in s]
        self.assertGreaterEqual(len(snaps), 2)

    def test_bash_pre_hook_blocks_only_with_open_error_and_shared_path(self):
        p = self.project("bash-block")
        (p / "records" / "E2.md").rename(self.scratch / "bash-block_E2.bak")
        self.check(p, "--quick", codes=(2,))
        h = hook("pre", {"tool_name": "Bash", "tool_input": {"command": "python tools/x.py tracker_pending.md"}, "cwd": str(p), "tool_use_id": "c1"}, p)
        self.assertIn("deny", h.stdout)
        h = hook("pre", {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(p), "tool_use_id": "c2"}, p)
        self.assertEqual(h.stdout.strip(), "")
        (self.scratch / "bash-block_E2.bak").rename(p / "records" / "E2.md")

    def test_hook_dedupes_same_tool_use_and_ignores_other_folders(self):
        p = self.project("dedupe")
        (p / "records" / "E2.md").rename(self.scratch / "dedupe_E2.bak")
        payload = self.edit_payload(p, "tracker_pending.md", "same-id")
        self.assertIn("deny", hook("pre", payload, p).stdout)
        self.assertEqual(hook("pre", payload, p).stdout.strip(), "")        # the second one (another hook registration) does nothing
        outside = self.scratch / "outside"
        outside.mkdir(exist_ok=True)
        (outside / "x.md").write_text("x", encoding="utf-8")
        h = hook("pre", {"tool_name": "Edit", "tool_input": {"file_path": str(outside / "x.md")}, "cwd": str(outside), "tool_use_id": "o1"}, outside)
        self.assertEqual(h.stdout.strip(), "")
        (self.scratch / "dedupe_E2.bak").rename(p / "records" / "E2.md")

    def test_legacy_overwrite_denial_still_works(self):
        p = self.project("overwrite")
        payload = {"tool_name": "Write", "tool_input": {"file_path": str(p / "records" / "E1.md"), "content": "x"}, "cwd": str(p), "tool_use_id": "l1"}
        self.assertIn("deny", hook("pre", payload, p).stdout)
        payload = {"tool_name": "Write", "tool_input": {"file_path": str(p / "records" / "E99.md"), "content": "x"}, "cwd": str(p), "tool_use_id": "l2"}
        self.assertEqual(hook("pre", payload, p).stdout.strip(), "")


# ---------------------------------------------------------------- helpers · snapshot retention · hook registration file
class Helpers(Fixture):
    def test_replace_once_preserves_crlf_and_requires_single_match(self):
        p = self.project("replace")
        f = p / "manuscript" / "results.md"
        f.write_bytes("@H1 Results\r\n\r\nFirst paragraph.\r\nSecond paragraph.\r\n".encode("utf-8"))
        out = _sync.replace_once(str(f), "First paragraph.", "First paragraph, revised.\nA new line.")
        self.assertTrue(out["crlf"])
        b = f.read_bytes()
        self.assertEqual(b.count(b"\r\n"), 5)
        self.assertEqual(b.count(b"\n"), b.count(b"\r\n"))
        with self.assertRaises(ValueError):
            _sync.replace_once(str(f), "paragraph", "x")                 # twice
        with self.assertRaises(ValueError):
            _sync.replace_once(str(f), "a phrase that is not there", "x")             # zero times
        lf = p / "manuscript" / "intro.md"
        lf.write_bytes(b"a\nb\n")                                   # write_text turns LF into CRLF on Windows
        _sync.replace_once(str(lf), "a\n", "a\nc\n")
        self.assertEqual(lf.read_bytes(), b"a\nc\nb\n")
        snaps = _sync.Sync(_config.load(str(p))).snapshots_of("manuscript/results.md")
        self.assertGreaterEqual(len(snaps), 2)                      # before and after the replacement

    def test_prune_by_age_count_and_other_computers(self):
        p = self.project("retention")
        s = _sync.Sync(_config.load(str(p)))
        drive = Path(s.snapshot_dir)
        now = datetime.datetime.now(datetime.timezone.utc)

        def fake(stem, comp, n, when):
            (drive / s._snap_name(stem, comp, "%08x" % n, when)).write_bytes(b"x")

        # (1) age — 14 of its own from 45 days ago: the latest 10 stay, the rest are deleted
        for i in range(14):
            fake("tracker_pending.md", s.me, i, now - datetime.timedelta(days=45, minutes=-i))
        # (2) count — 30 of its own from yesterday (within 30 days): the oldest 10 beyond the cap of 20 are deleted
        for i in range(30):
            fake("manuscript/results.md", s.me, 100 + i, now - datetime.timedelta(days=1, minutes=-i))
        # (3) another computer — the one from 45 days ago stays (under 90 days), the one from 120 days ago is deleted
        fake("tracker_pending.md", "OTHER-PC", 0xdead, now - datetime.timedelta(days=45))
        fake("tracker_pending.md", "OTHER-PC", 0xbeef, now - datetime.timedelta(days=120))
        self.check(p, codes=(0,))                                   # retention pruning also runs at session start
        names = os.listdir(drive)
        mine_pend = [n for n in names if "_tracker_pending_" in n and ("_%s_" % s.me) in n]
        mine_res = [n for n in names if "_manuscript__results_" in n and ("_%s_" % s.me) in n]
        others = [n for n in names if "OTHER-PC" in n]
        self.assertEqual(len(mine_pend), 10, mine_pend)              # of the 1 real version + 14 fakes, only the latest 10 stay
        self.assertLessEqual(len(mine_res), 20 + 1)
        self.assertGreaterEqual(len(mine_res), 20)
        self.assertEqual(len(others), 1)
        self.assertIn("0000dead", others[0])

    def test_nfc_finder_imports_nfd_named_module(self):
        # a Korean module whose file name is NFD, as on a Mac drive mirror — the finder registered by `_config` accepts it (NTFS keeps the code points as they are)
        import importlib
        import unicodedata
        d = self.scratch / "nfd모듈"
        d.mkdir(exist_ok=True)
        nfd_name = unicodedata.normalize("NFD", "한글표본모듈")
        (d / (nfd_name + ".py")).write_text("VALUE = 42\n", encoding="utf-8")
        self.assertNotEqual(nfd_name, "한글표본모듈")
        sys.path.insert(0, str(d))
        try:
            mod = importlib.import_module("한글표본모듈")
            self.assertEqual(mod.VALUE, 42)
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("한글표본모듈", None)

    def test_nfd_named_shared_file_is_matched_as_nfc(self):
        import unicodedata
        p = self.project("nfd-file")
        nfd = unicodedata.normalize("NFD", "노트_결과")          # a Korean file name on purpose — stored in NFD as on a macOS drive mirror
        (p / "manuscript" / (nfd + ".md")).write_text("Manuscript note with an NFD name — a line long enough.\n", encoding="utf-8")
        s = _sync.Sync(_config.load(str(p)))
        self.assertIn("manuscript/노트_결과.md", s.shared_files())
        self.assertTrue(s.is_shared("manuscript/노트_결과.md"))
        self.assertTrue(s.is_shared("manuscript/" + nfd + ".md"))
        # NTFS is sensitive to normalization — reading by the NFC name must still reach the actual (NFD) file
        self.assertIn("Manuscript note with an NFD name", s.read("manuscript/노트_결과.md").decode("utf-8"))
        made1 = s.snapshot("manuscript/노트_결과.md", drive=True)
        made2 = s.snapshot("manuscript/" + nfd + ".md", drive=True)
        self.assertTrue(made1)
        self.assertEqual(made2, [])                                  # same file · same hash — not made again
        self.assertEqual(len(s.snapshots_of("manuscript/" + nfd + ".md")), len(s.snapshots_of("manuscript/노트_결과.md")))

    def test_plugin_hooks_json_is_valid_and_points_to_existing_script(self):
        data = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        for ev in ("PreToolUse", "PostToolUse"):
            self.assertIn(ev, data["hooks"])
            entry = data["hooks"][ev][0]
            self.assertEqual(entry["matcher"], "Edit|Write|Bash|PowerShell")
            cmd = entry["hooks"][0]["command"]
            self.assertIn('"${CLAUDE_PLUGIN_ROOT}/skills/new-manuscript/hooks/guard_write.py"', cmd)
            self.assertTrue(cmd.rstrip().endswith("pre" if ev == "PreToolUse" else "post"))
        self.assertTrue(HOOK.is_file())
        example = json.loads((SKILL / "hooks" / "settings.example.json").read_text(encoding="utf-8"))
        self.assertEqual(set(example["hooks"]), {"PreToolUse", "PostToolUse"})

    def test_project_root_is_found_from_file_path_upwards(self):
        p = self.project("root-search")
        deep = p / "notes" / "deep" / "folder"
        deep.mkdir(parents=True, exist_ok=True)
        self.assertEqual(_sync.find_project_root(str(deep)), str(p))
        self.assertEqual(_sync.find_project_root(str(p / "tracker_pending.md")), str(p))
        self.assertIsNone(_sync.find_project_root(str(self.scratch)))


# ---------------------------------------------------------------- S4 — tell the direction when the stamps differ
class StampDirection(Fixture):
    def test_source_edited_after_tidy_is_todo_not_a_sync_warning(self):
        p = self.project("forward")
        time.sleep(0.2)
        self.add_row(p, "A9", "edited after tidy")                      # without the hook — a version that is not in this computer's snapshots
        r = self.check(p, "--quick", codes=(0,))
        self.assertIn("Sync OK", r.stdout)
        self.assertIn("to do", r.stdout)
        self.assertIn("Not a sync problem", r.stdout)
        self.assertNotIn("Check that the drive is up to date", r.stdout)
        r = self.check(p, "--quick", "-v", codes=(0,))
        self.assertIn("INFO  S4", r.stdout)
        # a version registered by the hook (with a snapshot) is also forward — the edit time is attached
        self.check(p, "--after-write", "tracker_pending.md", codes=(0,))
        r = self.check(p, "--quick", codes=(0,))
        self.assertIn("to do", r.stdout)
        self.assertIn("edited", r.stdout)
        run(PY + [str(p / "tools" / "tidy_tracker.py"), "--apply"], p, codes=(0, 1))
        r = self.check(p, "--quick", "-v", codes=(0,))
        self.assertNotIn("S4", r.stdout)

    def test_source_back_to_older_known_version_is_regress_or_revert(self):
        p = self.project("regress")
        pend = p / "tracker_pending.md"
        self.add_row(p, "A9", "first version")
        run(PY + [str(p / "tools" / "tidy_tracker.py"), "--apply"], p, codes=(0, 1))   # v1 · stamp v1 · IDs registered
        v1 = pend.read_bytes()
        pend.write_bytes(v1.replace("first version — a note".encode("utf-8"), "second version — a note".encode("utf-8")))
        self.check(p, "--after-write", "tracker_pending.md", codes=(0,))                # v2 snapshot (what the hook does)
        time.sleep(1.1)                                                              # so the seconds in the snapshot names do not collide
        run(PY + [str(p / "tools" / "tidy_tracker.py"), "--apply"], p, codes=(0, 1))   # stamp = v2
        idx_m = os.path.getmtime(p / "tracker_index.md")
        pend.write_bytes(v1)                                                         # goes back to the old version
        os.utime(pend, (idx_m - 100, idx_m - 100))                                   # the modification time is also earlier than the generated file — an overwrite
        r = self.check(p, "--quick", codes=(2,))
        self.assertIn("ERROR S4", r.stdout)
        self.assertIn("went back to the old version", r.stdout)
        now = time.time()
        os.utime(pend, (now, now))                                                   # the modification time is later — it may have been reverted
        r = self.check(p, "--quick", codes=(1,))
        self.assertIn("WARN  S4", r.stdout)
        self.assertIn("reverted", r.stdout)

    def test_unknown_source_version_without_later_edit_is_suspect(self):
        p = self.project("unknown-src")
        pend = p / "tracker_pending.md"
        idx_m = os.path.getmtime(p / "tracker_index.md")
        self.add_row(p, "A9", "an edit from another computer")                 # a version that is not in this computer's snapshots
        os.utime(pend, (idx_m - 100, idx_m - 100))                  # yet it looks as if it was written before the generated file
        r = self.check(p, "--quick", codes=(1,))
        self.assertIn("WARN  S4", r.stdout)
        self.assertIn("overwrote", r.stdout)
        self.assertIn("--accept-warn", r.stdout)                  # a WARN is reported · accepted — not a request for confirmation

    def test_new_record_refreshes_index_and_added_records_are_todo(self):
        p = self.project("record-add", records=2)
        body = p / "body_new.md"
        body.write_text("# E? — new record\n\n**Completed** 2026-10-03\n**Target** `manuscript/results.md` ④\n**Status** confirmed\n\n"
                        "Body sentence — a line long enough for the survival check.\n", encoding="utf-8")
        r = run(PY + [str(p / "tools" / "new_record.py"), str(body)], p)
        self.assertEqual(r.stdout.strip().split("\t"), ["E3", "records/E3.md"])     # standard output is the number line only
        self.assertIn("regenerated", r.stderr)                            # the index is rebuilt too — the notice goes to standard error
        rec = (p / "tracker_records_index.md").read_text(encoding="utf-8").split("\n")
        self.assertTrue(rec[1].startswith("<!-- generated-stamp records/ n=3 max=3 sha="), rec[:3])
        r = self.check(p, "--quick", "-v", codes=(0,))
        self.assertNotIn("S4", r.stdout)
        # --no-index — the index stays as it is, the check reports "to do" (not a sync warning)
        r = run(PY + [str(p / "tools" / "new_record.py"), str(body), "--no-index"], p)
        self.assertEqual(r.stdout.strip().split("\t"), ["E4", "records/E4.md"])
        self.assertNotIn("regenerated", r.stderr)
        r = self.check(p, "--quick", codes=(0,))
        self.assertIn("Sync OK", r.stdout)
        self.assertIn("to do", r.stdout)
        self.assertIn("E4", r.stdout)
        # WARN when the content of a record that existed when the index was made changes
        e1 = p / "records" / "E1.md"
        e1.write_text(e1.read_text(encoding="utf-8") + "\nAn added line — a confirmed record was edited.\n", encoding="utf-8")
        r = self.check(p, "--quick", codes=(1,))
        self.assertIn("WARN  S4", r.stdout)
        self.assertIn("have changed", r.stdout)


# ---------------------------------------------------------------- baseline of written lines — the version this computer saw just before writing
class PreVersion(Fixture):
    LINES = ["Reference %d — a line long enough for the survival check %s" % (i, "·" * i) for i in range(1, 11)]

    def _foreign_later_snapshot(self, p: Path, rel: str, content: str):
        """An old version snapshotted by another computer at a later time — placed in the drive snapshot folder."""
        data = content.encode("utf-8")
        later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=30)
        name = _sync.Sync._snap_name(rel, "OTHER-PC", hashlib.sha256(data).hexdigest(), later)
        (p / "archive" / "tracker_backup" / name).write_bytes(data)
        return name

    def test_removed_lines_are_unregistered_even_if_a_foreign_old_snapshot_is_later(self):
        p = self.project("pre-version")
        rel = "manuscript/intro.md"
        f = p / "manuscript" / "intro.md"
        f.write_text("# Intro\n\n" + "\n".join(self.LINES) + "\n", encoding="utf-8")       # v1 — 10 lines
        self.check(p, "--after-write", rel, codes=(0,))                                      # 10 lines registered · v1 snapshot
        s = _sync.Sync(_config.load(str(p)))
        self.assertEqual(len(s._load("written.json", {}).get(rel, {})), 10)
        self._foreign_later_snapshot(p, rel, "# Intro\n\nA line of the old version — none of this computer's lines.\n")
        # this computer writes v1 → v2 (6 lines deleted) — the same order as the hook and replace_once
        s.before_write(rel)
        f.write_text("# Intro\n\n" + "\n".join(self.LINES[:4]) + "\n", encoding="utf-8")
        s.after_write(rel)
        mine = s._load("written.json", {}).get(rel, {})
        self.assertEqual(len(mine), 4, mine)                                                 # the 6 deleted lines leave the registry
        r = self.check(p, "--quick", codes=(0,))
        self.assertNotIn("S6", r.stdout)
        # Bash path (no before_write) — the baseline is the "last seen version" recorded at the session boundary
        self._foreign_later_snapshot(p, rel, "# Intro\n\nAnother old version — again none of this computer's lines.\n")
        f.write_text("# Intro\n\n" + "\n".join(self.LINES[:2]) + "\n", encoding="utf-8")
        self.check(p, "--after-bash", codes=(0,))
        s = _sync.Sync(_config.load(str(p)))
        self.assertEqual(len(s._load("written.json", {}).get(rel, {})), 2)
        r = self.check(p, "--quick", codes=(0,))
        self.assertNotIn("S6", r.stdout)

    def test_unknown_previous_version_falls_back_to_my_own_snapshots_only(self):
        p = self.project("pre-unknown")
        rel = "manuscript/results.md"
        f = p / "manuscript" / "results.md"
        f.write_text("# Res\n\n" + "\n".join(self.LINES) + "\n", encoding="utf-8")        # the title is under 8 characters — not counted as a "written line"
        self.check(p, "--after-write", rel, codes=(0,))
        s = _sync.Sync(_config.load(str(p)))
        seen = s._load("seen.json", {})
        seen.pop(rel, None)
        s._save("seen.json", seen)                                                           # the previous version is unknown
        self._foreign_later_snapshot(p, rel, "# Res\n\nOld version — another computer · a later time.\n")
        f.write_text("# Res\n\n" + "\n".join(self.LINES[:3]) + "\n", encoding="utf-8")
        s2 = _sync.Sync(_config.load(str(p)))
        s2.after_write(rel)
        self.assertEqual(len(s2._load("written.json", {}).get(rel, {})), 3)                  # this computer's v1 snapshot is the baseline


# ---------------------------------------------------------------- ID positions in the list (S3) · persistence of a confirmation (ack)
class ListIdsAndAck(Fixture):
    """Labels of other documents inside the copied note of the focus block must not be read as open-item IDs. Otherwise they are read as IDs,
    and even after an ack the re-check just before writing blocks the same key again, which also stops the tidy tool that would rebuild the list."""
    LABELS = "decisions of the revision plan D4 · D6 · another project journal_paper A40 · dissertation H21"

    def _labelled(self, name, kind="journal"):
        p = self.project(name, kind=kind)
        base = (p / "tracker_pending.md").read_bytes()
        self.add_row(p, "A1", self.LABELS)          # labels of other documents in the item and note — carried into the location table, now, and focus
        run(PY + [str(p / "tools" / "tidy_tracker.py"), "--focus", "ch2", "--apply"], p, codes=(0, 1))
        return p, base

    @staticmethod
    def _s3(out):
        return [l for l in out.splitlines() if " S3 " in l]

    def tidy(self, p, codes):
        return run(PY + [str(p / "tools" / "tidy_tracker.py"), "--apply"], p, codes=codes)

    def test_labels_in_copied_notes_are_not_pending_ids(self):
        for kind in ("journal", "dissertation"):
            with self.subTest(kind=kind):
                p, base = self._labelled("labels-" + kind, kind)
                listing = (p / "tracker_index.md").read_text(encoding="utf-8")
                focus = listing.split("<!-- focus -->", 1)[1].split("<!-- /focus -->", 1)[0]
                self.assertIn("#### A1 — ", focus)
                self.assertIn("A40", focus)                                   # the labels are still in the copied note
                ids, unknown = _config.list_block_ids(listing)               # reads the shape the tidy tool wrote (round trip)
                self.assertEqual(unknown, [])
                self.assertEqual((ids["locations"], ids["now"], ids["focus"], ids["triggers"]), (["A1"], ["A1"], ["A1"], []))
                r = self.check(p, "--quick", codes=(0, 1))
                self.assertEqual(self._s3(r.stdout), [])
                self.assertEqual(hook("pre", self.edit_payload(p, "tracker_pending.md", "lab-" + kind), p).stdout.strip(), "")
                # a real dangling reference in an ID position is still an ERROR — labels are not mixed in
                (p / "tracker_pending.md").write_bytes(base)
                r = self.check(p, "--quick", codes=(2,))
                s3 = self._s3(r.stdout)
                self.assertEqual(len(s3), 1, r.stdout)
                self.assertIn("ERROR S3", s3[0])
                self.assertTrue(s3[0].rstrip().endswith("— A1"), s3[0])

    def test_ack_lets_tidy_rebuild_the_list_that_still_shows_the_condition(self):
        p = self.project("deadlock")
        self.add_row(p, "A2", "remaining item")                                     # also checks that the remaining row is carried into the rebuilt list (the zero case is the test below)
        keep = (p / "tracker_pending.md").read_bytes()
        self.add_row(p, "A1", self.LABELS)
        run(PY + [str(p / "tools" / "tidy_tracker.py"), "--focus", "ch2", "--apply"], p, codes=(0, 1))
        self.check(p, "--quick", codes=(0, 1))                                # registers A1
        (p / "tracker_pending.md").write_bytes(keep)                             # the user deletes the A1 row — the list still points at A1
        r = self.check(p, "--quick", codes=(2,))
        self.assertTrue(any(l.rstrip().endswith("— A1") for l in self._s3(r.stdout)), r.stdout)
        self.tidy(p, codes=(3,))                                              # before the confirmation — refused
        self.check(p, "--ack", "test: I deleted A1", codes=(0,))
        r = self.tidy(p, codes=(0, 1))                                        # after the confirmation — runs even though the list still shows the same condition (no deadlock)
        self.assertNotIn("Sync check ERROR", r.stdout)
        self.assertNotIn("ERROR left", r.stdout)
        ids, _ = _config.list_block_ids((p / "tracker_index.md").read_text(encoding="utf-8"))
        self.assertEqual((ids["locations"], ids["now"], ids["focus"]), (["A2"], ["A2"], ["A2"]))   # the tidy tool rebuilt the list, so the condition is gone
        r = self.check(p, "--quick", codes=(0, 1))
        self.assertNotIn("ERROR", r.stdout)

    def test_removing_the_last_open_row_empties_the_list_after_ack(self):
        """When the user deletes the last open row, the list points at a vanished ID and gives an S3 ERROR — after the confirmation the tidy tool rebuilds the blocks empty and the condition is gone.
        Journal: the last row of the pending file. Dissertation: the last row of an old proposals table without a status column (it cannot be closed by status, so the row is deleted)."""
        old_pro = "| ID | Proposal | Location | Basis |\n|---|---|---|---|\n"
        for kind, rid in (("journal", "A1"), ("dissertation", "H1")):
            with self.subTest(kind=kind):
                p = self.project("last-row-" + kind, kind=kind)
                pend, pro = p / "tracker_pending.md", p / "tracker_proposals.md"
                if rid == "H1":
                    text = pro.read_text(encoding="utf-8")
                    pro.write_text(text.split("| ID |", 1)[0] + old_pro, encoding="utf-8")
                    base = pro.read_bytes()
                    pro.write_text(base.decode("utf-8") + "| H1 | proposal to delete | `manuscript/results.md` ③ | basis — a note line long enough |\n",
                                   encoding="utf-8")
                else:
                    base = pend.read_bytes()
                    self.add_row(p, "A1", "item to delete")
                run(PY + [str(p / "tools" / "tidy_tracker.py"), "--focus", "ch2", "--apply"], p, codes=(0, 1))
                ids, _ = _config.list_block_ids((p / "tracker_index.md").read_text(encoding="utf-8"))
                self.assertEqual((ids["locations"], ids["focus"]), ([rid], [rid]))
                self.check(p, "--quick", codes=(0, 1))                        # registers
                (pro if rid == "H1" else pend).write_bytes(base)             # the user deletes the last row — zero open items
                r = self.check(p, "--quick", codes=(2,))
                self.assertTrue(any(l.rstrip().endswith("— " + rid) for l in self._s3(r.stdout)), r.stdout)
                self.tidy(p, codes=(3,))                                      # before the confirmation — refused
                self.check(p, "--ack", "test: I deleted the last row", codes=(0,))
                r = self.tidy(p, codes=(0, 1))
                self.assertNotIn("No open items could be read", r.stdout)
                self.assertIn("Zero open items", r.stdout)
                listing = (p / "tracker_index.md").read_text(encoding="utf-8")
                ids, unknown = _config.list_block_ids(listing)
                self.assertEqual((sum(map(len, ids.values())), unknown), (0, []))
                self.assertIn("> No open items", listing.split("<!-- now -->", 1)[1].split("<!-- /now -->", 1)[0])
                r = self.check(p, "--quick", codes=(0, 1))
                self.assertEqual(self._s3(r.stdout), [])
                self.assertNotIn("ERROR", r.stdout)

    def test_ack_holds_for_the_same_key_within_ack_hours_only(self):
        p = self.project("ack-hold")
        e2, e3 = self.scratch / "ack-hold_E2.bak", self.scratch / "ack-hold_E3.bak"
        (p / "records" / "E2.md").rename(e2)
        self.check(p, "--quick", codes=(2,))
        self.assertIn('"permissionDecision": "deny"', hook("pre", self.edit_payload(p, "tracker_pending.md", "k1"), p).stdout)
        self.check(p, "--ack", "test: confirmed that E2 is catching up", codes=(0,))
        # the same condition (gap E2) is not blocked within ack_hours — the check shows it as "confirmed" and rc is 1
        r = self.check(p, "--quick", codes=(1,))
        self.assertIn("ERROR (confirmed)", r.stdout)
        self.assertIn("[confirmed", r.stdout)
        self.assertEqual(hook("pre", self.edit_payload(p, "tracker_pending.md", "k2"), p).stdout.strip(), "")
        r = self.tidy(p, codes=(0, 1))
        self.assertNotIn("ERROR left", r.stdout)
        # when the condition changes (a new key), it blocks again
        (p / "records" / "E3.md").rename(e3)
        self.assertIn('"permissionDecision": "deny"', hook("pre", self.edit_payload(p, "tracker_pending.md", "k3"), p).stdout)
        self.tidy(p, codes=(3,))
        e3.rename(p / "records" / "E3.md")
        self.check(p, "--quick", codes=(1,))                                  # only the gap E2 again — a confirmed key
        self.assertEqual(hook("pre", self.edit_payload(p, "tracker_pending.md", "k4"), p).stdout.strip(), "")
        # after ack_hours, it blocks again
        alerts = next(STATE.glob("*ack-hold*/alerts.json"))
        a = json.loads(alerts.read_text(encoding="utf-8"))
        old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=10)).strftime("%Y%m%dT%H%M%SZ")
        for v in a["acked"].values():
            v["utc"] = old
        alerts.write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
        self.assertIn('"permissionDecision": "deny"', hook("pre", self.edit_payload(p, "tracker_pending.md", "k5"), p).stdout)
        self.check(p, "--quick", codes=(2,))
        e2.rename(p / "records" / "E2.md")

    def test_unknown_list_shape_warns_instead_of_guessing(self):
        p, _ = self._labelled("unknown-shape")
        listing = p / "tracker_index.md"
        listing.write_text(listing.read_text(encoding="utf-8").replace("#### A1 — ", "### A1 — "), encoding="utf-8")   # old · hand-edited shape
        r = self.check(p, "--quick", codes=(1,))
        s3 = self._s3(r.stdout)
        self.assertEqual(len(s3), 1, r.stdout)
        self.assertIn("WARN  S3", s3[0])
        self.assertIn("(focus)", s3[0])
        self.assertIn("could not read the ID positions", s3[0])


# ---------------------------------------------------------------- state folder id — independent of NFC/NFD in the root path
class StateFolderId(Fixture):
    """The hook builds Sync from the NFC path on standard input, and a tool run in a shell builds it from the NFD path of the file system. The id must not split the state folder in two,
    or a user `--ack` would not clear the hook's warning. The id is the hash of the NFC root, and a folder from the old definition is collected when first met."""

    @staticmethod
    def _cfg(root):
        return _config.Config(root, _config._merge(_config.DEFAULTS, {"project": "normalization sample"}))

    def test_project_id_hashes_the_nfc_root(self):
        import unicodedata
        p = self.project("정규화")                  # a Korean folder name on purpose — its NFC and NFD spellings differ
        nfc_root, nfd_root = unicodedata.normalize("NFC", str(p)), unicodedata.normalize("NFD", str(p))
        self.assertNotEqual(nfc_root, nfd_root)
        self.assertEqual(_sync.project_id("normalization sample", nfc_root), _sync.project_id("normalization sample", nfd_root))
        self.assertEqual(_sync.Sync(self._cfg(nfc_root)).state, _sync.Sync(self._cfg(nfd_root)).state)
        # the old definition (no normalization) gave a different name for an NFD root — that is the only candidate to collect, the same whichever form the root has
        legacy = _sync.project_id("normalization sample", nfd_root, form=None)
        self.assertNotEqual(legacy, _sync.project_id("normalization sample", nfd_root))
        self.assertEqual(_sync.legacy_project_ids("normalization sample", nfc_root), [legacy])
        self.assertEqual(_sync.legacy_project_ids("normalization sample", nfd_root), [legacy])
        self.assertEqual(_sync.legacy_project_ids("ascii", os.path.abspath(os.sep + "ascii-only")), [])

    def test_name_slug_is_unchanged_for_syllables_and_ascii(self):
        # Since the Hangul class comes from _textio it also holds stand-alone jamo. Names made of syllables, ASCII and other
        # characters must keep the slug the earlier hand-written range gave, so their state folders stay where they are.
        import re
        import unicodedata
        old = lambda s: re.sub(r'[^0-9A-Za-z가-힣_-]+', '-', unicodedata.normalize('NFC', s)).strip('-')[:24] or 'project'   # noqa: E731
        for name in ("Manuscript", "Paper_draft (rev 1)", "한글 원고 2026", unicodedata.normalize("NFD", "가나다 문헌"), "—", "x·y"):
            self.assertEqual(old(name), _sync._slug(name), name)
        self.assertEqual("가나-ㄱ", _sync._slug("가나 ㄱ"))     # a stand-alone jamo now stays; it became "-" before

    def test_legacy_state_folder_is_renamed_or_merged(self):
        import shutil
        import unicodedata
        p = self.project("옛폴더")                  # a Korean folder name on purpose — the old (unnormalized) id of its NFD root differs
        cfg = _config.load(str(p))
        s = _sync.Sync(cfg)
        legacy = STATE / _sync.project_id(cfg.name, unicodedata.normalize("NFD", s.root), form=None)
        self.assertNotEqual(str(legacy), s.state)
        # (1) without a new folder, only the old folder is renamed
        shutil.rmtree(s.state)
        legacy.mkdir()
        (legacy / "alerts.json").write_text(json.dumps({"findings": [], "acked": {"S2:9": {"utc": _sync.utc_stamp(), "text": "old"}}}), encoding="utf-8")
        (legacy / "snap").mkdir()
        (legacy / "snap" / "old.bin").write_bytes(b"x")
        s = _sync.Sync(cfg)
        self.assertFalse(legacy.exists())
        self.assertEqual(Path(s.state, "snap", "old.bin").read_bytes(), b"x")
        self.assertIn("S2:9", s._alerts()["acked"])
        # (2) with both, they are merged — written lines · IDs · confirmation records as a union, the seen maximum number the larger one, snapshots only those that are missing, the old folder deleted
        s._save("written.json", {"a.md": {"h1": ["20260101T000000Z", "new"]}})
        s._save("ids.json", {"A1": "20260102T000000Z"})
        s._save("records_max.json", {"max": 3, "utc": "20260101T000000Z"})
        legacy.mkdir()
        (legacy / "written.json").write_text(json.dumps({"a.md": {"h2": ["20260101T000000Z", "old"]}, "b.md": {"h3": ["20260101T000000Z", "old"]}}),
                                             encoding="utf-8")
        (legacy / "ids.json").write_text(json.dumps({"A1": "20260101T000000Z", "A2": "20260103T000000Z"}), encoding="utf-8")
        (legacy / "records_max.json").write_text(json.dumps({"max": 7, "utc": "20260102T000000Z"}), encoding="utf-8")
        (legacy / "alerts.json").write_text(json.dumps({"findings": [{"level": "ERROR", "code": "S2", "key": "S2:7", "msg": "m", "items": []}],
                                                        "acked": {"S2:7": {"utc": _sync.utc_stamp(), "text": "old2"}}}), encoding="utf-8")
        (legacy / "snap").mkdir()
        (legacy / "snap" / "old.bin").write_bytes(b"y")          # the same name — the new one is kept
        (legacy / "snap" / "old2.bin").write_bytes(b"z")
        s = _sync.Sync(cfg)
        self.assertFalse(legacy.exists())
        self.assertEqual(Path(s.state, "snap", "old.bin").read_bytes(), b"x")
        self.assertEqual(Path(s.state, "snap", "old2.bin").read_bytes(), b"z")
        reg = s._load("written.json", {})
        self.assertEqual(set(reg["a.md"]), {"h1", "h2"})
        self.assertIn("b.md", reg)
        ids = s._load("ids.json", {})
        self.assertEqual(ids["A1"], "20260101T000000Z")           # the first-seen time is the earlier one
        self.assertIn("A2", ids)
        self.assertEqual(s.max_record_seen(), 7)
        acked = s._alerts()["acked"]
        self.assertIn("S2:9", acked)
        self.assertIn("S2:7", acked)
        self.assertEqual(_sync.Sync(cfg).state, s.state)        # quiet when made again (no old folder)

    def test_windows_path_sample_keeps_its_old_id(self):
        # Windows path sample — imitates the definition with ntpath. Windows folder names are NFC, so the id equals the old definition (the state folder is not moved),
        # and drive-letter case · separators · NFD spelling all collapse to the same id (normcase → NFC).
        import ntpath
        import unicodedata
        saved = _sync.os.path
        _sync.os.path = ntpath
        try:
            # Korean folder names on purpose — NFC and NFD spellings of the path must give one id
            win = "G:\\다른 컴퓨터\\작업 컴퓨터\\연구\\원고\\Journal_Paper_revision\\revision_1"
            cur = _sync.project_id("sample", win)
            self.assertEqual(cur, _sync.project_id("sample", win, form=None))                  # the same as the old definition — no migration
            self.assertEqual(_sync.legacy_project_ids("sample", win), [_sync.project_id("sample", unicodedata.normalize("NFD", win), form=None)])
            self.assertEqual(cur, _sync.project_id("sample", unicodedata.normalize("NFD", win)))
            self.assertEqual(cur, _sync.project_id("sample", win.lower().replace("\\", "/")))
        finally:
            _sync.os.path = saved

    def test_cli_ack_from_nfd_root_unblocks_hook_with_nfc_path(self):
        import unicodedata
        p = self.project("확인경로")                # a Korean folder name on purpose — the test needs distinct NFC and NFD roots
        nfc_root, nfd_root = unicodedata.normalize("NFC", str(p)), unicodedata.normalize("NFD", str(p))
        if not os.path.isdir(nfd_root):
            self.skipTest("this file system does not treat an NFD path as the same folder (NTFS · ext4) — only reproducible on APFS · HFS+")
        (p / "records" / "E2.md").rename(self.scratch / "확인경로_E2.bak")
        self.assertIn('"permissionDecision": "deny"', hook("pre", self.edit_payload(Path(nfc_root), "tracker_pending.md", "n1"), p).stdout)
        # an --ack run in a shell from the NFD root must close the hook's warning (NFC path) — the same state folder
        run(PY + [str(p / "tools" / "check_sync.py"), "--dir", nfd_root, "--ack", "test: confirmed from the NFD root"], Path(nfd_root), codes=(0,))
        self.assertEqual(hook("pre", self.edit_payload(Path(nfc_root), "tracker_pending.md", "n2"), p).stdout.strip(), "")
        folders = [d.name for d in STATE.iterdir() if d.name.startswith(_sync._slug("Sync sample 확인경로") + "-")]
        self.assertEqual(len(folders), 1, folders)
        (self.scratch / "확인경로_E2.bak").rename(p / "records" / "E2.md")


if __name__ == "__main__":
    unittest.main()
