# -*- coding: utf-8 -*-
"""PostgreSQL 查询 MCP 骨架（W66-07 · P3 待命，mock 连接降级）。

评估结论 P3 待命项——toolbox-postgres 查询 MCP 的前置骨架，W-09（academic 数据
落 PG）落地后启用。不引 psycopg2 重依赖，接口层可跑；无 PG 时 mock 降级并标注
P3 待命。纯标准库。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PostgresQueryMCP:
    """PG 查询 MCP 骨架：连接/query/schema 列表，mock 降级。"""
    connected: bool = False
    status: str = "P3 待命"
    _schema: list[str] = field(default_factory=lambda: ["public"])

    def connect(self, dsn: str = "") -> bool:
        """mock 连接：真实连接需 psycopg2（P3 启用时接入）。"""
        if not dsn:
            self.connected = False
            self.status = "P3 待命（无 DSN，mock 降级）"
            return False
        self.connected = True
        self.status = "connected"
        return True

    def list_schema(self) -> list[str]:
        return self._schema if self.connected else []

    def query(self, sql: str) -> list[dict] | None:
        """mock 查询：未连接返回 None。"""
        if not self.connected:
            return None
        return [{"mock": True, "sql": sql}]


if __name__ == "__main__":
    m = PostgresQueryMCP()
    print("未连接 schema:", m.list_schema(), "query:", m.query("SELECT 1"))
    m.connect("postgres://x")
    print("连接后 schema:", m.list_schema(), "status:", m.status)
