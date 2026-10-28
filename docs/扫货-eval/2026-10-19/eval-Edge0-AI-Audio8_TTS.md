# Edge0-AI/Audio8_TTS 评估

## 1. 项目
- 定位：多说话人 TTS 模型仓（Apache-2.0，星数最高的语音项）
- 星数：**1853** ／ Fork：216 ／ Open issues：11
- 许可：spdx_id = `Apache-2.0`；顶层许可文件 `LICENSE, NOTICE`
- 仓体大小：`59589` KB（≈ 58.2 MB，GitHub 计量，含资产）
- 最近 push：`2026-09-02` ；创建：`2026-07-29` ；语言：`Python`
- archived：`False`

## 2. 协议与架构
- 入口点：推理脚本 + 预训练权重外链
- 关键 API：多说话人合成、音色切换
- 目录骨架（顶层，`gh api contents` 只读拉取，未 clone）：
```
  d .github
  f .gitignore
  f LICENSE
  f NOTICE
  f README.md
  f README_zh.md
  d assets
  f audio8_tts_data.py
  f audio8_tts_infer.py
  f audio8_tts_prepare.py
```
- 顶层共 20 项（截断显示前 10）。

## 3. 本侧对照
- 对应 `mcpserver/tts_api/`（引擎封装层）
- 判断依据：本项与上述模块解决的是同一层问题（多说话人 TTS 模型仓（Apache-2.0，星数最高的语音项）），因此对照点落在接口形态与数据流，而不是功能罗列。

## 4. 授粉价值（3 条）
1. 多说话人切换的接口形态，作为 breeze 之外的备选引擎 → ``mcpserver/``
2. 长文本切分的工程细节（分句→合成→拼接） → ``mcpserver/tts_api/agent.py``
3. 音色列表的组织方式（`list_voices()` 返回结构） → ``mcpserver/tts_api/agent.py``

## 5. 难度 × 收益
- **中 × 中**：权重体积与推理成本未知，先作为备选引擎记录，不排进本季

## 6. 接入模式
- **设计输入**：仓体 59,589 KB ≈ 58 MB，含示例音频；**权重需另行下载**，本单不评估推理质量。
