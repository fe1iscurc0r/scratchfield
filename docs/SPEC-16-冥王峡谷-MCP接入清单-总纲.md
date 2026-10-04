# SPEC-16 冥王峡谷 MCP 接入清单 · 总纲 v1

> 状态：待施工（2026-08-25 用户拍板：scratchpad 的 MCP/插件按三层清单筛选上机）
> 用途：冥王峡谷（NUC8i7HVK, i7-8809G + Vega M GH, 16GB RAM, 512GB NVMe, Kali 主力）给执行侧（Hermes profile `~/.hermes/profiles/linnan/`）接入 MCP 模块的选型与施工蓝图
> 归属：本 SPEC 属冥王峡谷线，**随 SPEC-14/15 迁入独立仓 canyon-kb**，不留在 scratchpad
> 读者：实验田维护者（spec+review）/ 部署执行者（执行侧侧 Kali）/ Trae（如需写码）
> 依据：SPEC-15（知识底座）、native-mcp（Hermes MCP 客户端）、linnan-onboarding、2026-08-25 会话结论

## 〇、定位与铁律（用户拍板）

- 冥王峡谷 = **Hermes 本地主场**（linnan profile），不是 Lumo/材料科研的机器
- 16GB 全给 Hermes 生态 + 嵌入式数据库，**不做本地 LLM 常驻**
- **零常驻守护进程**：新组件 = venv 依赖 + 按需 CLI/工具（Hermes MCP stdio 拉起），不跑 HTTP 服务
- Kali 有 PEP 668：一律 `python3 -m venv`，禁 `pip install` 系统级
- Vega M GH 驱动是坑：GUI 一律 `--disable-gpu`；Live2D 类 GPU 需求**不装**

## 一、接入架构

```
Hermes (linnan profile, ~/.hermes/profiles/linnan/)
  └─ config.yaml → mcpServers（stdio 协议）
       ├─ kb_retrieval    → venv python -m mcpserver.kb_retrieval    [T-03]
       ├─ linan_memory    → venv python -m mcpserver.linan_memory    [T-01]
       ├─ linan_bridge    → venv python -m mcpserver.linan_bridge    [T-05/07]
       ├─ sentinel_intel  → venv python -m mcpserver.sentinel_intel  [哨兵情报+OSINT]
       ├─ rf_brain        → venv python -m mcpserver.rf_brain        [决策层子集]
       ├─ memory_maas     → venv python -m mcpserver.memory_maas     [记忆服务]
       ├─ trust_layer     → venv python -m mcpserver.trust_layer     [信任层]
       └─ (可选) voice_pipeline → venv python -m ...                 [NEKO 语音]
```

**要点**：
- 用 Hermes 原生 MCP 客户端（stdio），**不搬** mcpserver 的 mcp_manager/mcporter_bridge/mcp_server.py 框架（那是 NEKO/Lumo 的，冥王峡谷不需要）
- 每个模块一个 venv 或共用一个 `~/hermes_env`（按依赖冲突决定）；模块入口统一 `python -m mcpserver.<mod>` 或 agent-manifest 声明
- 哨兵数据流：ESP32-S3 哨兵（家里）→ 本地上报冥王峡谷 `sentinel_intel` → SQLite 记忆库 → rf_brain 决策层

## 二、组件清单（三层筛选）

### ✅ 必装（契合 Hermes 底座 + 电台主线）

