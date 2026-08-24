const { ipcRenderer } = require('electron');
const { setupAutostartBridge, setupHostCapabilityBridge } = require('./preload-common');

// 状态缓存
let lastIgnoreState = null;
let isCtrlPressed = false;
let _nativeMouseThroughPendingPoint = null;
let _nativeMouseThroughTimer = null;
let _nativeMouseThroughFrame = null;
let _nativeMouseThroughLastRunAt = 0;
const _NATIVE_MOUSE_THROUGH_COALESCE_MS = 24;

// ===== 节流 & 过渡守卫（与 preload-pet.js 对齐）=====
let _transitionFrozen = false;  // 过渡守卫：冻结穿透状态切换
let _frozenTimer = null;        // 过渡守卫计时器
let _lastSwitchTime = 0;
let _pendingTimeout = null;
const _MIN_SWITCH_INTERVAL = 100; // ms，开启穿透的最小间隔

// ===== hitTest 滞后（施密特触发器）=====
let _lastHitResult = false;       // 上次 hitTest 结果
const _HYSTERESIS_PX = 10;        // 滞后区像素，防止模型边缘 true↔false 振荡

// 监听键盘事件以追踪 Ctrl 键状态
window.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey) isCtrlPressed = true;
});
window.addEventListener('keyup', (e) => {
    if (!e.ctrlKey && !e.metaKey) isCtrlPressed = false;
});
window.addEventListener('blur', () => {
    isCtrlPressed = false;
});

// 监听主进程信号
ipcRenderer.on('navigation-start', () => {
    ipcRenderer.send('set-ignore-mouse-events', false);
    lastIgnoreState = false;
});

ipcRenderer.on('page-fully-loaded', () => {
    ipcRenderer.send('set-ignore-mouse-events', false);
    lastIgnoreState = false;
    console.log('[Preload] Page loaded.');
});

// 【鼠标穿透逻辑】
// 
// 分支规则：
// #1. UI 元素（按钮等）→ 不穿透
// #2. 背景 + 🔒锁定 → 穿透（不检测 hitTest）
// #3. 背景 + 🔓解锁 + hitTest命中 → 不穿透
// #4. 背景 + 🔓解锁 + hitTest未命中 → 穿透
//
function setupMouseThroughLogic() {
    window.addEventListener('mousemove', (event) => {
        if (event && event.isTrusted === false) {
            handleMousePosition(event.clientX, event.clientY);
        } else {
            scheduleNativeMouseThroughPosition(event.clientX, event.clientY);
        }
    });
}

function scheduleNativeMouseThroughPosition(x, y) {
    if (!Number.isFinite(Number(x)) || !Number.isFinite(Number(y))) return;
    _nativeMouseThroughPendingPoint = { x: Number(x), y: Number(y) };
    if (_nativeMouseThroughTimer || _nativeMouseThroughFrame) return;

    const now = typeof performance !== 'undefined' && typeof performance.now === 'function'
        ? performance.now()
        : Date.now();
    const delay = Math.max(0, _NATIVE_MOUSE_THROUGH_COALESCE_MS - (now - _nativeMouseThroughLastRunAt));
    const scheduleFrame = () => {
        if (typeof window.requestAnimationFrame === 'function') {
            _nativeMouseThroughFrame = window.requestAnimationFrame(flushNativeMouseThroughPosition);
        } else {
            _nativeMouseThroughTimer = setTimeout(flushNativeMouseThroughPosition, 0);
        }
    };

    if (delay > 0) {
        _nativeMouseThroughTimer = setTimeout(() => {
            _nativeMouseThroughTimer = null;
            scheduleFrame();
        }, delay);
    } else {
        scheduleFrame();
    }
}

function flushNativeMouseThroughPosition() {
    _nativeMouseThroughTimer = null;
    _nativeMouseThroughFrame = null;
    const point = _nativeMouseThroughPendingPoint;
    _nativeMouseThroughPendingPoint = null;
    if (!point) return;
    _nativeMouseThroughLastRunAt = typeof performance !== 'undefined' && typeof performance.now === 'function'
        ? performance.now()
        : Date.now();
    handleMousePosition(point.x, point.y);
}

