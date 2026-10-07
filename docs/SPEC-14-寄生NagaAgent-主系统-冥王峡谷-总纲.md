# SPEC-14 寄生 NagaAgent 主系统 · 冥王峡谷部署总纲 · v1

> ⚠️ **方向修正（2026-08-25）**：用户拍板冥王峡谷主系统改为 Hermes（林楠 profile），NagaAgent 寄生层 + llama.cpp 本地 LLM 搁置，内存全给知识底座。本 SPEC 的 GPU 矩阵、扩展原则仍有效，具体落地见 SPEC-15。
> 状态：待施工（2026-08-24 用户拍板：目标机器 = 冥王峡谷）
> 用途：scratchpad 寄生 NagaAgent（定制 Agent 框架）当主系统，宿主机 = 冥王峡谷 Kali
> 读者：Trae / WorkBuddy / 沈遥（自包含，不共享写作者上下文）
> 依据：SPEC-Writing-Standard-v2；skill: naga-agent-bridge / naga-electron-gpu-troubleshooting（实测数据）

## 〇、一句话定位

**后端寄生 + 渲染外推 + GPU 兜底三层。** NagaAgent 的 5 个后端服务在冥王峡谷 systemd 常驻（零图形、零 GPU、零崩溃面），前端一律外推（WEB_ONLY 浏览器 / 客户端 Electron 壳），宿主永不碰 Vega M GH 渲染——"无头/GUI 两难"和"GPU 崩"一起消掉。

## 一、背景与边界

NagaAgent 是 Electron + Vue + pixi.js 前端 + 独立 HTTP 后端的解耦框架。scratchpad 寄生其上当主系统。卡点：冥王峡谷（NUC8i7HVK, i7-8809G + Vega M GH 4GB HBM2 + 16GB RAM，Kali 主力 + Windows 备用）的 AMD 驱动在 Linux 下不稳，Electron GPU 进程曾崩飞整个 X11 会话。

| 做 | 不做 |
|---|---|
| 后端 5 服务 systemd 常驻 | 不改 NagaAgent 核心源码（只加启动壳） |
| WEB_ONLY=1 渲染外推（dev:web） | 给 Electron 做无头改造（不做，绕开） |
| GPU 兜底三层（按需启用） | 宿主默认不碰渲染 |
| 复用 frp stcp / Tailscale / Kali 桥接 | Xvfb 常驻（最后手段，非日常） |
| 预留业务扩展位（本地 LLM/射频/算力） | 新增业务不碰渲染层（架构铁律） |

## 二、架构设计

```
┌─ 渲染层（外推）─────────────────────────┐
│ 浏览器 WEB_ONLY=1 → :8000（远程调试）    │
│ 客户端 Electron 壳 → 远程后端（Live2D）  │
└──────────────┬────────────────────────┘
               │ HTTP/WS
┌─ 寄生层（systemd 常驻 · 冥王峡谷 Kali）─┐
│ api_server :8000   agent_server :8001  │
│ mcp_server :8003   tts :5048  asr :5060│
└──────────────┬────────────────────────┘
               │ 已存在，复用
┌─ 接入层 ───────────────────────────────┐
│ frp stcp → 云服 :8000（K40→冥王峡谷）   │
│ Tailscale fe1iscurc0r 100.114.64.107   │
│ Kali 桥接 hermes-bridge.service (root) │
└────────────────────────────────────────┘
```

端口表（写死，勿改）：

| 服务 | 端口 | 组件 | systemd unit |
|---|---|---|---|
| API Server | 8000 | uvicorn apiserver.api_server:app | naga-api |
| Agent Server | 8001 | uvicorn agentserver.agent_server:app | naga-agent |
| MCP Server | 8003 | uvicorn mcpserver.mcp_server:app | naga-mcp |
| TTS (edge-tts) | 5048 | via main.py | naga-tts |
| ASR | 5060 | 按现有实现 | naga-asr |
| 前端 | 8000/web | WEB_ONLY=1 dev:web | 不常驻，按需拉起 |

GPU 策略矩阵（依据 naga-electron-gpu-troubleshooting.md 实测）：

