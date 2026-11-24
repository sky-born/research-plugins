"""scripts/check_public.py — 일반 패턴 · 허용 값 · 금지어 · 값을 가린 보고."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_public as C  # noqa: E402


class Findings(unittest.TestCase):
    def kinds(self, text, deny=()):
        return sorted(k for k, _ in C.findings(text, list(deny)))

    def test_generic_patterns(self):
        # 시험 값은 이어 붙여 만듭니다 — 이 파일도 공개 검사 대상이라 그대로 적으면 걸립니다
        self.assertEqual(self.kinds("mail someone" + "@" + "gmail.com"), ["email"])
        self.assertEqual(self.kinds("C:" + "\\Users\\" + "alice\\Documents"), ["user folder"])
        self.assertEqual(self.kinds("/Users/" + "alice/dev"), ["home folder"])
        self.assertEqual(self.kinds("token = '" + "abcdefghijklmnop1234" + "'"), ["secret assignment"])
        self.assertEqual(self.kinds("ghp_" + "a" * 36), ["secret"])

    def test_placeholders_and_noreply_pass(self):
        for text in ("1+x@users.noreply.github.com", "noreply@anthropic.com", "a@example.com", "t@example.invalid",
                     r"%USERPROFILE%\.claude", r"C:\Users\<user>\x", "/Users/$USER/x", r"C:\Users\Public\x", "/home/runner/x"):
            self.assertEqual(self.kinds(text), [], text)

    def test_deny_terms_ignore_case_and_are_masked(self):
        found = C.findings("Written by ALICE and alice", ["Alice"])
        self.assertEqual([k for k, _ in found], ["deny list", "deny list"])
        self.assertEqual(C.mask("Alice"), "A…(5)")

    def test_deny_list_file_comments_and_empty(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "deny.txt"
            p.write_text("# comment\nAlice  # inline\n\n", encoding="utf-8")
            self.assertEqual(C.load_deny(str(p))[0], ["Alice"])
            p.write_text("# only a comment\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                C.load_deny(str(p))


if __name__ == "__main__":
    unittest.main()
