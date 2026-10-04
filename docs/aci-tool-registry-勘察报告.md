# aci-mcp tool registry 勘察报告 · S-01

> 勘察对象：ACI.dev（`aipotheosis-labs/aci`）+ `aipotheosis-labs/aci-mcp`（MCP 薄封装）
> 授粉纪律：只读勘察，以下为**结构描述重写**，未复制任何 aci 源码。
> 前置缺项：`github_haul/POLLINATION-2026-08-24-round5.md` 全仓任何分支均不存在，§3.1 的 App/Function 二元定义已改用 aci 上游一手材料（`backend/apps/*/app.json` + `functions.json` 真例）直接核对，结论更可靠。

---

## 0. 结论先行

aci-mcp 的「工具注册」不是靠一个中心化 registry 文件，而是**「app 元数据 + functions 清单」两层分离 + 服务端按 JSON Schema 校验参数 + 动态发现**。mcpserver 现有 `agent-manifest.json` 已有「声明式描述工具」的正确方向，但缺三层关键能力：**① 参数没有类型/必填/枚举约束（JSON Schema）② 没有 app 层元数据（security_schemes/categories）③ 没有统一的搜索/执行 meta 工具**。S-02 的 `meta.yaml` 就是补这三层。

---

## 1. aci 注册表结构图

```
backend/
├── apps/                          # 600+ 个「App」= 工具的宿主/分组单元
│   ├── github/
│   │   ├── app.json               # ① App 层元数据
│   │   └── functions.json         # ② Function 层清单（数组）
│   ├── gmail/  app.json + functions.json
│   └── ...
├── aci/common/schemas/
│   ├── app.py                     # App 模型（字段契约）
│   ├── function.py                # Function 模型（字段契约）
│   └── security_scheme.py         # 鉴权方案模型
├── aci/cli/commands/upsert_functions.py   # 登记入口：CLI 把 app.json/functions.json 写入 DB
└── aci/server/
    ├── routes/functions.py        # 发现/执行路由（search / execute / get_definition）
    └── function_executors/        # 按 protocol+security_scheme 选执行器
        ├── rest_function_executor.py        # 无鉴权 REST
        ├── rest_api_key_function_executor.py
        ├── rest_oauth2_function_executor.py
        └── connector_function_executor.py

src/aci_mcp/                       # aci-mcp = 只做 MCP 协议适配，不存工具
├── apps_server.py                 # 模式1：暴露指定 apps 的所有 functions
├── unified_server.py              # 模式2：两个 meta 工具（search + execute）
└── common/{runners.py, validators.py}
```

**两层模型（App / Function 二元定义）**：

| 层 | 文件 | 关键字段 | 职责 |
|----|------|---------|------|
| App | `app.json` | `name` / `display_name` / `description` / `version` / `security_schemes` / `categories` / `visibility` / `active` | 工具的分组 + 鉴权 + 分类元数据（「工具即资源」的资源身份） |
| Function | `functions.json[]` | `name` / `description` / `tags` / `protocol` / `protocol_data` / `parameters`(JSON Schema) / `response` / `visibility` / `active` | 单个可调用接口 + 参数契约（JSON Schema） |

---

## 2. 注册 / 发现 / 校验 / 鉴权流程

### 2.1 注册（登记）
1. 每个 App 一个目录，手写 `app.json` + `functions.json`（纯声明，无代码）。
2. `aci/cli/commands/upsert_functions.py` 把两个文件 upsert 进服务端 DB（幂等，可重复跑）。
3. Function 的 `protocol`（rest/oauth2/connector）+ App 的 `security_schemes` 决定它走哪个 `function_executor`。

### 2.2 发现（Discovery）—— 动态，非静态文件扫描
1. aci-mcp `apps_server` 启动时持有一份 `APPS` 名单，`handle_list_tools` 调 `aci.functions.search(apps, FunctionDefinitionFormat.ANTHROPIC)`。
2. 返回的每个 function 被映射成 MCP `types.Tool{name, description, inputSchema}`（`inputSchema` 直接来自 function 的 `parameters` JSON Schema）。
3. `unified_server` 则暴露两个 **meta 函数**：`ACI_SEARCH_FUNCTIONS`（按描述搜函数）+ `ACI_EXECUTE_FUNCTION`（按名执行任意函数）——**「用工具发现工具」**，这是 aci 最值得借鉴的模式。

### 2.3 参数校验（Validation）
- **契约层**：function 的 `parameters` 是完整 JSON Schema（`type/properties/required/visible/additionalProperties`），发现阶段即暴露给 MCP client 做客户端侧校验。
- **执行层**：`aci.functions.execute(name, arguments, owner_id)` 把参数交给后端执行器，服务端按 schema 校验后调用真实 HTTP/REST 端点。
- 关键点：**参数是「有类型的 JSON Schema」，不是描述字符串**——这是与 mcpserver 现状最大的差距。

### 2.4 鉴权（Auth）
- App 层 `security_schemes` 声明鉴权方式（`api_key`/`oauth2`），含 `location`(header/query)、`name`、`prefix`、`oauth2 端点`等。
- 运行时凭据与 `security_scheme` 分离存储（`default_security_credentials_by_scheme`），执行器按 scheme 注入。
- aci-mcp 侧用 `ACI_API_KEY`（服务端凭据）+ `aci_override_linked_account_owner_id`（多租户临时覆盖）。

---

## 3. mcpserver 现状对照表（一致点 / 差距 / 可借鉴）

