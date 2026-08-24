# HW-06B 勘察报告：EasyEDA Pro AI 工具链 + API 读取验证

日期：2026-08-22 ｜ 落点：github_haul/easyeda/（4 仓库已 clone，去 .git）｜ 执行机：天选7

## 1. 四仓库深度勘察

### 1.1 pro-api-sdk（扩展开发 SDK）
- **功能**：官方扩展开发工具组（ESLint + esbuild + ts-node 模板），内置 demo，`npm run build` 产出可导入的 `.eext`
- **依赖**：Node + npm（本机用 Trae 自带 node v24.18.0 / npm 11.16 实测通过）；`@jlceda/pro-api-types ^0.4.14`（API 类型定义，Apache-2.0）
- **启动**：`npm install` → 改 extension.json → `npm run build` → 编辑器导入 `build/dist/*.eext`
- **授权**：Apache-2.0（商标仅限功能描述/标题使用）
- **实测**：本机构建成功 → `build/dist/your-extension-name_v1.0.0.eext`（46KB）。**扩展开发工具链已打通**，寄生链 Phase2 自写插件有底座。
- **环境要求**：构建可在云服跑（纯 Node）；产物使用必须进 EasyEDA Pro 客户端

### 1.2 eext-api-test-tool（API 调试工具）★ 最短路径
- **功能**：编辑器内"接口测试"面板（菜单 测试>接口测试）：输入 `类名.方法()` 实时看返回值与类型；历史记录；异步支持
- **依赖**：零依赖——**仓库自带预编译 `build/api-test-tool_v1.0.3.eext`，直接导入即用，不需要 Node**
- **启动**：扩展管理 → 导入该 .eext → 菜单 测试>接口测试 → 输入如 `eda.dmt_SelectControl.getCurrentDocumentInfo()`
- **授权**：官方开源（仓库 LICENSE）；无 API key
- **限制**：GUI 面板人工操作，不适合自动化链路（自动化走 easyeda-agent，见 HW-06 记录）

### 1.3 eext-easyeda-api-agent（大模型 API 助手）
- **功能**：NL/语音 → 自动调用 eda.* 扩展 API；DeepSeek 后端；Markdown 渲染；调用日志调试
- **依赖**：编辑器内运行 + **自配 LLM API 地址/密钥**（设置面板）
- **启动**：导入 .eext → 设置里填 API key
- **授权**：Apache-2.0（上游生态，HW-06 SPEC 已列为生态参考）

### 1.4 eext-chat-with-ai-kimi（Kimi 助手）
- **功能**：AI 问答 + 元件查询（相似物料推荐）+ **网表解析/电路分析**
- **依赖**：编辑器内运行 + **开启"外部交互"**（与 easyeda-agent 连接器同一开关！）+ Kimi API key（获取指南见其 README）
- **启动**：扩展管理启用 → 右下角配置按钮填 key → 菜单 Kimi>Kimi AI 助手
- **注意**：网表解析能力对寄生链 Phase2（连线对账）有直接参考价值

## 2. easyeda 组织全仓清单（GitHub API 实拉，共 30）

扩展类（全部需 EasyEDA Pro 客户端）：pro-api-sdk、eext-api-test-tool、**eext-api-debug-tool**（另一 API 调试工具）、eext-easyeda-api-agent、eext-chat-with-ai-kimi、eext-ai-library-builder、eext-ai-symbol-builder、eext-extension-demo（五合一案例）、eext-generate-schematic-from-netlist（**网表→原理图**，寄生链复刻方向直接相关）、eext-batch-place-components、eext-update-components-attributes、eext-delete-all-components、eext-export-design-report（PCB 统计报告导出）、eext-export-design-archive（批量导出工程压缩包）、eext-plm-integration-demo（PLM 对接参考）、eext-external-tool-integration-demo（**外部工具集成**——与寄生链通道B同构）、eext-coil-creator、eext-graffiti-silkscreen、eext-generate-silkscreen、eext-note-tools、eext-qrcode-generator、eext-pcb-price-calculator、eext-pcb-render-with-blender、eext-simulation-with-ngspice、eext-simulation-with-simulide、eext-freerouting-intergration（自动布线）
独立可跑（无需客户端）：easyeda-pcb-router（Freerouting CLI）、easyeda-simulation-engine（NGspice+SimulIDE 本地引擎）、easyeda-documents、easyeda-std-i18n
另有 easyeda-api-skill（README 提及的官方 AI 编程 SKILL，SDK 官方推荐配合使用）

