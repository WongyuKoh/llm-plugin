#!/usr/bin/env python3
"""T3 Code 기본 테마 색을 그대로 쓰면서 스레드 정보 카드 아래에 명령 안내 상자를 붙이는 테마를 만든다.

안내 상자는 카드와 분리된 별도 상자이고, 높이를 384px로 고정해 상자 안에서 따로 스크롤된다.
카드 안에 붙이면 카드의 하위 세션 목록(Lineage) 등이 밀려 보이지 않아서 패널(aside)에 붙인다.

출력: 같은 폴더의 theme.json (t3_theme_set의 theme 값), preview.html (확인용 화면)
명령을 바꾸면 GROUPS를 고치고 다시 실행한 뒤 theme.json을 T3 테마 `guide`로 적용한다.
"""
import base64
import json
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
# T3 정보 패널 너비는 280px로 고정이다(T3 0.1.11 앱 코드의 mf=280, 2026-11-25 확인).
# 그림 너비를 같게 두어 그림의 1단위가 화면 1px이 되게 한다. 줄 높이는 카드의 줄(h-8)과 같은 32px.
WIDTH = 280
ROW = 32
HEADER = 32
ICON = 17
VISIBLE_HEIGHT = 384  # 안내 상자 높이(px). 2026-11-25 사용자가 정한 값('내 명령' 7줄 높이의 1.5배). 명령을 더해도 유지한다.

