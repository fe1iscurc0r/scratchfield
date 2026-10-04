"""k-SwordStamp 语义水印最小原型（S25 · rf_brain 数据完整性验证）。

依据 round3 digest-g3-2026-08-31.md（2608.27666 k-SwordStamp）：
「提出嵌入位移攻击（EDA）重排/改写/重分割语义水印，并设计子句级顺序鲁棒
检测 k-SwordStamp 将攻击成功率压至 10.8-39.7%」。

核心对比（水印机制）：
  - 顺序脆弱水印（baseline）：按「位置」标记子句（偶数位标记）——重排即被破坏；
  - 顺序鲁棒水印（k-SwordStamp）：按「内容哈希」标记子句（与位置无关）——
    重排不影响标记集合，检测仍成立。

对频谱数据的映射：把「子句」换成「频谱 chunk」——水印嵌入在 chunk 的内容
统计量上（而非 chunk 顺序），则重分割/重排频谱片段不破坏水印。

原型（纯 stdlib，确定性）：子句级水印 embed/detect + 三类 EDA 攻击（重排/
改写/重分割），对比两种水印的检测率。

运行：
  python tools/kswordstamp.py
"""
from __future__ import annotations

import random

MARK = "\u200b"  # 零宽空格作为子句标记


def clauses(text: str) -> list[str]:
    return [s.strip() for s in text.split(".") if s.strip()]


def _content_bit(clause: str, salt: str) -> bool:
    """内容哈希决定是否标记（与位置无关）。"""
    return (hash((salt, clause)) & 1) == 1


def embed_position(text: str) -> str:
    """顺序脆弱水印：偶数位子句标记。"""
    return ". ".join((c + MARK if i % 2 == 0 else c) for i, c in enumerate(clauses(text)))


def embed_content(text: str, salt: str = "k") -> str:
    """顺序鲁棒水印（k-SwordStamp）：内容哈希决定标记。"""
    return ". ".join((c + MARK if _content_bit(c, salt) else c) for c in clauses(text))


def detect_position(text: str) -> float:
    """顺序检测：位置奇偶与标记一致性。"""
    cs = clauses(text)
    if not cs:
        return 1.0
    return sum(1 for i, c in enumerate(cs) if (MARK in c) == (i % 2 == 0)) / len(cs)


def detect_content(text: str, salt: str = "k") -> float:
    """顺序鲁棒检测：内容哈希与标记一致性（与顺序无关）。"""
    cs = clauses(text)
    if not cs:
        return 1.0
    return sum(1 for c in cs if (MARK in c) == _content_bit(c.replace(MARK, ""), salt)) / len(cs)


# ---- EDA 攻击 ----

def attack_rearrange(text: str, seed: int = 0) -> str:
    """重排：打乱子句顺序。"""
    rng = random.Random(seed)
    cs = clauses(text)
    rng.shuffle(cs)
    return ". ".join(cs)


def attack_rewrite(text: str, frac: float, seed: int = 0) -> str:
    """改写：替换 frac 比例的子句（标记丢失，替换文本带索引保证哈希分散）。"""
    rng = random.Random(seed)
    cs = clauses(text)
    for i in range(len(cs)):
        if rng.random() < frac:
            cs[i] = f"completely rewritten clause {i} about unrelated spectrum data"
    return ". ".join(cs)


def attack_resegment(text: str, seed: int = 0) -> str:
    """重分割：相邻子句合并（标记保留但粒度改变）。"""
    rng = random.Random(seed)
    cs = clauses(text)
    merged = []
    for i in range(0, len(cs) - 1, 2):
        merged.append(cs[i] + " " + cs[i + 1])
    if len(cs) % 2 == 1:
        merged.append(cs[-1])
    return ". ".join(merged)


def run_eval(seed: int = 0) -> dict:
    """对比两种水印在三类 EDA 攻击下的检测率。"""
    rng = random.Random(seed)
    src = ". ".join(f"clause number {i} carries spectrum segment information" for i in range(30))

    pos = embed_position(src)
    cont = embed_content(src)

    def eval_pair(det_pos, det_cont, name, transform):
        p = det_pos(transform(pos))
        c = det_cont(transform(cont))
        return {"attack": name, "position_watermark": p, "content_watermark": c}

    results = [
        eval_pair(detect_position, detect_content, "rearrange", lambda t: attack_rearrange(t, seed)),
        eval_pair(detect_position, detect_content, "rewrite_30%", lambda t: attack_rewrite(t, 0.3, seed)),
        eval_pair(detect_position, detect_content, "resegment", lambda t: attack_resegment(t, seed)),
    ]
    return {"results": results}


def main() -> int:
    for r in run_eval()["results"]:
        print(f"[{r['attack']:<12}] 顺序水印 {r['position_watermark']*100:.0f}%  vs  "
              f"k-SwordStamp {r['content_watermark']*100:.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
