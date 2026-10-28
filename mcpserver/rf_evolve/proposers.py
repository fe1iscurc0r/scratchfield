"""候选提案器（工单246 · 对应 SeisEvo 的 "LLM-driven multi-agent search"）。

本单**刻意**把默认路径做成**确定性规则**、把 LLM 做成**可选旁路**。理由是工程性的：

- 演化框架的价值在**门与打分**（约束能不能挡、执行能不能量化），不在"提案的是不是 LLM"；
- 本仓的 CI / 离线环境**不保证**有 LLM key。若把 LLM 做成必由之路，
  这个模块在没 key 的机器上就**无法被验证** —— 那就成了一个只能演示不能回归的东西。

因此：

| 提案器 | 何时用 | 是否可离线复现 |
|---|---|---|
| `RulesProposer` | **默认** | ✅ 固定 seed ⇒ 逐位可复现 |
| `LLMProposer`   | 显式启用且环境有 key | ❌（但有 key 时才出现，且降级**不静默**） |

LLM 通路复用本仓既有的 `mcpserver/llm_gateway/anthropic_compat.py`（工单228 的兼容层），
可用性判定与 242 的 `prompt_to_script.llm_refine_spec` 同口径：**不可用 ⇒ 返回 None + 明确 reason**。
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field

from .candidate import Candidate
from .editspace import EditSpace


@dataclass
class ProposeResult:
    """一次提案的结果（含"为什么没提到"的说明）。"""

    candidates: list[Candidate] = field(default_factory=list)
    mode: str = "rules"
    note: str = ""


class RulesProposer:
    """确定性提案器：**第一遍铺满离散网格，之后在最优附近做邻域扰动**。

    与"随机搜索"的区别：网格保证**编辑面被系统性覆盖**（SeisEvo 也是从经典算法出发
    做有结构的改动，而不是乱撒）；扰动则把预算集中在有希望的区域。
    """

    def __init__(self, space: EditSpace, *, seed: int = 20261016) -> None:
        self.space = space
        self.rng = random.Random(seed)
        self._grid_i = 0
        self._seeded = False
        # ⚠️ 网格**按 seed 打乱**再走：`itertools.product` 是字典序，最后一个参数变化最快，
        #    于是前几批会全落在**第一个参数的最低档**上 —— 实测那恰好是个灾难值
        #    （prominence=8 ⇒ 检出上百噪声峰 ⇒ 全被约束门否掉），小预算下搜索**覆盖不到**
        #    有希望的区域。打乱后仍是确定性的（同 seed 同顺序），但早期批次更分散。
        self._grid = list(space.grid())
        self.rng.shuffle(self._grid)

    def propose(self, *, generation: int, best: Candidate | None = None,
                n: int = 6) -> ProposeResult:
        if best is None or best.score is None:
            # ⚠️ 统一走游标：**首次调用也要推进 `_grid_i`** —— 早先给"第一次"单开了一个
            #    用 `_grid[:n]` 的分支却没推进游标，于是第二次调用会**重复第一批**
            #    （实测踩过：白丢一批提案预算）。
            start = self._grid_i
            rest = self._grid[start:start + n]
            self._grid_i += len(rest)
            first = (start == 0)
            note = (f"第一遍：离散网格前 {len(rest)} 点（共 {len(self._grid)} 点，顺序按 seed 打乱）"
                    if first else f"继续铺网格（已铺 {self._grid_i}/{len(self._grid)}）")
            if not rest:
                note = f"网格已铺完（{len(self._grid)} 点）—— 后续应转为邻域扰动"
            return ProposeResult(
                [Candidate(params=q, provenance="rules", label=f"grid[{start + i}]",
                           generation=generation) for i, q in enumerate(rest)],
                mode="rules", note=note)

        out: list[Candidate] = []
        for i in range(n):
            child = dict(best.params)
            p = self.rng.choice(self.space.params)
            if p.choices:
                pool = [c for c in p.choices if c != child[p.name]]
                if not pool:
                    continue
                child[p.name] = self.rng.choice(pool)
            elif p.kind == "bool":
                # ⚠️ 布尔参数不能走数值分支：`float(False) = 0.0`，而 `0.0 == False` 为真
                #    ⇒ 会被误判成「没改动」（实测踩过）。直接取反。
                child[p.name] = not bool(child[p.name])
            else:
                lo = p.low if p.low is not None else float(child[p.name])
                hi = p.high if p.high is not None else float(child[p.name]) * 2
                child[p.name] = round(self.rng.uniform(lo, hi), 4)
            label = f"perturb({p.name}={child[p.name]!r})"
            out.append(Candidate(params=child, provenance="rules", label=label,
                                 generation=generation))
        return ProposeResult(out, mode="rules", note=f"以 {best.label} 为父代做邻域扰动")


class LLMProposer:
    """可选的 LLM 提案器（**非默认**）。不可用时明确说明原因，绝不静默降级。"""

    def __init__(self, space: EditSpace, *, model: str = "") -> None:
        self.space = space
        self.model = model

    def available(self) -> tuple[bool, str]:
        """探测 LLM 通路是否可用（复用仓内 anthropic 兼容层）。"""
        try:
            from mcpserver.llm_gateway import anthropic_compat as compat  # type: ignore
        except Exception as exc:                      # noqa: BLE001
            return False, f"llm_gateway.anthropic_compat 不可导入：{type(exc).__name__}"
        try:
            client = compat.get_client()
        except Exception as exc:                      # noqa: BLE001
            return False, f"get_client 失败：{type(exc).__name__}: {exc}"
        if client is None:
            return False, "get_client 返回 None（未配置凭据）"
        return True, "ok"

    def propose(self, *, generation: int, best: Candidate | None = None,
                n: int = 4) -> ProposeResult:  # pragma: no cover - 需要真 key 才走到
        ok, reason = self.available()
        if not ok:
            return ProposeResult([], mode="llm", note=f"LLM 不可用，已降级为不提案：{reason}")
        from mcpserver.llm_gateway import anthropic_compat as compat  # type: ignore

        prompt = _build_prompt(self.space, best, n)
        try:
            client = compat.get_client()
            msg = compat.messages_create(client, model=self.model or "claude-sonnet-4-5",
                                         max_tokens=1200, system=_SYSTEM, prompt=prompt)
            text = compat.extract_text(msg)
            rows = json.loads(_strip_code_fence(text))
        except Exception as exc:                      # noqa: BLE001
            return ProposeResult([], mode="llm", note=f"LLM 提案失败，降级：{type(exc).__name__}: {exc}")
        out: list[Candidate] = []
        for i, row in enumerate(rows[:n]):
            try:
                params = self.space.canonical(row if isinstance(row, dict) else dict(row))
            except Exception:                          # noqa: BLE001
                continue                               # LLM 给的越界值直接丢（门在下面还有一道）
            out.append(Candidate(params=params, provenance="llm", label=f"llm[{i}]",
                                 generation=generation))
        return ProposeResult(out, mode="llm", note=f"LLM 返回 {len(rows)} 条，合法 {len(out)} 条")


_SYSTEM = ("你是射频信号处理算法工程师。只输出 JSON 数组，不要解释文字。"
           "每个元素是一组候选参数，键必须与给定可编辑面完全一致，值必须在给定取值域内。")


def _build_prompt(space: EditSpace, best: Candidate | None, n: int) -> str:
    lines = ["可编辑面（只允许改这些参数）：", json.dumps(space.describe(), ensure_ascii=False)]
    if best is not None and best.score is not None:
        lines += ["", f"当前最优：{json.dumps(best.params, ensure_ascii=False)}",
                  f"其执行读数（dB，S/N 提升）：{json.dumps(best.score, ensure_ascii=False)}"]
    lines += ["", f"请给出 {n} 组不同的候选参数（JSON 数组）。"]
    return "\n".join(lines)


def _strip_code_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def make_proposer(space: EditSpace, mode: str = "rules", **kw):
    """工厂：``mode="rules"``（默认）或 ``"llm"``。未知 mode 直接报错（不静默退回）。"""
    import inspect

    cls = {"rules": RulesProposer, "llm": LLMProposer}.get(mode)
    if cls is None:
        raise ValueError(f"未知提案器模式 {mode!r}（可用：rules / llm）")
    accepted = set(inspect.signature(cls.__init__).parameters) - {"self", "space"}
    unknown = sorted(set(kw) - accepted)
    if unknown:                     # 不静默丢弃：给错参数就是错，要报出来
        raise ValueError(f"{cls.__name__} 不接受参数 {unknown}（可用：{sorted(accepted)}）")
    return cls(space, **kw)
