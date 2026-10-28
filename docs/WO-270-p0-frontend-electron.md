# 工单 270 · 前端与 Electron 窗隔离（P0-9 / P0-10 / P0-11）

> ⚠️ **编号体系**：本文件是**施工记录**。指令原文是 `TRAE_WORKORDER_PROMPT_AGENT_270.md`（派单表 `P0-派单表-2026-10-22.md` 第三波）。
> 委托方：用户 · 执行：Qoder · 出单：沈遥 · 日期：2026-10-22
> **定罪基线**：`main@40f6999197915d72bc764dd208c7b9f923129c23`
> **交付分支**：`wo/270-frontend-electron`（不动 `main`；PR 见文末）
> **本机等价关系**：本地 git 根是 `D:\my git`，`scratchpad-unified/` 一层对应远端仓根。下文所有远端路径按远端写法（不带 `scratchpad-unified/` 前缀）。
> **进度**：T1 / T2 / T3 全部做完本机能自证的部分。T2 主窗 `contextIsolation` **未翻**，是实测出的阻塞（§2.3），按工单硬边界写清阻塞原因与需要的决策；T3 隔离已翻并有真 Electron 读数（§3.2）。

---

## §0 一句话结论

| 项 | 病灶 | 收口方式 | 反证实验 | 状态 |
|---|---|---|---|---|
| P0-9 | Steam 工坊条目的 7 个字段是**外部可控字符串**，其中 `publishedFileId` 直接拼进 `onclick="…('${id}')"` 的 **JS 代码位**、详情侧 `alt="${name}"` 与 `src="${previewUrl}"` 裸拼进**属性位** ⇒ 一个恶意工坊条目就能在角色卡管理页执行任意 JS | 属性位一律 `escapeHtml`；JS 代码位**取消**（改 `data-workshop-action` 事件委托）；URL 协议改白名单 `safeWorkshopImageUrl`；`style` 百分比改数值钳制 `safeProgressWidth` | 真浏览器 A/B（`_wo270/probe.html`）：基线版 `__pwned=[itemId×3, detailTitle]`，本版只剩正对照 `control`；把 `escapeHtml`/`safeWorkshopImageUrl` 换成恒等函数后断言必红 | ✅ 完成 |
| P0-10 | reactChat / fullChat / chat 窗 `contextIsolation:false`（基线 `nodeIntegration` 全站已是 `false`，§2.1 更正）⇒ 页面脚本与 preload 同世界，XSS 可直接调 `window.electronDesktopCapturer.captureSourceAsDataUrl` 整屏截图取回 data URL；另有一条工单没点名的真漏洞：`setWindowOpenHandler` 给**任意** `window.open` URL 无差别发 `webSecurity:false` | 子窗侧：`webSecurity` 改为按「与父窗同源且 http(s)」判定（`!childIsSameOriginLocal`）；主窗侧：基线用契约测试钉死（不隔离窗口必须逐个登记 + 带同行注释），迁移路径见 §2.4 | 5 处注入全部必红（§2.2 表）；机制对照 D/E 用真 Electron 实测「只翻开关 ⇒ 页面读不到 preload 直写的 `window.X`」 | ⚠️ 部分收口：子窗特权已收窄 + 基线钉死；主窗未翻隔离（阻塞见 §2.3） |
| P0-11 | jukebox 主窗 + manager 子窗同一组合 `contextIsolation:false / webSecurity:false`，preload 直写 `window.nekoJukeboxWindow` | 两处 `contextIsolation: true`；`preload-jukebox.js` 改 `contextBridge` 双模暴露（照 `preload-common.js` 既有写法）；子窗 `webSecurity` 按同源判定收窄；主窗 `webSecurity:false` 保留（有外部 https 素材依赖的证据） | test 2/3/4/5 覆盖：翻回 `false` 红、抹注释红、子窗退回无差别 `false` 红、preload 退回直写红；真 Electron 场景 A 读数：`require/process` 均 `undefined`，桥与真 IPC 往返仍可用 | ✅ 隔离已翻并实测（拖拽/置顶的整窗人眼验收缺，见 §3.3） |

---

## §1 T1 · 工坊条目字段进 HTML（P0-9）

**改动面**：`NEKO/N.E.K.O/static/js/character_card_manager/subscriptions-and-scan.js`（+85 / −24，单文件）
**新增测试**：`NEKO/N.E.K.O/tests/frontend/test_workshop_xss_runtime.js`（node `vm` 真源码 harness）、`tests/frontend/test_workshop_xss_node.py`（pytest 包装）

### 1.1 病灶（基线代码）

工坊订阅列表的数据来自 `/api/steam/workshop/subscribed-items`，其内容上游是 **Steam 创意工坊**：标题、作者、预览图地址、语音引用显示名、描述……全是上传者写的字符串。基线里有三处把它们当成可信代码用：

