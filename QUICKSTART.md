# 实验田 · 快速上手 QUICKSTART

> 从 clone 到看到第一个界面，最短路径。环境细节见 [环境依赖清单（Windows 装机指南）](docs/环境依赖清单-Windows装机-2026-09-27.md)。

## 普通用户（推荐）

1. 到 [Releases](https://github.com/fe1iscurc0r/scratchfield/releases) 下载最新的 `实验田-Setup-x.y.z.exe`
2. 双击安装（SmartScreen 提示「仍要运行」即可，安装包未做代码签名）
3. 首次启动后在设置里填 LLM API key
4. 完——不需要 Python/Node/命令行

## 开发者（源码路线）

```bash
# 1. 拉库
git clone https://github.com/fe1iscurc0r/scratchfield && cd scratchfield

# 2. 环境自检（缺什么报什么，给可直接粘贴的安装命令）
python doctor_env.py

# 3. 一键安装（uv sync → 前端 npm install → build）
./setup.ps1        # Windows
./setup.sh         # Linux/macOS（骨架版）

# 4. 配置
cp config.json.example config.json   # 填 LLM API key
cp .env .env.local                   # 敏感配置

# 5. 跑起来
cd frontend && npm run dev           # dev 模式自动拉起后端
```

## 装完想确认没装坏

```bash
python scripts/doctor.py --quick     # 应用层体检: 依赖/配置/数据目录/前端产物
```

## 常见坑

- **Python 必须 3.12.x**，装 3.13 会被 uv 直接拒（`requires-python >=3.12,<3.13`）
- **只用 npm**，本仓有 package-lock.json，别混 pnpm/yarn
- **用 uv 不用裸 pip**——绕过 uv.lock 会装出不可复现的环境
- 全量细节见环境依赖清单

## 插件商城

```bash
cat plugins/index.json                    # 看有什么
./scripts/plugin-install.sh <plugin-id>   # 装一个
```
