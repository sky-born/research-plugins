"""표 행 형식(_config.table_problems · split_cells) — 쪼개진 행 · `\\|` 셀 · 이관 표 구분선 · replace_once 차단 · 훅 알림. 합성 표본으로 검증합니다.

발단은 한 저널 원고 프로젝트의 2026-10-08 조사(표 행 쪼개짐) — Bash 도구가 명령 문자열의 `'\\n'` 을 줄바꿈으로 줄여 A70 행이
두 줄로 쪼개졌고, 행만 이관돼 꼬리가 대기 파일에 남았으며, 첫 이관이 이관 표의 구분선을 지웠고, `\\|` 가 든 비고가 포커스에서 잘렸습니다.
표본은 OS 임시 폴더에 만들고 컴퓨터별 상태도 임시 폴더(`SYNC_STATE_HOME`)에 둡니다. 연구 파일은 건드리지 않습니다.
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

os.environ.setdefault("SYNC_STATE_HOME", tempfile.mkdtemp(prefix="table-rows-state-"))   # 먼저 import 된 스위트의 상태 폴더를 덮지 않음
STATE = Path(os.environ["SYNC_STATE_HOME"])

sys.path.insert(0, str(TOOLS))
import _config  # noqa: E402
import _동기화  # noqa: E402

HDR_PEND = "| ID | 항목 | 위치 | 트리거 | 상태 | 비고 |\n|---|---|---|---|---|---|\n"
HDR_PRO = "| ID | 제안 | 위치 | 트리거 | 상태 | 비고 |\n|---|---|---|---|---|---|\n"
HDR_ARCH = "| ID | 항목 | 위치 | 상태 | 비고 |"
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
        run(PY + [str(INITIALIZER), str(p), "--name", "표 행 표본 " + name, "--kind", "journal",
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
        return run(PY + [str(p / "도구" / "수정필요_정리.py"), *args], p, codes=codes)

    @staticmethod
    def edit_payload(p: Path, rel: str, tid: str):
        return {"tool_name": "Edit", "tool_input": {"file_path": str(p / rel), "old_string": "a", "new_string": "b"},
                "cwd": str(p), "tool_use_id": tid}


# ---------------------------------------------------------------- 문법 — 한 곳의 정의
class GrammarTests(unittest.TestCase):
    def test_split_cells_keeps_escaped_pipe(self):
        self.assertEqual(_config.split_cells("| A1 | 값 \\| 둘 | 끝 |"), ["A1", "값 \\| 둘", "끝"])
        self.assertEqual(_config.split_cells("|a|b|"), ["a", "b"])
        self.assertEqual(_config.split_cells("| A1 | 끝이 \\|"), ["A1", "끝이 \\|"], "끝의 \\| 는 닫는 세로줄이 아닙니다")
        self.assertEqual(_config.unescape_cell("x \\| y"), "x | y")

    def test_row_regex_is_shared_by_sync_and_tidy(self):
        self.assertIs(_동기화.ROW_ID_RE, _config.TABLE_ROW_RE_M)
        for ok in ("| A70 | x |", "| AB1-2 | x |", "|D14|x|"):
            self.assertTrue(_config.TABLE_ROW_RE.match(ok), ok)
        for no in ("| ID | 항목 |", "| P006·P007 | x |", "|---|---|", " | A1 | x |"):
            self.assertFalse(_config.TABLE_ROW_RE.match(no), no)

    def test_table_problems_finds_split_rows_and_skips_breakers(self):
        text = "\n".join([
            "| ID | 항목 | 상태 |",            # 1 머리
            "|---|---|---|",                   # 2
            "| A1 | 첫째 | 완료 |",             # 3
            "'` 해 해시하고 S4 는 … 꼬리 |",    # 4 orphan — 저널 원고 프로젝트의 A70 모양
            "| A2 | 둘째 | 대기 |",             # 5
            " **2026-09-02 (E221)** — 꼬리 |",  # 6 orphan — 학위논문 프로젝트의 125행 모양(앞 공백)
            "| A3 | 셋째 | 대기 |",             # 7
            "<!-- /이관목록:A -->",              # 8 주석은 표를 끝냄
            "",                                 # 9
            "### A3 상세",                      # 10
            "| ID | 항목 | 상태 |",            # 11 새 표
            "| A4 | 셀이 | 넷 | 이다 |",        # 12 cells
            "| A5 | 끝 세로줄 없음",             # 13 cells + tail
            "| P006·P007 | ID 없는 행 |",       # 14 ID 없음 — 검사하지 않음
            "- 목록 줄",                        # 15 목록은 표를 끝냄
            "```",                              # 16
            "| x |",                            # 17 코드 펜스 안
            "펜스 안의 꼬리",                    # 18
            "```",                              # 19
            "| ID | a |",                       # 20
            "| A6 | b |",                       # 21
            "> 인용",                           # 22 인용은 표를 끝냄
            "| ID | a |",                       # 23
            "| A7 | c |",                       # 24
            "# 제목",                           # 25
            "", ])
        got = [(n, c) for n, c, _p in _config.table_problems(text)]
        self.assertEqual(got, [(4, "orphan"), (6, "orphan"), (12, "cells"), (13, "cells"), (13, "tail")])
        self.assertEqual([(n, c) for n, c, _p in _config.table_problems(text.replace("\n", "\r\n"))], got, "CRLF 도 같게")
        self.assertEqual(_config.table_problems("| ID | a |\n|---|---|\n| A1 | b \\| c |\n\n글\n"), [], "\\| 는 셀 경계가 아닙니다")
        self.assertIn("4행", _config.describe_table_problem((4, "orphan", "꼬리")))


# ---------------------------------------------------------------- 정리 도구 — 경고 · 이관 보류 · 구분선
class TidyTests(Fixture):
    def test_warns_split_row_holds_migration_and_restores_separator(self):
        p = self.project("쪼개진행")
        trig = self.trig(p)
        pend, arch = p / "수정필요_대기.md", p / "완료기록" / "이관_DB.md"
        tail = "'` 해 해시하고 꼬리 — 남은 것 |"
        self.add_rows(pend, HDR_PEND,
                      f"| A1 | 닫힘 | `manuscript/results.md` ③ | {trig} | 완료 (2026-10-06) | 비고 |\n"
                      f"{tail}\n"
                      f"| A2 | 열림 | `manuscript/intro.md` ¶1 | {trig} | 대기 | |\n")
        # 옛 판의 첫 이관이 지운 구분선을 흉내 냅니다
        arch.write_text(arch.read_text(encoding="utf-8").replace(SEP_ARCH + "\n", "", 1), encoding="utf-8", newline="\n")
        self.assertNotIn(SEP_ARCH, arch.read_text(encoding="utf-8"))
        n = pend.read_text(encoding="utf-8").split("\n").index(tail) + 1

        r = self.tidy(p)                                                   # 진단만
        self.assertIn("대기: 표 행 형식", r.stdout)
        self.assertIn(f"{n}행", r.stdout)
        self.assertIn("A1: 행 바로 아래", r.stdout)
        self.assertIn("이관을 보류", r.stdout)
        self.assertIn("구분선 복원", r.stdout)
        self.assertIn("이관_DB.md", r.stdout.split("바뀔 파일", 1)[1])
        self.assertNotIn(SEP_ARCH, arch.read_text(encoding="utf-8"), "진단만으로는 쓰지 않습니다")
        self.assertIn("| A1 |", pend.read_text(encoding="utf-8"))

        r = self.tidy(p, "--apply")
        self.assertIn("이관을 보류", r.stdout)
        self.assertIn("| A1 |", pend.read_text(encoding="utf-8"), "쪼개진 완료 행은 옮기지 않습니다")
        self.assertIn(tail, pend.read_text(encoding="utf-8"))
        lines = arch.read_text(encoding="utf-8").split("\n")
        self.assertEqual(lines[lines.index(HDR_ARCH) + 1], SEP_ARCH, "구분선이 머리 바로 아래로 복원")
        self.assertNotIn("| A1 |", arch.read_text(encoding="utf-8"))

        # 꼬리를 행에 합치면 이관됩니다 — 구분선은 그대로, 행은 그 아래
        _동기화.replace_once(str(pend), f"| 비고 |\n{tail}", f"| 비고 {tail}")
        r = self.tidy(p, "--apply")
        self.assertNotIn("표 행 형식", r.stdout)
        self.assertNotIn("보류", r.stdout)
        self.assertNotIn("| A1 |", pend.read_text(encoding="utf-8"))
        text = arch.read_text(encoding="utf-8")
        lines = text.split("\n")
        i = lines.index(HDR_ARCH)
        self.assertEqual(lines[i + 1], SEP_ARCH)
        self.assertTrue(lines[i + 2].startswith("| A1 |"), lines[i + 2])
        self.assertIn("남은 것 |", lines[i + 2])
        self.assertEqual(text.count(SEP_ARCH), 1)
        before = arch.read_bytes()
        self.tidy(p, "--apply")
        self.assertEqual(before, arch.read_bytes(), "두 번 돌려도 같아야 합니다")
        self.assertEqual(_config.table_problems(text), [])

    def test_skips_migration_when_archive_holds_a_stray_line(self):
        p = self.project("이관표꼬리")
        trig = self.trig(p)
        pend, arch = p / "수정필요_대기.md", p / "완료기록" / "이관_DB.md"
        self.add_rows(pend, HDR_PEND, f"| A1 | 닫힘 | `manuscript/results.md` ③ | {trig} | 완료 (2026-10-06) | |\n")
        arch.write_text(arch.read_text(encoding="utf-8").replace(SEP_ARCH + "\n", SEP_ARCH + "\n| B1 | 옛 이관 | x | 완료 | 비고 |\n꼬리만 남은 줄 |\n", 1),
                        encoding="utf-8", newline="\n")
        r = self.tidy(p, "--apply")
        self.assertIn("이관을 건너뜁니다", r.stdout)
        self.assertIn("이관_DB: 표 행 형식", r.stdout)
        self.assertIn("| A1 |", pend.read_text(encoding="utf-8"), "이관 표를 고칠 때까지 옮기지 않습니다")
        self.assertIn("꼬리만 남은 줄 |", arch.read_text(encoding="utf-8"), "이관 표를 다시 쓰지 않아 줄이 지워지지 않습니다")
        self.assertNotIn("이관 대상 없음", r.stdout)

    def test_focus_copies_cell_with_escaped_pipe_in_full(self):
        p = self.project("포커스세로줄")
        trig = self.trig(p)
        self.add_rows(p / "수정필요_제안.md", HDR_PRO,
                      f"| H1 | 보충 자료 안 | `manuscript/results.md` ③ | {trig} | 대기 | 앞부분 `@FIG a.png \\| 캡션` 뒷부분 끝말 |\n")
        r = self.tidy(p, "--focus", "ch2", "--apply")
        listing = (p / "수정필요_목록.md").read_text(encoding="utf-8")
        focus = listing.split("<!-- 포커스 -->", 1)[1].split("<!-- /포커스 -->", 1)[0]
        self.assertIn("#### H1 ", focus)
        self.assertIn("앞부분 `@FIG a.png | 캡션` 뒷부분 끝말", focus, "\\| 뒤가 잘리지 않고 문단에서는 | 로")
        self.assertNotIn("표 행 형식", r.stdout)
        table = listing.split("<!-- 위치표 -->", 1)[1].split("<!-- /위치표 -->", 1)[0]
        self.assertIn("| `results.md` | ③ | H1 |", table)


# ---------------------------------------------------------------- 쓰는 쪽 — replace_once
class ReplaceOnceTests(Fixture):
    def test_blocks_edit_that_splits_a_row_and_passes_escaped_pipe(self):
        p = self.project("치환차단")
        trig = self.trig(p)
        pend = p / "수정필요_대기.md"
        self.add_rows(pend, HDR_PEND, f"| A1 | 열림 | `manuscript/results.md` ③ | {trig} | 대기 | 비고 |\n")
        before = pend.read_bytes()
        with self.assertRaises(ValueError) as cm:
            _동기화.replace_once(str(pend), "| 대기 | 비고 |", "| 대기 | 비고\n꼬리 |")
        self.assertIn("표 행", str(cm.exception))
        self.assertEqual(before, pend.read_bytes(), "막혔으면 파일은 그대로")
        with self.assertRaises(ValueError):
            _동기화.replace_once(str(pend), "| 대기 | 비고 |", "| 대기 | 비고 | 셀 하나 더 |")      # 셀 수
        with self.assertRaises(ValueError):
            _동기화.replace_once(str(pend), "| 대기 | 비고 |", "| 대기 | 비고")                     # 끝 세로줄
        _동기화.replace_once(str(pend), "| 대기 | 비고 |", "| 대기 | 비고 \\| 덧붙임 |")           # 셀 안의 세로줄은 \\|
        self.assertEqual(_config.table_problems(pend.read_text(encoding="utf-8")), [])
        _동기화.replace_once(str(pend), "| 대기 | 비고 \\| 덧붙임 |", "| 대기 | 비고\n꼬리 |", check_tables=False)
        self.assertEqual(sorted(c for _n, c, _p in _config.table_problems(pend.read_text(encoding="utf-8"))),
                         ["orphan", "tail"], "알고 하는 치환은 통과 — 끝 세로줄 없는 행 + 꼬리")

    def test_existing_problem_only_warns(self):
        p = self.project("치환경고")
        trig = self.trig(p)
        pend = p / "수정필요_대기.md"
        self.add_rows(pend, HDR_PEND, f"| A1 | 열림 | `manuscript/results.md` ③ | {trig} | 대기 | |\n이미 있던 꼬리 |\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out = _동기화.replace_once(str(pend), "| A1 | 열림 |", "| A1 | 열림 (고침) |")
        self.assertEqual(out["count"], 1)
        self.assertIn("이미 있던 표 결함", err.getvalue())
        self.assertIn("열림 (고침)", pend.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 훅 — 쓰기 뒤 그 턴에 알림
class HookTests(Fixture):
    def test_post_hook_reports_broken_rows_in_tracker_files_only(self):
        p = self.project("훅알림")
        trig = self.trig(p)
        pend = p / "수정필요_대기.md"
        run(PY + [str(p / "도구" / "동기화_점검.py")], p, codes=(0, 1))          # 지문 기준
        good = f"| A1 | 열림 | `manuscript/results.md` ③ | {trig} | 대기 | 비고 |\n"
        self.add_rows(pend, HDR_PEND, good + "쪼개진 꼬리 |\n")
        r = hook("post", self.edit_payload(p, "수정필요_대기.md", "e1"), p)
        out = json.loads(r.stdout)
        self.assertIn("표 행", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("수정필요_대기.md", out["systemMessage"])
        self.assertIn("쪼개진 꼬리", out["systemMessage"])
        # 고치면 조용합니다
        pend.write_text(pend.read_text(encoding="utf-8").replace("쪼개진 꼬리 |\n", ""), encoding="utf-8", newline="\n")
        r = hook("post", self.edit_payload(p, "수정필요_대기.md", "e2"), p)
        self.assertEqual(r.stdout.strip(), "")
        # 셸 도구 경로 — 지문이 바뀐 추적 파일을 찾아 같은 알림. PowerShell 도 Bash 와 같이 봅니다
        pend.write_text(pend.read_text(encoding="utf-8").replace(good, good + "다시 쪼개진 꼬리 |\n"), encoding="utf-8", newline="\n")
        r = hook("post", {"tool_name": "PowerShell", "tool_input": {"command": "python x.py"}, "cwd": str(p), "tool_use_id": "ps1"}, p)
        self.assertIn("다시 쪼개진 꼬리", json.loads(r.stdout)["systemMessage"])
        r = hook("post", {"tool_name": "PowerShell", "tool_input": {"command": "python x.py"}, "cwd": str(p), "tool_use_id": "ps2"}, p)
        self.assertEqual(r.stdout.strip(), "", "지문이 안 바뀌면 다시 알리지 않습니다")
        # 추적 파일이 아닌 공용 파일(원고)은 표 검사 대상이 아닙니다
        res = p / "manuscript" / "results.md"
        res.write_text("@H1 Results\n\n| a | b |\n|---|---|\n| A1 | x |\n표 아래 문장 — 원고에서는 그냥 둡니다.\n", encoding="utf-8")
        r = hook("post", self.edit_payload(p, "manuscript/results.md", "e3"), p)
        self.assertEqual(r.stdout.strip(), "")

    def test_pre_hook_accepts_powershell_without_alerts(self):
        p = self.project("훅PS")
        r = hook("pre", {"tool_name": "PowerShell", "tool_input": {"command": "Get-Content 수정필요_대기.md"}, "cwd": str(p), "tool_use_id": "pp1"}, p)
        self.assertEqual(r.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
