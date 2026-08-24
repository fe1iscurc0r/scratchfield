from __future__ import annotations

import json
from typing import Any

from .cli_anything_tools import list_cli_tools, search_capabilities


class CliAnythingAgent:
    name = "CLI-Anything Agent"

    async def handle_handoff(self, task: dict[str, Any]) -> str:
        try:
            tool_name = str(task.get("tool_name") or "").strip()
            if not tool_name:
                return json.dumps(
                    {"status": "error", "message": "缺少tool_name参数", "data": {}},
                    ensure_ascii=False,
                )

            if tool_name == "list_cli_tools":
                data = list_cli_tools(
                    category=task.get("category"),
                    source=task.get("source"),
                    query=task.get("query"),
                    limit=task.get("limit"),
                )
            elif tool_name == "search_capabilities":
                data = search_capabilities(query=task.get("query"))
            else:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"未知工具: {tool_name}。可用工具: list_cli_tools, search_capabilities",
                        "data": {},
                    },
                    ensure_ascii=False,
                )

            return json.dumps(data, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"status": "error", "message": str(exc), "data": {}}, ensure_ascii=False)
