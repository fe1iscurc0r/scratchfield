// WO-270 T1 (P0-9): Steam 工坊条目里的不可信字段不得进 HTML。
//
// 跑的是 static/js/character_card_manager/subscriptions-and-scan.js 的真实源码：
// 列表走 renderSubscriptionsPage()，详情走 viewItemDetails()（window.fetch 被换成内存
// 响应，真实 .then 分支产出的 innerHTML 字符串被收下来检查）。没有复制生产代码。
//
// 三层，缺一层的绿灯都不算数：
//   1) 纯函数：safeWorkshopImageUrl 的放行/回落表，safeProgressWidth 的取值域；
//   2) 出口串：恶意样本喂进真实渲染路径，断言属性逃逸不可达、src 不是 javascript:/data:；
//   3) 变异对照：在同一份源码上把 escapeHtml 或 safeWorkshopImageUrl 单独换成恒等实现，
//      断言第 2 层这时必须失败。没有第 3 层，第 2 层可能只是在测一条永真正则。
//
// escapeHtml 用标记从 core-and-upload.js 切真身，不抄——抄的那份会腐烂。

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const JS_DIR = path.resolve(__dirname, '../../static/js/character_card_manager');
const WORKSHOP_FILE = path.join(JS_DIR, 'subscriptions-and-scan.js');
const CORE_FILE = path.join(JS_DIR, 'core-and-upload.js');
const ESCAPE_START = 'function escapeHtml(text) {';
const ESCAPE_END = '\n\n// 加载状态管理器';

const FALLBACK_ICON = '../static/icons/Steam_icon_logo.png';
const MALICIOUS_TITLE = '"><img src=x onerror=alert(1)>';
const MALICIOUS_URL = 'javascript:alert(1)';

const failures = [];

function assert(condition, message) {
  if (!condition) failures.push(message);
}

function readSource(file) {
  return fs.readFileSync(file, 'utf8');
}

function escapeHtmlSource() {
  const source = readSource(CORE_FILE);
  const start = source.indexOf(ESCAPE_START);
  const end = source.indexOf(ESCAPE_END, start);
  if (start < 0 || end <= start) {
    throw new Error(`escapeHtml block not found in ${path.basename(CORE_FILE)} - marker drifted`);
  }
  return source.slice(start, end);
}

function makeCaptureElement(id) {
  const element = {
    id,
    dataset: {},
    style: {},
    textContent: '',
    assignedHtml: '',
    addEventListener() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
    contains() { return true; },
    setAttribute(name, value) { element[name] = String(value); },
  };
  Object.defineProperty(element, 'innerHTML', {
    get: () => element.assignedHtml,
    set: (value) => { element.assignedHtml = String(value); },
  });
  return element;
}

