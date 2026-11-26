# -*- coding: utf-8 -*-
"""Text at the boundary — names that come from the file system, and the Hangul character class.

The rule (repository `CLAUDE.md`): file and folder names are compared, stored and used as keys in NFC; a file found on
disk is opened by the spelling the listing returned; a name the tool creates is written in NFC.
macOS (APFS, and Drive mirrors) may return names in NFD and opens either spelling. Linux file systems and NTFS keep
the code points as they were given, so a file stored in NFD does not open by its NFC name there.

The canonical copy is `shared/textio.py` in the plugin repository. `scripts/sync_shared.py` copies it byte for byte
into each install unit that cannot import from another, and `release.py check` stops when a copy differs — edit the
canonical copy and run the script, never edit a copy. It uses the standard library only and imports nothing from
the unit it is copied into.
"""
import glob as _glob
import os
import unicodedata

# Hangul syllables, conjoining jamo and compatibility jamo, for use inside a regex character class.
# The jamo ranges keep NFD text from falling out of a class; apply nfc() first anyway, so that keys compare equal.
HANGUL = '가-힣ᄀ-ᇿ㄰-㆏'


def nfc(s):
    """NFC form of a string; anything that is not a string is returned as it is."""
    return unicodedata.normalize('NFC', s) if isinstance(s, str) else s


def listdir(folder):
    """Entries of a folder as (key, name) pairs sorted by key — key is the NFC form to compare and store,
    name is the spelling on disk to join into a path and open."""
    return sorted((nfc(n), n) for n in os.listdir(folder))


def walk(root, suffix=''):
    """Files under root as (rel, path) pairs sorted by rel — rel is the NFC key relative to root, separated by '/';
    path is the real path to open. With suffix (compared case-insensitively, e.g. '.pdf') only those files."""
    out = []
    low = suffix.lower()
    for dp, _dns, fns in os.walk(root):
        for fn in fns:
            if low and not fn.lower().endswith(low):
                continue
            path = os.path.join(dp, fn)
            out.append((nfc(os.path.relpath(path, root).replace(os.sep, '/')), path))
    return sorted(out)


def resolve(root, rel):
    """Real path of rel, a key relative to root ('/' or '\\' separated). Each part is used as it is when it exists;
    otherwise the folder entry equal to it in NFC is used, so a key stored on one computer opens the file on another
    whatever the normalization of the name on disk. A part that is not found is kept as given."""
    path = root
    for part in rel.replace('\\', '/').split('/'):
        if not part:
            continue
        cand = os.path.join(path, part)
        if not os.path.lexists(cand) and os.path.isdir(path):
            want = nfc(part)
            for name in os.listdir(path):
                if nfc(name) == want:
                    cand = os.path.join(path, name)
                    break
        path = cand
    return path


def glob(pattern):
    """Paths matching a glob pattern whose literal parts may be stored on disk in either normalization, sorted by
    their NFC form. Each path is returned in its spelling on disk."""
    found = {}
    for form in ('NFC', 'NFD'):
        for p in _glob.glob(unicodedata.normalize(form, pattern)):
            found.setdefault(nfc(p), p)
    return [found[k] for k in sorted(found)]
