// 가이드북을 지금 작업 중인 화면 가운데의 떠 있는 창으로 띄운다(macOS, JXA + WebKit).
// 작업 중인 화면은 맨 앞 앱의 창이 있는 화면이고, 찾지 못하면 마우스가 있는 화면이다.
// 모니터를 연결하면 메뉴 막대가 노트북에만 있을 수 있어, 메뉴 막대를 누른 화면이 아니라 작업 중인 화면에 띄운다.
// 사용: osascript -l JavaScript guide-window.js <guidebook.html 절대 경로> [옵션]
//   --menubar        메뉴 막대에 '📘 T3 스킬 가이드'를 두고 계속 실행한다. 누르면 창을 열고 닫는다.
//   --debug          창 이벤트를 stderr에 적는다.
//   --check          창을 띄우지 않고 페이지를 불러 스크롤 막대 폭 등을 적은 뒤 끝낸다.
//   --where[=x,y]    창을 띄우지 않고 화면 목록과 창을 놓을 화면·위치를 적은 뒤 끝낸다.
//                    x,y(Cocoa 좌표)를 주면 맨 앞 창 대신 그 점이 있는 화면을 고른다.
//   --quit-after=초   시험용. 지정한 시간이 지나면 끝낸다.
//   --click-after=초[,초...]  시험용(--menubar). 지정한 시간에 아이콘을 누른 것처럼 동작한다.
// 창은 앱을 활성화하지 않는 패널이라 다른 앱을 앞에 둔 채로 키보드 입력(Esc 등)을 받는다.
// Esc를 누르거나 다른 곳을 클릭하면 닫힌다. 메뉴 막대 모드에서는 프로그램을 끝내지 않고 창만 숨긴다.
// 페이지의 복사 버튼은 이 프로그램이 클립보드에 넣는다.
ObjC.import('Cocoa');
ObjC.import('WebKit');
ObjC.import('CoreGraphics');

const state = {
  page: '', debug: false, menubar: false, closing: false,
  handler: null, panel: null, web: null, item: null, shownAt: 0, hiddenAt: 0
};

function log(text) {
  if (state.debug) console.log(text);
}

function quit(reason) {
  if (state.closing) return;
  state.closing = true;
  log('끝: ' + reason);
  $.NSApplication.sharedApplication.terminate(null);
}

// 창을 닫는다. 한 번만 띄운 경우에는 프로그램을 끝내고, 메뉴 막대 모드에서는 창만 숨긴다.
function dismiss(reason) {
  if (state.closing) return;
  if (!state.menubar) {
    log('닫힘: ' + reason + ' (' + (Date.now() - state.shownAt) + 'ms)');
    quit(reason);
    return;
  }
  if (!state.panel || !state.panel.isVisible) return;
  log('숨김: ' + reason + ' (' + (Date.now() - state.shownAt) + 'ms)');
  state.hiddenAt = Date.now();
  state.panel.orderOut(null);
}

ObjC.registerSubclass({
  name: 'GuideWindowHandler',
  superclass: 'NSObject',
  // 프로토콜 선언은 하지 않는다(JXA에서 "protocol does not exist" 오류). 메서드만 있으면 WebKit과 창이 호출한다.
  methods: {
    'userContentController:didReceiveScriptMessage:': {
      types: ['void', ['id', 'id']],
      implementation: function (controller, message) {
        const body = ObjC.deepUnwrap(message.body) || {};
        if (body.type === 'copy') {
          const board = $.NSPasteboard.generalPasteboard;
          board.clearContents;
          board.setStringForType($(String(body.text || '')), $.NSPasteboardTypeString);
        } else if (body.type === 'close') {
          dismiss('Esc');
        } else if (body.type === 'check') {
          console.log(String(body.text));
          quit('검사 끝');
        }
      }
    },
    'windowDidBecomeKey:': {
      types: ['void', ['id']],
      implementation: function (notification) { log('포커스 받음'); }
    },
    'windowDidResignKey:': {
      types: ['void', ['id']],
      implementation: function (notification) {
        // 창이 막 뜬 직후의 포커스 이동으로 닫히지 않게 잠시 기다린다.
        log('포커스 잃음');
        if (Date.now() - state.shownAt > 800) dismiss('다른 곳 클릭');
      }
    },
    'windowWillClose:': {
      types: ['void', ['id']],
      implementation: function (notification) {
        if (state.menubar) state.hiddenAt = Date.now();
        else dismiss('닫기 버튼');
      }
    },
    'toggleGuide:': {
      types: ['void', ['id']],
      implementation: function (sender) {
        if (state.panel && state.panel.isVisible) {
          dismiss('아이콘');
          return;
        }
        // 아이콘을 누르는 순간 창이 포커스를 잃어 먼저 숨었다면 다시 열지 않는다.
        if (Date.now() - state.hiddenAt < 300) return;
        showPanel();
      }
    },
    'reportFocus:': {
      types: ['void', ['id']],
      implementation: function (unused) {
        log('0.5초 뒤 · key=' + state.panel.isKeyWindow + ' visible=' + state.panel.isVisible);
      }
    },
    'quitTimer:': {
      types: ['void', ['id']],
      implementation: function (unused) { quit('시험 시간 끝'); }
    },
    'checkTimeout:': {
      types: ['void', ['id']],
      implementation: function (unused) {
        console.log('검사 실패: 10초 안에 페이지를 불러오지 못했습니다.');
        quit('시간 초과');
      }
    }
  }
});

