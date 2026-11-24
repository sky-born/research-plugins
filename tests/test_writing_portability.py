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
        # 동기화 안전장치의 컴퓨터별 상태를 실제 홈(~/.claude/sync-state)이 아니라 임시 폴더에 둡니다.
        os.environ["SYNC_STATE_HOME"] = str(cls.scratch / "_sync-state")

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
        self.assertIn("E*.md 를 찾을 수 없습니다", result.stdout)
        self.assertIn("미결 항목 0건", result.stdout)
        self.assertNotIn("미결 항목을 하나도 읽지 못했습니다", result.stdout)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def create_project(self, dirname: str) -> Path:
        project = self.scratch / dirname
        self.run_python(
            INITIALIZER, str(project), "--name", "이식성 검증 원고",
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
        project = self.create_project("새 원고 공백 경로")
        cfg = json.loads((project / ".manuscript" / "project.json").read_text(encoding="utf-8"))
        self.assertTrue(cfg["markers"])
        for marker in cfg["markers"]:
            self.assertTrue((project / marker).is_file(), marker)
        agents = (project / "AGENTS.md").read_text(encoding="utf-8")
        shared = (project / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("`CLAUDE.md`", agents)
        self.assertIn("`procedure`", agents)
        self.assertIn("manuscript-workflow", agents)
        self.assertNotIn("## 도메인 근거 한계", agents)
        self.assertIn("## 도메인 근거 한계", shared)
        self.assertIn("이식성 검증 원고", shared)
        self.assertNotIn("C:\\Users\\", agents + shared)

    def test_repeat_initialization_preserves_user_edits_and_timestamps(self):
        project = self.create_project("사용자 수정 보존")
        for relative in ("AGENTS.md", "CLAUDE.md", "draft sources/intro.md"):
            path = project / relative
            with path.open("a", encoding="utf-8") as stream:
                stream.write("\n사용자가 추가한 문장 — 유지합니다.\n")
        before = self.snapshot(project)
        self.run_python(INITIALIZER, str(project), "--name", "변경하면 안 되는 이름")
        after = self.snapshot(project)
        # A different default source directory may add skeletons, but existing
        # files, including both instruction files, must remain byte-identical.
        for relative, signature in before.items():
            self.assertEqual(after[relative], signature, relative)

    def test_generated_tools_run_with_nondefault_paths(self):
        project = self.create_project("도구 실행")
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
        project = self.create_project("색인 제목")
        records = project / "records"
        records.mkdir(exist_ok=True)
        (records / "E1.md").write_text(
            "# E1 — 색인 제목 검증\n\n**완료일** 2026-01-01\n**대상** `intro.md` ¶1\n"
            "**상태** 반영 (확정 대기)\n\n## 발단\n\n검증용 항목입니다.\n",
            encoding="utf-8",
        )
        index = project / "tracker_records_index.md"
        tool = project / "tools" / "index_records.py"
        self.run_python(tool, cwd=project)
        self.assertTrue(
            index.read_text(encoding="utf-8").startswith("# 완료 기록 색인 — 이식성 검증 원고"),
            index.read_text(encoding="utf-8").splitlines()[0],
        )
        cfg_path = project / ".manuscript" / "project.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["project"] = "중간에 바꾼 이름"
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        self.run_python(tool, cwd=project)
        self.assertTrue(
            index.read_text(encoding="utf-8").startswith("# 완료 기록 색인 — 중간에 바꾼 이름"),
            index.read_text(encoding="utf-8").splitlines()[0],
        )

    def test_focus_resolves_chapter_number_to_mapped_file(self):
        # ch1 is mapped to intro.md by project.json; a pending item located at
        # "intro.md ¶1" must be picked up by --focus ch1 even though its location
        # key is the real file name rather than "ch1.md".
        project = self.create_project("포커스 매핑")
        cfg = json.loads((project / ".manuscript" / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["manuscript"]["chapters"][0]["file"], "intro.md")
        trigger = cfg["tracker"]["triggers"][0]
        pending = project / "tracker_pending.md"
        text = pending.read_text(encoding="utf-8")
        header = "|---|---|---|---|---|---|\n"
        self.assertIn(header, text)
        row = "| A1 | 포커스 검증 항목 | intro.md ¶1 | %s | 대기 | |\n" % trigger
        pending.write_text(text.replace(header, header + row, 1), encoding="utf-8")
        result = self.run_python(
            project / "tools" / "tidy_tracker.py", "--focus", "ch1", "--apply",
            cwd=project, codes=(0, 1),
        )
        self.assertNotIn("Traceback", result.stderr)
        listing = (project / "tracker_index.md").read_text(encoding="utf-8")
        block = listing.split("<!-- 포커스 -->", 1)[1].split("<!-- /포커스 -->", 1)[0]
        self.assertIn("**작업 중인 장** ch1", block)
        self.assertIn("1건", block)
        self.assertIn("A1", block)

    def test_closed_proposals_leave_the_generated_tables(self):
        # A discarded proposal has no archive path: the proposals file only marks it
        # `종결`. The tracker must drop it from the generated tables by status, while
        # open proposals and pending A-D rows stay listed.
        project = self.create_project("종결 제안")
        cfg = json.loads((project / ".manuscript" / "project.json").read_text(encoding="utf-8"))
        trigger = cfg["tracker"]["triggers"][1]
        header = "|---|---|---|---|---|---|\n"
        pending = project / "tracker_pending.md"
        text = pending.read_text(encoding="utf-8")
        row = "| A1 | 남는 대기 항목 | intro.md ¶1 | %s | 대기 | |\n" % trigger
        pending.write_text(text.replace(header, header + row, 1), encoding="utf-8")
        proposals = project / "tracker_proposals.md"
        text = proposals.read_text(encoding="utf-8")
        rows = ("| H1 | 버린 제안 | intro.md ¶1 | %s | 종결 | 버림 |\n"
                "| H2 | 남는 제안 | intro.md ¶2 | %s | 대기 | 검토 중 |\n") % (trigger, trigger)
        proposals.write_text(text.replace(header, header + rows, 1), encoding="utf-8")
        result = self.run_python(
            project / "tools" / "tidy_tracker.py", "--focus", "ch1", "--apply",
            cwd=project, codes=(0, 1),
        )
        self.assertNotIn("Traceback", result.stderr)
        listing = (project / "tracker_index.md").read_text(encoding="utf-8")
        for name in ("위치표", "트리거표", "포커스"):
            block = listing.split("<!-- %s -->" % name, 1)[1].split("<!-- /%s -->" % name, 1)[0]
            self.assertIn("A1", block, name)
            self.assertIn("H2", block, name)
            self.assertNotRegex(block, r"\bH1\b", name)
        # Closing is a status, not a move: the proposal stays in its own file.
        self.assertIn("| H1 | 버린 제안", proposals.read_text(encoding="utf-8"))

    def test_journal_numbering_is_flat_across_the_manuscript(self):
        # kind "journal" (the initializer's default) numbers figures, tables and
        # references once for the whole manuscript. `Fig.` and `Figs. 1 and 2` count
        # as citations; a caption line does not cite itself.
        project = self.create_project("저널 번호")
        src = project / "draft sources"
        tool = project / "tools" / "check_numbers.py"
        (src / "bib.md").write_text("@REF 1. 첫 문헌.\n\n@REF 2. 둘째 문헌.\n", encoding="utf-8")
        (src / "intro.md").write_text("접합부가 깨진다 [1]. Fig. 1 을 봅니다.\n", encoding="utf-8")
        results = ("@FIG a.png | Figure 1. 첫 그림.\n\n"
                   "Figs. 1 and 2 를 비교하고 [2] Table 1 에 정리합니다.\n\n"
                   "@FIG b.png | Figure 2. 둘째 그림.\n\n"
                   "@TAB t1 | Table 1. 값.\n")
        (src / "results.md").write_text(results, encoding="utf-8")
        out = self.run_python(tool, cwd=project).stdout
        self.assertIn("원고 전체 Figure 캡션 2건  OK", out)
        self.assertIn("원고 전체 Table  캡션 1건  OK", out)
        self.assertIn("최초 등장 순서 = 목록 번호 순서  OK (1–2)", out)
        self.assertIn("요약 — 정상입니다", out)
        # A figure named only by its own caption is uncited, and a reference cited
        # before a lower-numbered one breaks first-appearance order.
        (src / "intro.md").write_text("접합부가 깨진다 [2]. Fig. 1 을 봅니다 [1].\n", encoding="utf-8")
        (src / "results.md").write_text(results + "\n@FIG c.png | Figure 3. 셋째 그림.\n",
                                        encoding="utf-8")
        out = self.run_python(tool, cwd=project).stdout
        self.assertIn("본문에서 인용되지 않음 ['3']", out)
        self.assertIn("최초 등장 순서가 번호 순서를 거스릅니다", out)

    def test_dissertation_numbering_restarts_in_each_chapter(self):
        # kind "dissertation" keeps chapter numbering (Figure 2-1 restarts per chapter)
        # and still lists cross-chapter references. The caption-is-not-a-citation fix
        # applies here too, so an uncited figure is no longer hidden by its caption.
        project = self.scratch / "학위논문 번호"
        self.run_python(
            INITIALIZER, str(project), "--name", "학위논문 번호 검증", "--kind", "dissertation",
            "--source-dir", "draft sources", "--chapters", "ch1.md", "ch2.md",
            "--references", "bib.md",
        )
        src = project / "draft sources"
        (src / "ch1.md").write_text("@FIG a.png | Figure 1-1. 첫 그림.\n\nFigure 1-1 을 봅니다.\n",
                                    encoding="utf-8")
        (src / "ch2.md").write_text(
            "@FIG b.png | Figure 2-1. 인용되는 그림.\n\n"
            "Figure 2-1 과 Fig. 1-1 을 비교합니다.\n\n"
            "@FIG c.png | Figure 2-2. 인용되지 않는 그림.\n",
            encoding="utf-8",
        )
        out = self.run_python(project / "tools" / "check_numbers.py", cwd=project).stdout
        self.assertIn("ch1 Figure 캡션 1건  OK", out)
        self.assertIn("ch2 Figure 캡션 2건  OK", out)
        self.assertIn("본문에서 인용되지 않음 ['2-2']", out)
        self.assertIn("ch2 → FIG 1-1", out)

    def test_record_allocator_assigns_next_free_number_atomically(self):
        # The allocator, not the model, picks the record number; a number another
        # session took first is skipped, and a malformed body creates nothing.
        project = self.create_project("기록 번호 할당")
        tool = project / "tools" / "new_record.py"
        body = self.scratch / "record_body.md"
        body.write_text(
            "# E? — 할당 검증\n\n**완료일** 2026-01-02\n**대상** `intro.md` ¶1\n**상태** 확정\n\n본문 (E?).\n",
            encoding="utf-8",
        )
        out = self.run_python(tool, str(body), cwd=project).stdout.strip().splitlines()[-1]
        self.assertEqual(out.split("\t"), ["E1", "records/E1.md"])
        text = (project / "records" / "E1.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# E1 — 할당 검증"), text.splitlines()[0])
        self.assertIn("본문 (E1).", text)
        (project / "records" / "E2.md").write_text("# E2 — 다른 세션이 먼저 만든 항목\n", encoding="utf-8")
        out = self.run_python(tool, str(body), cwd=project).stdout.strip().splitlines()[-1]
        self.assertEqual(out.split("\t")[0], "E3")
        self.assertIn("다른 세션이 먼저", (project / "records" / "E2.md").read_text(encoding="utf-8"))
        bad = self.scratch / "record_body_bad.md"
        bad.write_text("제목 줄이 없음\n\n**완료일** 2026-01-02\n", encoding="utf-8")
        self.run_python(tool, str(bad), cwd=project, codes=(1,))
        self.assertFalse((project / "records" / "E4.md").exists())

    def test_generated_files_do_not_depend_on_the_host(self):
        # Trackers are generated on Windows and on macOS and travel between them through
        # cloud sync, so their bytes must not record which host wrote them. Two ways they
        # used to: line endings left to the OS default, and an interpreter name baked into
        # the text (Windows `python3` is a Store stub, macOS `python` is a shell alias).
        project = self.create_project("호스트 독립 생성물")
        body = self.scratch / "host_independent_body.md"
        body.write_text(
            """# E? — 줄끝 검증

**완료일** 2026-01-02
**대상** `intro.md` ¶1
**상태** 확정

본문.
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
        self.assertEqual(crlf, [], "생성물의 줄끝은 LF 로 고정돼야 합니다")

        for path in sorted(p for p in produced if p.suffix == ".md"):
            text = path.read_text(encoding="utf-8")
            name = path.relative_to(project).as_posix()
            for baked in ("python tools", "python3 tools",
                          "python -X utf8 tools", "python3 -X utf8 tools"):
                self.assertNotIn(baked, text, "%s 에 실행기 이름이 박혔습니다: %s" % (name, baked))
            if "<py>" in text:
                # A file that uses the placeholder must also say what to substitute.
                self.assertIn("맥 `python3`", text, "%s 가 `<py>` 를 설명하지 않습니다" % name)

    def test_guard_hook_denies_overwrite_of_existing_record(self):
        # new-manuscript installs the PreToolUse hook; it denies Write on an existing
        # record or the generated index, and stays silent for new or unrelated files.
        project = self.create_project("덮어쓰기 차단")
        hook = project / ".claude" / "hooks" / "guard_write.py"
        self.assertTrue(hook.is_file())
        settings = json.loads((project / ".claude" / "settings.json").read_text(encoding="utf-8"))
        command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertIn("guard_write.py", command)
        self.assertEqual(settings["hooks"]["PreToolUse"][0]["matcher"], "Edit|Write|Bash|PowerShell")
        self.assertIn("PostToolUse", settings["hooks"])
        records = project / "records"
        (records / "E1.md").write_text("# E1 — 기존 항목\n", encoding="utf-8")

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
