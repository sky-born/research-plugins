# -*- coding: utf-8 -*-
r"""update_tools.py — 기존 원고 프로젝트의 관리 파일(도구 · 위치 문법 · 훅)을 정본과 맞춥니다.

원본은 **이 파일이 든 플러그인 사본**입니다 — 배포 전에는 작업 클론의 것을, 배포 뒤에는 설치본의 것을 돌립니다.
관리 대상은 `managed_files.json`, 정본 이력의 해시는 `tool_hashes.json`(둘 다 이 폴더)입니다.

사용법  (`<py>` 는 이 컴퓨터의 Python 3 — 윈도 `python` · 맥 `python3`)
    <py> -X utf8 update_tools.py <프로젝트>                       판정만 (기본, = --check)
    <py> -X utf8 update_tools.py <프로젝트> --apply               같지 않은 정본 판을 바꿈
    <py> -X utf8 update_tools.py <프로젝트> --apply --force tools/index_records.py   로컬 수정판도 바꿈(백업 뒤)
    <py> -X utf8 update_tools.py <프로젝트> --apply --add tools/_location.py         없는 파일을 새로 넣음
    <py> -X utf8 update_tools.py --scan <폴더> [--depth N]        아래 프로젝트들의 상태표

판정 — 파일마다 다음 가운데 하나. 해시는 줄끝을 LF 로 정규화한 내용으로 냅니다(맥 · 동기화 사본의 줄끝 차이를
로컬 수정으로 잘못 보지 않기 위한 방어).
    같음            정본과 같음 (줄끝만 다르면 「같음 · 줄끝 다름」 — --apply 가 정본 바이트로 맞춤)
    옛 정본 판 vX   정본 이력에 있는 판 (--apply 가 바꿈)
    로컬 수정       정본 이력에 없음 (--force <dst> 로만, 바꾸기 전 .manuscript/tools_backup/<날짜>/ 에 원본)
    없음            프로젝트에 없음 (--add <dst> 로만 — 도구 세트를 안 쓰는 프로젝트에 새로 깔지 않음)
    옛 이름         0.12 이하의 이름(`managed_files.json` 의 old)으로만 있음 — 정본 판이면 --apply 가 새 이름으로 옮기고,
                    로컬 수정이면 --force <dst> 로만(백업 뒤)

dst 의 `{tools_dir}` 는 그 프로젝트 설정의 도구 폴더입니다. 설정 없이 옛 기본 이름(한글)을 쓰는 프로젝트는 설정에 적을 값을
보이고 --apply 를 거부합니다 — 설정 파일은 이 도구가 쓰지 않습니다(세션이 사용자에게 보인 뒤 Edit 으로 적습니다).
함께 보고만 하는 것 — 기본값에 기대는 설정 키 · 훅 등록(.claude/settings.json)이 예시와 같은지.
종료 코드 — 0 모두 같음 · 1 다른 파일이 있음(또는 --apply 뒤에도 남음) · 2 인자 · 입력 오류 · 옛 이름 설정 없음
"""
import argparse, datetime, hashlib, io, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools'))
import _config                                      # noqa: E402  — 이 플러그인 사본의 로더


def _콘솔_UTF8():
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


def norm_hash(data):
    """줄끝을 LF 로 정규화한 sha256 — tool_hashes.json 과 같은 정의."""
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def load_manifest():
    m = json.load(io.open(os.path.join(HERE, 'managed_files.json'), encoding='utf-8'))
    p = os.path.join(HERE, 'tool_hashes.json')
    hist = json.load(io.open(p, encoding='utf-8')) if os.path.isfile(p) else {'files': {}}
    return m, hist


def plugin_version():
    p = os.path.join(os.path.dirname(os.path.dirname(HERE)), '.claude-plugin', 'plugin.json')
    try:
        return json.load(io.open(p, encoding='utf-8')).get('version', '?')
    except (OSError, ValueError):
        return '?'


# ---------------------------------------------------------------- 판정
def project_names(project):
    """(도구 폴더, 설정에 적을 옛 이름 {…} 또는 {}) — 옛 이름을 설정에 적지 않은 프로젝트는 옛 도구 폴더로 판정합니다."""
    cfg = _config.load(project, strict=False)
    pins = _config.legacy_pins(project, cfg.raw_file)
    return pins.get('tools_dir') or cfg.tools_dir, pins


def _verdict(sb, db, known):
    """(판정, 설명) — 같음 · 같음 · 줄끝 다름 · 옛 정본 판 · 로컬 수정."""
    if norm_hash(sb) == norm_hash(db):
        return ('같음' if sb == db else '같음 · 줄끝 다름'), ''
    if norm_hash(db) in known:
        return '옛 정본 판', 'v' + ' · v'.join(known[norm_hash(db)])
    return '로컬 수정', '정본 이력에 없는 내용'


