import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

spec = importlib.util.spec_from_file_location('notify', Path(__file__).resolve().parents[1] / 'notify.py')
notify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify)


class FindTodoTests(TestCase):
    def test_last_line_marker(self):
        self.assertEqual(notify.find_todo('결과입니다.\n\n🔔 할 일: **PR**을 검토해 주세요'), 'PR을 검토해 주세요')

    def test_ignores_examples_and_placeholders(self):
        self.assertIsNone(notify.find_todo('규칙: `🔔 할 일: 한 줄`을 쓴다'))
        self.assertIsNone(notify.find_todo('🔔 할 일: <한 줄 요약>'))

    def test_only_last_three_lines(self):
        self.assertIsNone(notify.find_todo('🔔 할 일: 오래된 줄\n가\n나\n다'))


class EventTests(TestCase):
    def test_stop_reads_transcript(self):
        with TemporaryDirectory() as directory:
            transcript = Path(directory) / 't.jsonl'
            lines = [{'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': '중간'}]}},
                     {'type': 'user', 'message': {'content': 'x'}},
                     {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': '끝\n🔔 할 일: 재인증'}]}}]
            transcript.write_text('\n'.join(json.dumps(line, ensure_ascii=False) for line in lines))
            event = {'hook_event_name': 'Stop', 'transcript_path': str(transcript), 'cwd': '/a/proj'}
            self.assertEqual(notify.from_claude(event), ('action', '재인증', 'proj'))
            self.assertIsNone(notify.from_claude(dict(event, stop_hook_active=True)))
            self.assertIsNone(notify.from_claude(dict(event, agent_id='sub')))

    def test_question_and_permission(self):
        ask = {'hook_event_name': 'PreToolUse', 'tool_name': 'AskUserQuestion', 'cwd': '/p',
               'tool_input': {'questions': [{'question': '어느 쪽?'}]}}
        self.assertEqual(notify.from_claude(ask), ('question', '어느 쪽?', 'p'))
        prompt = {'hook_event_name': 'Notification', 'notification_type': 'permission_prompt', 'message': 'Bash'}
        self.assertEqual(notify.from_claude(prompt)[0], 'approval')
        idle = {'hook_event_name': 'Notification', 'notification_type': 'idle_prompt'}
        self.assertIsNone(notify.from_claude(idle))
        self.assertIsNone(notify.from_claude(['not', 'a', 'dict']))

    def test_codex(self):
        done = {'type': 'agent-turn-complete', 'cwd': '/w/app', 'last-assistant-message': '완료\n🔔 할 일: 머지 결정'}
        self.assertEqual(notify.from_codex(done), ('action', '머지 결정', 'app'))
        self.assertIsNone(notify.from_codex(dict(done, **{'last-assistant-message': '완료'})))


class DeliveryTests(TestCase):
    def phone_message(self, conf, kind, text):
        sent = {}

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout):
            sent.update(json.loads(request.data))
            return Response()

        with mock.patch.object(notify.urllib.request, 'urlopen', fake_urlopen):
            result = notify.deliver(kind, text, 'secret-project', 'Claude', 'phone', conf)
        return result, sent

    def test_phone_shows_task_without_project_by_default(self):
        conf = dict(notify.DEFAULTS, ntfy_topic='t')
        result, sent = self.phone_message(conf, 'action', 'PR 리뷰 확인')
        self.assertEqual(result, ['phone'])
        self.assertEqual(sent['message'], 'PR 리뷰 확인')
        self.assertNotIn('secret-project', sent['message'])
        self.assertEqual(sent['priority'], 4)

    def test_phone_project_and_hidden_detail(self):
        conf = dict(notify.DEFAULTS, ntfy_topic='t', phone_project=True)
        _, sent = self.phone_message(conf, 'action', '내용')
        self.assertEqual(sent['message'], 'Claude · secret-project: 내용')
        _, sent = self.phone_message(dict(notify.DEFAULTS, ntfy_topic='t', phone_detail=False), 'action', '비공개')
        self.assertNotIn('비공개', sent['message'])
        _, sent = self.phone_message(dict(notify.DEFAULTS, ntfy_topic='t', phone_detail=False), 'alert', 'Drive 동기화 실패')
        self.assertEqual(sent['message'], 'Drive 동기화 실패')

    def test_dedupe(self):
        with TemporaryDirectory() as directory, mock.patch.object(notify, 'STATE', Path(directory) / 's.json'):
            self.assertFalse(notify.seen_recently('k', 60))
            self.assertTrue(notify.seen_recently('k', 60))
            self.assertFalse(notify.seen_recently('other', 60))


class InstallTests(TestCase):
    def test_install_and_uninstall_keep_other_settings(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            settings = root / 'settings.json'
            codex = root / 'config.toml'
            other = {'hooks': [{'type': 'command', 'command': 'other-hook'}]}
            settings.write_text(json.dumps({'model': 'x', 'hooks': {'Stop': [other]}}))
            codex.write_text('notify = ["/app/client", "turn-ended"]\nmodel = "m"\n\n[desktop]\nx = 1\n')
            with mock.patch.multiple(notify, CLAUDE_SETTINGS=settings, CODEX_CONFIG=codex, CONF_DIR=root,
                                     CONF=root / 'notify.json', STATE=root / 'state.json'), \
                 mock.patch('builtins.print'):
                notify.install()
                notify.install()  # 두 번 실행해도 중복되지 않는다
                data = json.loads(settings.read_text())
                self.assertEqual(data['model'], 'x')
                self.assertEqual(len(data['hooks']['Stop']), 2)
                self.assertEqual(data['hooks']['PreToolUse'][0]['matcher'], 'AskUserQuestion')
                first = codex.read_text().split('\n')[0]
                self.assertIn(str(notify.SCRIPT), first)
                self.assertTrue(first.endswith('"--chain", "/app/client", "turn-ended"]'))
                conf = json.loads((root / 'notify.json').read_text())
                self.assertTrue(conf['ntfy_topic'].startswith('llm-'))

                notify.uninstall()
                data = json.loads(settings.read_text())
                self.assertEqual(data['hooks'], {'Stop': [other]})
                self.assertEqual(codex.read_text().split('\n')[0], 'notify = ["/app/client", "turn-ended"]')

    def test_codex_command_runs_chain_first(self):
        payload = json.dumps({'type': 'agent-turn-complete', 'thread-id': 't', 'last-assistant-message': 'x'})
        with mock.patch.object(notify.subprocess, 'Popen') as popen:
            notify.main(['codex', '--chain', '/app/client', 'turn-ended', payload])
        self.assertEqual(popen.call_args_list[0].args[0], ['/app/client', 'turn-ended', payload])
        self.assertEqual(popen.call_count, 1)  # 할 일 표시가 없으면 알림을 보내지 않는다
