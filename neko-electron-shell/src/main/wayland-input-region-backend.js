'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');

const WAYLAND_SET_SHAPE_ELECTRON_VERSION = '41.2.0';
const WAYLAND_SET_SHAPE_ELECTRON_SHA256 = '9c1a3a9faf3f748157d35f071611fc3b4527cb45fb750e8e9b235825f18dacee';
const WAYLAND_SET_SHAPE_ELECTRON_SIZE_BYTES = 205941880;
const ELECTRON_FUSE_SENTINEL = Buffer.from('dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX');
const WAYLAND_SET_SHAPE_ELECTRON_DEFAULT_FUSE_WIRE = Buffer.from('101100011', 'latin1');

let cachedExecutableSha256 = null;
let cachedExecutableSha256Path = null;
let cachedExecutableSha256Error = null;

function _resetExecutableSha256CacheForTest() {
  cachedExecutableSha256 = null;
  cachedExecutableSha256Path = null;
  cachedExecutableSha256Error = null;
}

function isTruthyEnv(value) {
  return /^(1|true|yes|on)$/i.test(String(value || '').trim());
}

function normalizeElectronFuseWireForHash(buffer) {
  if (!Buffer.isBuffer(buffer)) return buffer;
  let normalized = null;
  let searchOffset = 0;

  while (searchOffset < buffer.length) {
    const sentinelIndex = buffer.indexOf(ELECTRON_FUSE_SENTINEL, searchOffset);
    if (sentinelIndex < 0) break;
    const versionIndex = sentinelIndex + ELECTRON_FUSE_SENTINEL.length;
    const wireLengthIndex = versionIndex + 1;
    const wireIndex = wireLengthIndex + 1;
    if (wireIndex >= buffer.length) break;

    const fuseVersion = buffer[versionIndex];
    const wireLength = buffer[wireLengthIndex];
    const replaceLength = Math.min(wireLength, WAYLAND_SET_SHAPE_ELECTRON_DEFAULT_FUSE_WIRE.length);
    if (fuseVersion === 1 && replaceLength > 0 && wireIndex + replaceLength <= buffer.length) {
      for (let i = 0; i < replaceLength; i += 1) {
        const expected = WAYLAND_SET_SHAPE_ELECTRON_DEFAULT_FUSE_WIRE[i];
        if (buffer[wireIndex + i] !== expected) {
          if (!normalized) normalized = Buffer.from(buffer);
          normalized[wireIndex + i] = expected;
        }
      }
    }
    searchOffset = wireIndex + Math.max(0, wireLength);
  }

  return normalized || buffer;
}

function isWaylandSessionEnv(env = process.env) {
  return String(env.XDG_SESSION_TYPE || '').toLowerCase() === 'wayland'
    || !!String(env.WAYLAND_DISPLAY || '').trim();
}

function getWaylandCompositorName(env = process.env) {
  const candidates = [
    env.XDG_CURRENT_DESKTOP,
    env.DESKTOP_SESSION,
    env.KDE_FULL_SESSION ? 'KDE' : '',
    env.SWAYSOCK ? 'sway' : '',
    env.NIRI_SOCKET ? 'niri' : '',
  ];
  return candidates.map((value) => String(value || '').trim()).find(Boolean) || 'unknown';
}

function getExecutableSha256(execPath, fsImpl = fs, cryptoImpl = crypto) {
  if (!execPath) return { sha256: null, error: 'missing-exec-path' };
  if (cachedExecutableSha256Path === execPath) {
    return { sha256: cachedExecutableSha256, error: cachedExecutableSha256Error };
  }
  cachedExecutableSha256Path = execPath;
  cachedExecutableSha256 = null;
  cachedExecutableSha256Error = null;
  try {
    const stat = typeof fsImpl.statSync === 'function' ? fsImpl.statSync(execPath) : null;
    const size = stat && Number.isFinite(Number(stat.size)) ? Number(stat.size) : null;
    if (size !== null && size !== WAYLAND_SET_SHAPE_ELECTRON_SIZE_BYTES) {
      cachedExecutableSha256Error = 'size-mismatch:' + size;
      return { sha256: cachedExecutableSha256, error: cachedExecutableSha256Error };
    }
    const executable = fsImpl.readFileSync(execPath);
    cachedExecutableSha256 = cryptoImpl
      .createHash('sha256')
      .update(normalizeElectronFuseWireForHash(executable))
      .digest('hex');
  } catch (error) {
    cachedExecutableSha256Error = error && error.message ? error.message : String(error || 'sha256-failed');
  }
  return { sha256: cachedExecutableSha256, error: cachedExecutableSha256Error };
}

