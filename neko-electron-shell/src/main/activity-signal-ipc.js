/**
 * activity-signal-ipc.js — main-process side of the cross-platform
 * OS-activity signal bridge.
 *
 * Companion to `static/app-activity-signal.js` in the NEKO repo and
 * `POST /api/activity_signal` (`main_routers/system_router.py` in NEKO,
 * forwarding to `UserActivityTracker.push_external_system_signal` —
 * see PR #1015 and issue #1023).
 *
 * Why this lives in main rather than renderer:
 *   - `powerMonitor.getSystemIdleTime()` is a main-process Electron API.
 *   - `get-windows` (active-win successor) needs to shell out / call
 *     native bridges; doing it from renderer would either go through
 *     remote module (deprecated) or repeat the IPC machinery anyway.
 *   - `nvidia-smi` spawn from the renderer would also need IPC.
 *
 * Polling vs. on-demand: the handler returns a *cached* snapshot
 * that the main process refreshes on a 5s interval. Three reasons:
 *   1. nvidia-smi spawn can take 200–800ms cold; doing it in the
 *      handler stalls the renderer for that long.
 *   2. get-windows on Linux X11 calls xdotool — also potentially slow.
 *   3. The backend tracker has a 15s freshness TTL on each push; 0–5s
 *      sampling staleness is well inside that window.
 *
 * Returned snapshot shape (camelCase — renderer converts to snake_case
 * for the HTTP POST):
 *
 *   {
 *     windowTitle: string | null,
 *     processName: string | null,
 *     idleSeconds: number | null,   // [0, ∞), OS-wide kbd/mouse idle
 *     cpuAvg30s:   number | null,   // [0, 100], rolling 30s utilisation
 *     gpuUtilization: number | null // [0, 100], primary NVIDIA GPU
 *   }
 *
 * Any field that fails to read becomes `null`. The renderer client
 * (and the backend after that) treats `null` as "absent — leave the
 * tracker's current view alone for this field", so a partial snapshot
 * is still useful.
 */

// Composition contract: this factory must NOT require('electron') directly
// (tracked by test/main-composition-contract.test.js). Electron primitives
// come in through the ``context`` parameter of registerActivitySignalIpc.
const os = require('node:os');
const { spawn } = require('child_process');

// Tunables. Match `_EXTERNAL_SIGNAL_MIN_INTERVAL` in the NEKO repo's
// `main_logic/activity/tracker.py`: the heartbeat is 5s. cpu_avg_30s is
// a single first→last os.cpus() diff across the sample buffer, so the
// covered span is (CPU_SAMPLE_WINDOW - 1) × 5s — 7 points give a true
// 30s window (Codex P2 on PR #127: 6 points only spanned 25s, making
// the metric shorter than its `_30s` label). This is the CPU averaging
// window, NOT the backend's freshness TTL (a separate 15s knob in the
// same NEKO file).
const SAMPLE_INTERVAL_MS = 5000;
const CPU_SAMPLE_WINDOW = 7;
// GPU sampling throttle. nvidia-smi is the one expensive signal — a
// subprocess spawn (200–800ms cold), so polling it every 5s tick burns
// a process every 5s on machines that DO have an NVIDIA GPU (the
// ENOENT latch below only spares the no-GPU hosts). Poll it every Nth
// tick instead and carry the last value between polls. Mirrors the
// NEKO backend collector's `_GPU_POLL_EVERY_N_TICKS = 2` ("once every
// other tick is plenty for catching gaming sessions"). 2 × 5s = 10s.
// Window / idle / CPU keep the full 5s cadence.
const GPU_POLL_EVERY_N_TICKS = 2;
// Hard cap on nvidia-smi response wait. Cold first call can be slow
// on some setups; 1.5s is generous without blocking the sampler tick.
const NVIDIA_SMI_TIMEOUT_MS = 1500;
// Watchdog ceiling on a single guarded sample run. A healthy tick
// finishes in well under 2s (nvidia-smi is capped at
// NVIDIA_SMI_TIMEOUT_MS and runs at most every other tick), so 15s
// (3× the heartbeat) only trips when a read wedges with no timeout of
// its own — e.g. get-windows / xprop blocking indefinitely. Without
// it a single hung sample() would pin ``samplingInFlight`` true
// forever and silently kill the sampler, freezing every snapshot.
// (Codex P1 on PR #127.)
const SAMPLE_WATCHDOG_MS = 15000;

