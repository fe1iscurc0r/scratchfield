# 可逆记忆 + Skill 依赖声明 SPEC v1

> 制定：实验田维护者（Hermes）｜施工：执行侧（Trae）
> 来源：论文《时空可组合性编程范式》× 系统工程四原则授粉（T1 两项）
> 日期：2026-08-15
> 原则：非侵入旁路——wrapper/事件监听器，零修改现有模块本体

---

## 背景（Layer 0）

论文核心机制：**可逆效应**（每次上下文变换带显式逆，运行时跟踪，可回滚）+ **响应式余效应**（组件声明依赖，变化时按规格通知：激活/去激活/中性）。

系统工程缺口映射：
- 记忆层缺 **P4 遗忘衰减** + **P1 图结构** → 模块 1（可逆记忆）堵前者
- skill 生态缺 **依赖管理** → 模块 2（coeffects 依赖声明）堵后者

---

## 模块 1：可逆记忆写入（ReversibleMemory）

### 功能（Layer 1）

包装 `summer_memory/GRAGMemoryManager`，每次写入记录逆操作到 undo 栈，支持撤销/回滚/定向遗忘。

**新文件**：`summer_memory/reversible.py`

```python
class ReversibleMemory:
    def __init__(self, backend: GRAGMemoryManager):
        self._backend = backend
        self._undo_stack: List[UndoOp] = []   # 逆累加器 φ

    # 包装写入方法：写入成功后 push 逆操作
    async def add_conversation_memory(self, user_input, ai_response) -> bool
    async def add_memory(self, user_input="", ai_response="", ...) -> ...

    # 撤销能力
    async def undo_last(self) -> bool          # 应用栈顶逆操作
    async def rollback(self, n: int) -> int    # 回滚 n 步，返回实际回滚数
    async def forget_entity(self, entity) -> int  # 定向遗忘某实体关联的全部记忆
```

**逆操作（UndoOp）定义**：写入时记录"写了什么"（五元组快照 + 实体/关系标识），逆操作 = 从后端删除这些条目。若后端无单条删除接口，逆操作降级为**标记删除**（写入 tombstone 集合，查询时过滤）。

### 技术限制（Layer 2）

1. **零侵入**：`GRAGMemoryManager` / `memory_client.py` 本体不得修改，ReversibleMemory 是纯 wrapper。
2. **undo 栈上限**：默认 50 步，超出丢最旧（防止无限膨胀，对应"遗忘是适应性"）。
3. **逆操作幂等**：重复 undo 已撤销条目不报错，返回 False。
4. **异步一致**：所有方法保持 async，与现有接口签名一致。
5. **降级路径**：后端删除接口缺失时走 tombstone 过滤，不能因为"没删除接口"就抛异常。

### 外部数据（Layer 3）

- 五元组结构见 `summer_memory/memory_manager.py` 的 `QuintupleType`
- 实体/关系查询走 `RemoteMemoryClient.query_by_entity` / `get_relationships`

### 验收

- 写入 3 条记忆 → `undo_last()` 后剩 2 条，再 `rollback(2)` 后剩 0 条
- `forget_entity("某实体")` 后，该实体关联记忆不可再查询到
- `GRAGMemoryManager` 本体 diff 为零

---

## 模块 2：Skill 依赖声明（coeffects）

### 功能（Layer 1）

给 `SKILL.md` frontmatter 增加可选 `coeffects:` 段，声明 skill 的依赖；加载时按规格解析，三分类通知。

**frontmatter 新增字段**：

```yaml
coeffects:
  skills:            # 依赖的其他 skill（按 name 匹配）
    - datamol
  packages:          # 依赖的 Python 包
    - rdkit
  services:          # 依赖的外部服务（声明式，不校验可达性）
    - neo4j
```

**新文件**：`skills/_coeffect_resolver.py`（解析器，独立可运行）

```python
def resolve_coeffects(skill_dir: str) -> CoeffectSpec:
    """读取 SKILL.md 的 coeffects 段，返回规格"""

def check_satisfied(spec: CoeffectSpec, installed: set[str]) -> CoeffectStatus:
    """按依赖是否满足，返回 activate/deactivate/neutral 三分类"""
```

三分类语义（对应论文）：
- **activate**：依赖全部满足 → skill 正常启用
- **deactivate**：硬依赖缺失（声明了 `required: true` 的 skills/packages 缺）→ 标记不可用，加载器跳过
- **neutral**：软依赖缺失（`required: false`）→ 启用但降级提示

### 技术限制（Layer 2）

1. **零侵入**：`coeffects:` 是可选段，不写该段的 skill 行为与现状完全一致。
2. **纯增量**：解析器是独立模块，不 hook 现有 skill 加载流程（旁路，先跑通再谈接入）。
3. **包检测**：`packages` 用 `importlib.util.find_spec` 检测，不实际 import（避免副作用）。
4. **不校验 services 可达性**：services 只声明、不 ping，避免启动慢和误报。

### 验收

- 一个声明 `packages: [rdkit]` 的 skill，在无 rdkit 环境返回 deactivate，有 rdkit 返回 activate
- 一个无 `coeffects:` 段的 skill，解析器返回 neutral（不影响）
- 解析器单测通过，`skills/` 现有 182 个 skill 零修改

---

## 元记录

- 论文依据：《A Programming Paradigm for Spatiotemporal Composability》第 3.1（可逆效应）/ 3.2（响应式余效应）
- 系统工程依据：`docs/System-Engineering-to-Agent-Workflow-Distillation.md` 四原则 P1/P3/P4
- 授粉评估：T1（落地难度 1 分 / 高收益），非侵入旁路
