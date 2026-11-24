"""위치 문법(_location.py) · 완료 색인 · 위치 표 · 포커스 · 새 기록 검사 · 갱신 도구 · 미리보기 — 합성 표본으로 검증합니다.

표본은 OS 임시 폴더에 만들고(저널형 · 학위논문형), 연구 파일은 건드리지 않습니다. 이 스위트는 프로젝트 파일을
지우거나 재귀 삭제하지 않습니다. 기대 행은 한 저널 원고 프로젝트의 색인 생성기 계획(2026-09-30, W1)의
표본 문자열과 같습니다 — 문서(tracker-workflow.md 「대상 · 위치 문법」)의 예시와도 같게 둡니다.
"""

from __future__ import annotations

import hashlib
import importlib
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
INITIALIZER = SKILL / "init_manuscript.py"
UPDATE = SKILL / "update_tools.py"
PY = [sys.executable, "-X", "utf8", "-B"]

sys.path.insert(0, str(TOOLS))
_config = importlib.import_module("_config")
_location = importlib.import_module("_location")


SYNC_STATE = Path(tempfile.mkdtemp(prefix="tracker-sync-state-"))
os.environ.setdefault("SYNC_STATE_HOME", str(SYNC_STATE))     # 동기화 상태를 실제 홈이 아니라 임시 폴더에


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
        (cls.scratch / "문헌인덱스").mkdir()          # 프로젝트 상위 폴더의 공유 자료 — `문헌인덱스/` 해석용

    def journal(self, name: str) -> Path:
        p = self.scratch / name
        run(PY + [str(INITIALIZER), str(p), "--name", "저널 표본", "--kind", "journal",
                  "--source-dir", "manuscript", "--chapters", "intro.md", "experimental.md", "results.md",
                  "--references", "references.md"], cwd=self.scratch)
        for f in ("노트/README.md", "노트/results.md", "노트/intro.md", "노트/experimental.md", "README.md"):
            write(p / "manuscript" / f, "@NOTE 표본\n")
        write(p / "README.md", "표본\n")
        write(p / "도판소스" / "INDEX.md", "| 도판 |\n")
        write(p / "archive" / "CHECKPOINT_로그.md", "옛 로그\n")
        write(p / "조사" / "CHECKPOINT.md", "인수인계\n")
        write(p / "조사" / "README.md", "조사\n")
        write(p / "journal_manuscript_v28.docx", "")
        (p / "records" / "스냅샷").mkdir(parents=True, exist_ok=True)
        set_cfg(p, tracker__record_index_exclude=["archive/", "조사/CHECKPOINT.md"],
                manuscript__output_pattern="journal_manuscript_v*.docx")
        return p

    def dissertation(self, name: str) -> Path:
        p = self.scratch / name
        run(PY + [str(INITIALIZER), str(p), "--name", "학위논문 표본", "--kind", "dissertation",
                  "--source-dir", "manuscript_src", "--chapters", "ch1.md", "ch2.md", "ch3.md", "ch4.md", "ch5.md",
                  "--references", "references.md", "--build-script", "build_tpl.py"], cwd=self.scratch)
        write(p / "manuscript_src" / "build_tpl.py", "APPROVE_DATE = ''\n")
        write(p / "manuscript_src" / "fig_src" / "C3_F11_shear.png", "")
        write(p / "도판소스" / "INDEX.md", "| 도판 |\n")
        (p / "records" / "스냅샷").mkdir(parents=True, exist_ok=True)
        set_cfg(p, tracker__record_index_exclude=["archive/"],
                manuscript__output_pattern="박사학위논문_초안_v*.docx")
        return p

    @staticmethod
    def grammar(project: Path):
        return _location.Grammar(_config.load(str(project)))

    @staticmethod
    def rows(g, text):
        p = g.parse(text)
        return {g.display(path): secs for path, secs in p.files.items()}, p


