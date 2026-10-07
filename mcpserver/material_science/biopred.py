"""生物质碳化预测器（靶子 B）— material_science agent 的 ML 扩展。

与现有 `property_calc` 区分：
- property_calc(calc_type="conductivity")：基于化学式查表/经验公式，单点值
- biopred_predict：基于实验参数（前驱体/KOH 比/碳化温度/保温时间）的 ML 预测，带置信区间
- biopred_suggest：基于已有数据，主动学习建议下一组最有信息量的参数

数据源：靶子 A 的 papers.db + 自己的实验记录（carbonization.db）。
方法：RandomForest / XGBoost（小样本友好），前端驱体指纹特征，不依赖 maml 的晶体结构假设。

降级策略：sklearn/xgboost 未装或数据不足时，返回可读的结构化说明，不崩溃。
"""
from __future__ import annotations

import logging
import math
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

#: 碳化实验库默认路径（卷192 黄档 Y4 处置：绝对化，不再随 CWD 漂移）。
#: 与 paper_miner 的 `_DEFAULT_DB` 同款口径：env 可覆盖，否则锚定仓库根。
_DEFAULT_CARBONIZATION_DB = os.environ.get(
    "CARBONIZATION_DB_PATH",
    str(Path(__file__).resolve().parents[2] / "carbonization.db"),
)

try:
    import numpy as np
    _HAS_NP = True
except Exception:
    _HAS_NP = False

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import train_test_split
    _HAS_SKLEARN = True
except Exception:
    _HAS_SKLEARN = False

try:
    import xgboost as xgb  # type: ignore
    _HAS_XGB = True
except Exception:
    _HAS_XGB = False


# 前驱体指纹：木质素类型/秸秆等 → 常量特征（真实项目中应从实验记录标定）
_PRECURSOR_FINGERPRINT: dict[str, float] = {
    "木质素": 1.0,
    "碱木质素": 1.1,
    "酶解木质素": 0.95,
    "稻草": 0.8,
    "秸秆": 0.82,
    "玉米芯": 0.85,
    "壳聚糖": 0.9,
    "纤维素": 0.75,
    "生物质": 0.8,
}
_DEFAULT_FP = 0.85

# 候选参数网格（主动学习搜索空间）
_GRID = {
    "koh_ratio": [1, 2, 3, 4, 5],
    "carbonization_temp": [600, 700, 800, 900],
    "holding_time": [60, 120, 180],
    "heating_rate": [2, 5, 10],
}


def _parse_description(desc: str) -> dict[str, Any]:
    """解析 '秸秆+KOH 800°C' / '{precursor:秸秆,koh_ratio:4,temp:800}' 等描述。"""
    desc = (desc or "").strip()
    parsed: dict[str, Any] = {}
    # 尝试 JSON 对象
    if desc.startswith("{"):
        try:
            import json
            data = json.loads(desc)
            for k in ("precursor", "koh_ratio", "carbonization_temp", "temp",
                      "holding_time", "heating_rate"):
                if k in data:
                    parsed[k] = data[k]
            parsed.setdefault("carbonization_temp", parsed.pop("temp", None))
            return parsed
        except Exception:
            pass
    # 启发式解析文本
    if "KOH" in desc or "koh" in desc:
        parsed["koh_ratio"] = 1.0  # 默认，后续可细化
    for key, pattern in (
        ("precursor", r"([\u4e00-\u9fa5]{2,6})"),
        ("carbonization_temp", r"(\d{3,4})\s*[°℃]"),
        ("koh_ratio", r"KOH\s*[:：=]\s*(\d+(?:\.\d+)?)"),
        ("holding_time", r"(\d+)\s*min"),
        ("heating_rate", r"(\d+(?:\.\d+)?)\s*[°℃]?/min"),
    ):
        m = re.search(pattern, desc)
        if m:
            val = m.group(1)
            parsed[key] = float(val) if key != "precursor" else val
    return parsed


def _precursor_fp(precursor: Any) -> float:
    if not precursor:
        return _DEFAULT_FP
    key = str(precursor)
    # 按键长度降序匹配，让更具体的标签（如"碱木质素"）优先于子串（如"木质素"）
    for name in sorted(_PRECURSOR_FINGERPRINT, key=len, reverse=True):
        if name in key:
            return _PRECURSOR_FINGERPRINT[name]
    return _DEFAULT_FP


def _load_dataset(db_path: str) -> list[dict[str, Any]]:
    """从 SQLite 加载碳化实验数据（兼容 papers.db 与 carbonization.db 的 experiments 表）。"""
    p = Path(db_path)
    if not p.is_file():
        return []
    rows: list[dict[str, Any]] = []
    conn = None
    try:
        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM experiments WHERE carbonization_temp IS NOT NULL "
            "AND conductivity IS NOT NULL"
        )
        rows = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.warning("[biopred] 数据集加载失败 %s: %s", db_path, e)
    finally:
        if conn is not None:
            conn.close()
    return rows


def _feature_vector(rec: dict[str, Any]) -> list[float]:
    """特征工程：前驱体指纹 + KOH 比 + 升温速率 + 碳化温度 + 保温时间。"""
    return [
        _precursor_fp(rec.get("precursor")),
        float(rec.get("koh_ratio") or 0),
        float(rec.get("heating_rate") or 0),
        float(rec.get("carbonization_temp") or 0),
        float(rec.get("holding_time") or 0),
    ]


