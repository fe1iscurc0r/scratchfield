# 工单204 任务三 · CI 等价 lint 债收口记录（2026-10-11）

> 一句话结论：**main `727853ac74` 上的 CI 等价 lint 实测为 369 错 / 10 文件（222 文件被扫），
> 其中 366 错集中在任务三的拆分产物上。** 本条流水把它清零（8 文件 / +357 −378 行），
> 并用产物级逐字节比对证明**行为等价**。

---

## 1. 起因

`TRAE_WORKORDER_PROMPT_AGENT_204.md` 任务三的验收条款第二条写的是：

```
- [ ] 全程 CI 绿（lint/smoke 若闸门未开则本地等价复现，参照 ci.yml 注释的两步法）
```

而 `.github/workflows/ci.yml` 里 `lint` job 挂着 `if: ${{ vars.ENABLE_LINT == 'true' }}`，
**变量默认为空 ⇒ 该 job 长期 skipped**。也就是说：任务三把 App.vue / SkillView / ForumSidebarRight
拆完之后，**"CI 绿" 这件事从来没有被真正执行过**，验收条款处于「未验证即打勾」的状态。

本卷即补做这一步：按 ci.yml 注释的两步法在本地等价复现，把暴露出来的错误清零。

## 2. 基线与范围（实测）

**扫描范围**（不是全仓！）：`frontend/scripts/run-eslint.mjs` 定义

```js
const defaultTargets = ['src', 'electron', 'eslint.config.js', 'vite.config.ts']
```

`npm run lint` = `node scripts/run-eslint.mjs`，并且**没有** `--max-warnings`
⇒ **warning 不挂 CI，只有 error 会挂**。tests / tools / scripts / package.json / docs 不在范围内。

**基线实测**（在 main `727853ac74` 的工作区上跑 CI 等价命令）：

```
node node_modules/eslint/bin/eslint.js src electron eslint.config.js vite.config.ts
→ 222 files scanned / 369 errors / 2 warnings / 10 files with problems
```

| 文件 | 错误数 | 主要规则 | 属任务三产物？ |
|---|---:|---|---|
| `src/views/skill/SkillMcpSection.vue` | 129 | `vue/html-indent` ×123 | ✅ |
| `src/forum/components/ForumStatsPanel.vue` | 84 | `vue/html-indent` ×82 | ✅ |
| `src/forum/components/ForumUnlockDialog.vue` | 80 | `vue/html-indent` ×79 | ✅ |
| `src/views/skill/SkillSection.vue` | 51 | `vue/html-indent` ×48 | ✅ |
| `src/views/SkillView.vue` | 14 | `unused-imports/no-unused-imports` ×8 | ✅ |
| `src/forum/components/ForumSidebarRight.vue` | 7 | unused-imports ×3 + no-unused-vars ×2 | ✅ |
| `src/views/config/ToolHealthTab.vue` | 3 | if-newline / prefer-separate-static-class / quote-props | ❌ |
| `src/api/core.ts` | 1 | `perfectionist/sort-imports` | ❌ |

规则聚合：`vue/html-indent` **333（90%）**、`unused-imports/no-unused-imports` 11、
`style/no-multiple-empty-lines` 8、`vue/block-tag-newline` 4、`antfu/if-newline` 3、
`perfectionist/sort-imports` 2、`unused-imports/no-unused-vars` 2、`style/member-delimiter-style` 2、
`vue/prefer-template` 2、`vue/prefer-separate-static-class` 1、`vue/quote-props` 1。

### 根因

**不是**写错了代码，而是**抽取子组件时只做了"内容搬移"，没有归一新容器的缩进**。
被抽出的模板片段原本嵌在父组件更深的缩进层里（例如 `SkillMcpSection` 的 `<section>` 下原本
多缩进 4 空格），搬进独立 `.vue` 后 `<template>` 根元素缩进层级变了，但内部子节点沿用了旧缩进。
`vue/html-indent` 由此报 333 处 —— 占了全部错误的 90%。

`SkillView.vue` 的 8 处则是抽取后遗留的未使用 import（组件与工具函数已下沉到子组件）。

## 3. 修复过程

### 3.1 自动修复：369 → 2

```
node node_modules/eslint/bin/eslint.js <8 个文件> --fix
→ exit 1（仍有 2 处不可自动修）；错误数 369 → 2
```