def classify(project, manifest, hist):
    """[(dst, 판정, 설명, src경로, dst경로, 옛 이름 사본)] — 판정은 '같음' '같음 · 줄끝 다름' '옛 정본 판' '로컬 수정' '없음' '옛 이름'.
    옛 이름 사본은 None 또는 (경로, 로컬 수정인가). 옛 이름의 설명은 그 사본의 판정입니다."""
    tools_dir = project_names(project)[0]
    out = []
    for item in manifest['files']:
        rel = item['dst'].replace('{tools_dir}', tools_dir)
        src = os.path.join(HERE, *item['src'].split('/'))
        dst = os.path.join(project, *rel.split('/'))
        path = os.path.join(os.path.dirname(dst), item['old']) if item.get('old') else None
        if not os.path.isfile(src):
            out.append((rel, '정본 없음', item['src'], src, dst, None)); continue
        sb, known = io.open(src, 'rb').read(), hist['files'].get(item['src'], {})
        old_v, old_note = _verdict(sb, io.open(path, 'rb').read(), known) if path and os.path.isfile(path) else (None, '')
        old = (path, old_v == '로컬 수정') if old_v else None
        if os.path.isfile(dst):
            v, note = _verdict(sb, io.open(dst, 'rb').read(), known)
            out.append((rel, v, note, src, dst, old))
        elif old:
            out.append((rel, '옛 이름', '%s — %s%s' % (item['old'], old_v, (' ' + old_note) if old_v == '옛 정본 판' else ''),
                        src, dst, old))
        else:
            out.append((rel, '없음', '', src, dst, None))
    return out


def config_report(project):
    """기본값에 기대는 설정 키 — 설정 파일에 없어 도구가 `_config.DEFAULTS` 를 쓰는 키."""
    raw, path = {}, None
    for rel in (_config.CONFIG_REL, _config.CONFIG_REL_OLD):
        p = os.path.join(project, rel)
        if os.path.isfile(p):
            path = p
            try:
                raw = json.load(io.open(p, encoding='utf-8'))
            except ValueError as e:
                return None, ['설정 파일을 읽지 못했습니다: %s' % e]
            break
    if path is None:
        return None, ['설정 파일이 없습니다 — 모든 값이 기본값입니다']
    missing = []
    if 'kind' not in raw:
        missing.append('kind')
    for sec, keys in _config.DEFAULTS.items():
        if not isinstance(keys, dict):
            if sec not in raw:
                missing.append(sec)
            continue
        if sec == 'sync':
            # 동기화 설정은 기본값으로 도는 것이 정상입니다 — 키마다 늘어놓지 않고 한 줄로만
            n = sum(1 for k in keys if k not in (raw.get(sec) or {}))
            if n:
                missing.append('sync(기본값으로 도는 키 %d개%s)' % (n, '' if 'sync' in raw else ' — 절 없음'))
            continue
        for k in keys:
            if k not in (raw.get(sec) or {}):
                missing.append('%s.%s' % (sec, k))
    return os.path.relpath(path, project), missing


def sync_gate(project, apply_, override):
    """S10 — 적용 직전 동기화 점검(S1 신선도 · S2 E 연속 · S5 충돌 사본). 낡은 미러에 정본을 덮어 쓰는 것이 이번 사고의 첫 쓰기였습니다.
    ERROR(S2)가 있으면 적용을 거부합니다(--sync-override 로만 통과). WARN(S1 · S5)은 보이고 진행합니다 — 갱신 전후의 드라이브 스냅샷과
    해시 대조(옛 정본 판만 바꿈)가 안전망입니다. 판정만 할 때는 보이기만 합니다."""
    try:
        import _sync                              # 이 플러그인 사본(설치본)의 점검 — 프로젝트 사본이 낡아도 최신 코드
    except ImportError as e:
        print('  동기화  점검 모듈을 불러오지 못했습니다(%s) — 건너뜁니다' % e)
        return True
    try:
        findings = _sync.Sync(_config.load(project)).check('tools')
    except Exception as e:                            # 점검의 결함이 갱신을 막지 않게 — 알리고 통과
        print('  동기화  점검 중 오류(%r) — 건너뜁니다' % (e,))
        return True
    bad = [f for f in findings if f.level in ('ERROR', 'WARN')]
    if not bad:
        print('  동기화  이상 없음 (S1 신선도 · S2 E 연속 · S5 충돌 사본)')
        return True
    for f in bad:
        print('  동기화  ! ' + f.line())
    if apply_ and not override and any(f.level == 'ERROR' for f in bad):
        print('  → 미러가 옛 판으로 되돌아간 증거(ERROR)가 있어 적용을 거부합니다. 드라이브가 최신인지 확인한 뒤 다시 돌리거나, '
              '사용자 확인을 받았으면 --sync-override 를 붙이십시오.')
        return False
    if apply_ and any(f.level == 'WARN' for f in bad):
        print('  → WARN 만이라 진행합니다(갱신 전후 스냅샷 · 해시 대조가 안전망).')
    return True


