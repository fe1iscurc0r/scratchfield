# W68-08 cti-expert 评估（CTI 分析 skill）

> 上游：github.com/7onez/cti-expert · 许可 MIT（API 误标 NOASSERTION，LICENSE 文本为 MIT）· 585★ · Python · 2026-08-28 活跃
> 落点：docs/cti-expert-评估.md · 勘察/评估

## 1. 项目定位

面向 Claude Code 的 **CTI（网络威胁情报）与 OSINT 分析 skill**：67+ 命令、35 种技术、无需 API key，把 CTI/OSINT 分析流程封装成可直接调用的 skill。

## 2. 架构拆解

- **形态**：Claude Code skill（67+ 命令 / 35 技术）。
- **无 API key**：依赖公开数据源与本地分析技术。
- **定位**：把「威胁情报分析 + OSINT」的专家流程沉淀为 skill，供 agent 直接调用。

## 3. 与本仓对照

| 维度 | cti-expert | 本仓 |
|---|---|---|
| CTI/OSINT | 67+ 命令 skill | agent_osint + sentinel_intel（实体图谱）+ sentinel-osint-勘察报告 |

## 4. 可落地借鉴点（≥3）

1. **「命令 + 技术」双目录**：67 命令（可执行步骤）× 35 技术（方法论），把专家流程结构化为「命令清单 + 技术清单」，可复用到我们 OSINT skill 的目录组织。
2. **无 API key 的公开源优先**：优先用公开数据源，降低接入门槛。
3. **skill 形态**：CTI/OSINT 作为可挂载 skill 而非独立服务，与我们 offensive-osint 的 skill 化方向一致。

## 5. 许可裁定 + 结论

- **许可**：LICENSE 文本为 MIT（API 误标 NOASSERTION，版权 Hieu Ngo）→ **MIT，可借鉴代码**。
- **并入 vs 参考结论**：**参考为主，不整体并入**。67+ 命令与技术清单可作为我们 osint-methodology / offensive-osint 的补强清单；若许可核清为宽松许可，可抽取无冲突的命令并入。