# ---------------------------------------------------------------- W1 위치 문법
class GrammarTests(Fixtures):
    def test_journal_expected_rows(self):
        g = self.grammar(self.journal("문법 저널"))
        cases = {
            "`manuscript/results.md` ③ · ④b · `도판소스/INDEX.md`":
                {"results.md": ["③", "④b"], "도판소스/INDEX.md": []},
            "`manuscript/results.md ③`":                                    # H9 — 백틱 안 「경로 + 절」
                {"results.md": ["③"]},
            "`manuscript/노트/intro.md` ① · 노트 `README.md` · `experimental.md`":   # 앞 경로의 폴더가 기준
                {"노트/intro.md": ["①"], "노트/README.md": [], "노트/experimental.md": []},
            "`manuscript/` 3 파일 (`intro.md` 신설 · `results.md`) · `CLAUDE.md` 「원자료 위치」「구성」":
                {"manuscript/": [], "intro.md": [], "results.md": [], "CLAUDE.md": ["「원자료 위치」", "「구성」"]},
            "`manuscript/results.md` ④ → ④a · ④b · 종전 Figure 3–10 → 4–11":    # E76 — 범위는 번호만
                {"results.md": ["④", "④a", "④b", "Figure 3–10"]},
            "`manuscript/experimental.md` ¶4 · 함께 볼 곳 `manuscript/results.md` ⑨a · ⑨b · Figure 5 · 6":   # A45
                {"experimental.md": ["¶4"], "results.md": ["⑨a", "⑨b", "Figure 5", "Figure 6"]},
            "`manuscript/results.md` ⑪–⑮ · `intro.md` ¶1–¶6":
                {"results.md": ["⑪–⑮"], "intro.md": ["¶1–¶6"]},
            "`manuscript/results.md` Figs. 3 and 4 · Fig. 1 캡션 · Table 1":
                {"results.md": ["Figure 3", "Figure 4", "Figure 1", "Table 1"]},
            "`manuscript/intro.md` ¶1 · 2026-09-30 · 3.2.1":                 # 네 자리 · 점 번호는 물려받지 않음
                {"intro.md": ["¶1"]},
            "`../문헌인덱스/` · 문헌인덱스/":                                   # 밖의 경로 · 상위 폴더 해석
                {"../문헌인덱스/": []},
            "`../CLAUDE.md` · `CLAUDE.md` · 「원자료 위치」":                 # A57 후속 — 밖의 경로는 뒤 맨 이름의 기준이 되지 않음(E28)
                {"../CLAUDE.md": [], "CLAUDE.md": ["「원자료 위치」"]},
            "`manuscript/노트/*.md` · `manuscript/results.md` ①·⑬(반영) · ②·캡션":
                {"노트/*.md": [], "results.md": ["①", "⑬", "②"]},
            "`manuscript/README.md` · `manuscript/results.md`":              # 같은 이름이 루트에도 있으면 루트 기준
                {"manuscript/README.md": [], "results.md": []},
        }
        for text, want in cases.items():
            got, _ = self.rows(g, text)
            self.assertEqual(got, want, text)

    def test_journal_free_text_orphans_unresolved(self):
        g = self.grammar(self.journal("문법 저널 특수"))
        p = g.parse("전체")
        self.assertEqual((p.free_text, p.files, p.orphans, p.empty), ("전체", {}, [], False))
        self.assertEqual(g.parse("전 챕터 (문체)").free_text, "전 챕터 (문체)")
        self.assertTrue(g.parse("").empty)
        p = g.parse("③ · ④b")                                   # 파일 없는 절 표기 — 경고 대상
        self.assertEqual((p.orphans, dict(p.files), p.free_text), (["③", "④b"], {}, None))
        p = g.parse("`표현색인/` · `zzz_없는파일.md`")               # 확인 못 한 이름 — 쓴 그대로, 경고 아님
        self.assertEqual(p.unresolved, ["표현색인/", "zzz_없는파일.md"])
        self.assertEqual(p.kinds["표현색인/"], "asis")
        p = g.parse("`@FIG imc_topview.png`(Figure 3) · `manuscript/results.md` ④b")   # @ 로 시작하는 백틱은 무시
        self.assertEqual({g.display(k): v for k, v in p.files.items()}, {"results.md": ["④b"]})
        self.assertEqual(p.orphans, ["Figure 3"])

    def test_dissertation_expected_rows(self):
        g = self.grammar(self.dissertation("문법 학위"))
        cases = {
            "ch2.md §2.9.1, ch3.md §3.2.9, ch4.md §4.1, ch4.md §4.2.4, build_tpl.py `abstract_src`, CLAUDE.md §6":   # E357
                {"ch2.md": ["§2.9.1"], "ch3.md": ["§3.2.9"], "ch4.md": ["§4.1", "§4.2.4"],
                 "build_tpl.py": ["abstract_src"], "CLAUDE.md": ["§6"]},
            "`build_tpl.py` `APPROVE_DATE`": {"build_tpl.py": ["APPROVE_DATE"]},
            "`build_tpl.py` `SEQ`/`REF` 필드": {"build_tpl.py": ["SEQ", "REF"]},
            "`build_tpl.py` tail 블록 (`_Toc_ch5`)": {"build_tpl.py": ["tail"]},
            "`build_tpl.py` `pf()` = `PAGEREF` 필드": {"build_tpl.py": ["pf"]},
            "`build_tpl.py` tail 블록 / `abstract_src`": {"build_tpl.py": ["tail", "abstract_src"]},
            "`manuscript_src/build_tpl.py` `image_para()`·`data_table()`": {"build_tpl.py": ["image_para", "data_table"]},
            "ch3.md §3.2.1, ch3.md §3.3(장 요약), Figure 3-2 캡션":              # E108 — 장-번호 도판
                {"ch3.md": ["§3.2.1", "§3.3", "Figure 3-2"]},
            "`도판소스/INDEX.md` Figure 3-4 행 · Figure 4-3 · 4-10":            # E315 · 이어지는 장-번호
                {"도판소스/INDEX.md": ["Figure 3-4", "Figure 4-3", "Figure 4-10"]},
            "`ch4.md` §4.2.6–§4.2.10": {"ch4.md": ["§4.2.6–§4.2.10"]},
            "`ch4.md` §4.2.6-§4.2.10": {"ch4.md": ["§4.2.6–§4.2.10"]},           # 하이픈은 양쪽이 온전할 때만 범위
            "ch4.md §4.2.7 (¶3 101행 신설 — Figure 4-10 캡션 99행 뒤, §4.2.8 제목 앞)":   # E251
                {"ch4.md": ["§4.2.7", "¶3", "Figure 4-10", "§4.2.8"]},
            "`manuscript_src/ch*.md`": {"ch*.md": []},
            "`ch*.md`": {"ch*.md": []},
            "`manuscript_src/fig_src` Figure 4-3 파일 2개 · `fig_src/`": {"fig_src/": ["Figure 4-3"]},
            "전 챕터 (문체)": {},
        }
        for text, want in cases.items():
            got, _ = self.rows(g, text)
            self.assertEqual(got, want, text)
        # 글롭 · 폴더는 쓴 모양이 달라도 같은 키
        self.assertEqual(list(g.parse("`manuscript_src/ch*.md`").files), list(g.parse("`ch*.md`").files))
        self.assertEqual(list(g.parse("`manuscript_src/fig_src`").files), list(g.parse("`fig_src/`").files))

    def test_sort_order(self):
        g = self.grammar(self.dissertation("정렬"))
        paths = ["zzz_없음.md", "../문헌인덱스/", "CLAUDE.md", "manuscript_src/fig_src/", "manuscript_src/references.md",
                 "manuscript_src/ch5.md", "manuscript_src/ch1.md"]
        got = sorted(paths, key=lambda p: g.sort_key(p))
        self.assertEqual(got, ["manuscript_src/ch1.md", "manuscript_src/ch5.md", "manuscript_src/references.md", "manuscript_src/fig_src/",
                               "CLAUDE.md", "../문헌인덱스/", "zzz_없음.md"])
        secs = ["abstract_src", "「절」", "Table 1", "Figure 3-2", "Figure 1", "§3.2.1", "¶2", "④b", "①", "", "⑪–⑮"]
        self.assertEqual(sorted(secs, key=_location.section_key),
                         ["", "①", "④b", "⑪–⑮", "¶2", "§3.2.1", "Figure 1", "Figure 3-2", "Table 1", "「절」", "abstract_src"])

    def test_excluder_matches_resolved_and_written_names(self):
        p = self.journal("제외")
        ex = _location.Excluder(_config.load(str(p)))
        for hit in ("archive/CHECKPOINT_로그.md", "조사/CHECKPOINT.md", "tracker_pending.md", "records/E1.md",
                    "records/", "journal_manuscript_v12.docx"):
            self.assertTrue(ex.hit(hit, hit), hit)
        for miss in ("조사/README.md", "manuscript/results.md", "tracker_proposals.md", "도판소스/INDEX.md"):
            self.assertFalse(ex.hit(miss, miss), miss)
        self.assertTrue(ex.hit("zzz.md", "journal_manuscript_v9.docx"))     # 쓴 이름에도 대조


