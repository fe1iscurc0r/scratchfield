# sentinel-osint-勘察报告

> 工单：SPEC-09 第五批 M 线 · OSINT 采集器勘察 + MCP 封装
> 范围：17 采集器逐一评估（能力/依赖/许可/封装成本/纯 Python?），选中 3 个做 MCP 封装
> 状态：已完成（2026-08-24）

## 一、选型口径

按工单硬约束逐项卡：
- **纯 Python 低依赖**：封装实现只允许 stdlib（不装 selenium/playwright/dnspython 等重依赖）
- **网络可 mock**：网络调用收敛到 `collectors/_net.py` 三原语（tcp/udp/http），离线可测
- **只读公开数据**：不要求 API key 的公开源优先（有 key 的标注"需 API key"）
- **降级纪律**：网络失败/超时 → `{"ok": False, "error": ...}` 永不抛错（照 `adapters/context7.py`）
- **接 K 线 schema**：成功载荷带 `ingest`（entities/edges），etype 走白名单
  `actor/tool/infra/indicator`，rel 走 `uses/indicates/alias_of/observed_at`

## 二、17 采集器评估表

| # | 采集器 | 能力 | 依赖 | 许可 | 封装成本 | 纯 Python? |
|---|--------|------|------|------|----------|-----------|
| 1 | WHOIS（RFC 3912 / RDAP） | 域名注册人/注册局/到期日/NS 归属 | stdlib socket | 公开数据 | 低（TCP:43 文本解析） | ✅ 已封装 `whois_lookup` |
| 2 | DNS 解析记录 | A/AAAA/NS/MX/TXT/CNAME | stdlib socket（自写最小客户端） | 公开数据 | 中（二进制包构造+解析） | ✅ 已封装 `dns_lookup` |
| 3 | 证书透明度（CT Log） | 域签发证书/签发者/有效期 | stdlib urllib（crt.sh JSON） | 公开数据（crt.sh 免费） | 低（JSON 解析） | ✅ 已封装 `cert_lookup` |
| 4 | 子域枚举（被动） | 被动子域发现（CT 日志聚合） | urllib + crt.sh/otx 聚合 | 公开数据 | 低（复用 cert_lookup 上游） | ✅（可做，cert_lookup 已覆盖主链路） |
| 5 | 被动 DNS（PDNS） | 历史解析记录/IP 变化轨迹 | SecurityTrails API（key）/ VirusTotal（key） | 需 API key | 中（key 管理+配额） | ⚠️ 需 key，纯 Python 可做 |
| 6 | IP 归属/定位 | ASN/ISP/地理位置/开放端口 | ip-api（免费 JSON）或 MaxMind GeoIP | 免费层有限 | 低 | ✅（可做，urllib 即可） |
| 7 | ASN 归属 | AS 号 ↔ 网段 ↔ 组织映射 | Team Cymru / RIPE API | 公开数据 | 低 | ✅（可做） |
| 8 | 端口扫描 | 开放端口/服务 banner | nmap（二进制）/ python-nmap | 工具 GPL | 中（本地扫描有侵入性） | ❌ 需 nmap 二进制，不满足低依赖 |
| 9 | 威胁情报摘要 | 威胁标签/家族/关联攻击 | AlienVault OTX（key）/ MISP（部署） | 需 API key | 中 | ⚠️ 需 key 或自建实例 |
| 10 | URL/沙箱扫描 | 恶意 URL 判定/行为报告 | urlscan.io（key）/ VirusTotal（key） | 需 API key | 中（配额+报告解析） | ⚠️ 需 key |
| 11 | 恶意样本哈希 | 样本哈希情报/家族标签 | MalwareBazaar（公开 API） | 公开 API | 低 | ✅（可做，urllib 即可） |
| 12 | MX/邮件头分析 | 邮件基础设施/SPF/DKIM | stdlib（dns 采集器扩展 TXT 段） | 公开数据 | 低 | ✅（dns_lookup 已带 TXT） |
| 13 | 社交账号关联 | 跨平台用户名/profile 关联 | 平台 API（多数需 auth） | 平台条款各异 | 高（反爬+条款风险） | ❌ 不做（条款/反爬成本高） |
| 14 | 泄露数据查询 | 凭据泄露/数据泄露范围 | HIBP（需 key）/ 暗网源（灰区） | 需 API key/灰区 | 中 | ⚠️ 灰色地带，仅存证不主动采集 |
| 15 | 网站指纹 | 技术栈/WAF/CDN 识别 | Wappalyzer（npm）/ WhatWeb（ruby） | 混合许可 | 中（跨语言运行时） | ❌ 非纯 Python 生态 |
| 16 | 网页快照 | 历史页面快照/归档检索 | archive.org 公开 API | 公开 API | 低 | ✅（可做，urllib 即可） |
| 17 | 地理位置（GeoIP） | IP 经纬度/时区/城市 | MaxMind 数据库（专有）或 ip-api | 免费层有限 | 低 | ✅（可做，ip-api 免费层） |

### 封装结论

- **选中并已实现**（#1/#2/#3）：**WHOIS + DNS + 证书透明度** —— 三个都是纯 stdlib、
  零 key、零重依赖，覆盖域名侧情报三大面（归属 / 解析 / 证书），互相独立可叠加。
- **顺位后备**（未封装，留待下批）：#4 子域枚举（复用 cert_lookup 上游）、#6 IP 归属、
  #11 MalwareBazaar、#16 网页快照 —— 同为纯 stdlib 低成本，但工单只要求 2~3 个。
- **排除**：#8 端口扫描（需 nmap 二进制）、#13 社交账号（反爬/条款）、#15 网站指纹
  （跨语言运行时）、#14 泄露数据（灰区）—— 违反"纯 Python 低依赖/只读公开数据"硬约束。

## 三、实现位置与接入

| 采集器 | 模块 | 入口 | 网络原语 |
|--------|------|------|----------|
| WHOIS | `collectors/whois.py` | `whois_lookup(domain, server=..., timeout=...)` | `_net.tcp_query` |
| DNS | `collectors/dns.py` | `dns_lookup(domain, rtypes=(...), resolver=..., timeout=...)` | `_net.udp_query` |
| 证书 | `collectors/cert.py` | `cert_lookup(domain, timeout=...)` | `_net.http_get` |
| 公共层 | `collectors/_net.py` | `tcp_query / udp_query / http_get` | 均可 mock |

- 成功返回统一为 `{"ok": True, "source", "domain", "ts", "data", "ingest"}`，
  其中 `ingest` 为 `{"entities": [...], "edges": [...]}`，直接对齐
  `bridge.py` 的 `intel_ingest(entities, edges)` 输入契约（etype=infra/indicator）。
- 失败返回统一为 `{"ok": False, "source", "domain", "data": {}, "ingest": {...空}, "error"}`。
- 时间戳统一 ISO-8601 UTC（`datetime.now(UTC)`，对齐 K 线 schema 契约）。

## 四、验收清单

- [x] 17 采集器逐一评估（上表 17 行）
- [x] 选中 3 个纯 Python 低依赖采集器并封装（whois/dns/cert）
- [x] `mcpserver/sentinel_intel/collectors/` 至少 3 个 .py（含 `__init__.py`，实为 5 个）
- [x] 网络失败/超时降级 `ok=False` 不抛错（照 context7.py 降级模式）
- [x] 采集结果带 ingest 载荷可直接喂 `intel_ingest`（接 K 线 schema）
- [x] `tests/test_collectors.py` 6 mock 用例全过（`pytest .../test_collectors.py -q`）