// 检测是否是 about:blank 页面（手机模式）
function isBlankPage() {
    return window.location.href === 'about:blank';
}

// 核心判断函数：根据鼠标位置决定是否穿透
function handleMousePosition(x, y) {
    // about:blank 页面（手机模式）：完全穿透（立即，绕过节流）
    if (isBlankPage()) {
        setIgnoreState(true, true);
        return;
    }
    
    const isHomePage = window.location.pathname === '/' || window.location.pathname === '/index.html';
    
    // 非首页：不穿透
    if (!isHomePage) {
        setIgnoreState(false);
        return;
    }

    // 【分支 #1】检查是否在 UI 元素上
    const el = document.elementFromPoint(x, y);
    if (!el) {
        setIgnoreState(true); // 没有元素，穿透
        return;
    }

    const isBackground = 
        el === document.body || 
        el.tagName === 'HTML' ||
        // Live2D 相关
        el.id === 'live2d-container' || 
        el.id === 'live2d-canvas' ||
        el.classList.contains('live2d-container') ||
        el.classList.contains('live2d') ||
        el.hasAttribute('data-live2d') ||
        // VRM 相关（Three.js 画布）
        el.id === 'vrm-canvas' ||
        el.id === 'vrm-container' ||
        el.hasAttribute('data-vrm') ||
        // MMD 相关（Three.js 画布）
        el.id === 'mmd-canvas' ||
        el.id === 'mmd-container';

    if (!isBackground) {
        // #1: UI 元素 → 不穿透
        setIgnoreState(false);
        return;
    }

    // 【分支 #2】检查锁定状态（根据当前活跃模型类型判断）
    let isLocked = false;
    try {
        const modelType = window.lanlan_config?.model_type || 'live2d';
        if (modelType === 'live3d') {
            // MMD / VRM——根据实际加载的子类型判断
            if (window.mmdManager && window.mmdManager.currentModel) {
                isLocked = window.mmdManager.isLocked ?? window.mmdManager.interaction?.isLocked ?? false;
            } else if (window.vrmManager && window.vrmManager.currentModel) {
                isLocked = window.vrmManager.isLocked ?? window.vrmManager.interaction?.isLocked ?? false;
            }
        } else if (modelType === 'vrm') {
            if (window.vrmManager) {
                isLocked = window.vrmManager.isLocked ?? window.vrmManager.interaction?.isLocked ?? false;
            }
        } else {
            // Live2D
            if (window.live2dManager) {
                isLocked = window.live2dManager.isLocked;
            }
        }
    } catch (e) {}

    if (isLocked) {
        // #2: 背景 + 锁定 → 穿透（不检测 hitTest，立即绕过节流）
        setIgnoreState(true, true);
        return;
    }

    // 【分支 #3-4】背景 + 解锁：用 hitTest + 滞后判定
    // 已在模型上时用扩大边界检测，防止边缘 1px 振荡触发反复 DWM 重建
    const margin = _lastHitResult ? _HYSTERESIS_PX : 0;
    const isOnModel = checkHitTest(x, y, margin);
    _lastHitResult = isOnModel;

    if (isOnModel) {
        // #3: 命中模型 → 不穿透
        setIgnoreState(false);
    } else {
        // #4: 未命中模型 → 穿透
        setIgnoreState(true);
    }
}