function buildSandbox(options) {
  const opts = options || {};
  const pageBase = opts.pageBase || 'http://127.0.0.1:48911/character_card_manager';
  const elements = {
    'subscriptions-list': makeCaptureElement('subscriptions-list'),
    itemDetailContent: makeCaptureElement('itemDetailContent'),
    modalTitle: makeCaptureElement('modalTitle'),
    itemDetailsModal: makeCaptureElement('itemDetailsModal'),
  };

  const documentStub = {
    baseURI: pageBase,
    documentElement: { style: {} },
    getElementById: (id) => elements[id] || null,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: () => {},
    createElement: () => makeCaptureElement('created'),
  };

  const windowStub = {
    location: { href: pageBase, search: '', origin: pageBase },
    localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    addEventListener: () => {},
    open: () => null,
    alert: () => {},
    confirm: () => false,
    close: () => {},
    fetch: () => Promise.reject(new Error('network is disabled in this harness')),
    setTimeout: () => 0,
    console,
  };

  const context = {
    window: windowStub,
    document: documentStub,
    navigator: { userAgent: 'harness' },
    console,
    URL,
    URLSearchParams,
    Object,
    Array,
    String,
    Number,
    Math,
    Date,
    JSON,
    Promise,
    Error,
    TypeError,
    RegExp,
    Map,
    Set,
    isNaN,
    parseInt,
    parseFloat,
    encodeURIComponent,
    decodeURIComponent,
    encodeURI,
    setTimeout: () => 0,
    setInterval: () => 0,
    fetch: () => Promise.reject(new Error('network is disabled in this harness')),
    showMessage: () => {},
    showAlertDialog: () => Promise.resolve(),
    loadCharacterCards: () => Promise.resolve(),
    switchTab: () => {},
  };
  context.self = context;
  context.window.document = documentStub;

  const escapeBlock = opts.identityEscape
    ? 'function escapeHtml(text) { return String(text); }'
    : escapeHtmlSource();

  // 变异开关 2：只拆 URL 白名单，转义保持真实实现。
  const urlOverride = opts.identityUrl
    ? 'safeWorkshopImageUrl = function (rawUrl) { return String(rawUrl === null || rawUrl === undefined ? "" : rawUrl); };'
    : '';

  const bootstrap = `
    ${escapeBlock}
    ${readSource(WORKSHOP_FILE)}
    ${urlOverride}
    __api = {
      safeWorkshopImageUrl: safeWorkshopImageUrl,
      safeProgressWidth: safeProgressWidth,
      escapeHtml: escapeHtml,
      renderSubscriptionsPage: renderSubscriptionsPage,
      viewItemDetails: viewItemDetails,
      setItems: function (items) {
        allSubscriptions = items;
        currentPage = 1;
        itemsPerPage = 10;
        totalPages = 1;
      },
      respondWith: function (payload) {
        // 生产代码调的是裸 fetch（走 vm 上下文全局），window.fetch 只是顺手一起换
        var response = function () {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: function () { return Promise.resolve(payload); },
          });
        };
        globalThis.fetch = response;
        window.fetch = response;
      },
    };
  `;

  vm.createContext(context);
  vm.runInContext(bootstrap, context, { filename: 'workshop-xss-harness.js' });
  return { context, elements, api: context.__api };
}

function workshopPayloadItem(extra) {
  return Object.assign({
    publishedFileId: "7' onclick=alert(1) data-x='",
    title: MALICIOUS_TITLE,
    authorName: "' onerror='alert(1)' data-x='Al",
    previewUrl: MALICIOUS_URL,
    previewImageUrl: 'data:text/html,<script>alert(1)</scr' + 'ipt>',
    timeAdded: 1710000000,
    timeUpdated: 1710001000,
    fileSizeOnDisk: 2048,
    state: { downloading: true },
    downloadProgress: { percentage: '50%;background:url(javascript:alert(1))' },
    voiceReferenceAvailable: true,
    voiceReference: { displayName: MALICIOUS_TITLE },
    description: '<script>alert(1)</script>',
  }, extra || {});
}

function attributeValues(html, name) {
  const out = [];
  const re = new RegExp('(?:^|\\s)' + name + '="([^"]*)"', 'g');
  let match;
  while ((match = re.exec(html)) !== null) out.push(match[1]);
  return out;
}

// HTML 属性解析会还原实体；还原一次才能判断「逃出属性之后是否真的多出一个标签」。
function decodeEntities(value) {
  return String(value)
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

// 真实浏览器会把属性值里的实体还原成字符再解析；出口串用同样的口径还原一次，
// 才能直接断言 src / data-item-id 的字面值。
function decodeAttributes(html) {
  return html.replace(/="([^"]*)"/g, (all, value) => `="${decodeEntities(value)}"`);
}

