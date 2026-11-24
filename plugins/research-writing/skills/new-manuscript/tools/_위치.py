# -*- coding: utf-8 -*-
r"""_위치.py — 「파일 · 절」 위치 문법. 완료기록의 `대상` 과 미결 · 제안의 `위치` 를 (파일, 절) 로 가릅니다.

한 정의를 세 곳이 씁니다 — 완료 색인 §1(`완료기록_색인.py`) · 목록 §3 위치 표와 포커스(`수정필요_정리.py`) ·
새 기록의 검사(`완료기록_새항목.py`). 쓰는 법의 규약은 플러그인 문서
`manuscript-workflow/references/tracker-workflow.md` 「대상 · 위치 문법」에 있습니다.

    from _위치 import Grammar
    g = Grammar(cfg)                     # cfg 는 _config.load()
    p = g.parse('`manuscript/results.md` ③ · ④b · `도판소스/INDEX.md`')
    p.files       -> OrderedDict  'manuscript/results.md': ['③', '④b'],  '도판소스/INDEX.md': []
    p.unresolved  -> 폴더를 확인하지 못해 쓴 그대로 둔 이름들 (경고 대상이 아님)
    p.orphans     -> 앞에 파일이 없어 붙이지 못한 절 표기들 (경고 대상)
    p.free_text   -> 파일도 절 표기도 없을 때 그 글 그대로(예: '전체'), 아니면 None
    p.empty       -> 빈 칸
    g.display('manuscript/results.md') -> 'results.md'    원고 폴더 안은 원고 폴더 기준 이름(결정 D5)
    g.sort_key('manuscript/results.md', '③')             색인 · 위치 표의 행 순서
    Excluder(cfg).hit(path, written)                       완료 색인 §1 의 제외 판정(해석 경로 · 쓴 이름 둘 다)

토큰 — 백틱 안 경로 · 맨 경로 · 백틱 안 「경로 + 절」 · 절 표기 · 범위 · 코드 파일 뒤 식별자 · 글롭.
절 표기(기본) — ①–⑳(뒤 a–z) · ¶n · §n.n… · Figure n / Table n(평면 · 장-번호 둘 다, 표지 정의는 `_config.py`) ·
「절 이름」 · 범위 X–Y(구분자 – ~ 만. 하이픈은 장-번호의 일부이고 양쪽이 온전한 표기일 때만 범위).
이어지는 번호 — 절 표기 뒤에 · , / and 로 이어지는 세 자리까지의 맨 번호는 앞 표기의 종류를 물려받습니다.
식별자 — 코드 파일(.py .ps1 .bat .sh .js) 뒤에 · / , 로 이어진 동안의 `[A-Za-z_][A-Za-z0-9_]*`(백틱 · () 허용).
글롭 — * { } 가 든 이름은 해석하지 않고 쓴 그대로 둡니다. 모르는 조각은 무시합니다.
맨 이름 해석 — 앞 경로의 폴더(없으면 그 상위) → 루트 → 원고 폴더 → 장 · 참고문헌 파일 이름 → 프로젝트 상위 폴더 → 쓴 그대로.
칸 안의 모든 경로가 위치입니다 — 「함께 볼 곳」 같은 말 뒤의 경로도 같습니다.
"""
import collections, fnmatch, os, re, unicodedata

from _config import FIG_TAB_WORDS, FIG_TAB_NUM_ANY

EXT = (r'(?:md|py|json|csv|pptx|png|docx|html|txt|xlsx|jpg|jpeg|ps1|pdf|tif|tiff|bat|sh|js|emd|svg|xml'
       r'|yaml|yml|toml|ini|cfg|zip|plugin)')
