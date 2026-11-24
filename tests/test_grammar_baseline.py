"""grammar_baseline.py — 합성 표본(학위논문형 LF · 저널형 CRLF)으로 시나리오와 경계 사례를 확인합니다.

표본은 OS 임시 폴더에 만들고 연구 파일은 건드리지 않습니다. 시나리오 본체는 grammar_scenarios.py(실제 사본 시험과 공용)입니다.

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
BUILD_REGION_UNITS = 2 + 7 + 3           # TITLE 2줄 · TABLES 7줄 · Appendix 3줄

CH1 = """@H1 Chapter 1. Introduction

@H2 1.1 Background

The first paragraph explains the motivation of the sample study in several plain words.

The second paragraph describes the samples that were weighed to the target ratios before melting.

@NOTE [확정 — E1] 시험 메모입니다.

@FIG f1.png | Figure 1-1. Optical image of the sample surface after the polishing step.

The third paragraph continues the discussion with another simple sentence for testing.
"""
CH2 = """@H1 Chapter 2. Methods

The methods paragraph lists the instruments that were used for every measurement here.

@NOTE 시험 메모 둘.

The closing paragraph of the methods chapter summarizes the procedure in one sentence.
"""
ABSTRACT = """@H1 Abstract

@NOTE [확정 대기] 초록 메모.

The abstract paragraph states the purpose of the sample study and its main findings briefly.

The second abstract paragraph reports the measured values and the conclusion of the sample work.
"""
FIGLIST = """{
 "_설명": "목차에 싣는 짧은 제목 — 시험용 설명 문구입니다",
 "f1.png": "Optical image of the sample surface after polishing.",
 "T1_1": "Conditions of the sample preparation steps used here."
}
"""
AVOID = """# 피할 표현 — 시험

| 표현 | 편 수 | 왜 | 대신 | 기록 |
|---|---|---|---|---|
| `Weighed to` (조성에 맞춰) | 0 | 문법 오류 | `weighed according to` | 시험 |
| `increase of the time` (늘어나는 양 앞의 `of`) | 0 | 문법 오류 | `increase in` | 시험 |
"""
J_INTRO = """@H1 Introduction

Solder joints in the sample package are introduced with a short and plain sentence here.

The second introduction paragraph motivates the comparison between the two surface finishes.

@NOTE 저널 메모.
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
        'project': '학위논문 표본', 'kind': 'dissertation',
        'manuscript': {'source_dir': 'manuscript_src', 'chapters': [{'n': 1, 'file': 'ch1.md'}, {'n': 2, 'file': 'ch2.md'}],
                       'references': 'references.md', 'build_script': 'build_tpl.py'},
        'grammar': {
            'sources': [
                {'file': 'manuscript_src/abstract.md'},
                {'file': 'manuscript_src/build_tpl.py', 'kind': 'lines', 'regions': [
                    {'start': '^TITLE = ', 'end': '^AUTHOR = '},
                    {'start': '^TABLES = \\{', 'end': '^# -+ collectors'},
                    {'start': '^\\s*# ---- Appendix', 'end': '^\\s*# ---- References'}]},
                {'file': 'manuscript_src/그림목차.json', 'kind': 'json-values'}],
            'avoid_lists': ['../피할_표현/분야.md']},
    }
    write(p / '.manuscript' / 'project.json', json.dumps(cfg, ensure_ascii=False, indent=2) + '\n')
    write(p / 'manuscript_src' / 'ch1.md', CH1)
    write(p / 'manuscript_src' / 'ch2.md', CH2)
    write(p / 'manuscript_src' / 'abstract.md', ABSTRACT)
    write(p / 'manuscript_src' / 'references.md', '[1] A. Author, Sample Journal 1 (2020) 1.\n')
    write(p / 'manuscript_src' / 'build_tpl.py', BUILD_PY)
    write(p / 'manuscript_src' / '그림목차.json', FIGLIST)
    write(root / '피할_표현' / '분야.md', AVOID)
    return p


