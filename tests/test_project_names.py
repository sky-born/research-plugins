"""프로젝트 폴더 · 파일 이름 — 새 프로젝트는 영어 기본값, 0.12 이하가 만든 프로젝트는 설정에 적은 옛 이름(한글)으로 그대로 돕니다.

옛 프로젝트는 합성 표본으로 만듭니다 — 새로 만든 프로젝트의 폴더 · 파일을 옛 이름으로 바꾸고, 설정은 0.12 의 init 이 쓰던 모양
(추적 파일 이름은 적혀 있고 도구 폴더 · 동기화 설정은 없음)으로 되돌립니다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_sync_guard import Fixture, PY, INITIALIZER, UPDATE, SKILL, hook, run  # noqa: E402  — SYNC_STATE_HOME 도 거기서

import _config  # noqa: E402

MANIFEST = json.loads((SKILL / "managed_files.json").read_text(encoding="utf-8"))
OLD_TRACKER = _config.LEGACY_DEFAULTS["tracker"]


def legacy_copy(p: Path, rename_tools=True) -> Path:
    """새 프로젝트 p 를 0.12 의 모양으로 — 도구 폴더 · 추적 파일 · 기록 폴더 · 스냅샷 폴더를 옛 이름으로, rename_tools 면 도구 파일도.
    rename_tools=False 는 도구 사본만 새 판으로 바뀌고 설정은 아직 적지 않은 상태입니다."""
    cfg_path = p / ".manuscript" / "project.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    new_t = cfg["tracker"]
    (p / new_t["records_dir"]).rename(p / OLD_TRACKER["records_dir"])
    archive_new = p / OLD_TRACKER["records_dir"] / Path(new_t["archive"]).name
    archive_new.rename(p / OLD_TRACKER["archive"])
    for key in ("index", "pending", "record_index", "literature", "proposals"):
        (p / new_t[key]).rename(p / OLD_TRACKER[key])
    snap = p / _config.DEFAULTS["sync"]["snapshot_dir"]
    if snap.exists():
        (p / "보관").mkdir(exist_ok=True)
        snap.rename(p / _config.LEGACY_DEFAULTS["sync"]["snapshot_dir"])
    tools = p / cfg.pop("tools_dir")
    for item in MANIFEST["files"]:
        if item.get("old") and rename_tools:
            (tools / Path(item["dst"]).name).rename(tools / item["old"])
    tools.rename(p / _config.LEGACY_DEFAULTS["tools_dir"])
    cfg["tracker"].update({k: OLD_TRACKER[k] for k in OLD_TRACKER})
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def pin(p: Path, pins: dict):
    cfg_path = p / ".manuscript" / "project.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    for k, v in pins.items():
        if isinstance(v, dict):
            cfg.setdefault(k, {}).update(v)
        else:
            cfg[k] = v
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class NewProject(Fixture):
    def test_fresh_project_paths_are_ascii(self):
        p = self.scratch / "fresh"
        run(PY + [str(INITIALIZER), str(p), "--name", "Fresh"], self.scratch)
        bad = [x.relative_to(p).as_posix() for x in p.rglob("*")
               if not x.relative_to(p).as_posix().isascii() and "__pycache__" not in x.parts]
        self.assertEqual(bad, [])
        self.assertTrue((p / _config.DEFAULTS["tools_dir"] / "tidy_tracker.py").is_file())

    def test_defaults_are_ascii(self):
        for sec, key, value in _config._items(_config.DEFAULTS):
            if key in ("triggers",):                # 트리거 값은 이름이 아니라 내용입니다
                continue
            for v in (value if isinstance(value, list) else [value]):
                if isinstance(v, str):
                    self.assertTrue(v.isascii(), (sec, key, v))


class LegacyProject(Fixture):
    def legacy(self, name, rename_tools=True):
        return legacy_copy(self.project(name, records=2), rename_tools)

    def test_unpinned_legacy_project_stops_tools_hook_and_update(self):
        p = self.legacy("옛 이름 설정 없음", rename_tools=False)
        r = run(PY + [str(p / "도구" / "check_sync.py"), "--quick"], p, codes=(1, 3))
        self.assertIn("옛 기본 이름", r.stderr + r.stdout)
        denied = hook("pre", self.edit_payload(p, OLD_TRACKER["pending"], "legacy-1"), p)
        self.assertIn("옛 기본 이름", json.loads(denied.stdout)["hookSpecificOutput"]["permissionDecisionReason"])
        allowed = hook("pre", self.edit_payload(p, ".manuscript/project.json", "legacy-2"), p)
        self.assertEqual(allowed.stdout.strip(), "")
        u = run(PY + [str(UPDATE), str(p), "--apply"], p, codes=(2,))
        self.assertIn('"tools_dir": "도구"', u.stdout)
        self.assertTrue((p / "도구" / "tidy_tracker.py").is_file(), "설정 전에는 아무것도 바꾸지 않습니다")

    def test_pinned_legacy_project_renames_tools_and_keeps_korean_names(self):
        p = self.legacy("옛 이름 설정함")
        pins = _config.legacy_pins(p, json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8")))
        self.assertEqual(pins.get("tools_dir"), "도구")
        pin(p, pins)
        # 로컬 수정판 하나 — 옛 이름 그대로 남기고 --force 로만 옮깁니다
        local = p / "도구" / "번호점검.py"
        local.write_text(local.read_text(encoding="utf-8") + "\n# 로컬 수정\n", encoding="utf-8")
        u = run(PY + [str(UPDATE), str(p), "--apply"], p, codes=(1,))
        self.assertIn("남김", u.stdout)
        for item in MANIFEST["files"]:
            if item.get("old") and item["old"] != "번호점검.py":
                self.assertFalse((p / "도구" / item["old"]).exists(), item["old"])
                self.assertTrue((p / "도구" / Path(item["dst"]).name).is_file(), item["dst"])
        self.assertTrue(local.is_file())
        run(PY + [str(UPDATE), str(p), "--apply", "--force", "도구/check_numbers.py"], p, codes=(0,))
        self.assertFalse(local.exists())
        self.assertTrue(list((p / ".manuscript" / "tools_backup").rglob("번호점검.py")))

        body = p / "본문9.md"
        body.write_text("# E? — 옛 이름 표본\n\n**완료일** 2026-11-24\n**대상** `manuscript/results.md` ③\n**상태** 확정\n\n본문.\n",
                        encoding="utf-8")
        outs = [run(PY + [str(p / "도구" / "new_record.py"), str(body)], p),
                run(PY + [str(p / "도구" / "tidy_tracker.py"), "--apply"], p, codes=(0, 1)),
                run(PY + [str(p / "도구" / "index_records.py")], p),
                run(PY + [str(p / "도구" / "check_sync.py"), "--quick"], p, codes=(0, 1))]
        self.assertTrue((p / "완료기록" / "E3.md").is_file())
        text = "\n".join(r.stdout + r.stderr for r in outs)
        text += (p / OLD_TRACKER["index"]).read_text(encoding="utf-8").split("## 2.", 1)[1]   # 생성 블록 — 머리는 init 이 쓴 그대로
        text += (p / OLD_TRACKER["record_index"]).read_text(encoding="utf-8")
        for english in ("tracker_", "records/", "records\\", "tools/", "tools\\", "archive/"):
            self.assertNotIn(english, text, english)
        self.assertIn("도구/tidy_tracker.py", (p / OLD_TRACKER["index"]).read_text(encoding="utf-8"))

    def test_local_old_copy_beside_new_name_is_kept_until_force(self):
        # 새 이름이 이미 있어도, 손으로 고친 옛 이름 사본은 --force 로만 백업한 뒤 지웁니다
        p = self.legacy("두 이름", rename_tools=False)
        pin(p, _config.legacy_pins(p, json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8"))))
        old = p / "도구" / "번호점검.py"
        old.write_text((p / "도구" / "check_numbers.py").read_text(encoding="utf-8") + "\n# 로컬 수정\n", encoding="utf-8")
        u = run(PY + [str(UPDATE), str(p), "--apply"], p, codes=(1,))
        self.assertIn("옛 이름 사본이 로컬 수정", u.stdout)
        self.assertTrue(old.is_file())
        run(PY + [str(UPDATE), str(p), "--apply", "--force", "도구/check_numbers.py"], p, codes=(0,))
        self.assertFalse(old.exists())
        self.assertTrue(list((p / ".manuscript" / "tools_backup").rglob("번호점검.py")))


if __name__ == "__main__":
    unittest.main()
