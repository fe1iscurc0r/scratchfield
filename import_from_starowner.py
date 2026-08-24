"""从星藏家知识 API 批量导入视频摘要到 scratchpad RAG 知识库。

数据流:
    星藏家 (127.0.0.1:17391)  →  本脚本  →  scratchpad RAG (127.0.0.1:8000)

前置条件:
    1. 星藏家桌面应用在运行（知识 API 默认 127.0.0.1:17391）
    2. scratchpad 后端在运行（lumo.bat 启动，默认 127.0.0.1:8000）
    3. 星藏家里已有「已完成」的视频转化产物
    4. scratchpad 未启用密码登录（auth.require_auth=False，默认）。
       若已启用密码，需在前端登录后将 access_token 导出到 SCRATCHPAD_TOKEN 环境变量。

用法:
    python import_from_starowner.py              # 全量导入（自动跳过已导入）
    python import_from_starowner.py --doc <id>   # 只导入指定 documentId（可逗号分隔多个）
    python import_from_starowner.py --dry-run    # 只预览，不实际写入
    python import_from_starowner.py --force      # 不跳过已导入，强制重新导入

环境变量:
    STAROWNER_API     星藏家知识 API 基址（默认 http://127.0.0.1:17391）
    SCRATCHPAD_API    scratchpad RAG 基址（默认 http://127.0.0.1:8000）
    SCRATCHPAD_TOKEN  可选。scratchpad 启用 require_auth 时需传 access_token
                      （在浏览器 DevTools 看 localStorage access_token）。
"""
import argparse
import json
import os
import re
import sys
from urllib.parse import quote

import requests

STAROWNER_API = os.getenv("STAROWNER_API", "http://127.0.0.1:17391").rstrip("/")
SCRATCHPAD_API = os.getenv("SCRATCHPAD_API", "http://127.0.0.1:8000").rstrip("/")
SCRATCHPAD_TOKEN = os.getenv("SCRATCHPAD_TOKEN", "").strip()

# ─── 服务端硬约束（来自 apiserver/routes/rag.py） ───
MAX_CONTENT_CHARS = 200_000   # POST /api/rag/document content 上限，超了会直接 400
MAX_TITLE_CHARS = 200         # title 上限
MAX_TAG_CHARS = 50            # 单个 tag 安全长度（收藏夹/UP 主名可能很长）
PAGE_LINES = 400              # 星藏家 content 分页行数（API 上限 1000，默认 400）
LIST_PAGE = 500               # 文档列表分页大小（API 上限 500）
SOURCE_PREFIX = "starowner://"

# Origin + Content-Type 在 require_auth=False 时可过；有 token 时再附加 Authorization
HEADERS = {"Origin": "http://127.0.0.1:5173", "Content-Type": "application/json"}
if SCRATCHPAD_TOKEN:
    HEADERS["Authorization"] = f"Bearer {SCRATCHPAD_TOKEN}"


_AUTH_HINT = """
       scratchpad 已启用密码认证（auth.require_auth=True），本脚本需要 access_token。
       请执行以下任一步骤：
       a) 在 scratchpad 前端登录后，浏览器 DevTools → Application → localStorage
          找到 access_token 复制，然后：
             set SCRATCHPAD_TOKEN=<复制的值>
             python import_from_starowner.py
       b) 临时关闭认证：在 scratchpad 配置文件里 auth.require_auth 设为 false，重启后端。
"""


def _scratchpad_error_message(resp: requests.Response) -> str:
    """根据 scratchpad HTTP 响应给出可读错误 + 修复提示。"""
    try:
        body = resp.json()
    except Exception:
        body = {"detail": resp.text[:300]}
    detail = body.get("detail", "") or resp.reason or ""
    if resp.status_code == 401:
        return f"HTTP 401 {detail}{_AUTH_HINT}"
    if resp.status_code == 400 and str(detail).startswith("内容过长"):
        return (
            f"HTTP 400 {detail}\n"
            "       说明：脚本 _split_long_content 自动分片应该已经兜底；若仍触发，\n"
            "       请检查 MAX_CONTENT_CHARS 是否与服务端 rag.py 中的 MAX_TEXT_CHARS 同步。"
        )
    return f"HTTP {resp.status_code} {detail}"


