#!/usr/bin/env python3
"""사용자가 해야 할 일이 생기면 이 Mac(소리 포함)과 휴대폰(ntfy)으로 알리고, 할 일 목록에 넣는다.

사용:
  notify.py hook                 Claude Code 훅. 이벤트 JSON을 표준 입력으로 받는다.
  notify.py codex [--chain 명령...] JSON
                                 Codex notify 프로그램. JSON은 마지막 인자다.
  notify.py send [--kind 종류] [--project 이름] [--agent 이름] [--dedupe 초] [--only mac|phone] 내용
  notify.py test [--only mac|phone]
  notify.py todo [list] [--json]  할 일 목록(메뉴 막대 '🔔 할 일'과 같은 내용)
  notify.py todo done 번호|id...  완료한 할 일 지우기
  notify.py todo act 번호|id [--choice 선택]
                                 할 일을 그 T3 세션에 맡기기(메뉴 막대 '알아서 진행'·'선택')
  notify.py todo add [--kind 종류] [--project 이름] 내용
  notify.py todo clear           할 일 모두 지우기
  notify.py install | uninstall | status

종류: question(답변 필요), approval(승인 필요), action(할 일), alert(확인 필요)
설정: ~/.config/llm-plugin/notify.json
할 일 목록: ~/.config/llm-plugin/todos.json
"""
import fcntl
import hashlib
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

HOME = Path.home()
CONF_DIR = HOME / '.config' / 'llm-plugin'
CONF = CONF_DIR / 'notify.json'
STATE = CONF_DIR / 'notify-state.json'
TODOS = CONF_DIR / 'todos.json'
TODOS_LOCK = CONF_DIR / 'todos.lock'
# 질문·승인 항목이 있을 때만 있는 표시 파일. PostToolUse 훅은 이 파일이 있을 때만 Python을 실행한다.
WAITING = CONF_DIR / 'todos-waiting'
T3_DB = HOME / '.t3' / 'userdata' / 'statev2.sqlite'
T3_MANIFEST = HOME / '.t3' / 'userdata' / 'model-manifest.json'
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
    'relay_percent': 80,
}
# '🔔 할 일: 내용' 또는 줄 끝의 '🔔 할 일:'(다음 줄부터 목록). '🔔 할 일이 있습니다' 같은 문장은 표시로 보지 않는다.
TODO = re.compile(r'🔔\s*할\s*일\s*(?:[:：]\s*(.*)|$)')
LIST_ITEM = re.compile(r'^(?:\d{1,2}[.)]|[-*•])\s+(.+)$')
CODE_LINE = '\0code'
MAX_TODOS = 10
KINDS = ('question', 'approval', 'action', 'alert')
WAITING_KINDS = ('question', 'approval')


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


def clean_lines(text, limit=400):
    """줄바꿈은 살리고 각 줄을 clean한다. 여러 할 일을 번호 목록으로 보여 줄 때 쓴다."""
    text = '\n'.join(line for line in (clean(part) for part in str(text or '').splitlines()) if line)
    return text if len(text) <= limit else text[:limit - 1] + '…'


def visible_lines(message):
    """빈 줄을 뺀 줄 목록. 코드 블록(``` 또는 ~~~) 안의 줄은 CODE_LINE으로 바꿔 표시로 읽지 않게 한다."""
    lines, fence = [], False
    for raw in str(message or '').splitlines():
        line = raw.strip()
        if line.startswith('```') or line.startswith('~~~'):
            fence = not fence
            lines.append(CODE_LINE)
        elif line:
            lines.append(CODE_LINE if fence else line)
    return lines


