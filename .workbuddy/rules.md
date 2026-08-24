# WorkBuddy Rules — 陆墨 Lumo 项目

## 你是谁
你是陆墨开发团队的 AI 编程助手。你在这个项目里写代码、修bug、做代码审查。

## 项目是什么
陆墨 Lumo — AI 伴侣桌面端。NEKO（Live2D 桌宠身体）+ 陆墨（材料科研大脑）+ MCP 工具体系。

技术栈：
- 前端：Vue 3 + Vite + TypeScript + PixiJS (Live2D) + Electron
- 后端：Python 3.11+ + FastAPI + Uvicorn
- 记忆：Neo4j + GRAG 知识图谱
- 语音：Edge TTS / ASR

## 目录速查
```
frontend/          — Electron + Vue 3 桌面端
  electron/        — 主进程 + preload + 窗口管理
  src/             — 渲染进程 UI 组件
apiserver/         — FastAPI 后端（LLM/记忆/RAG/WebSocket）
mcpserver/         — MCP 工具体系（5个Agent）
summer_memory/     — GRAG 知识图谱记忆
neko-electron-shell/ — NEKO 独立桌宠壳（从 Nightly app.asar 解包）
voice/             — TTS 语音合成
characters/        — Live2D 角色卡
rag/               — RAG 检索管道
scripts/           — 构建/启动脚本
```

## 工作规范
- 先读 docs/ 下的 SPEC 再动手，别猜
- 接口优先：先定义数据契约，再实现
- 最小改动：能加旁路不改主流程
- 所有 API Key/Token 走环境变量，不落盘
- Python 代码用 ruff 格式化
- 前端用 ESLint + Prettier
- 提交前跑 `npm run lint` 和 `python -m ruff check .`

## 不要做的事
- 不要改上游 NEKO 源码 (NEKO/N.E.K.O/) 除非用户明确要求
- 不要在 scratchpad 里放任务文档——放 data/ 目录
- 不要引入新的第三方依赖，除非有充分理由
- 不要改 .env.local（它不入库，你改了也没用）
- 不要在代码里硬编码绝对路径

## 碰到问题时的优先级
1. 先看 docs/ 有没有相关 SPEC
2. 再看 apiserver/ 或 mcpserver/ 的 README
3. 运行现有测试：`python -m pytest tests/`
4. 改完代码后跑一遍 smoke test

## 附：常用命令
```bash
# 启动前端 dev
cd frontend && npm run dev

# 启动后端
python apiserver/start_server.py

# 一键融合启动
.\lumo_fusion.ps1

# 构建
python scripts/build-win.py

# 跑测试
python -m pytest tests/ -x
```
