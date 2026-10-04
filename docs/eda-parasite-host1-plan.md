# JLC-EDA 寄生控制链第一宿主计划（W66-06）

> 来源 docs/JLC-EDA-寄生控制链-SPEC-v1.md §4.1

## 复刻目标选型依据

- **选型**：AntiHunter DIGI 节点（物料最贴近，双通道可复用）。
- 理由：屏幕控制通道 + 软件接入（API）通道共用一个指挥层，AntiHunter 的硬件形态
  与该双通道架构最匹配。

## 双通道指挥层架构

```
             EDACommander（统一指挥层）
            /                        \
  屏幕控制通道                  软件接入(API)通道
  （寄生/OCR/点击）             （EasyEDA Pro eda.* 类型化操作）
```

## 类型化操作目录

`place_symbol / route_track / export_gerber / drf_check`（骨架，API 不可用则 mock 降级）。

## 实现

`tools/eda_parasite.py`：`EDACommander`（双通道指挥层 + 类型化操作封装）+ `replica_target_plan`。
