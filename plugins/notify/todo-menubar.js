// 할 일 목록을 맥 메뉴 막대에 보여 준다(macOS, JXA + WebKit).
// 메뉴 막대의 '🔔 할 일 N'은 todos.json을 1초마다 읽어 개수를 바꾼다. 누르면 작업 중인 화면 오른쪽 위에 목록 창을 열고 닫는다.
// 창이 열려 있는 동안 목록이 바뀌면 바로 다시 그린다. 버튼은 다음을 실행한다.
//   완료          notify.py todo done <id>
//   알아서 진행·선택  notify.py todo act <id> [--choice 선택] (그 T3 세션에 t3 thread send로 보낸다)
//   T3에서 답하기·열기  t3code://threads/<환경 id>/<세션 id> 링크로 T3 데스크톱 앱에서 그 세션을 연다
// 작업 중인 화면은 맨 앞 앱의 창이 있는 화면이고, 찾지 못하면 마우스가 있는 화면이다(가이드북 창과 같은 기준).
// 사용: osascript -l JavaScript todo-menubar.js <todo.html> <todos.json> <notify.py> [옵션]
//   --open           시작하자마자 목록 창을 연다(시험용).
//   --check          창을 띄우지 않고 페이지에 지금 목록을 넣어 본 뒤, 그려진 항목 수와 높이를 적고 끝낸다.
//   --debug          창 이벤트를 stderr에 적는다.
//   --quit-after=초   시험용. 지정한 시간이 지나면 끝낸다.
// 창은 앱을 활성화하지 않는 패널이라 다른 앱을 앞에 둔 채로 키보드 입력(Esc)을 받는다.
// Esc를 누르거나 다른 곳을 클릭하면 숨는다. 창 아래 '고정'을 켜면 다른 곳을 눌러도 숨지 않는다.
ObjC.import('Cocoa');
ObjC.import('WebKit');
ObjC.import('CoreGraphics');

const WIDTH = 380;
const MARGIN = 10;

