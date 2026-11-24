"""Project folder and file names — a new project uses English defaults; a project made by 0.12 or earlier keeps running on the old (Korean) names written in its settings.

An old project is built as a synthetic fixture — the folders and files of a new project are renamed to the old names, and the settings are put back into the shape written by the 0.12 init
(tracker file names are written; the tools folder and sync settings are absent).
Old-format data on purpose: these fixtures carry the old Korean *names* (folders, tracker files, tool files), taken from `_config.LEGACY_DEFAULTS` and
`_config.LEGACY_TOOL_NAMES`. Their tracker anchors stay English (the project is made by the current init), so the writing tools accept them — reading the
old Korean anchors and migrating them is covered by test_format_migration.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_sync_guard import Fixture, PY, INITIALIZER, UPDATE, SKILL, hook, run  # noqa: E402  — SYNC_STATE_HOME is set there too

import _config  # noqa: E402

MANIFEST = json.loads((SKILL / "managed_files.json").read_text(encoding="utf-8"))
OLD_TRACKER = _config.LEGACY_DEFAULTS["tracker"]
OLD_TOOLS = _config.LEGACY_DEFAULTS["tools_dir"]                         # the old tools folder name
OLD_NUMBERS = _config.LEGACY_TOOL_NAMES["tools/check_numbers.py"]        # the old file name of check_numbers.py


def old_name(item):
    """The 0.12 file name of a managed file, or None."""
    return _config.LEGACY_TOOL_NAMES.get(item["src"])


def legacy_copy(p: Path, rename_tools=True) -> Path:
    """Turn a new project p into the 0.12 shape — tools folder, tracker files, records folder and snapshot folder get the old names, and the tool files too when rename_tools is set.
    rename_tools=False leaves only the tool copies at the new version, with the settings not yet written."""
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
        old_snap = p / _config.LEGACY_DEFAULTS["sync"]["snapshot_dir"]
        old_snap.parent.mkdir(exist_ok=True)
        snap.rename(old_snap)
    tools = p / cfg.pop("tools_dir")
    for item in MANIFEST["files"]:
        if old_name(item) and rename_tools:
            (tools / Path(item["dst"]).name).rename(tools / old_name(item))
    tools.rename(p / OLD_TOOLS)
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
            for v in (value if isinstance(value, list) else [value]):
                if isinstance(v, str):
                    self.assertTrue(v.isascii(), (sec, key, v))     # the default triggers are English now too

    def test_every_old_tool_name_is_a_managed_file(self):
        srcs = {item["src"] for item in MANIFEST["files"]}
        self.assertTrue(_config.LEGACY_TOOL_NAMES)
        self.assertEqual(sorted(set(_config.LEGACY_TOOL_NAMES) - srcs), [], "an old name for a file that is not managed")
        self.assertFalse(any("old" in item for item in MANIFEST["files"]), "old names live in _config.LEGACY_TOOL_NAMES only")


class LegacyProject(Fixture):
    def legacy(self, name, rename_tools=True):
        return legacy_copy(self.project(name, records=2), rename_tools)

    def test_unpinned_legacy_project_stops_tools_hook_and_update(self):
        p = self.legacy("legacy unpinned", rename_tools=False)
        r = run(PY + [str(p / OLD_TOOLS / "check_sync.py"), "--quick"], p, codes=(1, 3))
        self.assertIn("old default (Korean) names", r.stderr + r.stdout)
        denied = hook("pre", self.edit_payload(p, OLD_TRACKER["pending"], "legacy-1"), p)
        self.assertIn("old default (Korean) names", json.loads(denied.stdout)["hookSpecificOutput"]["permissionDecisionReason"])
        allowed = hook("pre", self.edit_payload(p, ".manuscript/project.json", "legacy-2"), p)
        self.assertEqual(allowed.stdout.strip(), "")
        u = run(PY + [str(UPDATE), str(p), "--apply"], p, codes=(2,))
        self.assertIn('"tools_dir": "%s"' % OLD_TOOLS, u.stdout)
        self.assertTrue((p / OLD_TOOLS / "tidy_tracker.py").is_file(), "nothing is changed before the settings are written")

    def test_pinned_legacy_project_renames_tools_and_keeps_korean_names(self):
        p = self.legacy("legacy pinned")
        pins = _config.legacy_pins(p, json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8")))
        self.assertEqual(pins.get("tools_dir"), OLD_TOOLS)
        pin(p, pins)
        # one locally modified copy — it stays under the old name and is moved only with --force
        local = p / OLD_TOOLS / OLD_NUMBERS
        local.write_text(local.read_text(encoding="utf-8") + "\n# local edit\n", encoding="utf-8")
        u = run(PY + [str(UPDATE), str(p), "--apply"], p, codes=(1,))
        self.assertIn("kept", u.stdout)
        for item in MANIFEST["files"]:
            if old_name(item) and old_name(item) != OLD_NUMBERS:
                self.assertFalse((p / OLD_TOOLS / old_name(item)).exists(), old_name(item))
                self.assertTrue((p / OLD_TOOLS / Path(item["dst"]).name).is_file(), item["dst"])
        self.assertTrue(local.is_file())
        run(PY + [str(UPDATE), str(p), "--apply", "--force", OLD_TOOLS + "/check_numbers.py"], p, codes=(0,))
        self.assertFalse(local.exists())
        self.assertTrue(list((p / ".manuscript" / "tools_backup").rglob(OLD_NUMBERS)))

        body = p / "body9.md"
        body.write_text("# E? — legacy names sample\n\n**Completed** 2026-11-24\n**Target** `manuscript/results.md` ③\n**Status** confirmed\n\nBody.\n",
                        encoding="utf-8")
        outs = [run(PY + [str(p / OLD_TOOLS / "new_record.py"), str(body)], p),
                run(PY + [str(p / OLD_TOOLS / "tidy_tracker.py"), "--apply"], p, codes=(0, 1)),
                run(PY + [str(p / OLD_TOOLS / "index_records.py")], p),
                run(PY + [str(p / OLD_TOOLS / "check_sync.py"), "--quick"], p, codes=(0, 1))]
        self.assertTrue((p / OLD_TRACKER["records_dir"] / "E3.md").is_file())
        text = "\n".join(r.stdout + r.stderr for r in outs)
        text += (p / OLD_TRACKER["index"]).read_text(encoding="utf-8").split("## 2.", 1)[1]   # generated block — the head is as written by init
        text += (p / OLD_TRACKER["record_index"]).read_text(encoding="utf-8")
        for english in ("tracker_", "records/", "records\\", "tools/", "tools\\", "archive/"):
            self.assertNotIn(english, text, english)
        self.assertIn(OLD_TOOLS + "/tidy_tracker.py", (p / OLD_TRACKER["index"]).read_text(encoding="utf-8"))

    def test_local_old_copy_beside_new_name_is_kept_until_force(self):
        # even when the new name exists, a hand-edited old-name copy is deleted only with --force, after a backup
        p = self.legacy("two names", rename_tools=False)
        pin(p, _config.legacy_pins(p, json.loads((p / ".manuscript" / "project.json").read_text(encoding="utf-8"))))
        old = p / OLD_TOOLS / OLD_NUMBERS
        old.write_text((p / OLD_TOOLS / "check_numbers.py").read_text(encoding="utf-8") + "\n# local edit\n", encoding="utf-8")
        u = run(PY + [str(UPDATE), str(p), "--apply"], p, codes=(1,))
        self.assertIn("the old-name copy is locally modified", u.stdout)
        self.assertTrue(old.is_file())
        run(PY + [str(UPDATE), str(p), "--apply", "--force", OLD_TOOLS + "/check_numbers.py"], p, codes=(0,))
        self.assertFalse(old.exists())
        self.assertTrue(list((p / ".manuscript" / "tools_backup").rglob(OLD_NUMBERS)))


if __name__ == "__main__":
    unittest.main()
