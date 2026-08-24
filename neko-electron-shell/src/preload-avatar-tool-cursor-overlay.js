const { ipcRenderer } = require('electron');

const CHANNEL = 'neko:avatar-tool-cursor-overlay-state';

let cursorImage = null;
let lastImageUrl = '';

function ensureCursorImage() {
  if (cursorImage) return cursorImage;
  cursorImage = document.getElementById('cursor-image');
  return cursorImage;
}

function applyCursorState(state) {
  const image = ensureCursorImage();
  if (!image) return;

  if (!state || state.active !== true || !state.imageUrl) {
    image.hidden = true;
    image.style.transform = 'translate3d(-9999px, -9999px, 0)';
    return;
  }

  const imageUrl = String(state.imageUrl || '');
  if (imageUrl && imageUrl !== lastImageUrl) {
    image.src = imageUrl;
    lastImageUrl = imageUrl;
  }

  const x = Number.isFinite(Number(state.x)) ? Number(state.x) : -9999;
  const y = Number.isFinite(Number(state.y)) ? Number(state.y) : -9999;
  const hotspotX = Number.isFinite(Number(state.hotspotX)) ? Number(state.hotspotX) : 0;
  const hotspotY = Number.isFinite(Number(state.hotspotY)) ? Number(state.hotspotY) : 0;
  const scale = Number.isFinite(Number(state.scale)) ? Number(state.scale) : 1;
  const displayWidth = Number(state.displayWidth);
  const displayHeight = Number(state.displayHeight);
  const naturalWidth = Number(state.naturalWidth);
  const naturalHeight = Number(state.naturalHeight);
  const safeScale = scale > 0 ? scale : 1;
  const displayRatioX = Number.isFinite(naturalWidth) && naturalWidth > 0
    && Number.isFinite(displayWidth) && displayWidth > 0
    ? displayWidth / naturalWidth
    : 1;
  const displayRatioY = Number.isFinite(naturalHeight) && naturalHeight > 0
    && Number.isFinite(displayHeight) && displayHeight > 0
    ? displayHeight / naturalHeight
    : 1;
  const scaledHotspotX = hotspotX * displayRatioX * safeScale;
  const scaledHotspotY = hotspotY * displayRatioY * safeScale;

  if (Number.isFinite(displayWidth) && displayWidth > 0) {
    image.style.width = Math.round(displayWidth) + 'px';
  } else {
    image.style.removeProperty('width');
  }
  if (Number.isFinite(displayHeight) && displayHeight > 0) {
    image.style.height = Math.round(displayHeight) + 'px';
  } else {
    image.style.removeProperty('height');
  }

  image.hidden = false;
  image.style.transformOrigin = '0 0';
  image.style.transform = `translate3d(${Math.round(x - scaledHotspotX)}px, ${Math.round(y - scaledHotspotY)}px, 0) scale(${safeScale})`;
}

ipcRenderer.on(CHANNEL, (_event, state) => {
  applyCursorState(state);
});

window.addEventListener('DOMContentLoaded', () => {
  ensureCursorImage();
});