function testPureUrlAllowlist() {
  const { api } = buildSandbox();
  const cases = [
    ['https://steamuserimages-a.akamaihd.net/abc.jpg', true],
    ['/api/steam/proxy-image?image_path=preview.png', true],
    ['../static/icons/Steam_icon_logo.png', true],
    ['http://127.0.0.1:48911/x.png', true],
    ['http://localhost:48911/x.png', true],
    ['http://[::1]:48911/x.png', true],
    ['http://127.0.0.1:48911/x.png?a=1&b=2', true],
    ['javascript:alert(1)', false],
    ['JaVaScRiPt:alert(1)', false],
    [' javascript:alert(1)', false],
    ['java\tscript:alert(1)', false],
    ['java\nscript:alert(1)', false],
    ['data:image/svg+xml,<svg onload=alert(1)>', false],
    ['blob:http://127.0.0.1:48911/uuid', false],
    ['vbscript:msgbox(1)', false],
    ['//evil.test/x.png', false],
    ['http://cdn.not-loopback.test/x.png', false],
    ['', false],
    ['   ', false],
    [null, false],
    [undefined, false],
    // 纯数字相对路径按「同源相对地址」放行：它落不进任何可执行面（出口仍过 escapeHtml），
    // 取不到图时由 onerror 兜底成默认图标，不值得为它开特例。
    [12345, true],
    [{ toString: function () { return 'javascript:alert(1)'; } }, false],
  ];

  for (const [input, allowed] of cases) {
    const result = api.safeWorkshopImageUrl(input);
    if (allowed) {
      assert(result === String(input).trim(),
        `应原样放行 ${JSON.stringify(input)}，实得 ${JSON.stringify(result)}`);
    } else {
      assert(result === FALLBACK_ICON,
        `应回落默认图标 ${JSON.stringify(input)}，实得 ${JSON.stringify(result)}`);
    }
  }

  const fileBase = buildSandbox({ pageBase: 'file:///D:/NEKO/templates/index.html' });
  assert(fileBase.api.safeWorkshopImageUrl('../static/icons/a.png') === '../static/icons/a.png',
    'file:// 页面下的相对图标地址必须仍然放行（Electron 直接打开模板的场景）');
  assert(fileBase.api.safeWorkshopImageUrl('javascript:alert(1)') === FALLBACK_ICON,
    'file:// 页面下 javascript: 仍然回落');
  assert(fileBase.api.safeWorkshopImageUrl('https://cdn.test/a.png') === 'https://cdn.test/a.png',
    'file:// 页面下的 https 外链仍然放行');
}

function testProgressWidth() {
  const { api } = buildSandbox();
  const accepted = [[42.5, '42.5'], ['61.8', '61.8'], [0, '0'], [-3, '0'], [100, '100'], [9999, '100']];
  for (const [input, expected] of accepted) {
    assert(String(api.safeProgressWidth(input)) === expected,
      `safeProgressWidth(${JSON.stringify(input)}) 应为 ${expected}，实得 ${api.safeProgressWidth(input)}`);
  }
  const poisoned = [
    '100%;background:url(javascript:alert(1))',
    '50}" onmouseover="alert(1)',
    'expression(alert(1))',
    '50% ; }',
    NaN,
    Infinity,
    -Infinity,
    undefined,
    null,
    '',
    [1, 2],
    { valueOf: function () { return 7; } },
  ];
  for (const input of poisoned) {
    const value = api.safeProgressWidth(input);
    assert(Number.isFinite(value) && value >= 0 && value <= 100,
      `safeProgressWidth 必须把 ${JSON.stringify(input)} 收进 0~100，实得 ${value}`);
    assert(/^[0-9.]+$/.test(String(value)),
      `safeProgressWidth(${JSON.stringify(input)}) 出口只应是数字，实得 ${JSON.stringify(String(value))}`);
  }
}

function renderList(sandboxOptions, items) {
  const env = buildSandbox(sandboxOptions);
  env.api.setItems(items);
  env.api.renderSubscriptionsPage();
  return { html: env.elements['subscriptions-list'].assignedHtml, env };
}

async function renderDetail(sandboxOptions, item) {
  const env = buildSandbox(sandboxOptions);
  env.api.respondWith({ success: true, item });
  env.api.viewItemDetails('42');
  // fetch().then().then() 是一条微任务链，用宏任务把它排空
  await new Promise((resolve) => global.setTimeout(resolve, 0));
  await new Promise((resolve) => global.setTimeout(resolve, 0));
  return {
    html: env.elements.itemDetailContent.assignedHtml,
    modalTitle: env.elements.modalTitle.textContent,
    env,
  };
}

function assertNoEscape(html, label) {
  assert(html.indexOf(MALICIOUS_TITLE) < 0,
    `${label}：恶意标题原样出现在出口串里（属性逃逸成功）`);
  assert((html.match(/<img src=x /g) || []).length === 0,
    `${label}：出口串里凭空多出注入的 <img src=x ...> 标签`);
  assert(html.indexOf('<script>') < 0, `${label}：出口串里出现裸 <script>`);
  // escapeHtml 的产物形态："><img 必须整体变成 &quot;&gt;&lt;img
  assert(html.indexOf('&quot;&gt;&lt;img src=x onerror=alert(1)&gt;') >= 0,
    `${label}：恶意标题没有出现预期的转义形态（&quot;&gt;&lt;img ...）`);
}