def _train_model(rows: list[dict[str, Any]]):
    """训练 RandomForest/XGBoost，返回 (model, feature_importance, std)。"""
    if not _HAS_NP:
        raise RuntimeError("缺 numpy，无法训练模型")
    X = np.array([_feature_vector(r) for r in rows], dtype=float)
    y = np.array([float(r["conductivity"]) for r in rows], dtype=float)
    if len(X) < 5:
        raise RuntimeError(f"数据不足（{len(X)} 条 < 5），无法训练；请先积累文献提取+实验记录")
    model = None
    if _HAS_XGB:
        model = xgb.XGBRegressor(n_estimators=200, max_depth=4, random_state=42)
    elif _HAS_SKLEARN:
        model = RandomForestRegressor(n_estimators=300, random_state=42)
    else:
        raise RuntimeError("缺 scikit-learn/xgboost，无法训练模型")
    model.fit(X, y)
    import numpy as np_  # 局部别名避免遮蔽
    # 置信区间：用训练集残差 std 近似（小样本下不 holdout）
    preds = model.predict(X)
    resid_std = float(np_.std(y - preds)) if len(y) > 1 else 0.0
    importance: dict[str, float] = {}
    if hasattr(model, "feature_importances_"):
        names = ["precursor_fp", "koh_ratio", "heating_rate", "carbonization_temp", "holding_time"]
        importance = {n: float(v) for n, v in zip(names, model.feature_importances_)}
    return model, importance, resid_std


def predict(desc: str, *, db_path: str = _DEFAULT_CARBONIZATION_DB) -> dict[str, Any]:
    """预测给定参数组合的导电率 + 置信区间。"""
    parsed = _parse_description(desc)
    rows = _load_dataset(db_path)
    if not rows:
        return {
            "ok": False,
            "error": f"数据集 {db_path} 为空或缺失。请先运行靶子 A 提取文献参数或导入实验记录。",
            "parsed": parsed,
            "expected_output": {"ok": True, "prediction_s_cm": 12.3, "ci_lower": 8.0, "ci_upper": 17.0},
        }
    try:
        model, importance, resid_std = _train_model(rows)
    except RuntimeError as e:
        return {"ok": False, "error": str(e), "parsed": parsed, "dataset_rows": len(rows)}
    if not _HAS_NP:
        return {"ok": False, "error": "缺 numpy"}
    x = _feature_vector(parsed)
    pred = float(model.predict([x])[0])
    ci = 1.96 * max(resid_std, 0.01)
    return {
        "ok": True,
        "input": parsed,
        "prediction_s_cm": round(pred, 2),
        "ci_lower": round(max(pred - ci, 0.0), 2),
        "ci_upper": round(pred + ci, 2),
        "feature_importance": importance,
        "dataset_rows": len(rows),
        "model": "xgboost" if _HAS_XGB else ("random_forest" if _HAS_SKLEARN else "none"),
    }


def suggest(*, db_path: str = _DEFAULT_CARBONIZATION_DB, target: str = "conductivity") -> dict[str, Any]:
    """主动学习：在参数网格上建议下一组最有信息量的实验（不确定性最大化）。"""
    rows = _load_dataset(db_path)
    if len(rows) < 3:
        return {
            "ok": False,
            "error": f"数据不足（{len(rows)} 条 < 3），无法做主动学习建议；请先积累数据。",
            "suggested": _GRID,
        }
    if not _HAS_NP or not (_HAS_SKLEARN or _HAS_XGB):
        return {"ok": False, "error": "缺 numpy/scikit-learn/xgboost，无法做主动学习"}
    try:
        model, importance, resid_std = _train_model(rows)
    except RuntimeError as e:
        return {"ok": False, "error": str(e), "dataset_rows": len(rows)}
    import numpy as np_
    # 在网格上枚举候选，用预测方差/距离已采样最远点作为信息量打分
    candidates = []
    for kr in _GRID["koh_ratio"]:
        for temp in _GRID["carbonization_temp"]:
            for hold in _GRID["holding_time"]:
                for hr in _GRID["heating_rate"]:
                    rec = {"precursor": "生物质", "koh_ratio": kr, "heating_rate": hr,
                           "carbonization_temp": temp, "holding_time": hold}
                    x = _feature_vector(rec)
                    pred = float(model.predict([x])[0])
                    # 距离已有样本集最近邻距离（探索度）
                    X = np_.array([_feature_vector(r) for r in rows], dtype=float)
                    dist = float(np_.min(np_.sqrt(((X - np_.array(x)) ** 2).sum(axis=1))))
                    candidates.append((dist, pred, rec))
    candidates.sort(key=lambda t: t[0], reverse=True)
    top = [{"parameters": c[2], "prediction_s_cm": round(c[1], 2),
            "exploration_score": round(c[0], 2)} for c in candidates[:5]]
    return {"ok": True, "target": target, "note": "当前仅支持 conductivity 目标预测",
            "suggested": top, "grid_size": len(candidates), "dataset_rows": len(rows)}


def register_biopred_tools(agent) -> None:
    """往 MaterialScienceAgent 注入 biopred_predict / biopred_suggest 两个工具。"""
    def _tool_predict(params: dict[str, Any]) -> dict[str, Any]:
        desc = params.get("desc") or params.get("description") or params.get("query") or ""
        db_path = params.get("db_path") or _DEFAULT_CARBONIZATION_DB
        return predict(desc, db_path=db_path)

    def _tool_suggest(params: dict[str, Any]) -> dict[str, Any]:
        db_path = params.get("db_path") or _DEFAULT_CARBONIZATION_DB
        target = params.get("target", "conductivity")
        return suggest(db_path=db_path, target=target)

    agent.tools["biopred_predict"] = _tool_predict
    agent.tools["biopred_suggest"] = _tool_suggest
    logger.info("[MCP] biopred_predict + biopred_suggest 已注入 material_science agent")