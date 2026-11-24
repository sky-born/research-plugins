"""release.py against throwaway git repositories: the version rule, tags, changelog and README parity.

No network and no Claude CLI: each case builds a bare "origin" and a working clone in a temp folder
and runs release.main() with --skip-claude --skip-tests.
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
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cli_common  # noqa: E402
import release  # noqa: E402
from sync_codex_manifests import synchronize  # noqa: E402


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          encoding="utf-8").stdout.strip()


class RepoCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="release-test-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        base = Path(temp.name).resolve()
        self.origin, self.root = base / "origin.git", base / "work"
        git(base, "init", "--bare", "-b", "main", str(self.origin))
        git(base, "init", "-b", "main", str(self.root))
        # Runners and fresh machines have no git identity; the fixture brings its own.
        for key, value in (("user.name", "Tester"), ("user.email", "tester@example.invalid"),
                           ("core.autocrlf", "false"), ("commit.gpgsign", "false"), ("tag.gpgsign", "false")):
            git(self.root, "config", key, value)
        git(self.root, "remote", "add", "origin", str(self.origin))
        self.write(".claude-plugin/marketplace.json", json.dumps(
            {"name": "test-marketplace", "plugins": [{"name": "example", "source": "./plugins/example"}]}))
        self.add_plugin("example")
        synchronize(self.root, check=False)
        self.commit("initial")
        git(self.root, "push", "origin", "main")

    # ------------------------------------------------------------ helpers
    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def add_plugin(self, name: str, version: str = "1.0.0") -> None:
        self.write(f"plugins/{name}/.claude-plugin/plugin.json", json.dumps(
            {"name": name, "version": version, "description": "Example.", "author": {"name": "Tester"}}, indent=2) + "\n")
        self.write(f"plugins/{name}/skills/{name}/SKILL.md", f"---\nname: {name}\ndescription: Example skill.\n---\nBody.\n")

    def commit(self, subject: str) -> str:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", subject)
        return git(self.root, "rev-parse", "HEAD")

    def release(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        command, rest = argv[0], list(argv[1:])
        if command != "bump":
            rest += ["--skip-claude", "--skip-tests"]
        with contextlib.redirect_stdout(out):
            code = release.main([command, *rest, "--root", str(self.root)])
        return code, out.getvalue()

    def version(self, name: str = "example") -> str:
        return json.loads((self.root / f"plugins/{name}/.claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]

    def remote_tags(self) -> list[str]:
        return sorted(git(self.origin, "tag").split())


class VersionRule(RepoCase):
    def test_unchanged_repository_passes_and_has_nothing_to_release(self):
        code, out = self.release("publish")
        self.assertEqual(0, code, out)
        self.assertIn("nothing to release", out)

    def test_changed_plugin_without_a_version_bump_stops(self):
        self.write("plugins/example/skills/example/SKILL.md", "---\nname: example\ndescription: Changed.\n---\nBody.\n")
        code, out = self.release("check")
        self.assertEqual(1, code, out)
        self.assertIn("version is still 1.0.0", out)
        self.assertIn("plugins/example/skills/example/SKILL.md", out)

    def test_bump_raises_the_version_and_regenerates_derived_files(self):
        self.write("plugins/example/skills/example/SKILL.md", "---\nname: example\ndescription: Changed.\n---\nBody.\n")
        code, out = self.release("bump", "example", "patch")
        self.assertEqual(0, code, out)
        self.assertEqual("1.0.1", self.version())
        codex = json.loads((self.root / "plugins/example/.codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("1.0.1", codex["version"])
        code, out = self.release("check")
        self.assertEqual(0, code, out)
        self.assertIn("example  1.0.0 -> 1.0.1", out)

    def test_bump_parts_and_explicit_versions(self):
        for part, expected in (("minor", "1.1.0"), ("major", "2.0.0"), ("2.3.4", "2.3.4")):
            code, out = self.release("bump", "example", part)
            self.assertEqual((0, expected), (code, self.version()), out)
        code, out = self.release("bump", "example", "2.3.4")          # not higher
        self.assertEqual(1, code, out)
        code, out = self.release("bump", "missing", "patch")
        self.assertEqual(1, code, out)
        self.assertIn("unknown plugin", out)

    def test_files_outside_plugins_need_no_version(self):
        self.write("docs/notes.md", "notes\n")
        code, out = self.release("check")
        self.assertEqual(0, code, out)
        self.assertIn("no plugin changed", out)

    def test_a_plugin_absent_from_the_baseline_is_new(self):
        market = self.root / ".claude-plugin/marketplace.json"
        data = json.loads(market.read_text(encoding="utf-8"))
        data["plugins"].append({"name": "extra", "source": "./plugins/extra"})
        self.write(".claude-plugin/marketplace.json", json.dumps(data))
        self.add_plugin("extra", "0.1.0")
        synchronize(self.root, check=False)
        code, out = self.release("check")
        self.assertEqual(0, code, out)
        self.assertIn("extra  (new) -> 0.1.0", out)

    def test_stale_generated_metadata_stops(self):
        manifest = self.root / "plugins/example/.claude-plugin/plugin.json"
        manifest.write_text(manifest.read_text(encoding="utf-8").replace("1.0.0", "1.0.1"), encoding="utf-8", newline="\n")
        code, out = self.release("check")
        self.assertEqual(1, code, out)
        self.assertIn("sync_codex_manifests.py", out)

    def test_version_comparison(self):
        self.assertTrue(release.version_increased("0.9.6", "0.10.0"))
        self.assertTrue(release.version_increased("1.0.0", "1.0.1-rc.1"))
        self.assertFalse(release.version_increased("0.10.0", "0.9.9"))
        self.assertFalse(release.version_increased("1.2.3", "1.2.3"))


class Publish(RepoCase):
    def bumped(self) -> None:
        self.write("plugins/example/skills/example/SKILL.md", "---\nname: example\ndescription: Changed.\n---\nBody.\n")
        self.assertEqual(0, self.release("bump", "example", "patch")[0])

    def test_publish_commits_pushes_and_tags(self):
        self.bumped()
        code, out = self.release("publish", "-m", "example v1.0.1: change", "-m", "Body paragraph.")
        self.assertEqual(0, code, out)
        head = git(self.root, "rev-parse", "HEAD")
        self.assertEqual(head, git(self.origin, "rev-parse", "main"))
        self.assertEqual("example v1.0.1: change\n\nBody paragraph.", git(self.root, "log", "-1", "--format=%B"))
        self.assertEqual(["example--v1.0.1"], self.remote_tags())
        self.assertEqual("tag", git(self.origin, "cat-file", "-t", "example--v1.0.1"))          # annotated
        self.assertEqual("example 1.0.1", git(self.origin, "tag", "-l", "--format=%(contents:subject)", "example--v1.0.1"))
        self.assertEqual(head, git(self.origin, "rev-parse", "example--v1.0.1^{commit}"))

    def test_no_push_and_no_tag_stay_local_and_a_later_publish_finishes(self):
        self.bumped()
        before = git(self.origin, "rev-parse", "main")
        code, out = self.release("publish", "-m", "example v1.0.1", "--no-push", "--no-tag")
        self.assertEqual(0, code, out)
        self.assertEqual(before, git(self.origin, "rev-parse", "main"))
        self.assertEqual("", git(self.root, "tag"))
        code, out = self.release("publish")                       # clean tree, ahead of origin
        self.assertEqual(0, code, out)
        self.assertIn("working tree is clean", out)
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), git(self.origin, "rev-parse", "main"))
        self.assertEqual(["example--v1.0.1"], self.remote_tags())

    def test_tag_lands_on_the_last_commit_that_changed_the_plugin(self):
        self.bumped()
        plugin_commit = self.commit("example v1.0.1")
        self.write("docs/notes.md", "notes\n")
        self.commit("docs only")
        code, out = self.release("publish")
        self.assertEqual(0, code, out)
        self.assertEqual(plugin_commit, git(self.origin, "rev-parse", "example--v1.0.1^{commit}"))

    def test_a_local_tag_that_was_never_pushed_is_pushed(self):
        self.bumped()
        commit = self.commit("example v1.0.1")
        git(self.root, "tag", "-a", "example--v1.0.1", "-m", "example 1.0.1", commit)
        code, out = self.release("publish")
        self.assertEqual(0, code, out)
        self.assertIn("already exists", out)
        self.assertEqual(["example--v1.0.1"], self.remote_tags())

    def test_a_tag_on_another_commit_stops_instead_of_passing_as_already_there(self):
        git(self.root, "tag", "-a", "example--v1.0.1", "-m", "example 1.0.1", "HEAD")
        before = git(self.root, "rev-parse", "HEAD")
        self.bumped()
        code, out = self.release("publish", "-m", "example v1.0.1")
        self.assertEqual(1, code, out)
        self.assertIn("already exists on", out)
        self.assertEqual(before, git(self.root, "rev-parse", "HEAD"))            # stopped before committing
        self.assertEqual(before, git(self.origin, "rev-parse", "main"))
        self.assertEqual([], self.remote_tags())
        self.commit("example v1.0.1")                                            # committed by hand: still refused
        code, out = self.release("publish")
        self.assertEqual(1, code, out)
        self.assertEqual(before, git(self.origin, "rev-parse", "main"))

    def test_long_subject_warns(self):
        self.write("docs/notes.md", "notes\n")
        code, out = self.release("publish", "-m", "x" * 73, "--no-push")
        self.assertEqual(0, code, out)
        self.assertIn("commit subject is 73 characters", out)

    def test_changelog_entry_is_required_once_the_file_exists(self):
        self.write("CHANGELOG.md", "# Changelog\n\n## example\n\n### 1.0.0\n\n- First.\n")
        self.commit("changelog")
        git(self.root, "push", "origin", "main")
        self.bumped()
        code, out = self.release("check")
        self.assertEqual(1, code, out)
        self.assertIn("add '### 1.0.1'", out)
        self.write("CHANGELOG.md", "# Changelog\n\n## example\n\n### 1.0.1 - 2026-01-01\n\n### 1.0.0\n\n- First.\n")
        self.assertEqual(1, self.release("check")[0])               # heading without a bullet
        self.write("CHANGELOG.md", "# Changelog\n\n## example\n\n### 1.0.1 - 2026-01-01\n\n- Changed.\n\n### 1.0.0\n\n- First.\n")
        code, out = self.release("check")
        self.assertEqual(0, code, out)


class RepositoryWithoutHistory(unittest.TestCase):
    """This repository's files committed as the first commit of a new repository must still pass the checks."""

    def test_checks_pass_when_the_files_start_a_new_repository(self):
        source = Path(__file__).resolve().parents[1]
        temp = tempfile.TemporaryDirectory(prefix="fresh-repo-test-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve() / "repo"
        listed = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files", "-z"], cwd=source,
                                check=True, capture_output=True).stdout.decode("utf-8").split("\0")
        for name in filter(None, listed):
            if (source / name).is_file():                     # a file deleted but not committed yet is skipped
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((source / name).read_bytes())
        git(root, "init", "-b", "main")
        for key, value in (("user.name", "Tester"), ("user.email", "tester@example.invalid"),
                           ("core.autocrlf", "false"), ("commit.gpgsign", "false")):
            git(root, "config", key, value)
        git(root, "add", "-A")
        git(root, "commit", "-m", "first commit")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = release.main(["check", "--root", str(root), "--baseline", "HEAD", "--no-fetch",
                                 "--skip-claude", "--skip-tests"])
        self.assertEqual(0, code, out.getvalue())
        self.assertIn("tool hash list is current", out.getvalue())