| 模块 | 来源 | 用途 | 入口 |
|---|---|---|---|
| linan_memory (T-01) | SPEC-15 施工 | Sibyl-Memory 迁移桥 | `mcpserver/linan_memory/` |
| kb_retrieval (T-03) | SPEC-15 施工 | LanceDB 向量检索 | `mcpserver/kb_retrieval/`（有 agent-manifest） |
| linan_bridge (T-05/07) | SPEC-15 施工 | hermes_proxy 灵魂桥 + 主动搭话 | `mcpserver/linan_bridge/` |
| sentinel_intel + collectors | N/M 线 | 哨兵情报入库 + OSINT 三采集器（whois/dns/cert，纯 stdlib） | `mcpserver/sentinel_intel/`（有 agent-manifest） |
| rf_brain 决策层 | N 线 | 频谱决策（deploy/decide 子集；实时采集留 ESP32 侧） | `mcpserver/rf_brain/`（有 agent-manifest） |
| memory_maas | 已有 | 嵌入式记忆服务（SQLite） | `mcpserver/memory_maas/`（有 `__main__.py`） |
| trust_layer | 已有 | 信任评分/安全层 | `mcpserver/trust_layer.py` |
| web_search / memo_reminder / lifekit | NEKO 插件 | 轻量工具 | NEKO 插件目录 |

### ⚠️ 可选（按需）

| 模块 | 条件 |
|---|---|
| NEKO 语音（voice_pipeline + edge-tts + tts_api） | T-06 已做 Kali 适配；Edge TTS 走网络 + Clash；确认 headless 跑法后装 |
| agent_cli_anything | 需要 CLI 工具调用时 |

### ❌ 排除（明确不装）

| 模块 | 原因 |
|---|---|
| bofire / chembl / scikit_fingerprints / material_science / academic | 材料科研是 Lumo（云服/天选7）主场，白吃 16GB |
| torch / transformers 全家桶 | embedding 用 all-MiniLM-L6-v2（~80MB）够，不铺重依赖 |
| neko_live（Live2D） | Vega M GH 驱动坑，GUI 起不来 |
| galgame / MC / 战争雷霆 / steam / bilibili 弹幕 | 服务器形态无意义 |
| mijia | 除非家里米家设备确认要接 |

## 三、资源预算

| 项 | 常驻 |
|---|---|
| Hermes 本体 + 知识底座（SQLite/LanceDB/Sibyl/kaas）+ Obsidian | ~2-3GB |
| 哨兵情报 + 信任层 + OSINT | <1GB |
| 语音（按需，edge-tts/silero_vad） | ~200MB 按需 |
| **合计** | **<4GB / 16GB**，余量给 OCR/PDF/轻量处理 |

## 四、接入步骤（冥王峡谷 Kali）

```bash
# 1. 代码上机（canyon-kb 建好后从该仓拉，暂用 scratchpad agent-t/main）
# 2. venv + 依赖（PEP 668 铁律）
python3 -m venv ~/hermes_env
~/hermes_env/bin/pip install lancedb sibyl-memory-hermes edge-tts \
    sentence-transformers pyserial numpy pandas
# kaas (bybit, MIT)：源码编译（编译时占用，运行零常驻）
# 3. Hermes MCP 配置
# ~/.hermes/profiles/linnan/config.yaml → mcpServers 段，stdio 指向各模块
# 4. systemd：kb-build.timer / linan-proactive.timer 启用（T-02/T-07 交付）
systemctl enable --now kb-build.timer linan-proactive.timer
```

## 五、验收清单（部署后）

1. `hermes mcp list`（或等价）能看到全部接入模块，无报错
2. `kb_search "关键词"` 返回 vault 片段（T-03）
3. `sentinel ingest` 接收 ESP32 哨兵 NDJSON 入库可查（N 线）
4. `memory_maas` 增查改删正常（与 Sibyl 不冲突）
5. `verify_hermes_kb.sh` 全 PASS（T-04）
6. 常驻内存 <4GB；无多余 HTTP 守护进程
7. Obsidian `--disable-gpu` 打开 ~/kb 不崩

## 六、归属与提交规范

- 本 SPEC + SPEC-14/15 + T 线施工产物 → **canyon-kb 独立仓**（`fe1iscurc0r/canyon-kb`），不在 scratchpad 维护
- 施工产物分支：`trae/agent-t` 等，合入 canyon-kb main 后从 scratchpad 移除
- 施工中假设不成立 → 回填本 SPEC，不绕过硬干

---

*制定：实验田维护者（Hermes）· 2026-08-25*
*依据：SPEC-15 + native-mcp + 2026-08-25 会话结论*
