"""判例导入器（法学领域包）— 本地导出文件 → papers 一键入库。

卷163 交付。数据来源为**用户自购商业数据库的本地导出文件**
（北大法宝 / 威科先行个人订阅，允许付费用户批量导出 Word/PDF/Excel）
与官方开放法规库。本模块**不含任何判例爬虫**。

管线
----
```
上传文件(.docx/.pdf/.xlsx)
  → 提取纯文本（docx: python-docx；pdf: docling；xlsx: openpyxl 表头映射）
  → 规则抽取（纯正则，不用 LLM）：案号/法院/审理程序/裁判日期/案由/当事人
  → 入库 papers（law 包 id_fields: flk_id / case_no）
  → 失败文件写入 _queue/ 待人工补录，整批不炸
```

案号规范依据
------------
《人民法院民事裁判文书制作规范》（法〔2016〕221号）与
《关于修改〈关于人民法院案件案号的若干规定〉的决定》（法〔2018〕335号）：

    案号 = "(" + 收案年度 + ")" + 法院代字 + [专门审判代字] + 类型代字 + 案件编号 + "号"

- 收案年度：4 位阿拉伯数字
- 法院代字：中文汉字 + 阿拉伯数字（如 ``最高法`` / ``京01`` / ``粤03`` / ``沪``）
- 专门审判代字：1 个中文汉字（如专利知识产权案件的 ``知``）
- 类型代字：中文汉字，可多字（``刑``/``民``/``行``/``执``/``赔``/``破``/``监``，
  以及 ``民终``/``民初``/``民申``/``行申``/``刑终`` 等组合）
- 案件编号：阿拉伯数字
- 括号全角 ``（）`` 与半角 ``()`` 都可能出现，均需匹配

真实样例：``(2019)最高法民终1524号`` / ``（2019）最高法民再152号`` /
``(2018)最高法行申3190号`` / ``(2015)海行民初字第5号``
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: 本包目录（domains/law/）。
PACK_DIR = Path(__file__).resolve().parent.parent

#: 抽取失败文件的待补录队列目录。
QUEUE_DIR = PACK_DIR / "_queue"

#: 单批上传限制（工单 A1）。
MAX_FILES_PER_BATCH = 50
MAX_BATCH_BYTES = 200 * 1024 * 1024  # 200MB

#: 支持的扩展名。
SUPPORTED_SUFFIXES = (".docx", ".pdf", ".xlsx")


# ===========================================================================
# 文本解析（docx / pdf / xlsx）
# ===========================================================================


class ParseError(Exception):
    """文件无法解析为纯文本（含缺失可选依赖、格式损坏等）。"""


def parse_docx(path: Path) -> str:
    """用 python-docx 抽取 ``.docx`` 正文（段落 + 表格单元格）。

    python-docx 是本卷唯一新增依赖（工单已授权）。缺失时抛 ``ParseError``
    并给出可执行的安装提示，绝不静默返回空串。
    """
    try:
        import docx  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - 环境相关
        raise ParseError(
            "解析 .docx 需要 python-docx，请执行：uv pip install python-docx"
        ) from exc

    try:
        document = docx.Document(str(path))
    except Exception as exc:  # noqa: BLE001 - 统一转成 ParseError
        raise ParseError(f"无法打开 .docx：{exc}") from exc

    parts: list[str] = []
    for para in document.paragraphs:
        text = (para.text or "").strip()
        if text:
            parts.append(text)
    # 表格里的当事人信息也要（部分导出为表格）
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
            if cells:
                parts.append("　".join(cells))
    return "\n".join(parts)


def parse_pdf(path: Path) -> str:
    """用 docling（可选 pdf2md extra）抽取 ``.pdf`` 正文。

    复用 ``mcpserver/adapters/pdf2md_adapter`` 的 ``pdf2md_convert``。
    未安装 docling 时抛 ``ParseError``（明确提示安装 ``pdf2md`` extra），
    绝不静默跳过 —— 这样批量导入时该文件会进待补录队列并标明原因。
    """
    try:
        from mcpserver.adapters.pdf2md_adapter.adapter import pdf2md_convert
    except ImportError as exc:  # pragma: no cover - 环境相关
        raise ParseError(f"无法加载 pdf2md 适配器：{exc}") from exc

    result = pdf2md_convert(str(path))
    if not result.get("ok"):
        err = result.get("error") or "pdf2md 转换失败"
        if "docling" in str(err).lower() or "not installed" in str(err).lower():
            raise ParseError(
                f"解析 .pdf 需要 docling，请执行：uv pip install -e '.[pdf2md]'（{err}）"
            )
        raise ParseError(str(err))
    text = (result.get("markdown") or "").strip()
    if not text:
        raise ParseError("pdf2md 转换成功但未提取到文本（可能是扫描件，需 OCR）")
    return text


def parse_xlsx(path: Path) -> str:
    """用 openpyxl 抽取 ``.xlsx`` 内容（逐行拼接为文本）。

    商业数据库的批量导出常为「一行一案」的表格；这里把每行按键值对
    拼成文本，行与行之间用换行分隔，交给规则抽取复用。
    **注意**：多行表意味着多个判例，调用方应优先用 ``parse_xlsx_rows()``
    逐行独立抽取，而非把全文当单案（见 ``iter_cases_from_xlsx``）。
    """
    return "\n".join(row for row, _ in _xlsx_rows(path))


def _xlsx_rows(path: Path) -> list[tuple[str, dict[str, str]]]:
    """读取 xlsx，返回 ``[(行文本, {列头: 值}), ...]``（不含表头行）。"""
    try:
        from openpyxl import load_workbook  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - 环境相关
        raise ParseError("解析 .xlsx 需要 openpyxl，请执行：uv pip install openpyxl") from exc

    try:
        wb = load_workbook(filename=str(path), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"无法打开 .xlsx：{exc}") from exc

    out: list[tuple[str, dict[str, str]]] = []
    try:
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue
            header = [str(c).strip() if c is not None else "" for c in rows[0]]
            for row in rows[1:]:
                cells = [str(c).strip() if c is not None else "" for c in row]
                if not any(cells):
                    continue
                mapping = {
                    (header[i] if i < len(header) and header[i] else f"列{i + 1}"): cells[i]
                    for i in range(len(cells))
                    if cells[i]
                }
                line = "　".join(f"{k}：{v}" for k, v in mapping.items())
                out.append((line, mapping))
    finally:
        try:
            wb.close()
        except Exception:  # noqa: BLE001
            pass
    return out


def iter_cases_from_xlsx(path: Path) -> list[ExtractedCase]:
    """把 xlsx 的每一行独立抽取为一个判例（一行一案语义）。"""
    cases: list[ExtractedCase] = []
    for line, _mapping in _xlsx_rows(path):
        if line.strip():
            cases.append(extract_case(line))
    return cases


#: 扩展名 → 解析函数。
PARSERS: dict[str, Any] = {
    ".docx": parse_docx,
    ".pdf": parse_pdf,
    ".xlsx": parse_xlsx,
}


def parse_file(path: Path) -> str:
    """按扩展名分派解析器，返回纯文本。

    不支持的扩展名或不存在的文件 → ``ParseError``。
    """
    suffix = path.suffix.lower()
    if not path.exists():
        raise ParseError(f"文件不存在：{path}")
    parser = PARSERS.get(suffix)
    if parser is None:
        raise ParseError(
            f"不支持的格式 {suffix or '(无扩展名)'}，仅支持 {', '.join(SUPPORTED_SUFFIXES)}"
        )
    return parser(path)


# ===========================================================================
# 案件类型代字
# ===========================================================================

#: 单字类型代字（《人民法院案件案号的若干规定》）。
_SINGLE_TYPE_CODES = "刑民行执赔破监"

#: 多字类型代字（常见组合，按长度降序匹配，避免 ``民初`` 被 ``民`` 抢先）。
_MULTI_TYPE_CODES = (
    "民终", "民初", "民申", "民再", "民辖终", "民辖", "民提", "民监",
    "刑终", "刑初", "刑申", "刑再", "刑更", "刑监",
    "行终", "行初", "行申", "行再", "行赔", "行辖",
    "执复", "执异", "执监", "执恢", "执保",
    "赔终", "赔初",
    "破申", "破终", "破初",
    "知民初", "知行初", "知民终", "知行终",
)

#: 类型代字正则片段（多字优先 + 单字兜底，允许 1-4 个汉字）。
_TYPE_CODE_PATTERN = (
    "(?:"
    + "|".join(re.escape(c) for c in sorted(_MULTI_TYPE_CODES, key=len, reverse=True))
    + "|"
    + f"[{_SINGLE_TYPE_CODES}]"
    + "(?:[终初申再更监辖提赔]|\u5b57)?"
    + ")"
)

#: 案号：``(年度)法院代字(专门代字)类型代字编号号``。
#: - 括号全/半角均可
#: - 法院代字：汉字 + 可选数字（``最高法`` / ``京01`` / ``粤0305``）
#: - ``字第`` 是历史格式（如 ``海行民初字第5号``），可选
CASE_NO_RE = re.compile(
    rf"[（(]\s*(?P<year>\d{{4}})\s*[）)]"
    rf"\s*(?P<court>[\u4e00-\u9fa5]{{1,4}}\d{{0,4}})"
    rf"\s*(?P<type>{_TYPE_CODE_PATTERN})"
    rf"\s*(?:字第\s*)?"
    rf"(?P<num>\d{{1,6}})"
    rf"\s*号"
)

#: 宽松兜底：结构不符但明显是案号（含 4 位年度 + 号 + 含类型代字）。
CASE_NO_LOOSE_RE = re.compile(
    r"[（(]\s*(?P<year>\d{4})\s*[）)]\s*(?P<body>[^\s，。；、）)]{2,20}?号)"
)


# ===========================================================================
# 法院名称 / 审理程序 / 日期
# ===========================================================================

#: 法院名称（``XX省XX市中级人民法院`` / ``最高人民法院`` / ``XX县人民法院`` 等）。
#: 注意：中间那截 ``[\u4e00-\u9fa5]{0,4}`` **不能过宽**，否则会把正文动词
#: （「不服」）吞进法院名。用负向排除常见动词前缀。
COURT_NAME_RE = re.compile(
    r"(?<![不服系为与和及依按据经查])"
    r"((?:中华人民共和国)?"
    r"(?:最高|"
    r"[\u4e00-\u9fa5]{2,8}省|[\u4e00-\u9fa5]{2,8}自治区|"
    r"北京市|天津市|上海市|重庆市|"
    r"[\u4e00-\u9fa5]{2,8}市|[\u4e00-\u9fa5]{2,8}自治州|[\u4e00-\u9fa5]{2,8}地区|"
    r"[\u4e00-\u9fa5]{2,8}县|[\u4e00-\u9fa5]{2,8}区|"
    r"[\u4e00-\u9fa5]{2,8}自治县|[\u4e00-\u9fa5]{2,8}旗"
    r")?[\u4e00-\u9fa5]{0,4}"
    r"(?:高级|中级|基层)?人民法院)"
)

#: 专门法院（海事 / 铁路运输 / 知识产权 / 军事 / 金融）。
SPECIAL_COURT_RE = re.compile(
    r"((?:[\u4e00-\u9fa5]{2,8})?"
    r"(?:海事|铁路运输|知识产权|军事|金融|互联网|环境资源)"
    r"(?:中级|第一|第二|第三|第四|第五|第六)?法院)"
)

#: 审理程序。**顺序敏感**：更具体的程序放前面（再审/执行先于二审/一审），
#: 否则「申请再审」会被「上诉」误判为二审。
TRIAL_LEVEL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("再审", re.compile(r"(?:再审|审判监督|申请再审|再审申请)")),
    ("执行", re.compile(r"(?:执异|执复|执行异议|执行程序|强制执行|执行裁定)")),
    ("二审", re.compile(r"(?:二审|第二审|提起上诉|不服.{0,30}判决.{0,10}上诉|终审)")),
    ("一审", re.compile(r"(?:一审|第一审|初审|提起公诉|依法适用简易程序|适用普通程序)")),
)

#: 中文数字日期（``二〇二四年五月六日``）。
_CN_DIGITS = {
    "〇": 0, "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}

CHINESE_DATE_RE = re.compile(
    r"(?P<year>[〇零一二三四五六七八九]{4})\s*年\s*"
    r"(?P<month>[〇零一二三四五六七八九十]{1,3})\s*月\s*"
    r"(?P<day>[〇零一二三四五六七八九十]{1,3})\s*日"
)

#: 阿拉伯数字日期（``2024年5月6日`` / ``2024-05-06`` / ``2024/5/6``）。
NUMERIC_DATE_RE = re.compile(
    r"(?P<year>(?:19|20)\d{2})\s*[-年/]\s*(?P<month>\d{1,2})\s*[-月/]\s*(?P<day>\d{1,2})\s*日?"
)


# ===========================================================================
# 当事人 / 案由
# ===========================================================================

#: 当事人段首定位（诉讼地位称谓）。
#: 姓名部分不含连接词与标点 —— 当事人栏里人名/公司名不会含「因与系为」，
#: 借此与正文叙述句「上诉人XX因与YY……一案」区分开。
#: **称谓按长度降序排列**，否则「被告人」会被「被告」抢先匹配、把「人」当姓名。
PARTY_ROLE_RE = re.compile(
    r"(?:^|\n)\s*"
    r"(?P<role>"
    r"附带民事诉讼原告人|附带民事诉讼被告人|"
    r"再审申请人|再审被申请人|原审原告|原审被告|原审第三人|"
    r"申请执行人|被申请执行人|被执行人|公诉机关|"
    r"上诉人|被上诉人|申请人|被申请人|"
    r"原告人|被告人|原告|被告|第三人"
    r")"
    r"(?P<sep>[：:，,\s]|（[^）]*）)*"
    r"(?P<name>[^\n，。；：因与系为、（(]{1,30})"
)

#: 案由抽取：锚定 ``……一案`` 前的名词短语。
#: 关键观察：案由以「纠纷/责任/案件/争议」结尾，且**左边界**落在标点或
#: 连接词（与/因/系/为/和/及/诉）之后。句中「上诉人A与被上诉人B买卖合同
#: 纠纷一案」的案由 = 「买卖合同纠纷」。
#:
#: 实现路线（三次踩坑后定稿）：
#:   ❌ ``re.split(…|(?<=[与和及因系为诉]))``：零宽 lookbehind 会切开连接词
#:      词本身（「被上诉人」→「被」「上诉」「人…」）。
#:   ❌ 锚定正则 ``(?:称谓)?(?:人名)?案由尾词``：懒惰量词左边界不可控。
#:   ❌ 最短后缀扫描：恒返回「纠纷」这类 2 字尾词，丢掉案由主体。
#:   ✅ **称谓剥离为主、窗口右收为辅**：先按标点/连接词切窗，再**从左**剥掉
#:      当事人称谓与紧随人名，剩下以案由尾词结尾的部分即为案由。
CAUSE_LABEL_RE = re.compile(r"案\s*由\s*[：:]\s*(?P<cause>[^\n，。；]{2,40})")
#: 「……一案」锚点（案由短语的结束位置）。
_AN_YI_ANCHOR_RE = re.compile(r"(?:一案|案件)")
#: 窗口左边界：标点（切在标点后）。
_WINDOW_PUNCT_RE = re.compile(r"[，。；：、（）()【】\n\r\t\s]")
#: 当事人称谓（长的在前）。
_CAUSE_STOP = ("再审申请人", "被上诉人", "上诉人", "被申请人", "申请人",
               "被执行人", "公诉机关", "原告", "被告", "第三人", "当事人")
_STOP_RE = re.compile(rf"^(?:{'|'.join(sorted(_CAUSE_STOP, key=len, reverse=True))})")
#: 称谓后的人名 + 连接词（``李四与`` / ``赵六诉`` / ``甲公司与``）。
_PARTY_NAME_RE = re.compile(
    r"^[\u4e00-\u9fa5A-Za-z0-9（）()]{1,12}?[与和及因系为诉]"
)
#: 常见案由词根（用于消歧：优先匹配这些已知案由短语，而非猜测切分点）。
#: 取自《民事案件案由规定》与常见判决书表述，按长度降序。
_CAUSE_LEXICON = (
    "买卖合同纠纷", "商品房买卖合同纠纷", "房屋买卖合同纠纷",
    "房屋租赁合同纠纷", "租赁合同纠纷", "建设工程施工合同纠纷",
    "劳动争议", "劳动合同纠纷", "劳务合同纠纷",
    "民间借贷纠纷", "借款合同纠纷", "金融借款合同纠纷",
    "离婚纠纷", "离婚后财产纠纷", "抚养费纠纷", "赡养纠纷", "继承纠纷",
    "侵权责任纠纷", "机动车交通事故责任纠纷", "医疗损害责任纠纷",
    "生命权、身体权、健康权纠纷", "名誉权纠纷", "财产损害赔偿纠纷",
    "物业服务合同纠纷", "供用电合同纠纷", "承揽合同纠纷", "运输合同纠纷",
    "保证合同纠纷", "抵押合同纠纷", "质押合同纠纷", "定金合同纠纷",
    "股权转让纠纷", "公司决议效力确认纠纷", "股东资格确认纠纷",
    "证券虚假陈述责任纠纷", "票据纠纷", "保险纠纷",
    "著作权权属、侵权纠纷", "商标权权属、侵权纠纷", "专利权权属、侵权纠纷",
    "不正当竞争纠纷", "垄断纠纷",
    "行政处罚纠纷", "行政复议纠纷", "行政强制纠纷", "行政许可纠纷",
    "故意伤害罪", "盗窃罪", "诈骗罪", "受贿罪", "贪污罪", "走私罪",
    "组织、领导、参加黑社会性质组织罪",
)
#: 案由通用尾词（词典未命中时的兜底）。
_CAUSE_TAIL_WORDS = ("纠纷", "责任", "案件", "争议")


# ===========================================================================
# 数据模型
# ===========================================================================


@dataclass
class ExtractedCase:
    """从一份判决书抽取出的结构化字段。"""

    case_no: str = ""
    court: str = ""
    trial_level: str = ""
    judgment_date: str = ""
    cause_of_action: str = ""
    parties: list[str] = field(default_factory=list)
    content: str = ""
    #: 各字段是否成功抽取（供质量报告）。
    missing: list[str] = field(default_factory=list)

    def to_paper_dict(self, source: str = "manual", license_note: str = "") -> dict[str, Any]:
        """映射到 papers 表字段（law 包 id_fields: flk_id / case_no）。

        .. important::
            ``tags`` **留给卷164 的 AI 打标**（JSON 数组，如
            ``["案由分类:合同纠纷"]``），本函数**不写 tags**。
            规则抽取出的法院/程序/案由属于「元数据」而非「AI 标签」，
            统一落到 ``notes``（见 :meth:`_build_notes`），避免两种语义
            挤同一列、破坏 ``_JSON_ARRAY_FIELDS`` 的数组契约。
        """
        title = self.case_no or (self.parties[0] if self.parties else "未命名判例")
        return {
            "title": title,
            "case_no": self.case_no or None,
            "source": source,
            "license_note": license_note or None,
            "abstract": self.content[:2000] if self.content else None,
            "notes": self._build_notes(),
        }

    def _build_notes(self) -> str | None:
        parts: list[str] = []
        if self.court:
            parts.append(f"法院: {self.court}")
        if self.trial_level:
            parts.append(f"程序: {self.trial_level}")
        if self.cause_of_action:
            parts.append(f"案由: {self.cause_of_action}")
        if self.judgment_date:
            parts.append(f"裁判日期: {self.judgment_date}")
        if self.parties:
            parts.append("当事人: " + "、".join(self.parties))
        if self.missing:
            parts.append("未抽取: " + "、".join(self.missing))
        return "\n".join(parts) or None


@dataclass
class ImportResult:
    """单个文件的导入结果（工单 A4 要求的逐文件结构）。

    .. deprecated::
        保留以供外部（旧调用方）兼容；新代码请用 :class:`BatchItem`。
    """

    filename: str
    case_no: str = ""
    status: str = "ok"  # ok | queued | error
    error: str = ""
    paper_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "filename": self.filename,
            "case_no": self.case_no,
            "status": self.status,
        }
        if self.error:
            d["error"] = self.error
        if self.paper_id is not None:
            d["paper_id"] = self.paper_id
        return d


# ===========================================================================
# 案号抽取
# ===========================================================================


def extract_case_no(text: str) -> str:
    """从判决书正文抽取案号。

    优先精确匹配规范格式；失败时退回宽松匹配（仍是 ``(年度)……号`` 结构）。
    **保留原文的括号形式与空白形态**（案号是 law 包 id_field，须可回溯比对，
    不做全/半角归一化），仅去掉内部多余空白。
    """
    if not text:
        return ""
    m = CASE_NO_RE.search(text)
    if m:
        # 直接取匹配原文，仅压缩内部空白，保留原括号形态
        return re.sub(r"\s+", "", m.group(0))
    m2 = CASE_NO_LOOSE_RE.search(text)
    if m2:
        return re.sub(r"\s+", "", m2.group(0))
    return ""


def extract_court(text: str, case_no: str = "") -> str:
    """抽取法院名称。

    优先级（从可靠到兜底）：
    1. **文书首部第一行**（判决书标题行，如 ``上海市浦东新区人民法院`` /
       ``北京知识产权法院``）—— 最可靠，且能区分专门法院；
    2. 正文中首个法院全称（去掉 ``中华人民共和国`` 前缀）；
    3. 案号法院代字反推，**仅限可唯一确定的情形**（最高法院 ``最高法``）。
    """
    # 1) 首部首行（法院名称通常独占第一行）
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = SPECIAL_COURT_RE.fullmatch(line) or SPECIAL_COURT_RE.match(line)
        if m:
            return _clean_court_name(m.group(1))
        m = COURT_NAME_RE.fullmatch(line) or COURT_NAME_RE.match(line)
        if m:
            return _clean_court_name(m.group(1))
        # 首行不是法院名 → 不再看后续行首（避免抓到正文里的下级法院）
        break
    # 2) 全文首个法院全称
    m = SPECIAL_COURT_RE.search(text)
    if m:
        return _clean_court_name(m.group(1))
    m = COURT_NAME_RE.search(text)
    if m:
        return _clean_court_name(m.group(1))
    # 3) 案号代字反推（仅最高法等唯一可定者）
    if case_no:
        guess = _court_from_code(case_no)
        if guess:
            return guess
    return ""


def _clean_court_name(name: str) -> str:
    """去掉法院名前的 ``中华人民共和国`` 前缀与空白。"""
    name = re.sub(r"\s+", "", name or "")
    return re.sub(r"^中华人民共和国", "", name)


#: 法院代字 → 全称（**仅收录可唯一确定**者：最高法院）。
#: 省/直辖市高院代字（京/沪/粤…）**不可**单独成案，因为要跟数字才能
#: 定位到具体中院/基层院（``沪0115`` = 浦东新区法院，而非上海高院）。
_COURT_CODE_MAP = {
    "最高法": "最高人民法院",
}


def _court_from_code(case_no: str) -> str:
    """从案号的法院代字反推法院全称（仅覆盖可唯一确定的最高法情形）。"""
    m = re.match(r"[（(]\d{4}[）)](?P<code>[\u4e00-\u9fa5]{1,4})", case_no)
    if not m:
        return ""
    code = m.group("code")
    for prefix, full in _COURT_CODE_MAP.items():
        if code.startswith(prefix):
            return full
    return ""


def extract_trial_level(text: str) -> str:
    """抽取审理程序（一审/二审/再审/执行）。

    策略：
    1. **文书首部 + 案号类型代字**优先判级：``民终/刑终``→二审、``民申/刑申``
       →再审、``执异/执复``→执行、``民初/刑初``→一审。案号代字是**法定**标识，
       比正文关键词可靠。
    2. 否则扫文书首部（前 1500 字）匹配程序关键词（再审/执行先于二审/一审）。
    3. 最后全文兜底。
    """
    if not text:
        return ""
    # 1) 案号类型代字判级（最可靠）
    from_code = _trial_level_from_case_no(text)
    if from_code:
        return from_code
    # 2) 首部关键词
    head = text[:1500]
    for level, pat in TRIAL_LEVEL_PATTERNS:
        if pat.search(head):
            return level
    # 3) 全文兜底
    for level, pat in TRIAL_LEVEL_PATTERNS:
        if pat.search(text):
            return level
    return ""


#: 案号类型代字 → 审理程序。
_TYPE_CODE_TRIAL_LEVEL: tuple[tuple[str, str], ...] = (
    ("民终", "二审"), ("刑终", "二审"), ("行终", "二审"), ("赔终", "二审"),
    ("民申", "再审"), ("刑申", "再审"), ("行申", "再审"),
    ("民再", "再审"), ("刑再", "再审"), ("行再", "再审"),
    ("民提", "再审"), ("民监", "再审"),
    ("执异", "执行"), ("执复", "执行"), ("执监", "执行"),
    ("执恢", "执行"), ("执保", "执行"), ("执", "执行"),
    ("民初", "一审"), ("刑初", "一审"), ("行初", "一审"), ("赔初", "一审"),
    ("破申", "一审"), ("破初", "一审"),
    ("知民初", "一审"), ("知行初", "一审"),
    ("知民终", "二审"), ("知行终", "二审"),
)


def _trial_level_from_case_no(text: str) -> str:
    """从文案号（首个匹配）的类型代字判审理程序。"""
    m = CASE_NO_RE.search(text)
    if not m:
        return ""
    type_code = m.group("type")
    # 多字代字优先（长度降序已由表顺序保证：先查长串）
    for code, level in sorted(_TYPE_CODE_TRIAL_LEVEL, key=lambda x: -len(x[0])):
        if type_code.startswith(code):
            return level
    return ""


def _cn_to_int(s: str) -> int | None:
    """中文数字转整数（支持 〇零一二……十 十位/个位）。"""
    s = s.strip()
    if not s:
        return None
    # 纯阿拉伯
    if s.isdigit():
        return int(s)
    total = 0
    if "十" in s:
        left, _, right = s.partition("十")
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        total = tens * 10 + ones
        return total
    for ch in s:
        if ch not in _CN_DIGITS:
            return None
        total = total * 10 + _CN_DIGITS[ch]
    return total


#: 显式日期标签（xlsx 导出常带「裁判日期：」列，优先级最高）。
_DATE_LABEL_RE = re.compile(
    r"(?:裁判日期|判决日期|裁定日期|审结日期|裁判时间|日期)\s*[：:]\s*"
    r"(?P<val>[〇零一二三四五六七八九十0-9]{2,4}\s*[-年/]\s*"
    r"[〇零一二三四五六七八九十0-9]{1,3}\s*[-月/]\s*"
    r"[〇零一二三四五六七八九十0-9]{1,3}\s*日?)"
)


def extract_judgment_date(text: str) -> str:
    """抽取裁判日期，统一返回 ``YYYY-MM-DD``；抽取失败返回空串。

    优先级：
    1. **显式标签** ``裁判日期：2021年6月15日``（xlsx 导出列）—— 最高优先，
       避免被正文里的立案/受理日期带偏；
    2. 否则取**最后出现**的日期（判决书落款日期在文末）。
    支持中文数字（``二〇二四年五月六日``）与阿拉伯数字（``2024年5月6日``
    / ``2024-05-06``）两种格式。
    """
    if not text:
        return ""

    # 1) 显式标签优先
    lm = _DATE_LABEL_RE.search(text)
    if lm:
        parsed = _parse_one_date(lm.group("val"))
        if parsed:
            return parsed.isoformat()

    candidates: list[tuple[int, date]] = []

    for m in CHINESE_DATE_RE.finditer(text):
        parsed = _parse_one_date(m.group(0))
        if parsed:
            candidates.append((m.start(), parsed))

    for m in NUMERIC_DATE_RE.finditer(text):
        parsed = _parse_one_date(m.group(0))
        if parsed:
            candidates.append((m.start(), parsed))

    if not candidates:
        return ""
    # 落款日期在文末 → 取最后出现
    candidates.sort(key=lambda t: t[0])
    return candidates[-1][1].isoformat()


def _parse_one_date(raw: str) -> date | None:
    """解析单个月/日形式的日期串（支持中文数字与阿拉伯数字混用）。"""
    m = re.search(
        r"(?P<y>[〇零一二三四五六七八九十0-9]{2,4})\s*[-年/]\s*"
        r"(?P<m>[〇零一二三四五六七八九十0-9]{1,3})\s*[-月/]\s*"
        r"(?P<d>[〇零一二三四五六七八九十0-9]{1,3})",
        raw or "",
    )
    if not m:
        return None
    try:
        y = _cn_to_int(m.group("y"))
        mo = _cn_to_int(m.group("m"))
        d = _cn_to_int(m.group("d"))
        if not (y and mo and d):
            return None
        return date(y, mo, d)
    except (ValueError, TypeError):
        return None


def extract_cause_of_action(text: str) -> str:
    """抽取案由（短名词短语，如「买卖合同纠纷」）。

    步骤：
    1. 优先 ``案由：XXX`` 显式标签；
    2. 否则定位 ``……一案`` 锚点，取其左侧窗口（截至最近一个标点）；
    3. 在窗口内剥掉**所有**当事人称谓与人名（可叠多层）；
    4. 剩下以案由尾词收尾的部分即为案由。
    """
    if not text:
        return ""

    m = CAUSE_LABEL_RE.search(text)
    if m:
        cause = _clean_cause(m.group("cause"))
        if cause:
            return cause

    for am in _AN_YI_ANCHOR_RE.finditer(text):
        window = _left_window(text[: am.start()])
        cause = _strip_all_parties(window)
        if cause:
            return cause
    return ""


def _left_window(left: str) -> str:
    """从锚点左侧文本截取最近一个标点之后的窗口。"""
    boundary = 0
    for bm in _WINDOW_PUNCT_RE.finditer(left):
        boundary = bm.end()
    return left[boundary:]


def _strip_all_parties(window: str) -> str:
    """剥掉窗口内所有前导的当事人称谓 + 人名/连接词，校验并以案由尾词收尾。"""
    seg = re.sub(r"[\s，。；：、（）()【】]", "", window or "")
    if not seg:
        return ""
    for _ in range(6):
        sm = _STOP_RE.match(seg)
        if not sm:
            break
        rest = seg[sm.end():]
        # 称谓后：优先剥「人名 + 连接词」，否则直接取「以案由尾词收尾的最短后缀」
        nm = _PARTY_NAME_RE.match(rest)
        if nm and len(rest) - nm.end() >= 2:
            seg = rest[nm.end():]
            continue
        cause = _shortest_valid_cause(rest)
        if cause is None:
            seg = rest
            break
        seg = cause
    return _clean_cause(seg)


def _shortest_valid_cause(text: str) -> str | None:
    """取 ``text`` 中**最短的、以案由尾词收尾**的合法案由后缀。

    两级策略：
    1. **词典优先**：命中 ``_CAUSE_LEXICON`` 中已知案由短语者直接采用
       （``李四买卖合同纠纷`` → ``买卖合同纠纷``，而非误切 ``四买卖合同纠纷``）；
    2. **通用尾词兜底**：词典未命中时，取最短的、以纠纷/责任/案件/争议
       收尾且长度 >= 3 的后缀。

    要求后缀长度 >= 3（案由主体 >= 1 + 尾词 >= 2），避免误取 ``纠纷``。
    """
    # 1) 词典优先：取命中位置最靠右（最短后缀）的已知案由
    best_lex: str | None = None
    for term in sorted(_CAUSE_LEXICON, key=len):
        idx = text.rfind(term)
        if idx != -1:
            cand = text[idx:]
            if best_lex is None or len(cand) < len(best_lex):
                best_lex = cand
    if best_lex is not None:
        return best_lex
    # 2) 通用尾词兜底
    for i in range(1, len(text)):
        cand = text[i:]
        if len(cand) >= 3 and cand.endswith(_CAUSE_TAIL_WORDS):
            return cand
    return None


def _clean_cause(raw: str) -> str:
    """清理案由候选：剥掉残余称谓/连接词，校验尾词，并去掉前导连接词。"""
    cause = re.sub(r"[\s，。；：、（）()【】]", "", raw or "")
    if not cause:
        return ""
    for _ in range(4):
        sm = _STOP_RE.match(cause)
        if sm:
            rest = cause[sm.end():]
            nm = _PARTY_NAME_RE.match(rest)
            if nm and len(rest) - nm.end() >= 2:
                cause = rest[nm.end():]
                continue
            sc = _shortest_valid_cause(rest)
            if sc is not None:
                cause = sc
                continue
            cause = rest
            continue
        if cause[0] in "与和及因系为诉、":
            cause = cause[1:]
            continue
        break
    if len(cause) >= 2 and cause.endswith(_CAUSE_TAIL_WORDS):
        return cause
    return ""


def extract_parties(text: str) -> list[str]:
    """抽取当事人（按诉讼地位段首定位，保留「称谓+姓名」）。

    只取「段首/行首」的称谓行（判决书首部的当事人栏），并过滤正文里
    「上诉人XX因与YY……一案」「被告人陈某犯诈骗罪」这类叙述句 —— 后者含
    连接词/罪名动词，或姓名过长。
    """
    out: list[str] = []
    seen: set[str] = set()
    # 叙述句特征：连接词、案由词、程序动词、罪名动词 —— 当事人栏的姓名不含这些
    _CONNECTORS = re.compile(r"因|与|系|为|一案|纠纷|不服|向本院|提起|犯|罪|诉|请求|辩称")
    for m in PARTY_ROLE_RE.finditer(text):
        role = m.group("role")
        raw = re.sub(r"\s+", "", m.group("name") or "")
        if not raw:
            continue
        # 姓名截止到首个标点/括号/逗号
        name = re.split(r"[，,（(。；;]", raw)[0].strip()
        # 当事人栏姓名：非空、短（<=20 字）、不含连接词/罪名动词
        if not name or len(name) > 20 or _CONNECTORS.search(name):
            continue
        item = f"{role}{name}"
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


# ===========================================================================
# 综合抽取
# ===========================================================================


def extract_case(text: str) -> ExtractedCase:
    """从判决书全文抽取全部结构化字段（纯规则，不用 LLM）。"""
    text = text or ""
    case = ExtractedCase(content=text)
    case.case_no = extract_case_no(text)
    case.court = extract_court(text, case.case_no)
    case.trial_level = extract_trial_level(text)
    case.judgment_date = extract_judgment_date(text)
    case.cause_of_action = extract_cause_of_action(text)
    case.parties = extract_parties(text)

    for label, value in (
        ("案号", case.case_no),
        ("法院", case.court),
        ("审理程序", case.trial_level),
        ("裁判日期", case.judgment_date),
        ("案由", case.cause_of_action),
        ("当事人", case.parties),
    ):
        if not value:
            case.missing.append(label)
    return case


def is_usable(case: ExtractedCase) -> bool:
    """判定抽取结果是否足以入库。

    最低门槛：必须有案号（law 包主键之一）或至少一对当事人 + 正文。
    只有正文而无任何结构化信息 → 进待补录队列。
    """
    if case.case_no:
        return True
    return bool(case.parties) and len(case.content.strip()) > 50


# ===========================================================================
# 待补录队列
# ===========================================================================


def enqueue_failure(
    filename: str,
    raw_bytes: bytes | None,
    error: str,
    extracted: ExtractedCase | None = None,
) -> Path:
    """把抽取失败的文件写入 ``_queue/`` 待人工补录。

    落盘两个文件：原文件副本（便于人工打开）+ 同名 ``.json`` 元数据。
    返回元数据文件路径。
    """
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", filename).strip(" .") or "unnamed"
    base = f"{stamp}__{safe_name}"

    meta: dict[str, Any] = {
        "filename": filename,
        "enqueued_at": datetime.now().isoformat(timespec="seconds"),
        "error": error,
    }
    if extracted is not None:
        meta["partial"] = {
            "case_no": extracted.case_no,
            "court": extracted.court,
            "judgment_date": extracted.judgment_date,
            "missing": extracted.missing,
        }
        if extracted.content:
            raw_file = QUEUE_DIR / f"{base}.txt"
            raw_file.write_text(extracted.content, encoding="utf-8")
            meta["raw_text"] = raw_file.name
    elif raw_bytes is not None:
        bin_file = QUEUE_DIR / base
        bin_file.write_bytes(raw_bytes)
        meta["raw_file"] = bin_file.name

    meta_path = QUEUE_DIR / f"{base}.json"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("[case_import] 失败文件入队: %s (%s)", filename, error)
    return meta_path


def list_queue() -> list[dict[str, Any]]:
    """列出待补录队列（供 PapersView 法学视图展示）。"""
    if not QUEUE_DIR.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for p in sorted(QUEUE_DIR.glob("*.json")):
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:  # 坏元数据不阻塞列表
            logger.warning("[case_import] 队列元数据损坏: %s (%s)", p.name, e)
    return items


# ===========================================================================
# 批量导入编排（解析 → 抽取 → 判定可入库）
# ===========================================================================


@dataclass
class BatchItem:
    """单个文件的导入结果（xlsx 一行一案时可能含多个 case）。"""

    filename: str
    ok: bool
    error: str = ""
    case: ExtractedCase | None = None
    """主 case（兼容单案场景，取第一个可入库者）。"""
    cases: list[ExtractedCase] = field(default_factory=list)
    """该文件抽取出的全部可入库判例（xlsx 多行时 >1）。"""
    queued_path: str = ""


@dataclass
class BatchResult:
    """一批文件导入的汇总。"""

    total: int = 0
    imported: int = 0
    """成功入库的**判例数**（非文件数，xlsx 一行一案会累加）。"""
    queued: int = 0
    failed: int = 0
    items: list[BatchItem] = field(default_factory=list)

    @property
    def ok_items(self) -> list[BatchItem]:
        return [i for i in self.items if i.ok and i.cases]

    @property
    def all_cases(self) -> list[ExtractedCase]:
        out: list[ExtractedCase] = []
        for i in self.items:
            out.extend(i.cases)
        return out


def process_upload(
    filename: str,
    raw_bytes: bytes,
    *,
    source: str = "manual",
    license_note: str = "",
) -> BatchItem:
    """处理单个上传文件：写临时文件 → 解析 → 抽取 → 判定。

    不触碰数据库；入库由调用方（路由层）完成，保证本模块可独立单测。
    解析失败 / 抽取不可入库 → 写入待补录队列（``_queue/``）。

    ``.xlsx`` 按**一行一案**处理：每行独立抽取，产出多个 case。
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        err = f"不支持的格式 {suffix or '(无扩展名)'}"
        path = enqueue_failure(filename, raw_bytes, err)
        return BatchItem(filename=filename, ok=False, error=err, queued_path=str(path))

    import tempfile

    tmp_dir = Path(tempfile.mkdtemp(prefix="caseimp_"))
    tmp_path = tmp_dir / f"upload{suffix}"
    try:
        tmp_path.write_bytes(raw_bytes)
        try:
            if suffix == ".xlsx":
                cases = iter_cases_from_xlsx(tmp_path)
            else:
                cases = [extract_case(parse_file(tmp_path))]
        except ParseError as exc:
            path = enqueue_failure(filename, raw_bytes, str(exc))
            return BatchItem(
                filename=filename, ok=False, error=str(exc), queued_path=str(path)
            )

        usable = [c for c in cases if is_usable(c)]
        if not usable:
            err = "未抽取到可入库的结构化字段（缺案号且当事人不足）"
            first = cases[0] if cases else None
            path = enqueue_failure(filename, raw_bytes, err, extracted=first)
            return BatchItem(
                filename=filename, ok=False, error=err,
                case=first, queued_path=str(path),
            )
        return BatchItem(
            filename=filename, ok=True, case=usable[0], cases=usable
        )
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except Exception:  # noqa: BLE001 - 清理失败不影响结果
            pass


def process_batch(
    files: list[tuple[str, bytes]],
    *,
    source: str = "manual",
    license_note: str = "",
) -> BatchResult:
    """处理一批 ``(filename, bytes)``：逐文件解析抽取，单文件失败不炸整批。

    校验批量上限（工单 A1：≤50 文件 / ≤200MB）。
    """
    if len(files) > MAX_FILES_PER_BATCH:
        raise ValueError(
            f"单批文件数 {len(files)} 超过上限 {MAX_FILES_PER_BATCH}"
        )
    total_bytes = sum(len(b) for _, b in files)
    if total_bytes > MAX_BATCH_BYTES:
        raise ValueError(
            f"单批总大小 {total_bytes} 字节超过上限 {MAX_BATCH_BYTES}"
        )

    result = BatchResult(total=len(files))
    for filename, raw in files:
        item = process_upload(
            filename, raw, source=source, license_note=license_note
        )
        result.items.append(item)
        if item.ok:
            result.imported += len(item.cases)
        elif item.queued_path:
            result.queued += 1
        else:
            result.failed += 1
    return result
