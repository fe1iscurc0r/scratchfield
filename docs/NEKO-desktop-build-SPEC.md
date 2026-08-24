# N.E.K.O. Windows 桌面端构建与获取指南

> 原仓库: [Project-N-E-K-O/N.E.K.O](https://github.com/Project-N-E-K-O/N.E.K.O) (Apache 2.0, 2.3k⭐)
> 基于: 源码 `tools/windows/N.E.K.O/` + 官方 Release

---

## 零、先看结论：你不需要自己打包

**GitHub Releases 有现成的 Windows 桌面安装包**，含 Electron 外壳 + Live2D 桌面宠物 + 系统托盘。

| 版本 | 文件 | 大小 | 来源 |
|---|---|---|---|
| **Nightly** (最新 2026-08-06) | `NEKO-desktop-nightly.exe` | 1,067MB | 云服 HTTP 直链 ↓ |
| **Stable** (v0.8.3) | `N.E.K.O_0.8.3.1_win.zip` | 1,114MB | GitHub Releases |
| **Steam** | Steam 商店 | — | [商店页](https://store.steampowered.com/app/4099310/) |

**云服已拉取 Nightly**：`http://43.155.165.80/NEKO-desktop-nightly.exe`

---

## 一、两种运行模式对比

| | 源码模式 (`launcher.py`) | 桌面模式 (`.exe` 安装) |
|---|---|---|
| 启动方式 | `uv run python launcher.py` | 双击 `N.E.K.O.exe` |
| Live2D 在哪 | 浏览器 `localhost:48911` | **独立浮动窗口 + 系统托盘** |
| 桌面宠物 | ❌ 只在网页里 | ✅ 浮动在桌面上 |
| Electron 外壳 | ❌ | ✅ 窗口管理/托盘/Steam |
| 需要安装 | Python 3.11 + uv + Node.js | 双击安装即可 |
| 适合场景 | 开发/调试/定制 | 日常使用 |

**你要的"桌面宠物模式"只有桌面模式才有。**

---

## 二、方案 A：直接用现成安装包（推荐）

### 从云服下载

```
http://43.155.165.80/NEKO-desktop-nightly.exe
```

双击安装 → 启动 → 桌面出现猫耳 Live2D 浮动窗口。

### 首次配置

1. 启动后打开 `http://127.0.0.1:48911/api_key`
2. 选择 Core Provider（对话模型）+ Assist Provider
3. 输入 API Key → 连通性检查
4. 回到主页面 → 猫耳开始互动

---

## 三、方案 B：从源码构建桌面端

> 打包机必须是 **Windows x64**。云服 (Linux) 无法交叉编译。

### 前置条件

| 工具 | 版本 | 安装 |
|---|---|---|
| Python | **3.11.x 严格** | [python.org](https://www.python.org/downloads/) |
| uv | latest | `pip install uv` |
| Node.js | >= 22 | [nodejs.org](https://nodejs.org/) |
| npm | >= 10 | 随 Node.js |
| Git | latest | [git-scm.com](https://git-scm.com/) |

### Step 1: 获取源码

```powershell
# 从 GitHub 直接 clone（最新）
git clone https://github.com/Project-N-E-K-O/N.E.K.O.git
cd N.E.K.O

# 或从你已有的云服源码合并（含 .git 历史）
# 先解 Part1 源码，再解 Part2 .git 到同目录
```

### Step 2: 同步 Python 依赖

```powershell
uv sync
```

> 不要用 `pip install -r requirements.txt`——官方明确要求 `uv sync`。

### Step 3: 构建前端

```powershell
.\build_frontend.bat
```

这一步自动完成：
- 解压 `assets/yui-origin.tar.gz` → `static/yui-origin/`（Live2D 猫耳模型）
- `npm ci && npm run build` → `frontend/plugin-manager/dist/`
- `npm ci && npm run build` → `static/react/neko-chat/`

### Step 4: 开发模式验证

```powershell
uv run python launcher.py
```

浏览器打开报告的 URL（默认 `http://127.0.0.1:48911`），确认 Live2D 正常渲染。

**此时还是 Web 模式，猫耳在浏览器里，不是桌面浮动窗口。**

### Step 5: 准备 OpenClaw 运行时（可选）

桌面版 Agent/Browser-Use 能力需要预装 Node.js 运行时。不装也能用，只是首次使用 Agent 功能时会自动下载（慢）。

```powershell
# 下载 Node.js v22.13.1 便携版
# https://nodejs.org/dist/v22.13.1/node-v22.13.1-win-x64.zip
# 解压到: frontend/backend-dist/openclaw-runtime/node/

cd frontend/backend-dist/openclaw-runtime
.\node\npm.cmd install openclaw --location=project
.\node\npm.cmd install agent-browser --location=project
.\openclaw\node_modules\.bin\agent-browser.cmd install
```

### Step 6: PyInstaller 编译后端

```powershell
uv run pyinstaller naga-backend.spec `
  --distpath frontend/backend-dist `
  --clean -y
```

产物：`frontend/backend-dist/naga-backend/naga-backend.exe`

> `naga-backend.spec` 配置了排除 PyQt5/torch/tensorflow 等大型库以减小体积。

### Step 7: Electron 打包

```powershell
cd frontend
npm install
npm run dist:win
```

等效于：TypeScript 检查 → Vite 构建 → electron-builder → NSIS 安装包

### Step 8: 产物

```
frontend/release/
  N.E.K.O Setup x.x.x.exe    ← 安装包
```

---

## 四、安装后目录结构

```
N.E.K.O/
  N.E.K.O.exe                 ← Electron 主进程（桌面浮动窗口）
  resources/
    app.asar                  ← Vue 前端 + Electron 代码
    backend/                  ← PyInstaller 编译的 Python 后端
      naga-backend.exe
    openclaw-runtime/         ← OpenClaw + Agent Browser 运行时
```

启动后：
- 系统托盘出现 N.E.K.O 图标
- Live2D 猫耳浮动在桌面上（Electron pet window）
- 浏览器访问 `localhost:48911` 进入设置/角色管理

---

## 五、桌面宠物窗口的技术细节

```
桌面浮动窗口 (Electron BrowserWindow, transparent + alwaysOnTop)
  └── 加载 index.html
        └── #live2d-canvas ← Live2D 模型渲染
              ├── live2d-core.js      (Cubism SDK)
              ├── live2d-model.js     (模型加载)
              ├── live2d-emotion.js   (表情映射)
              ├── live2d-interaction.js (点击/拖拽)
              └── LanLan1.setEmotion()  (兼容层)
```

窗口属性：透明背景、置顶、无边框、可拖拽。

**PNGTuber 模式也支持**——如果你不想用 Live2D，可以用静态/动图形象（idle/talking 两张图即可）。

---

## 六、常见问题

### 桌面浮动窗口没出现？

Nightly build 启动后窗口默认可能隐藏——检查系统托盘图标，右键 → "显示"。

### 从源码启动只有浏览器没有浮动窗口？

正常。`launcher.py` = 开发模式 = Web only。桌面浮动窗口（Electron pet window）只在打包后的 .exe 里。

### 能直接用 Electron 外壳套源码吗？

理论上可以。Electron 外壳在 GitHub workflow 中从 `N.E.K.O.-PC` 仓库拉取，但该仓库未公开独立存在。建议直接下载 Nightly .exe。

### Nightly vs Stable 选哪个？

- **Nightly**：每日自动构建，最新功能，可能有 bug
- **Stable** (v0.8.3)：经过测试的稳定版
- 建议先试 Nightly，有问题再换 Stable

---

*SPEC 基于 Project-N-E-K-O/N.E.K.O 官方文档（docs/deployment/windows-exe.md + docs/deployment/manual.md + docs/frontend/live2d.md）*