```js
// :139  列表 formattedItem
previewUrl: encodeURI(item.previewUrl || item.previewImageUrl || '../static/icons/Steam_icon_logo.png'),
// :168  <img src="${formattedItem.previewUrl}" alt="${formattedItem.name}" ...>
// :201  <button onclick="openWorkshopVoiceClone('${formattedItem.id}')" ...>
// :204/205 data-item-id="${formattedItem.id}" data-item-name="${formattedItem.name}" onclick="unsubscribeItem(this.dataset.itemId, ...)"
// :193/581 <div class="progress-fill" style="width: ${item.downloadProgress.percentage}%">
// :525/530 详情 formattedItem：name: item.title（原文）、previewUrl: item.previewUrl（原文）
// :559  <img src="${formattedItem.previewUrl}" alt="${formattedItem.name}" class="item-preview-large" ...>
```

三个独立缺陷叠在一起：

1. **JS 代码位拼接**。`onclick="f('${id}')"` 里，`id = '">…'` 会把 `'` 之后的内容交回 HTML 分词器：`"` 先闭合 `onclick` 属性，`>` 闭合 `<button>` 标签，紧跟的 `<img … onerror=…>` 就成了**真元素**。HTML 转义在这里救不了——属性值里的 `"` 转成 `&quot;` 之前，模板已经把 `"` 写进去了（列表侧 `id` 根本没转义）。
2. **`encodeURI` 被当成协议闸门用**。`encodeURI` 会转义 `"` `<` `>`，但**不转义 `'`，也不改变 `javascript:` / `data:` 前缀**——它对 `javascript:alert(1)` 返回原串。所以 `previewUrl` 那条链路上"看起来编码过了"其实什么都没挡。
3. **列表转义、详情不转义的分裂约定**。同一个 `title`，列表走 `escapeHtml(item.title)`（:133），详情走 `name: item.title`（:525）。审查时最容易漏的就是这种"同一个字段两条路径，一条已经安全"的情形。

### 1.2 字段清单：可控 / 不可控

判定标准只有一个：**这个值是不是原样来自工坊元数据**。宿主自己生成的（日期格式化、字节数格式化、状态文案、i18n 文案）算不可控，但仍按纵深原则处理。

| 字段 | 来源 | 基线出口 | 基线结论 | 本版处置 |
|---|---|---|---|---|
| `publishedFileId` | 工坊条目 id（`String()` 后原样） | `onclick` 的 **JS 代码位** + `data-item-id` **属性位** | **可控且可利用**（实测执行 3 次） | 属性位 `escapeHtml`；`onclick` 整条删除，改 `data-workshop-action` 委托 |
| `title` | 条目标题 | 列表 `escapeHtml`；详情 `alt=`/`name` **裸拼** | 详情侧**可控且可利用**（实测执行 1 次） | 详情 `name` 存原文（`modalTitle.textContent` 需要原文，不双重转义），进 HTML 的出口统一走 `nameHtml`（:622） |
| `previewUrl` / `previewImageUrl` | 工坊图片地址 | `encodeURI` 后进 `src=` | **可控**，协议不受约束 | `safeWorkshopImageUrl` 协议白名单（:46）+ `escapeHtml` |
| `voiceReference.displayName` | 语音引用显示名 | `escapeHtml` 后进 `title=` | 基线已安全 | 保持源侧转义 |
| `authorName` / `creator` | 作者名 | `safeAuthorName` + `escapeHtml` | 基线已安全 | 保持 |
| `description` | 条目描述 | `escapeHtml` 后进 `<p>` 文本位 | 基线已安全 | 保持 |
| `downloadProgress.percentage` | 下载百分比 | 裸拼进 `style="width: …%"` | **可控**（可注入 `;` 断言 CSS，且字符串形态会抛 `TypeError` 让整页卡片渲染中断） | `safeProgressWidth` 数值钳制（:74），非数字/≤0 → `0`，>100 → `100` |
| `timeAdded` / `timeUpdated` | 秒级时间戳 | `toLocaleDateString()` 后 `innerHTML` | 不可控字符（数字→本地化日期串） | 仍套 `escapeHtml`（纵深，成本 0） |
| `fileSizeOnDisk` / `fileSize` | 字节数 | `formatFileSize()` | 不可控字符 | 同上 |
| `state.*`（installed / downloading / needsUpdate） | 安装状态布尔 | `getStatusText()` → 本地化常量 | 不可控字符 | 同上 |
| `data.error`（:55）/ `error.message`（:107） | 后端错误回显 / 异常文本 | 裸拼进 `innerHTML` | **半可控**（后端错误串可能带外部输入回显） | `escapeHtml` |
| 详情请求的 `itemId` | 上游调用参数 | `fetch('/api/steam/workshop/item/' + itemId)` **未编码** | 路径注入（可越到别的端点） | `encodeURIComponent(itemId)`（:574 调用侧） |

### 1.3 验收命令与真实输出

**① node harness（真源码切片，无浏览器）**

```
$ node NEKO/N.E.K.O/tests/frontend/test_workshop_xss_runtime.js
workshop XSS guard runtime tests passed
```

**② pytest 包装**

```
$ .venv/Scripts/python.exe -m pytest tests/frontend/test_workshop_xss_node.py -v --noconftest -o addopts=""
tests/frontend/test_workshop_xss_node.py::test_workshop_xss_runtime PASSED [100%]
======================== 1 passed, 2 warnings in 0.23s ========================
```