function assertPreviewSrcSafe(html, label) {
  // 先按浏览器口径还原属性实体，再取 src：这样断言的是「解析后真正生效的地址」
  const srcs = attributeValues(decodeAttributes(html), 'src').filter((v) => v.indexOf('paw_ui.png') < 0);
  assert(srcs.length > 0, `${label}：出口串里找不到预览图，样本没走到渲染路径`);
  for (const src of srcs) {
    assert(src.indexOf('javascript:') < 0, `${label}：解析后的 img src 含 javascript: -> ${src}`);
    assert(src.indexOf('data:') < 0, `${label}：解析后的 img src 含 data: -> ${src}`);
    assert(src.indexOf('vbscript:') < 0, `${label}：解析后的 img src 含 vbscript: -> ${src}`);
  }
  return srcs;
}

async function testRenderedHtml() {
  const list = renderList({}, [workshopPayloadItem()]);
  assertNoEscape(list.html, '列表');
  const srcs = assertPreviewSrcSafe(list.html, '列表');
  assert(srcs.every((src) => src === FALLBACK_ICON),
    `列表：恶意 previewUrl 应回落默认图标，实得 ${JSON.stringify(srcs)}`);
  assert(list.html.indexOf('&quot;&gt;&lt;img') >= 0, '列表：恶意标题未按预期转义（找不到 &quot;&gt;&lt;img 前缀）');
  // 列表模板不渲染 description，这条只在详情里断言（见下）

  assert(!/onclick="\$\{/.test(list.html), '列表：出口串里仍有模板拼接的 onclick');
  assert(list.html.indexOf('onclick="openWorkshopVoiceClone') < 0, '列表：仍在用内联 onclick 拼接工坊 id');
  assert(!/onclick="[^"]*alert/.test(list.html), '列表：内联 onclick 里出现了 alert');
  for (const action of ['voice-clone', 'add-card', 'unsubscribe']) {
    assert(list.html.indexOf(`data-workshop-action="${action}"`) >= 0,
      `列表：${action} 按钮未改为 data-workshop-action 委托`);
  }
  assert(attributeValues(list.html, 'data-item-id').every((v) => v.indexOf("'") < 0),
    '列表：data-item-id 解码前不得出现裸单引号');
  assert(list.html.indexOf(`data-item-id="7&#39; onclick=alert(1) data-x=&#39;"`) >= 0,
    '列表：工坊 id 里的单引号未转义，data-item-id 属性可被切断');
  assert(!/style="width:\s*[^";]*;/.test(list.html), '列表：style 属性里出现了分号（百分比逃出 width 声明）');
  assert(list.html.indexOf('style="width: 0%"') >= 0,
    '列表：被投毒的百分比应收敛为 0%');

  const detail = await renderDetail({}, workshopPayloadItem({ downloadProgress: { percentage: 61.8 } }));
  assertNoEscape(detail.html, '详情');
  const detailSrcs = assertPreviewSrcSafe(detail.html, '详情');
  assert(detailSrcs.every((src) => src === FALLBACK_ICON),
    `详情：恶意 previewUrl 应回落默认图标，实得 ${JSON.stringify(detailSrcs)}`);
  assert(detail.html.indexOf('&lt;script&gt;alert(1)&lt;/script&gt;') >= 0,
    '详情：工坊描述未按预期转义');
  assert(detail.modalTitle === MALICIOUS_TITLE,
    `详情：modalTitle 走 textContent，应保留原文（不被二次转义），实得 ${JSON.stringify(detail.modalTitle)}`);
  assert(detail.html.indexOf('style="width: 61.8%"') >= 0,
    '详情：正常百分比应照常渲染为 61.8%');

  // 正常样本必须照常渲染，否则「安全」是靠功能坏死换来的
  const normal = renderList({}, [{
    publishedFileId: 42,
    title: 'Neko Asset',
    authorName: 'Alice',
    previewUrl: 'https://cdn.example.test/a.jpg',
    timeAdded: 1710000000,
    timeUpdated: 1710001000,
    fileSizeOnDisk: 2048,
    state: { installed: true },
  }]);
  assert(attributeValues(decodeAttributes(normal.html), 'src').includes('https://cdn.example.test/a.jpg'),
    '列表：正常 https 预览图被误杀');
  assert(normal.html.indexOf('card-title">Neko Asset') >= 0, '列表：正常标题渲染丢失');
  assert(normal.html.indexOf('data-item-id="42"') >= 0, '列表：正常 id 渲染丢失');

  const proxied = renderList({}, [{
    publishedFileId: 43,
    title: 'Proxied',
    previewUrl: '',
    previewImageUrl: '/api/steam/proxy-image?image_path=preview.png',
    timeAdded: 1710000000,
    fileSizeOnDisk: 1,
    state: { installed: true },
  }]);
  assert(attributeValues(decodeAttributes(proxied.html), 'src').includes('/api/steam/proxy-image?image_path=preview.png'),
    '列表：同源相对代理地址被误杀（会打断 tests/frontend 已有的 preview fallback 断言）');
}

