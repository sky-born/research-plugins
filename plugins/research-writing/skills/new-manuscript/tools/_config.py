r"""Manuscript project settings loader — `.manuscript/project.json`

Reads in one place the values the tools use to adapt to a project (chapter list, tracker file names, triggers).
**Without a settings file the defaults apply.** The defaults match the tools' built-in behaviour, so the tools
also run in projects that have no settings file.

    from _config import load
    cfg = load()
    cfg.chapters          -> [(1, 'ch1.md'), ...]
    cfg.tracker_files     -> ['tracker_index.md', ...]
    cfg.triggers          -> `['now', ...]`

To use the tools in another manuscript, create `.manuscript/project.json` only. The tools stay unchanged.
The old location `.writing/project.json` is still read.
"""

import importlib.abc, importlib.util, io, json, os, re, sys, unicodedata

# nfc and the Hangul class have one definition, the text module beside this file (a copy of shared/textio.py in the plugin
# repository). Apply nfc when file names, paths and lines are compared or used as keys — a macOS mirror returns Korean names in NFD.
# The tools keep importing nfc from here.
from _textio import HANGUL, nfc  # noqa: E402,F401


class _NFCFinder(importlib.abc.MetaPathFinder):
    """Last-resort finder that lets modules with Korean names stored in NFD be imported.

    Python's FileFinder caches folder listings as raw strings, so importing a module with a Korean name does not find a file stored in NFD
    and raises ModuleNotFoundError (seen on a Google Drive mirror on macOS). Only for **Korean names** that the default finders failed on,
    this finder looks in this file's folder and the sys.path folders for a .py whose NFC name matches, and loads it by path. ASCII names are left alone.
    The managed tools have ASCII names, so this is for Korean-named modules a project keeps itself — such tools import `_config` first."""

    def find_spec(self, fullname, path=None, target=None):
        if path is not None or '.' in fullname or fullname.isascii():
            return None
        want = nfc(fullname)
        seen = set()
        for d in [os.path.dirname(os.path.abspath(__file__))] + [p for p in sys.path if isinstance(p, str) and p]:
            d = os.path.abspath(d)
            if d in seen:
                continue
            seen.add(d)
            try:
                names = os.listdir(d)
            except OSError:
                continue
            for f in names:
                stem, ext = os.path.splitext(f)
                if ext == '.py' and nfc(stem) == want:
                    return importlib.util.spec_from_file_location(fullname, os.path.join(d, f))
        return None


if not any(isinstance(f, _NFCFinder) for f in sys.meta_path):
    sys.meta_path.append(_NFCFinder())


def _utf8_console():
    """The default Windows console (cp949) cannot print characters such as '—' and dies mid-output.
    Switches standard output to UTF-8 so the tools run from any shell,
    without a `PYTHONIOENCODING` prefix."""
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass

