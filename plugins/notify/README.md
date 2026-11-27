# 할 일 알림

Claude Code나 Codex 세션에서 사용자가 해야 할 일이 생기면 이 Mac(소리 포함)과 휴대폰([ntfy](https://ntfy.sh))으로 알리고, 맥 메뉴 막대의 할 일 목록에 모읍니다. 목록은 세션이 응답을 마칠 때 그 응답의 할 일로 바뀌고, `완료` 버튼으로도 지울 수 있습니다. Python 표준 라이브러리만 사용합니다.

## 알리는 경우

| 경우 | 출처 |
|---|---|
| ❓ 질문에 답해야 할 때 | Claude `AskUserQuestion`(PreToolUse 훅), 입력 요청 알림 |
| 🔐 승인이 필요할 때 | Claude `PermissionRequest` 훅, 권한 요청 알림 |
| 🔔 할 일이 남았을 때 | 응답 마지막 줄의 `🔔 할 일: …`(Claude Stop 훅, Codex `notify`) |
| ⚠️ 확인이 필요할 때 | Drive 동기화가 약 30분 연속 실패할 때(`obsidian-note-inbox`) |

`🔔 할 일` 표시는 전역 지침(`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`)에 따라 에이전트가 응답 맨 끝에 씁니다. 할 일이 하나면 한 줄, 둘 이상이면 번호 목록입니다.

```text
🔔 할 일: PR 12 머지 여부 결정

🔔 할 일:
1. T3를 완전히 끄고 다시 열기
2. 메뉴 막대의 🔔 할 일을 눌러 목록 확인
```

- `1.`, `1)`, `-` 목록을 읽습니다. 목록 뒤에 다른 줄이 세 줄 이상 있으면 오래된 표시로 보고 무시합니다.
- 인라인 코드와 코드 블록 안의 예시, `<…>` 자리표시는 무시합니다.
- 여러 개면 알림 내용도 번호 목록으로 보냅니다. 같은 알림은 60초 안에 다시 보내지 않습니다.

## 메뉴 막대 할 일 목록

맥 메뉴 막대의 `🔔 할 일 N`이 지금 남은 할 일 개수를 보여 줍니다. 누르면 작업 중인 화면 오른쪽 위에 목록 창이 열립니다.

- 목록은 세션별로 묶이고, 할 일이 최근에 생긴 세션이 위에 옵니다. 묶음 제목은 T3 세션 제목(없으면 프로젝트 이름)입니다.
- 항목마다 종류(질문·승인·할 일·확인), 생긴 시각, `완료` 버튼이 있습니다. `완료`를 누르면 바로 지워집니다.
- T3 세션의 할 일에는 `/handoff`처럼 그 세션에 일을 맡기는 버튼이 하나 더 있습니다.

| 버튼 | 나오는 항목 | 누르면 |
|---|---|---|
| `알아서 진행` | 선택지가 없는 할 일 | 그 세션에 "추천대로(추천이 없으면 알맞게) 진행해 달라"는 메시지를 보냅니다. |
| `선택…` | `(선택: …)`이 붙은 할 일 | 선택지 모달을 띄웁니다. 추천 선택지가 미리 골라져 있고, 직접 입력도 됩니다. 고른 답을 그 세션에 보냅니다. |
| `T3에서 답하기` | 질문·승인 | T3 데스크톱 앱에서 그 세션을 엽니다. 선택지는 목록에도 보여 줍니다. |
| `열기 ↗`(묶음 제목) | T3 세션 묶음 | T3 데스크톱 앱에서 그 세션을 엽니다. |

- 보내기는 T3 명령줄 도구 `~/.t3/bin/t3 thread send`로 합니다. 세션이 바쁘면 진행 중인 작업을 끊지 않고 다음 차례로 들어갑니다. 보낸 항목에는 `맡김`이, 실패하면 이유가 나옵니다.
- 보내는 메시지에는 그 세션의 다른 남은 할 일도 함께 적어, 이번에 끝내지 않은 것을 응답 끝에 다시 적게 합니다. 응답이 끝나면 목록이 그 응답의 할 일로 바뀝니다.
- 질문(`AskUserQuestion`)과 승인은 메뉴 막대에서 바로 답하지 못합니다. T3 명령줄 도구에 대기 중인 질문에 답하는 명령이 없고, 질문이 걸린 세션에 보낸 메시지는 질문에 답할 때까지 대기열에 머물기 때문입니다.
- 세션 열기 링크는 `t3code://threads/<환경 id>/<세션 id>`입니다. 환경 id는 `~/.t3/userdata/environment-id`에서 읽습니다.
- T3 밖 세션(VS Code, 터미널)의 할 일에는 `완료`만 있습니다.

에이전트는 전역 지침에 따라 할 일 끝에 버튼에 쓸 내용을 붙입니다. 사용자만 할 수 있는 일에는 붙이지 않습니다.

```text
🔔 할 일:
1. 실패한 테스트 고치기 (추천: 타임아웃을 30초로 늘려 다시 실행)
2. PR 12 머지 방식 정하기 (선택: squash(추천) / rebase)
3. T3를 완전히 끄고 다시 열기
```

목록에는 괄호 앞 본문만 할 일로 보이고, 추천은 `추천` 줄로, 선택지는 칩으로 보입니다. 선택지 구분은 ` / `이고 `(추천)`이나 ` 추천`을 붙인 선택지가 추천입니다.
- 메뉴 막대 개수와 열린 창은 1초 안에 바뀐 내용을 반영합니다.
- Esc를 누르거나 다른 곳을 클릭하면 창이 닫힙니다. 창 아래 `고정`을 켜면 다른 곳을 눌러도 닫히지 않습니다.

목록은 세션의 진행에 따라 자동으로 바뀝니다.

| 일어난 일 | 목록 변화 |
|---|---|
| 응답이 끝남(Claude `Stop`, Codex `agent-turn-complete`) | 그 세션의 항목을 응답 끝 `🔔 할 일` 목록으로 바꿉니다. 표시가 없으면 그 세션의 항목을 지웁니다. |
| 사용자가 그 세션에 메시지를 보냄(Claude `UserPromptSubmit`) | 그 세션의 질문·승인 항목만 지웁니다. 할 일은 응답이 끝날 때까지 그대로 둡니다. 하나에만 답했는데 나머지까지 사라지지 않게 하기 위해서입니다. |
| 질문(`AskUserQuestion`)이나 승인 요청이 생김 | 질문·승인 항목을 넣습니다. |
| 질문에 답하거나 승인한 도구가 실행됨(Claude `PostToolUse`) | 그 질문·승인 항목을 지웁니다. |
| 다른 프로그램이 `send --kind alert`나 `action`으로 알림(예: Drive 동기화 실패) | 세션 없는 항목으로 넣습니다. `완료`로만 지워집니다. |

- 하위 에이전트(`agent_id`가 있는 이벤트)는 목록에 넣지 않습니다.
- Codex는 `notify`로 응답 끝만 알려 주므로, 사용자가 답할 때가 아니라 다음 응답이 끝날 때 바뀝니다.
- `PostToolUse` 훅은 질문·승인 항목이 있을 때만(`todos-waiting` 파일이 있을 때만) Python을 실행합니다. 도구를 쓸 때마다 Python을 띄우지 않기 위해서입니다.
- 세션 제목은 T3 상태 DB(`~/.t3/userdata/statev2.sqlite`)를 읽기 전용으로 열어 Claude·Codex 세션 ID로 찾습니다. T3 밖 세션은 프로젝트 이름만 나옵니다.

## 설치

```sh
/usr/bin/python3 plugins/notify/notify.py install    # Claude 훅과 Codex notify 등록, 설정 생성
/usr/bin/python3 plugins/notify/notify.py status     # 등록 상태
/usr/bin/python3 plugins/notify/notify.py test       # 시험 알림
/usr/bin/python3 plugins/notify/notify.py uninstall  # 등록 해제(Codex의 기존 notify 복원)
```

- `install`은 `~/.claude/settings.json`의 다른 설정과 훅을 유지하고 이 스크립트의 훅만 더합니다. 다시 실행해도 중복되지 않습니다. `status`에 `빠진 훅`이 나오면 `install`을 다시 실행하세요.
- Codex는 `notify`를 하나만 쓸 수 있습니다. 기존 값이 있으면 이 스크립트가 먼저 그 명령을 그대로 실행한 뒤 알림을 처리합니다. Codex 앱이 이 스크립트를 `--previous-notify`로 감싼 줄도 등록된 것으로 보고 바꾸지 않습니다.
- 훅 변경은 새로 시작한 세션부터 적용됩니다.
- 저장소 폴더를 옮기면 `install`과 `menubar.sh install`을 다시 실행하세요.

메뉴 막대 할 일 목록은 따로 켭니다. 로그인할 때 자동으로 켜지는 LaunchAgent(`local.llm-plugin.todo-menubar`)라 T3가 꺼져 있어도 동작합니다.

```sh
sh plugins/notify/menubar.sh install    # 켜기(todo-menubar.js를 고친 뒤에도 다시 실행)
sh plugins/notify/menubar.sh status     # 실행 상태
sh plugins/notify/menubar.sh uninstall  # 끄기
```

터미널에서도 같은 목록을 보고 지울 수 있습니다.

```sh
/usr/bin/python3 plugins/notify/notify.py todo            # 목록(번호와 id)
/usr/bin/python3 plugins/notify/notify.py todo done 2     # 2번 지우기(id도 됨)
/usr/bin/python3 plugins/notify/notify.py todo act 1      # 1번을 그 T3 세션에 맡기기('알아서 진행')
/usr/bin/python3 plugins/notify/notify.py todo act 2 --choice rebase  # 2번을 rebase로 정해 맡기기
/usr/bin/python3 plugins/notify/notify.py todo add 내용   # 직접 넣기
/usr/bin/python3 plugins/notify/notify.py todo clear      # 모두 지우기
```

## 휴대폰

ntfy 앱(iOS, Android)에서 서버 `https://ntfy.sh`의 주제를 구독합니다. 주제는 `~/.config/llm-plugin/notify.json`의 `ntfy_topic`이며, 저장소에는 넣지 않습니다. 공개 서버라서 주제를 아는 사람은 알림을 읽거나 보낼 수 있습니다. 휴대폰 알림에는 할 일·질문 내용을 한 줄로 넣고, 프로젝트 이름은 넣지 않습니다. 주제는 추측하기 어려운 값으로 두세요.

## 설정

`~/.config/llm-plugin/notify.json`

| 키 | 기본값 | 의미 |
|---|---|---|
| `mac` | `true` | Mac 알림 |
| `sound` | `"Glass"` | Mac 알림 소리(`/System/Library/Sounds`의 이름) |
| `phone` | `true` | 휴대폰 알림 |
| `ntfy_server`, `ntfy_topic` | `https://ntfy.sh`, 설치 때 무작위 생성 | 휴대폰 알림 서버와 주제 |
| `phone_detail` | `true` | 휴대폰 알림에 할 일·질문 내용을 넣음. `false`면 종류만 보냄 |
| `phone_project` | `false` | `true`면 휴대폰 알림에 에이전트와 프로젝트 이름도 넣음 |

Mac 알림은 `osascript`로 보내며 처음에는 macOS가 알림 허용을 물을 수 있습니다. 방해 금지 모드에서는 소리가 나지 않을 수 있습니다.

| 파일 | 역할 |
|---|---|
| `~/.config/llm-plugin/todos.json` | 할 일 목록. 훅과 `todo` 명령이 잠금(`todos.lock`)을 잡고 고칩니다. |
| `~/.config/llm-plugin/todos-waiting` | 질문·승인 항목이 있을 때만 있는 표시 파일 |
| `plugins/notify/todo-menubar.js` | 메뉴 막대 항목과 목록 창(JXA + WebKit) |
| `plugins/notify/todo.html` | 목록 창 내용. 브라우저로 열면 예시 목록이 보입니다. |
| `~/Library/Logs/llm-plugin-todo-menubar.log` | 메뉴 막대 프로그램 오류 기록 |

## 테스트

```sh
python3 -m unittest discover -s plugins/notify/tests -v
osascript -l JavaScript plugins/notify/todo-menubar.js "$PWD/plugins/notify/todo.html" ~/.config/llm-plugin/todos.json "$PWD/plugins/notify/notify.py" --check
```

두 번째 명령은 창을 띄우지 않고 지금 목록을 그려 본 뒤 `items=… groups=… buttons=… height=…`를 적고 끝납니다. `buttons`는 맡기기·열기 버튼 수입니다. `--open --quit-after=5`로 바꾸면 창을 5초 동안 띄웁니다.
