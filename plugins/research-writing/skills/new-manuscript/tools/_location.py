# -*- coding: utf-8 -*-
r"""_location.py — the "file · section" location syntax. Splits the target of completion records and the location of open items and proposals into (file, section).

Three places share this one definition — record index §1 (`index_records.py`), list §3 location table and focus (`tidy_tracker.py`),
and the check of new records (`new_record.py`). The rules for writing it are in the plugin document
`manuscript-workflow/references/tracker-workflow.md` "Target and location syntax — the location table and the reverse index are built from it".

    from _location import Grammar
    g = Grammar(cfg)                     # cfg is _config.load()
    p = g.parse('`manuscript/results.md` ③ · ④b · `fig_src/INDEX.md`')
    p.files       -> OrderedDict  'manuscript/results.md': ['③', '④b'],  'fig_src/INDEX.md': []
    p.unresolved  -> names kept as written because no folder was confirmed (not warned about)
    p.orphans     -> section markers that could not be attached because no file came before them (warned about)
    p.free_text   -> the text as written when there is neither a file nor a section marker (e.g. 'whole manuscript'), otherwise None
    p.empty       -> empty cell
    g.display('manuscript/results.md') -> 'results.md'    files inside the manuscript folder are named relative to that folder
    g.sort_key('manuscript/results.md', '③')             row order of the index and the location table
    Excluder(cfg).hit(path, written)                       exclusion test of record index §1 (both the resolved path and the written name)

Tokens — path in backticks · bare path · "path + section" in backticks · section marker · range · identifier after a code file · glob.
Section markers (default) — ①–⑳ (followed by a–z) · ¶n · §n.n… · Figure n / Table n (flat and chapter-number both; the labels are defined in `_config.py`) ·
「section name」 · range X–Y (separators – and ~ only. A hyphen is part of a chapter number and makes a range only when both sides are complete markers).
Continued numbers — after a section marker, a bare number of up to three digits joined by · , / or and inherits the kind of the marker before it.
Identifiers — after a code file (.py .ps1 .bat .sh .js), `[A-Za-z_][A-Za-z0-9_]*` for as long as they are joined by · / , (backticks and () allowed).
Globs — names containing * { } are not resolved and stay as written. Unknown fragments are ignored.
Bare name resolution — folder of the previous path (else its parent) → root → manuscript folder → chapter and reference file names → the project's parent folder → as written.
Every path in the cell is a location — including paths after words such as "see also".
"""
import collections, fnmatch, os, re, unicodedata

from _config import FIG_TAB_WORDS, FIG_TAB_NUM_ANY, LEGACY_RECORDS_FILE, HANGUL, nfc

EXT = (r'(?:md|py|json|csv|pptx|png|docx|html|txt|xlsx|jpg|jpeg|ps1|pdf|tif|tiff|bat|sh|js|emd|svg|xml'
       r'|yaml|yml|toml|ini|cfg|zip|plugin)')
CODE_EXT = ('.py', '.ps1', '.bat', '.sh', '.js')
# path segment — a glob `{a,b}` is one piece; otherwise no commas (so they do not mix with list separators)
SEG = r'(?:[A-Za-z0-9' + HANGUL + r'_.\-*~]|\{[^}]*\})+'
BARE = (r'(?:\.\./)*(?:' + SEG + r'/)+(?:' + SEG + r')?'        # path with a folder · the folder itself
        r'|(?:\.\./)*' + SEG + r'\.' + EXT + r'(?![A-Za-z0-9' + HANGUL + r'_])')  # file name with an extension
LIST_CONN = ('·', ',', '/', 'and')     # chain of continued numbers and identifiers
RANGE_CONN = ('–', '~')                # range (the bare number after it inherits the label)
HYPHEN = '-'                           # a range only when both sides are complete markers


def _strip_md(s):
    return re.sub(r'\s+', ' ', re.sub(r'\*\*|`', '', s)).strip()


