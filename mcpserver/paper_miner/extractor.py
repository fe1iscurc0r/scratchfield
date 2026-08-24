"""提取 pipeline：论文 → 结构化实验参数 JSON（靶子 A）。

两条路径：
- Markdown 输入（靶子 D 产物）：跳过 VLM，直接 LLM 提取结构化 JSON
- PDF 输入：逐页渲染为图片 → VLM 看图产出结构化 Markdown → LLM 提取 JSON

Ollama 未装 / 模型未拉时，返回结构化错误（不崩溃），并给出可读诊断。
"""
from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path
from typing import Any

from mcpserver.paper_miner.ollama_client import OllamaUnavailable, chat, generate, healthcheck

logger = logging.getLogger(__name__)

# 默认模型（可用 env 覆盖）
VLM_MODEL = "minicpm-v:8b"
LLM_MODEL = "llama3.2:3b"

_EXTRACTION_PROMPT = (
    "你是材料科学实验参数提取器。从下面论文文本中提取所有实验参数组合，"
    "输出 JSON 数组，每个元素含字段（无信息则省略该字段）："
    "precursor(前驱体), crosslinker(交联剂), koh_ratio(KOH活化比例), "
    "heating_rate(升温速率°C/min), carbonization_temp(碳化温度°C), "
    "holding_time(保温时间min), conductivity(导电率S/cm), "
    "surface_area(比表面积m2/g), porosity(孔隙率%), yield_rate(产率%). "
    "数值只输出数字。没有实验数据输出空数组 []。论文文本：\n\n"
)

_VLM_PAGE_PROMPT = (
    "把这张论文页面转成结构化 Markdown，保留所有表格、公式、图注与参数数值，"
    "不要省略数字。只输出 Markdown，不要解释。"
)


def _json_from_text(text: str) -> list[dict[str, Any]]:
    """从 LLM 输出中稳健解析 JSON 数组。"""
    text = text.strip()
    # 去掉可能的 ```json 围栏
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        candidate = m.group(0)
    else:
        candidate = text
    try:
        data = json.loads(candidate)
        return data if isinstance(data, list) else [data] if isinstance(data, dict) else []
    except json.JSONDecodeError:
        # 尝试包裹成数组
        try:
            data = json.loads("[" + candidate + "]")
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []


def extract_from_markdown(md_text: str, *, paper: str = "", source_path: str = "") -> list[dict[str, Any]]:
    """从 Markdown 文本提取实验参数（LLM 路径）。"""
    hc = healthcheck()
    if not hc["ok"]:
        raise OllamaUnavailable(hc.get("error", "Ollama 不可用"))
    out = generate(LLM_MODEL, _EXTRACTION_PROMPT + md_text[:60000], format_json=True)
    records = _json_from_text(out)
    for r in records:
        r.setdefault("paper", paper or Path(source_path).stem if source_path else "")
        r.setdefault("source_path", source_path or None)
    return records


def _pdf_to_markdown_vlm(pdf_path: Path) -> str:
    """把 PDF 逐页渲染为图片并用 VLM 转为 Markdown。"""
    from pdf2image import convert_from_path  # type: ignore
    hc = healthcheck()
    if not hc["ok"]:
        raise OllamaUnavailable(hc.get("error", "Ollama 不可用"))
    pages = convert_from_path(str(pdf_path))
    chunks: list[str] = []
    for i, img in enumerate(pages, 1):
        buf_io = __import__("io").BytesIO()
        img.save(buf_io, format="PNG")
        b64 = base64.b64encode(buf_io.getvalue()).decode("ascii")
        md = chat(VLM_MODEL, _VLM_PAGE_PROMPT, images=[b64], format_json=False, temperature=0.1)
        chunks.append(f"<!-- 第 {i} 页 -->\n{md}")
    return "\n\n".join(chunks)


def extract_paper(task_path: str, *, markdown: bool | None = None, db=None) -> dict[str, Any]:
    """提取单篇论文的实验参数并（可选）入库。

    Args:
        task_path: 论文路径（.md 走 LLM 路径；.pdf 走 VLM 路径）
        markdown: 强制按 Markdown 处理（默认按扩展名判断）
        db: 可选 ExperimentDB 实例；传入则写入 experiments 表
    """
    src = Path(task_path)
    try:
        src = src.resolve(strict=True)
        is_md = markdown if markdown is not None else src.suffix.lower() in (".md", ".markdown", ".txt")
        if is_md:
            md_text = src.read_text(encoding="utf-8", errors="replace")
        else:
            md_text = _pdf_to_markdown_vlm(src)

        records = extract_from_markdown(
            md_text, paper=src.stem, source_path=str(src)
        )
        inserted = []
        if db is not None:
            for rec in records:
                inserted.append(db.insert_experiment(rec))
        return {
            "ok": True,
            "source": str(src),
            "path": "markdown-llm" if is_md else "pdf-vlm+llm",
            "records": records,
            "inserted_ids": inserted,
        }
    except OllamaUnavailable as e:
        return {"ok": False, "error": str(e), "source": str(src)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "source": str(src)}