# -*- coding: utf-8 -*-
r"""check_sync.py — 공용 파일 동기화 점검 · 스냅샷 · 복구 · 확인. 본체는 `_sync.py`(같은 폴더).

사용법  (`<py>` 는 이 컴퓨터의 Python 3 — 윈도 `python` · 맥 `python3`)
    <py> -X utf8 tools/check_sync.py                       세션 시작 — 점검 전부 · 경계 스냅샷(로컬 + 드라이브) · 상태 한 줄
    <py> -X utf8 tools/check_sync.py --quick               점검만(스냅샷 없음)
    <py> -X utf8 tools/check_sync.py --end                 세션 끝 — 경계 스냅샷 · 보존 정리 (정리 도구 --apply 가 자동으로 부름)
    <py> -X utf8 tools/check_sync.py --ack "<사용자 문구>"  열린 ERROR 를 사용자 확인으로 닫음 — 사용자에게 보이고 확인을 받은 뒤에만
    <py> -X utf8 tools/check_sync.py --accept-warn         WARN 만 있을 때 기준(쓴 줄 등록 · 본 기록 · ID)을 지금 상태에 맞춤 — 문구 불필요 ·
                                                           열린 ERROR 가 있으면 거부(2)
    <py> -X utf8 tools/check_sync.py --damage              손실 보고 전체 — 이 컴퓨터가 쓴 줄 가운데 사라진 것
    <py> -X utf8 tools/check_sync.py --restore <파일> [--at "YYYY-MM-DD HH:MM" | --hash <8자리>]
                                                           스냅샷으로 되돌림(되돌리기 전 현재 판도 남김)
    <py> -X utf8 tools/check_sync.py --snapshots <파일>    그 파일의 스냅샷 목록
    <py> -X utf8 tools/check_sync.py --guard <파일> [--tool Edit]   쓰기 직전 판정(훅 · 도구가 부름) — 막으면 사유를 내고 2
    <py> -X utf8 tools/check_sync.py --after-write <파일>  쓰기 직후 처리(훅 · 도구가 부름)
    <py> -X utf8 tools/check_sync.py --after-bash          Bash 뒤 — 지문이 바뀐 공용 파일만 처리

종료 코드 — 0 OK · 1 WARN 또는 확인된 ERROR(ack_hours 안 — 쓰기를 막지 않음) · 2 확인되지 않은 ERROR(또는 --guard 가 막음) · 3 인자 · 설정 오류
ERROR 가 있으면 공용 파일을 쓰기 전에 사용자에게 보이고 확인을 받습니다(`--ack`). WARN 만 있으면 동기화된 것으로 봅니다 — 상태 한 줄로
보고하고 `--accept-warn` 으로 기준을 맞춘 뒤 진행합니다. 「할 일」(생성물이 원본보다 낡음 — S4 순방향)은 재생성만 하면 되는 평소 상태라
동기화 경고가 아니고 종료 코드도 0 입니다. 규약은 플러그인 `tracker-workflow.md` 「동기화」.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import load as _load_cfg, _콘솔_UTF8  # noqa: E402
from _sync import Sync, find_project_root, parse_utc  # noqa: E402


def _rc(findings, sync=None):
    """2 — 확인되지 않은 ERROR · 1 — 확인된 ERROR(ack_hours 안) 또는 WARN · 0. 확인 판정은 Sync.ack_of 한 곳."""
    errs = [f for f in findings if f.level == 'ERROR']
    if any(sync is None or sync.ack_of(f.key) is None for f in errs):
        return 2
    return 1 if errs or any(f.level == 'WARN' for f in findings) else 0


def _print(findings, show_info=False, sync=None):
    for f in findings:
        if f.level == 'INFO' and not show_info:
            continue
        ack = sync.ack_of(f.key) if (sync is not None and f.level == 'ERROR') else None
        note = ''
        if ack:
            try:
                when = parse_utc(ack['utc']).astimezone().strftime('%m-%d %H:%M')
            except (KeyError, ValueError):
                when = '?'
            note = '  [확인됨 %s — %s]' % (when, str(ack.get('text', ''))[:40])
        print(('  ! ' if f.level != 'INFO' else '  · ') + f.line() + note)


def main(argv=None):
    _콘솔_UTF8()
    ap = argparse.ArgumentParser(description='공용 파일 동기화 점검 · 스냅샷 · 복구')
    ap.add_argument('--dir', help='프로젝트 루트(없으면 이 파일의 위치 또는 현재 폴더에서 찾음)')
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--end', action='store_true')
    ap.add_argument('--ack', metavar='문구')
    ap.add_argument('--accept-warn', action='store_true')
    ap.add_argument('--damage', action='store_true')
    ap.add_argument('--restore', metavar='파일')
    ap.add_argument('--at', metavar='시각')
    ap.add_argument('--hash', metavar='해시8')
    ap.add_argument('--snapshots', metavar='파일')
    ap.add_argument('--guard', metavar='파일')
    ap.add_argument('--tool', default='도구')
    ap.add_argument('--after-write', metavar='파일')
    ap.add_argument('--after-bash', action='store_true')
    ap.add_argument('--verbose', '-v', action='store_true')
    a = ap.parse_args(argv)

    root = a.dir
    if not root:
        here = os.path.dirname(os.path.abspath(__file__))
        root = find_project_root(here) or find_project_root(os.getcwd())
    if not root:
        print('프로젝트 설정(.manuscript/project.json)을 찾지 못했습니다 — --dir 로 루트를 주십시오', file=sys.stderr)
        return 3
    try:
        sync = Sync(_load_cfg(root))
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 3

    if a.guard:
        reason = sync.guard(a.tool, a.guard.replace('\\', '/'))
        if reason:
            print(reason)
            return 2
        return 0
    if a.after_write:
        sync.after_write(a.after_write.replace('\\', '/'))
        return 0
    if a.after_bash:
        ch = sync.after_bash()
        if a.verbose and ch:
            print('지문이 바뀐 공용 파일: ' + ' · '.join(ch))
        return 0
    if a.ack is not None:
        if not a.ack.strip():
            print('--ack 에는 사용자가 확인한 문구를 그대로 적습니다', file=sys.stderr)
            return 3
        n = sync.ack(a.ack.strip())
        print('확인 기록 — ERROR %d건 닫음 · 사라진 ID · 줄은 정당한 삭제로 받아들였습니다 (%s)' % (n, sync.me))
        return 0
    if a.accept_warn:
        if sync.accept_warn() is None:
            print('WARN 수용 거부 — 확인되지 않은 ERROR 가 있습니다. 사용자에게 보이고 확인을 받은 뒤 `--ack "<문구>"` 로 닫으십시오.')
            _print(sync.unacked(), sync=sync)
            return 2
        print('WARN 수용 — 기준(쓴 줄 등록 · 본 기록 · ID)을 지금 상태에 맞췄습니다 (%s). ERROR 는 건드리지 않았습니다' % sync.me)
        return 0
    if a.snapshots:
        snaps = sync.snapshots_of(a.snapshots)
        if not snaps:
            print('스냅샷 없음: %s' % a.snapshots)
            return 1
        for s in snaps:
            where = '로컬' if s[5].startswith(sync.local_snap_dir) else '드라이브'
            print('  %s  %-16s %s  %s  %s' % (s[0], s[1], s[3], where, os.path.getsize(s[5])))
        return 0
    if a.restore:
        pick = sync.restore(a.restore, at=a.at, digest=a.hash)
        print('되돌림: %s ← %s (%s · %s)' % (a.restore, os.path.basename(pick[5]), pick[1], pick[0]))
        return 0
    if a.damage:
        findings = sync.s6(verbose=True)
        if not findings:
            print('손실 없음 — 이 컴퓨터가 쓴 줄은 모두 남아 있습니다')
            return 0
        for f in findings:
            print('! ' + f.msg)
            for pv in f.items:
                print('    - ' + pv)
        return 1
    if a.end:
        findings, removed = sync.session_end()
        print('세션 끝 — 드라이브 스냅샷 갱신 · 보존 정리 %d개 삭제%s' % (removed, '' if not findings else ' · ERROR 남음'))
        _print(findings, sync=sync)
        return _rc(findings, sync)

    findings = sync.session_start(snapshot=not a.quick)
    print(sync.status_line(findings))
    _print(findings, show_info=a.verbose, sync=sync)
    if not a.verbose:                     # S4 순방향 — 동기화 경고가 아니라 할 일. INFO 지만 늘 보입니다
        for f in findings:
            if f.level == 'INFO' and f.key.endswith(':stale'):
                print('  · 할 일  ' + f.msg)
    rc = _rc(findings, sync)
    if rc == 2:
        print('  → 공용 파일을 쓰기 전에 사용자에게 보이고 확인을 받으십시오. 확인 뒤 `--ack "<문구>"`. 덮인 파일은 `--restore <파일>`.')
    elif rc == 1:
        print('  → WARN 은 상태 한 줄로 보고하고 진행합니다(묻지 않음). 기준을 지금 상태에 맞추려면 `--accept-warn`(열린 ERROR 가 있으면 거부).')
        if any(f.level == 'ERROR' for f in findings):
            print('    확인된 ERROR 는 `ack_hours` 동안 쓰기를 막지 않습니다 — 조건이 바뀌면(다른 번호 · ID) 다시 막습니다.')
    return rc


if __name__ == '__main__':
    sys.exit(main())
