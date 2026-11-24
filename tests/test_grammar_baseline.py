"""grammar_baseline.py — checks scenarios and edge cases with synthetic fixtures (dissertation kind with LF · journal kind with CRLF).

Fixtures are built in the OS temp folder and no research files are touched. The scenarios themselves are in grammar_scenarios.py (shared with the test on a copy of a real project).

    python -X utf8 -B -m unittest discover -s tests -p "test_grammar*.py"
"""

from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grammar_scenarios as S  # noqa: E402

STATE = Path(tempfile.mkdtemp(prefix='grammar-sync-state-'))
os.environ.setdefault('SYNC_STATE_HOME', str(STATE))
atexit.register(shutil.rmtree, STATE, True)

BUILD_PY = """# -*- coding: utf-8 -*-
import os

TITLE = ('A Sample Title for the Baseline Tool and Its '
         'Behavior on Different Inputs')   # title note
AUTHOR = 'Sample Author'


def helper():
    return 1


TABLES = {
    'T1_1': lambda: data_table(
        [['Item', 'Value']],
        [['Reflow', 'Reflowed on a hot plate for one minute'],
         ['Aging', 'Not applied']],
        [1000, 2000]),
}

# ------------------------------------------------------------------- collectors
toc = []


def build():
    tail = []
    # ---- Appendix / extra
    tail.append(para('Appendix'))
    tail.append(para('The complete set is collected here so that the main text stays short.'))
    # ---- References
    tail.append(para('References'))
    return tail
"""
BUILD_REGION_UNITS = 2 + 7 + 3           # TITLE 2 lines · TABLES 7 lines · Appendix 3 lines

CH1 = """@H1 Chapter 1. Introduction

@H2 1.1 Background

The first paragraph explains the motivation of the sample study in several plain words.

The second paragraph describes the samples that were weighed to the target ratios before melting.

@NOTE [confirmed — E1] a test note.

@FIG f1.png | Figure 1-1. Optical image of the sample surface after the polishing step.

The third paragraph continues the discussion with another simple sentence for testing.
"""
CH2 = """@H1 Chapter 2. Methods

The methods paragraph lists the instruments that were used for every measurement here.

@NOTE a second test note.

The closing paragraph of the methods chapter summarizes the procedure in one sentence.
"""
ABSTRACT = """@H1 Abstract

@NOTE [awaiting confirmation] an abstract note.

The abstract paragraph states the purpose of the sample study and its main findings briefly.

The second abstract paragraph reports the measured values and the conclusion of the sample work.
"""
FIGLIST = """{
 "_note": "short titles for the list of figures — a description for the test",
 "f1.png": "Optical image of the sample surface after polishing.",
 "T1_1": "Conditions of the sample preparation steps used here."
}
"""
AVOID = """# Avoid list — test

| Expression | Papers | Why | Instead | Record |
|---|---|---|---|---|
| `Weighed to` (to match the composition) | 0 | grammar error | `weighed according to` | test |
| `increase of the time` (`of` before a quantity that grows) | 0 | grammar error | `increase in` | test |
"""
J_INTRO = """@H1 Introduction

Solder joints in the sample package are introduced with a short and plain sentence here.

The second introduction paragraph motivates the comparison between the two surface finishes.

@NOTE a journal note.
"""
J_RESULTS = """@H1 Results and discussion

@H2 3.1 Microstructure

The microstructure paragraph describes the phases that formed after reflow in the joints.

@TAB T1 | Table 1. Composition of the phases measured at the interface of the joints.

The results paragraph compares the thickness of the layer after each aging time in turn.
"""
J_ABSTRACT = """@TITLE A sample journal title for the baseline tool test

The journal abstract summarizes the sample study in a single short paragraph for testing.
"""


def write(path: Path, text: str, crlf=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace('\n', '\r\n' if crlf else '\n').encode('utf-8'))


def make_thesis(root: Path) -> Path:
    p = root / 'thesis'
    cfg = {
        'project': 'Dissertation sample', 'kind': 'dissertation',
        'manuscript': {'source_dir': 'manuscript_src', 'chapters': [{'n': 1, 'file': 'ch1.md'}, {'n': 2, 'file': 'ch2.md'}],
                       'references': 'references.md', 'build_script': 'build_tpl.py'},
        'grammar': {
            'sources': [
                {'file': 'manuscript_src/abstract.md'},
                {'file': 'manuscript_src/build_tpl.py', 'kind': 'lines', 'regions': [
                    {'start': '^TITLE = ', 'end': '^AUTHOR = '},
                    {'start': '^TABLES = \\{', 'end': '^# -+ collectors'},
                    {'start': '^\\s*# ---- Appendix', 'end': '^\\s*# ---- References'}]},
                {'file': 'manuscript_src/그림목차.json', 'kind': 'json-values'}],     # a Korean file name on purpose — the NFD scenario needs one
            'avoid_lists': ['../avoid_phrases/field.md']},
    }
    write(p / '.manuscript' / 'project.json', json.dumps(cfg, ensure_ascii=False, indent=2) + '\n')
    write(p / 'manuscript_src' / 'ch1.md', CH1)
    write(p / 'manuscript_src' / 'ch2.md', CH2)
    write(p / 'manuscript_src' / 'abstract.md', ABSTRACT)
    write(p / 'manuscript_src' / 'references.md', '[1] A. Author, Sample Journal 1 (2020) 1.\n')
    write(p / 'manuscript_src' / 'build_tpl.py', BUILD_PY)
    write(p / 'manuscript_src' / '그림목차.json', FIGLIST)
    write(root / 'avoid_phrases' / 'field.md', AVOID)
    return p