def health_check():
    """检查两边服务是否可用。"""
    ok = True
    try:
        r = requests.get(f"{STAROWNER_API}/api/manifest", timeout=5)
        r.raise_for_status()
        m = r.json()
        print(f"[星藏家] OK  {m.get('product','?')} protocol {m.get('protocolVersion','?')} @ {STAROWNER_API}")
    except Exception as e:
        print(f"[星藏家] 不可达 @ {STAROWNER_API}: {e}")
        print("       请先启动星藏家桌面应用。")
        ok = False
    try:
        r = requests.get(f"{SCRATCHPAD_API}/api/rag/stats", headers=HEADERS, timeout=5)
        if r.status_code != 200:
            raise RuntimeError(_scratchpad_error_message(r))
        s = r.json()
        # stats 返回结构是嵌套的：collections.<name>.doc_count
        doc_count = "?"
        try:
            cols = s.get("collections", {}) or {}
            for name in ("materialscience", "default"):
                if name in cols:
                    doc_count = cols[name].get("doc_count", "?")
                    break
            else:
                # 降级：直接查 documents 接口拿 total
                lr = requests.get(
                    f"{SCRATCHPAD_API}/api/rag/documents",
                    headers=HEADERS, params={"limit": 1}, timeout=5,
                )
                if lr.status_code == 200:
                    doc_count = lr.json().get("total", "?")
        except Exception:
            pass
        print(f"[scratchpad] OK  docs={doc_count} @ {SCRATCHPAD_API}")
    except RuntimeError as e:
        print(f"[scratchpad] 认证或服务异常 @ {SCRATCHPAD_API}: {e}")
        ok = False
    except Exception as e:
        print(f"[scratchpad] 不可达 @ {SCRATCHPAD_API}: {e}")
        print("       请先用 lumo.bat 启动 scratchpad 后端。")
        ok = False
    return ok


def fetch_existing_starowner_docs():
    """拉取 scratchpad 已有星藏家文档的 documentId 集合（用于去重）。

    实现策略：服务端 list_documents 的 source 参数是精确匹配
    （WHERE json_extract(metadata, '$.source') = ?），不能前缀匹配。
    所以只能全量拉 documents，然后在客户端过滤 source.startswith(starowner://)。
    如果将来文档 > 5000 条，应在服务端补一个 source_prefix 查询参数。
    """
    imported = set()
    offset = 0
    while True:
        try:
            r = requests.get(
                f"{SCRATCHPAD_API}/api/rag/documents",
                headers=HEADERS,
                params={"limit": LIST_PAGE, "offset": offset},
                timeout=15,
            )
            if r.status_code != 200:
                raise RuntimeError(_scratchpad_error_message(r))
        except RuntimeError:
            raise
        except Exception as e:
            print(f"[去重] 拉取已有文档失败: {e}（将跳过去重，可能产生重复）")
            return imported
        data = r.json()
        if not data.get("success", True):
            err = data.get("error") or "list_documents 返回失败"
            print(f"[去重] 拉取已有文档失败: {err}（将跳过去重，可能产生重复）")
            return imported
        docs = data.get("documents", []) or []
        for doc in docs:
            # list_documents 返回的 source 在顶层（meta.get("source") 回填的）
            # 格式见 vecdb_client.list_documents: {"source": meta.get("source", source_type)}
            src = doc.get("source")
            if isinstance(src, str) and src.startswith(SOURCE_PREFIX):
                # source 可能是 starowner://<id>#partN（长视频分片导入）
                # 提取主干 id：# 之前的部分
                core = src[len(SOURCE_PREFIX):].split("#", 1)[0]
                imported.add(core)
        if len(docs) < LIST_PAGE:
            break
        offset += len(docs)
    print(f"[去重] scratchpad 已有 {len(imported)} 个星藏家视频（可能含多分片）")
    return imported