CODE_EXT = ('.py', '.ps1', '.bat', '.sh', '.js')
# 경로 조각 — 글롭 `{a,b}` 는 한 덩어리로, 그 밖에는 쉼표를 넣지 않습니다(목록 구분자와 섞이지 않게)
SEG = r'(?:[A-Za-z0-9가-힣_.\-*~]|\{[^}]*\})+'
BARE = (r'(?:\.\./)*(?:' + SEG + r'/)+(?:' + SEG + r')?'        # 폴더가 든 경로 · 폴더 자체
        r'|(?:\.\./)*' + SEG + r'\.' + EXT + r'(?![A-Za-z0-9가-힣_])')  # 확장자가 있는 파일 이름
LIST_CONN = ('·', ',', '/', 'and')     # 이어지는 번호 · 식별자 사슬
RANGE_CONN = ('–', '~')                # 범위 (뒤 맨 번호는 표지를 물려받음)
HYPHEN = '-'                           # 양쪽이 온전한 표기일 때만 범위


def _strip_md(s):
    return re.sub(r'\s+', ' ', re.sub(r'\*\*|`', '', s)).strip()


class Parsed(object):
    def __init__(self):
        self.files = collections.OrderedDict()   # 루트 기준 경로(또는 쓴 그대로) -> [절, ...]
        self.kinds = {}                          # 경로 -> 'ctx' 'root' 'src' 'chapter' 'parent' 'outside' 'glob' 'asis'
        self.written = {}                        # 경로 -> 처음 쓴 이름 (제외 판정이 쓴 이름에도 대조할 때)
        self.unresolved = []                     # 쓴 그대로 둔 이름
        self.orphans = []                        # 파일 없이 나온 절 표기
        self.free_text = None
        self.empty = False

    @property
    def has_file(self):
        return bool(self.files)

    def add_file(self, path, kind):
        if path not in self.files:
            self.files[path] = []
            self.kinds[path] = kind
        if kind == 'asis' and path not in self.unresolved:
            self.unresolved.append(path)

    def add_section(self, path, sec):
        if path is None:
            if sec not in self.orphans:
                self.orphans.append(sec)
            return
        if sec not in self.files[path]:
            self.files[path].append(sec)


