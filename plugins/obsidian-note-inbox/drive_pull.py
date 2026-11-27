#!/usr/bin/env python3
"""Pull Markdown from one Google Drive folder into an explicit local inbox.

This is a one-shot, read-only importer. OAuth provisioning and refresh are external.
"""

import argparse
from collections import Counter
import hashlib
import json
import os
import re
import sys
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

import note_inbox

API_ROOT = 'https://www.googleapis.com/drive/v3/files'
ALLOWED_MIME = {'text/markdown', 'text/plain', 'application/octet-stream'}
MAX_LIST_BYTES = 1024 * 1024
MAX_PAGES = 50
MAX_FILES = 5000
ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,200}$')


class DriveError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DriveClient:
    def __init__(self, token):
        if not token or not re.fullmatch(r'[A-Za-z0-9._~+/-]+={0,2}', token):
            raise DriveError('invalid token')
        self._token = token
        self._opener = build_opener(NoRedirect())

    def _get(self, url, limit):
        request = Request(url, headers={'Authorization': 'Bearer ' + self._token}, method='GET')
        try:
            with self._opener.open(request, timeout=30) as response:
                if response.status != 200:
                    raise DriveError('unexpected HTTP status')
                data = response.read(limit + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise DriveError('Drive request failed') from exc
        if len(data) > limit:
            raise DriveError('response exceeds size limit')
        return data

    def _json(self, url):
        try:
            result = json.loads(self._get(url, MAX_LIST_BYTES))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DriveError('invalid Drive response') from exc
        if not isinstance(result, dict):
            raise DriveError('invalid Drive response')
        return result

    def list_files(self, folder_id):
        files, page_token, seen_tokens = [], None, set()
        for _ in range(MAX_PAGES):
            params = {'q': "'%s' in parents and trashed = false" % folder_id,
                      'fields': 'nextPageToken,incompleteSearch,files(id,name,mimeType,parents,size,md5Checksum,version,trashed)',
                      'pageSize': '100'}
            if page_token:
                params['pageToken'] = page_token
            page = self._json(API_ROOT + '?' + urlencode(params))
            entries = page.get('files')
            if page.get('incompleteSearch') or not isinstance(entries, list):
                raise DriveError('incomplete Drive listing')
            files.extend(entries)
            if len(files) > MAX_FILES:
                raise DriveError('too many Drive entries')
            page_token = page.get('nextPageToken')
            if page_token is None:
                return files
            if not isinstance(page_token, str) or not page_token or page_token in seen_tokens:
                raise DriveError('invalid Drive page token')
            seen_tokens.add(page_token)
        raise DriveError('too many Drive pages')

    def metadata(self, file_id):
        fields = 'id,name,mimeType,parents,size,md5Checksum,version,trashed'
        return self._json(API_ROOT + '/' + quote(file_id, safe='') + '?' + urlencode({'fields': fields}))

    def content(self, file_id):
        return self._get(API_ROOT + '/' + quote(file_id, safe='') + '?alt=media', note_inbox.MAX_NOTE_BYTES)


def valid_meta(meta, folder_id):
    if (not isinstance(meta, dict) or not isinstance(meta.get('id'), str) or
            not ID_RE.fullmatch(meta['id'])):
        return False
    if meta.get('parents') != [folder_id] or meta.get('trashed', False):
        return False
    if meta.get('mimeType') not in ALLOWED_MIME or not isinstance(meta.get('name'), str):
        return False
    try:
        note_inbox.validate_filename(meta['name'])
        size = int(meta.get('size', -1))
    except (ValueError, TypeError, UnicodeError, note_inbox.InvalidInput):
        return False
    return 0 < size <= note_inbox.MAX_NOTE_BYTES and isinstance(meta.get('version'), str) and meta['version'].isdigit()


def sync_folder(client, folder_id, inbox):
    if not ID_RE.fullmatch(folder_id):
        raise DriveError('invalid folder id')
    # Validate destination even when the remote folder is empty.
    directory_fd = note_inbox.open_directory(inbox)
    os.close(directory_fd)
    folder = client.metadata(folder_id)
    if (folder.get('id') != folder_id or folder.get('mimeType') != 'application/vnd.google-apps.folder'
            or folder.get('trashed', False)):
        raise DriveError('inaccessible Drive folder')
    entries = client.list_files(folder_id)
    counts = Counter(created=0, duplicate=0, conflict=0, skipped=0, failed=0)
    candidates = []
    for item in entries:
        if valid_meta(item, folder_id):
            candidates.append(item)
        else:
            counts['skipped'] += 1
    # Conservative name matching works on case-insensitive and Unicode-normalizing filesystems.
    def key(item):
        return unicodedata.normalize('NFC', item['name']).casefold()
    names = Counter(key(item) for item in candidates)
    for item in candidates:
        if names[key(item)] > 1:
            counts['conflict'] += 1
            continue
        try:
            before = client.metadata(item['id'])
            if (not valid_meta(before, folder_id) or before.get('id') != item['id'] or
                    before.get('name') != item['name']):
                counts['skipped'] += 1
                continue
            body = client.content(item['id'])
            after = client.metadata(item['id'])
            if (not valid_meta(after, folder_id) or
                    any(before.get(field) != after.get(field) for field in
                        ('id', 'name', 'mimeType', 'parents', 'size', 'version', 'md5Checksum')) or
                    len(body) != int(before['size'])):
                counts['failed'] += 1
                continue
            checksum = before.get('md5Checksum')
            if checksum is not None and (not re.fullmatch(r'[a-fA-F0-9]{32}', str(checksum)) or
                                         hashlib.md5(body).hexdigest() != checksum.lower()):
                counts['failed'] += 1
                continue
            status = note_inbox.write_note(inbox, before['name'], body)
            counts[status] += 1
        except note_inbox.Conflict:
            counts['conflict'] += 1
        except (DriveError, note_inbox.InvalidInput, OSError, UnicodeError):
            counts['failed'] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(description='Import notes from a single Drive folder (read-only).')
    parser.add_argument('--folder-id', required=True, help='Explicit Google Drive folder ID')
    parser.add_argument('--inbox', required=True, help='Existing absolute local directory')
    parser.add_argument('--token-fd', required=True, type=int, help='FD containing a short-lived OAuth token')
    args = parser.parse_args()
    try:
        parts = []
        remaining = 8193
        while remaining:
            part = os.read(args.token_fd, remaining)
            if not part:
                break
            parts.append(part)
            remaining -= len(part)
        token = b''.join(parts)
        if len(token) > 8192:
            raise DriveError('invalid token')
        client = DriveClient(token.decode('ascii').strip())
        counts = sync_folder(client, args.folder_id, args.inbox)
    except (DriveError, note_inbox.InvalidInput, OSError, UnicodeError):
        print('Drive import failed; check authorization and local access', file=sys.stderr)
        return 2
    print(' '.join('%s=%d' % (key, counts[key]) for key in ('created', 'duplicate', 'conflict', 'skipped', 'failed')))
    return 1 if counts['conflict'] or counts['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