def fetch_starowner_documents():
    """分页拉取星藏家所有已完成文档元数据。"""
    docs = []
    offset = 0
    while True:
        r = requests.get(
            f"{STAROWNER_API}/api/knowledge/documents",
            params={"offset": offset, "limit": LIST_PAGE, "sort": "completed-desc"},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        page = data.get("documents", []) or []
        docs.extend(page)
        nxt = data.get("nextOffset")
        if nxt is None or not page:
            break
        offset = nxt
    return docs


def fetch_full_content(document_id):
    """分页读取一个文档的完整 Markdown 原文，follow nextStartLine 直到 null。"""
    parts = []
    start_line = 1
    total_lines = None
    while True:
        r = requests.get(
            f"{STAROWNER_API}/api/knowledge/documents/{quote(document_id, safe='')}/content",
            params={"startLine": start_line, "lineCount": PAGE_LINES},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        parts.append(data.get("content", ""))
        total_lines = data.get("totalLines", total_lines)
        nxt = data.get("nextStartLine")
        if nxt is None:
            break
        start_line = nxt
    return "\n".join(parts), total_lines


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize_tag(t: str) -> str:
    """清理 tag：None/空 → ''；控制字符、首尾空白；超过 MAX_TAG_CHARS 截断并加省略号。"""
    if t is None:
        return ""
    t = _CONTROL_CHARS_RE.sub("", str(t))
    t = t.strip().replace("\n", " ").replace("\r", " ")
    if len(t) > MAX_TAG_CHARS:
        t = t[: MAX_TAG_CHARS - 1] + "…"
    return t


def _split_long_content(content: str) -> list:
    """按 空行/段落 优先切分，保证每片长度 <= MAX_CONTENT_CHARS。

    服务端 MAX_TEXT_CHARS=200_000 是硬线，这里用 190_000 留 10k buffer 给换行拼接、
    标题截断、字段序列化开销。
    """
    cap = MAX_CONTENT_CHARS - 10_000
    if len(content) <= cap:
        return [content]

    # 1) 按空行分段（Markdown 段落分隔）
    blocks = re.split(r"\n\s*\n", content)
    pieces: list[str] = []
    cur = ""
    for block in blocks:
        if not cur:
            nxt = block
        else:
            nxt = cur + "\n\n" + block
        if len(nxt) <= cap:
            cur = nxt
        else:
            if cur:
                pieces.append(cur)
            # 单 block > cap 的情况，再按行切
            if len(block) <= cap:
                cur = block
            else:
                for line in block.splitlines(keepends=True):
                    if not cur:
                        nxt2 = line
                    else:
                        nxt2 = cur + line
                    if len(nxt2) <= cap:
                        cur = nxt2
                    else:
                        if cur:
                            pieces.append(cur)
                        # 单行长到装不下：硬切
                        while len(line) > cap:
                            pieces.append(line[:cap])
                            line = line[cap:]
                        cur = line
    if cur:
        pieces.append(cur)
    return pieces


def build_payload(doc, content, part_index=None, part_total=None):
    """把星藏家文档 + 完整内容组装成 /api/rag/document 的 payload。

    part_index/part_total：长内容自动分片后（_split_long_content），在标题、source、
    metadata 中记录分片位置，保证去重和展示可识别。
    """
    doc_id = doc.get("id", "")
    title = doc.get("title", "未命名视频")
    bvid = doc.get("bvid", "")
    owner = doc.get("owner", "")
    tags = doc.get("tags") or []
    collection = doc.get("collection") or {}
    user = doc.get("user") or {}

    # 标题：加 [BV]，多分片时再追加分片号
    display_title = f"[{bvid}] {title}" if bvid else title
    if part_total and part_total > 1:
        display_title = f"{display_title} ({part_index}/{part_total})"
    display_title = display_title.strip()[:MAX_TITLE_CHARS]

    # tags 清理 + 去重，UP 主/收藏夹名追加到末尾
    raw_tag_list = []
    for t in list(tags) + [owner, collection.get("name", "")]:
        clean = _sanitize_tag(t)
        if clean and clean not in raw_tag_list:
            raw_tag_list.append(clean)

    # source：单分片 starowner://<id>，多分片 starowner://<id>#partN
    source_part_suffix = ""
    if part_total and part_total > 1:
        source_part_suffix = f"#part{part_index}"
    source = f"{SOURCE_PREFIX}{doc_id}{source_part_suffix}"

    metadata = {
        "starowner_document_id": doc_id,
        "bvid": bvid,
        "owner": owner,
        "collection_id": collection.get("id", ""),
        "collection_name": collection.get("name", ""),
        "user_id": user.get("id", ""),
        "user_name": user.get("name", ""),
        "published_at": doc.get("publishedAt", ""),
        "favorite_added_at": doc.get("favoriteAddedAt", ""),
        "completed_at": doc.get("completedAt", ""),
        "bilibili_url": doc.get("url", ""),
        "multi_part_role": doc.get("multiPartRole", ""),
    }
    if part_total and part_total > 1:
        metadata["part_index"] = part_index
        metadata["part_total"] = part_total
        metadata["starowner_document_id_core"] = doc_id
    # source 会在服务端 rag.py 里再次合并到 metadata.source，这里显式塞一次以防万一
    metadata["source"] = source

    return {
        "title": display_title,
        "content": content,
        "tags": raw_tag_list,
        "source": source,
        "metadata": metadata,
    }


def ingest_one(doc, dry_run=False):
    """读取完整内容、按服务端上限分片、逐个投递到 scratchpad。返回 (ok, total_chunks)。"""
    doc_id = doc.get("id", "")
    title = doc.get("title", "")
    try:
        content, total_lines = fetch_full_content(doc_id)
    except Exception as e:
        print(f"  ✗ 拉取内容失败: {e}")
        return False, 0
    if not content.strip():
        print(f"  ✗ 跳过（内容为空）: {title}")
        return False, 0

    pieces = _split_long_content(content)
    part_total = len(pieces)

    # 第一个分片先打印整体摘要，后面分片再追加信息
    base_preview = build_payload(doc, pieces[0], part_index=1, part_total=part_total)
    print(
        f"  → {base_preview['title']}  "
        f"({total_lines} 行, {len(content)} 字符 → {part_total} 分片, "
        f"tags={base_preview['tags']})"
    )
    if dry_run:
        print(f"    [dry-run] 不写入。source={base_preview['source']}")
        if part_total > 1:
            for p in range(2, part_total + 1):
                print(f"    [dry-run] part{p}  source=starowner://{doc_id}#part{p}")
        return True, 0

    ok_count = 0
    total_chunks = 0
    for idx, piece in enumerate(pieces, 1):
        payload = build_payload(doc, piece, part_index=idx, part_total=part_total)
        if part_total > 1:
            print(f"    分片 {idx}/{part_total}: {len(piece)} 字符  source={payload['source']}")
        try:
            r = requests.post(
                f"{SCRATCHPAD_API}/api/rag/document",
                headers=HEADERS,
                json=payload,
                timeout=180,  # 嵌入+分块可能比较慢，放宽
            )
        except Exception as e:
            print(f"    ✗ 请求异常: {e}")
            continue
        if r.status_code == 200:
            data = r.json()
            chunks = data.get("chunk_count", 0)
            d_id = data.get("doc_id", "?")
            if part_total == 1:
                print(f"  ✓ 成功: doc_id={d_id}, chunks={chunks}")
            else:
                print(f"    ✓ part{idx} 成功: doc_id={d_id}, chunks={chunks}")
            ok_count += 1
            total_chunks += chunks
        else:
            err = _scratchpad_error_message(r)
            if part_total == 1:
                print(f"  ✗ 失败: {err}")
            else:
                print(f"    ✗ part{idx} 失败: {err}")

    if part_total > 1:
        if ok_count == part_total:
            print(f"  ✓ {part_total}/{part_total} 分片全部成功")
        else:
            print(f"  ⚠ 分片部分成功: {ok_count}/{part_total}（需用 --force 重跑此 --doc 补全）")
    return (ok_count == part_total and part_total > 0), total_chunks


def main():
    ap = argparse.ArgumentParser(description="从星藏家知识 API 导入视频摘要到 scratchpad RAG")
    ap.add_argument("--doc", help="只导入指定 documentId（可逗号分隔多个）")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不实际写入 scratchpad")
    ap.add_argument("--force", action="store_true", help="不跳过已导入，强制重新导入")
    args = ap.parse_args()

    print("=" * 70)
    print("星藏家 → scratchpad 知识导入")
    print(f"  源:   {STAROWNER_API}")
    print(f"  目标: {SCRATCHPAD_API}")
    print("=" * 70)

    if not health_check():
        sys.exit(1)

    # 1. 拉星藏家文档列表
    print("\n[1/3] 拉取星藏家已完成文档列表...")
    docs = fetch_starowner_documents()
    print(f"  共 {len(docs)} 个已完成文档")
    if not docs:
        print("  星藏家还没有已完成的视频转化产物。先用星藏家转化视频后再跑本脚本。")
        return

    if args.doc:
        wanted = {d.strip() for d in args.doc.split(",") if d.strip()}
        docs = [d for d in docs if d.get("id") in wanted]
        print(f"  --doc 筛选后: {len(docs)} 个")

    # 2. 去重
    imported = set() if args.force else fetch_existing_starowner_docs()
    pending = [d for d in docs if d.get("id") not in imported]
    skipped = len(docs) - len(pending)
    print(f"\n[2/3] 去重: 跳过 {skipped} 个已导入，待导入 {len(pending)} 个")

    if not pending:
        print("  没有需要导入的新文档。")
        return

    # 3. 逐个导入
    print(f"\n[3/3] 开始导入 {len(pending)} 个文档...")
    ok = 0
    fail = 0
    total_chunks = 0
    for i, doc in enumerate(pending, 1):
        print(f"\n[{i}/{len(pending)}] {doc.get('title','')}")
        try:
            success, chunks = ingest_one(doc, dry_run=args.dry_run)
            if success:
                ok += 1
                total_chunks += chunks
            else:
                fail += 1
        except KeyboardInterrupt:
            print("\n用户中断。")
            break
        except Exception as e:
            print(f"  ✗ 异常: {e}")
            fail += 1

    print("\n" + "=" * 70)
    print(f"完成: 成功 {ok} / 失败 {fail} / 跳过 {skipped} / 总分块 {total_chunks}")
    if not args.dry_run:
        try:
            r = requests.get(f"{SCRATCHPAD_API}/api/rag/stats", headers=HEADERS, timeout=10)
            if r.status_code == 200:
                print(f"scratchpad 当前: {json.dumps(r.json(), ensure_ascii=False)}")
        except Exception:
            pass
    print("=" * 70)


if __name__ == "__main__":
    main()
