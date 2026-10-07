/**
 * agent-state-expression.js
 * NEKO 桌宠壳 · 「agent 状态 → 表情/动作」状态机与映射表
 *
 * 工单202 任务四落地。设计参照 Andersen216/dsh-whale-girl-live2d（★24 MIT）的
 * 状态机 + 触发词思路（状态预览/优先级/转换语义），按 NEKO 侧契约重写：
 *   - 输入：后端 agent 事件流（与 apiserver/event_bus/topics.py 的主题对齐）
 *   - 输出：NEKO 注入体 {emotion, motion, label}，经既有 /api/lumo/emotion 通道下发
 *     （见 apiserver/event_bus/bridge.py:362-370；NEKO 端按模型的 EmotionMapping
 *      解析 emotion → 具体 motion group / expression 前缀）
 *
 * 铁律（与鲸鱼娘同款）：
 *   1. 不编造进度 —— label 只有状态名，没有百分比/阶段编号。
 *   2. 未知事件不改写状态 —— 原状态返回并附 reason，绝不猜。
 *   3. 纯函数、零依赖、可测；不做任何 IO。
 *
 * 只动包装层：本文件属 neko-electron-shell（壳），不触碰 NEKO/N.E.K.O 上游。
 */

'use strict';

/** 六个 agent 状态（工单验收要求 ≥4 个状态触发不同表情，本表给 6 个）。 */
const STATES = Object.freeze({
  IDLE: 'idle',           // 待机
  THINKING: 'thinking',   // 思考中（模型在推理/组织回答）
  WORKING: 'working',     // 执行工具（搜索/读写/执行/测试）
  WAIT: 'wait',           // 等待用户确认（confirm_gate 挂起）
  ERROR: 'error',         // 出错
  CELEBRATE: 'celebrate', // 任务完成
});

/**
 * 多会话聚合优先级：同时有多个会话时，展示「最需要注意」的那个。
 * WAIT > ERROR > WORKING > THINKING > CELEBRATE > IDLE
 * （等待确认压过报错：用户可行动的阻塞最优先暴露。）
 */
const PRIORITY = Object.freeze({
  [STATES.WAIT]: 5,
  [STATES.ERROR]: 4,
  [STATES.WORKING]: 3,
  [STATES.THINKING]: 2,
  [STATES.CELEBRATE]: 1,
  [STATES.IDLE]: 0,
});

/**
 * NEKO 情绪标准集（**实测契约**，2026-10-06）：
 *   `NEKO/N.E.K.O/main_routers/system_router/emotion.py:401 _normalize_emotion_label`
 *   会把任意标签（165 个别名）归一化到这 5 个 canonical 值之一。
 *   注入侧（/api/lumo/emotion）**只认这 5 个** —— 自定义标签（如 thinking）会被
 *   fuzzy 匹配改写或回落，不可依赖。故本表的 emotion 字段必须收敛到标准集；
 *   状态级区分由 `motion`/`label` 承担（壳层本地 HUD 展示维度，不受 NEKO 限制）。
 */
const NEKO_STANDARD_EMOTIONS = Object.freeze([
  'angry', 'happy', 'neutral', 'sad', 'surprised',
]);

/**
 * 状态 → 表情/动作映射表。
 *   emotion：注入 NEKO 用（⊆ 5 标准集）
 *   motion / label：壳层展示用（HUD / 气泡文案；6 个状态各不相同）
 * 4 个状态拿到不同情绪（neutral / surprised / sad / happy），
 * 6 个状态拿到不同 motion+label —— 满足「≥4 个 agent 状态触发不同表情」。
 */
const EXPRESSION_MAP = Object.freeze({
  [STATES.IDLE]: { emotion: 'neutral', motion: 'idle', label: '待机' },
  [STATES.THINKING]: { emotion: 'neutral', motion: 'think', label: '思考中' },
  [STATES.WORKING]: { emotion: 'neutral', motion: 'working', label: '执行中' },
  [STATES.WAIT]: { emotion: 'surprised', motion: 'wait', label: '等待确认' },
  [STATES.ERROR]: { emotion: 'sad', motion: 'error', label: '出错了' },
  [STATES.CELEBRATE]: { emotion: 'happy', motion: 'celebrate', label: '完成' },
});

/**
 * 事件 → 状态转换表。
 * key 为归一化事件名（支持 event_bus 主题短名与语义别名）；
 * value 为 (event) => 目标状态，未列出的 → null（不改写）。
 */
const TRANSITIONS = Object.freeze({
  // 一轮开始 / 用户输入 → 思考
  session_start: () => STATES.THINKING,
  user_input: () => STATES.THINKING,
  'lumo.user.input.received': () => STATES.THINKING,

  // 工具前置（含 guard / confirm 放行）→ 执行
  tool_pre_execute: () => STATES.WORKING,
  tool_call: () => STATES.WORKING,
  'lumo.tool.pre-execute': () => STATES.WORKING,
  'lumo.tool.guard': () => STATES.WORKING,

  // 工具后置 → 有错则 ERROR，否则回到思考（整理工具结果）
  tool_post_execute: (ev) => (isFailure(ev) ? STATES.ERROR : STATES.THINKING),
  'lumo.tool.post-execute': (ev) => (isFailure(ev) ? STATES.ERROR : STATES.THINKING),

  // 确认门挂起/解除（apiserver/event_bus/confirm_gate.py）
  confirm_pending: () => STATES.WAIT,
  confirm_resolved: () => STATES.THINKING,

  // 完成 / 收尾
  turn_completed: () => STATES.CELEBRATE,
  task_done: () => STATES.CELEBRATE,
  session_end: () => STATES.IDLE,
  idle: () => STATES.IDLE,

  // 显式错误
  error: () => STATES.ERROR,
});

