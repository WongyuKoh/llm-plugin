import concurrent.futures
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'note_inbox.py'


class NoteInboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # macOS commonly exposes /var through a system symlink.
        self.root = Path(self.temp.name).resolve()
        self.inbox = self.root / 'inbox'
        self.inbox.mkdir()

    def run_inbox(self, name='학습.md', content=b'# Example\n', inbox=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), '--inbox', str(inbox or self.inbox), '--name', name],
            input=content, capture_output=True, timeout=10,
        )

    def assert_no_staging_files(self):
        self.assertEqual(list(self.inbox.glob('.note-inbox-*.md')), [])

    def test_create_and_repeat_same_content(self):
        first = self.run_inbox()
        self.assertEqual((first.returncode, first.stdout), (0, b'created\n'))
        path = self.inbox / '학습.md'
        self.assertEqual(path.read_bytes(), b'# Example\n')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        second = self.run_inbox()
        self.assertEqual((second.returncode, second.stdout), (0, b'duplicate\n'))
        self.assertEqual(path.read_bytes(), b'# Example\n')
        self.assert_no_staging_files()

    def test_different_content_never_overwrites(self):
        path = self.inbox / '학습.md'
        path.write_bytes(b'original')
        result = self.run_inbox(content=b'changed')
        self.assertEqual(result.returncode, 3)
        self.assertEqual(path.read_bytes(), b'original')
        self.assert_no_staging_files()

    def test_reject_unsafe_names_and_content(self):
        for name in ('../escape.md', 'folder/note.md', 'folder\\note.md', '.hidden.md',
                     'note.txt', 'bad:name.md', 'note.md\n'):
            with self.subTest(name=name):
                self.assertEqual(self.run_inbox(name=name).returncode, 2)
        for content in (b'', b' \n\t', b'\xff', b'\x00', b'a' * (256 * 1024 + 1)):
            with self.subTest(length=len(content), prefix=content[:3]):
                self.assertEqual(self.run_inbox(content=content).returncode, 2)
        self.assertEqual(list(self.inbox.iterdir()), [])
        self.assertFalse((self.root / 'escape.md').exists())

    def test_symlink_destination_is_never_followed(self):
        victim = self.root / 'victim.md'
        victim.write_bytes(b'original')
        (self.inbox / '학습.md').symlink_to(victim)
        result = self.run_inbox(content=b'original')
        self.assertEqual(result.returncode, 3)
        self.assertEqual(victim.read_bytes(), b'original')
        self.assert_no_staging_files()

    def test_reject_symlink_directories_and_traversal(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.inbox, target_is_directory=True)
        self.assertNotEqual(self.run_inbox(inbox=alias).returncode, 0)
        nested = self.root / 'nested'
        nested.mkdir()
        (nested / 'link').symlink_to(self.root, target_is_directory=True)
        self.assertNotEqual(self.run_inbox(inbox=nested / 'link' / 'inbox').returncode, 0)
        self.assertNotEqual(self.run_inbox(inbox=str(self.root) + '/nested/../inbox').returncode, 0)
        self.assertEqual(list(self.inbox.iterdir()), [])

    def test_concurrent_matching_submissions_are_idempotent(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(lambda _: self.run_inbox(), range(6)))
        self.assertTrue(all(result.returncode == 0 for result in results))
        self.assertEqual(sum(result.stdout == b'created\n' for result in results), 1)
        self.assertEqual(sum(result.stdout == b'duplicate\n' for result in results), 5)
        self.assertEqual((self.inbox / '학습.md').read_bytes(), b'# Example\n')
        self.assert_no_staging_files()

    def test_same_length_different_concurrent_submissions_conflict(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda body: self.run_inbox(content=body), [b'# AAA\n', b'# BBB\n']))
        self.assertEqual(sorted(result.returncode for result in results), [0, 3])
        self.assertIn((self.inbox / '학습.md').read_bytes(), [b'# AAA\n', b'# BBB\n'])
        self.assert_no_staging_files()

    def test_output_does_not_include_note_body(self):
        secret = b'private-body-example'
        result = self.run_inbox(content=secret)
        self.assertNotIn(secret, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
