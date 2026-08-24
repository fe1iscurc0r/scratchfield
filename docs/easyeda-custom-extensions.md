# EasyEDA Pro 定制扩展四件套（2026-08-22）

体检报告的改造路线全量落地。产物在 **`D:\tools\easyeda-agent\custom-eext\`**，源码在 `github_haul/easyeda/`。安装：EasyEDA Pro → 高级 → 扩展 → 扩展管理器 → 导入扩展 → 选 .eext。需要网络/推送的记得在扩展管理器里把对应扩展的「外部交互」开成"是"。

## 1. parasite-export（寄生链导出器）★ 新写

HW-06 寄生链通道B的第一块砖。菜单「寄生链」（原理图/PCB 页）：
- **导出文档源码**：`getDocumentSource()` → 存本地 `.esch/.epcb`
- **推送到管线**：当前文档元信息+源码打包 POST 到可配置 URL（默认 `http://127.0.0.1:8765/ingest`）——云服 RAG/寄生参数提取直接吃；这同时就是 knowledge-base 对接 scratchpad 的实际通道（云服起个接收端即可）
- **配置管线地址**：URL 存 sys_Storage（扩展配置）
- 依赖：原理图/PCB 页面激活；推送需外部交互=是

## 2. export-design-report（官方 fork，v1.0.17）+ 寄生参数估算

原功能不动，新增菜单 **设计报告 → 寄生参数估算...**：
- 逐网络读长度（`pcb_Net.getNetLength`），按 **IPC-2141A 微带线闭式**估算 Z0/R/L/C（含铜厚有效线宽补偿）
- 4 个顺序输入框收集叠层参数（Er/h/w/t，默认 FR-4 4.4 / 0.2mm / 10mil / 35µm）
- 导出 `ParasiticEstimate.csv`，按长度降序，尾部注明参数与模型（估算级，非场求解）
- 这是 SPEC 寄生链 Phase1 的骨架：网络级 R-L-C 表直接可喂后续射频性能预测

## 3. project-describe（项目描述生成器·开源版）★ 新写

kap1bala 的开源替代（Apache-2.0）。菜单「描述生成 → 打开面板」：
- 面板输入要点草稿 → 自动带工程上下文 → LLM 生成"一句话简介 + README 描述段 + 关键词"
- 默认 **DeepSeek 官方直连**（`https://api.deepseek.com` + deepseek-chat），可改任意 OpenAI 兼容 baseURL
- key 存本机 sys_Storage，**不经任何第三方中转**（对齐体检报告对 opencodego 的风险提示）
- 装了它就可以把闭源的 eext-kap1bala 卸了

## 4. interactive-html-bom（官方 fork，v2.8.1）+ 比价列

iBOM 界面新增 **Sourcing 列**：每行 BOM 两个直链——淘宝搜索 + 立创商城搜索（按 value+footprint 拼查询词）。对齐 SPEC 采购决策（比价走淘宝，立创只做兜底）。列可在表头设置里隐藏。

## 维护说明

- 重建：`cd github_haul/easyeda/<项目> && npm install && npm run build`（Node ≥20，本机用 Trae 自带 v24.18，见 HW-06 记录）
- 改造均为源码级（B/D 是官方开源 fork，A/C 是 SDK 新写），无闭源成分
- 版本对齐提醒：market 版 export-design-report/iBOM 若在线更新会覆盖 fork——长期用建议关掉这两个的自动更新，或重新导入我们的 .eext
