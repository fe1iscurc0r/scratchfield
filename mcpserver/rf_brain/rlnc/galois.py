"""GF(2^8) 有限域运算（AES 不可约多项式 x^8+x^4+x^3+x+1 = 0x11B）。

纯 Python 查表实现，无第三方依赖（不引 numpy）。

关键实现细节：
  - 0x02(=x) 在 0x11B 域中**不是**生成元（不生成全部 255 个非零元素），
    若以 0x02 为底建 exp/log 表，log[3] 等元素会留空导致乘法错误。
  - 因此 exp/log 对表以生成元 0x03(=x+1) 为底构建；域本身由多项式唯一确定，
    查表底数只影响表的内容、不影响乘法结果。

运算：
  - gf_add / gf_sub = 按位异或（特征 2 域）
  - gf_mul(a,b)      = exp[log[a] + log[b]]（0 是零元，特殊处理）
  - gf_div(a,b)      = exp[log[a] - log[b] mod 255]
  - gf_inv(a)        = exp[255 - log[a]]
  - gf_pow(a,n)      = exp[(log[a] * n) mod 255]
"""
from __future__ import annotations

GF_ORDER = 256
GF_PRIMITIVE_POLY = 0x11B  # x^8 + x^4 + x^3 + x + 1（AES 标准）
GF_GENERATOR = 0x03        # 生成元 = x + 1

_EXP: list[int] = [0] * 512
_LOG: list[int] = [0] * 256


def _mul_by_generator(x: int) -> int:
    """x * 0x03 = xtime(x) ^ x（因为 3 = x + 1，且特征 2 下 2x = 0）。"""
    xt = x << 1
    if xt & 0x100:
        xt ^= GF_PRIMITIVE_POLY
    return (xt ^ x) & 0xFF


_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x = _mul_by_generator(_x)
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def gf_add(a: int, b: int) -> int:
    """有限域加法（= 按位异或）。"""
    return a ^ b


def gf_sub(a: int, b: int) -> int:
    """有限域减法（特征 2 下 == 加法）。"""
    return a ^ b


def gf_mul(a: int, b: int) -> int:
    """有限域乘法（查表）。0 是零元。"""
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def gf_div(a: int, b: int) -> int:
    """有限域除法 a / b；b == 0 抛 ZeroDivisionError。"""
    if b == 0:
        raise ZeroDivisionError("gf_div by zero")
    if a == 0:
        return 0
    return _EXP[(_LOG[a] - _LOG[b]) % 255]


def gf_inv(a: int) -> int:
    """乘法逆元 a^-1；a == 0 抛 ZeroDivisionError。"""
    if a == 0:
        raise ZeroDivisionError("gf_inv of zero")
    return _EXP[255 - _LOG[a]]


def gf_pow(a: int, n: int) -> int:
    """幂 a^n（n >= 0）。0^n = 0（n>0）/ 1（n==0）。"""
    if a == 0:
        return 0 if n > 0 else 1
    if n == 0:
        return 1
    return _EXP[(_LOG[a] * n) % 255]


__all__ = [
    "GF_ORDER",
    "GF_PRIMITIVE_POLY",
    "GF_GENERATOR",
    "gf_add",
    "gf_sub",
    "gf_mul",
    "gf_div",
    "gf_inv",
    "gf_pow",
]