// VRM hitTest 检测：判断坐标是否在 VRM 模型实体上
function checkVRMHitTest(x, y, margin) {
    try {
        if (!window.vrmManager || !window.vrmManager.currentModel) return false;

        const interaction = window.vrmManager.interaction;
        if (!interaction) return false;

        // 尝试更新缓存（如果过期或不存在）
        if (typeof interaction.updateModelBoundsCache === 'function') {
            interaction.updateModelBoundsCache();
        }

        // 使用缓存的屏幕边界检测
        if (interaction._cachedScreenBounds) {
            const { minX, maxX, minY, maxY } = interaction._cachedScreenBounds;
            const m = margin || 0;
            if (minX !== undefined && maxX !== undefined && minY !== undefined && maxY !== undefined) {
                return x >= minX - m && x <= maxX + m && y >= minY - m && y <= maxY + m;
            }
        }
        
        // 【新增】兜底检测：如果缓存无效，尝试使用模型的直接边界
        const model = window.vrmManager.currentModel;
        if (model && typeof model.getBoundingBox === 'function') {
            try {
                const box = model.getBoundingBox();
                if (box && box.isBoundingBox) {
                    return x >= box.min.x && x <= box.max.x && y >= box.min.y && y <= box.max.y;
                }
            } catch (e) {}
        }
        
        // 【新增】兜底检测：尝试使用模型的场景变换信息
        if (model && model.scene && model.scene.children && model.scene.children.length > 0) {
            try {
                const object3d = model.scene.children.find(child => 
                    child.isMesh || child.isSkinnedMesh || child.type === 'Group'
                );
                if (object3d) {
                    const box = new (window.THREE?.Box3 || Object).setFromObject(object3d);
                    if (box && box.min && box.max) {
                        // 简单屏幕坐标转换（假设使用默认相机）
                        const centerX = (box.min.x + box.max.x) / 2;
                        const centerY = (box.min.y + box.max.y) / 2;
                        const sizeX = box.max.x - box.min.x;
                        const sizeY = box.max.y - box.min.y;
                        
                        // 使用宽松的边界检测
                        return x >= centerX - sizeX * 0.6 && x <= centerX + sizeX * 0.6 &&
                               y >= centerY - sizeY * 0.6 && y <= centerY + sizeY * 0.6;
                    }
                }
            } catch (e) {}
        }
        
        return false;
    } catch (e) {
        return false;
    }
}

// MMD hitTest 检测：判断坐标是否在 MMD 模型实体上
function checkMMDHitTest(x, y, margin) {
    try {
        if (!window.mmdManager || !window.mmdManager.currentModel) return false;

        const interaction = window.mmdManager.interaction;
        if (!interaction) return false;

        // 尝试更新缓存（如果过期或不存在）
        if (typeof interaction.updateScreenBounds === 'function') {
            interaction.updateScreenBounds();
        }

        // 使用缓存的屏幕边界检测
        if (interaction._cachedScreenBounds) {
            const { minX, maxX, minY, maxY } = interaction._cachedScreenBounds;
            const m = margin || 0;
            if (minX !== undefined && maxX !== undefined && minY !== undefined && maxY !== undefined) {
                return x >= minX - m && x <= maxX + m && y >= minY - m && y <= maxY + m;
            }
        }
        
        // 【新增】兜底检测：如果缓存无效，尝试使用 mmdManager 的直接边界
        const mmdCore = window.mmdManager.core;
        if (mmdCore && typeof mmdCore.getModelBounds === 'function') {
            try {
                const bounds = mmdCore.getModelBounds();
                if (bounds && bounds.min && bounds.max) {
                    return x >= bounds.min.x && x <= bounds.max.x && 
                           y >= bounds.min.y && y <= bounds.max.y;
                }
            } catch (e) {}
        }
        
        // 【新增】兜底检测：尝试使用 Three.js 场景信息
        if (mmdCore && mmdCore.scene && mmdCore.scene.children && mmdCore.scene.children.length > 0) {
            try {
                const object3d = mmdCore.scene.children.find(child => 
                    child.isMesh || child.isSkinnedMesh || child.type === 'Group'
                );
                if (object3d) {
                    const box = new (window.THREE?.Box3 || Object).setFromObject(object3d);
                    if (box && box.min && box.max) {
                        const centerX = (box.min.x + box.max.x) / 2;
                        const centerY = (box.min.y + box.max.y) / 2;
                        const sizeX = box.max.x - box.min.x;
                        const sizeY = box.max.y - box.min.y;
                        
                        // 使用宽松的边界检测
                        return x >= centerX - sizeX * 0.6 && x <= centerX + sizeX * 0.6 &&
                               y >= centerY - sizeY * 0.6 && y <= centerY + sizeY * 0.6;
                    }
                }
            } catch (e) {}
        }
        
        return false;
    } catch (e) {
        return false;
    }
}