> `--noconftest -o addopts=""` 是**本机解释器缺仓库依赖**（`nest_asyncio`、`pytest-randomly`）时的绕法，不是绕测试：被执行的断言一条没少。NEKO 自己的 `.venv` 版本锁死，按委托方要求**未安装任何东西**。

**③ 静态契约回归**（这两份都会把 `character_card_manager` 全部分片拼起来断言）

```
$ pytest tests/unit/test_card_maker_static_contracts.py --noconftest -o addopts=""
======================= 34 passed, 2 warnings in 0.28s ========================
```

`tests/unit/test_cloudsave_pages.py` 在本机**整份 collect 不了**：文件顶部 `from main_routers.pages_router import …` 需要 `cachetools`，`.venv` 没有、NEKO `.venv` 禁装。该文件对 P0-9 唯一相关的是 `test_character_card_manager_disables_cloudsave_entry_when_provider_is_unavailable`，它是 10 条纯字符串断言，已用 `D:\my git\_wo270\t_cloudsave_contract.js` 原样复刻并全绿（`parts used: 10/10 / cloudsave entry contract intact`）。**这条替代验证的边界要说清：它证明"契约字符串还在"，不证明那个文件里的 `cloudsave_manager_page` 渲染测试没被影响。**

**④ 真浏览器 A/B**：本机 `127.0.0.1:48970` 静态服务器同时服务两份 `subscriptions-and-scan.js`——`before` = 基线提交原样副本（sha256 前缀 `2f2154c7f41b`），`after` = 本地已修副本；`?variant=` 决定加载哪份。恶意样本：

```js
publishedFileId / title / authorName / voiceReference.displayName / description
  = '"><img src="/missing-<tag>.png" onerror="pwn(\'<tag\')">'
previewUrl     = "javascript:pwn('previewUrl')"
previewImageUrl = 'data:image/svg+xml,<svg …><circle onload=…></svg>'
percentage     = '50%;background-image:url("/missing-percent.png")'
```

`<img>` 的 src 全部指向服务器上不存在的 `missing-*.png`（一律 404），于是**只要元素真的进了 DOM，`onerror` 就会调用 `window.pwn(tag)`**——这是"执行了没有"的硬证据，不靠肉眼看弹窗。度量分两套：`__pwned` 增量来自 live DOM（执行事实），结构度量在 `<template>` 里解析同一段 HTML（惰性、不产生新执行）。

| 度量 | before | after |
|---|---|---|
| `pwnedAll` | `["itemId","itemId","itemId","detailTitle","control"]` | `["control"]` |
| `listPwned` | 3 次 | `[]` |
| `detailPwned` | `["detailTitle"]` | `[]` |
| `controlFired`（正对照，必须执行） | `["control"]` | `["control"]` |
| `listMetrics.cardImgSrc` | `javascript:pwn('previewUrl')` | `../static/icons/Steam_icon_logo.png` |
| `listMetrics.injectedImgCount` | 3 | 0 |
| `listMetrics.buttonsWithOnclick` / `…DatasetAction` | 1 / 0 | 0 / **3** |
| `styleMetrics.htmlLength` | **0**（渲染整页中断） | 2973 |
| `styleMetrics.progressStyle` | — | `width: 0%` |
| `detailMetrics.detailImgSrc` | `null`（img 标签被 payload 打断） | `../static/icons/Steam_icon_logo.png` |
| `missingFns` | `["safeWorkshopImageUrl"]` | `[]` |
| 良性样本 `benignMetrics` | https 图 + `width: 61.8%` + `onclick×2` | 同一张 https 图 + `width: 61.8%` + `data-workshop-action×2` |
| `thrown` | `renderSubscriptionsPage(stylePoison): item.downloadProgress.percentage.toFixed is not a function` | `[]` |

原始 JSON 落盘：`D:\my git\_wo270\evidence\before.json`、`evidence\after.json`。

**DOM 快照**（`#subscriptions-list` 的 innerHTML 头部，已把换行压平）：

before：
```html
<h3 class="card-title">"><img src="/missing-title.png" onerror="pwn('title')">…
<div class="card-actions"> <button class="button button-primary" onclick="openWorkshopVoiceClone('"><img src="/missing-itemId.png …
<img src="javascript:pwn('previewUrl')" alt="&quot;&gt;&lt;img src=&quot;/missing-title.png …" class="card-image" …
```

after：
```html
<img src="../static/icons/Steam_icon_logo.png" alt="&quot;&gt;&lt;img src=&quot;/missing-title.png&quot; onerror=&quot;pwn('title')&quot;&gt;" class="card-image" …
<h3 class="card-title">&quot;&gt;&lt;img src=&quot;/missing-title.png …
<button class="button button-primary" type="button" data-workshop-action="voice-clone" data-item-id="&quot;&gt;&lt;img …
```

`brokenTagCount`（渲染串里 `&quot;&gt;&lt;img` 出现次数）：before 列表 = 1，after 列表 = **7**。这个数字变大才是对的——payload 从"只有 `title` 一个字段被转义"变成"7 个字段全部被转义成文本"。

### 1.4 关于"没能证明的东西"