| 场景 | 方案 | 依据/开关 |
|---|---|---|
| 默认无头 | 不启动 Electron | systemd 只管后端 |
| 远程调试 | 浏览器 WEB_ONLY=1 | `WEB_ONLY=1 npm run dev:web` |
| 客户端渲染 | Electron 壳连远程后端 | 渲染在客户端，宿主不沾 |
| 宿主必须显示 | pixi `forceCanvas:true` + `app.disableHardwareAcceleration()` | Canvas 2D 软渲染，桌宠低负载 CPU 扛得住 |
| 宿主要 GPU 加速 | `--use-gl=angle --use-angle=vulkan` | ✅ 实测稳定，日常推荐 |
| 软渲染最稳 | `--use-gl=angle --use-angle=swiftshader-webgl` | CPU only，Live2D 卡但不崩 |
| GPU 进程 EACCES | `--in-process-gpu` | 绕过 GPU 进程 namespace 隔离 |
| 最坏兜底 | Xvfb + x11vnc/noVNC | 最后手段，不日常 |

**铁律：默认形态 = systemd 后端 + 无 Electron 进程。** GPU 相关开关只在"必须宿主显示"时按矩阵启用。

## 三、施工步骤

- **Phase 0 · 摸底**（Kali 上执行，一次跑完）：
  1. `ss -tlnp | grep -E '8000|8001|8003|5048|5060'` 查端口占用
  2. `ls ~/.naga/config.json && cat ~/.naga/config.json` 确认 WEB_ONLY 字段
  3. `ps aux | grep -iE 'electron|uvicorn'` 查现存活进程
  4. 确认 NagaAgent 目录与启动命令（`~/NagaAgent/`，参考 kali-bridge-management/nagaagent-config-reference）

- **Phase 1 · 后端 systemd 化**：为 5 个服务写 unit（`Restart=always`、`User=fe1iscurc0r`、日志走 journald），`systemctl enable --now` 全部。禁止以 root 跑（Electron 坑，后端同理避免 XDG_RUNTIME_DIR 类问题）。

- **Phase 2 · WEB_ONLY 验证**：无 Electron 情况下 `WEB_ONLY=1` 拉起前端，浏览器访问 `http://<冥王峡谷>:8000` 能看到 MindView 云图页面 = 渲染外推成立。

- **Phase 3 · GPU 兜底**：仅在"必须宿主显示"时按矩阵启用。默认装好即可，不主动开。

- **Phase 4 · 接入复用**：确认 frp stcp 链路（K40 → cloud api_server → frp stcp → Kali :8000）与 Tailscale 直连；云服到冥王峡谷 `tailscale ping fe1iscurc0r` 通 = 接入层 OK。

- **Phase 5 · 业务扩展位**：见第十节，按需逐个挂载，每个 = 新 unit + 新端口，不碰渲染层。

## 四、关键假设与 fallback

| 假设 | fallback |
|---|---|
| Kali 白天在线、晚上休眠 | unit 随开机自启；休眠恢复后服务仍在（Restart=always） |
| Vega M GH 驱动不稳 | 宿主永不碰渲染；兜底三层按矩阵 |
| 端口 8000/8001/8003 被占 | Phase 0 先摸底，冲突者改端口并回填本 SPEC |
| frp stcp 链路断 | Tailscale 直连（100.114.64.107）备用 |
| WEB_ONLY=1 不生效 | 查 .naga/config.json 字段名；直接浏览器访问 :8000 前端静态目录 |
| libGLESv2.so 缺失/损坏 | 只能 Electron 官方 6.3MB 版，`node install.js` 重装；系统 71KB stub 不可用 |

## 五、已知限制

- 冥王峡谷 16GB RAM：NagaAgent 后端 + scratchpad 全家 + 本地模型会紧张 → 建议扩 32GB（SODIMM 两条，成本低）。
- Kali 是攻击节点，常驻服务扩大攻击面 → 监听只绑 Tailscale/回环，frp 已有 HMAC 鉴权。
- 晚上休眠 → 不是 24h 服务，云服侧调用需容忍离线（桥接轮询已处理）。
- Vega M GH 的 radeonsi `ReadPixels stall` 是已知性能损耗（非崩溃），不影响功能。
- 桌面被 GPU 崩飞过：任何 Electron 实验必须先在 X11 会话外验证（Phase 3 最后做）。