let latestSnapshot = {
    windowTitle: null,
    processName: null,
    idleSeconds: null,
    cpuAvg30s: null,
    gpuUtilization: null,
};

// Rolling CPU sample buffer. Each entry is the array returned by
// os.cpus(); we compute usage by diffing first/last total vs idle.
let cpuSamples = [];

// nvidia-smi availability gate. ``null`` = unprobed, ``false`` = ENOENT
// (skip future calls — no NVIDIA GPU), ``true`` = at least one call
// has succeeded.
let nvidiaSmiAvailable = null;

// GPU throttle state (see GPU_POLL_EVERY_N_TICKS). ``gpuTickCounter``
// counts sampler ticks; ``lastGpuValue`` carries the most recent
// nvidia-smi reading between the ticks we actually poll on.
let gpuTickCounter = 0;
let lastGpuValue = null;

let samplerTimer = null;
let registered = false;
// Re-entrancy latch for the timer-driven sampler. ``sample()`` is async
// and a tick can outlast SAMPLE_INTERVAL_MS (a stalled get-windows /
// xprop read has no timeout), so without this two ticks would run
// concurrently — spawning overlapping nvidia-smi processes and letting
// an older run finish last and overwrite ``latestSnapshot`` with stale
// data. The guard wraps the *timer* path only; ``forceSample`` (test /
// debug hook) stays unguarded and awaitable. (Codex P2 on PR #127;
// same fix the renderer's app-activity-signal.js already carries.)
let samplingInFlight = false;
// Handle for the per-run watchdog timer (see SAMPLE_WATCHDOG_MS). At
// most one guarded run is in flight, so a single handle suffices.
let samplingWatchdog = null;

function pushCpuSample() {
    try {
        cpuSamples.push(os.cpus());
        while (cpuSamples.length > CPU_SAMPLE_WINDOW) {
            cpuSamples.shift();
        }
    } catch (_) {
        // os.cpus() failing on weird platforms shouldn't kill the
        // sampler — just skip this sample.
    }
}

function computeCpuAvg30s() {
    if (cpuSamples.length < 2) {
        return null; // not enough samples yet (boot warm-up)
    }
    const first = cpuSamples[0];
    const last = cpuSamples[cpuSamples.length - 1];
    if (!first || !last || first.length !== last.length) {
        // Core count changed mid-window — unlikely but possible if a
        // VM re-hot-plugs CPUs. Drop the buffer rather than emit
        // garbage values.
        cpuSamples = [last];
        return null;
    }
    let totalDiff = 0;
    let idleDiff = 0;
    for (let i = 0; i < first.length; i++) {
        const fTimes = first[i].times;
        const lTimes = last[i].times;
        const fTotal = fTimes.user + fTimes.nice + fTimes.sys + fTimes.idle + fTimes.irq;
        const lTotal = lTimes.user + lTimes.nice + lTimes.sys + lTimes.idle + lTimes.irq;
        totalDiff += lTotal - fTotal;
        idleDiff += lTimes.idle - fTimes.idle;
    }
    if (totalDiff <= 0) {
        return null;
    }
    const usage = 100 * (1 - idleDiff / totalDiff);
    if (!Number.isFinite(usage)) return null;
    return Math.max(0, Math.min(100, usage));
}

function readGpuUtilization() {
    if (nvidiaSmiAvailable === false) {
        return Promise.resolve(null);
    }
    return new Promise((resolve) => {
        let resolved = false;
        let stdout = '';
        let proc;
        try {
            proc = spawn('nvidia-smi', [
                '--query-gpu=utilization.gpu',
                '--format=csv,noheader,nounits',
            ]);
        } catch (e) {
            if (e && e.code === 'ENOENT') {
                nvidiaSmiAvailable = false;
            }
            return resolve(null);
        }
        const timer = setTimeout(() => {
            if (resolved) return;
            resolved = true;
            try { proc.kill('SIGKILL'); } catch (_) {}
            resolve(null);
        }, NVIDIA_SMI_TIMEOUT_MS);
        proc.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        proc.on('error', (err) => {
            if (resolved) return;
            resolved = true;
            clearTimeout(timer);
            // ENOENT = no nvidia-smi binary at all. Latch off so we
            // don't keep spawning every 5s on AMD/Intel/no-GPU hosts.
            // Other errors (EACCES, driver issue) might be transient,
            // so we don't latch — try again next tick.
            if (err && err.code === 'ENOENT') {
                nvidiaSmiAvailable = false;
            }
            resolve(null);
        });
        proc.on('close', (code) => {
            if (resolved) return;
            resolved = true;
            clearTimeout(timer);
            if (code !== 0) {
                // Non-zero without ENOENT — likely "no devices were
                // found" or a driver error. Don't latch off; user may
                // plug in a GPU / fix drivers and we should pick up.
                return resolve(null);
            }
            nvidiaSmiAvailable = true;
            const line = String(stdout || '').trim().split('\n')[0];
            const val = parseFloat(line);
            if (!Number.isFinite(val) || val < 0 || val > 100) {
                return resolve(null);
            }
            resolve(val);
        });
    });
}