const state = {
  page: '', file: '', script: '', debug: false, check: false, closing: false,
  handler: null, panel: null, web: null, item: null,
  raw: null, items: [], ready: false, pinned: false, contentHeight: 160, shownAt: 0, hiddenAt: 0
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

// todos.json을 읽는다. 내용이 바뀌었으면 true. 파일이 없으면 빈 목록이다.
function readTodos() {
  const text = $.NSString.stringWithContentsOfFileEncodingError($(state.file), $.NSUTF8StringEncoding, null);
  const raw = ObjC.unwrap(text) || '';
  if (raw === state.raw) return false;
  let items = [];
  if (raw) {
    try {
      const data = JSON.parse(raw);
      items = Array.isArray(data.items) ? data.items : [];
    } catch (error) {
      return false; // 해석하지 못하면 다음 틱에 다시 읽는다.
    }
  }
  state.raw = raw;
  state.items = items;
  return true;
}

function updateTitle() {
  const count = state.items.length;
  const button = state.item && state.item.button;
  if (button) {
    button.title = $('🔔 할 일 ' + count);
    button.appearsDisabled = count === 0;
    button.toolTip = $(count ? '할 일 ' + count + '개 — 눌러서 목록 보기' : '할 일이 없습니다');
  }
  if (state.panel) state.panel.title = $(count ? '할 일 ' + count + '개' : '할 일');
}

// 목록을 페이지에 넣는다. 페이지가 준비되기 전이면 준비 신호(ready)를 받은 뒤 넣는다.
function push() {
  if (!state.web || !state.ready) return;
  const payload = JSON.stringify({ items: state.items, pinned: state.pinned, check: state.check });
  // 완료 콜백을 비워 두면(null) WebKit이 콜백을 부를 때 프로그램이 죽는다. 빈 함수를 넘긴다.
  state.web.evaluateJavaScriptCompletionHandler($("render(" + payload + ")"), function (result, error) {});
}

// notify.py todo <args...>를 기다리지 않고 실행한다. 결과는 todos.json에 적히고 다음 틱에 보인다.
function runTodo(args) {
  try {
    const task = $.NSTask.alloc.init;
    task.launchPath = $('/usr/bin/python3');
    task.arguments = $([state.script, 'todo'].concat(args));
    task.standardOutput = $.NSFileHandle.fileHandleWithNullDevice;
    task.standardError = $.NSFileHandle.fileHandleWithNullDevice;
    task.launch;
    log('실행: todo ' + args.join(' '));
  } catch (error) {
    log('실행 실패: ' + error);
  }
}

const ITEM_ID = /^[0-9a-f]{1,32}$/i;

function runDone(id) {
  if (ITEM_ID.test(String(id))) runTodo(['done', String(id)]);
}

function runAct(id, choice) {
  if (!ITEM_ID.test(String(id))) return;
  const text = typeof choice === 'string' ? choice.trim().slice(0, 300) : '';
  runTodo(text ? ['act', String(id), '--choice', text] : ['act', String(id)]);
}

// T3 데스크톱 앱에서 세션을 연다. 환경 id는 ~/.t3/userdata/environment-id에 있다.
function openThread(thread) {
  if (!/^[A-Za-z0-9:_.-]{1,200}$/.test(String(thread))) return;
  const path = ObjC.unwrap($.NSHomeDirectory()) + '/.t3/userdata/environment-id';
  const env = (ObjC.unwrap($.NSString.stringWithContentsOfFileEncodingError($(path), $.NSUTF8StringEncoding, null)) || '').trim();
  if (!/^[A-Za-z0-9-]{1,80}$/.test(env)) {
    log('환경 id를 읽지 못했습니다: ' + path);
    return;
  }
  const url = $.NSURL.URLWithString($('t3code://threads/' + env + '/' + thread));
  if (!url || url.isNil()) return;
  $.NSWorkspace.sharedWorkspace.openURL(url);
  log('열기: ' + thread);
  if (!state.pinned) dismiss('T3 열기');
}

function dismiss(reason) {
  if (!state.panel || !state.panel.isVisible) return;
  log('숨김: ' + reason + ' (' + (Date.now() - state.shownAt) + 'ms)');
  state.hiddenAt = Date.now();
  state.panel.orderOut(null);
}

ObjC.registerSubclass({
  name: 'TodoMenubarHandler',
  superclass: 'NSObject',
  // 프로토콜 선언은 하지 않는다(JXA에서 "protocol does not exist" 오류). 메서드만 있으면 WebKit과 창이 호출한다.
  methods: {
    'userContentController:didReceiveScriptMessage:': {
      types: ['void', ['id', 'id']],
      implementation: function (controller, message) {
        const body = ObjC.deepUnwrap(message.body) || {};
        if (body.type === 'ready') {
          state.ready = true;
          push();
        } else if (body.type === 'size') {
          state.contentHeight = Math.max(80, Number(body.height) || 0);
          if (state.panel.isVisible) placePanel(false);
        } else if (body.type === 'done') {
          runDone(body.id);
        } else if (body.type === 'act') {
          runAct(body.id, body.choice);
        } else if (body.type === 'open') {
          openThread(body.thread);
        } else if (body.type === 'pin') {
          state.pinned = Boolean(body.on);
          log('고정: ' + state.pinned);
        } else if (body.type === 'close') {
          dismiss('Esc');
        } else if (body.type === 'check') {
          console.log(String(body.text));
          quit('검사 끝');
        }
      }
    },
    'windowDidResignKey:': {
      types: ['void', ['id']],
      implementation: function (notification) {
        // 창이 막 뜬 직후의 포커스 이동으로 숨지 않게 잠시 기다린다.
        if (!state.pinned && Date.now() - state.shownAt > 800) dismiss('다른 곳 클릭');
      }
    },
    'windowWillClose:': {
      types: ['void', ['id']],
      implementation: function (notification) { state.hiddenAt = Date.now(); }
    },
    'toggleList:': {
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
    'tick:': {
      types: ['void', ['id']],
      implementation: function (timer) {
        if (readTodos()) {
          updateTitle();
          push();
        }
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

function createPanel() {
  const rect = $.NSMakeRect(0, 0, WIDTH, 200);
  // 작은 제목 막대의 패널(UtilityWindow = 16)이고, 앱을 활성화하지 않는다(NonactivatingPanel = 128).
  const style = $.NSWindowStyleMaskTitled | $.NSWindowStyleMaskClosable
    | ($.NSWindowStyleMaskUtilityWindow || 16) | ($.NSWindowStyleMaskNonactivatingPanel || 128);
  const panel = $.NSPanel.alloc.initWithContentRectStyleMaskBackingDefer(rect, style, $.NSBackingStoreBuffered, false);
  panel.floatingPanel = true;
  panel.hidesOnDeactivate = false;
  panel.becomesKeyOnlyIfNeeded = false;
  panel.level = $.NSFloatingWindowLevel;
  // 지금 보고 있는 Space에 뜨고, 전체 화면 앱 위에도 뜬다(MoveToActiveSpace | FullScreenAuxiliary).
  panel.collectionBehavior = (1 << 1) | (1 << 8);
  panel.releasedWhenClosed = false;
  panel.delegate = state.handler;

  const config = $.WKWebViewConfiguration.alloc.init;
  config.userContentController.addScriptMessageHandlerName(state.handler, 'todo');
  const web = $.WKWebView.alloc.initWithFrameConfiguration(rect, config);
  web.autoresizingMask = $.NSViewWidthSizable | $.NSViewHeightSizable;
  panel.contentView = web;
  state.panel = panel;
  state.web = web;
  updateTitle();
  const url = $.NSURL.fileURLWithPath($(state.page));
  web.loadFileURLAllowingReadAccessToURL(url, url.URLByDeletingLastPathComponent);
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
  const windows = ObjC.deepUnwrap(ObjC.castRefToObject($.CGWindowListCopyWindowInfo(1 | 16, 0))) || [];
  const win = windows.find(w => w.kCGWindowOwnerPID === pid && w.kCGWindowLayer === 0
    && w.kCGWindowBounds && w.kCGWindowBounds.Width > 50 && w.kCGWindowBounds.Height > 50);
  if (!win) return null;
  const b = win.kCGWindowBounds;
  const primaryHeight = screenList()[0].frame.size.height;
  return { x: b.X + b.Width / 2, y: primaryHeight - (b.Y + b.Height / 2) };
}

function targetScreen() {
  const screens = screenList();
  if (screens.length === 0) return null;
  const front = frontWindowCenter();
  let index = front ? screenIndexAt(front) : -1;
  if (index < 0) index = screenIndexAt($.NSEvent.mouseLocation);
  return screens[index < 0 ? 0 : index];
}

// 창 크기를 내용 높이에 맞춘다. fresh면 작업 중인 화면 오른쪽 위로 옮기고, 아니면 위쪽 가장자리를 그대로 둔다.
function placePanel(fresh) {
  const current = state.panel.frame;
  const screen = fresh ? targetScreen() : state.panel.screen;
  const v = screen && !screen.isNil() ? screen.visibleFrame : null;
  const maxContent = v ? v.size.height * 0.75 : 600;
  const content = $.NSMakeRect(0, 0, WIDTH, Math.min(state.contentHeight, maxContent));
  const size = state.panel.frameRectForContentRect(content).size;
  let x = current.origin.x;
  let top = current.origin.y + current.size.height;
  if (fresh && v) {
    x = v.origin.x + v.size.width - size.width - MARGIN;
    top = v.origin.y + v.size.height - MARGIN / 2;
  }
  state.panel.setFrameDisplay($.NSMakeRect(x, top - size.height, size.width, size.height), true);
}

function showPanel() {
  if (!state.panel) createPanel();
  placePanel(true);
  state.panel.makeKeyAndOrderFront(null);
  state.shownAt = Date.now();
  log('창 표시 · key=' + state.panel.isKeyWindow);
}

function setupMenubar() {
  const item = $.NSStatusBar.systemStatusBar.statusItemWithLength(-1); // NSVariableStatusItemLength
  item.button.target = state.handler;
  item.button.action = 'toggleList:';
  state.item = item;
  updateTitle();
}

function optionValue(argv, name) {
  const arg = argv.find(value => value.startsWith(name + '='));
  return arg ? arg.slice(name.length + 1) : '';
}

function run(argv) {
  const paths = argv.filter(arg => !arg.startsWith('--'));
  [state.page, state.file, state.script] = paths;
  if (!state.page || !state.file || !state.script) {
    throw new Error('사용: todo-menubar.js <todo.html> <todos.json> <notify.py> [--open|--check|--debug]');
  }
  state.debug = argv.includes('--debug');
  state.check = argv.includes('--check');
  const quitAfter = Number(optionValue(argv, '--quit-after')) || 0;

  const app = $.NSApplication.sharedApplication;
  app.setActivationPolicy($.NSApplicationActivationPolicyAccessory);
  state.handler = $.TodoMenubarHandler.alloc.init;
  readTodos();

  if (state.check) {
    createPanel();
    state.handler.performSelectorWithObjectAfterDelay('checkTimeout:', null, 10);
    app.run;
    return;
  }

  setupMenubar();
  $.NSTimer.scheduledTimerWithTimeIntervalTargetSelectorUserInfoRepeats(1, state.handler, 'tick:', null, true);
  if (argv.includes('--open')) state.handler.performSelectorWithObjectAfterDelay('toggleList:', null, 0.3);
  if (quitAfter > 0) state.handler.performSelectorWithObjectAfterDelay('quitTimer:', null, quitAfter);
  app.run;
}
