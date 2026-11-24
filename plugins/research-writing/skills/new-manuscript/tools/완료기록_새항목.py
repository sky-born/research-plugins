# -*- coding: utf-8 -*-
r"""완료기록_새항목.py — 완료 기록 파일을 다음 빈 번호에 원자적으로 만듭니다.

사용
    python 도구\완료기록_새항목.py <본문파일> [--no-index]

<본문파일> 은 UTF-8 텍스트이고 **첫 줄이 `# E? — 제목`** 입니다. `E?` 자리에 이 도구가 배정한
번호가 들어가고, 본문 안의 다른 `E?` 도 같은 번호로 바뀝니다 (자기 참조용).
본문에는 `**완료일**`·`**대상**`·`**상태**` 줄이 있어야 합니다 — 없으면 경고만 내고 만듭니다.
`대상` 은 색인의 역색인이 되므로 만들 때 위치 문법(`_위치.py`)으로 검사합니다 — 파일이 없거나 절 표기만 있으면
경고, 폴더를 확인하지 못한 이름은 안내만 내고 파일은 만듭니다. 규약은 `tracker-workflow.md` 「대상 · 위치 문법」.

왜 도구가 번호를 정하는가 — 두 세션이 같은 폴더를 쓰면 "다음 번호" 를 같이 집어 한쪽 기록이 덮인
사례가 있습니다. 이 도구는 `O_CREAT|O_EXCL` 로 파일을 만들므로 이미 있으면 실패하고 다음 번호로 넘어갑니다.
**호출한 쪽은 출력된 번호를 받아서만 다른 문서에 적습니다.** 번호를 먼저 적고 파일을 나중에 만드는 순서는
금지입니다 — 생성이 실패하면 적어 둔 참조를 전부 되짚어야 합니다.

기록을 만든 뒤 **완료 색인(`완료기록_색인.py`)을 함께 다시 만듭니다** — 색인은 기록 파일만으로 결정되므로 바로 맞출 수 있고,
그래야 다음 세션 시작의 동기화 점검(S4)이 「색인이 낡음」을 내지 않습니다. `--no-index` 로 끕니다(여러 기록을 잇달아 만들 때).

출력  표준 출력 한 줄:  E316<TAB>완료기록/E316.md  (색인 재생성의 안내는 표준 오류로 — 표준 출력은 번호 한 줄뿐)
종료  0 성공 · 1 본문 형식·읽기 오류 · 2 번호 확보 실패 · 3 동기화 점검 ERROR 로 거부

스크립트는 `도구\` 안에 있고 기록 폴더·접두어는 `.manuscript/project.json` (`_config.py`) 에서 읽습니다.
"""
import io
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import load, _콘솔_UTF8  # noqa: E402

MAX_TRIES = 100
REQUIRED = ('**완료일**', '**대상**', '**상태**')


def _rebuild_index(root):
    """완료 색인을 다시 만듭니다 — 같은 폴더의 `완료기록_색인.py` 를 별도 프로세스로(모듈 전역 상태를 섞지 않게)."""
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), '완료기록_색인.py')
    r = subprocess.run([sys.executable, '-X', 'utf8', tool], cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace')
    # 표준 출력은 「번호 한 줄」 계약을 지키고, 색인 도구의 말은 표준 오류로 보냅니다
    for line in (r.stdout + r.stderr).splitlines():
        if line.strip():
            print('  ' + line, file=sys.stderr)
    if r.returncode != 0:
        print('  ! 색인을 다시 만들지 못했습니다(rc=%d) — `완료기록_색인.py` 를 따로 돌리십시오' % r.returncode, file=sys.stderr)
    return r.returncode


def main(argv):
    _콘솔_UTF8()
    rebuild = '--no-index' not in argv[1:]
    args = [a for a in argv[1:] if a != '--no-index']
    if len(args) != 1 or args[0] in ('-h', '--help'):
        print(__doc__)
        return 1
    try:
        body = io.open(args[0], encoding='utf-8-sig').read()
    except OSError as e:
        print('본문 파일을 읽지 못했습니다: %s' % e)
        return 1

    cfg = load()
    from _동기화 import Sync, refuse_if_alert
    sync = Sync(cfg)
    if not refuse_if_alert(sync, True, '완료기록_새항목'):
        return 3
    prefix = cfg.raw['tracker'].get('record_prefix', 'E')
    holder = re.compile(r'\b%s\?' % re.escape(prefix))
    first = body.split('\n', 1)[0].rstrip('\r')
    if not re.match(r'^# %s\?\s*[—-]\s*\S' % re.escape(prefix), first):
        print("첫 줄은 '# %s? — 제목' 형식이어야 합니다. 지금: %r" % (prefix, first[:80]))
        return 1
    for key in REQUIRED:
        if key not in body:
            print('  ! %s 줄이 없습니다 — 색인·정리 도구가 경고합니다' % key)
    m = re.search(r'\*\*대상\*\*\s*(.+)', body)
    if m:
        # 고칠 수 없는 것은 만들 때 검사합니다 — 확정된 기록은 고치지 않으므로 색인 도구는 실행마다 경고하지 않습니다.
        from _위치 import Grammar
        p = Grammar(cfg).parse(m.group(1).strip())
        if p.empty or (not p.files and p.orphans):
            print('  ! 대상을 해석할 수 없습니다 — 루트 기준 경로를 백틱에, 절은 경로 바로 뒤에 적으십시오: %r'
                  % m.group(1).strip()[:80])
        elif p.unresolved:
            print('  · 확인하지 못한 이름(쓴 그대로 색인됨): ' + ' · '.join(p.unresolved))

    rec_dir = os.path.join(cfg.root, cfg.records_dir)
    if not os.path.isdir(rec_dir):
        os.makedirs(rec_dir)
    pat = re.compile(r'^%s(\d+)\.md$' % re.escape(prefix))
    nums = [int(m.group(1)) for f in os.listdir(rec_dir) for m in [pat.match(f)] if m]
    n = (max(nums) if nums else 0) + 1
    seen_max = sync.max_record_seen()
    if n <= seen_max:
        # 폴더의 최대 번호가 이 컴퓨터가 전에 본 것보다 작으면 미러가 따라잡지 못한 상태 — 여기서 번호를 집으면 다른 컴퓨터의 기록과 겹칩니다.
        print('번호를 배정하지 않습니다 — 이 컴퓨터는 %s%d 까지 봤는데 폴더의 최대는 %s%d 입니다. 최신 기록이 아직 내려오지 않았을 수 있으니 '
              '동기화가 끝난 뒤 다시 돌리십시오(사용자가 확인했으면 `도구/동기화_점검.py --ack "<문구>"`).' % (prefix, seen_max, prefix, n - 1))
        return 2

    for _ in range(MAX_TRIES):
        path = os.path.join(rec_dir, '%s%d.md' % (prefix, n))
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            n += 1
            continue
        with io.open(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(holder.sub('%s%d' % (prefix, n), body))
        rel = os.path.relpath(path, cfg.root).replace(os.sep, '/')
        sync.after_write(rel)
        sync.remember_records()
        print('%s%d\t%s' % (prefix, n, rel), flush=True)
        if rebuild:
            _rebuild_index(cfg.root)      # 실패해도 기록은 이미 만들어졌으므로 0 — 안내만 냅니다
        return 0

    print('번호를 확보하지 못했습니다 (%d번 시도)' % MAX_TRIES)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
