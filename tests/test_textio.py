"""The shared text module (shared/textio.py) and its copies in the install units.

Fixture names are made at run time and in NFD on purpose: Linux and NTFS keep the code points as given, so these
cases reproduce on every system what a macOS Drive mirror hands to the tools (the repository itself keeps ASCII
file names). The Korean strings are fixture data.
"""
import importlib.util
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("shared_textio", ROOT / "shared" / "textio.py")
textio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(textio)
sys.path.insert(0, str(ROOT / "scripts"))
import sync_shared  # noqa: E402


def nfd(s):
    return unicodedata.normalize("NFD", s)


DIR = "한글폴더"
PDF = "가나다문헌_1.pdf"


class TextioTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="textio-")
        self.addCleanup(temp.cleanup)
        self.root = temp.name

    def make(self, *parts, body=b"x"):
        path = os.path.join(self.root, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(body)
        return path

    def test_nfc_composes_strings_and_passes_other_values(self):
        self.assertEqual(PDF, textio.nfc(nfd(PDF)))
        self.assertIsNone(textio.nfc(None))
        self.assertEqual(3, textio.nfc(3))

    def test_listdir_gives_nfc_key_and_name_on_disk(self):
        self.make(nfd(PDF))
        [(key, name)] = textio.listdir(self.root)
        self.assertEqual(PDF, key)
        self.assertTrue(os.path.isfile(os.path.join(self.root, name)))

    def test_walk_keys_are_nfc_and_paths_open(self):
        self.make(nfd(DIR), nfd(PDF))
        self.make("A.PDF")
        self.make("note.txt")
        got = textio.walk(self.root, ".pdf")
        self.assertEqual(["A.PDF", DIR + "/" + PDF], [rel for rel, _ in got])
        for _rel, path in got:
            self.assertTrue(os.path.isfile(path))

    def test_resolve_reaches_an_nfd_file_by_its_nfc_key(self):
        self.make(nfd(DIR), nfd(PDF), body=b"found")
        path = textio.resolve(self.root, DIR + "/" + PDF)
        with open(path, "rb") as f:
            self.assertEqual(b"found", f.read())
        self.assertEqual(os.path.join(self.root, "missing", "x.pdf"), textio.resolve(self.root, "missing/x.pdf"))

    def test_resolve_scans_the_folder_where_names_are_spelling_exact(self):
        # On Linux and NTFS only the stored code points exist, so resolve must list the folder and take the entry equal
        # in NFC. macOS would accept the NFC spelling at once, so a spelling-exact existence check is simulated here.
        self.make(nfd(DIR), nfd(PDF), body=b"scanned")
        real = os.path.lexists

        def exact(p):
            head, tail = os.path.split(p)
            return real(p) and (not tail or tail in os.listdir(head or "."))

        with mock.patch.object(textio.os.path, "lexists", exact):
            path = textio.resolve(self.root, DIR + "/" + PDF)
        self.assertEqual([nfd(DIR), nfd(PDF)], os.path.relpath(path, self.root).split(os.sep))
        with open(path, "rb") as f:
            self.assertEqual(b"scanned", f.read())

    def test_glob_matches_either_normalization(self):
        self.make(nfd("검색_x.bat"))
        hits = textio.glob(os.path.join(self.root, "검색_*.bat"))
        self.assertEqual(1, len(hits))
        self.assertTrue(os.path.isfile(hits[0]))

    def test_hangul_class_keeps_korean_in_either_form(self):
        cls = "[^a-z%s]" % textio.HANGUL
        self.assertEqual("abc가나다", re.sub(cls, "", textio.nfc(nfd("ABC 가나다!").lower())))
        self.assertEqual(nfd("가나다"), re.sub(cls, "", nfd("가나 다")))


class CopyTests(unittest.TestCase):
    def test_every_copy_matches_its_canonical_file(self):
        self.assertEqual([], sync_shared.synchronize(ROOT, check=True))

    def test_copies_are_where_the_units_import_them(self):
        for dst in sync_shared.copy_targets():
            self.assertTrue((ROOT / dst).is_file(), dst)


if __name__ == "__main__":
    unittest.main()