# ================================================================ legacy spellings — the one place for Korean
# Projects made before 0.14, and projects that stay in that format, use Korean names and format tokens. The tools read them forever
# and never write them. Every Korean string of the tools lives in this section (`LEGACY_*`); each entry says in English what it is.
# The release check stops on Korean anywhere else in the code.
LEGACY_SPELLINGS = {
    'blocks': {                                    # block markers `<!-- name -->`
        'standing': '상시F',                       # standing items (F)
        'locations': '위치표',                     # location table
        'triggers': '트리거표',                    # trigger table
        'now': '지금',                             # items that can be done now
        'focus': '포커스',                         # focus (chapter in progress)
        'archive_body': '본문:이관',               # archive table body
        'archived_list': '이관목록:{}',            # list of archived items, per class letter
        'hand_locations': '{}위치',                # hand-kept location table, per class letter
    },
    'stamp': '생성스탬프',                         # generation stamp
    'columns': {
        'item': '항목', 'location': '위치', 'trigger': '트리거', 'status': '상태', 'note': '비고',   # item · location · trigger · status · note
        'proposal': '제안', 'basis': '근거',       # proposal · basis
        'file': '파일', 'section': '절', 'linked': '걸린 항목',     # file · section · items (tied to it)
        'condition': '조건이 풀리면', 'take_up': '꺼낼 항목',      # when this clears · items to take up
        'completed': '완료일',                     # date completed
    },
    'fields': {'completed': '완료일', 'target': '대상', 'status': '상태'},   # record fields: completed · target · status
    'focus': '작업 중인 장',                       # chapter in progress
    'triggers': {
        'now': '지금',                             # now
        'section': '해당 절 작업 시',              # when working on the section
        'user': '사용자 판단',                     # user decision
        'data': '자료 확보 후',                    # when data is available
        'final': '최종 제출 직전',                 # before final submission
    },
    'placeholders': {'no_location': '(위치 미기재)', 'not_given': '(미기재)', 'excluded_only': '(제외 파일만)'},  # no location · not given · excluded files only
    'states': {
        'applied_unconfirmed': '반영 (확정 대기)',  # applied (awaiting confirmation)
        'partly_confirmed': '부분 확정',           # partly confirmed
        'confirmed': '확정',                       # confirmed
        'closed': '종결',                          # closed
        'logged': '기록',                          # logged
        'on_hold': '보류',                         # on hold
        'in_progress': '진행',                     # in progress
        'applied': '반영',                         # applied
        'done': '완료',                            # done
        'waiting': '대기',                         # waiting
        'standing': '상시',                        # standing
        'refresh': '갱신',                         # refresh
    },
    'open_hints': {'needed': '필요', 'waiting': '대기'},   # needed · waiting
    'superseded': '대체됨',                        # superseded (by E<n>)
    'refs': ' · 관련 ',                            # ' · see ' (E numbers after a status head)
    'baseline_keys': {'fingerprint': '지문', 'time': '시각', 'computer': '컴퓨터', 'file': '파일', 'phrase': '문구'},
    'packet_keys': {'format': '형식', 'created': '만든 시각', 'computer': '컴퓨터', 'root': '루트', 'baseline': '기준',
                    'units': '단위', 'fingerprint': '지문', 'text': '글', 'locations': '위치', 'file': '파일', 'line': '줄',
                    'avoid': '피할'},              # the same English words as the keys
    'packet_format': '문법기준-묶음/1',            # grammar-baseline packet, version 1
}
LEGACY_NAMES = {'_콘솔_UTF8': '_utf8_console'}   # identifiers that locally modified tool copies from before 0.14.0 still import
# Default names of projects made by 0.12 or earlier. A project whose settings lack such a key and whose disk has only the old name is an old project —
# load() stops and shows the values to add to the settings (this table as is). New projects use DEFAULTS (English).
LEGACY_DEFAULTS = {
    "tools_dir": "도구",                                       # tools
    "manuscript": {"source_dir": "초안_소스"},                 # draft sources
    "tracker": {
        "index": "수정필요_목록.md",                           # tracker index
        "pending": "수정필요_대기.md",                         # pending items
        "record_index": "수정필요_색인.md",                    # record index
        "literature": "수정필요_문헌.md",                      # literature
        "proposals": "수정필요_제안.md",                       # proposals
        "records_dir": "완료기록",                             # completion records
        "archive": "완료기록/이관_DB.md",                      # archive
    },
    "sync": {
        "snapshot_dir": "보관/추적_백업",                      # archive/tracker backup
        "exclude": [".git/", "__pycache__/", "node_modules/", "보관/", ".manuscript/도구_백업/", ".manuscript/tools_backup/"],   # `보관/` archive/ · `도구_백업/` tools_backup/
    },
}
LEGACY_TOOL_NAMES = {                              # file names of the managed tools in 0.12 or earlier — update_tools.py moves them
    'tools/_location.py': '_위치.py',              # location syntax
    'tools/check_numbers.py': '번호점검.py',       # number check
    'tools/tidy_tracker.py': '수정필요_정리.py',   # tracker tidy
    'tools/index_records.py': '완료기록_색인.py',  # record index
    'tools/new_record.py': '완료기록_새항목.py',   # new record
    'tools/new_pending.py': '미결_새항목.py',      # new open item
    'tools/_sync.py': '_동기화.py',                # sync
    'tools/check_sync.py': '동기화_점검.py',       # sync check
    'tools/grammar_baseline.py': '문법기준.py',    # grammar baseline
}
LEGACY_RECORDS_FILE = '수정필요_완료기록.md'       # the single records file of the oldest projects, before one file per item
LEGACY_GRAMMAR = ('.manuscript/문법기준.jsonl', '문법묶음')   # grammar_baseline's baseline file and packet folder of 0.12 or earlier
LEGACY_FLAGS = {'--검사': '--check-targets'}       # old command-line flags, still accepted
_L = LEGACY_SPELLINGS
globals().update({old: globals()[new] for old, new in LEGACY_NAMES.items()})


CONFIG_REL = os.path.join('.manuscript', 'project.json')
CONFIG_REL_OLD = os.path.join('.writing', 'project.json')   # old name — fallback

# ---------------------------------------------------------------- shared definitions — one place per concept
# Figure and table labels. check_numbers accepts either the flat or the chapter-number form depending on kind; the location syntax (_location.py) accepts both.
FIG_TAB_WORDS = r'(?:Figs?\.|Figures?|Tables?)'
FIG_TAB_NUM_FLAT = r'\d+'
FIG_TAB_NUM_CHAPTER = r'\d+-\d+'
FIG_TAB_NUM_ANY = r'\d+(?:-\d+)?'

# ---------------------------------------------------------------- format tokens — every string the tools find in or write into project files
# Each pair is (English, older spelling). The tools write the English one; every reader accepts both forever (`tracker-workflow.md`
# "Format tokens"). The older spellings come from LEGACY_SPELLINGS above. `update_tools.py --apply` rewrites the anchors of an older
# project (`migrate_format.py`); history (records, archive rows, the grammar baseline) and values stay as written.
_BLOCK_EN = {'standing': 'standing-F', 'locations': 'location-table', 'triggers': 'trigger-table', 'now': 'now', 'focus': 'focus',
             'archive_body': 'archive-body', 'archived_list': 'archived-list:{}', 'hand_locations': '{}-locations'}
BLOCKS = dict((k, (en, _L['blocks'][k])) for k, en in _BLOCK_EN.items())   # block markers `<!-- name -->` … `<!-- /name -->` — `{}` is a class letter
STAMP_WORDS = ('generated-stamp', _L['stamp'])    # `<!-- generated-stamp … -->` — what a generated file was made from
_COLUMN_EN = {'item': 'Item', 'location': 'Location', 'trigger': 'Trigger', 'status': 'Status', 'note': 'Note', 'proposal': 'Proposal',
              'basis': 'Basis', 'file': 'File', 'section': 'Section', 'linked': 'Items', 'condition': 'When this clears',
              'take_up': 'Take up', 'completed': 'Completed'}
