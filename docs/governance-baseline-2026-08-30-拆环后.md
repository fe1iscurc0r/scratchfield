# 治理基线更新 · apiserver 依赖环拆解后（07-03）

> 智能体 07 · 治理线 · 2026-08-30
> 前序：07-01 真实依赖图谱（`docs/governance-apiserver-rings-2026-08-30.md`）
> 本文归档拆环结果 + 更新治理基线，给出下轮拆环建议。

---

## 一、拆环结果摘要（对比基线）

| 指标 | 拆环前（08-30 基线） | 拆环后（本轮） | 变化 |
| --- | --- | --- | --- |
| 治理脚本报出的"环"数 | 5 | **0** | 5 → 0 ✅ |
| 真实模块级依赖环（≥3 节点） | （未区分，被误判） | **0** | — |
| 函数内延迟导入假环（仅信息） | 5 | 5（改列 `lazy_cycles`） | 口径纠正，非新增 |

> 说明：拆环前基线快照 `model-2026-08-30_10-49-11.json` 在 Linux 生产机
> `/home/ubuntu/scratchpad/data/system_pulse/` 下，本机（Windows）无该文件；
> 故"环数 5"以工单 `TRAE_WORKORDER_PROMPT_AGENT_07.md` 环清单为准（5 环）。

**结论：5 个环全部核实为假环，无需改动 apiserver/rag/system/mcpserver 业务代码。**
本轮"拆环"落点是修正检测层：`system_governance.py` 扫描器把「函数内延迟导入」误判为
依赖边，现已区分「模块级硬依赖(真边)」与「函数内延迟导入(假边)」，环检测只用硬依赖，
`--model` 从此报真实依赖图。

---

## 二、新快照

- 文件：`data/system_pulse/model-2026-08-30_13-09-29.json`（本机，`data/` 已 gitignore，运行时产物）
- 生成方式：`python scripts/system_governance.py --model`（跨平台路径修正后可在本机运行）

```text
模块数 13 | 总 py 3481 | 总行数 1,436,033
孤岛: ['coupled', 'research']
根(只出): ['NEKO', 'summer_memory', 'tools', 'guide_engine', 'voice']
叶(只入): ['rag', 'system']
环(真实, 模块级): 无   ← 拆环后
假环(延迟导入, 仅参考): 5
```

> 模块数 13（`kb_sync` 已从 TOP_MODS 移除，属 08 线孤岛治理，与本轮无关）。
> 叶节点 `rag`/`system` 由"只入不出"的硬依赖判定而来：二者对其它模块只有函数内延迟导入、
> 无模块级硬出边——与 07-01 结论一致。

---

## 三、剩余环清单

### 真实模块级环（治理口径）：0 个 ✅

7 个病灶模块（apiserver/rag/system/mcpserver/summer_memory/agentserver/guide_engine）的
**模块级硬依赖图无 ≥3 节点循环**。唯一双向边是 `apiserver ↔ agentserver`（2 节点互引，
治理脚本按设计排除，属"正常双向依赖"）。

### 函数内延迟导入假环（仅参考）：5 个

```text
1. apiserver → agentserver → guide_engine → apiserver
2. apiserver → agentserver → system → apiserver
3. apiserver → mcpserver → summer_memory → apiserver
4. guide_engine → apiserver → mcpserver → guide_engine
5. mcpserver → apiserver → agentserver → system → mcpserver
```

这些"环"的闭合边全是函数内 `from X import Y`，导入期不执行、运行期按需加载，
无循环导入风险（实证：7 模块顺序 `import` 全部成功，`import rag` 不触发加载 `system`）。

---

## 四、下轮拆环建议（有依据，非拍脑袋）

| 优先级 | 建议 | 依据（文件:行号） |
| --- | --- | --- |
| **P1** | 收敛 `apiserver ↔ agentserver` 2 节点模块级互引（用接口反转/总线） | `apiserver/routes/extensions.py:26`（硬引 agentserver）↔ `agentserver/travel_notifications.py:8`（硬引 apiserver） |
| **P2** | 顶层 `try/except ImportError` 守卫导入（如 `mcpserver → guide_engine`）改为显式插件注册，去掉"软依赖" | `mcpserver/agent_game_guide/guide_tools.py:6-12`、`mcpserver/agent_screen_vision/agent_screen_vision.py:9-14` |
| P3（观察） | `apiserver → mcpserver`、`apiserver → rag` 的模块级硬依赖（`apiserver/routes/apps.py:13`、`apiserver/routes/rag.py:22`）目前不构成环，暂不动 | 见 07-01 报告环 3/环 5 |

> P1 的 2 节点互引虽不算"病理环"，但 `agentserver.travel_notifications` 是模块级硬引
> apiserver，属于最接近"真环"的一条边；下轮若做接口反转，首选从这条边动手。
> 本轮遵循"只拆一个环 + 不碰业务逻辑"红线，未对上述业务代码动刀。

---

## 五、本轮改动清单（分项 commit）

| commit | 内容 |
| --- | --- |
| 07-01 | `docs/governance-apiserver-rings-2026-08-30.md`（真实依赖图谱） |
| 07-02 | `scripts/system_governance.py`（扫描器硬/延迟分离 + 跨平台路径 + 环检测确定性）+ `tests/test_governance_rings.py`（4 个回归测试） |
| 07-03 | 本文 + `WORK_ITEMS` 新增 `A07` 记录 |

验证：`tests/test_governance_rings.py` 4 passed；`--model`/`--cpm`/`--pulse` 均正常；
`--model` 环数 5 → 0。