def make_journal(root: Path) -> Path:
    p = root / 'journal'
    cfg = {'project': 'Journal sample', 'kind': 'journal',
           'manuscript': {'source_dir': 'manuscript', 'chapters': [{'n': 0, 'file': 'abstract.md'}, {'n': 1, 'file': 'intro.md'},
                                                                   {'n': 2, 'file': 'results.md'}],
                          'references': 'references.md'}}
    write(p / '.manuscript' / 'project.json', json.dumps(cfg, ensure_ascii=False, indent=2) + '\n')
    write(p / 'manuscript' / 'abstract.md', J_ABSTRACT, crlf=True)
    write(p / 'manuscript' / 'intro.md', J_INTRO, crlf=True)
    write(p / 'manuscript' / 'results.md', J_RESULTS, crlf=True)
    write(p / 'manuscript' / 'references.md', '[1] B. Author, Sample 2 (2021) 2.\n', crlf=True)
    return p


MAKERS = {'thesis': make_thesis, 'journal': make_journal}


class Base(unittest.TestCase):
    def fresh(self, kind):
        tmp = Path(tempfile.mkdtemp(prefix='grammar-%s-' % kind))
        self.addCleanup(shutil.rmtree, tmp, True)
        return MAKERS[kind](tmp)

    def proj(self, kind, init=True):
        root = self.fresh(kind)
        p = S.Proj(root, STATE)
        p.install()
        if init:
            p.run('init', '--confirm', 'test baseline')
        return p


def _make_case(kind, name, fn, needs_work):
    def test(self):
        root = self.fresh(kind)
        S.run_scenario(fn, needs_work, root, STATE, root.parent / 'work')     # inside the temp folder of fresh() — deleted with it
    test.__name__ = 'test_%s_%s' % (kind, name)
    return test


class Scenarios(Base):
    pass


for _kind in MAKERS:
    for _name, _fn, _w in S.SCENARIOS:
        setattr(Scenarios, 'test_%s_%s' % (_kind, _name), _make_case(_kind, _name, _fn, _w))


class ReadOnly(Base):
    def test_readonly_both(self):
        for kind in MAKERS:
            root = self.fresh(kind)
            outside = Path(tempfile.mkdtemp(prefix='grammar-outside-'))
            self.addCleanup(shutil.rmtree, outside, True)
            S.s_readonly(root, STATE, outside)


