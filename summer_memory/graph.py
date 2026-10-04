import json as _json
import logging
import os
import sys
from typing import Optional

from charset_normalizer import from_path

try:
    from py2neo import Graph as Py2NeoGraph
    from py2neo import Node, Relationship
    from py2neo.errors import ServiceUnavailable
except ImportError:
    Py2NeoGraph = None  # type: ignore[assignment]
    Node = None  # type: ignore[assignment]
    Relationship = None  # type: ignore[assignment]
    ServiceUnavailable = Exception  # type: ignore[assignment]


# 添加项目根目录到路径，以便导入 config
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

logger = logging.getLogger(__name__)

_graph: Py2NeoGraph | None = None
_graph_connection_failed = False

NEO4J_URI: str | None = None
NEO4J_USER: str | None = None
NEO4J_PASSWORD: str | None = None
NEO4J_DATABASE: str | None = None
GRAG_ENABLED = False


class Graph:
    """兼容旧接口的轻量封装。"""

    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        if Py2NeoGraph is None:
            raise RuntimeError("py2neo 未安装，请运行 pip install py2neo 或禁用图数据库功能")
        self.driver = Py2NeoGraph(uri, auth=(user, password), name=database)

    def check_connection(self) -> bool:
        try:
            _ = self.driver.service.kernel_version
            return True
        except (ServiceUnavailable, Exception):
            return False

    def close(self) -> None:
        # py2neo 没有显式 close，这里仅释放引用以兼容旧调用方。
        self.driver = None


def _load_config() -> None:
    global NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE, GRAG_ENABLED

    if NEO4J_URI is not None:
        return

    try:
        from system.config import config

        GRAG_ENABLED = config.grag.enabled
        NEO4J_URI = config.grag.neo4j_uri
        NEO4J_USER = config.grag.neo4j_user
        NEO4J_PASSWORD = config.grag.neo4j_password
        NEO4J_DATABASE = config.grag.neo4j_database
        return
    except Exception as exc:
        print(f"[GRAG] 无法从 config 模块读取 Neo4j 配置: {exc}", file=sys.stderr)

    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
        charset_results = from_path(config_path)
        best_match = charset_results.best() if charset_results else None
        encoding = best_match.encoding if best_match and best_match.encoding else "utf-8"
        with open(config_path, encoding=encoding) as handle:
            raw_config = _json.load(handle)
        grag_cfg = raw_config.get("grag", {})
        NEO4J_URI = grag_cfg.get("neo4j_uri")
        NEO4J_USER = grag_cfg.get("neo4j_user")
        NEO4J_PASSWORD = grag_cfg.get("neo4j_password")
        NEO4J_DATABASE = grag_cfg.get("neo4j_database")
        GRAG_ENABLED = grag_cfg.get("enabled", True)
    except Exception as exc:
        print(f"[GRAG] 无法从 config.json 读取 Neo4j 配置: {exc}", file=sys.stderr)
        GRAG_ENABLED = False


def get_graph() -> Py2NeoGraph | None:
    global _graph, _graph_connection_failed, GRAG_ENABLED

    if _graph_connection_failed:
        return None

    if _graph is not None:
        return _graph

    if Py2NeoGraph is None:
        GRAG_ENABLED = False
        _graph_connection_failed = True
        return None

    _load_config()

    if not (GRAG_ENABLED and NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD):
        _graph_connection_failed = True
        return None

    try:
        _graph = Py2NeoGraph(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            name=NEO4J_DATABASE,
        )
        _ = _graph.service.kernel_version
        return _graph
    except ServiceUnavailable:
        print("[GRAG] 未能连接到 Neo4j，图数据库功能已禁用。", file=sys.stderr)
    except Exception as exc:
        print(f"[GRAG] Neo4j 连接失败: {exc}", file=sys.stderr)

    _graph = None
    GRAG_ENABLED = False
    _graph_connection_failed = True
    return None


def _get_triples_file() -> str:
    from system.config import get_data_dir

    return str(get_data_dir() / "knowledge_graph" / "triples.json")


TRIPLES_FILE = _get_triples_file()


def load_triples():
    try:
        with open(TRIPLES_FILE, encoding="utf-8") as handle:
            return set(tuple(item) for item in _json.load(handle))
    except FileNotFoundError:
        return set()


def save_triples(triples) -> None:
    os.makedirs(os.path.dirname(TRIPLES_FILE), exist_ok=True)
    with open(TRIPLES_FILE, "w", encoding="utf-8") as handle:
        _json.dump(list(triples), handle, ensure_ascii=False, indent=2)