def find_todos(message):
    """응답 끝의 '🔔 할 일' 표시에서 할 일 목록을 읽는다. 없으면 빈 목록.

    한 줄 형식: '🔔 할 일: 내용'
    목록 형식: '🔔 할 일:' 다음 줄부터 '1. 내용' 또는 '- 내용'을 한 줄에 하나씩
    표시(와 이어진 목록) 뒤에 다른 줄이 세 줄 이상 있으면 오래된 표시로 보고 무시한다.
    인라인 코드와 코드 블록 안의 예시, '<…>' 자리표시는 무시한다.
    """
    lines = visible_lines(message)
    for index in range(len(lines) - 1, -1, -1):
        match = TODO.search(lines[index])
        if not match or '`' in lines[index][:match.start()]:
            continue
        after = lines[index + 1:]
        items = []
        while after and LIST_ITEM.match(after[0]):
            items.append(LIST_ITEM.match(after[0]).group(1))
            after = after[1:]
        if len(after) > 2:
            return []
        if not items and match.group(1):
            items = [match.group(1)]
        items = [clean(item) for item in items]
        return [item for item in items if item and not item.startswith('<')][:MAX_TODOS]
    return []


def todo_text(items):
    """알림에 넣을 할 일 내용. 하나면 그대로, 여러 개면 번호 목록."""
    if len(items) == 1:
        return items[0]
    return '\n'.join('%d. %s' % (number, item) for number, item in enumerate(items, 1))


def find_todo(message):
    """알림 내용으로 쓸 할 일. 없으면 None."""
    items = find_todos(message)
    return todo_text(items) if items else None


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
        if todo:
            return 'action', todo, project
        usage = context_usage(event.get('transcript_path'))
        if usage and is_long(usage) and not seen_recently('relay|%s' % event.get('session_id'), 6 * 3600):
            return 'action', '세션이 길어졌습니다(%s). /relay로 새 세션에서 이어갈 수 있습니다.' % tokens_text(usage[0]), project
        return None
    if name == 'PreCompact':
        return 'action', '세션을 압축합니다. 지금까지 내용을 새 세션으로 옮기려면 /relay를 쓰세요.', project
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


# --- 할 일 목록 -----------------------------------------------------------
# todos.json: {"items": [{id, kind, text, agent, project, session, title, tool, created}]}
# 메뉴 막대 프로그램(todo-menubar.js)이 이 파일을 1초마다 읽어 보여 주고, 완료 버튼은 'todo done'을 실행한다.
# 세션마다 할 일을 다음처럼 바꾼다.
#   응답이 끝남(Stop, Codex agent-turn-complete): 그 세션의 항목을 응답 끝 '🔔 할 일' 목록으로 바꾼다.
#   사용자가 그 세션에 메시지를 보냄(UserPromptSubmit): 그 세션의 질문·승인 항목만 지운다.
#     할 일은 지우지 않는다. 하나에만 답했는데 나머지까지 사라지지 않게, 응답이 끝날 때 그 응답의 목록으로 바꾼다.
#   질문·승인이 끝남(PostToolUse): 그 도구의 질문·승인 항목을 지운다.

