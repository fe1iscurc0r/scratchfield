# MODEL_INTERFACE: WaveBench

- 上游仓库: 本地镜像（中转库 academic/WaveBench）；插件仓
  https://github.com/Scaxlibur/wavebench-instrument-plugins
- 许可证: MIT（README 声明；引用须保留，见 ../LICENSES.md）
- 安装: `pip install -e .`（Python ≥ 3.11，建议独立环境）
- 模块名/CLI: `wavebench`

## 算法定位

实验室自动测量台（Python）：把信号源、示波器、电源、万用表编排成可复现的
实验流程（run plan），先离线校验（plan/check）再连硬件（verify/plan 执行），
全程保留命令记录与采集证据链，可生成离线 HTML 测试报告。

## 核心 API / CLI

```bash
# 离线路径（不连仪器、不开输出）
wavebench run template --list
wavebench run template source-scope-sine --output plans/demo.toml --force
wavebench run check --plan plans/demo.toml
wavebench run report data/runs/<run-dir>     # 生成 HTML 报告
wavebench run compare / run resume           # 多 run 离线比较 / 补测清单

# 上机路径（确认接线与安全限值后）
wavebench run verify --config wavebench.toml --plan plans/demo.toml
wavebench run plan  --config wavebench.toml --plan plans/demo.toml
```

内建设备: R&S RTM2000/RTM2032、RIGOL DS1104Z/DS1000Z（示波器）、
DG4000/DG4202（信号源）、DP800（电源）、DM3000/DM3058（万用表）。

## 数据格式

- 输入: TOML plan 文件（步骤编排）+ wavebench.toml（仪器 resource 配置）
- 输出: 采集包（CSV/NPY）+ run.json 元数据 + 命令记录 + HTML 报告
- 频响: 幅频/相频曲线，二维扫频（Vpp×频率）可生成校准 LUT

## 安全边界

不发 *RST、不自动开输出、不改输入阻抗；仪器配置支持
read_write / read_only / disabled 三档；HTTP MCP 工具只读且需认证。

## Lumo 工作台用途

- 材料电学表征（电阻率/阻抗扫频）的测量流程模板化
- 与 duckdb 工作台衔接：采集的 CSV 直接进分析管线

## 引用

WaveBench（Scaxlibur），MIT License。
