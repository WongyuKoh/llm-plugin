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

    def test_numbered_and_bulleted_lists(self):
        message = '결과입니다.\n\n🔔 할 일:\n1. T3를 **완전히** 끄고 다시 열기\n2. 메뉴 막대 확인\n'
        self.assertEqual(notify.find_todos(message), ['T3를 완전히 끄고 다시 열기', '메뉴 막대 확인'])
        self.assertEqual(notify.find_todo(message), '1. T3를 완전히 끄고 다시 열기\n2. 메뉴 막대 확인')
        self.assertEqual(notify.find_todos('끝\n🔔 할 일:\n\n- 가\n- 나'), ['가', '나'])
        self.assertEqual(notify.find_todos('끝\n🔔 할 일\n1) 가'), ['가'])

    def test_list_then_short_trailer_and_old_markers(self):
        self.assertEqual(notify.find_todos('🔔 할 일:\n1. 가\n2. 나\n덧붙임'), ['가', '나'])
        self.assertEqual(notify.find_todos('🔔 할 일:\n1. 가\n다\n라\n마'), [])
        self.assertEqual(notify.find_todos('🔔 할 일이 있습니다'), [])

    def test_ignores_code_blocks(self):
        self.assertEqual(notify.find_todos('예시:\n```\n🔔 할 일: 예시\n```'), [])
        self.assertEqual(notify.find_todos('```\n🔔 할 일:\n1. 예시\n```\n끝'), [])


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


class TodoListTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        root = Path(self.directory.name)
        self.patch = mock.patch.multiple(notify, CONF_DIR=root, TODOS=root / 'todos.json',
                                         TODOS_LOCK=root / 'todos.lock', WAITING=root / 'todos-waiting',
                                         T3_DB=root / 'missing.sqlite')
        self.patch.start()
        self.root = root

    def tearDown(self):
        self.patch.stop()
        self.directory.cleanup()

    def items(self):
        return notify.load_todos()['items']

    def stop(self, session, text):
        notify.track_claude({'hook_event_name': 'Stop', 'session_id': session, 'cwd': '/w/app',
                             'last_assistant_message': text})

    def test_stop_replaces_session_items_and_keeps_ids(self):
        self.stop('s1', '끝\n🔔 할 일:\n1. 가\n2. 나')
        self.stop('s2', '끝\n🔔 할 일: 다른 세션')
        first = {item['text']: item['id'] for item in self.items()}
        self.assertEqual(sorted(first), ['가', '나', '다른 세션'])
        self.stop('s1', '끝\n🔔 할 일:\n1. 나\n2. 라')
        texts = [(item['session'], item['text']) for item in self.items()]
        self.assertEqual(sorted(texts), [('s1', '나'), ('s1', '라'), ('s2', '다른 세션')])
        self.assertEqual({item['text']: item['id'] for item in self.items()}['나'], first['나'])
        self.stop('s1', '모두 끝났습니다.')
        self.assertEqual([item['text'] for item in self.items()], ['다른 세션'])

    def test_user_reply_keeps_todos_until_the_reply_ends(self):
        # 하나에만 답해도 나머지가 사라지지 않게, 메시지를 받을 때는 할 일을 지우지 않는다.
        self.stop('s1', '🔔 할 일:\n1. 가\n2. 나\n3. 다')
        notify.track_claude({'hook_event_name': 'PermissionRequest', 'tool_name': 'Bash', 'session_id': 's1'})
        notify.track_claude({'hook_event_name': 'UserPromptSubmit', 'session_id': 's1', 'prompt': '가는 A로 해'})
        self.assertEqual([item['text'] for item in self.items()], ['가', '나', '다'])  # 승인 대기만 지워짐
        self.stop('s1', '가를 A로 했습니다.\n\n🔔 할 일:\n1. 나\n2. 다')
        self.assertEqual([item['text'] for item in self.items()], ['나', '다'])

    def test_question_and_approval_clear_after_tool_runs(self):
        ask = {'hook_event_name': 'PreToolUse', 'tool_name': 'AskUserQuestion', 'session_id': 's1', 'cwd': '/p',
               'tool_input': {'questions': [{'question': '어느 쪽?'}, {'question': '언제?'}]}}
        notify.track_claude(ask)
        notify.track_claude({'hook_event_name': 'PermissionRequest', 'tool_name': 'Bash', 'session_id': 's1'})
        notify.track_claude({'hook_event_name': 'Notification', 'notification_type': 'permission_prompt',
                             'session_id': 's1', 'message': 'Bash 권한'})
        self.assertEqual([item['kind'] for item in self.items()], ['question', 'question', 'approval'])
        self.assertTrue(notify.WAITING.exists())
        notify.track_claude({'hook_event_name': 'PostToolUse', 'tool_name': 'Bash', 'session_id': 's1'})
        self.assertEqual([item['text'] for item in self.items()], ['어느 쪽?', '언제?'])
        notify.track_claude(dict(ask, hook_event_name='PostToolUse'))
        self.assertEqual(self.items(), [])
        self.assertFalse(notify.WAITING.exists())

    def test_subagents_and_missing_session_are_ignored(self):
        notify.track_claude({'hook_event_name': 'Stop', 'session_id': 's', 'agent_id': 'sub',
                             'last_assistant_message': '🔔 할 일: 하위'})
        notify.track_claude({'hook_event_name': 'Stop', 'last_assistant_message': '🔔 할 일: 세션 없음'})
        self.assertEqual(self.items(), [])

    def test_codex_turn_replaces_thread_items(self):
        payload = {'type': 'agent-turn-complete', 'thread-id': 't', 'cwd': '/w/app',
                   'last-assistant-message': '완료\n🔔 할 일:\n- 머지 결정\n- 배포 확인'}
        notify.track_codex(payload)
        self.assertEqual([(item['agent'], item['text']) for item in self.items()],
                         [('Codex', '머지 결정'), ('Codex', '배포 확인')])
        notify.track_codex(dict(payload, **{'last-assistant-message': '끝'}))
        self.assertEqual(self.items(), [])

    def test_todo_command_done_by_number_and_id(self):
        self.stop('s1', '🔔 할 일:\n1. 가\n2. 나\n3. 다')
        with mock.patch('builtins.print'):
            self.assertEqual(notify.main(['todo', 'done', '2']), 0)
            self.assertEqual([item['text'] for item in self.items()], ['가', '다'])
            self.assertEqual(notify.main(['todo', 'done', self.items()[0]['id']]), 0)
            self.assertEqual(notify.main(['todo', 'done', 'nope']), 1)
        self.assertEqual([item['text'] for item in self.items()], ['다'])

    def test_send_adds_alert_once_and_hook_send_does_not(self):
        with mock.patch.object(notify, 'deliver', return_value=[]), mock.patch('builtins.print'):
            notify.main(['send', '--kind', 'alert', 'Drive 동기화 실패'])
            notify.main(['send', '--kind', 'alert', 'Drive 동기화 실패'])
            notify.main(['send', '--kind', 'action', '--no-list', '훅이 보낸 알림'])
        self.assertEqual([(item['kind'], item['text']) for item in self.items()], [('alert', 'Drive 동기화 실패')])

    def test_parse_recommend_and_choices(self):
        self.assertEqual(notify.parse_todo('실패한 테스트 고치기 (추천: 타임아웃을 늘려 다시 실행)'),
                         ('실패한 테스트 고치기', '타임아웃을 늘려 다시 실행', []))
        body, recommend, choices = notify.parse_todo('머지 방식 정하기 (선택: squash(추천) / rebase / merge)')
        self.assertEqual((body, recommend), ('머지 방식 정하기', ''))
        self.assertEqual(choices, [{'label': 'squash', 'recommended': True}, {'label': 'rebase', 'recommended': False},
                                   {'label': 'merge', 'recommended': False}])
        self.assertEqual(notify.parse_todo('T3 다시 시작하기'), ('T3 다시 시작하기', '', []))
        self.assertEqual(notify.parse_todo('하나뿐 (선택: A)'), ('하나뿐 (선택: A)', '', []))
        self.assertEqual(notify.parse_todo('경로 고르기 (선택: a/b 추천 / c/d)')[2],
                         [{'label': 'a/b', 'recommended': True}, {'label': 'c/d', 'recommended': False}])

    def test_stop_stores_hints_and_ask_stores_options(self):
        self.stop('s1', '🔔 할 일:\n1. 머지 방식 정하기 (선택: squash(추천) / rebase)\n2. 재시작 (추천: 지금 다시 시작)')
        first, second = self.items()
        self.assertEqual((first['text'], [c['label'] for c in first['choices']]), ('머지 방식 정하기', ['squash', 'rebase']))
        self.assertEqual((second['text'], second['recommend']), ('재시작', '지금 다시 시작'))
        notify.track_claude({'hook_event_name': 'PreToolUse', 'tool_name': 'AskUserQuestion', 'session_id': 's2',
                             'tool_input': {'questions': [{'question': '어느 쪽?', 'multiSelect': True,
                                                           'options': [{'label': 'A'}, {'label': 'B'}]}]}})
        question = self.items()[-1]
        self.assertEqual(([c['label'] for c in question['choices']], question['multi']), (['A', 'B'], True))

    def test_act_sends_to_t3_thread(self):
        self.stop('s1', '🔔 할 일: 머지 방식 정하기 (선택: squash(추천) / rebase)')
        item_id = self.items()[0]['id']
        with mock.patch.object(notify.subprocess, 'run') as run:
            self.assertEqual(notify.act(item_id, 'rebase')[0], 1)  # T3 세션 id가 없으면 보내지 않는다
            run.assert_not_called()
            self.assertEqual(self.items()[0]['state'], 'error')
            data = notify.load_todos()
            data['items'][0]['thread'] = 'thread-1'
            notify.save_json(notify.TODOS, data)
            run.return_value = mock.Mock(returncode=0, stdout='{"delivery": "queued"}', stderr='')
            self.assertEqual(notify.act(item_id, 'rebase'), (0, '보냄'))
        command, kwargs = run.call_args.args[0], run.call_args.kwargs
        self.assertEqual(command[1:], ['thread', 'send', '--json', 'thread-1', '-'])
        self.assertIn('- 선택: rebase', kwargs['input'])
        self.assertEqual((self.items()[0]['state'], self.items()[0]['note']), ('sent', '세션이 바빠 다음 차례로 넣었습니다.'))

    def test_act_message_lists_other_todos_of_the_session(self):
        self.stop('s1', '🔔 할 일:\n1. 가 (추천: 가 하기)\n2. 나 (선택: B(추천) / C)\n3. 다')
        self.stop('s2', '🔔 할 일: 다른 세션 일')
        data = notify.load_todos()
        for item in data['items']:
            item['thread'] = 'thread-' + item['session']
        notify.save_json(notify.TODOS, data)
        ok = mock.Mock(returncode=0, stdout='{"delivery": "sent"}', stderr='')
        with mock.patch.object(notify.subprocess, 'run', return_value=ok) as run:
            notify.act(self.items()[0]['id'])
        message = run.call_args.kwargs['input']
        self.assertIn('- 할 일: 가\n- 추천: 가 하기', message)
        self.assertTrue(message.endswith('다시 적어 주세요.\n1. 나 (선택: B(추천) / C)\n2. 다'))
        self.assertNotIn('다른 세션 일', message)
        self.assertEqual(len(self.items()), 4)  # 맡겨도 목록은 그대로, 응답이 끝날 때 바뀐다

    def test_act_reports_t3_errors(self):
        notify.add_todo('action', '맡길 일')
        data = notify.load_todos()
        data['items'][0].update(thread='thread-1', recommend='추천대로')
        notify.save_json(notify.TODOS, data)
        failed = mock.Mock(returncode=1, stdout='', stderr='Thread thread-1 was not found.\n자세한 설명')
        with mock.patch.object(notify.subprocess, 'run', return_value=failed) as run:
            self.assertEqual(notify.act(data['items'][0]['id']), (1, 'Thread thread-1 was not found.'))
        self.assertIn('- 추천: 추천대로', run.call_args.kwargs['input'])
        self.assertEqual(self.items()[0]['state'], 'error')

    def test_broken_file_does_not_break_hooks(self):
        notify.TODOS.write_text('{깨짐')
        self.stop('s1', '🔔 할 일: 새 일')
        self.assertEqual([item['text'] for item in self.items()], ['새 일'])


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
                self.assertIn('UserPromptSubmit', data['hooks'])
                post = data['hooks']['PostToolUse'][0]['hooks'][0]['command']
                self.assertTrue(post.startswith("[ ! -e '%s' ] || exec " % notify.WAITING))
                first = codex.read_text().split('\n')[0]
                self.assertIn(str(notify.SCRIPT), first)
                self.assertTrue(first.endswith('"--chain", "/app/client", "turn-ended"]'))
                conf = json.loads((root / 'notify.json').read_text())
                self.assertTrue(conf['ntfy_topic'].startswith('llm-'))

                notify.uninstall()
                data = json.loads(settings.read_text())
                self.assertEqual(data['hooks'], {'Stop': [other]})
                self.assertEqual(codex.read_text().split('\n')[0], 'notify = ["/app/client", "turn-ended"]')

    def test_install_keeps_codex_line_that_wraps_this_script(self):
        # Codex 앱이 기존 notify를 '--previous-notify'로 감싼 경우. 경로가 '\/'로 이스케이프돼 있어도 이미 등록된 것으로 본다.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            inner = json.dumps(['/usr/bin/python3', str(notify.SCRIPT), 'codex']).replace('/', '\\/')
            line = 'notify = ' + json.dumps(['/app/client', 'turn-ended', '--previous-notify', inner])
            codex = root / 'config.toml'
            codex.write_text(line + '\n')
            with mock.patch.multiple(notify, CLAUDE_SETTINGS=root / 'settings.json', CODEX_CONFIG=codex,
                                     CONF_DIR=root, CONF=root / 'notify.json', STATE=root / 'state.json'), \
                 mock.patch('builtins.print'):
                notify.install()
            self.assertEqual(codex.read_text(), line + '\n')

    def test_codex_command_runs_chain_first(self):
        payload = json.dumps({'type': 'agent-turn-complete', 'thread-id': 't', 'last-assistant-message': 'x'})
        with mock.patch.object(notify.subprocess, 'Popen') as popen:
            notify.main(['codex', '--chain', '/app/client', 'turn-ended', payload])
        self.assertEqual(popen.call_args_list[0].args[0], ['/app/client', 'turn-ended', payload])
        self.assertEqual(popen.call_count, 1)  # 할 일 표시가 없으면 알림을 보내지 않는다
