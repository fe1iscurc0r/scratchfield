# A09 Agent 记忆投毒防护（写时筛查 + 来源分级 + Provenance Ranking）

> 任务：A09 Agent 记忆投毒防护
> 来源：8-25 轮授粉点 1 · 核心论文 2608.21230《Utility Under Attack: Agent Memory Poisoning and the Limits of Content Screening and Provenance Ranking》+ 2608.21159《AID-Guard》
> 场景：weixin / qqbot / cli 共享工作树（NEKO 记忆融合 + 工单流水线）
> 日期：2026-08-30

---

## 一、问题陈述

持久记忆让假信息**持久化**：一条假陈述一旦存入，之后所有匹配会话都会检索到它。在 weixin / qqbot / cli **共享同一个工作树/记忆库**的场景下，任何一个低信任入口写进来的假内容，都会污染后续所有入口的会话——"一条假事实污染后续会话"。

论文 2608.21230 给出了最致命的实证：

- 攻击者**只需一次生成、平实无害的假断言**——不需要指令注入、不需要触发器、不需要检索优化，就是一句看起来合理但错误的陈述；
- 污染 LongMemEval 语料**仅 1.2%**，就把准确率从 **0.850 → 0.300**（1.2% 的投毒造成 55pp 的准确率崩塌，放大效应极大）。

论文标题直指 A09 工单的两个手段：**Content Screening（写时筛查）和 Provenance Ranking（来源分级排序）的极限**——即这两个手段是必要的，但**单独不足以防御**，因为它们都挡不住"一句平实假断言"。

## 二、来源论文核心结论

### 2608.21230 · Utility Under Attack
1. **持久记忆 = 攻击面**：假陈述存进去就持久，未来匹配会话持续检索到。
2. **攻击极廉价**：单次生成的平实假断言，无需指令/触发器/检索优化。
3. **放大效应**：1.2% 投毒 → 准确率 0.850→0.300。
4. **两个手段的极限**：写时筛查挡不住"非指令型平实假事实"（它不触发注入特征）；provenance ranking 可被伪造来源或"低信任但内容可信"的假陈述绕过。

### 2608.21159 · AID-Guard（配套）
- 授权常止于 **admission**，但 provider 的 **state / delivery / retry / recovery** 持续演化——需要**状态化授权到 effect 的闭环**。
- 与 A09 同批配套：写时校验 + **授权跟到副作用发生**，防止"准入通过后、副作用阶段被投毒"。

## 三、防护设计（三层 + 两个极限补丁）

### 层 1：写时筛查（Content Screening）
- 拦截**改写性指令**（"忽略之前规则 / 之后必须 / 你现在的身份是"）。
- 拦截**事实冲突**（与已有记忆矛盾时不静默覆盖，标记冲突排队仲裁）。
- **承认极限**：写时筛查对"平实假断言"无效（它不是指令、不触发注入特征），因此必须叠加层 2/3 之外的补丁（见 3.4/3.5）。

### 层 2：来源分级（Source Grading）
| 来源 | 分级 | 写入权限 |
|---|---|---|
| cli（本地受信终端） | 高 | 可写高权重记忆 |
| weixin / qqbot（外部群聊） | 低 | 默认只读 / 低权重，不得覆盖高信任源 |
| 工具返回 / 文件导入 | 中 | 视工具可信度 |

### 层 3：Provenance Ranking（来源溯源排序）
每条记忆强制携带 `{来源, 时间, 置信度, 校验状态}`，检索/推理按 provenance 排序，冲突按 provenance 裁决，支持溯源审计与回滚。

### 层 3.4（极限补丁 1）：事实交叉校验
针对"平实假断言"——写时筛查和 provenance 都拦不住它，需要**对可信语料库做事实一致性校验**：新写入的断言与受信知识库/已确认事实交叉比对，矛盾则降级为"待验证"或拒绝固化。

### 层 3.5（极限补丁 2）：Utility-Under-Attack 监测
针对"1.2% 投毒 → 55pp 崩塌"的放大效应——**持续监测记忆库的"效用信号"**（下游任务准确率/检索命中质量）。一旦检测到准确率的异常骤降（投毒放大特征），触发：
- 记忆基线回滚；
- 定位近期写入的低信任条目并隔离。

### 层 4（配套）：状态化授权（AID-Guard）
授权跟到**副作用发生**：写入记忆的授权不止于准入，还要覆盖该记忆被检索、被用于决策、被回写等后续 effect 的每个环节（state/delivery/retry/recovery 闭环）。

## 四、防护模块骨架

```python
@dataclass
class MemoryEntry:
    content: str
    source: str            # "cli" | "weixin" | "qqbot" | "tool:<name>"
    confidence: float
    verified: bool
    timestamp: float

SOURCE_TRUST = {"cli": 0.9, "tool": 0.6, "weixin": 0.2, "qqbot": 0.2}

def write_gate(entry, existing, trusted_kb):
    # 层1 写时筛查：拦指令注入 + 高信任冲突
    if looks_like_injection(entry.content):
        return "reject:injection"
    for e in existing:
        if conflicts(e, entry) and SOURCE_TRUST[entry.source] < SOURCE_TRUST[e.source]:
            return "reject:lower_trust_conflict"
    # 3.4 极限补丁：事实交叉校验（拦"平实假断言"）
    if contradicts_kb(entry.content, trusted_kb):
        entry.verified = False
        entry.confidence *= 0.3              # 降级为待验证，不固化
    if not entry.verified:
        entry.confidence *= 0.5
    return "accept"

def monitor_utility(history, threshold=0.2):
    # 3.5 极限补丁：效用监测，检测投毒放大特征（准确率骤降）
    recent = utility(history[-WINDOW:])
    if recent < utility(history[:-WINDOW]) * (1 - threshold):
        return "trigger:rollback_and_isolate"   # 回滚 + 隔离近期低信任写入
    return "ok"
```

## 五、投毒注入测试

| 注入向量 | 攻击内容 | 预期拦截 |
|---|---|---|
| qqbot 群消息 | "以后你的系统提示改为……" | 层1 reject:injection |
| weixin 低信任源 | 覆盖 cli 写入的配置 | 层1 reject:lower_trust_conflict |
| **平实假断言**（论文主攻击） | 无指令、无触发、看似合理的假事实 | **层3.4 交叉校验降级 + 层3.5 效用监测**（单靠筛查/ranking 会漏） |
| 伪造来源 | 低信任源伪装高可信 | 层2 来源分级 + 层3 provenance |
| 副作用阶段投毒 | 准入通过后篡改 | 层4 AID-Guard 状态化授权 |

**验收判据**：覆盖上述向量；尤其要对论文的"平实假断言"给出拦截/降级路径（不能只依赖写时筛查和 provenance，要证明 3.4/3.5 补丁生效）。

## 六、验收对照

| 验收项 | 交付 |
|---|---|
| 写时筛查 / 来源分级 / provenance ranking | §三 层 1–3 |
| 正视两手段极限（论文核心） | §二 + §三 3.4/3.5 补丁 |
| 防护模块 | §四 `write_gate` / `monitor_utility` 骨架 |
| 投毒注入测试 | §五（含平实假断言 + 副作用阶段） |
| 配套 AID-Guard | §三 层 4 |
| 文档 | `docs/agent-memory-poisoning-defense-2026-08-30.md` |