def hook_report(project, manifest):
    ex = os.path.join(HERE, *manifest.get('settings_example', 'hooks/settings.example.json').split('/'))
    tg = os.path.join(project, *manifest.get('settings_target', '.claude/settings.json').split('/'))
    if not os.path.isfile(tg):
        return '없음'
    try:
        want = json.load(io.open(ex, encoding='utf-8')).get('hooks')
        have = json.load(io.open(tg, encoding='utf-8')).get('hooks')
    except (OSError, ValueError) as e:
        return '읽지 못함 (%s)' % e
    if have is None:
        return '등록 없음 — settings.example.json 의 hooks 블록을 합쳐 넣으십시오'
    return '같음' if have == want else '다름 — 예시와 대조해 손으로 맞추십시오'


def print_report(project, rows, cfg, hook):
    print('프로젝트  %s' % project)
    print('정본      %s (research-writing %s)' % (HERE, plugin_version()))
    w = max(len(r[0]) for r in rows) if rows else 10
    for dst, verdict, note, _s, _d, old in rows:
        if old and verdict != '옛 이름':
            note = (note + ' · ' if note else '') + '옛 이름 사본도 있음(%s%s)' % (os.path.basename(old[0]), ' · 로컬 수정' if old[1] else '')
        print('  %-*s  %s%s' % (w, dst, verdict, ('  ' + note) if note else ''))
    path, missing = cfg
    if path is None:
        print('  설정      ' + missing[0])
    elif missing:
        print('  설정      %s — 기본값에 기대는 키 %d개: %s' % (path, len(missing), ', '.join(missing)))
        print('            (설정 파일은 이 도구가 쓰지 않습니다. 필요한 값은 사용자에게 보인 뒤 Edit 으로 적으십시오)')
    else:
        print('  설정      %s — 기본값에 기대는 키 없음' % path)
    print('  훅 등록   ' + hook)


# ---------------------------------------------------------------- 적용
def backup(project, rel, path):
    day = datetime.date.today().isoformat()
    folder = os.path.join(project, _config.TOOLS_BACKUP, day)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    base = os.path.basename(rel)
    for i in range(1, 100):
        cand = os.path.join(folder, base if i == 1 else '%s.%d' % (base, i))
        try:
            fd = os.open(cand, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        with os.fdopen(fd, 'wb') as f:
            f.write(io.open(path, 'rb').read())
        return cand
    raise SystemExit('백업 이름을 잡지 못했습니다: %s' % folder)


def apply(project, rows, force, add):
    """옛 이름 사본은 새 이름을 정본으로 쓴 뒤 지웁니다 — 정본 판이 아닌(로컬 수정) 옛 사본은 백업한 뒤에만."""
    changed, left = [], []
    for dst, verdict, note, src, dpath, old in rows:
        old_path, old_local = old if old else (None, False)
        if verdict == '정본 없음':
            continue
        if verdict == '없음' and dst not in add:
            left.append((dst, verdict, '--add 로만 넣습니다')); continue
        if (verdict == '로컬 수정' or old_local) and dst not in force:
            why = '옛 이름 사본이 로컬 수정이라 ' if old_local and verdict != '로컬 수정' else ''
            left.append((dst, verdict, why + '--force 로만 바꿉니다')); continue
        if verdict == '로컬 수정':
            print('  백업      %s → %s' % (dst, os.path.relpath(backup(project, dst, dpath), project)))
        if old_local:
            print('  백업      %s → %s' % (os.path.relpath(old_path, project), os.path.relpath(backup(project, old_path, old_path), project)))
        if verdict != '같음':
            d = os.path.dirname(dpath)
            if not os.path.isdir(d):
                os.makedirs(d)
            shutil.copyfile(src, dpath)
            if norm_hash(io.open(dpath, 'rb').read()) != norm_hash(io.open(src, 'rb').read()):
                raise SystemExit('쓴 뒤 해시가 다릅니다: %s' % dst)
            changed.append((dst, verdict))
        if old_path:
            os.remove(old_path)
            changed.append((os.path.relpath(old_path, project).replace(os.sep, '/'), '옛 이름 사본 지움'))
    for dst, verdict in changed:
        print('  바꿈      %-30s (%s)' % (dst, verdict if verdict.endswith('지움') else verdict + ' → 정본'))
    for dst, verdict, why in left:
        print('  남김      %-30s %s — %s' % (dst, verdict, why))
    return left


# ---------------------------------------------------------------- 훑기
SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '보관', 'archive', '.manuscript', '.claude'}