// hitTest 检测：根据当前活跃模型类型判断坐标是否在模型实体上
function checkHitTest(x, y, margin) {
    try {
        const modelType = window.lanlan_config?.model_type || 'live2d';

        // 【优化】对于 live3d 模式，同时检查 mmdManager 和 vrmManager
        // 因为可能在 MMD 模式下设置了 VRM 模型，或者相反
        if (modelType === 'live3d') {
            const hasMMD = window.mmdManager && window.mmdManager.currentModel;
            const hasVRM = window.vrmManager && window.vrmManager.currentModel;

            if (hasMMD && hasVRM) {
                if (checkMMDHitTest(x, y, margin)) return true;
                return checkVRMHitTest(x, y, margin);
            }
            if (hasMMD) return checkMMDHitTest(x, y, margin);
            if (hasVRM) return checkVRMHitTest(x, y, margin);
            return false;
        }

        if (modelType === 'vrm') {
            if (window.vrmManager && window.vrmManager.currentModel) {
                return checkVRMHitTest(x, y, margin);
            }
            if (window.mmdManager && window.mmdManager.currentModel) {
                return checkMMDHitTest(x, y, margin);
            }
            return false;
        }

        // live2d 模式下也检查是否有意外的 3D 模型
        if (modelType === 'live2d') {
            if (window.mmdManager && window.mmdManager.currentModel) {
                return checkMMDHitTest(x, y, margin);
            }
            if (window.vrmManager && window.vrmManager.currentModel) {
                return checkVRMHitTest(x, y, margin);
            }
        }

        // Live2D 检测
        if (!window.live2dManager) return false;

        const model = window.live2dManager.getCurrentModel();
        if (!model) return false;

        const bounds = model.getBounds();
        const m = margin || 0;

        // 快速剔除：不在矩形边界内（含滞后余量）
        if (x < bounds.x - m || x > bounds.x + bounds.width + m ||
            y < bounds.y - m || y > bounds.y + bounds.height + m) {
            return false;
        }

        // 方法A：Live2D 内置 hitTest
        try {
            if (typeof model.hitTest === 'function') {
                const hitAreas = model.hitTest(x, y);
                if (hitAreas && hitAreas.length > 0) {
                    return true;
                }
            }
        } catch (e) {}

        // 方法B：椭圆近似检测（更接近人物形状，含滞后余量）
        const centerX = bounds.x + bounds.width / 2;
        const centerY = bounds.y + bounds.height / 2;
        const radiusX = bounds.width * 0.35 + m;
        const radiusY = bounds.height * 0.45 + m;
        const normalizedX = (x - centerX) / radiusX;
        const normalizedY = (y - centerY) / radiusY;

        return (normalizedX * normalizedX + normalizedY * normalizedY) <= 1;
        
    } catch (e) {
        return false;
    }
}

// 设置穿透状态（节流 + 过渡守卫，与 preload-pet.js 对齐）
// - 取消穿透（进入模型）→ 立即执行（保证点击响应）
// - 开启穿透（离开模型）→ 100ms 节流（缓解 DWM 重建闪烁）
function setIgnoreState(ignore, immediate) {
    if (_transitionFrozen) return;
    // 持续收到 ignore=false 时，取消 pending 的 ignore=true 定时器，
    // 否则旧定时器到期会强制切穿透 → cursor 闪成箭头再切回。
    if (!ignore && _pendingTimeout) {
        clearTimeout(_pendingTimeout);
        _pendingTimeout = null;
    }
    if (lastIgnoreState === ignore) return;

    if (immediate) {
        if (_pendingTimeout) { clearTimeout(_pendingTimeout); _pendingTimeout = null; }
        ipcRenderer.send('set-ignore-mouse-events', ignore);
        lastIgnoreState = ignore;
        _lastSwitchTime = Date.now();
        return;
    }

    // 取消穿透 → 立即执行
    if (ignore === false) {
        if (_pendingTimeout) { clearTimeout(_pendingTimeout); _pendingTimeout = null; }
        ipcRenderer.send('set-ignore-mouse-events', false);
        lastIgnoreState = false;
        _lastSwitchTime = Date.now();
        return;
    }

    // 开启穿透 → 节流
    var now = Date.now();
    var elapsed = now - _lastSwitchTime;
    if (elapsed < _MIN_SWITCH_INTERVAL) {
        if (!_pendingTimeout) {
            _pendingTimeout = setTimeout(function() {
                _pendingTimeout = null;
                if (lastIgnoreState !== true) {
                    ipcRenderer.send('set-ignore-mouse-events', true);
                    lastIgnoreState = true;
                    _lastSwitchTime = Date.now();
                }
            }, _MIN_SWITCH_INTERVAL - elapsed);
        }
        return;
    }
    ipcRenderer.send('set-ignore-mouse-events', true);
    lastIgnoreState = true;
    _lastSwitchTime = now;
}

