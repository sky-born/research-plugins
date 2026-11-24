"""쓰기 잠금 · 정리 도구의 저장 순서 · 새 미결 번호 도구 · 훅의 손 등록 거부와 기다림 — 합성 표본으로 검증합니다.

다른 세션이 열려 있어도 쓰게 하는 장치들입니다(tracker-workflow.md 「동시 편집」).
  · 잠금은 쓰는 동안만 — 두 프로세스가 서로 막고, 쥔 쪽을 강제 종료하면 저절로 풀리고, 같은 프로세스는 다시 잡을 수 있습니다.
  · 정리 도구는 「잠금 → 읽기 → 계산 → 전체 검사 → 저장」 — 읽은 뒤 바뀐 파일이 하나라도 있으면 아무것도 저장하지 않고 한 번 더.
  · 새 미결 번호는 도구가 잠금 안에서 — 동시에 돌려도 번호가 겹치지 않고, 이관된 번호를 다시 쓰지 않습니다.
  · 훅은 손으로 넣는 새 ID 행만 거부하고(범위 밖 · 이미 아는 ID · 가지 번호는 통과), 잠금은 기다릴 뿐 막지 않습니다.
표본은 OS 임시 폴더, 상태는 `SYNC_STATE_HOME` 의 임시 폴더입니다(test_sync_guard 의 표본 도우미를 그대로 씁니다).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_sync_guard import Fixture, PY, TOOLS, HOOK  # noqa: E402  — SYNC_STATE_HOME 도 거기서 정해집니다

import _config  # noqa: E402
import _sync  # noqa: E402

HOLD_PATH = ("import sys, time; sys.path.insert(0, sys.argv[1]); import _config, _sync as S; "
             "l = S.WriteLock(sys.argv[2], '쥔 쪽', 5).acquire(); print(l.state, flush=True); time.sleep(120)")
HOLD_PROJECT = ("import sys, time; sys.path.insert(0, sys.argv[1]); import _config, _sync as S; "
                "l = S.Sync(_config.load(sys.argv[2])).write_lock('쥔 쪽', 5).acquire(); print(l.state, flush=True); time.sleep(120)")
TRY_PATH = ("import sys; sys.path.insert(0, sys.argv[1]); import _config, _sync as S; "
            "l = S.WriteLock(sys.argv[2], '시도', float(sys.argv[3])).acquire(); print(l.state); print(l.who()); l.release()")

# 정리 도구를 프로젝트 안에서 불러, 읽기와 저장 사이에 다른 세션의 쓰기를 끼워 넣습니다(once — 첫 시도에만 · always — 매번).
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
            f.write('\n다른 세션이 읽은 뒤에 넣은 줄 %d\n' % n['run'])
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


def pending_row(letter, text, state="대기"):
    return f"| {letter}? | **{text}** | `manuscript/results.md` ③ | 지금 | {state} | {text} — {letter}? 의 비고 줄입니다 |"


def edit(p: Path, rel: str, new: str, tid: str, tool_name="Edit"):
    ti = {"file_path": str(p / rel)}
    if tool_name == "Write":
        ti["content"] = new
    elif tool_name == "MultiEdit":
        ti["edits"] = [{"old_string": "a", "new_string": "b"}, {"old_string": "c", "new_string": new}]
    else:
        ti.update(old_string="a", new_string=new)
    return {"tool_name": tool_name, "tool_input": ti, "cwd": str(p), "tool_use_id": tid}


class LockItself(unittest.TestCase):
    def setUp(self):
        self.path = str(Path(tempfile.mkdtemp(prefix="write-lock-")) / "state" / "write.lock")

    def attempt(self, wait):
        t = time.monotonic()
        r = run(PY + ["-c", TRY_PATH, str(TOOLS), self.path, str(wait)], TOOLS)
        out = r.stdout.split("\n")
        return out[0].strip(), out[1].strip(), time.monotonic() - t

    def test_second_process_is_busy_and_sees_who_holds(self):
        self.assertEqual(self.attempt(0.5)[0], "held")                 # 아무도 안 쥐었을 때
        a = holder(HOLD_PATH, self.path)
        try:
            state, who, dt = self.attempt(1)
            self.assertEqual(state, "busy")
            self.assertIn("쥔 쪽", who)
            self.assertGreater(dt, 0.9)
            self.assertEqual(self.attempt(0)[0], "busy")               # 기다림 0 — 바로 판정
        finally:
            stop(a)

    def test_killed_holder_leaves_no_lock_behind(self):
        a = holder(HOLD_PATH, self.path)
        b = subprocess.Popen(PY + ["-c", TRY_PATH, str(TOOLS), self.path, "20"], stdout=subprocess.PIPE, text=True, encoding="utf-8")
        time.sleep(0.8)
        stop(a)                                                        # 강제 종료 — 풀어 주는 코드가 돌지 않습니다
        out = b.communicate(timeout=60)[0]
        self.assertEqual(out.split("\n")[0].strip(), "held")           # 기다리던 쪽이 이어받음
        self.assertEqual(self.attempt(0.5)[0], "held")

    def test_same_process_may_take_it_twice(self):
        outer = _sync.WriteLock(self.path, "바깥", 1).acquire()
        inner = _sync.WriteLock(self.path, "안", 1).acquire()
        self.assertTrue(outer.held and inner.held)
        inner.release()
        self.assertEqual(self.attempt(0.3)[0], "busy")                 # 안쪽을 풀어도 밖에서는 아직 잠김
        outer.release()
        self.assertEqual(self.attempt(0.3)[0], "held")

    def test_broken_lock_folder_does_not_block(self):
        blocker = Path(self.path).parent.parent / "파일"
        blocker.write_text("x", encoding="utf-8")
        lock = _sync.WriteLock(str(blocker / "sub" / "write.lock"), "y", 0.2).acquire()
        self.assertEqual(lock.state, "off")                            # 막지 않고 잠금 없이 진행
        self.assertFalse(lock.busy)
        lock.release()


class TidySaves(Fixture):
    @staticmethod
    def closed_row(p: Path, rid: str):
        pend = p / "tracker_pending.md"
        lines = pend.read_text(encoding="utf-8").split("\n")
        idx = next(i for i, l in enumerate(lines) if l.startswith("## A"))
        hdr = next(i for i in range(idx, len(lines)) if lines[i].startswith("|---"))
        lines.insert(hdr + 1, f"| {rid} | **끝난 항목** | `manuscript/results.md` ③ | 지금 | 완료 (2026-11-01) | 이관될 행입니다 — 충분히 긴 비고 |")
        pend.write_text("\n".join(lines), encoding="utf-8")

    def test_apply_refuses_while_locked_but_diagnosis_still_runs(self):
        p = self.project("정리잠금")
        self.closed_row(p, "A7")
        before = (p / "tracker_pending.md").read_bytes()
        a = holder(HOLD_PROJECT, p)
        try:
            r = run(PY + [tool(p, "tidy_tracker.py"), "--apply"], p, codes=(4,), wait=0.4)
            self.assertIn("쥔 쪽", r.stdout)
            self.assertIn("다시 돌리면 됩니다", r.stdout)
            self.assertEqual((p / "tracker_pending.md").read_bytes(), before)
            run(PY + [tool(p, "tidy_tracker.py")], p, codes=(0, 1), wait=0.4)      # 진단은 잠금 없이
        finally:
            stop(a)
        run(PY + [tool(p, "tidy_tracker.py"), "--apply"], p, codes=(0, 1))
        self.assertNotIn("| A7 |", (p / "tracker_pending.md").read_text(encoding="utf-8"))
        self.assertIn("| A7 |", (p / "records" / "archive.md").read_text(encoding="utf-8"))

    def test_changed_after_reading_once_means_read_again_then_save(self):
        p = self.project("정리재시도")
        self.closed_row(p, "A7")
        r = run(PY + ["-c", TIDY_DRIVER, "once"], p)
        self.assertIn("처음부터 다시 읽습니다", r.stdout)
        self.assertIn("RUNS=2", r.stdout)
        self.assertNotIn("RC=4", r.stdout)
        self.assertNotIn("| A7 |", (p / "tracker_pending.md").read_text(encoding="utf-8"))
        self.assertIn("| A7 |", (p / "records" / "archive.md").read_text(encoding="utf-8"))
        self.assertIn("넣은 줄 1", (p / "tracker_proposals.md").read_text(encoding="utf-8"))     # 다른 세션의 줄은 남습니다

    def test_changed_after_both_reads_saves_nothing_at_all(self):
        p = self.project("정리포기")
        self.closed_row(p, "A7")
        pend, rec, idx = (p / "tracker_pending.md").read_bytes(), (p / "records" / "archive.md").read_bytes(), (p / "tracker_index.md").read_bytes()
        r = run(PY + ["-c", TIDY_DRIVER, "always"], p)
        self.assertIn("RC=4 RUNS=2", r.stdout)
        self.assertIn("저장하지 않았습니다", r.stdout)
        self.assertEqual((p / "tracker_pending.md").read_bytes(), pend)        # 일부만 저장하면 A7 이 양쪽 어디에도 없게 됩니다
        self.assertEqual((p / "records" / "archive.md").read_bytes(), rec)
        self.assertEqual((p / "tracker_index.md").read_bytes(), idx)
        run(PY + [tool(p, "tidy_tracker.py"), "--apply"], p, codes=(0, 1))                 # 다시 돌리면 됩니다
        self.assertIn("| A7 |", (p / "records" / "archive.md").read_text(encoding="utf-8"))


class NewPendingId(Fixture):
    def register(self, p: Path, row: str, codes=(0,), wait=None, name="행.md"):
        f = self.scratch / (p.name + "_" + name)
        f.write_text(row + "\n", encoding="utf-8")
        return run(PY + [tool(p, "new_pending.py"), str(f)], p, codes=codes, wait=wait)

    def test_next_number_goes_past_existing_and_archived_ids(self):
        p = self.project("번호")
        r = self.register(p, pending_row("A", "첫 항목"))
        self.assertEqual(r.stdout.strip(), "A1\ttracker_pending.md")
        text = (p / "tracker_pending.md").read_text(encoding="utf-8")
        self.assertIn("| A1 | **첫 항목** |", text)
        self.assertIn("A1 의 비고 줄입니다", text)                             # 행 안의 `A?` 도 같은 번호로
        self.add_row(p, "A5", "손으로 넣어 둔 옛 항목")
        self.assertEqual(self.register(p, pending_row("A", "다음")).stdout.split("\t")[0], "A6")
        # A6 을 닫아 이관한 뒤에도 그 번호를 다시 쓰지 않습니다
        pend = p / "tracker_pending.md"
        pend.write_text(pend.read_text(encoding="utf-8").replace("| 지금 | 대기 | 다음", "| 지금 | 완료 (2026-11-01) | 다음"), encoding="utf-8")
        run(PY + [tool(p, "tidy_tracker.py"), "--apply"], p, codes=(0, 1))
        self.assertNotIn("| A6 |", pend.read_text(encoding="utf-8"))
        self.assertEqual(self.register(p, pending_row("A", "이관 뒤")).stdout.split("\t")[0], "A7")
        lines = pend.read_text(encoding="utf-8").split("\n")
        a = next(i for i, l in enumerate(lines) if l.startswith("| A7 |"))
        self.assertTrue(lines[a - 1].startswith("| A"), lines[a - 1])          # 표 맨 아래, 이관 목록 블록 앞
        self.assertEqual(_config.table_problems("\n".join(lines)), [])
        run(PY + [tool(p, "tidy_tracker.py"), "--apply"], p, codes=(0,))       # 정리 도구가 그대로 읽습니다

    def test_proposals_and_other_letters_in_a_dissertation_project(self):
        p = self.project("학위", kind="dissertation")
        hdr = next(l for l in (p / "tracker_proposals.md").read_text(encoding="utf-8").split("\n") if l.startswith("| ID |"))
        cells = ["H?"] + ["제안 본문 — 충분히 긴 칸"] * (len(_config.split_cells(hdr)) - 1)
        if "트리거" in _config.split_cells(hdr):
            cells[_config.split_cells(hdr).index("트리거")] = "지금"
        r = self.register(p, "| " + " | ".join(cells) + " |")
        self.assertEqual(r.stdout.strip(), "H1\ttracker_proposals.md")
        self.assertIn("| H1 |", (p / "tracker_proposals.md").read_text(encoding="utf-8"))
        self.assertEqual(self.register(p, pending_row("D", "문체")).stdout.strip(), "D1\ttracker_pending.md")
        self.assertEqual(self.register(p, pending_row("D", "문체 둘")).stdout.split("\t")[0], "D2")
        self.assertEqual(self.register(p, pending_row("B", "후속")).stdout.split("\t")[0], "B1")

    def test_bad_rows_and_letters_outside_the_scope_change_nothing(self):
        p = self.project("거절")
        before = {f: (p / f).read_bytes() for f in ("tracker_pending.md", "tracker_proposals.md", "tracker_literature.md")}
        self.assertIn("범위가 아닙니다", self.register(p, pending_row("F", "문헌"), codes=(2,)).stderr)
        self.assertIn("범위가 아닙니다", self.register(p, pending_row("Z", "모르는 글자"), codes=(2,)).stderr)
        self.assertIn("칸 수", self.register(p, "| A? | 칸이 모자란 행 | 지금 |", codes=(1,)).stderr)
        self.assertIn("글자?", self.register(p, pending_row("A", "번호를 손으로").replace("| A? |", "| A9 |", 1), codes=(1,)).stderr)
        self.assertIn("한 줄", self.register(p, pending_row("A", "하나") + "\n" + pending_row("A", "둘"), codes=(1,)).stderr)
        r = self.register(p, pending_row("A", "모르는 트리거").replace("| 지금 |", "| 언젠가 |"))
        self.assertIn("트리거", r.stderr)                                       # 경고만 — 등록은 됩니다
        before["tracker_pending.md"] = None
        for f, b in before.items():
            if b is not None:
                self.assertEqual((p / f).read_bytes(), b, f)

    def test_rows_spaced_by_blank_lines_and_crlf_files(self):
        p = self.project("옛모양")
        pend = p / "tracker_pending.md"
        self.add_row(p, "C3", "하나")
        self.add_row(p, "C8", "둘")                                            # add_row 는 A 절에 넣으므로 C 절로 옮겨 빈 줄로 띄웁니다
        lines = [l for l in pend.read_text(encoding="utf-8").split("\n") if not l.startswith(("| C3 |", "| C8 |"))]
        c = next(i for i, l in enumerate(lines) if l.startswith("## C"))
        sep = next(i for i in range(c, len(lines)) if lines[i].startswith("|---"))
        row = "| {0} | **옛 항목** | `manuscript/results.md` ③ | 지금 | 대기 | {0} 비고 — 충분히 긴 줄입니다 |"
        lines[sep + 1:sep + 1] = ["", row.format("C3"), "", row.format("C8"), ""]
        pend.write_bytes("\r\n".join(lines).encode("utf-8"))                   # CRLF 파일
        run(PY + [tool(p, "check_sync.py"), "--accept-warn"], p, codes=(0, 1, 2))
        r = self.register(p, pending_row("C", "새 항목"))
        self.assertEqual(r.stdout.split("\t")[0], "C9")
        raw = pend.read_bytes()
        self.assertEqual(raw.count(b"\r\n"), raw.count(b"\n"))                 # 줄끝 보존
        out = raw.decode("utf-8").split("\r\n")
        i = next(k for k, l in enumerate(out) if l.startswith("| C9 |"))
        self.assertTrue(out[i - 1].startswith("| C8 |"))                       # 마지막 행 바로 아래
        self.assertLess(i, next(k for k, l in enumerate(out) if l.startswith("<!-- 이관목록:C")))

    def test_runs_started_together_get_distinct_numbers(self):
        p = self.project("동시")
        procs = []
        for k in range(6):
            f = self.scratch / f"동시_{k}.md"
            f.write_text(pending_row("B", f"동시 항목 {k}") + "\n", encoding="utf-8")
            procs.append(subprocess.Popen(PY + [tool(p, "new_pending.py"), str(f)], cwd=str(p), stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True, encoding="utf-8"))
        outs = [q.communicate(timeout=120) for q in procs]
        self.assertEqual([q.returncode for q in procs], [0] * 6, outs)
        ids = sorted(o[0].split("\t")[0] for o in outs)
        self.assertEqual(ids, ["B%d" % n for n in range(1, 7)])                # 겹치는 번호 없음
        text = (p / "tracker_pending.md").read_text(encoding="utf-8")
        self.assertEqual(sum(1 for l in text.split("\n") if l.startswith("| B")), 6)
        self.assertEqual(_config.table_problems(text), [])
        for k in range(6):
            self.assertIn(f"동시 항목 {k}", text)

    def test_busy_lock_means_no_number(self):
        p = self.project("번호잠금")
        before = (p / "tracker_pending.md").read_bytes()
        a = holder(HOLD_PROJECT, p)
        try:
            r = self.register(p, pending_row("A", "못 넣음"), codes=(4,), wait=0.4)
            self.assertEqual(r.stdout.strip(), "")
            self.assertIn("다시 돌리면 됩니다", r.stderr)
            self.assertEqual((p / "tracker_pending.md").read_bytes(), before)
        finally:
            stop(a)
        self.assertEqual(self.register(p, pending_row("A", "넣음")).stdout.split("\t")[0], "A1")


class HookNewIdsAndWait(Fixture):
    ROW = "| {0} | **손 등록** | `manuscript/results.md` ③ | 지금 | 대기 | 손으로 넣는 행 — 충분히 긴 비고 |"

    def test_new_id_by_hand_is_denied_for_edit_write_and_multiedit(self):
        p = self.project("손등록")
        self.add_row(p, "A1", "이미 있는 항목")
        whole = (p / "tracker_pending.md").read_text(encoding="utf-8")
        for n, (name, new) in enumerate([("Edit", "앞 줄\n" + self.ROW.format("A9")), ("Write", whole + "\n" + self.ROW.format("A9")),
                                         ("MultiEdit", self.ROW.format("A9")), ("Edit", self.ROW.format("A9-1"))]):
            out = hook(edit(p, "tracker_pending.md", new, f"deny-{n}", name), p).stdout
            self.assertIn("deny", out, name)
            msg = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
            self.assertIn("new_pending.py", msg)
            self.assertIn("A?", msg)
        hrow = "| H4 | 제안 | `manuscript/results.md` | 대기 | 근거 |"
        self.assertIn("deny", hook(edit(p, "tracker_proposals.md", hrow, "deny-h"), p).stdout)

    def test_known_ids_branches_and_other_tables_pass(self):
        p = self.project("통과")
        self.add_row(p, "A1", "이미 있는 항목")
        ok = [("tracker_pending.md", self.ROW.format("A1")),                      # 있는 행을 고침
              ("tracker_pending.md", self.ROW.format("A1-1")),                    # 가지 번호 — 줄기가 있음
              ("tracker_pending.md", "| P006 | 파일명 | 내용 |"),                  # 범위 밖 글자
              ("tracker_pending.md", "비고만 고칩니다 — A9 라는 글자가 본문에 있어도 행이 아닙니다"),
              ("tracker_literature.md", "| F7 | 문헌 항목 | `x` | 대기 | 비고 |"),     # 범위 밖 파일
              ("records/archive.md", self.ROW.format("A9"))]                   # 이관 표는 정리 도구가 씁니다
        for n, (rel, new) in enumerate(ok):
            self.assertEqual(hook(edit(p, rel, new, f"pass-{n}"), p).stdout.strip(), "", (rel, new))
        # 지웠던 행을 되살리는 것 — 이 컴퓨터가 본 ID 라 새 ID 가 아닙니다
        pend = p / "tracker_pending.md"
        run(PY + [tool(p, "check_sync.py"), "--quick"], p, codes=(0, 1, 2))
        _sync.Sync(_config.load(str(p))).remember_ids()
        pend.write_text("\n".join(l for l in pend.read_text(encoding="utf-8").split("\n") if not l.startswith("| A1 |")), encoding="utf-8")
        sync = _sync.Sync(_config.load(str(p)))
        self.assertEqual(sync.hand_added_ids("tracker_pending.md", self.ROW.format("A1")), [])
        self.assertEqual(sync.hand_added_ids("tracker_pending.md", self.ROW.format("A2") + "\n" + self.ROW.format("B3")), ["A2", "B3"])

    def test_project_without_the_tool_is_not_denied(self):
        p = self.project("도구없음")
        os.remove(tool(p, "new_pending.py"))                                    # 사본을 갱신하지 않은 프로젝트 — 막으면 넣을 길이 없습니다
        self.assertEqual(hook(edit(p, "tracker_pending.md", self.ROW.format("A9"), "no-tool"), p).stdout.strip(), "")

    def test_edit_waits_for_the_lock_and_is_never_blocked_by_it(self):
        p = self.project("훅기다림")
        a = holder(HOLD_PROJECT, p)
        try:
            t = time.monotonic()
            h = hook(edit(p, "tracker_pending.md", "비고 한 줄", "wait-1"), p, wait=0.6)
            self.assertGreater(time.monotonic() - t, 0.5)                       # 잠금이 풀리기를 기다렸고
            self.assertEqual(h.stdout.strip(), "")                             # 그래도 막지 않음
            self.assertIn("쓰기 잠금", h.stderr)
        finally:
            stop(a)
        h = hook(edit(p, "tracker_pending.md", "비고 한 줄", "wait-2"), p, wait=0.6)
        self.assertEqual(h.stdout.strip(), "")
        self.assertNotIn("쓰기 잠금", h.stderr)


class OtherWriters(Fixture):
    def test_replace_once_inside_a_held_lock_and_when_another_holds_it(self):
        p = self.project("치환잠금")
        self.add_row(p, "A1", "치환 대상")
        pend = p / "tracker_pending.md"
        sync = _sync.Sync(_config.load(str(p)))
        with sync.write_lock("시험") as lock:                                   # 같은 프로세스가 다시 잡음 — 서로 기다리지 않습니다
            self.assertTrue(lock.held)
            _sync.replace_once(str(pend), "**치환 대상**", "**치환 하나**")
        self.assertIn("**치환 하나**", pend.read_text(encoding="utf-8"))
        a = holder(HOLD_PROJECT, p)
        os.environ["SYNC_LOCK_WAIT"] = "0.3"
        try:
            _sync.replace_once(str(pend), "**치환 하나**", "**치환 둘**")       # 못 잡아도 치환은 합니다 — 1회 검사가 받칩니다
        finally:
            del os.environ["SYNC_LOCK_WAIT"]
            stop(a)
        self.assertIn("**치환 둘**", pend.read_text(encoding="utf-8"))

    def test_index_tool_refuses_when_busy_but_a_new_record_is_still_made(self):
        p = self.project("색인잠금")
        body = p / "본문새.md"
        body.write_text("# E? — 잠금 중에 만든 기록\n\n**완료일** 2026-11-01\n**대상** `manuscript/results.md` ③\n**상태** 확정\n\n"
                        "본문 문장입니다 — 충분히 긴 줄.\n", encoding="utf-8")
        a = holder(HOLD_PROJECT, p)
        try:
            run(PY + [tool(p, "index_records.py")], p, codes=(4,), wait=0.3)
            r = run(PY + [tool(p, "new_record.py"), str(body)], p, wait=0.3)   # 번호 도구는 잠금을 잡지 않습니다
            self.assertEqual(r.stdout.strip(), "E4\trecords/E4.md")
            self.assertIn("색인을 다시 만들지 못했습니다", r.stderr)
        finally:
            stop(a)
        run(PY + [tool(p, "index_records.py")], p)
        self.assertIn("| E4 |", (p / "tracker_records_index.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