# T3 Code 기본 테마(t3-code) 색. T3 앱의 packages/shared/src/themePalettes.ts에서 옮김(2026-11-25 확인).
DARK = {
    'searchMatchBackground': '#8c6c1f', 'searchMatchForeground': '#f5f5f5',
    'searchMatchActiveBackground': '#eea52b', 'searchMatchActiveForeground': '#21180a',
    'canvas': '#0a0a0a', 'chrome': '#0a0a0a', 'toolbar': '#0a0a0a', 'toolbarForeground': '#f5f5f5',
    'toolbarBorder': '#191919', 'toolbarControl': '#111111', 'toolbarControlForeground': '#f5f5f5',
    'toolbarControlHover': '#141414', 'surface': '#111111', 'surfaceRaised': '#111111',
    'surfaceOverlay': '#111111', 'text': '#f5f5f5', 'textMuted': '#818181', 'border': '#191919',
    'input': '#1e1e1e', 'focus': '#346bf1', 'accent': '#346bf1', 'accentForeground': '#ffffff',
    'secondary': '#111111', 'secondaryForeground': '#f5f5f5', 'muted': '#111111',
    'mutedForeground': '#818181', 'placeholder': '#818181', 'secondaryLabel': '#818181',
    'iconMuted': '#818181', 'error': '#fb414a', 'errorForeground': '#ff6467', 'errorSurface': '#301214',
    'warning': '#fe9a00', 'warningForeground': '#ffb900', 'warningSurface': '#312108',
    'update': '#346bf1', 'updateForeground': '#51a2ff', 'updateSurface': '#121b34',
    'accentSurface': '#141414', 'accentSurfaceForeground': '#f5f5f5', 'messageSurface': '#141414',
    'messageForeground': '#f5f5f5', 'messageAction': '#346bf1', 'messageActionForeground': '#ffffff',
    'messageActionHover': '#3061d9', 'codeBackground': '#111111', 'codeForeground': '#f5f5f5',
    'sidebar': '#000000', 'sidebarForeground': '#f1f3f7', 'sidebarMutedForeground': '#a3a3a3',
    'sidebarControlSurface': '#0a0a0a', 'sidebarRowHover': '#131313', 'sidebarRowActive': '#1a1b1b',
    'sidebarRowSelected': '#111111', 'sidebarBorder': '#141414', 'terminalBackground': '#0a0a0a',
    'terminalForeground': '#f5f5f5', 'terminalCursor': '#b4cbff', 'terminalSelection': '#343a47',
    'terminalScrollbar': '#222222', 'terminalScrollbarHover': '#363636',
}
LIGHT = {
    'searchMatchBackground': '#ffde8b', 'searchMatchForeground': '#21180a',
    'searchMatchActiveBackground': '#eea52b', 'searchMatchActiveForeground': '#21180a',
    'canvas': '#fcfcfc', 'chrome': '#fcfcfc', 'toolbar': '#fcfcfc', 'toolbarForeground': '#27272a',
    'toolbarBorder': '#e4e4e7', 'toolbarControl': '#ffffff', 'toolbarControlForeground': '#27272a',
    'toolbarControlHover': '#f4f4f5', 'surface': '#ffffff', 'surfaceRaised': '#fcfcfc',
    'surfaceOverlay': '#ffffff', 'text': '#27272a', 'textMuted': '#71717b', 'border': '#e4e4e7',
    'input': '#d4d4d8', 'focus': '#1b4ed8', 'accent': '#1b4ed8', 'accentForeground': '#ffffff',
    'secondary': '#fafafa', 'secondaryForeground': '#27272a', 'muted': '#fafafa',
    'mutedForeground': '#71717b', 'placeholder': '#71717b', 'secondaryLabel': '#71717b',
    'iconMuted': '#71717b', 'error': '#fb2c36', 'errorForeground': '#c10007', 'errorSurface': '#fcebec',
    'warning': '#fe9a00', 'warningForeground': '#bb4d00', 'warningSurface': '#fcf4e8',
    'update': '#1b4ed8', 'updateForeground': '#1b4ed8', 'updateSurface': '#e0e6f7',
    'accentSurface': '#f4f4f5', 'accentSurfaceForeground': '#18181b', 'messageSurface': '#f4f4f5',
    'messageForeground': '#27272a', 'messageAction': '#1b4ed8', 'messageActionForeground': '#ffffff',
    'messageActionHover': '#3160db', 'codeBackground': '#ffffff', 'codeForeground': '#27272a',
    'sidebar': '#fafafa', 'sidebarForeground': '#27272a', 'sidebarMutedForeground': '#71717b',
    'sidebarControlSurface': '#f4f4f5', 'sidebarRowHover': '#fcfcfc', 'sidebarRowActive': '#ffffff',
    'sidebarRowSelected': '#ffffff', 'sidebarBorder': '#e4e4e7', 'terminalBackground': '#fcfcfc',
    'terminalForeground': '#27272a', 'terminalCursor': '#26384e', 'terminalSelection': '#d0d6dd',
    'terminalScrollbar': '#d6d6d6', 'terminalScrollbarHover': '#bdbdbd',
}

# 24x24 선 아이콘(lucide와 같은 선 굵기·모양)
ICONS = {
    'layout': '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16"/>',
    'card': '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/>',
    'send': '<path d="M5 12h14M13 6l6 6-6 6"/>',
    'split': '<path d="M3 12h5l4-6h7M8 12l4 6h7"/><path d="M16 3l3 3-3 3M16 15l3 3-3 3"/>',
    'check': '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.5"/>',
    'activity': '<path d="M3 12h4l3-7 4 14 3-7h4"/>',
    'history': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    'git': '<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="9" r="2.5"/>'
           '<path d="M6 8.5v7M18 11.5c0 3.5-3 4.5-9.5 5.5"/>',
    'search': '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.3-4.3"/>',
    'note': '<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h11"/>',
    'archive': '<rect x="3" y="4" width="18" height="5" rx="1.5"/><path d="M5 9v9a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9M10 13h4"/>',
    'leaf': '<path d="M5 19C5 10 11 5 19 5c0 8-5 14-14 14z"/><path d="M5 19l7-7"/>',
    'key': '<circle cx="8" cy="15" r="4"/><path d="M11 12l8-8M16 7l2.5 2.5"/>',
    'bell': '<path d="M6 16v-5a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    'book': '<path d="M4 5.5C6.5 4 9.5 4 12 6c2.5-2 5.5-2 8-.5V19c-2.5-1.5-5.5-1.5-8 .5-2.5-2-5.5-2-8-.5z"/><path d="M12 6v13.5"/>',
}

