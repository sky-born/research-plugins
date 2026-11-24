# -*- coding: utf-8 -*-
r"""guard_write.py — Claude Code 훅 본체(PreToolUse · PostToolUse). 원고 프로젝트의 공용 파일을 지킵니다.

    guard_write.py pre     Edit · Write · Bash · PowerShell 직전 — ① 이미 있는 완료기록 `E*.md` 와 생성 색인을 Write 로 덮어쓰면 거부
                                                    ② 동기화 점검(_동기화.py)에 확인되지 않은 ERROR 가 있으면 공용 파일 쓰기를 거부
                                                    ③ Edit · Write 직전 판을 로컬 스냅샷으로 남김(뒤의 차이 계산용)
                                                    ⑤ 새 미결 ID 행을 손으로 넣는 Edit · Write 를 거부 — 번호는 `도구/미결_새항목.py` 가 정함
                                                       (그 도구가 프로젝트에 있을 때만 · 범위는 `_config.allocation_scope`)
                                                    ⑥ 공용 파일 Edit · Write 직전, 도구가 쓰기 잠금을 쥐고 있으면 풀릴 때까지 잠깐 기다림
                                                       (막지 않음 — 훅은 Edit 보다 먼저 끝나므로 잠금을 쥐지는 못합니다)
    guard_write.py post    같은 도구 직후 — 공용 파일이면 스냅샷 · 지문 · 「이 컴퓨터가 쓴 줄」 기록(셸 도구는 지문이 바뀐 파일만)
                                        ④ 추적 파일의 표 행이 깨져 있으면(쪼개진 행 등) 그 턴에 모델 · 사용자에게 알림(막지 않음)
    (인자가 없으면 pre — 옛 등록과 호환)

어디서 도는가 — 둘 다 같은 파일입니다.
  · 플러그인 설치본 `hooks/hooks.json` 이 `${CLAUDE_PLUGIN_ROOT}/skills/new-manuscript/hooks/guard_write.py` 로 등록(본체) —
    낡은 미러의 프로젝트 사본과 무관하게 설치본의 최신 코드가 돕니다.
  · 프로젝트 `.claude/settings.json` 이 `.claude/hooks/guard_write.py`(관리 사본)로 등록(보조) — 플러그인 훅이 없는 환경용.
  둘 다 있으면 같은 도구 호출을 한 번만 처리합니다(상태 폴더의 `hook_seen/<tool_use_id>` 표시).
프로젝트 판정 — Edit · Write 는 **대상 파일 경로에서**, Bash · PowerShell 은 cwd 에서 위로 올라가며 `.manuscript/project.json`(또는 `.writing/`)을
찾습니다. 없으면 즉시 0 으로 끝나 다른 프로젝트에 영향이 없습니다. 점검 모듈은 이 파일 옆 `../tools/_동기화.py`(플러그인 배치) →
프로젝트 `도구/_동기화.py` 순으로 찾습니다.

입출력 — 표준 입력의 JSON(tool_name, tool_input, cwd, tool_use_id)을 읽고, 막을 때만 표준 출력에
  {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}
를, 쓰기 뒤 표 결함을 알릴 때만 {"systemMessage": …, "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": …}} 를
씁니다. 종료 코드는 항상 0 이고, 스크립트 자체의 오류는 stderr 에 적고 1 로 끝냅니다(비차단 — fail-open).
**2 로 끝나지 않습니다** — 2 는 훅 규약에서 차단이라, 스크립트 결함이 모든 쓰기를 막는 일을 피합니다.
표준 입력은 바이트로 읽어 UTF-8 로 해독합니다 — 윈도 파이썬이 cp949 로 읽으면 한글 경로가 깨져 검사가 빗나갑니다(2026-09-14 실측).
"""
import hashlib
import importlib.util
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_RELS = (os.path.join('.manuscript', 'project.json'), os.path.join('.writing', 'project.json'))


def find_root(start):
    if not start:
        return None
    p = os.path.abspath(start)
    if os.path.isfile(p):
        p = os.path.dirname(p)
    while True:
        for rel in CONFIG_RELS:
            if os.path.isfile(os.path.join(p, rel)):
                return p
        up = os.path.dirname(p)
        if up == p:
            return None
        p = up


def _tracker(root):
    rec_dir, prefix, index = '완료기록', 'E', '수정필요_색인.md'
    for rel in CONFIG_RELS:
        p = os.path.join(root, rel)
        if not os.path.isfile(p):
            continue
        try:
            t = json.load(io.open(p, encoding='utf-8')).get('tracker', {})
            rec_dir = t.get('records_dir', rec_dir)
            prefix = t.get('record_prefix', prefix)
            index = t.get('record_index', index)
        except (OSError, ValueError) as e:
            sys.stderr.write('guard_write: %s 를 읽지 못해 기본값을 씁니다: %s\n' % (rel, e))
        break
    return rec_dir, prefix, index


