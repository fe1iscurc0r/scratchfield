# SPEC-19 · pymatviz 材料可视化组件 · 授粉落地总纲 · v1

> 状态：待施工（2026-08-26 授粉流水线 round7 候选，扫货日报 8-26 推荐，用户拍板开线）
> 用途：把 janosh/pymatviz（MIT，⭐329，材料信息学可视化）授粉成科研可视化独立组件——周期表热图/结构图/凸包能量图，输出 PNG/HTML 供 ELN 与实验报告用
> 读者：Trae（施工）/ 沈遥（评审）/ 陆墨（使用）
> 依据：SPEC-17/18 架构裁决（独立组件+总线，陆墨是陆墨）；SPEC-Writing-Standard-v2；github_haul/POLLINATION-2026-08-26-round7.md
> 依赖事实：pymatviz v0.8+（plotly 系，ptable 热图支持多值 split 2/3/4 色块；结构/轨迹 widgets 基于 anywidget+MatterViz）；凸包/能量图在 pymatviz 的 convex_hull.py / energy.py；重依赖 pymatgen 仅结构/相图数据需要

---

## 〇、一句话定位

**pymatviz 授粉成 `viz_pymatviz` 独立组件：纯 Python API + CLI，把材料数据变成可落盘的科研图表（周期表热图/结构图/凸包能量图/空间群分布），不塞 lumo 壳、不引 LLM，图表文件进 ELN 当附件。**

## 一、背景与边界（P3 边界，做/不做对照）

| 做（纳入本件） | 不做（显式排除） |
|---|---|
| 周期表热图（单值热图 + 多值 split 对比） | matterviz 全套交互可视化（费米面/能带/DOS/布里渊区——工程量与依赖远超授粉收益） |
| ptable 直方图/散点/线图（元素性质分布） | lumo 前端集成（本组件只出声文件；前端集成留给 V/W 线需要时另行 SPEC） |
| 结构 3D 可视化（pymatgen Structure → Plotly HTML/PNG，含内置样张 NaCl） | 材料 ML 预测绘图（W 线材料模型管线的活，不抢） |
| 凸包能量图/能量图（合成相图数据 + pymatgen PhaseDiagram） | 语音/实时/交互式 Notebook 服务（不部署 Jupyter 服务） |
| 空间群分布图 + 组分分布 | 任何 LLM 调用（这是纯计算组件） |
| CLI 封装（`viz-pymatviz <cmd>`）+ tests ≥10 + README | 去重绘制 TGA/DSC/XRD 原始曲线（那是 SPEC-18 E 模块的活，本组件只补"元素/结构/相图"视角） |

**层次选择**：在"Python 库 + CLI"抽象层施工（不上 Web 服务、不碰 lumo 前端），上移一层的代价 = 需要 IPC/总线，下移一层 = 失去复用性。本层最稳。

## 二、架构设计（P2 层次 / P1 关系）

```
数据（合成/真实 CSV/用户输入）
   │ CLI: viz-pymatviz <cmd> --input --out
   ▼
viz_pymatviz 组件（独立目录，不塞 lumo 壳）
   ├─ core/  ptable_hmap.py   (周期表热图, split 支持)
   ├─ core/  structure_viz.py (结构3D, pymatgen→Plotly)
   ├─ core/  hull_energy.py   (凸包/能量图)
   ├─ core/  spacegroup.py    (空间群/组分分布)
   ├─ cli.py  (入口, argparse)
   └─ registry.py (cmd 注册表, 复用 rf_brain registry 风格)
   │
   ▼
输出：PNG/HTML 文件 → ELN 附件 / 实验报告插图
```

- **依赖关系**：pymatviz（plotly 系）为硬依赖；pymatgen 为可选（结构/凸包功能才需要，见 fallback）
- **换件测试**：把 pymatviz 换成 matplotlib 手绘？撤——授粉目的就是用成熟库，不用考虑换件，但 core 接口留薄封装层（输出 PNG 路径统一返回），将来升级库不倒 API

## 三、施工步骤

1. 建目录 `research/viz/`（天选7 陆墨工作区；云端可同构开发），`pip install pymatviz`（+ 可选 `pymatgen`）
2. 搭包骨架：`research/viz/viz_pymatviz/{__init__.py, cli.py, registry.py, core/}`；README 写用法（陆墨可直接抄）
3. Z-01 周期表热图：`ptable_hmap.py`——`ptable_heatmap(values: dict[元素, 数值])` + `hist`/`scatter` 变体；合成数据出图
4. Z-02 结构可视化：`structure_viz.py`——`structure_3d(structure | json)`，内置 NaCl 样张（不依赖外部文件）；输出 HTML（可交互）+ PNG（静态）
5. Z-03 凸包能量图：`hull_energy.py`——输入 {组成, 能量} 列表 → pymatgen PhaseDiagram 凸包图（pymatgen 缺失时降级：纯散点能量图，标注"非凸包"）
6. Z-04 空间群分布 + CLI 集成：`spacegroup.py`（空间群/元素频次分布图）+ `cli.py` 统一 `--out` 输出目录
7. tests ≥10：每个 cmd 输出文件存在且非空、PNG 魔数（\x89PNG）校验、坏输入（空 dict/None/非法元素）降级不崩溃、registry 可见
8. README + 验收自检（下方验收命令逐条跑）