// 冻结穿透状态切换（弹窗动画过渡期间调用）
function freezeMouseThrough(durationMs) {
    _transitionFrozen = true;
    if (_frozenTimer) clearTimeout(_frozenTimer);
    _frozenTimer = setTimeout(() => {
        _transitionFrozen = false;
        _frozenTimer = null;
    }, durationMs);
}

// 轮询器：
// 1. 在穿透模式下检测是否该切回不穿透（UI元素/模型命中）
// 2. 转发鼠标事件 + 视线追踪
function startMousePoller() {
    setInterval(async () => {
        // about:blank 页面（手机模式）：跳过轮询，保持完全穿透
        if (isBlankPage()) return;
        
        const isHomePage = window.location.pathname === '/' || window.location.pathname === '/index.html';
        if (!isHomePage) return;
        
        try {
            const point = await ipcRenderer.invoke('get-cursor-point');
            
            if (point && typeof point.x === 'number' && typeof point.y === 'number') {
                const isOutside = point.x < 0 || point.y < 0 || 
                                  point.x > window.innerWidth || point.y > window.innerHeight;
                
                // 【关键】在穿透模式下，始终检测是否该切回不穿透
                // handleMousePosition 会先检测 UI 元素（不受锁定状态影响）
                // 这样即使 UI 元素从 hidden 恢复为 visible，也能正确响应
                if (lastIgnoreState === true && !isOutside) {
                    handleMousePosition(point.x, point.y);
                }
                
                // 在穿透模式下或鼠标在窗口外时：转发鼠标事件 + 视线追踪
                if (lastIgnoreState === true || isOutside) {
                    // 视线追踪由原始脚本管理，electron只需要转发事件即可
                    // 模拟 mousemove 事件
                    const mouseEvent = new MouseEvent('mousemove', {
                        view: window,
                        bubbles: true,
                        cancelable: true,
                        clientX: point.x,
                        clientY: point.y,
                        screenX: point.screenX,
                        screenY: point.screenY
                    });
                    window.dispatchEvent(mouseEvent);
                    
                    // 模拟 pointermove 事件（网页代码 enableMouseTracking 监听的是这个）
                    const pointerEvent = new PointerEvent('pointermove', {
                        view: window,
                        bubbles: true,
                        cancelable: true,
                        clientX: point.x,
                        clientY: point.y,
                        screenX: point.screenX,
                        screenY: point.screenY,
                        pointerId: 1,
                        pointerType: 'mouse',
                        isPrimary: true,
                        ctrlKey: isCtrlPressed,
                        metaKey: isCtrlPressed // 同时设置 metaKey 以支持 Mac
                    });
                    window.dispatchEvent(pointerEvent);
                }

                // 始终直接驱动 VRM/MMD cursor-follow 视线追踪（不受穿透状态限制）
                // 解锁状态下穿透关闭时，浏览器原生事件在 Electron 透明窗口中
                // 无法可靠触达 cursor-follow 的 window 级监听器，
                // 因此由 poller 每 50ms 直接喂坐标。handler 是幂等的（仅赋值），
                // 与原生事件并存时无副作用。
                try {
                    const gazeEvt = { type: 'pointermove', clientX: point.x, clientY: point.y };
                    if (window.vrmManager?._cursorFollow?._onPointerMove) {
                        window.vrmManager._cursorFollow._onPointerMove(gazeEvt);
                    }
                    if (window.mmdManager?.cursorFollow?._pointerMoveHandler) {
                        window.mmdManager.cursorFollow._pointerMoveHandler(gazeEvt);
                    }
                } catch (e) { /* cursor-follow 未就绪时静默忽略 */ }
            }
        } catch (e) {
            // ignore
        }
    }, 50);
}