class Parsed(object):
    def __init__(self):
        self.files = collections.OrderedDict()   # path relative to the root (or as written) -> [section, ...]
        self.kinds = {}                          # path -> 'ctx' 'root' 'src' 'chapter' 'parent' 'outside' 'glob' 'asis'
        self.written = {}                        # path -> name as first written (for the exclusion test on written names)
        self.unresolved = []                     # names kept as written
        self.orphans = []                        # section markers that came without a file
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
        self.src = cfg.source_rel                       # e.g. 'manuscript'  ('' if none)
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

    # ------------------------------------------------------------ paths
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
            return re.search(r'[A-Za-z' + HANGUL + r']', t) is not None
        return re.search(r'\.' + EXT + r'$', t) is not None

    @staticmethod
    def _dir_of(p):
        return p if p.endswith('/') else (p.rsplit('/', 1)[0] + '/' if '/' in p else '')

    def resolve(self, t, ctx=''):
        """(path relative to the root, kind). Never guesses — an unconfirmed name stays as written.
        An existing folder gets a trailing `/` so that `fig_src` and `fig_src/` make one row."""
        t = self._clean(t)
        if '*' in t or '{' in t:
            return self._resolve_glob(t, ctx), 'glob'
        path, kind = self._resolve(t, ctx)
        if kind != 'asis' and not path.endswith('/') and os.path.isdir(os.path.join(self.root, path)):
            path += '/'
        return path, kind

    def _resolve_glob(self, t, ctx):
        """A glob is not resolved itself; only its folder is looked up in the same order (previous path → root → manuscript folder), so that
        `ch*.md` and `manuscript_src/ch*.md` make one row. If no file matches anywhere, it stays as written."""
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
        """Files inside the manuscript folder are named relative to that folder, others relative to the root. If the same name also exists at the root, relative to the root."""
        if self.src and path.startswith(self.src + '/') and len(path) > len(self.src) + 1:
            rel = path[len(self.src) + 1:]
            if not self._exists(rel):
                return rel
        return path

    def classify(self, path):
        """Class for the row order — chapter files · other files of the manuscript folder · relative to the root · outside · as written."""
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

    # ------------------------------------------------------------ section markers
    @staticmethod
    def _ft(word, num):
        return ('Table ' if word.lower().startswith('tab') else 'Figure ') + num

    def _sec_of(self, m):
        """(string, kind) if the token is a section marker, otherwise None."""
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

    # ------------------------------------------------------------ main
    def parse(self, text):
        p = Parsed()
        text = nfc(text or '')                           # keys are NFC — a cell pasted from a macOS file name may arrive in NFD
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
        """Attaches the section to the current file. With an open range, joins it to the previous section — an inherited number adds the number only (`Figure 3–10`)."""
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
        toks = list(self.token.finditer(text))
        for i, m in enumerate(toks):
            k = m.lastgroup
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            # what may follow a list item: the end, a list connector, an opening parenthesis (a remark) or non-ASCII prose (older records)
            st['list_next'] = nxt is None or (nxt.lastgroup == 'conn' and nxt.group('conn') in LIST_CONN) \
                or (nxt.lastgroup == 'other' and (nxt.group() == '(' or not nxt.group().isascii()))
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
                if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?:\(\))?', c):   # `name`, `name()`, `Class.method`
                    self._ident(p, st, c)
                    continue
                st['in_bt'] = True            # section markers etc. inside backticks — a plain word there is part of a name, not a list item
                self._scan(c, p, st)
                st['in_bt'] = False
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
                self._ident(p, st, m.group('ident'), bare=True)
                continue
            # other — breaks the chain. The file (cur) stays.
            st['prev'] = 'other'; st['pending_range'] = None; st['last_kind'] = None

    def _file(self, p, st, raw):
        path, kind = self.resolve(raw, st['ctx'])
        p.add_file(path, kind)
        p.written.setdefault(path, self._clean(raw))
        # A path outside (`../`) is not the base for the bare names after it — the second name in `../CLAUDE.md · CLAUDE.md` is the root's file.
        if kind not in ('asis', 'glob', 'outside', 'parent'):
            st['ctx'] = self._dir_of(path) or st['ctx']
        st['cur'] = path
        st['prev'] = 'file'; st['last_kind'] = None; st['pending_range'] = None; st['last_sec'] = None

    def _ident(self, p, st, name, bare=False):
        """An identifier right after a code file is a section of it. In backticks, or when the word looks like code (`_`, a digit, `()`
        or an upper-case letter after the first), it continues the chain as before. A plain word without backticks counts only as a
        list item — right after the file or a list connector, and followed by a list connector or the end (`tail · cover`); otherwise
        it is prose and ends the chain (`tail block`, `and the caption text`)."""
        cur = st['cur']
        code_like = not bare or bool(re.search(r'[_\d]|\(\)$', name) or re.search(r'.[A-Z]', name))
        list_item = st['prev'] in ('file', 'conn') and st.get('list_next', True) and not st.get('in_bt')
        if cur is not None and cur.lower().endswith(CODE_EXT) and st['prev'] in ('file', 'ident', 'conn') \
                and st['last_kind'] is None and (code_like or list_item):
            p.add_section(cur, name[:-2] if name.endswith('()') else name)
            st['prev'] = 'ident'
        else:
            st['prev'] = 'other'; st['pending_range'] = None; st['last_kind'] = None


# ---------------------------------------------------------------- section order
def section_key(s):
    """no section → ①–⑳ → ¶ → § → Figure → Table → 「」 → extra markers → identifiers (alphabetical). A range sorts by its start."""
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


# ---------------------------------------------------------------- exclusions of the record index
class Excluder(object):
    """Files left out of record index §1 — the tracker files the settings point to (a plugin concept) + `record_index_exclude` + `output_pattern`.
    Matches both the resolved path relative to the root and the name as written (so names that no longer exist, such as a deleted build docx, match too)."""

    def __init__(self, cfg):
        t = cfg.raw['tracker']
        self.files = {t[k].replace('\\', '/') for k in ('index', 'pending', 'record_index', 'archive') if t.get(k)}
        self.files.add(LEGACY_RECORDS_FILE)                        # old single file, before records were split into one file per item
        self.dirs = [cfg.records_dir.replace('\\', '/').rstrip('/') + '/']
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
