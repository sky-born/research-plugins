"""Format tokens — projects write English anchors; the pre-0.14 Korean spellings are read, refused for writing, and migrated.

Covered, for journal and dissertation projects:
  · an old-format project (anchors, record fields, trigger and status values in the pre-0.14 Korean spellings) — diagnosis runs,
    the writing tools refuse with exit 5, `update_tools.py` previews (exit 1), `--apply` migrates and rebuilds, a second run changes
    nothing; records stay byte-identical, an unknown column name is kept and reported, the focus and the `now` rows survive;
  · a mixed project (a Korean stamp line inserted into an English index, as an old tidy tool does) — refused, S9 ERROR, migrated back;
  · the archive join between an English pending table and a Korean archive table (and the reverse), through the tidy tool's own code;
  · the status vocabulary of both spellings, the grammar baseline's old keys and packet format, and the generated skeleton.
Old-format data on purpose: the old project is made by converting the anchors of a fresh English project back with the pairs in
`_config.py` (`BLOCKS`, `STAMP_WORDS`, `COLUMNS`, `FIELDS`, `FOCUS_LABEL`, `DEFAULT_TRIGGERS`, `STATES`), so no Korean token is written here.
Fixtures live in the OS temp folder and the per-computer sync state in a temp `SYNC_STATE_HOME`; no research files are touched.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "research-writing" / "skills" / "new-manuscript"
WORKFLOW = ROOT / "plugins" / "research-writing" / "skills" / "manuscript-workflow"
TOOLS = SKILL / "tools"
INITIALIZER = SKILL / "init_manuscript.py"
UPDATE = SKILL / "update_tools.py"
MIGRATE = SKILL / "migrate_format.py"
HOOK = SKILL / "hooks" / "guard_write.py"
PY = [sys.executable, "-X", "utf8", "-B"]

os.environ.setdefault("SYNC_STATE_HOME", tempfile.mkdtemp(prefix="format-migration-state-"))   # shared with suites imported earlier
STATE = Path(os.environ["SYNC_STATE_HOME"])

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(TOOLS))
import _config  # noqa: E402
import grammar_scenarios as GS  # noqa: E402

HANGUL = re.compile("[%s-%s%s-%s%s-%s]" % tuple(map(chr, (0x1100, 0x11FF, 0x3130, 0x318F, 0xAC00, 0xD7A3))))   # Hangul jamo · compatibility jamo · syllables
KINDS = {
    "journal": (["--source-dir", "manuscript", "--chapters", "intro.md", "results.md", "--references", "references.md"],
                "manuscript/intro.md", "manuscript/results.md"),
    "dissertation": (["--source-dir", "manuscript_src", "--chapters", "ch1.md", "ch2.md", "ch3.md", "--references", "references.md",
                      "--build-script", "build_tpl.py"], "manuscript_src/ch1.md", "manuscript_src/ch2.md"),
}


def run(cmd, cwd, codes=(0,), inp=None):
    r = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", timeout=180, input=inp)
    assert r.returncode in codes, f"{cmd}\nrc={r.returncode}\n{r.stdout}\n{r.stderr}"
    assert "Traceback" not in r.stderr, r.stderr
    return r


def tool(p: Path, name: str) -> Path:
    return p / "tools" / name


def fmt(p: Path) -> str:
    return _config.project_format(_config.load(str(p)))[0]


def files(p: Path, skip=("archive/", ".manuscript/tools_backup/")):
    """{path relative to the root: sha256} — drive snapshots (archive/) and tool backups left out."""
    out = {}
    for f in p.rglob("*"):
        rel = f.relative_to(p).as_posix()
        if f.is_file() and "__pycache__" not in f.parts and not rel.startswith(skip):
            out[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def block(text: str, key: str) -> str:
    """Inside of the English block `BLOCKS[key]` (the class letter form is not needed here)."""
    name = _config.BLOCKS[key][0]
    return text.split("<!-- %s -->" % name, 1)[1].split("<!-- /%s -->" % name, 1)[0]


# ---------------------------------------------------------------- old format, built from the `_config` pairs
_MARKERS = [(re.compile("^" + re.escape(en).replace(r"\{\}", "([A-Z]{1,2})") + "$"), ko) for en, ko in _config.BLOCKS.values()]
_MARKER_LINE = re.compile(r"^<!-- (/?)(.+?) -->$")
_STAMP_EN, _STAMP_KO = ("<!-- %s " % w for w in _config.STAMP_WORDS)
_COL_KO = dict(_config.COLUMNS.values())
_FIELD_KO = dict(_config.FIELDS.values())
_TRIGGER_KO = dict(_config.DEFAULT_TRIGGERS)
_STATE_KO = sorted(((en, ko) for _k, en, ko in _config.STATES), key=lambda x: -len(x[0]))
_FOCUS_EN, _FOCUS_KO = ("**%s**" % s for s in _config.FOCUS_LABEL)


def legacy_value(cell: str) -> str:
    """A trigger or status cell in the old spelling — a default trigger as a whole, a status word at the head."""
    if cell in _TRIGGER_KO:
        return _TRIGGER_KO[cell]
    for en, ko in _STATE_KO:
        if cell.lower().startswith(en) and not cell[len(en):len(en) + 1].isalpha():
            return ko + cell[len(en):]
    return cell


def legacy_text(text: str) -> str:
    """One tracker file in the pre-0.14 spellings — markers, stamp lines, `| ID |` header names, the focus label, and the trigger and
    status cells of `| ID |` tables. Unknown column names stay as written (as in a real old project)."""
    out, cols = [], {}
    for line in text.split("\n"):
        m = _MARKER_LINE.match(line)
        if line.startswith(_STAMP_EN):                    # a stamp line has the comment shape too — test it first
            line = _STAMP_KO + line[len(_STAMP_EN):]
        elif m:
            for rx, ko in _MARKERS:
                k = rx.match(m.group(2))
                if k:
                    line = "<!-- %s%s -->" % (m.group(1), ko.format(*k.groups()))
                    break
        elif line.startswith("|"):
            cells = _config.split_cells(line)
            if cells[0] == "ID":
                cols = {_config.column_key(c): j for j, c in enumerate(cells)}
                line = "| " + " | ".join(_COL_KO.get(c, c) for c in cells) + " |"
            elif _config.TABLE_ROW_RE.match(line):
                new = list(cells)
                for key in ("trigger", "status"):
                    j = cols.get(key)
                    if j is not None and j < len(new):
                        new[j] = legacy_value(new[j])
                if new != cells:
                    line = "| " + " | ".join(new) + " |"
        out.append(line.replace(_FOCUS_EN, _FOCUS_KO))
    return "\n".join(out)


def to_legacy(p: Path):
    """Turn an English project into the shape of a project made before 0.14 — tracker anchors and values, record field labels and status
    values, and the default triggers of project.json in the old spellings. Tools and file names stay as they are."""
    cfg = _config.load(str(p))
    for rel in _config.tracker_anchor_files(cfg):
        f = p / rel
        if f.is_file():
            f.write_bytes(legacy_text(f.read_bytes().decode("utf-8")).encode("utf-8"))
    for rec in (p / cfg.records_dir).glob("E*.md"):
        text = rec.read_bytes().decode("utf-8")
        for en, ko in _FIELD_KO.items():
            text = text.replace("**%s**" % en, "**%s**" % ko)
        text = re.sub(r"(?m)^(\*\*%s\*\* )(.+)$" % re.escape(_FIELD_KO["Status"]), lambda m: m.group(1) + legacy_value(m.group(2)), text)
        rec.write_bytes(text.encode("utf-8"))
    cfg_path = p / ".manuscript" / "project.json"
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    raw["tracker"]["triggers"] = [_TRIGGER_KO.get(t, t) for t in raw["tracker"]["triggers"]]
    cfg_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- fixtures
class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = Path(tempfile.mkdtemp(prefix="format-migration-"))

    def init(self, name: str, kind: str) -> Path:
        p = self.scratch / name
        run(PY + [INITIALIZER, p, "--name", "Format sample " + name, "--kind", kind] + KINDS[kind][0], self.scratch)
        return p

    @staticmethod
    def add_rows(path: Path, section: str, rows, header=None):
        """Put rows under the `| ID |` table of the section whose heading starts with `## <section>` (or the only table of the file);
        `header` replaces that table's header line first."""
        lines = path.read_text(encoding="utf-8").split("\n")
        start = next(i for i, l in enumerate(lines) if l.startswith("## " + section)) if section else 0
        hdr = next(i for i in range(start, len(lines)) if lines[i].startswith("| ID |"))
        if header:
            lines[hdr] = header
        lines[hdr + 2:hdr + 2] = list(rows)
        path.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    def project(self, name: str, kind: str) -> Path:
        """An English project with open rows (now · later · a column the tools do not know), a closed row archived by the tidy tool,
        a proposal, two completion records and the focus on chapter 2."""
        p = self.init(name, kind)
        ch1, ch2 = KINDS[kind][1], KINDS[kind][2]
        trig = dict((key, _config.tok(pair)) for key, pair in zip(("now", "section", "user", "data", "final"), _config.DEFAULT_TRIGGERS))
        pend = p / "tracker_pending.md"
        self.add_rows(pend, "A.", [f"| A1 | an item to do now | `{ch2}` ③ | {trig['now']} | waiting | the note of A1 |",
                                   f"| A2 | an item for later | `{ch1}` ¶1 | {trig['section']} | in progress | the note of A2 |"])
        self.add_rows(pend, "B.", [f"| B1 | a finished item | `{ch2}` ④ | {trig['user']} | done (2026-11-01) | the note of B1 |"])
        self.add_rows(pend, "D.", [f"| D1 | a style item | all | {trig['final']} | waiting | the note of D1 | the user |"],
                      header="| ID | Item | Location | Trigger | Status | Note | Owner |")
        self.add_rows(p / "tracker_proposals.md", None,
                      [f"| H1 | a proposal | `{ch2}` ③ | {trig['user']} | waiting | the basis of H1 |"])
        for n, status in ((1, "confirmed"), (2, "applied (awaiting confirmation)")):
            body = self.scratch / f"{name}_record{n}.md"
            body.write_text(f"# E? — record {n}\n\n**Completed** 2026-11-0{n}\n**Target** `{ch2}` ③\n**Status** {status}\n\nBody {n}.\n",
                            encoding="utf-8")
            run(PY + [tool(p, "new_record.py"), body], p)
        run(PY + [tool(p, "tidy_tracker.py"), "--focus", "ch2", "--apply"], p, codes=(0, 1))
        self.assertEqual(fmt(p), "en")
        self.assertIn("| B1 |", (p / "records" / "archive.md").read_text(encoding="utf-8"))
        return p

    def writing_tools_refuse(self, p: Path, why: str):
        """Every writing tool exits 5 with the message and changes no file."""
        before = files(p)
        row = self.scratch / (p.name + "_row.md")
        row.write_text(f"| A? | a new item | `{KINDS['journal'][2]}` ③ | now | waiting | a note |\n", encoding="utf-8")
        body = self.scratch / (p.name + "_body.md")
        body.write_text("# E? — refused\n\n**Completed** 2026-11-03\n**Target** all\n**Status** confirmed\n\nBody.\n", encoding="utf-8")
        for cmd in ([tool(p, "tidy_tracker.py"), "--apply"], [tool(p, "index_records.py")],
                    [tool(p, "new_pending.py"), row], [tool(p, "new_record.py"), body]):
            r = run(PY + cmd, p, codes=(_config.RC_FORMAT,))
            self.assertIn(why, r.stderr, cmd)
            self.assertIn("update_tools.py", r.stderr, cmd)
        self.assertEqual(files(p), before, "a refused tool writes nothing")


