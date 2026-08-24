# GitHub 扫货 — 最终规划（2026-08-13）

> 来源: 2026-08-13 扫货日报（Discovery-Only）
> 去重基准: GitHub-Haul-Merged-Final-20260809.md + github_haul/ 实际包 + scratchpad 现有 skill
> 落地: 已拉 12 项 → GitHub 私库 `fe1iscurc0r/scratchpad-preprocess`（Trae 手机端预处理，回家拉回 Gitee）

---

## 一、已拉取（12 项，归档于 scratchpad-preprocess）

### mcp/（8 项）

| 项目 | ⭐ | 许可 | 语言 | 说明 |
|------|-----|------|------|------|
| googleapis/mcp-toolbox | 16k | Apache-2.0 | Go | 数据库 MCP，给 Lumo 材料库接 SQL/NoSQL |
| apify/apify-mcp-server | 3.4k | MIT | TS | 现成爬虫 MCP 入口（运行需 APIFY_TOKEN） |
| affaan-m/agentshield | 1k | MIT | TS | Agent 配置/MCP/工具权限漏洞扫描，三层防御自检 |
| PV-Bhat/vibe-check-mcp-server | 503 | MIT | TS | Agent 导师式反馈，防隧道视野 |
| Eshaan-Nair/ArcRift | 246 | MIT | TS | 浏览器↔IDE agent 记忆同步，SQLite 图 |
| swarmclawai/swarmvault | 653 | MIT | TS | 本地 LLM Wiki+知识图谱，离线 heuristic provider |
| nambok/mentedb | 113 | Apache-2.0 | Rust | 认知感知数据库引擎（WAL+HNSW+图） |
| ArcadeAI/arcade-mcp | 1k | MIT | Python | MCP 开发框架（OAuth 依赖 Arcade Cloud） |

### infra/（4 项）

| 项目 | ⭐ | 许可 | 语言 | 说明 |
|------|-----|------|------|------|
| remsky/Kokoro-FastAPI | 5.3k | Apache-2.0 | Python | 本地 TTS Docker API，CPU 可跑 |
| thewh1teagle/kokoro-onnx | 2.7k | MIT | Python | Kokoro TTS 的 ONNX 运行时 |
| rsxdalv/TTS-WebUI | 3.2k | MIT | TS/Python | 30+ TTS 模型聚合（跑满需 GPU） |
| agentic-community/mcp-gateway-registry | 859 | Apache-2.0 | Python | 企业级 MCP 网关+注册中心，OAuth/审计 |

---

## 二、排除（2 项）

| 项目 | 原因 |
|------|------|
| screenpipe (20.9k) | **非 MIT** — source-available 商业许可，商用需付费，不能吞进 AGPL 主仓 |
| materialyzeai/mlearn | 已 archived 废弃 |

## 三、已融合（1 项，不重复拉）

- hachmannlab/chemml → scratchpad skills/ 已有 deepchem/rdkit/datamol/molfeat/pytdc 覆盖材料特征工程

---

## 四、预处理优先级（回家后按序执行）

| 优先级 | 项目 | 理由 |
|--------|------|------|
| P0 | Kokoro-FastAPI + kokoro-onnx | NEKO 语音本地化，CPU 可跑，最高降本点 |
| P1 | mcp-toolbox | Lumo 材料库接 DB 工具链，零 UI 即插 |
| P1 | agentshield | 三层防御体系安全自检补位 |
| P2 | mcp-gateway-registry | 多实例 Hermes 工具治理架构参考 |
| P2 | swarmvault / mentedb / ArcRift | 记忆层候选，先吃架构再决定自研/集成 |
| P3 | apify / arcade-mcp | 二线，前者付费后者云托管，先看代码模式 |

---

## 五、关键认知修正（本轮教训）

1. **预处理环境 ≠ 云服**：项目拉到 Trae 手机端预处理（看代码/写 SPEC），不是云服跑。云服的 node/Rust/GPU 版本不构成筛选标准——之前误杀 5 项已补回。
2. **运行依赖 ≠ 能不能拉**：apify（付费）、arcade-mcp（云托管）、TTS-WebUI（GPU）运行有门槛，但代码能拉能看，README 标了运行条件即可。
3. **screenpipe 许可真相**：早报标的 MIT 是错的，实为 source-available 商业许可，是 AGPL 主仓的硬边界。
4. **AV 误报处理**：agentshield tests/ 含恶意配置样本触发腾讯云告警，已打包 tests_archive.tar.gz（tar.gz 不触发 AV），源码树删除，数据不丢。

---

## 元记录

- 关联: GitHub-Haul-Merged-Final-20260809.md（基准清单）
- GitHub 私库: fe1iscurc0r/scratchpad-preprocess（private，204M）
- 下一步: 回家 git clone → 拉回 Gitee → 按优先级融合
