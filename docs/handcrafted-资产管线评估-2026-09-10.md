# handcrafted 资产管线评估（W100-03）

> 2026-09-10 · 评估 + 轻落地 · 蒸馏依据：docs/handcrafted-system-skeleton-distill-2026-09-10.md 第 1 节
> （InstallManifest / AssetCatalog / 双快照原子发布）· 上游无 LICENSE，仅蒸馏不融合（代码原创）

## 一、上游设计要点（蒸馏）

- InstallManifest：模型/资产的声明式清单（版本、校验、来源）。
- AssetCatalog：资产目录（按档位/类型组织，可查可切）。
- 双快照原子发布：不可变快照 + 一次性重建，发布不撕裂。

## 二、与本仓现状对照（模型管理）

| 维度 | 上游（handcrafted） | 本仓现状 | 差异 |
|------|--------------------|---------|------|
| 清单机制 | InstallManifest | ❌ 无统一 manifest | 缺口 |
| 校验 | sha256 | ❌ 分散（各模块自理） | 缺口 |
| 档位/切换 | AssetCatalog 按档位 | 部分（config 切换模型名） | 部分 |
| 下载 | 断点下载 | 无统一下载器 | 缺口 |
| 原子发布 | 双快照 | ❌ 无 | 后置 |

## 三、可执行落地建议（≥3）

1. **统一 asset manifest（已轻落地）**：`tools/lumo/asset_manifest.py`——JSON manifest
   + sha256 校验 + 缺失/损坏检测（6 测试全绿），作为模型资产的声明式基线。
2. **档位接入**：把 manifest 的 `tier` 字段与现有「模型档位切换」配置对齐，切换即校验
   （工作量 0.5 天，后续工单）。
3. **断点下载器**：manifest 的 url 字段已预留；下载器（断点 + 校验合一）工作量 1 天，
   建议并入「云服/NEKO 模型同步」工单。
4. **双快照原子发布 Python 等价**：immutable snapshot + 一次性重建（swap 指针/目录 rename），
   只写进评估（不强制实现）。

## 四、结论

manifest 机制为真缺口，本批已落最小集（清单+校验+缺失检测）；档位对齐与断点下载
列为后续；双快照原子发布作 Python 侧实现指引归档本报告。

---
*评估：fe1iscurc0r · 2026-09-10 · 设计参考 handcrafted-persona-engine（无 LICENSE，原创实现）*
