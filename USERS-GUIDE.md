# 陆墨 Lumo · 使用者导航

> 如果你只是想**用**这个系统（不是改它），从这里开始。
> 调试者/开发者看 README.md；使用者看这个。

## 这是什么

陆墨（Lumo）是一个 AI 伴侣 + 科研助手桌面端：
- **桌宠模式**：Live2D 桌面宠物，会说话、会听、会记住你（NEKO 框架）
- **科研模式**：材料科学助手，能查文献、分析数据、辅助写论文（Lumo 人格）
- **射频模式**（开发中）：无线电频谱大脑，接 IC-705 / LoRa

## 你能做什么（按使用场景）

| 场景 | 怎么做 |
|------|--------|
| 启动陆墨 | 见 README「快速开始」或 `scripts/` 下的启动脚本 |
| 让它记住你的事 | 直接聊天，记忆自动落库（SQLite + 向量） |
| 查科研资料 | 输入材料/课题关键词，走 matchat 桥 + RAG 召回 |
| 分析实验数据 | 把 CSV 丢进 duckdb 工作台（建设中） |
| 看代码/项目结构 | `/graphify <目录>` 生成知识图谱（已装 Hermes skills） |
| 让它推荐思维方式 | 女娲造人：输入人名 → 生成"XX视角"skill |
| 无线电相关 | 看 rf_brain 目录（建设中，别期待完整功能） |

## 关键目录（使用者视角）

| 目录 | 是什么 | 你什么时候会碰它 |
|------|--------|-----------------|
| `frontend/` | 桌面界面（Electron+Vue） | 启动、设置 |
| `apiserver/` | 后端 API（FastAPI） | 基本不用碰 |
| `mcpserver/` | 工具总线（MCP） | 加功能时 |
| `NEKO/` | 桌宠框架 | 桌宠行为/记忆 |
| `skills/` | 186 个技能 | 让陆墨会新技能 |
| `docs/` | 文档/报告/SPEC | 查资料 |
| `rag/` | 知识检索 | 换知识库时 |
| `voice/` | 语音模块 | 语音设置 |

## 日常命令

```bash
# 启动后端
cd apiserver && uvicorn main:app --port 8000

# 启动前端
cd frontend && npm run dev

# 建知识图谱（需 graphify skill）
graphify /path/to/project

# 跑测试
python -m pytest tests/ -x
```

## 求助路径

1. 看 `docs/` 下的报告（授粉/SPEC/评估，都有日期和结论）
2. 看本文件 + 各子模块 README
3. 还不行 → 到 GitHub Issues 提问

---
*维护：2026-08-22*
