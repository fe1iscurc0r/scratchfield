const nodeFs = require('node:fs');
const nodePath = require('node:path');
const nodeOs = require('node:os');

const SUPPORTED_LOGIN_ITEM_PLATFORMS = new Set(['win32', 'darwin']);

const PROVIDER_NAME = 'neko-pc';
const LOGIN_ITEM_MECHANISM = 'electron-login-item';
const XDG_AUTOSTART_MECHANISM = 'xdg-autostart';
const UNSUPPORTED_MECHANISM = 'unsupported';
const PACKAGED_APP_REQUIRED_ERROR = 'autostart_requires_packaged_app';
const REQUIRES_APPROVAL_ERROR = 'autostart_requires_approval';
const SERVICE_NOT_FOUND_ERROR = 'autostart_service_not_found';
const CONFIG_SYNC_FAILED_ERROR = 'autostart_config_sync_failed';

const XDG_DESKTOP_FILE_NAME = 'neko-pc.desktop';

function getPlatformName(platform) {
  switch (platform) {
    case 'win32':
      return 'windows';
    case 'darwin':
      return 'macos';
    case 'linux':
      return 'linux';
    default:
      return String(platform || 'unknown');
  }
}

function createAutostartService({
  app,
  log,
  getConfig,
  saveConfig,
  isPackaged,
  platform,
  processExecPath,
  fs,
  homeDir,
  env,
}) {
  const writeLog = typeof log === 'function' ? log : () => {};
  const readConfig = typeof getConfig === 'function' ? getConfig : () => ({});
  const persistConfig = typeof saveConfig === 'function' ? saveConfig : () => {};
  const runtimeIsPackaged = typeof isPackaged === 'boolean'
    ? isPackaged
    : (typeof app?.isPackaged === 'boolean' ? app.isPackaged : true);
  const runtimePlatform = typeof platform === 'string' && platform
    ? platform
    : process.platform;
  const fallbackExecPath = typeof processExecPath === 'string' && processExecPath
    ? processExecPath
    : process.execPath;
  const runtimeFs = fs || nodeFs;
  const runtimeHomeDir = typeof homeDir === 'function'
    ? homeDir
    : (typeof homeDir === 'string' && homeDir
      ? () => homeDir
      : () => {
        try {
          if (typeof app?.getPath === 'function') {
            const p = app.getPath('home');
            if (p) return p;
          }
        } catch (_e) {}
        return nodeOs.homedir();
      });
  const runtimeEnv = (env && typeof env === 'object') ? env : process.env;

  function isLinuxRuntime() {
    return runtimePlatform === 'linux';
  }

  function hasLoginItemApi() {
    return SUPPORTED_LOGIN_ITEM_PLATFORMS.has(runtimePlatform)
      && typeof app?.getLoginItemSettings === 'function'
      && typeof app?.setLoginItemSettings === 'function';
  }

  function hasXdgAutostartCapability() {
    if (!isLinuxRuntime()) return false;
    return runtimeFs
      && typeof runtimeFs.readFileSync === 'function'
      && typeof runtimeFs.writeFileSync === 'function'
      && typeof runtimeFs.existsSync === 'function'
      && typeof runtimeFs.unlinkSync === 'function'
      && typeof runtimeFs.mkdirSync === 'function';
  }

  function getUnsupportedErrorCode() {
    if (isLinuxRuntime()) {
      if (!hasXdgAutostartCapability()) {
        return 'autostart_not_supported';
      }
      if (!runtimeIsPackaged) {
        return PACKAGED_APP_REQUIRED_ERROR;
      }
      return null;
    }
    if (!hasLoginItemApi()) {
      return 'autostart_not_supported';
    }
    if (!runtimeIsPackaged) {
      return PACKAGED_APP_REQUIRED_ERROR;
    }
    return null;
  }

  function isSupported() {
    return getUnsupportedErrorCode() === null;
  }

  function getMechanism() {
    if (!isSupported()) {
      return UNSUPPORTED_MECHANISM;
    }
    if (isLinuxRuntime()) {
      return XDG_AUTOSTART_MECHANISM;
    }
    return LOGIN_ITEM_MECHANISM;
  }

  function getConfiguredEnabled() {
    try {
      const config = readConfig() || {};
      return !!config.autoLaunch;
    } catch (error) {
      writeLog('autostart - 读取配置失败:', error.message);
      return false;
    }
  }

  function saveConfiguredEnabled(enabled) {
    try {
      const currentConfig = readConfig() || {};
      if (currentConfig.autoLaunch === !!enabled) {
        return currentConfig;
      }
      const nextConfig = {
        ...currentConfig,
        autoLaunch: !!enabled,
      };
      persistConfig(nextConfig);
      writeLog('autostart - 已同步配置 autoLaunch:', !!enabled);
      return nextConfig;
    } catch (error) {
      writeLog('autostart - 保存配置失败:', error.message);
      const configError = new Error(error.message);
      configError.code = CONFIG_SYNC_FAILED_ERROR;
      configError.cause = error;
      throw configError;
    }
  }

  function getExecutablePath() {
    try {
      if (typeof app?.getPath === 'function') {
        const exePath = app.getPath('exe');
        if (exePath) {
          return exePath;
        }
      }
    } catch (error) {
      writeLog('autostart - 获取 exe 路径失败，回退到 process.execPath:', error.message);
    }
    return fallbackExecPath || '';
  }

  function getXdgAutostartDir() {
    const pathApi = isLinuxRuntime() ? nodePath.posix : nodePath;
    const xdgConfigHome = runtimeEnv.XDG_CONFIG_HOME;
    const configHome = (xdgConfigHome && pathApi.isAbsolute(xdgConfigHome))
      ? xdgConfigHome
      : pathApi.join(runtimeHomeDir(), '.config');
    return pathApi.join(configHome, 'autostart');
  }

  function getXdgAutostartFilePath() {
    const pathApi = isLinuxRuntime() ? nodePath.posix : nodePath;
    return pathApi.join(getXdgAutostartDir(), XDG_DESKTOP_FILE_NAME);
  }

  function buildXdgDesktopFileContents(execPath) {
    // Escape per Desktop Entry spec: char escapes first (backslash first to avoid
    // double-escaping), then field-code escape (% → %%).
    const escapedPath = execPath
      .replace(/\\/g, '\\\\')
      .replace(/\$/g, '\\$')
      .replace(/`/g, '\\`')
      .replace(/"/g, '\\"')
      .replace(/%/g, '%%');
    return [
      '[Desktop Entry]',
      'Type=Application',
      'Name=N.E.K.O',
      `Exec="${escapedPath}"`,
      'Hidden=false',
      'NoDisplay=false',
      'X-GNOME-Autostart-enabled=true',
      '',
    ].join('\n');
  }

  function readXdgAutostartEnabled() {
    if (!runtimeFs.existsSync(getXdgAutostartFilePath())) return false;

    const content = runtimeFs.readFileSync(getXdgAutostartFilePath(), 'utf8');
    const hidden = content.match(/^Hidden\s*=\s*(.+)$/im)?.[1]?.trim().toLowerCase();
    if (hidden === 'true') return false;

    const gnomeEnabled = content.match(/^X-GNOME-Autostart-enabled\s*=\s*(.+)$/im)?.[1]?.trim().toLowerCase();
    if (gnomeEnabled === 'false') return false;

    return true;
  }

  function readXdgAutostartExecPath() {
    if (typeof runtimeFs.readFileSync !== 'function') return null;
    try {
      const content = runtimeFs.readFileSync(getXdgAutostartFilePath(), 'utf8');
      const match = content.match(/^Exec=(.+)$/m);
      if (!match) return null;
      const rawExec = match[1].trim();
      if (!rawExec) return null;
      const unquotedExec = rawExec.replace(/^"(.*)"$/, '$1');
      // Single-pass char-unescape (\\ \" \$ \`), then field-code unescape (%% → %).
      return unquotedExec.replace(/\\(["$`\\])/g, '$1').replace(/%%/g, '%') || null;
    } catch (error) {
      writeLog('autostart - 读取 XDG autostart Exec 路径失败:', error.message);
      return null;
    }
  }

  function writeXdgAutostartFile(execPath) {
    const dir = getXdgAutostartDir();
    runtimeFs.mkdirSync(dir, { recursive: true });
    runtimeFs.writeFileSync(getXdgAutostartFilePath(), buildXdgDesktopFileContents(execPath), 'utf8');
  }

  function removeXdgAutostartFile() {
    const filePath = getXdgAutostartFilePath();
    try {
      if (runtimeFs.existsSync(filePath)) {
        runtimeFs.unlinkSync(filePath);
      }
    } catch (error) {
      if (error && error.code === 'ENOENT') {
        return;
      }
      throw error;
    }
  }

  function buildStatus(overrides = {}) {
    return {
      ok: true,
      supported: isSupported(),
      enabled: false,
      authoritative: true,
      provider: PROVIDER_NAME,
      mechanism: getMechanism(),
      platform: getPlatformName(runtimePlatform),
      ...overrides,
    };
  }

  function buildUnsupportedStatus(overrides = {}) {
    const unsupportedErrorCode = getUnsupportedErrorCode();
    return buildStatus({
      supported: false,
      enabled: false,
      authoritative: true,
      current_executable_path: getExecutablePath(),
      requires_packaged_app: unsupportedErrorCode === PACKAGED_APP_REQUIRED_ERROR,
      ...overrides,
    });
  }

  function getSystemApprovalStatus(settings) {
    if (!settings || typeof settings.status !== 'string') {
      return '';
    }
    return settings.status;
  }

  function isApprovalRequired(systemStatus) {
    return runtimePlatform === 'darwin' && systemStatus === 'requires-approval';
  }

  function isServiceNotFound(systemStatus) {
    return runtimePlatform === 'darwin' && systemStatus === 'not-found';
  }

  function readSystemStatus() {
    if (!isSupported()) {
      return buildUnsupportedStatus();
    }

    if (isLinuxRuntime()) {
      try {
        const currentExePath = getExecutablePath();
        const enabled = readXdgAutostartEnabled();
        const registeredExePath = enabled ? readXdgAutostartExecPath() : '';
        return buildStatus({
          enabled,
          current_executable_path: currentExePath,
          registered_executable_path: registeredExePath ?? '',
          registration_invalid: registeredExePath === null,
          path_matches_current_executable: registeredExePath === null
            ? false
            : (!registeredExePath || registeredExePath === currentExePath),
          requires_approval: false,
          service_not_found: false,
        });
      } catch (error) {
        writeLog('autostart - 读取 XDG autostart 状态失败:', error.message);
        return buildStatus({
          ok: false,
          enabled: getConfiguredEnabled(),
          authoritative: false,
          error: error.message,
          error_code: 'autostart_status_unavailable',
          current_executable_path: getExecutablePath(),
        });
      }
    }

    try {
      const settings = app.getLoginItemSettings() || {};
      const currentExePath = getExecutablePath();
      const systemStatus = getSystemApprovalStatus(settings);
      const requiresApproval = isApprovalRequired(systemStatus);
      const serviceNotFound = isServiceNotFound(systemStatus);
      const enabled = runtimePlatform === 'darwin'
        ? (systemStatus ? systemStatus === 'enabled' : !!settings.openAtLogin)
        : !!settings.openAtLogin;
      const registeredExePath = typeof settings.executableWillLaunchAtLogin === 'string'
        ? settings.executableWillLaunchAtLogin
        : '';

      return buildStatus({
        enabled,
        current_executable_path: currentExePath,
        registered_executable_path: registeredExePath,
        path_matches_current_executable: !registeredExePath || registeredExePath === currentExePath,
        requires_approval: requiresApproval,
        service_not_found: serviceNotFound,
        system_status: systemStatus || undefined,
      });
    } catch (error) {
      writeLog('autostart - 读取系统状态失败:', error.message);
      return buildStatus({
        ok: false,
        enabled: getConfiguredEnabled(),
        authoritative: false,
        error: error.message,
        error_code: 'autostart_status_unavailable',
        current_executable_path: getExecutablePath(),
      });
    }
  }

  function clearConfiguredEnabledIfNeeded() {
    if (getConfiguredEnabled()) {
      saveConfiguredEnabled(false);
    }
  }

  function clearDevelopmentRegistrationIfNeeded() {
    if (getUnsupportedErrorCode() !== PACKAGED_APP_REQUIRED_ERROR) {
      return readSystemStatus();
    }

    try {
      if (isLinuxRuntime()) {
        const currentExePath = getExecutablePath();
        let registeredExePath = '';
        if (readXdgAutostartEnabled()) {
          registeredExePath = currentExePath;
          writeLog(
            'autostart - 检测到开发环境误注册的 XDG autostart 文件，准备清理:',
            getXdgAutostartFilePath()
          );
          removeXdgAutostartFile();
        }

        clearConfiguredEnabledIfNeeded();

        return buildUnsupportedStatus({
          current_executable_path: currentExePath,
          registered_executable_path: registeredExePath,
          path_matches_current_executable: true,
        });
      }

      const settings = hasLoginItemApi() ? (app.getLoginItemSettings() || {}) : {};
      const currentExePath = getExecutablePath();
      const registeredExePath = typeof settings.executableWillLaunchAtLogin === 'string'
        ? settings.executableWillLaunchAtLogin
        : '';

      if (settings.openAtLogin) {
        writeLog(
          'autostart - 检测到开发环境误注册的登录项，准备清理:',
          registeredExePath || currentExePath
        );
        app.setLoginItemSettings({ openAtLogin: false });
      }

      clearConfiguredEnabledIfNeeded();

      return buildUnsupportedStatus({
        current_executable_path: currentExePath,
        registered_executable_path: registeredExePath,
        path_matches_current_executable: !registeredExePath || registeredExePath === currentExePath,
      });
    } catch (error) {
      writeLog('autostart - 清理开发环境登录项失败:', error.message);
      return buildUnsupportedStatus({
        ok: false,
        authoritative: false,
        enabled: getConfiguredEnabled(),
        error: error.message,
        error_code: 'autostart_dev_cleanup_failed',
      });
    }
  }

  function setSystemEnabled(enabled, { path: executablePath } = {}) {
    if (isLinuxRuntime()) {
      if (!enabled) {
        removeXdgAutostartFile();
        writeLog('autostart - 已移除 XDG autostart 文件');
        return;
      }
      const exePath = executablePath || getExecutablePath();
      if (!exePath) {
        throw new Error('current_executable_path_unavailable');
      }
      writeXdgAutostartFile(exePath);
      writeLog('autostart - 已写入 XDG autostart 文件, exePath:', exePath);
      return;
    }

    if (!enabled) {
      app.setLoginItemSettings({ openAtLogin: false });
      writeLog('autostart - 已请求关闭开机自启动');
      return;
    }

    const exePath = executablePath || getExecutablePath();
    if (!exePath) {
      throw new Error('current_executable_path_unavailable');
    }

    app.setLoginItemSettings({ openAtLogin: true, path: exePath });
    writeLog('autostart - 已请求开启开机自启动, exePath:', exePath);
  }

  function rewriteSystemRegistration(executablePath) {
    setSystemEnabled(false);
    setSystemEnabled(true, { path: executablePath });
  }

  function isRegistrationBlocked(status) {
    return !!(
      status
      && (
        status.requires_approval === true
        || status.service_not_found === true
      )
    );
  }

  function shouldKeepSystemRegistration(status) {
    return !!(
      status
      && (
        status.enabled === true
        || isRegistrationBlocked(status)
      )
    );
  }

  function hasPathMismatch(status) {
    return !!(
      status
      && status.supported
      && shouldKeepSystemRegistration(status)
      && status.current_executable_path
      && (
        status.registration_invalid === true
        || (
          status.registered_executable_path
          && status.registered_executable_path !== status.current_executable_path
        )
      )
    );
  }

  function isRepairOutcomeAcceptable(status) {
    return !!(
      status
      && status.path_matches_current_executable === true
      && shouldKeepSystemRegistration(status)
    );
  }

  function buildSystemStateSnapshot(status) {
    return {
      shouldRestoreRegistration: shouldKeepSystemRegistration(status),
      executablePath: status?.registered_executable_path || status?.current_executable_path || getExecutablePath(),
    };
  }

  function getOperationFailureMessage(failure, fallbackMessage = 'autostart_status_unavailable') {
    if (!failure || typeof failure !== 'object') {
      return fallbackMessage;
    }
    return failure.message || failure.error || fallbackMessage;
  }

  function getOperationFailureCode(failure, fallbackCode = 'autostart_status_unavailable') {
    if (!failure || typeof failure !== 'object') {
      return fallbackCode;
    }
    return failure.code || failure.error_code || fallbackCode;
  }

  function buildOperationFailureStatus(failure, overrides = {}) {
    const failureStatus = failure && typeof failure === 'object' ? failure : {};
    return {
      ...failureStatus,
      ok: false,
      error: getOperationFailureMessage(failure),
      error_code: getOperationFailureCode(failure),
      ...overrides,
    };
  }

  function rollbackSystemState(snapshot) {
    if (!snapshot || !snapshot.shouldRestoreRegistration) {
      setSystemEnabled(false);
      return readSystemStatus();
    }

    setSystemEnabled(true, {
      path: snapshot.executablePath,
    });
    return readSystemStatus();
  }

  function buildRollbackFailureStatus(previousStatus, failure, rollbackLogMessage) {
    writeLog(rollbackLogMessage, getOperationFailureMessage(failure));

    try {
      const rolledBackStatus = rollbackSystemState(buildSystemStateSnapshot(previousStatus));
      return {
        ...rolledBackStatus,
        ok: false,
        error: getOperationFailureMessage(failure),
        error_code: getOperationFailureCode(failure),
      };
    } catch (rollbackError) {
      writeLog('autostart - 回滚系统登录项失败:', rollbackError.message);
      return buildStatus({
        ok: false,
        enabled: !!previousStatus?.enabled,
        authoritative: false,
        error: getOperationFailureMessage(failure),
        error_code: getOperationFailureCode(failure),
        rollback_error: rollbackError.message,
        rollback_error_code: 'autostart_system_rollback_failed',
        current_executable_path: getExecutablePath(),
      });
    }
  }

  function commitConfiguredEnabled(enabled) {
    const previousStatus = readSystemStatus();
    if (!previousStatus.authoritative) {
      writeLog('autostart - 切换前系统状态不可确认，拒绝执行变更');
      return buildOperationFailureStatus(previousStatus);
    }

    setSystemEnabled(enabled);
    const status = readSystemStatus();
    if (!status.authoritative) {
      return buildRollbackFailureStatus(
        previousStatus,
        status,
        'autostart - 切换后系统状态不可确认，准备回滚系统登录项:'
      );
    }

    if (enabled) {
      if (status.requires_approval === true) {
        writeLog('autostart - 系统要求用户批准登录项后才能生效');
        return {
          ...status,
          ok: false,
          error: REQUIRES_APPROVAL_ERROR,
          error_code: REQUIRES_APPROVAL_ERROR,
        };
      }
      if (status.service_not_found === true) {
        writeLog('autostart - 系统未识别当前应用为可用登录项 service');
        return {
          ...status,
          ok: false,
          error: SERVICE_NOT_FOUND_ERROR,
          error_code: SERVICE_NOT_FOUND_ERROR,
        };
      }
      if (status.enabled !== true) {
        return {
          ...status,
          ok: false,
          error: status.error || 'autostart_enable_failed',
          error_code: status.error_code || 'autostart_enable_failed',
        };
      }
    } else if (status.enabled !== false) {
      return {
        ...status,
        ok: false,
        error: status.error || 'autostart_disable_failed',
        error_code: status.error_code || 'autostart_disable_failed',
      };
    }

    try {
      saveConfiguredEnabled(enabled);
    } catch (persistError) {
      return buildRollbackFailureStatus(
        previousStatus,
        persistError,
        'autostart - 配置写盘失败，准备回滚系统登录项:'
      );
    }

    return status;
  }

  function enable() {
    const unsupportedErrorCode = getUnsupportedErrorCode();
    if (unsupportedErrorCode !== null) {
      return buildUnsupportedStatus({
        ok: false,
        error: unsupportedErrorCode,
        error_code: unsupportedErrorCode,
      });
    }

    try {
      return commitConfiguredEnabled(true);
    } catch (error) {
      writeLog('autostart - 开启失败:', error.message);
      return buildStatus({
        ok: false,
        enabled: getConfiguredEnabled(),
        authoritative: false,
        error: error.message,
        error_code: 'autostart_enable_failed',
        current_executable_path: getExecutablePath(),
      });
    }
  }

  function disable() {
    const unsupportedErrorCode = getUnsupportedErrorCode();
    if (unsupportedErrorCode !== null) {
      return buildUnsupportedStatus({
        ok: false,
        error: unsupportedErrorCode,
        error_code: unsupportedErrorCode,
      });
    }

    try {
      return commitConfiguredEnabled(false);
    } catch (error) {
      writeLog('autostart - 关闭失败:', error.message);
      return buildStatus({
        ok: false,
        enabled: getConfiguredEnabled(),
        authoritative: false,
        error: error.message,
        error_code: 'autostart_disable_failed',
        current_executable_path: getExecutablePath(),
      });
    }
  }

  function repairIfNeeded(status) {
    if (!hasPathMismatch(status)) {
      return status;
    }

    const previousStatus = status;
    writeLog(
      'autostart - 检测到路径不匹配，准备修复:',
      status.registered_executable_path,
      '=>',
      status.current_executable_path
    );

    try {
      rewriteSystemRegistration(status.current_executable_path);
    } catch (error) {
      return buildRollbackFailureStatus(
        previousStatus,
        {
          message: error.message,
          code: 'autostart_repair_failed',
        },
        'autostart - 修复路径失败，准备回滚系统登录项:'
      );
    }

    const repairedStatus = readSystemStatus();
    if (!repairedStatus.authoritative) {
      return buildRollbackFailureStatus(
        previousStatus,
        repairedStatus,
        'autostart - 修复路径后系统状态不可确认，准备回滚系统登录项:'
      );
    }

    if (!isRepairOutcomeAcceptable(repairedStatus)) {
      return buildRollbackFailureStatus(
        previousStatus,
        {
          ...repairedStatus,
          error: repairedStatus.error || 'autostart_repair_failed',
          error_code: repairedStatus.error_code || 'autostart_repair_failed',
        },
        'autostart - 修复路径后系统状态不符合预期，准备回滚系统登录项:'
      );
    }

    if (repairedStatus.enabled === true) {
      try {
        saveConfiguredEnabled(true);
      } catch (persistError) {
        return buildRollbackFailureStatus(
          previousStatus,
          persistError,
          'autostart - 修复路径后配置写盘失败，准备回滚系统登录项:'
        );
      }
    }

    return repairedStatus;
  }

  function reconcile() {
    if (getUnsupportedErrorCode() === PACKAGED_APP_REQUIRED_ERROR) {
      return clearDevelopmentRegistrationIfNeeded();
    }

    let status = readSystemStatus();
    if (!status.authoritative || !status.supported) {
      return status;
    }

    status = repairIfNeeded(status);
    if (!status.ok) {
      return status;
    }

    const configuredEnabled = getConfiguredEnabled();
    if (shouldKeepSystemRegistration(status)) {
      if (!configuredEnabled) {
        if (status.enabled !== true) {
          return status;
        }
        try {
          saveConfiguredEnabled(true);
        } catch (error) {
          return {
            ...status,
            ok: false,
            error: error.message,
            error_code: error.code || CONFIG_SYNC_FAILED_ERROR,
          };
        }
      }
      return status;
    }

    if (configuredEnabled) {
      writeLog('autostart - 配置要求开启，但系统当前未启用，尝试恢复');
      return enable();
    }

    return status;
  }

  return {
    getStatus: readSystemStatus,
    enable,
    disable,
    reconcile,
  };
}

module.exports = {
  createAutostartService,
};