# ---------------------------------------------------------------- W2 완료 색인 · W4 새 기록 검사
class RecordIndexTests(Fixtures):
    def test_reverse_index_rows_and_state_heads(self):
        p = self.journal("색인")
        rec = p / "records"
        items = {
            1: ("`manuscript/results.md` ③ · `tracker_pending.md` A1", "확정 — 사용자 「좋아」"),
            2: ("`manuscript/results.md` ③ · ⑫b", "확정 — 사용자 「확정」. **2026-09-24 부분 갱신 [E5](E5.md)**"),
            3: ("`tracker_pending.md` A2 · `조사/CHECKPOINT.md`", "종결"),
            4: ("전체", "반영 (확정 대기)"),
            5: ("`journal_manuscript_v12.docx` · `archive/정리/`", "확정"),
            6: ("`도판소스/INDEX.md` Figure 3 · `zzz_없는파일.md`", "대체됨 E2 (2026-09-15) — 다시 만듦"),
        }
        for n, (tgt, st) in items.items():
            write(rec / f"E{n}.md", f"# E{n} — 항목 {n}\n\n**완료일** 2026-09-{10 + n:02d}\n**대상** {tgt}\n**상태** {st}\n\n본문.\n")
        tool = p / "tools" / "index_records.py"
        run(PY + [str(tool)], cwd=p)
        idx = (p / "tracker_records_index.md").read_text(encoding="utf-8")
        for line in ("| 파일 | 절 | 항목 |",
                     "| `results.md` | ③ | E1 · E2 |",
                     "| `results.md` | ⑫b | E2 |",
                     "| `도판소스/INDEX.md` | Figure 3 | E6 |",
                     "| `zzz_없는파일.md` | — | E6 |",
                     "| 전체 | — | E4 |",
                     "| (제외 파일만) | — | E3 · E5 |",
                     "| ID | 항목 | 완료일 | 상태 |",
                     "| E2 | 항목 2 | 2026-09-12 | 확정 · 관련 E5 |",
                     "| E4 | 항목 4 | 2026-09-14 | 반영 (확정 대기) |",
                     "| E6 | 항목 6 | 2026-09-16 | 대체됨 E2 |"):
            self.assertIn(line, idx, line)
        self.assertNotIn("| 대상 |", idx)
        self.assertNotIn("archive/", idx.split("## 2.")[0])
        first = (p / "tracker_records_index.md").read_bytes()
        run(PY + [str(tool)], cwd=p)
        self.assertEqual(first, (p / "tracker_records_index.md").read_bytes(), "두 번 돌려도 같아야 합니다")
        self.assertNotIn(b"\r\n", first)
        out = run(PY + [str(tool), "--검사"], cwd=p).stdout
        self.assertIn("zzz_없는파일.md", out)
        self.assertIn("E3 · E5", out)

    def test_new_record_warns_on_bad_target_but_creates(self):
        p = self.journal("새항목 검사")
        tool = p / "tools" / "new_record.py"
        body = self.scratch / "bad_target.md"
        write(body, "# E? — 절만 적은 기록\n\n**완료일** 2026-01-02\n**대상** ③ · ④b\n**상태** 확정\n\n본문.\n")
        out = run(PY + [str(tool), str(body)], cwd=p).stdout
        self.assertIn("대상을 해석할 수 없습니다", out)
        self.assertTrue((p / "records" / "E1.md").is_file())
        write(body, "# E? — 확인 못 한 이름\n\n**완료일** 2026-01-02\n**대상** `zzz_없는파일.md` ③\n**상태** 확정\n\n본문.\n")
        out = run(PY + [str(tool), str(body)], cwd=p).stdout
        self.assertIn("확인하지 못한 이름", out)
        self.assertNotIn("해석할 수 없습니다", out)
        write(body, "# E? — 정상\n\n**완료일** 2026-01-02\n**대상** `manuscript/results.md` ③\n**상태** 확정\n\n본문.\n")
        out = run(PY + [str(tool), str(body)], cwd=p).stdout
        self.assertNotIn("!", out.split("\n")[-2] if len(out.split("\n")) > 1 else out)
        self.assertTrue((p / "records" / "E3.md").is_file())


