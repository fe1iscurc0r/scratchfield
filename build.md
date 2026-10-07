# Windows 打包与发布说明

## 概述

产物是**陆墨本体**的 Windows 安装包：后端（PyInstaller 冻结）+ 前端（Electron/NSIS）。

**不随包分发**的组件（按架构边界，由用户按需自行获取）：

| 组件 | 不进包的原因 | 获取方式 |
|---|---|---|
| `NEKO` / `neko-electron-shell` | 上游独立项目，本仓仅含少量桥接改动（反向事件等） | 自行获取上游；未就位时 `local_apps.py` 给出「去 clone」提示 |
| `HamLog` | 第三方独立项目（GPL-3.0），打进 MIT 系包有许可传染风险 | 自行 clone 到 `scratchpad/HamLog` |
| `coupled/*`（如 omnilimb-face） | standalone 插件（自带 `plugin.yaml` + 商业许可） | 各插件自己的分发渠道 |
| OpenClaw | 可选增强，不属发布包（体积与攻击面都不划算） | 需要时全局 `npm install openclaw` |

> 打包范围由 `naga-backend.spec` 的黑名单决定。**改黑名单等于改产品边界**——
> 需同步本表与 `CHANGELOG.md`。

## 版本号约定（单一来源）

**版本号的唯一来源是 annotated git tag（`vX.Y.Z`）**，与 `frontend/package.json` 的 `version` 必须一致。

```bash
git tag -a v5.1.5 -m "陆墨 v5.1.5"    # 必须 annotated（git tag -a），不要用轻量 tag
```

`scripts/build-win.py --tag vX.Y.Z` 会在构建前校验三件事，**任一不满足即报错退出**：

1. tag 格式合法（`vX.Y.Z`）
2. tag 存在，且是 annotated tag
3. tag 与 `frontend/package.json` 的 `version` 一致，且 tag 指向当前 HEAD

脚本**不会**替你改写任何文件——版本不一致必须人工统一后再构建。

## 一键构建（推荐）

在 Windows 环境执行：

```bash
python scripts/build-win.py --tag v5.1.5
```

常用参数：

- `--tag vX.Y.Z`：指定发布版本（校验 tag + package.json 一致）
- `--backend-only`：仅构建后端，不打包 Electron
- `--skip-openclaw`：跳过 OpenClaw 运行时准备（**发布构建应使用**——OpenClaw 不随包分发）
- `--verify-only`：**不构建**，只校验既有产物（可配合 `--tag` 校验产物文件名里的版本号）
- `--debug`：安装后启动时弹出后端日志终端
- `--force-openclaw`：强制重装 OpenClaw 与 Agent Browser 运行时

## 构建流程

`scripts/build-win.py` 会自动执行：

1. **前置环境自检**（调用仓库根目录 `doctor_env.py`，缺必装项即停）
2. 检查 Python / uv / Node.js / npm 环境
3. `uv sync --group build`
4. 下载并解压 Node.js 便携版到 `frontend/backend-dist/runtime/node/`
5. （仅当**未**传 `--skip-openclaw`）准备 OpenClaw 运行时——发布构建传 `--skip-openclaw` 跳过
6. 使用 PyInstaller 构建后端
7. 使用 electron-builder 生成 Windows 安装包
8. **产物校验**（缺失或体积异常即退出码 1）

## 产物校验

构建结束会自动跑一遍产物校验并输出表格。也可随时手动校验既有构建：

```bash
python scripts/build-win.py --verify-only
```

关键产物清单：

| 产物 | 路径 | 体积下限 |
|---|---|---|
| 后端主程序 | `frontend/backend-dist/naga-backend/naga-backend.exe` | ≥ 5 MiB |
| Node 运行时 | `frontend/backend-dist/runtime/node/node.exe` | ≥ 20 MiB |
| npm 命令 | `frontend/backend-dist/runtime/node/npm.cmd` | 存在 |
| NSIS 安装包 | `frontend/release/*.exe` | ≥ 200 MiB |

> NSIS 安装包 **小于 200 MiB 视为异常**——通常意味着 `extraResources` 里的后端或运行时没打进去。
> 任一关键项失败，脚本退出码为 1。