// --- DOM Ready ---
document.addEventListener('DOMContentLoaded', () => {
    setupMouseThroughLogic();
    startMousePoller();
    
    // 初始状态：不穿透
    ipcRenderer.send('set-ignore-mouse-events', false);
    lastIgnoreState = false;
    
    // 【过渡守卫】监听弹窗动画事件，冻结穿透状态防止闪烁
    const POPUP_GUARD_MS = 280; // 略大于弹窗动画时长 (200ms)
    window.addEventListener('neko-popup-opening', () => freezeMouseThrough(POPUP_GUARD_MS));
    window.addEventListener('neko-popup-closed',  () => freezeMouseThrough(POPUP_GUARD_MS));
    // 通用弹窗事件（如有）
    window.addEventListener('neko-popup-transition-start', (e) => {
        const duration = (e.detail && e.detail.duration) || POPUP_GUARD_MS;
        freezeMouseThrough(duration);
    });
    
    console.log('[Preload] Mouse through logic initialized.');
});

// --- 复位模型位置处理 ---
ipcRenderer.on('reset-model-position', () => {
    console.log('[Preload] 收到复位模型位置消息');
    try {
        // model_type 为 'live3d' 时，VRM 和 MMD 都走这个值，需要看 live3d_sub_type 区分
        const modelType = (window.lanlan_config?.model_type || 'live2d').toLowerCase();
        const subType = (window.lanlan_config?.live3d_sub_type || '').toLowerCase();

        if ((modelType === 'vrm' || (modelType === 'live3d' && subType === 'vrm')) && window.vrmManager && typeof window.vrmManager.resetModelPosition === 'function') {
            window.vrmManager.resetModelPosition();
            console.log('[Preload] VRM 模型位置复位成功');
        } else if ((modelType === 'live3d' && subType !== 'vrm') && window.mmdManager && typeof window.mmdManager.resetModelPosition === 'function') {
            window.mmdManager.resetModelPosition();
            console.log('[Preload] MMD 模型位置复位成功');
        } else if (window.live2dManager && typeof window.live2dManager.resetModelPosition === 'function') {
            window.live2dManager.resetModelPosition();
            console.log('[Preload] Live2D 模型位置复位成功');
        } else {
            console.warn('[Preload] 没有可用的模型管理器来复位位置');
        }
    } catch (error) {
        console.error('[Preload] 复位模型位置时出错:', error);
    }
});

// --- 恢复默认模型（live2d/MMD/VRM -> 默认 Live2D） ---
// 由托盘"高级设置 → 恢复默认模型"菜单触发。renderer 侧的
// window.resetToDefaultModel（定义于 NEKO 的 static/app-interpage.js）
// 会持久化默认 Live2D 模型并触发 handleModelReload 完成热切换。
ipcRenderer.on('reset-to-default-model', () => {
    console.log('[Preload] 收到恢复默认模型消息');
    try {
        if (typeof window.resetToDefaultModel === 'function') {
            Promise.resolve(window.resetToDefaultModel()).catch((err) => {
                console.error('[Preload] 恢复默认模型失败:', err);
            });
        } else {
            console.warn('[Preload] window.resetToDefaultModel 未就绪，无法恢复默认模型');
        }
    } catch (error) {
        console.error('[Preload] 恢复默认模型时出错:', error);
    }
});

// --- 暗色模式处理 ---
ipcRenderer.on('toggle-dark-mode', (event, isDark) => {
    console.log('[Preload] 收到暗色模式切换消息:', isDark);
    try {
        if (isDark) {
            document.documentElement.setAttribute('data-theme', 'dark');
        } else {
            document.documentElement.removeAttribute('data-theme');
        }
        // 同步到 localStorage 以便前端脚本也能读取
        localStorage.setItem('neko-dark-mode', isDark ? 'true' : 'false');
        // 派发自定义事件，让前端代码可以响应
        window.dispatchEvent(new CustomEvent('neko-theme-changed', { detail: { darkMode: isDark } }));
    } catch (error) {
        console.error('[Preload] 切换暗色模式时出错:', error);
    }
});

