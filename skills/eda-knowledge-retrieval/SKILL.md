---
name: eda-knowledge-retrieval
description: EDA 知识回查 skill：查询历史项目文档源码、寄生参数估算、BOM 比价等已入库数据（ingest 落盘 + lightrag 知识库），并把结果回注当前设计。适用于设计中"查以前怎么画的/上次这个件多少钱"的场景。
allowed-tools: Read Write Edit Bash
license: MIT license
metadata:
  version: "1.0"
  skill-author: scratchpad
  workorder: "219"
---

# eda-knowledge-retrieval

## Overview

工单217 落了 ingest（EDA→云服单向），本件补"**入库之后怎么查**"：
查 `<user_data>/eda_ingest/` 的历史文档源码 + lightrag 知识库 + SPEC-20 系列文档，
把历史经验**回注到当前设计**。

## When to Use This Skill

- 用户说"上次 RA01 底板的电源是怎么画的 / 以前的寄生估算多少 / 这颗料上回买多少钱"。
- 新板设计前的**借鉴环**（skill 矩阵的最后一环：归档→复刻）。
- DRC/仿真遇到可疑问题时查历史同型问题的处置。

不要用于：
- 实时编辑器状态查询（那是 easyeda-agent daemon 的活）；
- 公开资料检索（那是 web_search/学术工具的活）。

## Workflow

### 0. 数据源盘点（三处）

| 源 | 位置 | 内容 | 查法 |
|---|---|---|---|
| ① ingest 落盘 | `<user_data>/eda_ingest/*.json` | 历史文档源码（.esch/.epcb，工单217） | 文件名（工程名+时间）→ 读 JSON → 解析 |
| ② 知识库 | lightrag_graph（`/api/knowledge/*`） | 结构化知识项（含 fork 版 export-design-report 的报告） | `knowledge search` 端点 |
| ③ SPEC/文档 | `docs/SPEC-20-*`、`docs/easyeda-*` | 设计决策/工单记录 | grep |

### 1. 查历史文档源码（①）

```bash
ls <user_data>/eda_ingest/ | grep <工程名>
# → 最新一份（时间戳最大）
python -c "import json; d=json.load(open('<file>')); ..."   # 或走 read_schematic.py 解析链
```
典型问题→查法映射：
- "电源怎么画的" → 解析 .esch 找 LDO 器件 + 相连网络（网表级问答）。
- "RF 匹配网络值" → .esch 中电感/电容值 + 网络拓扑。

### 2. 查寄生估算/报告（②）

- export-design-report（fork 版）推过的 PCB 统计/寄生参数 → knowledge 库按工程名/器件位号查。

### 3. 查 BOM 比价历史（①+③）

- ingest 里的 .epcb 源 → 器件表；对比 SPEC-20 BOM 节的历史价格列。

### 4. 结果回注 EDA（闭环）

查到的东西怎么用回去：
- **数值复用**：把历史网络值写进当前网表定义 → schematic-autodraw 重画该子电路；
- **布局参考**：历史 .epcb 器件坐标 → 给 layout skill 的摆放建议当初始分区参考；
- **避坑注入**：历史 pitfalls（如某料封装错）写进当前板的 SPEC 备注节。

## Pitfalls

1. ingest 是**快照**不是版本历史——同工程多次推送时按内容 hash 去重（工单217 幂等设计），
   "最早版本"可能已被"最新版"替代语义覆盖，查演进史要去 git/归档找。
2. .esch 解析依赖自家 `read_schematic.py`（HW-06 链），复杂图页解析不全时降级为
   器件清单级问答（不硬答拓扑）。
3. knowledge 库内容质量取决于当时入库的报告——查到旧数据先看 timestamp 再信。
4. 涉及未推云服的本机项目 → ingest 里没有（提醒用户先跑一次 parasite-export）。

## 实测验证步骤

1. 对最近一次 ingest 的工程执行"电源链路查询"：断言能列出 LDO 型号 + 输入输出网络。
2. 查一个 SPEC-20 记录过的器件价格，与知识库/文档两处比对一致性。