class ReadmeParity(unittest.TestCase):
    BASE = ("# Title\n\nEnglish | [Korean](README.ko.md)\n\n## Install\n\nSee [rules](CLAUDE.md#rules).\n\n"
            "```bash\ngit pull   # get the latest\n# then check\npython scripts/release.py check\n"
            "python scripts/release.py bump <plugin> patch\n```\n\n"
            "```\ntree with prose\n```\n")
    OTHER = ("# 제목\n\n[English](README.md) | 한국어\n\n## 설치\n\n[규칙](CLAUDE.md#규칙) 참고.\n\n"
             "```bash\ngit pull   # 최신으로\n# 그다음 검사\npython scripts/release.py check\n"
             "python scripts/release.py bump <플러그인> patch\n```\n\n"
             "```\n설명이 붙은 트리\n```\n")

    def problems(self, other: str) -> list[str]:
        return release.compare_readmes("README.md", self.BASE, "README.ko.md", other)

    def test_translation_with_the_same_structure_passes(self):
        self.assertEqual([], self.problems(self.OTHER))

    def test_a_changed_command_is_reported(self):
        found = self.problems(self.OTHER.replace("release.py check", "release.py publish"))
        self.assertEqual(1, len(found), found)
        self.assertIn("code block 1 (bash)", found[0])

    def test_a_missing_heading_is_reported(self):
        found = self.problems(self.OTHER.replace("## 설치\n", ""))
        self.assertTrue(any("heading structure differs" in problem for problem in found), found)

    def test_a_missing_link_and_an_unclosed_fence_are_reported(self):
        found = self.problems(self.OTHER.replace("[규칙](CLAUDE.md#규칙)", "규칙"))
        self.assertTrue(any("link targets differ" in problem for problem in found), found)
        found = self.problems(self.OTHER + "\n```text\nopen\n")
        self.assertTrue(any("never closed" in problem for problem in found), found)

    def test_this_repository_has_matching_readmes(self):
        problems, _ = release.readme_parity(Path(__file__).resolve().parents[1])
        self.assertEqual([], problems)