// 暗色模式 API
window.nekoDarkMode = {
    get: () => ipcRenderer.invoke('get-dark-mode'),
    set: (enabled) => ipcRenderer.invoke('set-dark-mode', enabled),
    toggle: async () => {
        const current = await ipcRenderer.invoke('get-dark-mode');
        return ipcRenderer.invoke('set-dark-mode', !current);
    }
};

// --- 多屏幕边缘检测 API ---
// 暴露给网页的屏幕边界检测接口
window.electronScreen = {
    // 获取所有屏幕的边界（窗口坐标系）
    getAllDisplays: () => ipcRenderer.invoke('get-all-displays'),
    
    // 获取当前窗口所在屏幕的信息
    getCurrentDisplay: () => ipcRenderer.invoke('get-current-display'),

    // 主屏信息（屏幕坐标系，与 win:get-bounds 同坐标系）
    getPrimaryDisplayInfo: () => ipcRenderer.invoke('get-primary-display-info'),

    // 检测坐标是否在有效屏幕区域内
    isPointOnScreen: (x, y) => ipcRenderer.invoke('is-point-on-screen', x, y),
    
    // 将坐标限制在有效屏幕区域内
    // 返回 { x, y, clamped } - clamped 为 true 表示坐标被调整过
    clampToScreen: (x, y, elementWidth = 0, elementHeight = 0) => 
        ipcRenderer.invoke('clamp-to-screen', x, y, elementWidth, elementHeight),
    
    // 切换窗口到指定屏幕（通过屏幕坐标）
    // 当模型被拖动到另一个屏幕时调用
    moveWindowToDisplay: (screenX, screenY) => 
        ipcRenderer.invoke('move-window-to-display', screenX, screenY)
};


// --- 屏幕捕获源选择 API ---
// 暴露给网页的 desktopCapturer 接口，用于获取可共享的屏幕/窗口列表
window.electronDesktopCapturer = {
    // 获取可用的屏幕/窗口源列表
    // types: ['window', 'screen'] - 默认获取窗口和屏幕
    // thumbnailSize: { width, height } - 缩略图尺寸
    getSources: (options = {}) => ipcRenderer.invoke('get-desktop-sources', options),
    // 将渲染器端选中的源 ID 同步到主进程，供 setDisplayMediaRequestHandler 使用
    setSelectedSource: (sourceId) => ipcRenderer.invoke('set-selected-screen-source', sourceId || null),
    // 主进程直接对某个源做一次性截图，返回 { success, dataUrl, width, height } 或 { success:false, error }
    // 这是聊天框截图按钮最可靠的路径：绕开 getUserMedia/getDisplayMedia 的 Chromium 桌面捕获管线
    captureSourceAsDataUrl: (sourceId) => ipcRenderer.invoke('capture-source-as-dataurl', sourceId),
    // "隐藏NEKO" 再截图：主进程原子化闭环 hide 全部 NEKO 窗口 → desktopCapturer 抓图 → show
    captureSourceWithoutNeko: (sourceId) => ipcRenderer.invoke('capture-source-without-neko', sourceId),
    hideNekoWindows: () => ipcRenderer.invoke('hide-neko-windows'),
    restoreNekoWindows: (hiddenIds) => ipcRenderer.invoke('restore-neko-windows', hiddenIds),
};

console.log('[Preload] 屏幕捕获源选择 API 已注入 (window.electronDesktopCapturer)');


// 监听屏幕切换事件
ipcRenderer.on('display-changed', (event, displayInfo) => {
    console.log('[Preload] 屏幕已切换:', displayInfo);
    // 派发自定义事件，让前端代码可以响应
    window.dispatchEvent(new CustomEvent('electron-display-changed', { 
        detail: displayInfo 
    }));
});

console.log('[Preload] 多屏幕边缘检测 API 已注入 (window.electronScreen)');

// --- 系统浏览器打开外部链接 API ---
window.electronShell = {
    openExternal: (url) => ipcRenderer.invoke('open-external-url', url)
};

setupAutostartBridge();
setupHostCapabilityBridge();
