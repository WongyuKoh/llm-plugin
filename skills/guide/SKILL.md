---
name: guide
description: 내 스킬·명령 가이드북을 화면에 띄운다. 항목을 누르면 설명, 예시, 시험 방법이 팝업으로 열린다. 사용자가 /guide를 입력하거나 가이드북·명령 사용법을 보여 달라고 할 때 사용한다.
---

# 가이드북

T3 도구가 있으면 `html_render`로 이 스킬 폴더의 `guidebook.html`을 띄운다(`path`: 이 스킬 폴더의 `guidebook.html` 절대 경로, `title`: "스킬 가이드북", `height`: 560).

- 페이지 내용을 다시 설명하지 않는다. "항목을 누르면 설명과 예시가 열리고, 예시는 복사해서 입력창에 붙여 넣으면 된다"는 안내만 한 줄로 쓴다.
- `html_render`를 쓸 수 없는 환경이면 `guidebook.html` 경로를 알려 주고, 브라우저로 열면 된다고 안내한다.
- 명령을 추가하거나 바꾸면 `guidebook.html`의 `ITEMS`와 `plugins/t3-guide/build_theme.py`의 `GROUPS`를 함께 고친다.
