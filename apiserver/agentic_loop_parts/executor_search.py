"""搜索与本地执行器（Brave/搜索代理 / 本地能力直调）（卷190-A2：从 agentic_tool_loop.py 纯搬移）。"""
#!/usr/bin/env python3
"""
Agentic Tool Loop 核心引擎
实现单LLM agentic loop：模型在对话中发起工具调用，接收结果，再继续推理，直到不再需要工具。
"""

import asyncio
import base64
import ipaddress
import json
import logging
import mimetypes
import re
import socket
import time as _time
from collections.abc import AsyncGenerator
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from apiserver import naga_auth
from apiserver.agent_directory import format_agent_directory_text, resolve_agent_descriptor
from apiserver.tool_schemas import resolve_mcp_func_name
from system.config import get_config, get_data_dir, get_server_port

logger = logging.getLogger("apiserver.agentic_tool_loop")  # 保持原日志通道名
from .markers import *  # noqa: F401,F403


async def _execute_search_tool(call: dict[str, Any]) -> dict[str, Any]:
    """通过 NagaBusiness 搜索代理执行 web_search（已登录时优先使用）"""
    tool_args = call.get("args", {})
    query = tool_args.get("query", "") or tool_args.get("q", "")
    count = tool_args.get("count", 10)
    freshness = tool_args.get("freshness")

    if not query:
        return {
            "tool_call": call, "result": "缺少搜索关键词",
            "status": "error", "service_name": "naga_search", "tool_name": "web_search",
        }

    try:
        token = naga_auth.get_access_token()
        params: dict[str, Any] = {"q": query, "count": count}
        if freshness:
            params["freshness"] = freshness

        client = _get_openclaw_client()
        t0 = _time.monotonic()
        from system.config import config as _sys_cfg
        upstream_base = (_sys_cfg.api.base_url or "").rstrip("/")
        if not upstream_base:
            raise ValueError("未配置 API base_url，无法执行搜索")
        resp = await client.post(
            upstream_base + "/tools/search",
            json=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
        elapsed = _time.monotonic() - t0

        if resp.status_code != 200:
            try:
                error_data = resp.json()
                error_msg = error_data.get("error", {}).get("message", f"HTTP {resp.status_code}")
            except Exception:
                error_msg = f"HTTP {resp.status_code}"
            logger.error(f"[AgenticLoop] 陆墨搜索代理错误: {error_msg}")
            return {
                "tool_call": call, "result": f"搜索失败: {error_msg}",
                "status": "error", "service_name": "naga_search", "tool_name": "web_search",
            }

        data = resp.json()
        results = data.get("web", {}).get("results", [])
        # 格式化搜索结果为可读文本
        if not results:
            readable = "未找到相关搜索结果。"
        else:
            lines = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                url = r.get("url", "")
                desc = r.get("description", "")
                age = r.get("age", "")
                lines.append(f"{i}. {title}")
                lines.append(f"   URL: {url}")
                if desc:
                    lines.append(f"   摘要: {desc}")
                if age:
                    lines.append(f"   时间: {age}")
                lines.append("")
            readable = "\n".join(lines)

        logger.info(f"[AgenticLoop] 陆墨搜索完成: query=\"{query}\" 耗时 {elapsed:.2f}s, 结果数={len(results)}")
        return {
            "tool_call": call, "result": readable,
            "status": "success", "service_name": "naga_search", "tool_name": "web_search",
        }
    except Exception as e:
        logger.error(f"[AgenticLoop] 陆墨搜索代理异常: {e}")
        return {
            "tool_call": call, "result": f"搜索异常: {e}",
            "status": "error", "service_name": "naga_search", "tool_name": "web_search",
        }



async def _execute_brave_search(call: dict[str, Any]) -> dict[str, Any]:
    """通过配置的 Brave Search API Key 直接搜索（未登录陆墨时使用）"""
    tool_args = call.get("args", {})
    query = tool_args.get("query", "") or tool_args.get("q", "")
    count = tool_args.get("count", 10)
    freshness = tool_args.get("freshness")

    if not query:
        return {
            "tool_call": call, "result": "缺少搜索关键词",
            "status": "error", "service_name": "brave_search", "tool_name": "web_search",
        }

    try:
        cfg = get_config()
        api_key = cfg.online_search.search_api_key
        api_base = cfg.online_search.search_api_base

        params: dict[str, Any] = {"q": query, "count": count}
        if freshness:
            params["freshness"] = freshness

        client = _get_openclaw_client()
        t0 = _time.monotonic()
        resp = await client.get(
            api_base,
            params=params,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
            },
            timeout=30.0,
        )
        elapsed = _time.monotonic() - t0

        if resp.status_code != 200:
            try:
                error_data = resp.json()
                error_msg = str(error_data)[:200]
            except Exception:
                error_msg = f"HTTP {resp.status_code}"
            logger.error(f"[AgenticLoop] Brave搜索错误: {error_msg}")
            return {
                "tool_call": call, "result": f"搜索失败: {error_msg}",
                "status": "error", "service_name": "brave_search", "tool_name": "web_search",
            }

        data = resp.json()
        results = data.get("web", {}).get("results", [])
        if not results:
            readable = "未找到相关搜索结果。"
        else:
            lines = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                url = r.get("url", "")
                desc = r.get("description", "")
                age = r.get("age", "")
                lines.append(f"{i}. {title}")
                lines.append(f"   URL: {url}")
                if desc:
                    lines.append(f"   摘要: {desc}")
                if age:
                    lines.append(f"   时间: {age}")
                lines.append("")
            readable = "\n".join(lines)

        logger.info(f"[AgenticLoop] Brave搜索完成: query=\"{query}\" 耗时 {elapsed:.2f}s, 结果数={len(results)}")
        return {
            "tool_call": call, "result": readable,
            "status": "success", "service_name": "brave_search", "tool_name": "web_search",
        }
    except Exception as e:
        logger.error(f"[AgenticLoop] Brave搜索异常: {e}")
        return {
            "tool_call": call, "result": f"搜索异常: {e}",
            "status": "error", "service_name": "brave_search", "tool_name": "web_search",
        }


