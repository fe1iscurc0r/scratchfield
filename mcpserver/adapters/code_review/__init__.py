"""code-review-graph 适配包（审查专用代码知识图谱，授粉自 tirth8205/code-review-graph）。

上游 https://github.com/tirth8205/code-review-graph（MIT，见 UPSTREAM-LICENSE）。

与 graphify 分工（互补不重叠）：
- graphify = 通用知识图谱（代码/文献/PDF → GraphRAG 检索，EXTRACTED/INFERRED 置信边）
- code_review = 审查专用（git diff → 变更函数 → 风险分 + 测试缺口 + 影响半径）

设计：零新依赖薄引擎（stdlib ast，全确定性）——目标场景 apiserver/、summer_memory/
全为 Python；tree-sitter 多语言解析留作将来可选增强。默认关（ENABLE_ADAPTER_CODE_REVIEW）。

用法：
    from mcpserver.adapters.code_review.adapter import CodeReviewGraphBridge
    # 需先 ENABLE_ADAPTER_CODE_REVIEW=1，否则实例化 raise（门禁默认关）
"""
from mcpserver.adapters.code_review.adapter import (  # noqa: F401
    CodeReviewGraphBridge,
    is_enabled,
)
from mcpserver.adapters.code_review.engine import (  # noqa: F401
    CodeReviewError,
    GraphIndex,
    estimate_tokens,
)

__all__ = ["CodeReviewGraphBridge", "is_enabled", "CodeReviewError",
           "GraphIndex", "estimate_tokens"]
