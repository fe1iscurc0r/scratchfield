"""中文拼音口型表（9 维 PhonemePose，原创推导）。

设计参考：handcrafted-persona-engine 的 PhonemePose 九维结构（无 LICENSE，仅蒸馏不融合）；
数值按汉语发音生理特征从零推导，未复制上游任何数值。

九维（与 Live2D Cubism 参数对应）：
    MouthOpenY(0-1) JawOpen(0-1) MouthForm(-1~1) MouthShrug(0-1) MouthFunnel(0-1)
    MouthPuckerWiden(-1~1) MouthPressLipOpen(-1~1) MouthX(-1~1) CheekPuff(0-1)

推导规则（发音生理）：
    - 塞音 b/p/m（双唇）：闭唇抿紧（PressLipOpen=-1），除阻时轻微鼓腮（b 0.5 / p 0.7）。
    - 擦音 s/f/x/sh/r：气流形状（PuckerWiden 按气流宽度），露齿（PressLipOpen +）。
    - 鼻音 n/m/ng：近闭（OpenY 小），口腔闭合（PressLipOpen=-1）。
    - 元音按开口度：a/o/e 开口大，i/ü/u 开口小，i 带嘴角（MouthForm +）。
    - 圆唇 ü/u/o：嘟嘴（Funnel +，PuckerWiden +）。
"""
from __future__ import annotations

# 中性姿态（SIL / 停顿）
NEUTRAL_POSE = dict(
    MouthOpenY=0.0, JawOpen=0.0, MouthForm=0.0, MouthShrug=0.0,
    MouthFunnel=0.0, MouthPuckerWiden=0.0, MouthPressLipOpen=0.0,
    MouthX=0.0, CheekPuff=0.0,
)

# 21 个声母
_INITIALS = {
    "b": dict(MouthPressLipOpen=-1.0, CheekPuff=0.5),
    "p": dict(MouthPressLipOpen=-1.0, CheekPuff=0.7),
    "m": dict(MouthPressLipOpen=-1.0),
    "f": dict(MouthPressLipOpen=0.4, MouthPuckerWiden=-0.3),
    "d": dict(MouthPressLipOpen=-0.5, MouthOpenY=0.15, JawOpen=0.1),
    "t": dict(MouthPressLipOpen=-0.4, MouthOpenY=0.15, JawOpen=0.1),
    "n": dict(MouthPressLipOpen=-0.8, MouthOpenY=0.05),
    "l": dict(MouthOpenY=0.25, JawOpen=0.15, MouthPressLipOpen=0.5),
    "g": dict(MouthOpenY=0.2, MouthPressLipOpen=-0.5),
    "k": dict(MouthOpenY=0.25, MouthPressLipOpen=-0.4),
    "h": dict(MouthOpenY=0.3, JawOpen=0.2),
    "j": dict(MouthOpenY=0.1, MouthForm=0.4, MouthPuckerWiden=-0.6, MouthPressLipOpen=0.6),
    "q": dict(MouthOpenY=0.15, MouthForm=0.2, MouthPuckerWiden=-0.5, MouthPressLipOpen=0.6),
    "x": dict(MouthOpenY=0.1, MouthForm=0.5, MouthPuckerWiden=-0.7, MouthPressLipOpen=0.7),
    "zh": dict(MouthOpenY=0.2, MouthFunnel=0.3, MouthPuckerWiden=0.3),
    "ch": dict(MouthOpenY=0.2, MouthFunnel=0.4, MouthPuckerWiden=0.4),
    "sh": dict(MouthOpenY=0.15, MouthFunnel=0.6, MouthPuckerWiden=0.5, MouthPressLipOpen=0.2),
    "r": dict(MouthOpenY=0.25, MouthFunnel=0.2, MouthPuckerWiden=0.1),
    "z": dict(MouthOpenY=0.15, MouthPressLipOpen=0.5, MouthPuckerWiden=-0.2),
    "c": dict(MouthOpenY=0.15, MouthPressLipOpen=0.5, MouthPuckerWiden=-0.2),
    "s": dict(MouthOpenY=0.05, MouthPuckerWiden=-0.6, MouthPressLipOpen=0.8, MouthForm=0.3),
}

