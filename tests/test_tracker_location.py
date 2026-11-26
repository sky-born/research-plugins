"""Location grammar (_location.py) · record index · location table · focus · new-record check · update tool · preview — checked with synthetic fixtures.

Fixtures are built in the OS temp folder (journal and dissertation kinds); no research files are touched. This suite does not
delete project files or delete recursively. The expected rows follow the samples of the documentation
(`tracker-workflow.md` "Target and location syntax").
"""

from __future__ import annotations

import hashlib
import importlib
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
TOOLS = SKILL / "tools"
INITIALIZER = SKILL / "init_manuscript.py"
UPDATE = SKILL / "update_tools.py"
PY = [sys.executable, "-X", "utf8", "-B"]

sys.path.insert(0, str(TOOLS))
_config = importlib.import_module("_config")
_location = importlib.import_module("_location")


SYNC_STATE = Path(tempfile.mkdtemp(prefix="tracker-sync-state-"))
os.environ.setdefault("SYNC_STATE_HOME", str(SYNC_STATE))     # sync state goes to a temp folder, not the real home


def run(cmd, cwd, codes=(0,)):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode in codes, f"{cmd}\n{r.stdout}\n{r.stderr}"
    return r


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def snapshot(project: Path):
    return {p.relative_to(project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in project.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def set_cfg(project: Path, **dotted):
    p = project / ".manuscript" / "project.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    for k, v in dotted.items():
        d = raw
        keys = k.split("__")
        for kk in keys[:-1]:
            d = d.setdefault(kk, {})
        d[keys[-1]] = v
    p.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Fixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = Path(tempfile.mkdtemp(prefix="tracker-location-"))
        # shared material in the folder above the project — for resolving `문헌인덱스/`. A Korean folder name on purpose: one location case
        # keeps a non-ASCII path, the rest of the fixtures use English names
        (cls.scratch / "문헌인덱스").mkdir()

    def journal(self, name: str) -> Path:
        p = self.scratch / name
        run(PY + [str(INITIALIZER), str(p), "--name", "Journal sample", "--kind", "journal",
                  "--source-dir", "manuscript", "--chapters", "intro.md", "experimental.md", "results.md",
                  "--references", "references.md"], cwd=self.scratch)
        for f in ("notes/README.md", "notes/results.md", "notes/intro.md", "notes/experimental.md", "README.md"):
            write(p / "manuscript" / f, "@NOTE sample\n")
        write(p / "README.md", "sample\n")
        write(p / "figures" / "INDEX.md", "| figure |\n")
        write(p / "archive" / "CHECKPOINT_log.md", "old log\n")
        write(p / "research" / "CHECKPOINT.md", "handover\n")
        write(p / "research" / "README.md", "research\n")
        write(p / "journal_manuscript_v28.docx", "")
        (p / "records" / "snapshots").mkdir(parents=True, exist_ok=True)
        set_cfg(p, tracker__record_index_exclude=["archive/", "research/CHECKPOINT.md"],
                manuscript__output_pattern="journal_manuscript_v*.docx")
        return p

    def dissertation(self, name: str) -> Path:
        p = self.scratch / name
        run(PY + [str(INITIALIZER), str(p), "--name", "Dissertation sample", "--kind", "dissertation",
                  "--source-dir", "manuscript_src", "--chapters", "ch1.md", "ch2.md", "ch3.md", "ch4.md", "ch5.md",
                  "--references", "references.md", "--build-script", "build_tpl.py"], cwd=self.scratch)
        write(p / "manuscript_src" / "build_tpl.py", "APPROVE_DATE = ''\n")
        write(p / "manuscript_src" / "fig_src" / "C3_F11_shear.png", "")
        write(p / "figures" / "INDEX.md", "| figure |\n")
        (p / "records" / "snapshots").mkdir(parents=True, exist_ok=True)
        set_cfg(p, tracker__record_index_exclude=["archive/"],
                manuscript__output_pattern="dissertation_draft_v*.docx")
        return p

    @staticmethod
    def grammar(project: Path):
        return _location.Grammar(_config.load(str(project)))

    @staticmethod
    def rows(g, text):
        p = g.parse(text)
        return {g.display(path): secs for path, secs in p.files.items()}, p


# ---------------------------------------------------------------- location grammar
class GrammarTests(Fixtures):
    def test_journal_expected_rows(self):
        g = self.grammar(self.journal("grammar journal"))
        cases = {
            "`manuscript/results.md` ③ · ④b · `figures/INDEX.md`":
                {"results.md": ["③", "④b"], "figures/INDEX.md": []},
            "`manuscript/results.md ③`":                                    # path + section inside one pair of backticks
                {"results.md": ["③"]},
            "`manuscript/notes/intro.md` ① · notes `README.md` · `experimental.md`":   # the folder of the preceding path is the base
                {"notes/intro.md": ["①"], "notes/README.md": [], "notes/experimental.md": []},
            "`manuscript/` 3 files (`intro.md` new · `results.md`) · `CLAUDE.md` 「Raw data location」「Layout」":
                {"manuscript/": [], "intro.md": [], "results.md": [], "CLAUDE.md": ["「Raw data location」", "「Layout」"]},
            "`manuscript/results.md` ④ → ④a · ④b · formerly Figure 3–10 → 4–11":    # a range keeps the number only
                {"results.md": ["④", "④a", "④b", "Figure 3–10"]},
            "`manuscript/experimental.md` ¶4 · see also `manuscript/results.md` ⑨a · ⑨b · Figure 5 · 6":
                {"experimental.md": ["¶4"], "results.md": ["⑨a", "⑨b", "Figure 5", "Figure 6"]},
            "`manuscript/results.md` ⑪–⑮ · `intro.md` ¶1–¶6":
                {"results.md": ["⑪–⑮"], "intro.md": ["¶1–¶6"]},
            "`manuscript/results.md` Figs. 3 and 4 · Fig. 1 caption · Table 1":
                {"results.md": ["Figure 3", "Figure 4", "Figure 1", "Table 1"]},
            "`manuscript/intro.md` ¶1 · 2026-09-30 · 3.2.1":                 # four-digit and dotted numbers are not inherited
                {"intro.md": ["¶1"]},
            "`../문헌인덱스/` · 문헌인덱스/":                                   # a path outside · resolved in the parent folder (Korean name on purpose)
                {"../문헌인덱스/": []},
            "`../CLAUDE.md` · `CLAUDE.md` · 「Raw data location」":          # a path outside does not become the base of a bare name after it
                {"../CLAUDE.md": [], "CLAUDE.md": ["「Raw data location」"]},
            "`manuscript/notes/*.md` · `manuscript/results.md` ①·⑬(applied) · ②·caption":
                {"notes/*.md": [], "results.md": ["①", "⑬", "②"]},
            "`manuscript/README.md` · `manuscript/results.md`":              # when the same name exists at the root too, the root wins
                {"manuscript/README.md": [], "results.md": []},
        }
        for text, want in cases.items():
            got, _ = self.rows(g, text)
            self.assertEqual(got, want, text)

    def test_journal_free_text_orphans_unresolved(self):
        g = self.grammar(self.journal("grammar journal special"))
        p = g.parse("all")
        self.assertEqual((p.free_text, p.files, p.orphans, p.empty), ("all", {}, [], False))
        self.assertEqual(g.parse("all chapters (style)").free_text, "all chapters (style)")
        self.assertTrue(g.parse("").empty)
        p = g.parse("③ · ④b")                                   # a section mark without a file — a warning case
        self.assertEqual((p.orphans, dict(p.files), p.free_text), (["③", "④b"], {}, None))
        p = g.parse("`phrase-index/` · `zzz_missing.md`")           # a name that could not be confirmed — kept as written, not a warning
        self.assertEqual(p.unresolved, ["phrase-index/", "zzz_missing.md"])
        self.assertEqual(p.kinds["phrase-index/"], "asis")
        p = g.parse("`@FIG imc_topview.png`(Figure 3) · `manuscript/results.md` ④b")   # backticks that start with @ are ignored
        self.assertEqual({g.display(k): v for k, v in p.files.items()}, {"results.md": ["④b"]})
        self.assertEqual(p.orphans, ["Figure 3"])

    def test_dissertation_expected_rows(self):
        g = self.grammar(self.dissertation("grammar dissertation"))
        cases = {
            "ch2.md §2.9.1, ch3.md §3.2.9, ch4.md §4.1, ch4.md §4.2.4, build_tpl.py `abstract_src`, CLAUDE.md §6":
                {"ch2.md": ["§2.9.1"], "ch3.md": ["§3.2.9"], "ch4.md": ["§4.1", "§4.2.4"],
                 "build_tpl.py": ["abstract_src"], "CLAUDE.md": ["§6"]},
            "`build_tpl.py` `APPROVE_DATE`": {"build_tpl.py": ["APPROVE_DATE"]},
            "`build_tpl.py` `SEQ`/`REF` (fields)": {"build_tpl.py": ["SEQ", "REF"]},
            "`build_tpl.py` tail (the block of `_Toc_ch5`)": {"build_tpl.py": ["tail"]},
            "`build_tpl.py` `pf()` = `PAGEREF` field": {"build_tpl.py": ["pf"]},
            "`build_tpl.py` tail (block) / `abstract_src`": {"build_tpl.py": ["tail", "abstract_src"]},
            "`manuscript_src/build_tpl.py` `image_para()`·`data_table()`": {"build_tpl.py": ["image_para", "data_table"]},
            # after a code file, plain words without backticks count only as list items — English prose is not taken for identifiers
            "`build_tpl.py` tail block (`_Toc_ch5`)": {"build_tpl.py": []},
            "`build_tpl.py` `SEQ`/`REF` fields": {"build_tpl.py": ["SEQ", "REF"]},
            "`build_tpl.py` `abstract_src` and the caption text": {"build_tpl.py": ["abstract_src"]},
            "`build_tpl.py` COVER_YEAR · cover · submission_form · tail": {"build_tpl.py": ["COVER_YEAR", "cover", "submission_form", "tail"]},
            "`build_tpl.py` `Chapter.fixed_size` · `report()`": {"build_tpl.py": ["Chapter.fixed_size", "report"]},
            "`build_tpl.py` (new) · plugin `research-writing` 0.6.1": {"build_tpl.py": []},
            "ch3.md §3.2.1, ch3.md §3.3 (chapter summary), Figure 3-2 caption":   # chapter-numbered figures
                {"ch3.md": ["§3.2.1", "§3.3", "Figure 3-2"]},
            "`figures/INDEX.md` Figure 3-4 row · Figure 4-3 · 4-10":            # continuing chapter numbers
                {"figures/INDEX.md": ["Figure 3-4", "Figure 4-3", "Figure 4-10"]},
            "`ch4.md` §4.2.6–§4.2.10": {"ch4.md": ["§4.2.6–§4.2.10"]},
            "`ch4.md` §4.2.6-§4.2.10": {"ch4.md": ["§4.2.6–§4.2.10"]},           # a hyphen is a range only when both sides are complete
            "ch4.md §4.2.7 (¶3 new at line 101 — after the Figure 4-10 caption at line 99, before the §4.2.8 title)":
                {"ch4.md": ["§4.2.7", "¶3", "Figure 4-10", "§4.2.8"]},
            "`manuscript_src/ch*.md`": {"ch*.md": []},
            "`ch*.md`": {"ch*.md": []},
            "`manuscript_src/fig_src` Figure 4-3 (two files) · `fig_src/`": {"fig_src/": ["Figure 4-3"]},
            "all chapters (style)": {},
        }
        for text, want in cases.items():
            got, _ = self.rows(g, text)
            self.assertEqual(got, want, text)
        # a glob or folder gives the same key however it is written
        self.assertEqual(list(g.parse("`manuscript_src/ch*.md`").files), list(g.parse("`ch*.md`").files))
        self.assertEqual(list(g.parse("`manuscript_src/fig_src`").files), list(g.parse("`fig_src/`").files))

    # ---- old-format values on purpose: the migration never rewrites values, so the `Location` cells and record targets of projects made
    # before 0.14 keep their Korean prose and folder names forever, and the grammar must keep reading them. Korean words also end an
    # identifier chain after a code file, which English words do not (see the cases above, written with parentheses).
    def test_old_korean_location_values_journal(self):
        p = self.journal("grammar journal old values")
        for f in ("README.md", "results.md", "intro.md", "experimental.md"):
            write(p / "manuscript" / "노트" / f, "@NOTE sample\n")
        write(p / "도판소스" / "INDEX.md", "| figure |\n")
        g = self.grammar(p)
        cases = {
            "`manuscript/results.md` ③ · ④b · `도판소스/INDEX.md`":
                {"results.md": ["③", "④b"], "도판소스/INDEX.md": []},
            "`manuscript/노트/intro.md` ① · 노트 `README.md` · `experimental.md`":
                {"노트/intro.md": ["①"], "노트/README.md": [], "노트/experimental.md": []},
            "`manuscript/` 3 파일 (`intro.md` 신설 · `results.md`) · `CLAUDE.md` 「원자료 위치」「구성」":
                {"manuscript/": [], "intro.md": [], "results.md": [], "CLAUDE.md": ["「원자료 위치」", "「구성」"]},
            "`manuscript/results.md` ④ → ④a · ④b · 종전 Figure 3–10 → 4–11":
                {"results.md": ["④", "④a", "④b", "Figure 3–10"]},
            "`manuscript/experimental.md` ¶4 · 함께 볼 곳 `manuscript/results.md` ⑨a · ⑨b · Figure 5 · 6":
                {"experimental.md": ["¶4"], "results.md": ["⑨a", "⑨b", "Figure 5", "Figure 6"]},
            "`manuscript/results.md` Figs. 3 and 4 · Fig. 1 캡션 · Table 1":
                {"results.md": ["Figure 3", "Figure 4", "Figure 1", "Table 1"]},
            "`manuscript/노트/*.md` · `manuscript/results.md` ①·⑬(반영) · ②·캡션":
                {"노트/*.md": [], "results.md": ["①", "⑬", "②"]},
        }
        for text, want in cases.items():
            got, _ = self.rows(g, text)
            self.assertEqual(got, want, text)
        p = g.parse("전체")
        self.assertEqual((p.free_text, p.files, p.orphans, p.empty), ("전체", {}, [], False))
        self.assertEqual(g.parse("전 챕터 (문체)").free_text, "전 챕터 (문체)")
        self.assertEqual(g.parse("`표현색인/` · `zzz_없는파일.md`").unresolved, ["표현색인/", "zzz_없는파일.md"])

    def test_old_korean_location_values_dissertation(self):
        p = self.dissertation("grammar dissertation old values")
        write(p / "도판소스" / "INDEX.md", "| figure |\n")
        g = self.grammar(p)
        cases = {
            "`build_tpl.py` `SEQ`/`REF` 필드": {"build_tpl.py": ["SEQ", "REF"]},
            "`build_tpl.py` tail 블록 (`_Toc_ch5`)": {"build_tpl.py": ["tail"]},
            "`build_tpl.py` `pf()` = `PAGEREF` 필드": {"build_tpl.py": ["pf"]},
            "`build_tpl.py` tail 블록 / `abstract_src`": {"build_tpl.py": ["tail", "abstract_src"]},
            "ch3.md §3.2.1, ch3.md §3.3(장 요약), Figure 3-2 캡션": {"ch3.md": ["§3.2.1", "§3.3", "Figure 3-2"]},
            "`도판소스/INDEX.md` Figure 3-4 행 · Figure 4-3 · 4-10": {"도판소스/INDEX.md": ["Figure 3-4", "Figure 4-3", "Figure 4-10"]},
            "ch4.md §4.2.7 (¶3 101행 신설 — Figure 4-10 캡션 99행 뒤, §4.2.8 제목 앞)": {"ch4.md": ["§4.2.7", "¶3", "Figure 4-10", "§4.2.8"]},
            "`manuscript_src/fig_src` Figure 4-3 파일 2개 · `fig_src/`": {"fig_src/": ["Figure 4-3"]},
            "전 챕터 (문체)": {},
        }
        for text, want in cases.items():
            got, _ = self.rows(g, text)
            self.assertEqual(got, want, text)

    def test_sort_order(self):
        g = self.grammar(self.dissertation("sort order"))
        paths = ["zzz_none.md", "../문헌인덱스/", "CLAUDE.md", "manuscript_src/fig_src/", "manuscript_src/references.md",
                 "manuscript_src/ch5.md", "manuscript_src/ch1.md"]
        got = sorted(paths, key=lambda p: g.sort_key(p))
        self.assertEqual(got, ["manuscript_src/ch1.md", "manuscript_src/ch5.md", "manuscript_src/references.md", "manuscript_src/fig_src/",
                               "CLAUDE.md", "../문헌인덱스/", "zzz_none.md"])
        secs = ["abstract_src", "「section」", "Table 1", "Figure 3-2", "Figure 1", "§3.2.1", "¶2", "④b", "①", "", "⑪–⑮"]
        self.assertEqual(sorted(secs, key=_location.section_key),
                         ["", "①", "④b", "⑪–⑮", "¶2", "§3.2.1", "Figure 1", "Figure 3-2", "Table 1", "「section」", "abstract_src"])

    def test_excluder_matches_resolved_and_written_names(self):
        p = self.journal("exclusion")
        ex = _location.Excluder(_config.load(str(p)))
        for hit in ("archive/CHECKPOINT_log.md", "research/CHECKPOINT.md", "tracker_pending.md", "records/E1.md",
                    "records/", "journal_manuscript_v12.docx"):
            self.assertTrue(ex.hit(hit, hit), hit)
        for miss in ("research/README.md", "manuscript/results.md", "tracker_proposals.md", "figures/INDEX.md"):
            self.assertFalse(ex.hit(miss, miss), miss)
        self.assertTrue(ex.hit("zzz.md", "journal_manuscript_v9.docx"))     # also matched against the written name


# ---------------------------------------------------------------- record index · new-record check
class RecordIndexTests(Fixtures):
    def test_reverse_index_rows_and_state_heads(self):
        p = self.journal("record index")
        rec = p / "records"
        # E1–E3 and E7–E8 use the English labels and status words; E4–E6 are records written before 0.14 (Korean labels and
        # status words) — history is never rewritten, so the index reads both and keeps each status head as written.
        en = "# E{n} — item {n}\n\n**Completed** 2026-09-{d:02d}\n**Target** {tgt}\n**Status** {st}\n\nBody.\n"
        ko = "# E{n} — 항목 {n}\n\n**완료일** 2026-09-{d:02d}\n**대상** {tgt}\n**상태** {st}\n\n본문.\n"
        items = {
            1: (en, "`manuscript/results.md` ③ · `tracker_pending.md` A1", "confirmed — the user said 「good」"),
            2: (en, "`manuscript/results.md` ③ · ⑫b", "confirmed — the user said 「confirm」. **2026-09-24 partly refreshed [E5](E5.md)**"),
            3: (en, "`tracker_pending.md` A2 · `research/CHECKPOINT.md`", "closed"),
            4: (ko, "전체", "반영 (확정 대기)"),
            5: (ko, "`journal_manuscript_v12.docx` · `archive/old/`", "확정"),
            6: (ko, "`figures/INDEX.md` Figure 3 · `zzz_missing.md`", "대체됨 E2 (2026-09-15) — 다시 만듦"),
            7: (en, "`manuscript/intro.md` ¶1", "superseded by E2 (2026-09-17) — redone"),
            8: (en, "all", "applied (awaiting confirmation)"),
        }
        for n, (form, tgt, st) in items.items():
            write(rec / f"E{n}.md", form.format(n=n, d=10 + n, tgt=tgt, st=st))
        tool = p / "tools" / "index_records.py"
        run(PY + [str(tool)], cwd=p)
        idx = (p / "tracker_records_index.md").read_text(encoding="utf-8")
        for line in ("| File | Section | Item |",
                     "| `results.md` | ③ | E1 · E2 |",
                     "| `results.md` | ⑫b | E2 |",
                     "| `intro.md` | ¶1 | E7 |",
                     "| `figures/INDEX.md` | Figure 3 | E6 |",
                     "| `zzz_missing.md` | — | E6 |",
                     "| 전체 | — | E4 |",
                     "| all | — | E8 |",
                     "| (excluded files only) | — | E3 · E5 |",
                     "| ID | Item | Completed | Status |",
                     "| E1 | item 1 | 2026-09-11 | confirmed |",
                     "| E2 | item 2 | 2026-09-12 | confirmed · see E5 |",
                     "| E3 | item 3 | 2026-09-13 | closed |",
                     "| E4 | 항목 4 | 2026-09-14 | 반영 (확정 대기) |",
                     "| E5 | 항목 5 | 2026-09-15 | 확정 |",
                     "| E6 | 항목 6 | 2026-09-16 | 대체됨 E2 |",
                     "| E7 | item 7 | 2026-09-17 | superseded by E2 |",
                     "| E8 | item 8 | 2026-09-18 | applied (awaiting confirmation) |"):
            self.assertIn(line, idx, line)
        self.assertNotIn("| Target |", idx)
        for old in ("| 대상 |", "| 파일 | 절 |", "| ID | 항목 |", "(제외 파일만)", "관련 E5"):     # the old Korean spellings of generated text
            self.assertNotIn(old, idx, "generated headers, placeholders and the status suffix are English")
        self.assertNotIn("archive/", idx.split("## 2.")[0])
        first = (p / "tracker_records_index.md").read_bytes()
        run(PY + [str(tool)], cwd=p)
        self.assertEqual(first, (p / "tracker_records_index.md").read_bytes(), "two runs must give the same result")
        self.assertNotIn(b"\r\n", first)
        out = run(PY + [str(tool), "--check-targets"], cwd=p).stdout
        self.assertEqual(out, run(PY + [str(tool), "--검사"], cwd=p).stdout)   # the old (Korean) flag name still works
        self.assertIn("zzz_missing.md", out)
        self.assertIn("E3 · E5", out)

    def test_new_record_warns_on_bad_target_but_creates(self):
        p = self.journal("new record check")
        tool = p / "tools" / "new_record.py"
        body = self.scratch / "bad_target.md"
        write(body, "# E? — sections only\n\n**Completed** 2026-01-02\n**Target** ③ · ④b\n**Status** confirmed\n\nBody.\n")
        out = run(PY + [str(tool), str(body)], cwd=p).stdout
        self.assertIn("cannot parse the target", out)
        self.assertTrue((p / "records" / "E1.md").is_file())
        # the pre-0.14 Korean labels are still accepted — the target is found and checked the same way
        write(body, "# E? — a name not confirmed\n\n**완료일** 2026-01-02\n**대상** `zzz_missing.md` ③\n**상태** 확정\n\nBody.\n")
        out = run(PY + [str(tool), str(body)], cwd=p).stdout
        self.assertIn("names not confirmed", out)
        self.assertNotIn("cannot parse", out)
        self.assertNotIn("no **", out)
        write(body, "# E? — sound\n\n**Completed** 2026-01-02\n**Target** `manuscript/results.md` ③\n**Status** confirmed\n\nBody.\n")
        out = run(PY + [str(tool), str(body)], cwd=p).stdout
        self.assertNotIn("!", out.split("\n")[-2] if len(out.split("\n")) > 1 else out)
        self.assertTrue((p / "records" / "E3.md").is_file())


# ---------------------------------------------------------------- location table · focus · warnings
class TrackerTablesTests(Fixtures):
    HDR = "|---|---|---|---|---|---|\n"

    def add_rows(self, path: Path, rows: str):
        text = path.read_text(encoding="utf-8")
        self.assertIn(self.HDR, text)
        path.write_text(text.replace(self.HDR, self.HDR + rows, 1), encoding="utf-8")

    def test_location_table_focus_and_warnings_journal(self):
        p = self.journal("location table")
        trig = json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8"))["tracker"]["triggers"][1]
        self.add_rows(p / "tracker_pending.md",
                      f"| A1 | two sections | `manuscript/results.md` ③ · ④b | {trig} | waiting | |\n"
                      f"| A2 | a tracker folder as the location | `records/snapshots/` | {trig} | waiting | |\n"
                      f"| A3 | a scope word | all | {trig} | waiting | |\n"
                      f"| A4 | section only | ③ | {trig} | waiting | |\n"
                      f"| A5 | empty cell |  | {trig} | waiting | |\n"
                      f"| A6 | note file | `manuscript/notes/results.md` ① | {trig} | waiting | |\n")
        self.add_rows(p / "tracker_proposals.md", f"| H1 | proposal | `manuscript/results.md` ③ | {trig} | waiting | basis |\n")
        r = run(PY + [str(p / "tools" / "tidy_tracker.py"), "--focus", "ch3", "--apply"], cwd=p, codes=(0, 1))
        self.assertNotIn("Traceback", r.stderr)
        listing = (p / "tracker_index.md").read_text(encoding="utf-8")
        table = listing.split("<!-- location-table -->", 1)[1].split("<!-- /location-table -->", 1)[0]
        for line in ("| File | Section | Items |",
                     "| `results.md` | ③ | A1 · H1 |",
                     "| `results.md` | ④b | A1 |",
                     "| `records/snapshots/` | — | A2 |",
                     "| all | — | A3 |",
                     "| `notes/results.md` | ① | A6 |",
                     "| (no location) | — | A4 · A5 |"):
            self.assertIn(line, table, line)
        self.assertNotIn("…", table)
        focus = listing.split("<!-- focus -->", 1)[1].split("<!-- /focus -->", 1)[0]
        self.assertIn("**Working chapter** ch3", focus)
        self.assertIn("· items: 2", focus)
        for rid in ("A1", "H1"):
            self.assertIn(f"#### {rid} ", focus)
        self.assertNotIn("#### A6 ", focus, "a note file is not a chapter file")
        self.assertIn("A4: cannot parse the location", r.stdout)
        self.assertIn("A5: cannot parse the location", r.stdout)
        self.assertNotIn("A3: cannot parse the location", r.stdout)
        self.assertNotIn("A2: cannot parse the location", r.stdout)
        before = (p / "tracker_index.md").read_bytes()
        run(PY + [str(p / "tools" / "tidy_tracker.py"), "--apply"], cwd=p, codes=(0, 1))
        self.assertEqual(before, (p / "tracker_index.md").read_bytes(), "two runs must give the same result")

    def test_single_letter_table_keeps_old_ids(self):
        """A project reduced to the single letter A — the location table, archiving and archive-list blocks still work when old B and C IDs remain under the A section."""
        p = self.journal("single letter")
        trig = json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8"))["tracker"]["triggers"][1]
        pend = p / "tracker_pending.md"
        text = pend.read_text(encoding="utf-8")
        blocks = {c: re.search(r"<!-- archived-list:%s -->\n.*?<!-- /archived-list:%s -->" % (c, c), text, re.S).group(0) for c in "BCD"}
        for c in "BCD":                                                   # delete the B, C and D sections (heading through block)
            text, n = re.subn(r"\n## %s\. [^\n]*\n.*?<!-- /archived-list:%s -->\n" % (c, c), "\n", text, count=1, flags=re.S)
            self.assertEqual(n, 1, c)
        text = text.replace("<!-- /archived-list:A -->", "<!-- /archived-list:A -->\n" + "\n".join(blocks[c] for c in "BCD"), 1)
        pend.write_text(text, encoding="utf-8")                           # leave only the blocks under the A section
        self.add_rows(pend,
                      f"| A1 | the letter that stays | `manuscript/results.md` ③ | {trig} | waiting | |\n"
                      f"| B2 | old letter · open | `manuscript/intro.md` ¶1 | {trig} | waiting | |\n"
                      f"| C1 | old letter · closed | `manuscript/references.md` | {trig} | closed (2026-10-06) | |\n")
        r = run(PY + [str(p / "tools" / "tidy_tracker.py"), "--apply"], cwd=p, codes=(0, 1))
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("` block, so", r.stdout)
        listing = (p / "tracker_index.md").read_text(encoding="utf-8")
        table = listing.split("<!-- location-table -->", 1)[1].split("<!-- /location-table -->", 1)[0]
        self.assertIn("| `results.md` | ③ | A1 |", table)
        self.assertIn("| `intro.md` | ¶1 | B2 |", table, "an open row of an old letter is in the location table too")
        self.assertNotIn("C1", table)
        after = pend.read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^## ([A-Z])\. ", after, re.M), ["A"])
        self.assertNotIn("| C1 |", after)
        self.assertIn("| C1 |", (p / "records" / "archive.md").read_text(encoding="utf-8"))
        block_c = after.split("<!-- archived-list:C -->", 1)[1].split("<!-- /archived-list:C -->", 1)[0]
        self.assertIn("C1", block_c, "the archive trace line of an old letter")
        self.assertIn("1 completed or closed C items were moved to `records\\archive.md`", block_c)
        before = (p / "tracker_index.md").read_bytes()
        run(PY + [str(p / "tools" / "tidy_tracker.py"), "--apply"], cwd=p, codes=(0, 1))
        self.assertEqual(before, (p / "tracker_index.md").read_bytes(), "two runs must give the same result")

    def test_focus_ch5_and_symbol_rows_dissertation(self):
        p = self.dissertation("focus ch5")
        trig = json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8"))["tracker"]["triggers"][1]
        self.add_rows(p / "tracker_pending.md",
                      f"| A1 | fifth chapter | `manuscript_src/ch5.md` §5.1 | {trig} | waiting | |\n"
                      f"| A2 | symbol | `build_tpl.py` `APPROVE_DATE` | {trig} | waiting | |\n"
                      f"| A3 | two symbols | `build_tpl.py` `SEQ`/`REF` (fields) | {trig} | waiting | |\n"
                      f"| A4 | glob | `manuscript_src/ch*.md` | {trig} | waiting | |\n"
                      f"| A5 | short glob | `ch*.md` | {trig} | waiting | |\n")
        r = run(PY + [str(p / "tools" / "tidy_tracker.py"), "--focus", "ch5", "--apply"], cwd=p, codes=(0, 1))
        self.assertNotIn("Traceback", r.stderr)
        listing = (p / "tracker_index.md").read_text(encoding="utf-8")
        table = listing.split("<!-- location-table -->", 1)[1].split("<!-- /location-table -->", 1)[0]
        for line in ("| `ch5.md` | §5.1 | A1 |", "| `build_tpl.py` | APPROVE_DATE | A2 |",
                     "| `build_tpl.py` | REF | A3 |", "| `build_tpl.py` | SEQ | A3 |", "| `ch*.md` | — | A4 · A5 |"):
            self.assertIn(line, table, line)
        focus = listing.split("<!-- focus -->", 1)[1].split("<!-- /focus -->", 1)[0]
        self.assertIn("**Working chapter** ch5", focus)
        self.assertIn("#### A1 ", focus)
        self.assertNotIn("#### A2 ", focus)

    # ---- zero open items — with a sound table structure the blocks of the list are emptied; when rows could not be read (a format problem) the blocks and stamp are left as they are
    BLOCKS = ("location-table", "trigger-table", "now", "focus")
    SKIPPED = "No open items could be read"

    @classmethod
    def list_state(cls, p: Path):
        t = (p / "tracker_index.md").read_text(encoding="utf-8")
        out = {n: t.split(f"<!-- {n} -->", 1)[1].split(f"<!-- /{n} -->", 1)[0] for n in cls.BLOCKS}
        out["stamp"] = next(l for l in t.splitlines() if l.startswith("<!-- generated-stamp "))
        return out

    @staticmethod
    def tidy(p: Path, *args):
        return run(PY + [str(p / "tools" / "tidy_tracker.py"), *args], cwd=p, codes=(0, 1))

    @staticmethod
    def ack(p: Path):
        """Deleting or masking a row makes the sync check (S3 · S7) report an ERROR and the tidy tool refuse `--apply` — this imitates the user's confirmation."""
        run(PY + [str(p / "tools" / "check_sync.py"), "--quick"], cwd=p, codes=(0, 1, 2))
        run(PY + [str(p / "tools" / "check_sync.py"), "--ack", "test: fixture row edited"], cwd=p)

    @staticmethod
    def single_letter(p: Path):
        """Delete the B, C and D sections to leave one A table — the shape of a pending file with a single letter (blocks under the A section)."""
        pend = p / "tracker_pending.md"
        text = pend.read_text(encoding="utf-8")
        blocks = [re.search(r"<!-- archived-list:%s -->\n.*?<!-- /archived-list:%s -->" % (c, c), text, re.S).group(0) for c in "BCD"]
        for c in "BCD":
            text = re.sub(r"\n## %s\. [^\n]*\n.*?<!-- /archived-list:%s -->\n" % (c, c), "\n", text, count=1, flags=re.S)
        pend.write_text(text.replace("<!-- /archived-list:A -->", "<!-- /archived-list:A -->\n" + "\n".join(blocks), 1), encoding="utf-8")

    def zero_fixtures(self, tag: str):
        """(kind, project, location, focus chapter) — journal (one A table) · dissertation (four tables A–D, the initializer default)."""
        j = self.journal(f"zero_{tag}_journal")
        self.single_letter(j)
        d = self.dissertation(f"zero_{tag}_dissertation")
        return [("journal", j, "`manuscript/results.md` ③", "ch3"), ("dissertation", d, "`manuscript_src/ch3.md` §3.1", "ch3")]

    def test_zero_open_rows_rebuild_empty_blocks(self):
        """When the last open item is closed and archived and the remaining proposal is closed too, the blocks of the list are rebuilt as header only plus a notice and the stamp is made from the current sources."""
        for kind, p, loc, ch in self.zero_fixtures("closed"):
            with self.subTest(kind=kind):
                self.add_rows(p / "tracker_pending.md", f"| A1 | item to close | {loc} | now | waiting | |\n")
                self.add_rows(p / "tracker_proposals.md", f"| H1 | proposal to drop | {loc} | now | waiting | basis |\n")
                self.tidy(p, "--focus", ch, "--apply")
                before = self.list_state(p)
                for n in ("location-table", "now", "focus"):
                    self.assertIn("A1", before[n], n)
                for f, old, new in (("tracker_pending.md", "| now | waiting |", "| now | done (2026-10-12) |"),
                                    ("tracker_proposals.md", "| now | waiting |", "| now | closed (2026-10-12) |")):
                    text = (p / f).read_text(encoding="utf-8")
                    self.assertEqual(text.count(old), 1, f)
                    (p / f).write_text(text.replace(old, new), encoding="utf-8")
                r = self.tidy(p, "--apply")
                self.assertNotIn(self.SKIPPED, r.stdout)
                self.assertIn("Zero open items", r.stdout)
                self.assertIn("| A1 |", (p / "records" / "archive.md").read_text(encoding="utf-8"))
                after = self.list_state(p)
                self.assertEqual(after["location-table"].strip().splitlines(), ["| File | Section | Items |", "|---|---|---|"])
                self.assertEqual(after["trigger-table"].strip().splitlines(), ["| When this clears | Take up |", "|---|---|"])
                self.assertEqual(after["now"].strip(), "> No open items — the pending and proposals files have no open rows.")
                self.assertIn(f"**Working chapter** {ch}", after["focus"])
                self.assertIn("· items: 0", after["focus"])
                self.assertNotIn("####", after["focus"])
                ids, unknown = _config.list_block_ids((p / "tracker_index.md").read_text(encoding="utf-8"))
                self.assertEqual((sum(map(len, ids.values())), unknown), (0, []))
                self.assertNotEqual(after["stamp"], before["stamp"])
                r = run(PY + [str(p / "tools" / "check_sync.py"), "--quick"], cwd=p, codes=(0, 1))
                self.assertNotIn(" S3 ", r.stdout)
                self.assertNotIn(" S4 ", r.stdout)
                once = (p / "tracker_index.md").read_bytes()
                self.tidy(p, "--apply")
                self.assertEqual(once, (p / "tracker_index.md").read_bytes(), "two runs must give the same result")

    def test_unreadable_rows_keep_blocks_and_stamp(self):
        """When no open item could be read and the table structure is not sound (rows unreadable), only a warning is given and the blocks, the focus copy and the stamp are left as they are."""
        variants = [
            # (name, file to edit, text to replace, replacement, reason the warning must contain)
            ("decorated-id", "tracker_pending.md", "| A1 |", "| **A1** |", "were not read — pending"),
            ("header-changed", "tracker_pending.md", "| ID | Item |", "| No. | Item |", "pending category sections: no `| ID |` table header"),
            ("no-section", "tracker_pending.md", "\n## ", "\n### ", "the pending file has no category section (`## X.`"),
            ("split-row", "tracker_pending.md", "| A1 |", "A1 a row that lost its pipe |", "table row format defects — pending"),
            ("proposal-decorated-id", "tracker_proposals.md", "| H1 |", "| `H1` |", "were not read — proposals"),
        ]
        for name, f, old, new, why in variants:
            for kind, p, loc, ch in self.zero_fixtures(name):
                with self.subTest(kind=kind, variant=name):
                    row = (f"| H1 | remaining proposal | {loc} | now | waiting | basis |\n" if f == "tracker_proposals.md"
                           else f"| A1 | remaining item | {loc} | now | waiting | |\n")
                    self.add_rows(p / f, row)                # one row in that file only — the other is empty
                    self.tidy(p, "--focus", ch, "--apply")
                    before = self.list_state(p)
                    rid = row.split("|")[1].strip()
                    self.assertIn(rid, before["location-table"])
                    self.assertIn(f"#### {rid} ", before["focus"])
                    text = (p / f).read_text(encoding="utf-8")
                    self.assertIn(old, text)
                    (p / f).write_text(text.replace(old, new), encoding="utf-8")
                    self.ack(p)
                    r = self.tidy(p, "--apply")
                    self.assertIn(self.SKIPPED, r.stdout)
                    warn = next(l for l in r.stdout.splitlines() if self.SKIPPED in l)
                    self.assertIn(why, warn)
                    self.assertEqual(self.list_state(p), before, "a read failure must not change the blocks or the stamp")


# ---------------------------------------------------------------- update tool · preview · hash list
class UpdateToolsTests(Fixtures):
    def old_content(self, rel: str) -> bytes:
        """One old content from the canonical history that differs from the current one — oldest first (commits that renamed the file are skipped)."""
        cur = (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")
        commits = subprocess.run(["git", "log", "--format=%H", "--follow", "--", rel],
                                 cwd=ROOT, capture_output=True, text=True).stdout.split()
        for c in reversed(commits):
            r = subprocess.run(["git", "-c", "core.quotepath=false", "show", f"{c}:{rel}"], cwd=ROOT, capture_output=True)
            if r.returncode == 0 and r.stdout and r.stdout.replace(b"\r\n", b"\n") != cur:
                return r.stdout
        self.skipTest("no old version in the canonical history: " + rel)

    def test_check_apply_force_add_and_eol(self):
        p = self.journal("update-sample")
        r = run(PY + [str(UPDATE), str(p)], cwd=self.scratch)
        managed = json.loads((SKILL / "managed_files.json").read_text(encoding="utf-8"))["files"]
        self.assertEqual(len(re.findall(r"\ssame$", r.stdout, re.M)), len(managed) + 1, r.stdout)   # all managed files (managed_files.json) + hook registration
        self.assertIn("keys that rely on defaults", r.stdout)
        self.assertIn("manuscript.build_script", r.stdout)
        # locally modified · older canonical version · missing · line endings
        tool = p / "tools" / "index_records.py"
        tool.write_text(tool.read_text(encoding="utf-8") + "\n# local edit\n", encoding="utf-8")
        (p / "tools" / "_config.py").write_bytes(self.old_content("plugins/research-writing/skills/new-manuscript/tools/_config.py"))
        (p / "tools" / "_location.py").unlink()            # a required module — the other tools import it
        (p / "tools" / "grammar_baseline.py").unlink()     # an optional tool
        eol = p / "tools" / "check_numbers.py"
        eol.write_bytes(eol.read_bytes().replace(b"\n", b"\r\n"))
        r = run(PY + [str(UPDATE), str(p)], cwd=self.scratch, codes=(1,))
        self.assertIn("tools/index_records.py", r.stdout); self.assertIn("locally modified", r.stdout)
        self.assertIn("older canonical version", r.stdout)
        self.assertRegex(r.stdout, r"tools/_location\.py\s+missing")
        self.assertRegex(r.stdout, r"required\s+tools/_location\.py")
        self.assertRegex(r.stdout, r"tools/grammar_baseline\.py\s+missing")
        self.assertNotRegex(r.stdout, r"required\s+tools/grammar_baseline\.py")
        self.assertIn("same · line endings differ", r.stdout)
        # --apply alone: old versions and line endings are replaced and a missing required module is added;
        # locally modified files and other missing files stay
        r = run(PY + [str(UPDATE), str(p), "--apply"], cwd=self.scratch, codes=(1,))
        self.assertIn("kept", r.stdout)
        self.assertEqual((p / "tools" / "_config.py").read_bytes(), (TOOLS / "_config.py").read_bytes())
        self.assertNotIn(b"\r\n", eol.read_bytes())
        self.assertEqual((p / "tools" / "_location.py").read_bytes(), (TOOLS / "_location.py").read_bytes())
        self.assertFalse((p / "tools" / "grammar_baseline.py").exists())
        self.assertIn("# local edit", tool.read_text(encoding="utf-8"))
        # --force · --add
        r = run(PY + [str(UPDATE), str(p), "--apply", "--force", "tools/index_records.py", "--add", "tools/grammar_baseline.py"],
                cwd=self.scratch)
        self.assertIn("all same", r.stdout)
        backups = list((p / ".manuscript" / "tools_backup").rglob("index_records.py"))
        self.assertEqual(len(backups), 1)
        self.assertIn("# local edit", backups[0].read_text(encoding="utf-8"))
        self.assertEqual(tool.read_bytes(), (TOOLS / "index_records.py").read_bytes())
        self.assertTrue((p / "tools" / "grammar_baseline.py").is_file())
        # the settings file is not written
        self.assertNotIn("record_index_exclude_written", (p / ".manuscript" / "project.json").read_text(encoding="utf-8"))
        r = run(PY + [str(UPDATE), "--scan", str(self.scratch), "--depth", "1"], cwd=self.scratch, codes=(0, 1))
        self.assertIn("update-sample", r.stdout)

    def test_apply_adds_the_text_module_an_older_project_lacks(self):
        # a project made before tools/_textio.py existed: its _config.py does not import it and the file is not there
        p = self.journal("textio-sample")
        (p / "tools" / "_textio.py").unlink()
        (p / "tools" / "_config.py").write_bytes(self.old_content("plugins/research-writing/skills/new-manuscript/tools/_config.py"))
        r = run(PY + [str(UPDATE), str(p), "--apply"], cwd=self.scratch)
        self.assertIn("all same", r.stdout)
        self.assertEqual((p / "tools" / "_textio.py").read_bytes(), (TOOLS / "_textio.py").read_bytes())
        run(PY + [str(p / "tools" / "index_records.py")], cwd=p)        # the updated tools import it

    def test_hook_registration_ignores_status_messages(self):
        # statusMessage is display text: a project that still shows older wording is not a different registration
        p = self.journal("hook-status")
        settings = p / ".claude" / "settings.json"
        data = json.loads(settings.read_text(encoding="utf-8"))
        for entries in data["hooks"].values():
            for entry in entries:
                for hook in entry["hooks"]:
                    hook["statusMessage"] = "Checking shared-file writes (older wording)"
        settings.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        r = run(PY + [str(UPDATE), str(p)], cwd=self.scratch)
        self.assertRegex(r.stdout, r"hooks\s+same", r.stdout)
        data["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 99
        settings.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        r = run(PY + [str(UPDATE), str(p)], cwd=self.scratch, codes=(0, 1))
        self.assertRegex(r.stdout, r"hooks\s+differs", r.stdout)

    def test_preview_leaves_original_untouched(self):
        p = self.journal("preview")
        trig = json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8"))["tracker"]["triggers"][1]
        hdr = "|---|---|---|---|---|---|\n"
        pend = p / "tracker_pending.md"
        pend.write_text(pend.read_text(encoding="utf-8").replace(
            hdr, hdr + f"| A1 | item | `manuscript/results.md` ③ | {trig} | waiting | |\n", 1), encoding="utf-8")
        write(p / "records" / "E1.md", "# E1 — sample\n\n**Completed** 2026-01-01\n**Target** `manuscript/results.md` ③\n**Status** confirmed\n\nBody.\n")
        before = snapshot(p)
        r = run(PY + [str(ROOT / "scripts" / "preview_projects.py"), str(p), "--focus", "ch3",
                      "--set", 'tracker.record_index_exclude=["archive/"]'], cwd=ROOT)
        self.assertIn("same after two runs: yes", r.stdout)
        self.assertIn("tracker_records_index.md", r.stdout)
        self.assertEqual(before, snapshot(p), "the preview must not write to the original")

    def test_hash_list_is_fresh_and_manifest_is_the_source(self):
        manifest = json.loads((SKILL / "managed_files.json").read_text(encoding="utf-8"))
        hashes = json.loads((SKILL / "tool_hashes.json").read_text(encoding="utf-8"))
        self.assertEqual([m["src"] for m in manifest["files"]], list(hashes["files"]))
        for m in manifest["files"]:
            self.assertTrue((SKILL / m["src"]).is_file(), m["src"])
        r = run(PY + [str(ROOT / "scripts" / "tool_hashes.py"), "--check"], cwd=ROOT)
        self.assertIn("is current", r.stdout)


if __name__ == "__main__":
    unittest.main()
