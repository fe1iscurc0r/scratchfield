'use strict';

const { spawn, spawnSync } = require('node:child_process');

const MAX_RECTS = 64;

let helperProcess = null;
let helperStarting = false;
let helperReady = false;
let helperReadyWaiters = [];
let helperShapeSeq = 0;
let helperAckWaiters = new Map();
let helperPointerSeq = 0;
let helperPointerWaiters = new Map();
let helperUnavailableLogged = false;
let helperGeneration = 0;
let pointerProbeBackoffUntil = 0;
let xidFinderUnavailableLogged = false;
let cachedXidByWindowId = new Map();
let lastDebugHashByWindowId = new Map();
const POINTER_PROBE_HELPER_UNAVAILABLE_BACKOFF_MS = 5000;

function isHelperWritable(child) {
  return !!(child && child.stdin && !child.stdin.destroyed && child.exitCode === null && !child.killed);
}

function settleHelperReadyWaiters(value) {
  const waiters = helperReadyWaiters;
  helperReadyWaiters = [];
  for (const resolve of waiters) {
    try { resolve(value); } catch (_) {}
  }
}

function settleHelperAckWaiters(value) {
  const waiters = Array.from(helperAckWaiters.values());
  helperAckWaiters.clear();
  for (const finish of waiters) {
    try { finish(value); } catch (_) {}
  }
}

function settleHelperPointerWaiters(value) {
  const waiters = Array.from(helperPointerWaiters.values());
  helperPointerWaiters.clear();
  for (const finish of waiters) {
    try { finish(value); } catch (_) {}
  }
}

function waitForHelperReady(child, timeoutMs = 750) {
  if (helperReady && isHelperWritable(child)) return Promise.resolve(true);
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      const idx = helperReadyWaiters.indexOf(finish);
      if (idx !== -1) helperReadyWaiters.splice(idx, 1);
      resolve(value);
    };
    const timer = setTimeout(() => finish(false), timeoutMs);
    helperReadyWaiters.push(finish);
  });
}

function waitForShapeAck(seq, timeoutMs = 1000) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      helperAckWaiters.delete(seq);
      resolve(value);
    };
    const timer = setTimeout(() => finish(false), timeoutMs);
    helperAckWaiters.set(seq, finish);
  });
}

function waitForPointerQuery(seq, timeoutMs = 120) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      helperPointerWaiters.delete(seq);
      resolve(value);
    };
    const timer = setTimeout(() => finish(null), timeoutMs);
    helperPointerWaiters.set(seq, finish);
  });
}

function isX11InputShapeHelperReady() {
  return helperReady && isHelperWritable(helperProcess);
}

function isPointerProbeBackedOff() {
  return !isX11InputShapeHelperReady() && Date.now() < pointerProbeBackoffUntil;
}

function backOffPointerProbe() {
  if (isX11InputShapeHelperReady()) return;
  pointerProbeBackoffUntil = Date.now() + POINTER_PROBE_HELPER_UNAVAILABLE_BACKOFF_MS;
}

function clearPointerProbeBackoff() {
  pointerProbeBackoffUntil = 0;
}

function getLinuxPythonExecutable() {
  for (const candidate of ['python3', 'python']) {
    try {
      const result = spawnSync(candidate, ['--version'], { stdio: 'ignore', timeout: 1000 });
      if (result.status === 0) return candidate;
    } catch (_) {}
  }
  return '';
}

function getX11WindowId(win) {
  if (!win || win.isDestroyed()) return 0;

  try {
    const mediaSourceId = typeof win.getMediaSourceId === 'function' ? win.getMediaSourceId() : '';
    const match = /^window:(\d+):/.exec(String(mediaSourceId || ''));
    if (match) {
      const xid = Number(match[1]);
      if (Number.isFinite(xid) && xid > 0) return xid;
    }
  } catch (_) {}

  try {
    const handle = typeof win.getNativeWindowHandle === 'function' ? win.getNativeWindowHandle() : null;
    if (Buffer.isBuffer(handle)) {
      if (handle.length >= 8 && typeof handle.readBigUInt64LE === 'function') {
        const value = Number(handle.readBigUInt64LE(0));
        if (Number.isFinite(value) && value > 0) return value;
      }
      if (handle.length >= 4) {
        const value = handle.readUInt32LE(0);
        if (Number.isFinite(value) && value > 0) return value;
      }
    }
  } catch (_) {}

  return 0;
}

