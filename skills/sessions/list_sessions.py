#!/usr/bin/env python3
"""T3 밖에서 실행한 Claude Code·Codex 세션을 이 Mac의 기록에서 찾아 Markdown 표로 출력한다.

기록 파일과 T3 상태 DB를 읽기만 한다. 실행 상태(실행 중·입력 대기)는 기록만으로 알 수 없다.
사용: list_sessions.py [--days 3] [--limit 20]
"""
import argparse
import glob
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

HOME = Path.home()
CLAUDE_SOURCES = {'cli': '터미널', 'claude-vscode': 'VS Code', 'claude-desktop': 'Claude 앱',
                  'sdk-cli': '스크립트', 'sdk-ts': 'SDK', 'sdk-py': 'SDK'}
CODEX_SOURCES = {'cli': '터미널', 'vscode': 'Codex 앱', 'exec': '스크립트'}


def t3_native_ids():
    database = HOME / '.t3' / 'userdata' / 'statev2.sqlite'
    if not database.exists():
        return None
    try:
        connection = sqlite3.connect('file:%s?mode=ro' % database, uri=True, timeout=3)
        rows = connection.execute("select json_extract(payload_json, '$.nativeThreadRef.nativeId') "
                                  "from orchestration_v2_projection_provider_threads").fetchall()
        connection.close()
    except sqlite3.Error:
        return None
    return {row[0] for row in rows if row[0]}


def short(text, limit=40):
    text = ' '.join(str(text or '').replace('|', '/').split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def is_prompt(text):
    text = (text or '').strip()
    return bool(text) and not text.startswith(('<', '[Request', 'Caveat'))


def read_lines(path, limit):
    with open(path, encoding='utf-8', errors='ignore') as handle:
        for index, line in enumerate(handle):
            if index >= limit:
                return
            try:
                yield json.loads(line)
            except ValueError:
                continue


def claude_sessions(since, known):
    for path in glob.glob(str(HOME / '.claude' / 'projects' / '*' / '*.jsonl')):
        modified = os.path.getmtime(path)
        if modified < since:
            continue
        session = os.path.basename(path)[:-6]
        entry, cwd, prompt, sidechain = None, '', '', False
        for item in read_lines(path, 300):
            entry = entry or item.get('entrypoint')
            cwd = cwd or item.get('cwd') or ''
            sidechain = sidechain or bool(item.get('isSidechain'))
            if not prompt and item.get('type') == 'user':
                content = (item.get('message') or {}).get('content')
                if isinstance(content, list):
                    content = ' '.join(part.get('text', '') for part in content
                                       if isinstance(part, dict) and part.get('type') == 'text')
                if isinstance(content, str) and is_prompt(content):
                    prompt = content
            if entry and cwd and prompt:
                break
        if sidechain or entry == 't3-code' or (known is not None and session in known):
            continue
        yield modified, CLAUDE_SOURCES.get(entry, entry or '알 수 없음'), cwd, prompt, \
            'claude --resume %s' % session


def codex_sessions(since, known):
    for path in glob.glob(str(HOME / '.codex' / 'sessions' / '*' / '*' / '*' / 'rollout-*.jsonl')):
        modified = os.path.getmtime(path)
        if modified < since:
            continue
        meta, prompt = {}, ''
        for index, item in enumerate(read_lines(path, 400)):
            payload = item.get('payload') or {}
            if index == 0:
                meta = payload
            elif payload.get('type') == 'user_message' and is_prompt(payload.get('message')):
                prompt = payload.get('message')
                break
        source = meta.get('source')
        if isinstance(source, dict) or (known is not None and meta.get('id') in known):
            continue  # 하위 에이전트 기록이거나 T3 세션
        yield modified, CODEX_SOURCES.get(source, str(source or '알 수 없음')), meta.get('cwd') or '', prompt, \
            'codex resume %s' % meta.get('id')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=float, default=3)
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    now = time.time()
    since = now - args.days * 86400
    known = t3_native_ids()
    rows = sorted(list(claude_sessions(since, known)) + list(codex_sessions(since, known)), reverse=True)
    print('## 🗂 T3 밖 세션 · 최근 %g일 · %s' % (args.days, datetime.now().strftime('%m-%d %H:%M')))
    if known is None:
        print('\nT3 기록을 읽지 못해 T3에서 만든 세션이 섞여 있을 수 있습니다.')
    if not rows:
        print('\n최근 %g일 동안 T3 밖에서 실행한 세션이 없습니다.' % args.days)
        return 0
    print('\n| 마지막 기록 | 출처 | 폴더 | 첫 요청 | 이어서 하기 |\n|---|---|---|---|---|')
    for modified, source, cwd, prompt, resume in rows[:args.limit]:
        when = '🟢 방금' if now - modified < 300 else datetime.fromtimestamp(modified).strftime('%m-%d %H:%M')
        folder = Path(cwd).name or '-'
        print('| %s | %s | %s | %s | `%s` |' % (when, source, short(folder, 24), short(prompt) or '-', resume))
    if len(rows) > args.limit:
        print('\n외 %d개. `--limit`으로 더 볼 수 있습니다.' % (len(rows) - args.limit))
    print('\n"방금"은 5분 안에 기록이 바뀐 세션입니다. Claude 세션은 해당 폴더에서 이어서 실행합니다.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
