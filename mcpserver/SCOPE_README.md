# Scope：per-角色 / per-会话 工具可见性（卷124 W124-01）

问题：mcpserver 注册表全局可见，任何角色都能看到并调用全部工具（32 个 agent、上百个工具）。
本模块给出「角色 → 可见工具集」，设计借鉴 DeepSeek Harness 的 Scope 机制（只抄机制，不引代码）。

## 两道校验（缺一不可）

```
tool_schemas.get_all_tool_schemas(agent_id)       ← 展示层：只把可见工具交给模型
        ...
agentic_tool_loop.execute_tool_calls → _guarded
        ├─ _run_scope_gate（本模块）              ← 执行层：直接构造调用也拦得住
        ├─ _run_tool_gate（卷119 pre-execute waterfall）
        └─ _dispatch_one_call → 真正执行
```

只做展示层过滤是不够的（构造一个调用就绕过去了）；只做执行层则会白白浪费 token
（模型看到一堆调不动的工具）。所以两层都做，执行层是兜底。

## 配置

`config.json` 的 `scope` 段：

```json
{
  "scope": {
    "enabled": true,
    "default_visible_all": true,
    "roles": {
      "科研": {
        "allowed_tools": ["mcp__material_science__*", "mcp__code_workspace__*", "mcp__paper_miner__*"],
        "denied_tools": ["mcp__code_workspace__shell_exec"],
        "skills": ["paper-*", "material-*"]
      },
      "桌宠": {
        "allowed_tools": ["live2d__*", "mcp__weather_time__*", "mcp__tts_api__*"]
      }
    },
    "session_roles": { "session-科研-001": "科研" }
  }
}
```

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `enabled` | `true` | 总开关（false = 整层旁路） |
| `default_visible_all` | `true` | 未配置的角色是否可见全部（true = 向后兼容） |
| `roles` | `{}` | 角色 → `{allowed_tools, denied_tools, skills}` |
| `session_roles` | `{}` | 会话 → 角色（会话级覆盖，便于按通道/按会话隔离） |
| `registry_path` | `characters/registry.json` | 角色注册表（其中的 `tool_scope` 会被并入配置） |

### 角色注册表里的写法（可选）

`characters/registry.json` 的每个角色支持 `tool_scope` 字段（与上面 `roles[角色]` 同结构）：

```json
"naga-nadezhda": {
  "role_id": "naga-nadezhda",
  "display_name": "娜杰日达",
  "tool_scope": { "allowed_tools": ["mcp__material_science__*"], "skills": ["paper-*"] }
}
```

中英文名都能引用同一份规则（`resolve_role` 会把显示名/别名归一化回 `role_id`）。
> 注：`characters/registry.json` 是运行时数据文件（未入库），仓库侧只提供**读支持**；
> 要固化某角色的 Scope，写进 `config.json` 的 `scope.roles` 更稳。

## 匹配规则

工具名沿用 `{agentType}__{service}__{tool}` 命名：

| 写法 | 命中 |
| --- | --- |
| `mcp__code_workspace__code_exec` | 精确 |
| `mcp__code_workspace__*` / `mcp__code_workspace*` | `*` 通配（fnmatch） |
| `mcp__code_workspace` | 前缀（该服务下全部工具） |

**`denied_tools` 优先于 `allowed_tools`**；`allowed_tools` 为空 = 该角色不设白名单
（但仍受黑名单限制）。

命名形态差异也被兜住：native function calling 传 `mcp__svc__tool`，文本兼容期只有
`service_name` + 短工具名——判定时用多个别名（限定名/原名/短名）一起试，避免误拦。

## 示例：三角色

| 角色 | 可见 | 说明 |
| --- | --- | --- |
| 陆墨（默认角色） | 全量 | 未配置 → `default_visible_all=true` 全可见（现状不变） |
| 科研 | 材料/代码/论文三个服务，去掉 `shell_exec` | 白名单 + 黑名单覆盖 |
| 桌宠 | `live2d__*`、天气、TTS | 白名单 |

## 调试

```python
from mcpserver import scope
scope.scope_summary()                     # 当前配置 + 解析到的角色 + 注册表路径
scope.visible_tools(["mcp__code_workspace__code_exec"], role="科研")
scope.resolve_role(agent_id="娜杰日达")     # -> "naga-nadezhda"
```

启动日志里能看到过滤结果：`[ToolSchemas] Scope 过滤：角色 科研 隐藏 87/94 个工具`。

## 测试

```bash
.venv/Scripts/python.exe -m pytest tests -k test_scope -q      # 11 passed
```

覆盖：匹配规则（精确/前缀/通配）/ 白名单过滤 / 黑名单优先 / 未配置角色兼容（含
`default_visible_all=false` 收紧）/ 总开关旁路 / 会话级绑定 / 注册表 `tool_scope` 合并与
中文名归一化 / 技能白名单 / 执行层拦截（含短名形态）/ 执行层按会话角色 / Scope 异常 fail-open /
整链路拦截（不可见工具不进执行器）。

## 回滚

`scope.enabled=false` 即整层旁路；删 `mcpserver/scope.py` 与两处接线
（`tool_schemas` 过滤、`_run_scope_gate`）回到全局可见。
