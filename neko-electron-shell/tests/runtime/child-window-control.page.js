'use strict';

/**
 * 页面侧探针：只通过 `window.nekoWindowControl` 与主进程交互。
 * 结果用 `HARNESS_RESULT <json>` 打到 console，由主进程收集。
 */

(function () {
  var checks = [];
  var observed = {};

  function check(name, pass, detail) {
    checks.push({ name: name, pass: !!pass, detail: detail });
  }

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  function report() {
    console.log('HARNESS_RESULT ' + JSON.stringify({
      mode: 'child-window-control',
      userAgentIsElectron: /Electron\//.test(navigator.userAgent),
      checks: checks,
      observed: observed,
      pass: checks.every(function (c) { return c.pass; }),
    }));
  }

  async function run() {
    var api = window.nekoWindowControl;

    check('nekoWindowControl 已通过 contextBridge 暴露', !!api && typeof api === 'object', typeof api);
    check('四个方法都是可调用函数',
      !!api && ['minimize', 'restore', 'maximize', 'isMaximized'].every(function (k) {
        return typeof api[k] === 'function';
      }),
      api ? Object.keys(api).join(',') : null);

    // 隔离生效的旁证：页面世界拿不到 preload 的 require / ipcRenderer
    check('页面世界看不到 require（contextIsolation 生效）', typeof window.require === 'undefined');
    check('页面世界看不到 ipcRenderer（contextIsolation 生效）', typeof window.ipcRenderer === 'undefined');

    var initial = await api.isMaximized();
    check('初始未最大化（isMaximized 返回 false）', initial === false, initial);

    var r1 = await api.maximize();
    check('maximize 返回 {ok:true, isMaximized:true}', !!r1 && r1.ok === true && r1.isMaximized === true,
      JSON.stringify(r1));
    await sleep(400);
    var afterMax = await api.isMaximized();
    check('isMaximized() 读到 true', afterMax === true, afterMax);

    var r2 = await api.maximize();
    check('再次 maximize 切换回 false', !!r2 && r2.ok === true && r2.isMaximized === false, JSON.stringify(r2));
    await sleep(400);
    var afterToggle = await api.isMaximized();
    check('isMaximized() 读到 false', afterToggle === false, afterToggle);

    var r3 = await api.maximize();
    check('第三次 maximize 回到 true', !!r3 && r3.ok === true && r3.isMaximized === true, JSON.stringify(r3));
    await sleep(300);

    var r4 = await api.restore();
    check('restore 返回 {ok:true}', !!r4 && r4.ok === true, JSON.stringify(r4));
    await sleep(300);
    // 记实际语义：处理器的 restore 只在最小化时 restore()，其余情况 show+focus，
    // 所以它对最大化状态**不生效**。这条写成断言是为了钉住现状，避免以后误以为它会还原。
    var afterRestore = await api.isMaximized();
    observed.restoreLeavesMaximized = afterRestore;
    check('restore 不解除最大化（restore 语义 = 最小化恢复 + 聚焦）', afterRestore === true, afterRestore);

    var r5 = await api.minimize();
    check('minimize 返回 {ok:true}', !!r5 && r5.ok === true, JSON.stringify(r5));
    await sleep(500);

    var r6 = await api.restore();
    check('最小化后 restore 返回 {ok:true}', !!r6 && r6.ok === true, JSON.stringify(r6));
    await sleep(600);

    // 收尾复位：先解除最大化，再确认 isMaximized 为 false（主进程还会独立核对最终状态）
    var r7 = await api.maximize();
    check('收尾：解除最大化', !!r7 && r7.ok === true && r7.isMaximized === false, JSON.stringify(r7));
    await sleep(400);
    var finalMax = await api.isMaximized();
    check('收尾后 isMaximized() = false', finalMax === false, finalMax);

    report();
  }

  run().catch(function (err) {
    check('探针自身未抛异常', false, String(err && err.stack ? err.stack : err).slice(0, 300));
    report();
  });
})();
