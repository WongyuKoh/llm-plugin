---
name: commit
description: 변경 사항을 확인하고 저장소 규칙에 맞는 커밋을 만든다. 푸시는 하지 않는다.
argument-hint: "[메시지 요점]"
disable-model-invocation: true
---

# 커밋

`review-learning`의 작성 규칙을 따른다. 메시지 요점: `$ARGUMENTS`

1. `git status`와 diff로 변경을 확인하고, 이번 작업과 관련된 파일만 고른다. 비밀 값이 있을 수 있는 파일(.env, 인증 정보, 개인 설정)은 커밋하지 않고 알린다.
2. 기본 브랜치라면 작업 브랜치를 만든 뒤 커밋한다. 사용자가 기본 브랜치에 커밋하라고 하면 따른다.
3. 메시지는 저장소의 기존 형식을 따르고 실제 변경만 쓴다. AI 홍보 문구, 불필요한 `Co-Authored-By`, Obsidian 노트 내용이나 vault 경로를 넣지 않는다.
4. 커밋한 파일과 커밋 해시를 알린다. 푸시는 `/pr`이나 사용자 요청이 있을 때만 한다.