function getWaylandSetShapePatchStatus(options = {}) {
  const proc = options.process || process;
  const env = proc.env || {};
  const platform = options.platform || proc.platform;
  const electronVersion = proc.versions && proc.versions.electron ? String(proc.versions.electron) : '';
  const execPath = options.execPath || proc.execPath || '';
  const status = {
    platform,
    isWaylandSession: isWaylandSessionEnv(env),
    compositor: getWaylandCompositorName(env),
    electronVersion,
    expectedElectronVersion: WAYLAND_SET_SHAPE_ELECTRON_VERSION,
    execPath,
    execSha256: null,
    expectedSha256: WAYLAND_SET_SHAPE_ELECTRON_SHA256,
    verified: false,
    forced: false,
    disabled: false,
    reason: '',
  };

  if (platform !== 'linux') {
    status.reason = 'not-linux';
    return status;
  }
  if (isTruthyEnv(env.NEKO_DISABLE_WAYLAND_SET_SHAPE)) {
    status.disabled = true;
    status.reason = 'disabled-by-env';
    return status;
  }
  if (isTruthyEnv(env.NEKO_ASSUME_WAYLAND_SET_SHAPE_PATCH) || isTruthyEnv(env.NEKO_WAYLAND_SET_SHAPE_PATCHED)) {
    status.verified = true;
    status.forced = true;
    status.reason = 'forced-by-env';
    return status;
  }
  const isWaylandRuntime = typeof options.isLinuxWaylandRuntime === 'function'
    ? !!options.isLinuxWaylandRuntime()
    : status.isWaylandSession;
  if (!isWaylandRuntime) {
    status.reason = 'not-wayland-runtime';
    return status;
  }
  if (electronVersion !== WAYLAND_SET_SHAPE_ELECTRON_VERSION) {
    status.reason = electronVersion ? 'electron-version-mismatch' : 'missing-electron-version';
    return status;
  }

  const hash = getExecutableSha256(execPath, options.fs || fs, options.crypto || crypto);
  status.execSha256 = hash.sha256;
  if (hash.error) {
    status.reason = 'sha256-unavailable:' + hash.error;
    return status;
  }
  if (hash.sha256 === WAYLAND_SET_SHAPE_ELECTRON_SHA256) {
    status.verified = true;
    status.reason = 'sha256-match';
    return status;
  }
  status.reason = 'sha256-mismatch';
  return status;
}

function shouldAllowUnverifiedWaylandSetShape(options = {}, env = process.env) {
  if (isTruthyEnv(env.NEKO_DISABLE_WAYLAND_SET_SHAPE)) return false;
  return options.allowUnverifiedWaylandSetShape === true
    || isTruthyEnv(env.NEKO_ALLOW_UNVERIFIED_WAYLAND_SET_SHAPE);
}

function isWaylandSetShapePatchVerified(options = {}) {
  return getWaylandSetShapePatchStatus(options).verified === true;
}

function shouldAutoFallbackToX11ForWayland(options = {}) {
  const proc = options.process || process;
  const env = proc.env || {};
  if ((options.platform || proc.platform) !== 'linux') return false;
  if (!isWaylandSessionEnv(env)) return false;
  if (shouldAllowUnverifiedWaylandSetShape(options, env)) return false;
  return !isWaylandSetShapePatchVerified(options);
}

function getLinuxInputRegionBackend(options = {}) {
  const proc = options.process || process;
  const platform = options.platform || proc.platform;
  const isWaylandRuntime = typeof options.isLinuxWaylandRuntime === 'function'
    ? !!options.isLinuxWaylandRuntime()
    : isWaylandSessionEnv(proc.env || {});
  const win = options.win || null;
  const hasSetShapeMethod = !!(win && !win.isDestroyed?.() && typeof win.setShape === 'function');
  const patchStatus = getWaylandSetShapePatchStatus(options);
  const allowUnverifiedWaylandSetShape = shouldAllowUnverifiedWaylandSetShape(options, proc.env || {});

  if (platform !== 'linux') {
    return {
      backend: 'native-ignore',
      canUseSetShape: false,
      hasSetShapeMethod,
      patchStatus,
    };
  }
  if (!isWaylandRuntime) {
    return {
      backend: 'x11-shape',
      canUseSetShape: false,
      hasSetShapeMethod,
      patchStatus,
    };
  }
  if (patchStatus.disabled) {
    return {
      backend: 'wayland-setshape-disabled',
      canUseSetShape: false,
      hasSetShapeMethod,
      patchStatus,
    };
  }
  if (hasSetShapeMethod && patchStatus.verified) {
    return {
      backend: 'wayland-setshape',
      canUseSetShape: true,
      hasSetShapeMethod,
      patchStatus,
    };
  }
  if (hasSetShapeMethod && allowUnverifiedWaylandSetShape) {
    return {
      backend: 'wayland-unverified-setshape-allowed',
      canUseSetShape: true,
      hasSetShapeMethod,
      patchStatus,
    };
  }
  return {
    backend: hasSetShapeMethod ? 'wayland-unverified-setshape' : 'wayland-no-setshape',
    canUseSetShape: false,
    hasSetShapeMethod,
    patchStatus,
  };
}

module.exports = {
  WAYLAND_SET_SHAPE_ELECTRON_SHA256,
  WAYLAND_SET_SHAPE_ELECTRON_SIZE_BYTES,
  WAYLAND_SET_SHAPE_ELECTRON_VERSION,
  _resetExecutableSha256CacheForTest,
  getLinuxInputRegionBackend,
  getWaylandCompositorName,
  getWaylandSetShapePatchStatus,
  isWaylandSessionEnv,
  isWaylandSetShapePatchVerified,
  shouldAllowUnverifiedWaylandSetShape,
  shouldAutoFallbackToX11ForWayland,
};
