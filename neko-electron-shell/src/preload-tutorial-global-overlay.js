const { ipcRenderer } = require('electron');

const CHANNEL = 'neko:tutorial-overlay-state';

let stage = null;
let cursor = null;
let cursorVisual = null;
let lastPetalId = '';
let lastCursorKey = '';
let lastCursorPoint = null;
let cursorWasVisible = false;
let cursorEffectTimer = null;
let avatarStandIn = null;
let avatarStandInHideTimer = null;
let lastAvatarStandInKey = '';
let lastAvatarStandInHideKey = '';
let expiredAvatarStandInHideKey = '';
const FALLBACK_CURSOR_MOVE_DURATION_MS = 560;
const spotlightPool = [];
const spotlightRenderKeys = [];

function ensureElements() {
  if (!stage) stage = document.getElementById('stage');
  if (!cursor) cursor = document.getElementById('cursor');
  if (cursor && !cursorVisual) {
    cursorVisual = cursor.querySelector('.cursor-visual');
    if (!cursorVisual) {
      cursorVisual = document.createElement('div');
      cursorVisual.className = 'cursor-visual';
      cursor.appendChild(cursorVisual);
    }
  }
}

function clearCursorEffectTimer() {
  if (cursorEffectTimer) {
    window.clearTimeout(cursorEffectTimer);
    cursorEffectTimer = null;
  }
}

function ensureSpotlight(index) {
  ensureElements();
  if (spotlightPool[index]) return spotlightPool[index];
  const element = document.createElement('div');
  element.className = 'spotlight';
  element.setAttribute('aria-hidden', 'true');
  ['spotlight-chrome', 'spotlight-sweep', 'spotlight-circle-skin', 'spotlight-ear-left', 'spotlight-ear-right', 'spotlight-paw'].forEach((className) => {
    const child = document.createElement(className === 'spotlight-sweep' ? 'span' : 'div');
    child.className = className;
    element.appendChild(child);
  });
  stage.appendChild(element);
  spotlightPool[index] = element;
  return element;
}

function ensureAvatarStandIn() {
  ensureElements();
  if (avatarStandIn && avatarStandIn.parentNode) return avatarStandIn;
  avatarStandIn = document.createElement('img');
  avatarStandIn.className = 'avatar-stand-in';
  avatarStandIn.alt = '';
  avatarStandIn.decoding = 'async';
  avatarStandIn.draggable = false;
  stage.appendChild(avatarStandIn);
  return avatarStandIn;
}

function hideUnusedSpotlights(fromIndex) {
  for (let index = fromIndex; index < spotlightPool.length; index += 1) {
    const element = spotlightPool[index];
    if (!element) continue;
    element.classList.remove('is-visible');
    element.hidden = true;
    spotlightRenderKeys[index] = '';
  }
}

function renderSpotlights(state) {
  const assets = state.assets || {};
  const spotlights = Array.isArray(state.spotlights) ? state.spotlights : [];
  spotlights.forEach((rect, index) => {
    const element = ensureSpotlight(index);
    const isCircle = rect.shape === 'circle';
    const variant = String(rect.variant || (isCircle ? 'circle-image' : '')).trim();
    const renderKey = [
      rect.id || '',
      rect.kind || '',
      rect.shape || '',
      variant,
    ].join('|');
    const shouldResetGeometry = element.hidden || spotlightRenderKeys[index] !== renderKey;
    if (shouldResetGeometry) {
      element.style.transition = 'none';
    }
    element.hidden = false;
    element.classList.toggle('is-circle', isCircle);
    element.classList.toggle('is-circle-image', isCircle && variant !== 'plain-circle' && variant !== 'circle-contained');
    element.classList.toggle('is-circle-contained', isCircle && variant === 'circle-contained');
    element.classList.toggle('is-plain-circle', isCircle && variant === 'plain-circle');
    element.classList.add('is-visible');
    element.style.left = Math.round(rect.x || 0) + 'px';
    element.style.top = Math.round(rect.y || 0) + 'px';
    element.style.width = Math.max(1, Math.round(rect.width || 1)) + 'px';
    element.style.height = Math.max(1, Math.round(rect.height || 1)) + 'px';
    element.style.borderRadius = (isCircle ? 999 : Math.max(0, Math.round(rect.radius || 24))) + 'px';
    element.style.backgroundImage = isCircle && variant === 'circle-contained' && assets.circleHighlightUrl
      ? `url("${assets.circleHighlightUrl}")`
      : '';
    element.style.setProperty('--left-ear-url', assets.leftCatEarUrl ? `url("${assets.leftCatEarUrl}")` : 'none');
    element.style.setProperty('--right-ear-url', assets.rightCatEarUrl ? `url("${assets.rightCatEarUrl}")` : 'none');
    element.style.setProperty('--paw-url', assets.catPawUrl ? `url("${assets.catPawUrl}")` : 'none');
    element.style.setProperty('--circle-url', assets.circleHighlightUrl ? `url("${assets.circleHighlightUrl}")` : 'none');
    spotlightRenderKeys[index] = renderKey;
    if (shouldResetGeometry) {
      void element.offsetWidth;
      element.style.transition = '';
    }
  });
  hideUnusedSpotlights(spotlights.length);
}

