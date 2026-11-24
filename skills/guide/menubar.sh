#!/bin/sh
# 가이드북 메뉴 막대 항목('📘 T3 스킬 가이드')을 로그인할 때 자동으로 켜거나 끈다(macOS LaunchAgent).
# 사용: sh menubar.sh install | uninstall | status
set -eu

label=local.llm-plugin.guide-menubar
plist="$HOME/Library/LaunchAgents/$label.plist"
logfile="$HOME/Library/Logs/llm-plugin-guide-menubar.log"
domain="gui/$(id -u)"

# ~/.claude/skills/guide 링크가 있으면 그 경로를 써서 저장소를 옮겨도 install.sh만 다시 실행하면 되게 한다.
if [ -f "$HOME/.claude/skills/guide/guide-window.js" ]; then
  dir="$HOME/.claude/skills/guide"
else
  dir=$(cd "$(dirname "$0")" && pwd -P)
fi

case "${1:-status}" in
  install)
    mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
    cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/osascript</string>
    <string>-l</string>
    <string>JavaScript</string>
    <string>$dir/guide-window.js</string>
    <string>$dir/guidebook.html</string>
    <string>--menubar</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardErrorPath</key><string>$logfile</string>
</dict>
</plist>
EOF
    launchctl bootout "$domain/$label" 2>/dev/null || true
    # 이전 프로그램을 내린 직후에는 bootstrap이 "5: Input/output error"로 실패할 수 있어 잠시 뒤 다시 시도한다.
    tries=0
    until launchctl bootstrap "$domain" "$plist" 2>/dev/null; do
      tries=$((tries + 1))
      if [ "$tries" -ge 5 ]; then
        echo "실패: launchctl bootstrap이 계속 실패합니다. 잠시 뒤 다시 실행하세요." >&2
        exit 1
      fi
      sleep 1
    done
    echo "켜짐: 메뉴 막대에 '📘 T3 스킬 가이드'가 생깁니다. 로그인할 때마다 자동으로 켜집니다."
    ;;
  uninstall)
    launchctl bootout "$domain/$label" 2>/dev/null || true
    rm -f "$plist"
    echo "꺼짐: 메뉴 막대 아이콘과 자동 실행을 지웠습니다."
    ;;
  status)
    if launchctl print "$domain/$label" >/dev/null 2>&1; then
      echo "실행 중 ($plist)"
    else
      echo "꺼져 있음"
    fi
    ;;
  *)
    echo "사용: sh menubar.sh install | uninstall | status" >&2
    exit 2
    ;;
esac
