# T3 명령 안내

T3 Code 데스크톱·웹 화면 오른쪽 위 스레드 정보 카드 아래에 이 저장소의 슬래시 명령 목록을 카드와 같은 모양(아이콘, 명령, 오른쪽 설명, 묶음 제목과 구분선)으로 표시합니다. 휴대폰 T3 앱은 테마를 쓰지 않아 표시되지 않습니다.

## 동작 방식

- T3 테마의 사용자 CSS로 스레드 정보 카드(`[data-thread-details-card]`)의 `::after`에 안내를 붙입니다.
- 테마 CSS로는 줄마다 글자색을 다르게 줄 수 없어서, 안내를 SVG 그림으로 그려 넣습니다. 어두운 모드와 밝은 모드용 그림을 따로 만듭니다.
- 색은 T3 기본 테마(`t3-code`)의 값을 그대로 씁니다. T3는 사용자 테마에 색을 요구하므로, T3 앱 코드(`packages/shared/src/themePalettes.ts`)의 기본 색 전체를 `colors`(어두운 모드)와 `variants.light`(밝은 모드)에 넣었습니다. T3가 업데이트로 기본 색을 바꾸면 `build_theme.py`의 값을 다시 맞춰야 합니다.

## 만들기·적용·되돌리기

```sh
python3 plugins/t3-guide/build_theme.py   # theme.json, preview.html 생성
```

- 적용·갱신: `theme.json` 내용을 `t3_theme_set`의 `theme`로 게시합니다(테마 id `guide`). 이미 게시돼 있으면 `~/.t3/userdata/themes/guide.json`을 `theme.json`으로 바꾼 뒤 기본 테마로 한 번 바꿨다가 `guide`로 되돌려도 됩니다.
- 되돌리기: 테마를 `t3-code`로 바꿉니다.
- 확인: `preview.html`에서 두 모드의 모양을 미리 볼 수 있습니다.

명령을 추가하거나 바꾸면 `build_theme.py`의 `GROUPS`를 고치고 다시 만드세요.

## 가이드북 버튼(프로젝트 스크립트)

카드 안내는 그림이라 누를 수 없습니다. 누르는 가이드북은 `/guide`로 대화에 띄우거나, T3 프로젝트 스크립트 버튼으로 오른쪽 미리보기 패널에 엽니다. llm-plugin 프로젝트에는 다음 스크립트를 등록했습니다(2026-11-25).

| 항목 | 값 |
|---|---|
| 이름 | 📘 가이드북 |
| 명령 | `python3 -m http.server 8777 --bind 127.0.0.1 --directory "$HOME/.claude/skills/guide"` |
| 미리보기 | `http://127.0.0.1:8777/guidebook.html` 자동 열기 |
| 실행 방식 | 계속 실행(async), 세션 정리 때 중지 |

다른 프로젝트에 넣으려면 같은 값을 그 프로젝트 스크립트에 추가하세요. 8777 포트를 이미 쓰고 있으면 서버가 시작되지 않습니다.
