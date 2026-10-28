# breezeblue-ai/breeze-tts 评估

## 1. 项目
- 定位：轻量 TTS 模型（支持方括号情绪标记，如 [笑]/[叹气]）
- 星数：**621** ／ Fork：98 ／ Open issues：4
- 许可：spdx_id = `Apache-2.0`；顶层许可文件 `LICENSE`
- 仓体大小：`151` KB（≈ 0.1 MB，GitHub 计量，含资产）
- 最近 push：`2026-10-13` ；创建：`2026-08-25` ；语言：`Python`
- archived：`False`

## 2. 协议与架构
- 入口点：推理脚本 + 模型权重（权重不在仓内）
- 关键 API：`synthesize(text, voice, speed)` 类接口；情绪标签解析
- 目录骨架（顶层，`gh api contents` 只读拉取，未 clone）：
```
  f .dockerignore
  f .gitignore
  f LICENSE
  f README.md
  d assets
  d breeze_infer
  d configs
  d docker
  f infer.py
  d models
```
- 顶层共 12 项（截断显示前 10）。

## 3. 本侧对照
- 对应 `mcpserver/tts_api/`（现有 TTS 封装形态：一个引擎一个目录一个 Agent 类）
- 判断依据：本项与上述模块解决的是同一层问题（轻量 TTS 模型（支持方括号情绪标记，如 [笑]/[叹气]）），因此对照点落在接口形态与数据流，而不是功能罗列。

## 4. 授粉价值（3 条）
1. 情绪标记解析（`[笑]` 等）独立成函数，供现有 TTS Agent 复用 → ``mcpserver/breeze_tts/agent.py``
2. 按 `tts_api` 同构新增 provider（`name/display_name/synthesize/list_voices/health`） → ``mcpserver/breeze_tts/agent-manifest.json``
3. 权重路径走环境变量的约定（缺失时抛可读 RuntimeError 而非崩服务） → ``mcpserver/breeze_tts/agent.py``

## 5. 难度 × 收益
- **低 × 中**：纯封装 + 一个解析函数，工作量小；收益是拿到情绪化语音这条能力

## 6. 接入模式
- **MCP**：**宣称标注**：对「Artificial Analysis 开放权重第一」类榜单说法一律标 **待核实**，不写进任何对外文档。本单不下载权重（`BREEZE_TTS_MODEL_DIR` 缺失即报可读错误）。