class TryInSession(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="release-try-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / ".claude-plugin").mkdir()
        (self.root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
            {"name": "test-marketplace", "plugins": [{"name": "example", "source": "./plugins/example"}]}), encoding="utf-8")
        for skill in ("one", "two"):
            path = self.root / "plugins" / "example" / "skills" / skill / "SKILL.md"
            path.parent.mkdir(parents=True)
            path.write_text("", encoding="utf-8")
        self.folder = self.root / "trial"
        self.folder.mkdir()

    def start(self, path=None, skills=("example:one", "example:two")) -> dict:
        return {"plugins": [{"name": "example", "path": str(path or self.root / "plugins" / "example")}],
                "skills": list(skills)}

    def problems(self, start: dict) -> list[str]:
        return release.load_problems(start, self.root, ["example"])

    def run_try(self, start: dict) -> tuple[int, str]:
        out = io.StringIO()
        with mock.patch.object(release, "find_claude", return_value=("claude", "test")), \
                mock.patch.object(release, "claude_version", return_value="claude 0.0.0"), \
                mock.patch.object(release, "read_start_info", return_value=start), \
                mock.patch.object(release.sys.stdin, "isatty", return_value=False), \
                contextlib.redirect_stdout(out):
            code = release.main(["try", str(self.folder), "--root", str(self.root)])
        return code, out.getvalue()

    def test_one_plugin_dir_per_plugin(self):
        self.assertEqual(["--plugin-dir", str(self.root / "plugins" / "a"), "--plugin-dir", str(self.root / "plugins" / "b")],
                         release.plugin_dir_args(self.root, ["a", "b"]))

    def test_clone_with_every_skill_listed_passes(self):
        self.assertEqual([], self.problems(self.start()))

    def test_installed_copy_is_reported(self):
        self.assertIn("not from this clone", self.problems(self.start(path=self.root / "cache" / "example"))[0])

    def test_skill_missing_from_the_session_is_reported(self):
        self.assertIn("example:two is not in the session's skill list", self.problems(self.start(skills=["example:one"]))[0])

    def test_plugin_not_loaded_is_reported(self):
        self.assertEqual(["example was not loaded"], self.problems({"plugins": [], "skills": []}))

    def test_start_up_info_without_lists_stops_instead_of_passing(self):
        self.assertIn("has no plugins or skills list", self.problems({})[0])

    def test_outside_a_terminal_it_prints_the_command_instead_of_opening(self):
        code, out = self.run_try(self.start())
        self.assertEqual(0, code)
        self.assertIn("open the session yourself", out)
        self.assertIn("--plugin-dir", out)

    def test_a_problem_stops_before_the_session(self):
        code, out = self.run_try(self.start(skills=[]))
        self.assertEqual(1, code)
        self.assertNotIn("open the session yourself", out)