def load_todos():
    try:
        data = json.loads(TODOS.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = {}
    items = data.get('items') if isinstance(data, dict) else None
    relay = data.get('relay') if isinstance(data, dict) else None
    return {'items': [item for item in items or [] if isinstance(item, dict) and item.get('id')],
            'relay': {key: value for key, value in (relay or {}).items() if isinstance(value, dict)}}


@contextmanager
def todo_store():
    """잠금을 잡고 목록을 읽어 넘긴다. 블록 안에서 바꾼 내용이 있으면 저장한다."""
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    with open(TODOS_LOCK, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = load_todos()
        before = json.dumps(data, sort_keys=True, ensure_ascii=False)
        yield data
        if json.dumps(data, sort_keys=True, ensure_ascii=False) != before or not TODOS.exists():
            save_json(TODOS, data)
        waiting = any(item.get('kind') in WAITING_KINDS for item in data['items'])
        if waiting and not WAITING.exists():
            WAITING.touch()
        elif not waiting and WAITING.exists():
            WAITING.unlink()


def t3_thread(native_id):
    """(T3 세션 id, 제목). Claude·Codex 세션 ID로 T3 상태 DB를 읽기 전용으로 찾는다. T3 밖 세션이면 ('', '')."""
    if not native_id or not T3_DB.exists():
        return '', ''
    try:
        connection = sqlite3.connect(T3_DB.as_uri() + '?mode=ro', uri=True, timeout=0.3)
        try:
            row = connection.execute(
                "select t.thread_id, t.title from orchestration_v2_projection_provider_threads p "
                "join orchestration_v2_projection_threads t on t.thread_id = p.thread_id "
                "where json_extract(p.payload_json, '$.nativeThreadRef.nativeId') = ? "
                "order by p.updated_at desc limit 1", (native_id,)).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return '', ''
    if not row:
        return '', ''
    return str(row[0] or ''), clean(row[1], 80) if row[1] else ''


# 할 일 끝의 '(추천: 행동)' 또는 '(선택: A(추천) / B / C)'. 메뉴 막대가 '알아서 진행'·'선택' 버튼으로 쓴다.
TODO_HINT = re.compile(r'\s*[(（]\s*(추천|선택)\s*[:：]\s*(.+)[)）]\s*$')
RECOMMENDED = re.compile(r'\s*(?:[(（]\s*추천\s*[)）]|\s추천)\s*$')


def parse_todo(text):
    """할 일 문장을 (본문, 추천, 선택지)로 나눈다. 선택지는 [{'label', 'recommended'}]."""
    match = TODO_HINT.search(text)
    if not match:
        return text, '', []
    body, kind, rest = text[:match.start()].strip(), match.group(1), match.group(2).strip()
    if not body or not rest:
        return text, '', []
    if kind == '추천':
        return body, rest, []
    parts = [part.strip() for part in re.split(r'\s+/\s+', rest) if part.strip()]
    if len(parts) < 2:
        parts = [part.strip() for part in rest.split('/') if part.strip()]
    choices = []
    for part in parts[:8]:
        label = RECOMMENDED.sub('', part).strip()
        if label:
            choices.append({'label': label, 'recommended': label != part})
    return (body, '', choices) if len(choices) >= 2 else (text, '', [])


def new_item(kind, text, agent='', project='', session='', t3=('', ''), tool='', recommend='', choices=None,
             multi=False):
    return {'id': secrets.token_hex(4), 'kind': kind if kind in KINDS else 'action', 'text': clean(text),
            'agent': agent, 'project': project, 'session': session, 'thread': t3[0], 'title': t3[1],
            'tool': tool, 'recommend': clean(recommend), 'choices': choices or [], 'multi': bool(multi),
            'created': round(time.time(), 1)}


def add_items(data, items):
    """같은 세션·종류·내용의 항목이 이미 있으면 넣지 않는다."""
    have = {(item.get('session'), item.get('kind'), item.get('text')) for item in data['items']}
    for item in items:
        key = (item['session'], item['kind'], item['text'])
        if item['text'] and key not in have:
            data['items'].append(item)
            have.add(key)


def drop_items(data, test):
    data['items'] = [item for item in data['items'] if not test(item)]


# 일을 하지 않는 명령(지침 새로고침, 압축)으로 시작한 차례. 응답에 할 일 표시가 없어도 목록을 비우지 않는다.
META_TURN = re.compile(r'^\s*(?:<command-message>[^<]*</command-message>\s*)?(?:<command-name>)?[/$](?:refresh|compact)\b')


def turn_prompt(path):
    """이번 차례를 시작한 사용자 입력. 도구 결과와 스킬 본문(isMeta)은 건너뛴다. 읽지 못하면 ''."""
    try:
        with open(path, 'rb') as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - 1024 * 1024))
            chunk = handle.read().decode('utf-8', 'ignore')
    except (OSError, TypeError, ValueError):
        return ''
    for line in reversed(chunk.splitlines()):
        if '"user"' not in line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if not isinstance(item, dict) or item.get('type') != 'user' or item.get('isSidechain') or item.get('isMeta'):
            continue
        content = (item.get('message') or {}).get('content')
        if isinstance(content, str):
            return content
        texts = [part.get('text', '') for part in content or [] if isinstance(part, dict) and part.get('type') == 'text']
        if texts:
            return '\n'.join(texts)
    return ''