# ---------------------------------------------------------------- W3 위치 표 · 포커스 · W4 경고
class TrackerTablesTests(Fixtures):
    HDR = "|---|---|---|---|---|---|\n"

    def add_rows(self, path: Path, rows: str):
        text = path.read_text(encoding="utf-8")
        self.assertIn(self.HDR, text)
        path.write_text(text.replace(self.HDR, self.HDR + rows, 1), encoding="utf-8")

    def test_location_table_focus_and_warnings_journal(self):
        p = self.journal("위치표")
        trig = json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8"))["tracker"]["triggers"][1]
        self.add_rows(p / "tracker_pending.md",
                      f"| A1 | 두 절 | `manuscript/results.md` ③ · ④b | {trig} | 대기 | |\n"
                      f"| A2 | 추적 파일이 위치 | `완료기록/스냅샷/` | {trig} | 대기 | |\n"
                      f"| A3 | 범위 낱말 | 전체 | {trig} | 대기 | |\n"
                      f"| A4 | 절만 | ③ | {trig} | 대기 | |\n"
                      f"| A5 | 빈 칸 |  | {trig} | 대기 | |\n"
                      f"| A6 | 노트 | `manuscript/노트/results.md` ① | {trig} | 대기 | |\n")
        self.add_rows(p / "tracker_proposals.md", f"| H1 | 제안 | `manuscript/results.md` ③ | {trig} | 대기 | 근거 |\n")
        r = run(PY + [str(p / "tools" / "tidy_tracker.py"), "--focus", "ch3", "--apply"], cwd=p, codes=(0, 1))
        self.assertNotIn("Traceback", r.stderr)
        listing = (p / "tracker_index.md").read_text(encoding="utf-8")
        table = listing.split("<!-- 위치표 -->", 1)[1].split("<!-- /위치표 -->", 1)[0]
        for line in ("| 파일 | 절 | 걸린 항목 |",
                     "| `results.md` | ③ | A1 · H1 |",
                     "| `results.md` | ④b | A1 |",
                     "| `완료기록/스냅샷/` | — | A2 |",
                     "| 전체 | — | A3 |",
                     "| `노트/results.md` | ① | A6 |",
                     "| (위치 미기재) | — | A4 · A5 |"):
            self.assertIn(line, table, line)
        self.assertNotIn("…", table)
        focus = listing.split("<!-- 포커스 -->", 1)[1].split("<!-- /포커스 -->", 1)[0]
        self.assertIn("**작업 중인 장** ch3", focus)
        self.assertIn("2건", focus)
        for rid in ("A1", "H1"):
            self.assertIn(f"#### {rid} ", focus)
        self.assertNotIn("#### A6 ", focus, "노트 파일은 장 파일이 아닙니다")
        self.assertIn("A4: 위치를 해석할 수 없습니다", r.stdout)
        self.assertIn("A5: 위치를 해석할 수 없습니다", r.stdout)
        self.assertNotIn("A3: 위치를", r.stdout)
        self.assertNotIn("A2: 위치를", r.stdout)
        before = (p / "tracker_index.md").read_bytes()
        run(PY + [str(p / "tools" / "tidy_tracker.py"), "--apply"], cwd=p, codes=(0, 1))
        self.assertEqual(before, (p / "tracker_index.md").read_bytes(), "두 번 돌려도 같아야 합니다")

    def test_single_letter_table_keeps_old_ids(self):
        """글자를 A 하나로 줄인 프로젝트 — 옛 B · C ID 가 A 절 아래 그대로 있어도 위치 표 · 이관 · 이관목록 블록이 돕니다."""
        import re
        p = self.journal("글자 하나")
        trig = json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8"))["tracker"]["triggers"][1]
        pend = p / "tracker_pending.md"
        text = pend.read_text(encoding="utf-8")
        blocks = {c: re.search(r"<!-- 이관목록:%s -->\n.*?<!-- /이관목록:%s -->" % (c, c), text, re.S).group(0) for c in "BCD"}
        for c in "BCD":                                                   # B · C · D 절(제목 ~ 블록)을 지우고
            text, n = re.subn(r"\n## %s\. [^\n]*\n.*?<!-- /이관목록:%s -->\n" % (c, c), "\n", text, count=1, flags=re.S)
            self.assertEqual(n, 1, c)
        text = text.replace("<!-- /이관목록:A -->", "<!-- /이관목록:A -->\n" + "\n".join(blocks[c] for c in "BCD"), 1)
        pend.write_text(text, encoding="utf-8")                           # 블록만 A 절 아래 남깁니다
        self.add_rows(pend,
                      f"| A1 | 남는 글자 | `manuscript/results.md` ③ | {trig} | 대기 | |\n"
                      f"| B2 | 옛 글자 · 열림 | `manuscript/intro.md` ¶1 | {trig} | 대기 | |\n"
                      f"| C1 | 옛 글자 · 닫힘 | `manuscript/references.md` | {trig} | 종결 (2026-10-06) | |\n")
        r = run(PY + [str(p / "tools" / "tidy_tracker.py"), "--apply"], cwd=p, codes=(0, 1))
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("블록이 없어", r.stdout)
        listing = (p / "tracker_index.md").read_text(encoding="utf-8")
        table = listing.split("<!-- 위치표 -->", 1)[1].split("<!-- /위치표 -->", 1)[0]
        self.assertIn("| `results.md` | ③ | A1 |", table)
        self.assertIn("| `intro.md` | ¶1 | B2 |", table, "옛 글자의 열린 행도 위치 표에")
        self.assertNotIn("C1", table)
        after = pend.read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^## ([A-Z])\. ", after, re.M), ["A"])
        self.assertNotIn("| C1 |", after)
        self.assertIn("| C1 |", (p / "records" / "archive.md").read_text(encoding="utf-8"))
        block_c = after.split("<!-- 이관목록:C -->", 1)[1].split("<!-- /이관목록:C -->", 1)[0]
        self.assertIn("C1", block_c, "옛 글자의 이관 흔적 줄")
        before = (p / "tracker_index.md").read_bytes()
        run(PY + [str(p / "tools" / "tidy_tracker.py"), "--apply"], cwd=p, codes=(0, 1))
        self.assertEqual(before, (p / "tracker_index.md").read_bytes(), "두 번 돌려도 같아야 합니다")

    def test_focus_ch5_and_symbol_rows_dissertation(self):
        p = self.dissertation("포커스 ch5")
        trig = json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8"))["tracker"]["triggers"][1]
        self.add_rows(p / "tracker_pending.md",
                      f"| A1 | 다섯째 장 | `manuscript_src/ch5.md` §5.1 | {trig} | 대기 | |\n"
                      f"| A2 | 심볼 | `build_tpl.py` `APPROVE_DATE` | {trig} | 대기 | |\n"
                      f"| A3 | 심볼 둘 | `build_tpl.py` `SEQ`/`REF` 필드 | {trig} | 대기 | |\n"
                      f"| A4 | 글롭 | `manuscript_src/ch*.md` | {trig} | 대기 | |\n"
                      f"| A5 | 글롭 짧게 | `ch*.md` | {trig} | 대기 | |\n")
        r = run(PY + [str(p / "tools" / "tidy_tracker.py"), "--focus", "ch5", "--apply"], cwd=p, codes=(0, 1))
        self.assertNotIn("Traceback", r.stderr)
        listing = (p / "tracker_index.md").read_text(encoding="utf-8")
        table = listing.split("<!-- 위치표 -->", 1)[1].split("<!-- /위치표 -->", 1)[0]
        for line in ("| `ch5.md` | §5.1 | A1 |", "| `build_tpl.py` | APPROVE_DATE | A2 |",
                     "| `build_tpl.py` | REF | A3 |", "| `build_tpl.py` | SEQ | A3 |", "| `ch*.md` | — | A4 · A5 |"):
            self.assertIn(line, table, line)
        focus = listing.split("<!-- 포커스 -->", 1)[1].split("<!-- /포커스 -->", 1)[0]
        self.assertIn("**작업 중인 장** ch5", focus)
        self.assertIn("#### A1 ", focus)
        self.assertNotIn("#### A2 ", focus)

    # ---- 미결 0건 — 표 구조가 정상이면 목록의 블록을 비우고, 행을 읽지 못했으면(형식 문제) 블록 · 스탬프를 그대로 둡니다
    BLOCKS = ("위치표", "트리거표", "지금", "포커스")
    SKIPPED = "미결 항목을 하나도 읽지 못했습니다"

    @classmethod
    def list_state(cls, p: Path):
        t = (p / "tracker_index.md").read_text(encoding="utf-8")
        out = {n: t.split(f"<!-- {n} -->", 1)[1].split(f"<!-- /{n} -->", 1)[0] for n in cls.BLOCKS}
        out["스탬프"] = next(l for l in t.splitlines() if l.startswith("<!-- 생성스탬프 "))
        return out

    @staticmethod
    def tidy(p: Path, *args):
        return run(PY + [str(p / "tools" / "tidy_tracker.py"), *args], cwd=p, codes=(0, 1))

    @staticmethod
    def ack(p: Path):
        """행을 지우거나 가리면 동기화 점검(S3 · S7)이 ERROR 를 내고 정리 도구가 `--apply` 를 거부합니다 — 사용자 확인을 흉내 냅니다."""
        run(PY + [str(p / "tools" / "check_sync.py"), "--quick"], cwd=p, codes=(0, 1, 2))
        run(PY + [str(p / "tools" / "check_sync.py"), "--ack", "시험: 표본 행을 고쳤음"], cwd=p)

    @staticmethod
    def single_letter(p: Path):
        """B · C · D 절을 지워 A 표 하나로 — 저널 원고 프로젝트의 대기 파일 모양(블록은 A 절 아래)."""
        import re
        pend = p / "tracker_pending.md"
        text = pend.read_text(encoding="utf-8")
        blocks = [re.search(r"<!-- 이관목록:%s -->\n.*?<!-- /이관목록:%s -->" % (c, c), text, re.S).group(0) for c in "BCD"]
        for c in "BCD":
            text = re.sub(r"\n## %s\. [^\n]*\n.*?<!-- /이관목록:%s -->\n" % (c, c), "\n", text, count=1, flags=re.S)
        pend.write_text(text.replace("<!-- /이관목록:A -->", "<!-- /이관목록:A -->\n" + "\n".join(blocks), 1), encoding="utf-8")

    def zero_fixtures(self, tag: str):
        """(종류, 프로젝트, 위치, 포커스 장) — 저널(A 표 하나 · 저널 원고 프로젝트 모양) · 학위논문(A–D 표 넷 · 초기화 기본)."""
        j = self.journal(f"영건_{tag}_저널")
        self.single_letter(j)
        d = self.dissertation(f"영건_{tag}_학위")
        return [("journal", j, "`manuscript/results.md` ③", "ch3"), ("dissertation", d, "`manuscript_src/ch3.md` §3.1", "ch3")]

    def test_zero_open_rows_rebuild_empty_blocks(self):
        """마지막 미결이 닫혀 이관되고 남은 제안도 종결되면 — 목록의 블록을 머리만 · 안내문으로 다시 만들고 스탬프를 지금 원본으로 찍습니다."""
        for kind, p, loc, ch in self.zero_fixtures("닫힘"):
            with self.subTest(kind=kind):
                self.add_rows(p / "tracker_pending.md", f"| A1 | 닫힐 항목 | {loc} | 지금 | 대기 | |\n")
                self.add_rows(p / "tracker_proposals.md", f"| H1 | 버릴 제안 | {loc} | 지금 | 대기 | 근거 |\n")
                self.tidy(p, "--focus", ch, "--apply")
                before = self.list_state(p)
                for n in ("위치표", "지금", "포커스"):
                    self.assertIn("A1", before[n], n)
                for f, old, new in (("tracker_pending.md", "| 지금 | 대기 |", "| 지금 | 완료 (2026-10-12) |"),
                                    ("tracker_proposals.md", "| 지금 | 대기 |", "| 지금 | 종결 (2026-10-12) |")):
                    text = (p / f).read_text(encoding="utf-8")
                    self.assertEqual(text.count(old), 1, f)
                    (p / f).write_text(text.replace(old, new), encoding="utf-8")
                r = self.tidy(p, "--apply")
                self.assertNotIn(self.SKIPPED, r.stdout)
                self.assertIn("미결 항목 0건", r.stdout)
                self.assertIn("| A1 |", (p / "records" / "archive.md").read_text(encoding="utf-8"))
                after = self.list_state(p)
                self.assertEqual(after["위치표"].strip().splitlines(), ["| 파일 | 절 | 걸린 항목 |", "|---|---|---|"])
                self.assertEqual(after["트리거표"].strip().splitlines(), ["| 조건이 풀리면 | 꺼낼 항목 |", "|---|---|"])
                self.assertEqual(after["지금"].strip(), "> 미결 항목이 없습니다 — 대기 · 제안 파일에 열린 행이 0건입니다.")
                self.assertIn(f"**작업 중인 장** {ch}", after["포커스"])
                self.assertIn("0건", after["포커스"])
                self.assertNotIn("####", after["포커스"])
                ids, unknown = _config.list_block_ids((p / "tracker_index.md").read_text(encoding="utf-8"))
                self.assertEqual((sum(map(len, ids.values())), unknown), (0, []))
                self.assertNotEqual(after["스탬프"], before["스탬프"])
                r = run(PY + [str(p / "tools" / "check_sync.py"), "--quick"], cwd=p, codes=(0, 1))
                self.assertNotIn(" S3 ", r.stdout)
                self.assertNotIn(" S4 ", r.stdout)
                once = (p / "tracker_index.md").read_bytes()
                self.tidy(p, "--apply")
                self.assertEqual(once, (p / "tracker_index.md").read_bytes(), "두 번 돌려도 같아야 합니다")

    def test_unreadable_rows_keep_blocks_and_stamp(self):
        """미결을 하나도 읽지 못했는데 표 구조가 정상이 아니면(행을 읽지 못함) — 경고만 하고 블록 · 포커스 사본 · 스탬프를 그대로 둡니다."""
        variants = [
            # (이름, 고칠 파일, 바꿀 글, 바꿀 것, 경고에 들 까닭)
            ("꾸민ID", "tracker_pending.md", "| A1 |", "| **A1** |", "읽지 못한 줄 — 대기"),
            ("머리바뀜", "tracker_pending.md", "| ID | 항목 |", "| 번호 | 항목 |", "대기 분류 절에 `| ID |` 표 머리가 없음"),
            ("절없음", "tracker_pending.md", "\n## ", "\n### ", "대기 파일에 분류 절(`## X.`"),
            ("쪼개진행", "tracker_pending.md", "| A1 |", "A1 파이프를 잃은 행 |", "표 행 형식 결함 — 대기"),
            ("제안꾸민ID", "tracker_proposals.md", "| H1 |", "| `H1` |", "읽지 못한 줄 — 제안"),
        ]
        for name, f, old, new, why in variants:
            for kind, p, loc, ch in self.zero_fixtures(name):
                with self.subTest(kind=kind, variant=name):
                    row = (f"| H1 | 남는 제안 | {loc} | 지금 | 대기 | 근거 |\n" if f == "tracker_proposals.md"
                           else f"| A1 | 남는 항목 | {loc} | 지금 | 대기 | |\n")
                    self.add_rows(p / f, row)                # 그 파일의 행 하나만 — 다른 쪽은 비어 있음
                    self.tidy(p, "--focus", ch, "--apply")
                    before = self.list_state(p)
                    rid = row.split("|")[1].strip()
                    self.assertIn(rid, before["위치표"])
                    self.assertIn(f"#### {rid} ", before["포커스"])
                    text = (p / f).read_text(encoding="utf-8")
                    self.assertIn(old, text)
                    (p / f).write_text(text.replace(old, new), encoding="utf-8")
                    self.ack(p)
                    r = self.tidy(p, "--apply")
                    self.assertIn(self.SKIPPED, r.stdout)
                    warn = next(l for l in r.stdout.splitlines() if self.SKIPPED in l)
                    self.assertIn(why, warn)
                    self.assertEqual(self.list_state(p), before, "읽기 실패로 블록 · 스탬프를 바꾸지 않습니다")