async function readActiveWindow() {
    try {
        // get-windows is ESM-only since v8; use dynamic import to
        // keep this file CJS (NEKO-PC's main process is CJS).
        const mod = await import('get-windows');
        const win = await mod.activeWindow();
        if (!win || typeof win !== 'object') {
            return { title: null, processName: null };
        }
        const title = typeof win.title === 'string' && win.title ? win.title : null;
        const owner = win.owner && typeof win.owner === 'object' ? win.owner : null;
        const processName = owner && typeof owner.name === 'string' && owner.name
            ? owner.name
            : null;
        return { title, processName };
    } catch (_) {
        // Common failure modes:
        //   - macOS: missing Screen Recording permission → title null
        //   - Wayland: no surface API → throws
        //   - Linux without xdotool: throws
        // All fall through to "no signal" — backend tracker falls back
        // to its local collector (which on remote backends is degraded
        // mode), which is the right behaviour.
        return { title: null, processName: null };
    }
}

async function sample(logger) {
    try {
        pushCpuSample();
        // GPU is throttled to every Nth tick (see GPU_POLL_EVERY_N_TICKS)
        // because nvidia-smi spawns a subprocess; window / idle / CPU
        // stay at the full 5s cadence. On GPU ticks we run active-win +
        // nvidia-smi in parallel (they don't share resources and
        // serialising them would double the tick latency on slow Linux
        // setups); on non-GPU ticks we only read the active window and
        // carry the last GPU value forward.
        gpuTickCounter += 1;
        const pollGpuThisTick = gpuTickCounter % GPU_POLL_EVERY_N_TICKS === 0;

        let activeWin;
        if (pollGpuThisTick) {
            const [win, gpu] = await Promise.all([
                readActiveWindow(),
                readGpuUtilization(),
            ]);
            activeWin = win;
            lastGpuValue = gpu;
        } else {
            activeWin = await readActiveWindow();
        }
        const idleSeconds = readIdleSeconds();
        latestSnapshot = {
            windowTitle: activeWin.title,
            processName: activeWin.processName,
            idleSeconds,
            cpuAvg30s: computeCpuAvg30s(),
            gpuUtilization: lastGpuValue,
        };
    } catch (e) {
        if (logger && typeof logger.warn === 'function') {
            logger.warn('[activity-signal-ipc] sample failed:', e);
        }
    }
}

// Timer-path wrapper: skip this tick if the previous sample() is still
// running (see ``samplingInFlight``). Fire-and-forget — the timer must
// not await — but the latch guarantees at most one sample() in flight at
// a time.
//
// The latch is released two ways (whichever comes first):
//   * normally, when sample()'s promise settles (``.finally``); or
//   * by a watchdog after SAMPLE_WATCHDOG_MS, in case a read wedges
//     with no timeout of its own (get-windows / xprop can block
//     indefinitely) — otherwise ``.finally`` never runs and the latch
//     pins true forever, silently killing the sampler. (Codex P1 on
//     PR #127.) ``released`` makes the two paths idempotent.
function runGuardedSample(logger) {
    if (samplingInFlight) {
        return;
    }
    samplingInFlight = true;
    let released = false;
    const release = () => {
        if (released) {
            return;
        }
        released = true;
        if (samplingWatchdog) {
            clearTimeout(samplingWatchdog);
            samplingWatchdog = null;
        }
        samplingInFlight = false;
    };
    samplingWatchdog = setTimeout(() => {
        if (logger && typeof logger.warn === 'function') {
            logger.warn(
                '[activity-signal-ipc] sample watchdog fired after '
                + SAMPLE_WATCHDOG_MS + 'ms — releasing in-flight latch '
                + '(a read likely wedged)',
            );
        }
        release();
    }, SAMPLE_WATCHDOG_MS);
    // Don't keep the event loop alive purely for the watchdog.
    if (samplingWatchdog && typeof samplingWatchdog.unref === 'function') {
        samplingWatchdog.unref();
    }
    Promise.resolve()
        .then(() => sample(logger))
        .finally(release);
}