# 可本地执行的工具（无需经过 OpenClaw，直接本地完成）
_LOCAL_EXEC_TOOLS = frozenset({
    "exec", "read", "write", "edit", "ls", "find", "grep", "process", "image",
    "sessions_spawn", "sessions_send", "gateway", "agents_list", "agent_relay",
})



async def _execute_local_tool(
    call: dict[str, Any],
    tool_name: str,
    tool_args: dict[str, Any],
    source_agent_id: str | None = None,
) -> dict[str, Any]:
    """本地直接执行 agent-session 级工具（exec/read/write/ls/grep 等），不经过 OpenClaw。"""
    import subprocess as _sp
    from pathlib import Path as _Path

    def _ok(text: str) -> dict[str, Any]:
        return {
            "tool_call": call, "result": text,
            "status": "success", "service_name": "openclaw_tool", "tool_name": tool_name,
        }

    def _err(text: str) -> dict[str, Any]:
        return {
            "tool_call": call, "result": text,
            "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
        }

    # ── exec 命令安全白名单 ──
    # 阻止 LLM 注入 shell 元字符，禁止危险命令，防止提示注入→RCE
    _EXEC_SAFE_COMMANDS = frozenset({
        "ls", "cat", "echo", "pwd", "whoami", "date", "uname", "head", "tail",
        "wc", "sort", "grep", "find", "which", "python", "python3", "node",
        "npm", "ping", "curl", "wget", "tar", "zip", "unzip", "git",
        "mkdir", "cp", "mv", "rm", "chmod", "chown", "stat", "du", "df",
        "ps", "top", "kill", "env", "printenv", "id", "hostname", "ip",
        "ifconfig", "netstat", "ss", "systeminfo", "tasklist", "taskkill",
    })
    _EXEC_DANGEROUS_CHARS_RE = __import__('re').compile(r'[;&|`$(){}\[\]<>]')

    try:
        if tool_name == "exec":
            cmd = tool_args.get("command", "")
            if not cmd:
                return _err("缺少 command 参数")
            # 安全校验：阻止 shell 元字符（提示注入逃逸）
            if _EXEC_DANGEROUS_CHARS_RE.search(cmd):
                return _err("命令包含非法字符（; & | ` $ ( ) { } [ ] < >），禁止执行")
            # 安全校验：只允许白名单命令
            first_token = cmd.strip().split()[0] if cmd.strip() else ""
            if first_token and first_token not in _EXEC_SAFE_COMMANDS:
                return _err(f"命令 '{first_token}' 不在执行白名单中，禁止执行")
            timeout = min(tool_args.get("timeout", 60), 300)
            workdir = tool_args.get("workdir")
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except TimeoutError:
                proc.kill()
                return _err(f"命令执行超时 ({timeout}s)")
            out = (stdout or b"").decode(errors="replace")
            err = (stderr or b"").decode(errors="replace")
            text = out
            if err:
                text += f"\n[stderr]\n{err}" if out else err
            if proc.returncode != 0:
                text += f"\n[exit code: {proc.returncode}]"
            return _ok(text[:50000] if text else "(无输出)")

        elif tool_name == "read":
            fp = tool_args.get("file_path", "")
            if not fp:
                return _err("缺少 file_path 参数")
            p = _Path(fp).expanduser()
            if not p.exists():
                return _err(f"文件不存在: {fp}")
            content = p.read_text(encoding="utf-8", errors="replace")
            return _ok(content[:100000])

        elif tool_name == "write":
            fp = tool_args.get("file_path", "")
            content = tool_args.get("content", "")
            if not fp:
                return _err("缺少 file_path 参数")
            p = _Path(fp).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return _ok(f"已写入 {fp} ({len(content)} 字符)")

        elif tool_name == "edit":
            fp = tool_args.get("file_path", "")
            old = tool_args.get("old_string", "")
            new = tool_args.get("new_string", "")
            if not fp or not old:
                return _err("缺少 file_path 或 old_string 参数")
            p = _Path(fp).expanduser()
            if not p.exists():
                return _err(f"文件不存在: {fp}")
            text = p.read_text(encoding="utf-8", errors="replace")
            if old not in text:
                return _err("未找到要替换的文本")
            text = text.replace(old, new, 1)
            p.write_text(text, encoding="utf-8")
            return _ok(f"已替换 {fp}")

        elif tool_name == "ls":
            path = tool_args.get("path", ".")
            p = _Path(path).expanduser()
            if not p.is_dir():
                return _err(f"目录不存在: {path}")
            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            lines = []
            for e in entries[:500]:
                prefix = "d " if e.is_dir() else "  "
                lines.append(f"{prefix}{e.name}")
            return _ok("\n".join(lines) if lines else "(空目录)")

        elif tool_name == "find":
            pattern = tool_args.get("pattern", "*")
            path = tool_args.get("path", ".")
            p = _Path(path).expanduser()
            matches = sorted(p.rglob(pattern))[:200]
            return _ok("\n".join(str(m) for m in matches) if matches else "未找到匹配文件")

        elif tool_name == "grep":
            import re as _re
            pattern = tool_args.get("pattern", "")
            path = tool_args.get("path", ".")
            include = tool_args.get("include", "")
            if not pattern:
                return _err("缺少 pattern 参数")
            p = _Path(path).expanduser()
            glob_pat = include if include else "**/*"
            files = p.rglob(glob_pat) if p.is_dir() else [p]
            results = []
            try:
                regex = _re.compile(pattern)
            except _re.error as e:
                return _err(f"正则表达式错误: {e}")
            for f in files:
                if not f.is_file() or f.stat().st_size > 2_000_000:
                    continue
                try:
                    for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                        if regex.search(line):
                            results.append(f"{f}:{i}: {line.rstrip()}")
                            if len(results) >= 200:
                                break
                except Exception:
                    continue
                if len(results) >= 200:
                    break
            return _ok("\n".join(results) if results else "未找到匹配")

        elif tool_name == "agents_list":
            return _ok(format_agent_directory_text())

        elif tool_name == "agent_relay":
            return await _execute_agent_relay(call, tool_args, source_agent_id)

        elif tool_name == "image":
            text, failed = await _analyze_image_local(tool_args)
            return _err(text) if failed else _ok(text)

        elif tool_name == "web_fetch":
            text, failed = await _fetch_web_page_local(tool_args)
            return _err(text) if failed else _ok(text)

        elif tool_name == "tts":
            text, failed = await _synthesize_speech_local(tool_args)
            return _err(text) if failed else _ok(text)

        elif tool_name == "process":
            # 本地 exec 是同步白名单执行、没有会话注册表，进程管理交给 OpenClaw agent 会话，
            # 不再一律报"暂不支持本地执行"把工具变成死胡同。
            return await _execute_openclaw_session_tool(call, tool_name, tool_args)

        else:
            # sessions_spawn, sessions_send, gateway 等走 OpenClaw agent session 降级
            return await _execute_openclaw_session_tool(call, tool_name, tool_args)

    except Exception as e:
        logger.error(f"[AgenticLoop] 本地工具执行失败: {tool_name}, error={e}")
        return _err(f"执行失败: {e}")