// 검사 모드에서 페이지에 넣는 스크립트. 스크롤 막대가 보이면 scrollbar 값이 0보다 크다.
const CHECK_SOURCE = "addEventListener('load', () => webkit.messageHandlers.guide.postMessage({ type: 'check', text: "
  + "'scrollbar=' + (innerWidth - document.documentElement.clientWidth) + 'px content=' + document.documentElement.scrollHeight"
  + " + 'px window=' + innerHeight + 'px' }))";

function createPanel(check) {
  const screen = $.NSScreen.mainScreen.visibleFrame;
  const width = Math.min(640, screen.size.width * 0.9);
  const height = Math.min(780, screen.size.height * 0.88);
  const rect = $.NSMakeRect(0, 0, width, height);
  // 앱을 활성화하지 않는 패널(NSWindowStyleMaskNonactivatingPanel = 128)로 만든다.
  // 다른 앱이 활성 앱으로 남아 있어도 이 창이 키 입력을 받는다.
  const style = $.NSWindowStyleMaskTitled | $.NSWindowStyleMaskClosable | $.NSWindowStyleMaskFullSizeContentView
    | ($.NSWindowStyleMaskNonactivatingPanel || 128);

  const panel = $.NSPanel.alloc.initWithContentRectStyleMaskBackingDefer(rect, style, $.NSBackingStoreBuffered, false);
  panel.floatingPanel = true;
  panel.hidesOnDeactivate = false;
  panel.becomesKeyOnlyIfNeeded = false;
  panel.titlebarAppearsTransparent = true;
  panel.titleVisibility = $.NSWindowTitleHidden;
  panel.level = $.NSFloatingWindowLevel;
  // 지금 보고 있는 Space에 뜨고, 전체 화면 앱 위에도 뜬다(MoveToActiveSpace | FullScreenAuxiliary).
  panel.collectionBehavior = (1 << 1) | (1 << 8);
  panel.releasedWhenClosed = false;
  panel.delegate = state.handler;

  const config = $.WKWebViewConfiguration.alloc.init;
  config.userContentController.addScriptMessageHandlerName(state.handler, 'guide');
  if (check) {
    const script = $.WKUserScript.alloc.initWithSourceInjectionTimeForMainFrameOnly(
      $(CHECK_SOURCE), $.WKUserScriptInjectionTimeAtDocumentEnd, true);
    config.userContentController.addUserScript(script);
  }
  const web = $.WKWebView.alloc.initWithFrameConfiguration(rect, config);
  web.autoresizingMask = $.NSViewWidthSizable | $.NSViewHeightSizable;
  panel.contentView = web;
  state.panel = panel;
  state.web = web;
}

function loadPage() {
  const url = $.NSURL.fileURLWithPath($(state.page));
  state.web.loadFileURLAllowingReadAccessToURL(url, url.URLByDeletingLastPathComponent);
}

function screenList() {
  const screens = $.NSScreen.screens;
  const list = [];
  for (let i = 0; i < screens.count; i++) list.push(screens.objectAtIndex(i));
  return list;
}

function screenIndexAt(point) {
  return screenList().findIndex(screen => {
    const f = screen.frame;
    return point.x >= f.origin.x && point.x <= f.origin.x + f.size.width
      && point.y >= f.origin.y && point.y <= f.origin.y + f.size.height;
  });
}

// 맨 앞 앱의 맨 앞 창 가운데(Cocoa 좌표). 창 위치는 화면 기록 권한 없이 읽힌다.
function frontWindowCenter() {
  const front = $.NSWorkspace.sharedWorkspace.frontmostApplication;
  if (!front || front.isNil()) return null;
  const pid = front.processIdentifier;
  if (pid === $.NSProcessInfo.processInfo.processIdentifier) return null;
  // kCGWindowListOptionOnScreenOnly(1) | kCGWindowListExcludeDesktopElements(16), kCGNullWindowID(0). 앞에 있는 창부터 온다.
  const windows = ObjC.deepUnwrap(ObjC.castRefToObject($.CGWindowListCopyWindowInfo(1 | 16, 0))) || [];
  const win = windows.find(w => w.kCGWindowOwnerPID === pid && w.kCGWindowLayer === 0
    && w.kCGWindowBounds && w.kCGWindowBounds.Width > 50 && w.kCGWindowBounds.Height > 50);
  if (!win) return null;
  const b = win.kCGWindowBounds;
  // Quartz 좌표는 주 화면 왼쪽 위가 원점이고 아래로 커진다. Cocoa 좌표로 바꾼다.
  const primaryHeight = screenList()[0].frame.size.height;
  return { x: b.X + b.Width / 2, y: primaryHeight - (b.Y + b.Height / 2), app: ObjC.unwrap(front.localizedName) };
}