COLUMNS = dict((k, (en, _L['columns'][k])) for k, en in _COLUMN_EN.items())   # column names of `| ID |` tables and of the generated tables
FIELDS = dict((k, (en, _L['fields'][k])) for k, en in (('completed', 'Completed'), ('target', 'Target'), ('status', 'Status')))   # record lines `**name** value`
FOCUS_LABEL = ('Working chapter', _L['focus'])
TRIGGER_NOW = ('now', _L['triggers']['now'])      # the one trigger whose meaning the tools know (list §5)
DEFAULT_TRIGGERS = (TRIGGER_NOW, ('when working on the section', _L['triggers']['section']), ('user decision', _L['triggers']['user']),
                    ('when data is available', _L['triggers']['data']), ('before final submission', _L['triggers']['final']))
PLACEHOLDERS = dict((k, (en, _L['placeholders'][k])) for k, en in
                    (('no_location', '(no location)'), ('not_given', '(not given)'), ('excluded_only', '(excluded files only)')))
# Status vocabulary — (key, English, older spelling), shared by the tidy tool (archive decision, status check) and the index tool (status head).
# English matches whole words at the head of the cell; the open hints match anywhere and win. The older spelling keeps its old rule
# (substring of the cell with spaces removed), so `done (visual check needed)` and its older form both stay open.
_STATE_EN = (('applied_unconfirmed', 'applied (awaiting confirmation)'), ('partly_confirmed', 'partly confirmed'), ('confirmed', 'confirmed'),
             ('closed', 'closed'), ('logged', 'logged'), ('on_hold', 'on hold'), ('in_progress', 'in progress'), ('applied', 'applied'),
             ('done', 'done'), ('waiting', 'waiting'), ('standing', 'standing'), ('refresh', 'refresh'))
STATES = tuple((k, en, _L['states'][k]) for k, en in _STATE_EN)
STATE_HEAD_KEYS = ('applied_unconfirmed', 'partly_confirmed', 'confirmed', 'closed', 'logged', 'on_hold', 'in_progress', 'applied', 'done')
STATE_KNOWN_KEYS = ('waiting', 'in_progress', 'on_hold', 'done', 'closed', 'applied', 'standing', 'refresh')
STATE_CLOSED_KEYS = ('done', 'closed')
STATE_OPEN_HINTS = tuple((en, _L['open_hints'][en]) for en in ('needed', 'waiting'))
STATE_PENDING_KEY = 'applied'                      # applied — in the file but not yet confirmed by the user; stays in the list
SUPERSEDED = ('superseded by', _L['superseded'])   # `superseded by E<n>` — a record replaced by a later one
STATE_REFS = (' · see ', _L['refs'])              # what the record index appends to a status head
_STATE = {k: (en, ko) for k, en, ko in STATES}
# grammar_baseline.py — keys of the baseline `.jsonl` (append-only history: new lines use English keys, old lines keep theirs)
# and of the packet JSON. Both spellings are read.
BASELINE_KEYS = dict((k, (k, v)) for k, v in _L['baseline_keys'].items())
PACKET_KEYS = dict((k, (k, v)) for k, v in _L['packet_keys'].items())
PACKET_FORMAT = ('grammar-packet/2', _L['packet_format'])


def english_keys(obj, table):
    """A dict (or a list of dicts, recursively) with every key of `table` renamed to its English spelling — for reading old files."""
    if isinstance(obj, list):
        return [english_keys(x, table) for x in obj]
    if not isinstance(obj, dict):
        return obj
    rename = dict((ko, en) for en, ko in table.values())
    return dict((rename.get(k, k), english_keys(v, table)) for k, v in obj.items())


def tok(pair, *fmt):
    """The spelling to write — English — of a token pair, with `{}` filled in."""
    return pair[0].format(*fmt)

# Row grammar of the tracker tables, shared by the tidy tool (reading rows, archive, focus), sync (S7 ID collection, the table check
# in replace_once) and the hook (post-write warning) — one `| ID | … |` line is one item, and `|` inside a cell is `\|`
# (rules: `tracker-workflow.md` "Table row format — one item per line").
TABLE_ID = r'[A-Z]{1,2}\d+(?:-\d+)?'                                        # row ID — 1–2 letters + number (-branch number)
TABLE_ROW_RE = re.compile(r'^\|\s*(' + TABLE_ID + r')\s*\|')                 # match on one line
TABLE_ROW_RE_M = re.compile(r'^\|\s*(' + TABLE_ID + r')\s*\|', re.M)         # findall over a whole file
TABLE_SEP_RE = re.compile(r'^\|\s*:?-{3,}')                                  # separator under the header `|---|`
_TABLE_BREAK_RE = re.compile(r'^(?:<|#|>|[-*+] |\d+[.)] |```|---|\*\*\*)')  # start of a block that ends a table — not an orphan line
_CELL_SPLIT_RE = re.compile(r'(?<!\\)\|')
TABLE_PROBLEM_TEXT = {
    'orphan': 'non-table line right below a row — the row is split over two lines. Join it to the end of the row above (one item per line) or delete it',
    'cells': 'cell count differs from the header — write `|` inside a cell as `\\|`',
    'tail': 'row does not end with `|`',
}


