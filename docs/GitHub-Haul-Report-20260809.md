# GitHub 扫货日报 — 2026-08-09

> 扫货时间：2026-08-09 10:00 CST
> 定位：AI伴侣 + Live2D桌宠 + MCP工具 + 记忆系统 + 材料科研
> 授粉视角：不只垂直扩展，重点看跨域错位使用机会

---

## A 级 — 高度匹配

### Open-LLM-VTuber ⭐10k+ | MIT
- https://github.com/Open-LLM-VTuber/Open-LLM-VTuber
- Live2D + 语音打断 + 视觉 + 桌宠，跨平台(Win/Mac/Linux)
- **可借鉴**：VAD状态机→语音打断链、Agent装饰器抽象、Live2D表情映射
- **授粉机会**：语音打断的 asyncio.Task 取消链 → 可用于 MCP 工具执行超时强制终止
- **v2.0 重写中**，趁现在看 v1 的坑
- 许可：MIT ✅ 可直接参考代码

### Soul-of-Waifu ⭐高 | GPL-3.0
- https://github.com/jofizcd/Soul-of-Waifu
- 最完整的桌面AI伴侣：四层认知记忆 + MCP桌面工具 + RPG引擎 + 神经激素
- **可借鉴**：Soul Memory 四层架构(心理层/关系档案/情景记忆/日记)
- **授粉机会**：神经激素模拟系统 → Agent情绪衰减曲线，可独立实现
- ⚠️ GPL-3.0：只能参考设计，代码不入库

---

## B 级 — 桌面组件

### Live2DPet + Live2DPet-Enhanced | 2026年
- https://github.com/x380kkm/Live2DPet
- https://github.com/dwgx/Live2DPet-Enhanced
- 纯 Live2D 桌宠 + VOICEVOX TTS
- Enhanced版加了记忆系统和模型显示改进
- **授粉机会**：可作为 NEKO 桌宠窗口的轻量替代方案参考

### DesktopBuddy | 2026年
- https://github.com/DCDingCong/desktopbuddy
- Windows桌宠：Live2D + 物理引擎 + Ollama + 一键主题生成
- **授粉机会**：物理引擎(Live2D物理) → 桌宠交互的物理反馈

### desktop-agent-runtime | 2026年
- https://github.com/lulu930128/desktop-agent-runtime
- 本地优先 AI 伴侣运行时，集成 OLV + GPT-SoVITS + Live2D + 记忆
- **授粉机会**：launcher 编排设计 → 改进 lumo_fusion.ps1

---

## C 级 — 记忆/知识引擎

### cognee | 活跃开发中
- https://github.com/topoteretes/cognee
- 开源AI记忆平台：知识图谱+向量混合，自托管
- 活跃（昨天有提交），已有多个集成案例(Letta/AgentOS)
- **授粉机会**：作为 summer_memory/GRAG 的替代/补充评估

### Agent_Memory_Techniques | 2026年
- https://github.com/NirDiamant/Agent_Memory_Techniques
- 30个Jupyter Notebook：Mem0/Letta/Zep/Graphiti/LoCoMo 全方案对比
- **授粉机会**：可直接跑的内存技术对比，选型参考

---

## 跨界授粉发现

### PEG 解析器 → 化学式分词
- 编译器领域的 PEG (Parsing Expression Grammar) 可以精确解析化学式
- 自然语言分词器(MeCab等)无法处理 H₂SO₄ → {H:2, S:1, O:4}
- 落地点：mcpserver/material_science/

### 游戏中存档模式 → Agent 对话 Checkpoint
- Sequence/Deserialize 模式天然适合多轮对话的持久化
- 比数据库 + ORM 更简洁，适合"存就存，恢复就恢复"

---

## 下次扫货关键词

```
MeCab 日语分词    → 化学式分词
Bullet Physics    → 晶体结构模拟  
Raft Python       → 多Agent共识
CRDT              → 离线记忆同步
zk-SNARKs Python  → 知识隐私验证
```
