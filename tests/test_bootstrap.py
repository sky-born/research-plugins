"""bootstrap.py without any app installed: the command plans, state parsing and the dry run.

The Claude Code and Codex executables are replaced by fakes, so nothing is registered or installed.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location("marketplace_bootstrap", ROOT / "bootstrap" / "bootstrap.py")
bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bootstrap)

NAME = "test-marketplace"
PLUGINS = ["alpha", "beta"]


class Plans(unittest.TestCase):
    def test_fresh_computer_registers_and_installs(self):
        self.assertEqual(
            [["plugin", "marketplace", "add", "owner/repo", "--scope", "user"],
             ["plugin", "install", f"alpha@{NAME}", "--scope", "user"],
             ["plugin", "install", f"beta@{NAME}", "--scope", "user"]],
            bootstrap.claude_commands(NAME, PLUGINS, "owner/repo", False, set()))

    def test_installed_plugins_are_updated_not_reinstalled(self):
        self.assertEqual(
            [["plugin", "marketplace", "update", NAME],
             ["plugin", "update", f"alpha@{NAME}"],
             ["plugin", "install", f"beta@{NAME}", "--scope", "user"]],      # added to the marketplace later
            bootstrap.claude_commands(NAME, PLUGINS, "owner/repo", True, {f"alpha@{NAME}"}))

    def test_codex_commands(self):
        listing = ["plugin", "list", "--marketplace", NAME, "--json"]
        adds = [["plugin", "add", f"alpha@{NAME}"], ["plugin", "add", f"beta@{NAME}"]]
        for action in ("install", "update"):
            self.assertEqual(
                [["plugin", "marketplace", "add", "owner/repo", "--ref", "v1"],
                 ["plugin", "marketplace", "upgrade", NAME], *adds, listing],
                bootstrap.codex_commands(action, NAME, PLUGINS, "owner/repo", local=False, ref="v1"))
        self.assertEqual([["plugin", "marketplace", "add", "/clone"], *adds, listing],
                         bootstrap.codex_commands("install", NAME, PLUGINS, "/clone", local=True, ref="main"))
        self.assertEqual([listing], bootstrap.codex_commands("status", NAME, PLUGINS, "owner/repo", local=False, ref="main"))


class Runs(unittest.TestCase):
    """main() against this repository's own marketplace.json, with every executable faked."""

    def setUp(self):
        self.name, self.plugins = bootstrap.marketplace(ROOT)
        self.ran: list[list[str]] = []
        self.markets = [{"name": "other", "source": "github", "repo": "x/y"}]
        self.installed: list[dict] = []
        patches = [
            mock.patch.object(bootstrap, "find_claude", return_value=("claude-bin", "PATH")),
            mock.patch.object(bootstrap, "claude_version", return_value="9.9.9 (fake)"),
            mock.patch.object(bootstrap, "remote_url", return_value="https://github.com/owner/repo.git"),
            mock.patch.object(bootstrap, "json_output", side_effect=self.fake_json),
            mock.patch.object(bootstrap, "run", side_effect=self.fake_run),
            mock.patch.object(bootstrap, "find_codex", side_effect=bootstrap.Stop("Codex CLI not found (test)")),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def fake_json(self, command, **_):
        return self.markets if "marketplace" in command else self.installed

    def fake_run(self, command, **_):
        self.ran.append([str(part) for part in command])
        return mock.Mock(returncode=0, stdout="")

    def main(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = bootstrap.main(list(argv))
        return code, out.getvalue()

    def test_dry_run_prints_the_plan_and_runs_nothing(self):
        code, out = self.main("install", "--dry-run")
        self.assertEqual(0, code, out)
        self.assertEqual([], self.ran)
        self.assertIn("claude-bin plugin marketplace add owner/repo --scope user", out)
        for plugin in self.plugins:
            self.assertIn(f"claude-bin plugin install {plugin}@{self.name} --scope user", out)
        self.assertIn("codex: not found on this computer - skipped", out)

    def test_update_checks_access_then_runs_the_plan_in_order(self):
        self.markets.append({"name": self.name, "source": "github", "repo": "owner/repo"})
        self.installed = [{"id": f"{self.plugins[0]}@{self.name}", "version": "0.0.1", "enabled": True}]
        code, out = self.main("update")
        self.assertEqual(0, code, out)
        self.assertEqual(["git", "ls-remote", "--exit-code", "https://github.com/owner/repo.git", "HEAD"], self.ran[0])
        self.assertEqual(["claude-bin", "plugin", "marketplace", "update", self.name], self.ran[1])
        self.assertEqual(["claude-bin", "plugin", "update", f"{self.plugins[0]}@{self.name}"], self.ran[2])
        self.assertTrue(all(command[2] == "install" for command in self.ran[3:]), self.ran)
        self.assertIn("installed 0.0.1, this clone has", out)      # the fake state never changes

    def test_a_failing_command_stops_the_run(self):
        def failing(command, **_):
            self.ran.append([str(part) for part in command])
            if "install" in command:
                raise bootstrap.Stop("exit 1: install")
            return mock.Mock(returncode=0, stdout="")
        with mock.patch.object(bootstrap, "run", side_effect=failing):
            code, out = self.main("install")
        self.assertEqual(1, code, out)
        self.assertEqual(1, sum("install" in command for command in self.ran))     # nothing after the failure

    def test_status_reports_missing_and_outdated_plugins_without_running_anything(self):
        self.installed = [{"id": f"{self.plugins[0]}@{self.name}", "version": "0.0.1", "enabled": True},
                          {"id": "unrelated@other", "version": "1.0.0", "enabled": True}]
        code, out = self.main("status")
        self.assertEqual(0, code, out)
        self.assertEqual([], self.ran)
        self.assertIn(f"marketplace {self.name} is not registered", out)
        self.assertIn(f"{self.plugins[0]}: installed 0.0.1", out)
        if len(self.plugins) > 1:
            self.assertIn(f"{self.plugins[1]}: not installed", out)
        self.assertNotIn("unrelated", out)

    def test_a_marketplace_registered_from_another_address_stops_before_anything_runs(self):
        self.markets.append({"name": self.name, "source": "github", "repo": "someone/old-repo"})
        code, out = self.main("update")
        self.assertEqual(1, code, out)
        self.assertEqual([], self.ran)
        self.assertIn("someone/old-repo", out)
        self.assertIn(f"plugin marketplace remove {self.name}", out)
        code, out = self.main("status")                    # status only reports
        self.assertEqual(0, code, out)

    def test_the_same_address_written_differently_is_not_a_mismatch(self):
        for entry in ({"source": "github", "repo": "Owner/Repo"},
                      {"source": "git", "url": "https://github.com/owner/repo.git"},
                      {"source": "git", "url": "git@github.com:owner/repo"},
                      {"source": "url", "url": "https://github.com/owner/repo/"}):
            self.ran.clear()
            self.markets[:] = [dict(entry, name=self.name)]
            code, out = self.main("update")
            self.assertEqual(0, code, out)
            self.assertIn(["claude-bin", "plugin", "marketplace", "update", self.name], self.ran)
        for first, second, same in (("https://gitlab.example/a/b.git", "https://gitlab.example/a/b", True),
                                    ("owner/repo", "owner/other", False)):
            self.assertEqual(same, bootstrap.same_remote(first, second), (first, second))

    def test_unexpected_cli_output_stops(self):
        with mock.patch.object(bootstrap, "json_output", return_value={"not": "a list"}):
            code, out = self.main("status")
        self.assertEqual(1, code, out)

    def test_an_app_asked_for_by_name_must_exist(self):
        code, out = self.main("status", "--app", "codex")
        self.assertEqual(1, code, out)
        self.assertIn("Codex CLI not found", out)

    def test_codex_only_options_need_app_codex(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            bootstrap.main(["install", "--local"])


if __name__ == "__main__":
    unittest.main()