async def _analyze_image_local(tool_args: dict[str, Any]) -> Tuple[str, bool]:
    """image 工具的本地实现：本地图片文件或 http(s) URL → 视觉上游 → 文字分析结论。

    复用 lumo_proxy 的视觉客户端（凭证优先 LUMO_VISION_API_KEY，回落 NEKO
    core_config.coreApiKey），不再一律返回"暂不支持本地执行"。

    Returns:
        (文本结果, 是否失败)
    """
    target = str(tool_args.get("url") or tool_args.get("path") or "").strip()
    if not target:
        return "缺少 url 参数", True

    if target.lower().startswith(("http://", "https://")):
        image_url = target
    else:
        candidate = Path(target).expanduser()
        if any(part == ".." for part in candidate.parts):
            return f"路径不合法（含 ..）: {target}", True
        resolved = candidate.resolve()
        if not resolved.is_file():
            return f"图片文件不存在: {target}", True
        size = resolved.stat().st_size
        if size > 12 * 1024 * 1024:
            return f"图片过大（{size // 1024 // 1024}MB > 12MB）", True
        mime = mimetypes.guess_type(str(resolved))[0] or "image/png"
        if not mime.startswith("image/"):
            return f"不是图片类型（{mime}）: {target}", True
        image_url = f"data:{mime};base64,{base64.b64encode(resolved.read_bytes()).decode()}"

    try:
        from apiserver.routes.lumo_proxy import (
            _VISION_MODEL,
            _get_vision_client,
            _resolve_vision_api_key,
        )
    except Exception as e:  # noqa: BLE001
        return f"视觉通路不可用: {type(e).__name__}: {e}", True

    api_key = _resolve_vision_api_key()
    if not api_key:
        return "视觉上游未配置（设置 LUMO_VISION_API_KEY 或 NEKO core_config.coreApiKey）", True

    body = {
        "model": _VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请描述这张图片的内容并给出关键结论（中文，简明）。"},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ],
        "max_tokens": 800,
    }
    try:
        client = _get_vision_client()
        resp = await client.post(
            "/chat/completions", json=body, headers={"Authorization": f"Bearer {api_key}"}
        )
        resp.raise_for_status()
        data = resp.json()
        text = str(data["choices"][0]["message"].get("content") or "").strip()
        return (text or "视觉上游返回空结果"), False
    except Exception as e:  # noqa: BLE001
        return f"图片分析失败: {type(e).__name__}: {str(e)[:200]}", True



