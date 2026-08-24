'use strict';

const { escapeHtml, safeScriptJson } = require('./html-escape');

function createExitRetentionPrompt(context) {
  const {
    BrowserWindow,
    app,
    beginExitRetentionShutdown = () => {},
    fs,
    getAppConfig,
    getCurrentLanguage,
    getMainWindow,
    getOriginalUrl,
    log,
    normalizeSupportedLanguage,
    path,
    t,
    tForLanguage,
    requestCompactKittenCompanion = () => {},
  } = context;

  let exitRetentionWindow;
  let exitRetentionConfirmPromise = null;

  const EXIT_RETENTION_VOICE_DIR = 'exit_retention_voices';
  const EXIT_RETENTION_LANGUAGE_PROBE_TIMEOUT_MS = 1000;
  const EXIT_RETENTION_MESSAGE_COUNT = 7;
  const EXIT_RETENTION_TYPE_INTERVAL_MS = 65;
  const EXIT_RETENTION_NO_VOICE_HOLD_MS = 900;
  const EXIT_RETENTION_FAREWELL_TIMEOUT_MS = 16000;
  const EXIT_RETENTION_STATE_FILE = 'exit-retention-state.json';
  const EXIT_RETENTION_WINDOW_WIDTH = 680;
  const EXIT_RETENTION_WINDOW_HEIGHT = 560;

  function resolveExitRetentionSkin(referenceDate = new Date()) {
    return 'kitten';
  }

  function getExitRetentionTopLevel() {
    return process.platform === 'win32' ? 'screen-saver' : 'floating';
  }

  function getExitRetentionStatePath() {
    return path.join(app.getPath('userData'), EXIT_RETENTION_STATE_FILE);
  }

  function normalizeDayIndex(dayIndex) {
    const numericDayIndex = Number.isInteger(dayIndex) ? dayIndex : 0;
    return ((numericDayIndex % EXIT_RETENTION_MESSAGE_COUNT) + EXIT_RETENTION_MESSAGE_COUNT) % EXIT_RETENTION_MESSAGE_COUNT;
  }

  // 退出挽留语音整体比应用内扬声器音量再低 8dB，让告别语音更克制、不盖过环境。
  // -8dB 对应的线性增益系数 = 10^(-8/20) ≈ 0.3981。
  const EXIT_RETENTION_VOICE_GAIN_DB_OFFSET = -8;
  const EXIT_RETENTION_VOICE_GAIN_SCALE = Math.pow(10, EXIT_RETENTION_VOICE_GAIN_DB_OFFSET / 20);

  function normalizeExitRetentionVoiceGain(speakerVolume) {
    // speakerVolume 是渲染进程的扬声器音量百分比（0-100），先转成 <audio>.volume 的 0-1 基准增益，
    // 再统一乘上 8dB 衰减系数，使退出挽留语音比应用内设置低 8dB。
    // 读不到时以满音量为基准做同样的 8dB 衰减，保持“始终低 8dB”的语义。
    const numeric = Number(speakerVolume);
    const baseGain = Number.isFinite(numeric) ? Math.max(0, Math.min(1, numeric / 100)) : 1;
    return Math.max(0, Math.min(1, baseGain * EXIT_RETENTION_VOICE_GAIN_SCALE));
  }

  function getTodayKey() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function readExitRetentionState() {
    try {
      const statePath = getExitRetentionStatePath();
      if (!fs.existsSync(statePath)) return {};
      const state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
      return state && typeof state === 'object' ? state : {};
    } catch (e) {
      log('退出挽留状态读取失败，回退第一天:', e.message);
      return {};
    }
  }

  function writeExitRetentionState(state) {
    try {
      const statePath = getExitRetentionStatePath();
      fs.mkdirSync(path.dirname(statePath), { recursive: true });
      fs.writeFileSync(statePath, JSON.stringify(state, null, 2));
    } catch (e) {
      log('退出挽留状态写入失败，继续使用当前文案:', e.message);
    }
  }

  function shouldSkipExitRetentionToday() {
    const state = readExitRetentionState();
    return state.lastShownDate === getTodayKey();
  }

  function getExitRetentionDayIndex(today = getTodayKey()) {
    const state = readExitRetentionState();
    if (state.lastShownDate === today) {
      return normalizeDayIndex(state.currentDayIndex);
    }

    return state.lastShownDate ? normalizeDayIndex(normalizeDayIndex(state.currentDayIndex) + 1) : 0;
  }

  function markExitRetentionShownToday(dayIndex, shownDateKey) {
    writeExitRetentionState({
      lastShownDate: shownDateKey,
      currentDayIndex: normalizeDayIndex(dayIndex),
    });
  }

  function getExitRetentionMessages(language = getCurrentLanguage()) {
    const normalizedLanguage = normalizeSupportedLanguage(language);
    const messages = tForLanguage('exitRetentionMessages', normalizedLanguage);
    if (Array.isArray(messages) && messages.length >= EXIT_RETENTION_MESSAGE_COUNT) {
      return messages;
    }

    const fallbackMessages = tForLanguage('exitRetentionMessages', 'en');
    if (Array.isArray(fallbackMessages) && fallbackMessages.length >= EXIT_RETENTION_MESSAGE_COUNT) {
      return fallbackMessages;
    }

    const fallbackMessage = (
      tForLanguage('exitRetentionMessage', normalizedLanguage)
      || tForLanguage('exitRetentionMessage', 'en')
      || 'Do you really want me to go?'
    );
    return Array.from({ length: EXIT_RETENTION_MESSAGE_COUNT }, () => fallbackMessage);
  }

  function getExitRetentionMessage(language, dayIndex) {
    const messages = getExitRetentionMessages(language);
    return String(messages[normalizeDayIndex(dayIndex)] || messages[0] || '').trim();
  }

  function getExitRetentionConfirmVoiceCandidates(language = getCurrentLanguage()) {
    const normalizedLanguage = normalizeSupportedLanguage(language);
    const basePath = app.isPackaged ? process.resourcesPath : process.cwd();
    return [
      path.join(basePath, 'assets', EXIT_RETENTION_VOICE_DIR, `${normalizedLanguage}.mp3`),
      path.join(basePath, 'assets', EXIT_RETENTION_VOICE_DIR, `${normalizedLanguage}.wav`),
    ];
  }

  function getExitRetentionVoiceCandidates(language = getCurrentLanguage(), dayIndex = 0) {
    const normalizedLanguage = normalizeSupportedLanguage(language);
    const basePath = app.isPackaged ? process.resourcesPath : process.cwd();
    const oneBasedDay = normalizeDayIndex(dayIndex) + 1;
    return [
      path.join(basePath, 'assets', EXIT_RETENTION_VOICE_DIR, normalizedLanguage, `day-${oneBasedDay}.mp3`),
      path.join(basePath, 'assets', EXIT_RETENTION_VOICE_DIR, normalizedLanguage, `day-${oneBasedDay}.wav`),
      path.join(basePath, 'assets', EXIT_RETENTION_VOICE_DIR, `${normalizedLanguage}-day-${oneBasedDay}.mp3`),
      path.join(basePath, 'assets', EXIT_RETENTION_VOICE_DIR, `${normalizedLanguage}-day-${oneBasedDay}.wav`),
    ];
  }

  function getExitRetentionVoiceMimeType(voicePath) {
    const extension = path.extname(String(voicePath || '')).toLowerCase();
    if (extension === '.wav') return 'audio/wav';
    return 'audio/mpeg';
  }

  function getExitRetentionStaticUrl(pathname) {
    try {
      return new URL(pathname, getOriginalUrl() || getAppConfig()?.apiBaseUrl || 'http://localhost:48911/').href;
    } catch (_) {
      return `http://localhost:48911${pathname}`;
    }
  }

  function getExitRetentionStyleSrc(cssUrl) {
    const styleSrc = ["'self'", "'unsafe-inline'", 'http://localhost:*', 'http://127.0.0.1:*'];
    try {
      const cssOrigin = new URL(cssUrl).origin;
      if (cssOrigin && cssOrigin !== 'null' && !styleSrc.includes(cssOrigin)) {
        styleSrc.push(cssOrigin);
      }
    } catch (_) {
      // Keep the localhost defaults when cssUrl cannot be parsed.
    }
    return styleSrc.join(' ');
  }

  function setExitRetentionPointerPassthrough(enabled) {
    const win = exitRetentionWindow;
    if (!win || win.isDestroyed() || typeof win.setIgnoreMouseEvents !== 'function') return;
    try {
      if (process.platform === 'linux') {
        win.setIgnoreMouseEvents(false);
        return;
      }
      if (enabled) {
        win.setIgnoreMouseEvents(true, { forward: true });
      } else {
        win.setIgnoreMouseEvents(false);
      }
    } catch (e) {
      log('退出挽留鼠标穿透状态更新失败:', e.message);
    }
  }

  function getExitRetentionPointerPassthroughScript() {
    return `
    const exitRetentionPointerSelectors = [
      '.exit-retention-cat-card',
      '.exit-retention-cat-character',
      '.exit-retention-toaster-box',
      '.exit-retention-toast-wrapper',
      '.exit-retention-toast',
      '.exit-retention-lever-hotspot'
    ];
    let exitRetentionPointerActive = false;
    function setExitRetentionPointerActive(active) {
      if (exitRetentionPointerActive === active) return;
      exitRetentionPointerActive = active;
      window.location.href = 'neko-exit-retention://' + (active ? 'pointer-active' : 'pointer-passive');
    }
    function isExitRetentionPointerHit(event) {
      const x = event.clientX;
      const y = event.clientY;
      return exitRetentionPointerSelectors.some(function (selector) {
        const element = document.querySelector(selector);
        if (!element) return false;
        const rect = element.getBoundingClientRect();
        return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
      });
    }
    window.addEventListener('mousemove', function (event) {
      setExitRetentionPointerActive(isExitRetentionPointerHit(event));
    });
    window.addEventListener('mouseleave', function () {
      setExitRetentionPointerActive(false);
    });
    window.addEventListener('blur', function () {
      setExitRetentionPointerActive(false);
    });
`;
  }

  async function resolveExitRetentionLanguage() {
    try {
      if (getMainWindow() && !getMainWindow().isDestroyed() && getMainWindow().webContents) {
        const rendererLanguageProbe = getMainWindow().webContents.executeJavaScript(`(() => {
          try {
            return (
              (window.i18next && window.i18next.language)
              || (window.i18n && window.i18n.language)
              || localStorage.getItem('i18nextLng')
              || document.documentElement.lang
              || ''
            );
          } catch (_) {
            return '';
          }
        })()`, true);
        const rendererLanguage = await Promise.race([
          rendererLanguageProbe,
          new Promise((resolve) => {
            setTimeout(() => resolve(''), EXIT_RETENTION_LANGUAGE_PROBE_TIMEOUT_MS);
          }),
        ]);
        if (rendererLanguage) {
          return normalizeSupportedLanguage(rendererLanguage);
        }
      }
    } catch (e) {
      log('读取前端语言失败，回退主进程语言:', e.message);
    }

    return normalizeSupportedLanguage(getCurrentLanguage());
  }

  async function resolveExitRetentionSpeakerVolume() {
    // 退出挽留弹窗是独立 data: URL 窗口，读不到主渲染进程的 neko_speaker_volume，
    // 这里探针主窗口拿到用户的扬声器音量，让告别语音和常规语音音量对齐。
    try {
      if (getMainWindow() && !getMainWindow().isDestroyed() && getMainWindow().webContents) {
        const rendererVolumeProbe = getMainWindow().webContents.executeJavaScript(`(() => {
          try {
            var raw = (typeof window.getSpeakerVolume === 'function')
              ? window.getSpeakerVolume()
              : localStorage.getItem('neko_speaker_volume');
            var numeric = Number(raw);
            return Number.isFinite(numeric) ? String(numeric) : '';
          } catch (_) {
            return '';
          }
        })()`, true);
        const rendererVolume = await Promise.race([
          rendererVolumeProbe,
          new Promise((resolve) => {
            setTimeout(() => resolve(''), EXIT_RETENTION_LANGUAGE_PROBE_TIMEOUT_MS);
          }),
        ]);
        const numericVolume = Number.parseFloat(rendererVolume);
        if (Number.isFinite(numericVolume)) {
          return Math.max(0, Math.min(100, numericVolume));
        }
      }
    } catch (e) {
      log('读取扬声器音量失败，退出挽留语音回退满音量:', e.message);
    }

    return 100;
  }

  function buildExitRetentionKittenDialogHtml(language = getCurrentLanguage(), confirmVoiceUrl = '', farewellVoiceUrl = '', dayIndex = 0, speakerVolume = 100) {
    const voiceGain = normalizeExitRetentionVoiceGain(speakerVolume);
    const cssUrl = getExitRetentionStaticUrl('/static/css/storage-location.css');
    const exitLanguage = normalizeSupportedLanguage(language);
    const title = escapeHtml(tForLanguage('exitRetentionTitle', exitLanguage));
    const rawMessage = String(tForLanguage('exitRetentionMessage', exitLanguage) || '');
    const message = escapeHtml(rawMessage);
    const farewellTitle = escapeHtml(tForLanguage('exitRetentionFarewellTitle', exitLanguage) || 'N.E.K.O.');
    const farewellMessage = getExitRetentionMessage(exitLanguage, dayIndex);
    const chooseText = escapeHtml(tForLanguage('exitRetentionChoose', exitLanguage) || 'Choose');
    const confirmText = escapeHtml(tForLanguage('exitRetentionConfirm', exitLanguage));
    const stayText = escapeHtml(tForLanguage('exitRetentionKittenStay', exitLanguage) || tForLanguage('exitRetentionStay', exitLanguage) || 'Stay');
    const leaveText = escapeHtml(tForLanguage('exitRetentionKittenLeave', exitLanguage) || tForLanguage('exitRetentionLeave', exitLanguage) || tForLanguage('exitRetentionConfirm', exitLanguage) || 'Leave');
    const catPromptText = message;
    const isLongCatPrompt = Array.from(rawMessage).length > 18;
    const longCopyClass = isLongCatPrompt ? ' exit-retention-stage--long-copy' : '';
    const theme = getAppConfig() && getAppConfig().darkMode ? 'dark' : 'light';
    const oneBasedDay = normalizeDayIndex(dayIndex) + 1;
    const contentSecurityPolicy = `default-src 'self' data: http://localhost:* http://127.0.0.1:*; img-src 'self' data: http://localhost:* http://127.0.0.1:*; media-src data:; style-src ${getExitRetentionStyleSrc(cssUrl)}; script-src 'unsafe-inline';`;

    return `<!doctype html>
<html lang="${escapeHtml(exitLanguage || 'en')}" data-theme="${theme}">
<head>
  <meta charset="utf-8">
  <meta http-equiv="Content-Security-Policy" content="${escapeHtml(contentSecurityPolicy)}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="${escapeHtml(cssUrl)}">
  <style>
    :root {
      --exit-bg-top: #e0f2fe;
      --exit-bg-bottom: #f8fafc;
      --exit-yui-blue: #8eceff;
      --exit-yui-blue-glow: rgba(92, 168, 230, 0.26);
      --exit-yui-pink: #ffa8ba;
      --exit-text-main: #4a5d73;
      --exit-text-sub: #799bbb;
      --exit-card-bg: linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(242, 248, 255, 0.88));
      --exit-card-border: rgba(255, 255, 255, 0.96);
      --exit-card-shadow: rgba(150, 180, 220, 0.22);
      --exit-cat-main: #ffffff;
      --exit-cat-shadow: #cce0ff;
      --exit-cat-face: #475a6e;
      --exit-button-stay: linear-gradient(180deg, #a3d9ff, #6bb0f2);
      --exit-button-leave: linear-gradient(180deg, #ffffff, #e2e8f0);
      --exit-close-bg: rgba(255, 255, 255, 0.86);
      --exit-close-color: #7c91ae;
    }
    [data-theme="dark"] {
      --exit-bg-top: #172436;
      --exit-bg-bottom: #101821;
      --exit-yui-blue: #5ca8ff;
      --exit-yui-blue-glow: rgba(92, 168, 255, 0.24);
      --exit-yui-pink: #f687b3;
      --exit-text-main: #e2f2ff;
      --exit-text-sub: #a8c4df;
      --exit-card-bg: linear-gradient(135deg, rgba(38, 48, 64, 0.96), rgba(24, 33, 45, 0.90));
      --exit-card-border: rgba(137, 196, 255, 0.24);
      --exit-card-shadow: rgba(4, 12, 24, 0.36);
      --exit-cat-main: #f4f9ff;
      --exit-cat-shadow: #4d6f99;
      --exit-cat-face: #2d4664;
      --exit-button-stay: linear-gradient(180deg, #78c5ff, #357ec8);
      --exit-button-leave: linear-gradient(180deg, #435165, #2b3442);
      --exit-close-bg: rgba(34, 42, 54, 0.86);
      --exit-close-color: #c6d5e8;
    }
    html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; background: transparent; box-shadow: none; outline: 0; }
    body.storage-location-modal-open { background: transparent !important; }
    body, button { font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; user-select: none; }
    .storage-location-overlay {
      padding: 24px;
      background: transparent !important;
      backdrop-filter: none;
      -webkit-backdrop-filter: none;
      box-shadow: none;
      outline: 0;
      filter: none;
      isolation: auto;
      align-items: center;
      justify-content: center;
    }
    [data-theme="dark"] .storage-location-overlay { background: transparent !important; }
    .storage-location-overlay::before,
    [data-theme="dark"] .storage-location-overlay::before { content: none !important; }
    .storage-location-modal::before,
    .storage-location-modal::after { content: none; }
    .storage-location-modal.exit-retention-stage {
      width: min(620px, calc(100vw - 48px));
      height: min(500px, calc(100vh - 48px));
      min-height: 0;
      overflow: visible;
      border: 0;
      border-radius: 0;
      background: transparent;
      box-shadow: none;
      aspect-ratio: auto;
      filter: none;
      outline: 0;
      animation: none;
      color: var(--exit-text-main);
    }
    .exit-retention-modal-container {
      position: absolute;
      inset: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 0;
      overflow: visible;
      border: 0;
      border-radius: inherit;
      background: transparent;
    }
    [data-theme="dark"] .exit-retention-modal-container { border-color: rgba(255, 255, 255, 0.08); }
    .exit-retention-scene {
      position: relative;
      z-index: 10;
      width: 520px;
      height: 420px;
      display: flex;
      align-items: flex-end;
      justify-content: center;
      transition: opacity 0.5s ease, transform 0.7s cubic-bezier(0.23, 1, 0.32, 1);
    }
    .exit-retention-cat-backglow {
      position: absolute;
      top: 16px;
      z-index: 4;
      width: 220px;
      height: 150px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.76);
      filter: blur(30px);
      transition: opacity 0.6s ease, transform 0.72s cubic-bezier(0.23, 1, 0.32, 1), background 0.35s ease;
      pointer-events: none !important;
    }
    .exit-retention-floor-shadow {
      position: absolute;
      bottom: 12px;
      z-index: 2;
      width: 330px;
      height: 34px;
      border-radius: 50%;
      background: rgba(80, 120, 160, 0.16);
      filter: blur(11px);
      transition: transform 0.58s ease, opacity 0.58s ease;
      pointer-events: none !important;
    }
    .exit-retention-cat-character {
      position: absolute;
      top: 12px;
      left: 50%;
      z-index: 22;
      width: 190px;
      height: 160px;
      transform: translateX(-50%);
      transition: opacity 0.54s ease, transform 0.56s cubic-bezier(0.34, 1.56, 0.64, 1);
      pointer-events: none !important;
    }
    .exit-retention-cat-heart {
      position: absolute;
      top: -16px;
      left: 50%;
      color: #ff85a2;
      font-size: 24px;
      font-weight: 900;
      opacity: 0;
      transform: translateX(-50%) translateY(10px) scale(0.4);
      transition: opacity 0.3s ease, transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
      pointer-events: none !important;
    }
    .exit-retention-cat-head-group {
      position: relative;
      width: 100%;
      height: 100%;
      animation: exitRetentionCatBreathe 3.5s infinite ease-in-out;
      transform-origin: bottom center;
      transition: transform 0.46s cubic-bezier(0.34, 1.56, 0.64, 1);
      pointer-events: none !important;
    }
    .exit-retention-cat-head {
      position: absolute;
      bottom: 0;
      z-index: 2;
      width: 100%;
      height: 140px;
      border-radius: 45% 45% 40% 40% / 60% 60% 40% 40%;
      background: var(--exit-cat-main);
      box-shadow: inset -8px -12px 25px var(--exit-cat-shadow), inset 8px 8px 20px rgba(255,255,255,0.95), 0 -5px 20px rgba(163,217,255,0.15);
      pointer-events: none !important;
    }
    .exit-retention-cat-ear {
      position: absolute;
      top: -10px;
      z-index: 1;
      width: 55px;
      height: 65px;
      background: var(--exit-cat-main);
      box-shadow: inset -4px -4px 10px var(--exit-cat-shadow), inset 4px 4px 10px rgba(255,255,255,0.95);
      transition: transform 0.46s cubic-bezier(0.34, 1.56, 0.64, 1);
      pointer-events: none !important;
    }
    .exit-retention-cat-ear--left { left: 8px; border-radius: 12px 40px 10px 10px; transform: rotate(-22deg); }
    .exit-retention-cat-ear--right { right: 8px; border-radius: 40px 12px 10px 10px; transform: rotate(22deg); }
    .exit-retention-cat-ear::after {
      content: '';
      position: absolute;
      bottom: 8px;
      width: 32px;
      height: 40px;
      border-radius: inherit;
      background: linear-gradient(180deg, #ffcce5, var(--exit-yui-pink));
      box-shadow: inset 0 2px 6px rgba(0,0,0,0.05);
      opacity: 0.9;
    }
    .exit-retention-cat-ear--left::after { left: 12px; transform: rotate(10deg); }
    .exit-retention-cat-ear--right::after { right: 12px; transform: rotate(-10deg); }
    .exit-retention-cat-face { position: absolute; top: 65px; left: 0; z-index: 3; width: 100%; height: 50px; transition: transform 0.35s ease; pointer-events: none !important; }
    .exit-retention-cat-eye { position: absolute; top: 10px; width: 16px; height: 16px; border-radius: 50%; background: var(--exit-cat-face); transition: all 0.36s cubic-bezier(0.34, 1.56, 0.64, 1); }
    .exit-retention-cat-eye--left { left: 48px; }
    .exit-retention-cat-eye--right { right: 48px; }
    .exit-retention-cat-eye::after { content: ''; position: absolute; top: 2px; right: 3px; width: 6px; height: 6px; border-radius: 50%; background: #ffffff; transition: all 0.3s ease; }
    .exit-retention-cat-mouth { position: absolute; top: 22px; left: 50%; display: flex; justify-content: center; width: 22px; height: 10px; transform: translateX(-50%); transition: all 0.36s ease; }
    .exit-retention-cat-mouth::before,
    .exit-retention-cat-mouth::after { content: ''; width: 11px; height: 9px; border-bottom: 3.5px solid var(--exit-cat-face); border-radius: 50%; transition: all 0.36s ease; }
    .exit-retention-cat-mouth::before { margin-right: -2px; border-right: 3.5px solid var(--exit-cat-face); border-bottom-right-radius: 12px; transform: rotate(15deg); }
    .exit-retention-cat-mouth::after { margin-left: -2px; border-left: 3.5px solid var(--exit-cat-face); border-bottom-left-radius: 12px; transform: rotate(-15deg); }
    .exit-retention-cat-blush { position: absolute; top: 20px; width: 24px; height: 12px; border-radius: 50%; background: var(--exit-yui-pink); filter: blur(4px); opacity: 0.72; transition: all 0.36s ease; }
    .exit-retention-cat-blush--left { left: 25px; }
    .exit-retention-cat-blush--right { right: 25px; }
    .exit-retention-cat-paw { position: absolute; bottom: -15px; z-index: 25; width: 40px; height: 50px; border-radius: 25px; background: var(--exit-cat-main); box-shadow: 0 6px 10px rgba(0,0,0,0.06), inset -4px -4px 10px var(--exit-cat-shadow), inset 4px 4px 10px rgba(255,255,255,0.95); transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.36s ease; pointer-events: none !important; }
    .exit-retention-cat-paw--left { left: 35px; transform: rotate(20deg); }
    .exit-retention-cat-paw--right { right: 35px; transform: rotate(-20deg); }
    .exit-retention-cat-card {
      position: relative;
      z-index: 20;
      width: 440px;
      height: 220px;
      padding: 46px 46px 32px;
      border: 2px solid var(--exit-card-border);
      border-radius: 45px;
      background: var(--exit-card-bg);
      box-shadow: 0 40px 80px var(--exit-card-shadow), inset 0 10px 20px rgba(255,255,255,0.78);
      backdrop-filter: blur(15px);
      -webkit-backdrop-filter: blur(15px);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: flex-end;
      transition: width 0.76s cubic-bezier(0.34, 1.56, 0.64, 1), height 0.76s cubic-bezier(0.34, 1.56, 0.64, 1), padding 0.76s cubic-bezier(0.23, 1, 0.32, 1), border-radius 0.76s cubic-bezier(0.23, 1, 0.32, 1), transform 0.76s cubic-bezier(0.23, 1, 0.32, 1), opacity 0.36s ease, box-shadow 0.55s ease;
    }
    .exit-retention-cat-copy { text-align: center; margin-bottom: 30px; transition: opacity 0.32s ease, transform 0.38s cubic-bezier(0.34, 1.56, 0.64, 1); }
    .exit-retention-cat-title { margin: 0 0 10px; color: var(--exit-text-main); font-size: 29px; font-weight: 900; line-height: 1.22; letter-spacing: 0; overflow-wrap: anywhere; }
    .exit-retention-cat-message { margin: 0; color: var(--exit-text-sub); font-size: 16px; font-weight: 800; line-height: 1.45; overflow-wrap: anywhere; }
    .exit-retention-stage--long-copy .exit-retention-scene:not(.state-farewell) .exit-retention-cat-card { width: 500px; height: 220px; padding: 46px 38px 32px; }
    .exit-retention-stage--long-copy .exit-retention-scene:not(.state-farewell) .exit-retention-cat-title { font-size: 23px; line-height: 1.14; }
    .exit-retention-stage--long-copy .exit-retention-scene:not(.state-farewell) .exit-retention-cat-copy { margin-bottom: 18px; }
    .exit-retention-cat-actions { display: flex; gap: 24px; align-items: center; justify-content: center; transition: opacity 0.28s ease, transform 0.36s ease; }
    .exit-retention-cat-button {
      min-width: 128px;
      padding: 16px 42px;
      border: 0;
      border-radius: 30px;
      color: #ffffff;
      font-size: 18px;
      font-weight: 900;
      line-height: 1.2;
      letter-spacing: 0;
      cursor: pointer;
      position: relative;
      overflow: hidden;
      transition: transform 0.32s cubic-bezier(0.175, 0.885, 0.32, 1.275), box-shadow 0.22s ease, filter 0.22s ease;
    }
    .exit-retention-stay-button { background: var(--exit-button-stay); box-shadow: 0 15px 30px rgba(107,176,242,0.35), inset 0 4px 8px rgba(255,255,255,0.46); }
    .exit-retention-leave-button { background: var(--exit-button-leave); color: #8fa3c0; box-shadow: 0 10px 20px rgba(0,0,0,0.06), inset 0 4px 8px rgba(255,255,255,0.72); }
    [data-theme="dark"] .exit-retention-leave-button { color: #d2deee; box-shadow: 0 10px 20px rgba(0,0,0,0.22), inset 0 4px 8px rgba(255,255,255,0.10); }
    .exit-retention-cat-button:hover,
    .exit-retention-cat-button:focus-visible { transform: translateY(-6px) scale(1.05); outline: none; filter: brightness(1.04); }
    .exit-retention-cat-button:active { transform: scale(0.95); }
    .exit-retention-farewell-kicker { display: none; margin-bottom: 18px; color: var(--exit-yui-blue); font-size: 13px; font-weight: 900; letter-spacing: 3px; text-transform: uppercase; }
    .exit-retention-farewell-text { display: none; max-width: 410px; color: var(--exit-text-main); font-size: 22px; font-weight: 900; line-height: 1.72; text-align: center; white-space: pre-wrap; overflow-wrap: anywhere; }
    .exit-retention-scene.state-curious .exit-retention-cat-head-group { transform: rotate(10deg) translateY(2px); }
    .exit-retention-scene.state-curious .exit-retention-cat-ear--left { transform: rotate(-8deg); }
    .exit-retention-scene.state-curious .exit-retention-cat-eye { transform: scale(1.13); }
    .exit-retention-scene.state-happy .exit-retention-cat-character { transform: translateX(-50%) translateY(18px); }
    .exit-retention-scene.state-happy .exit-retention-cat-eye { top: 16px; height: 5px; border-radius: 10px; transform: scaleX(1.2); }
    .exit-retention-scene.state-happy .exit-retention-cat-eye::after { opacity: 0; }
    .exit-retention-scene.state-happy .exit-retention-cat-mouth::before,
    .exit-retention-scene.state-happy .exit-retention-cat-mouth::after { border-bottom: 0; border-top: 3.5px solid var(--exit-cat-face); }
    .exit-retention-scene.state-happy .exit-retention-cat-blush { background: #ff7e5f; transform: scale(1.4); opacity: 0.92; }
    .exit-retention-scene.state-happy .exit-retention-cat-paw { transform: translateY(-8px) rotate(0deg); }
    .exit-retention-scene.state-happy .exit-retention-cat-heart { opacity: 1; transform: translateX(-50%) translateY(-34px) scale(1); }
    .exit-retention-scene.state-sad .exit-retention-cat-head-group { transform: translateY(12px); animation: exitRetentionSadTremble 0.3s infinite; }
    .exit-retention-scene.state-sad .exit-retention-cat-ear--left { transform: rotate(-65deg) translateY(8px) translateX(-5px); }
    .exit-retention-scene.state-sad .exit-retention-cat-ear--right { transform: rotate(65deg) translateY(8px) translateX(5px); }
    .exit-retention-scene.state-sad .exit-retention-cat-eye { transform: scale(1.2); background: #2c3a4a; box-shadow: inset 0 -4px 6px rgba(163,217,255,0.8); }
    .exit-retention-scene.state-sad .exit-retention-cat-eye::after { top: 5px; right: 2px; width: 9px; height: 9px; box-shadow: -3px -3px 0 rgba(255,255,255,0.6); }
    .exit-retention-scene.state-sad .exit-retention-cat-mouth::before,
    .exit-retention-scene.state-sad .exit-retention-cat-mouth::after { border-bottom: 0; border-top: 3.5px solid var(--exit-cat-face); }
    .exit-retention-scene.state-sad .exit-retention-cat-backglow { background: rgba(163,217,255,0.45); }
    .exit-retention-scene.state-farewell { z-index: 110; }
    .exit-retention-scene.state-farewell .exit-retention-cat-card {
      width: 440px;
      height: 220px;
      padding: 46px 46px 32px;
      justify-content: flex-start;
      box-shadow: 0 46px 90px var(--exit-card-shadow), inset 0 10px 20px rgba(255,255,255,0.62);
    }
    .exit-retention-scene.state-farewell .exit-retention-cat-character {
      opacity: 1;
      top: 12px;
      transform: translateX(-50%);
    }
    .exit-retention-scene.state-farewell .exit-retention-cat-head-group { transform: translateY(12px); animation: exitRetentionSadTremble 0.3s infinite; }
    .exit-retention-scene.state-farewell .exit-retention-cat-ear--left { transform: rotate(-65deg) translateY(8px) translateX(-5px); }
    .exit-retention-scene.state-farewell .exit-retention-cat-ear--right { transform: rotate(65deg) translateY(8px) translateX(5px); }
    .exit-retention-scene.state-farewell .exit-retention-cat-eye { transform: scale(1.2); background: #2c3a4a; box-shadow: inset 0 -4px 6px rgba(163,217,255,0.8); }
    .exit-retention-scene.state-farewell .exit-retention-cat-eye::after { top: 5px; right: 2px; width: 9px; height: 9px; box-shadow: -3px -3px 0 rgba(255,255,255,0.6); }
    .exit-retention-scene.state-farewell .exit-retention-cat-mouth::before,
    .exit-retention-scene.state-farewell .exit-retention-cat-mouth::after { border-bottom: 0; border-top: 3.5px solid var(--exit-cat-face); }
    .exit-retention-scene.state-farewell .exit-retention-cat-paw,
    .exit-retention-scene.state-farewell .exit-retention-cat-heart { opacity: 0; }
    .exit-retention-scene.state-farewell .exit-retention-cat-backglow,
    .exit-retention-scene.state-farewell .exit-retention-floor-shadow { opacity: 0; transform: translateY(90px) scale(0.8); }
    .exit-retention-scene.state-farewell .exit-retention-cat-copy,
    .exit-retention-scene.state-farewell .exit-retention-cat-actions { opacity: 0; transform: translateY(18px); pointer-events: none !important; position: absolute; }
    .exit-retention-scene.state-farewell .exit-retention-farewell-kicker,
    .exit-retention-scene.state-farewell .exit-retention-farewell-text { display: block; transform: none; }
    .exit-retention-scene.state-farewell .exit-retention-farewell-kicker { margin-top: 24px; }
    .exit-retention-scene.state-farewell .exit-retention-farewell-text { max-width: 410px; min-height: 104px; }
    .exit-retention-scene.state-farewell .exit-retention-farewell-text::after { content: ''; display: inline-block; width: 3px; height: 22px; margin-left: 4px; vertical-align: middle; background: var(--exit-text-main); animation: exitRetentionCaret 0.8s infinite; }
    .exit-retention-farewell-complete .exit-retention-farewell-text::after { content: none; }
    @keyframes exitRetentionCatBreathe { 0%, 100% { transform: scaleY(1); } 50% { transform: scaleY(0.97) translateY(3px); } }
    @keyframes exitRetentionSadTremble { 0%, 100% { transform: translateY(12px) translateX(0); } 50% { transform: translateY(12px) translateX(1px); } }
    @keyframes exitRetentionCaret { 50% { opacity: 0; } }
    @media (max-width: 560px) {
      .storage-location-modal.exit-retention-stage { width: min(620px, calc(100vw - 32px)); height: min(500px, calc(100vh - 32px)); border-radius: 0; }
      .exit-retention-scene { transform: scale(0.88); }
      .exit-retention-scene.state-farewell { transform: none; width: min(520px, calc(100vw - 64px)); }
      .exit-retention-scene.state-farewell .exit-retention-cat-card { width: min(520px, calc(100vw - 96px)); height: 340px; }
    }
  </style>
</head>
<body class="storage-location-modal-open">
  ${confirmVoiceUrl ? `<audio id="exit-retention-confirm-voice" preload="auto" src="${escapeHtml(confirmVoiceUrl)}"></audio>` : ''}
  ${farewellVoiceUrl ? `<audio id="exit-retention-voice" preload="auto" src="${escapeHtml(farewellVoiceUrl)}"></audio>` : ''}
  <div class="storage-location-overlay" id="storage-location-overlay">
    <section class="storage-location-modal exit-retention-stage${longCopyClass}" role="dialog" aria-modal="true" aria-labelledby="exit-retention-title">
      <div class="exit-retention-modal-container" id="exit-retention-modal-container">
        <div class="exit-retention-scene" id="exit-retention-scene">
          <div class="exit-retention-cat-backglow" aria-hidden="true"></div>
          <div class="exit-retention-floor-shadow" aria-hidden="true"></div>
          <div class="exit-retention-cat-character" aria-hidden="true">
            <div class="exit-retention-cat-heart">♥</div>
            <div class="exit-retention-cat-head-group">
              <div class="exit-retention-cat-ear exit-retention-cat-ear--left"></div>
              <div class="exit-retention-cat-ear exit-retention-cat-ear--right"></div>
              <div class="exit-retention-cat-head">
                <div class="exit-retention-cat-face">
                  <div class="exit-retention-cat-blush exit-retention-cat-blush--left"></div>
                  <div class="exit-retention-cat-eye exit-retention-cat-eye--left"></div>
                  <div class="exit-retention-cat-mouth"></div>
                  <div class="exit-retention-cat-eye exit-retention-cat-eye--right"></div>
                  <div class="exit-retention-cat-blush exit-retention-cat-blush--right"></div>
                </div>
              </div>
            </div>
            <div class="exit-retention-cat-paw exit-retention-cat-paw--left"></div>
            <div class="exit-retention-cat-paw exit-retention-cat-paw--right"></div>
          </div>
          <div class="exit-retention-cat-card">
            <div class="exit-retention-cat-copy" id="exit-retention-text-hover">
              <h2 class="exit-retention-cat-title" id="exit-retention-title">${catPromptText}</h2>
              <p class="exit-retention-cat-message">${chooseText}</p>
            </div>
            <div class="exit-retention-cat-actions">
              <button class="exit-retention-cat-button exit-retention-stay-button" id="exit-retention-stay" type="button">${stayText}</button>
              <button class="exit-retention-cat-button exit-retention-leave-button" id="exit-retention-leave" type="button" aria-label="${confirmText}">${leaveText}</button>
            </div>
            <div class="exit-retention-farewell-kicker">${farewellTitle} / DAY ${oneBasedDay}</div>
            <div class="exit-retention-farewell-text" id="exit-retention-farewell-text"></div>
          </div>
        </div>
      </div>
    </section>
  </div>
  <script>
    const farewellText = ${safeScriptJson(farewellMessage)};
    const typeIntervalMs = ${EXIT_RETENTION_TYPE_INTERVAL_MS};
    const noVoiceHoldMs = ${EXIT_RETENTION_NO_VOICE_HOLD_MS};
    const farewellTimeoutMs = ${EXIT_RETENTION_FAREWELL_TIMEOUT_MS};
    const farewellRevealDelayMs = 360;
    const scene = document.getElementById('exit-retention-scene');
    const textHoverArea = document.getElementById('exit-retention-text-hover');
    const stayButton = document.getElementById('exit-retention-stay');
	    const leaveButton = document.getElementById('exit-retention-leave');
	    let farewellStarted = false;
	    let textDone = false;
	    let audioDone = !document.getElementById('exit-retention-voice');
	    let finished = false;
	    ${getExitRetentionPointerPassthroughScript()}
	
	    function choose(action) {
	      window.location.href = 'neko-exit-retention://' + action;
	    }

    function finishFarewell() {
      if (finished) return;
      finished = true;
      document.body.classList.add('exit-retention-farewell-complete');
      choose('finish-confirm');
    }

    function finishIfReady() {
      if (!textDone || !audioDone) return;
      if (document.getElementById('exit-retention-voice')) {
        finishFarewell();
        return;
      }
      setTimeout(finishFarewell, noVoiceHoldMs);
    }

    function typeFarewellText() {
      const target = document.getElementById('exit-retention-farewell-text');
      const chars = Array.from(farewellText || '');
      let index = 0;
      target.textContent = '';
      if (!chars.length) {
        textDone = true;
        finishIfReady();
        return;
      }
      const timer = setInterval(function () {
        target.textContent += chars[index] || '';
        index += 1;
        if (index >= chars.length) {
          clearInterval(timer);
          textDone = true;
          finishIfReady();
        }
      }, typeIntervalMs);
    }

    function setSceneState(stateName) {
      if (farewellStarted) return;
      scene.classList.remove('state-curious', 'state-happy', 'state-sad');
      if (stateName) scene.classList.add(stateName);
    }

    const exitRetentionVoiceVolume = ${voiceGain};
    function applyExitRetentionVoiceVolume(audioEl) {
      if (!audioEl) return;
      try { audioEl.volume = exitRetentionVoiceVolume; } catch (_) {}
    }
    function playConfirmVoice() {
      const confirmVoice = document.getElementById('exit-retention-confirm-voice');
      if (!confirmVoice) return;
      applyExitRetentionVoiceVolume(confirmVoice);
      confirmVoice.play().catch(function () {});
    }

    function stopConfirmVoice() {
      const confirmVoice = document.getElementById('exit-retention-confirm-voice');
      if (!confirmVoice) return;
      confirmVoice.pause();
      try {
        confirmVoice.currentTime = 0;
      } catch (_) {}
    }

    function prepareFarewell() {
      startFarewell();
    }

    function startFarewell() {
      if (farewellStarted) return;
      farewellStarted = true;
      stopConfirmVoice();
      scene.classList.remove('state-curious', 'state-happy', 'state-sad');
      scene.classList.add('state-farewell');
      document.body.classList.add('exit-retention-is-farewell');
      stayButton.disabled = true;
      leaveButton.disabled = true;
      choose('confirmed');
      setTimeout(typeFarewellText, farewellRevealDelayMs);
      const voice = document.getElementById('exit-retention-voice');
      if (voice) {
        applyExitRetentionVoiceVolume(voice);
        voice.addEventListener('ended', function () {
          audioDone = true;
          finishIfReady();
        }, { once: true });
        voice.addEventListener('error', function () {
          audioDone = true;
          finishIfReady();
        }, { once: true });
        voice.play().catch(function () {
          audioDone = true;
          finishIfReady();
        });
      }
      setTimeout(finishFarewell, farewellTimeoutMs);
    }

    document.getElementById('exit-retention-stay').addEventListener('click', function () { choose('stay'); });
    document.getElementById('exit-retention-leave').addEventListener('click', prepareFarewell);
    textHoverArea.addEventListener('mouseenter', function () { setSceneState('state-curious'); });
    textHoverArea.addEventListener('mouseleave', function () { setSceneState(''); });
    stayButton.addEventListener('mouseenter', function () { setSceneState('state-happy'); });
    stayButton.addEventListener('mouseleave', function () { setSceneState(''); });
    leaveButton.addEventListener('mouseenter', function () { setSceneState('state-sad'); });
    leaveButton.addEventListener('mouseleave', function () { setSceneState(''); });
    window.addEventListener('DOMContentLoaded', playConfirmVoice);
    window.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && !farewellStarted) choose('cancel');
    });
  </script>
</body>
</html>`;
  }

  function buildExitRetentionToasterDialogHtml(language = getCurrentLanguage(), confirmVoiceUrl = '', farewellVoiceUrl = '', dayIndex = 0, speakerVolume = 100) {
    const voiceGain = normalizeExitRetentionVoiceGain(speakerVolume);
    const cssUrl = getExitRetentionStaticUrl('/static/css/storage-location.css');
    const exitLanguage = normalizeSupportedLanguage(language);
    const title = escapeHtml(tForLanguage('exitRetentionTitle', exitLanguage));
    const message = escapeHtml(tForLanguage('exitRetentionMessage', exitLanguage));
    const farewellMessage = getExitRetentionMessage(exitLanguage, dayIndex);
    const chooseText = escapeHtml(tForLanguage('exitRetentionChoose', exitLanguage) || 'Choose');
    const confirmText = escapeHtml(tForLanguage('exitRetentionConfirm', exitLanguage));
    const leverText = escapeHtml(tForLanguage('exitRetentionToasterStart', exitLanguage) || tForLanguage('exitRetentionLeave', exitLanguage) || tForLanguage('exitRetentionConfirm', exitLanguage) || 'Leave');
    const stayRawText = tForLanguage('exitRetentionToasterStay', exitLanguage) || tForLanguage('exitRetentionStay', exitLanguage) || 'Stay';
    const stayText = escapeHtml(stayRawText);
    const toastHintText = escapeHtml(tForLanguage('exitRetentionToasterLeave', exitLanguage) || tForLanguage('exitRetentionClickToLeave', exitLanguage) || tForLanguage('exitRetentionConfirm', exitLanguage));
    const toastPromptText = message;
    const theme = getAppConfig() && getAppConfig().darkMode ? 'dark' : 'light';
    const contentSecurityPolicy = `default-src 'self' data: http://localhost:* http://127.0.0.1:*; img-src 'self' data: http://localhost:* http://127.0.0.1:*; media-src data:; style-src ${getExitRetentionStyleSrc(cssUrl)}; script-src 'unsafe-inline';`;

    return `<!doctype html>
<html lang="${escapeHtml(exitLanguage || 'en')}" data-theme="${theme}">
<head>
  <meta charset="utf-8">
  <meta http-equiv="Content-Security-Policy" content="${escapeHtml(contentSecurityPolicy)}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="${escapeHtml(cssUrl)}">
  <style>
    :root {
      --exit-bg-top: #e0f2fe;
      --exit-bg-bottom: #f8fafc;
      --exit-yui-blue: #8eceff;
      --exit-yui-blue-light: #cce8ff;
      --exit-yui-blue-shadow: #5ca8e6;
      --exit-yui-blue-dark: #3a85c4;
      --exit-yui-blue-glow: rgba(92, 168, 230, 0.26);
      --exit-yui-pink: #ffa8ba;
      --exit-text-main: #476b8a;
      --exit-text-sub: #799bbb;
      --exit-toaster-main: #8eceff;
      --exit-toaster-light: #cce8ff;
      --exit-toaster-shadow: #5ca8e6;
      --exit-toaster-dark: #3a85c4;
      --exit-slot-glow: #ff7e5f;
      --exit-toast-crust-out: #c28851;
      --exit-toast-crust-in: #e6b981;
      --exit-toast-crumb: #fff5e6;
      --exit-toast-stamp: #7a4f32;
      --exit-final-bg: rgba(255, 255, 255, 0.94);
      --exit-final-border: rgba(142, 206, 255, 0.30);
      --exit-close-bg: rgba(255, 255, 255, 0.86);
      --exit-close-color: #7c91ae;
    }
    [data-theme="dark"] {
      --exit-bg-top: #172436;
      --exit-bg-bottom: #101821;
      --exit-yui-blue: #5ca8ff;
      --exit-yui-blue-light: #89c4ff;
      --exit-yui-blue-shadow: #2266aa;
      --exit-yui-blue-dark: #1f5f9a;
      --exit-yui-blue-glow: rgba(92, 168, 255, 0.24);
      --exit-yui-pink: #f687b3;
      --exit-text-main: #e2f2ff;
      --exit-text-sub: #a8c4df;
      --exit-toaster-main: #4b9fe8;
      --exit-toaster-light: #85c8ff;
      --exit-toaster-shadow: #1f5f9a;
      --exit-toaster-dark: #173f68;
      --exit-slot-glow: #ff8d72;
      --exit-toast-crust-out: #a96f3e;
      --exit-toast-crust-in: #d49d61;
      --exit-toast-crumb: #fff1dc;
      --exit-toast-stamp: #6d4329;
      --exit-final-bg: rgba(28, 39, 53, 0.95);
      --exit-final-border: rgba(137, 196, 255, 0.24);
      --exit-close-bg: rgba(34, 42, 54, 0.86);
      --exit-close-color: #c6d5e8;
    }
    html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; background: transparent; }
    body, button { font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; user-select: none; }
    .storage-location-overlay {
      padding: 24px;
      background: transparent;
      backdrop-filter: none;
      -webkit-backdrop-filter: none;
      align-items: center;
      justify-content: center;
    }
    .storage-location-overlay::before { content: none; }
    .storage-location-modal::before,
    .storage-location-modal::after { content: none; }
    .storage-location-modal.exit-retention-stage {
      width: min(880px, calc(100vw - 48px));
      height: min(640px, calc(100vh - 48px));
      min-height: 0;
      overflow: visible;
      border: 0;
      border-radius: 0;
      background: transparent;
      box-shadow: none;
      aspect-ratio: auto;
      filter: none;
      animation: none;
      color: var(--exit-text-main);
    }
    .exit-retention-modal-container {
      position: absolute;
      inset: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 0;
      overflow: visible;
      border: 0;
      border-radius: inherit;
      background: transparent;
    }
    .exit-retention-scene {
      position: relative;
      z-index: 10;
      width: 420px;
      height: 430px;
      display: flex;
      align-items: flex-end;
      justify-content: center;
      padding-bottom: 62px;
      transition: opacity 0.5s ease, transform 0.7s cubic-bezier(0.23, 1, 0.32, 1);
    }
    .exit-retention-floor-shadow {
      position: absolute;
      bottom: 26px;
      z-index: 1;
      width: 282px;
      height: 30px;
      border-radius: 50%;
      background: rgba(80, 120, 160, 0.15);
      filter: blur(10px);
      transition: transform 0.35s ease, opacity 0.35s ease;
    }
    .exit-retention-toast-wrapper {
      position: absolute;
      bottom: 78px;
      left: 50%;
      z-index: 2;
      width: 190px;
      height: 145px;
      transform: translateX(-50%) translateY(0);
    }
    .exit-retention-toast {
      position: absolute;
      bottom: 0;
      width: 100%;
      height: 100%;
      padding: 18px 20px 20px;
      border: 0;
      border-radius: 30px 30px 20px 20px;
      background: radial-gradient(circle at center, var(--exit-toast-crumb) 40%, #fdf0dc 100%);
      box-shadow: inset 0 0 0 10px var(--exit-toast-crust-in), inset 0 0 0 16px var(--exit-toast-crust-out), 0 15px 25px rgba(0,0,0,0.08);
      color: var(--exit-toast-stamp);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 8px;
      text-align: center;
      cursor: pointer;
      opacity: 0.98;
      transform: translateY(0);
      transition: transform 0.82s cubic-bezier(0.34, 1.56, 0.64, 1), width 0.7s ease, height 0.7s ease, padding 0.62s ease, border-radius 0.62s ease, box-shadow 0.62s ease, opacity 0.28s ease;
    }
    .exit-retention-toast:focus-visible { outline: 3px solid rgba(92, 168, 255, 0.42); outline-offset: 4px; }
    .exit-retention-toast-stamp { color: var(--exit-toast-stamp); font-size: 25px; font-weight: 900; line-height: 1; opacity: 0.84; filter: drop-shadow(0 1px 1px rgba(255,255,255,0.8)); }
    .exit-retention-toast-text { max-width: 136px; color: var(--exit-toast-stamp); font-size: 16px; font-weight: 900; line-height: 1.36; overflow-wrap: anywhere; }
    .exit-retention-toast-hint {
      position: absolute;
      top: -31px;
      left: 50%;
      padding: 4px 10px;
      border-radius: 11px;
      background: rgba(255,255,255,0.92);
      box-shadow: 0 4px 10px rgba(0,0,0,0.05);
      color: var(--exit-toast-crust-out);
      font-size: 12px;
      font-weight: 900;
      opacity: 0;
      transform: translate(-50%, 10px);
      transition: opacity 0.3s ease, transform 0.3s ease;
      white-space: nowrap;
      pointer-events: none !important;
    }
    .exit-retention-toast-hint::after {
      content: '';
      position: absolute;
      left: 50%;
      bottom: -6px;
      transform: translateX(-50%);
      width: 0;
      height: 0;
      border-left: 7px solid transparent;
      border-right: 7px solid transparent;
      border-top: 7px solid rgba(255,255,255,0.92);
      filter: drop-shadow(0 3px 2px rgba(0,0,0,0.04));
    }
    .exit-retention-scene.is-popped .exit-retention-toast { transform: translateY(-130px) rotate(-2deg); }
    .exit-retention-scene.is-popped .exit-retention-toast:hover,
    .exit-retention-scene.is-popped .exit-retention-toast:focus-visible {
      transform: translateY(-140px) rotate(1deg) scale(1.06);
      box-shadow: inset 0 0 0 10px var(--exit-toast-crust-in), inset 0 0 0 16px var(--exit-toast-crust-out), 0 25px 40px rgba(0,0,0,0.12);
    }
    .exit-retention-scene.is-popped .exit-retention-toast:hover .exit-retention-toast-hint,
    .exit-retention-scene.is-popped .exit-retention-toast:focus-visible .exit-retention-toast-hint { opacity: 1; transform: translate(-50%, 0); }
    .exit-retention-scene.is-popped .exit-retention-mouth {
      transform: rotate(180deg);
      border-bottom-width: 4px;
      border-radius: 0 0 15px 15px;
    }
    .exit-retention-toaster-box {
      position: relative;
      z-index: 10;
      width: 260px;
      height: 170px;
      display: flex;
      justify-content: center;
      border-radius: 50px 50px 25px 25px;
      background: linear-gradient(145deg, var(--exit-toaster-light), var(--exit-toaster-main));
      box-shadow: inset -8px -8px 20px var(--exit-toaster-shadow), inset 8px 8px 20px rgba(255,255,255,0.85), 0 30px 50px var(--exit-yui-blue-glow), 0 10px 20px rgba(92,168,230,0.2);
      transition: opacity 0.82s ease, transform 0.82s cubic-bezier(0.23, 1, 0.32, 1);
    }
    .exit-retention-toaster-slot-wrapper { position: absolute; top: 0; z-index: 12; width: 180px; height: 10px; border-radius: 12px; display: flex; align-items: center; justify-content: center; overflow: hidden; }
    .exit-retention-slot-heater { width: 90%; height: 4px; border-radius: 2px; background: transparent; transition: background 0.5s ease, box-shadow 0.5s ease; }
    .exit-retention-cat-ear { position: absolute; top: -30px; z-index: 9; width: 50px; height: 50px; border-radius: 10px; background: linear-gradient(145deg, var(--exit-toaster-light), var(--exit-toaster-main)); box-shadow: inset -5px -5px 10px var(--exit-toaster-shadow), inset 5px 5px 10px rgba(255,255,255,0.76); }
    .exit-retention-cat-ear--left { left: 20px; transform: rotate(-24deg); }
    .exit-retention-cat-ear--right { right: 20px; transform: rotate(24deg); }
    .exit-retention-cat-ear::after { content: ''; position: absolute; bottom: 5px; left: 12px; width: 26px; height: 30px; border-radius: 8px; background: linear-gradient(180deg, var(--exit-yui-pink), #ffd1dc); box-shadow: inset 0 2px 5px rgba(0,0,0,0.1); }
    .exit-retention-toaster-face { position: absolute; top: 55%; display: flex; align-items: center; gap: 20px; }
    .exit-retention-eye { position: relative; width: 14px; height: 14px; border-radius: 50%; background: #334a5e; animation: exitRetentionBlink 4s infinite; }
    .exit-retention-eye::after { content: ''; position: absolute; top: 2px; left: 3px; width: 5px; height: 5px; border-radius: 50%; background: #ffffff; }
    .exit-retention-mouth { width: 22px; height: 12px; border-bottom: 4px solid #334a5e; border-radius: 0 0 15px 15px; transition: all 0.3s ease; }
    .exit-retention-blush { position: absolute; top: 6px; width: 20px; height: 10px; border-radius: 50%; background: var(--exit-yui-pink); filter: blur(3px); opacity: 0.8; transition: all 0.3s ease; }
    .exit-retention-blush--left { left: -30px; }
    .exit-retention-blush--right { right: -30px; }
    .exit-retention-lever-track { position: absolute; right: -18px; top: 45px; z-index: 8; width: 14px; height: 80px; border-radius: 7px; background: var(--exit-toaster-dark); box-shadow: inset 2px 2px 5px rgba(0,0,0,0.30), 1px 0 2px rgba(255,255,255,0.5); pointer-events: none !important; }
    .exit-retention-lever-hotspot { position: absolute; right: -70px; top: 30px; z-index: 80; width: 112px; height: 120px; border: 0; padding: 0; background: transparent; cursor: pointer; }
    .exit-retention-lever-knob {
      position: absolute;
      top: 10px;
      left: 25px;
      width: 76px;
      height: 30px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 15px;
      background: linear-gradient(145deg, #ffffff, #e6f3ff);
      box-shadow: 3px 5px 10px rgba(0,0,0,0.15), inset 2px 2px 5px rgba(255,255,255,1), inset -2px -2px 5px rgba(150,200,255,0.3);
      color: #668aad;
      font-size: 12px;
      font-weight: 900;
      line-height: 1;
      letter-spacing: 0;
      white-space: nowrap;
      transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275), background 0.3s ease, box-shadow 0.3s ease, color 0.3s ease;
      pointer-events: none !important;
    }
    .exit-retention-lever-hotspot:hover .exit-retention-lever-knob,
    .exit-retention-lever-hotspot:focus-visible .exit-retention-lever-knob { transform: scale(1.1) translateX(2px); }
    .exit-retention-lever-hotspot:focus-visible { outline: none; }
    .exit-retention-lever-hotspot:active .exit-retention-lever-knob { transform: scale(0.95); }
    .exit-retention-steam-container { position: absolute; top: -10px; z-index: 15; width: 100%; height: 100px; display: none; pointer-events: none !important; }
    .exit-retention-steam { position: absolute; bottom: 0; border-radius: 50%; background: #ffffff; filter: blur(12px); opacity: 0; }
    .exit-retention-scene.is-heating .exit-retention-toaster-box { animation: exitRetentionHeatingVibrate 0.08s infinite; box-shadow: inset -8px -8px 20px var(--exit-toaster-shadow), inset 8px 8px 20px rgba(255,255,255,0.85), 0 30px 60px rgba(255,126,95,0.30), 0 10px 20px rgba(92,168,230,0.20); }
    .exit-retention-scene.is-heating .exit-retention-lever-knob { transform: translateY(55px); background: linear-gradient(145deg, #ff9a9e, #fecfef); box-shadow: 0 5px 15px rgba(255,154,158,0.50); }
    .exit-retention-scene.is-heating .exit-retention-lever-knob { color: #d77082; }
    .exit-retention-scene.is-heating .exit-retention-slot-heater { background: var(--exit-slot-glow); box-shadow: 0 0 15px 5px var(--exit-slot-glow); }
    .exit-retention-scene.is-heating .exit-retention-mouth { width: 18px; height: 18px; border: 4px solid #334a5e; border-radius: 50%; background: #ffb7c5; transform: translateY(2px); }
    .exit-retention-scene.is-heating .exit-retention-blush { background: var(--exit-slot-glow); transform: scale(1.2); }
    .exit-retention-scene.is-heating .exit-retention-eye { animation: none; transform: scaleY(1.2); }
    .exit-retention-scene.is-heating .exit-retention-steam-container { display: block; }
    .exit-retention-scene.is-heating .exit-retention-steam--a { left: 30%; width: 40px; height: 40px; animation: exitRetentionRise 1.2s infinite ease-in; }
    .exit-retention-scene.is-heating .exit-retention-steam--b { left: 50%; width: 50px; height: 50px; animation: exitRetentionRise 1.5s infinite ease-in 0.3s; }
    .exit-retention-scene.is-heating .exit-retention-steam--c { left: 65%; width: 35px; height: 35px; animation: exitRetentionRise 1.1s infinite ease-in 0.6s; }
    .exit-retention-scene.is-eaten { z-index: 110; pointer-events: none !important; }
    .exit-retention-scene.is-eaten .exit-retention-toast-wrapper { z-index: 120; bottom: 96px; width: 420px; height: 320px; transition: width 0.82s cubic-bezier(0.34, 1.56, 0.64, 1), height 0.82s cubic-bezier(0.34, 1.56, 0.64, 1), bottom 0.82s cubic-bezier(0.34, 1.56, 0.64, 1); }
    .exit-retention-scene.is-popped.is-eaten .exit-retention-toast,
    .exit-retention-scene.is-popped.is-eaten .exit-retention-toast:hover,
    .exit-retention-scene.is-popped.is-eaten .exit-retention-toast:focus-visible {
      transform: translateY(-18px) rotate(0deg) scale(1);
      padding: 44px 50px 48px;
      border-radius: 58px 58px 34px 34px;
      box-shadow: inset 0 0 0 14px var(--exit-toast-crust-in), inset 0 0 0 24px var(--exit-toast-crust-out), 0 30px 58px rgba(120, 78, 40, 0.18);
      cursor: default;
    }
    .exit-retention-scene.is-eaten .exit-retention-toast-stamp,
    .exit-retention-scene.is-eaten .exit-retention-toast-hint { display: none; }
    .exit-retention-scene.is-eaten .exit-retention-toast-text { max-width: 310px; font-size: 22px; line-height: 1.72; font-weight: 900; white-space: pre-wrap; transition: opacity 0.2s ease 0.48s; }
    .exit-retention-scene.is-eaten .exit-retention-toast-text::after { content: ''; display: inline-block; width: 3px; height: 22px; margin-left: 4px; vertical-align: middle; background: var(--exit-toast-stamp); animation: exitRetentionCaret 0.8s infinite; }
    .exit-retention-farewell-complete .exit-retention-toast-text::after { content: none; }
    .exit-retention-scene.is-eaten .exit-retention-toaster-box,
    .exit-retention-scene.is-eaten .exit-retention-floor-shadow { opacity: 0; transform: translateY(110px) scale(0.86); }
    @keyframes exitRetentionBlink { 0%, 96%, 100% { transform: scaleY(1); } 98% { transform: scaleY(0.1); } }
    @keyframes exitRetentionHeatingVibrate { 0%, 100% { transform: translate(0,0); } 25% { transform: translate(1px,-1px); } 50% { transform: translate(-1px,1px); } 75% { transform: translate(1px,1px); } }
    @keyframes exitRetentionRise { 0% { transform: translateY(0) scale(0.5); opacity: 0; } 30% { opacity: 0.8; } 100% { transform: translateY(-100px) scale(2.5); opacity: 0; } }
    @keyframes exitRetentionCaret { 50% { opacity: 0; } }
    @media (max-width: 760px) {
      .storage-location-modal.exit-retention-stage { width: min(720px, calc(100vw - 32px)); height: min(590px, calc(100vh - 32px)); border-radius: 42px; }
      .exit-retention-scene { transform: scale(0.9); }
      .exit-retention-scene.is-eaten { transform: none; }
      .exit-retention-scene.is-eaten .exit-retention-toast-wrapper { width: min(420px, calc(100vw - 88px)); height: 320px; }
    }
  </style>
</head>
<body class="storage-location-modal-open">
  ${confirmVoiceUrl ? `<audio id="exit-retention-confirm-voice" preload="auto" src="${escapeHtml(confirmVoiceUrl)}"></audio>` : ''}
  ${farewellVoiceUrl ? `<audio id="exit-retention-voice" preload="auto" src="${escapeHtml(farewellVoiceUrl)}"></audio>` : ''}
  <div class="storage-location-overlay" id="storage-location-overlay">
    <section class="storage-location-modal exit-retention-stage" role="dialog" aria-modal="true" aria-labelledby="exit-retention-title">
      <div class="exit-retention-modal-container" id="exit-retention-modal-container">
        <div class="exit-retention-scene" id="exit-retention-scene">
          <h1 id="exit-retention-title" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;">${title}</h1>
          <div class="exit-retention-floor-shadow" aria-hidden="true"></div>
          <div class="exit-retention-toast-wrapper">
            <button class="exit-retention-toast" id="exit-retention-confirm" type="button" aria-disabled="true" aria-label="${confirmText}">
              <span class="exit-retention-toast-hint">${toastHintText}</span>
              <span class="exit-retention-toast-stamp">இдஇ</span>
              <span class="exit-retention-toast-text" id="exit-retention-toast-text">${toastPromptText}</span>
            </button>
          </div>
          <div class="exit-retention-toaster-box">
            <div class="exit-retention-steam-container" aria-hidden="true">
              <div class="exit-retention-steam exit-retention-steam--a"></div>
              <div class="exit-retention-steam exit-retention-steam--b"></div>
              <div class="exit-retention-steam exit-retention-steam--c"></div>
            </div>
            <div class="exit-retention-cat-ear exit-retention-cat-ear--left" aria-hidden="true"></div>
            <div class="exit-retention-cat-ear exit-retention-cat-ear--right" aria-hidden="true"></div>
            <div class="exit-retention-toaster-slot-wrapper" aria-hidden="true"><div class="exit-retention-slot-heater"></div></div>
            <div class="exit-retention-toaster-face" aria-hidden="true">
              <div class="exit-retention-blush exit-retention-blush--left"></div>
              <div class="exit-retention-eye"></div>
              <div class="exit-retention-mouth"></div>
              <div class="exit-retention-eye"></div>
              <div class="exit-retention-blush exit-retention-blush--right"></div>
            </div>
            <div class="exit-retention-lever-track" aria-hidden="true"></div>
            <button class="exit-retention-lever-hotspot" id="exit-retention-lever" type="button" aria-label="${chooseText}">
              <span class="exit-retention-lever-knob" aria-hidden="true">${leverText}</span>
            </button>
          </div>
        </div>

      </div>
    </section>
  </div>
  <script>
    const farewellText = ${safeScriptJson(farewellMessage)};
    const typeIntervalMs = ${EXIT_RETENTION_TYPE_INTERVAL_MS};
    const noVoiceHoldMs = ${EXIT_RETENTION_NO_VOICE_HOLD_MS};
    const farewellTimeoutMs = ${EXIT_RETENTION_FAREWELL_TIMEOUT_MS};
    const farewellRevealDelayMs = 620;
    const stayText = ${safeScriptJson(stayRawText)};
    const scene = document.getElementById('exit-retention-scene');
    const toastButton = document.getElementById('exit-retention-confirm');
    const leverButton = document.getElementById('exit-retention-lever');
    let toastPopped = false;
	    let toastBusy = false;
	    let farewellStarted = false;
	    let textDone = false;
	    let audioDone = !document.getElementById('exit-retention-voice');
	    let finished = false;
	    ${getExitRetentionPointerPassthroughScript()}
	
	    function choose(action) {
	      window.location.href = 'neko-exit-retention://' + action;
	    }

    function finishFarewell() {
      if (finished) return;
      finished = true;
      document.body.classList.add('exit-retention-farewell-complete');
      choose('finish-confirm');
    }

    function finishIfReady() {
      if (!textDone || !audioDone) return;
      if (document.getElementById('exit-retention-voice')) {
        finishFarewell();
        return;
      }
      setTimeout(finishFarewell, noVoiceHoldMs);
    }

    function typeFarewellText() {
      const target = document.getElementById('exit-retention-toast-text');
      const chars = Array.from(farewellText || '');
      let index = 0;
      target.textContent = '';
      if (!chars.length) {
        textDone = true;
        finishIfReady();
        return;
      }
      const timer = setInterval(function () {
        target.textContent += chars[index] || '';
        index += 1;
        if (index >= chars.length) {
          clearInterval(timer);
          textDone = true;
          finishIfReady();
        }
      }, typeIntervalMs);
    }

    const exitRetentionVoiceVolume = ${voiceGain};
    function applyExitRetentionVoiceVolume(audioEl) {
      if (!audioEl) return;
      try { audioEl.volume = exitRetentionVoiceVolume; } catch (_) {}
    }
    function playConfirmVoice() {
      const confirmVoice = document.getElementById('exit-retention-confirm-voice');
      if (!confirmVoice) return;
      applyExitRetentionVoiceVolume(confirmVoice);
      confirmVoice.play().catch(function () {});
    }

    function stopConfirmVoice() {
      const confirmVoice = document.getElementById('exit-retention-confirm-voice');
      if (!confirmVoice) return;
      confirmVoice.pause();
      try {
        confirmVoice.currentTime = 0;
      } catch (_) {}
    }

    function makeToast() {
      if (toastPopped && !farewellStarted) {
        cancelAfterToast();
        return;
      }
      if (toastBusy || farewellStarted) return;
      toastBusy = true;
      leverButton.disabled = true;
      scene.classList.add('is-heating');
      setTimeout(function () {
        scene.classList.remove('is-heating');
        scene.classList.add('is-popped');
        toastPopped = true;
        toastBusy = false;
        leverButton.disabled = false;
        leverButton.setAttribute('aria-label', stayText);
        leverButton.querySelector('.exit-retention-lever-knob').textContent = stayText;
        toastButton.setAttribute('aria-disabled', 'false');
        playConfirmVoice();
      }, 1200);
    }

    function cancelAfterToast() {
      if (farewellStarted) return;
      stopConfirmVoice();
      choose('cancel');
    }

    function startFarewell() {
      if (!toastPopped || farewellStarted) return;
      farewellStarted = true;
      stopConfirmVoice();
      scene.classList.add('is-eaten');
      document.body.classList.add('exit-retention-is-farewell');
      toastButton.disabled = true;
      leverButton.disabled = true;
      choose('confirmed');
      setTimeout(typeFarewellText, farewellRevealDelayMs);
      const voice = document.getElementById('exit-retention-voice');
      if (voice) {
        applyExitRetentionVoiceVolume(voice);
        voice.addEventListener('ended', function () {
          audioDone = true;
          finishIfReady();
        }, { once: true });
        voice.addEventListener('error', function () {
          audioDone = true;
          finishIfReady();
        }, { once: true });
        voice.play().catch(function () {
          audioDone = true;
          finishIfReady();
        });
      }
      setTimeout(finishFarewell, farewellTimeoutMs);
    }

    document.getElementById('exit-retention-lever').addEventListener('click', makeToast);
    document.getElementById('exit-retention-confirm').addEventListener('click', startFarewell);
    window.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && !farewellStarted) choose('cancel');
    });
  </script>
</body>
</html>`;
  }
  function buildExitRetentionDialogHtml(language = getCurrentLanguage(), confirmVoiceUrl = '', farewellVoiceUrl = '', dayIndex = 0, speakerVolume = 100) {
    return buildExitRetentionKittenDialogHtml(language, confirmVoiceUrl, farewellVoiceUrl, dayIndex, speakerVolume);
  }

  function parseExitRetentionAction(url) {
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== 'neko-exit-retention:') return null;
      return parsed.hostname || parsed.pathname.replace(/^\/+/, '');
    } catch (_) {
      return null;
    }
  }

  function readExitRetentionVoiceUrl(voiceCandidates, failureLogMessage) {
    let selectedVoicePath = '';
    try {
      selectedVoicePath = voiceCandidates.find((candidate) => fs.existsSync(candidate)) || '';
      if (selectedVoicePath) {
        const mimeType = getExitRetentionVoiceMimeType(selectedVoicePath);
        return {
          voiceUrl: `data:${mimeType};base64,${fs.readFileSync(selectedVoicePath).toString('base64')}`,
          selectedVoicePath,
          voiceCandidates,
        };
      }
    } catch (e) {
      log(failureLogMessage, e.message);
    }
    return { voiceUrl: '', selectedVoicePath, voiceCandidates };
  }

  async function confirmTrayExitWithRetention() {
    if (exitRetentionConfirmPromise) {
      try {
        if (exitRetentionWindow && !exitRetentionWindow.isDestroyed()) {
          exitRetentionWindow.show();
          exitRetentionWindow.focus();
        }
      } catch (_) {}
      return exitRetentionConfirmPromise;
    }

    if (shouldSkipExitRetentionToday()) {
      log('退出挽留今日已展示过，后续托盘退出直接继续');
      return true;
    }

    let resolveConfirm;
    const pendingExitRetentionConfirmPromise = new Promise((resolve) => {
      resolveConfirm = resolve;
    });
    exitRetentionConfirmPromise = pendingExitRetentionConfirmPromise;

    let settled = false;
    let shutdownStarted = false;
    const settle = (confirmed) => {
      if (settled) return;
      settled = true;
      const win = exitRetentionWindow;
      exitRetentionWindow = null;
      exitRetentionConfirmPromise = null;
      if (win && !win.isDestroyed()) {
        win.destroy();
      }
      resolveConfirm(!!confirmed);
    };

    const exitRetentionDayKey = getTodayKey();
    // 两个探针都各带 1s 超时且互不依赖，并行跑避免最坏 2s 串行等待。
    const [exitLanguage, speakerVolume] = await Promise.all([
      resolveExitRetentionLanguage(),
      resolveExitRetentionSpeakerVolume(),
    ]);
    const dayIndex = getExitRetentionDayIndex(exitRetentionDayKey);
    const {
      voiceUrl: confirmVoiceUrl,
      selectedVoicePath: selectedConfirmVoicePath,
      voiceCandidates: confirmVoiceCandidates,
    } = readExitRetentionVoiceUrl(
      getExitRetentionConfirmVoiceCandidates(exitLanguage),
      '退出确认语音读取失败，继续显示确认弹窗:',
    );
    const {
      voiceUrl: farewellVoiceUrl,
      selectedVoicePath: selectedFarewellVoicePath,
      voiceCandidates: farewellVoiceCandidates,
    } = readExitRetentionVoiceUrl(
      getExitRetentionVoiceCandidates(exitLanguage, dayIndex),
      '退出挽留语音读取失败，降级为无语音告别:',
    );
    if (!confirmVoiceUrl) {
      log('退出确认语音不存在，确认弹窗仅显示文案:', confirmVoiceCandidates.join(', '));
    } else {
      log('退出确认语音已选择:', selectedConfirmVoicePath);
    }
    if (!farewellVoiceUrl) {
      log('退出挽留语音不存在，确认后只显示文案:', farewellVoiceCandidates.join(', '));
    } else {
      log('退出挽留语音已选择:', selectedFarewellVoicePath);
    }

    const startShutdown = () => {
      if (shutdownStarted) return;
      shutdownStarted = true;
      try {
        beginExitRetentionShutdown('tray menu exit confirmed');
      } catch (e) {
        log('退出挽留确认后启动 shutdown 失败，继续等待退出:', e.message);
      }
    };

    const handleExitRetentionAction = (action) => {
      if (action === 'pointer-active') {
        setExitRetentionPointerPassthrough(false);
        return;
      }
      if (action === 'pointer-passive') {
        setExitRetentionPointerPassthrough(true);
        return;
      }
      if (action === 'confirmed') {
        startShutdown();
        return;
      }
      if (action === 'finish-confirm') {
        settle(true);
        return;
      }
      if (action === 'stay') {
        settle(false);
        try {
          requestCompactKittenCompanion();
        } catch (e) {
          log('退出挽留触发小猫形态失败:', e.message);
        }
        return;
      }
      if (!shutdownStarted) {
        settle(false);
      }
    };

    try {
      const parentWindow = getMainWindow() && !getMainWindow().isDestroyed() ? getMainWindow() : undefined;
      const win = new BrowserWindow({
        width: EXIT_RETENTION_WINDOW_WIDTH,
        height: EXIT_RETENTION_WINDOW_HEIGHT,
        minWidth: EXIT_RETENTION_WINDOW_WIDTH,
        minHeight: EXIT_RETENTION_WINDOW_HEIGHT,
        frame: false,
        transparent: true,
        hasShadow: false,
        resizable: false,
        minimizable: false,
        maximizable: false,
        fullscreenable: false,
        focusable: true,
        acceptFirstMouse: true,
        show: false,
        skipTaskbar: true,
        parent: parentWindow,
        modal: false,
        title: t('exitRetentionTitle'),
        backgroundColor: '#00000000',
        webPreferences: {
          nodeIntegration: false,
          contextIsolation: true,
          sandbox: true,
          webSecurity: true,
          backgroundThrottling: false,
        },
      });

      exitRetentionWindow = win;
      setExitRetentionPointerPassthrough(true);
      win.setAlwaysOnTop(true, getExitRetentionTopLevel());
      win.webContents.on('will-navigate', (event, url) => {
        const action = parseExitRetentionAction(url);
        if (!action) return;
        event.preventDefault();
        handleExitRetentionAction(action);
      });
      win.webContents.setWindowOpenHandler(({ url }) => {
        const action = parseExitRetentionAction(url);
        if (action) handleExitRetentionAction(action);
        return { action: 'deny' };
      });
      win.once('ready-to-show', () => {
        if (!win.isDestroyed()) {
          win.setAlwaysOnTop(true, getExitRetentionTopLevel());
          win.show();
          markExitRetentionShownToday(dayIndex, exitRetentionDayKey);
          win.focus();
        }
      });
      win.on('closed', () => settle(shutdownStarted));
      win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(buildExitRetentionDialogHtml(exitLanguage, confirmVoiceUrl, farewellVoiceUrl, dayIndex, speakerVolume))}`)
        .catch((e) => {
          log('退出挽留弹窗加载失败，取消退出:', e.message);
          settle(false);
        });
    } catch (e) {
      log('退出挽留弹窗失败，取消退出:', e.message);
      settle(false);
    }

    return pendingExitRetentionConfirmPromise;
  }

  return {
    confirmTrayExitWithRetention,
  };
}

module.exports = {
  createExitRetentionPrompt,
};
