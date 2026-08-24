/* ═══════════════════════════════════════════════════════════
   api.js — API 桩层
   纯静态项目无真实后端，此处模拟异步请求（带 400ms 延迟以呈现加载态）。
   未来接入真实后端时，仅需替换 fetchTasks 的实现，调用方无需改动。
   ═══════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  function delay(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  window.LumoAPI = {
    /** 获取 GitHub 任务列表（模拟 /api/tasks 接口） */
    async fetchTasks() {
      await delay(400);
      const data = (window.LumoMock && window.LumoMock.MOCK_TASKS) || [];
      // 返回副本，避免外部改动污染数据源
      return JSON.parse(JSON.stringify(data));
    }
  };
})();
