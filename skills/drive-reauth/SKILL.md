---
name: drive-reauth
description: Obsidian 수집용 Google Drive 인증(rclone)을 다시 연결하고 동기화로 확인한다. 이 Mac에서만 동작한다.
disable-model-invocation: true
---

# Drive 재인증

[수신기](../../plugins/obsidian-note-inbox/README.md)의 rclone 인증을 다시 연결한다. 사용자가 이 Mac의 브라우저에서 Google 로그인과 권한 승인을 해야 한다.

1. 아래 명령을 백그라운드로 실행한다. 브라우저 열기와 로컬 포트(53682)가 필요하므로 샌드박스가 막으면 샌드박스 밖에서 실행한다.

   ```sh
   /opt/homebrew/bin/rclone --config "$HOME/Library/Application Support/ClaudeObsidianInbox/rclone.conf" config reconnect claude-obsidian-inbox: --auto-confirm
   ```

2. 출력의 로그인 주소와 함께 "이 Mac 브라우저에서 Google 로그인 → 확인되지 않은 앱 경고는 고급 → 계속 → Drive 권한 승인"을 안내하고, 응답 마지막 줄에 `🔔 할 일:`을 쓴다. 로그인 주소는 이 Mac에서만 열린다.
3. 명령이 끝나면 동기화를 한 번 실행해 결과를 확인한다.

   ```sh
   cd "$HOME/Library/Application Support/ClaudeObsidianInbox" && /opt/anaconda3/bin/python3 auto_pull.py
   ```

4. 토큰 값은 출력하지 않는다. Google 테스트 상태 앱이라 새 토큰도 7일 뒤 만료되며, 만료 하루 전에 알림이 온다고 알린다.
