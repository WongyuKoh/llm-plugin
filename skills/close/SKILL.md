---
name: close
description: 현재 T3 세션을 보관(archive)한다. settle 인자를 주면 완료 목록으로 정리한다.
argument-hint: "[settle]"
disable-model-invocation: true
---

# 세션 닫기

`t3-session-workflow`의 완료와 종료 규칙을 따른다. 인자: `$ARGUMENTS`

1. 실행 중인 하위 작업이나 처리하지 않은 요청이 있으면 닫지 않고 목록을 보여 준 뒤 어떻게 할지 묻는다.
2. 인자가 `settle`이면 `t3_thread_organize`의 `settle`, 아니면 `archive`를 현재 세션(`threadId` 생략)에 실행한다.
3. 도구 결과를 확인한 뒤 결과를 한 줄로 알린다. 실패하면 이유를 그대로 전한다.
