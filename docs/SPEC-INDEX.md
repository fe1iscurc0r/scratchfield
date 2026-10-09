# SPEC-INDEX · docs/ 索引与归档台账（工单212）

> 生成：2026-10-08 ｜ 覆盖 `docs/SPEC-*.md`（34）+ `docs/*方案*.md`（29）共 **63 个文件**
> 锚定版判定：正文头部日期（标题大多无日期）；同组多版本取最新。
> `[需归档]` = 同议题存在更新版本且本文件无废弃声明（已归档的见 `archive/`）。
> 归档目录：`docs/archive/SPEC-历史版本/` · `docs/archive/未启动/`（文件加 `archived-2026-10-08-` 前缀，git 历史可查、可还原）。

---

## 一、SPEC 主线组（SPEC-01 ~ SPEC-20）

### SPEC-01 rf_brain 全自动闭环
- 锚定：`SPEC-01-rf-brain-闭环.md`（2026-08-22）
- 状态：rf_brain 已在总线（radio 域）；dcp/哨兵线见 SPEC-12/13 与 `dcp-lora-方案.md`

### SPEC-02 Lumo 科研规模化
- 锚定：`SPEC-02-lumo-科研规模化.md`（2026-08-22）
- 关联：`SPEC-02-report.md`（2026-08-23，**验收报告**，更新于 SPEC 本体）
- 状态：已落地部分（lumo 设计系统在 frontend/ 应用）；仍有欠账（lumo 前端状态管理未拆完，见工单204）

### SPEC-03 NEKO 记忆层工程化 + 授粉落地
- 锚定：`SPEC-03-NEKO记忆-授粉落地.md`（2026-08-22）
- 关联：`SPEC-03-report.md`（验收报告）
- 状态：memory_maas 已落地（对照见 `topoteretes-cognee.md` 调研卡）

### SPEC-04 集成地狱 2.0 总纲
- 锚定：`SPEC-04-集成地狱2.0-总纲.md`

### SPEC-05 五维记忆融合（调研+设计）
- 锚定：`SPEC-05-五维记忆融合.md`

### SPEC-06 mcpserver 总线优化
- 锚定：`SPEC-06-总线优化.md`
- 状态：工单189 三层优化已落地（manifest 懒加载 / 能力索引 / 画像熔断 / 链编排）

### SPEC-07 寄生 Windows 总纲 · v1 —— `[需归档]` → **已归档 `archive/未启动/`**
- 原文件（2026-08-23）：用户明确"先放放"，按工单212 任务二移入未启动区

### SPEC-08 三线收口 · 第四批工单总纲
- 锚定：`SPEC-08-三线收口-第四批工单-总纲.md`

### SPEC-09 威胁情报记忆层 · 第五批工单总纲 · v1
- 锚定：`SPEC-09-威胁情报记忆层-第五批工单-总纲.md`

### SPEC-10 三线收口解冻 · 第六批工单总纲 · v1
- 锚定：`SPEC-10-三线收口解冻-第六批工单-总纲.md`

### SPEC-11 陆墨轻量 Gateway（方案 B）
- 锚定：`SPEC-11-lumo-gateway-接入QQ微信.md`

### SPEC-12 哨兵网格 Phase 1 · 第七批工单总纲
- 锚定：`SPEC-12-哨兵网格-第七批工单-总纲.md`
- 状态：**部分落地**（w187 Sentinel-Link 协议 + `/sentinel` 端点 + SentinelPanel 已合并）

### SPEC-13 三链路授粉落地 · 第八批工单总纲
- 锚定：`SPEC-13-三链路授粉落地-第八批工单-总纲.md`

### SPEC-14 寄生 NagaAgent 主系统 · 冥王峡谷部署总纲 · v1
- 锚定：`SPEC-14-寄生NagaAgent-主系统-冥王峡谷-总纲.md`
- 关联方案：`openarc-部署方案-spec.md`

### SPEC-15 冥王峡谷 Hermes 知识底座 · 第九批工单总纲 · v1
- 锚定：`SPEC-15-冥王峡谷-Hermes知识底座-第九批工单-总纲.md`（2026-08-25）
- 关联：`SPEC-15-补充-T线-持久主体设计输入-2026-09-07.md`（**更新于主 SPEC**，设计输入）

### SPEC-16 冥王峡谷 MCP 接入清单 · 总纲 v1
- 锚定：`SPEC-16-冥王峡谷-MCP接入清单-总纲.md`（2026-08-25）

### SPEC-17 radio_suite 无线电套件 · 总纲 · v1
- 锚定：`SPEC-17-Lumo无线电套件-总纲.md`
- 关联方案：`dcp-lora-方案.md`（P 线）、`modem73-kiss-tnc-接入方案.md`（R54）、
  `esp32-rf-fronthaul-方案.md`（R51）、`koopman-rf-frontend-方案.md`（K16）

### SPEC-18 天选7 Lumo 科研增强 · 总纲 · v1
- 锚定：`SPEC-18-天选7-Lumo科研增强-总纲.md`（2026-08-25）
- ⚠️ **标题错位 bug**：文件名 SPEC-18，正文标题写成 "SPEC-16 天选7…" → 待修（改名或改正文，需用户定）