### 3.2 手工处置 2 处（`ForumSidebarRight.vue`）

```
 8:7   error  'router' is assigned a value but never used.  unused-imports/no-unused-vars
 9:18  error  'load' is assigned a value but never used.    unused-imports/no-unused-vars
```

实测确认（非推断）：`router` 全文件仅 L9 声明 1 次、模板零引用；`load` 仅 L10 解构 1 次；
`profile` 被正常使用。故删 `const router = useRouter()` 及其 import、解构改为 `const { profile } = ...`。

### 3.3 顺带清掉一处静默残渣（eslint 与 build 都测不到）

`ForumSidebarRight.vue` 的 `<style scoped>` 末尾有一个**孤立的 `}`**（上次拆分时的残留）：

```css
.level-badge {
  border: 1px solid;
  background: rgba(255, 255, 255, 0.03);
  line-height: 1;
}

}        ← 这一行
</style>
```

⚠️ **eslint 测不到它**（css 不在解析器覆盖范围），**`vite build` 也不报错**（postcss 容忍）。
属"静默残渣"，**只能靠人眼/本记录显式点名**。已在本次一并删除。

### 3.4 一个工具链坑：`--fix` 跨 filePattern 冲突会整体失败

实验期间曾误让 `$FILES` 为空（bash `mkdir -p /d/...` 在 Git Bash 下报 `Not a directory`，
`&&` 链中断），导致 eslint 退化为扫全目录；此时 `--fix` 因**跨 filePattern 规则的修复区间冲突**
直接 `exit 1` 且**一个字都不写盘**。事后用 tree API 逐 blob 比对证明工作区 282 文件全一致、0 被改。
结论：`--fix` 失败时是"全有或全无"，不会留下半成品。

## 4. 逐文件改动分类（三层判据）

判据：① 逐行 diff；② 去掉每行首尾空白后比对（暴露"拆行"类改动）；
③ 去掉**全部**空白后比对（暴露真实 token 改动）。
行数采用 **GitHub numstat 口径**（`GET /pulls/{n}/files`），比 difflib 的 hunk 分组口径权威。

| 文件 | +/− 行 | 类型 | 真实改动 |
|---|---:|---|---|
| `views/skill/SkillSection.vue` | +46 / −49 | **纯缩进**（token 全等） | 无 |
| `forum/components/ForumStatsPanel.vue` | +89 / −89 | 缩进 + 1 处拆行 | `if (!q \|\| q.dailyBudget === 0) return 0` → 两行 |
| `forum/components/ForumUnlockDialog.vue` | +86 / −85 | 缩进 + 1 处拆行 | `if (v) pulseTimeline()` → 两行 |
| `api/core.ts` | +1 / −1 | **仅 import 排序** | `sentinelMethods` 一行移到字母序位置（字节数不变 2466B） |
| `views/config/ToolHealthTab.vue` | +4 / −3 | 3 处 | ① `if (timer) clearInterval(timer)` 拆两行；② `:class="['badge', x]"` → `class="badge" :class="[x]"`；③ `:class="{ 'err': … }"` → `{ err: … }` |
| `views/skill/SkillMcpSection.vue` | +118 / −120 | 缩进 + 3 处 | ① `interface { a: string; b: string }` → 逗号分隔；② ③ 两处 `:title="'缺依赖：' + x"` → 模板字面量 |
| `views/SkillView.vue` | +2 / −13 | **删 8 个未使用符号** | `McpService` / `SkillCatalogItem` / `Dialog` / `computed` / `API` / `EmptyState` / `SkeletonCard` / `feedback` |
| `forum/components/ForumSidebarRight.vue` | +2 / −9 | **删 6 个未使用符号 + CSS 残渣** | `Dialog` / `computed` / `onMounted` / `useRouter` / `router` / `load`，以及 §3.3 的孤立 `}` |

**8 个代码文件合计 +348 / −369 行**（本记录文档为新增，行数另计）。

**删除安全性人工核实**（`unused-imports` 规则**不感知模板**，必须人工确认）：

- `SkillView.vue` 模板只用到 `BoxContainer` / `SkillMcpSection` / `SkillSection` / `SkillHelpDialog`；
  脚本只用 `ref`。**无 `<EmptyState>` / `<SkeletonCard>` / `<Dialog>`，也无 kebab-case 形式** ⇒ 删除安全。