class Edges(Base):
    def test_region_bounds(self):
        p = self.proj('thesis')
        out = p.run('status').stdout
        row = [l for l in out.splitlines() if 'manuscript_src/build_tpl.py' in l][0]
        self.assertEqual(int(row.split()[2]), BUILD_REGION_UNITS, out)
        # AUTHOR (the end-marker line) and the function body are outside the region
        p.replace_once('manuscript_src/build_tpl.py', "AUTHOR = 'Sample Author'", "AUTHOR = 'Other Author'")
        p.replace_once('manuscript_src/build_tpl.py', '    return 1\n', '    return 2\n')
        p.run('changed')
        p.replace_once('manuscript_src/build_tpl.py', "'Behavior on Different Inputs')", "'Behaviour on Different Inputs')")
        r = p.run('changed', codes=(1,))
        self.assertEqual(len(p.listed(r.stdout)), 1)
        self.assertIn('manuscript_src/build_tpl.py L5', r.stdout)

    def test_json_units(self):
        p = self.proj('thesis')
        out = p.run('status').stdout
        row = [l for l in out.splitlines() if '그림목차.json' in l][0]
        self.assertEqual(int(row.split()[2]), 2, out)       # `_note` is a comment field, so it is left out

    def test_json_comment_keys_nested_and_duplicate(self):
        p = self.proj('thesis', init=False)
        fig = 'manuscript_src/그림목차.json'
        write(p.root / fig, '{\n'
              ' "_note": "a description",\n'
              ' "_group": {"a": "Nested text under a comment key.", "b": ["Listed text under a comment key."]},\n'
              ' "f1.png": "Same text in two places.",\n'
              ' "f2.png": ["Same text in two places.", "Another value in a list."]\n'
              '}\n')
        p.run('init', '--confirm', 'test baseline')
        out = p.run('status').stdout
        row = [l for l in out.splitlines() if '그림목차.json' in l][0]
        self.assertEqual(int(row.split()[2]), 3, out)       # f1 and f2 — the three under `_` keys are left out; the same text twice counts at each position
        self.assertNotIn('Could not locate every string value', out)
        p.replace_once(fig, 'Nested text under a comment key.', 'Nested text changed.')
        p.replace_once(fig, 'Listed text under a comment key.', 'Listed text changed.')
        p.run('changed')                                    # under a `_` key is not a unit
        p.replace_once(fig, '"f1.png": "Same text in two places."', '"f1.png": "Same text in two places now."')
        r = p.run('changed', codes=(1,))
        self.assertEqual([w for _i, w in p.listed(r.stdout)], ['%s L4' % fig], r.stdout)     # the same text is on L5 too, but only the edited position is listed

    @unittest.skipUnless(os.name == 'nt', 'Windows drive letters')
    def test_disp_other_drive(self):
        import importlib.util
        import types
        spec = importlib.util.spec_from_file_location('grammar_tool_under_test', S.TOOL_FILES[0])
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fake = types.SimpleNamespace(root='Q:\\proj')                      # comparing drives is string work — no real drive is needed
        self.assertEqual(mod.Ctx.disp(fake, 'R:\\x\\grammar_packets'), 'R:\\x\\grammar_packets')
        self.assertEqual(mod.Ctx.disp(fake, 'Q:\\proj\\.manuscript\\grammar_packets'), '.manuscript/grammar_packets')

    def test_packet_beside_outside_baseline(self):
        p = self.proj('journal', init=False)
        outside = Path(tempfile.mkdtemp(prefix='grammar-outbase-'))
        self.addCleanup(shutil.rmtree, outside, True)
        base = outside / 'baseline.jsonl'
        p.run('--baseline', base, 'init', '--confirm', 'test baseline')
        para = J_INTRO.split('\n\n')[1]
        p.replace_once('manuscript/intro.md', para, para + ' ZZ')
        r = p.run('--baseline', base, 'changed', '--out', codes=(1,))
        made = list((outside / 'grammar_packets').glob('*.json'))
        self.assertEqual(len(made), 1, r.stdout)
        self.assertNotIn(' ', made[0].name)
        self.assertFalse((p.root / '.manuscript' / 'grammar_packets').exists())
        r = p.run('--baseline', base, 'clean', '--packet', made[0], '--all-except')
        self.assertIn('recorded 1', r.stdout)
        p.run('--baseline', base, 'changed')

    def test_default_range_excludes_references(self):
        p = self.proj('journal')
        out = p.run('status').stdout
        self.assertNotIn('references.md', out)
        self.assertEqual([l.split()[0] for l in out.splitlines() if l.strip().startswith('manuscript/')],
                         ['manuscript/abstract.md', 'manuscript/intro.md', 'manuscript/results.md'])

    def test_duplicate_paragraph(self):
        p = self.proj('thesis')
        before = p.run('status').stdout
        tot0 = int(re.search(r'total\s+(\d+)', before).group(1))
        dup = 'ZZDUP The same paragraph appears in two chapters for the duplicate test.'
        p.replace_once('manuscript_src/ch1.md', CH1.split('\n\n')[2], CH1.split('\n\n')[2] + '\n\n' + dup)
        p.replace_once('manuscript_src/ch2.md', CH2.split('\n\n')[1], CH2.split('\n\n')[1] + '\n\n' + dup)
        r = p.run('changed', codes=(1,))
        got = p.listed(r.stdout)
        self.assertEqual(len(got), 1)
        self.assertIn('manuscript_src/ch1.md L', got[0][1])
        self.assertIn(' · manuscript_src/ch2.md L', got[0][1])
        st = p.run('status', codes=(1,)).stdout
        m = re.search(r'total\s+(\d+)\s+(\d+)\s+(\d+)', st)
        self.assertEqual((int(m.group(1)), int(m.group(3))), (tot0 + 2, 2))
        self.assertEqual(int(m.group(1)), int(m.group(2)) + int(m.group(3)))

    def test_avoid_flag_case_insensitive(self):
        p = self.proj('thesis')
        para = CH1.split('\n\n')[3]
        self.assertIn('weighed to', para)
        p.replace_once('manuscript_src/ch1.md', para, para.replace('before melting', 'before the melting'))
        r = p.run('changed', codes=(1,))
        self.assertIn('! avoid list: `Weighed to`\n', r.stdout)                 # only the first code span — the `of` in the parenthetical note is not an expression
        para2 = CH1.split('\n\n')[2]
        p.replace_once('manuscript_src/ch1.md', para2, para2.replace('motivation of the', 'motivation of this'))
        r = p.run('changed', codes=(1,))
        self.assertEqual(r.stdout.count('avoid list'), 1, r.stdout)

    def test_packet_tamper_and_unknown_id(self):
        p = self.proj('thesis')
        para = CH1.split('\n\n')[2]
        p.replace_once('manuscript_src/ch1.md', para, para + ' ZZ')
        work = Path(tempfile.mkdtemp(prefix='grammar-pk-'))
        self.addCleanup(shutil.rmtree, work, True)
        pk = work / 'p.json'
        p.run('changed', '--out', pk, codes=(1,))
        r = p.run('changed', '--out', pk, codes=(2,))                        # a packet is never overwritten
        self.assertIn('already exists', r.stdout)
        before = p.baseline_bytes()
        r = p.run('clean', '--packet', pk, '--ids', 'ffffffffffff', codes=(2,))
        self.assertIn('is not in the packet', r.stdout)
        r = p.run('clean', '--packet', pk, '--ids', 'ab', codes=(2,))
        self.assertIn('is too short', r.stdout)
        data = json.loads(pk.read_text(encoding='utf-8'))
        self.assertEqual(data['format'], 'grammar-packet/2')
        data['units'][0]['text'] += ' tampered'
        pk2 = work / 'p2.json'
        pk2.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        r = p.run('clean', '--packet', pk2, '--all-except', codes=(2,))
        self.assertIn('do not match', r.stdout)
        self.assertEqual(p.baseline_bytes(), before)

    def test_legacy_baseline_name_is_kept(self):
        # when only the baseline file name of 0.12 or earlier exists, that file is used as it is and packets are kept in the old place too
        # (old-format data on purpose: the 0.12 names are Korean)
        p = self.proj('journal')
        new = p.root / '.manuscript' / 'grammar_baseline.jsonl'
        old = p.root / '.manuscript' / '문법기준.jsonl'
        new.rename(old)
        p.run('status')
        para = J_INTRO.split('\n\n')[1]
        p.replace_once('manuscript/intro.md', para, para + ' ZZ')
        p.run('changed', '--out', codes=(1,))
        self.assertTrue(list((p.root / '.manuscript' / '문법묶음').glob('*.json')))
        self.assertFalse(new.exists())

    def test_needs_baseline_and_confirm(self):
        p = self.proj('journal', init=False)
        r = p.run('changed', codes=(2,))
        self.assertIn('No baseline file', r.stdout)
        r = p.run('init', '--confirm', '   ', codes=(2,))
        self.assertIsNone(p.baseline())
        r = p.run('status', codes=(1,))
        self.assertIn('No baseline file', r.stdout)

    def test_init_zero_units_refused(self):
        p = self.proj('journal', init=False)
        raw = p.cfg()
        raw['manuscript']['chapters'] = [{'n': 1, 'file': 'zz_none.md'}]
        p.set_cfg(raw)
        r = p.run('init', '--confirm', 'x', codes=(2,))
        self.assertIn('No units found in scope', r.stdout)
        self.assertIsNone(p.baseline())

    def test_append_after_unterminated_line_and_bad_line(self):
        p = self.proj('journal')
        b = p.baseline()
        b.write_bytes(b.read_bytes().rstrip(b'\n'))                         # a baseline without a final line break
        para = J_INTRO.split('\n\n')[1]
        p.replace_once('manuscript/intro.md', para, para + ' ZZ')
        work = Path(tempfile.mkdtemp(prefix='grammar-pk-'))
        self.addCleanup(shutil.rmtree, work, True)
        pk = work / 'p.json'
        p.run('changed', '--out', pk, codes=(1,))
        p.run('clean', '--packet', pk, '--all-except')
        lines = b.read_text(encoding='utf-8').split('\n')
        self.assertTrue(all(json.loads(l) for l in lines if l))
        p.run('changed')
        with open(b, 'ab') as f:
            f.write(b'{broken\n')
        r = p.run('changed')
        self.assertIn('Could not read line', r.stdout)

    def test_baseline_is_lf_jsonl(self):
        p = self.proj('journal')
        data = p.baseline().read_bytes()
        self.assertNotIn(b'\r', data)
        recs = [json.loads(l) for l in data.decode('utf-8').splitlines()]
        self.assertTrue(all(set(r) == {'fingerprint', 'how', 'time', 'computer', 'file', 'phrase'} for r in recs))
        self.assertEqual(len({r['fingerprint'] for r in recs}), len(recs))


if __name__ == '__main__':
    unittest.main()