### SPEC-19 pymatviz 材料可视化 · 授粉落地总纲 · v1
- 锚定：`SPEC-19-pymatviz材料可视化-授粉落地-总纲.md`

### SPEC-20 LoRa 环境感知节点（LoRaCanary）—— **7 个文件，多代总纲**
- **锚定：`SPEC-20-v1.6-LoRaCanary弱链路增强-总纲.md`**（2026-08-29，EWMA 可靠度分组 + 断电不丢相位）
- 关联（保留）：`SPEC-20-PCB两方案提示词.md`、`SPEC-20-PCB前置资料-嘉立创AI.md`（v0.6 直焊版）、
  `SPEC-20-参考案例-立创开源.md`
- `[需归档]` → **已归档 `archive/SPEC-历史版本/`**：
  - `SPEC-20-LoRa环境感知节点-总纲.md`（v1，08-26，被 v1.5 取代）
  - `SPEC-20-v1.5-LoRaCanary扩增-GPS睡眠C3-总纲.md`（08-29，被 v1.6 取代）
  - `SPEC-20-v1.5-PCB-Board1-操作记录.md`（v1.5 期操作记录）

## 二、SPEC 写作规范组

| 文件 | 判定 |
|---|---|
| **`SPEC-Writing-Standard-v2.md`** | **锚定**（spec 的 spec v2） |
| `SPEC-Writing-Standard-v1.md` | `[需归档]` → **已归档** |
| `SPEC-Standard-Manifesto-v1.md` | 保留（说明书，与 v2 互补） |

## 三、单文件 SPEC（无版本重复，保留）

| 文件 | 日期 |
|---|---|
| `SPEC-neko-行为投影-事件映射-2026-09-20.md` | 2026-09-20 |
| `SPEC-技术雷达四方向落地-2026-09-02.md` | 2026-09-02 |

## 四、方案类（29 个，均为独立设计、无版本重复 → 全部保留 docs/ 根）

### 射频 / 频谱线
`dcp-lora-方案.md`（P 线）· `esp32-rf-fronthaul-方案.md`（R51）· `koopman-rf-frontend-方案.md`（K16）·
`modem73-kiss-tnc-接入方案.md`（R54）· `spectrum-arbitration-方案.md`（S16）·
`spectrum-semantic-transmission-方案.md` · `swarm-collaborative-sensing-方案.md` ·
`multihop-spectrum-collab-方案.md` · `esp32-em-twin-spectrum-方案-2026-08-30.md` ·
`esp32-nearfield-probe-方案-2026-08-30.md`

### LoRa 硬件线（LoRaCanary 配套）
`loracanary-module-ota-方案.md`（S13）· `loracanary-rlnc-mesh-方案.md`（R50）

### 材料线
`biomass-mlip-benchmark-方案.md`（M32）· `maelle-离散流匹配-方案.md`（M29）·
`mm-spectrum-多模态光谱-方案.md`（M28）· `dino2lvssm-distill-方案.md`（K14）·
`cross-simulator-foundation-model-方案.md`

### 防御 / 安全线
`camodocs-rag-defense-方案.md`（S23）· `contextleak-defense-方案.md`（S27）·
`longpi-bench-方案.md`（S24）· `agent-trace-integrity-方案.md`（S21）·
`dreamledger-信用文件-方案.md`（A26）· `uc-psro-通信退化课程-方案.md`（A22）

### 平台 / 工程线
`openarc-部署方案-spec.md` · `apify-接入方案.md` · `agent73-落地方案-执行清单.md` ·
`可实现方案规划-74.md` · `前端巨石拆分方案-2026-10-07.md`（工单204，App.vue/弹窗剩余项）

---

## 五、归档双向索引（可逆）

| 归档路径 | 原路径 | 归档原因 |
|---|---|---|
| `archive/SPEC-历史版本/archived-2026-10-08-SPEC-20-LoRa环境感知节点-总纲.md` | `docs/SPEC-20-LoRa环境感知节点-总纲.md` | 被 v1.5 取代 |
| `archive/SPEC-历史版本/archived-2026-10-08-SPEC-20-v1.5-LoRaCanary扩增-GPS睡眠C3-总纲.md` | `docs/SPEC-20-v1.5-LoRaCanary扩增-GPS睡眠C3-总纲.md` | 被 v1.6 取代 |
| `archive/SPEC-历史版本/archived-2026-10-08-SPEC-20-v1.5-PCB-Board1-操作记录.md` | `docs/SPEC-20-v1.5-PCB-Board1-操作记录.md` | v1.5 期操作记录 |
| `archive/SPEC-历史版本/archived-2026-10-08-SPEC-Writing-Standard-v1.md` | `docs/SPEC-Writing-Standard-v1.md` | 被 v2 取代 |
| `archive/未启动/archived-2026-10-08-SPEC-07-寄生Windows-总纲.md` | `docs/SPEC-07-寄生Windows-总纲.md` | 用户明确"先放放" |

还原方式：`git log --follow <归档路径>` 找到移动前历史；或直接把文件复制回 `docs/` 根并去掉前缀。
