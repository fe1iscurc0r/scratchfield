'use strict';

function buildWin32CursorHelperScript() {
  return `
$source = @'
using System;
using System.Runtime.InteropServices;

namespace NekoNative {
  public static class CursorApi {
    [DllImport("user32.dll", SetLastError = true)]
    public static extern IntPtr CreateCursor(
      IntPtr hInst,
      int xHotSpot,
      int yHotSpot,
      int nWidth,
      int nHeight,
      byte[] pvANDPlane,
      byte[] pvXORPlane
    );

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SetSystemCursor(IntPtr hcur, uint id);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SystemParametersInfo(uint uiAction, uint uiParam, IntPtr pvParam, uint fWinIni);
  }
}
'@
Add-Type -TypeDefinition $source

$SPI_SETCURSORS = 0x0057
$cursorIds = @(32512, 32513, 32514, 32515, 32516, 32640, 32641, 32642, 32643, 32644, 32645, 32646, 32648, 32649, 32650, 32651, 32671, 32672)

function New-TransparentCursor {
  $andMask = New-Object byte[] 128
  $xorMask = New-Object byte[] 128
  for ($i = 0; $i -lt $andMask.Length; $i++) {
    $andMask[$i] = 0xFF
  }
  return [NekoNative.CursorApi]::CreateCursor([IntPtr]::Zero, 0, 0, 32, 32, $andMask, $xorMask)
}

function Hide-SystemCursor {
  foreach ($cursorId in $cursorIds) {
    $cursor = New-TransparentCursor
    if ($cursor -ne [IntPtr]::Zero) {
      [NekoNative.CursorApi]::SetSystemCursor($cursor, [uint32]$cursorId) | Out-Null
    }
  }
}

function Restore-SystemCursor {
  [NekoNative.CursorApi]::SystemParametersInfo([uint32]$SPI_SETCURSORS, 0, [IntPtr]::Zero, 0) | Out-Null
}

try {
  Hide-SystemCursor
  while (($line = [Console]::In.ReadLine()) -ne $null) {
    if ($line -eq 'restore') { break }
    Start-Sleep -Milliseconds 100
  }
} finally {
  Restore-SystemCursor
}
`;
}

function buildDarwinCursorHelperScript() {
  return `
ObjC.import('CoreGraphics');
ObjC.import('Foundation');

const display = $.CGMainDisplayID();
const hidden = $.CGDisplayHideCursor(display) === 0;
console.log('hidden=' + hidden + ';display=' + display);
if (!hidden) {
  throw new Error('CGDisplayHideCursor failed display=' + display);
}

try {
  const _stdinData = $.NSFileHandle.fileHandleWithStandardInput.readDataToEndOfFile();
} finally {
  $.CGDisplayShowCursor(display);
}
`;
}

