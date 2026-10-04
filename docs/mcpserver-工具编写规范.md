# mcpserver 工具编写规范

> 工单 04-02 产物。惯例源自 **ChemMCP**（OSU-NLP-Group，Apache-2.0，本机 clone
> `github_haul/ChemMCP/`）的模块化工具 schema 与 **fastmcp** 的自动 schema 机制，
> 结合本仓 `mcpserver/` 既有注册门禁（`adapters/_common.py` + `adapters/__init__.py`）
> 制定。目的：**加一个工具 = 写一个 Python 文件**，接口签名统一、文档/manifest 自动生成、
> 降级行为可预期。

---

## 1. 两种工具形态

| 形态 | 位置 | 适用 | 注册路径 |
|------|------|------|----------|
| **adapter 型**（首选） | `mcpserver/adapters/<name>.py` 单文件 | 封装一个外部项目/服务的一组小工具 | `_ADAPTERS` 表 + `register_all_adapters()` 门禁 |
| **agent 目录型** | `mcpserver/<name>/` 目录 | 有独立状态/配置/多文件的较大能力包 | `<name>/agent-manifest.json` + `entryPoint` |

判断标准：能写进一个文件、无独立状态的，用 adapter 型；需要数据目录、独立进程
（sidecar）或复杂配置的，用 agent 目录型。

## 2. 加工具 = 写一个 Python 文件（adapter 型五步）

1. 新建 `mcpserver/adapters/<name>.py`，实现三要素：
   - `CAPABILITY: dict` —— 能力卡（见 §5），六必需字段
   - `healthcheck() -> bool` —— 纳入门禁探针
   - `register(mcp_server, mcp_registry=None)` —— 挂工具 + 登记能力卡
2. 在 `adapters/__init__.py` 的 `_ADAPTERS` 表加一行
   `"<name>": ("mcpserver.adapters.<name>", "ENABLE_ADAPTER_<NAME大写>")`
3. Python 面：每个工具写一个 `*_impl` 同步函数（可直接 import，数据处理不用起 server）
4. MCP 面：每个工具写一个 async 包装（类型注解 + Google 风格 docstring），`mcp_server.add_tool(fn, name=...)` 挂载
5. 写 `mcpserver/tests/test_<name>_adapter.py`（坏输入 + 降级 + 注册契约必测）

门禁会自动做：ENABLE 开关检查 → import → `validate_adapter()` 契约校验 →
CAPABILITY.name 冲突检测 → healthcheck → register（失败回滚半挂载工具）。
**维护者不需要写任何注册循环代码。**

## 3. 统一接口签名

### 3.1 MCP 面（agent 走这条路径）

```python
async def <adapter>_<tool>(arg: str, limit: int = 5) -> dict[str, Any]:
    """一句话功能描述（fastmcp 据此生成工具 description）。

    Args:
        arg: 参数说明（fastmcp 据签名+本节生成 JSON Schema）
        limit: 返回条数，默认 5

    Returns:
        {"ok": True, ...}；失败 → {"ok": False, "error": 原因}（永不抛错）
    """
    return <tool>_impl(arg, limit)
```

- **类型注解必写**：fastmcp 从函数签名自动生成输入 schema（ChemMCP 的
  `code_input_sig` 手写签名在本仓被「签名即 schema」取代，等价且免双写）
- **docstring 必写 Args/Returns**：这就是 ChemMCP `get_doc()` 自动文档的本仓等价物
  ——ChemMCP 把元数据渲染进 `wrapper.__doc__` 再由 fastmcp 读走；本仓直接把
  文档写在函数上，同一机制、少一层元数据类
- 工具名一律 `<adapter>_<tool>` 前缀，防跨 adapter 撞名

### 3.2 Python 面（数据处理直接 import）

```python
from mcpserver.adapters.chemmcp import smiles2formula_impl
result = smiles2formula_impl("CCO")   # {"ok": True, "formula": "C2H6O", ...}
```

`*_impl` 必须是同步纯函数式封装（不依赖事件循环），MCP 包装只是薄转发。

## 4. 统一输入输出契约（含降级铁律）

成功：`{"ok": True, "tool"/"source": "<名>", ...业务字段}`
失败：`{"ok": False, "tool"/"source": "<名>", "error": "人读原因"}`

1. **MCP 工具面一律不抛错**（照 context7 惯例）：网络失败、依赖缺失、坏输入都降级为
   `ok=False`。工具挂了只是这个能力不可用，不该打断 agent 主流程。
2. **依赖缺失给安装提示**：error 里写 `"<pkg> 未安装：pip install <pkg> 后可用"`。
3. **healthcheck 恒 True 是合法选择**：若依赖缺失时仍想让工具「存在但返回安装提示」，
   healthcheck 返回 True、在调用期降级（context7/chemmcp 模式）；只有凭证类
   fail-fast（如 OPENAI_API_KEY）才在 healthcheck 返回 False 让门禁整卡跳过。
4. **库内部可以抛**：`*_impl` 之下、不跨边界的内部错误照常抛；跨 MCP/跨进程边界
   必须接住转成 `ok=False`。agent 目录型历史上有抛 ValueError 流派（chembl /
   scikit_fingerprints），新工具不要再加，老工具迁移时统一。
5. 返回形状字段名统一 `ok`：**不用** `"status": "error"`（memory_maas 历史形状），
   迁移时兼容读取、新代码一律 `ok`。

## 5. CAPABILITY 能力卡（自动 manifest 文档）

六必需字段（`_common.py::_REQUIRED_CAPABILITY_KEYS` 校验，缺一跳过注册）：

