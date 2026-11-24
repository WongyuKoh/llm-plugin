# Claude 스킬 사용과 Obsidian 연결

## 스킬

스킬과 명령의 원본은 각각 `skills/<이름>/SKILL.md`에 있습니다. 목록은 [README](../README.md)와 [개발 흐름 설계](dev-flow.md)에 있습니다. 이 저장소에서는 `.claude/skills/`, `.agents/skills/`의 상대 심볼릭 링크로 제공하며, `CLAUDE.md`가 세션 목적과 응답 구조를 기본 지침으로 불러옵니다.

이 Mac의 모든 프로젝트에서 쓰려면 저장소 루트에서 `./install.sh`를 실행합니다. `~/.claude/skills`와 `~/.codex/skills`에 링크를 만들고, 같은 이름의 다른 스킬이 있으면 건너뜁니다. Claude Code는 같은 이름이면 개인 스킬을 프로젝트 스킬보다 우선합니다. 다른 컴퓨터에서는 저장소를 받은 뒤 같은 스크립트를 실행합니다.

Claude가 이름을 제안하면 `/rename 제안한 이름`으로 실제 세션 이름을 정할 수 있습니다. 도구가 다른 세션에 접근할 수 없다면 실제 세션을 조회하거나 생성했다고 가정하지 않습니다.

한국어 응답, 사실 기준 답변, 스킬 안내(명령 없이 요청해도 맞는 스킬을 알리고 그 스킬로 진행)는 전역 지침(`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`)에도 넣었습니다. 특정 프로젝트에서 세션 목적과 응답 구조까지 항상 적용하려면 그 프로젝트의 `CLAUDE.md`에 다음을 추가하세요. `dev-flow`, `t3-session-workflow`와 명령은 T3 도구가 있는 세션에서만 동작합니다.

```markdown
@~/.claude/skills/session-focus/SKILL.md
@~/.claude/skills/clear-response/SKILL.md

리뷰·PR·머지·커밋 작업에는 `review-learning` 스킬을 사용한다.
문서 작성이나 수정에는 `document-writing` 스킬을 사용한다.
세션 구성과 세션별 모델 선택에는 `dev-flow` 스킬을 사용한다.
사용자가 토큰 절약을 요청한 경우에만 `eco` 스킬을 적용한다.
Obsidian vault의 노트 내용과 경로는 저장소 파일, 커밋, PR, 이슈에 넣지 않는다.
```

프로젝트 설정 `.claude/settings.json`은 Claude Code의 커밋·PR 기본 홍보 문구와 세션 링크를 끄도록 구성합니다. 기존 기여자 표기와 조직 정책은 그대로 따릅니다. 관리 설정이나 플랫폼이 별도로 붙이는 표기는 이 설정만으로 바뀌지 않을 수 있습니다. 다른 프로젝트에 적용하려면 기존 설정과 병합하세요.

## Claude 계정과 클라우드

claude.ai 웹·모바일처럼 이 Mac 밖에서 쓸 스킬의 업로드용 ZIP은 `artifacts/claude-skills/`에 있습니다(`session-focus`, `clear-response`, `review-learning`, `document-writing`, `eco`). T3 도구가 필요한 `dev-flow`, `t3-session-workflow`와 명령은 claude.ai에서 동작하지 않아 ZIP을 만들지 않았습니다. [Claude 스킬 설정](https://claude.ai/customize/skills/yours)에서 각 ZIP을 개별 업로드하고 활성화할 수 있습니다. 올린 스킬은 이 Mac의 Claude Code에도 `anthropic-skills:` 이름으로 함께 보이므로, 올렸다면 개인 스킬과 같은 버전으로 유지하세요. 휴대폰에서 쓰는 방법은 [휴대폰에서 쓰기](mobile.md)를 보세요. 스킬 원본을 수정한 뒤에는 ZIP을 다시 만들고 다시 업로드해야 합니다. ZIP 안의 경로가 `session-focus/SKILL.md`가 되도록 `skills/` 안에서 만듭니다. 예를 들어 이 저장소 루트에서:

```sh
rm -f artifacts/claude-skills/session-focus.zip
(cd skills && zip -r ../artifacts/claude-skills/session-focus.zip session-focus)
```

이 저장소에 반영된 스킬과 지침을 일반 Claude Code 클라우드 세션에서 사용하려면 저장소의 대상 브랜치에 필요한 파일을 커밋하고 원격에 반영해야 합니다. 일부 프로젝트 클라우드 스레드는 저장소의 `.claude/skills/`를 불러오지 않으므로 계정에 스킬을 활성화하세요. 세션 목적·응답 구조를 항상 적용하려면 해당 프로젝트의 지침에도 내용을 추가하세요. 개인 설정과 Mac의 파일은 클라우드에 자동으로 전달되지 않습니다. 자세한 범위는 [공식 스킬 문서](https://code.claude.com/docs/en/skills)를 확인하세요.

## Obsidian 연결

이 프로젝트의 로컬 전용 `CLAUDE.local.md`에는 이 Mac에서 확인한 vault 위치와 학습 노트 저장 지침이 있습니다. `.claude/settings.local.json`은 그 vault를 Claude Code의 추가 작업 디렉터리로 지정합니다. 두 파일은 Git에서 제외되며 다른 프로젝트·기기·클라우드 세션에는 적용되지 않습니다. 추가 디렉터리는 vault 전체를 파일 도구의 작업 범위에 포함합니다. 기본 권한 모드에 따라 쓰기 승인 요청이 나올 수 있고, 자동 편집 모드에서는 동작이 다릅니다. 필요한 자료만 읽고 개인 vault 전체를 전송하지 않도록 지침에 명시했습니다.

리뷰나 PR 정리 시 `/review-learning`을 사용하세요. 로컬 vault에 접근할 수 있으면 보관함의 자체 지침과 노트 작성 규칙을 따르고, 관련 기록이 없거나 분류가 불확실하면 수집함에 학습 노트를 만듭니다. 실제 노트 생성 및 변경은 해당 작업의 요청과 Claude 권한에 따릅니다.

클라우드 환경은 Mac의 vault 경로를 직접 볼 수 없습니다. Claude 클라우드 세션에서 Google Drive 커넥터를 켜고 학습 Markdown을 `Claude-Obsidian-Inbox` 폴더에 저장하면, 이 Mac의 수신기가 이를 Obsidian `00_Inbox`로 가져옵니다. 다른 클라우드 세션에서도 커넥터 활성화나 도구 승인이 필요할 수 있습니다.

2026-11-22에 클라우드 Claude가 생성한 테스트 노트의 Mac 저장을 확인했습니다. 로그인한 Mac에서 5분 간격으로 자동 실행되도록 설정했으며, 기존 파일을 덮어쓰거나 Drive에서 삭제된 파일을 로컬에서 삭제하지 않습니다. 변경된 같은 이름의 노트는 충돌로 처리합니다. 개인 OAuth 클라이언트는 Google 테스트 상태라 갱신 토큰이 7일 후 만료됩니다. Google 권한 범위, 재인증, 오류 확인 및 장기 사용 조건은 [수신기 안내](../plugins/obsidian-note-inbox/README.md)를 참고하세요.
