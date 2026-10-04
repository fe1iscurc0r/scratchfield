# scratchpad 总体规划书 · v1

> 制定：实验田维护者（Hermes）｜施工：执行侧（Trae）
> 定位：NEKO（身体）+ 陆墨（大脑）六线整合施工总纲
> 日期：2026-08-13
> 引用文档（同目录，Trae 施工时翻）：
> `scratchpad-issues-2026-08-13.md`（26 项台账）／`scratchpad-code-review-report-2026-08-13.md`（15 高危）／`scan-commit-2026-08-13.md`（物理层拉取字据）／`GRAG-search-fix-SPEC.md`／`LLM4Decompile-MCP-SPEC-v1.md`／`Old-Target-New-Model-Plan-v1.md`（四靶子）／`GitHub-Haul-New-Unplanned-20260813.md`（预处理清单）

---

## 一、现状快照（三句话）

1. **壳通了，脑子在漏**。NEKO 桌宠壳 + 陆墨 21 模块后端已跑通，但 RAG/GRAG 检索「静默坏」——默认参数下检索恒空、搜索与存储数据源分离。这是每天在用、但坏了不报错的东西。
2. **安全债没清**。一条 `neko-electron-shell` RCE 链（nodeIntegration 三件套）+ 明文 token 已入库 + `openai_proxy` 无鉴权转发真实 api_key，是当前最大风险。
3. **增长点已拍板、未开工**。物理层 AI 决策大脑（射频大脑）方向已定、拉取清单已签字（scan-commit），只差融合 SPEC。

**一句话战略**：先止血 + 修通检索，再把陆墨从「材料科研问答机」升级成「物理层 AI 决策大脑」——底座用开源，脑子用 LLM+逻辑引擎。

---

## 二、六条工作线全景

| 线 | 状态 | 下一步 | 谁做 |
|---|---|---|---|
| **A 安全止血** | 26 项台账，第一梯队 2 项未动 | 按四梯队清 | Trae 施工 / 实验田维护者 review |
| **B 功能正确性** | RAG 恒空、GRAG 错位、cancel_task 未 await | 四个「静默坏」全修 | Trae |
| **C 物理层大脑** | 方向已拍板、清单已签字 | 出「射频大脑」融合 SPEC | 实验田维护者出 SPEC / Trae 施工 |
| **D 四靶子** | C 已开工，A/B/D 待启 | C 收尾 → A/B 排期 | Trae（C）／实验田维护者出 A/B SPEC |
| **E 预处理融合** | 12 项已拉 GitHub 私库，未拉回 | 回家拉回 Gitee → 按优先级融合 | Trae |
| **F 认知架构/记忆层** | 扫描完成，未动手 | 先吃 caura-memclaw 架构再定自研/集成 | 实验田维护者评估 |

---

## 三、本周施工顺序（可立即下工单，零阻塞）

### W1 安全止血 — 要命，先做

**第一梯队（1-2 项，今天清）**
- [ ] `route_map.py` 明文 token：删行改环境变量（私库，不用清 git 历史）
- [ ] 08-11 已修的 10 项高危：确认本地改动已 push 远端（本地 vs Gitee 分叉）

**第二梯队（陆墨 5 新发现，见 issues B 段 #3-#7）**
- [ ] `agentic_tool_loop.py` LLM 驱动裸 shell：exec 加确认门 + write/edit 限白名单目录
- [ ] `openai_proxy.py` 无鉴权转发：加共享密钥鉴权
- [ ] `main.py` 热补丁 `.py` 优先加载：补丁加 SHA-256 白名单
- [ ] `build.py` 供应链：下载加 SHA-256 + npm 钉版本
- [ ] `summer_memory` cancel_task 未 await：补 await

**最高危单列（code-review #1/#2，唯一 RCE 链）**
- [ ] `neko-electron-shell` 窗口三件套：`contextIsolation:true + sandbox:true + nodeIntegration:false`，能力走 contextBridge 白名单
- [ ] 特权 IPC 加 sender 校验 + `open-path` 限数据目录

> Trae 施工时先读 `scratchpad-code-review-report-2026-08-13.md` 的修复方向，照着改，每模块单独 commit。