class Grammar(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.root = cfg.root
        self.src = cfg.source_rel                       # 예: 'manuscript'  (없으면 '')
        self.chapters = [f for _, f in cfg.chapters]
        self.refs = cfg.references
        extra = [re.compile(x) for x in cfg.section_markers]
        self.extra = extra
        parts = [r'`(?P<bt>[^`]+)`',
                 r'(?P<name>「[^」]+」)',
                 r'(?P<ft>' + FIG_TAB_WORDS + r'\s*(?P<ftn>' + FIG_TAB_NUM_ANY + r'))(?![\d.])',
                 r'(?P<sec>§\s*\d+(?:\.\d+)*[a-z]?)(?![\d.])',
                 r'(?P<para>¶\s*\d+)(?!\d)',
                 r'(?P<circ>[①-⑳][a-z]?)']
        for i, x in enumerate(extra):
            parts.append(r'(?P<x%d>%s)' % (i, x.pattern))
        parts += [r'(?P<bare>' + BARE + r')',
                  r'(?P<conn>·|,|/|\band\b|–|~|-)',
                  r'(?<![\d.])(?P<num>\d{1,3}(?:-\d{1,3})?)(?![\d.])',
                  r'(?P<ident>[A-Za-z_][A-Za-z0-9_]*(?:\(\))?)',
                  r'(?P<other>\S)']
        self.token = re.compile('|'.join(parts))

    # ------------------------------------------------------------ 경로
    def _exists(self, rel):
        return os.path.exists(os.path.join(self.root, rel.rstrip('/')))

    @staticmethod
    def _clean(t):
        t = t.strip().strip('*').replace('\\', '/')
        return t[2:] if t.startswith('./') else t

    def _pathlike(self, t):
        t = self._clean(t)
        if not t or t.startswith('@') or re.fullmatch(r'\.' + EXT, t):
            return False
        if re.search(r'[①-⑳¶§「」]', t) or (' ' in t and '/' not in t):
            return False
        if '/' in t:
            return re.search(r'[A-Za-z가-힣]', t) is not None
        return re.search(r'\.' + EXT + r'$', t) is not None

    @staticmethod
    def _dir_of(p):
        return p if p.endswith('/') else (p.rsplit('/', 1)[0] + '/' if '/' in p else '')

    def resolve(self, t, ctx=''):
        """(루트 기준 경로, 종류). 추측으로 붙이지 않습니다 — 확인되지 않으면 쓴 그대로.
        실재하는 폴더는 끝에 `/` 를 붙여 `fig_src` 와 `fig_src/` 가 한 행이 되게 합니다."""
        t = self._clean(t)
        if '*' in t or '{' in t:
            return self._resolve_glob(t, ctx), 'glob'
        path, kind = self._resolve(t, ctx)
        if kind != 'asis' and not path.endswith('/') and os.path.isdir(os.path.join(self.root, path)):
            path += '/'
        return path, kind

    def _resolve_glob(self, t, ctx):
        """글롭은 내용을 해석하지 않고, 폴더만 같은 순서(앞 경로 → 루트 → 원고 폴더)로 찾아 `ch*.md` 와
        `초안_소스/ch*.md` 가 한 행이 되게 합니다. 어디에도 맞는 파일이 없으면 쓴 그대로."""
        if t.startswith('../'):
            return t
        import glob as _glob
        cands = []
        c = ctx
        while c:
            cands.append(c); c = self._dir_of(c.rstrip('/'))
        cands += ['', (self.src + '/') if self.src else '']
        for base in cands:
            if _glob.glob(os.path.join(self.root, base + t)):
                return base + t
        return t

    def _resolve(self, t, ctx):
        if t.startswith('../'):
            return t, 'outside'
        first = t.split('/')[0]
        c = ctx
        while c:
            if self._exists(c + first):
                return c + t, 'ctx'
            c = self._dir_of(c.rstrip('/'))
        if self._exists(first):
            return t, 'root'
        if self.src and self._exists(self.src + '/' + first):
            return self.src + '/' + t, 'src'
        if t in self.chapters or t == self.refs:
            return (self.src + '/' + t) if self.src else t, 'chapter'
        if os.path.exists(os.path.join(self.root, '..', first)):
            return '../' + t, 'parent'
        return t, 'asis'

    def display(self, path):
        """원고 폴더 안 파일은 원고 폴더 기준 이름, 그 밖은 루트 기준. 같은 이름이 루트에도 있으면 루트 기준."""
        if self.src and path.startswith(self.src + '/') and len(path) > len(self.src) + 1:
            rel = path[len(self.src) + 1:]
            if not self._exists(rel):
                return rel
        return path

    def classify(self, path):
        """행 순서를 위한 분류 — 장 파일 · 원고 폴더의 다른 파일 · 루트 기준 · 밖 · 쓴 그대로."""
        if self.src and path.startswith(self.src + '/'):
            rel = path[len(self.src) + 1:]
            if rel in self.chapters:
                return (0, self.chapters.index(rel))
            if rel == self.refs:
                return (0, len(self.chapters))
            return (1, 0)
        if path.startswith('../'):
            return (3, 0)
        if self._exists(path):
            return (2, 0)
        return (4, 0)

    def sort_key(self, path, sec=''):
        return self.classify(path) + (path, section_key(sec))

    # ------------------------------------------------------------ 절 표기
    @staticmethod
    def _ft(word, num):
        return ('Table ' if word.lower().startswith('tab') else 'Figure ') + num

    def _sec_of(self, m):
        """토큰이 절 표기이면 (문자열, 종류) 를, 아니면 None 을 돌려줍니다."""
        k = m.lastgroup
        if k == 'ft':
            return self._ft(m.group('ft'), m.group('ftn')), 'Figure' if not m.group('ft').lower().startswith('tab') else 'Table'
        if k == 'sec':
            return '§' + m.group('sec')[1:].strip(), '§'
        if k == 'para':
            return '¶' + m.group('para')[1:].strip(), '¶'
        if k == 'circ':
            return m.group('circ'), '①'
        if k == 'name':
            return m.group('name'), '「'
        if k.startswith('x'):
            return m.group(k), 'extra'
        return None

    @staticmethod
    def _inherit(kind, num):
        return {'Figure': 'Figure ' + num, 'Table': 'Table ' + num, '§': '§' + num, '¶': '¶' + num}.get(kind)

    # ------------------------------------------------------------ 본체
    def parse(self, text):
        p = Parsed()
        text = text or ''
        st = {'cur': None, 'ctx': '', 'prev': None,      # prev: 'file' 'ident' 'conn' 'sec' 'other'
              'last_kind': None, 'last_sec': None, 'pending_range': None, 'range_hyphen': False,
              'pending_list': False}
        self._scan(text, p, st)
        if not p.files and not p.orphans and not st.get('had_sec'):
            t = _strip_md(text).strip(' —-')
            if not t:
                p.empty = True
            else:
                p.free_text = t if len(t) <= 40 else t[:38] + '…'
        return p

    def _put_sec(self, p, st, sec, kind, short=None):
        """절을 현재 파일에 붙입니다. 범위가 걸려 있으면 앞 절과 합칩니다 — 물려받은 번호는 번호만(`Figure 3–10`)."""
        st['had_sec'] = True
        if st['pending_range'] is not None and (not st['range_hyphen'] or kind == st['last_kind']):
            base = st['pending_range']
            if p.files and st['cur'] is not None and base in p.files[st['cur']]:
                p.files[st['cur']].remove(base)
            elif base in p.orphans:
                p.orphans.remove(base)
            sec = base + '–' + (short or sec)
        st['pending_range'] = None
        st['range_hyphen'] = False
        p.add_section(st['cur'], sec)
        st['last_kind'], st['last_sec'], st['prev'] = kind, sec, 'sec'

    def _scan(self, text, p, st):
        for m in self.token.finditer(text):
            k = m.lastgroup
            if k == 'bt':
                c = m.group('bt').strip()
                if c.startswith('@'):
                    st['prev'] = 'other'
                    continue
                head, _, rest = c.partition(' ')
                if self._pathlike(head):
                    self._file(p, st, head)
                    if rest.strip():
                        self._scan(rest, p, st)
                    continue
                if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\(\))?', c):
                    self._ident(p, st, c)
                    continue
                self._scan(c, p, st)          # 백틱 안의 절 표기 등
                continue
            sec = self._sec_of(m)
            if sec is not None:
                self._put_sec(p, st, sec[0], sec[1])
                continue
            if k == 'bare':
                self._file(p, st, m.group('bare'))
                continue
            if k == 'conn':
                c = m.group('conn')
                if c in RANGE_CONN or c == HYPHEN:
                    if st['prev'] == 'sec' and st['last_sec'] is not None:
                        st['pending_range'] = st['last_sec']
                        st['range_hyphen'] = (c == HYPHEN)
                    st['prev'] = 'conn'
                elif c in LIST_CONN:
                    st['prev'] = 'conn'
                continue
            if k == 'num':
                n = m.group('num')
                if st['pending_range'] is not None and not st['range_hyphen'] and st['last_kind'] in ('Figure', 'Table', '§', '¶'):
                    self._put_sec(p, st, self._inherit(st['last_kind'], n), st['last_kind'], short=n)
                elif st['prev'] == 'conn' and st['last_kind'] in ('Figure', 'Table', '§', '¶') and st['pending_range'] is None:
                    self._put_sec(p, st, self._inherit(st['last_kind'], n), st['last_kind'])
                else:
                    st['prev'] = 'other'; st['pending_range'] = None; st['last_kind'] = None
                continue
            if k == 'ident':
                self._ident(p, st, m.group('ident'))
                continue
            # other — 사슬을 끊습니다. 파일(cur)은 그대로 둡니다.
            st['prev'] = 'other'; st['pending_range'] = None; st['last_kind'] = None

    def _file(self, p, st, raw):
        path, kind = self.resolve(raw, st['ctx'])
        p.add_file(path, kind)
        p.written.setdefault(path, self._clean(raw))
        # 밖(`../`)의 경로는 뒤에 오는 맨 이름의 기준이 되지 않습니다 — `../CLAUDE.md · CLAUDE.md` 의 둘째는 루트의 파일입니다(A57 후속).
        if kind not in ('asis', 'glob', 'outside', 'parent'):
            st['ctx'] = self._dir_of(path) or st['ctx']
        st['cur'] = path
        st['prev'] = 'file'; st['last_kind'] = None; st['pending_range'] = None; st['last_sec'] = None

    def _ident(self, p, st, name):
        cur = st['cur']
        if cur is not None and cur.lower().endswith(CODE_EXT) and st['prev'] in ('file', 'ident', 'conn') \
                and st['last_kind'] is None:
            p.add_section(cur, name[:-2] if name.endswith('()') else name)
            st['prev'] = 'ident'
        else:
            st['prev'] = 'other'; st['pending_range'] = None; st['last_kind'] = None


