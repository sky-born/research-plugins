"""동기화 안전장치(_동기화.py · 동기화_점검.py · guard_write.py pre/post · update_tools S10) — 합성 표본으로 검증합니다.

표본은 OS 임시 폴더에 만들고 컴퓨터별 상태도 임시 폴더(`SYNC_STATE_HOME`)에 둡니다. 연구 파일은 건드리지 않습니다.
시나리오는 한 저널 원고 프로젝트의 재발 방지 계획(2026-10-01 대기 복구 조사 §9)의 것입니다 — 빈칸(S2) · 참조(S3) · 스탬프(S4) ·
충돌 사본(S5) · 손실 보고(S6) · ID 단조(S7) · 신선도(S1) · 가드 · 확인 · 복구 · 1회 치환 · Bash 지문 · update_tools 거부 · 보존 정리.
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

STATE = Path(tempfile.mkdtemp(prefix="sync-guard-state-"))
os.environ["SYNC_STATE_HOME"] = str(STATE)

sys.path.insert(0, str(TOOLS))
import _config  # noqa: E402
import _동기화  # noqa: E402


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
        run(PY + [str(INITIALIZER), str(p), "--name", "동기화 표본 " + name, "--kind", kind,
                  "--source-dir", "manuscript", "--chapters", "intro.md", "results.md", "--references", "references.md"],
            self.scratch)
        if with_checkpoint:
            (p / "조사").mkdir(exist_ok=True)
            (p / "조사" / "CHECKPOINT.md").write_text("# 인수인계\n\n갱신 2026-10-01\n", encoding="utf-8")
            cfg = json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8"))
            cfg["tracker"]["checkpoint"] = "조사/CHECKPOINT.md"
            (p / ".manuscript" / "project.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for i in range(1, records + 1):
            body = p / f"본문{i}.md"
            body.write_text(f"# E? — 표본 기록 {i}\n\n**완료일** 2026-10-01\n**대상** `manuscript/results.md` ③\n**상태** 확정\n\n"
                            f"본문 문장입니다 {i} — 생존율 검사용으로 충분히 긴 줄.\n", encoding="utf-8")
            run(PY + [str(p / "도구" / "완료기록_새항목.py"), str(body)], p)
        run(PY + [str(p / "도구" / "수정필요_정리.py"), "--apply"], p, codes=(0, 1))
        run(PY + [str(p / "도구" / "완료기록_색인.py")], p)
        return p

    @staticmethod
    def check(p: Path, *args, codes=(0, 1, 2)):
        return run(PY + [str(p / "도구" / "동기화_점검.py"), *args], p, codes=codes)

    @staticmethod
    def add_row(p: Path, rid: str, text: str):
        pend = p / "수정필요_대기.md"
        lines = pend.read_text(encoding="utf-8").split("\n")
        idx = next(i for i, l in enumerate(lines) if l.startswith("## A"))
        hdr = next(i for i in range(idx, len(lines)) if lines[i].startswith("|---"))
        lines.insert(hdr + 1, f"| {rid} | **{text}** | `manuscript/results.md` ③ | 지금 | 대기 | {text} — 비고 줄입니다, 충분히 깁니다 |")
        pend.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def edit_payload(p: Path, rel: str, tid: str):
        return {"tool_name": "Edit", "tool_input": {"file_path": str(p / rel), "old_string": "a", "new_string": "b"},
                "cwd": str(p), "tool_use_id": tid}


# ---------------------------------------------------------------- 정상 · 스탬프 · 멱등
class HealthyProject(Fixture):
    def test_stamp_hashes_the_file_as_left_on_disk(self):
        """끝 빈 줄이 둘인 대기 파일(손편집, 정리 도구는 저장하지 않음)도 스탬프는 디스크 바이트의 해시 — S4 거짓 WARN 없음."""
        p = self.project("끝빈줄")
        pend = p / "수정필요_대기.md"
        self.add_row(p, "A1", "지금 할 것")                                   # 목록이 다시 만들어질 이유
        pend.write_bytes(pend.read_bytes() + b"\n")                           # 끝 빈 줄 둘 — dirty 가 아니라 저장되지 않는 변경
        before = pend.read_bytes()
        run(PY + [str(p / "도구" / "수정필요_정리.py"), "--apply"], p, codes=(0, 1))
        self.assertEqual(pend.read_bytes(), before, "정리 도구가 대기 파일을 다시 쓰면 이 시험의 전제가 아닙니다")
        self.assertTrue(before.endswith(b"\n\n"))
        idx = (p / "수정필요_목록.md").read_text(encoding="utf-8").split("\n")[1]
        stamped = idx.split("수정필요_대기.md=", 1)[1][:16]
        self.assertEqual(stamped, _동기화.norm_sha(before)[:16], "스탬프는 디스크에 있는 판의 해시여야 합니다")
        r = self.check(p, codes=(0,))
        self.assertIn("동기화 OK", r.stdout)
        self.assertNotIn("S4", r.stdout)

    def test_fresh_project_is_ok_and_generated_files_carry_stamps(self):
        p = self.project("정상")
        r = self.check(p, "-v", codes=(0,))
        self.assertIn("동기화 OK", r.stdout)
        self.assertIn("E3", r.stdout.split("\n")[0])
        idx = (p / "수정필요_목록.md").read_text(encoding="utf-8").split("\n")
        rec = (p / "수정필요_색인.md").read_text(encoding="utf-8").split("\n")
        self.assertTrue(idx[1].startswith("<!-- 생성스탬프 수정필요_대기.md="), idx[:3])
        self.assertTrue(rec[1].startswith("<!-- 생성스탬프 완료기록/ n=3 max=3 sha="), rec[:3])
        # 스냅샷 — 드라이브 폴더에 공용 파일마다 하나, 이름 규약 · 같은 해시는 다시 만들지 않음
        snaps = sorted(os.listdir(p / "보관" / "추적_백업"))
        self.assertTrue(snaps and all(_동기화.SNAP_RE.match(s) for s in snaps), snaps[:3])
        n = len(snaps)
        self.check(p, codes=(0,))
        self.assertEqual(len(os.listdir(p / "보관" / "추적_백업")), n)
        # 정리 도구 두 번 — 추적 파일이 그대로(스탬프가 결정적)
        before = {f: digest(p / f) for f in ("수정필요_목록.md", "수정필요_대기.md", "수정필요_색인.md")}
        run(PY + [str(p / "도구" / "수정필요_정리.py"), "--apply"], p, codes=(0, 1))
        after = {f: digest(p / f) for f in before}
        self.assertEqual(before, after)

    def test_defaults_only_project_runs_core_checks(self):
        # 설정에 sync · checkpoint 가 없는 옛 형식 프로젝트도 기본값만으로 돕니다
        p = self.project("옛형식", with_checkpoint=False)
        cfg = _config.load(str(p))
        self.assertIsNone(cfg.checkpoint)
        s = _동기화.Sync(cfg)
        self.assertEqual(s.opt("stale_days", 2), 2)
        self.assertEqual([f.level for f in s.check("start") if f.level == "ERROR"], [])
        self.assertIn("수정필요_대기.md", s.shared_files())
        self.assertIn("manuscript/results.md", s.shared_files())


# ---------------------------------------------------------------- 가해 쪽 — 따라잡는 중 · 낡음
class StaleMirror(Fixture):
    def test_record_gap_is_error_and_blocks_tools_and_hook(self):
        p = self.project("빈칸")
        (p / "완료기록" / "E2.md").rename(self.scratch / "빈칸_E2.bak")
        r = self.check(p, "--quick", codes=(2,))
        self.assertIn("ERROR S2", r.stdout)
        self.assertIn("ERROR S3", r.stdout)            # 색인이 가리키는 E2 가 없음
        self.assertIn("E2", r.stdout)
        # 훅 — 공용 파일 Edit 을 막음(JSON deny), 공용이 아닌 파일은 막지 않음
        h = hook("pre", self.edit_payload(p, "수정필요_대기.md", "t1"), p)
        self.assertIn('"permissionDecision": "deny"', h.stdout)
        h2 = hook("pre", self.edit_payload(p, "본문1.md", "t2"), p)
        self.assertEqual(h2.stdout.strip(), "")
        # 일괄 도구 — 거부(3)
        run(PY + [str(p / "도구" / "수정필요_정리.py"), "--apply"], p, codes=(3,))
        run(PY + [str(p / "도구" / "완료기록_색인.py")], p, codes=(3,))
        run(PY + [str(p / "도구" / "완료기록_새항목.py"), str(p / "본문1.md")], p, codes=(3,))
        # 진단만(쓰지 않음)은 통과
        run(PY + [str(p / "도구" / "수정필요_정리.py")], p, codes=(0, 1))
        # 돌아오면 정상 · 훅 통과
        (self.scratch / "빈칸_E2.bak").rename(p / "완료기록" / "E2.md")
        self.check(p, "--quick", codes=(0,))
        h3 = hook("pre", self.edit_payload(p, "수정필요_대기.md", "t3"), p)
        self.assertEqual(h3.stdout.strip(), "")

    def test_truncated_top_is_error_and_new_record_refuses_reuse(self):
        p = self.project("끝잘림")
        (p / "완료기록" / "E3.md").rename(self.scratch / "끝잘림_E3.bak")
        (p / "수정필요_색인.md").write_text("# 색인\n", encoding="utf-8")     # 색인도 옛 판처럼
        r = self.check(p, "--quick", codes=(2,))
        self.assertIn("S2:max", r.stdout) if "S2:max" in r.stdout else self.assertIn("뒤입니다", r.stdout)
        # 새항목이 E3 를 다시 집지 않음
        r2 = run(PY + [str(p / "도구" / "완료기록_새항목.py"), str(p / "본문1.md")], p, codes=(2, 3))
        self.assertFalse((p / "완료기록" / "E3.md").exists())
        (self.scratch / "끝잘림_E3.bak").rename(p / "완료기록" / "E3.md")

    def test_known_gaps_are_not_errors(self):
        p = self.project("빈번호허용", records=1)
        # E2 를 건너뛰고 E3 만 — 옛 프로젝트의 원래 빈 번호
        (p / "완료기록" / "E3.md").write_text((p / "완료기록" / "E1.md").read_text(encoding="utf-8").replace("E1", "E3"), encoding="utf-8")
        r = self.check(p, "--quick")
        self.assertIn("ERROR S2", r.stdout)
        cfg_p = p / ".manuscript" / "project.json"
        cfg = json.loads(cfg_p.read_text(encoding="utf-8"))
        cfg["sync"] = {"known_gaps": [2]}
        cfg_p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.check(p, "--ack", "시험: 옛 빈 번호", codes=(0,))
        r = self.check(p, "--quick")
        self.assertNotIn("ERROR S2", r.stdout)

    def test_stale_days_warns(self):
        p = self.project("낡음")
        s = _동기화.Sync(_config.load(str(p)))
        old = time.time() - 3 * 86400
        for rel in s.shared_files():
            os.utime(p / rel, (old, old))
        r = self.check(p, "--quick", codes=(1,))
        self.assertIn("WARN  S1", r.stdout)
        self.assertIn("일 전", r.stdout)
        self.assertIn("--accept-warn", r.stdout)                  # 안내는 진행 · 수용 — 확인 요청이 아님
        self.assertNotIn("확인을 받", r.stdout)
        # S10 — WARN(S1)만이면 도구 갱신을 거부하지 않음(ERROR 만 거부)
        r = run(PY + [str(UPDATE), str(p), "--apply"], p, codes=(0, 1))
        self.assertNotIn("적용을 거부합니다", r.stdout)
        self.assertIn("WARN 만이라 진행", r.stdout)

    def test_update_tools_refuses_apply_on_stale_or_broken_mirror(self):
        p = self.project("갱신거부")
        (p / "완료기록" / "E2.md").rename(self.scratch / "갱신거부_E2.bak")
        (p / "도구" / "_config.py").write_text("# 옛 판 흉내\n", encoding="utf-8")   # 로컬 수정판 — --force 대상
        r = run(PY + [str(UPDATE), str(p), "--apply", "--force", "도구/_config.py"], p, codes=(1,))
        self.assertIn("적용을 거부합니다", r.stdout)
        self.assertEqual((p / "도구" / "_config.py").read_text(encoding="utf-8"), "# 옛 판 흉내\n")
        r = run(PY + [str(UPDATE), str(p), "--apply", "--force", "도구/_config.py", "--sync-override"], p, codes=(0, 1))
        self.assertIn("바꿈", r.stdout)
        (self.scratch / "갱신거부_E2.bak").rename(p / "완료기록" / "E2.md")

    def test_conflict_copies_warn_but_pycache_is_excluded(self):
        p = self.project("충돌사본")
        (p / "도구" / "__pycache__").mkdir(exist_ok=True)
        (p / "도구" / "__pycache__" / "x.cpython-313.pyc").write_bytes(b"")
        (p / "도구" / "__pycache__" / "x.cpython-313 2.pyc").write_bytes(b"")
        r = self.check(p, "--quick", codes=(0,))
        self.assertNotIn("S5", r.stdout)
        (p / "수정필요_대기 2.md").write_bytes((p / "수정필요_대기.md").read_bytes())
        (p / "manuscript" / "intro (1).md").write_text("x", encoding="utf-8")
        (p / "manuscript" / "Figure 2.md").write_text("x", encoding="utf-8")       # 원본 `Figure.md` 가 없으므로 충돌 사본이 아님
        r = self.check(p, "--quick", codes=(1,))
        self.assertIn("S5", r.stdout)
        self.assertIn("수정필요_대기 2.md(바이트 동일)", r.stdout)
        self.assertIn("intro (1).md", r.stdout)
        self.assertNotIn("Figure 2.md", r.stdout)


# ---------------------------------------------------------------- 피해 쪽 — 정확한 손실 목록 · 복구 · 확인
class VictimSide(Fixture):
    def test_lost_ids_error_then_restore_then_ack(self):
        p = self.project("ID손실")
        pend = p / "수정필요_대기.md"
        base = pend.read_bytes()
        self.add_row(p, "A1", "표본 항목 하나")
        self.add_row(p, "A2", "표본 항목 둘")
        self.check(p, "--after-write", "수정필요_대기.md", codes=(0,))
        self.check(p, "--quick", codes=(0, 1))                 # ID 등록(S4 WARN 은 정상 — 목록 미재생성)
        pend.write_bytes(base)                                   # 다른 컴퓨터가 옛 판으로 덮은 것처럼
        r = self.check(p, "--quick", codes=(2,))
        self.assertIn("ERROR S7", r.stdout)
        self.assertIn("A1 A2", r.stdout)
        # 쓰기마다 로컬 스냅샷이 남아 드라이브 웹 없이 되돌림
        r = self.check(p, "--snapshots", "수정필요_대기.md", codes=(0,))
        self.assertIn("로컬", r.stdout)
        self.check(p, "--restore", "수정필요_대기.md", codes=(0,))
        self.assertIn("| A2 |", pend.read_text(encoding="utf-8"))
        r = self.check(p, "--quick", codes=(0, 1))
        self.assertNotIn("S7", r.stdout)
        # 정당한 삭제는 사용자 확인으로 닫힘
        pend.write_bytes(base)
        self.check(p, "--quick", codes=(2,))
        r = self.check(p, "--ack", "사용자: A1 · A2 는 내가 지웠음", codes=(0,))
        self.assertIn("1건 닫음", r.stdout)
        self.check(p, "--quick", codes=(0, 1))
        log = json.loads(next(STATE.glob("*ID손실*/ack_log.json")).read_text(encoding="utf-8"))
        self.assertEqual(log[-1]["text"], "사용자: A1 · A2 는 내가 지웠음")

    def test_lost_lines_report_only_counts_my_lines(self):
        p = self.project("손실보고")
        res = p / "manuscript" / "results.md"
        res.write_text("@H1 Results\n\n" + "\n".join(f"이 컴퓨터가 쓴 문장 {i} 입니다 — 충분히 긴 줄." for i in range(10)) + "\n", encoding="utf-8")
        hook("pre", self.edit_payload(p, "manuscript/results.md", "w1"), p)
        hook("post", self.edit_payload(p, "manuscript/results.md", "w2"), p)
        # 다른 세션의 정당한 큰 개고 — 내 줄은 그대로 두고 많은 줄을 더함 → 경고 없음
        with res.open("a", encoding="utf-8") as f:
            f.write("\n".join(f"다른 컴퓨터가 더한 문장 {i} 입니다 — 충분히 긴 줄." for i in range(40)) + "\n")
        r = self.check(p, "--quick", codes=(0, 1))
        self.assertNotIn("S6", r.stdout)
        # 낡은 판으로 덮임 — 내 줄이 사라짐 → WARN · --damage 가 사라진 줄을 보임
        res.write_text("@H1 Results\n\n옛 판 문장 하나뿐입니다 — 충분히 긴 줄.\n", encoding="utf-8")
        r = self.check(p, "--quick", codes=(1, 2))
        self.assertIn("WARN  S6", r.stdout)
        self.assertIn("results.md", r.stdout)
        r = self.check(p, "--damage", codes=(1,))
        self.assertIn("이 컴퓨터가 쓴 문장 0 입니다", r.stdout)
        # 갈아쓰는 문서(checkpoint)는 손실 보고에서 제외
        cp = p / "조사" / "CHECKPOINT.md"
        cp.write_text("# 인수인계\n\n" + "\n".join(f"상태 줄 {i} 입니다 — 충분히 긴 줄." for i in range(10)) + "\n", encoding="utf-8")
        hook("post", self.edit_payload(p, "조사/CHECKPOINT.md", "w3"), p)
        cp.write_text("# 인수인계\n\n갈아썼습니다 — 충분히 긴 줄.\n", encoding="utf-8")
        r = self.check(p, "--damage", codes=(0, 1))
        self.assertNotIn("CHECKPOINT", r.stdout)

    def test_warn_only_is_accepted_without_asking_and_error_still_needs_ack(self):
        p = self.project("WARN수용")
        res = p / "manuscript" / "results.md"
        res.write_text("@H1 Results\n\n" + "\n".join(f"이 컴퓨터가 쓴 문장 {i} 입니다 — 충분히 긴 줄." for i in range(10)) + "\n", encoding="utf-8")
        hook("pre", self.edit_payload(p, "manuscript/results.md", "w1"), p)
        hook("post", self.edit_payload(p, "manuscript/results.md", "w2"), p)
        res.write_text("@H1 Results\n\n옛 판 문장 하나뿐입니다 — 충분히 긴 줄.\n", encoding="utf-8")
        r = self.check(p, "--quick", codes=(1,))                      # WARN 만 — rc 1, 안내는 수용 · 진행
        self.assertIn("WARN  S6", r.stdout)
        self.assertIn("--accept-warn", r.stdout)
        self.assertNotIn("확인을 받", r.stdout)
        r = self.check(p, "--accept-warn", codes=(0,))
        self.assertIn("WARN 수용", r.stdout)
        r = self.check(p, "--quick", codes=(0, 1))
        self.assertNotIn("S6", r.stdout)                              # 기준이 지금 상태 — 같은 조건이 다시 걸리지 않음
        # 열린 ERROR 가 있으면 --accept-warn 은 거부 — ERROR 를 닫는 길은 --ack 뿐
        (p / "완료기록" / "E2.md").rename(self.scratch / "WARN수용_E2.bak")
        self.check(p, "--quick", codes=(2,))
        r = self.check(p, "--accept-warn", codes=(2,))
        self.assertIn("거부", r.stdout)
        self.assertIn("S2", r.stdout)
        self.assertTrue(hook("pre", self.edit_payload(p, "manuscript/results.md", "w3"), p), "ERROR 는 여전히 막음")
        (self.scratch / "WARN수용_E2.bak").rename(p / "완료기록" / "E2.md")

    def test_bash_post_hook_registers_changed_shared_files_only(self):
        p = self.project("Bash지문")
        self.check(p, codes=(0,))                                 # 지문 기준
        (p / "manuscript" / "intro.md").write_text("@H1 Intro\n\nBash 경로로 쓴 문장입니다 — 충분히 긴 줄.\n", encoding="utf-8")
        (p / "조사" / "메모.md").write_text("공용이 아닌 파일\n", encoding="utf-8")
        hook("post", {"tool_name": "Bash", "tool_input": {"command": "python x.py"}, "cwd": str(p), "tool_use_id": "b1"}, p)
        written = json.loads(next(STATE.glob("*Bash지문*/written.json")).read_text(encoding="utf-8"))
        self.assertIn("manuscript/intro.md", written)
        self.assertNotIn("조사/메모.md", written)
        snaps = [s for s in os.listdir(next(STATE.glob("*Bash지문*")) / "snap") if "manuscript__intro" in s]
        self.assertGreaterEqual(len(snaps), 2)

    def test_bash_pre_hook_blocks_only_with_open_error_and_shared_path(self):
        p = self.project("Bash차단")
        (p / "완료기록" / "E2.md").rename(self.scratch / "Bash차단_E2.bak")
        self.check(p, "--quick", codes=(2,))
        h = hook("pre", {"tool_name": "Bash", "tool_input": {"command": "python 도구/x.py 수정필요_대기.md"}, "cwd": str(p), "tool_use_id": "c1"}, p)
        self.assertIn("deny", h.stdout)
        h = hook("pre", {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(p), "tool_use_id": "c2"}, p)
        self.assertEqual(h.stdout.strip(), "")
        (self.scratch / "Bash차단_E2.bak").rename(p / "완료기록" / "E2.md")

    def test_hook_dedupes_same_tool_use_and_ignores_other_folders(self):
        p = self.project("중복처리")
        (p / "완료기록" / "E2.md").rename(self.scratch / "중복_E2.bak")
        payload = self.edit_payload(p, "수정필요_대기.md", "same-id")
        self.assertIn("deny", hook("pre", payload, p).stdout)
        self.assertEqual(hook("pre", payload, p).stdout.strip(), "")        # 두 번째(다른 훅 등록)는 아무것도 하지 않음
        outside = self.scratch / "밖"
        outside.mkdir(exist_ok=True)
        (outside / "x.md").write_text("x", encoding="utf-8")
        h = hook("pre", {"tool_name": "Edit", "tool_input": {"file_path": str(outside / "x.md")}, "cwd": str(outside), "tool_use_id": "o1"}, outside)
        self.assertEqual(h.stdout.strip(), "")
        (self.scratch / "중복_E2.bak").rename(p / "완료기록" / "E2.md")

    def test_legacy_overwrite_denial_still_works(self):
        p = self.project("덮어쓰기")
        payload = {"tool_name": "Write", "tool_input": {"file_path": str(p / "완료기록" / "E1.md"), "content": "x"}, "cwd": str(p), "tool_use_id": "l1"}
        self.assertIn("deny", hook("pre", payload, p).stdout)
        payload = {"tool_name": "Write", "tool_input": {"file_path": str(p / "완료기록" / "E99.md"), "content": "x"}, "cwd": str(p), "tool_use_id": "l2"}
        self.assertEqual(hook("pre", payload, p).stdout.strip(), "")


# ---------------------------------------------------------------- 도우미 · 스냅샷 보존 · 훅 등록 파일
class Helpers(Fixture):
    def test_replace_once_preserves_crlf_and_requires_single_match(self):
        p = self.project("치환")
        f = p / "manuscript" / "results.md"
        f.write_bytes("@H1 Results\r\n\r\n첫 문단입니다.\r\n둘째 문단입니다.\r\n".encode("utf-8"))
        out = _동기화.replace_once(str(f), "첫 문단입니다.", "첫 문단을 고쳤습니다.\n새 줄입니다.")
        self.assertTrue(out["crlf"])
        b = f.read_bytes()
        self.assertEqual(b.count(b"\r\n"), 5)
        self.assertEqual(b.count(b"\n"), b.count(b"\r\n"))
        with self.assertRaises(ValueError):
            _동기화.replace_once(str(f), "문단", "x")                 # 2회
        with self.assertRaises(ValueError):
            _동기화.replace_once(str(f), "없는 문구", "x")             # 0회
        lf = p / "manuscript" / "intro.md"
        lf.write_bytes(b"a\nb\n")                                   # write_text 는 윈도에서 CRLF 로 바꿉니다
        _동기화.replace_once(str(lf), "a\n", "a\nc\n")
        self.assertEqual(lf.read_bytes(), b"a\nc\nb\n")
        snaps = _동기화.Sync(_config.load(str(p))).snapshots_of("manuscript/results.md")
        self.assertGreaterEqual(len(snaps), 2)                      # 치환 전후

    def test_prune_by_age_count_and_other_computers(self):
        p = self.project("보존")
        s = _동기화.Sync(_config.load(str(p)))
        drive = Path(s.snapshot_dir)
        now = datetime.datetime.now(datetime.timezone.utc)

        def fake(stem, comp, n, when):
            (drive / s._snap_name(stem, comp, "%08x" % n, when)).write_bytes(b"x")

        # ① 나이 — 자기 것 45일 전 14개: 최근 10개는 남고 나머지는 지워짐
        for i in range(14):
            fake("수정필요_대기.md", s.me, i, now - datetime.timedelta(days=45, minutes=-i))
        # ② 개수 — 자기 것 어제 30개(30일 안): 상한 20 을 넘는 오래된 10개가 지워짐
        for i in range(30):
            fake("manuscript/results.md", s.me, 100 + i, now - datetime.timedelta(days=1, minutes=-i))
        # ③ 다른 컴퓨터 — 45일 전 것은 남고(90일 미만) 120일 전 것은 지워짐
        fake("수정필요_대기.md", "OTHER-PC", 0xdead, now - datetime.timedelta(days=45))
        fake("수정필요_대기.md", "OTHER-PC", 0xbeef, now - datetime.timedelta(days=120))
        self.check(p, codes=(0,))                                   # 세션 시작에도 보존 정리가 돕니다
        names = os.listdir(drive)
        mine_pend = [n for n in names if "_수정필요_대기_" in n and ("_%s_" % s.me) in n]
        mine_res = [n for n in names if "_manuscript__results_" in n and ("_%s_" % s.me) in n]
        others = [n for n in names if "OTHER-PC" in n]
        self.assertEqual(len(mine_pend), 10, mine_pend)              # 실제 판 1 + 가짜 14 가운데 최근 10개만 남음
        self.assertLessEqual(len(mine_res), 20 + 1)
        self.assertGreaterEqual(len(mine_res), 20)
        self.assertEqual(len(others), 1)
        self.assertIn("0000dead", others[0])

    def test_nfc_finder_imports_nfd_named_module(self):
        # 맥 구글드라이브 미러처럼 파일 이름이 NFD 인 한글 모듈 — `_config` 가 등록한 finder 가 받아 줍니다(NTFS 는 코드 포인트를 그대로 보존)
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
        p = self.project("NFD파일")
        nfd = unicodedata.normalize("NFD", "노트_결과")
        (p / "manuscript" / (nfd + ".md")).write_text("NFD 이름의 원고 노트 — 충분히 긴 줄.\n", encoding="utf-8")
        s = _동기화.Sync(_config.load(str(p)))
        self.assertIn("manuscript/노트_결과.md", s.shared_files())
        self.assertTrue(s.is_shared("manuscript/노트_결과.md"))
        self.assertTrue(s.is_shared("manuscript/" + nfd + ".md"))
        # NTFS 는 정규화에 민감 — NFC 이름으로 읽어도 실제(NFD) 파일에 닿아야 합니다
        self.assertIn("NFD 이름의 원고 노트", s.read("manuscript/노트_결과.md").decode("utf-8"))
        made1 = s.snapshot("manuscript/노트_결과.md", drive=True)
        made2 = s.snapshot("manuscript/" + nfd + ".md", drive=True)
        self.assertTrue(made1)
        self.assertEqual(made2, [])                                  # 같은 파일 · 같은 해시 — 다시 만들지 않음
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
        p = self.project("루트탐색")
        deep = p / "조사" / "깊은" / "폴더"
        deep.mkdir(parents=True, exist_ok=True)
        self.assertEqual(_동기화.find_project_root(str(deep)), str(p))
        self.assertEqual(_동기화.find_project_root(str(p / "수정필요_대기.md")), str(p))
        self.assertIsNone(_동기화.find_project_root(str(self.scratch)))


# ---------------------------------------------------------------- S4 — 스탬프가 다를 때 방향을 가림
class StampDirection(Fixture):
    def test_source_edited_after_tidy_is_todo_not_a_sync_warning(self):
        p = self.project("순방향")
        time.sleep(0.2)
        self.add_row(p, "A9", "정리 뒤 편집")                      # 훅 없이 — 이 컴퓨터의 스냅샷에 없는 판
        r = self.check(p, "--quick", codes=(0,))
        self.assertIn("동기화 OK", r.stdout)
        self.assertIn("할 일", r.stdout)
        self.assertIn("동기화 문제 아님", r.stdout)
        self.assertNotIn("드라이브가 최신인지", r.stdout)
        r = self.check(p, "--quick", "-v", codes=(0,))
        self.assertIn("INFO  S4", r.stdout)
        # 훅이 등록한 판(스냅샷 있음)도 순방향 — 편집 시각이 붙음
        self.check(p, "--after-write", "수정필요_대기.md", codes=(0,))
        r = self.check(p, "--quick", codes=(0,))
        self.assertIn("할 일", r.stdout)
        self.assertIn("편집", r.stdout)
        run(PY + [str(p / "도구" / "수정필요_정리.py"), "--apply"], p, codes=(0, 1))
        r = self.check(p, "--quick", "-v", codes=(0,))
        self.assertNotIn("S4", r.stdout)

    def test_source_back_to_older_known_version_is_regress_or_revert(self):
        p = self.project("역행")
        pend = p / "수정필요_대기.md"
        self.add_row(p, "A9", "첫 판")
        run(PY + [str(p / "도구" / "수정필요_정리.py"), "--apply"], p, codes=(0, 1))   # v1 · 스탬프 v1 · ID 등록
        v1 = pend.read_bytes()
        pend.write_bytes(v1.replace("첫 판 — 비고".encode("utf-8"), "둘째 판 — 비고".encode("utf-8")))
        self.check(p, "--after-write", "수정필요_대기.md", codes=(0,))                # v2 스냅샷(훅이 하는 일)
        time.sleep(1.1)                                                              # 스냅샷 이름의 초가 겹치지 않게
        run(PY + [str(p / "도구" / "수정필요_정리.py"), "--apply"], p, codes=(0, 1))   # 스탬프 = v2
        idx_m = os.path.getmtime(p / "수정필요_목록.md")
        pend.write_bytes(v1)                                                         # 옛 판으로 돌아감
        os.utime(pend, (idx_m - 100, idx_m - 100))                                   # 수정 시각도 생성물보다 앞 — 덮어쓰기
        r = self.check(p, "--quick", codes=(2,))
        self.assertIn("ERROR S4", r.stdout)
        self.assertIn("옛 판으로", r.stdout)
        now = time.time()
        os.utime(pend, (now, now))                                                   # 수정 시각이 뒤 — 되돌렸을 수도
        r = self.check(p, "--quick", codes=(1,))
        self.assertIn("WARN  S4", r.stdout)
        self.assertIn("되돌린", r.stdout)

    def test_unknown_source_version_without_later_edit_is_suspect(self):
        p = self.project("미지")
        pend = p / "수정필요_대기.md"
        idx_m = os.path.getmtime(p / "수정필요_목록.md")
        self.add_row(p, "A9", "다른 컴퓨터의 편집")                 # 이 컴퓨터의 스냅샷에 없는 판
        os.utime(pend, (idx_m - 100, idx_m - 100))                  # 그런데 생성물보다 먼저 쓰인 것으로 보임
        r = self.check(p, "--quick", codes=(1,))
        self.assertIn("WARN  S4", r.stdout)
        self.assertIn("덮었거나", r.stdout)
        self.assertIn("--accept-warn", r.stdout)                  # WARN 은 보고 · 수용 — 확인 요청이 아님

    def test_new_record_refreshes_index_and_added_records_are_todo(self):
        p = self.project("기록추가", records=2)
        body = p / "본문_새.md"
        body.write_text("# E? — 새 기록\n\n**완료일** 2026-10-03\n**대상** `manuscript/results.md` ④\n**상태** 확정\n\n"
                        "본문 문장입니다 — 생존율 검사용으로 충분히 긴 줄.\n", encoding="utf-8")
        r = run(PY + [str(p / "도구" / "완료기록_새항목.py"), str(body)], p)
        self.assertEqual(r.stdout.strip().split("\t"), ["E3", "완료기록/E3.md"])     # 표준 출력은 번호 한 줄뿐
        self.assertIn("재생성", r.stderr)                            # 색인을 함께 다시 만듦 — 안내는 표준 오류로
        rec = (p / "수정필요_색인.md").read_text(encoding="utf-8").split("\n")
        self.assertTrue(rec[1].startswith("<!-- 생성스탬프 완료기록/ n=3 max=3 sha="), rec[:3])
        r = self.check(p, "--quick", "-v", codes=(0,))
        self.assertNotIn("S4", r.stdout)
        # --no-index — 색인은 그대로, 점검은 「할 일」(동기화 경고 아님)
        r = run(PY + [str(p / "도구" / "완료기록_새항목.py"), str(body), "--no-index"], p)
        self.assertEqual(r.stdout.strip().split("\t"), ["E4", "완료기록/E4.md"])
        self.assertNotIn("재생성", r.stderr)
        r = self.check(p, "--quick", codes=(0,))
        self.assertIn("동기화 OK", r.stdout)
        self.assertIn("할 일", r.stdout)
        self.assertIn("E4", r.stdout)
        # 색인을 만들 때 있던 기록의 내용이 바뀌면 WARN
        e1 = p / "완료기록" / "E1.md"
        e1.write_text(e1.read_text(encoding="utf-8") + "\n덧붙인 줄입니다 — 확정 기록을 고친 경우.\n", encoding="utf-8")
        r = self.check(p, "--quick", codes=(1,))
        self.assertIn("WARN  S4", r.stdout)
        self.assertIn("내용이 바뀐", r.stdout)


# ---------------------------------------------------------------- 쓴 줄의 기준 — 이 컴퓨터가 쓰기 직전에 본 판
class PreVersion(Fixture):
    LINES = ["참고문헌 %d — 생존율 검사용으로 충분히 긴 줄입니다 %s" % (i, "·" * i) for i in range(1, 11)]

    def _foreign_later_snapshot(self, p: Path, rel: str, content: str):
        """다른 컴퓨터가 더 늦은 시각에 찍은 옛 판 — 드라이브 스냅샷 폴더에 둡니다."""
        data = content.encode("utf-8")
        later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=30)
        name = _동기화.Sync._snap_name(rel, "OTHER-PC", hashlib.sha256(data).hexdigest(), later)
        (p / "보관" / "추적_백업" / name).write_bytes(data)
        return name

    def test_removed_lines_are_unregistered_even_if_a_foreign_old_snapshot_is_later(self):
        p = self.project("직전판")
        rel = "manuscript/intro.md"
        f = p / "manuscript" / "intro.md"
        f.write_text("# Intro\n\n" + "\n".join(self.LINES) + "\n", encoding="utf-8")       # v1 — 10줄
        self.check(p, "--after-write", rel, codes=(0,))                                      # 10줄 등록 · v1 스냅샷
        s = _동기화.Sync(_config.load(str(p)))
        self.assertEqual(len(s._load("written.json", {}).get(rel, {})), 10)
        self._foreign_later_snapshot(p, rel, "# Intro\n\n옛 판의 줄입니다 — 이 컴퓨터의 줄은 하나도 없습니다.\n")
        # 이 컴퓨터가 v1 → v2 로 씀(6줄 지움) — 훅 · replace_once 와 같은 순서
        s.before_write(rel)
        f.write_text("# Intro\n\n" + "\n".join(self.LINES[:4]) + "\n", encoding="utf-8")
        s.after_write(rel)
        mine = s._load("written.json", {}).get(rel, {})
        self.assertEqual(len(mine), 4, mine)                                                 # 지운 6줄은 등록에서 빠짐
        r = self.check(p, "--quick", codes=(0,))
        self.assertNotIn("S6", r.stdout)
        # Bash 경로(before_write 없음) — 세션 경계가 적어 둔 「마지막으로 본 판」이 기준
        self._foreign_later_snapshot(p, rel, "# Intro\n\n또 다른 옛 판입니다 — 역시 이 컴퓨터의 줄이 없습니다.\n")
        f.write_text("# Intro\n\n" + "\n".join(self.LINES[:2]) + "\n", encoding="utf-8")
        self.check(p, "--after-bash", codes=(0,))
        s = _동기화.Sync(_config.load(str(p)))
        self.assertEqual(len(s._load("written.json", {}).get(rel, {})), 2)
        r = self.check(p, "--quick", codes=(0,))
        self.assertNotIn("S6", r.stdout)

    def test_unknown_previous_version_falls_back_to_my_own_snapshots_only(self):
        p = self.project("직전판모름")
        rel = "manuscript/results.md"
        f = p / "manuscript" / "results.md"
        f.write_text("# Res\n\n" + "\n".join(self.LINES) + "\n", encoding="utf-8")        # 제목은 8자 미만 — 「쓴 줄」로 세지 않음
        self.check(p, "--after-write", rel, codes=(0,))
        s = _동기화.Sync(_config.load(str(p)))
        seen = s._load("seen.json", {})
        seen.pop(rel, None)
        s._save("seen.json", seen)                                                           # 직전 판을 모르는 상태
        self._foreign_later_snapshot(p, rel, "# Res\n\n옛 판 — 다른 컴퓨터 · 더 늦은 시각.\n")
        f.write_text("# Res\n\n" + "\n".join(self.LINES[:3]) + "\n", encoding="utf-8")
        s2 = _동기화.Sync(_config.load(str(p)))
        s2.after_write(rel)
        self.assertEqual(len(s2._load("written.json", {}).get(rel, {})), 3)                  # 이 컴퓨터의 v1 스냅샷이 기준


# ---------------------------------------------------------------- 목록의 ID 자리(S3) · 확인의 유지(ack)
class ListIdsAndAck(Fixture):
    """저널 원고 프로젝트(2026-10-12 `S3:list:D4,D6`) · 학위논문 프로젝트(2026-10-10 `S3:list:A40`) — 포커스의 비고 사본에 든 다른 문서의 라벨을 미결 ID 로
    읽었고, ack 뒤에도 쓰기 직전 재검사가 같은 key 를 다시 막아 그 목록을 다시 만들 정리 도구까지 멈췄습니다."""
    LABELS = "반영계획 결정 D4 · D6 · 다른 프로젝트 journal_paper A40 · dissertation H21"

    def _labelled(self, name, kind="journal"):
        p = self.project(name, kind=kind)
        base = (p / "수정필요_대기.md").read_bytes()
        self.add_row(p, "A1", self.LABELS)          # 항목 · 비고에 다른 문서의 라벨 — 위치 표 · 지금 · 포커스에 실림
        run(PY + [str(p / "도구" / "수정필요_정리.py"), "--focus", "ch2", "--apply"], p, codes=(0, 1))
        return p, base

    @staticmethod
    def _s3(out):
        return [l for l in out.splitlines() if " S3 " in l]

    def tidy(self, p, codes):
        return run(PY + [str(p / "도구" / "수정필요_정리.py"), "--apply"], p, codes=codes)

    def test_labels_in_copied_notes_are_not_pending_ids(self):
        for kind in ("journal", "dissertation"):
            with self.subTest(kind=kind):
                p, base = self._labelled("라벨_" + kind, kind)
                listing = (p / "수정필요_목록.md").read_text(encoding="utf-8")
                focus = listing.split("<!-- 포커스 -->", 1)[1].split("<!-- /포커스 -->", 1)[0]
                self.assertIn("#### A1 — ", focus)
                self.assertIn("A40", focus)                                   # 비고 사본에는 라벨이 그대로 있음
                ids, unknown = _config.list_block_ids(listing)               # 정리 도구가 쓴 모양을 그대로 읽음(왕복)
                self.assertEqual(unknown, [])
                self.assertEqual((ids["위치표"], ids["지금"], ids["포커스"], ids["트리거표"]), (["A1"], ["A1"], ["A1"], []))
                r = self.check(p, "--quick", codes=(0, 1))
                self.assertEqual(self._s3(r.stdout), [])
                self.assertEqual(hook("pre", self.edit_payload(p, "수정필요_대기.md", "lab-" + kind), p).stdout.strip(), "")
                # ID 자리의 진짜 빈 참조는 그대로 ERROR — 라벨은 섞이지 않음
                (p / "수정필요_대기.md").write_bytes(base)
                r = self.check(p, "--quick", codes=(2,))
                s3 = self._s3(r.stdout)
                self.assertEqual(len(s3), 1, r.stdout)
                self.assertIn("ERROR S3", s3[0])
                self.assertTrue(s3[0].rstrip().endswith("— A1"), s3[0])

    def test_ack_lets_tidy_rebuild_the_list_that_still_shows_the_condition(self):
        p = self.project("교착")
        self.add_row(p, "A2", "남는 항목")                                     # 남는 행이 다시 만든 목록에 실리는지까지 봄(0건은 아래 시험)
        keep = (p / "수정필요_대기.md").read_bytes()
        self.add_row(p, "A1", self.LABELS)
        run(PY + [str(p / "도구" / "수정필요_정리.py"), "--focus", "ch2", "--apply"], p, codes=(0, 1))
        self.check(p, "--quick", codes=(0, 1))                                # A1 등록
        (p / "수정필요_대기.md").write_bytes(keep)                             # 사용자가 A1 행을 지움 — 목록은 아직 A1 을 가리킴
        r = self.check(p, "--quick", codes=(2,))
        self.assertTrue(any(l.rstrip().endswith("— A1") for l in self._s3(r.stdout)), r.stdout)
        self.tidy(p, codes=(3,))                                              # 확인 전 — 거부
        self.check(p, "--ack", "시험: A1 은 내가 지웠음", codes=(0,))
        r = self.tidy(p, codes=(0, 1))                                        # 확인 뒤 — 목록에 같은 조건이 남아 있어도 돎(교착 없음)
        self.assertNotIn("동기화 점검 ERROR", r.stdout)
        self.assertNotIn("ERROR 남음", r.stdout)
        ids, _ = _config.list_block_ids((p / "수정필요_목록.md").read_text(encoding="utf-8"))
        self.assertEqual((ids["위치표"], ids["지금"], ids["포커스"]), (["A2"], ["A2"], ["A2"]))   # 정리 도구가 목록을 다시 만들어 조건이 사라짐
        r = self.check(p, "--quick", codes=(0, 1))
        self.assertNotIn("ERROR", r.stdout)

    def test_removing_the_last_open_row_empties_the_list_after_ack(self):
        """마지막 미결 행을 사용자가 지우면 목록이 사라진 ID 를 가리켜 S3 ERROR — 확인 뒤 정리 도구가 블록을 빈 상태로 다시 만들어 조건이 사라집니다.
        저널은 대기 파일의 마지막 행, 학위논문은 상태 열이 없는 옛 제안 표(학위논문 프로젝트 모양 — 상태로 닫지 못하고 행을 지움)의 마지막 행."""
        old_pro = "| ID | 제안 | 위치 | 근거 |\n|---|---|---|---|\n"
        for kind, rid in (("journal", "A1"), ("dissertation", "H1")):
            with self.subTest(kind=kind):
                p = self.project("마지막행_" + kind, kind=kind)
                pend, pro = p / "수정필요_대기.md", p / "수정필요_제안.md"
                if rid == "H1":
                    text = pro.read_text(encoding="utf-8")
                    pro.write_text(text.split("| ID |", 1)[0] + old_pro, encoding="utf-8")
                    base = pro.read_bytes()
                    pro.write_text(base.decode("utf-8") + "| H1 | 지울 제안 | `manuscript/results.md` ③ | 근거 — 충분히 긴 비고 줄입니다 |\n",
                                   encoding="utf-8")
                else:
                    base = pend.read_bytes()
                    self.add_row(p, "A1", "지울 항목")
                run(PY + [str(p / "도구" / "수정필요_정리.py"), "--focus", "ch2", "--apply"], p, codes=(0, 1))
                ids, _ = _config.list_block_ids((p / "수정필요_목록.md").read_text(encoding="utf-8"))
                self.assertEqual((ids["위치표"], ids["포커스"]), ([rid], [rid]))
                self.check(p, "--quick", codes=(0, 1))                        # 등록
                (pro if rid == "H1" else pend).write_bytes(base)             # 사용자가 마지막 행을 지움 — 미결 0건
                r = self.check(p, "--quick", codes=(2,))
                self.assertTrue(any(l.rstrip().endswith("— " + rid) for l in self._s3(r.stdout)), r.stdout)
                self.tidy(p, codes=(3,))                                      # 확인 전 — 거부
                self.check(p, "--ack", "시험: 마지막 행은 내가 지웠음", codes=(0,))
                r = self.tidy(p, codes=(0, 1))
                self.assertNotIn("미결 항목을 하나도 읽지 못했습니다", r.stdout)
                self.assertIn("미결 항목 0건", r.stdout)
                listing = (p / "수정필요_목록.md").read_text(encoding="utf-8")
                ids, unknown = _config.list_block_ids(listing)
                self.assertEqual((sum(map(len, ids.values())), unknown), (0, []))
                self.assertIn("> 미결 항목이 없습니다", listing.split("<!-- 지금 -->", 1)[1].split("<!-- /지금 -->", 1)[0])
                r = self.check(p, "--quick", codes=(0, 1))
                self.assertEqual(self._s3(r.stdout), [])
                self.assertNotIn("ERROR", r.stdout)

    def test_ack_holds_for_the_same_key_within_ack_hours_only(self):
        p = self.project("확인유지")
        e2, e3 = self.scratch / "확인유지_E2.bak", self.scratch / "확인유지_E3.bak"
        (p / "완료기록" / "E2.md").rename(e2)
        self.check(p, "--quick", codes=(2,))
        self.assertIn('"permissionDecision": "deny"', hook("pre", self.edit_payload(p, "수정필요_대기.md", "k1"), p).stdout)
        self.check(p, "--ack", "시험: E2 는 따라잡는 중임을 확인", codes=(0,))
        # 같은 조건(빈칸 E2)이 남아 있어도 ack_hours 안에서는 막지 않음 — 점검은 「확인됨」으로 보이고 rc 1
        r = self.check(p, "--quick", codes=(1,))
        self.assertIn("ERROR(확인됨)", r.stdout)
        self.assertIn("[확인됨", r.stdout)
        self.assertEqual(hook("pre", self.edit_payload(p, "수정필요_대기.md", "k2"), p).stdout.strip(), "")
        r = self.tidy(p, codes=(0, 1))
        self.assertNotIn("ERROR 남음", r.stdout)
        # 조건이 달라지면(새 key) 다시 막음
        (p / "완료기록" / "E3.md").rename(e3)
        self.assertIn('"permissionDecision": "deny"', hook("pre", self.edit_payload(p, "수정필요_대기.md", "k3"), p).stdout)
        self.tidy(p, codes=(3,))
        e3.rename(p / "완료기록" / "E3.md")
        self.check(p, "--quick", codes=(1,))                                  # 다시 빈칸 E2 만 — 확인된 key
        self.assertEqual(hook("pre", self.edit_payload(p, "수정필요_대기.md", "k4"), p).stdout.strip(), "")
        # ack_hours 가 지나면 다시 막음
        alerts = next(STATE.glob("*확인유지*/alerts.json"))
        a = json.loads(alerts.read_text(encoding="utf-8"))
        old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=10)).strftime("%Y%m%dT%H%M%SZ")
        for v in a["acked"].values():
            v["utc"] = old
        alerts.write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
        self.assertIn('"permissionDecision": "deny"', hook("pre", self.edit_payload(p, "수정필요_대기.md", "k5"), p).stdout)
        self.check(p, "--quick", codes=(2,))
        e2.rename(p / "완료기록" / "E2.md")

    def test_unknown_list_shape_warns_instead_of_guessing(self):
        p, _ = self._labelled("모양모름")
        listing = p / "수정필요_목록.md"
        listing.write_text(listing.read_text(encoding="utf-8").replace("#### A1 — ", "### A1 — "), encoding="utf-8")   # 옛 · 손편집 모양
        r = self.check(p, "--quick", codes=(1,))
        s3 = self._s3(r.stdout)
        self.assertEqual(len(s3), 1, r.stdout)
        self.assertIn("WARN  S3", s3[0])
        self.assertIn("포커스", s3[0])
        self.assertIn("ID 자리를 읽지 못해", s3[0])


# ---------------------------------------------------------------- 상태 폴더 id — 루트 경로의 NFC/NFD 와 무관
class StateFolderId(Fixture):
    """맥(2026-11-06 실측) — 훅은 표준 입력의 NFC 경로로, 셸의 도구는 파일 시스템의 NFD 경로로 Sync 를 만들어 상태 폴더가 둘로 갈렸고,
    사용자가 `--ack` 해도 훅의 경고가 풀리지 않았습니다. id 는 NFC 루트의 해시이고, 옛 정의의 폴더는 처음 만날 때 거둬들입니다."""

    @staticmethod
    def _cfg(root):
        return _config.Config(root, _config._merge(_config.DEFAULTS, {"project": "정규화 표본"}))

    def test_project_id_hashes_the_nfc_root(self):
        import unicodedata
        p = self.project("정규화")
        nfc_root, nfd_root = unicodedata.normalize("NFC", str(p)), unicodedata.normalize("NFD", str(p))
        self.assertNotEqual(nfc_root, nfd_root)
        self.assertEqual(_동기화.project_id("정규화 표본", nfc_root), _동기화.project_id("정규화 표본", nfd_root))
        self.assertEqual(_동기화.Sync(self._cfg(nfc_root)).state, _동기화.Sync(self._cfg(nfd_root)).state)
        # 옛 정의(정규화 없음)는 NFD 루트에서 다른 이름을 냈습니다 — 거둬들일 후보는 그것 하나, 루트가 어느 형이든 같은 후보
        legacy = _동기화.project_id("정규화 표본", nfd_root, form=None)
        self.assertNotEqual(legacy, _동기화.project_id("정규화 표본", nfd_root))
        self.assertEqual(_동기화.legacy_project_ids("정규화 표본", nfc_root), [legacy])
        self.assertEqual(_동기화.legacy_project_ids("정규화 표본", nfd_root), [legacy])
        self.assertEqual(_동기화.legacy_project_ids("ascii", os.path.abspath(os.sep + "ascii-only")), [])

    def test_legacy_state_folder_is_renamed_or_merged(self):
        import shutil
        import unicodedata
        p = self.project("옛폴더")
        cfg = _config.load(str(p))
        s = _동기화.Sync(cfg)
        legacy = STATE / _동기화.project_id(cfg.name, unicodedata.normalize("NFD", s.root), form=None)
        self.assertNotEqual(str(legacy), s.state)
        # ① 새 폴더가 없으면 옛 폴더의 이름만 바꿉니다
        shutil.rmtree(s.state)
        legacy.mkdir()
        (legacy / "alerts.json").write_text(json.dumps({"findings": [], "acked": {"S2:9": {"utc": _동기화.utc_stamp(), "text": "옛"}}}), encoding="utf-8")
        (legacy / "snap").mkdir()
        (legacy / "snap" / "old.bin").write_bytes(b"x")
        s = _동기화.Sync(cfg)
        self.assertFalse(legacy.exists())
        self.assertEqual(Path(s.state, "snap", "old.bin").read_bytes(), b"x")
        self.assertIn("S2:9", s._alerts()["acked"])
        # ② 둘 다 있으면 합칩니다 — 쓴 줄 · ID · 확인 기록은 합집합, 본 최대 번호는 큰 쪽, 스냅샷은 없는 것만, 옛 폴더는 지움
        s._save("written.json", {"a.md": {"h1": ["20260101T000000Z", "새"]}})
        s._save("ids.json", {"A1": "20260102T000000Z"})
        s._save("records_max.json", {"max": 3, "utc": "20260101T000000Z"})
        legacy.mkdir()
        (legacy / "written.json").write_text(json.dumps({"a.md": {"h2": ["20260101T000000Z", "옛"]}, "b.md": {"h3": ["20260101T000000Z", "옛"]}}),
                                             encoding="utf-8")
        (legacy / "ids.json").write_text(json.dumps({"A1": "20260101T000000Z", "A2": "20260103T000000Z"}), encoding="utf-8")
        (legacy / "records_max.json").write_text(json.dumps({"max": 7, "utc": "20260102T000000Z"}), encoding="utf-8")
        (legacy / "alerts.json").write_text(json.dumps({"findings": [{"level": "ERROR", "code": "S2", "key": "S2:7", "msg": "m", "items": []}],
                                                        "acked": {"S2:7": {"utc": _동기화.utc_stamp(), "text": "옛2"}}}), encoding="utf-8")
        (legacy / "snap").mkdir()
        (legacy / "snap" / "old.bin").write_bytes(b"y")          # 같은 이름 — 새 쪽을 지킵니다
        (legacy / "snap" / "old2.bin").write_bytes(b"z")
        s = _동기화.Sync(cfg)
        self.assertFalse(legacy.exists())
        self.assertEqual(Path(s.state, "snap", "old.bin").read_bytes(), b"x")
        self.assertEqual(Path(s.state, "snap", "old2.bin").read_bytes(), b"z")
        reg = s._load("written.json", {})
        self.assertEqual(set(reg["a.md"]), {"h1", "h2"})
        self.assertIn("b.md", reg)
        ids = s._load("ids.json", {})
        self.assertEqual(ids["A1"], "20260101T000000Z")           # 처음 본 시각은 더 이른 쪽
        self.assertIn("A2", ids)
        self.assertEqual(s.max_record_seen(), 7)
        acked = s._alerts()["acked"]
        self.assertIn("S2:9", acked)
        self.assertIn("S2:7", acked)
        self.assertEqual(_동기화.Sync(cfg).state, s.state)        # 다시 만들어도 조용함(옛 폴더 없음)

    def test_windows_path_sample_keeps_its_old_id(self):
        # 윈도 경로 표본 — ntpath 로 정의를 흉내 냅니다. 윈도 폴더 이름은 NFC 라 옛 정의와 같은 id(상태 폴더가 옮겨지지 않음)이고,
        # 드라이브 문자 대소문자 · 구분자 · NFD 표기는 모두 같은 id 로 모입니다(normcase → NFC).
        import ntpath
        import unicodedata
        saved = _동기화.os.path
        _동기화.os.path = ntpath
        try:
            win = "G:\\다른 컴퓨터\\작업 컴퓨터\\연구\\원고\\Journal_Paper_revision\\revision_1"
            cur = _동기화.project_id("표본", win)
            self.assertEqual(cur, _동기화.project_id("표본", win, form=None))                  # 옛 정의와 같음 — 이관 없음
            self.assertEqual(_동기화.legacy_project_ids("표본", win), [_동기화.project_id("표본", unicodedata.normalize("NFD", win), form=None)])
            self.assertEqual(cur, _동기화.project_id("표본", unicodedata.normalize("NFD", win)))
            self.assertEqual(cur, _동기화.project_id("표본", win.lower().replace("\\", "/")))
        finally:
            _동기화.os.path = saved

    def test_cli_ack_from_nfd_root_unblocks_hook_with_nfc_path(self):
        import unicodedata
        p = self.project("확인경로")
        nfc_root, nfd_root = unicodedata.normalize("NFC", str(p)), unicodedata.normalize("NFD", str(p))
        if not os.path.isdir(nfd_root):
            self.skipTest("이 파일 시스템은 NFD 경로를 같은 폴더로 보지 않습니다(NTFS · ext4) — 맥(APFS · HFS+)에서만 재현되는 사례")
        (p / "완료기록" / "E2.md").rename(self.scratch / "확인경로_E2.bak")
        self.assertIn('"permissionDecision": "deny"', hook("pre", self.edit_payload(Path(nfc_root), "수정필요_대기.md", "n1"), p).stdout)
        # 셸에서 NFD 루트로 돌린 --ack 가 훅(NFC 경로)의 경고를 닫아야 합니다 — 같은 상태 폴더
        run(PY + [str(p / "도구" / "동기화_점검.py"), "--dir", nfd_root, "--ack", "시험: NFD 루트에서 확인"], Path(nfd_root), codes=(0,))
        self.assertEqual(hook("pre", self.edit_payload(Path(nfc_root), "수정필요_대기.md", "n2"), p).stdout.strip(), "")
        folders = [d.name for d in STATE.iterdir() if d.name.startswith(_동기화._slug("동기화 표본 확인경로") + "-")]
        self.assertEqual(len(folders), 1, folders)
        (self.scratch / "확인경로_E2.bak").rename(p / "완료기록" / "E2.md")


if __name__ == "__main__":
    unittest.main()
