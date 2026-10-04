"""
LLM4Decompile MCP Server。

基于本仓库已装的 mcp SDK（构造函数式 handler + mcp_types + stdio transport），
暴露三个工具：
  - decompile_binary     反编译 ELF 二进制 → C
  - polish_ghidra_output 将 Ghidra 伪 C 润色为可读 C（RS-BA1 PE 主用）
  - health               检查模型加载状态

用法：
  python mcp_server.py --config config.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import yaml
from inference import LLM4Decompile, ModelNotLoadedError
from mcp import types  # 官方 mcp SDK 的类型模块（mcp.types）
from mcp.server import stdio
from mcp.server.lowlevel import Server

logger = logging.getLogger("llm4decompile.mcp")


# ---------------------------------------------------------------------- #
# 配置加载
# ---------------------------------------------------------------------- #
def load_config(config_path: str | None) -> dict:
    """加载 YAML 配置；未提供时回退到环境变量/默认值。"""
    import os

    cfg: dict[str, Any] = {}
    if config_path and Path(config_path).exists():
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    model = cfg.get("model", {})
    return {
        "model_path": model.get("path")
                      or model.get("model_path")
                      or os.environ.get("LLM4DECOMPILE_MODEL_PATH", ""),
        "n_gpu_layers": int(model.get("n_gpu_layers", -1)),
        "n_ctx": int(model.get("n_ctx", 16384)),
        "verbose": bool(model.get("verbose", False)),
        "config_path": config_path or "",
    }


# ---------------------------------------------------------------------- #
# MCP Server（低层 API）
# ---------------------------------------------------------------------- #
def build_server(cfg: dict) -> Server:
    llm = LLM4Decompile(
        model_path=cfg["model_path"],
        n_gpu_layers=cfg["n_gpu_layers"],
        n_ctx=cfg["n_ctx"],
        verbose=cfg["verbose"],
    )

    def _tool_def(name: str, description: str, props: dict) -> types.Tool:
        """构造 Tool 定义（只读入参 schema，无执行体——执行在 call_tool 中分发）。"""
        return types.Tool(
            name=name,
            description=description,
            input_schema={
                "type": "object",
                "properties": props,
            },
        )

    async def on_list_tools(ctx, params=None) -> types.ListToolsResult:
        tools = [
            _tool_def(
                "decompile_binary",
                "反编译 Linux x86_64 ELF 二进制文件 → 人类可读 C 代码（仅支持 ELF；PE 请用 polish_ghidra_output）",
                {
                    "binary_path": {"type": "string", "description": "二进制文件绝对路径"},
                    "optimization": {"type": "string", "description": "O0/O1/O2/O3，默认 auto"},
                    "max_tokens": {"type": "integer", "description": "最大输出 token，默认 4096"},
                },
            ),
            _tool_def(
                "polish_ghidra_output",
                "将 Ghidra/IDA 反编译输出润色为人类可读 C（适用于 PE/非 ELF 二进制，RS-BA1 主用）",
                {
                    "pseudo_c": {"type": "string", "description": "Ghidra 反编译输出的伪 C 代码"},
                    "function_name": {"type": "string", "description": "函数名"},
                    "context_hint": {"type": "string", "description": "额外上下文"},
                },
            ),
            _tool_def(
                "health",
                "检查模型加载状态、上下文窗口、GPU 卸载层数",
                {},
            ),
        ]
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        name = params.name
        args: dict = params.arguments or {}
        try:
            if name == "decompile_binary":
                result = llm.decompile_binary(
                    str(args.get("binary_path", "")),
                    str(args.get("optimization", "auto")),
                    int(args.get("max_tokens", 4096)),
                )
            elif name == "polish_ghidra_output":
                result = llm.polish_ghidra_output(
                    str(args.get("pseudo_c", "")),
                    str(args.get("function_name", "")),
                    str(args.get("context_hint", "")),
                )
            elif name == "health":
                result = json.dumps(llm.get_status(), ensure_ascii=False)
            else:
                result = f"ERROR: 未知工具 {name}"
        except ModelNotLoadedError as e:
            result = f"ERROR: {e}"
        except Exception as e:  # noqa: BLE001 - MCP 边界统一兜底
            result = f"ERROR: {e}"
        return types.CallToolResult(content=[types.TextContent(type="text", text=result)])

    return Server(
        "llm4decompile",
        version="1.0.0",
        description="LLM4Decompile 本地反编译 MCP 服务",
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM4Decompile MCP Server")
    parser.add_argument("--config", default="config.yaml",
                        help="YAML 配置文件路径（默认 config.yaml）")
    args = parser.parse_args()

    cfg = load_config(args.config)
    server = build_server(cfg)

    async def _run():
        async with stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    logger.info("LLM4Decompile MCP server 启动 (stdio)")
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    # 简单日志到 stderr，避免污染 MCP stdio 通道
    logging.basicConfig(level=logging.INFO,
                        stream=sys.stderr,
                        format="%(levelname)s %(name)s: %(message)s")
    main()