def split_cells(line):
    """'| a | b \\| c |' -> ['a', 'b \\| c'] — `\\|` inside a cell is not a boundary and stays as is (use unescape_cell when copying out of the table)."""
    t = line.strip()
    if t.startswith('|'):
        t = t[1:]
    if t.endswith('|') and not t.endswith('\\|'):
        t = t[:-1]
    return [c.strip() for c in _CELL_SPLIT_RE.split(t)]


def unescape_cell(cell):
    """For copying a cell value out of the table (into a paragraph) — `\\|` becomes `|`."""
    return cell.replace('\\|', '|')


def table_problems(text):
    """Table defects — [(line number (from 1), code, preview of the line)]. Codes are explained in TABLE_PROBLEM_TEXT.

    A table is a run of lines starting with `|`; the first line is the header. A blank line or another block (comment `<!-- -->`, heading,
    quote, list, code fence, horizontal rule) ends the table. Any other line directly below a row is `orphan` — GFM draws it as a one-cell
    row and the tools cannot see it (it has no ID), so it is the trace of a row split over two lines. Cell count and the trailing `|` are
    checked only for rows whose ID can be read (tables without IDs, such as the detail tables of the literature file, are free-form).
    Code fences are skipped. CRLF line endings are fine.
    """
    out = []
    hdr_n, prev_row, in_code = None, False, False
    for n, line in enumerate(text.replace('\r\n', '\n').split('\n'), 1):
        if line.startswith('```'):
            in_code, prev_row = not in_code, False
            continue
        if in_code:
            continue
        if line.startswith('|'):
            if not prev_row:
                hdr_n = len(split_cells(line))
            elif not TABLE_SEP_RE.match(line) and TABLE_ROW_RE.match(line):
                if len(split_cells(line)) != hdr_n:
                    out.append((n, 'cells', line.strip()[:60]))
                r = line.rstrip()
                if not r.endswith('|') or r.endswith('\\|'):
                    out.append((n, 'tail', line.strip()[:60]))
            prev_row = True
            continue
        if prev_row and line.strip() and not _TABLE_BREAK_RE.match(line.lstrip()):
            out.append((n, 'orphan', line.strip()[:60]))
        prev_row = False
    return out


def describe_table_problem(prob):
    """(line number, code, preview) → one human-readable line."""
    n, code, preview = prob
    return 'line %d — %s: `%s`' % (n, TABLE_PROBLEM_TEXT.get(code, code), preview)


def is_orphan_after(lines, i):
    """When lines[i] is a row: whether the line right below it is an orphan line (a split-off tail)."""
    if i + 1 >= len(lines):
        return False
    nxt = lines[i + 1]
    return bool(nxt.strip()) and not nxt.startswith('|') and not _TABLE_BREAK_RE.match(nxt.lstrip())


_ROWISH_STRIP_RE = re.compile(r'[*`~\s]')


def row_like_id(line):
    """The ID if the first cell of a `|` line looks like one — after stripping emphasis, code and strike-through marks (`**A1**` · `` `A1` `` · `~~A1~~`) it matches TABLE_ID. Otherwise None.
    Rows that TABLE_ROW_RE reads return the same ID — callers compare with the rows they read to find lines that look like rows but were not read as rows."""
    if not line.startswith('|') or TABLE_SEP_RE.match(line):
        return None
    first = _ROWISH_STRIP_RE.sub('', split_cells(line)[0])
    return first if re.fullmatch(TABLE_ID, first) else None


def id_key(rid):
    """ID sort key — `A2` < `A12` < `A12-1` < `B1`. Shared by the tidy tool (numkey) and sync (S3, S7)."""
    m = re.match(r'^([A-Z]+)(\d+)(?:-(\d+))?$', rid)
    return (m.group(1), int(m.group(2)), int(m.group(3) or 0)) if m else (rid, 0, 0)


# Numbers of new open items are assigned by a tool (`new_pending.py`). The scope is defined here only; the tool (assignment) and the hook (refusing hand-added rows) share it.
PROPOSAL_PREFIX = 'H'                                                        # ID letter of the proposals file
NEW_ROW_RE = re.compile(r'^\|\s*([A-Z]{1,2})\?\s*\|')                        # new row whose number is `?` — `| D? | … |`


def allocation_scope(cfg):
    """{letter: file relative to the root (`/`-separated, NFC)} — the tables whose numbers the tool assigns: the pending file's category letters (tracker.movable_prefixes) and the proposals file's letter.
    The literature file holds several kinds of table and is left out. Other files and letters are not assigned by the tool, and the hook does not check them."""
    rel = lambda p: nfc(str(p).replace('\\', '/'))                           # noqa: E731
    out = dict((str(l), rel(cfg.pending_file)) for l in cfg.movable)
    out[PROPOSAL_PREFIX] = rel(cfg.proposals_file)
    return out


def id_stem(rid):
    """Stem of a branch number — `D35-1` → `D35`. Unchanged when there is no branch."""
    return rid.split('-', 1)[0]