## 发布到 GitHub Release

发布走 `scripts/release-win.py`，**draft 起步，绝不自动 publish**。

前置要求：

- 已安装 `gh` CLI（`winget install --id GitHub.cli`）且 **`gh auth login` 已完成**
  - token 走 gh 自身登录态，**脚本不读取也不写入任何凭证文件**
- 已完成 `python scripts/build-win.py --tag v5.1.5` 且产物校验全过
- 当前 HEAD 就是 tag 指向的提交

```bash
python scripts/release-win.py --tag v5.1.5              # 建 draft release + 上传安装包
python scripts/release-win.py --tag v5.1.5 --dry-run    # 只校验 + 生成 notes，不发请求
python scripts/release-win.py --tag v5.1.5 --notes-only # 只生成 notes 文件
```

发布前会做这些校验（任一失败即停）：

1. `gh` 已安装且已登录
2. tag 存在、是 annotated、且 **即当前 HEAD**（防拿旧构建发新 tag）
3. tag 与 `package.json` 版本一致
4. 产物校验全过（复用 `build-win.py --verify-only`）
5. **release notes 敏感词扫描通过**

### Release Notes

自动生成，优先从 `CHANGELOG.md` 抽取对应版本段落；无对应段落时生成骨架
（版本 / 日期 / 安装方法三条 / 已知问题占位）。生成后写入 `build/release-notes/release-notes-<tag>.md`。

### 隐私铁律

notes 及一切对外发布物中**不得出现真实人名、QQ 号、内部路径、内网地址**，贡献者一律匿名或写团队名。

发布前脚本会用 `scripts/release-notes-blocklist.txt` 对 notes 做一遍正则扫描，
命中任一条即中止发布（退出码 1）并打印命中行。黑名单文件本身也**不能写入完整真名/完整主机名**——
它随仓库公开分发，只写「够识别的唯一片段」。

### 草稿审阅

脚本创建的 Release 状态为 **draft**。请到 `https://github.com/<owner>/<repo>/releases`
人工过目标题、notes、资产链接，确认无误后点「Publish release」正式发布。

## 运行时验证

在一台**未安装 Node.js / 未 clone NEKO / 未装 OpenClaw** 的 Windows 机器上安装并启动，预期：

- 应用可正常启动（后端 + 前端都起来）
- 无「等待安装 OpenClaw」流程——它不随包分发，缺它不影响启动
- 桌宠相关入口在 NEKO 未就位时给出明确的「去获取」提示（不崩、不静默降级）

## CI 构建验证

`.github/workflows/build-windows.yml` 在 push tag `v*` 时触发，
在 `windows-latest` 上跑 `build-win.py --backend-only`，**只验证后端可构建，不发布任何产物**。

该 workflow 权限为 `contents: read`——**没有 release 权限**。正式发布永远在本地做。

### ⚠️ 该 CI 默认关闭（2026-09-28 实测）

本仓库是**私有仓**，其 GitHub Actions 免费额度已耗尽。症状：

- job 能创建，但拿不到 runner
- `runner_name` 为空、`steps` 数量为 0、起止时间同秒
- `conclusion = failure`
- **同一现象在既有的 `build-release.yml` 的 `test` job 上完全一致** ⇒ 账号层问题，仓库内改不了

为避免「红灯变狼来了」淹没真故障，相关 job 已加**变量闸门**，默认 `skipped`（绿）：

| Workflow | 开关变量 |
|---|---|
| `build-windows.yml`（后端构建冒烟） | `ENABLE_WINDOWS_BUILD` |
| `build-release.yml`（三平台全量打包） | `ENABLE_FULL_BUILD` |

**恢复方式**：Settings → Secrets and variables → Actions → **Variables** →
新建对应变量并设为 `true`。

> 前提是先解决账号层的 Actions 额度/账单问题，否则开了仍是同样的失败。

> 历史遗留的 `build-release.yml`（三平台全量打包）的 Release 步骤已改为 `draft: true`，
> 不会自动对外发布。
