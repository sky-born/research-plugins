# -*- coding: utf-8 -*-
r"""new_pending.py — 새 미결 항목(대기 파일의 글자 표 · 제안 표)을 다음 번호로 등록합니다.

사용  (`<py>` 는 이 컴퓨터의 Python 3 — 윈도 `python` · 맥 `python3`)
    <py> -X utf8 tools/new_pending.py <행 파일>

<행 파일> 은 UTF-8 텍스트 한 줄이고 **ID 자리가 `글자?`** 인 표 행입니다 — 대기 `| D? | 항목 | 위치 | 트리거 | 상태 | 비고 |`,
제안 `| H? | 제안 | 위치 | 상태 | 근거 |`. 칸의 수와 순서는 그 표의 머리와 같아야 합니다(한 항목은 한 줄 · 셀 안의 `|` 는 `\|`).
`글자?` 자리에 이 도구가 배정한 번호가 들어가고, 행 안의 다른 `글자?` 도 같은 번호로 바뀝니다(자기 참조용).

왜 도구가 번호를 정하는가 — 두 세션이 같은 폴더를 쓰면 "다음 번호"를 같이 집어 한 ID 가 두 항목에 붙습니다. Edit 은 대상 문자열만
바꾸므로 둘 다 성공하고, 중복은 정리 도구의 경고로 나중에야 드러납니다. 이 도구는 **쓰기 잠금 안에서** 파일을 다시 읽어 번호를
정하고 그 자리에서 행을 넣으므로, 같은 컴퓨터의 두 실행이 같은 번호를 받지 않습니다. 손으로 새 ID 행을 넣는 Edit · Write 는
훅(`guard_write.py`)이 거부합니다. **호출한 쪽은 출력된 번호를 받아서만 다른 문서에 적습니다.**

번호 — 그 글자의 최대 번호 + 1. 대기 · 이관 · 제안 · 문헌 파일의 행과 이 컴퓨터가 본 ID 등록(동기화 상태)을 함께 봅니다 — ID 는
       재사용하지 않으므로 이관된 번호도 건너뜁니다.
자리 — 그 글자의 표 맨 아래. 대기 파일은 `## <글자>. …` 절의 표, 제안 파일은 그 글자의 행이 있는 표(없으면 첫 표).
범위 — `_config.allocation_scope`(대기 파일의 분류 글자 · 제안 파일의 글자). 문헌 파일과 가지 번호(`D35-1`)는 다루지 않습니다.
막지 못하는 것 — 다른 컴퓨터가 같은 번호를 받는 것(동기화 점검이 봅니다) · Python · Bash 로 행을 직접 넣는 길.

목록(색인 파일)의 위치 표 · 트리거 표는 다음 `tidy_tracker.py --apply` 가 맞춥니다.

출력  표준 출력 한 줄:  D137<TAB>tracker_pending.md  (안내 · 경고는 표준 오류로 — 표준 출력은 번호 한 줄뿐)
종료  0 성공 · 1 행 형식 오류 · 2 표를 찾지 못함(범위 밖 글자 · 절이나 표가 없음 · 표가 여럿) · 3 동기화 점검 ERROR 로 거부 ·
      4 잠금을 못 잡음(다시 돌리면 됩니다)
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import (load, _콘솔_UTF8, nfc, NEW_ROW_RE, allocation_scope,                      # noqa: E402
                     TABLE_ROW_RE, TABLE_SEP_RE, split_cells, table_problems, describe_table_problem)

HDR = re.compile(r'^\|\s*ID\s*\|')           # 표 머리 — 정리 도구가 읽는 것과 같은 모양


class Problem(Exception):
    def __init__(self, code, text):
        Exception.__init__(self, text)
        self.code = code


def say(text):
    print(text, file=sys.stderr)


def read_row(path):
    """행 파일 → (행, 글자). 빈 줄을 뺀 한 줄이어야 하고 ID 자리가 `글자?` 여야 합니다."""
    try:
        body = io.open(path, encoding='utf-8-sig').read()
    except OSError as e:
        raise Problem(1, '행 파일을 읽지 못했습니다: %s' % e)
    rows = [l.rstrip() for l in body.replace('\r\n', '\n').split('\n') if l.strip()]
    if len(rows) != 1:
        raise Problem(1, '행 파일은 한 줄이어야 합니다(한 항목은 한 줄) — 지금 %d줄' % len(rows))
    row = rows[0].strip()
    m = NEW_ROW_RE.match(row)
    if not m:
        raise Problem(1, "행은 `| D? | … |` 처럼 ID 자리가 `글자?` 여야 합니다 — 번호는 이 도구가 정합니다. 지금: %r" % row[:60])
    if not row.endswith('|') or row.endswith('\\|'):
        raise Problem(1, '행은 `|` 로 끝나야 합니다: %r' % row[-30:])
    return row, m.group(1)


def _letter(line):
    m = TABLE_ROW_RE.match(line)
    return re.match(r'[A-Z]+', m.group(1)).group(0) if m else None


def _tables(lines, a, b):
    """구간 [a, b) 의 표 — [[머리 인덱스, 머리 셀, [행 인덱스 …]]]. 머리는 `| ID | …` 줄, 행은 그 아래 다음 머리 · 제목 · 주석 전까지의
    ID 행입니다. 행 사이의 빈 줄은 건너뜁니다 — 행을 빈 줄로 띄워 둔 옛 파일이 있습니다."""
    out, cur = [], None
    for i in range(a, b):
        l = lines[i]
        if HDR.match(l):
            cur = [i, split_cells(l), []]
            out.append(cur)
        elif cur is not None:
            if l.startswith('#') or l.startswith('<!--'):
                cur = None
            elif TABLE_ROW_RE.match(l):
                cur[2].append(i)
    return out


def locate(lines, letter, sectioned, label):
    """그 글자의 표에서 새 행이 들어갈 줄 인덱스와 머리 셀. sectioned — 대기 파일처럼 `## <글자>. …` 절로 나뉜 파일."""
    a, b = 0, len(lines)
    if sectioned:
        heads = [i for i, l in enumerate(lines) if l.startswith('## ')]
        mine = [i for i in heads if re.match(r'^## %s\. ' % re.escape(letter), lines[i])]
        if not mine:
            raise Problem(2, '%s 에 `## %s. …` 절이 없습니다 — 없앤 분류라면 남아 있는 분류의 글자로 등록하십시오(없앤 글자는 다시 내지 않습니다)'
                          % (label, letter))
        if len(mine) > 1:
            raise Problem(2, '%s 에 `## %s. …` 절이 %d개 있습니다(하나여야 함)' % (label, letter, len(mine)))
        a = mine[0]
        b = min([h for h in heads if h > a] or [len(lines)])
    tabs = _tables(lines, a, b)
    if not tabs:
        raise Problem(2, '%s 에서 %s 표(머리 `| ID | …`)를 찾지 못했습니다' % (label, letter))
    own = [t for t in tabs if any(_letter(lines[i]) == letter for i in t[2])]
    if len(own) > 1:
        raise Problem(2, '%s 에 %s 행이 있는 표가 %d개입니다 — 어느 표에 넣을지 정할 수 없습니다(머리 %s행)'
                      % (label, letter, len(own), ' · '.join(str(t[0] + 1) for t in own)))
    head, cells, rows = own[0] if own else tabs[0]
    if rows:
        return rows[-1] + 1, cells
    if head + 1 < len(lines) and TABLE_SEP_RE.match(lines[head + 1]):
        return head + 2, cells
    raise Problem(2, '%s %d행의 표 머리 아래에 구분선(`|---|`)이 없습니다 — 먼저 고치십시오' % (label, head + 1))


def next_number(known, letter):
    pat = re.compile(r'^%s(\d+)(?:-\d+)?$' % re.escape(letter))
    nums = [int(m.group(1)) for i in known for m in [pat.match(i)] if m]
    return (max(nums) if nums else 0) + 1


def register(cfg, sync, row, letter):
    """잠금 안에서 부릅니다 — 파일을 지금 읽어 번호를 정하고 행을 넣습니다. (ID, 루트 기준 파일)."""
    from _sync import _read_bytes, _atomic_write
    scope = allocation_scope(cfg)
    if letter not in scope:
        raise Problem(2, '글자 %s 는 이 도구가 번호를 정하는 범위가 아닙니다 — 되는 글자: %s (문헌 파일 · 가지 번호는 손으로)'
                      % (letter, ' · '.join(sorted(scope))))
    rel = scope[letter]
    pending = nfc(str(cfg.pending_file).replace('\\', '/'))
    path = os.path.join(cfg.root, *rel.split('/'))
    try:
        raw = _read_bytes(path)
    except OSError as e:
        raise Problem(2, '%s 를 읽지 못했습니다: %s' % (rel, e))
    crlf = b'\r\n' in raw and raw.count(b'\r\n') >= raw.count(b'\n') // 2
    eol = '\r\n' if crlf else '\n'
    text = raw.decode('utf-8')
    lines = text.split(eol)
    at, hdr = locate(lines, letter, rel == pending, rel)
    cells = split_cells(row)
    if len(cells) != len(hdr):
        raise Problem(1, '칸 수가 표와 다릅니다 — 행 %d칸, 표 %d칸: | %s |' % (len(cells), len(hdr), ' | '.join(hdr)))
    if '트리거' in hdr:
        trig = cells[hdr.index('트리거')].strip()
        if trig not in cfg.triggers:
            say('  ! 트리거 값 %r 는 설정(tracker.triggers)에 없습니다 — 정리 도구가 경고합니다' % trig)

    new_id = '%s%d' % (letter, next_number(sync.known_ids(), letter))
    line = re.sub(r'(?<![\w-])%s\?' % re.escape(letter), new_id, row)
    lines.insert(at, line)
    out = eol.join(lines)
    before, after = table_problems(text), table_problems(out)
    grew = [c for c in ('orphan', 'cells', 'tail')
            if sum(1 for x in after if x[1] == c) > sum(1 for x in before if x[1] == c)]
    if grew:
        raise Problem(1, '이 행을 넣으면 표가 깨져 넣지 않았습니다 — %s'
                      % ' · '.join(describe_table_problem(x) for x in after if x[1] in grew)[:400])
    sync.before_write(rel)
    _atomic_write(path, out.encode('utf-8'))
    sync.after_write(rel)
    sync.remember_ids()
    if ('<!-- %s위치 -->' % letter) in lines:      # 손으로 관리하는 위치 표가 있는 파일(제안의 `<!-- H위치 -->`) — 정리 도구가 빠진 ID 를 경고합니다
        say('  %s 의 위치 표(`<!-- %s위치 -->`)에도 %s 을(를) 적으십시오 — 손으로 관리하는 표입니다' % (rel, letter, new_id))
    return new_id, rel


def main(argv):
    _콘솔_UTF8()
    args = argv[1:]
    if len(args) != 1 or args[0] in ('-h', '--help'):
        print(__doc__)
        return 1
    try:
        row, letter = read_row(args[0])
        cfg = load()
        from _sync import Sync, refuse_if_alert
        sync = Sync(cfg)
        if not refuse_if_alert(sync, True, 'new_pending'):
            return 3
        with sync.write_lock('new_pending') as lock:
            if lock.busy:
                say('! ' + lock.busy_message())
                return 4
            new_id, rel = register(cfg, sync, row, letter)
    except Problem as e:
        say('등록하지 않았습니다 — %s' % e)
        return e.code
    print('%s\t%s' % (new_id, rel), flush=True)
    say('  목록의 위치 표 · 트리거 표는 다음 `tidy_tracker.py --apply` 가 맞춥니다')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
