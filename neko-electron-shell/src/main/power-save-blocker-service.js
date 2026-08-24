'use strict';

const BLOCKER_TYPE = 'prevent-app-suspension';

function createPowerSaveBlockerService(context = {}) {
  const {
    powerSaveBlocker,
    log = () => {},
  } = context;

  let blockerId = null;

  function writeLog(...args) {
    try {
      log(...args);
    } catch (_) {
      // Logging must never affect power-state cleanup.
    }
  }

  function isSupported() {
    return !!(
      powerSaveBlocker
      && typeof powerSaveBlocker.start === 'function'
      && typeof powerSaveBlocker.stop === 'function'
      && typeof powerSaveBlocker.isStarted === 'function'
    );
  }

  function isStarted(id) {
    if (!isSupported() || id === null || typeof id === 'undefined') return false;
    try {
      return !!powerSaveBlocker.isStarted(id);
    } catch (_) {
      return false;
    }
  }

  function clearStaleBlocker() {
    if (blockerId !== null && !isStarted(blockerId)) {
      blockerId = null;
    }
  }

  function getStatus() {
    clearStaleBlocker();
    return {
      supported: isSupported(),
      active: blockerId !== null,
      blockerId,
      type: BLOCKER_TYPE,
    };
  }

  function start(reason = 'manual') {
    if (!isSupported()) {
      return {
        ok: false,
        error: 'power_save_blocker_unavailable',
        ...getStatus(),
      };
    }

    clearStaleBlocker();
    if (blockerId !== null) {
      return {
        ok: true,
        ...getStatus(),
      };
    }

    try {
      const nextId = powerSaveBlocker.start(BLOCKER_TYPE);
      if (!isStarted(nextId)) {
        return {
          ok: false,
          error: 'power_save_blocker_start_failed',
          ...getStatus(),
        };
      }
      blockerId = nextId;
      writeLog('防睡眠已启用:', `id=${blockerId}`, `type=${BLOCKER_TYPE}`, `reason=${reason}`);
      return {
        ok: true,
        ...getStatus(),
      };
    } catch (error) {
      blockerId = null;
      return {
        ok: false,
        error: error && error.message ? error.message : 'power_save_blocker_start_failed',
        ...getStatus(),
      };
    }
  }

  function stop(reason = 'manual') {
    const previousId = blockerId;
    blockerId = null;

    if (isSupported() && previousId !== null) {
      try {
        if (isStarted(previousId)) {
          powerSaveBlocker.stop(previousId);
        }
      } catch (error) {
        writeLog('防睡眠停止失败:', error && error.message ? error.message : error);
      }
      writeLog('防睡眠已关闭:', `id=${previousId}`, `reason=${reason}`);
    }

    return {
      ok: true,
      ...getStatus(),
    };
  }

  function setEnabled(enabled, reason = 'manual') {
    return enabled ? start(reason) : stop(reason);
  }

  function isActive() {
    return getStatus().active;
  }

  return {
    type: BLOCKER_TYPE,
    getStatus,
    isActive,
    setEnabled,
    start,
    stop,
  };
}

module.exports = {
  createPowerSaveBlockerService,
};
