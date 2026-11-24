#!/usr/bin/env python3
"""Refresh a dedicated rclone credential and import a single Drive folder.

Personal values live in config.json inside the state directory, not in this file:
  {"folder_id": "<Drive folder ID>", "inbox": "<absolute inbox path>",
   "notify_command": ["optional", "command", "for", "failure", "alerts"]}
"""
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import drive_pull

RCLONE = '/opt/homebrew/bin/rclone'
REMOTE = 'claude-obsidian-inbox'
STATE = Path.home() / 'Library' / 'Application Support' / 'ClaudeObsidianInbox'
ALERT_AFTER = 6        # consecutive failed runs, about 30 minutes at a 5-minute interval
ALERT_REPEAT = 144     # then remind about every 12 hours while it keeps failing
ALERT_TEXT = ('Drive 동기화가 30분 넘게 실패하고 있습니다. 네트워크나 Google 재인증'
              '(/drive-reauth)을 확인해 주세요.')
TOKEN_LIFETIME = 7 * 86400   # refresh tokens of a Google OAuth app in testing status
REMIND_BEFORE = 86400
REMIND_HOURS = (9, 22)       # local hours; the advance reminder waits for daytime
REAUTH_TEXT = 'Drive 인증이 %s쯤 만료됩니다. 이 Mac에서 /drive-reauth로 다시 인증해 주세요.'


def check_reauth(token, notify_command, now=None):
    """Note when the refresh token changes and remind once a day before it expires.

    Only a short hash of the refresh token is stored, never the token itself.
    """
    refresh = token.get('refresh_token') if isinstance(token, dict) else None
    if not refresh:
        return
    now = time.time() if now is None else now
    digest = hashlib.sha256(refresh.encode('utf-8')).hexdigest()[:16]
    path = STATE / 'reauth.json'
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {}
    if state.get('hash') != digest:
        state = {'hash': digest, 'since': now, 'reminded': False}
    due = now - state['since'] >= TOKEN_LIFETIME - REMIND_BEFORE
    daytime = REMIND_HOURS[0] <= datetime.fromtimestamp(now).hour < REMIND_HOURS[1]
    if due and daytime and not state.get('reminded') and isinstance(notify_command, list) and notify_command:
        expires = datetime.fromtimestamp(state['since'] + TOKEN_LIFETIME).strftime('%m-%d %H:%M')
        try:
            subprocess.run([str(part) for part in notify_command] + [REAUTH_TEXT % expires], timeout=30,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            state['reminded'] = True
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        path.write_text(json.dumps(state), encoding='utf-8')
    except OSError:
        pass


def load_settings():
    data = json.loads((STATE / 'config.json').read_text(encoding='utf-8'))
    return str(data['folder_id']), str(data['inbox']), data.get('notify_command')


def record_result(ok, notify_command):
    marker = STATE / 'failures'
    if ok:
        try:
            marker.unlink()
        except FileNotFoundError:
            pass
        return
    try:
        count = int(marker.read_text() or 0) + 1
    except (OSError, ValueError):
        count = 1
    marker.write_text(str(count))
    due = count == ALERT_AFTER or (count > ALERT_AFTER and (count - ALERT_AFTER) % ALERT_REPEAT == 0)
    if due and isinstance(notify_command, list) and notify_command:
        try:
            subprocess.run([str(part) for part in notify_command] + [ALERT_TEXT], timeout=30,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass


def run():
    os.umask(0o077)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / 'run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('already running')
            return 0
        notify_command = None
        try:
            folder_id, inbox, notify_command = load_settings()
            rclone_config = str(STATE / 'rclone.conf')
            # Initial request makes rclone refresh and persist an expired token.
            subprocess.run([RCLONE, '--config', rclone_config, '--retries', '1',
                            '--low-level-retries', '1', 'lsjson', REMOTE + ':',
                            '--max-depth', '1'], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True, timeout=90)
            result = subprocess.run([RCLONE, '--config', rclone_config, 'config', 'dump'],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    check=True, timeout=15)
            config = json.loads(result.stdout)[REMOTE]
            token_data = json.loads(config['token'])
            token = token_data['access_token']
            if config.get('scope') != 'drive.readonly' or config.get('root_folder_id') != folder_id:
                raise ValueError('unexpected remote configuration')
            check_reauth(token_data, notify_command)
            counts = drive_pull.sync_folder(drive_pull.DriveClient(token), folder_id, inbox)
        except (OSError, subprocess.SubprocessError, ValueError, KeyError,
                TypeError, drive_pull.DriveError):
            print('sync failed; check authentication, network, inbox access and config.json', file=sys.stderr)
            record_result(False, notify_command)
            return 2
        record_result(True, notify_command)
        print(' '.join('%s=%d' % (key, counts[key]) for key in
                       ('created', 'duplicate', 'conflict', 'skipped', 'failed')))
        return 1 if counts['conflict'] or counts['failed'] else 0


if __name__ == '__main__':
    print(datetime.now().astimezone().isoformat(timespec='seconds'), end=' ')
    raise SystemExit(run())