# ---------------------------------------------------------------- 절 정렬
def section_key(s):
    """절 없음 → ①–⑳ → ¶ → § → Figure → Table → 「」 → 추가 표기 → 식별자(글자순). 범위는 시작 값으로."""
    if not s:
        return (0,)
    a = s.split('–')[0].strip()
    m = re.fullmatch(r'([①-⑳])([a-z]?)', a)
    if m:
        return (1, ord(m.group(1)), m.group(2), s)
    if a.startswith('¶'):
        return (2, int(re.sub(r'\D', '', a) or 0), s)
    if a.startswith('§'):
        return (3, tuple(int(x) for x in re.findall(r'\d+', a)), s)
    m = re.fullmatch(r'(Figure|Table) (\d+)(?:-(\d+))?', a)
    if m:
        return (4 if m.group(1) == 'Figure' else 5, int(m.group(3) is not None and m.group(2) or 0),
                int(m.group(3) or m.group(2)), s)
    if a.startswith('「'):
        return (6, s)
    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', a):
        return (8, s)
    return (7, s)


# ---------------------------------------------------------------- 완료 색인의 제외
class Excluder(object):
    """완료 색인 §1 에서 뺄 파일 — 설정이 가리키는 추적 파일(플러그인 개념) + `record_index_exclude` + `output_pattern`.
    해석된 루트 기준 경로와 쓴 그대로의 이름 둘 다에 대조합니다(지운 빌드 docx 처럼 실재하지 않는 이름도 걸리게)."""

    def __init__(self, cfg):
        t = cfg.raw['tracker']
        self.files = {t[k].replace('\\', '/') for k in ('index', 'pending', 'record_index', 'archive') if t.get(k)}
        self.files.add('수정필요_완료기록.md')                      # 항목당 파일로 나누기 전의 옛 통합 파일
        self.dirs = [t.get('records_dir', '완료기록').replace('\\', '/').rstrip('/') + '/']
        self.globs = list(cfg.record_index_exclude) + ([cfg.output_pattern] if cfg.output_pattern else [])

    def _one(self, p):
        p = p.replace('\\', '/')
        if p in self.files or any(p == d.rstrip('/') or p.startswith(d) for d in self.dirs):
            return True
        for g in self.globs:
            g = g.replace('\\', '/')
            if g.endswith('/'):
                if p == g.rstrip('/') or p.startswith(g):
                    return True
            elif fnmatch.fnmatchcase(p, g) or fnmatch.fnmatchcase(os.path.basename(p), g):
                return True
        return False

    def hit(self, path, written=None):
        return self._one(path) or (written is not None and self._one(written))
