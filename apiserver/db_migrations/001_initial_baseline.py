"""001_initial_baseline — 基线（版本 1）。

**只登记版本号，不执行任何 DDL。**

为什么基线不带 DDL：勘察（卷192-A）实测本仓**没有任何删库重建**，表结构由各模块自己用
`CREATE TABLE IF NOT EXISTS` 建立（21 个连接点里 17 个文件为 IF NOT EXISTS 风格）。
因此基线若重复建表只会制造"两处 schema 定义"的漂移源。基线的价值是**版本锚点**：
让未来每一次结构变更都有个可追溯的起点（002、003…）。

注：本文件刻意只定义**纯数据**（dict 列表），不 import runner——
避免"数据文件与执行器互相导入"造成的加载顺序问题。runner 负责把 dict 转成对象。

红线：本文件一经发布不得改版本号；结构变更一律新增 `00N_xxx.py`。
"""

MIGRATIONS = [
    {
        "version": 1,
        "name": "initial_baseline",
        "apply_sql": None,
        "note": "基线锚点：登记 version=1，不建表不改表（表由各模块 CREATE TABLE IF NOT EXISTS 自建）",
    },
]

# ruff: noqa: N999  # 迁移文件按 001_/002_ 编号命名