# Where open-item IDs sit in the generated blocks of the list (index file). The tidy tool writes this shape; sync S3 and the tidy tool's own check
# read only these positions — free text such as item, location and notes copies labels from other documents verbatim (decision numbers of a plan, IDs of another project).
#   locations  `| File | Section | ID · ID |`          last cell
#   triggers   `| **condition** | ID · ID (n) |`      last cell
#   now        `| **ID** | Item | Location | Status |`  first cell
#   focus      `#### ID — item`                         item heading (the notes copy below it is not read)
_LIST_KEYS = ('locations', 'triggers', 'now', 'focus')
_LIST_NAME_KEY = dict((name, k) for k in _LIST_KEYS for name in BLOCKS[k])
LIST_BLOCK_RE = re.compile(r'<!-- (%s) -->(.*?)<!-- /\1 -->' % '|'.join(re.escape(n) for n in _LIST_NAME_KEY), re.S)
LIST_FOCUS_HEAD_RE = re.compile(r'^#### (' + TABLE_ID + r')\s+—', re.M)
_ID_TOKEN_RE = re.compile(r'(?<![\w-])(' + TABLE_ID + r')(?![\w-])')


def list_block_ids(text):
    """List text → ({block key: [ID …]}, [blocks whose shape could not be read …]). Keys are those of `BLOCKS` (`locations` …);
    both spellings of the markers are read. Shape not read — the block contains ID-like text but no ID could be read from the ID
    positions (old version or hand edit). Callers warn."""
    ids, unknown = {}, []
    for m in LIST_BLOCK_RE.finditer(text.replace('\r\n', '\n')):
        key, body = _LIST_NAME_KEY[m.group(1)], m.group(2)
        if key == 'focus':
            got = LIST_FOCUS_HEAD_RE.findall(body)
        else:
            got = []
            for line in body.split('\n'):
                if not line.startswith('|') or TABLE_SEP_RE.match(line):
                    continue
                cs = split_cells(line)
                got += _ID_TOKEN_RE.findall(cs[0] if key == 'now' else cs[-1])
        ids.setdefault(key, []).extend(got)
        if not got and _ID_TOKEN_RE.search(body):
            unknown.append(key)
    return ids, unknown


def _norm(s):
    """Comparison string with Markdown emphasis and whitespace removed"""
    return re.sub(r'\s+', '', re.sub(r'\*\*|`', '', unicodedata.normalize('NFC', s or '')))


def _plain(s):
    """Lower-case text with Markdown emphasis removed and whitespace collapsed — for English whole-word matching."""
    return re.sub(r'\s+', ' ', re.sub(r'\*\*|`', '', unicodedata.normalize('NFC', s or ''))).strip().lower()


def _en_head(text, words):
    """The English word or phrase among `words` that opens `text` as whole words (case-insensitive), else None."""
    t = _plain(text)
    for w in sorted(words, key=len, reverse=True):
        if re.match(re.escape(w.lower()) + r'(?![a-z])', t):
            return w
    return None


def column_key(cell):
    """Key of a column name in either spelling (`Status` or its older spelling → `status`), else None."""
    n = _norm(cell)
    for k, (en, ko) in COLUMNS.items():
        if n == _norm(ko) or n.lower() == _norm(en).lower():
            return k
    return None


def field_pattern(key):
    """Regex text for a record field label in either spelling — `\\*\\*(?:Target|<older spelling>)\\*\\*`."""
    return r'\*\*(?:%s)\*\*' % '|'.join(re.escape(s) for s in FIELDS[key])


FOCUS_RE = re.compile(r'\*\*(?:%s)\*\*\s+(ch\d+)' % '|'.join(re.escape(s) for s in FOCUS_LABEL))


def trigger_key(value):
    """Comparison form of a trigger cell — the English spelling for the default triggers in either spelling, otherwise the
    value with emphasis and spaces removed. Projects keep their own trigger list (`tracker.triggers`); this only makes
    the two spellings of `now` (and of the other default triggers) the same trigger."""
    n = _norm(value)
    for pair in DEFAULT_TRIGGERS:
        if n == _norm(pair[1]) or n.lower() == _norm(pair[0]).lower():
            return _norm(pair[0]).lower()
    return n


def is_now(value):
    return trigger_key(value) == _norm(TRIGGER_NOW[0])


def state_is_closed(status):
    """With this status value the item moves from the list to the completion records.

    Not moved — `applied (E<n>)` (before the user's confirmation), `done (visual check needed)` (work remains),
    `waiting` `in progress` `on hold` — and the same in the older spellings.
    """
    s, t = _norm(status), _plain(status)
    en_applied, ko_applied = _STATE[STATE_PENDING_KEY]
    if s.startswith(ko_applied) or _en_head(status, [en_applied]):
        return False
    if any(ko in s for _en, ko in STATE_OPEN_HINTS) or \
            re.search(r'(?<![a-z])(?:%s)(?![a-z])' % '|'.join(en for en, _ko in STATE_OPEN_HINTS), t):
        return False
    return any(_STATE[k][1] in s for k in STATE_CLOSED_KEYS) or bool(_en_head(status, [_STATE[k][0] for k in STATE_CLOSED_KEYS]))