## 六、测试用例（全部云服/宿主机可跑，无需真机）

```bash
# 1. systemd 五件套全 active
systemctl is-active naga-api naga-agent naga-mcp naga-tts naga-asr | grep -c active   # = 5

# 2. 后端端口在听
ss -tlnp | grep -cE ':8000|:8001|:8003|:5048|:5060'   # ≥ 4

# 3. 无头模式无 Electron
ps aux | grep -c '[e]lectron'   # = 0

# 4. WEB_ONLY 前端可达
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/   # = 200

# 5. 云图接口有数据
curl -s http://127.0.0.1:8000/memory/quintuples | head -c 100   # JSON 非空

# 6. Tailscale 通
tailscale ping fe1iscurc0r   # pong
```

## 七、交付物清单

| 交付物 | 位置（冥王峡谷） |
|---|---|
| systemd unit ×5 | /etc/systemd/system/naga-{api,agent,mcp,tts,asr}.service |
| WEB_ONLY 启动脚本 | ~/NagaAgent/scripts/web_only.sh + README |
| GPU 兜底补丁（main.ts 开关注释） | ~/NagaAgent/frontend/electron/main.ts（按需启用） |
| 巡检脚本 | ~/scripts/naga_health.sh（跑第六节 1-3 条） |

## 八、验收标准（可执行不变量）

1. `systemctl is-active naga-api naga-agent naga-mcp naga-tts naga-asr` 输出 5 个 active。
2. `ps aux | grep '[e]lectron'` 在无头模式下输出空（零 Electron）。
3. `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/` = 200。
4. `curl -s http://127.0.0.1:8000/memory/quintuples` 返回合法 JSON。
5. 从云服 `tailscale ping fe1iscurc0r` pong；frp stcp 链路 curl 通。
6. 新增业务 unit 上线后，1-5 全量回归通过（渲染层隔离铁律未破）。

## 九、提交规范

- SPEC 与巡检脚本进 scratchpad 仓库（分支 `feat/parasite-naga-20260824`），推送 GitHub（fe1iscurc0r/scratchpad），不落本地副本（用户铁律 8-22）。
- 冥王峡谷部署物（unit/脚本/README）进 `~/NagaAgent/deploy/` 子目录，随 NagaAgent 备份。
- 施工中发现假设不成立 → 回填本 SPEC，不绕过硬干（SPEC-Writing-Standard-v2 动力学规则）。

## 十、业务扩展位（冥王峡谷承接更多业务）

寄生层服务化后不锁死 NagaAgent 独占，以下业务均为"新 unit + 新端口 + Tailscale 网格"即可挂载：

| 扩展业务 | 形态 | 依据 |
|---|---|---|
| 本地 LLM API | llama.cpp CPU 推理（GGUF），OpenAI 兼容 :8080，给 NagaAgent/scratchpad 当省钱后端 | 6-16 已讨论 llama.exe serve |
| 射频前哨真机闭环 | RTL-SDR / SX1278 OOK（N-01~04 已写解码器），rf_brain Phase7 真机验证 HW-04/05 | SPEC-12 哨兵网格 |
| Kali 攻防/蜜罐 | 已有 hermes-bridge (root)，保持不动 | 三层防御体系 |
| 分布式算力 | 与 W540/天选7 组网，ML 长任务兜底 | 7-28 方案 |
| 存储扩展 | 双 M.2 槽，知识图谱/采集数据本地落盘 | ~/.naga/knowledge_graph/ |

**扩展原则**：新增业务永远不碰渲染层、不抢既有端口、不依赖 Vega M GH——GPU 在这台机器上只是"可选加速器"，不是系统支柱。

---

*制定：沈遥（Hermes）· 2026-08-24 22:55 CST*
*依据：SPEC-Writing-Standard-v2 + naga-agent-bridge（实测 GPU 排障数据）*