```python
CAPABILITY: dict = {
    "name": "chemmcp",                    # 必须与 _ADAPTERS 注册名一致（门禁强校验）
    "displayName": "ChemMCP SMILES 纯转换工具",
    "description": "一句话能力描述",
    "version": "0.1.0",                   # semver
    "license": "Apache-2.0",              # 上游许可，供应链审计入口
    "vendor": "OSU-NLP-Group/ChemMCP",    # 上游坐标
    "_from_adapter": "chemmcp",           # 能力卡归属（与注册名一致）
    # 可选：degradation_mode / security_notice / deployment_mode ...
}
```

`register()` 里调 `register_capability_safe(mcp_registry, dict(CAPABILITY))` 后，
能力卡自动进 `_ADAPTER_CAPABILITIES` 全局登记表，冲突自动告警——这就是本仓的
「manifest 文档自动生成」：**能力元数据写在代码里，登记/冲突检测/调度路由全自动**。

agent 目录型的 `agent-manifest.json` 对应关系（源自 ChemMCP ToolMeta 的启示）：

| agent-manifest.json 字段 | ChemMCP ToolMeta 对应 | 要求 |
|---|---|---|
| name / displayName / version | name / __version__ | 与 CAPABILITY 同名同版 |
| description | description + implementation_description | 一句话说清「做什么+怎么实现」 |
| license | oss_dependencies 的 license | **必填**，供应链铁律 |
| entryPoint | —（ChemMCP 无此项） | module+class 指向真实可 import 的类 |
| capabilities.invocationCommands[].params | code_input_sig | 与函数签名一致 |
| capabilities.invocationCommands[].example | examples | **键必须与 params 一致**（ChemMCP 用 pydantic validator 强校验，本仓以测试保证：manifest 测试断言 example 键 ⊆ params 键） |

## 6. 供应链与许可声明

1. 吞外部代码前先查 license（Apache-2.0/MIT 可吞；GPL/AGPL 只可隔离调用不可复制源码）
2. 上游声明保留：adapter 模块 docstring 写明 `上游: <repo>（<license>）` + 逐文件来源
3. `CAPABILITY.license` 填上游许可；复用了上游哪些文件在 docstring 逐条列出
   （参照 `adapters/chemmcp.py` 头部）
4. 与上游的实现差异**诚实标注**在 docstring（如 chemmcp 规范化弃 rdchiral 改标准
   RDKit 的说明），不做静默改动

## 7. 现有 adapter 对照表（合规审计）

✅=合规 ❌=不合规 ⚠️=可接受但建议改进（`—` 表示该形态不适用）

| 规范条目 | context7（adapter 型） | memory_maas（agent 型） | chembl（agent 型） | chem_adapter（库适配） | chemmcp（adapter 型，本规范示范） |
|---|---|---|---|---|---|
| CAPABILITY 六必需字段 | ✅ | ❌ 无（agent 型不走 adapters 门禁） | ❌ 无 | ❌ 无（未注册） | ✅ |
| healthcheck/register 三要素 | ✅ | ⚠️ 仅 manifest entryPoint | ⚠️ 仅 manifest entryPoint | ❌ 无 | ✅ |
| MCP 面永不抛错（§4.1） | ✅ 空结果降级 | ⚠️ `{"status":"error"}` 形状 | ❌ 参数非法抛 ValueError | — | ✅ ok=False 降级 |
| 依赖缺失给安装提示（§4.2） | — （零依赖） | — | ✅ AcademicDependencyError 带 pip 提示 | ⚠️ 缺 casregnum 时裸 ImportError | ✅ error 含 pip install rdkit |
| 统一 ok 字段（§4.5） | ✅ | ❌ status 字段（历史） | ✅ ok+source | — | ✅ |
| 工具名 adapter 前缀（§3.1） | ✅ context7_query_docs | ✅ memory_* | ✅ chembl_* | — | ✅ chemmcp_* |
| 上游许可声明（§6） | ✅ docstring 标 MIT | ✅ manifest 标 AGPL-3.0 | ✅ 标 Apache-2.0 | ✅ 原样复制零修改声明 | ✅ Apache-2.0 逐文件来源 |
| 自动 schema（签名+docstring，§3.1） | ✅ | ❌ 手写 manifest params | ❌ 手写 manifest params | — | ✅ |
| 参数-示例一致性校验（§5） | ⚠️ 无 manifest 测试 | ⚠️ example 手写无校验 | ⚠️ example 手写无校验 | — | ✅ 测试断言（§5 建议做法） |

（另有 vulnclaw/memclaw/headroom/markitdown/llm4decompile/paper_miner/agent_reach 等
adapter 均为三要素齐全的早期形态，未逐个列入；上表取代表性样本。）

## 8. ChemMCP schema 惯例：采纳与不采纳

| ChemMCP 惯例 | 决定 | 理由 |
|---|---|---|
| 类属性元数据 + pydantic 强校验（ToolMeta） | ⚠️ 不整体采纳 | 本仓「签名即 schema」已消除双写；元数据由 CAPABILITY 承担 |
| 双输入签名 code_input_sig / text_input_sig | ❌ 不采纳 | 本仓无纯文本交互面，单签名够用 |
| examples 键与签名强一致（validator 报错） | ✅ 采纳为测试要求 | 示例漂移是文档腐烂主因 |
| oss_dependencies / services_and_software 声明字段 | ✅ 精神采纳 | 落在 docstring 来源声明 + CAPABILITY.license/vendor（§6） |
| wrapper.__doc__ 注入 → fastmcp 自动 schema | ✅ 等价采纳 | 直接把文档写在 async 包装上，同一机制 |
| _run_base 共享实现 + 双暴露面 | ✅ 采纳 | 即本规范 `*_impl` + async 包装双模式 |
