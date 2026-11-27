#!/bin/sh
# 이 저장소의 skills/를 이 컴퓨터의 Claude Code(~/.claude/skills)와 Codex(~/.codex/skills)
# 개인 스킬로 연결한다. 링크라서 저장소의 스킬을 고치면 바로 반영된다.
#
#   ./install.sh           연결한다. 같은 이름의 다른 스킬이 이미 있으면 건너뛴다.
#   ./install.sh --remove  이 저장소를 가리키는 링크만 지운다.
set -eu

repo=$(cd "$(dirname "$0")" && pwd -P)
mode=${1:-}

for target in "$HOME/.claude/skills" "$HOME/.codex/skills"; do
  mkdir -p "$target"

  # 이 저장소를 가리키는 링크 중 원본이 없어진 것(또는 --remove면 전부)을 지운다.
  for link in "$target"/*; do
    [ -L "$link" ] || continue
    dest=$(readlink "$link")
    case "$dest" in "$repo"/skills/*) ;; *) continue ;; esac
    if [ "$mode" = "--remove" ] || [ ! -e "$dest" ]; then
      rm "$link"
      echo "제거: $link"
    fi
  done
  [ "$mode" = "--remove" ] && continue

  for src in "$repo"/skills/*; do
    [ -f "$src/SKILL.md" ] || continue
    link="$target/$(basename "$src")"
    if [ -L "$link" ] && [ "$(readlink "$link")" = "$src" ]; then continue; fi
    if [ -e "$link" ] || [ -L "$link" ]; then
      echo "건너뜀: $link (같은 이름이 이미 있음)"
      continue
    fi
    ln -s "$src" "$link"
    echo "연결: $link"
  done
done
