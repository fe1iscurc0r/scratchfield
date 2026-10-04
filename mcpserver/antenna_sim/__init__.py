"""天线仿真管线（卷122）—— 模型生成 / 执行 / 结果分析 / 档案。

模块划分：
- `model_generator`：按类型+频率+尺寸生成 OpenEMS 模型（CSX XML + Python 脚本），参数校验
- `sim_runner`：任务编排（本机 OpenEMS / Kali 桥 / 本地 MoM），状态机与结果拉回（W122-02）
- `result_analyzer`：S11/方向图/增益提取 + 理论对照 + summary.json 归档（W122-03）
- `local_mom`：本地薄线矩量法求解器（无 OpenEMS 也能出真数字）

许可边界：OpenEMS/CSXCAD 为 GPL-3.0 独立工具链，仅以「外部进程 + 文件」交互，本模块不引其源码。
"""

from .model_generator import gen_model, sweep_params  # noqa: F401

__all__ = ["gen_model", "sweep_params"]
