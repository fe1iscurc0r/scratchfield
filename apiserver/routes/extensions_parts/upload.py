"""文件上传与解析（卷190-A1：从 extensions.py 纯搬移）。"""
"""OpenClaw 技能市场、MCP 服务、技能导入、文件上传、旅行、记忆、搜索代理路由"""

import html
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

import yaml
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agentserver.openclaw.state_paths import get_openclaw_config_path, get_openclaw_state_dir
from apiserver import naga_auth
from apiserver.api_server import FileUploadResponse, _call_agentserver
from apiserver.mcp_assembly import (
    KNOWN_FAMILIES,
    KNOWN_TIERS,
)
from apiserver.mcp_assembly import (
    check_requirements as _assembly_check_requirements,
)
from apiserver.mcp_assembly import (
    decide_enabled as _assembly_decide_enabled,
)
from apiserver.mcp_assembly import (
    load_policy as _assembly_load_policy,
)
from apiserver.mcp_assembly import (
    set_agent_override as _assembly_set_override,
)
from apiserver.mcp_assembly import (
    set_policy as _assembly_set_policy,
)
from apiserver.telemetry import emit_telemetry
from system.config import get_config, get_data_dir

from .common import *  # noqa: F401,F403

router = APIRouter()



# ============ 文件上传 ============


@router.post("/upload/document", response_model=FileUploadResponse)
async def upload_document(file: UploadFile = File(...), description: str = Form(None)):
    """上传文档接口"""
    try:
        # 确保上传目录存在
        upload_dir = Path("uploaded_documents")
        upload_dir.mkdir(exist_ok=True)

        # 使用原始文件名
        filename = file.filename
        file_path = upload_dir / filename

        # 保存文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 获取文件信息
        stat = file_path.stat()

        return FileUploadResponse(
            filename=filename,
            file_path=str(file_path.absolute()),
            file_size=stat.st_size,
            file_type=file_path.suffix,
            upload_time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
        )
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail="上传失败")



@router.post("/upload/parse")
async def upload_parse(file: UploadFile = File(...)):
    """上传并解析文档内容（支持 .docx / .xlsx / .txt）"""
    import tempfile
    filename = file.filename or "unknown"
    suffix = Path(filename).suffix.lower()

    if suffix not in (".docx", ".xlsx", ".txt", ".csv", ".md"):
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {suffix}，支持 .docx / .xlsx / .txt / .csv / .md")

    # 写入临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        if suffix == ".docx":
            import importlib.util
            _docx_spec = importlib.util.spec_from_file_location(
                "docx_extract", Path(__file__).parent.parent / "skills_templates" / "office-docs" / "tools" / "docx_extract.py"
            )
            _docx_mod = importlib.util.module_from_spec(_docx_spec)
            _docx_spec.loader.exec_module(_docx_mod)
            lines = _docx_mod.extract_docx_text(tmp_path)
            content = "\n".join(lines)
        elif suffix == ".xlsx":
            import importlib.util
            import zipfile as _zf
            _xlsx_spec = importlib.util.spec_from_file_location(
                "xlsx_extract", Path(__file__).parent.parent / "skills_templates" / "office-docs" / "tools" / "xlsx_extract.py"
            )
            _xlsx_mod = importlib.util.module_from_spec(_xlsx_spec)
            _xlsx_spec.loader.exec_module(_xlsx_mod)
            with _zf.ZipFile(tmp_path, "r") as archive:
                shared_strings = _xlsx_mod._load_shared_strings(archive)
                sheets = _xlsx_mod._load_sheet_targets(archive)
                parts = []
                for name, path in sheets:
                    rows = _xlsx_mod._parse_sheet(archive, path, shared_strings, max_rows=500)
                    parts.append(f"## Sheet: {name}\n{_xlsx_mod._format_sheet_csv(rows, ',')}")
                content = "\n".join(parts)
        else:
            # txt / csv / md 直接读取
            content = tmp_path.read_text(encoding="utf-8", errors="replace")

        # 截断过长内容
        max_chars = 50000
        truncated = len(content) > max_chars
        if truncated:
            content = content[:max_chars]

        return {
            "status": "success",
            "filename": filename,
            "content": content,
            "truncated": truncated,
            "char_count": len(content),
        }
    except Exception as e:
        logger.error(f"文档解析失败: {e}")
        raise HTTPException(status_code=500, detail="解析失败")
    finally:
        tmp_path.unlink(missing_ok=True)

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