* `javascript:` 在 `<img src>` 里 Chrome 本来就不执行，`data:image/svg+xml` 在 `<img>` 里脚本也是被禁的。所以这两个 sink 的结论只能来自**值断言**（`cardImgSrc` 不再等于 `javascript:…`），不是执行断言。真正被证明"会执行"的是 `onclick` 属性位（itemId×3）和详情 `alt` 属性位（detailTitle）。正对照 `control` 就是为了把这条界线钉住：探针有检出执行的能力。
* 截图没拿到：内置浏览器面板当时不可见（`viewport=0x0, visible=false`），工单要求的"贴 DOM 快照"已满足，"贴图"缺失，如实记录。
* Playwright 那套 `test_character_card_manager_regressions.py` 在本机跑不了（`.venv` 无 playwright，NEKO env 禁装）。它对 P0-9 的约束——`/api/steam/proxy-image?image_path=preview.png` 这种**同源相对地址必须原样返回**——已经被复刻进 node harness 的 URL 白名单表（同源相对项）与列表渲染断言里，不会等 CI 才发现。

### 1.5 改坏 ⇒ 必红（反证）

`test_workshop_xss_runtime.js` 里 `testMutationControl()` 用三个独立开关做对照，全部在 harness 内断言"**关掉防护时守卫必须失败**"，否则说明断言本身是空转的：

| 开关 | 改法 | 期望 |
|---|---|---|
| `escapeHtml` 换成恒等函数 | 属性位不再编码 | 断言必须变红（且属性逃逸真的出现 `<img src=x `） |
| `safeWorkshopImageUrl` 换成恒等函数 | `javascript:` 直接进 `src` | 断言必须变红 |
| 两个开关**互不联动** | 只开其中一个 | 另一个仍必须红 ⇒ 证明两条防线各自独立有效 |

另有 `testStaticContract()`：对源文件做禁/需正则（`onclick="…${`、`src="${formattedItem`、`encodeURI(item.previewUrl` 等）+ 属性 sink 遍历，要求每个 `src/alt/title/data-item-*/class/style` 插值要么被转义、要么在白名单里，且覆盖数 `>= 10`——防止"新增一个 sink 但没进测试"。

### 1.6 顺带修掉的两个真 bug

1. **字符串百分比会让整页订阅卡片消失**：基线 `${item.downloadProgress.percentage}` 与 `percentage.toFixed(1)` 组合下，后端把进度传成字符串时直接 `TypeError`，`renderSubscriptionsPage()` 整段中断（before 的 `styleMetrics.htmlLength = 0` 就是这个）。现在 `safeProgressWidth` 统一 `Number()` + 钳制，良性样本 `61.8%` 仍照常渲染。
2. **详情 fetch 路径未编码**：`/api/steam/workshop/item/${itemId}` → `encodeURIComponent(itemId)`，与同文件 `:308` 的 `sync-character/${encodeURIComponent(itemId)}` 对齐。

**明确没动的**：`rawName`（当前无消费者，删它属于顺手清理，不在本工单范围）、`id: item.publishedFileId.toString()`（对 `null` 会抛，但不是安全问题，且已实测与 P0-9 无关）、`showMessage(...)` 调用点（`textContent` 出口，本来就安全）。

---

## §2 T2 · React Chat 窗（P0-10）

**改动面**：`neko-electron-shell/src/window-manager.js`（两处子窗 `webSecurity` 按同源收窄 + 6 个窗口的豁免注释）、`src/main/pet-window-lifecycle.js`（1 行注释）、新增 `tests/window-hardening.contract.test.js`、`package.json` 补 `test` 脚本。
**主窗的 `contextIsolation` 本次没翻**，理由见 2.3，是实测出来的阻塞，不是偷懒。

### 2.1 先把定罪校一遍：nodeIntegration 那半句是错的

工单 T2 现状栏写的是 `contextIsolation:false` + `webSecurity:false` + `sandbox:false`（没提 nodeIntegration），但 §0 早先那版记录里我顺手写了「nodeIntegration:true」。基线实测**不存在**这种窗口：

```
$ grep -n "nodeIntegration" _wo270/remote/neko-electron-shell/src/window-manager.js \
      _wo270/remote/neko-electron-shell/src/main/pet-window-lifecycle.js
14 处全部是 nodeIntegration: false      # 取自 main@40f699919791 原文，不是本地工作区
```

所以 P0-10 的真实风险面只有一条：**隔离关着**。`nodeIntegration:false` 时页面拿不到 `require`，但 `contextIsolation:false` 让页面脚本和 preload 跑在**同一个世界**——preload 往 `window` 上挂的那些桥，页面 XSS 可以直接调用、也可以直接改写。最扎手的是 `preload-chat-react.js:406` 的 `window.electronDesktopCapturer`：

```js
captureSourceAsDataUrl: (sourceId) => ipcRenderer.invoke('capture-source-as-dataurl', sourceId),
captureSourceWithoutNeko: (sourceId) => ipcRenderer.invoke('capture-source-without-neko', sourceId),
```

即：聊天页里一段能跑起来的脚本 = 「整屏截图并拿到 data URL」+ 挪动/隐藏窗口 + 装卸字幕窗 + 顶掉页面的 `WebSocket`。这就是把隔离翻成 `true` 之后会消失的能力，也是 P0-10 的实际价值。

