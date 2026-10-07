/**
 * agent-state-expression.test.js
 * 工单202 任务四验收：≥4 个 agent 状态触发不同表情；状态机转换与聚合语义正确。
 * 运行：node --test neko-electron-shell/src/agent-state-expression.test.js
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert');

const S = require('./agent-state-expression');

test('验收核心：情绪 ⊆ NEKO 标准集且 ≥4 种；6 状态 motion 两两不同', () => {
  const emotions = new Set();
  const motions = new Set();
  for (const key of Object.keys(S.STATES)) {
    const payload = S.toNekoPayload(S.STATES[key]);
    assert.ok(S.NEKO_STANDARD_EMOTIONS.includes(payload.emotion),
      `${key} 的 emotion 必须 ⊆ NEKO 标准集，实际 ${payload.emotion}`);
    assert.ok(payload.motion, `${key} 必须有 motion`);
    emotions.add(payload.emotion);
    motions.add(payload.motion);
  }
  assert.ok(emotions.size >= 4, `不同情绪数须 ≥4（验收），实际 ${emotions.size}`);
  assert.strictEqual(motions.size, 6, '6 个状态的 motion 必须两两不同');
});

test('toNekoEmotionRequest 对齐注入契约；无角色名时 fail closed（null）', () => {
  assert.deepStrictEqual(
    S.toNekoEmotionRequest(S.STATES.CELEBRATE, '陆墨'),
    { lanlan_name: '陆墨', emotion: 'happy' });
  assert.deepStrictEqual(
    S.toNekoEmotionRequest('thinking', '陆墨'),
    { lanlan_name: '陆墨', emotion: 'neutral' });
  assert.strictEqual(S.toNekoEmotionRequest(S.STATES.IDLE, ''), null);
  assert.strictEqual(S.toNekoEmotionRequest(S.STATES.IDLE, '   '), null);
  assert.strictEqual(S.toNekoEmotionRequest(S.STATES.IDLE), null);
});

test('标签不含任何进度数字（不编造进度）', () => {
  for (const key of Object.keys(S.STATES)) {
    const { label } = S.toNekoPayload(S.STATES[key]);
    assert.ok(!/\d|%/.test(label), `label 不得含数字/百分比: ${label}`);
    assert.ok(!/阶段|phase/i.test(label), `label 不得编造阶段: ${label}`);
  }
});

test('一轮开始：user_input → thinking', () => {
  const r = S.reduceAgentEvent(S.STATES.IDLE, 'user_input');
  assert.strictEqual(r.state, S.STATES.THINKING);
  assert.strictEqual(r.changed, true);
  assert.strictEqual(r.reason, 'user_input');
});

test('event_bus 全名主题同样识别（lumo.* 前缀）', () => {
  assert.strictEqual(
    S.reduceAgentEvent(S.STATES.THINKING, 'lumo.tool.pre-execute').state,
    S.STATES.WORKING);
  assert.strictEqual(
    S.reduceAgentEvent(S.STATES.IDLE, 'lumo.user.input.received').state,
    S.STATES.THINKING);
});

test('工具后置：成功回思考、失败进错误', () => {
  const ok = S.reduceAgentEvent(S.STATES.WORKING, { event: 'tool_post_execute', status: 'ok' });
  assert.strictEqual(ok.state, S.STATES.THINKING, '整理工具结果 → 回到思考');

  const fail = S.reduceAgentEvent(S.STATES.WORKING, { event: 'tool_post_execute', status: 'error' });
  assert.strictEqual(fail.state, S.STATES.ERROR);

  const failByFlag = S.reduceAgentEvent(S.STATES.WORKING, { event: 'tool_post_execute', ok: false });
  assert.strictEqual(failByFlag.state, S.STATES.ERROR, 'ok:false 也算失败');

  const failByError = S.reduceAgentEvent(S.STATES.WORKING, { topic: 'lumo.tool.post-execute', error: 'boom' });
  assert.strictEqual(failByError.state, S.STATES.ERROR, 'error 字段也算失败');
});

test('确认门挂起 → wait（用户可行动的阻塞最高优先暴露）', () => {
  assert.strictEqual(
    S.reduceAgentEvent(S.STATES.WORKING, 'confirm_pending').state, S.STATES.WAIT);
  assert.strictEqual(
    S.reduceAgentEvent(S.STATES.WAIT, 'confirm_resolved').state, S.STATES.THINKING);
});

test('完成与收尾：turn_completed → celebrate；session_end → idle', () => {
  assert.strictEqual(
    S.reduceAgentEvent(S.STATES.WORKING, 'turn_completed').state, S.STATES.CELEBRATE);
  assert.strictEqual(
    S.reduceAgentEvent(S.STATES.CELEBRATE, 'session_end').state, S.STATES.IDLE);
});

test('未知事件/空事件不改写状态，并说明原因（绝不猜）', () => {
  const unknown = S.reduceAgentEvent(S.STATES.WORKING, 'totally_unknown_event');
  assert.strictEqual(unknown.state, S.STATES.WORKING);
  assert.strictEqual(unknown.changed, false);
  assert.strictEqual(unknown.reason, 'unknown_event:totally_unknown_event');

  const empty = S.reduceAgentEvent(S.STATES.WAIT, '');
  assert.strictEqual(empty.state, S.STATES.WAIT);
  assert.strictEqual(empty.reason, 'empty_event');
});

test('同一事件在当前状态下不重复触发（changed=false）', () => {
  const r = S.reduceAgentEvent(S.STATES.THINKING, 'user_input');
  assert.strictEqual(r.state, S.STATES.THINKING);
  assert.strictEqual(r.changed, false);
});

test('多会话聚合优先级：wait > error > working > thinking > celebrate > idle', () => {
  const order = [
    [S.STATES.THINKING, S.STATES.IDLE, S.STATES.CELEBRATE],
    [S.STATES.WORKING, S.STATES.THINKING],
    [S.STATES.ERROR, S.STATES.WORKING],
    [S.STATES.WAIT, S.STATES.ERROR],
  ];
  const expected = [S.STATES.THINKING, S.STATES.WORKING, S.STATES.ERROR, S.STATES.WAIT];
  order.forEach((states, i) => {
    assert.strictEqual(S.pickDominant(states), expected[i], JSON.stringify(states));
  });
  assert.strictEqual(S.pickDominant([]), S.STATES.IDLE, '空集合 → 待机');
  assert.strictEqual(S.pickDominant(['bogus_state']), S.STATES.IDLE, '未知状态不参与聚合');
});

test('会话注册表：多会话各自记状态，展示取主导，remove 生效', () => {
  const reg = S.createSessionRegistry();
  reg.apply('s1', 'user_input');              // s1 → thinking
  reg.apply('s2', 'tool_pre_execute');        // s2 → working
  assert.strictEqual(reg.dominant(), S.STATES.WORKING);

  reg.apply('s1', 'confirm_pending');         // s1 → wait（压过 working）
  assert.strictEqual(reg.dominant(), S.STATES.WAIT);
  assert.deepStrictEqual(reg.snapshot(), { s1: S.STATES.WAIT, s2: S.STATES.WORKING });

  reg.remove('s1');
  assert.strictEqual(reg.dominant(), S.STATES.WORKING, '移除后回落到次优');
});

test('toNekoPayload 形态符合展示契约（state/emotion/motion/label）', () => {
  const p = S.toNekoPayload(S.STATES.WAIT);
  assert.deepStrictEqual(Object.keys(p).sort(), ['emotion', 'label', 'motion', 'state']);
  assert.strictEqual(p.state, 'wait');
  assert.ok(S.NEKO_STANDARD_EMOTIONS.includes(p.emotion), p.emotion);
});

test('大小写不敏感（状态传入小写/大写均可用）', () => {
  assert.strictEqual(S.toNekoPayload('idle').emotion, 'neutral');
  assert.strictEqual(S.toNekoPayload('IDLE').emotion, 'neutral');
  assert.strictEqual(S.pickDominant(['IDLE', 'WORKING']), S.STATES.WORKING);
});

test('未知状态入参回落到 idle 表情（不抛错、不猜）', () => {
  const p = S.toNekoPayload('nonexistent');
  assert.strictEqual(p.emotion, 'neutral');
});
