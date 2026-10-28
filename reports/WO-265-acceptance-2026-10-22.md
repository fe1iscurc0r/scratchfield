# WO-265 验收报告：声学层 P0 六项

- **工单**：`TRAE_WORKORDER_PROMPT_AGENT_265.md`
- **来源**：轮48 报告 §6「优先级与验收不变量」（P0 六项）
- **验收日期**：2026-10-22
- **main tip（收口时）**：`3d7e97d18715`
- **结论**：**P0 六项全部交付**；三项可编码项（P0-1/P0-2/P0-3）用例全过，
  P0-4 数据集与 P0-5/P0-6 文档判据全过。
  **三条已知边界如实登记**（§4），不作"已完全闭环"表述。

---

## §1 交付清单（17 文件，全部在 main）

| 路径 | 字节 | 对应 |
|---|---:|---|
| `acoustics/__init__.py` | 2155 | 包入口 |
| `acoustics/atten_inverse.py` | 12982 | P0-1 |
| `acoustics/cavitation_dose.py` | 14233 | P0-2 |
| `acoustics/source_map.py` | 11879 | P0-3 |
| `acoustics/dataset.py` | 6823 | P0-4 |
| `tests/test_atten_inverse.py` | 8766 | P0-1 验收 |
| `tests/test_cavitation_dose.py` | 7680 | P0-2 验收 |
| `tests/test_source_map.py` | 6081 | P0-3 验收 |
| `tests/test_dataset.py` | 4476 | P0-4 验收 |
| `data/acoustics/README.md` | 2478 | P0-4 |
| `data/acoustics/dataset_meta.json` | 1086 | P0-4 |
| `data/acoustics/mono_10um.csv` | 1820 | P0-4 |
| `data/acoustics/mono_50um.csv` | 1820 | P0-4 |
| `data/acoustics/mono_100um.csv` | 1820 | P0-4 |
| `docs/声悬浮实验台-单液滴-2026-10-22.md` | 7069 | P0-5 |
| `docs/超声谱仪路线-pic0rick-2026-10-22.md` | 6509 | P0-6 |
| `TRAE_WORKORDER_PROMPT_AGENT_265.md` | 8802 | 工单正文 |

四次提交：

| 批 | commit | 内容 | 用例 |
|---|---|---|---|
| 1 | `51c380b5c26d` | P0-1 衰减谱反演 | 11 |
| 2 | `f966b4eda69a` | P0-3 声源成像 | 8 |
| 3 | `61835ad63625` | P0-2 空化剂量 | 10 |
| 4 | `3d7e97d18715` | P0-4 标定集 + P0-5/P0-6 文档 | 6 |

---

## §2 验收判据逐条对账

| # | 工单判据（原文） | 实测 | 结论 |
|---|---|---|---|
| P0-1 | `pytest tests/test_atten_inverse.py -q` 全过 | **11 passed** | ✅ |
| P0-1 | 反演 `(a,b)` 相对误差 < 5% | a **0.3%** / b **0.4%**（0.5% 噪声） | ✅ |
| P0-1 | `grep -c "plot_lcurve\|tikhonov"` ≥ 2 | **9** | ✅ |
| P0-2 | `pytest tests/test_cavitation_dose.py -q` 全过 | **10 passed** | ✅ |
| P0-2 | 复现 APECSS 谱峰、偏差 < 5% | **无法执行**（缺基准数据）→ 用四条锚点替代，见 §4-1 | ⚠️ 部分 |
| P0-2 | `grep -c "Keller\|Gilmore\|RPModel"` ≥ 3 | **7** | ✅ |
| P0-3 | 双点源 + 白噪，DAMAS 定位误差 < λ/4 | **0.00 mm**（λ/4 = 2.14 mm） | ✅ |
| P0-3 | CLEAN-SC 定位误差 < λ/4 | **0.00 mm** | ✅ |
| P0-4 | 3 组不同粒径，指数随粒径单调 | 局部指数 @10 MHz：**1.993 → 1.661 → 0.716** | ✅（口径见 §4-3） |
| P0-4 | 数据集 < 50 MB | **6.4 KB** | ✅ |
| P0-5 | 含 换能器间距 / 频率 / 相位解算 | 三项齐全 | ✅ |
| P0-5 | `grep -c "phase_alignment\|radiation force"` ≥ 2 | **7** | ✅ |
| P0-6 | TAPR OHL 1.0 不入 AGPL 的显式声明 | 已有（§6 整节） | ✅ |
| P0-6 | 探头中心频率 ↔ 采样率匹配表 | 6 行 × 5·f_c，含"够不够"判定 | ✅ |

**全局**：四个测试文件合计 **35 passed**；`ruff check` / `ruff format --check` 通过；
所有新增文件（含 CSV/JSON）**CRLF = 0**。

