// compact 独立球窗口的 preload —— minimized 态毛线球折叠后，对话框被 hide、
// 球独立 BrowserWindow 作为可视入口出现，用户点球恢复对话框、拖球同时拖动对话框
// （隐藏态下也同步 setBounds，保证下次展开左下角对齐到球当前位置）。
const { ipcRenderer } = require('electron');
const { COMPACT_CHAT_BALL_CHANNELS, F8_FADE_CHANNELS } = require('./ipc-channels');

// 拖动判定阈值：pointerdown 后移动超过此距离才视为拖动，否则视为 click
const DRAG_THRESHOLD_PX = 4;
const APPEAR_ANIMATION_NAMES = {
  'neko-ball-appear': true,
  'neko-ball-appear-frames': true,
};
const BOUNCE_ANIMATION_NAMES = {
  'neko-ball-bounce': true,
  'neko-ball-bounce-frames': true,
};

// 球可见状态管理：
// CSS 默认 opacity:0（防止 showInactive 在页面加载/动画前闪现全尺寸球）。
// appear 动画期间 opacity:1（CSS class 控制）。appear 结束后设 inline opacity:1
// 保持可见。bounce 前清 inline style 让 bounce 动画自行控制 opacity（含末尾淡出）。
// bounce 结束后 class 移除，CSS 默认 opacity:0 生效，球不可见。
function showBall(button) {
  button.style.opacity = '1';
}
function hideBallForBounce(button) {
  button.style.opacity = '';
}

function isKnownAnimationName(animationName, names) {
  return !animationName || !!names[animationName];
}

function extractBackgroundImageUrlCandidates(backgroundImage) {
  var candidates = [];
  if (!backgroundImage || backgroundImage === 'none') return '';
  var matcher = /url\((?:"([^"]+)"|'([^']+)'|([^)]*))\)\s*([0-9]*\.?[0-9]+)?\s*(x|dppx)?/g;
  var match;
  while ((match = matcher.exec(backgroundImage))) {
    var url = (match[1] || match[2] || match[3] || '').trim();
    if (!url) continue;
    candidates.push({
      url,
      scale: Number(match[4]) > 0 ? Number(match[4]) : 1,
    });
  }
  return candidates;
}

