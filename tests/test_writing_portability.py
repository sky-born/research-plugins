"""Exercise new-manuscript on synthetic projects without touching research files.

Fixtures stay in a dedicated OS temporary folder; this suite performs no cleanup
or recursive deletion of project files.
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
SKILLS = ROOT / "plugins" / "research-writing" / "skills"
INITIALIZER = SKILLS / "new-manuscript" / "init_manuscript.py"


class WritingPortabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = Path(tempfile.mkdtemp(prefix="shared-writing-fixture-"))
        # Keep the per-computer state of the sync guard in a temp folder, not in the real home (~/.claude/sync-state).
        # setdefault — another suite in the same process may already have set it, and its tests read that folder.
        os.environ.setdefault("SYNC_STATE_HOME", str(cls.scratch / "_sync-state"))

    def run_python(self, script: Path, *args: str, cwd: Path | None = None, codes=(0,)):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(script), *args],
            cwd=cwd or self.scratch,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        self.assertIn(result.returncode, codes, result.stdout + result.stderr)
        return result

    def run_empty_tracker(self, project: Path, *args: str):
        result = self.run_python(
            project / "tools" / "tidy_tracker.py", *args, cwd=project, codes=(1,)
        )
        # Empty new projects intentionally return 1 for the missing-records diagnostic.
        # Zero open items with intact tables is a note, not a warning: the list
        # blocks are rebuilt empty instead of being skipped as a read failure.
        self.assertIn("E*.md not found", result.stdout)
        self.assertIn("Zero open items", result.stdout)
        self.assertNotIn("No open items could be read", result.stdout)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def create_project(self, dirname: str) -> Path:
        project = self.scratch / dirname
        self.run_python(
            INITIALIZER, str(project), "--name", "Portability check manuscript",
            "--source-dir", "draft sources", "--chapters", "intro.md", "results.md",
            "--references", "bib.md",
        )
        return project

    @staticmethod
    def snapshot(project: Path):
        return {
            path.relative_to(project).as_posix(): (
                hashlib.sha256(path.read_bytes()).hexdigest(),
                path.stat().st_mtime_ns,
            )
            for path in project.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }

    def test_generated_project_routes_both_hosts_to_one_rule_source(self):
        project = self.create_project("new manuscript spaced path")
        cfg = json.loads((project / ".manuscript" / "project.json").read_text(encoding="utf-8"))
        self.assertTrue(cfg["markers"])
        for marker in cfg["markers"]:
            self.assertTrue((project / marker).is_file(), marker)
        agents = (project / "AGENTS.md").read_text(encoding="utf-8")
        shared = (project / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("`CLAUDE.md`", agents)
        self.assertIn("`procedure`", agents)
        self.assertIn("manuscript-workflow", agents)
        self.assertNotRegex(agents, r"(?m)^## .*Limits of the domain evidence")
        self.assertRegex(shared, r"(?m)^## 6\. Limits of the domain evidence")
        self.assertNotIn("writing_guide.md", json.dumps(cfg))     # never wired into `procedure`
        self.assertIn("Portability check manuscript", shared)
        self.assertNotIn("C:\\Users\\", agents + shared)

    def test_generated_instructions_point_only_at_things_that_exist(self):
        # Per-task rules are reached through the CLAUDE.md tables; a pointer to nothing fails silently.
        project = self.create_project("pointer check")
        refs = SKILLS / "manuscript-workflow" / "references"
        checked = titles = 0
        for doc in ("CLAUDE.md", "writing_guide.md", "AGENTS.md"):
            for line in (project / doc).read_text(encoding="utf-8").splitlines():
                placeholder = "fill in" in line.lower()    # may name project files that do not exist yet
                tokens = re.findall(r'`([^`]+)`(?:\s*"([^"]+)")?', line)     # a reference title follows the file name in double quotes
                if line.startswith("    "):          # indented command lines
                    tokens += [(name, "") for name in re.findall(r"(\S+\.py)", line)]
                for token, title in tokens:
                    if token == ".md" or not ("/" in token or token.endswith((".md", ".json", ".py"))):
                        continue
                    checked += 1
                    reference = refs / token
                    if reference.is_file():
                        if title:
                            # a title names a heading — the whole heading, or the part before its ` — ` subtitle
                            headings = [h.strip() for h in
                                        re.findall(r"(?m)^#+ (.+)$", reference.read_text(encoding="utf-8"))]
                            self.assertTrue(any(h == title or h.startswith(title + " — ") for h in headings),
                                            f'{doc}: "{title}" is not a heading of {token}')
                            titles += 1
                        continue
                    if (refs.parent / token).exists():   # a folder of the skill itself, e.g. `references/`
                        continue
                    if placeholder:
                        continue
                    target = token.rstrip("/")
                    where = (project / target).parent if "*" in target else project / target
                    self.assertTrue(where.exists(), f"{doc}: `{token}` does not exist in the project")
        self.assertGreater(checked, 10)
        self.assertGreater(titles, 0, "no quoted reference title was checked — the title pattern no longer matches the generated text")

    def test_repeat_initialization_preserves_user_edits_and_timestamps(self):
        project = self.create_project("user edits kept")
        for relative in ("AGENTS.md", "CLAUDE.md", "draft sources/intro.md"):
            path = project / relative
            with path.open("a", encoding="utf-8") as stream:
                stream.write("\nA sentence the user added — it stays.\n")
        before = self.snapshot(project)
        self.run_python(INITIALIZER, str(project), "--name", "A name that must not change anything")
        after = self.snapshot(project)
        # A different default source directory may add skeletons, but existing
        # files, including both instruction files, must remain byte-identical.
        for relative, signature in before.items():
            self.assertEqual(after[relative], signature, relative)

    def test_generated_tools_run_with_nondefault_paths(self):
        project = self.create_project("tools run")
        for tool in ("check_numbers.py", "index_records.py"):
            self.run_python(project / "tools" / tool, cwd=project)
        self.run_empty_tracker(project)
        self.assertTrue((project / "tracker_records_index.md").is_file())
        before = self.snapshot(project)
        self.run_empty_tracker(project, "--apply")
        once = self.snapshot(project)
        self.run_empty_tracker(project, "--apply")
        twice = self.snapshot(project)
        self.assertEqual(
            {name: value[0] for name, value in once.items()},
            {name: value[0] for name, value in twice.items()},
        )
        for name in ("AGENTS.md", "CLAUDE.md", "draft sources/intro.md"):
            self.assertEqual(before[name], twice[name], name)

    def test_index_title_follows_project_name(self):
        # The index title must follow project.json, not a name baked into the tool,
        # and a later rename must show up on the next regeneration.
        project = self.create_project("index title")
        records = project / "records"
        records.mkdir(exist_ok=True)
        (records / "E1.md").write_text(
            "# E1 — index title check\n\n**Completed** 2026-01-01\n**Target** `intro.md` ¶1\n"
            "**Status** applied (awaiting confirmation)\n\n## Background\n\nAn item for the check.\n",
            encoding="utf-8",
        )
        index = project / "tracker_records_index.md"
        tool = project / "tools" / "index_records.py"
        self.run_python(tool, cwd=project)
        self.assertTrue(
            index.read_text(encoding="utf-8").startswith("# Record index — Portability check manuscript"),
            index.read_text(encoding="utf-8").splitlines()[0],
        )
        cfg_path = project / ".manuscript" / "project.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["project"] = "A name changed midway"
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        self.run_python(tool, cwd=project)
        self.assertTrue(
            index.read_text(encoding="utf-8").startswith("# Record index — A name changed midway"),
            index.read_text(encoding="utf-8").splitlines()[0],
        )

    def test_focus_resolves_chapter_number_to_mapped_file(self):
        # ch1 is mapped to intro.md by project.json; a pending item located at
        # "intro.md ¶1" must be picked up by --focus ch1 even though its location
        # key is the real file name rather than "ch1.md".
        project = self.create_project("focus mapping")
        cfg = json.loads((project / ".manuscript" / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["manuscript"]["chapters"][0]["file"], "intro.md")
        trigger = cfg["tracker"]["triggers"][0]
        pending = project / "tracker_pending.md"
        text = pending.read_text(encoding="utf-8")
        header = "|---|---|---|---|---|---|\n"
        self.assertIn(header, text)
        row = "| A1 | focus check item | intro.md ¶1 | %s | waiting | |\n" % trigger
        pending.write_text(text.replace(header, header + row, 1), encoding="utf-8")
        result = self.run_python(
            project / "tools" / "tidy_tracker.py", "--focus", "ch1", "--apply",
            cwd=project, codes=(0, 1),
        )
        self.assertNotIn("Traceback", result.stderr)
        listing = (project / "tracker_index.md").read_text(encoding="utf-8")
        block = listing.split("<!-- focus -->", 1)[1].split("<!-- /focus -->", 1)[0]
        self.assertIn("**Working chapter** ch1", block)
        self.assertIn("· items: 1", block)
        self.assertIn("A1", block)

    def test_closed_proposals_leave_the_generated_tables(self):
        # A discarded proposal has no archive path: the proposals file only marks it
        # `closed`. The tracker must drop it from the generated tables by status, while
        # open proposals and pending A-D rows stay listed.
        project = self.create_project("closed proposal")
        cfg = json.loads((project / ".manuscript" / "project.json").read_text(encoding="utf-8"))
        trigger = cfg["tracker"]["triggers"][1]
        header = "|---|---|---|---|---|---|\n"
        pending = project / "tracker_pending.md"
        text = pending.read_text(encoding="utf-8")
        row = "| A1 | remaining pending item | intro.md ¶1 | %s | waiting | |\n" % trigger
        pending.write_text(text.replace(header, header + row, 1), encoding="utf-8")
        proposals = project / "tracker_proposals.md"
        text = proposals.read_text(encoding="utf-8")
        rows = ("| H1 | dropped proposal | intro.md ¶1 | %s | closed | dropped |\n"
                "| H2 | remaining proposal | intro.md ¶2 | %s | waiting | under review |\n") % (trigger, trigger)
        proposals.write_text(text.replace(header, header + rows, 1), encoding="utf-8")
        result = self.run_python(
            project / "tools" / "tidy_tracker.py", "--focus", "ch1", "--apply",
            cwd=project, codes=(0, 1),
        )
        self.assertNotIn("Traceback", result.stderr)
        listing = (project / "tracker_index.md").read_text(encoding="utf-8")
        for name in ("location-table", "trigger-table", "focus"):
            block = listing.split("<!-- %s -->" % name, 1)[1].split("<!-- /%s -->" % name, 1)[0]
            self.assertIn("A1", block, name)
            self.assertIn("H2", block, name)
            self.assertNotRegex(block, r"\bH1\b", name)
        # Closing is a status, not a move: the proposal stays in its own file.
        self.assertIn("| H1 | dropped proposal", proposals.read_text(encoding="utf-8"))

    def test_journal_numbering_is_flat_across_the_manuscript(self):
        # kind "journal" (the initializer's default) numbers figures, tables and
        # references once for the whole manuscript. `Fig.` and `Figs. 1 and 2` count
        # as citations; a caption line does not cite itself.
        project = self.create_project("journal numbers")
        src = project / "draft sources"
        tool = project / "tools" / "check_numbers.py"
        (src / "bib.md").write_text("@REF 1. First reference.\n\n@REF 2. Second reference.\n", encoding="utf-8")
        (src / "intro.md").write_text("The joint cracks [1]. See Fig. 1.\n", encoding="utf-8")
        results = ("@FIG a.png | Figure 1. First figure.\n\n"
                   "Figs. 1 and 2 are compared [2] and summarized in Table 1.\n\n"
                   "@FIG b.png | Figure 2. Second figure.\n\n"
                   "@TAB t1 | Table 1. Values.\n")
        (src / "results.md").write_text(results, encoding="utf-8")
        out = self.run_python(tool, cwd=project).stdout
        self.assertIn("whole manuscript Figure captions 2  OK", out)
        self.assertIn("whole manuscript Table  captions 1  OK", out)
        self.assertIn("order of first appearance = list order  OK (1–2)", out)
        self.assertIn("Summary — all fine", out)
        # A figure named only by its own caption is uncited, and a reference cited
        # before a lower-numbered one breaks first-appearance order.
        (src / "intro.md").write_text("The joint cracks [2]. See Fig. 1 [1].\n", encoding="utf-8")
        (src / "results.md").write_text(results + "\n@FIG c.png | Figure 3. Third figure.\n",
                                        encoding="utf-8")
        out = self.run_python(tool, cwd=project).stdout
        self.assertIn("not cited in the text ['3']", out)
        self.assertIn("order of first appearance goes against the numbers", out)

    def test_dissertation_numbering_restarts_in_each_chapter(self):
        # kind "dissertation" keeps chapter numbering (Figure 2-1 restarts per chapter)
        # and still lists cross-chapter references. The caption-is-not-a-citation fix
        # applies here too, so an uncited figure is no longer hidden by its caption.
        project = self.scratch / "dissertation numbers"
        self.run_python(
            INITIALIZER, str(project), "--name", "Dissertation numbering check", "--kind", "dissertation",
            "--source-dir", "draft sources", "--chapters", "ch1.md", "ch2.md",
            "--references", "bib.md",
        )
        src = project / "draft sources"
        (src / "ch1.md").write_text("@FIG a.png | Figure 1-1. First figure.\n\nSee Figure 1-1.\n",
                                    encoding="utf-8")
        (src / "ch2.md").write_text(
            "@FIG b.png | Figure 2-1. A cited figure.\n\n"
            "Figure 2-1 is compared with Fig. 1-1.\n\n"
            "@FIG c.png | Figure 2-2. A figure nobody cites.\n",
            encoding="utf-8",
        )
        out = self.run_python(project / "tools" / "check_numbers.py", cwd=project).stdout
        self.assertIn("ch1 Figure captions 1  OK", out)
        self.assertIn("ch2 Figure captions 2  OK", out)
        self.assertIn("not cited in the text ['2-2']", out)
        self.assertIn("ch2 → FIG 1-1", out)

    def test_record_allocator_assigns_next_free_number_atomically(self):
        # The allocator, not the model, picks the record number; a number another
        # session took first is skipped, and a malformed body creates nothing.
        project = self.create_project("record numbering")
        tool = project / "tools" / "new_record.py"
        body = self.scratch / "record_body.md"
        body.write_text(
            "# E? — numbering check\n\n**Completed** 2026-01-02\n**Target** `intro.md` ¶1\n**Status** confirmed\n\nBody (E?).\n",
            encoding="utf-8",
        )
        out = self.run_python(tool, str(body), cwd=project).stdout.strip().splitlines()[-1]
        self.assertEqual(out.split("\t"), ["E1", "records/E1.md"])
        text = (project / "records" / "E1.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# E1 — numbering check"), text.splitlines()[0])
        self.assertIn("Body (E1).", text)
        (project / "records" / "E2.md").write_text("# E2 — an item another session made first\n", encoding="utf-8")
        out = self.run_python(tool, str(body), cwd=project).stdout.strip().splitlines()[-1]
        self.assertEqual(out.split("\t")[0], "E3")
        self.assertIn("another session made first", (project / "records" / "E2.md").read_text(encoding="utf-8"))
        bad = self.scratch / "record_body_bad.md"
        bad.write_text("no title line\n\n**Completed** 2026-01-02\n", encoding="utf-8")
        self.run_python(tool, str(bad), cwd=project, codes=(1,))
        self.assertFalse((project / "records" / "E4.md").exists())

    def test_generated_files_do_not_depend_on_the_host(self):
        # Trackers are generated on Windows and on macOS and travel between them through
        # cloud sync, so their bytes must not record which host wrote them. Two ways they
        # used to: line endings left to the OS default, and an interpreter name baked into
        # the text (Windows `python3` is a Store stub, macOS `python` is a shell alias).
        project = self.create_project("host independent output")
        body = self.scratch / "host_independent_body.md"
        body.write_text(
            """# E? — line ending check