## 四、关键假设与 fallback（P1 关系，表格）

| 假设 | 若不成立 |
|---|---|
| 云端可 pip install pymatviz（含依赖） | 记录失败原因回填本 SPEC，改真机（天选7）安装 |
| pymatgen 可安装 | 结构/凸包两功能降级：结构用 pymatviz 内置样张 only；凸包降级散点能量图并显式标注"非凸包"（禁止伪造凸包线） |
| 合成数据即可验收 | 若需真实数据验收，天选7 用 ELN 里真实元素分布出一张周期表热图（真机验证点） |
| 无网络也能跑 | CLI `--demo` 模式内置合成数据，离线可验证组件自检 |

## 五、已知限制（诚实标注）

1. 相图/费米面/能带全套交互（matterviz 旗舰功能）不在本件——依赖体积与施工量 10 倍于授粉收益，纳入会造成"授粉变重开发"，超出"轻量授粉"边界
2. 周期表热图只支持元素级数值映射，不支持任意物相/配合物作为格子单位（pymatviz 上游限制）
3. 结构可视化依赖 pymatgen 数据格式；无 pymatgen 时仅样张可玩（fallback 已述）
4. 全部输出为静态文件，不做实时流式渲染（数据工具台 E 模块的 matplotlib 管线继续管实时曲线）

## 六、测试用例（纯 Python 优先，云端 python -c 可验）

1. `test_ptable_hmap`：合成 {Li:1.0, Fe:2.0, O:3.0} → PNG 存在且魔数 \x89PNG
2. `test_ptable_split`：多值输入（dict[元素, list[float]]）→ split 模式出图不报错
3. `test_ptable_bad_input`：空 dict → 清晰报错不崩溃；含非法元素符号 → 警告+忽略
4. `test_structure_naCl`：内置样张 → HTML 与 PNG 均产出
5. `test_structure_bad`：坏 JSON → 降级报错；无 pymatgen → 仅样张可用（显式提示）
6. `test_hull_demo`：合成 3 相数据 → 凸包图（或降级散点图）文件产出
7. `test_hull_nopygen`：pymatgen 缺失 → 降级路径输出且标题标注"非凸包"
8. `test_spacegroup`：合成 {Fm-3m:5, P21/c:3} → 分布图产出
9. `test_cli_all`：`viz-pymatviz --demo --out tmp` 一键跑通全部 cmd
10. `test_registry`：registry 里 4 个 cmd 全注册

## 七、交付物清单

- `research/viz/viz_pymatviz/` 包（core 4 模块 + cli + registry）
- `research/viz/tests/` ≥10 用例
- `research/viz/README.md`（安装/用法/真机验证点）
- 合成数据输出样张 PNG（至少周期表热图一张）

## 八、验收标准（可执行不变量，逐条跑）

```bash
# 1. 依赖到位
pip list | grep -i pymatviz          # 非空
python -c "import pymatviz; print(pymatviz.__version__)"  # 成功打印版本
# 2. 测试全绿
cd research/viz && pytest            # ≥10 通过
# 3. 真用了 pymatviz 不是空壳
grep -rn "ptable_heatmap\|pymatviz" viz_pymatviz/ | head   # 非空
# 4. 无 LLM 调用（纯计算铁律）
grep -rn "openai\|anthropic\|ollama\|requests.post" viz_pymatviz/  # 空
# 5. 输出可落盘
python -m viz_pymatviz --demo --out /tmp/vizdemo && file /tmp/vizdemo/*.png | grep PNG  # 有 PNG
# 6. registry 完整
grep -n "ptable_hmap\|structure_3d\|hull_energy\|spacegroup" viz_pymatviz/registry.py  # 4 cmd 全在
```

**真机验证点（天选7，用户实测）**：用 ELN/实验里真实元素分布数据跑 `viz-pymatviz ptable-hmap` 出一张图并入实验报告。

## 九、提交规范

- 分项 commit 前缀：`feat(viz-pymatviz):`（Z-01~Z-04 各一）+ `docs(viz):`（README）
- 成果推 `trae/agent-z` 分支
- MIT 授粉纪律：包内保留 pymatviz LICENSE 声明（THIRD_PARTY_NOTICES.md 一行注释亦可）

## 十、工单划分

单线 Z 工单（Z-01~Z-04 顺序做，量约几百行，一个智能体一轮完成）：完整任务在 `TRAE_WORKORDER_PROMPT_AGENT_Z.md`。