def state_known(status):
    """True when the status uses the vocabulary — a Korean word anywhere (old rule) or an English one at the head."""
    s = _norm(status)
    return any(_STATE[k][1] in s for k in STATE_KNOWN_KEYS) or bool(_en_head(status, [_STATE[k][0] for k in STATE_KNOWN_KEYS]))


def state_head(status):
    """Head of a long status string + ` · see E…`. Used by record index §2.

    The head is the first match among the head words (either spelling) or `… superseded by E<n>` (either spelling); otherwise
    the first clause (before ` — `, `(` or `「`, at most 24 characters). The head is kept as written — the record's own words.
    ` · see` appends the E numbers that follow the head, in order and without duplicates.
    """
    heads = sorted([s for k in STATE_HEAD_KEYS for s in _STATE[k]], key=len, reverse=True)
    pat = re.compile(r'^\**\s*(' + '|'.join(re.escape(h) + (r'(?![a-z])' if h.isascii() else '') for h in heads)
                     + r'|[^—(「\n]{0,20}?(?:%s)\s*E\d+)' % '|'.join(re.escape(w) for w in SUPERSEDED), re.I)
    m = pat.match(status)
    if m:
        h, rest = m.group(1).strip('* '), status[m.end():]
    else:
        h = re.split(r' — |\(|「', status)[0].strip('* ')[:24]
        rest = status[len(h):]
    refs = []
    for r in re.findall(r'E\d+', rest):
        if r not in refs and r not in h:
            refs.append(r)
    return h + ((STATE_REFS[0] + ' '.join(refs)) if refs else '')

DEFAULTS = {
    "tools_dir": "tools",                         # folder for the managed tools (directly under the root)
    "manuscript": {
        "source_dir": "manuscript_src",
        "chapters": [{"n": i, "file": "ch%d.md" % i} for i in (1, 2, 3, 4)],
        "references": "references.md",
        "build_script": "build_tpl.py",
        "figure_dir": "fig_src",
    },
    "tracker": {
        "index": "tracker_index.md",
        "pending": "tracker_pending.md",
        "record_index": "tracker_records_index.md",
        "literature": "tracker_literature.md",
        "proposals": "tracker_proposals.md",
        "records_dir": "records",
        "archive": "records/archive.md",
        "record_prefix": "E",
        "movable_prefixes": ["A", "B", "C", "D"],
        "index_size_limit_kb": 40,
        # the five shared triggers — values tied to review or submission dates are added by the project's project.json (tracker.triggers)
        "triggers": [tok(pair) for pair in DEFAULT_TRIGGERS],
        # location syntax (_location.py) — section markers the project adds (regex list) and files left out of record index §1 (glob list)
        "section_markers": [],
        "record_index_exclude": [],
        # handover (current state) file — rewritten wholesale, so left out of the sync loss report (S6). Empty string if none
        "checkpoint": "",
    },
    # sync guard for the shared files (_sync.py) — meanings in `tracker-workflow.md` "Sync — several computers write the shared files". The core checks run on these defaults alone.
    "sync": {
        "shared_extra": [],                        # shared files besides tracker files, completion records and manuscript .md (globs relative to the root)
        "snapshot_dir": "archive/tracker_backup",    # snapshot folder on the drive side (relative to the root)
        "conflict_patterns": [" \\d+$", " \\(\\d+\\)$", "conflicted copy"],   # conflict-copy names (matched against the name without extension)
        "exclude": [".git/", "__pycache__/", "node_modules/", "archive/", ".manuscript/tools_backup/"],
        "stale_days": 2,
        "snapshot_days": 30,                       # retention of this computer's snapshots in days (drive — local keeps them twice as long)
        "snapshot_days_others": 90,                # age after which snapshots made by other computers may be deleted
        "snapshot_min": 10,                        # most recent snapshots always kept per file
        "snapshot_max": 20,                        # cap on this computer's snapshots per file (drive)
        "snapshot_max_local": 100,                 # same cap (local — larger, since every write leaves one)
        "ack_hours": 4,
        "known_gaps": [],                          # completion record numbers that are missing on purpose
        "rewrite_ok": [],                          # documents rewritten wholesale — left out of the loss report (checkpoint is automatic)
        "survival_pct": 70,
    },
}


TOOLS_BACKUP = os.path.join('.manuscript', 'tools_backup')     # where update_tools.py keeps copies before replacing files


def _items(table):
    """[(section or None, key, value)] — top-level values have section None."""
    out = []
    for k, v in table.items():
        if isinstance(v, dict):
            out += [(k, kk, vv) for kk, vv in v.items()]
        else:
            out.append((None, k, v))
    return out


def _has(raw, sec, key):
    return key in (raw if sec is None else (raw.get(sec) or {}))


def legacy_pins(root, raw):
    """For an old project, the values to add to the settings {section: {key: value}} (top-level keys as is); otherwise {}.
    Old project — among the path keys missing from the settings, at least one has no new name on disk while its old name exists. The values to add are all old keys missing from the settings."""
    absent = [(s, k, v) for s, k, v in _items(LEGACY_DEFAULTS) if not _has(raw, s, k)]
    new = dict(((s, k), v) for s, k, v in _items(DEFAULTS))
    old_only = lambda rel_old, rel_new: (os.path.exists(os.path.join(root, *rel_old.split('/')))       # noqa: E731
                                         and not os.path.exists(os.path.join(root, *rel_new.split('/'))))
    if not any(isinstance(v, str) and old_only(v, new[(s, k)]) for s, k, v in absent):
        return {}
    pins = {}
    for s, k, v in absent:
        if s is None:
            pins[k] = v
        else:
            pins.setdefault(s, {})[k] = v
    return pins


