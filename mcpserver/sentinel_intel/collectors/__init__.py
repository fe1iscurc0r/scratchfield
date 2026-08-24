"""collectors — OSINT 采集器 MCP 封装（SPEC-09 第五批 M 线）。

三个纯 Python 低依赖采集器（全 stdlib，零第三方依赖，离线可测）：
- whois_lookup(domain)：WHOIS 协议（RFC 3912，socket TCP:43，默认 whois.iana.org）
- dns_lookup(domain) ：最小 DNS 客户端（UDP:53，A/AAAA/NS/MX/TXT，自解析不依赖系统）
- cert_lookup(domain)：证书透明度日志（crt.sh JSON API，urllib）

降级纪律（照 adapters/context7.py）：网络失败/超时/解析异常一律返回
{"ok": False, "error": ...}，永不抛错；成功载荷带 ingest（entities/edges，
对齐 bridge.py intel_ingest 输入结构，etype 走 K 线 schema 白名单 infra/
indicator），可直接喂 IntelBridge 入库。

硬约束：不引重依赖（不装 selenium/playwright）；只读公开数据；
网络调用全部收敛到 _net.py 原语，可被 unittest.mock 替换（离线可测）。
"""