function renderCursor(state) {
  ensureElements();
  const assets = state.assets || {};
  const data = state.cursor || null;
  if (!data || data.visible === false) {
    lastCursorKey = '';
    cursorWasVisible = false;
    clearCursorEffectTimer();
    cursor.classList.remove('is-visible', 'is-clicking', 'is-wobbling');
    if (data && Number.isFinite(Number(data.x)) && Number.isFinite(Number(data.y))) {
      lastCursorPoint = {
        x: Math.round(Number(data.x)),
        y: Math.round(Number(data.y)),
      };
      cursor.style.transitionDuration = '0ms, 140ms';
      cursor.style.transform = `translate3d(${lastCursorPoint.x}px, ${lastCursorPoint.y}px, 0)`;
    }
    cursor.style.opacity = '0';
    return;
  }
  const x = Math.round(Number(data.x) || 0);
  const y = Math.round(Number(data.y) || 0);
  const requestedDurationMs = Math.max(0, Math.round(Number(data.durationMs) || 0));
  const durationMs = resolveCursorMoveDurationMs(x, y, requestedDurationMs);
  const chosenCursorUrl = data.effect === 'click'
    ? (assets.clickCursorUrl || assets.defaultCursorUrl || '')
    : (assets.defaultCursorUrl || '');
  const cursorKey = [
    x,
    y,
    durationMs,
    data.effect || '',
    chosenCursorUrl,
  ].join('|');
  const lastCursorKeyParts = String(lastCursorKey || '').split('|');
  const lastCursorEffect = lastCursorKeyParts.length >= 4 ? lastCursorKeyParts[3] : '';
  const isSamePointEffectRestore = !!(
    cursor.classList.contains('is-visible')
    && lastCursorPoint
    && x === lastCursorPoint.x
    && y === lastCursorPoint.y
    && durationMs === 0
    && !(data.effect || '')
    && (lastCursorEffect === 'click' || lastCursorEffect === 'wobble')
  );
  if (isSamePointEffectRestore) {
    lastCursorKey = cursorKey;
    clearCursorEffectTimer();
    if (cursorVisual) {
      cursorVisual.style.backgroundImage = chosenCursorUrl ? `url("${chosenCursorUrl}")` : '';
    }
    cursor.classList.remove('is-clicking', 'is-wobbling');
    lastCursorPoint = { x, y };
    cursorWasVisible = true;
    return;
  }
  if (cursorKey === lastCursorKey && cursor.classList.contains('is-visible')) {
    return;
  }
  lastCursorKey = cursorKey;
  clearCursorEffectTimer();
  cursor.style.transitionDuration = durationMs > 0 ? `${durationMs}ms, 140ms` : '0ms, 140ms';
  if (cursorVisual) {
    cursorVisual.style.backgroundImage = chosenCursorUrl ? `url("${chosenCursorUrl}")` : '';
  }
  cursor.style.transform = `translate3d(${x}px, ${y}px, 0)`;
  cursor.style.opacity = '';
  cursor.classList.add('is-visible');
  cursor.classList.remove('is-clicking', 'is-wobbling');
  lastCursorPoint = { x, y };
  cursorWasVisible = true;
  if (data.effect === 'click') {
    void cursor.offsetWidth;
    cursor.classList.add('is-clicking');
    cursorEffectTimer = window.setTimeout(() => {
      cursorEffectTimer = null;
      cursor.classList.remove('is-clicking');
      if (cursor.classList.contains('is-visible') && assets.defaultCursorUrl && cursorVisual) {
        cursorVisual.style.backgroundImage = `url("${assets.defaultCursorUrl}")`;
      }
    }, 430);
  } else if (data.effect === 'wobble') {
    void cursor.offsetWidth;
    cursor.classList.add('is-wobbling');
    cursorEffectTimer = window.setTimeout(() => {
      cursorEffectTimer = null;
      cursor.classList.remove('is-wobbling');
    }, 720);
  }
}

function resolveCursorMoveDurationMs(x, y, requestedDurationMs) {
  if (requestedDurationMs > 0) {
    return requestedDurationMs;
  }
  if (!cursorWasVisible || !lastCursorPoint) {
    return 0;
  }
  const distance = Math.hypot(x - lastCursorPoint.x, y - lastCursorPoint.y);
  if (distance < 2) {
    return 0;
  }
  return FALLBACK_CURSOR_MOVE_DURATION_MS;
}