function createSystemCursorVisibilityService(options = {}) {
  const platform = options.platform || process.platform;
  const spawn = options.spawn;
  const log = typeof options.log === 'function' ? options.log : () => {};
  const app = options.app || null;
  const shouldDeferRestore = typeof options.shouldDeferRestore === 'function'
    ? options.shouldDeferRestore
    : () => false;
  const deferredRestoreRetryMs = Number.isFinite(Number(options.deferredRestoreRetryMs))
    ? Math.max(1, Number(options.deferredRestoreRetryMs))
    : 120;
  let helperProcess = null;
  let restoringHelperProcess = null;
  let helperHideConfirmed = false;
  let pendingHideReason = '';
  let hiddenRequested = false;
  let deferredRestoreTimer = null;

  function logFailure(prefix, error) {
    const message = error && error.message ? error.message : String(error);
    try {
      log(`[SystemCursor] ${prefix}: ${message}`);
    } catch (_) {}
  }

  function clearDeferredRestoreTimer() {
    if (!deferredRestoreTimer) return;
    clearTimeout(deferredRestoreTimer);
    deferredRestoreTimer = null;
  }

  function shouldDeferHelperRestore(reason) {
    if (platform !== 'win32') return false;
    if (reason === 'app-before-quit' || reason === 'app-will-quit') return false;
    try {
      return !!shouldDeferRestore();
    } catch (error) {
      logFailure(`restore defer check failed (${reason || 'restore'})`, error);
      return false;
    }
  }

  function scheduleDeferredRestore(reason) {
    if (deferredRestoreTimer) return;
    deferredRestoreTimer = setTimeout(() => {
      deferredRestoreTimer = null;
      if (hiddenRequested) return;
      closeHelperProcess(reason || 'deferred-restore');
    }, deferredRestoreRetryMs);
    try {
      if (typeof deferredRestoreTimer.unref === 'function') deferredRestoreTimer.unref();
    } catch (_) {}
  }

  function closeHelperProcess(reason) {
    const child = helperProcess;
    if (!child) return;
    if (restoringHelperProcess === child) return;
    if (shouldDeferHelperRestore(reason)) {
      scheduleDeferredRestore(reason);
      return;
    }
    clearDeferredRestoreTimer();
    restoringHelperProcess = child;

    try {
      if (child.stdin && !child.stdin.destroyed && !child.stdin.writableEnded) {
        if (platform === 'win32' && typeof child.stdin.write === 'function') child.stdin.write('restore\n');
        if (typeof child.stdin.end === 'function') child.stdin.end();
      }
    } catch (error) {
      logFailure(`restore stdin failed (${reason || 'restore'})`, error);
      try {
        if (typeof child.kill === 'function') child.kill();
      } catch (_) {}
    }
  }

  function show(reason) {
    hiddenRequested = false;
    pendingHideReason = '';
    try {
      log(`[SystemCursor] restore requested reason=${reason || 'show'}`);
    } catch (_) {}
    closeHelperProcess(reason || 'show');
    return { ok: true, active: false };
  }

  function startPlatformHelper(reason) {
    if (platform === 'win32') {
      const encodedScript = Buffer.from(buildWin32CursorHelperScript(), 'utf16le').toString('base64');
      return startHelper('powershell.exe', [
        '-NoProfile',
        '-NonInteractive',
        '-ExecutionPolicy',
        'Bypass',
        '-EncodedCommand',
        encodedScript,
      ], {
        windowsHide: true,
        stdio: ['pipe', 'ignore', 'ignore'],
      }, reason);
    }

    if (platform === 'darwin') {
      return startHelper('osascript', ['-l', 'JavaScript', '-e', buildDarwinCursorHelperScript()], {
        stdio: ['pipe', 'pipe', 'pipe'],
      }, reason);
    }

    hiddenRequested = false;
    return { ok: false, unsupported: true, active: false };
  }

  function startHelper(command, args, spawnOptions, reason) {
    try {
      const child = spawn(command, args, spawnOptions);
      helperProcess = child;
      restoringHelperProcess = null;
      helperHideConfirmed = platform !== 'darwin';
      hiddenRequested = helperHideConfirmed;
      try {
        log(`[SystemCursor] helper started platform=${platform} command=${command} reason=${reason || 'hide'}`);
      } catch (_) {}

      if (child && typeof child.once === 'function') {
        child.once('exit', () => {
          try {
            log(`[SystemCursor] helper exited platform=${platform}`);
          } catch (_) {}
          clearDeferredRestoreTimer();
          const shouldStartPending = hiddenRequested && pendingHideReason && restoringHelperProcess === child;
          if (helperProcess === child) helperProcess = null;
          if (restoringHelperProcess === child) restoringHelperProcess = null;
          helperHideConfirmed = false;
          if (shouldStartPending) {
            const nextReason = pendingHideReason;
            pendingHideReason = '';
            startPlatformHelper(nextReason);
          } else if (!pendingHideReason) {
            hiddenRequested = false;
          }
        });
      }
      if (child && typeof child.on === 'function') {
        child.on('error', (error) => {
          logFailure(`helper error (${reason || 'hide'})`, error);
          clearDeferredRestoreTimer();
          if (helperProcess === child) helperProcess = null;
          if (restoringHelperProcess === child) restoringHelperProcess = null;
          helperHideConfirmed = false;
          hiddenRequested = false;
          pendingHideReason = '';
        });
      }
      const logHelperOutput = (streamName, chunk) => {
        const line = String(chunk || '').trim();
        if (!line) return;
        try {
          log(`[SystemCursor] helper ${streamName}: ${line}`);
        } catch (_) {}
        if (platform === 'darwin' && streamName === 'stdout' && /(?:^|;)hidden=true(?:;|$)/.test(line)) {
          helperHideConfirmed = true;
          if (restoringHelperProcess !== child) {
            hiddenRequested = true;
          }
        }
        if (platform === 'darwin' && streamName === 'stdout' && /(?:^|;)hidden=false(?:;|$)/.test(line)) {
          helperHideConfirmed = false;
          hiddenRequested = false;
          pendingHideReason = '';
          if (helperProcess === child) helperProcess = null;
          if (restoringHelperProcess === child) restoringHelperProcess = null;
          try {
            if (typeof child.kill === 'function') child.kill();
          } catch (_) {}
        }
      };
      if (child && child.stdout && typeof child.stdout.on === 'function') {
        child.stdout.on('data', chunk => logHelperOutput('stdout', chunk));
      }
      if (child && child.stderr && typeof child.stderr.on === 'function') {
        child.stderr.on('data', chunk => logHelperOutput('stderr', chunk));
      }

      return platform === 'darwin'
        ? { ok: true, active: false, pending: true }
        : { ok: true, active: true };
    } catch (error) {
      hiddenRequested = false;
      helperProcess = null;
      logFailure(`hide failed (${reason || 'hide'})`, error);
      return { ok: false, active: false, error: error && error.message ? error.message : String(error) };
    }
  }

  function hide(reason) {
    if (helperProcess) {
      if (restoringHelperProcess === helperProcess) {
        hiddenRequested = true;
        pendingHideReason = reason || 'hide';
        return { ok: true, active: true, queued: true };
      }
      if (platform === 'darwin' && !helperHideConfirmed) {
        return { ok: true, active: false, pending: true };
      }
      hiddenRequested = true;
      return { ok: true, active: true, alreadyActive: true };
    }
    if (typeof spawn !== 'function') {
      return { ok: false, active: false, error: 'spawn unavailable' };
    }

    return startPlatformHelper(reason);
  }

  function setHidden(hidden, reason) {
    return hidden ? hide(reason) : show(reason);
  }

  if (app && typeof app.on === 'function') {
    app.on('before-quit', () => {
      show('app-before-quit');
    });
    app.on('will-quit', () => {
      show('app-will-quit');
    });
  }

  return {
    setHidden,
    restore: show,
    isHiddenRequested() {
      return hiddenRequested;
    },
  };
}

module.exports = {
  buildDarwinCursorHelperScript,
  createSystemCursorVisibilityService,
};
