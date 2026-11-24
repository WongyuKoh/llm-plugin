---
name: pr
description: 커밋과 푸시 후 PR을 만들고, CI 실패·리뷰 코멘트·충돌을 지켜보며 대응한다.
argument-hint: "[PR에 넣을 요점]"
disable-model-invocation: true
---

# PR 만들기

`review-learning` 규칙을 따른다. 추가 요점: `$ARGUMENTS`

1. 커밋하지 않은 관련 변경이 있으면 `/commit` 절차로 먼저 커밋한다.
2. 브랜치를 원격에 푸시하고 PR을 만든다. T3 PR 도구가 있으면 그것을 쓰고, 없으면 `gh`를 쓴다. 이 브랜치의 PR이 이미 있으면 새로 만들지 않고 푸시만 한다.
3. PR 본문에는 목적, 주요 변경, 실행한 검증과 결과, 남은 위험을 쓴다. 저장소 PR 템플릿이 있으면 따른다. AI 홍보 문구, Obsidian 노트 내용이나 vault 경로는 넣지 않는다.
4. PR을 이 세션에 연결하고 감시한다(T3 `link_pull_request`, `watch_pull_request`). CI 실패, 리뷰 코멘트, 충돌이 오면 대응한다.
5. PR link를 알린다. 이 세션이 `[작업 요청]` 메시지로 일을 받았다면 PR link를 담아 메인 세션에 ✅ 완료 알림을 보낸다(`dev-flow` 알림 형식).