- `ForumSidebarRight.vue` 模板用到 `ForumStatsPanel` / `ForumUnlockDialog` / `profile` / `levelColor` /
  `openUnlockDialog` / `unlockDialogVisible` / `unlockPercent` ⇒ 被删的 6 个符号模板零引用，删除安全。

## 5. 验收（before / after，本机同环境同命令）

| 项 | 改前（main `727853ac74`） | 改后 |
|---|---|---|
| **eslint（CI 等价，222 文件）** | **369 错** / 10 文件有错 | **0 错** / 0 文件有错 |
| eslint warnings | 2 | 2（**同一批**，见 §7.3） |
| `vue-tsc -b` | exit 0 / 0 错 | exit 0 / 0 错 |
| `vue-tsc --noEmit -p tsconfig.app.json` | exit 0 / 0 错 | exit 0 / 0 错 |
| `vite build` | exit 0 / 1243 模块 | exit 0 / 1243 模块 |
| 入口 chunk 体积 | 174.75 kB / gzip 57.53 kB | 174.75 kB / gzip 57.53 kB |
| 入口 chunk 内容 hash | `index-BJ53aWIv.js` | `index-CAujGHJj.js`（见 §6） |
| `dist/assets/index-*.css` | `index-E5q5wf-Z.css` 88.33 kB | **同 hash 同字节** |
| `node --test` | 77 pass / 0 fail | 77 pass / 0 fail |
| `vitest run` | 5 files / 29 passed | 5 files / 29 passed |
| 8 文件体积合计 | — | 净 −1383 B |

## 6. 行为等价的**产物级**证明（逐字节）

仅有"测试通过"还不够 —— `node --test` / `vitest` 覆盖不到这些视图组件。故补做产物级比对：

1. 保存改后 `dist/`；回滚 8 个文件到 main 版本重建 → 复现出**完全相同的 base hash**
   （`index-BJ53aWIv.js`，证明构建是确定性的）。

2. `index-*.js` 全长 174755 B，**体积完全相同**，逐字节比较有 **388 字节差异，分布在 39 个区段**。
   逐一核验：**39 个区段全部只是 lazy chunk 的文件名哈希**，形如

   ```
   "./SkillView-BFovRPN0.js"  →  "./SkillView-D8QRs11z.js"
   ```

   出现在 `__vite__mapDeps` 数组、动态 `import()` 说明符、路由表 `load:` 惰性工厂中。
   即：**index 的 hash 变化是级联结果**（子 chunk 内容变 → 其文件名 hash 变 → index 里引用它们的字符串变），
   **不含任何逻辑字节差异**。

3. 全量比对两棵 `dist/` 树（152 文件 / 152 个 chunk stem，集合完全一致）：25 个文件字节不同，
   其中 **5 个**的差异"超出纯哈希引用" —— 逐个解释如下：

| 文件 | 归一化后的差异 | 判定 |
|---|---|---|
| `ConfigView.css` / `SkillView.css` | 只有 `data-v-<hash>` 作用域 id 变了 | Vue SFC 源码内容变 ⇒ scopeId 变；**规则体字节完全相同**，且 JS 侧用的是同一个新 id ⇒ 样式仍正确配对 |
| `ConfigView.js` | 1 处：`class:u(["badge",cond])` → `class:u(["badge",[cond]])` | `normalizeClass` 会**递归展平嵌套数组**，二者产出的 class 字符串相同 ⇒ 等价 |
| `SkillView.js` | 1 处：`title:"缺依赖："+x` → `` title:`缺依赖：${x}` `` | 字符串拼接 vs 模板字面量，**运行时产出同一字符串** ⇒ 等价 |
| `core.js` | 变量名与 spread 顺序的**字母**序列变了 | 见下方专项核验 ⇒ 合并顺序**未变** |