def replace_session_todos(data, session, texts, agent, project, context=None, keep=False):
    """응답이 끝난 세션의 항목을 그 응답의 할 일 목록으로 바꾼다. 같은 내용은 처음 생긴 시각을 그대로 둔다.
    context가 (토큰, 창 크기)면 세션이 길어졌는지 보고 '새 세션으로 이어가기' 제안을 다시 넣는다.
    keep이면(새로고침 같은 명령으로 시작한 차례) 할 일 표시가 없을 때 기존 할 일을 그대로 둔다."""
    if keep and not texts:
        t3 = t3_thread(session) if context or session in data['relay'] else ('', '')
        relay_suggestion(data, session, t3, agent, project, context)
        return
    old = {item.get('text'): item for item in data['items']
           if item.get('session') == session and item.get('kind') == 'action'}
    drop_items(data, lambda item: item.get('session') == session)
    t3 = t3_thread(session) if texts or context or session in data['relay'] else ('', '')
    relay_suggestion(data, session, t3, agent, project, context)
    for text in texts:
        body, recommend, choices = parse_todo(text)
        item = new_item('action', body, agent, project, session, t3, recommend=recommend, choices=choices)
        if item['text'] in old:
            item['id'], item['created'] = old[item['text']]['id'], old[item['text']]['created']
        add_items(data, [item])


# --- 새 세션으로 이어가기(/relay) 제안 ----------------------------------------
# 응답이 끝날 때 컨텍스트가 창의 relay_percent(기본 80%)를 넘었거나, 이 세션이 압축된 적이 있으면
# 메뉴 막대에 '새 세션으로 이어가기' 할 일을 넣는다. '알아서 진행'을 누르면 그 세션이 /relay를 실행한다.
# 완료로 지우면 다음 압축 전까지 다시 넣지 않는다. /relay가 원래 세션 제목 앞에 RELAYED를 붙이면 넣지 않는다.
RELAYED = '(이어감)'