def decide_overwrite(root, data):
    """완료 기록 · 생성 색인의 Write 덮어쓰기 — 막아야 하면 사유, 아니면 None."""
    if data.get('tool_name') != 'Write':
        return None
    fp = (data.get('tool_input') or {}).get('file_path') or ''
    if not fp:
        return None
    rec_dir, prefix, index = _tracker(root)
    target = os.path.abspath(fp if os.path.isabs(fp) else os.path.join(root, fp))
    try:
        rel = os.path.relpath(target, root)
    except ValueError:
        return None
    if rel.startswith('..'):
        return None
    rel = rel.replace(os.sep, '/')
    rec_pat = re.escape(rec_dir.replace(os.sep, '/').strip('/')) + '/' + re.escape(prefix) + r'\d+\.md'
    if re.fullmatch(rec_pat, rel) and os.path.exists(target):
        return ('완료 기록 %s 은 이미 있습니다. 기록은 덮어쓰지 않습니다 — 고칠 곳만 Edit 으로 바꾸고, '
                '새 항목은 도구/완료기록_새항목.py 로 다음 번호에 만듭니다 (동시 편집 규칙 — tracker-workflow.md).' % rel)
    if rel == index.replace(os.sep, '/') and os.path.exists(target):
        return ('%s 은 도구가 생성하는 파일입니다. 손으로 쓰지 말고 도구/완료기록_색인.py 로 다시 만듭니다.' % rel)
    return None


NEW_ITEM_TOOL = os.path.join('도구', '미결_새항목.py')


def decide_new_ids(root, sync, tool, ti, rel):
    """새 미결 ID 를 손으로 넣는 Edit · Write — 막아야 하면 사유, 아니면 None. 번호는 도구가 잠금 안에서 정합니다(두 세션이 같은 번호를
    집지 않게). 판정은 `Sync.hand_added_ids`(범위 · 새 ID 의 정의는 그 한 곳). 프로젝트에 번호 도구가 아직 없으면(사본을 갱신하지 않은
    프로젝트) 막지 않습니다 — 막으면 넣을 길이 없습니다. 옛 `_동기화.py` 도 통과시킵니다."""
    find = getattr(sync, 'hand_added_ids', None)
    if find is None or not os.path.isfile(os.path.join(root, NEW_ITEM_TOOL)):
        return None
    if tool == 'Write':
        text = ti.get('content') or ''
    elif tool == 'MultiEdit':
        text = '\n'.join((e or {}).get('new_string') or '' for e in (ti.get('edits') or []))
    else:
        text = ti.get('new_string') or ''
    new = find(rel, text)
    if not new:
        return None
    letter = re.match(r'[A-Z]+', new[0]).group(0)
    return ('새 미결 항목 %s 을(를) 손으로 넣으려 했습니다. 번호는 도구가 정합니다 — 두 세션이 같은 번호를 집지 않게 하기 위해서입니다. '
            '행의 ID 자리를 `%s?` 로 바꿔 한 줄짜리 파일로 적고 `<py> -X utf8 %s <그 파일>` 을 돌린 뒤, 출력된 번호를 받아 쓰십시오 '
            '(tracker-workflow.md 「동시 편집」).' % (' · '.join(new), letter, NEW_ITEM_TOOL.replace(os.sep, '/')))


def _load_sync(root):
    """(_config, _동기화) 모듈 — 플러그인 배치(`../tools`)를 먼저, 없으면 프로젝트 사본(`도구/`)."""
    for tools in (os.path.join(os.path.dirname(HERE), 'tools'), os.path.join(root, '도구')):
        if os.path.isfile(os.path.join(tools, '_동기화.py')) and os.path.isfile(os.path.join(tools, '_config.py')):
            if tools not in sys.path:
                sys.path.insert(0, tools)
            mods = []
            for name in ('_config', '_동기화'):
                spec = importlib.util.spec_from_file_location(name, os.path.join(tools, name + '.py'))
                m = importlib.util.module_from_spec(spec)
                sys.modules[name] = m
                spec.loader.exec_module(m)
                mods.append(m)
            return mods[0], mods[1]
    return None, None


def deny(reason):
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                         "permissionDecision": "deny",
                                                         "permissionDecisionReason": reason}}, ensure_ascii=True))