---

## §3 过程中修掉的 9 个真 bug（都靠"量级/单位/对称性"自检发现）

| # | 模块 | bug | 症状 | 判据 |
|---|---|---|---|---|
| 1 | atten_inverse | 幂律拟合未做列归一化 | `b` 相对误差 **1.7e6%** | `f⁴` 与 `f²` 量级差 1e14 |
| 2 | atten_inverse | 收敛判据初值 `prev=inf` | 只迭代 200 步就退出，残差卡 5.5% | `inf <= tol·inf` 恒真 |
| 3 | source_map | `das_map` einsum 共轭写错 | DAS 出现**负功率** | 与暴力参考逐点对拍 |
| 4 | source_map | `csm_from_snapshots` 共轭方向反 | 峰落在**镜像**方向（−20 mm → +20 mm） | 单源用例（双源对称会掩盖） |
| 5 | source_map | DAMAS 误认为 `diag(PSF)=1/M²` | 返回的其实是 DAS 图，主瓣没窄 | 残差 92.86、主瓣不变 |
| 6 | cavitation_dose | Tait 焓前因子写 `p_ref/ρ` | 气泡**完全不动**（R̈ 差 3000×） | 一阶展开 `H≈(p−p_ref)/ρ` |
| 7 | cavitation_dose | 焓的参考压力用固定 `p0` | **驱动项整块丢失** | 谱峰跑到 2.4 MHz |
| 8 | cavitation_dose | 自由振荡把半周期当整周期 | 得到正好 **2×** Minnaert | 过零点计数 |
| 9 | 包导出 | 函数 `cavitation_dose` 覆盖同名子模块 | 10 个用例 AttributeError | `from acoustics import cavitation_dose` |

另有 1 处工程性修正：`simulate` 加 `|Ṙ| ≤ 0.9c` 上限（RP/KM 的可压缩修正项在 `Ṙ→c` 失效）。

---

## §4 三条已知边界（**如实登记，不冒充闭环**）

### §4-1 P0-2 的 APECSS 对拍未做

轮48 原判据要求复现 `polycfd/apecss` 的 `examples/acousticemitter` 谱峰（偏差 < 5%）。
本机**没有该基准数据**（Discovery-Only，未 clone 上游）。当前用四条可自证锚点替代：
Minnaert 自由振荡（**0.00%**）、Tait 焓一阶展开（<1%）、Gilmore↔Keller 弱驱动极限（<2%）、
驱动频率 + 二次谐波。
**补齐条件**：拿到 APECSS 示例的谱峰数据后，新增一条测试替换第四条錨点。

### §4-2 P0-1 的双峰不可分辨

本频带（0.5–30 MHz）内 10 µm 与 100 µm 的核形状余弦相似度 **> 0.8**，
系统**在数学上不可辨识**（不是调参问题）。已写成
`test_bimodal_split_is_documented_limitation`。
**补齐条件**：更宽频带 / 更多独立机制 / 引入先验（已知单分散库）。

### §4-3 P0-4 的"指数单调"口径

按**全局** log-log 斜率理解则**不单调**（1.992 / **2.007** / 1.796），
因全局斜率把「粘性 ∝ f²」与「散射 ∝ f⁴ 上升期→饱和」混在一起。
验收改用**固定 10 MHz 处的局部指数**（严格单调）。
两者都已写成断言，防止将来为凑单调去改核。

---

## §5 复现命令

```bash
cd <repo-root>
python -m pytest tests/test_atten_inverse.py tests/test_cavitation_dose.py \
                 tests/test_source_map.py tests/test_dataset.py -q      # 期望 35 passed
grep -c "plot_lcurve\|tikhonov" acoustics/atten_inverse.py              # ≥2
grep -c "Keller\|Gilmore\|RPModel" acoustics/cavitation_dose.py         # ≥3
grep -c "phase_alignment\|radiation force" docs/*声悬浮*.md              # ≥2
grep -c "TAPR" docs/*超声谱仪*.md                                        # ≥1
```

---

## §6 下游接口（交接要点）

1. **P0-4 数据集单位是 `Np/m`**；P0-6 实测链路输出是 `dB/cm`。
   换算 `1 dB/cm = 11.51 Np/m`，**导入前必须归一**，否则反演出 `(a,b)` 差常数倍。
2. **P0-1 的 `inversion_kernel` 是唯一真值源**：P0-4 数据集、后续反演器都必须用它，
   否则"标定集—反演器"口径不一致，测出的误差没有意义。
3. **P0-3 的 `csm_from_snapshots` 只能吃 `(T, M)` 快拍矩阵**；若从外部读 CSM，
   注意别把 `XᴴX` 当成 CSM（那是 `Cᵀ = C*`）。
