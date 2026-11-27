# llm-plugin

T3 Code에서 Claude와 Codex가 함께 쓰는 작업 규칙(스킬), 슬래시 명령, 개발 흐름 설계, Obsidian 노트 수신기를 모아 둔 저장소입니다.

## 설치

이 Mac의 모든 프로젝트와 폴더 없는 세션에서 쓰려면 저장소 루트에서 실행합니다.

```sh
./install.sh            # ~/.claude/skills, ~/.codex/skills에 링크 연결
./install.sh --remove   # 이 저장소를 가리키는 링크만 제거
```

링크라서 `skills/`를 고치면 바로 반영됩니다. 저장소 폴더를 옮기면 다시 실행하세요.

## 구성

| 경로 | 내용 |
|---|---|
| `skills/` | 스킬과 명령 원본 |
| `install.sh` | 개인 스킬 폴더 연결 |
| `.claude/skills/`, `.agents/skills/` | 이 저장소 안에서 쓰는 스킬 링크 |
| `CLAUDE.md`, `AGENTS.md` | Claude와 Codex의 기본 지침 |
| `docs/dev-flow.md` | 개발 흐름 설계: 세션 구성, 모델, 작업 카드, 알림, 명령, 토큰 절약 모드 |
| `docs/claude-skills.md` | 스킬 사용법, claude.ai 적용, Obsidian 연결 |
| `docs/mobile.md` | 휴대폰에서 쓰기: T3 앱, Claude 앱, 알림 |
| `plugins/notify/` | 질문·승인·할 일이 생기면 이 Mac(소리)과 휴대폰으로 알리고, 메뉴 막대 할 일 목록에 모음 |
| `plugins/obsidian-note-inbox/` | Google Drive 폴더의 Markdown을 Obsidian 수집함으로 가져오는 수신기 |
| `artifacts/claude-skills/` | claude.ai 업로드용 스킬 ZIP |

## 규칙 스킬

| 스킬 | 용도 | Claude 적용 시점 |
|---|---|---|
| `session-focus` | 세션 목적·이름, 주제 이탈과 역할 세션 조율 | 항상(`CLAUDE.md`) |
| `clear-response` | 한국어 결론 우선 응답, 사실 기준 답변 | 항상(`CLAUDE.md`) |
| `t3-session-workflow` | T3 세션 상태 확인, 보관·정리, 재연결 | 항상(`CLAUDE.md`) |
| `dev-flow` | 세션 구성, 세션별 모델, 작업 카드, 하위 세션 알림 | 필요할 때 |
| `review-learning` | 리뷰·PR·커밋과 Obsidian 학습 노트 | 필요할 때 |
| `document-writing` | 근거 기반 문서 작성 | 필요할 때 |

## 명령

