"""``cluster_sim`` · 节点空间分簇模拟器（工单 243 任务一）。

对外入口
--------
- ``generate`` / ``grid_topology`` / ``random_topology`` / ``lora_deployment_topology``
  —— 拓扑生成（``grid`` / ``random`` / ``lora_deployment``）。
- ``cluster_report`` / ``build_clusters`` —— 阈值 + 跳数分簇，输出
  ``{clusters: [{id, members, health}], unstable_pairs: [...]}``。
- ``load_config`` / ``simulate`` —— YAML 配置读取与一次完整仿真。

与 ``mcpserver/rf_brain/rlnc/clustering.py`` 的分工见 ``cluster.py`` 顶部说明：
本包按**空间可达性**分**节点**，那个模块按**链路可靠度**分**链路**，不同层、不可互替。
"""
from __future__ import annotations

from .cluster import (
    DEFAULT_MAX_HOPS,
    DEFAULT_UNSTABLE_MARGIN_DB,
    Cluster,
    Link,
    adjacency,
    bfs_hops,
    build_clusters,
    cluster_report,
    rssi_links,
    unstable_pairs,
)
from .config import (
    DEFAULT_AREA,
    DEFAULT_CONFIG,
    DEFAULT_NODES,
    DEFAULT_RSSI_THRESHOLD_DBM,
    DEFAULT_SIMULATE_DURATION_H,
    apply_failure,
    build_topology,
    load_config,
    normalize_config,
    simulate,
)
from .node import (
    DEFAULT_FREQ_HZ,
    DEFAULT_PATH_LOSS_EXPONENT,
    DEFAULT_TX_POWER_DBM,
    Node,
    free_space_path_loss_db,
    max_range_m,
    path_loss_db,
    rssi_dbm,
)
from .topology import GRID, LORA_DEPLOYMENT, RANDOM, TOPOLOGY_KINDS, Topology, generate

__all__ = [
    "DEFAULT_AREA",
    "DEFAULT_CONFIG",
    "DEFAULT_FREQ_HZ",
    "DEFAULT_MAX_HOPS",
    "DEFAULT_NODES",
    "DEFAULT_PATH_LOSS_EXPONENT",
    "DEFAULT_RSSI_THRESHOLD_DBM",
    "DEFAULT_SIMULATE_DURATION_H",
    "DEFAULT_TX_POWER_DBM",
    "DEFAULT_UNSTABLE_MARGIN_DB",
    "GRID",
    "LORA_DEPLOYMENT",
    "RANDOM",
    "TOPOLOGY_KINDS",
    "Cluster",
    "Link",
    "Node",
    "Topology",
    "adjacency",
    "apply_failure",
    "bfs_hops",
    "build_clusters",
    "build_topology",
    "cluster_report",
    "free_space_path_loss_db",
    "generate",
    "load_config",
    "max_range_m",
    "normalize_config",
    "path_loss_db",
    "rssi_dbm",
    "rssi_links",
    "simulate",
    "unstable_pairs",
]