### W2 功能正确性 — 每天在用，坏了要修

- [ ] **RAG 检索恒空**（code-review #7）：RRF 融合分数 max≈0.32 与默认 `min_score=0.6` 错配 → 融合后归一化到 [0,1] 或降阈值
- [ ] **嵌入失败随机向量**（code-review #8）：`embedding_engine.py` 失败返回 None，别返回固定种子随机向量，让上层 fail-fast 真生效
- [ ] **GRAG 搜索数据源错位**（P0）：`graph.py` 的 `query_graph_by_keywords` 加文件模式 fallback → **照 `GRAG-search-fix-SPEC.md` 施工，SPEC 已就位**
- [ ] **refresh 签名错位**（code-review #9）：`auth.py:393` 调 `naga_auth.refresh()` 去掉多余参数
- [ ] **cancel_task 未 await**（code-review #10）：与 W1 第二梯队第 5 项合并处理

### W3 战略主线 — 增长点

- [ ] **四靶子 C 收尾**：LLM4Decompile MCP，照 `LLM4Decompile-MCP-SPEC-v1.md` 施工（08-12 工单已下，确认进度）
- [ ] **四靶子 D**：论文 PDF → Markdown 管线（Docling + MarkItDown，1 天量）
- [ ] **物理层大脑**：⚠️ **等实验田维护者出「射频大脑」融合 SPEC，不要自行开工**

---

## 四、等待条件（别开工，标 🟡）

| 项 | 等待什么 |
|---|---|
| E 预处理融合（12 项） | 回家把 `fe1iscurc0r/scratchpad-preprocess` 拉回 Gitee |
| 靶子 A（论文实验提取） | 需本地 VLM（olmOCR/Qwen3-VL），出 SPEC 后再排期 |
| 靶子 B（材料预测） | 论文级课题，5-7 天，放远期 |
| 认知架构记忆层（F） | 先吃 caura-memclaw/swarmvault 架构再定自研/集成 |
| SCI 综述 | 等导师确认方向 |
| Nostr / prime-agent | 观望阶段 |

---

## 五、分工边界（谁碰什么）

| 边界 | 内容 |
|---|---|
| **Trae 做** | W1 安全修复、W2 功能修复、四靶子 C/D、E 预处理融合、LOW 级代码债务 |
| **实验田维护者做** | 出「射频大脑」融合 SPEC、四靶子 A/B SPEC、MEDIUM/HIGH 架构级修复决策、review Trae 提交、认知架构评估 |
| **不碰** | 架构变更、SCI 综述、观望项目、删文件、清 git 历史 |

---

## 六、验收标准

1. **安全止血**：`grep -rn "nodeIntegration:true" neko-electron-shell/` 返回空；route_map.py 无明文 token；openai_proxy 拒绝无鉴权请求
2. **RAG 修通**：默认参数下检索返回非空结果（补回归测试，见 code-review #7 要求）
3. **GRAG 修通**：不连 Neo4j 时，搜 `triples.json` 里的实体能返回正确三元组（见 GRAG SPEC 验收标准）
4. **四靶子 C/D**：LLM4Decompile 本地跑通出一个 test.dll 的可读 C；10 篇 PDF 批量转 Markdown

---

## 七、里程碑

```
Week 1（本周）: W1 安全止血全清 + W2 检索修通 → 陆墨「能安全地正常检索」
Week 2         : 四靶子 C/D 收尾 + 物理层拉取清单拉回 → 出射频大脑 SPEC
Week 3+        : 靶子 A 开工（喂综述）+ 射频大脑 M1 + E 预处理融合
持续           : GitHub 扫货日报（cron 9:00）+ 授粉复盘
```

---

## 元记录

- 整合来源：08-11 九份审计 + 08-13 陆墨全仓 code-review + 08-13 实验田维护者仓库审计 + 08-13 物理层盲区摸底 + 08-09 四靶子 + 08-09 授粉计划
- 下一份文档：`射频大脑-融合-SPEC-v1.md`（实验田维护者出，衔接本规划 W3）
- 变更日志：v1 初版，覆盖六线，后续按周滚动更新