**Completed** 2026-01-02
**Target** `intro.md` ¶1
**Status** confirmed

Body.
""",
            encoding="utf-8",
        )
        self.run_python(project / "tools" / "new_record.py", str(body), cwd=project)
        self.run_python(project / "tools" / "index_records.py", cwd=project)
        self.run_python(project / "tools" / "tidy_tracker.py", "--apply",
                        cwd=project, codes=(0, 1))

        produced = [p for p in project.rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts]
        crlf = sorted(p.relative_to(project).as_posix()
                      for p in produced if b"\r\n" in p.read_bytes())
        self.assertEqual(crlf, [], "line endings of generated files must be fixed to LF")

        for path in sorted(p for p in produced if p.suffix == ".md"):
            text = path.read_text(encoding="utf-8")
            name = path.relative_to(project).as_posix()
            for baked in ("python tools", "python3 tools",
                          "python -X utf8 tools", "python3 -X utf8 tools"):
                self.assertNotIn(baked, text, "%s has an interpreter name baked in: %s" % (name, baked))
            if "<py>" in text:
                # A file that uses the placeholder must also say what to substitute.
                self.assertIn("`python3` on macOS", text, "%s does not explain `<py>`" % name)

    def test_guard_hook_denies_overwrite_of_existing_record(self):
        # new-manuscript installs the PreToolUse hook; it denies Write on an existing
        # record or the generated index, and stays silent for new or unrelated files.
        project = self.create_project("overwrite blocked")
        hook = project / ".claude" / "hooks" / "guard_write.py"
        self.assertTrue(hook.is_file())
        settings = json.loads((project / ".claude" / "settings.json").read_text(encoding="utf-8"))
        command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertIn("guard_write.py", command)
        self.assertEqual(settings["hooks"]["PreToolUse"][0]["matcher"], "Edit|Write|Bash|PowerShell")
        self.assertIn("PostToolUse", settings["hooks"])
        records = project / "records"
        (records / "E1.md").write_text("# E1 — existing item\n", encoding="utf-8")

        def run(path, tool_name="Write"):
            payload = json.dumps({"tool_name": tool_name, "cwd": str(project),
                                  "tool_input": {"file_path": str(path)}})
            env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project))
            return subprocess.run(
                [sys.executable, "-X", "utf8", str(hook)], input=payload, cwd=project,
                capture_output=True, text=True, encoding="utf-8", timeout=30, env=env,
            )

        denied = run(records / "E1.md")
        self.assertEqual(denied.returncode, 0, denied.stderr)
        decision = json.loads(denied.stdout)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("E1.md", decision["permissionDecisionReason"])
        index = run(project / "tracker_records_index.md")
        self.assertEqual(json.loads(index.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        for allowed in (run(records / "E2.md"), run(project / "CLAUDE.md"), run(records / "E1.md", "Edit")):
            self.assertEqual((allowed.returncode, allowed.stdout.strip()), (0, ""), allowed.stderr)

    def test_skill_reference_paths_exist(self):
        for skill in SKILLS.glob("*/SKILL.md"):
            body = skill.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", body):
                if "://" not in target:
                    self.assertTrue((skill.parent / target.split("#")[0]).is_file(), (skill, target))
        workflow = SKILLS / "manuscript-workflow"
        for target in re.findall(r"`(references/[^`]+\.md)`", (workflow / "SKILL.md").read_text(encoding="utf-8")):
            self.assertTrue((workflow / target).is_file(), target)
        self.assertTrue((SKILLS / "new-manuscript" / "tools" / "_config.py").is_file())


if __name__ == "__main__":
    unittest.main()