顺带把另一条真漏洞收掉：`setWindowOpenHandler` 原来给**所有** `window.open` 的 URL 无条件发 `webSecurity: false`（jukebox 侧 `:1137`、chat 侧 `:1695`）。`webSecurity:false` 就是关掉同源策略，等于对任意被诱导打开的外部页面开放「跨源读 `http://localhost:48911/api/...`」——本机聊天历史、配置、角色卡数据都在那条 URL 后面。现在两处都改成只对「确认与父窗同源且是 http(s)」的子窗沿用 `false`，其余保持默认强隔离：

```js
const childIsSameOriginLocal = shouldAttachSameOriginChildPreload(win, details.url);
...
webSecurity: !childIsSameOriginLocal,
```

`shouldAttachSameOriginChildPreload`（`window-manager.js:231`）是基线就有的判定，原本用来决定「要不要给子窗挂 preload」，不是我新写的逻辑；manager 子窗仍是同源本地页，行为不变。

### 2.2 验收命令与真实输出

```
$ cd neko-electron-shell && npm test
ok 1 - 所有窗口都不允许 nodeIntegration:true
ok 2 - contextIsolation:false 只允许出现在白名单窗口，且必须带同行说明
ok 3 - jukebox 主窗与 manager 子窗已开隔离，webSecurity 仍按白名单登记且带说明
ok 4 - window.open 子窗口不得无差别发放 webSecurity:false
ok 5 - 已隔离窗口的 preload 不得再直接写 window.*
# pass 5  # fail 0
```

> `node --test tests/` 在 Windows 下会把目录当模块解析并报 `Cannot find module '...\tests'`，所以 `package.json` 里的 `test` 用 glob 形式 `node --test "tests/*.test.js"`。

工单要求的 `grep -n "contextIsolation: false\|webSecurity: false" window-manager.js` 在 Chat 窗段落 0 命中——**没达成**，主窗两处仍是 `false`，白名单把它钉在案（`reactChatWindow` / `fullChatWindow` / `chatWindow`），并要求每条豁免自带同行注释，注释被抹掉测试就红。

**改坏 ⇒ 必红**（在 `D:\my git\_wo270\mut` 的副本上做，不碰工作区；跑完复原并复跑全绿）：

| 注入 | 期望 | 实测 |
|---|---|---|
| pet 段 `nodeIntegration: false` → `true` | test 1 红 | `not ok 1` |
| jukebox 主窗 `contextIsolation: true` → `false` | test 2 红（未登记窗口） | `not ok 2` |
| 删掉 toast 的 `webSecurity:false` 豁免注释 | test 3 红（豁免必须有说明） | `not ok 3` |
| manager 子窗 `webSecurity: !childIsSameOriginLocal` → `false` | test 3 + test 4 红 | `not ok 3` / `not ok 4` |
| `preload-jukebox.js` 退回 `window.nekoJukeboxWindow = {` | test 5 红 | `not ok 5` |
| 复原 | 全绿 | `# pass 5`（本轮无 `not ok`） |

### 2.3 为什么主窗没翻隔离：实测的阻塞清单

用真 Electron（本机 `neko-electron-shell/node_modules/electron`，42.11.18）起一次性窗口，把真 preload 挂上去，从**页面世界**读回来看得到什么（`_wo270/eharness/`，userData 指到临时目录，不碰真应用配置）。机制对照用一份 6 行的合成 preload，同一份代码在两种隔离档下的页面可见性：

| 场景 | `window.__SYNTH_DIRECT__`（preload 里 `window.X = 'written-directly'`） | `window.__SYNTH_BRIDGE__`（`contextBridge.exposeInMainWorld`） |
|---|---|---|
| D `contextIsolation: true` | `undefined` ← **页面读不到** | `object / "via-bridge"` |
| E `contextIsolation: false` | `string / "written-directly"` | `object / "via-bridge"` |

⇒ 「只翻开关、不迁 preload」会让页面侧的 stub 整片消失，这不再是推断，是读数。而 chat 侧的耦合面正好落在这条线以下：

| 阻塞点 | 计数（实测） | 说明 |
|---|---|---|
| `preload-chat-react.js` 顶层直写 `window.X =` | 40 处（8124 行文件） | 全部要在翻隔离前迁进 `exposeInMainWorld` |
| 替换页面内建：`window.WebSocket = WSProxy` | `:366` | `exposeInMainWorld` **不能**覆盖页面内建；只有 `contextBridge.executeInMainWorld`（Electron ≥28.1）能做。版本依据分两档：main 的 manifest 是 `devDependencies.electron: ^41.10.3`，本机实装 42.11.18 —— 两档都 ≥28.1，结论不受影响。本工单**不改依赖版本**（本机那个 `^42.11.18` 属于 #24「Electron 升级」那条线，混进本 PR 会让一个供应链升级看起来像 XSS/隔离修复的一部分，见 §4） |
| preload ↔ 页面**双向**共享的状态全局 | `window.__nekoDesktopCompactLayout` 25 次引用、`__nekoForceInteractive` 7、`__nekoDesktopCompactHistoryDragState` 5、`__nekoDesktopCompactBallScreenRect` 5 | 页面侧 `static/app/app-react-chat-window/*` 与构建产物 `static/react/neko-chat/neko-chat-window.{es,iife}.js`（源在 `frontend/react-neko-chat/src/App.tsx`）另有 23 处 `window.__nekoDesktopCompactLayout`。隔离后两个世界不再共享 JS 全局，得改成桥 + 事件，**要连 React 构建产物一起重出** |
| 页面侧消费者 | `static/app/` 下 12 个文件读 `nekoChatWindow / electronDesktopCapturer / __NEKO_MULTI_WINDOW__` | stub 形状必须逐一对齐后再翻开关 |
| `webSecurity:false` | 保留 | 页面 origin 由 `appConfig.apiBaseUrl` 决定（`main.js:3007` 默认可改成远程），翻成默认同源要靠 Electron 运行期自测；本机工具只能驱动 Chrome/Edge，驱动不了这些原生窗口 ⇒ 不敢凭静态证据翻 |