// Module-level reference to the Electron primitives that were injected
// at registration time. Stays null until ``registerActivitySignalIpc``
// runs so the module can be required from tests without Electron.
let injectedIpcMain = null;
let injectedPowerMonitor = null;

function readIdleSeconds() {
    if (!injectedPowerMonitor || typeof injectedPowerMonitor.getSystemIdleTime !== 'function') {
        return null;
    }
    try {
        const raw = injectedPowerMonitor.getSystemIdleTime();
        if (Number.isFinite(raw) && raw >= 0) {
            return raw;
        }
    } catch (_) { /* fall through */ }
    return null;
}

/**
 * Register the IPC handler and start the background sampler.
 *
 * Safe to call multiple times — second call is a no-op. Call once
 * from main.js after the app is ready, passing the Electron primitives:
 *
 *   const { ipcMain, powerMonitor } = require('electron');
 *   registerActivitySignalIpc({ ipcMain, powerMonitor, log });
 *
 * This DI shape is the project-wide convention — see ``screen-capture-ipc``
 * and other factories under ``src/main/``, plus the contract enforced by
 * ``test/main-composition-contract.test.js``: only ``src/main.js`` may
 * require('electron') directly.
 */
function registerActivitySignalIpc(context = {}) {
    if (registered) return { stop };
    const { ipcMain, powerMonitor, logger: providedLogger, log } = context;
    if (!ipcMain || typeof ipcMain.handle !== 'function') {
        throw new TypeError(
            'registerActivitySignalIpc: ipcMain.handle is required',
        );
    }
    const logger = providedLogger || (log ? { info: log, warn: log } : console);
    injectedIpcMain = ipcMain;
    injectedPowerMonitor = powerMonitor || null;
    registered = true;

    // Kick off the first sample immediately so the renderer's first
    // call doesn't get an empty snapshot. (Won't have cpuAvg30s on
    // the first tick — that needs ≥2 samples — but everything else
    // will be live.) Both the kickoff and the interval go through the
    // in-flight guard so a slow first tick can't overlap the first
    // interval tick.
    runGuardedSample(logger);
    samplerTimer = setInterval(() => runGuardedSample(logger), SAMPLE_INTERVAL_MS);
    // Don't keep the event loop alive purely for sampling on shutdown.
    if (samplerTimer && typeof samplerTimer.unref === 'function') {
        samplerTimer.unref();
    }

    ipcMain.handle('neko:read-activity-signal', async () => {
        // Return a shallow clone so the renderer can't accidentally
        // mutate our cached state via the IPC structured-clone path.
        return { ...latestSnapshot };
    });

    if (logger.info) {
        logger.info('[activity-signal-ipc] registered '
            + '(SAMPLE_INTERVAL_MS=' + SAMPLE_INTERVAL_MS + ', '
            + 'CPU_SAMPLE_WINDOW=' + CPU_SAMPLE_WINDOW + ')');
    }

    return { stop };
}

function stop() {
    if (samplerTimer) {
        clearInterval(samplerTimer);
        samplerTimer = null;
    }
    if (samplingWatchdog) {
        clearTimeout(samplingWatchdog);
        samplingWatchdog = null;
    }
    cpuSamples = [];
    gpuTickCounter = 0;
    lastGpuValue = null;
    samplingInFlight = false;
    registered = false;
    try {
        if (injectedIpcMain && typeof injectedIpcMain.removeHandler === 'function') {
            injectedIpcMain.removeHandler('neko:read-activity-signal');
        }
    } catch (_) {}
    injectedIpcMain = null;
    injectedPowerMonitor = null;
}

module.exports = {
    registerActivitySignalIpc,
    stop,
    // Exposed for tests / introspection. Not a public API.
    _internals: {
        getLatestSnapshot: () => ({ ...latestSnapshot }),
        getCpuSampleCount: () => cpuSamples.length,
        getNvidiaSmiAvailable: () => nvidiaSmiAvailable,
        forceSample: (logger) => sample(logger),
        // Test hooks — seed sample buffer with synthetic os.cpus()-shaped
        // entries to exercise the diff math without waiting 30 wall-clock
        // seconds for real samples to accumulate.
        _seedCpuSamples: (samples) => {
            cpuSamples = Array.isArray(samples) ? samples.slice() : [];
        },
        _computeCpuAvg30s: computeCpuAvg30s,
    },
};