def context_usage(path):
    """(지금 컨텍스트 토큰, 창 크기). 기록의 마지막 응답 사용량으로 센다. 읽지 못하면 None."""
    try:
        with open(path, 'rb') as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - 512 * 1024))
            chunk = handle.read().decode('utf-8', 'ignore')
    except (OSError, TypeError, ValueError):
        return None
    for line in reversed(chunk.splitlines()):
        if '"usage"' not in line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if not isinstance(item, dict) or item.get('type') != 'assistant' or item.get('isSidechain'):
            continue
        message = item.get('message') or {}
        usage = message.get('usage') or {}
        tokens = sum(int(usage.get(key) or 0) for key in
                     ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'))
        if tokens:
            return tokens, context_window(message.get('model'))
    return None


def context_window(model):
    """모델의 컨텍스트 창 크기. T3 모델 목록(model-manifest.json)에서 찾고, 없으면 100만."""
    name = re.sub(r'^claude-|-\d{8}$', '', str(model or '')).replace('[1m]', '')
    try:
        profiles = json.loads(T3_MANIFEST.read_text(encoding='utf-8'))['manifest']['providers']['claudeAgent']['profiles']
        adapter = (profiles.get(name) or {}).get('adapter', {}).get('claudeCode', {})
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        adapter = {}
    if adapter.get('fixedContextWindowTokens'):
        return int(adapter['fixedContextWindowTokens'])
    sizes = adapter.get('contextWindowTokens') or {}
    if sizes:
        return int(sizes.get('1m' if '[1m]' in str(model) else '200k') or max(sizes.values()))
    return 1000000


def is_long(usage):
    tokens, window = usage
    return bool(window) and tokens >= window * float(load_conf().get('relay_percent') or 80) / 100


def tokens_text(tokens):
    return '컨텍스트 약 %d만 토큰' % round(tokens / 10000) if tokens >= 10000 else '컨텍스트 %d토큰' % tokens


def relay_suggestion(data, session, t3, agent, project, context):
    """조건이 맞으면 이 세션의 '새 세션으로 이어가기' 할 일을 넣는다."""
    state = data['relay'].get(session) or {}
    if t3[1].startswith(RELAYED) or state.get('dismissed'):
        return
    if state.get('compacted'):
        reason = '이 세션이 압축됐습니다(직전 %s)' % tokens_text(state.get('tokens') or 0)
    elif context and is_long(context):
        reason = '이 세션이 길어졌습니다(%s, 창의 %d%%)' % (tokens_text(context[0]), round(100 * context[0] / context[1]))
    else:
        return
    item = new_item('action', reason + '. 새 세션으로 이어가기', agent, project, session, t3,
                    recommend='/relay로 지금까지 내용을 정리해 새 세션을 만들고 거기서 이어가기')
    item['id'] = hashlib.sha1(('relay:' + session).encode('utf-8')).hexdigest()[:8]
    item['source'] = 'relay'
    drop_items(data, lambda old: old['id'] == item['id'])
    data['items'].append(item)


def track_claude(event):
    """Claude Code 훅 이벤트로 할 일 목록을 고친다."""
    if not isinstance(event, dict) or event.get('agent_id'):
        return
    name = event.get('hook_event_name')
    session = str(event.get('session_id') or '')
    if not session:
        return
    project = Path(event.get('cwd') or '').name
    tool = str(event.get('tool_name') or '')
    with todo_store() as data:
        if name == 'PreToolUse' and tool == 'AskUserQuestion':
            questions = [q for q in (event.get('tool_input') or {}).get('questions') or []
                         if isinstance(q, dict) and q.get('question')]
            t3 = t3_thread(session)
            # 선택지는 보여 주기만 한다. 답은 T3 화면에서 한다(메뉴 막대의 'T3에서 답하기').
            add_items(data, [new_item('question', q['question'], 'Claude', project, session, t3, tool,
                                      choices=[{'label': clean(o.get('label'), 60), 'recommended': False}
                                               for o in q.get('options') or [] if isinstance(o, dict) and o.get('label')],
                                      multi=q.get('multiSelect'))
                             for q in questions]
                      or [new_item('question', '질문이 있습니다.', 'Claude', project, session, t3, tool)])
        elif name == 'PermissionRequest':
            add_items(data, [new_item('approval', '%s 실행 승인' % (tool or '도구'), 'Claude', project, session,
                                      t3_thread(session), tool)])
        elif name == 'Notification':
            kind = {'permission_prompt': 'approval', 'elicitation_dialog': 'question',
                    'elicitation_url_dialog': 'question'}.get(event.get('notification_type'))
            # PermissionRequest가 이미 넣은 승인은 알림 문구로 한 번 더 넣지 않는다.
            if kind and not any(item.get('session') == session and item.get('kind') == kind
                                for item in data['items']):
                add_items(data, [new_item(kind, event.get('message') or TITLES[kind], 'Claude', project,
                                          session, t3_thread(session))])
        elif name == 'PostToolUse':
            drop_items(data, lambda item: item.get('session') == session and item.get('kind') in WAITING_KINDS
                       and item.get('tool') in (tool, ''))
        elif name == 'UserPromptSubmit':
            drop_items(data, lambda item: item.get('session') == session and item.get('kind') in WAITING_KINDS)
        elif name == 'Stop' and not event.get('stop_hook_active'):
            message = event.get('last_assistant_message') or last_assistant_text(event.get('transcript_path'))
            replace_session_todos(data, session, find_todos(message), 'Claude', project,
                                  context_usage(event.get('transcript_path')),
                                  keep=bool(META_TURN.match(turn_prompt(event.get('transcript_path')))))
        elif name == 'PreCompact':
            tokens, window = context_usage(event.get('transcript_path')) or (0, 0)
            data['relay'][session] = {'compacted': round(time.time(), 1), 'tokens': tokens,
                                      'trigger': str(event.get('trigger') or '')}
            relay_suggestion(data, session, t3_thread(session), 'Claude', project, (tokens, window))


def track_codex(payload):
    """Codex notify 이벤트로 할 일 목록을 고친다."""
    if not isinstance(payload, dict):
        return
    thread = str(payload.get('thread-id') or '')
    if not thread:
        return
    kind = str(payload.get('type') or '')
    project = Path(payload.get('cwd') or '').name
    with todo_store() as data:
        if kind == 'agent-turn-complete':
            inputs = [str(text) for text in payload.get('input-messages') or []]
            replace_session_todos(data, thread, find_todos(payload.get('last-assistant-message')), 'Codex', project,
                                  keep=bool(inputs) and all(META_TURN.match(text) for text in inputs))
        elif 'approval' in kind or 'question' in kind:
            found = from_codex(payload)
            add_items(data, [new_item(found[0], found[1], 'Codex', project, thread, t3_thread(thread))])


T3_CLI = HOME / '.t3' / 'bin' / 't3'


def todo_line(item):
    """할 일을 응답 끝에 쓰는 형식으로 되돌린다(추천·선택지 포함)."""
    if item.get('recommend'):
        return '%s (추천: %s)' % (item.get('text'), item['recommend'])
    if item.get('choices'):
        return '%s (선택: %s)' % (item.get('text'), ' / '.join(
            choice['label'] + ('(추천)' if choice.get('recommended') else '') for choice in item['choices']))
    return item.get('text')


def act_message(item, choice='', others=()):
    """'알아서 진행'·'선택'을 눌렀을 때 그 세션에 보낼 메시지.
    응답이 끝나면 목록이 그 응답의 할 일로 바뀌므로, 같은 세션의 다른 남은 할 일을 적어 다시 적게 한다."""
    if choice:
        message = ('메뉴 막대 할 일 목록에서 선택했습니다.\n- 할 일: %s\n- 선택: %s\n이 선택으로 진행해 주세요.'
                   % (item.get('text'), choice))
    elif item.get('recommend'):
        message = ('메뉴 막대 할 일 목록에서 "알아서 진행"을 눌렀습니다.\n- 할 일: %s\n- 추천: %s\n'
                   '추천대로 진행해 주세요. 진행할 수 없으면 이유와 필요한 것을 알려 주세요.'
                   % (item.get('text'), item['recommend']))
    else:
        message = ('메뉴 막대 할 일 목록에서 "알아서 진행"을 눌렀습니다.\n- 할 일: %s\n'
                   '가장 알맞은 방법으로 진행해 주세요. 사용자만 할 수 있는 일이면 무엇이 필요한지 알려 주세요.'
                   % item.get('text'))
    if others:
        message += ('\n\n이 세션에 남은 다른 할 일입니다. 이번에 끝내지 않은 것은 응답 끝 할 일 목록에 다시 적어 주세요.\n'
                    + '\n'.join('%d. %s' % (number, todo_line(other)) for number, other in enumerate(others, 1)))
    return message


def set_state(item_id, state, note=''):
    with todo_store() as data:
        for item in data['items']:
            if item['id'] == item_id:
                item.update(state=state, note=note, stateAt=round(time.time(), 1))


def act(item_id, choice=''):
    """할 일을 그 T3 세션에 맡긴다(t3 thread send). 세션이 바쁘면 다음 차례로 들어간다.
    세션의 응답이 끝나면 Stop 훅이 그 세션의 항목을 응답 끝 할 일 목록으로 바꾼다."""
    choice = clean(choice, 300)
    with todo_store() as data:
        item = next((entry for entry in data['items'] if entry['id'] == item_id), None)
        if item is None:
            return 1, '할 일을 찾지 못했습니다.'
        if not item.get('thread'):
            item.update(state='error', note='T3 세션의 할 일만 맡길 수 있습니다.')
            return 1, item['note']
        if item.get('state') == 'sending' and time.time() - (item.get('stateAt') or 0) < 120:
            return 0, '이미 보내는 중입니다.'
        item.update(state='sending', note='', stateAt=round(time.time(), 1))
        others = [entry for entry in data['items'] if entry is not item and entry.get('kind') == 'action'
                  and entry.get('session') and entry.get('session') == item.get('session')]
        thread, message = item['thread'], act_message(item, choice, others)
    try:
        result = subprocess.run([str(T3_CLI), 'thread', 'send', '--json', thread, '-'], input=message,
                                capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        set_state(item_id, 'error', 'T3에 보내지 못했습니다: %s' % clean(error, 100))
        return 1, 'T3에 보내지 못했습니다.'
    if result.returncode != 0:
        lines = (result.stderr or result.stdout or '').strip().splitlines()
        reason = clean(lines[0] if lines else '알 수 없는 오류', 120)
        set_state(item_id, 'error', 'T3에 보내지 못했습니다: %s' % reason)
        return 1, reason
    try:
        delivery = json.loads(result.stdout or '{}').get('delivery')
    except ValueError:
        delivery = None
    set_state(item_id, 'sent', '세션이 바빠 다음 차례로 넣었습니다.' if delivery == 'queued' else '')
    return 0, '보냄'


def add_todo(kind, text, agent='', project=''):
    """세션 밖에서 생긴 할 일. 세션이 없으므로 완료 버튼이나 'todo done'으로만 지워진다."""
    with todo_store() as data:
        add_items(data, [new_item(kind, text, agent, project)])


def safely(function, *args):
    """훅에서 목록을 고치다 실패해도 Claude·Codex를 막지 않는다."""
    try:
        function(*args)
    except Exception:  # noqa: BLE001 - 훅은 어떤 경우에도 조용히 끝나야 한다
        pass


def ordered_todos(data):
    """세션별로 묶어 최근 세션부터. 메뉴 막대와 'todo list'가 같은 순서를 쓴다."""
    groups = {}
    for item in data['items']:
        groups.setdefault(item.get('session') or item['id'], []).append(item)
    ordered = sorted(groups.values(), key=lambda items: -max(item.get('created') or 0 for item in items))
    return [item for items in ordered for item in items]


def ago(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return '방금'
    if seconds < 3600:
        return '%d분 전' % (seconds // 60)
    if seconds < 86400:
        return '%d시간 전' % (seconds // 3600)
    return '%d일 전' % (seconds // 86400)


ICONS = {'question': '❓', 'approval': '🔐', 'action': '🔔', 'alert': '⚠️'}


def todo_command(args):
    sub = args.pop(0) if args and not args[0].startswith('--') else 'list'
    if sub == 'list':
        items = ordered_todos(load_todos())
        if '--json' in args:
            print(json.dumps({'items': items}, ensure_ascii=False, indent=2))
            return 0
        if not items:
            print('할 일이 없습니다.')
            return 0
        now = time.time()
        for number, item in enumerate(items, 1):
            where = ' · '.join(part for part in (item.get('title'), item.get('project'), item.get('agent')) if part)
            print('%d. %s %s' % (number, ICONS.get(item.get('kind'), '🔔'), item.get('text')))
            if item.get('recommend'):
                print('   추천: %s' % item['recommend'])
            if item.get('choices'):
                print('   선택: %s' % ' / '.join(choice['label'] + (' (추천)' if choice.get('recommended') else '')
                                            for choice in item['choices']))
            print('   %s · %s · id %s' % (where or '세션 정보 없음', ago(now - (item.get('created') or now)), item['id']))
        return 0
    if sub == 'act':
        choice = option(args, '--choice', '')
        if not args:
            print('맡길 할 일의 번호나 id를 적어 주세요.', file=sys.stderr)
            return 2
        target = args[0]
        if target.isdigit() and len(target) <= 3:
            items = ordered_todos(load_todos())
            if not 1 <= int(target) <= len(items):
                print('그 번호의 할 일이 없습니다.', file=sys.stderr)
                return 1
            target = items[int(target) - 1]['id']
        code, message = act(target, choice)
        print(message, file=sys.stderr if code else sys.stdout)
        return code
    if sub == 'done':
        if not args:
            print('지울 할 일의 번호나 id를 적어 주세요.', file=sys.stderr)
            return 2
        with todo_store() as data:
            items = ordered_todos(data)
            targets = set()
            for arg in args:
                if arg.isdigit() and 1 <= int(arg) <= len(items) and len(arg) <= 3:
                    targets.add(items[int(arg) - 1]['id'])
                else:
                    targets.add(arg)
            before = len(data['items'])
            for item in data['items']:
                if item['id'] in targets and item.get('source') == 'relay' and item.get('session'):
                    data['relay'].setdefault(item['session'], {})['dismissed'] = True
            drop_items(data, lambda item: item['id'] in targets)
            removed = before - len(data['items'])
        print('%d개 지움' % removed)
        return 0 if removed else 1
    if sub == 'add':
        kind = option(args, '--kind', 'action')
        project = option(args, '--project', '')
        text = ' '.join(args)
        if not clean(text):
            print('내용을 적어 주세요.', file=sys.stderr)
            return 2
        add_todo(kind, text, '', project)
        print('넣음')
        return 0
    if sub == 'clear':
        with todo_store() as data:
            count = len(data['items'])
            data['items'] = []
        print('%d개 지움' % count)
        return 0
    print(__doc__)
    return 2


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
    text = clean_lines(text) or title
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
        # 할 일 목록은 훅이 이미 고쳤으므로 send가 목록에 다시 넣지 않게 한다(--no-list).
        subprocess.Popen([sys.executable, str(SCRIPT), 'send', '--kind', kind, '--project', project,
                          '--agent', agent, '--dedupe', '0', '--no-list', text],
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

HOOK_EVENTS = {'PreToolUse': 'AskUserQuestion', 'PermissionRequest': None, 'Notification': None, 'Stop': None,
               'UserPromptSubmit': None, 'PostToolUse': None, 'PreCompact': None}


def hook_command(event=None):
    command = "'%s' '%s' hook" % (PYTHON, SCRIPT)
    if event == 'PostToolUse':
        # 도구를 쓸 때마다 Python을 띄우지 않도록, 질문·승인 항목이 있을 때만 실행한다.
        return "[ ! -e '%s' ] || exec %s" % (WAITING, command)
    return command


def is_ours(command):
    # Codex 앱이 notify를 감싸면 이 스크립트 경로가 JSON 안에 '\/'로 이스케이프되어 들어간다. 역슬래시를 빼고 찾는다.
    return str(SCRIPT) in str(command or '').replace('\\', '')


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
        entry = {'hooks': [{'type': 'command', 'command': hook_command(event), 'timeout': 10}]}
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
    missing = [event for event in HOOK_EVENTS if event not in found]
    if found and missing:
        print('  빠진 훅:', ', '.join(missing), '→ install을 다시 실행하세요.')
    print('할 일 목록: %d개 (%s)' % (len(load_todos()['items']), TODOS))
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
        safely(track_claude, event)
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
        safely(track_codex, payload)
        handle(from_codex(payload), 'Codex', thread)
        return 0
    if command == 'send':
        kind = option(args, '--kind', 'action')
        project = option(args, '--project', '')
        agent = option(args, '--agent', '')
        dedupe = float(option(args, '--dedupe', '0'))
        only = option(args, '--only')
        listed = '--no-list' not in args
        args = [arg for arg in args if arg != '--no-list']
        text = ' '.join(args)
        if dedupe and seen_recently('send|%s|%s' % (kind, text), dedupe):
            return 0
        # 다른 프로그램이 보낸 할 일·확인 알림(Drive 동기화 실패 등)은 목록에도 넣는다. 완료 버튼으로 지운다.
        if listed and kind in ('action', 'alert'):
            safely(add_todo, kind, text, agent, project)
        print(', '.join(deliver(kind, text, project, agent or 'Claude', only)) or '보낼 곳 없음')
        return 0
    if command == 'todo':
        return todo_command(args)
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