def store_triples(new_triples) -> bool:
    """存储三元组到本地文件和 Neo4j。"""
    try:
        valid_triples = {
            tuple(item)
            for item in new_triples
            if isinstance(item, (list, tuple))
            and len(item) == 3
            and all(isinstance(part, str) and part.strip() for part in item)
        }
        if not valid_triples:
            logger.warning("未收到有效三元组，跳过存储")
            return False

        all_triples = load_triples()
        all_triples.update(valid_triples)
        save_triples(all_triples)

        graph = get_graph()
        if graph is None:
            logger.info("跳过 Neo4j 存储（未启用），已保存 %s 个三元组到文件", len(valid_triples))
            return True

        success_count = 0
        for head, rel, tail in valid_triples:
            try:
                head_node = Node("Entity", name=head)
                tail_node = Node("Entity", name=tail)
                relation = Relationship(head_node, rel, tail_node)
                graph.merge(head_node, "Entity", "name")
                graph.merge(tail_node, "Entity", "name")
                graph.merge(relation)
                success_count += 1
            except Exception as exc:
                logger.error("存储三元组失败: %s-%s-%s, 错误: %s", head, rel, tail, exc)

        logger.info("成功存储 %s/%s 个三元组到 Neo4j", success_count, len(valid_triples))
        return success_count > 0
    except Exception as exc:
        logger.error("存储三元组失败: %s", exc)
        return False


def get_all_triples():
    return load_triples()


# 噪声过滤：禁止返回含人称代词的不可用三元组（我/你/它等）
_PRONOUN_TERMS = {"我", "你", "它", "他", "她", "我们", "你们", "他们", "她们", "它们"}


def _has_pronoun(triple) -> bool:
    """判断三元组是否含人称代词。含代词的三元组信息量低，一律不返回。"""
    try:
        head, rel, tail = triple
    except (TypeError, ValueError):
        return True
    return (
        head.strip() in _PRONOUN_TERMS
        or rel.strip() in _PRONOUN_TERMS
        or tail.strip() in _PRONOUN_TERMS
    )


def query_graph_by_keywords(keywords):
    # Neo4j 不可用时回退到本地文件（triples.json）搜索，保证双写数据仍可检索
    graph = get_graph()
    if graph is None:
        return _query_triples_from_file(keywords)

    results = []
    seen = set()
    query = """
    MATCH (e1:Entity)-[r]->(e2:Entity)
    WHERE e1.name CONTAINS $kw OR e2.name CONTAINS $kw OR type(r) CONTAINS $kw
    RETURN e1.name AS head, type(r) AS relation, e2.name AS tail
    LIMIT 5
    """

    for kw in keywords:
        if not isinstance(kw, str) or not kw.strip():
            continue
        try:
            rows = graph.run(query, kw=kw.strip()).data()
        except Exception as exc:
            logger.error("按关键词查询图谱失败: %s, 错误: %s", kw, exc)
            continue

        for row in rows:
            triple = (row["head"], row["relation"], row["tail"])
            # 禁止返回含人称代词的噪声三元组
            if _has_pronoun(triple):
                continue
            if triple not in seen:
                seen.add(triple)
                results.append(triple)

    return results


def _query_triples_from_file(keywords, limit=5):
    """Neo4j 不可用时回退到 triples.json 文件搜索。

    匹配策略：精确匹配（关键词 == 实体/关系名）优先，CONTAINS 模糊匹配兜底；
    禁止返回含人称代词（我/你/它）的噪声三元组。
    """
    triples = load_triples()
    if not triples:
        return []

    norm_keywords = [kw.strip() for kw in keywords if isinstance(kw, str) and kw.strip()]

    exact = []
    fuzzy = []
    for kw in norm_keywords:
        for triple in triples:
            if _has_pronoun(triple):
                continue
            head, rel, tail = triple
            if kw in (head, tail, rel):
                if triple not in exact:
                    exact.append(triple)
            elif kw in head or kw in tail or kw in rel:
                if triple not in fuzzy:
                    fuzzy.append(triple)

    # 精确匹配优先，CONTAINS 模糊作为 fallback；跨关键词去重并限制返回条数
    results = []
    seen = set()
    for triple in exact + fuzzy:
        if triple in seen:
            continue
        seen.add(triple)
        results.append(triple)
        if len(results) >= limit:
            break
    return results