# ---------------------------------------------------------------- an old-format project → migration
class LegacyProject(Fixture):
    def test_old_project_is_read_refused_previewed_and_migrated(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                p = self.project("legacy-" + kind, kind)
                to_legacy(p)
                self.assertEqual(fmt(p), "ko")
                records = {f.name: f.read_bytes() for f in (p / "records").glob("*.md") if f.name != "archive.md"}   # E*.md and README.md
                settings = (p / ".manuscript" / "project.json").read_bytes()
                self.assertIn(_config.FOCUS_LABEL[1], (p / "tracker_index.md").read_text(encoding="utf-8"))

                # diagnosis reads the old anchors and values — no exit 5, no unknown trigger or status, the trigger column is found
                r = run(PY + [tool(p, "tidy_tracker.py")], p, codes=(0, 1))
                self.assertIn("diagnosis only", r.stdout)
                for bad in ("has no `", "unknown trigger", "unknown status value", "could not be read"):
                    self.assertNotIn(bad, r.stdout)
                r = run(PY + [tool(p, "check_sync.py"), "--quick", "-v"], p, codes=(0, 1))
                self.assertIn("INFO  S9", r.stdout)
                self.assertNotIn("ERROR S9", r.stdout)

                self.writing_tools_refuse(p, "Korean anchors")

                # preview — exit 1, lists the anchors and the unknown column, writes nothing
                before = files(p)
                r = run(PY + [UPDATE, p], self.scratch, codes=(1,))
                self.assertRegex(r.stdout, r"Format migration — \d+ anchor lines to change")
                self.assertIn("unknown column names kept: 1", r.stdout)
                self.assertIn("kept `Owner`", r.stdout)
                self.assertEqual(files(p), before, "the preview writes nothing")
                r = run(PY + [UPDATE, "--scan", self.scratch, "--depth", "1"], self.scratch, codes=(0, 1))
                self.assertRegex(r.stdout, re.escape(p.name) + r"\n\s+files .*\| format ko")

                # --apply — migrates, rebuilds with the project's tools, ends English
                r = run(PY + [UPDATE, p, "--apply"], self.scratch, codes=(0,))
                self.assertRegex(r.stdout, r"rebuild   index_records\.py \(rc=0\)")
                self.assertRegex(r.stdout, r"rebuild   tidy_tracker\.py --apply \(rc=[01]\)")
                self.assertIn("format    now en", r.stdout)
                self.assertEqual(fmt(p), "en")
                self.assertEqual({f.name: f.read_bytes() for f in (p / "records").glob("*.md") if f.name != "archive.md"}, records, "records are history — never rewritten")
                self.assertEqual((p / ".manuscript" / "project.json").read_bytes(), settings, "the settings are not written")
                pend = (p / "tracker_pending.md").read_text(encoding="utf-8")
                self.assertIn("| ID | Item | Location | Trigger | Status | Note | Owner |", pend, "the unknown column name is kept")
                self.assertIn(_TRIGGER_KO["now"], pend, "values stay as written")
                index = (p / "tracker_index.md").read_text(encoding="utf-8")
                self.assertIn("**Working chapter** ch2", block(index, "focus"), "the focus set before the migration is still set")
                self.assertIn("#### A1 ", block(index, "focus"))
                self.assertIn("| **A1** |", block(index, "now"), "a row whose trigger is the old `now` is still in §5")
                self.assertNotIn("| **A2** |", block(index, "now"))
                self.assertIn("A2", block(index, "triggers"))
                self.assertEqual(sum(l.startswith(_STAMP_EN) for l in index.split("\n")), 1)
                self.assertEqual(sum(l.startswith(_STAMP_KO) for l in index.split("\n")), 0)
                self.assertIn("| B1 |", (p / "records" / "archive.md").read_text(encoding="utf-8"))
                self.assertNotIn(_config.FOCUS_LABEL[1], index)

                # idempotent — a second --apply and a preview change nothing; the writing tools work again
                once = files(p)
                r = run(PY + [UPDATE, p, "--apply"], self.scratch, codes=(0,))
                self.assertIn("Format migration — nothing to change", r.stdout)
                self.assertEqual(files(p), once, "a second --apply changes nothing")
                r = run(PY + [UPDATE, p], self.scratch, codes=(0,))
                self.assertIn("Format migration — nothing to change", r.stdout)
                run(PY + [MIGRATE, p], self.scratch, codes=(0,))
                self.assertEqual(files(p), once)
                run(PY + [tool(p, "index_records.py")], p)
                run(PY + [tool(p, "tidy_tracker.py"), "--apply"], p, codes=(0, 1))


# ---------------------------------------------------------------- mixed anchors — an old tool wrote into an English project
class MixedProject(Fixture):
    @staticmethod
    def hook_pre(p: Path, tid: str):
        payload = {"tool_name": "Edit", "tool_input": {"file_path": str(p / "tracker_pending.md"), "old_string": "a", "new_string": "b"},
                   "cwd": str(p), "tool_use_id": tid}
        return run(PY + [HOOK, "pre"], p, inp=json.dumps(payload)).stdout

    def mixed(self, name: str, kind: str) -> Path:
        """An English project whose index also got a Korean stamp line — what a tidy tool from before 0.14 adds (its own stamp, same hashes)."""
        p = self.project(name, kind)
        idx = p / "tracker_index.md"
        lines = idx.read_text(encoding="utf-8").split("\n")
        stamp = next(l for l in lines if l.startswith(_STAMP_EN))
        lines.insert(1, _STAMP_KO + stamp[len(_STAMP_EN):])
        idx.write_text("\n".join(lines), encoding="utf-8", newline="\n")
        self.assertEqual(fmt(p), "mixed")
        return p

    @staticmethod
    def stamps(p: Path):
        return [l for l in (p / "tracker_index.md").read_text(encoding="utf-8").split("\n") if l.startswith((_STAMP_EN, _STAMP_KO))]

    def test_korean_stamp_in_an_english_index_is_refused_and_migrated(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                p = self.mixed("mixed-" + kind, kind)
                self.writing_tools_refuse(p, "mix English and Korean anchors")
                r = run(PY + [tool(p, "check_sync.py"), "--quick"], p, codes=(2,))
                self.assertIn("ERROR S9", r.stdout)
                self.assertIn('"permissionDecision": "deny"', self.hook_pre(p, "mixed-" + kind), "an S9 ERROR blocks guarded writes")

                r = run(PY + [UPDATE, p], self.scratch, codes=(1,))
                self.assertIn("Format migration — 1 anchor lines to change", r.stdout)
                r = run(PY + [UPDATE, p, "--apply"], self.scratch, codes=(0,))
                self.assertIn("format    now en", r.stdout)
                self.assertEqual(fmt(p), "en")
                # a new session-start check records the current state (no S9) — then the tidy tool leaves a single stamp
                r = run(PY + [tool(p, "check_sync.py"), "--quick"], p, codes=(0, 1))
                self.assertNotIn("S9", r.stdout)
                run(PY + [tool(p, "tidy_tracker.py"), "--apply"], p, codes=(0, 1))
                stamps = self.stamps(p)
                self.assertEqual(len(stamps), 1, stamps)
                self.assertTrue(stamps[0].startswith(_STAMP_EN))
                self.assertEqual(self.hook_pre(p, "mixed-after-" + kind).strip(), "")

    def test_migration_rebuild_is_not_blocked_by_the_alert_it_fixes(self):
        """The S9 ERROR recorded by the session-start check (or by the hook) must not refuse the rebuild that `update_tools.py --apply`
        runs right after migrating — the rebuild is what removes the second stamp line."""
        p = self.mixed("mixed-rebuild", "journal")
        run(PY + [tool(p, "check_sync.py"), "--quick"], p, codes=(2,))          # records the S9 ERROR, as at a session start
        r = run(PY + [UPDATE, p, "--apply"], self.scratch, codes=(0, 1))
        self.assertEqual(fmt(p), "en")
        self.assertRegex(r.stdout, r"rebuild   index_records\.py \(rc=0\)", r.stdout)
        self.assertRegex(r.stdout, r"rebuild   tidy_tracker\.py --apply \(rc=[01]\)", r.stdout)
        self.assertEqual(len(self.stamps(p)), 1, self.stamps(p))

    def test_migration_refuses_while_another_error_is_open(self):
        """An open ERROR other than S9 (here an S4 overwrite) stops the rewrite — the migration must not rebuild over its evidence —
        and stays recorded; only S9, the condition the migration removes, may be dropped from the record."""
        import _sync
        p = self.mixed("mixed-other-error", "journal")
        sync = _sync.Sync(_config.load(str(p)))
        sync.record_alerts([_sync.Finding("ERROR", "S4", "S4:index:regress", "the pending file went back to an older version"),
                            _sync.Finding("ERROR", "S9", "S9:mixed:tracker_index.md", "mixed anchors")])
        before = {f.name: f.read_bytes() for f in p.glob("tracker_*.md")}
        r = run(PY + [UPDATE, p, "--apply"], self.scratch, codes=(1,))
        self.assertIn("Not migrated — the sync check has open ERRORs", r.stdout)
        self.assertIn("format    not migrated", r.stdout)
        self.assertEqual(fmt(p), "mixed")
        self.assertEqual(before, {f.name: f.read_bytes() for f in p.glob("tracker_*.md")}, "nothing was rewritten")
        self.assertIn("S4:index:regress", [d["key"] for d in sync._alerts()["findings"]], "the open S4 ERROR stays recorded")
        r = run(PY + [MIGRATE, p, "--apply"], self.scratch, codes=(2,))
        self.assertIn("update_tools.py <project> --apply", r.stdout, "the rewrite runs only through update_tools")


# ---------------------------------------------------------------- archive join — tables matched by column key, not by the written name
JOIN_DRIVER = r"""
import json, sys
sys.path.insert(0, 'tools')
import tidy_tracker as T
t = T.Tidy('.', True)
t.migrate()                       # in memory only — nothing is saved
print(json.dumps({'rec': t.rec.lines, 'pend': t.pend.lines, 'warns': t.warns}, ensure_ascii=False))
"""


class ArchiveJoin(Fixture):
    def join(self, name: str, pend_header: str, arch_header: str):
        """Two closed B rows and one archived row; the tidy tool's archive step runs in memory in the project (tables of either spelling)."""
        p = self.init(name, "journal")
        rows = ["| B1 | first finished item | `manuscript/results.md` ③ | user decision | done (2026-11-01) | first note | first owner |",
                "| B2 | second finished item | `manuscript/intro.md` ¶2 | when working on the section | closed — duplicate | second note | second owner |"]
        self.add_rows(p / "tracker_pending.md", "B.", rows, header=pend_header)
        arch = p / "records" / "archive.md"
        text = arch.read_text(encoding="utf-8")
        old = next(l for l in text.split("\n") if l.startswith("| ID |"))
        sep = "|" + "---|" * len(_config.split_cells(arch_header))
        cells = {"ID": "B0", "Owner": "earlier owner"}
        row = "| " + " | ".join(cells.get(c, "earlier " + (_config.column_key(c) or c)) for c in _config.split_cells(arch_header)) + " |"
        text = text.replace(old + "\n" + "|" + "---|" * len(_config.split_cells(old)), arch_header + "\n" + sep + "\n" + row, 1)
        arch.write_text(text, encoding="utf-8", newline="\n")
        out = json.loads(run(PY + ["-c", JOIN_DRIVER], p).stdout)
        lines = out["rec"]
        a = lines.index(arch_header)
        got = [_config.split_cells(l) for l in lines[a + 2:] if _config.TABLE_ROW_RE.match(l)]
        return out, [_config.split_cells(arch_header)] + got

    def check(self, out, table):
        hdr, got = table[0], table[1:]
        self.assertEqual([r[0] for r in got], ["B0", "B1", "B2"], "no row is lost and the archived row stays")
        for r in got:
            self.assertEqual(len(r), len(hdr), r)
            self.assertTrue(all(c.strip() for c in r), "no empty cell: %r" % (r,))
        col = dict((_config.column_key(c) or c, j) for j, c in enumerate(hdr))
        b1, b2 = got[1], got[2]
        self.assertEqual((b1[col["item"]], b1[col["location"]], b1[col["status"]]),
                         ("first finished item", "`manuscript/results.md` ③", "done (2026-11-01)"))
        self.assertEqual(b1[col["note"]], "(trigger: user decision) first note")
        self.assertEqual(b1[col["Owner"]], "first owner", "an unknown column is joined by its written name")
        self.assertEqual((b2[col["status"]], b2[col["Owner"]]), ("closed — duplicate", "second owner"))
        self.assertFalse(any(re.match(r"^\| B[12] \|", l) for l in out["pend"]), "the archived rows leave the pending table")
        self.assertEqual(out["warns"], [])

    def test_english_pending_into_korean_archive(self):
        ko = _COL_KO
        arch = "| ID | %s | %s | %s | %s | Owner |" % (ko["Status"], ko["Item"], ko["Note"], ko["Location"])   # another order, old spelling
        out, table = self.join("join-en-ko", "| ID | Item | Location | Trigger | Status | Note | Owner |", arch)
        self.check(out, table)

    def test_korean_pending_into_english_archive(self):
        ko = _COL_KO
        pend = "| ID | %s | %s | %s | %s | %s | Owner |" % (ko["Item"], ko["Location"], ko["Trigger"], ko["Status"], ko["Note"])
        out, table = self.join("join-ko-en", pend, "| ID | Note | Status | Location | Item | Owner |")
        self.check(out, table)


# ---------------------------------------------------------------- status vocabulary — both spellings
class States(unittest.TestCase):
    def test_closed_and_open_states(self):
        ko = dict((k, v) for k, _en, v in _config.STATES)
        closed = ["closed — duplicate", "done", "Done (2026-11-01)", "closed", ko["done"] + " (2026-10-12)", ko["closed"]]
        not_closed = ["redone", "done (visual check needed)", "applied (E3)", "waiting", "in progress", "on hold",
                      ko["done"] + "(육안 확인 필요)",            # old-format value on purpose: "done (visual check needed)"
                      ko["applied"] + " (E3)", ko["waiting"], "closed but waiting for the reviewer"]
        for s in closed:
            self.assertTrue(_config.state_is_closed(s), s)
        for s in not_closed:
            self.assertFalse(_config.state_is_closed(s), s)
        self.assertFalse(_config.state_known("redone"))
        self.assertTrue(_config.state_known("waiting"))
        self.assertTrue(_config.state_known(ko["waiting"]))

    def test_default_triggers_are_one_trigger_in_either_spelling(self):
        for en, ko in _config.DEFAULT_TRIGGERS:
            self.assertEqual(_config.trigger_key(en), _config.trigger_key(ko), en)
        self.assertTrue(_config.is_now(_config.TRIGGER_NOW[1]))
        self.assertTrue(_config.is_now("**now**"))
        self.assertFalse(_config.is_now("someday"))


# ---------------------------------------------------------------- grammar baseline — old keys and the old packet format
_BASE_KO = dict((en, ko) for en, ko in _config.BASELINE_KEYS.values())
_PACKET_KO = dict((en, ko) for en, ko in _config.PACKET_KEYS.values())


def korean_keys(obj, table):
    """Inverse of `_config.english_keys` — an old file built from a new one."""
    if isinstance(obj, list):
        return [korean_keys(x, table) for x in obj]
    if not isinstance(obj, dict):
        return obj
    return dict((table.get(k, k), korean_keys(v, table)) for k, v in obj.items())


class GrammarBaseline(unittest.TestCase):
    INTRO = ("@H1 Introduction\n\nThe first paragraph of the sample introduces the topic in plain words for the test.\n\n"
             "The second paragraph of the sample motivates the comparison of the two surface finishes here.\n")

    def test_old_keys_are_read_new_lines_use_english_and_old_packets_are_accepted(self):
        root = Path(tempfile.mkdtemp(prefix="format-grammar-")) / "journal"
        (root / ".manuscript").mkdir(parents=True)
        (root / ".manuscript" / "project.json").write_text(json.dumps({
            "project": "Grammar format sample", "kind": "journal",
            "manuscript": {"source_dir": "manuscript", "chapters": [{"n": 1, "file": "intro.md"}], "references": "references.md"}}),
            encoding="utf-8")
        (root / "manuscript").mkdir()
        (root / "manuscript" / "intro.md").write_text(self.INTRO, encoding="utf-8", newline="\n")
        p = GS.Proj(root, STATE)
        p.install()
        p.run("init", "--confirm", "test baseline")
        base = p.baseline()
        old = [json.dumps(korean_keys(json.loads(l), _BASE_KO), ensure_ascii=False) for l in base.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(all(HANGUL.search(l) for l in old))
        base.write_bytes(("\n".join(old) + "\n").encode("utf-8"))               # a baseline written before 0.14 — Korean keys only
        before = base.read_bytes()
        p.run("changed")                                                         # every unit is found in the old lines

        para = self.INTRO.split("\n\n")[1]
        p.replace_once("manuscript/intro.md", para, para.replace("plain words", "simple words"))
        work = Path(tempfile.mkdtemp(prefix="format-grammar-work-"))
        new_pk = work / "new.json"
        p.run("changed", "--out", new_pk, codes=(1,))
        data = json.loads(new_pk.read_text(encoding="utf-8"))
        self.assertEqual(data["format"], _config.PACKET_FORMAT[0])
        self.assertIn("units", data)
        old_pk = work / "old.json"                                               # the same packet in the old format and keys
        legacy = korean_keys(data, _PACKET_KO)
        legacy[_PACKET_KO["format"]] = _config.PACKET_FORMAT[1]
        old_pk.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
        r = p.run("clean", "--packet", old_pk, "--all-except")
        self.assertIn("recorded 1", r.stdout)
        p.run("changed")
        after = base.read_bytes()
        self.assertTrue(after.startswith(before), "the baseline is append-only — old lines stay as written")
        added = [json.loads(l) for l in after[len(before):].decode("utf-8").splitlines() if l]
        self.assertEqual(len(added), 1)
        self.assertIn("fingerprint", added[0])
        self.assertFalse(set(added[0]) & set(_BASE_KO.values()), added[0])
        self.assertTrue(all(k.isascii() for k in added[0]), added[0])


# ---------------------------------------------------------------- generated skeleton
class Skeleton(Fixture):
    def test_generated_files_are_english_and_point_at_single_sources(self):
        managed = json.loads((SKILL / "managed_files.json").read_text(encoding="utf-8"))["files"]
        skill = (WORKFLOW / "SKILL.md").read_text(encoding="utf-8")
        headings = lambda text: [h.strip() for h in re.findall(r"(?m)^#+ (.+)$", text)]          # noqa: E731
        for kind in KINDS:
            with self.subTest(kind=kind):
                p = self.init("skeleton-" + kind, kind)
                copies = {item["dst"].replace("{tools_dir}", _config.DEFAULTS["tools_dir"]) for item in managed}
                made = [f for f in p.rglob("*") if f.is_file() and "__pycache__" not in f.parts]
                own = [f for f in made if f.relative_to(p).as_posix() not in copies]
                self.assertGreater(len(own), 10)
                # the managed tool copies hold the legacy spellings by design (`_config.py`); every other file the initializer writes is English
                hangul = [f.relative_to(p).as_posix() for f in own if HANGUL.search(f.read_text(encoding="utf-8"))]
                self.assertEqual(hangul, [])
                self.assertEqual(fmt(p), "en")

                agents = (p / "AGENTS.md").read_text(encoding="utf-8")
                line = next(l for l in agents.split("\n") if "`procedure`" in l)
                self.assertIn("only check at entry that the file exists", line)
                self.assertIn("resolved against the project root", agents)
                self.assertIn("when a row of the `CLAUDE.md` §2 table points to it", agents)
                self.assertNotRegex(agents, r"(?i)\bread\b[^.\n]*`procedure`", "procedure is not read at entry")

                claude = (p / "CLAUDE.md").read_text(encoding="utf-8")
                sec2 = claude.split("\n## 2.", 1)[1].split("\n## 3.", 1)[0]
                header = next(l for l in sec2.split("\n") if l.startswith("|"))
                self.assertEqual(_config.split_cells(header), ["When", "In this project"])
                self.assertNotIn("plugin", header.lower())
                table = "Reference documents — read only the one you need"
                self.assertIn("`manuscript-workflow` skill's table \"%s\"" % table, sec2)
                self.assertIn(table, headings(skill), "the table §2 names is a heading of the skill")
                sec1 = claude.split("\n## 1.", 1)[1].split("\n## 2.", 1)[0]
                self.assertIn('"Check first"', sec1)
                self.assertIn("Check first", headings(skill))
                sec3 = claude.split("\n## 3.", 1)[1].split("\n## 4.", 1)[0]
                row = next(l for l in sec3.split("\n") if l.startswith("| Completion records |"))
                self.assertEqual(_config.split_cells(row)[-1], "Format: `records/README.md`")

                readme = (p / "records" / "README.md").read_text(encoding="utf-8")
                self.assertIn('`revision-protocol.md` "Approval and comparison"', readme)
                self.assertIn("Approval and comparison", headings((WORKFLOW / "references" / "revision-protocol.md").read_text(encoding="utf-8")))
                self.assertIn("IDs are never reused", (p / "tracker_pending.md").read_text(encoding="utf-8"))
                self.assertNotIn("IDs are never reused", (p / "tracker_index.md").read_text(encoding="utf-8"))

                raw = json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8"))
                self.assertEqual(raw["tracker"]["triggers"], [_config.tok(pair) for pair in _config.DEFAULT_TRIGGERS])
                src = raw["manuscript"]["source_dir"]
                self.assertIn("**Fill in.**", (p / src / raw["manuscript"]["chapters"][0]["file"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
