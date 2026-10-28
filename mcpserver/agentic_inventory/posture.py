"""置信度分级与风险姿态（工单249 · 方法借自 karmine05/agentic-detector）。

上游那张 `ai_tools` 表最值得学的两条方法论**不是**它的表结构，而是：

1. **多信号 + 置信度分级**（而不是关键词匹配）：
   > "Agent discovery is multi-signal, not keyword-only. ... **Name matching alone never creates a row.**"
   分级：catalog=100 / 多信号 70-99 / 强工作区形状 40-69 / 边缘 30-39 / **低于 30 不出行**。
   每一行的 `evidence` 字段是**可核对的信号令牌**（如 `catalog,binary,running,tool_home`）。

2. **风险姿态是静态推断的，且每条风险都有判据**：
   `remote_fetch_exec`（经 npx/uvx 启动 ⇒ 每次拉起都取新代码）、`unpinned_dependency`（且版本未钉）、
   `mcp_shell_exec` / `mcp_fs_write`（推断的能力）、`plaintext_secret`、`cleartext_endpoint`、
   `injection_markers` / `hidden_unicode`（指令文件）……
   并且**只读不执行**："It never executes a discovered binary, and never connects to an MCP server
   to enumerate its tools."

本模块把这两条落到**本仓的 agent 资产**上（不是主机扫描 —— 见 README §边界）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: 置信度分档（照上游的 bands，档名与语义对齐）
BAND_CATALOG = "catalog"        # 100：在册且有完整签名（我们这里 = manifest + entryPoint 可解析）
BAND_HIGH = "high"              # 70-99：多信号
BAND_MEDIUM = "medium"          # 40-69：强形状（如目录结构齐全但契约不完备）
BAND_LOW = "low"                # 30-39：边缘
BAND_NOT_EMITTED = "not_emitted"  # <30：**不出行**（照上游纪律）

#: 各信号的权重。**权重之和即置信度上限** —— 刻意让"只有名字"拿不到分。
SIGNAL_WEIGHTS: dict[str, int] = {
    "manifest": 40,          # 有 agent-manifest.json（这是本仓 agent 的"户口本"）
    "entrypoint_resolves": 30,   # entryPoint 能**静态**落到真实文件 + 真实类
    "dispatcher_match": 15,      # manifest 声明的 command 与代码里的派发表逐项一致
    "handoff_contract": 10,      # entryPoint 的类有 handle_handoff（注册器硬要求）
    "tests": 5,                  # 有对应测试文件
    "readme": 5,                 # 有 README
    "requirements_declared": 5,  # 有 requirements.txt（哪怕内容是"零依赖"）
}

#: 低于此分**不出行**（照上游 "Not emitted < 30"）
MIN_EMITTED = 30

#: 风险令牌 → (判据一句话, 适用范围)
#: ⚠️ **这张表不许有"愿望"** —— 每个键都必须有真实产出点，否则报告里会出现一个
#:    永远不亮、却好像"在监控"的令牌（实测踩过：`world_writable` 只登记了没实现，
#:    已删；守卫见 `tests/test_agentic_inventory.py::test_risk_registry_has_no_aspirational_entries`）。
RISK_TOKENS: dict[str, str] = {
    "remote_fetch_exec": "经 npx/uvx/bunx/pnpx 启动 ⇒ 每次拉起都从远端取代码执行",
    "unpinned_dependency": "上一条且版本未钉（@latest 或省略版本）⇒ 供应链可变",
    "cleartext_endpoint": "远程端点走明文 http://（凭证与内容可被旁路读取）",
    "secret_var_name_in_docs": "文档/依赖声明里出现**密钥形状的变量名**（比上游的"
                              " plaintext_secret 弱一档：本模块**不读值**，故无法断言值是否真在盘上）",
    "injection_markers": "指令文件含 prompt-injection / 数据外传类短语",
    "hidden_unicode": "指令文件含零宽/Unicode-Tag 等**不可见字符**（可夹带指令）",
}

#: 工程质量标记（**刻意与安全风险分开** —— 混在一起会让两者都失去意义）
QUALITY_TOKENS: dict[str, str] = {
    "no_tests": "模块目录下没有测试文件",
    "no_readme": "模块目录下没有 README",
    "no_requirements": "模块目录下没有 requirements.txt",
    "dispatcher_mismatch": "manifest 声明的 command 与代码派发表不一致",
    "no_handoff": "entryPoint 的类没有 handle_handoff（注册器会拒）",
}


@dataclass
class Posture:
    """一条行的姿态：置信度 + 证据 + 风险/质量标记。"""

    confidence: int = 0
    signals: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)

    @property
    def band(self) -> str:
        c = self.confidence
        if c >= 100:
            return BAND_CATALOG
        if c >= 70:
            return BAND_HIGH
        if c >= 40:
            return BAND_MEDIUM
        if c >= MIN_EMITTED:
            return BAND_LOW
        return BAND_NOT_EMITTED

    @property
    def emitted(self) -> bool:
        """低于 `MIN_EMITTED` **不出行**（照上游纪律：只有名字不构成一行）。"""
        return self.confidence >= MIN_EMITTED

    def as_dict(self) -> dict:
        return {
            "confidence": self.confidence,
            "band": self.band,
            "evidence": ",".join(self.signals),
            "risk_flags": ",".join(self.risk_flags),
            "quality_flags": ",".join(self.quality_flags),
        }


def score(signals: dict[str, bool]) -> Posture:
    """按信号表算置信度。

    ⚠️ 未知信号**直接报错**（不静默忽略）—— 否则加了一条信号却忘了配权重时，
    置信度会**悄悄偏低**，而没有人会发现。
    """
    unknown = sorted(set(signals) - set(SIGNAL_WEIGHTS))
    if unknown:
        raise KeyError(f"未配置权重的信号 {unknown}（可用：{sorted(SIGNAL_WEIGHTS)}）")
    post = Posture()
    for name, present in sorted(signals.items()):
        if present:
            post.confidence += SIGNAL_WEIGHTS[name]
            post.signals.append(name)
    return post


# --------------------------------------------------------------------------- 风险判定


_LAUNCHERS = re.compile(r"\b(npx|uvx|bunx|pnpx)\b")
#: 一个包规格：可选 scope + 名字 + 可选 `@版本`
#: ⚠️ 包名必须限 **ASCII**：Python 的 `\w` 默认匹配中文，不加限制时
#:    「本模块只经 npx 调用」里的「调用」会被当成包名 ⇒ 假阳性（实测踩过）。
_PKG_SPEC = re.compile(
    r"(@[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*|[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?:@([A-Za-z0-9][A-Za-z0-9.+-]*))?")


#: 包规格两侧可能出现的「包裹符」（markdown/代码/表格里到处是）
_WRAPPERS = "`\"'()[]{}|,;:"


def _first_pkg_spec(tail: str) -> tuple[str, int] | None:
    """取 `tail` 里**紧接着的第一个**包规格 token（跳过 `-` 标志、剥掉包裹符）。

    ⚠️ 这一条是整段判定的关键，两个坑都实测踩过：
    ① 真实命令行常带标志：``npx -y @toolknit/cli@2.3.1`` —— 若直接取"第一个 token"会拿到 ``-y``，
       把**已钉**的调用误判成未钉；
    ② 文档/表格里会有**纯提及**（如 ``| Node ≥ 20.12.0 + `npx` |``）—— 那**不是**依赖声明，
       必须**不产出任何判定**（取不到包规格 ⇒ 返回 None ⇒ 既不报已钉也不报未钉）。
    """
    cur = ""
    for i, ch in enumerate(tail):
        if ch in " \t" or ch in _WRAPPERS or ch in ">":
            if cur:
                tok = _clean(cur)
                return (tok, i) if tok else None
            continue
        cur += ch
    if cur:
        tok = _clean(cur)
        return (tok, len(tail)) if tok else None
    return None


def _clean(token: str) -> str | None:
    """剥掉 token 两端的包裹符；`-` 开头的是 CLI 标志 ⇒ 返回 None 表示"继续找下一个"。"""
    t = token.strip(_WRAPPERS + "<>")
    if not t or t.startswith("-"):
        return None
    return t


def fetch_exec_flags(text: str) -> tuple[bool, bool]:
    """扫描"经 npx/uvx/bunx/pnpx 拉起"的痕迹，返回 ``(有远程取码, 有未钉版本)``。

    判定规则（只在**能认出包规格**时才下结论）：
    - 取启动关键字之后**紧接着的第一个**包规格（跳过 `-y` 之类的标志）
    - 该规格带 `@<版本>` 且版本不是 `latest` ⇒ **已钉**
    - 否则（无版本 / `@latest`）⇒ **未钉**
    - **取不到包规格就不判定**（如文档表格里的纯提及）—— 宁可漏报，也不造假阳性
    """
    found = unpinned = False
    for m in _LAUNCHERS.finditer(text or ""):
        found = True
        tail = text[m.end():m.end() + 160]
        got = _first_pkg_spec(tail)
        guard = 0
        while got is None and guard < 4:               # 跳过 `-y` 之类的标志继续找
            guard += 1
            if _LAUNCHERS.search(tail):
                break
            i = tail.find(" ")
            if i < 0:
                break
            tail = tail[i + 1:]
            got = _first_pkg_spec(tail)
        if got is None:
            continue                                   # 认不出包 ⇒ **不判定**
        tok, pos = got
        if "<" in tok or ">" in tok:
            continue                                   # `pkg@<ver>` 是占位符 ⇒ **不判定**
        spec = _PKG_SPEC.match(tok)
        if not spec:
            continue
        version = spec.group(2)
        if version and version.lower() != "latest":
            continue                                   # 已钉（`pkg@1.2.3`）
        if version is None:
            # 「版本分开写」：`pkg @1.2.3` / `pkg @ 1.2.3`
            after = tail[pos:pos + 20]
            m2 = re.search(r"@\s*([A-Za-z0-9][A-Za-z0-9.+-]*)", after)
            if m2 and m2.group(1).lower() != "latest":
                continue                               # 也算钉了
        unpinned = True
    return found, unpinned


# --- 文本类判据
# ⚠️ 这一组**只吃文本、不碰文件系统、不发网络请求** —— 是本模块"只读不执行"纪律的最小单位。

#: 密钥形状的**变量名**（只认名字，不取值）。
#: 要求全大写 + 下划线/数字，且含一个"密钥词"。这样 `sk-ant-REALSECRET` 里那个
#: `REALSECRET`（出现在**值**侧）不会被误认成名字（见 `secret_var_names` 的键位切分）。
_SECRETISH = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)[A-Z0-9_]*)\b")

#: 明文端点：只认 `http://`（`https://` **不算**风险 —— 否则满仓的文档链接都会变成红旗）。
_CLEARTEXT = re.compile(r"http://[^\s\"'<>)\]]+", re.IGNORECASE)

#: 指令文件里的注入 / 外传短语（中英混排的仓里只认英文短语：中文同义表述太发散，会假阳性）
_INJECTION = re.compile(
    r"ignore (?:all )?(?:previous|prior) instructions"
    r"|disregard (?:the )?(?:above|previous)"
    r"|exfiltrat"
    r"|send (?:the )?(?:contents|data) to"
    r"|do not tell the user",
    re.IGNORECASE)

#: 不可见字符：零宽（U+200B-200F）+ 双向控制（U+202A-202E）+ 词连接符（U+2060-2064）
#: + Unicode Tag（U+E0000-E007F，可整段夹带 ASCII 指令而肉眼不可见）。
_INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\U000e0000-\U000e007f]")


def scan_text_risks(text: str, *, kind: str) -> list[str]:
    """从一段文本里提取风险令牌。`kind` ∈ {manifest, config, instruction}。

    ⚠️ **`plaintext_secret` 只报变量名，绝不把值写进结果** —— 否则审计工具自己就成了泄漏源。
    """
    out: list[str] = []
    if not text:
        return out
    if kind in ("manifest", "config"):
        fetched, unpinned = fetch_exec_flags(text)
        if fetched:
            out.append("remote_fetch_exec")
        if unpinned:
            out.append("unpinned_dependency")
        if _CLEARTEXT.search(text):
            out.append("cleartext_endpoint")
        if secret_var_names(text):
            # ⚠️ 只报"名字出现在文档里"，**不**声称"值在盘上"（那是上游 plaintext_secret 的强判据，
            #    需要读配置值 —— 本模块刻意不读值，所以名字必须弱一档，别 over-claim）。
            #    判定复用 `secret_var_names` ⇒ 两处语义**不会分叉**（这也是上面的坑的根治）。
            out.append("secret_var_name_in_docs")
    if kind == "instruction":
        if _INJECTION.search(text):
            out.append("injection_markers")
        if _INVISIBLE.search(text):
            out.append("hidden_unicode")
    return sorted(set(out))


def secret_var_names(text: str) -> list[str]:
    """取出密钥形状的**变量名**（**绝不返回值**）。

    ⚠️ 必须在**键位**上找名字 —— 直接在整段文本里跑正则会**把值报成名字**：
    实测 `ANTHROPIC_API_KEY=sk-ant-REALSECRET` 里的 `REALSECRET` 因为含 `SECRET` 被匹配上了
    （那正是"审计工具自己变成泄漏源"）。所以先按 `=`/`:` 切成键位侧，只在键位侧找。
    """
    out: set[str] = set()
    for line in (text or "").splitlines():
        parts = re.split(r"[:=]", line, maxsplit=1)
        key_side = parts[0]
        for m in _SECRETISH.finditer(key_side):
            out.add(m.group(1))
        if len(parts) == 1:                     # 没有 `=`/`:` 的行整行都算"名字侧"（如文档里的提及）
            for m in _SECRETISH.finditer(line):
                out.add(m.group(1))
    return sorted(out)


def cleartext_endpoints(text: str) -> list[str]:
    """取出明文 http 端点（同样只读出来给人看，不做任何连接）。"""
    return sorted(set(_CLEARTEXT.findall(text or "")))