REAL_BUNDLE_BASES = cli_common._bundle_bases


def isolate_bundle_bases(case: unittest.TestCase, base: Path) -> None:
    """Point the home and Applications folders into `base`, so an app installed on this computer cannot leak in."""
    def bases(env):
        found = REAL_BUNDLE_BASES(env)
        found.update(home=base / "home", applications=base / "Applications")
        return found
    patch = mock.patch.object(cli_common, "_bundle_bases", side_effect=bases)
    patch.start()
    case.addCleanup(patch.stop)


def touch(path: Path, mtime: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


class FindClaude(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="claude-cli-test-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        isolate_bundle_bases(self, self.base)
        self.explicit, self.session, self.path, self.bundle = (self.base / name for name in ("explicit", "session", "path", "bundle"))
        for file in (self.explicit, self.session, self.path, self.bundle):
            file.write_text("", encoding="utf-8")

    def find(self, explicit=None, session=True, on_path=True, bundle=True):
        env = {"CLAUDE_CODE_EXECPATH": str(self.session)} if session else {}
        with mock.patch.object(cli_common.shutil, "which", return_value=str(self.path) if on_path else None), \
                mock.patch.object(cli_common, "_bundle_candidates", return_value=[self.bundle] if bundle else []):
            return cli_common.find_claude(explicit, env)

    def test_order_is_explicit_then_session_then_path_then_app_bundle(self):
        self.assertEqual((str(self.explicit), "--claude"), self.find(str(self.explicit)))
        self.assertEqual((str(self.session), "CLAUDE_CODE_EXECPATH"), self.find())
        self.assertEqual((str(self.path), "PATH"), self.find(session=False))
        self.assertEqual((str(self.bundle), "desktop app bundle"), self.find(session=False, on_path=False))

    def test_nothing_found_stops_instead_of_skipping(self):
        with self.assertRaises(cli_common.Stop):
            self.find(session=False, on_path=False, bundle=False)
        with self.assertRaises(cli_common.Stop):
            self.find(str(self.base / "missing"))

    def test_newest_app_bundle_wins(self):
        for version in ("2.1.99", "2.1.330", "2.1.247"):
            target = self.base / "Claude-Data" / "pkg" / "claude-code" / version / "abc" / "claude.exe"
            target.parent.mkdir(parents=True)
            target.write_text("", encoding="utf-8")
        found = cli_common._bundle_candidates({"LOCALAPPDATA": str(self.base)})
        self.assertEqual("2.1.330", found[0].parts[-3])

    def test_macos_app_bundle_with_and_without_the_build_folder(self):
        support = self.base / "home" / "Library" / "Application Support" / "Claude" / "claude-code"
        binary = Path("claude.app") / "Contents" / "MacOS" / "claude"
        oldest = touch(support / "2.1.99" / "abc123" / binary)
        newest = touch(support / "2.1.330" / "def456" / binary)
        without_build_folder = touch(support / "2.1.247" / binary)
        self.assertEqual([newest, without_build_folder, oldest], cli_common._bundle_candidates({}))

    def test_remote_source(self):
        for url in ("https://github.com/owner/repo", "https://github.com/owner/repo.git",
                    "git@github.com:owner/repo.git", "ssh://git@github.com/owner/repo.git"):
            self.assertEqual("owner/repo", cli_common.remote_source(url), url)
        for url in ("https://gitlab.example/owner/repo.git", "/srv/git/repo.git"):
            self.assertEqual(url, cli_common.remote_source(url))



class FindCodex(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="codex-cli-test-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        isolate_bundle_bases(self, self.base)
        self.explicit, self.path = self.base / "explicit", self.base / "path"
        for file in (self.explicit, self.path):
            file.write_text("", encoding="utf-8")
        self.bundles = []
        for n, folder in enumerate(("aaaa", "bbbb")):            # 폴더 이름은 해시 — 판이 없어 수정 시각이 새것을 정합니다
            target = self.base / "OpenAI" / "Codex" / "bin" / folder / "codex.exe"
            target.parent.mkdir(parents=True)
            target.write_text("", encoding="utf-8")
            os.utime(target, (1_000_000 + n * 1000, 2_000_000 - n * 1000))
            self.bundles.append(target)

    def find(self, explicit=None, on_path=True):
        with mock.patch.object(cli_common.shutil, "which", return_value=str(self.path) if on_path else None):
            return cli_common.find_codex(explicit, {"LOCALAPPDATA": str(self.base)})

    def test_order_is_explicit_then_path_then_newest_app_bundle(self):
        self.assertEqual((str(self.explicit), "--codex"), self.find(str(self.explicit)))
        self.assertEqual((str(self.path), "PATH"), self.find())
        self.assertEqual((str(self.bundles[0]), "desktop app bundle"), self.find(on_path=False))

    def test_nothing_found_stops(self):
        with mock.patch.object(cli_common.shutil, "which", return_value=None), self.assertRaises(cli_common.Stop):
            cli_common.find_codex(None, {"LOCALAPPDATA": str(self.base / "empty")})
        with self.assertRaises(cli_common.Stop):
            self.find(str(self.base / "missing"))

    def test_macos_app_bundle_in_either_applications_folder_newest_first(self):
        cli = Path("Contents") / "Resources" / "codex-cli" / "bin" / "codex"
        every_user = touch(self.base / "Applications" / "Any Name.app" / cli, mtime=3_000_000)
        this_user = touch(self.base / "home" / "Applications" / "Other.app" / cli, mtime=4_000_000)
        touch(self.base / "Applications" / "Unrelated.app" / "Contents" / "MacOS" / "codex", mtime=5_000_000)
        self.assertEqual([this_user, every_user, *self.bundles],
                         cli_common._bundle_candidates({"LOCALAPPDATA": str(self.base)}, cli_common.CODEX_BUNDLE_GLOBS))
        with mock.patch.object(cli_common.shutil, "which", return_value=None):
            self.assertEqual((str(this_user), "desktop app bundle"), cli_common.find_codex(None, {}))


if __name__ == "__main__":
    unittest.main()