GROUPS = [
    ('내 명령', '/ 입력 · Codex는 $', [
        ('book', '/guide', '가이드북·예시'),
        ('layout', '/setup', '주제별 세션 3개'),
        ('card', '/card', '작업 카드'),
        ('send', '/handoff', '작업 넘기기'),
        ('split', '/parallel', '나눠서 동시 진행'),
        ('check', '/qa', '완료 조건 검증'),
        ('activity', '/progress', '진행·질문 보기'),
        ('history', '/sessions', 'T3 밖 세션'),
    ]),
    ('Git · 기록', '', [
        ('git', '/commit · /pr · /merge', ''),
        ('search', '/code-review', '리뷰'),
        ('note', '/note', '학습 노트'),
        ('archive', '/close', '세션 정리'),
    ]),
    ('설정 · 알림', '', [
        ('leaf', '/eco', '절약 모드'),
        ('key', '/drive-reauth', 'Drive 재인증'),
        ('bell', '할 일 알림', '휴대폰 · Mac'),
    ]),
]

FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Apple SD Gothic Neo', 'Helvetica Neue', sans-serif"


def height():
    return sum(HEADER + ROW * len(rows) for _, _, rows in GROUPS) + 10


def visible_height():
    """안내 상자에 한 번에 보이는 높이: VISIBLE_HEIGHT에 가장 가까운 줄 경계(줄 중간에서 잘리지 않게)."""
    target = VISIBLE_HEIGHT
    edges, y = [], 0
    for _, _, rows in GROUPS:
        y += HEADER
        edges.append(y)
        for _ in rows:
            y += ROW
            edges.append(y)
    return min(edges, key=lambda edge: abs(edge - target))


def svg(colors, weight=400):
    parts, y = [], 0
    for index, (title, hint, rows) in enumerate(GROUPS):
        if index:  # 첫 묶음 위 선은 상자 테두리와 겹치므로 그리지 않는다. 둥근 모서리 밖으로 나가지 않게 양끝을 줄인다.
            parts.append('<line x1="12" y1="%.1f" x2="%d" y2="%.1f" stroke="%s"/>' % (y + 0.5, WIDTH - 12, y + 0.5, colors['border']))
        parts.append('<text x="18" y="%.1f" font-size="12" font-weight="500" fill="%s">%s</text>'
                     % (y + 21.5, colors['textMuted'], escape(title)))
        if hint:
            parts.append('<text x="%d" y="%.1f" font-size="12" text-anchor="end" fill="%s">%s</text>'
                         % (WIDTH - 18, y + 21.5, colors['textMuted'], escape(hint)))
        y += HEADER
        for icon, label, desc in rows:
            parts.append('<g transform="translate(18 %.1f) scale(%.4f)" fill="none" stroke="%s" stroke-width="2" '
                         'stroke-linecap="round" stroke-linejoin="round">%s</g>'
                         % (y + (ROW - ICON) / 2, ICON / 24, colors['iconMuted'], ICONS[icon]))
            parts.append('<text x="47" y="%d" font-size="14" font-weight="%d" fill="%s">%s</text>'
                         % (y + 21, weight, colors['text'], escape(label)))
            if desc:
                parts.append('<text x="%d" y="%d" font-size="13" text-anchor="end" fill="%s">%s</text>'
                             % (WIDTH - 18, y + 21, colors['textMuted'], escape(desc)))
            y += ROW
    # width/height 없이 viewBox만 두어 상자 너비에 맞춰 늘고 준다(높이는 비율대로).
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" font-family="%s">%s</svg>'
            % (WIDTH, height(), escape(FONT, quote=True), ''.join(parts)))