async def _is_public_http_url(raw: str) -> Tuple[bool, str]:
    """SSRF 边界校验：仅允许 http/https，且解析后的 IP 必须是公网地址。

    拒绝环回、私网、链路本地、保留、组播与未指定地址（防内网探测 / 云元数据）。
    """
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        return False, f"只支持 http/https（收到 {parsed.scheme or '空'}）"
    host = (parsed.hostname or "").lower()
    if not host:
        return False, "缺少主机名"
    if host == "localhost" or host.endswith(".local"):
        return False, f"拒绝本机主机名: {host}"
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as e:
        return False, f"域名解析失败: {e}"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False, f"拒绝非公网地址: {ip}"
    return True, ""



async def _fetch_web_page_local(tool_args: dict[str, Any]) -> Tuple[str, bool]:
    """web_fetch 的本地实现：抓取公开 http(s) 页面并抽成文本。

    Returns:
        (文本结果, 是否失败)
    """
    url = str(tool_args.get("url") or "").strip()
    if not url:
        return "缺少 url 参数", True
    ok, reason = await _is_public_http_url(url)
    if not ok:
        return f"URL 被拒绝：{reason}", True

    max_chars = min(int(tool_args.get("maxChars") or 8000), 40000)
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, max_redirects=5) as client:
            resp = await client.get(url, headers={"User-Agent": "Lumo/5.1 (local-fetch)"})
    except Exception as e:  # noqa: BLE001
        return f"抓取失败: {type(e).__name__}: {str(e)[:200]}", True

    # 重定向可能跳到内网 → 对最终 URL 再校验一次
    final_url = str(resp.url)
    ok_final, reason_final = await _is_public_http_url(final_url)
    if not ok_final:
        return f"重定向目标被拒绝：{reason_final}（{final_url}）", True
    if resp.status_code >= 400:
        return f"HTTP {resp.status_code}: {final_url}", True

    content_type = str(resp.headers.get("content-type") or "").lower()
    body = resp.text
    if "html" in content_type or body.lstrip()[:1] == "<":
        try:
            from apiserver.local_search import _strip_tags

            body = _strip_tags(body)
        except Exception:  # noqa: BLE001 - 抽取失败就返回原始文本
            pass
    text = re.sub(r"\n{3,}", "\n\n", body).strip()
    truncated = len(text) > max_chars
    suffix = f"\n\n…（已截断，原文 {len(text)} 字符）" if truncated else ""
    return f"[{final_url}]\n{text[:max_chars]}{suffix}", False