def find_projects(folder, depth):
    folder = os.path.abspath(folder)
    out = []
    for root, dirs, files in os.walk(folder):
        rel = os.path.relpath(root, folder)
        level = 0 if rel == '.' else rel.count(os.sep) + 1
        if os.path.isfile(os.path.join(root, '.manuscript', 'project.json')) \
                or os.path.isfile(os.path.join(root, '.writing', 'project.json')) \
                or os.path.isfile(os.path.join(root, '.claude', 'hooks', 'guard_write.py')):
            out.append(root)
        if level >= depth:
            dirs[:] = []
        else:
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
    return out


def scan(folder, depth, manifest, hist):
    projects = find_projects(folder, depth)
    if not projects:
        print('프로젝트를 찾지 못했습니다: %s (깊이 %d)' % (folder, depth)); return 1
    rc = 0
    for p in projects:
        rows = classify(p, manifest, hist)
        tools_dir, pins = project_names(p)
        tool_dsts = {item['dst'].replace('{tools_dir}', tools_dir) for item in manifest['files'] if item['src'].startswith('tools/')}
        counts = {}
        for _d, v, *_ in rows:
            counts[v.split(' ')[0]] = counts.get(v.split(' ')[0], 0) + 1
        summary = ' · '.join('%s %d' % (k, v) for k, v in counts.items())
        name = os.path.relpath(p, folder) or '.'
        # 도구 세트를 안 쓰는 프로젝트(훅만 등록)의 「없음」은 차이가 아닙니다 — 새로 깔지 않습니다.
        if not any(v != '없음' for d, v, *_ in rows if d in tool_dsts):
            print('%s\n    도구 세트 없음 — 훅만 (파일 %s) | 훅 등록 %s' % (name, summary, hook_report(p, manifest)))
            continue
        print('%s\n    파일 %s | 훅 등록 %s%s' % (name, summary, hook_report(p, manifest),
                                              ' | 옛 이름 설정 없음 — 적용 전에 설정에 적어야 합니다' if pins else ''))
        if pins or any(v != '같음' for _d, v, *_ in rows):
            rc = 1
    return rc


# ---------------------------------------------------------------- 진입
def main(argv=None):
    _콘솔_UTF8()
    ap = argparse.ArgumentParser(description='기존 프로젝트의 관리 파일을 정본과 맞춥니다.')
    ap.add_argument('project', nargs='?', help='프로젝트 루트 (없으면 --scan)')
    ap.add_argument('--check', action='store_true', help='판정만 (기본)')
    ap.add_argument('--apply', action='store_true', help='같지 않은 정본 판을 바꿉니다')
    ap.add_argument('--force', action='append', default=[], metavar='DST', help='로컬 수정판도 바꿉니다 (백업 뒤)')
    ap.add_argument('--add', action='append', default=[], metavar='DST', help='없는 파일을 새로 넣습니다')
    ap.add_argument('--scan', metavar='FOLDER', help='아래 프로젝트들의 상태표')
    ap.add_argument('--depth', type=int, default=3)
    ap.add_argument('--sync-override', action='store_true', help='동기화 점검(S10)에 ERROR 가 있어도 적용합니다 — 사용자 확인 뒤에만')
    a = ap.parse_args(argv)
    manifest, hist = load_manifest()
    if a.scan:
        return scan(a.scan, a.depth, manifest, hist)
    if not a.project:
        ap.print_usage(); return 2
    project = os.path.abspath(a.project)
    if not os.path.isdir(project):
        print('프로젝트 폴더가 없습니다: %s' % project); return 2
    rows = classify(project, manifest, hist)
    force = [x.replace('\\', '/') for x in a.force]
    add = [x.replace('\\', '/') for x in a.add]
    print_report(project, rows, config_report(project), hook_report(project, manifest))
    pins = project_names(project)[1]
    if pins:
        print('  옛 이름   ' + _config.legacy_message(pins).replace('\n', '\n            '))
        if a.apply:
            print('적용하지 않았습니다 — 위 값을 설정에 적은 뒤 다시 돌리십시오.')
        return 2
    ok = sync_gate(project, a.apply, a.sync_override)
    if not a.apply:
        return 0 if all(v == '같음' and not old for _d, v, _n, _s, _p, old in rows) else 1
    if not ok:
        return 1
    print('적용')
    apply(project, rows, force, add)
    rows2 = classify(project, manifest, hist)
    bad = [(d, v) for d, v, _n, _s, _p, old in rows2 if v != '같음' or old]
    print('적용 뒤   ' + ('모두 같음' if not bad else '남은 차이 — ' + ', '.join('%s(%s)' % x for x in bad)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
