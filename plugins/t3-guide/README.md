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

## 가이드북 메뉴 막대 아이콘

카드 안내는 그림이라 누를 수 없습니다. 누르는 가이드북은 `/guide`로 대화에 띄우거나, 맥 메뉴 막대의 `📘 T3 스킬 가이드`를 눌러 화면 가운데의 창으로 엽니다. 메뉴 막대 항목을 다시 누르거나 Esc를 누르거나 다른 곳을 클릭하면 닫힙니다.

- 창은 앱을 활성화하지 않는 패널이라, 다른 앱을 앞에 둔 채로 바로 키보드 입력을 받습니다.
- 메뉴 막대 항목은 macOS가 로그인할 때 켜는 별도 프로그램(LaunchAgent)이라 T3가 꺼져 있어도 동작합니다.
- 창을 열 때마다 `guidebook.html`을 다시 읽으므로, 페이지를 고치면 다음에 열 때 반영됩니다.

| 파일 | 역할 |
|---|---|
| `skills/guide/guide-window.js` | 창과 메뉴 막대 아이콘(JXA + WebKit). `--menubar`로 실행하면 계속 떠 있고, 옵션 없이 실행하면 창을 한 번 띄웁니다. |
| `skills/guide/menubar.sh` | 로그인할 때 아이콘이 켜지도록 LaunchAgent(`local.llm-plugin.guide-menubar`)를 설치하거나 지웁니다. |
| `skills/guide/open.sh` | 창을 한 번 띄웁니다. 띄우지 못하면 기본 브라우저로 엽니다. |

```sh
sh skills/guide/menubar.sh install    # 켜기(로그인할 때마다 자동 실행)
sh skills/guide/menubar.sh status     # 상태 확인
sh skills/guide/menubar.sh uninstall  # 끄고 자동 실행 지우기
```

오류는 `~/Library/Logs/llm-plugin-guide-menubar.log`에 남습니다. LaunchAgent는 `~/.claude/skills/guide`의 파일을 실행합니다.

### T3 버튼을 쓰지 않는 이유

처음에는 T3 프로젝트 스크립트 버튼(`~/.t3/userdata/settings.json`의 `defaultProjectScripts`)으로 열었지만, 다음 문제가 있어 메뉴 막대 아이콘으로 바꿨습니다(2026-11-25). T3 0.1.11 앱 코드와 터미널 기록으로 확인한 내용입니다.

- 프로젝트 스크립트를 실행하면 T3는 항상 아래 터미널을 열고 그 안에서 명령을 실행합니다. 이를 끄는 스크립트 항목이나 설정은 없습니다.
- 버튼으로 연 창은 잠깐 떴다가 저절로 닫혔습니다. 터미널이 열리면서 포커스가 T3로 돌아간 것으로 보입니다.
- T3는 쉬고 있는 터미널을 다시 쓰면서, 입력 줄에 남은 글자를 지우지 않고 그 뒤에 명령을 입력합니다. 남은 글자가 있으면 `command not found`로 실패합니다. 명령 앞에 Ctrl-U(`\u0015`)를 넣으면 막을 수 있습니다(zsh 기본 키 설정에서 확인).
- 대화 도구 `t3_project_update`의 `scripts`로 넣은 버튼은 화면에 보이지 않았습니다. `settings.json`을 고치면 T3를 완전히 종료했다가 다시 열어야 반영됩니다.

### 창 시험

`guide-window.js`의 시험 옵션입니다. 저장소 최상위에서 실행합니다.

```sh
# 창을 띄우지 않고 스크롤 막대 폭을 잰다(0px이면 숨겨진 상태)
osascript -l JavaScript skills/guide/guide-window.js "$PWD/skills/guide/guidebook.html" --check
# 창을 3초 동안 띄우고 포커스 변화를 기록한다
osascript -l JavaScript skills/guide/guide-window.js "$PWD/skills/guide/guidebook.html" --debug --quit-after=3
# 메뉴 막대 아이콘을 4초 동안 띄우고, 1초에 창을 열고 2.5초에 닫는다
osascript -l JavaScript skills/guide/guide-window.js "$PWD/skills/guide/guidebook.html" --menubar --debug --click-after=1,2.5 --quit-after=4
```
