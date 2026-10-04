"""materials_model — 生物质材料 ML 预测管线（W-01 / SPEC-16 靶子 B）。

碳化条件（温度/时间/升温速率）× 原料特性 → 产物性质（产率/比表面积/热值）。

子模块：
- data:       ELN 导出 → 特征矩阵/标签（缺失处理 + 坏数据降级）
- train:      随机森林 + BP 基线训练（R²/MAE/RMSE 报告，sklearn 缺失时降级）
- predict:    CLI 推理接口（结构化预测 + 不确定区间）
- writeback:  预测结果按 V-01 ELN 格式回写（标注「模型预测待验证」）
- sample_data: 样例数据生成/加载（明确标注「样例数据」，非真实实验）
- suggest:    Ollama 辅助「实验建议」（可选，调用失败降级）

定位：跑材料 ML 预测，不是 LLM 聊天；Ollama 只做数据解读/建议辅助，可选。
"""
from __future__ import annotations

__all__ = [
    "data",
    "train",
    "predict",
    "writeback",
    "sample_data",
    "suggest",
]

__version__ = "0.1.0"