function extractBackgroundImageUrlForDevicePixelRatio(backgroundImage, devicePixelRatio) {
  var candidates = extractBackgroundImageUrlCandidates(backgroundImage);
  if (!candidates || !candidates.length) {
    return (backgroundImage || '').replace(/^url\(["']?|["']?\)$/g, '').trim();
  }
  var dpr = Number(devicePixelRatio);
  if (!Number.isFinite(dpr) || dpr <= 0) dpr = 1;
  candidates.sort(function (a, b) { return a.scale - b.scale; });
  for (var i = 0; i < candidates.length; i += 1) {
    if (candidates[i].scale >= dpr) return candidates[i].url;
  }
  return candidates[candidates.length - 1].url;
}


window.addEventListener('DOMContentLoaded', () => {
  var button = document.querySelector('[data-compact-chat-ball]');
  if (!button) return;

  // compat recreate 缩短入场动画：F8 恢复场景不需要 380ms 的 scale 动画，
  // 但完全跳过会在精灵图未解码时揭示白圈。等具体背景图解码完成后再发 APPEAR_DONE，
  // 把延迟从 ~600ms 压到 ~100-150ms。
  if (window.__nekoSkipAppear) {
    var _sendDone = function () {
      button.style.opacity = '1';
      try { ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.APPEAR_DONE); } catch (_) {}
    };
    var _imgSrc = extractBackgroundImageUrlForDevicePixelRatio(
      getComputedStyle(button).backgroundImage,
      window.devicePixelRatio,
    );
    if (!_imgSrc) {
      _sendDone();
    } else {
      var _img = new Image();
      _img.src = _imgSrc;
      if (_img.decode) {
        _img.decode().then(_sendDone).catch(_sendDone);
      } else {
        _sendDone();
      }
    }
  } else {
    // 入场动画：球窗口创建后首帧「从底部长出来 + 轻微放大」（CSS @keyframes neko-ball-appear-frames）。
    // CSS 默认 opacity:0 盖住 loadURL→showInactive 之间的空帧。animationend 后用 inline
    // opacity:1 保持可见（移除 class 后不会回到 CSS 默认 opacity:0）。
    button.classList.add('neko-ball-appearing');
    button.addEventListener('animationend', function onAppearEnd(e) {
      if (e && !isKnownAnimationName(e.animationName, APPEAR_ANIMATION_NAMES)) return;
      button.classList.remove('neko-ball-appearing');
      button.removeEventListener('animationend', onAppearEnd);
      // appear 结束：inline opacity:1 保持球可见
      showBall(button);
      // 通知主进程球已完全就绪（opacity:1 已设），compat 路径收到后执行 showInactive + setShape
      try { ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.APPEAR_DONE); } catch (_) {}
    });
  }

  // macOS 窗口复用：窗口被 hide 后重新 showInactive 时不触发 DOMContentLoaded。
  // 监听 IPC 信号重播入场动画。
  ipcRenderer.on('neko:ball-reappear', () => {
    if (!button) return;
    button.classList.remove('neko-ball-appearing');
    button.classList.remove('neko-ball-bouncing');
    hideBallForBounce(button); // 清 inline style，让动画 CSS 的 opacity:1 控制
    void button.offsetWidth;
    button.classList.add('neko-ball-appearing');
    function onReappearEnd(e) {
      if (e && !isKnownAnimationName(e.animationName, APPEAR_ANIMATION_NAMES)) return;
      button.classList.remove('neko-ball-appearing');
      button.removeEventListener('animationend', onReappearEnd);
      showBall(button);
    }
    button.addEventListener('animationend', onReappearEnd);
  });

  // dragState 仅在 pointerdown ↔ pointerup 之间存活：
  //   pointerId / startScreenX / startScreenY —— pointer 事件起点（屏幕坐标，
  //     不受窗口移动影响，所以拖动跟随期间用 e.screenX - startScreenX 作偏移）
  //   startWindowX / startWindowY —— pointerdown 瞬间球窗口的屏幕坐标（用
  //     window.screenX / window.screenY 同步读取，无需 IPC roundtrip 即可立刻
  //     开始跟随；zoomFactor=1.0 保证 CSS 像素 = 屏幕像素）
  //   moved —— 是否已超过阈值进入「拖动」语义（一旦 true 则 pointerup 不发 CLICK）
  var dragState = null;

  // 恢复握手状态：球点击后播 bounce 动画，但**只有同时满足**「动画播完(_animEnded)」+
  // 「main 回了 RESTORE_ACK 确认 restore 真的发生(_restored)」才自行 HIDE。若这次 CLICK 因
  // chat renderer 正在 reload / CLICK listener 未装而被丢弃（收不到 ACK），球就一直留着且
  // 可点，避免「球消失 + 对话框仍 opacity 0」两头落空。每次新点击（开新周期）时重置。
  var _restored = false;
  var _animEnded = false;
  function maybeHideBall() {
    if (_restored && _animEnded) {
      try { ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.HIDE); } catch (_) {}
    }
  }
  ipcRenderer.on(COMPACT_CHAT_BALL_CHANNELS.RESTORE_ACK, () => {
    _restored = true;
    maybeHideBall();
  });

  button.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    // 恢复弹跳进行中（restore 周期未结束）：忽略新的按下，既不开始拖动也不触发点击 ——
    // 否则在 doExpand 隐性定位对话框的同时拖球会派 DRAG_MOVE 把球+对话框移走、与定位竞态错位。
    // bounce 结束后（含 restore 被丢弃、球留存的情况）class 已移除，交互恢复正常。
    if (button.classList.contains('neko-ball-bouncing')) return;
    var captureOk = false;
    try { button.setPointerCapture(e.pointerId); captureOk = true; } catch (_) {}
    void captureOk;
    dragState = {
      pointerId: e.pointerId,
      startScreenX: e.screenX,
      startScreenY: e.screenY,
      startWindowX: window.screenX,
      startWindowY: window.screenY,
      moved: false,
    };
  });

  button.addEventListener('pointermove', (e) => {
    if (!dragState || e.pointerId !== dragState.pointerId) return;
    var dx = e.screenX - dragState.startScreenX;
    var dy = e.screenY - dragState.startScreenY;
    if (!dragState.moved && Math.hypot(dx, dy) >= DRAG_THRESHOLD_PX) {
      dragState.moved = true;
    }
    if (!dragState.moved) return;
    // DRAG_MOVE：main 收到后同时移动球窗口和 hidden 的 reactChatWindow。坐标为
    // 球窗口的目标左上角屏幕坐标。
    ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.DRAG_MOVE, {
      x: dragState.startWindowX + dx,
      y: dragState.startWindowY + dy,
    });
  });

  function endPointer(e) {
    if (!dragState || e.pointerId !== dragState.pointerId) return;
    try { button.releasePointerCapture(e.pointerId); } catch (_) {}
    var wasDrag = dragState.moved;
    dragState = null;
    if (wasDrag) {
      // 真实拖动结束：让 main 把球（及同步的对话框窗口）夹回工作区，避免甩出屏幕外。
      try { ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.DRAG_END); } catch (_) {}
      return;
    }
    // bounce 动画还在播 = 上一次点击的恢复周期未结束 → 忽略这次点击：避免弹跳期二次点击
    // 重置握手状态/重复触发。bounce 结束后（含 restore 被丢弃、球留存的情况）class 已移除，
    // 再点即开新周期可重试。（chat 侧 CLICK handler 在非 minimized 时已是 no-op，二次点击
    // 即使发到 chat 也不会误折叠，这里再挡一层是为了不打乱本窗口的握手状态。）
    if (button.classList.contains('neko-ball-bouncing')) return;
    // 未拖动 = 点击：开新恢复周期。重置握手状态，播 bounce 动画，发 CLICK 触发 chat
    // 的 doExpand。对话框 ~140ms 揭示（与球弹跳并发），球弹完 + 收到 RESTORE_ACK 才隐藏。
    _restored = false;
    _animEnded = false;
    try {
      button.classList.remove('neko-ball-appearing'); // 入场动画若还在播，先清掉，避免与 bounce 冲突
      button.classList.remove('neko-ball-bouncing');
      hideBallForBounce(button); // 清 inline opacity，让 bounce 动画 CSS 控制 opacity
      void button.offsetWidth;
      button.classList.add('neko-ball-bouncing');
    } catch (_) {}
    ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.CLICK);
  }

  button.addEventListener('pointerup', endPointer);
  button.addEventListener('pointercancel', endPointer);
  // bounce 动画结束：移除 class（下次点击靠 remove+add 重新触发），标记动画已结束，
  // 再尝试隐藏 —— 只有同时收到 RESTORE_ACK（restore 确认发生）才真正 HIDE；否则（CLICK 被
  // 丢弃、restore 没跑）球留存且可点，等用户重试。正常流程 ACK 在揭示时到（稳定后揭示，略晚于旧
  // ~140ms），球照样弹满整段动画（~760ms，含落定后保持可见的尾巴，桥接文本框揭示）再隐藏。
  button.addEventListener('animationend', (e) => {
    if (e && !isKnownAnimationName(e.animationName, BOUNCE_ANIMATION_NAMES)) return;
    try { button.classList.remove('neko-ball-bouncing'); } catch (_) {}
    // bounce 结束后 class 移除，CSS 默认 opacity:0 生效，球不可见。
    // 如果 restore 被丢弃（球留存），需要让球恢复可见以便用户重试：
    // maybeHideBall 只在 _restored && _animEnded 时才 HIDE；若 !_restored 则球留存，
    // 此时需要恢复 inline opacity:1。
    if (!_restored) {
      showBall(button);
    }
    _animEnded = true;
    maybeHideBall();
  });

  // F8 兼容模式 CSS 淡入淡出：主进程不碰 setOpacity（DWM bug），由渲染进程 CSS transition
  // 负责视觉效果。淡出结束回复 FADE_OUT_DONE，主进程再执行 setShape(1x1) 物理隔离。
  ipcRenderer.on(F8_FADE_CHANNELS.FADE_OUT, () => {
    if (!button) return;
    button.style.transition = 'opacity 200ms ease-out';
    button.style.opacity = '0';
    var fadeOutDone = false;
    function onFadeOutEnd(e) {
      if (e && e.propertyName !== 'opacity') return;
      if (fadeOutDone) return;
      fadeOutDone = true;
      button.removeEventListener('transitionend', onFadeOutEnd);
      button.style.transition = '';
      try { ipcRenderer.send(F8_FADE_CHANNELS.FADE_OUT_DONE); } catch (_) {}
    }
    button.addEventListener('transitionend', onFadeOutEnd);
    // 保底：transitionend 可能不触发（display:none、窗口被提前 hide 等），200ms 后强制回复
    setTimeout(onFadeOutEnd, 220);
  });
  ipcRenderer.on(F8_FADE_CHANNELS.FADE_IN, () => {
    if (!button) return;
    // 窗口已被主进程 setShape([]) 恢复尺寸，但 CSS 仍为 opacity:0，用户看不到
    button.style.transition = 'opacity 200ms ease-in';
    button.style.opacity = '1';
    function onFadeInEnd(e) {
      if (e && e.propertyName !== 'opacity') return;
      button.removeEventListener('transitionend', onFadeInEnd);
      button.style.transition = '';
    }
    button.addEventListener('transitionend', onFadeInEnd);
    setTimeout(onFadeInEnd, 220);
  });

  // 抑制合成 click：pointerdown→pointerup 之后浏览器还会派发一个合成 click 事件，
  // 而 endPointer 已经在 pointerup 里发过 CLICK 了。这里 preventDefault 把这个合成 click
  // 拦掉，避免二次 send CLICK。（Electron/Chromium 下 pointer 事件始终可用，不存在
  // 「pointer 不支持需要 click 兜底」的场景，所以这里只做抑制、不再补发 CLICK。）
  button.addEventListener('click', (event) => {
    event.preventDefault();
  });
});
