#!/usr/bin/env python3
"""사용자가 해야 할 일이 생기면 이 Mac(소리 포함)과 휴대폰(ntfy)으로 알린다.

사용:
  notify.py hook                 Claude Code 훅. 이벤트 JSON을 표준 입력으로 받는다.
  notify.py codex [--chain 명령...] JSON
                                 Codex notify 프로그램. JSON은 마지막 인자다.
  notify.py send [--kind 종류] [--project 이름] [--agent 이름] [--dedupe 초] [--only mac|phone] 내용
  notify.py test [--only mac|phone]
  notify.py install | uninstall | status

종류: question(답변 필요), approval(승인 필요), action(할 일), alert(확인 필요)
설정: ~/.config/llm-plugin/notify.json
"""
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HOME = Path.home()
CONF_DIR = HOME / '.config' / 'llm-plugin'
CONF = CONF_DIR / 'notify.json'
STATE = CONF_DIR / 'notify-state.json'
CLAUDE_SETTINGS = HOME / '.claude' / 'settings.json'
CODEX_CONFIG = HOME / '.codex' / 'config.toml'
SCRIPT = Path(__file__).resolve()
PYTHON = '/usr/bin/python3'

TITLES = {
    'question': '❓ 답변이 필요합니다',
    'approval': '🔐 승인이 필요합니다',
    'action': '🔔 할 일이 있습니다',
    'alert': '⚠️ 확인이 필요합니다',
}
PHONE_TEXT = {
    'question': '{agent}가 답변을 기다립니다.',
    'approval': '{agent}가 승인을 기다립니다.',
    'action': '{agent} 세션에 할 일이 있습니다.',
}
DEFAULTS = {
    'mac': True,
    'sound': 'Glass',
    'phone': True,
    'ntfy_server': 'https://ntfy.sh',
    'ntfy_topic': '',
    'phone_detail': True,
    'phone_project': False,
}
TODO = re.compile(r'🔔\s*할\s*일\s*[:：]\s*(.+)')


def load_conf():
    conf = dict(DEFAULTS)
    try:
        conf.update(json.loads(CONF.read_text(encoding='utf-8')))
    except (OSError, ValueError):
        pass
    return conf


def save_json(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.%d.tmp' % os.getpid())
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def clean(text, limit=180):
    text = ' '.join(re.sub(r'[`*_#>]', '', str(text or '')).split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def find_todo(message):
    """응답의 마지막 세 줄에서 '🔔 할 일:' 줄을 찾는다. 코드 표기 안의 예시는 무시한다."""
    lines = [line.strip() for line in str(message or '').splitlines() if line.strip()]
    for line in reversed(lines[-3:]):
        match = TODO.search(line)
        if not match or '`' in line[:match.start()]:
            continue
        text = clean(match.group(1))
        if text and not text.startswith('<'):
            return text
    return None


def last_assistant_text(path):
    try:
        with open(path, 'rb') as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - 512 * 1024))
            chunk = handle.read().decode('utf-8', 'ignore')
    except (OSError, TypeError, ValueError):
        return ''
    for line in reversed(chunk.splitlines()):
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if not isinstance(item, dict) or item.get('type') != 'assistant' or item.get('isSidechain'):
            continue
        content = (item.get('message') or {}).get('content')
        if isinstance(content, str):
            return content
        texts = [part.get('text', '') for part in content or []
                 if isinstance(part, dict) and part.get('type') == 'text']
        if texts:
            return '\n'.join(texts)
    return ''


def from_claude(event):
    if not isinstance(event, dict) or event.get('agent_id'):
        return None
    name = event.get('hook_event_name')
    project = Path(event.get('cwd') or '').name
    if name == 'PreToolUse' and event.get('tool_name') == 'AskUserQuestion':
        questions = (event.get('tool_input') or {}).get('questions') or []
        first = questions[0] if questions and isinstance(questions[0], dict) else {}
        return 'question', first.get('question') or '질문이 있습니다.', project
    if name == 'PermissionRequest':
        return 'approval', '%s 실행 승인을 기다립니다.' % (event.get('tool_name') or '도구'), project
    if name == 'Notification':
        kind = {'permission_prompt': 'approval', 'elicitation_dialog': 'question',
                'elicitation_url_dialog': 'question'}.get(event.get('notification_type'))
        return (kind, event.get('message') or TITLES[kind], project) if kind else None
    if name == 'Stop' and not event.get('stop_hook_active'):
        message = event.get('last_assistant_message') or last_assistant_text(event.get('transcript_path'))
        todo = find_todo(message)
        return ('action', todo, project) if todo else None
    return None


def from_codex(payload):
    if not isinstance(payload, dict):
        return None
    kind = str(payload.get('type') or '')
    project = Path(payload.get('cwd') or '').name
    if kind == 'agent-turn-complete':
        todo = find_todo(payload.get('last-assistant-message'))
        return ('action', todo, project) if todo else None
    if 'approval' in kind:
        return 'approval', '승인을 기다립니다.', project
    if 'question' in kind:
        return 'question', '입력을 기다립니다.', project
    return None


