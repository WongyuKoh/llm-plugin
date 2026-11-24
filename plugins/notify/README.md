# 할 일 알림

Claude Code나 Codex 세션에서 사용자가 해야 할 일이 생기면 이 Mac(소리 포함)과 휴대폰([ntfy](https://ntfy.sh))으로 알립니다. Python 표준 라이브러리만 사용합니다.

## 알리는 경우

| 경우 | 출처 |
|---|---|
| ❓ 질문에 답해야 할 때 | Claude `AskUserQuestion`(PreToolUse 훅), 입력 요청 알림 |
| 🔐 승인이 필요할 때 | Claude `PermissionRequest` 훅, 권한 요청 알림 |
| 🔔 할 일이 남았을 때 | 응답 마지막 줄의 `🔔 할 일: …`(Claude Stop 훅, Codex `notify`) |
| ⚠️ 확인이 필요할 때 | Drive 동기화가 약 30분 연속 실패할 때(`obsidian-note-inbox`) |

`🔔 할 일:` 줄은 전역 지침(`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`)에 따라 에이전트가 씁니다. 응답의 마지막 세 줄만 보고, 코드 표기 안의 예시는 무시합니다. 같은 알림은 60초 안에 다시 보내지 않습니다.

## 설치

```sh
/usr/bin/python3 plugins/notify/notify.py install    # Claude 훅과 Codex notify 등록, 설정 생성
/usr/bin/python3 plugins/notify/notify.py status     # 등록 상태
/usr/bin/python3 plugins/notify/notify.py test       # 시험 알림
/usr/bin/python3 plugins/notify/notify.py uninstall  # 등록 해제(Codex의 기존 notify 복원)
```

- `install`은 `~/.claude/settings.json`의 다른 설정과 훅을 유지하고 이 스크립트의 훅만 더합니다. 다시 실행해도 중복되지 않습니다.
- Codex는 `notify`를 하나만 쓸 수 있습니다. 기존 값이 있으면 이 스크립트가 먼저 그 명령을 그대로 실행한 뒤 알림을 처리합니다.
- 훅 변경은 새로 시작한 세션부터 적용됩니다.
- 저장소 폴더를 옮기면 `install`을 다시 실행하세요.

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

## 테스트

```sh
python3 -m unittest discover -s plugins/notify/tests -v
```