class LegacyNames(SystemExit):
    """A project that uses the old default (Korean) names without settings — stops and shows the values to add to the settings."""
    def __init__(self, root, pins):
        self.root, self.pins = root, pins
        SystemExit.__init__(self, legacy_message(pins))


def legacy_message(pins):
    return ('This project uses the old default (Korean) names. Add the values below to `%s` and run again — they keep the current names:\n%s'
            % (CONFIG_REL.replace(os.sep, '/'), json.dumps(pins, ensure_ascii=False, indent=2)))


def project_root(start=None):
    """The given folder; otherwise this file's folder or its parent, whichever holds a settings file. If neither does, the parent of the tools folder (`tools` or its old default name)."""
    if start:
        return os.path.abspath(start)
    d = os.path.dirname(os.path.abspath(__file__))
    for cand in (d, os.path.dirname(d)):
        if any(os.path.isfile(os.path.join(cand, rel)) for rel in (CONFIG_REL, CONFIG_REL_OLD)):
            return cand
    return os.path.dirname(d) if os.path.basename(d) in (DEFAULTS['tools_dir'], LEGACY_DEFAULTS['tools_dir']) else d


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


class Config(object):
    def __init__(self, root, raw):
        self.root = root
        self.raw = raw
        self.name = raw.get('project', os.path.basename(root))
        self.kind = raw.get('kind', 'manuscript')
        self._m = raw['manuscript']
        self._t = raw['tracker']

    # ---- tools
    @property
    def tools_dir(self):
        return self.raw['tools_dir']

    def tool(self, name):
        """Tool path for messages (relative to the root, `/`-separated) — e.g. `tools/tidy_tracker.py`."""
        return '%s/%s' % (str(self.tools_dir).replace('\\', '/').strip('/'), name)

    # ---- manuscript
    @property
    def source_dir(self):
        p = os.path.join(self.root, self._m['source_dir'])
        return p if os.path.isdir(p) else self.root

    @property
    def source_rel(self):
        """Name of the manuscript folder relative to the root (`/`-separated, no trailing `/`). The location syntax uses it for display and resolution."""
        return str(self._m['source_dir']).replace('\\', '/').strip('/')

    @property
    def output_pattern(self):
        """Glob of build output names (e.g. `manuscript_v*.docx`). None if unset — the record index uses it to leave those files out."""
        return self._m.get('output_pattern') or None

    @property
    def chapters(self):
        """[(number, file name), ...] — the form check_numbers and the build use"""
        return [(c['n'], c['file']) for c in self._m['chapters']]

    @property
    def references(self):
        return self._m['references']

    @property
    def build_script(self):
        return self._m['build_script']

    # ---- tracking
    @property
    def tracker_files(self):
        """The five files the tidy tool handles. Keep this order."""
        t = self._t
        return [t['index'], t['pending'], t['record_index'], t['literature'], t['proposals']]

    @property
    def index_file(self):
        return self._t['index']

    @property
    def pending_file(self):
        return self._t['pending']

    @property
    def record_index_file(self):
        return self._t['record_index']

    @property
    def literature_file(self):
        return self._t['literature']

    @property
    def proposals_file(self):
        return self._t['proposals']

    @property
    def records_dir(self):
        return self._t['records_dir']

    @property
    def archive(self):
        return os.path.join(*self._t['archive'].split('/'))

    @property
    def triggers(self):
        return list(self._t['triggers'])

    @property
    def movable(self):
        return list(self._t['movable_prefixes'])

    @property
    def index_limit(self):
        return int(self._t['index_size_limit_kb']) * 1024

    @property
    def section_markers(self):
        """Section markers the project adds — list of regex strings. Empty by default."""
        return list(self._t.get('section_markers') or [])

    @property
    def record_index_exclude(self):
        """Globs of files and folders left out of record index §1 (relative to the root, folders end in `/`). Empty by default."""
        return list(self._t.get('record_index_exclude') or [])

    @property
    def checkpoint(self):
        """Handover file (relative to the root). None if unset."""
        return (self._t.get('checkpoint') or None)

    # ---- sync
    @property
    def sync(self):
        """Sync guard settings (dict merged with the defaults). Meanings in `tracker-workflow.md` "Sync — several computers write the shared files"."""
        return dict(self.raw.get('sync') or {})

    def __getitem__(self, k):
        return self.raw[k]


def load(root=None, strict=True):
    """strict — stop with LegacyNames in a project that uses the old default names without settings. Only update_tools.py reads with False and reports by itself."""
    root = project_root(root)
    path = os.path.join(root, CONFIG_REL)
    if not os.path.isfile(path):
        old = os.path.join(root, CONFIG_REL_OLD)
        if os.path.isfile(old):
            path = old
    raw = {}
    if os.path.isfile(path):
        try:
            with io.open(path, encoding='utf-8') as f:
                raw = json.load(f)
        except ValueError as e:
            raise SystemExit('Could not read %s: %s' % (CONFIG_REL, e))
    if strict:
        pins = legacy_pins(root, raw)
        if pins:
            raise LegacyNames(root, pins)
    cfg = Config(root, _merge(DEFAULTS, raw))
    cfg.raw_file = raw                     # as written in the settings file (before merging with the defaults)
    return cfg


