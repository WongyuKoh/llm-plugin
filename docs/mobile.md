# 휴대폰에서 쓰기

휴대폰에서 작업하는 방법은 두 가지이고, 알림은 따로 받습니다.

## 1. T3 앱으로 이 Mac의 세션 쓰기

휴대폰 T3 앱이 T3 Connect로 이 Mac에 연결되면 세션은 이 Mac에서 실행됩니다. 그래서 `install.sh`로 연결한 스킬과 명령(`/progress`, `/sessions`, `/handoff` 등), Claude Code 플러그인, 알림 훅이 컴퓨터에서와 같이 적용됩니다. 이 Mac이 켜져 있고 T3가 실행 중이어야 합니다.

2026-11-25 기준으로 이 Mac에 T3 Connect 연결 기록은 있지만, 휴대폰 앱의 연결 여부는 확인하지 않았습니다.

## 2. Claude 앱(claude.ai)

Claude 앱은 이 Mac에 접근하지 못합니다. T3 도구가 필요한 명령과 `dev-flow`는 동작하지 않습니다.

- 스킬: `artifacts/claude-skills/`의 ZIP 5개(`session-focus`, `clear-response`, `review-learning`, `document-writing`, `eco`)를 [Claude 스킬 설정](https://claude.ai/customize/skills/yours)에 올립니다.
- 학습 노트: Google Drive 커넥터를 켜고, Claude 개인 설정의 지침에 "학습 노트는 Google Drive의 `Claude-Obsidian-Inbox` 폴더에 Markdown으로 저장한다."를 넣습니다. 이 Mac이 5분마다 그 폴더의 새 노트를 vault 수집함으로 가져옵니다([수신기](../plugins/obsidian-note-inbox/README.md)).

## 알림

[할 일 알림](../plugins/notify/README.md)이 질문, 승인 요청, 응답 끝의 `🔔 할 일`, Drive 동기화 연속 실패를 이 Mac과 휴대폰으로 보냅니다.

1. 휴대폰에 ntfy 앱을 설치합니다.
2. 서버 `https://ntfy.sh`, 주제는 `~/.config/llm-plugin/notify.json`의 `ntfy_topic`으로 구독합니다.
3. 컴퓨터에서 `/usr/bin/python3 plugins/notify/notify.py test`를 실행해 두 곳에 알림이 오는지 확인합니다.

T3 앱 자체의 알림 설정도 있습니다. 2026-11-25 기준 이 Mac의 T3 알림은 꺼져 있습니다. 켜면 T3 알림과 이 알림이 함께 올 수 있습니다.