## 3. API 版本与鉴权结论

| 项 | 结论 |
|---|---|
| API 类型定义 | `@jlceda/pro-api-types` **v0.4.14**（Apache-2.0），**130 个类**；本机 easyeda-agent CLI 索引版为 0.3.12（93 命名空间/742 方法）——SDK 里的更新 |
| 鉴权 | `eda.*` 扩展 API **本身无鉴权、无 API key**；鉴权边界在编辑器登录态（嘉立创账号）+「允许外部交互」开关（管 WebSocket/HTTP 桥） |
| 登录态 | 桌面客户端已登录（你已打开 pro）；网页版同理。**云服无 GUI 跑不了编辑器内 API**，只能跑构建/类型/解析类工作 |
| `eda.editor.getDocument()` | **不存在**（HW-06 已证）。等价链：`eda.dmt_SelectControl.getCurrentDocumentInfo()`（文档元信息）+ `eda.sys_FileManager.getDocumentSource()`（文档源码文本） |

**getCurrentDocumentInfo() 返回结构（类型定义原文，v0.4.14）：**
```ts
interface IDMT_EditorDocumentItem {
  documentType: EDMT_EditorDocumentType;  // 文档类型（原理图/PCB/库…枚举）
  uuid: string;                            // 文档 UUID
  tabId: string;                           // 标签页 ID
  parentProjectUuid?: string;              // 所属工程 UUID
  parentLibraryUuid?: string;              // 库文档所属库 UUID
}
```
完整原理图数据再走 `getDocumentSource()` 拿源码字符串（.esch 行式 JSON），与 HW-06 离线解析脚本 `read_schematic.py` 的 file 模式同构——两环已对上。

## 4. 最短路径验证记录

按工单优先级选 eext-api-test-tool 路线：
1. ✅ 仓库 clone 完成，**预编译 .eext 在位**：`github_haul/easyeda/eext-api-test-tool/build/api-test-tool_v1.0.3.eext`（无需 Node 构建）
2. ✅ 备选路径同时就绪：SDK demo 构建成功（证明能自产 .eext）；easyeda-agent daemon 活着（60832）
3. ⏳ 导入动作（编辑器 GUI，无法无人值守）——两种等价方式任选：
   - 调试面板：导入 `api-test-tool_v1.0.3.eext` → 测试>接口测试 → 输入 `eda.dmt_SelectControl.getCurrentDocumentInfo()`，面板直接显示返回 JSON（= getDocument 等价验证）
   - 自动化：导入 `D:\tools\easyeda-agent\easyeda-agent-connector.eext` + 设置开启"允许外部交互" → 终端 `easyeda project doc`（HW-06 已铺好）
4. 踩坑：trae 自带的 node 不在 PATH（全路径调用解决）；npm 11.16 的 allow-scripts 会拦 simple-git-hooks postinstall（不影响构建）；两个 AI 助手扩展都要自备 LLM key，调试工具不要。
5. **实机补充（2026-08-22 20:30）**：easyeda-agent 连接器链路已实机闭环（详见 HW-06 记录第 5/7 节）——"外部交互"开关位置在扩展管理器表格的按扩展列，不在全局设置；实机 `project doc` 返回样例：`{"documentType":"home","documentTypeCode":-1,"tabId":"tab_page1","uuid":"tab_page1"}`，与 IDMT_EditorDocumentItem 字段一一对应。

## 5. 验收对照

- ✅ github_haul/easyeda/ 下 4 仓库全 clone
- ✅ 勘察报告列 30 仓清单 + 4 仓深度功能/依赖/启动/授权
- ✅ getDocument 等价读取的结构化样例：类型定义级（IDMT_EditorDocumentItem 全字段）+ 离线 .esch 解析实测（HW-06 的 mini_ldo 样例）；**编辑器内实机返回值待导入后一步到位**
- ✅ 客户端/云服依赖矩阵：扩展类 26 个全部需客户端；云服可独立跑的仅 build/类型/解析/CLI 类（pro-api-sdk 构建、pro-api-types、pcb-router、simulation-engine、read_schematic.py 离线模式）
- ✅ 未触碰付费/企业功能；寄生参数提取未提前做