/** 事件是否表示失败（tool.post-execute 的结果字段方言多，只认显式失败标记）。 */
function isFailure(event) {
  if (!event || typeof event !== 'object') return false;
  const status = String(event.status || event.result || '').toLowerCase();
  if (status === 'error' || status === 'failed' || status === 'failure') return true;
  if (event.ok === false) return true;
  if (event.error) return true;
  return false;
}

/** 事件名归一化：优先用 event.topic，其次 event.type，最后原字符串。 */
function normalizeEvent(event) {
  if (typeof event === 'string') return event.trim();
  if (event && typeof event === 'object') {
    const name = event.topic || event.type || event.event || '';
    return String(name).trim();
  }
  return '';
}

/**
 * 纯 reducer：给定当前状态与事件，返回下一个状态。
 * 未知事件 → 状态不变，changed=false，并给出 reason（绝不猜）。
 * @param {string} state
 * @param {string|object} event
 * @returns {{state: string, changed: boolean, reason: string}}
 */
function reduceAgentEvent(state, event) {
  const current = STATES[String(state).toUpperCase()] || state || STATES.IDLE;
  const name = normalizeEvent(event);
  if (!name) {
    return { state: current, changed: false, reason: 'empty_event' };
  }
  const rule = TRANSITIONS[name];
  if (!rule) {
    return { state: current, changed: false, reason: `unknown_event:${name}` };
  }
  const next = rule(typeof event === 'object' && event !== null ? event : {});
  if (!next) {
    return { state: current, changed: false, reason: `no_target:${name}` };
  }
  return { state: next, changed: next !== current, reason: name };
}

/**
 * 多会话聚合：从一组会话状态里取优先级最高者。
 * @param {string[]} states
 * @returns {string}
 */
function pickDominant(states) {
  let best = STATES.IDLE;
  let bestRank = -1;
  for (const s of states || []) {
    const st = STATES[String(s).toUpperCase()] || s;
    const rank = PRIORITY[st];
    if (rank === undefined) continue;      // 未知状态不参与（不猜）
    if (rank > bestRank) {
      bestRank = rank;
      best = st;
    }
  }
  return best;
}

/**
 * 生成**壳层展示体**（HUD / 桌宠气泡用）——包含不受 NEKO 限制的 motion/label。
 * 只带状态可解释的信息；不含任何进度估计。
 * @param {string} state
 * @returns {{emotion: string, motion: string, label: string, state: string}}
 */
function toNekoPayload(state) {
  const st = STATES[String(state).toUpperCase()] || state || STATES.IDLE;
  const entry = EXPRESSION_MAP[st] || EXPRESSION_MAP[STATES.IDLE];
  return { state: st, emotion: entry.emotion, motion: entry.motion, label: entry.label };
}

/**
 * 生成**NEKO 注入请求体**（POST /api/lumo/emotion 的最小契约）。
 * 实测契约：`NEKO/N.E.K.O/main_routers/lumo_inject_router.py` 的 EmotionRequest
 * 只接受 `{lanlan_name, emotion, confidence?}`，且 emotion 会被归一化到 5 标准集。
 * 角色名缺失时返回 null —— 不猜角色，让调用方决定（fail closed）。
 * @param {string} state
 * @param {string} character lanlan_name
 * @returns {{lanlan_name: string, emotion: string}|null}
 */
function toNekoEmotionRequest(state, character) {
  const name = String(character || '').trim();
  if (!name) return null;
  const { emotion } = EXPRESSION_MAP[
    STATES[String(state).toUpperCase()] || state || STATES.IDLE
  ] || EXPRESSION_MAP[STATES.IDLE];
  return { lanlan_name: name, emotion };
}

/**
 * 会话注册表：跟踪每个会话的状态并给出聚合展示态。
 * 只存内存，进程退出即清（与 confirm_gate 同口径）。
 */
function createSessionRegistry() {
  const sessions = new Map();
  return {
    /** 应用一个会话事件，返回该会话的新状态。 */
    apply(sessionId, event) {
      const sid = String(sessionId || 'default');
      const prev = sessions.get(sid) || STATES.IDLE;
      const { state } = reduceAgentEvent(prev, event);
      sessions.set(sid, state);
      return state;
    },
    /** 当前应展示的状态（多会话取最优）。 */
    dominant() {
      return pickDominant([...sessions.values()]);
    },
    /** 显式移除会话（会话结束清理）。 */
    remove(sessionId) {
      return sessions.delete(String(sessionId || 'default'));
    },
    /** 只读快照。 */
    snapshot() {
      return Object.fromEntries(sessions);
    },
  };
}

module.exports = {
  STATES,
  PRIORITY,
  EXPRESSION_MAP,
  TRANSITIONS,
  NEKO_STANDARD_EMOTIONS,
  reduceAgentEvent,
  pickDominant,
  toNekoPayload,
  toNekoEmotionRequest,
  createSessionRegistry,
  _internal: { isFailure, normalizeEvent },
};
