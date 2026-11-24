# -*- coding: utf-8 -*-
r"""Full number check — Figure · Table · references

Run once after finishing the text edits of each chapter. It **only diagnoses**; it changes nothing.

Usage  (`<py>` is this computer's Python 3 — `python` on Windows, `python3` on macOS)
    <py> tools/check_numbers.py                 # checks against the manuscript folder in the settings (manuscript.source_dir) (default)
    <py> tools/check_numbers.py <manuscript folder path>

On a sync mirror that the shell cannot reach,
stage `ch1~4.md`, `references.md`, `build_tpl.py` and this file, and run it on the copies.

Checks
  1. Caption numbers run from 1 without gaps in each chapter
  2. The order of first citation in the text matches the caption order (if not, swap the numbers or reorder the sentences)
  3. Figures and tables with a caption but no citation in the text, and citations of numbers that have no caption
  4. Cross-references between chapters and references inside build_tpl.py (Appendix, table of contents)
  5. Reference keys: duplicates, gaps, temporary numbers (N*), citations of numbers not in the list, uncited entries
  6. Places where the order of first appearance in the text goes against the list numbers (single numbering)
  7. Preview of the output numbers the build's renumbering produces — check that gaps disappear

The numbering scheme is set by `kind` in `.manuscript/project.json`.
  kind = "journal"   flat numbers. Figure 1, Figure 2 … run through the whole manuscript.
                     The references are one list, and order of first appearance = number order is checked.
  anything else (dissertation)   chapter numbers. Every chapter starts again at Figure 3-1.

Both `Figure 1` and `Fig. 1` are accepted (including `Figs. 1 and 2`).
Whichever form the journal requires, only the manuscript text changes; this tool stays as it is.
"""
import re, sys, os, collections

def _utf8_console():
    """The default Windows console (cp949) cannot print characters such as '—' and dies mid-output.
    Switches standard output to UTF-8 so the tool runs from any shell,
    without a `PYTHONIOENCODING` prefix."""
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


_utf8_console()


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import load as _load_cfg, FIG_TAB_WORDS, FIG_TAB_NUM_FLAT, FIG_TAB_NUM_CHAPTER  # noqa: E402

_CFG = _load_cfg()
HERE = sys.argv[1] if len(sys.argv) > 1 else _CFG.source_dir
FILES = _CFG.chapters                           # set by .manuscript/project.json
REFS_FILE = _CFG.references
BUILD_SCRIPT = _CFG.build_script
SHOW_NOTES = False                     # keep equal to the build_tpl.py default
CITE_PAT = re.compile(r'\[(N?\d+)(?:\s[^\]]*)?\]')

# Journal manuscripts — the numbering scheme is set by `kind` in the settings (see the module docstring).
JOURNAL = (_CFG.kind == 'journal')
_NUM = FIG_TAB_NUM_FLAT if JOURNAL else FIG_TAB_NUM_CHAPTER   # flat number / chapter number — the labels are defined in _config.py only
_HEAD = FIG_TAB_WORDS                                        # Figure 1 · Fig. 1 · Figs. 1 · Table 1
CAP_PAT = re.compile(r'@(FIG|TAB)\s+(\S+)\s*\|\s*' + _HEAD + r'\s+(%s)\.' % _NUM)
XREF_PAT = re.compile(r'(' + _HEAD + r')\s+(%s)(?:\s+and\s+(%s))?' % (_NUM, _NUM))
problems = []


def path(f):
    return os.path.join(HERE, f)


def blocks(f):
    src = open(path(f), encoding='utf8').read()
    for b in re.split(r'\n\s*\n', src):
        yield re.sub(r'\s*\n\s*', ' ', b.strip())


def printable(b):
    return not (b.startswith('@REF ') or (b.startswith('@NOTE ') and not SHOW_NOTES))


def xrefs(b):
    """Figure and table references of one block, in order of appearance. Includes the form `Figures 3-5 and 3-6`."""
    out = []
    for m in XREF_PAT.finditer(b):
        kind = 'FIG' if m.group(1).startswith('Fig') else 'TAB'
        out.append((kind, m.group(2)))
        if m.group(3):
            out.append((kind, m.group(3)))
    return out