# 36 个韵母（按开口度/唇形推导）
_FINALS = {
    "a": dict(MouthOpenY=0.75, JawOpen=0.65),
    "o": dict(MouthOpenY=0.5, JawOpen=0.4, MouthFunnel=0.3, MouthPuckerWiden=0.3),
    "e": dict(MouthOpenY=0.45, JawOpen=0.35),
    "i": dict(MouthOpenY=0.12, JawOpen=0.08, MouthForm=0.7, MouthPuckerWiden=-0.8, MouthPressLipOpen=0.8),
    "u": dict(MouthOpenY=0.15, JawOpen=0.05, MouthFunnel=0.7, MouthPuckerWiden=0.7),
    "v": dict(MouthOpenY=0.12, JawOpen=0.05, MouthFunnel=0.8, MouthPuckerWiden=0.8, MouthForm=0.2),  # ü
    "ai": dict(MouthOpenY=0.6, JawOpen=0.5),
    "ei": dict(MouthOpenY=0.4, JawOpen=0.3),
    "ui": dict(MouthOpenY=0.25, MouthFunnel=0.4, MouthPuckerWiden=0.4),
    "ao": dict(MouthOpenY=0.6, JawOpen=0.5, MouthFunnel=0.2),
    "ou": dict(MouthOpenY=0.4, MouthFunnel=0.5, MouthPuckerWiden=0.5),
    "iu": dict(MouthOpenY=0.2, MouthFunnel=0.4, MouthPuckerWiden=0.4),
    "ie": dict(MouthOpenY=0.35, JawOpen=0.25, MouthForm=0.3),
    "ve": dict(MouthOpenY=0.3, MouthFunnel=0.4, MouthForm=0.2),  # üe
    "er": dict(MouthOpenY=0.35, JawOpen=0.25),
    "an": dict(MouthOpenY=0.5, JawOpen=0.4),
    "en": dict(MouthOpenY=0.3, JawOpen=0.2),
    "in": dict(MouthOpenY=0.12, MouthPressLipOpen=-0.3),
    "un": dict(MouthOpenY=0.2, MouthFunnel=0.3),
    "vn": dict(MouthOpenY=0.15, MouthFunnel=0.4),  # ün
    "ang": dict(MouthOpenY=0.6, JawOpen=0.45),
    "eng": dict(MouthOpenY=0.4, JawOpen=0.25),
    "ing": dict(MouthOpenY=0.15, MouthForm=0.2),
    "ong": dict(MouthOpenY=0.35, MouthFunnel=0.4, MouthPuckerWiden=0.4),
    "ia": dict(MouthOpenY=0.5, JawOpen=0.4),
    "iao": dict(MouthOpenY=0.55, JawOpen=0.45),
    "ian": dict(MouthOpenY=0.45, JawOpen=0.35),
    "iang": dict(MouthOpenY=0.5, JawOpen=0.4),
    "iong": dict(MouthOpenY=0.3, MouthFunnel=0.4),
    "ua": dict(MouthOpenY=0.55, MouthFunnel=0.3),
    "uo": dict(MouthOpenY=0.45, MouthFunnel=0.35, MouthPuckerWiden=0.3),
    "uai": dict(MouthOpenY=0.5, MouthFunnel=0.3),
    "uan": dict(MouthOpenY=0.4, MouthFunnel=0.3),
    "uang": dict(MouthOpenY=0.5, MouthFunnel=0.3),
    "ueng": dict(MouthOpenY=0.35, MouthFunnel=0.3),
    "van": dict(MouthOpenY=0.3, MouthFunnel=0.5),  # üan
}

# 整体认读音节常用组合（与声韵母独立覆盖，防缺）
_WHOLE_SYLLABLES = {
    "zhi": dict(MouthOpenY=0.15, MouthFunnel=0.2),
    "chi": dict(MouthOpenY=0.15, MouthFunnel=0.3),
    "shi": dict(MouthOpenY=0.12, MouthFunnel=0.5, MouthPuckerWiden=0.4),
    "ri": dict(MouthOpenY=0.2, MouthFunnel=0.2),
    "zi": dict(MouthOpenY=0.1, MouthPuckerWiden=-0.3, MouthPressLipOpen=0.5),
    "ci": dict(MouthOpenY=0.1, MouthPuckerWiden=-0.3, MouthPressLipOpen=0.5),
    "si": dict(MouthOpenY=0.05, MouthPuckerWiden=-0.5, MouthPressLipOpen=0.7),
    "yi": dict(MouthOpenY=0.12, MouthForm=0.6, MouthPuckerWiden=-0.7, MouthPressLipOpen=0.8),
    "wu": dict(MouthOpenY=0.15, MouthFunnel=0.7, MouthPuckerWiden=0.7),
    "yu": dict(MouthOpenY=0.12, MouthFunnel=0.8, MouthPuckerWiden=0.8),
    "ye": dict(MouthOpenY=0.35, MouthForm=0.3),
    "yue": dict(MouthOpenY=0.3, MouthFunnel=0.4),
    "yuan": dict(MouthOpenY=0.3, MouthFunnel=0.5),
    "yin": dict(MouthOpenY=0.12, MouthPressLipOpen=-0.3),
    "yun": dict(MouthOpenY=0.15, MouthFunnel=0.4),
    "ying": dict(MouthOpenY=0.15, MouthForm=0.2),
}

_POSE_DIMENSIONS = (
    "MouthOpenY", "JawOpen", "MouthForm", "MouthShrug", "MouthFunnel",
    "MouthPuckerWiden", "MouthPressLipOpen", "MouthX", "CheekPuff",
)


def _fill(overrides: dict) -> dict:
    """用覆盖值填充 9 维，缺失维度默认 0（对齐上游「只写差异维度」的写法）。"""
    pose = dict(NEUTRAL_POSE)
    for k, v in overrides.items():
        if k not in pose:
            raise KeyError(f"未知维度 {k}（合法维度：{_POSE_DIMENSIONS}）")
        pose[k] = float(v)
    return pose


# 组装最终口型表：SIL/停顿 + 声母 + 韵母 + 整体认读，韵母覆盖优先（后写入覆盖前者）
_PINYIN_POSES: dict[str, dict] = {"SIL": dict(NEUTRAL_POSE), "PAUSE": dict(NEUTRAL_POSE)}
for _src in (_INITIALS, _FINALS, _WHOLE_SYLLABLES):
    for _key, _ov in _src.items():
        _PINYIN_POSES[_key] = _fill(_ov)


def get_pose(phoneme: str) -> dict:
    """查口型表：未知音素回落中性（SIL），保证任何输入都有 9 维输出。"""
    if not phoneme:
        return dict(NEUTRAL_POSE)
    key = phoneme.strip().lower()
    if key in ("sil", "sp", "spn", "pau", ""):
        return dict(NEUTRAL_POSE)
    pose = _PINYIN_POSES.get(key)
    if pose is None:
        return dict(NEUTRAL_POSE)
    return dict(pose)


def all_phonemes() -> list[str]:
    """口型表全部可查键（验收用）。"""
    return sorted(_PINYIN_POSES.keys())