# ---------------------------------------------------------------- W7 갱신 도구 · W8 미리보기 · 해시 목록
class UpdateToolsTests(Fixtures):
    def old_content(self, rel: str) -> bytes:
        """정본 이력에서 지금과 다른 옛 내용 하나 — 가장 오래된 것부터 (이름이 바뀐 커밋은 건너뜀)."""
        cur = (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")
        commits = subprocess.run(["git", "log", "--format=%H", "--follow", "--", rel],
                                 cwd=ROOT, capture_output=True, text=True).stdout.split()
        for c in reversed(commits):
            r = subprocess.run(["git", "-c", "core.quotepath=false", "show", f"{c}:{rel}"], cwd=ROOT, capture_output=True)
            if r.returncode == 0 and r.stdout and r.stdout.replace(b"\r\n", b"\n") != cur:
                return r.stdout
        self.skipTest("정본 이력에 옛 판이 없습니다: " + rel)

    def test_check_apply_force_add_and_eol(self):
        p = self.journal("갱신")
        r = run(PY + [str(UPDATE), str(p)], cwd=self.scratch)
        managed = json.loads((SKILL / "managed_files.json").read_text(encoding="utf-8"))["files"]
        self.assertEqual(r.stdout.count("같음"), len(managed) + 1, r.stdout)   # 관리 파일 전부(managed_files.json) + 훅 등록
        self.assertIn("기본값에 기대는 키", r.stdout)
        self.assertIn("manuscript.build_script", r.stdout)
        # 로컬 수정 · 옛 정본 판 · 없음 · 줄끝
        tool = p / "tools" / "index_records.py"
        tool.write_text(tool.read_text(encoding="utf-8") + "\n# 로컬 수정\n", encoding="utf-8")
        (p / "tools" / "_config.py").write_bytes(self.old_content("plugins/research-writing/skills/new-manuscript/tools/_config.py"))
        (p / "tools" / "_location.py").unlink()
        eol = p / "tools" / "check_numbers.py"
        eol.write_bytes(eol.read_bytes().replace(b"\n", b"\r\n"))
        r = run(PY + [str(UPDATE), str(p)], cwd=self.scratch, codes=(1,))
        self.assertIn("tools/index_records.py", r.stdout); self.assertIn("로컬 수정", r.stdout)
        self.assertIn("옛 정본 판", r.stdout)
        self.assertIn("없음", r.stdout)
        self.assertIn("같음 · 줄끝 다름", r.stdout)
        # --apply 만: 옛 판 · 줄끝은 바뀌고 로컬 수정 · 없음은 남음
        r = run(PY + [str(UPDATE), str(p), "--apply"], cwd=self.scratch, codes=(1,))
        self.assertIn("남김", r.stdout)
        self.assertEqual((p / "tools" / "_config.py").read_bytes(), (TOOLS / "_config.py").read_bytes())
        self.assertNotIn(b"\r\n", eol.read_bytes())
        self.assertFalse((p / "tools" / "_location.py").exists())
        self.assertIn("# 로컬 수정", tool.read_text(encoding="utf-8"))
        # --force · --add
        r = run(PY + [str(UPDATE), str(p), "--apply", "--force", "tools/index_records.py", "--add", "tools/_location.py"],
                cwd=self.scratch)
        self.assertIn("모두 같음", r.stdout)
        backups = list((p / ".manuscript" / "tools_backup").rglob("index_records.py"))
        self.assertEqual(len(backups), 1)
        self.assertIn("# 로컬 수정", backups[0].read_text(encoding="utf-8"))
        self.assertEqual(tool.read_bytes(), (TOOLS / "index_records.py").read_bytes())
        self.assertTrue((p / "tools" / "_location.py").is_file())
        # 설정 파일은 쓰지 않음
        self.assertNotIn("record_index_exclude_written", (p / ".manuscript" / "project.json").read_text(encoding="utf-8"))
        r = run(PY + [str(UPDATE), "--scan", str(self.scratch), "--depth", "1"], cwd=self.scratch, codes=(0, 1))
        self.assertIn("갱신", r.stdout)

    def test_preview_leaves_original_untouched(self):
        p = self.journal("미리보기")
        trig = json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8"))["tracker"]["triggers"][1]
        hdr = "|---|---|---|---|---|---|\n"
        pend = p / "tracker_pending.md"
        pend.write_text(pend.read_text(encoding="utf-8").replace(
            hdr, hdr + f"| A1 | 항목 | `manuscript/results.md` ③ | {trig} | 대기 | |\n", 1), encoding="utf-8")
        write(p / "records" / "E1.md", "# E1 — 표본\n\n**완료일** 2026-01-01\n**대상** `manuscript/results.md` ③\n**상태** 확정\n\n본문.\n")
        before = snapshot(p)
        r = run(PY + [str(ROOT / "scripts" / "preview_projects.py"), str(p), "--focus", "ch3",
                      "--set", 'tracker.record_index_exclude=["archive/"]'], cwd=ROOT)
        self.assertIn("두 번 돌려도 같음: 예", r.stdout)
        self.assertIn("tracker_records_index.md", r.stdout)
        self.assertEqual(before, snapshot(p), "미리보기는 원본에 쓰지 않습니다")

    def test_hash_list_is_fresh_and_manifest_is_the_source(self):
        manifest = json.loads((SKILL / "managed_files.json").read_text(encoding="utf-8"))
        hashes = json.loads((SKILL / "tool_hashes.json").read_text(encoding="utf-8"))
        self.assertEqual([m["src"] for m in manifest["files"]], list(hashes["files"]))
        for m in manifest["files"]:
            self.assertTrue((SKILL / m["src"]).is_file(), m["src"])
        r = run(PY + [str(ROOT / "scripts" / "tool_hashes.py"), "--check"], cwd=ROOT)
        self.assertIn("최신", r.stdout)


if __name__ == "__main__":
    unittest.main()