# ---------------------------------------------------------------- format of a project — read from its anchors
# The anchors are what the tools own in the tracker files: block markers, generated-stamp lines and the known column names of
# `| ID |` header rows. Each tracker file shows English, Korean, both or none; the project's format is their union. There is no
# settings key — the files say which format they are in, and the tools do not write `project.json`.
def _marker_re(lang):
    names = [re.escape(pair[lang]).replace(r'\{\}', '[A-Z]{1,2}') for pair in BLOCKS.values()]
    return re.compile(r'^<!-- /?(?:%s) -->\s*$' % '|'.join(names))


_MARKER_RES = (_marker_re(0), _marker_re(1))
STAMP_RE = re.compile(r'^<!-- (?:%s) (.*?) -->\s*$' % '|'.join(re.escape(w) for w in STAMP_WORDS), re.M)
_STAMP_LANG = tuple(re.compile(r'^<!-- %s ' % re.escape(w)) for w in STAMP_WORDS)
LANGS = ('en', 'ko')


def text_format(text):
    """{'en', 'ko'} — the spellings of the anchors in one file's text (code fences are skipped)."""
    out, fence = set(), False
    for line in text.replace('\r\n', '\n').split('\n'):
        if line.startswith('```'):
            fence = not fence
            continue
        if fence:
            continue
        for i in (0, 1):
            if _MARKER_RES[i].match(line) or _STAMP_LANG[i].match(line):
                out.add(LANGS[i])
        if line.startswith('|'):
            cells = split_cells(line)
            if cells and cells[0] == 'ID':
                for c in cells[1:]:
                    k = column_key(c)
                    if k:
                        out.add('ko' if _norm(c) == _norm(COLUMNS[k][1]) else 'en')
    return out


def is_anchor_line(line):
    """True for a line the tools own as structure — a block marker or a generated-stamp line in either spelling, or an `| ID |` header row.
    The sync loss report (S6) leaves these out: they are not anyone's content, and the format migration rewrites them."""
    t = (line or '').strip()
    return bool(_MARKER_RES[0].match(t) or _MARKER_RES[1].match(t) or _STAMP_LANG[0].match(t) or _STAMP_LANG[1].match(t)
                or re.match(r'^\|\s*ID\s*\|', t))


def tracker_anchor_files(cfg):
    """The files whose anchors decide the format — the five tracker files and the archive (relative to the root, `/`)."""
    t = cfg.raw['tracker']
    return [str(t[k]).replace('\\', '/') for k in ('index', 'pending', 'archive', 'proposals', 'literature', 'record_index') if t.get(k)]


def project_format(cfg):
    """('en' | 'ko' | 'mixed' | 'none', {file: sorted languages}) — 'none' when no tracker file shows an anchor."""
    per = {}
    for rel in tracker_anchor_files(cfg):
        p = os.path.join(cfg.root, *rel.split('/'))
        if os.path.isfile(p):
            with io.open(p, encoding='utf-8') as f:
                langs = text_format(f.read())
            if langs:
                per[rel] = sorted(langs)
    union = set(x for v in per.values() for x in v)
    state = 'mixed' if len(union) > 1 else (union.pop() if union else 'none')
    return state, per


RC_FORMAT = 5      # exit code of a writing tool that refuses an old-format or mixed project


def format_problem(cfg, tool):
    """None when the project may be written by this version (English anchors or none), otherwise the message to show."""
    state, per = project_format(cfg)
    if state in ('en', 'none'):
        return None
    where = '; '.join('%s: %s' % (rel, '+'.join(v)) for rel, v in sorted(per.items()))
    fix = 'python -X utf8 <plugin>/skills/new-manuscript/update_tools.py "%s"' % cfg.root
    if state == 'ko':
        return ('%s: this project still uses the pre-0.14 Korean anchors (%s). This version writes English anchors only, so it stops '
                'here — reading and diagnosis still work. Preview the migration with `%s`, then add --apply after the user agrees.'
                % (tool, where, fix))
    return ('%s: the tracker files mix English and Korean anchors (%s) — Drive may not have caught up, or a tool from an older plugin '
            'version wrote here. Nothing is written. Check that Drive is up to date and every computer has the new plugin, then run '
            '`%s --apply` (the migration is idempotent).' % (tool, where, fix))


def require_writable_format(cfg, tool):
    """Writing tools call this first — exits with RC_FORMAT and the message when the format is old or mixed."""
    msg = format_problem(cfg, tool)
    if msg:
        sys.stderr.write(msg + '\n')
        raise SystemExit(RC_FORMAT)


if __name__ == '__main__':
    _utf8_console()
    c = load()
    print('project    :', c.name, '(%s)' % c.kind)
    print('root       :', c.root)
    print('source_dir :', c.source_dir)
    print('chapters   :', c.chapters)
    print('references :', c.references)
    print('tracker    :', c.tracker_files)
    print('records    :', c.records_dir, '/ archive:', c.archive)
    print('triggers   :', len(c.triggers), 'values')
    print('movable    :', c.movable, '/ limit:', c.index_limit)