4. **`core.js` 的合并顺序专项核验**（唯一有实际语义风险的改动）：
   `api/core.ts` 的 `domains` 对象字面量（15 个 `...xxxMethods`）**源码文本完全未改**；
   变的只是 import 行顺序。而 `Object.assign(CoreApiClient.prototype, domains)` 中
   **同名键后写覆盖先写**，若合并顺序真的变了、且存在跨域重名方法，就是真回归。

   实测：把两侧 bundle 的压缩变量名映射回模块（用 `getSentinelNodes`→sentinel、`elnList`→eln、
   `importLawCases`→law、`getMarketItems`→market、`getLive2dActions`→media、`getMemoryStats`→memory、
   `listPapers`→papers 作为指纹）：

   ```
   AFTER 字母: L D N I M E R j w P A k T O F   → ? ? memory ? media ? ? market ? papers law eln ? ? sentinel
   BASE  字母: L D P I N E R M w F j A T O k   → ? ? memory ? media ? ? market ? papers law eln ? ? sentinel
   >>> 模块序列完全一致 = True
   ```

   即：**7 个可解析位置逐一对应同一模块，合并顺序未变**；字母重排只是 rolldown 按 import 顺序
   重新分配压缩变量名的结果。

## 7. 附带发现（本次实测）

### 7.1 `ci.yml` bootstrap 注释已失真

`.github/workflows/ci.yml` 内注释声称"本地已按 CI 两步复现并通过（… frontend `npm ci && npm run lint` → 0 error）"。
**本次实测该说法在 main `727853ac74` 上不成立（实为 369 错）** —— 该注释是闸门刚落地时写的，
后续任务三的拆分把 lint 打红，注释却没有跟着更新。**它给人以"已验证"的假象，比没有注释更危险。**

### 7.2 `src/forum/` 子树是死代码，不进包

`Forum*View.vue`（8 个）都 `import ForumSidebarRight`，路由表却把 `/forum` 直接
`redirect: '/'`（含 `pathMatch(.*)*` 通配）。实测 `dist/` 中**搜不到任何 `forum` 相关字符串**、
也没有 Forum chunk ⇒ 整个子树被 tree-shake 掉。

后果：任务三里拆的 3 个 forum 文件（`ForumSidebarRight` / `ForumStatsPanel` / `ForumUnlockDialog`）
**无法用 bundle 差分验证"页面行为不变"**（页面根本不可达），只能靠类型检查 + 单测 +
逐行等价性证明（§4）。这一点值得单独决策：子树是留作未来启用，还是清理。

### 7.3 残余 2 条 warning（本次不定，原因见下）

```
src/components/NetworkCanvas.vue:25      Unused eslint-disable directive (e18e/prefer-array-fill)
src/utils/spectrumTraceRenderer.ts:287   Unused eslint-disable directive (e18e/prefer-array-fill)
```

- 均为 `severity: 1`（warning），**eslint 退出码仍为 0，不挂 CI**（`run-eslint.mjs` 无 `--max-warnings`）。
- 两文件**不在本次错误清单内**，属既有噪声，与任务三无关。
- 本次**刻意不改**：删 `eslint-disable` 注释属独立语义改动，会扩大本 PR 范围。

## 8. 残留与后续（未在本卷处理）

1. **`ci.yml` 那句失真注释**：属 workflow 文件。本 PR 未动 `.github/`；建议单独一卷更正，
   并把 `ENABLE_LINT` 闸门的默认值/说明与实际状态对齐。
2. **`src/forum/` 死代码**：需产品侧决策（启用 / 删除）。
3. **2 条 unused-disable warning**：可顺手清零，但属独立范围。
4. **仍在的规则盲区**：`App.vue` 是 `<script>` + `<script setup>` 双 script 块结构，
   该结构下 `ts/no-use-before-define` 对 `.vue` **实际失效**（已由步骤⑥ 的最小对照实验定性）。
   属解析器/规则层面问题，未处理。
5. **`--fix` 跨 filePattern 冲突**：已知会整体失败（§3.4），未做工具侧加固。

## 9. 复现命令（本卷全部结论的原始凭据）

```bash
cd frontend

# ① CI 等价 lint（精确范围见 scripts/run-eslint.mjs 的 defaultTargets）
node node_modules/eslint/bin/eslint.js src electron eslint.config.js vite.config.ts
#    基线：222 files / 369 errors / 2 warnings  →  本卷：222 files / 0 errors / 2 warnings

# ② 类型
node node_modules/vue-tsc/bin/vue-tsc.js -b
node node_modules/vue-tsc/bin/vue-tsc.js --noEmit -p tsconfig.app.json

# ③ 构建（产物 hash 用于 §6 的等价性证明）
node node_modules/vite/bin/vite.js build     # 1243 modules

# ④ 测试
node --test --experimental-strip-types tests/*.test.ts   # 77 pass
node node_modules/vitest/vitest.mjs run                  # 5 files / 29 passed
```
