import contextlib
import importlib.util
import io
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location('auto_pull', Path(__file__).resolve().parents[1] / 'auto_pull.py')
auto_pull = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auto_pull)

FOLDER = 'test-folder'
INBOX = '/tmp/test-inbox'


def write_settings(directory, **extra):
    data = {'folder_id': FOLDER, 'inbox': INBOX}
    data.update(extra)
    (Path(directory) / 'config.json').write_text(json.dumps(data))


def remote(scope='drive.readonly', token='secret'):
    return {auto_pull.REMOTE: {'scope': scope, 'root_folder_id': FOLDER,
                               'token': json.dumps({'access_token': token})}}


class AutoPullTests(TestCase):
    def test_refreshes_and_imports_only_selected_folder(self):
        token = 'test-secret-token'
        with TemporaryDirectory() as directory, \
             mock.patch.object(auto_pull, 'STATE', Path(directory)), \
             mock.patch.object(auto_pull.subprocess, 'run', side_effect=[mock.Mock(), mock.Mock(stdout=json.dumps(remote(token=token)).encode())]) as run, \
             mock.patch.object(auto_pull.drive_pull, 'sync_folder', return_value=Counter(created=1)) as sync, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            write_settings(directory)
            self.assertEqual(auto_pull.run(), 0)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(sync.call_args.args[1:], (FOLDER, INBOX))
        self.assertNotIn(token, output.getvalue())

    def test_bad_scope_fails_without_import(self):
        with TemporaryDirectory() as directory, \
             mock.patch.object(auto_pull, 'STATE', Path(directory)), \
             mock.patch.object(auto_pull.subprocess, 'run', side_effect=[mock.Mock(), mock.Mock(stdout=json.dumps(remote(scope='drive')).encode())]), \
             mock.patch.object(auto_pull.drive_pull, 'sync_folder') as sync, \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            write_settings(directory)
            self.assertEqual(auto_pull.run(), 2)
        sync.assert_not_called()
        self.assertNotIn('secret', errors.getvalue())

    def test_missing_settings_fails_before_network(self):
        with TemporaryDirectory() as directory, \
             mock.patch.object(auto_pull, 'STATE', Path(directory)), \
             mock.patch.object(auto_pull.subprocess, 'run') as run, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(auto_pull.run(), 2)
        run.assert_not_called()

    def test_alerts_once_after_repeated_failures_and_resets(self):
        alerts = []

        def fake_run(command, **kwargs):
            if command[0] == 'alert':
                alerts.append(command)
                return mock.Mock()
            raise subprocess.CalledProcessError(1, command)

        with TemporaryDirectory() as directory, \
             mock.patch.object(auto_pull, 'STATE', Path(directory)), \
             mock.patch.object(auto_pull.subprocess, 'run', side_effect=fake_run), \
             contextlib.redirect_stderr(io.StringIO()):
            write_settings(directory, notify_command=['alert'])
            for _ in range(auto_pull.ALERT_AFTER + 2):
                self.assertEqual(auto_pull.run(), 2)
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0][-1], auto_pull.ALERT_TEXT)
            auto_pull.record_result(True, ['alert'])
            self.assertFalse((Path(directory) / 'failures').exists())

    def test_reminds_once_a_day_before_token_expiry(self):
        calls = []
        day = 86400
        start = datetime(2026, 1, 1, 12, 0).timestamp()  # local noon
        with TemporaryDirectory() as directory, \
             mock.patch.object(auto_pull, 'STATE', Path(directory)), \
             mock.patch.object(auto_pull.subprocess, 'run', side_effect=lambda command, **kw: calls.append(command)):
            auto_pull.check_reauth({'refresh_token': 'r1'}, ['alert'], now=start)
            auto_pull.check_reauth({'refresh_token': 'r1'}, ['alert'], now=start + 5 * day)
            self.assertEqual(calls, [])
            auto_pull.check_reauth({'refresh_token': 'r1'}, ['alert'], now=start + 6 * day)
            auto_pull.check_reauth({'refresh_token': 'r1'}, ['alert'], now=start + 6 * day + 300)
            self.assertEqual(len(calls), 1)
            self.assertIn('/drive-reauth', calls[0][-1])
            stored = (Path(directory) / 'reauth.json').read_text()
            self.assertNotIn('r1', stored)
            auto_pull.check_reauth({'refresh_token': 'r2'}, ['alert'], now=start + 6 * day + 600)
            self.assertFalse(json.loads((Path(directory) / 'reauth.json').read_text())['reminded'])

    def test_reminder_waits_for_daytime(self):
        calls = []
        night = datetime(2026, 1, 1, 3, 0).timestamp()  # local 03:00
        with TemporaryDirectory() as directory, \
             mock.patch.object(auto_pull, 'STATE', Path(directory)), \
             mock.patch.object(auto_pull.subprocess, 'run', side_effect=lambda command, **kw: calls.append(command)):
            auto_pull.check_reauth({'refresh_token': 'r'}, ['alert'], now=night)
            auto_pull.check_reauth({'refresh_token': 'r'}, ['alert'], now=night + 6 * 86400)
            self.assertEqual(calls, [])
            auto_pull.check_reauth({'refresh_token': 'r'}, ['alert'], now=night + 6 * 86400 + 6 * 3600)
            self.assertEqual(len(calls), 1)