`chatWindow`（旧 Chat 窗，`:488`）基线注释已经自认「preload 需替换页面 window.WebSocket 代理（架构约束）」，与上表同源，所以本次只补注释、不动开关。

**反事实场景 B/C 未取得读数**，如实记录：给空页面挂真 `preload-chat-react.js` 后，`loadURL` 与 `executeJavaScript` 双双超时（18s 档），日志里能看到该 preload 依赖真后端才有的通道——

```
WebContents #2 called ipcRenderer.sendSync() with 'neko:input-region-backend' channel without listeners.
Error occurred in handler for 'get-dark-mode': Error: No handler registered for 'get-dark-mode'
```

所以「chat 窗翻隔离后 stub 一定不可见」这句只能用 D/E 的机制读数 + 上表的静态计数来支撑，不能号称在真 chat 窗口上实测过。原始读数：`_wo270/evidence/electron_chat_preload_attempts.jsonl`。

**工单 T2 验收里我没做到的部分**（按工单「做不到就写阻塞原因 + 需要什么决策」的硬边界处理，不硬改）：
- 「起 Electron，Chat 窗功能自测清单（发消息 / 收 WS / 拖拽 / 设置项）逐项过」——需要 Python 后端 + 真角色卡会话 + 人眼确认窗口行为。这一台机器能起 Electron 进程，但起不了「有头验收」：我驱动不了原生窗口，也没有可复现的会话脚本。**需要的决策**：要么授权一次人工自测（我给出逐项清单和预期），要么把这窗口列入「迁 preload 时一起做」的独立工程单。
- 「DevTools 里 `window.<stub>` 仍可用、`window.require` 为 undefined」——`window.require` 这条在场景 A 已实测为 `undefined`（`processInPage` 同样 `undefined`）；stub 那条要等迁移后才谈得上。

### 2.4 迁移路径（给下一手，不是本次交付）

1. 先把 `preload-chat-react.js` 的 40 处直写改成分组注册表：纯函数对象走 `contextBridge.exposeInMainWorld`（照 `preload-common.js` 已有的 `process.contextIsolated` 双模写法，别发明第二套）。
2. `window.WebSocket = WSProxy` 用 `contextBridge.executeInMainWorld` 装进页面世界；先做一个最小窗口验证「页面 `new WebSocket()` 走代理 + `onmessage` 能收到」，因为跨世界 Promise/事件是这条路的唯一真风险点（本次场景 A 已经证明 `invoke` 返回的 Promise 跨世界可用）。
3. `__nekoDesktopCompactLayout` 这类双向状态改成「页面持有、preload 通过 `executeInMainWorld` 读写」或事件同步，重出 `static/react/neko-chat/*` 产物。
4. 以上三步齐了才翻 `contextIsolation: true`，并同步把 `tests/window-hardening.contract.test.js` 的白名单里 `reactChatWindow` / `fullChatWindow` / `chatWindow` 三条**删掉**（白名单只会缩小，不会为通过而新增）。
5. `webSecurity` 单独一步：先用真后端跑一遍「发消息 / 头像 / 截图 / TTS」，确认没有跨源读，再翻。

---

## §3 T3 · jukebox 主窗与 manager 子窗（P0-11）

**改动面**：`window-manager.js`（主窗 `:1072`、manager 子窗 `:1141`）、`src/preload-jukebox.js`（103 行，改双模暴露）。
**结论：`contextIsolation` 两处都翻成 `true` 并做了运行期实测；`webSecurity` 主窗保留 `false`（有证据），子窗按同源收窄。**

工单 T3 说「若拖拽 IPC 在开隔离后失效，改主进程实现，不许回退隔离开关」——本次不用回退，因为隔离和桥同时到位、且实测桥在页面世界可用（见 3.2）。

### 3.1 最终片段（工单要求贴 PR 的那两段）

主窗（`window-manager.js:1069-1080`）：

```js
    webPreferences: {
      preload: preloadPath,
      nodeIntegration: false,
      // P0-11：点歌台窗口的 preload 面很小（nekoJukeboxWindow / nekoJukeboxBridge 两个纯函数
      // 对象 + 一个独立模式标记），已全部改成 preload-common 那套双模暴露，因此这里开隔离：
      // 页面 XSS 不再能直接改写/借用 preload 所在世界的对象去摸 IPC。
      contextIsolation: true,
      sandbox: false, // preload-jukebox.js require 相对模块（ipc-channels / preload-common），不能开 sandbox
      webSecurity: false, // 点歌台会从 allowlist 外部 https 源取素材（music_ui.js isSafeUrl），同源策略关掉是现行依赖，翻它需运行期验证
```