def notice_tables(sync, rels):
    """쓰기 뒤 — 추적 파일에 표 결함(쪼개진 행 등)이 남아 있으면 그 턴에 알립니다(막지 않음). 모델에게는 additionalContext,
    사용자에게는 systemMessage. 옛 `_동기화.py`(table_report 없음)나 검사 결함은 조용히 건너뜁니다 — fail-open."""
    try:
        probs = sync.table_report(rels)
    except Exception as e:
        sys.stderr.write('guard_write: 표 검사 중 오류, 건너뜁니다: %r\n' % (e,))
        return
    if not probs:
        return
    msg = ('추적 파일의 표 행이 깨져 있습니다 — 한 항목은 한 줄이고 셀 안의 | 는 \\| 입니다(tracker-workflow.md 「표 행 형식」). '
           '이번 쓰기가 원인이면 바로 고치십시오: ' + ' / '.join('%s %s' % (r, d) for r, d in probs[:6]))
    sys.stdout.write(json.dumps({"systemMessage": msg,
                                 "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}},
                                ensure_ascii=True))


def run(mode, data):
    tool = data.get('tool_name')
    ti = data.get('tool_input') or {}
    if tool in ('Edit', 'Write', 'MultiEdit'):
        fp = ti.get('file_path') or ''
        root = find_root(fp if os.path.isabs(fp) else os.path.join(data.get('cwd') or os.getcwd(), fp)) \
            or find_root(data.get('cwd') or os.getcwd())
    elif tool in ('Bash', 'PowerShell'):
        root = find_root(data.get('cwd') or os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd())
    else:
        return 0
    if root is None:
        return 0

    if mode == 'pre':
        reason = decide_overwrite(root, data)
        if reason:
            deny(reason)
            return 0

    cfg_mod, sync_mod = _load_sync(root)
    if sync_mod is None:
        return 0
    cfg = cfg_mod.load(root)
    sync = sync_mod.Sync(cfg)
    marker = '%s_%s' % (mode, data.get('tool_use_id') or hashlib.sha1(json.dumps(ti, sort_keys=True).encode('utf-8')).hexdigest()[:16])
    if sync.hook_seen(marker):
        return 0

    if tool in ('Edit', 'Write', 'MultiEdit'):
        fp = ti.get('file_path') or ''
        target = os.path.abspath(fp if os.path.isabs(fp) else os.path.join(root, fp))
        nfc = getattr(cfg_mod, 'nfc', None) or (lambda s: s)     # 경로 비교는 NFC — 입력(NFC)과 파일 시스템(맥 NFD)의 형이 달라도 같은 파일
        try:
            rel = os.path.relpath(nfc(target), nfc(root)).replace(os.sep, '/')
        except ValueError:
            return 0
        if rel.startswith('..') or not sync.is_shared(rel):
            return 0
        if mode == 'pre':
            reason = sync.guard(tool, rel) or decide_new_ids(root, sync, tool, ti, rel)
            if reason:
                deny(reason)
                return 0
            wait = getattr(sync, 'wait_write_lock', None)        # 옛 `_동기화.py` 에는 없습니다
            if wait and not wait():                              # 정리 도구 등이 쓰는 중이면 풀릴 때까지 잠깐 — 못 기다려도 막지 않습니다
                sys.stderr.write('guard_write: 쓰기 잠금이 풀리지 않아 기다리지 않고 통과시킵니다\n')
            sync.before_write(rel)
        else:
            sync.after_write(rel)
            notice_tables(sync, [rel])
        return 0

    # Bash · PowerShell — 명령을 해석하지 않고, 앞에서는 공용 파일 이름이 명령에 보일 때만 가드, 뒤에서는 지문이 바뀐 파일만
    if mode == 'pre':
        open_ = sync.unacked()
        if not open_:
            return 0
        cmd = ti.get('command') or ''
        names = {os.path.basename(r) for r in sync.shared_files()} | {sync.cfg.raw.get('tracker', {}).get('records_dir', '완료기록')}
        if any(n and n in cmd for n in names):
            deny(sync.guard(tool))
        return 0
    notice_tables(sync, sync.after_bash())
    return 0


def main(argv):
    mode = (argv[1] if len(argv) > 1 else 'pre').lower()
    if mode not in ('pre', 'post'):
        sys.stderr.write('guard_write: 모드는 pre 또는 post 입니다: %r\n' % mode)
        return 1
    try:
        raw = sys.stdin.buffer.read() if hasattr(sys.stdin, 'buffer') else sys.stdin.read().encode('utf-8')
        data = json.loads(raw.decode('utf-8-sig')) if raw.strip() else {}
    except (ValueError, UnicodeDecodeError) as e:
        sys.stderr.write('guard_write: 입력 JSON 을 읽지 못했습니다: %s\n' % e)
        return 1
    try:
        return run(mode, data)
    except Exception as e:  # 결함이 쓰기 전체를 막지 않게 — 비차단 경고
        sys.stderr.write('guard_write(%s): 검사 중 오류, 통과시킵니다: %r\n' % (mode, e))
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
