# Trae 批量工单 · 2026-08-22 夜班

> 交接背景：陆墨侧已完成授粉系列 A1/A2/A3/C1/C2/C3 + 射频大脑 Phase 4，
> 本单 = **老 3 单 push 收尾** + **新 6 单施工**。FTS5 修复用户已自行推分支，不碰。
> 硬约束：铁律7 密钥不落盘（json 只存环境变量名）；不硬编码凭证；
> 每个 commit 用中文 conventional 格式，提交前跑对应验收测试。

---

## 第零步：git 收尾（先做，全部验收过的存量）

本机 main 分支有 4 个未推 commit + 一批已暂存改动，按顺序处理：

1. **未推的 4 个 commit**（授粉-A1 `4ed8c8fa0` / C1 / A2 / C2，验收记录见各 commit message）：
   `git push origin main` 然后 `git push backup main`（双远程都要）。
2. **已暂存未提交**：`characters/陆墨/capabilities.json`、`system/capability.py`、
   `tests/test_capability.py`（授粉-A3）；`research/planner/`、`tests/test_planner.py`（授粉-C3）；
   `mcpserver/rf_brain/` 的 Phase 4 改动（liquid_backend.py / test_phase4_dsp.py /
   sensor.py / feature_extractor.py / rule_engine.py / decision_layer.py / schemas.py / SELFTEST.md）。
   分三个 commit 提交（A3 / C3 / Phase 4 各一个），提交前跑：
   ```
   pytest tests/test_capability.py tests/test_planner.py mcpserver/rf_brain/test_phase1.py mcpserver/rf_brain/test_phase2.py mcpserver/rf_brain/test_phase3.py mcpserver/rf_brain/test_phase4_dsp.py
   ```
   预期 71 passed, 1 skipped（liquid 对拍在无 DLL 环境跳过，属正常）。推双远程。
3. `wt-overwatch-v6/` 的暂存改动与本单无关，原样保留，不提交不丢弃。
4. 新暂存：`rag/test_corpus/` 三个 PDF（本单已放好，RAG 测试语料），随第 5 单一起提交。

---

## 新单 1 · 授粉-A1 回验（CCv3 人格导出）

已提交（`4ed8c8fa0`），天选7 侧回验即可：
- `pytest tests/test_ccv3_export.py` → 6/6。
- 检查 `characters/陆墨/陆墨.chara_card_v3.json` 与 airi ccc codec schema 字段对齐。
- 若天选7 本地有更新的人格材料（prompt/lorebook 变化），重跑导出脚本并 diff。

## 新单 2 · 授粉-C1 上传 + RAG 三文档测试

C1 本体已提交（`c06fec0a4`，`research/execution/`）。本单重点是 **RAG 验收**：

语料已就位：`rag/test_corpus/`（3 个 PDF，来自 Icom RS-BA1 文档包）：
- `CP210x_USB_driver_ENG_Inst_USB3.0_2.pdf`（CP210x USB 驱动安装指南）
- `Icom_USB_driver_ENG_Inst_USB3.0_0.pdf`（IC-705 Icom USB 串口驱动指南）
- `RS-BA1_manual_ENG.pdf`（RS-BA1 v2 远程控制软件手册）

验收步骤（写成 `tests/test_rag_icom_corpus.py`）：
1. 用 `rag.rag_service.RagService().ingest_document()` 逐个入库 3 个 PDF，断言 success=True 且 chunk 数 > 0。
2. 查询断言（`query()` top_k≥3，命中必须含正确出处）：
   - "IC-705 使用哪种 USB 驱动？" → 命中 Icom USB Serial Port Driver（非 CP210x）。
   - "RS-BA1 Remote Utility 默认使用哪几个 UDP 端口？" → 50001/50002/50003。
   - "安装 USB 驱动前能不能先连 USB 线？" → 明确"装完驱动前禁止连线"语义。
3. 注意：手册 PDF 含大量图示占位文本，解析可能噪声大——命中率断言放宽到 top-5 含关键词即可，
   解析失败（pypdf 缺页）要 fail-fast 报错而不是静默入库空文档（对齐 HIGH-2 既有策略）。

