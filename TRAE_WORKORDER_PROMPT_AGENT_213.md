# 工单 213 · 材料科研线盘点 + 本科实验数据快通道

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-08
> 背景：用户生物质能源与材料专业，邵长优惠组（木质素NPs→水凝胶/共熔凝胶→水下电子/太阳能蒸发）。工单206任务三（小数据回归模板）已在跑，本单做材料线整体快通道规划。

## 任务一（P0）：材料线现有工具盘点

1. 扫 `~/scratchpad/mcpserver/material_science/` 和 `docs/material-pollination/`、`docs/material*`：
   - 每件工具/报告出一行：`工具名 | 做什么 | 数据格式 | 依赖 | 可否邵长组实验数据直用`
2. 重点标注 matchat_bridge（MatChat浏览器自动化）：是否可绕过登录/反爬限制；biopred（生物预测）的模型精度账
3. 报告落 `docs/material-science-toolkit-2026-10.md`

## 任务二（P1）：本科实验数据快通道搭设

邵长优惠组可能用到的数据流：
- 木质素纳米粒子：粒径(DLS)/PDI/zeta电位 → 分散稳定性预测
- 水凝胶：溶胀率/力学性能(压缩模量) → 性能-配方回归
- 共熔凝胶：相变温度/热容 → 热力学模拟

1. 在 `research/material/` 下建 `research/material/bachelor-lab/`：
   - `data_schema.md`：上述每类数据的字段定义（实验员填表格式，非代码）
   - `quick_import.py`：CSV 入库脚本（读 CSV → 写 SQLite/JSONL，带数据校验）
   - `回归预测工作流.md`：输入实验数据 → LOO回归（复用工单206的小数据模板）→ 输出预测结果，本科生可照单操作
2. 脚本对标工单206任务三已产出的 `loo_regression_template.py`，两者共用水电：`research/material/lignin-np-regression/`

## 验收
- [ ] 任务一：material-science-toolkit 盘点含所有工具（matchat/biopred/历次授粉报告）可利用度标注
- [ ] 任务二：bachelor-lab/ 三件套落盘（data_schema/quick_import.py/回归工作流md）；quick_import.py 用合成数据实跑通过
- [ ] 全程 CI 绿（lint/smoke 若闸门未开则本地等价复现，参照 ci.yml 注释的两步法）