def make_journal(root: Path) -> Path:
    p = root / 'journal'
    cfg = {'project': '저널 표본', 'kind': 'journal',
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
            p.run('init', '--confirm', '시험 기준')
        return p


def _make_case(kind, name, fn, needs_work):
    def test(self):
        root = self.fresh(kind)
        S.run_scenario(fn, needs_work, root, STATE, root.parent / 'work')     # fresh() 의 임시 폴더 안 — 함께 지워짐
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
        # AUTHOR(끝 표지 줄)와 함수 본문은 구간 밖
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
        self.assertEqual(int(row.split()[2]), 2, out)       # `_설명` 은 설명 칸이라 빠짐

    def test_json_comment_keys_nested_and_duplicate(self):
        p = self.proj('thesis', init=False)
        fig = 'manuscript_src/그림목차.json'
        write(p.root / fig, '{\n'
              ' "_설명": "설명 문구",\n'
              ' "_묶음": {"a": "Nested text under a comment key.", "b": ["Listed text under a comment key."]},\n'
              ' "f1.png": "Same text in two places.",\n'
              ' "f2.png": ["Same text in two places.", "Another value in a list."]\n'
              '}\n')
        p.run('init', '--confirm', '시험 기준')
        out = p.run('status').stdout
        row = [l for l in out.splitlines() if '그림목차.json' in l][0]
        self.assertEqual(int(row.split()[2]), 3, out)       # f1 · f2 둘 — `_` 키 아래 셋은 빠짐, 같은 글 둘은 자리마다
        self.assertNotIn('다 읽지 못했습니다', out)
        p.replace_once(fig, 'Nested text under a comment key.', 'Nested text changed.')
        p.replace_once(fig, 'Listed text under a comment key.', 'Listed text changed.')
        p.run('changed')                                    # `_` 키 아래는 단위가 아님
        p.replace_once(fig, '"f1.png": "Same text in two places."', '"f1.png": "Same text in two places now."')
        r = p.run('changed', codes=(1,))
        self.assertEqual([w for _i, w in p.listed(r.stdout)], ['%s L4' % fig], r.stdout)     # 같은 글이 L5 에도 있지만 고친 자리만

    @unittest.skipUnless(os.name == 'nt', 'Windows 드라이브 글자')
    def test_disp_other_drive(self):
        import importlib.util
        import types
        spec = importlib.util.spec_from_file_location('grammar_tool_under_test', S.TOOL_FILES[0])
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fake = types.SimpleNamespace(root='Q:\\proj')                      # 드라이브 비교는 글자 연산 — 실제 드라이브가 없어도 됨
        self.assertEqual(mod.Ctx.disp(fake, 'R:\\x\\문법묶음'), 'R:\\x\\문법묶음')
        self.assertEqual(mod.Ctx.disp(fake, 'Q:\\proj\\.manuscript\\문법묶음'), '.manuscript/문법묶음')

    def test_packet_beside_outside_baseline(self):
        p = self.proj('journal', init=False)
        outside = Path(tempfile.mkdtemp(prefix='grammar-outbase-'))
        self.addCleanup(shutil.rmtree, outside, True)
        base = outside / '기준.jsonl'
        p.run('--baseline', base, 'init', '--confirm', '시험 기준')
        para = J_INTRO.split('\n\n')[1]
        p.replace_once('manuscript/intro.md', para, para + ' ZZ')
        r = p.run('--baseline', base, 'changed', '--out', codes=(1,))
        made = list((outside / 'grammar_packets').glob('*.json'))
        self.assertEqual(len(made), 1, r.stdout)
        self.assertNotIn(' ', made[0].name)
        self.assertFalse((p.root / '.manuscript' / 'grammar_packets').exists())
        r = p.run('--baseline', base, 'clean', '--packet', made[0], '--all-except')
        self.assertIn('찍음 1', r.stdout)
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
        tot0 = int(re.search(r'합계\s+(\d+)', before).group(1))
        dup = 'ZZDUP The same paragraph appears in two chapters for the duplicate test.'
        p.replace_once('manuscript_src/ch1.md', CH1.split('\n\n')[2], CH1.split('\n\n')[2] + '\n\n' + dup)
        p.replace_once('manuscript_src/ch2.md', CH2.split('\n\n')[1], CH2.split('\n\n')[1] + '\n\n' + dup)
        r = p.run('changed', codes=(1,))
        got = p.listed(r.stdout)
        self.assertEqual(len(got), 1)
        self.assertIn('manuscript_src/ch1.md L', got[0][1])
        self.assertIn(' · manuscript_src/ch2.md L', got[0][1])
        st = p.run('status', codes=(1,)).stdout
        m = re.search(r'합계\s+(\d+)\s+(\d+)\s+(\d+)', st)
        self.assertEqual((int(m.group(1)), int(m.group(3))), (tot0 + 2, 2))
        self.assertEqual(int(m.group(1)), int(m.group(2)) + int(m.group(3)))

    def test_avoid_flag_case_insensitive(self):
        p = self.proj('thesis')
        para = CH1.split('\n\n')[3]
        self.assertIn('weighed to', para)
        p.replace_once('manuscript_src/ch1.md', para, para.replace('before melting', 'before the melting'))
        r = p.run('changed', codes=(1,))
        self.assertIn('! 피할 표현: `Weighed to`\n', r.stdout)                 # 첫 코드 스팬만 — 괄호 설명의 `of` 는 표현이 아님
        para2 = CH1.split('\n\n')[2]
        p.replace_once('manuscript_src/ch1.md', para2, para2.replace('motivation of the', 'motivation of this'))
        r = p.run('changed', codes=(1,))
        self.assertEqual(r.stdout.count('피할 표현'), 1, r.stdout)

    def test_packet_tamper_and_unknown_id(self):
        p = self.proj('thesis')
        para = CH1.split('\n\n')[2]
        p.replace_once('manuscript_src/ch1.md', para, para + ' ZZ')
        work = Path(tempfile.mkdtemp(prefix='grammar-pk-'))
        self.addCleanup(shutil.rmtree, work, True)
        pk = work / 'p.json'
        p.run('changed', '--out', pk, codes=(1,))
        r = p.run('changed', '--out', pk, codes=(2,))                        # 묶음은 덮어쓰지 않음
        self.assertIn('이미 있습니다', r.stdout)
        before = p.baseline_bytes()
        r = p.run('clean', '--packet', pk, '--ids', 'ffffffffffff', codes=(2,))
        self.assertIn('없습니다', r.stdout)
        r = p.run('clean', '--packet', pk, '--ids', 'ab', codes=(2,))
        self.assertIn('너무 짧습니다', r.stdout)
        data = json.loads(pk.read_text(encoding='utf-8'))
        data['단위'][0]['글'] += ' tampered'
        pk2 = work / 'p2.json'
        pk2.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        r = p.run('clean', '--packet', pk2, '--all-except', codes=(2,))
        self.assertIn('맞지 않습니다', r.stdout)
        self.assertEqual(p.baseline_bytes(), before)

    def test_legacy_baseline_name_is_kept(self):
        # 0.12 이하의 기준 파일 이름만 있으면 그 파일을 그대로 쓰고, 묶음도 옛 자리에 둡니다
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
        self.assertIn('기준 파일이 없습니다', r.stdout)
        r = p.run('init', '--confirm', '   ', codes=(2,))
        self.assertIsNone(p.baseline())
        r = p.run('status', codes=(1,))
        self.assertIn('기준 파일이 없습니다', r.stdout)

    def test_init_zero_units_refused(self):
        p = self.proj('journal', init=False)
        raw = p.cfg()
        raw['manuscript']['chapters'] = [{'n': 1, 'file': 'zz_none.md'}]
        p.set_cfg(raw)
        r = p.run('init', '--confirm', 'x', codes=(2,))
        self.assertIn('하나도 찾지 못했습니다', r.stdout)
        self.assertIsNone(p.baseline())

    def test_append_after_unterminated_line_and_bad_line(self):
        p = self.proj('journal')
        b = p.baseline()
        b.write_bytes(b.read_bytes().rstrip(b'\n'))                         # 마지막 줄바꿈이 없는 기준
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
        self.assertIn('읽지 못했습니다', r.stdout)

    def test_baseline_is_lf_jsonl(self):
        p = self.proj('journal')
        data = p.baseline().read_bytes()
        self.assertNotIn(b'\r', data)
        recs = [json.loads(l) for l in data.decode('utf-8').splitlines()]
        self.assertTrue(all(set(r) == {'지문', 'how', '시각', '컴퓨터', '파일', '문구'} for r in recs))
        self.assertEqual(len({r['지문'] for r in recs}), len(recs))


if __name__ == '__main__':
    unittest.main()