print('=' * 72)
print('1. Figure · Table numbers')
print('=' * 72)
def collect(f):
    """Caption declarations and text references of one file, in order of appearance."""
    decl, refs = [], []
    for b in blocks(f):
        m = CAP_PAT.match(b)
        if m:
            decl.append((m.group(1), m.group(3), m.group(2)))
            # A caption block does not count as a citation in the text — otherwise every caption
            # would cite its own number and "uncited" could never be detected.
            continue
        if printable(b):
            refs += xrefs(b)
    return decl, refs


def check(tag, decl, refs, pre):
    """Checks the numbers of one group — the whole manuscript for a journal, one chapter for a dissertation.
    pre None means flat numbers (1, 2, …), otherwise chapter numbers (3-1, 3-2, …)."""
    for kind, label in (('FIG', 'Figure'), ('TAB', 'Table')):
        d = [n for k, n, _ in decl if k == kind]
        if not d:
            continue
        want = ([str(i) for i in range(1, len(d) + 1)] if pre is None
                else [f'{pre}-{i}' for i in range(1, len(d) + 1)])
        ok = d == want
        print(f'  {tag} {label:6s} captions {len(d)}  {"OK" if ok else "numbering gap"}  {d}')
        if not ok:
            problems.append(f'{tag} {label} caption numbering gap {d}')
        first = []
        for k, n in refs:
            if k == kind and n not in first:
                first.append(n)
        inch = first if pre is None else [n for n in first if n.startswith(f'{pre}-')]
        if inch != [n for n in d if n in inch]:
            print(f'      ! first-citation order {inch}  ≠  caption order {d}')
            problems.append(f'{tag} {label} first-citation order out of step')
        miss = [n for n in d if n not in first]
        if miss:
            print(f'      ! not cited in the text {miss}')
            problems.append(f'{tag} {label} uncited {miss}')
        ghost = [n for n in inch if n not in d]
        if ghost:
            print(f'      ! cites numbers without a caption {ghost}')
            problems.append(f'{tag} {label} citation without caption {ghost}')


gathered = [(ch, f) + collect(f) for ch, f in FILES]
if JOURNAL:
    # journal manuscript — one numbering through the whole manuscript.
    check('whole manuscript',
          [d for _, _, dd, _ in gathered for d in dd],
          [r for _, _, _, rr in gathered for r in rr], None)
    empty = [f for _, f, dd, _ in gathered if not dd]
    if empty:
        print(f'  (files with no caption declarations yet — {", ".join(empty)})')
else:
    for ch, f, dd, rr in gathered:
        check(f'ch{ch}', dd, rr, ch)

print()
print('=' * 72)
print('2. Cross-references between chapters and references in build_tpl.py')
print('=' * 72)
declared = set()
for ch, f in FILES:
    for b in blocks(f):
        m = CAP_PAT.match(b)
        if m:
            declared.add((m.group(1), m.group(3)))
if JOURNAL:
    # Flat numbers have no "other chapter" references — part 1 already checked the whole manuscript at once.
    print('  (journal manuscript — one numbering across the whole manuscript, so the cross-chapter check is skipped)')
else:
    for ch, f in FILES:
        cross = []
        for b in blocks(f):
            if not printable(b):
                continue
            for kind, n in xrefs(b):
                if not n.startswith(f'{ch}-') and (kind, n) not in cross:
                    cross.append((kind, n))
        for kind, n in cross:
            mark = '' if (kind, n) in declared else '   ← no such caption'
            print(f'  ch{ch} → {kind} {n}{mark}')
            if mark:
                problems.append(f'ch{ch} cross-chapter reference {kind} {n} has no caption')
# A project may or may not have a build script (journal manuscripts usually do not).
_bt_path = path(BUILD_SCRIPT)
if os.path.isfile(_bt_path):
    bt = open(_bt_path, encoding='utf8').read()
    for m in re.finditer(_HEAD + r"\s+(%s)" % _NUM, bt):
        kind = 'FIG' if m.group(0).startswith('Fig') else 'TAB'
        ln = bt[:m.start()].count('\n') + 1
        mark = '' if (kind, m.group(1)) in declared else '   ← no such caption'
        print(f'  {BUILD_SCRIPT}:{ln} → {m.group(0)}{mark}')
        if mark:
            problems.append(f'{BUILD_SCRIPT}:{ln} reference {m.group(0)} has no caption')