async function testMutationControl() {
  // 变异 1：把 escapeHtml 换成恒等实现，出口串里必须出现原始 payload——
  // 否则上面的「找不到 "><img」只是在测一条永真正则。
  const brokenEscape = renderList({ identityEscape: true }, [
    workshopPayloadItem({ previewUrl: 'https://ok.test/a.png', previewImageUrl: undefined }),
  ]);
  assert(brokenEscape.html.indexOf(MALICIOUS_TITLE) >= 0,
    '变异对照失效：escapeHtml 换成恒等后，出口串里也没出现原始 payload（断言没在测转义）');
  assert(brokenEscape.html.indexOf('<img src=x onerror=alert(1)>') >= 0,
    '变异对照失效：escapeHtml 换成恒等后没有还原出可执行的注入标签');

  // 变异 2：只拆 URL 白名单，javascript: 必须能落到 src 上
  const brokenUrl = renderList({ identityUrl: true }, [
    workshopPayloadItem({ previewImageUrl: undefined }),
  ]);
  const brokenSrcs = attributeValues(decodeAttributes(brokenUrl.html), 'src').filter((v) => v.indexOf('paw_ui.png') < 0);
  assert(brokenSrcs.some((src) => src.indexOf('javascript:') >= 0),
    '变异对照失效：拆掉 safeWorkshopImageUrl 后 javascript: 仍没能进入 img src');

  // 两个变异开关必须彼此独立，否则等于只有一个开关
  assert(brokenUrl.html.indexOf(MALICIOUS_TITLE) < 0,
    'URL 变异不该连带关掉标题转义（两个开关写成了一个）');
  assert(!attributeValues(brokenEscape.html, 'src').some((src) => src.indexOf('javascript:') === 0),
    '转义变异不该连带关掉 URL 白名单（两个开关写成了一个）');

  // 变异 3：拆掉 URL 白名单时，详情路径同样必须暴露出漏洞
  const brokenDetail = await renderDetail({ identityUrl: true }, workshopPayloadItem({ previewImageUrl: undefined }));
  assert(attributeValues(decodeAttributes(brokenDetail.html), 'src').some((src) => src.indexOf('javascript:') >= 0),
    '变异对照失效：详情路径在拆掉 URL 白名单后仍没暴露 javascript: src');
}

