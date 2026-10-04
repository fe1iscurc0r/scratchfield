"""BO 寻优旁路测试（H-02 验收，≥6 用例）。

覆盖：参数空间校验 / 代理模型拟合 / 采集函数推荐 / 回填更新 / 失败实验纳入 / CLI 集成，
外加 多目标标量化 / 历史数据迁移(warm-start) / 编码解码往返。
以合成数据验收，真实实验数据留真机。
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mcpserver.material_science.bo_optim import acquisition as acq  # noqa: E402
from mcpserver.material_science.bo_optim import cli  # noqa: E402
from mcpserver.material_science.bo_optim import loop as loop_mod  # noqa: E402
from mcpserver.material_science.bo_optim.params import (  # noqa: E402
    ParameterSpace,
    lignin_hydrothermal_space,
)
from mcpserver.material_science.bo_optim.surrogate import (  # noqa: E402
    GaussianProcessSurrogate,
    RandomForestSurrogate,
    make_surrogate,
)

VALID_POINT = {
    "T": 180.0, "t": 12.0, "C": 5.0, "R": 3.0,
    "S": "纯水", "pH": "中性", "L": "碱木质素",
}
GOOD_METRICS = {"yield": 0.31, "pdi": 0.26, "size_nm": 210.0}


class _DummySurrogate:
    """固定 mu/sigma 的假代理，用于确定性测试采集函数。"""

    def __init__(self, mu, sigma):
        self._mu = np.asarray(mu, dtype=float)
        self._sigma = np.asarray(sigma, dtype=float)

    def predict_with_uncertainty(self, X):
        return self._mu, self._sigma


# ---- 1. 参数空间校验 ----
def test_parameter_space_validation():
    space = lignin_hydrothermal_space()
    assert space.dim == 4 + (2 + 3 + 3)  # 4 连续 + one-hot(2+3+3)
    # 合法点通过
    space.validate(VALID_POINT)
    # 连续越界
    bad = dict(VALID_POINT, T=230.0)
    try:
        space.validate(bad)
        raise AssertionError("应抛出越界错误")
    except ValueError:
        pass
    # 约束违反（C ≤ 18，假设约束）
    bad_c = dict(VALID_POINT, C=19.0)
    try:
        space.validate(bad_c)
        raise AssertionError("应抛出约束违反错误")
    except ValueError:
        pass
    # 离散非法取值
    bad_s = dict(VALID_POINT, S="丙酮")
    try:
        space.validate(bad_s)
        raise AssertionError("应抛出离散非法取值错误")
    except ValueError:
        pass


def test_parameter_space_encode_decode_roundtrip():
    space = lignin_hydrothermal_space()
    vec = space.encode(VALID_POINT)
    assert vec.shape == (space.dim,)
    decoded = space.decode(vec)
    # 连续参数近似还原
    for name in space.continuous_names:
        assert abs(decoded[name] - VALID_POINT[name]) < 1e-6
    # 离散参数精确还原
    for name in space.categorical_names:
        assert decoded[name] == VALID_POINT[name]


# ---- 2. 代理模型拟合 ----
def test_surrogate_fit_and_uncertainty():
    X = np.linspace(0, 1, 20).reshape(-1, 1)
    y = np.sin(X.ravel())
    rf = make_surrogate("rf", n_estimators=30)
    rf.fit(X, y)
    mu, sigma = rf.predict_with_uncertainty(X[:5])
    assert mu.shape == (5,)
    assert (sigma >= 0).all()
    # 拟合后能大致还原趋势（合成数据，只验单调/有界）
    assert np.all(np.abs(mu) <= 1.0 + 0.5)

    gp = make_surrogate("gp")
    gp.fit(X, y)
    mu_gp, sigma_gp = gp.predict_with_uncertainty(X[:5])
    assert mu_gp.shape == (5,)
    assert (sigma_gp >= 0).all()


# ---- 3. 采集函数推荐 ----
def test_acquisition_recommend_selects_best():
    mu = np.array([0.1, 0.9, 0.5])
    sigma = np.array([0.1, 0.1, 0.1])
    dummy = _DummySurrogate(mu, sigma)
    X = np.arange(3).reshape(-1, 1)
    # EI 固定 sigma 下应选 mu 最大者（下标 1）
    idx, scores = acq.recommend(dummy, X, "ei", y_best=0.0)
    assert idx == 1
    # UCB 固定 sigma 下同样选 mu 最大者
    idx_ucb, _ = acq.recommend(dummy, X, "ucb", kappa=0.0)
    assert idx_ucb == 1
    # 随机策略返回合法下标
    idx_rnd, _ = acq.recommend(dummy, X, "random")
    assert 0 <= idx_rnd < 3


def test_expected_improvement_monotonic_in_mu():
    mu = np.array([0.0, 0.5, 1.0])
    sigma = np.array([0.2, 0.2, 0.2])
    ei = acq.expected_improvement(mu, sigma, y_best=0.0)
    assert ei[0] < ei[1] < ei[2]


# ---- 4. 回填更新 ----
def test_record_and_update_loop():
    space = lignin_hydrothermal_space()
    loop = loop_mod.BOLoop(space, n_candidates=64)
    loop.init(n=4)
    # 回填 3 个成功实验 + 1 个直接目标
    for i in range(3):
        loop.record(VALID_POINT, GOOD_METRICS)
    loop.record(VALID_POINT, objective=0.9)
    loop.update()
    assert loop.n_observations() == 4
    assert loop.surrogate_is_ready()
    assert loop.y_best() is not None
    # 更新后能推荐出合法配方
    recs = loop.recommend_batch(k=2)
    assert len(recs) == 2
    for r in recs:
        space.validate(r)


# ---- 5. 失败实验纳入 ----
def test_failed_experiment_included():
    space = lignin_hydrothermal_space()
    loop = loop_mod.BOLoop(space, n_candidates=64)
    loop.init(n=3)
    loop.record(VALID_POINT, GOOD_METRICS)
    loop.record(VALID_POINT, GOOD_METRICS)
    # 记录一个失败实验（无指标）
    loop.record(dict(VALID_POINT), failed=True)
    assert loop.failed[-1] is True
    assert loop.y[-1] == loop_mod.FAILED_OBJECTIVE
    assert loop.metrics[-1] is None
    # 失败点也进训练集，代理仍可拟合
    loop.update()
    assert loop.n_observations() == 3
    assert loop.surrogate_is_ready()
    recs = loop.recommend(k=1)
    assert len(recs) == 1
    space.validate(recs[0])


def test_failed_neighborhood_penalty_reduces_score():
    # 失败邻域惩罚应压低采集分数（映射 1）
    mu = np.array([0.5, 0.5])
    sigma = np.array([0.1, 0.1])
    dummy = _DummySurrogate(mu, sigma)
    X = np.array([[0.0], [1.0]])
    failed = np.array([[0.01]])  # 紧邻候选 0
    idx_no_pen, _ = acq.recommend(dummy, X, "ucb", kappa=0.0, failed_points=failed, failure_penalty=0.0)
    idx_pen, scores_pen = acq.recommend(dummy, X, "ucb", kappa=0.0, failed_points=failed, failure_penalty=10.0)
    assert scores_pen[0] < scores_pen[1]
    # 惩罚后不再必然选 0（0 紧邻失败点被压低）
    assert idx_no_pen != idx_pen or scores_pen[0] < scores_pen[1]


# ---- 6. CLI 集成 ----
def test_cli_integration_flow():
    with tempfile.TemporaryDirectory() as td:
        state = str(Path(td) / "bo.json")
        csv_out = str(Path(td) / "next_batch.csv")

        # init
        assert cli.main(["init", "--n", "4", "--state", state]) == 0
        s = json.loads(Path(state).read_text(encoding="utf-8"))
        assert len(s["pending"]) == 4

        # recommend（数据不足 → 随机，仍返回合法配方）
        assert cli.main(["recommend", "--state", state, "--n", "2", "--out", csv_out]) == 0
        assert Path(csv_out).exists()
        with open(csv_out, encoding="utf-8") as f:
            header = f.readline().strip()
        assert "T" in header and "S" in header

        # record 成功实验
        rc = cli.main([
            "record", "--state", state,
            "--recipe", json.dumps(VALID_POINT),
            "--metrics", json.dumps(GOOD_METRICS),
        ])
        assert rc == 0
        s = json.loads(Path(state).read_text(encoding="utf-8"))
        assert len(s["points"]) == 1 and s["failed"] == [False]

        # record 失败实验
        rc = cli.main([
            "record", "--state", state,
            "--recipe", json.dumps(VALID_POINT),
            "--failed",
        ])
        assert rc == 0
        s = json.loads(Path(state).read_text(encoding="utf-8"))
        assert len(s["points"]) == 2 and s["failed"] == [False, True]

        # 非法配方应被拒绝
        rc_bad = cli.main([
            "record", "--state", state,
            "--recipe", json.dumps(dict(VALID_POINT, T=999.0)),
            "--metrics", json.dumps(GOOD_METRICS),
        ])
        assert rc_bad == 2 or rc_bad != 0


# ---- 7. 多目标标量化 ----
def test_scalarize_multi_objective():
    objectives = loop_mod.lignin_objectives()
    good = loop_mod.scalarize(GOOD_METRICS, objectives)
    bad = loop_mod.scalarize({"yield": 0.05, "pdi": 0.9, "size_nm": 900.0}, objectives)
    assert good > bad
    # 缺测指标不参与、不崩溃
    partial = loop_mod.scalarize({"yield": 0.3}, objectives)
    assert isinstance(partial, float)


# ---- 8. 历史数据迁移（warm-start）----
def test_warm_start_historical_records():
    space = lignin_hydrothermal_space()
    loop = loop_mod.BOLoop(space, n_candidates=64)
    hist = [
        {"recipe": VALID_POINT, "metrics": GOOD_METRICS},
        {"recipe": VALID_POINT, "metrics": {"yield": 0.22, "pdi": 0.5, "size_nm": 150.0}},
    ]
    loop.init(n=2, warm_start=hist)
    # warm-start 直接进训练集，pending 只有新采的 2 个
    assert loop.n_observations() == 2
    assert len(loop.pending) == 2
    assert loop.surrogate_is_ready()
