import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import drive_pull

FOLDER = 'test_folder_123'


def metadata(name='note.md', file_id='file_123', body=b'# Example\n'):
    return {'id': file_id, 'name': name, 'mimeType': 'text/markdown', 'parents': [FOLDER],
            'size': str(len(body)), 'version': '1', 'md5Checksum': hashlib.md5(body).hexdigest()}


class FakeDrive:
    def __init__(self, records):
        self.records = records
        self.content_requests = []
        self.fail = set()
        self.before_after = {}
        self.metadata_calls = {}

    def list_files(self, folder):
        return [record[0].copy() for record in self.records]

    def metadata(self, file_id):
        if file_id == FOLDER:
            return {'id': FOLDER, 'mimeType': 'application/vnd.google-apps.folder', 'trashed': False}
        self.metadata_calls[file_id] = self.metadata_calls.get(file_id, 0) + 1
        if file_id in self.fail:
            raise drive_pull.DriveError('redacted')
        if file_id in self.before_after:
            before, after = self.before_after[file_id]
            return (before if self.metadata_calls[file_id] == 1 else after).copy()
        return next(item.copy() for item, _ in self.records if item['id'] == file_id)

    def content(self, file_id):
        self.content_requests.append(file_id)
        if file_id in self.fail:
            raise drive_pull.DriveError('redacted')
        return next(body for item, body in self.records if item['id'] == file_id)


class DrivePullTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.inbox = str(Path(self.tmp.name).resolve())

    def sync(self, records):
        client = FakeDrive(records)
        return client, drive_pull.sync_folder(client, FOLDER, self.inbox)

    def test_new_and_idempotent_import(self):
        record = (metadata(), b'# Example\n')
        client, result = self.sync([record])
        self.assertEqual(result['created'], 1)
        self.assertEqual((Path(self.inbox) / 'note.md').read_bytes(), record[1])
        self.assertEqual(drive_pull.sync_folder(client, FOLDER, self.inbox)['duplicate'], 1)

    def test_remote_update_preserves_local_note(self):
        original = b'# Example\n'
        client = FakeDrive([(metadata(body=original), original)])
        drive_pull.sync_folder(client, FOLDER, self.inbox)
        update = b'# Updated\n'
        result = drive_pull.sync_folder(FakeDrive([(metadata(body=update), update)]), FOLDER, self.inbox)
        self.assertEqual(result['conflict'], 1)
        self.assertEqual((Path(self.inbox) / 'note.md').read_bytes(), original)

    def test_conflicting_remote_names_are_skipped_before_download(self):
        client, result = self.sync([(metadata('NOTE.md', 'abc'), b'# Example\n'),
                                    (metadata('note.md', 'def'), b'# Example\n')])
        self.assertEqual(result['conflict'], 2)
        self.assertEqual(client.content_requests, [])
        self.assertEqual(list(Path(self.inbox).iterdir()), [])

    def test_disallowed_parents_names_types_and_sizes_never_download(self):
        items = []
        for field, value in [('parents', ['other_folder']), ('name', '../escape.md'),
                             ('mimeType', 'application/vnd.google-apps.shortcut'),
                             ('size', str(drive_pull.note_inbox.MAX_NOTE_BYTES + 1)),
                             ('trashed', True)]:
            item = metadata(file_id='id' + str(len(items)))
            item[field] = value
            items.append((item, b'# Example\n'))
        client, result = self.sync(items)
        self.assertEqual(result['skipped'], len(items))
        self.assertEqual(client.content_requests, [])

    def test_changed_during_download_is_never_written(self):
        item = metadata()
        client = FakeDrive([(item, b'# Example\n')])
        client.before_after[item['id']] = (item, {**item, 'version': '2'})
        result = drive_pull.sync_folder(client, FOLDER, self.inbox)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(list(Path(self.inbox).iterdir()), [])

    def test_checksum_mismatch_is_never_written(self):
        item = metadata()
        client, result = self.sync([(item, b'# Mismatch')])
        self.assertEqual(result['failed'], 1)
        self.assertEqual(list(Path(self.inbox).iterdir()), [])

    def test_remote_error_is_reported_without_body_or_token(self):
        client = FakeDrive([(metadata(), b'# Example\n')])
        client.fail.add('file_123')
        result = drive_pull.sync_folder(client, FOLDER, self.inbox)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(list(Path(self.inbox).iterdir()), [])

    def test_invalid_destination_and_folder_fail_closed(self):
        with self.assertRaises(drive_pull.DriveError):
            drive_pull.sync_folder(FakeDrive([]), "foo' or true", self.inbox)
        with self.assertRaises(OSError):
            drive_pull.sync_folder(FakeDrive([]), FOLDER, self.inbox + '/missing')

    def test_inaccessible_folder_cannot_report_empty_success(self):
        class Inaccessible(FakeDrive):
            def metadata(self, file_id):
                raise drive_pull.DriveError('folder is not accessible')
        with self.assertRaises(drive_pull.DriveError):
            drive_pull.sync_folder(Inaccessible([]), FOLDER, self.inbox)

    def test_invalid_utf8_never_written(self):
        body = b'\xff'
        _, result = self.sync([(metadata(body=body), body)])
        self.assertEqual(result['failed'], 1)
        self.assertEqual(list(Path(self.inbox).iterdir()), [])

    def test_auth_header_redirect_disabled_and_only_google_gets(self):
        client = drive_pull.DriveClient('test-token')
        self.assertTrue(any(isinstance(h, drive_pull.NoRedirect) for h in client._opener.handlers))
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return b'{"files":[]}'
        class Opener:
            def open(self, req, timeout):
                self.url = req.full_url
                self.method = req.method
                self.auth = req.get_header('Authorization')
                return Response()
        opener = Opener()
        client._opener = opener
        self.assertEqual(client.list_files(FOLDER), [])
        self.assertTrue(opener.url.startswith('https://www.googleapis.com/drive/v3/files?'))
        self.assertEqual(opener.method, 'GET')
        self.assertEqual(opener.auth, 'Bearer test-token')


if __name__ == '__main__':
    unittest.main()
