/* ═══════════════════════════════════════════════════════════
   app.js — 陆墨任务追踪面板 · 交互逻辑
   功能：
   1. GitHub 任务：加载（API 桩）、类型过滤、关键词搜索、刷新
   2. 日常计划：新建 / 完成切换 / 点击进度条调整 / 删除（localStorage 持久化）
   3. 主题切换：浅色 / 深色（localStorage + 系统偏好）
   4. 轻提示 Toast、标签页切换、响应式侧边栏
   ═══════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  /* ═══ 图标库：Lucide 风格内联 SVG（自包含，离线可用） ═══ */

  var ICONS = {
    'layout-dashboard': '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
    'refresh-cw': '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
    'github': '<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>',
    'calendar-check': '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><path d="m9 16 2 2 4-4"/>',
    'loader-2': '<path d="M21 12a9 9 0 1 1-6.219-8.56"/>',
    'inbox': '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    'circle-dot': '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="1"/>',
    'git-pull-request': '<circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 0 1 2 2v7M6 9v12"/>',
    'calendar': '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
    'message-circle': '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    'triangle-alert': '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    'clipboard-list': '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4M12 16h4M8 11h.01M8 16h.01"/>',
    'plus': '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    'tag': '<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.83Z"/><line x1="7" y1="7" x2="7.01" y2="7"/>',
    'check': '<polyline points="20 6 9 17 4 12"/>',
    'trash-2': '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>',
    'alert-circle': '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
    'clock': '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    'moon': '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    'sun': '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    'search': '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>'
  };

  /** 生成内联 SVG 图标字符串（便于在模板中直接嵌入） */
  function icon(name, cls) {
    return '<svg class="lucide ' + (cls || '') + '" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (ICONS[name] || '') + '</svg>';
  }

  /* ═══ 常量 ═══ */
  var REPO = 'fe1iscurc0r/scratchpad';
  var STORAGE_KEY = 'lumo-task-plans-v1';
  var THEME_KEY = 'lumo-task-theme';

  /* ═══ 状态 ═══ */
  var allTasks = [];
  var currentFilter = 'all';   // all | issue | pr
  var searchQuery = '';        // 搜索关键词
  var currentTab = 'github';
  var plans = [];
  var planFilter = 'all';      // all | doing | done

  /* ═══ 通用工具 ═══ */

  function $(id) { return document.getElementById(id); }

  function setText(id, value) {
    var el = $(id);
    if (el) el.textContent = value;
  }

  function escapeHtml(str) {
    return String(str == null ? '' : str).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function formatDate(iso) {
    if (!iso) return '-';
    var d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  }

  function hasLabel(item, name) {
    return (item.labels || []).some(function (l) { return (l.name || l).toLowerCase() === name.toLowerCase(); });
  }

  function labelClass(name) {
    var n = (name || '').toLowerCase();
    if (n === 'p0') return 'label-p0';
    if (n === 'p1') return 'label-p1';
    if (n === 'p2') return 'label-p2';
    if (n === '改进') return 'label-improvement';
    if (n === '合规') return 'label-compliance';
    return 'status-open';
  }

  /* ═══ Toast 轻提示 ═══ */
  var toastTimer = null;
  function showToast(msg) {
    var el = $('toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove('show'); }, 2200);
  }

  /* ═══ 主题切换 ═══ */
  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem(THEME_KEY); } catch (e) {}
    var prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    setTheme(saved ? saved === 'dark' : prefersDark, true);
  }

  function setTheme(dark, skipPersist) {
    var root = document.documentElement;
    root.classList.toggle('dark', dark);
    root.classList.toggle('light', !dark);
    root.setAttribute('data-theme', dark ? 'dark' : 'light');
    if (!skipPersist) {
      try { localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light'); } catch (e) {}
    }
    var btn = $('theme-toggle');
    if (btn) btn.innerHTML = icon(dark ? 'sun' : 'moon', 'w-4 h-4');
  }

  /* ═══ GitHub 任务 ═══ */
  function loadTasks() {
    var refreshBtn = $('refresh-btn');
    var list = $('card-list');
    if (refreshBtn) refreshBtn.disabled = true;
    list.innerHTML = '<div class="loading-state">' + icon('loader-2', 'w-6 h-6 animate-spin') + '<span>正在加载任务数据…</span></div>';

    (window.LumoAPI.fetchTasks() || Promise.resolve([])).then(function (data) {
      allTasks = data || [];
      $('last-updated').textContent = '更新于 ' + new Date().toLocaleString('zh-CN');
      renderStats(allTasks);
      renderCards(allTasks);
      if (refreshBtn) refreshBtn.disabled = false;
      showToast('任务数据已刷新');
    }).catch(function (err) {
      console.warn('加载任务失败：', err);
      list.innerHTML = '<div class="error-state">' + icon('triangle-alert', 'w-6 h-6') + '<span>任务数据加载失败</span></div>';
      if (refreshBtn) refreshBtn.disabled = false;
    });
  }

  function renderStats(tasks) {
    var openTasks = tasks.filter(function (t) { return (t.state || 'OPEN').toUpperCase() !== 'CLOSED'; });
    var today = new Date().toISOString().slice(0, 10);
    setText('stat-open', openTasks.length);
    setText('stat-issues', openTasks.filter(function (t) { return t.type === 'issue'; }).length);
    setText('stat-prs', openTasks.filter(function (t) { return t.type === 'pr'; }).length);
    setText('stat-today', tasks.filter(function (t) { return (t.createdAt || '').slice(0, 10) === today; }).length);
    setText('stat-p0', tasks.filter(function (t) { return hasLabel(t, 'P0'); }).length);
    setText('stat-p1', tasks.filter(function (t) { return hasLabel(t, 'P1'); }).length);
    setText('stat-p2', tasks.filter(function (t) { return hasLabel(t, 'P2'); }).length);
    setText('stat-improvement', tasks.filter(function (t) { return hasLabel(t, '改进'); }).length);
    setText('stat-compliance', tasks.filter(function (t) { return hasLabel(t, '合规'); }).length);
  }

  function renderCards(tasks) {
    var list = $('card-list');
    var filtered = tasks.filter(function (t) {
      if (currentFilter !== 'all' && t.type !== currentFilter) return false;
      if (searchQuery && !((t.title || '') + ' ' + (t.number || '') + ' ' + (t.head || '')).toLowerCase().includes(searchQuery)) return false;
      return true;
    });

    if (filtered.length === 0) {
      list.innerHTML = '<div class="empty-state">' + icon('inbox', 'w-8 h-8') + '<span>' + (tasks.length === 0 ? '暂无任务数据' : '没有匹配的任务') + '</span></div>';
      return;
    }
    list.innerHTML = filtered.map(function (t) {
      return t.type === 'issue' ? renderIssue(t) : renderPR(t);
    }).join('');
  }

  function renderIssue(issue) {
    var state = (issue.state || 'OPEN').toUpperCase();
    var url = 'https://github.com/' + REPO + '/issues/' + issue.number;
    var labels = (issue.labels || []).map(function (l) {
      var name = typeof l === 'string' ? l : l.name;
      return '<span class="label-pill ' + labelClass(name) + '">' + escapeHtml(name) + '</span>';
    }).join('');
    return '<article class="task-card">' +
      '<div class="task-card-header">' +
        '<div class="task-icon">' + icon('circle-dot', 'w-4 h-4') + '</div>' +
        '<div class="task-title"><a href="' + url + '" target="_blank" rel="noopener noreferrer">#' + issue.number + ' ' + escapeHtml(issue.title) + '</a></div>' +
      '</div>' +
      '<div class="task-meta">' +
        '<span class="status-badge ' + (state === 'OPEN' ? 'status-open' : 'status-closed') + '">' + (state === 'OPEN' ? 'OPEN' : 'CLOSED') + '</span>' +
        labels +
      '</div>' +
      '<div class="task-meta">' +
        '<span>' + icon('calendar', 'w-3 h-3') + formatDate(issue.createdAt) + '</span>' +
        '<span>' + icon('message-circle', 'w-3 h-3') + (issue.comments || 0) + '</span>' +
      '</div>' +
    '</article>';
  }

  function renderPR(pr) {
    var url = 'https://github.com/' + REPO + '/pull/' + pr.number;
    var ciClass = pr.ciStatus === 'success' ? 'ci-success' : pr.ciStatus === 'failure' ? 'ci-failure' : 'ci-pending';
    var ciText = pr.ciStatus === 'success' ? '通过' : pr.ciStatus === 'failure' ? '失败' : '进行中';
    return '<article class="task-card">' +
      '<div class="task-card-header">' +
        '<div class="task-icon">' + icon('git-pull-request', 'w-4 h-4') + '</div>' +
        '<div class="task-title"><a href="' + url + '" target="_blank" rel="noopener noreferrer">#' + pr.number + ' ' + escapeHtml(pr.title) + '</a></div>' +
      '</div>' +
      '<div class="task-meta">' +
        '<span class="status-badge status-open">PR</span>' +
        '<span class="font-mono">' + escapeHtml(pr.head || '-') + ' → ' + escapeHtml(pr.base || '-') + '</span>' +
      '</div>' +
      '<div class="task-meta">' +
        '<span><span class="ci-dot ' + ciClass + '"></span>CI ' + ciText + '</span>' +
        '<span>' + icon('calendar', 'w-3 h-3') + formatDate(pr.createdAt) + '</span>' +
      '</div>' +
    '</article>';
  }

  function setFilter(filter) {
    currentFilter = filter;
    document.querySelectorAll('.filter-bar .btn[data-filter]').forEach(function (btn) {
      btn.classList.toggle('filter-active', btn.dataset.filter === filter);
    });
    renderCards(allTasks);
  }

  /* ═══ 标签页切换 ═══ */
  function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach(function (btn) {
      btn.classList.toggle('tab-active', btn.dataset.tab === tab);
    });
    $('tab-github').style.display = tab === 'github' ? '' : 'none';
    $('tab-plans').style.display = tab === 'plans' ? '' : 'none';
    if (tab === 'plans') {
      renderPlanStats();
      renderPlans();
    }
  }

  /* ═══ 日常计划（localStorage 持久化） ═══ */

  function loadPlans() {
    try {
      var saved = localStorage.getItem(STORAGE_KEY);
      plans = saved ? JSON.parse(saved) : window.LumoMock.SAMPLE_PLANS.slice();
    } catch (e) {
      plans = window.LumoMock.SAMPLE_PLANS.slice();
    }
  }

  function savePlans() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(plans)); } catch (e) {}
  }

  function addPlan(plan) {
    plans.unshift({
      id: 'p' + Date.now(),
      title: plan.title,
      type: plan.type,
      priority: plan.priority,
      progress: 0,
      done: false,
      deadline: plan.deadline || null,
      createdAt: Date.now()
    });
    savePlans();
    renderPlanStats();
    renderPlans();
    showToast('已添加计划「' + plan.title + '」');
  }

  function togglePlanDone(id) {
    var plan = plans.find(function (p) { return p.id === id; });
    if (!plan) return;
    plan.done = !plan.done;
    plan.progress = plan.done ? 100 : (plan.progress < 100 ? plan.progress : 0);
    savePlans();
    renderPlanStats();
    renderPlans();
    showToast(plan.done ? '已完成：「' + plan.title + '」' : '已恢复进行中：「' + plan.title + '」');
  }

  function setPlanProgress(id, progress) {
    var plan = plans.find(function (p) { return p.id === id; });
    if (!plan) return;
    plan.progress = Math.max(0, Math.min(100, progress));
    plan.done = plan.progress >= 100;
    savePlans();
    renderPlanStats();
    renderPlans();
  }

  function deletePlan(id) {
    var target = plans.find(function (p) { return p.id === id; });
    plans = plans.filter(function (p) { return p.id !== id; });
    savePlans();
    renderPlanStats();
    renderPlans();
    if (target) showToast('已删除计划「' + target.title + '」');
  }

  function renderPlanStats() {
    var total = plans.length;
    var done = plans.filter(function (p) { return p.done; }).length;
    var todayStr = new Date().toISOString().slice(0, 10);
    var todayDeadline = plans.filter(function (p) {
      return p.deadline && !p.done && new Date(p.deadline).toISOString().slice(0, 10) === todayStr;
    }).length;
    setText('plan-total', total);
    setText('plan-done', done);
    setText('plan-doing', total - done);
    setText('plan-today', todayDeadline);

    var pct = total > 0 ? Math.round(plans.reduce(function (s, p) { return s + p.progress; }, 0) / total) : 0;
    setText('plan-progress-pct', pct + '%');
    var fill = $('plan-progress-fill');
    if (fill) fill.style.width = pct + '%';
  }

  function isOverdue(deadline, done) {
    return !done && !!deadline && new Date(deadline) < new Date();
  }

  function isDeadlineSoon(deadline) {
    if (!deadline) return false;
    var diff = new Date(deadline) - new Date();
    return diff > 0 && diff < 24 * 3600 * 1000;
  }

  function formatDeadline(deadline) {
    if (!deadline) return '无截止';
    var d = new Date(deadline);
    var now = new Date();
    var diff = d - now;
    var dayDiff = Math.ceil(diff / (1000 * 60 * 60 * 24));
    var timeStr = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    if (diff < 0) return '已逾期';
    if (dayDiff === 0) return '今天 ' + timeStr;
    if (dayDiff === 1) return '明天 ' + timeStr;
    return d.toLocaleDateString('zh-CN') + ' ' + timeStr;
  }

  function priorityClass(p) {
    if (p === 'P0') return 'label-p0';
    if (p === 'P1') return 'label-p1';
    return 'label-p2';
  }

  function renderPlans() {
    var list = $('plan-list');
    var filtered = plans.slice();
    if (planFilter === 'doing') filtered = filtered.filter(function (p) { return !p.done; });
    else if (planFilter === 'done') filtered = filtered.filter(function (p) { return p.done; });

    // 排序：P0 > P1 > P2，未完成优先
    var priorityOrder = { P0: 0, P1: 1, P2: 2 };
    filtered.sort(function (a, b) {
      if (a.done !== b.done) return a.done ? 1 : -1;
      return (priorityOrder[a.priority] == null ? 3 : priorityOrder[a.priority]) - (priorityOrder[b.priority] == null ? 3 : priorityOrder[b.priority]);
    });

    if (filtered.length === 0) {
      var msg = planFilter === 'done' ? '还没有已完成的计划' : planFilter === 'doing' ? '所有计划都完成了！' : '还没有计划，点击「新建」添加第一条';
      list.innerHTML = '<div class="empty-state">' + icon('clipboard-list', 'w-8 h-8') + '<span>' + msg + '</span></div>';
      return;
    }

    list.innerHTML = filtered.map(renderPlanCard).join('');

    // 绑定计划卡片交互
    filtered.forEach(function (p) {
      var card = list.querySelector('[data-plan-id="' + p.id + '"]');
      if (!card) return;
      card.querySelector('.plan-checkbox').addEventListener('click', function () { togglePlanDone(p.id); });
      card.querySelector('[data-action="delete"]').addEventListener('click', function () {
        if (confirm('确认删除这条计划？')) deletePlan(p.id);
      });
      var track = card.querySelector('.plan-progress-track');
      track.addEventListener('click', function (e) {
        var rect = track.getBoundingClientRect();
        var pct = Math.round(((e.clientX - rect.left) / rect.width) * 100);
        setPlanProgress(p.id, pct);
      });
    });
  }

  function renderPlanCard(plan) {
    var overdue = isOverdue(plan.deadline, plan.done);
    var soon = isDeadlineSoon(plan.deadline);
    var deadlineClass = (overdue || soon) ? 'deadline-soon' : '';
    var deadlineIcon = overdue ? 'alert-circle' : 'clock';
    return '<article class="plan-card ' + (plan.done ? 'is-done' : '') + '" data-plan-id="' + plan.id + '">' +
      '<div class="plan-card-header">' +
        '<button class="plan-checkbox ' + (plan.done ? 'is-checked' : '') + '" type="button" aria-label="切换完成状态">' +
          (plan.done ? icon('check', 'w-3.5 h-3.5') : '') +
        '</button>' +
        '<div class="plan-card-title">' + escapeHtml(plan.title) + '</div>' +
      '</div>' +
      '<div class="plan-meta">' +
        '<span class="plan-type-badge type-' + escapeHtml(plan.type) + '">' + icon('tag', 'w-3 h-3') + escapeHtml(plan.type) + '</span>' +
        '<span class="label-pill ' + priorityClass(plan.priority) + '">' + escapeHtml(plan.priority) + '</span>' +
      '</div>' +
      '<div class="plan-progress">' +
        '<div class="plan-progress-top"><span>进度</span><span>' + plan.progress + '%</span></div>' +
        '<div class="plan-progress-track" title="点击调整进度">' +
          '<div class="plan-progress-fill" style="width:' + plan.progress + '%"></div>' +
        '</div>' +
      '</div>' +
      '<div class="plan-meta">' +
        '<span class="' + deadlineClass + '">' + icon(deadlineIcon, 'w-3 h-3') + formatDeadline(plan.deadline) + '</span>' +
      '</div>' +
      '<div class="plan-actions">' +
        '<button class="plan-action-btn is-danger" data-action="delete" type="button">' +
          icon('trash-2', 'w-3.5 h-3.5') + '<span>删除</span>' +
        '</button>' +
      '</div>' +
    '</article>';
  }

  /* ═══ 计划表单 ═══ */
  function togglePlanForm(show) {
    var form = $('plan-form');
    if (show === undefined) show = form.style.display === 'none';
    form.style.display = show ? '' : 'none';
    if (show) {
      var titleInput = $('plan-title-input');
      if (titleInput) setTimeout(function () { titleInput.focus(); }, 50);
    }
  }

  function resetPlanForm() {
    $('plan-title-input').value = '';
    $('plan-type-input').value = '待办';
    $('plan-priority-input').value = 'P1';
    $('plan-deadline-input').value = '';
  }

  function handleSavePlan() {
    var title = $('plan-title-input').value.trim();
    var type = $('plan-type-input').value;
    var priority = $('plan-priority-input').value;
    var deadlineVal = $('plan-deadline-input').value;
    var deadline = deadlineVal ? new Date(deadlineVal).toISOString() : null;

    if (!title) { showToast('请输入计划标题'); $('plan-title-input').focus(); return; }
    addPlan({ title: title, type: type, priority: priority, deadline: deadline });
    resetPlanForm();
    togglePlanForm(false);
  }

  function setPlanFilter(filter) {
    planFilter = filter;
    document.querySelectorAll('#tab-plans .filter-bar .btn[data-plan-filter]').forEach(function (btn) {
      btn.classList.toggle('filter-active', btn.dataset.planFilter === filter);
    });
    renderPlans();
  }

  /* ═══ 初始化 ═══ */
  function init() {
    // 主题
    initTheme();
    $('theme-toggle').addEventListener('click', function () {
      setTheme(!document.documentElement.classList.contains('dark'));
    });

    // 任务：刷新 / 过滤 / 搜索
    $('refresh-btn').addEventListener('click', loadTasks);
    document.querySelectorAll('#tab-github .filter-bar .btn[data-filter]').forEach(function (btn) {
      btn.addEventListener('click', function () { setFilter(btn.dataset.filter); });
    });
    $('task-search').addEventListener('input', function (e) {
      searchQuery = e.target.value.trim().toLowerCase();
      var box = e.target.closest('.search-box');
      if (box) box.classList.toggle('has-value', searchQuery.length > 0);
      renderCards(allTasks);
    });

    // 标签页
    document.querySelectorAll('.tab-btn').forEach(function (btn) {
      btn.addEventListener('click', function () { switchTab(btn.dataset.tab); });
    });

    // 计划：表单 / 过滤
    $('add-plan-btn').addEventListener('click', function () { togglePlanForm(true); });
    $('plan-cancel-btn').addEventListener('click', function () { togglePlanForm(false); });
    $('plan-save-btn').addEventListener('click', handleSavePlan);
    $('plan-title-input').addEventListener('keydown', function (e) { if (e.key === 'Enter') handleSavePlan(); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && $('plan-form').style.display !== 'none') togglePlanForm(false);
    });
    document.querySelectorAll('#tab-plans .filter-bar .btn[data-plan-filter]').forEach(function (btn) {
      btn.addEventListener('click', function () { setPlanFilter(btn.dataset.planFilter); });
    });

    // 数据
    loadPlans();
    renderPlanStats();
    loadTasks();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