function testStaticContract() {
  const source = readSource(WORKSHOP_FILE);

  const forbidden = [
    [/function escapeHtml/, '本文件不得重新定义 escapeHtml（真身在 core-and-upload.js）'],
    [/onclick="\$\{/, '不得把变量拼进内联 onclick'],
    [/onclick="[a-zA-Z]+\('\$\{/, '不得把工坊字段拼进内联 onclick 的 JS 实参位'],
    [/<img src="\$\{item\./, 'img src 不得直接插工坊原始字段'],
    [/previewUrl: item\.(previewUrl|previewImageUrl)/, 'previewUrl 必须经 safeWorkshopImageUrl'],
    [/previewUrl: encodeURI\(/, 'encodeURI 不是 URL 白名单，不能继续充当 scheme 闸门'],
    [/name: item\.title\s*,/, '详情路径的 name 不得是 item.title 裸值'],
    [/width: \$\{item\.downloadProgress\.percentage\}/, '百分比不得裸插进 style 属性'],
    [/style="width: \$\{(?!safeProgressWidth)/, 'style 属性里的百分比必须过 safeProgressWidth'],
  ];
  for (const [re, message] of forbidden) {
    assert(!re.test(source), `源码静态约束被违反：${message}`);
  }

  const required = [
    [/function safeWorkshopImageUrl/, 'safeWorkshopImageUrl 定义丢失'],
    [/function safeProgressWidth/, 'safeProgressWidth 定义丢失'],
    [/function bindWorkshopCardActions/, '卡片按钮事件委托丢失（内联 onclick 会回来）'],
    [/nameHtml/, '详情模板缺少 name 的转义出口'],
    [/previewUrlHtml/, '详情模板缺少 previewUrl 的转义出口'],
  ];
  for (const [re, message] of required) {
    assert(re.test(source), `源码缺少必要的防线：${message}`);
  }

  // 属性出口逐条核对：每个 src/alt/title/data-item-* 的插值都必须经过转义或白名单。
  const escapedLocalNames = new Set(['nameHtml', 'previewUrlHtml', 'authorInitial', 'statusClass', 'statusText']);
  // 这两个字段在列表 formattedItem 里于赋值处就过了 escapeHtml
  const escapedAtSourceFields = new Set(['name', 'author', 'voiceReferenceDisplayName', 'description']);
  const sinkRe = /(?:src|alt|title|data-item-id|data-item-name)="(?:\$\{([^}]*)\}|([^"$]*))"/g;
  let match;
  let checked = 0;
  let unsafe = [];
  while ((match = sinkRe.exec(source)) !== null) {
    const expr = match[1];
    if (expr === undefined) continue;
    checked += 1;
    if (/^escapeHtml\(/.test(expr)) continue;
    if (escapedLocalNames.has(expr.trim())) continue;
    const field = expr.match(/^formattedItem\.([A-Za-z]+)/);
    if (field && escapedAtSourceFields.has(field[1])) continue;
    if (/^(window\.t|WORKSHOP_DEFAULT_ICON|item\.downloadProgress)/.test(expr.trim())) continue;
    unsafe.push(`\${${expr}}`);
  }
  assert(unsafe.length === 0, `存在未转义的属性出口：${unsafe.join(', ')}`);
  assert(checked >= 10, `属性出口只核对了 ${checked} 处（列表+详情两组模板合计应 >=10），标记漂移？`);
}

async function dumpEvidence() {
  // --dump：把恶意样本的真实出口串打出来（贴进 PR / 施工记录用），不做断言
  const list = renderList({}, [workshopPayloadItem()]);
  const detail = await renderDetail({}, workshopPayloadItem({ downloadProgress: { percentage: 61.8 } }));
  const pick = (html, needle, span) => {
    const at = html.indexOf(needle);
    return at < 0 ? `(未找到 ${needle})` : html.slice(Math.max(0, at - 20), at + span);
  };
  console.log('--- 列表卡片出口串（img + 按钮区）---');
  console.log(pick(list.html, '<img', 400));
  console.log('...');
  console.log(pick(list.html, '<div class="card-actions">', 900));
  console.log('\n--- 详情出口串（img + 描述）---');
  console.log(pick(detail.html, '<img', 260));
  console.log(pick(detail.html, 'item-description', 240));
  console.log('\n--- 还原后的 img src ---');
  console.log(JSON.stringify(attributeValues(decodeAttributes(list.html), 'src'), null, 0));
  console.log(JSON.stringify(attributeValues(decodeAttributes(detail.html), 'src'), null, 0));
  console.log('\n--- modalTitle.textContent（详情标题走 DOM 文本出口，保留原文）---');
  console.log(JSON.stringify(detail.modalTitle));
}

async function main() {
  if (process.argv.indexOf('--dump') >= 0) {
    await dumpEvidence();
    return;
  }
  testPureUrlAllowlist();
  testProgressWidth();
  testStaticContract();
  await testRenderedHtml();
  await testMutationControl();

  if (failures.length > 0) {
    console.error(`workshop XSS guard harness FAILED (${failures.length}):`);
    for (const failure of failures) console.error('  - ' + failure);
    process.exitCode = 1;
    return;
  }
  console.log('workshop XSS guard runtime tests passed');
}

main().catch((error) => {
  console.error(`workshop XSS guard harness crashed: ${error && error.stack ? error.stack : error}`);
  process.exitCode = 1;
});