| 명령 | 하는 일 |
|---|---|
| `/guide` | 가이드북 열기: 항목을 누르면 실행 모습 애니메이션·설명·예시·시험 방법 팝업 |
| `/setup [폴더] [설명]` | 주제를 정해 [작업]·[질문]·[테스트] 세션 구성. 범위 밖 요청은 막고 맞는 세션 안내 |
| `/card [내용]` | 작업 카드 작성 |
| `/handoff [작업\|테스트\|질문\|새] [할 일]` | 카드나 할 일을 맞는 세션에 넘기고 끝나면 알림 받기. 세션을 적지 않으면 할 일 종류로 고름 |
| `/parallel [개수] [계획]` | 항목을 고칠 파일이 겹치지 않는 단위로 나눠 하위 세션 여러 개로 동시에 진행하고 PR 하나로 합치기. 다시 나눌 만큼 큰 단위는 `↳ 원래 세션 · 단위` 이름의 연계 세션으로 따로 만들어 그 안에서 다시 나눔 |
| `/relay [바로 할 일]` | 세션이 길어지면 지금까지 내용을 인계해 새 세션을 만들고 이어가기. 컨텍스트가 창의 80%를 넘거나 압축되면 메뉴 막대에 제안이 뜸 |
| `/qa [PR\|브랜치]` | 완료 조건 검증 |
| `/progress [all]` | 다른 세션의 진행 상황과 질문 보기 |
| `/sessions [일수]` | T3 밖(VS Code, 터미널, 앱, 스크립트)에서 실행한 세션 보기 |
| `/commit [요점]` | 커밋 |
| `/pr [요점]` | 푸시, PR 생성과 감시 |
| `/merge [PR]` | 체크·리뷰 확인 후 머지 |
| `/note [주제]` | Obsidian 학습 노트 |
| `/obsidian [폴더] [분류]` | 프로젝트 폴더를 Obsidian vault에 연결하고 세션이 처음부터 vault 규칙을 따르도록 `CLAUDE.local.md`에 지침 넣기. `.gitignore` 같은 저장소 파일 변경은 기본 브랜치(main)에 커밋. `/setup`으로 새 폴더를 만들면 자동 실행 |
| `/minutes [transcript·메모] [주제]` | 회의 transcript와 직접 정리한 메모를 vault 회의록 양식으로 정리해 `docs/회의록/`에 저장 |
| `/drive-reauth` | Obsidian 수집용 Google Drive 인증 다시 연결 |
| `/close [settle]` | 세션 보관 또는 완료 정리 |
| `/refresh [스킬 이름...]` | 열려 있는 세션이 지침과 스킬을 다시 읽어 최신 내용으로 따르기 |
| `/eco [on\|off]` | 토큰 절약 모드 |

`/obsidian`과 `/minutes`는 전역 지침(`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`)에 적은 vault 위치를 씁니다. Codex는 `CLAUDE.local.md`를 자동으로 읽지 않으므로 전역 지침에 이 파일을 읽으라는 안내를 함께 둡니다.

리뷰는 Claude Code 기본 명령 `/code-review`, 앱 실행 확인은 `/run`을 씁니다. 화면 디자인 검토와 다듬기는 외부 스킬 [Impeccable](https://impeccable.style)의 `/impeccable [명령] [대상]`을 씁니다. `npx impeccable install`로 따로 설치하며, 프로젝트마다 `/impeccable init`과 `/impeccable document`로 만든 `DESIGN.md`가 그 프로젝트의 디자인 기준이 됩니다. Codex에서는 `$progress`처럼 `$`로 부릅니다. `/progress`, `/sessions`, `/eco`, `/parallel`, `/relay`, `/minutes`, `/obsidian`은 말로 요청해도 동작합니다. `/parallel`은 [작업] 세션이 고칠 파일이 다른 항목 여러 개를 맡으면 입력하지 않아도 씁니다. 나머지 명령은 입력할 때만 불러오므로 평소에는 토큰을 쓰지 않습니다.

## 알림과 휴대폰

질문, 승인 요청, 응답 끝의 `🔔 할 일`(여러 개면 번호 목록), Drive 동기화 연속 실패를 이 Mac(소리)과 휴대폰(ntfy)으로 알립니다. 남은 할 일은 맥 메뉴 막대의 `🔔 할 일 N`에 모이고, 세션이 응답을 마치면 그 응답의 할 일로 바뀌고, `완료`를 누르면 바로 지워집니다. T3 세션의 할 일은 `알아서 진행`이나 `선택…`(선택지 모달)으로 그 세션에 맡길 수 있습니다. 설치와 설정은 [할 일 알림](plugins/notify/README.md), 휴대폰에서 작업하는 방법은 [휴대폰에서 쓰기](docs/mobile.md)를 보세요.

## 확인

테스트는 저장소 루트에서 실행합니다.

```sh
python3 -m unittest discover -s plugins/obsidian-note-inbox/tests -v
python3 -m unittest discover -s plugins/notify/tests -v
```
