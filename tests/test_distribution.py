"""Regression checks for registration drift and shared source isolation."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from sync_codex_manifests import synchronize
from validate_shared_plugins import validate


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="shared-plugin-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.marketplace = self.root / ".claude-plugin" / "marketplace.json"
        self.manifest = self.root / "plugins" / "example" / ".claude-plugin" / "plugin.json"
        self.write_json(self.marketplace, {"name": "test-marketplace", "plugins": [
            {"name": "example", "source": "./plugins/example", "displayName": "Example"},
        ]})
        self.write_json(self.manifest, {"name": "example", "version": "1.0.0", "description": "Shared example.", "author": {"name": "Tester"}})
        self.skill = self.root / "plugins" / "example" / "skills" / "example" / "SKILL.md"
        self.skill.parent.mkdir(parents=True)
        self.skill.write_text("---\nname: example\ndescription: An example skill.\n---\nShared content.\n", encoding="utf-8")
        synchronize(self.root, check=False)

    @staticmethod
    def write_json(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_generation_is_idempotent_and_does_not_copy_skills(self):
        original = self.skill.read_bytes()
        self.assertEqual(synchronize(self.root, check=False), [])
        self.assertEqual(validate(self.root), ([], 1))
        self.assertEqual(self.skill.read_bytes(), original)
        self.assertEqual(list(self.root.rglob("SKILL.md")), [self.skill])

    def test_version_drift_fails_without_rewriting_generated_file(self):
        target = self.root / "plugins" / "example" / ".codex-plugin" / "plugin.json"
        original = target.read_bytes()
        source = json.loads(self.manifest.read_text())
        source["version"] = "1.1.0"
        self.write_json(self.manifest, source)
        self.assertTrue(synchronize(self.root, check=True))
        self.assertEqual(target.read_bytes(), original)
        self.assertTrue(validate(self.root)[0])
        synchronize(self.root, check=False)
        self.assertEqual(validate(self.root), ([], 1))

    def test_redirected_codex_skills_are_rejected(self):
        target = self.root / "plugins" / "example" / ".codex-plugin" / "plugin.json"
        value = json.loads(target.read_text(encoding="utf-8"))
        value["skills"] = "./other-skills/"
        self.write_json(target, value)
        errors, _ = validate(self.root)
        self.assertTrue(any("same skills directory" in error for error in errors))

    def test_plugin_paths_cannot_escape_repository(self):
        value = json.loads(self.marketplace.read_text())
        value["plugins"][0]["source"] = "../outside"
        self.write_json(self.marketplace, value)
        self.assertTrue(validate(self.root)[0])

    def test_unregistered_plugin_folder_fails(self):
        (self.root / "plugins" / "unregistered").mkdir()
        self.assertTrue(validate(self.root)[0])

    def test_missing_skill_is_rejected(self):
        self.skill.unlink()
        errors, _ = validate(self.root)
        self.assertTrue(any("missing SKILL.md" in error for error in errors))

    def test_marketplace_display_fields_follow_the_plugin_manifest(self):
        entry = json.loads(self.marketplace.read_text(encoding="utf-8"))["plugins"][0]
        self.assertEqual("Shared example.", entry["description"])           # filled in by the first sync
        self.assertEqual({"name": "Tester"}, entry["author"])
        self.assertEqual("Example", entry["displayName"])                    # entry-only keys are kept

        value = json.loads(self.marketplace.read_text(encoding="utf-8"))
        value["plugins"][0]["description"] = "Edited in the wrong place."
        value["plugins"][0]["repository"] = "https://example.invalid/repo"   # the manifest has no repository
        self.write_json(self.marketplace, value)
        errors, _ = validate(self.root)
        self.assertTrue(any(".claude-plugin/marketplace.json" in error for error in errors), errors)

        self.assertIn(".claude-plugin/marketplace.json", synchronize(self.root, check=False))
        entry = json.loads(self.marketplace.read_text(encoding="utf-8"))["plugins"][0]
        self.assertEqual("Shared example.", entry["description"])
        self.assertEqual("https://example.invalid/repo", entry["repository"])
        self.assertEqual(validate(self.root), ([], 1))


if __name__ == "__main__":
    unittest.main()