else:
    print(f'  (no {BUILD_SCRIPT} — the check of references inside the build script is skipped)')

print()
print('=' * 72)
print('3. References')
print('=' * 72)
refs = []
for b in blocks(REFS_FILE):
    m = re.match(r'@REF\s+(N?\d+)\.\s*(.+)$', b)
    if m:
        refs.append((m.group(1), m.group(2)))
keys = [k for k, _ in refs]
print(f'  {len(refs)} @REF entries')
dup = [k for k, c in collections.Counter(keys).items() if c > 1]
if dup:
    print(f'  ! duplicate keys {dup}')
    problems.append(f'references: duplicate keys {dup}')
nums = sorted(int(k) for k in keys if k.isdigit())
gaps = [n for n in range(nums[0], nums[-1] + 1) if n not in nums] if nums else []
if gaps:
    print(f'  ! missing numbers {gaps}')
    problems.append(f'references: missing numbers {gaps}')
temp = [k for k in keys if not k.isdigit()]
if temp:
    print(f'  ! temporary numbers {temp}')
    problems.append(f'references: temporary numbers {temp}')

ref_keys = set(keys)
order, seen, where = [], set(), {}
for ch, f in FILES:
    for b in blocks(f):
        if not printable(b):
            continue
        for m in CITE_PAT.finditer(b):
            k = m.group(1)
            where.setdefault(k, set()).add(ch)
            if k in ref_keys and k not in seen:
                seen.add(k)
                order.append((k, ch))
unknown = sorted(set(where) - ref_keys)
if unknown:
    print(f'  ! cites numbers not in the list {unknown}')
    problems.append(f'citations not in the list {unknown}')
unused = [k for k in keys if k not in seen]
if unused:
    print(f'  ! uncited entries: {len(unused)} — {unused}')
    problems.append(f'uncited references {unused}')
print(f'  {len(order)} cited in the text / {len(keys)} in the list')

# A journal manuscript has a single list. Elsevier numeric styles number by **order of first appearance**,
# so the numbers in the source md must follow that order. The per-chapter list check is skipped.
if JOURNAL:
    seq = [k for k, _ in order if k.isdigit()]
    want_seq = [str(i) for i in range(1, len(seq) + 1)]
    if not seq:
        print('  (no references cited by a final number yet)')
    elif seq == want_seq:
        print(f'  order of first appearance = list order  OK (1–{len(seq)})')
    else:
        off = next((i for i, (a, b2) in enumerate(zip(seq, want_seq)) if a != b2), 0)
        print(f'  ! order of first appearance goes against the numbers — from position {off + 1}. Actual {seq[:15]}')
        problems.append('references: order of first appearance out of step')

# A dissertation has per-chapter reference lists. Output numbers restart at 1 in every chapter, so a source md number
# that appears out of order has no effect on the output and is not checked.
# For a single list, the build uses REFS=single.
if not JOURNAL:
    per_ch = {}
    for ch, f in FILES:
        seen_ch = set()
        for b in blocks(f):
            if not printable(b):
                continue
            for m in CITE_PAT.finditer(b):
                k = m.group(1)
                if k in ref_keys and k not in seen_ch:
                    seen_ch.add(k)
                    per_ch.setdefault(ch, []).append(k)
    print('  build (REFS=perchapter) output — '
          + ' / '.join(f'Ch.{ch} 1–{len(v)}' for ch, v in sorted(per_ch.items())))
    both = sorted({k for a, va in per_ch.items() for b2, vb in per_ch.items()
                   if a < b2 for k in set(va) & set(vb)}, key=lambda x: (len(x), x))
    if both:
        print(f'  references cited in two or more chapters, numbered differently in each: {len(both)} — '
              + ', '.join(both) + ' (normal with per-chapter lists)')

print()
print('=' * 72)
if problems:
    print(f'Summary — {len(problems)} item(s) to check')
    for p in problems:
        print('  ·', p)
else:
    print('Summary — all fine. No numbering problems.')
print('=' * 72)