function renderPetal(state) {
  ensureElements();
  const data = state.petal || null;
  if (!data || !data.url || data.id === lastPetalId) return;
  lastPetalId = data.id;
  const oldLayer = stage.querySelector('.petal-layer');
  if (oldLayer && oldLayer.parentNode) oldLayer.parentNode.removeChild(oldLayer);

  const layer = document.createElement('div');
  layer.className = 'petal-layer';
  const image = document.createElement('img');
  image.alt = '';
  image.decoding = 'async';
  image.draggable = false;
  image.src = data.url;
  image.style.setProperty('--petal-duration', `${Math.max(240, Math.round(Number(data.durationMs) || 2600))}ms`);
  image.style.setProperty('--petal-origin-x', `${Math.round(Number(data.originX) || window.innerWidth / 2)}px`);
  image.style.setProperty('--petal-origin-y', `${Math.round(Number(data.originY) || window.innerHeight / 2)}px`);
  image.style.setProperty('--petal-opacity', String(Number.isFinite(Number(data.finalOpacity)) ? Number(data.finalOpacity) : 0.92));
  layer.appendChild(image);
  stage.appendChild(layer);
  window.requestAnimationFrame(() => layer.classList.add('is-active'));
  const removeMs = Math.max(900, Math.round(Number(data.durationMs) || 2600)) + 650;
  window.setTimeout(() => {
    layer.classList.add('is-exiting');
    window.setTimeout(() => {
      if (layer.parentNode) layer.parentNode.removeChild(layer);
    }, 540);
  }, removeMs);
}

function normalizeAvatarStandInPosition(position) {
  const value = String(position || '').trim();
  if (
    value === 'bottom-right'
    || value === 'top-right-border'
    || value === 'top-left-border'
    || value === 'top-left-flipped'
    || value === 'middle-left'
  ) {
    return value;
  }
  return 'bottom-right';
}

function clearAvatarStandInState() {
  if (avatarStandInHideTimer) {
    window.clearTimeout(avatarStandInHideTimer);
    avatarStandInHideTimer = null;
  }
  lastAvatarStandInKey = '';
  lastAvatarStandInHideKey = '';
  expiredAvatarStandInHideKey = '';
  if (avatarStandIn && avatarStandIn.parentNode) {
    avatarStandIn.parentNode.removeChild(avatarStandIn);
  }
  avatarStandIn = null;
}

function renderAvatarStandIn(state) {
  const data = state.avatarStandIn || null;
  if (!data || data.visible === false || !data.url) {
    clearAvatarStandInState();
    return;
  }

  const position = normalizeAvatarStandInPosition(data.position);
  const durationMs = Math.max(0, Math.round(Number(data.durationMs) || 0));
  const renderKey = [
    data.url || '',
    data.resource || '',
    position,
  ].join('|');
  const hideKey = [
    renderKey,
    durationMs,
    data.refreshKey || '',
  ].join('|');
  if (hideKey === expiredAvatarStandInHideKey) {
    return;
  }

  const element = ensureAvatarStandIn();
  if (renderKey !== lastAvatarStandInKey) {
    element.className = 'avatar-stand-in avatar-stand-in-' + position;
    element.src = data.url;
    lastAvatarStandInKey = renderKey;
    void element.offsetWidth;
  }
  window.requestAnimationFrame(() => {
    if (avatarStandIn === element) {
      element.classList.add('is-visible');
    }
  });

  if (hideKey !== lastAvatarStandInHideKey) {
    if (avatarStandInHideTimer) {
      window.clearTimeout(avatarStandInHideTimer);
      avatarStandInHideTimer = null;
    }
    lastAvatarStandInHideKey = hideKey;
    expiredAvatarStandInHideKey = '';
    if (durationMs > 0) {
      avatarStandInHideTimer = window.setTimeout(() => {
        if (avatarStandIn === element && lastAvatarStandInHideKey === hideKey) {
          if (avatarStandIn && avatarStandIn.parentNode) {
            avatarStandIn.parentNode.removeChild(avatarStandIn);
          }
          avatarStandIn = null;
          avatarStandInHideTimer = null;
          lastAvatarStandInKey = '';
          expiredAvatarStandInHideKey = hideKey;
        }
      }, durationMs + 650);
    }
  }
}

function clearPetalState() {
  ensureElements();
  lastPetalId = '';
  const oldLayer = stage.querySelector('.petal-layer');
  if (oldLayer && oldLayer.parentNode) oldLayer.parentNode.removeChild(oldLayer);
}

function applyState(state) {
  ensureElements();
  if (!state || state.active !== true) {
    renderSpotlights({ spotlights: [], assets: {} });
    renderCursor({ cursor: null, assets: {} });
    clearPetalState();
    clearAvatarStandInState();
    return;
  }
  renderSpotlights(state);
  renderCursor(state);
  renderPetal(state);
  renderAvatarStandIn(state);
}
ipcRenderer.on(CHANNEL, (_event, state) => {
  applyState(state);
});

window.addEventListener('DOMContentLoaded', ensureElements);
