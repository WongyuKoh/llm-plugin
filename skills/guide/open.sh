#!/bin/sh
# 가이드북을 화면 가운데 창으로 한 번 띄운다(macOS). 창을 띄우지 못하면 기본 브라우저로 연다.
# 늘 쓰는 방법은 메뉴 막대 📘 아이콘이다(menubar.sh install).
dir=$(cd "$(dirname "$0")" && pwd -P)
osascript -l JavaScript "$dir/guide-window.js" "$dir/guidebook.html" || open "$dir/guidebook.html"
