# EasyEDA Pro 已装插件体检报告 + 改造评估

日期：2026-08-22 ｜ 方法：IndexedDB blob（`LCEDA-Pro/cache.x64.3/IndexedDB/https_client_0.indexeddb.blob`，1322 文件/548MB）逐文件静态审计（`scripts/easyeda/audit_extensions.py`），24 个扩展全部映射到代码 blob，扫外联域名/危险 API/混淆特征。

## 结论：无恶意插件，两处建议关注，三个可优化点

### 分级清单

**✅ 官方开源（github.com/easyeda，可审计可改造）**
| 插件 | 审计结果 |
|---|---|
| eext-update-components-attributes | 外联仅 szlcsc.com（LCSC 元件资产，功能本体）；含 eval/new Function——是捆绑的 element-ui 运行时模板编译，官方库标准行为，非遗留风险 |
| eext-qrcode-generator | 干净；2.5MB 是自带文档/徽章资源，虚胖无害 |
| eext-export-design-report | 干净 |
| eext-simulation-with-ngspice | 干净 |
| eext-simul（=simulide） | 27.5MB wasm 仿真引擎本体；XHR/fetch/atob 均为 wasm 加载器标准行为 |
| easyeda-agent-connector | 第三方（zhoushoujianwork，MIT 开源）；WebSocket 仅连 127.0.0.1:60832，今日已实机验证 |

**✅ 市场闭源但行为正常（外联与功能声明一致，无混淆、无文件系统/子进程访问）**
eext-balance-copper、eext-timing-diagram-tool（wavedrom.com 渲染时序图）、eext-pad-fanout、eext-export-hyperlynx、eext-knowledge-base（huggingface/ollama/modelscope——本地/开源模型下载源）、eext-mcad-integration-with-{freecad,fusion360,solidworks}（WebSocket 桥本机 CAD，与连接器同模式）、eext-kipida-integration（KiCad 互操作）、eext-gerber-viewer、eext-ai-device-standardization、eext-interactive-html-bom、eext-schematic-pdf-interaction（pdf.js iframe 模式：postMessage+document.write 正常）、eext-filter-designer、eext-datasheet-helper、eext-export-pcb-to-svg（new Function 来自捆绑库）、eext-device-attribute-editor

**⚠️ 建议关注（不是恶意，是使用面问题）**
1. **eext-kap1bala「项目描述生成器」**（发行方：卡皮巴拉，v1.0.0，闭源）：BYO-key 调 LLM，端点含 deepseek/openai/anthropic/moonshot/minimax/siliconflow/小米/**api.opencodego.com**（小众中转站，key 会过它手）。API key 存 localStorage（扩展沙箱内，但 Electron profile 内其他组件可读）。**建议：不用就卸；用的话 key 别用主力号，或走 opencodego 之外的直连端点。**
2. **重量级插件拖慢编辑器**：eext-simul 27MB + qrcode 2.5MB + update-components 2.3MB——simulide 仿真不用时可在扩展管理器停用，按需再开。

## 改造路线（按性价比排序，SDK 工具链今日已验证可用）

1. **自写寄生链薄扩展**（推荐首选）：pro-api-sdk demo 构建已跑通，照 SDK 写一个"文档源码导出器"——一键 `getDocumentSource()` → 落盘/POST 云服，直接喂 HW-06 寄生链 Phase1 管线。这是 SPEC 通道B缺失的第一块砖。
2. **改造官方开源插件**（可直接 fork）：update-components-attributes / export-design-report / api-test-tool 都是 Apache 系开源、仓库在本地 github_haul/easyeda/。例：export-design-report 加"网络长度表 → 寄生参数估算"输出，就是 SPEC 寄生链 Phase1 的现成骨架。
3. **重写 kap1bala**：闭源不可改，用 SDK 重开一个开源版，端点固定 DeepSeek 直连 + key 走环境变量，顺便支持"选中网络 → 生成设计说明"（对齐 SPEC 的 BOM/复刻文档流）。
4. **knowledge-base 对接 scratchpad**：它已支持 ollama——把云服 RAG 的 embedding 接口暴露给它，EDA 内直接查知识库（跨系统粘合，二期）。
5. **interactive-html-bom 定制比价**：fork 后 BOM 导出走淘宝/闲鱼比价链（SPEC 核心决策：不走立创商城）。

## 技术备注
- 扩展代码不存在磁盘明文目录，全在 IndexedDB blob；审计脚本按 `eext-*` 标识符归属，689 个未匹配 blob 为编辑器自身库。
- 「外部交互」开关按扩展独立授权（今日排障实录见 HW-06 记录第 7 节）：mcad/knowledge-base 等需要本机 WebSocket 的插件，若失联先查该列。