manager 子窗（`:1141-1150`）：

```js
        webPreferences: {
          sandbox: false,
          // manager 子窗口复用 preload-jukebox.js，它已经是双模暴露，隔离照主窗一起开。
          contextIsolation: true,
          nodeIntegration: false,
          webSecurity: !childIsSameOriginLocal,
          // manager 需要 preload 提供 window.nekoJukeboxWindow 做窗口拖动的 IPC 桥接；
          // setWindowOpenHandler 的 webPreferences 是整体替换而非合并，不会从父窗口继承 preload。
          ...(isJukeboxManager ? { preload: preloadPath } : {}),
        }
```

`preload-jukebox.js` 的暴露面改成与 `preload-common.js` 同款的双模：

```js
function exposeToPage(name, value) {
  if (process.contextIsolated && contextBridge && typeof contextBridge.exposeInMainWorld === 'function') {
    contextBridge.exposeInMainWorld(name, value);
    return;
  }
  window[name] = value;
}
```

### 3.2 运行期实测（真 Electron 42.11.18 + 真 preload-jukebox.js + 真 IPC 往返）

场景 A 页面世界读数（`_wo270/evidence/electron_isolation_scenarios.jsonl`，184ms 完成）：

| 探针 | 读数 | 含义 |
|---|---|---|
| `requireInPage` / `processInPage` | `undefined` / `undefined` | 隔离真的把页面挡在 Node 之外 |
| `standaloneFlag` | `true` | `__NEKO_JUKEBOX_STANDALONE__` 经桥可见 ⇒ `jukebox-standalone.js:4` 的独立模式判定不因翻隔离而失效 |
| `jukeboxWindowBridge` / `jukeboxBridge` | `function` / `function` | `nekoJukeboxWindow.getBounds` / `nekoJukeboxBridge.dragStart` 在页面世界可调用 ⇒ manager 的拖动桥形状没变 |
| `getBoundsOk` / `getBoundsShape` | `true` / `height,width,x,y` | **页面调用 → 跨世界 Promise → 主进程 `ipcMain.handle` → 真窗口 bounds** 走通 |
| `darkModeBridge` / `openExternal` | `object` / `function` | `preload-common` 的 `setupDarkMode` / `setupElectronShell` 在隔离下仍把桥交给页面（它的 `process.contextIsolated` 分支生效） |
| `dragCssInjected` | `true` | `setupNativeDrag` 注入的 `-webkit-app-region` CSS 仍在共享 DOM 里命中 ⇒ 拖拽热区没因隔离丢失 |

> 注意 `getBounds` 的对端是 harness 自己注册的最小 handler，通道名取自被测代码的 `ipc-channels.js`。它证明「桥 + 跨世界 Promise」这条链路可用，**不**等价于真应用的整窗拖拽验收。

### 3.3 工单 T3 验收里做到的 / 没做到的

- 「两处 `webPreferences` 的最终片段贴进 PR」→ ✅ 3.1，PR 正文同段。
- 「拖拽 / 置顶 / 子窗关闭 三个交互实测通过（贴步骤）」→ **部分**：拖动链路的 renderer 侧（`dragStart/dragStop` 可调用、CSS 热区命中、IPC 往返）有 3.2 的读数；整窗跟手移动、`alwaysOnTop` 跟随全局开关、manager 关闭这三条**需要人眼在真窗口上看**，本机驱动不了原生窗口，没做到。按工单硬边界写在这里，不拿静态证据冒充交互验收。
- `webSecurity: true`（T3 目标里要求的）**没翻**，主窗保持 `false`。证据：`static/jukebox/music_ui.js` 的 `isSafeUrl` 走 `MUSIC_CONFIG.allowlist` 外部 https 域取素材，且后端代理 `/api/` 路径直接放行；这是现行功能依赖，翻它要跑真点歌台验一次。子窗侧把「任意 URL 都拿到该特权」这条真漏洞收掉了。


## §4 交付（分支 / PR / 自证 / 回滚）

### 4.1 落点

| 项 | 值 |
|---|---|
| 分支 | `wo/270-frontend-electron` |
| 基线（main tip，钉死） | `40f6999197915d72bc764dd208c7b9f923129c23`（tree `ccc33763246b2d1ae69e54fd0d07e7322224743c`） |
| 交付提交 | `594dca5f863628a5677de42d97ea74a4e26392b5`（tree `bd97b85d5301129f8691eb8197f04d3b5cbebdb3`）；其后只追加本文档 §4，无代码变更，分支 tip 以 PR #402 为准 |
| PR | #402 —— https://github.com/fe1iscurc0r/scratchpad/pull/402 |
| `main` | **没写**。合并与否由人决定 |
| 回滚点 | `git update-ref refs/heads/main 40f6999197915d72bc764dd208c7b9f923129c23`；或直接关 PR / 删分支 `wo/270-frontend-electron` |