// 창을 놓을 화면: 맨 앞 창이 있는 화면 → 마우스가 있는 화면 → 주 화면. 화면 정보를 못 읽으면 null.
function targetScreen(point) {
  const screens = screenList();
  if (screens.length === 0) return null;
  const front = point || frontWindowCenter();
  let index = front ? screenIndexAt(front) : -1;
  let reason = point ? '지정한 점' : front ? '맨 앞 창(' + front.app + ')' : '';
  if (index < 0) {
    index = screenIndexAt($.NSEvent.mouseLocation);
    reason = '마우스';
  }
  if (index < 0) return { screen: screens[0], index: 0, reason: '주 화면' };
  return { screen: screens[index], index, reason };
}

// 화면의 사용 가능 영역(메뉴 막대·Dock 제외) 가운데에 화면 크기에 맞춘 창 크기를 정한다.
function panelRect(screen) {
  const v = screen.visibleFrame;
  const width = Math.min(640, v.size.width * 0.9);
  const height = Math.min(780, v.size.height * 0.88);
  return $.NSMakeRect(v.origin.x + (v.size.width - width) / 2, v.origin.y + (v.size.height - height) / 2, width, height);
}

function describeRect(rect) {
  return [rect.origin.x, rect.origin.y, rect.size.width, rect.size.height].map(Math.round).join(',');
}

function showPanel() {
  if (!state.panel) createPanel(false);
  // 열 때마다 다시 불러 guidebook.html 변경을 바로 반영한다.
  loadPage();
  const target = targetScreen(null);
  if (target) {
    const rect = panelRect(target.screen);
    state.panel.setFrameDisplay(rect, true);
    log('화면 ' + target.index + '(' + target.reason + ')에 표시 · ' + describeRect(rect));
  } else {
    state.panel.center;
    log('화면 정보를 못 읽어 가운데에 표시');
  }
  state.panel.makeKeyAndOrderFront(null);
  state.shownAt = Date.now();
  log('창 표시 · key=' + state.panel.isKeyWindow + ' visible=' + state.panel.isVisible);
  if (state.debug) state.handler.performSelectorWithObjectAfterDelay('reportFocus:', null, 0.5);
}

function setupMenubar() {
  const item = $.NSStatusBar.systemStatusBar.statusItemWithLength(-1); // NSVariableStatusItemLength
  item.button.title = $('📘 T3 스킬 가이드');
  item.button.toolTip = $('스킬 가이드북');
  item.button.target = state.handler;
  item.button.action = 'toggleGuide:';
  state.item = item;
  log('메뉴 막대 아이콘 표시 · visible=' + item.isVisible);
}

function optionValue(argv, name) {
  const arg = argv.find(value => value.startsWith(name + '='));
  return arg ? arg.slice(name.length + 1) : '';
}

function run(argv) {
  state.page = argv.find(arg => !arg.startsWith('--')) || '';
  if (!state.page) throw new Error('guidebook.html 경로가 필요합니다.');
  state.debug = argv.includes('--debug');
  state.menubar = argv.includes('--menubar');
  const check = argv.includes('--check');
  const quitAfter = Number(optionValue(argv, '--quit-after')) || 0;
  const clicks = optionValue(argv, '--click-after').split(',').map(Number).filter(value => value > 0);

  const app = $.NSApplication.sharedApplication;
  app.setActivationPolicy($.NSApplicationActivationPolicyAccessory);
  state.handler = $.GuideWindowHandler.alloc.init;

  const where = argv.find(arg => arg === '--where' || arg.startsWith('--where='));
  if (where) {
    const xy = optionValue(argv, '--where').split(',').map(Number);
    const point = xy.length === 2 && xy.every(Number.isFinite) ? { x: xy[0], y: xy[1] } : null;
    const lines = screenList().map((screen, i) => '화면 ' + i + ': ' + ObjC.unwrap(screen.localizedName)
      + ' · 전체 ' + describeRect(screen.frame) + ' · 사용 가능 ' + describeRect(screen.visibleFrame));
    const target = targetScreen(point);
    lines.push(target ? '창을 놓을 곳: 화면 ' + target.index + '(' + target.reason + ') · ' + describeRect(panelRect(target.screen))
      : '화면 정보를 읽지 못했습니다(샌드박스 안에서 실행했는지 확인).');
    return lines.join('\n');
  }

  if (check) {
    createPanel(true);
    loadPage();
    state.handler.performSelectorWithObjectAfterDelay('checkTimeout:', null, 10);
    app.run;
    return;
  }

  if (state.menubar) {
    setupMenubar();
    clicks.forEach(seconds => state.handler.performSelectorWithObjectAfterDelay('toggleGuide:', null, seconds));
  } else {
    showPanel();
  }
  if (quitAfter > 0) state.handler.performSelectorWithObjectAfterDelay('quitTimer:', null, quitAfter);
  app.run;
}
