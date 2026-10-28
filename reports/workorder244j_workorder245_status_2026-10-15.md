# 工单 244j 报告 · 工单 245~249 的状态、查重预检 + 生成器模板修复

> 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）
> 日期：**2026-10-15** · 基线：main `01aa018dba`
> 触发：「我记得工单已经出了吧，没有上传吗？然后你再看看有没有其他问题？」
> 变更：**7 文件**（1 生成器模板修复 + 5 草稿同步修 + 本报告）—— **未 promote 任何草稿**

---

## §0 · 直接回答：「工单出了但没上传」= **设计如此，不是漏推**

**工单确实出了** —— 但不是规范工单，而是 **5 张自动草稿**：
`research/workorder_drafts/auto_2026-10-14/WO-245…WO-249`（含 `_manifest.json`），
由 `cron_to_workorder`（工单240 的自动化，来源 5 个 cron、27 个候选去重后取 5）于 **2026-10-14** 自动落盘。

**没上传到根目录是设计如此**：每张草稿第 5 行都写着
> ⚠️ 本文件是**自动草稿**，未经人工审阅；**`--promote` 前须师傅签字**（设计稿 §5「必须人工 --promote」）

⇒ 晋升（`--promote … --apply`）是**人工闸门**，我不能替你按。§3 给出现成命令与逐张建议。

**顺带发现并已修**：5 张草稿与生成器模板的「耦合点」清单里写着 **`core/`** ——
该目录**全树不存在**（242/243 已证 0 命中）。本单把模板与 5 张草稿统一改成真实存在的
`mcpserver/` / `agentserver/` / `apiserver/` / `coupled/`。

---

## §1 · 5 张草稿 × 查重预检（草稿 §4 要求人工做的，我已代做）

| 草稿 | 上游 | 主题线 | 分 | 查重结论 | 耦合点候选 | 建议 |
|---|---|---|---|---|---|---|
| **WO-245** | `mixelpixx/KiCAD-MCP-Server`（MIT） | agent, pcb | 7 | **不重复**：217 是**嘉立创 EDA**（不同工具）；且 242/244 的 prompt 都点名过 `mcpserver/kicad-mcp/` —— **该路径至今 404** ⇒ 正好补上这个被点名过两次的缺口 | `mcpserver/`（新 kicad-mcp 子模块）+ `coupled/`（EDA 生态，217 的四件套） | ⭐ **推荐 promote** |
| **WO-246** | `arXiv:2608.18272v1`（SeisEvo） | sdr, agent, esp32 | **11**（5 张里最高） | 不重复（已发工单零命中）；但与 `rf_workflow`(242)/`rf_brain` **相邻** —— SeisEvo 是 LLM 多智能体搜索，242 是 LoRa PHY 工作流，角度不同 | `mcpserver/rf_*` | 先划界再 promote |
| **WO-247** | `LimiNode/agent-memory-cpp`（MIT） | agent, esp32 | 7 | ⚠️ **工单214 已做过「记忆层第二梯队融合调研」**（EverOS / tigerless **agent-memory** / neo-chat）—— 主题高度相邻（LimiNode 是 C++ 嵌入式向） | `memory_maas/`、`graph_memory_adapter/`、`summer_memory/` | ⚠️ **查重最需人工判断**：若只做调研则与 214 重复；若做 ESP32 嵌入式落地则需与 214 划界 |
| **WO-248** | `78/xiaozhi-esp32` | agent, esp32 | 6 | 不重复；与 `esp32` 线(243)+`voice_mcp_*` 相邻 | `mcpserver/esp32/` + voice | 可 promote，需与 243 划界 |
| **WO-249** | `karmine05/agentic-detector`（MIT） | agent | 6 | 不重复；与 `agent_governance`(241) 相邻（osquery **端点探测** vs 治理**钩子**，互补） | `mcpserver/agent_governance/` | 可 promote |

> 查重方法：5 张草稿的主题词（kicad / pcb / 2608.18272 / agent-memory / xiaozhi / osquery）
> 对根目录 45 个已发工单逐词 grep；`core/` 无关紧要（不存在）。

---

## §2 · 本单修的问题：生成器模板里的陈旧路径

`tools/cron_to_workorder.py:561` 的草稿模板写着
`与现有模块的耦合点（mcpserver/ / coupled/ / core/）` —— **`core/` 全树 0 命中**（242/243 已证）。
每张自动草稿都会带着这条**指向不存在目录**的待补项出仓。

**修复**：模板与 5 张现存草稿统一改为
`mcpserver/ / agentserver/ / apiserver/ / coupled/`（全部真实存在）。
测试未锁定该行（`test_cron_to_workorder.py` 无断言），改动安全。

---

## §3 · promote 现成命令（师傅按需执行；默认 dry-run，`--apply` 才落盘）

```bash
.venv/Scripts/python.exe tools/cron_to_workorder.py --repo . \
  --promote research/workorder_drafts/auto_2026-10-14/WO-245-mixelpixx-kicad-mcp-server-kicad-pcb-mcp.md --apply
# …246/247/248/249 同理；目标号自动取根目录最大号+1（下一个=245），幂等保护：目标已存在则拒绝
```

机制已验证：`--promote` 默认 **dry-run**；首行必须是 `# 工单 <n> · …`；目标已存在**拒绝覆写**；
落盘强制 **LF**（内部有断言）。**本单未执行 --apply** —— 这是设计上留给师傅的闸门。

---

## §4 · 验证

| 项 | 结果 |
|---|---|
| 模板修复后 `cron_to_workorder.py` 语法 | ✅（`ast.parse`） |
| 5 张草稿的陈旧行 | ✅ 全部替换（5/5） |
| promote dry-run（修后代码） | ✅ `WO-245 → TRAE_WORKORDER_PROMPT_AGENT_245.md` |
| manifest 一致性 | 草稿文件名/编号未变 ⇒ `_manifest.json` 无需改动 |