async def _synthesize_speech_local(tool_args: dict[str, Any]) -> Tuple[str, bool]:
    """tts 的本地实现：调用本机 TTS 服务（voice/output/server.py，默认 :5048）合成音频文件。

    Returns:
        (文本结果, 是否失败)
    """
    text = str(tool_args.get("text") or "").strip()
    if not text:
        return "缺少 text 参数", True

    cfg = get_config()
    tts_cfg = getattr(cfg, "tts", None)
    port = int(getattr(tts_cfg, "port", 5048) or 5048)
    voice = str(
        tool_args.get("voice")
        or getattr(tts_cfg, "default_voice", "")
        or "zh-CN-XiaoxiaoNeural"
    )
    audio_format = str(
        tool_args.get("format") or getattr(tts_cfg, "default_format", "") or "mp3"
    )
    speed = float(getattr(tts_cfg, "default_speed", 1.0) or 1.0)

    payload = {
        "input": text,
        "voice": voice,
        "response_format": audio_format,
        "speed": speed,
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"http://127.0.0.1:{port}/v1/audio/speech", json=payload
            )
            resp.raise_for_status()
            audio = resp.content
    except Exception as e:  # noqa: BLE001
        return f"语音合成失败: {type(e).__name__}: {str(e)[:200]}", True

    out_dir = Path(get_data_dir()) / "tts_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"tts_{int(_time.time() * 1000)}.{audio_format}"
    out_path.write_bytes(audio)
    return f"语音已生成：{out_path}（{len(audio)} 字节，音色 {voice}，格式 {audio_format}）", False

__all__ = ['_LOCAL_EXEC_TOOLS', '_analyze_image_local', '_execute_brave_search', '_execute_local_tool', '_execute_search_tool', '_fetch_web_page_local', '_is_public_http_url', '_synthesize_speech_local']

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