## 新单 3 · 授粉-A2 回验（Lorebook 注入）

已提交（`110fb735a`，`research/lorebook/`），天选7 侧回验：
- `pytest tests/test_lorebook.py` → 13/13。
- 数据源在 `vault/`（材料库/实验/项目笔记）；如 vault 有新增条目，用
  `research/lorebook/build_lorebook.py` 重建 lorebook.json 并跑注入测试。

## 新单 4 · 授粉-C2 回验（SQLite 四表）

已提交（`6acc66719`，`research/memory/store.py`），天选7 侧回验：
- `pytest research/memory/tests/test_store.py` → 9/9。
- 回归检查：Windows 下所有 sqlite3 连接必须显式 close（不用裸 `with sqlite3.connect`，
  该写法不关闭连接会泄漏文件锁）。

## 新单 5 · screen_vision 补全（空壳填实）

先盘点再动手。本机现状（陆墨 2026-08-22 核验）：
- `mcpserver/agent_screen_vision/agent_screen_vision.py`：look_screen 已实现
  （截图→压缩 1280px/JPEG q80→视觉 LLM）。
- `agentserver/dogtag/screen_vision/`：analyzer/config/trigger/metrics 已实现
  （pHash 差异检测 + 规则/AI 匹配 + 主动消息）。

待补全的空壳在天选7 侧自查，候选位置：
- `agentserver/dogtag/screen_vision/trigger.py` 的 send_proactive_message 下游通道；
- 前端（neko-electron-shell / frontend）对主动视觉消息的展示入口；
- `system/health_check.py::check_screen_vision_mcp` 依赖的注册项是否缺失。

验收：
1. 从 dogtag scheduler 触发一次 screen_vision 检查，日志链路完整
   （截图→hash→AI 分析→规则匹配→消息推送，无 NotImplementedError/pass 占位）。
2. `GET` health_check 返回 screen_vision_mcp 状态为健康。
3. 无屏幕变化时差异检测跳过 AI 调用（日志可见 skip）。

## 新单 6 · voice 输入接通（ASR → 对话回路）

现状：TTS 输出链路已通（`voice/output/` + chat.py 的 voice_integration）；
ASR 事件协议已存在（`apiserver/routes/lumo_event.py` 的 `AsrResultEvent`，
`lumo_state.py` 已消费 asr_result），但**采集→识别→送入对话**的输入链路未接通。

可用资产：
- `voice/input/unified_voice_manager.py`（local FunASR / end2end 通义 / hybrid 三模式，PyQt 壳）；
- `voice/input/voice_realtime/adapters/`（local / qwen / openai 适配器已写）；
- 配置：`config.voice_realtime`（voice_mode / api_key 环境变量）。

施工目标：
1. 打通一条不依赖 PyQt 的服务端 ASR 路径：前端音频（或文件）→ apiserver 路由
   → voice/input 适配器识别 → 按 `AsrResultEvent` 协议注入对话（source="voice"）。
2. 优先 hybrid 模式（通义 ASR，key 走环境变量，铁律7）；本地 FunASR 不可用时优雅降级并明确报错。
3. 前端录音按钮如已有（neko-electron-shell），把音频上传端点接上；没有就提供
   `/api/voice/asr` multipart 上传端点 + 用 curl/脚本可验收。

验收：
1. 一段中文语音（可用 TTS 生成再回放录音）→ ASR 返回文本，字错可容忍但非空。
2. 识别结果经 AsrResultEvent 进入对话，陆墨能基于语音内容正常回复。
3. 无麦克风/无 key 场景 fail-fast，错误信息可读。

---

## 明早交付清单

1. 老单 push：4 个授粉 commit + A3/C3/Phase 4 三个新 commit，origin + backup 双远程可见。
2. 新 6 单：A1/A2/C2 回验结论（各一行）；C1+RAG 三文档测试通过；screen_vision 补全
   链路演示日志；voice 输入端到端验收记录。
3. 所有失败如实记录边界，不许伪造通过。
