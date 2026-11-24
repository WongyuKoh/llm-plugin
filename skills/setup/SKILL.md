---
name: setup
description: 프로젝트 폴더에 [작업]·[질문]·[테스트] 세션을 만들고 세션별 모델을 지정한다.
argument-hint: "[폴더 경로]"
disable-model-invocation: true
---

# 세션 구성

`dev-flow` 스킬을 불러 "새 프로젝트 구성" 절차를 그대로 따른다.

- 대상 폴더: `$ARGUMENTS`. 비어 있으면 현재 프로젝트를 대상으로 한다. 폴더가 없으면 만든다.
- 끝나면 세션 link, 역할, 모델을 표로 보여 준다. 이미 있던 역할 세션은 "기존"으로 표시하고 새로 만들지 않는다.
