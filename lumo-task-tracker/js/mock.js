/* ═══════════════════════════════════════════════════════════
   mock.js — 演示数据（纯静态项目内置，无真实后端）
   数据与设计稿中演示数据保持一致
   ═══════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  /* GitHub 任务演示数据（Issue / PR） */
  const MOCK_TASKS = [
    { type: 'issue', number: 12, title: '修复 P0 频率白名单校验绕过问题', labels: [{ name: 'P0' }], state: 'OPEN', createdAt: '2026-08-17T10:00:00Z', comments: 3 },
    { type: 'issue', number: 11, title: '改进 IC-705 控制面板响应速度', labels: [{ name: 'P1' }, { name: '改进' }], state: 'OPEN', createdAt: '2026-08-16T08:30:00Z', comments: 1 },
    { type: 'issue', number: 9, title: '合规检查：业余频段限制与告警', labels: [{ name: '合规' }], state: 'OPEN', createdAt: '2026-08-14T12:00:00Z', comments: 0 },
    { type: 'issue', number: 7, title: 'P2 文档补充：mailslot 通信协议说明', labels: [{ name: 'P2' }], state: 'OPEN', createdAt: '2026-08-10T09:15:00Z', comments: 2 },
    { type: 'pr', number: 14, title: '添加 mailslot 通信心跳保活', head: 'feature/mailslot-heartbeat', base: 'main', ciStatus: 'success', createdAt: '2026-08-18T06:00:00Z' },
    { type: 'pr', number: 13, title: '重构频率设置接口以支持 whitelisting', head: 'refactor/freq-api', base: 'main', ciStatus: 'pending', createdAt: '2026-08-17T16:00:00Z' }
  ];

  /* 截止时间辅助：n 天后 18:00 */
  function addDays(n) {
    const d = new Date();
    d.setDate(d.getDate() + n);
    d.setHours(18, 0, 0, 0);
    return d;
  }

  /* 日常计划演示数据 */
  const SAMPLE_PLANS = [
    { id: 'p1', title: '完成 IC-705 频率白名单功能测试', type: '工作', priority: 'P0', progress: 75, done: false, deadline: addDays(1).toISOString(), createdAt: Date.now() - 86400000 },
    { id: 'p2', title: '阅读《代码整洁之道》第 7 章', type: '学习', priority: 'P1', progress: 40, done: false, deadline: addDays(2).toISOString(), createdAt: Date.now() - 172800000 },
    { id: 'p3', title: '晨跑 5 公里', type: '健康', priority: 'P2', progress: 100, done: true, deadline: new Date().toISOString(), createdAt: Date.now() - 259200000 },
    { id: 'p4', title: '整理周末购物清单', type: '生活', priority: 'P2', progress: 20, done: false, deadline: addDays(3).toISOString(), createdAt: Date.now() - 43200000 },
    { id: 'p5', title: '回复邮件 & 整理待办事项', type: '待办', priority: 'P1', progress: 60, done: false, deadline: addDays(1).toISOString(), createdAt: Date.now() - 21600000 }
  ];

  window.LumoMock = { MOCK_TASKS, SAMPLE_PLANS };
})();