交付通道：本机 git over HTTPS 被拦（`Recv failure: Connection was reset`）、`gh` 未认证，所以走 GCM 凭据 + REST（`/git/trees` → `/git/commits` → `/git/refs` → `/pulls`）。两个踩过的坑记在下面，免得下次重踩：

- Trees API 的字段名是 `tree`，写成 `entries` 会 422 `Invalid tree info`（9 个条目逐个单独提交也是同样的 422，所以不是某一条内容脏）。
- 本仓库存的是 **LF** blob，而本地 `window-manager.js` / `preload-jukebox.js` / `pet-window-lifecycle.js` 是 CRLF。上传前必须归一成 LF，否则整文件几千行换行符变动会把真实改动埋掉，review 也没法看。校验方法：用 node 逐字节数 0x0D，不要用 `grep -c $'\r'`（在 Git Bash 里那会匹配到字面量 r，给出假计数）。

### 4.2 9 个文件

| 文件 | 增/删 | 说明 |
|---|---|---|
| `NEKO/N.E.K.O/static/js/character_card_manager/subscriptions-and-scan.js` | +85 −24 | T1 主改动：转义、URL 白名单、事件委托、进度百分比、详情路径编码 |
| `NEKO/N.E.K.O/tests/frontend/test_workshop_xss_runtime.js` | +543 −0 | T1 node harness（含变异对照与静态契约） |
| `NEKO/N.E.K.O/tests/frontend/test_workshop_xss_node.py` | +31 −0 | T1 pytest 包装（本机因 `nest_asyncio` 缺失跑不了，见 1.3/1.4） |
| `neko-electron-shell/src/window-manager.js` | +35 −11 | T2+T3：子窗按同源发 `webSecurity`、jukebox 开隔离、遗留豁免逐个注释 |
| `neko-electron-shell/src/preload-jukebox.js` | +18 −6 | T3：双模暴露（contextBridge / 直写） |
| `neko-electron-shell/src/main/pet-window-lifecycle.js` | +1 −1 | T2：只补注释，开关不动 |
| `neko-electron-shell/tests/window-hardening.contract.test.js` | +244 −0 | 契约测试（5 项） |
| `neko-electron-shell/package.json` | +3 −0 | 只加 `scripts.test` |
| `docs/WO-270-p0-frontend-electron.md` | +408 −0 | 本施工记录 |

### 4.3 交付自证（可复核的四条）

1. **逐字节一致**：从分支 ref 用 `contents` 接口把 9 个文件下回来，与本地暂存副本 `Buffer.compare === 0`，远端 CR=0。
2. **只动该动的**：`GET /compare/40f6999...594dca5` ⇒ `status: ahead`、`ahead_by: 1`、`behind_by: 0`、`files: 9`，**无删除文件**；四个被改文件的删除行数（24 / 11 / 6 / 1）与本地 `diff -u` 逐一对上，每一处都是「被替换掉的旧 sink」或「同一行补注释」。
3. **tree sha 相等**：远端生成的 tree `bd97b85d…` == 本地构造 tree 的 sha，内容一致不是靠肉眼。
4. **交付时可快进**：建 PR 那一刻 `behind_by 0`，PR 不基于旧基线、不会把别人新推的东西显示成删除。**此后 main 又前移了**（`40f6999` → `5d8485e`，acoustics 与工单文档 7 个文件），`compare 40f6999...5d8485e` 显示与本单 9 个文件**零交集**，PR 仍 `mergeable: true` —— 这条每次看 PR 都要重核，不能沿用。

### 4.4 一个故意没带进来的改动

本机工作区的 `neko-electron-shell/package.json` 把 `devDependencies.electron` 从 `^41.10.3` 改成了 `^42.11.18`。那是「Electron 升级」那条线的改动，**不属于 WO-270**：把它混进这个 PR，会让一次依赖升级看起来像 XSS/隔离修复的一部分，出了事也无法单点回滚。所以交付的 `package.json` 是「远端基线 + 本工单新增的 `scripts.test`」，增删行 `+3 −0`。

对本工单结论无影响：`contextBridge.executeInMainWorld` 要求 Electron ≥28.1，`^41.10.3` 与 `^42.11.18` 都满足；本机运行期读数用的是实装的 42.11.18（§3.2），版本写在读数旁边，没有拿版本宽范围冒充实测。

### 4.5 复现命令汇总

```bash
# T1
cd NEKO/N.E.K.O && node tests/frontend/test_workshop_xss_runtime.js
# => workshop XSS guard runtime tests passed
cd NEKO/N.E.K.O && node tests/frontend/test_workshop_xss_runtime.js --dump   # 贴 DOM 快照用

# T2/T3 契约
cd neko-electron-shell && node --test "tests/*.test.js"
# => # pass 5 / # fail 0

# T3 运行期（真 Electron，一次性窗口 + 临时 userData）
node "D:/my git/_wo270/eharness/main.js"        # 读数见 _wo270/evidence/electron_isolation_scenarios.jsonl
```

证据目录（本机 scratch，不入库）：`D:\my git\_wo270\` —— `eharness/` 探针、`evidence/*.jsonl` 读数、`remote/` 基线 blob、`upload/` 暂存副本。
