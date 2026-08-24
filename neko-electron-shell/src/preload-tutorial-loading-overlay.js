const { ipcRenderer } = require('electron');

const CHANNEL = 'neko:tutorial-loading-overlay-state';

let stage = null;
let loadingLayer = null;

function ensureElements() {
  if (!stage) {
    stage = document.getElementById('stage');
  }
}

function clearLoadingState() {
  if (loadingLayer && loadingLayer.parentNode) {
    loadingLayer.parentNode.removeChild(loadingLayer);
  }
  loadingLayer = null;
}

function renderLoading(state) {
  ensureElements();
  const data = state && state.loading ? state.loading : null;
  if (!stage || !data || data.visible === false) {
    clearLoadingState();
    return;
  }
  if (!loadingLayer || !loadingLayer.parentNode) {
    loadingLayer = document.createElement('div');
    loadingLayer.className = 'tutorial-loading';

    const loadingStage = document.createElement('div');
    loadingStage.className = 'tutorial-loading-stage';

    const loadingCat = document.createElement('img');
    loadingCat.className = 'tutorial-loading-cat';
    loadingCat.alt = '';
    loadingCat.decoding = 'async';
    loadingCat.draggable = false;
    loadingStage.appendChild(loadingCat);

    const loadingWave = document.createElement('img');
    loadingWave.className = 'tutorial-loading-wave';
    loadingWave.alt = '';
    loadingWave.decoding = 'async';
    loadingWave.draggable = false;
    loadingStage.appendChild(loadingWave);

    loadingLayer.appendChild(loadingStage);
    stage.appendChild(loadingLayer);
  }

  const loadingCat = loadingLayer.querySelector('.tutorial-loading-cat');
  if (loadingCat) {
    loadingCat.src = data.loadCatUrl || '';
  }
  const loadingWave = loadingLayer.querySelector('.tutorial-loading-wave');
  if (loadingWave) {
    loadingWave.src = data.loadingWaveUrl || '';
  }
}

function applyState(state) {
  ensureElements();
  if (!state || state.active !== true) {
    clearLoadingState();
    return;
  }
  renderLoading(state);
}

ipcRenderer.on(CHANNEL, (_event, state) => {
  applyState(state);
});

window.addEventListener('DOMContentLoaded', ensureElements);
