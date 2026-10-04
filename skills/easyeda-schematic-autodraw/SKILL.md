---
name: easyeda-schematic-autodraw
description: 通过 easyeda-agent daemon 的 typed action 将网表自动绘制成 EasyEDA Pro 原理图。自动处理器件库解析、器件放置、网络连接、断点续画和连接器降级恢复，适用于需要通过代码批量生成原理图的场景。
allowed-tools: Read Write Edit Bash
license: MIT license
metadata:
  version: "1.0"
  skill-author: K-Dense Inc.
---

# easyeda-schematic-autodraw

## Overview

把结构化的原理图网表（器件清单 + 每个器件的 pin→net 映射）自动绘制到 EasyEDA Pro 的原理图页面中。整个过程使用 `easyeda-agent` 的 typed action：`lib search` 解析器件、`sch place` 放置、`sch autoconnect` 批量连线。脚本具备幂等性和断点续画能力，当 EasyEDA 连接器降级时可以暂停、恢复后继续，无需从头开始。

## When to Use This Skill

在以下场景触发：

- 用户要求“把这份网表/器件表画成原理图”。
- 用户需要批量将 BOM + 接线定义转换为 EasyEDA Pro 可编辑的原理图。
- 用户已有 `docs/SPEC-*` 或类似文件，包含器件 C 编号、坐标、引脚网络。
- 用户遇到 `debug exec` 超时/连接器降级，希望改用更稳定的 typed-action 方案。

不要用于：
- 手动编辑单个小器件（直接 GUI 更快）。
- 连接器完全不可用（需先按 L-02 恢复）。
- 器件库中不存在对应 C 编号或型号歧义严重的场景。

## Workflow

### 0. 前置检查

- `easyeda health` 必须返回 `status: found` 且目标窗口已连接。
- 项目已在 EasyEDA Pro 中打开；若未打开，先用 `debug exec` 调用 `eda.dmt_Project.openProject(uuid)` 和 `eda.dmt_EditorControl.openDocument(pageUuid)`。

### 1. 准备网表

在脚本中定义 `COMPONENTS` 列表，每项包含：

```python
{
  "designator": "J1",
  "sid": "C9900001620",
  "x": 800, "y": 1200,
  "pins": {"A4": "VBUS", "A1": "GND", ...}
}
```

坐标单位为 EasyEDA 原理图单位（10mil）。

### 2. 解析器件库身份

对每个唯一的 `sid` 调用：

```bash
easyeda lib search --query <C编号> --limit 1 --project <项目名>
```

提取 `libraryUuid` 和 `uuid`。离线查询，不会打开库浏览器。

### 3. 放置器件

对每个器件调用：

```bash
easyeda sch place \
  --lib <libraryUuid> \
  --uuid <uuid> \
  --x <x> --y <y> \
  --designator <位号> \
  --project <项目名>
```

一次只放一个器件。位号通过 `--designator` 原子设置，避免后续 `modify` 触发降级（L-04）。

### 4. 批量连接网络

生成 JSON 规格文件：

```json
{
  "connections": [
    {"pin": "J1:A4*", "kind": "power", "net": "VBUS"},
    {"pin": "J1:A1*", "kind": "gnd", "net": "GND"}
  ]
}
```

调用：

```bash
easyeda sch autoconnect --spec <spec.json> --project <项目名> --json
```

- `*` 后缀用于连接同名重复引脚（如 USB-C 的 A4/B4 各两个）。
- `kind` 取值为 `gnd` / `power` / `netport` 等。
- `sch autoconnect` 是幂等的：已连到目标网络的引脚会自动跳过。

### 5. 降低连接器负载

- 每个器件之间 sleep 2 秒左右。
- 如果 `sch place` 失败且错误提示 `connector did not respond`，停止并等待 20–60 秒，再轻量读取状态（L-02）。

### 6. 断点续画

脚本启动时：

1. 用 `sch list` 读取当前图页所有 `designator`。
2. 对已存在的位号跳过 `sch place`，只执行 `sch autoconnect`（幂等）。
3. 对因位号分配失败留下的未命名器件，按 primitiveId 删除后重放。

用户只需反复运行 `python draw_schematic.py --current --no-clear` 即可在连接器恢复后继续。

### 7. 验证与保存

- 用 `sch read --project <项目名>` 读取完整网表，检查关键网络是否包含预期引脚。
- 用 `debug exec` 调用 `eda.sch_Document.save()` 保存文档。

---

## Configuration

- 环境变量/工具：`easyeda` CLI（版本与 daemon 建议一致或更新），EasyEDA Pro 已开启外部交互开关。
- 推荐参数：
  - `chunk_size = 1`（一次一个器件）
  - 器件间 sleep `2.0` 秒
  - autoconnect 超时 `60` 秒
  - 连接器降级时等待 `20–60` 秒再重试

---

## Output

- 放置并连接好的 EasyEDA Pro 原理图页面。
- 标准错误输出每个器件的放置/连线进度，便于观察连接器状态。
- `sch read` 结果，可用于自动化验证网络完整性。