def data_uri(colors):
    # 어두운 배경에서는 그림 속 글자가 화면 글자보다 굵게 보여 한 단계 가늘게 그린다.
    weight = 300 if colors is DARK else 400
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg(colors, weight).encode('utf-8')).decode('ascii')


PANEL = '[data-thread-details-panel="inline"]'


def css():
    # 패널(aside)을 세로 flex로 바꿔 [카드][안내 상자]로 나눈다. 공간이 모자라면 카드가 줄고 카드 안에서 스크롤된다.
    # 안내 상자(::after)는 content: url()의 그림이 상자보다 길어 상자 안에서 따로 스크롤된다.
    # 스크롤 상자에 border-radius나 clip-path가 있으면 Chromium에서 휠 스크롤이 막혀서(Chrome 158 시험, 2026-11-25)
    # 상자는 투명한 네모로 두고, 둥근 배경과 테두리는 같은 크기의 ::before를 뒤에 깔아 그린다.
    return '\n'.join([
        '/* llm-plugin: 스레드 정보 카드 아래, 따로 스크롤되는 명령 안내 상자 (plugins/t3-guide/build_theme.py로 생성) */',
        '%s { display: flex !important; flex-direction: column; gap: 8px; }' % PANEL,
        '%s > [data-thread-details-card] { flex: 0 1 auto; min-height: 0; }' % PANEL,
        '%s::after {' % PANEL,
        '  display: block; flex: none; aspect-ratio: %d / %d;' % (WIDTH, visible_height()),
        '  overflow-y: auto; overscroll-behavior: contain; scrollbar-width: none; font-size: 0; line-height: 0;',
        '}',
        '%s::before {' % PANEL,
        '  content: ""; position: absolute; left: 0; right: 0; bottom: 0; z-index: -1; pointer-events: none;',
        '  box-sizing: border-box; aspect-ratio: %d / %d;' % (WIDTH, visible_height()),
        '  background: var(--popover); border: 1px solid color-mix(in srgb, var(--contrast-foreground) 10%, transparent);',
        '  border-radius: 1rem;',
        '}',
        '.dark %s::after { content: url("%s"); }' % (PANEL, data_uri(DARK)),
        ':root:not(.dark) %s::after { content: url("%s"); }' % (PANEL, data_uri(LIGHT)),
    ])


def preview_html():
    blocks = []
    for name, colors in (('어두운 모드', DARK), ('밝은 모드', LIGHT)):
        blocks.append(
            '<div style="background:%s;padding:20px;border-radius:10px;flex:1">'
            '<div style="color:%s;font:12px %s;margin-bottom:8px">%s</div>'
            '<div style="width:%dpx;background:%s;border:1px solid %s;border-radius:16px;padding:8px 0;font:13px %s;color:%s">'
            '<div style="padding:8px 18px">Open in VS Code</div><div style="padding:8px 18px">Push &amp; create PR</div></div>'
            '<div style="width:%dpx;margin-top:8px;aspect-ratio:%d / %d;overflow-y:auto;scrollbar-width:none;'
            'background:%s;border:1px solid %s;border-radius:16px">'
            '<img src="%s" style="display:block;width:100%%"></div></div>'
            % (colors['canvas'], colors['textMuted'], FONT, name, WIDTH, colors['surface'], colors['border'], FONT,
               colors['text'], WIDTH, WIDTH, visible_height(), colors['surface'], colors['border'], data_uri(colors)))
    return ('<!doctype html><html><head><meta charset="utf-8"></head><body>'
            '<div style="display:flex;gap:12px">%s</div></body></html>' % ''.join(blocks))


def main():
    theme = {'name': 'T3 기본 + 명령 안내', 'appearance': 'dark', 'colors': DARK,
             'variants': {'light': LIGHT}, 'css': css()}
    (HERE / 'theme.json').write_text(json.dumps(theme, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (HERE / 'preview.html').write_text(preview_html(), encoding='utf-8')
    print('theme.json css %d chars, guide %dx%d' % (len(theme['css']), WIDTH, height()))


if __name__ == '__main__':
    main()
