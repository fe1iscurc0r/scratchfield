'use strict';

const { pathToFileURL } = require('node:url');
const { escapeHtml, safeScriptJson } = require('./html-escape');

function escapeCssString(value) {
  return String(value || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\a ');
}

function resolveAssetPath(app, path, fileName) {
  const basePath = app.isPackaged ? process.resourcesPath : process.cwd();
  return path.join(basePath, fileName);
}

function readAssetDataUrl(fs, filePath, mimeType, log, label) {
  try {
    if (fs.existsSync(filePath)) {
      const buffer = fs.readFileSync(filePath);
      return `data:${mimeType};base64,${buffer.toString('base64')}`;
    }
  } catch (err) {
    log(`读取 ${label} 失败:`, err.message);
  }
  return '';
}

function resolveAssetUrl({ app, assetMode, fs, log, mimeType, path, fileName }) {
  const filePath = resolveAssetPath(app, path, fileName);
  if (assetMode === 'file') {
    return fs.existsSync(filePath) ? pathToFileURL(filePath).href : '';
  }
  return readAssetDataUrl(fs, filePath, mimeType, log, fileName);
}

function setProgress(progressByTitle, title, progress) {
  if (title) progressByTitle[title] = progress;
}

function createLoadingWindowDataUrlBuilder(context) {
  const {
    fs,
    getApp,
    getCurrentLanguage,
    getLoadingWindowStatus,
    loadingText,
    log,
    path,
  } = context;

function getLoadingHTML(ratio = 1, options = {}) {
  const app = getApp();
  const currentLanguage = getCurrentLanguage();
  const loadingWindowStatus = getLoadingWindowStatus();
  const assetMode = options.assetMode === 'file' ? 'file' : 'inline';
  const bannerUrl = resolveAssetUrl({
    app,
    assetMode,
    fs,
    log,
    mimeType: 'image/png',
    path,
    fileName: 'launcher_banner.png',
  });
  const loadCatUrl = resolveAssetUrl({
    app,
    assetMode,
    fs,
    log,
    mimeType: 'image/gif',
    path,
    fileName: 'load_cat.gif',
  });
  const bannerBackground = bannerUrl ? `url("${escapeCssString(bannerUrl)}")` : 'none';
  const loadingStripPaddingY = Math.max(3, Math.round(5 * ratio));
  const loadingStripPaddingLeft = Math.max(5, Math.round(7 * ratio));
  const loadingStripPaddingRight = Math.max(14, Math.round(26 * ratio));
  const loadingCatAnchorOffset = Math.max(0, Math.max(58, Math.round(108 * ratio)) - Math.max(4, Math.round(8 * ratio)));
  const completionProgressByTitle = {};
  setProgress(completionProgressByTitle, loadingText('loadingReadyTitle'), 1);
  setProgress(completionProgressByTitle, loadingText('loadingAttachedTitle'), 1);
  const initialProgress = completionProgressByTitle[loadingWindowStatus.title] ?? 0;

  return `
<!DOCTYPE html>
<html lang="${escapeHtml(currentLanguage || 'en')}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${escapeHtml(loadingText('loadingDocumentTitle'))}</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        html,
        body {
            width: 100vw;
            height: 100vh;
            -webkit-app-region: drag;
            cursor: grab;
        }
        body {
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            background: transparent;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
            overflow: hidden;
        }
        .loading-container {
            position: relative;
            width: 100vw;
            height: 100vh;
            -webkit-app-region: drag;
            cursor: grab;
            display: flex;
            flex-direction: column;
            justify-content: flex-end;
            align-items: center;
            text-align: center;
            background-image: ${bannerBackground};
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            overflow: hidden;
        }
        .loading-strip {
            position: absolute;
            left: 57.9%;
            right: 3.4%;
            bottom: 4.8%;
            height: 8.2%;
            min-height: ${Math.max(34, Math.round(62 * ratio))}px;
            max-height: ${Math.max(42, Math.round(82 * ratio))}px;
            display: flex;
            align-items: center;
            padding: ${loadingStripPaddingY}px ${loadingStripPaddingRight}px ${loadingStripPaddingY}px ${loadingStripPaddingLeft}px;
            border-radius: ${Math.max(14, Math.round(22 * ratio))}px;
            background: rgba(255, 255, 255, 0.96);
            box-shadow: 0 ${Math.max(2, Math.round(4 * ratio))}px ${Math.max(12, Math.round(24 * ratio))}px rgba(45, 91, 172, 0.24);
            pointer-events: none;
            user-select: none;
            z-index: 1;
        }
        .loading-track {
            position: relative;
            flex: 1 1 auto;
            height: 88%;
            min-width: 0;
            border-radius: ${Math.max(11, Math.round(17 * ratio))}px;
            overflow: hidden;
            background: transparent;
        }
        .loading-progress {
            position: absolute;
            left: 0;
            top: 0;
            height: 100%;
            width: 100%;
            max-width: 100%;
            border-radius: inherit;
            overflow: hidden;
            background: linear-gradient(90deg, #5bb5ff 0%, #a5d6ff 100%);
            transform: scaleX(var(--loading-progress, ${initialProgress}));
            transform-origin: left center;
            will-change: transform;
        }
        .loading-progress::after {
            content: '';
            position: absolute;
            inset: 0;
            width: 42%;
            background: linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.42) 50%, rgba(255,255,255,0) 100%);
            transform: translateX(-120%);
            animation: loading-sheen 1.8s ease-in-out infinite;
        }
        .loading-cat {
            position: absolute;
            top: -136%;
            left: ${loadingStripPaddingLeft}px;
            height: 340%;
            max-height: ${Math.max(144, Math.round(264 * ratio))}px;
            aspect-ratio: 1 / 1;
            object-fit: contain;
            pointer-events: none;
            user-select: none;
            image-rendering: auto;
            will-change: transform;
        }
        .status-panel {
            display: none;
            position: absolute;
            left: ${Math.max(18, Math.round(28 * ratio))}px;
            top: ${Math.max(90, Math.round(110 * ratio))}px;
            max-width: min(60vw, ${Math.round(420 * ratio)}px);
            text-align: left;
            color: rgba(255, 255, 255, 0.96);
            text-shadow: 0 1px 3px rgba(0, 0, 0, 0.65), 0 2px 10px rgba(0, 0, 0, 0.45);
            pointer-events: none;
            user-select: none;
            z-index: 2;
        }
        .status-title {
            font-size: ${Math.max(14, Math.round(20 * ratio))}px;
            font-weight: 700;
            line-height: 1.2;
            letter-spacing: 0;
        }
        .status-detail {
            margin-top: ${Math.max(2, Math.round(4 * ratio))}px;
            font-size: ${Math.max(11, Math.round(14 * ratio))}px;
            line-height: 1.25;
            color: rgba(255, 255, 255, 0.78);
            letter-spacing: 0;
        }
        .status-dots::after {
            content: '';
            animation: dots 1.2s steps(4, end) infinite;
        }
        @keyframes dots {
            0% { content: ''; }
            25% { content: '.'; }
            50% { content: '..'; }
            75%, 100% { content: '...'; }
        }
        @keyframes loading-sheen {
            0% { transform: translateX(-120%); }
            60%, 100% { transform: translateX(260%); }
        }
    </style>
</head>
<body>
    <div class="loading-container">
        <div class="loading-strip" aria-hidden="true">
            <div class="loading-track">
                <div id="loading-progress" class="loading-progress"></div>
            </div>
            <img id="loading-cat" class="loading-cat" src="${escapeHtml(loadCatUrl)}" alt="" data-anchor-offset="${loadingCatAnchorOffset}" />
        </div>
        <div class="status-panel">
            <div id="loading-title" class="status-title">${escapeHtml(loadingWindowStatus.title)}<span class="status-dots"></span></div>
            <div id="loading-detail" class="status-detail">${escapeHtml(loadingWindowStatus.detail)}</div>
        </div>
    </div>
    <script>
        var __nekoLoadingCompletionProgressByTitle = ${safeScriptJson(completionProgressByTitle)};
        var __nekoLoadingStartedAt = Date.now();
        var __nekoLoadingProgressFrame = null;
        var __nekoLoadingProgressComplete = ${initialProgress >= 1 ? 'true' : 'false'};
        function __nekoApplyLoadingProgress(progress) {
            var next = Number(progress);
            if (!isFinite(next)) return;
            next = Math.max(0, Math.min(1, next));
            document.documentElement.style.setProperty('--loading-progress', String(next));
            var progressEl = document.getElementById('loading-progress');
            if (progressEl) {
                progressEl.style.transform = 'scaleX(' + next.toFixed(4) + ')';
            }
            var cat = document.getElementById('loading-cat');
            var track = document.querySelector('.loading-track');
            if (cat && track) {
                var travel = Math.max(0, track.clientWidth);
                var catWidth = Math.max(0, cat.offsetWidth || 0);
                var catAnchorOffset = Number(cat.getAttribute('data-anchor-offset')) || 0;
                cat.style.transform = 'translateX(' + (next * travel + catAnchorOffset - catWidth).toFixed(2) + 'px)';
            }
        }
        function __nekoGetTimedLoadingProgress(elapsedMs) {
            var firstPhaseMs = 6000;
            var slowPhaseMs = 10000;
            if (elapsedMs <= firstPhaseMs) {
                return 0.7 * Math.max(0, elapsedMs / firstPhaseMs);
            }
            var slowElapsed = elapsedMs - firstPhaseMs;
            if (slowElapsed <= slowPhaseMs) {
                var slowRatio = Math.max(0, Math.min(1, slowElapsed / slowPhaseMs));
                var slowed = 1 - Math.pow(1 - slowRatio, 3);
                return 0.7 + slowed * 0.1;
            }
            var stepElapsed = slowElapsed - slowPhaseMs;
            var stepProgress = stepElapsed / 100000;
            return Math.min(0.9, 0.8 + stepProgress);
        }
        function __nekoScheduleTimedLoadingProgress() {
            if (__nekoLoadingProgressComplete) return;
            if (__nekoLoadingProgressFrame !== null) {
                cancelAnimationFrame(__nekoLoadingProgressFrame);
                __nekoLoadingProgressFrame = null;
            }
            __nekoLoadingProgressFrame = requestAnimationFrame(function tick() {
                if (__nekoLoadingProgressComplete) return;
                var next = __nekoGetTimedLoadingProgress(Date.now() - __nekoLoadingStartedAt);
                __nekoApplyLoadingProgress(next);
                if (next < 0.9) {
                    __nekoLoadingProgressFrame = requestAnimationFrame(tick);
                } else {
                    __nekoLoadingProgressFrame = null;
                }
            });
        }
        __nekoApplyLoadingProgress(${initialProgress});
        __nekoScheduleTimedLoadingProgress();
        window.__nekoSetLoadingStatus = function(payload) {
            try {
                var title = document.getElementById('loading-title');
                var detail = document.getElementById('loading-detail');
                if (title && typeof payload.title === 'string') {
                    title.firstChild.nodeValue = payload.title;
                }
                if (detail && typeof payload.detail === 'string') {
                    detail.textContent = payload.detail;
                }
                if (typeof payload.title === 'string' && Object.prototype.hasOwnProperty.call(__nekoLoadingCompletionProgressByTitle, payload.title)) {
                    __nekoLoadingProgressComplete = true;
                    if (__nekoLoadingProgressFrame !== null) {
                        cancelAnimationFrame(__nekoLoadingProgressFrame);
                        __nekoLoadingProgressFrame = null;
                    }
                    __nekoApplyLoadingProgress(__nekoLoadingCompletionProgressByTitle[payload.title]);
                }
            } catch (e) {}
        };
    </script>
</body>
</html>
  `;
}

function getLoadingDataURL(ratio = 1, options = {}) {
  return `data:text/html;charset=utf-8,${encodeURIComponent(getLoadingHTML(ratio, options))}`;
}

  getLoadingDataURL.getHTML = getLoadingHTML;

  return getLoadingDataURL;
}

module.exports = {
  createLoadingWindowDataUrlBuilder,
};
