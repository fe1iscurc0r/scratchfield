# NEKO 源码引入报告

**日期**: 2026-08-01
**操作**: 将 NEKO (Project N.E.K.O.) 源码引入 scratchpad 仓库
**引入位置**: `NEKO/`（scratchpad 根目录下）

---

## 一、引入背景

scratchpad（陆墨）项目当前基于 NagaAgent (AGPL-3.0) fork，采用 Electron + Vue3 + FastAPI 单进程架构。多智能体审查发现以下架构短板：

1. **单进程一崩全崩** — FastAPI 崩溃拖垮 UI
2. **记忆系统单一** — 仅有 GRAG + Neo4j，缺分层降级
3. **Agent 与对话耦合** — 无独立 Agent 会话管理
4. **无 fallback gate** — 可选能力失败时反复重试拖慢响应

NEKO (Apache 2.0) 在这些方面有成熟实现，引入作为架构参考与改造基础。

---

## 二、许可证合规

### 许可证对比

| 项目 | 许可证 | 商业友好度 | 网络传染性 |
|------|--------|------------|------------|
| scratchpad (陆墨) | AGPL-3.0 (fork 自 NagaAgent) | 低 | 有 |
| NEKO | Apache 2.0 | 高 | 无 |

### 合规处理

1. **NOTICE 文件**: 已在 scratchpad 根目录创建 `NOTICE`，标注 NEKO 来源、版权与许可证
2. **LICENSE 保留**: NEKO 原始 LICENSE 保留于 `NEKO/N.E.K.O/LICENSE`
3. **兼容性**: Apache 2.0 兼容 AGPL-3.0（入站方向），NEKO 代码可被 AGPL 项目引入
4. **衍生约束**: NEKO/ 目录下的代码保留 Apache 2.0，其余部分遵循 AGPL-3.0

### 注意事项

- AGPL-3.0 的网络传染性适用于 scratchpad 主体（含对 NEKO 代码的修改若合并进主体）
- 若需闭源商业化，应避免将 NEKO 代码修改合并进 AGPL 主体，保持其独立 Apache 2.0 模块

---

## 三、引入范围

### 已引入（源码 + 文档）

```
NEKO/
├── N.E.K.O/                    # NEKO 完整源码
│   ├── app/                    # 三服务器（main/memory/agent）
│   ├── brain/                  # CUA / task_executor / openclaw_adapter
│   ├── main_logic/             # 会话管理 / turn / streaming
│   ├── memory/                 # 五维记忆系统
│   ├── plugin/                 # 插件 SDK + 子进程隔离
│   ├── config/                 # 配置 + 角色 + prompts
│   ├── utils/                  # 工具集（llm_client / tts / storage）
│   ├── static/                 # 前端静态资源
│   ├── docs/                   # 开发者文档
│   └── ...
├── NEKO-逻辑理解报告.md        # 多智能体审视报告
└── (NEKO-windows-src.zip 已排除)
```

### 已排除（.gitignore）

为减小仓库体积，以下大二进制资源已通过 `.gitignore` 排除（本地保留，不提交）：

| 类型 | 示例 | 排除原因 |
|------|------|----------|
| 原始压缩包 | `NEKO-windows-src.zip` (270MB) | 冗余 |
| 3D 模型 | `*.vrm`, `*.pmx` (29MB) | 二进制资源 |
| ONNX 模型 | `*.onnx` (10MB) | 二进制资源 |
| 压缩包 | `*.tar.gz` (8.5MB) | 冗余 |
| 视频资源 | `demo.mp4` | 二进制 |
| 字体文件 | `*.ttf` (15MB) | 二进制 |
| GIF 动画 | `static/**/*.gif` (20MB+) | 二进制 |
| 音频文件 | `static/**/*.mp3` | 二进制 |
| Wheel 包 | `deps/**/*.whl` | 二进制 |

---

## 四、NEKO 架构摘要

### 三服务器进程隔离

| 服务 | 端口 | 职责 |
|------|------|------|
| Main Server | 48911 | Web UI、REST API、WebSocket、会话管理 |
| Memory Server | 48912 | 五维记忆（工作/近期/事实/反思/人格） |
| Agent Server | 48915 | 任务评估、通道分发、CUA 执行 |

### 通信协议

- Browser ↔ Main: HTTP + WebSocket
- Main ↔ Memory: HTTP
- Main ↔ Agent: HTTP control + ZeroMQ 事件桥（PUB/PUSH/PULL）

### 核心技术亮点

1. **五维记忆 + 6 级 fallback gate** — ONNX 本地 embedding，sticky disable 永久降级
2. **混合召回 RRF 融合** — BM25 + cosine 并行，RRF(k=60) 融合，LLM rerank 仲裁
3. **产权门控** — `may_clear_shared_output` 防止旧请求迟到回调污染新轮次
4. **mixin 拆分巨型类** — LLMSessionManager 11 个 mixin 按能力域拆分
5. **CUA 坐标缩放代理** — [0,999] 归一化 → 物理像素，failsafe 边缘内缩

### 已知风险（详见 NEKO-逻辑理解报告.md）

| 严重性 | 风险 |
|--------|------|
| 严重 | CUA exec 沙箱暴露 `os` + `__builtins__`，可 RCE |
| 严重 | cross_server bullet 通道用 pickle + 关 SSL |
| 中等 | 端口绑定需确认是否 127.0.0.1 |
| 中等 | 插件 sys.path.insert 污染宿主 import |

---

## 五、后续改造方向（待用户决策）

基于多智能体审视，陆墨可从 NEKO 借鉴的优先级：

| 优先级 | 方向 | 说明 |
|--------|------|------|
| P1 | 进程隔离 | 把 GRAG+Neo4j 重计算拆到独立进程，不阻塞对话 |
| P2 | 分层记忆 + fallback gate | 五维分层，每层独立可降级，图谱挂了不 crash |
| P2 | sticky disable | 可选能力失败即永久关闭，不反复重试 |
| P3 | 模型 tier 化 | LLM 调用收敛到 tier，不写死模型名 |
| P3 | Agent 与对话解耦 | 后台跑，结果事件回传 |

### 应避免的坑

1. 不学 `recent.py` 1700 行并发过度复杂
2. 不学隐私政策留白（科研数据敏感）
3. 不学测试覆盖只保一个插件

---

## 六、操作记录

1. 解压 `NEKO-windows-src.zip` → `N.E.K.O/`
2. 多智能体（铁锚/实验田维护者/杜赞）并行审视 → `NEKO-逻辑理解报告.md`
3. 移动 `NEKO/` 到 `scratchpad/NEKO/`
4. 创建 `NOTICE` 文件（标注 Apache 2.0 归属）
5. 更新 `.gitignore`（排除大二进制资源）
6. 提交推送到 Gitee

---

*报告由 Hermes 协调生成。*