function parseXWindowIdFromText(text, title, pid) {
  const lines = String(text || '').split(/\r?\n/);
  const escapedTitle = String(title || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const titlePattern = escapedTitle ? new RegExp('^(\\s*)(0x[0-9a-fA-F]+)\\s+"' + escapedTitle + '"') : null;
  const fallbackPattern = /^(\s*)(0x[0-9a-fA-F]+)\s/;
  const candidates = [];

  for (const line of lines) {
    const match = titlePattern ? line.match(titlePattern) : line.match(fallbackPattern);
    if (!match) continue;
    candidates.push({
      xid: parseInt(match[2], 16),
      depth: match[1].length,
      line,
    });
  }

  if (candidates.length === 0) return 0;
  if (!pid) {
    return candidates.sort((a, b) => a.depth - b.depth)[0].xid || 0;
  }

  for (const candidate of candidates.sort((a, b) => a.depth - b.depth)) {
    try {
      const prop = spawnSync('xprop', ['-id', `0x${candidate.xid.toString(16)}`, '_NET_WM_PID'], {
        encoding: 'utf8',
        stdio: ['ignore', 'pipe', 'ignore'],
        timeout: 1000,
      });
      if (prop.status === 0 && new RegExp(`=\\s*${pid}\\s*$`).test(String(prop.stdout || '').trim())) {
        return candidate.xid;
      }
    } catch (_) {}
  }

  return candidates.sort((a, b) => a.depth - b.depth)[0].xid || 0;
}

function findX11WindowIdByTitle(win, log) {
  if (!win || win.isDestroyed() || !process.env.DISPLAY) return 0;
  let title = '';
  try { title = win.getTitle(); } catch (_) {}
  if (!title) return 0;

  try {
    const result = spawnSync('xwininfo', ['-root', '-tree'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
      timeout: 1500,
    });
    if (result.status !== 0) return 0;
    const xid = parseXWindowIdFromText(result.stdout, title, process.pid);
    if (xid) return xid;
  } catch (error) {
    if (!xidFinderUnavailableLogged) {
      xidFinderUnavailableLogged = true;
      log('[x11-input-shape] xwininfo lookup failed:', error.message || error);
    }
  }

  return 0;
}

function getCachedX11WindowId(win, log, options = {}) {
  if (!win || win.isDestroyed()) return 0;
  const cached = cachedXidByWindowId.get(win.id);
  if (cached) return cached;

  const titleXid = findX11WindowIdByTitle(win, log);
  if (titleXid) {
    cachedXidByWindowId.set(win.id, titleXid);
    return titleXid;
  }

  // The native handle can be an internal/transient Xwayland child before the
  // top-level WM window is fully named. Use it as a short-lived fallback only;
  // do not cache it or a later lookup can keep writing ShapeInput to BadWindow.
  if (options.allowNativeFallback === false) return 0;
  return getX11WindowId(win);
}

function clearCachedX11WindowId(win) {
  if (!win) return;
  cachedXidByWindowId.delete(win.id);
  lastDebugHashByWindowId.delete(win.id);
}

function getHelperScript() {
  return [
    'import ctypes, json, os, sys, traceback',
    'display_name = os.environ.get("DISPLAY")',
    'if not display_name:',
    '    print("missing DISPLAY", file=sys.stderr, flush=True)',
    '    sys.exit(2)',
    'class XRectangle(ctypes.Structure):',
    '    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short), ("width", ctypes.c_ushort), ("height", ctypes.c_ushort)]',
    'x11 = ctypes.CDLL("libX11.so.6")',
    'xext = ctypes.CDLL("libXext.so.6")',
    'x11.XOpenDisplay.argtypes = [ctypes.c_char_p]',
    'x11.XOpenDisplay.restype = ctypes.c_void_p',
    'x11.XFlush.argtypes = [ctypes.c_void_p]',
    'x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]',
    'x11.XCloseDisplay.argtypes = [ctypes.c_void_p]',
    'x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]',
    'x11.XDefaultRootWindow.restype = ctypes.c_ulong',
    'x11.XQueryPointer.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint)]',
    'x11.XQueryPointer.restype = ctypes.c_int',
    'xext.XShapeQueryExtension.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]',
    'xext.XShapeQueryExtension.restype = ctypes.c_int',
    'xext.XShapeCombineRectangles.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(XRectangle), ctypes.c_int, ctypes.c_int, ctypes.c_int]',
    'xext.XShapeCombineRectangles.restype = None',
    'display = x11.XOpenDisplay(display_name.encode())',
    'if not display:',
    '    print("cannot open display", file=sys.stderr, flush=True)',
    '    sys.exit(3)',
    'event_base = ctypes.c_int()',
    'error_base = ctypes.c_int()',
    'if not xext.XShapeQueryExtension(display, ctypes.byref(event_base), ctypes.byref(error_base)):',
    '    print("X SHAPE extension unavailable", file=sys.stderr, flush=True)',
    '    x11.XCloseDisplay(display)',
    '    sys.exit(4)',
    'ShapeBounding = 0',
    'ShapeInput = 2',
    'ShapeSet = 0',
    'Unsorted = 0',
    'root_window = x11.XDefaultRootWindow(display)',
    'def make_rect_array(rects):',
    '    safe = []',
    '    for r in rects[:64]:',
    '        x = max(-32768, min(32767, int(r.get("x", 0))))',
    '        y = max(-32768, min(32767, int(r.get("y", 0))))',
    '        w = max(1, min(65535, int(r.get("width", 1))))',
    '        h = max(1, min(65535, int(r.get("height", 1))))',
    '        safe.append((x, y, w, h))',
    '    count = len(safe)',
    '    if not count:',
    '        return None, 0',
    '    arr = (XRectangle * count)()',
    '    for i, (x, y, w, h) in enumerate(safe):',
    '        arr[i].x = x',
    '        arr[i].y = y',
    '        arr[i].width = w',
    '        arr[i].height = h',
    '    return arr, count',
    'def apply_shape(xid, shape_kind, rects):',
    '    ptr, count = make_rect_array(rects or [])',
    '    xext.XShapeCombineRectangles(display, ctypes.c_ulong(xid), shape_kind, 0, 0, ptr, count, ShapeSet, Unsorted)',
    'def query_pointer():',
    '    root_return = ctypes.c_ulong()',
    '    child_return = ctypes.c_ulong()',
    '    root_x = ctypes.c_int()',
    '    root_y = ctypes.c_int()',
    '    win_x = ctypes.c_int()',
    '    win_y = ctypes.c_int()',
    '    mask = ctypes.c_uint()',
    '    ok = x11.XQueryPointer(display, root_window, ctypes.byref(root_return), ctypes.byref(child_return), ctypes.byref(root_x), ctypes.byref(root_y), ctypes.byref(win_x), ctypes.byref(win_y), ctypes.byref(mask))',
    '    if not ok:',
    '        return None',
    '    return int(mask.value), int(root_x.value), int(root_y.value)',
    'print("ready", flush=True)',
    'try:',
    '    for line in sys.stdin:',
    '        try:',
    '            payload = json.loads(line)',
    '            seq = payload.get("seq")',
    '            if payload.get("op") == "queryPointer":',
    '                pointer = query_pointer()',
    '                if seq is not None:',
    '                    if pointer is None:',
    '                        print("pointer " + str(seq) + " -1 0 0", flush=True)',
    '                    else:',
    '                        print("pointer " + str(seq) + " " + str(pointer[0]) + " " + str(pointer[1]) + " " + str(pointer[2]), flush=True)',
    '                continue',
    '            xid = int(payload.get("xid") or 0)',
    '            input_rects = payload.get("inputRects")',
    '            if input_rects is None:',
    '                input_rects = payload.get("rects") or []',
    '            bounding_rects = payload.get("boundingRects")',
    '            if xid <= 0:',
    '                continue',
    '            apply_shape(xid, ShapeInput, input_rects)',
    '            if bounding_rects is not None:',
    '                apply_shape(xid, ShapeBounding, bounding_rects)',
    '            x11.XSync(display, 0)',
    '            if seq is not None:',
    '                print("applied " + str(seq), flush=True)',
    '        except Exception:',
    '            traceback.print_exc(file=sys.stderr)',
    'finally:',
    '    x11.XCloseDisplay(display)',
  ].join('\n');
}

function startHelper(log) {
  if (helperProcess && !helperProcess.killed) return helperProcess;
  if (helperStarting) return null;

  const python = getLinuxPythonExecutable();
  if (!python) {
    if (!helperUnavailableLogged) {
      helperUnavailableLogged = true;
      log('[x11-input-shape] python3/python unavailable; falling back to Electron ignore mouse events');
    }
    return null;
  }

  try {
    helperStarting = true;
    helperReady = false;
    helperGeneration += 1;
    const generation = helperGeneration;
    const child = spawn(python, ['-u', '-c', getHelperScript()], {
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    helperProcess = child;

    const markHelperClosed = (error = null) => {
      if (generation !== helperGeneration) return;
      if (helperProcess === child) helperProcess = null;
      helperStarting = false;
      helperReady = false;
      settleHelperReadyWaiters(false);
      settleHelperAckWaiters(false);
      settleHelperPointerWaiters(null);
      if (error && !helperUnavailableLogged) {
        helperUnavailableLogged = true;
        log('[x11-input-shape] helper failed:', error.message || error);
      }
    };

    if (child.stdin) {
      child.stdin.on('error', (error) => {
        markHelperClosed(error);
      });
    }

    if (child.stdout) {
      let stdoutBuffer = '';
      child.stdout.setEncoding('utf8');
      child.stdout.on('data', (chunk) => {
        stdoutBuffer += String(chunk || '');
        const lines = stdoutBuffer.split(/\r?\n/);
        stdoutBuffer = lines.pop() || '';
        for (const text of lines) {
          const line = text.trim();
          if (!line) continue;
          if (line === 'ready') {
            if (generation === helperGeneration) {
              helperReady = true;
              settleHelperReadyWaiters(true);
            }
          } else if (/^applied\s+\d+$/.test(line)) {
            const seq = Number(line.split(/\s+/)[1]);
            const finish = helperAckWaiters.get(seq);
            if (finish) finish(true);
          } else if (/^pointer\s+\d+\s+-?\d+\s+-?\d+\s+-?\d+$/.test(line)) {
            const parts = line.split(/\s+/);
            const seq = Number(parts[1]);
            const finish = helperPointerWaiters.get(seq);
            if (finish) {
              finish({
                mask: Number(parts[2]),
                x: Number(parts[3]),
                y: Number(parts[4]),
              });
            }
          } else {
            log('[x11-input-shape]', line);
          }
        }
      });
    }

    if (child.stderr) {
      child.stderr.setEncoding('utf8');
      child.stderr.on('data', (chunk) => {
        const text = String(chunk || '').trim();
        if (text) log('[x11-input-shape] stderr:', text);
      });
    }

    child.on('error', (error) => {
      markHelperClosed(error);
    });

    child.on('close', (code) => {
      markHelperClosed();
      if (code !== 0 && !helperUnavailableLogged) {
        helperUnavailableLogged = true;
        log('[x11-input-shape] helper exited with code', code);
      }
    });

    try { child.unref(); } catch (_) {}
    helperStarting = false;
    return child;
  } catch (error) {
    helperProcess = null;
    helperStarting = false;
    helperReady = false;
    settleHelperReadyWaiters(false);
    settleHelperAckWaiters(false);
    settleHelperPointerWaiters(null);
    if (!helperUnavailableLogged) {
      helperUnavailableLogged = true;
      log('[x11-input-shape] helper start failed:', error.message || error);
    }
    return null;
  }
}

function scaleInputRegions(rects, scaleFactor) {
  const scale = Number.isFinite(scaleFactor) && scaleFactor > 0 ? scaleFactor : 1;
  if (!Array.isArray(rects)) return [];
  return rects
    .filter(r => r && Number.isFinite(r.x) && Number.isFinite(r.y)
      && Number.isFinite(r.width) && Number.isFinite(r.height)
      && r.width > 0 && r.height > 0)
    .slice(0, MAX_RECTS)
    .map((r) => {
      const x = Math.max(0, Math.floor(r.x * scale));
      const y = Math.max(0, Math.floor(r.y * scale));
      const right = Math.max(x + 1, Math.ceil((r.x + r.width) * scale));
      const bottom = Math.max(y + 1, Math.ceil((r.y + r.height) * scale));
      return {
        x,
        y,
        width: Math.max(1, right - x),
        height: Math.max(1, bottom - y),
      };
    });
}

function x11PointerMaskToButtons(mask) {
  const value = Number(mask) || 0;
  let buttons = 0;
  if (value & (1 << 8)) buttons |= 1;   // Button1Mask: primary
  if (value & (1 << 9)) buttons |= 4;   // Button2Mask: auxiliary/middle
  if (value & (1 << 10)) buttons |= 2;  // Button3Mask: secondary/right
  if (value & (1 << 11)) buttons |= 8;  // Button4Mask
  if (value & (1 << 12)) buttons |= 16; // Button5Mask
  return buttons;
}

async function queryX11PointerButtons(log = console.log, options = {}) {
  if (process.platform !== 'linux') return null;
  if (!process.env.DISPLAY) return null;
  if (isPointerProbeBackedOff()) return null;
  const child = startHelper(log);
  if (!isHelperWritable(child)) {
    if (!helperStarting) backOffPointerProbe();
    return null;
  }
  if (!await waitForHelperReady(child, options.readyTimeoutMs || 200)) {
    backOffPointerProbe();
    return null;
  }
  if (!isHelperWritable(child)) {
    backOffPointerProbe();
    return null;
  }

  const payload = {
    op: 'queryPointer',
    seq: ++helperPointerSeq,
  };

  try {
    const pointerPromise = waitForPointerQuery(payload.seq, options.timeoutMs || 120);
    const wrote = await new Promise((resolve) => {
      let settled = false;
      const settle = (ok, error = null) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        child.off('close', onClose);
        child.off('error', onError);
        if (child.stdin) child.stdin.off('error', onStdinError);
        if (!ok) {
          if (helperProcess === child) {
            helperProcess = null;
            helperReady = false;
            settleHelperReadyWaiters(false);
            settleHelperAckWaiters(false);
            settleHelperPointerWaiters(null);
          }
          if (error) log('[x11-input-shape] pointer query failed:', error.message || error);
        }
        resolve(ok);
      };
      const onClose = () => settle(false);
      const onError = (error) => settle(false, error);
      const onStdinError = (error) => settle(false, error);
      const timer = setTimeout(() => settle(false, new Error('pointer query timed out')), options.timeoutMs || 120);
      child.once('close', onClose);
      child.once('error', onError);
      if (child.stdin) child.stdin.once('error', onStdinError);
      try {
        child.stdin.write(JSON.stringify(payload) + '\n', (error) => {
          settle(!error, error);
        });
      } catch (error) {
        settle(false, error);
      }
    });
    if (!wrote) {
      backOffPointerProbe();
      return null;
    }
    const pointer = await pointerPromise;
    if (!pointer || !Number.isFinite(pointer.mask) || pointer.mask < 0) {
      backOffPointerProbe();
      return null;
    }
    clearPointerProbeBackoff();
    return {
      mask: pointer.mask,
      x: pointer.x,
      y: pointer.y,
      buttons: x11PointerMaskToButtons(pointer.mask),
    };
  } catch (error) {
    log('[x11-input-shape] pointer query failed:', error.message || error);
    backOffPointerProbe();
    return null;
  }
}

async function applyX11InputShape(win, rects, options = {}) {
  const {
    log = console.log,
    scaleFactor = 1,
    boundingRects = null,
    beforeWrite = null,
    allowNativeFallback = true,
  } = options;
  if (process.platform !== 'linux') return false;
  if (!process.env.DISPLAY) return false;
  if (!win || win.isDestroyed()) return false;

  // Electron's Linux native handle/media source id can refer to an internal
  // compositor/native widget window under XWayland. The SHAPE extension needs
  // the real top-level X11 window, so prefer the WM tree lookup and cache it.
  const xid = getCachedX11WindowId(win, log, { allowNativeFallback });
  if (!xid) {
    log('[x11-input-shape] unable to resolve X11 window id for winId', win.id);
    return false;
  }
  if (process.env.NEKO_DEBUG_LINUX_INPUT === '1') {
    try {
      const debugHash = [
        xid,
        Array.isArray(rects) ? rects.length : 0,
        Array.isArray(boundingRects) ? boundingRects.length : 'none',
        scaleFactor,
      ].join(':');
      if (lastDebugHashByWindowId.get(win.id) !== debugHash) {
        lastDebugHashByWindowId.set(win.id, debugHash);
        log('[x11-input-shape] apply', JSON.stringify({
          winId: win.id,
          title: win.getTitle(),
          xid: `0x${xid.toString(16)}`,
          rectCount: Array.isArray(rects) ? rects.length : 0,
          boundingRectCount: Array.isArray(boundingRects) ? boundingRects.length : null,
          scaleFactor,
        }));
      }
    } catch (_) {}
  }

  const child = startHelper(log);
  if (!isHelperWritable(child)) return false;
  if (!await waitForHelperReady(child)) return false;
  if (!isHelperWritable(child)) return false;
  if (!win || win.isDestroyed()) return false;

  const payload = {
    seq: ++helperShapeSeq,
    xid,
    inputRects: scaleInputRegions(rects, scaleFactor),
  };
  if (Array.isArray(boundingRects)) {
    payload.boundingRects = scaleInputRegions(boundingRects, scaleFactor);
  }

  try {
    if (typeof beforeWrite === 'function') {
      const shouldContinue = await beforeWrite();
      if (shouldContinue === false) return false;
    }
    if (!isHelperWritable(child)) return false;
    const ackPromise = waitForShapeAck(payload.seq);
    const wrote = await new Promise((resolve) => {
      let settled = false;
      const settle = (ok, error = null) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        child.off('close', onClose);
        child.off('error', onError);
        if (child.stdin) child.stdin.off('error', onStdinError);
        if (!ok) {
          if (helperProcess === child) {
            helperProcess = null;
            helperReady = false;
            settleHelperReadyWaiters(false);
            settleHelperAckWaiters(false);
            settleHelperPointerWaiters(null);
          }
          if (error) log('[x11-input-shape] write failed:', error.message || error);
        }
        resolve(ok);
      };
      const onClose = () => settle(false);
      const onError = (error) => settle(false, error);
      const onStdinError = (error) => settle(false, error);
      const timer = setTimeout(() => settle(false, new Error('write timed out')), 1000);
      child.once('close', onClose);
      child.once('error', onError);
      if (child.stdin) child.stdin.once('error', onStdinError);
      try {
        child.stdin.write(JSON.stringify(payload) + '\n', (error) => {
          settle(!error, error);
        });
      } catch (error) {
        settle(false, error);
      }
    });
    if (!wrote) {
      clearCachedX11WindowId(win);
      return false;
    }
    const ack = await ackPromise;
    if (!ack) clearCachedX11WindowId(win);
    return ack;
  } catch (error) {
    clearCachedX11WindowId(win);
    helperProcess = null;
    helperReady = false;
    settleHelperReadyWaiters(false);
    settleHelperAckWaiters(false);
    settleHelperPointerWaiters(null);
    log('[x11-input-shape] write failed:', error.message || error);
    return false;
  }
}

module.exports = {
  applyX11InputShape,
  getX11WindowId,
  isX11InputShapeHelperReady,
  queryX11PointerButtons,
  scaleInputRegions,
};