| 维度 | mcpserver 现状（bofire/chembl/scikit_fingerprints） | aci 参照 | 判定 |
|------|------|------|------|
| 工具描述方式 | `agent-manifest.json` 声明式 `invocationCommands[]` | `functions.json[]` 声明式 | ✅ **一致点**：都是「元数据与执行体分离」的声明式思路 |
| 分组单元 | 一个包一个 manifest（`name` = 包名） | 一个 App 一个 `app.json` | ✅ 一致点：都有「分组」概念 |
| 执行体绑定 | `entryPoint.module/class` | `protocol + protocol_data` + executor | ✅ 一致点：都从元数据指向真实执行路径 |
| **参数契约** | `params` = 扁平 `{参数名: 描述字符串}`，**无类型/必填/枚举** | `parameters` = **完整 JSON Schema** | ❌ **差距**：mcpserver 参数无类型约束，只能靠 LLM 猜测 |
| **app 层元数据** | 无 `security_schemes`、无 `categories` | `security_schemes` + `categories` + `visibility/active` | ❌ 差距：缺鉴权声明与分类 |
| **发现方式** | `mcp_registry.py` 静态扫描 `**/agent-manifest.json` | DB 存储 + `search()` 动态查询 | ⚠️ 部分差距：mcpserver 只有静态扫描，无「搜工具」meta 能力 |
| **两层结构** | 单层（manifest 内扁平命令数组） | app/function 两层拆分 | ❌ 差距：S-02 要补的两层拆分 |
| 命名风格 | `displayName`（camelCase） | `display_name`（snake_case） | ⚠️ 小差异，兼容转换时映射 |
| 字段名 | `command` | `name` | ⚠️ 小差异，兼容转换时映射 |

**可借鉴点（按性价比排序）**：
1. **两层拆分**（app 元数据 + functions 清单）→ 直接落到 `meta.yaml` 的 `app:` / `functions:` 两段。
2. **参数 JSON Schema 化**（`type/properties/required/enum`）→ 让「参数校验」从 LLM 猜测变成机器可查。
3. **`security_schemes` + `categories`** → 为「工具即资源」的发现/鉴权预留接口（本地纯软件工具可空，但结构先占位）。
4. **meta 搜索工具**（`search_functions`/`execute_function`）→ registry.py 后续可加「按描述搜工具」的索引接口。

---

## 4. 统一 meta.yaml 建议（照 aci 拆两层）

### 4.1 结构总览

```yaml
# mcpserver/tool_registry/meta.yaml 的统一结构
app:                      # ① App 层（工具的资源身份）
  name: <snake_case 唯一名>          # 对齐 aci app.json.name
  display_name: <人类可读名>          # 对齐 aci app.json.display_name
  version: <semver>
  description: <一段话说明>
  categories: [materials, ...]        # 对齐 aci categories（发现用）
  security_schemes: {}                # 对齐 aci security_schemes（本地工具可为空）
  visibility: public
  active: true

functions:                # ② Function 层（可调用接口清单）
  - name: <函数名>                     # 对齐 aci functions.json[].name
    description: <函数说明>
    parameters:                        # 对齐 aci functions.json[].parameters = JSON Schema
      type: object
      properties:
        <arg>:
          type: <string|number|integer|boolean|array|object>
          description: <参数说明>
          enum: [...]                  # 可选
          default: ...                 # 可选
      required: [<arg>, ...]
      additionalProperties: false
    # 可选：本地工具额外保留入口指向（对齐 mcpserver entryPoint）
    entrypoint:
      module: mcpserver.bofire.agent
      class: BofireAgent
```

### 4.2 字段映射（旧 manifest → meta.yaml）

| 旧 agent-manifest.json | 新 meta.yaml |
|------------------------|-------------|
| `name` | `app.name` |
| `displayName` | `app.display_name` |
| `version` / `description` / `author` / `license` | `app.version` / `app.description` /（author/license 并入 `app` 可选字段） |
| `capabilities.invocationCommands[].command` | `functions[].name` |
| `capabilities.invocationCommands[].description` | `functions[].description` |
| `capabilities.invocationCommands[].params`（扁平描述字符串） | `functions[].parameters`（JSON Schema，**补类型/必填**） |
| `entryPoint.module/class` | `functions[].entrypoint.module/class`（或 `app.entrypoint`，见 4.3） |
| （无） | `app.categories` / `app.security_schemes`（新增） |

### 4.3 落地建议（给 S-02 的实现约束）

1. `meta.py`：加载 + 校验 `meta.yaml`（app 层必填 `name`，function 层必填 `name` + `parameters`）；构建 `name → MetaApp` 与 `(app.name, fn.name) → MetaFunction` 两级索引。
2. `registry.py`：扫描 `mcpserver/*/agent-manifest.json`，把旧格式**兼容转换**为统一 meta（旧 `params` 的扁平描述字符串 → `parameters.properties` 每个默认 `type: string`），**增量不破坏**已有 manifest。
3. `schemas/`：一份 JSON Schema 校验统一 meta.yaml（app 层 + function 层字段约束）。
4. 三库 meta.yaml：`bofire` 从真实接口提取参数类型；`pycalphad`/`smiles-transformer` 按 `docs/academic/` 调研报告写参数契约。

---

## 5. 勘察结论

- aci 的注册表本质是 **「两层声明式清单 + JSON Schema 参数契约 + 动态发现」**，没有魔法 registry 单例。
- mcpserver 现状方向正确（声明式 manifest），S-02 只需**补两层结构 + 参数类型化 + app 元数据**即可达到「工具即资源」的统一注册，无需重构现有 agent。
- 本报告未复制任何 aci 源码，所有结构均为对照 `app.json`/`functions.json` 真例后的文字重写，符合授粉纪律（aci 为 Apache-2.0，仅结构参考，无传染风险）。

*—— 智能体 S · S-01 勘察交付*