def seen_recently(key, window):
    now = time.time()
    try:
        state = json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {}
    state = {k: v for k, v in state.items() if isinstance(v, (int, float)) and now - v < 7 * 86400}
    hit = key in state and now - state[key] < window
    if not hit:
        state[key] = now
        try:
            save_json(STATE, state)
        except OSError:
            pass
    return hit


def deliver(kind, text, project='', agent='Claude', only=None, conf=None):
    """알림을 보내고 보낸 경로 목록을 돌려준다. 실패해도 예외를 내지 않는다."""
    conf = conf or load_conf()
    title = TITLES.get(kind, TITLES['action'])
    text = clean(text) or title
    sent = []
    if conf.get('mac') and only in (None, 'mac'):
        subtitle = ' · '.join(part for part in (agent, project) if part)
        try:
            result = subprocess.run(
                ['osascript', '-e', 'on run argv', '-e',
                 'display notification (item 1 of argv) with title (item 2 of argv) '
                 'subtitle (item 3 of argv) sound name (item 4 of argv)', '-e', 'end run',
                 text, title, subtitle, conf.get('sound') or 'Glass'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            sent.append('mac' if result.returncode == 0 else 'mac 실패')
        except (OSError, subprocess.SubprocessError):
            sent.append('mac 실패')
    if conf.get('phone') and conf.get('ntfy_topic') and only in (None, 'phone'):
        if kind == 'alert' or conf.get('phone_detail'):
            prefix = '%s · %s: ' % (agent, project) if conf.get('phone_project') and project else ''
            message = prefix + text
        else:
            message = PHONE_TEXT.get(kind, PHONE_TEXT['action']).format(agent=agent)
        body = json.dumps({'topic': conf['ntfy_topic'], 'title': title, 'message': message,
                           'priority': 4}).encode('utf-8')
        request = urllib.request.Request(str(conf.get('ntfy_server') or DEFAULTS['ntfy_server']).rstrip('/') + '/',
                                         data=body, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                sent.append('phone' if response.status == 200 else 'phone 실패(%d)' % response.status)
        except (OSError, ValueError):
            sent.append('phone 실패')
    return sent


def spawn_send(kind, text, project, agent):
    """훅이 Claude·Codex를 기다리게 하지 않도록 전송은 별도 프로세스로 한다."""
    try:
        subprocess.Popen([sys.executable, str(SCRIPT), 'send', '--kind', kind, '--project', project,
                          '--agent', agent, '--dedupe', '0', text],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


def handle(found, agent, session):
    if not found:
        return
    kind, text, project = found
    if not seen_recently('%s|%s|%s' % (kind, session, text), 60):
        spawn_send(kind, text, project, agent)


def option(args, name, default=None):
    if name in args:
        index = args.index(name)
        if index + 1 < len(args):
            value = args[index + 1]
            del args[index:index + 2]
            return value
    return default


# --- 설치 ---------------------------------------------------------------

HOOK_EVENTS = {'PreToolUse': 'AskUserQuestion', 'PermissionRequest': None, 'Notification': None, 'Stop': None}


def hook_command():
    return "'%s' '%s' hook" % (PYTHON, SCRIPT)


def is_ours(command):
    return str(SCRIPT) in str(command or '')


def strip_hooks(hooks):
    for event in list(hooks):
        groups = []
        for group in hooks.get(event) or []:
            if isinstance(group, dict) and isinstance(group.get('hooks'), list):
                kept = [hook for hook in group['hooks'] if not is_ours((hook or {}).get('command'))]
                if not kept:
                    continue
                group = dict(group, hooks=kept)
            groups.append(group)
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]


def read_claude_settings():
    try:
        settings = json.loads(CLAUDE_SETTINGS.read_text(encoding='utf-8'))
    except FileNotFoundError:
        settings = {}
    if not isinstance(settings, dict) or not isinstance(settings.get('hooks', {}), dict):
        raise ValueError('Claude 설정 형식을 해석할 수 없어 변경하지 않았습니다.')
    return settings


def codex_notify_line(lines):
    for index, line in enumerate(lines):
        if line.lstrip().startswith('['):
            return None, index
        if re.match(r'\s*notify\s*=', line):
            return index, index
    return None, len(lines)


def install():
    conf = load_conf()
    if not conf.get('ntfy_topic'):
        conf['ntfy_topic'] = 'llm-' + secrets.token_urlsafe(18)
    settings = read_claude_settings()
    hooks = settings.setdefault('hooks', {})
    strip_hooks(hooks)
    for event, matcher in HOOK_EVENTS.items():
        entry = {'hooks': [{'type': 'command', 'command': hook_command(), 'timeout': 10}]}
        if matcher:
            entry['matcher'] = matcher
        hooks.setdefault(event, []).append(entry)
    mode = CLAUDE_SETTINGS.stat().st_mode & 0o777 if CLAUDE_SETTINGS.exists() else 0o600
    save_json(CLAUDE_SETTINGS, settings, mode)
    print('Claude Code 훅 등록:', ', '.join(HOOK_EVENTS))

    if CODEX_CONFIG.exists():
        lines = CODEX_CONFIG.read_text(encoding='utf-8').split('\n')
        index, insert_at = codex_notify_line(lines)
        try:
            chain = json.loads(lines[index].split('=', 1)[1]) if index is not None else []
            if not isinstance(chain, list):
                raise ValueError
        except ValueError:
            chain = None
        if index is not None and is_ours(lines[index]):
            print('Codex notify: 이미 등록됨')
        elif chain is None:
            print('Codex notify: 기존 값을 해석할 수 없어 바꾸지 않았습니다.')
        else:
            conf['codex_chain'] = chain
            new = 'notify = ' + json.dumps([PYTHON, str(SCRIPT), 'codex'] + (['--chain'] + chain if chain else []),
                                           ensure_ascii=False)
            if index is None:
                lines.insert(insert_at, new)
            else:
                lines[index] = new
            CODEX_CONFIG.write_text('\n'.join(lines), encoding='utf-8')
            print('Codex notify 등록' + (' (기존 notify는 이어서 실행)' if chain else ''))
    save_json(CONF, conf)
    print('설정:', CONF)
    print('휴대폰 ntfy 앱에서 구독할 주제:', conf['ntfy_topic'], '(서버 %s)' % conf['ntfy_server'])
    return 0


def uninstall():
    conf = load_conf()
    settings = read_claude_settings()
    strip_hooks(settings.setdefault('hooks', {}))
    if not settings['hooks']:
        del settings['hooks']
    mode = CLAUDE_SETTINGS.stat().st_mode & 0o777 if CLAUDE_SETTINGS.exists() else 0o600
    save_json(CLAUDE_SETTINGS, settings, mode)
    print('Claude Code 훅 제거')
    if CODEX_CONFIG.exists():
        lines = CODEX_CONFIG.read_text(encoding='utf-8').split('\n')
        index, _ = codex_notify_line(lines)
        if index is not None and is_ours(lines[index]):
            chain = conf.get('codex_chain') or []
            if chain:
                lines[index] = 'notify = ' + json.dumps(chain, ensure_ascii=False)
            else:
                del lines[index]
            CODEX_CONFIG.write_text('\n'.join(lines), encoding='utf-8')
            print('Codex notify 원래대로 복원')
    return 0


def status():
    conf = load_conf()
    topic = conf.get('ntfy_topic') or ''
    print('설정 파일:', CONF if CONF.exists() else '없음')
    print('Mac 알림:', '켜짐' if conf.get('mac') else '꺼짐', '| 소리:', conf.get('sound'))
    print('휴대폰 알림:', ('켜짐, 주제 %s…' % topic[:8]) if conf.get('phone') and topic else '꺼짐',
          '| 내용 포함:', '예' if conf.get('phone_detail') else '아니오')
    try:
        hooks = read_claude_settings().get('hooks', {})
        found = [event for event, groups in hooks.items()
                 if any(is_ours((hook or {}).get('command')) for group in groups or []
                        for hook in (group or {}).get('hooks') or [])]
    except (OSError, ValueError):
        found = []
    print('Claude Code 훅:', ', '.join(found) or '없음')
    try:
        lines = CODEX_CONFIG.read_text(encoding='utf-8').split('\n')
        index, _ = codex_notify_line(lines)
        print('Codex notify:', '등록됨' if index is not None and is_ours(lines[index]) else '없음')
    except OSError:
        print('Codex notify: 설정 파일 없음')
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 0
    command, args = argv[0], list(argv[1:])
    if command == 'hook':
        try:
            event = json.load(sys.stdin)
        except ValueError:
            return 0
        session = str(event.get('session_id') or '') if isinstance(event, dict) else ''
        handle(from_claude(event), 'Claude', session)
        return 0
    if command == 'codex':
        chain = []
        if args[:1] == ['--chain']:
            chain, args = args[1:-1], args[-1:]
        raw = args[-1] if args else '{}'
        if chain:
            try:
                subprocess.Popen(chain + [raw], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError:
                pass
        try:
            payload = json.loads(raw)
        except ValueError:
            return 0
        thread = str(payload.get('thread-id') or '') if isinstance(payload, dict) else ''
        handle(from_codex(payload), 'Codex', thread)
        return 0
    if command == 'send':
        kind = option(args, '--kind', 'action')
        project = option(args, '--project', '')
        agent = option(args, '--agent', 'Claude')
        dedupe = float(option(args, '--dedupe', '0'))
        only = option(args, '--only')
        text = ' '.join(args)
        if dedupe and seen_recently('send|%s|%s' % (kind, text), dedupe):
            return 0
        print(', '.join(deliver(kind, text, project, agent, only)) or '보낼 곳 없음')
        return 0
    if command == 'test':
        only = option(args, '--only')
        print(', '.join(deliver('alert', '알림 시험입니다. 이 알림이 보이면 설정이 끝났습니다.', '', 'llm-plugin', only))
              or '보낼 곳 없음')
        return 0
    if command == 'install':
        return install()
    if command == 'uninstall':
        return uninstall()
    if command == 'status':
        return status()
    print(__doc__)
    return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
