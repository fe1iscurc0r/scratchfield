# Facet 槽位 · 阶段一落地报告 · 2026-09-30（卷178）

> 工单：`TRAE_WORKORDER_PROMPT_AGENT_178.md` · 设计稿：`docs/Facet槽位-设计-2026-09-29.md`（权威）
> 范围：**阶段一** = manifest 契约 + 宿主加载器 + 演示 Facet；渲染端（状态卡片/控制面板 UI）留阶段二。

---

## 一、交付物

| 任务 | 产物 | 说明 |
|---|---|---|
| A manifest 校验规则 | `mcpserver/tool_registry/check_classification.py` 新增 `check_facets_rules()` | 设计稿 §二 四条强制约束（校验入口沿用既有的 `check_classification.py`，设计稿原话「校验脚本后续可加规则」） |
| B 宿主加载器 | `apiserver/facet_loader.py`（`FacetRegistry` / `PanelSpec` / `PrecheckSpec` / `FacetActivationError`） | 扫描 → 注册 → 装配同源判定 → 预检 → 挂载；失败**结构化不静默** |
| C 演示 Facet | `tools/facet_demo.py`（uptime 状态卡片）+ 测试内端到端 | 玩具级，不碰真实硬件（mechat 侧是协商层定型后的事） |
| 测试 | `tests/test_facet_loader.py` **15 例** | 校验 7 例 + 注册 2 例 + 激活 5 例 + 端到端 1 例 |

## 二、契约实现（以设计稿为准）

**manifest 增量块** `facets.panel`（**无此块 = 无面板面，零迁移成本**）：

```jsonc
"facets": {
  "panel": {
    "kind": "status-card",              // status-card | control-panel
    "component": "UptimeCard",           // 前端注册表解析名（阶段二消费）
    "title": "系统运行时长",
    "poll": { "tool": "uptime_status", "interval_ms": 1000 },
    "actions": [ { "tool": "...", "confirm": true, "always_available": true, "reduces_risk": true } ],
    "precheck": { "command": "python", "label": "python 可用" }   // 工单要求的声明式预检
  }
}
```

**校验规则（写进 check_facets_rules，测试逐条断言）**：

| 规则 | 来源 |
|---|---|
| `poll.tool` / `actions[].tool` 必须在已声明工具面（tools[] 或 invocationCommands） | 设计稿：「面板不是旁路」 |
| `poll.interval_ms >= 250` | 设计稿：防轮询风暴 |
| `kind=control-panel` 必须声明 `actions` | 设计稿：名不副实的面板不如不声明 |
| `always_available: true` 须同时声明 `reduces_risk: true` | 设计稿 §四.3：闸门不得挡安全路径（急停例外） |
| `kind` ∈ {status-card, control-panel}；`component` 必填 | 结构完整性 |

**激活语义（与装配策略同源，单一判定）**：

```
activate(agent, enabled=, available=, tool_probe=)
  ① enabled && available（来自 GET /mcp/services 的该 agent 状态，设计稿 §四.1）
      不满足 → FacetActivationError(failed_check="assembly")
  ② precheck.command 存在性（shutil.which）/ precheck.tool 谓词
      不过 → FacetActivationError(failed_check="precheck:command" | "precheck:tool")
  ③ 全过 → 挂载 PanelSpec
```

失败错误的序列化形状（**不静默降级**，与仓内错误报告惯例对齐）：

```json
{"agent": "uptime_panel", "facet": "panel",
 "failed_check": "precheck:command",
 "reason": "命令 'definitely-not-a-real-command' 不存在于本机 PATH"}
```

## 三、命令行为（工单要求贴命令行）

**成功链路**：

```
$ python tools/facet_demo.py
== 1. 清单校验（设计稿 §二 四条规则）
   校验结果: 通过 ✓
== 2. 扫描注册
   注册 uptime_panel | kind=status-card | component=UptimeCard
== 3. 激活（装配同源判定 + 预检）
   激活成功 ✓ title=系统运行时长 poll={'tool': 'uptime_status', 'interval_ms': 1000}
== 4. 查询（宿主按 poll.tool 走工具面）
    {"tool": "uptime_status", "uptime_s": 4242.0, "render": "UptimeCard(系统运行时长)", "status": "ok"}

全链路通 ✓（注册 → 激活 → 查询）
```

**失败链路（预检不过 → 结构化错误，不静默）**：

```
$ python tools/facet_demo.py --fail
== 3. 激活（装配同源判定 + 预检）
   激活失败（结构化错误，不静默）:
    {"agent": "uptime_panel", "facet": "panel", "failed_check": "precheck:command",
     "reason": "命令 'definitely-not-a-real-command' 不存在于本机 PATH"}
```

**测试**：

```
$ pytest tests/test_facet_loader.py -q
15 passed
```

## 四、硬约束遵守与边界

| 约束 | 状态 |
|---|---|
| 不动既有域包加载器 | ✓（新增 `facet_loader.py`，零改造） |
| 零新增重依赖 | ✓（纯 stdlib；jsonschema 未引入——校验用手写规则，与既有 check_classification 同风格） |
| 渲染/UI 不碰 | ✓（阶段二；`component` 名仅作契约声明，未写前端） |
| mechat/法律包不碰 | ✓ |
| 真实能力清单零污染 | ✓（演示 manifest 在 tmp 目录；**当前仓库无任何 manifest 声明 facets——这是零迁移成本的现状基线**，真实面板待阶段二/mechat 侧按需声明） |

## 五、阶段二待办（不在本卷）

- 前端：`frontend/src/components/facets/registry.ts` 组件注册表 + `FacetPlaceholder` 降级
- 渲染位：SkillView 遍历「已启用且可用」agent 的 facets.panel
- `check_classification.py` 的 facets 规则接入 CI lint 路径（本卷已入校验函数，运行时机沿用既有脚本）
