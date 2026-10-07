# QUICKSTART — 从 clone 到第一个界面

> 最短路径，中文优先。遇到问题先跑体检命令，再看文末「卡住了？」。

## 0. 前置（只列必装）

| 依赖 | 版本 | 说明 |
|---|---|---|
| Python | **3.12.x（严格，不是 3.13）** | `requires-python = ">=3.12,<3.13"` |
| Node.js | ≥ 20.19 | 只用 npm（本仓有 package-lock.json） |
| uv | 最新 | 后端一律 `uv sync`，**不要裸 pip install** |

## 1. 拉库并自检工具链

```bash
git clone https://github.com/fe1iscurc0r/scratchpad && cd scratchpad
python doctor_env.py          # 缺什么报什么，附可直接粘贴的安装命令
```

## 2. 装依赖

```bash
uv sync                       # 后端（要判例/论文 PDF→MD 加 --extra pdf2md）
cd frontend && npm install && npm run build && cd ..
```

> Windows 全自动：`.\setup.ps1`（= 自检 + 上面两步 + 构建）。

## 3. 填两份配置

```bash
cp config.json.example config.json   # 填入 LLM API key
cp .env .env.local                   # 填入 MCP_API_KEY 等敏感配置
```

## 4. 安装后体检（卷186-B2）

```bash
.venv/Scripts/python.exe scripts/doctor.py        # Windows
python3 scripts/doctor.py                         # Linux / macOS
# 加 --quick 跳过前端现场构建，只查产物存在性
```

逐项 ✅/⚠️/❌ + 修复建议：依赖导入、.env.local 占位符、数据目录可写、
前端构建产物（`doctor_env.py` 管**装机前**的工具链，本脚本管**装机后**的应用层）。

## 5. 启动

```bash
cd frontend && npm run dev    # dev 模式自动拉起后端
```

看到工作台界面、设置里填好 LLM API key 能正常对话 —— 完成。

---

## 卡住了？

- 体检某项 ❌ → 按输出里的「↳ 修复建议」处理
- 工具链缺件 / 端口占用 → `docs/环境依赖清单-Windows装机-2026-09-27.md`
- Windows 一键启动全家桶（后端 + NEKO 桌宠 + Electron Shell）：
  `.\lumo_fusion.ps1`（最小启动加 `-NoNeo4j -NoFrontend`）
- 普通用户免构建路线：到 [Releases](https://github.com/fe1iscurc0r/scratchpad/releases)
  下载 `陆墨-Setup-x.y.z.exe` 双击安装（仅 Windows x64）
