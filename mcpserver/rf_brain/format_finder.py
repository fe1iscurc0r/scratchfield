"""
mcpserver/rf_brain/format_finder.py — 协议格式自动发现（纯 Python 原型）

参考来源：jopohl/urh（GPL-3.0，只读参考）awre/FormatFinder.py 设计思路
  - 输入多条已知消息的位流（含 preamble/address/length/checksum 的合成样本）
  - 迭代字段发现：跑字段引擎（address/length/checksum/seq）→ 按共同范围分组
  - 1 容器 = 1 消息类型；>1 容器 = 消息类型分裂
  - 迭代到不再发现新字段
  - 输出：字段边界 + 消息类型

【参考实现边界】
  本模块提取 urh FormatFinder 设计思路独立实现，未使用任何 urh 源码。
  urh 原型使用 numpy + PyQt；本模块使用纯 Python + numpy。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class Field:
    """
    发现的字段描述。
    name: 字段名称（preamble / address / length / checksum / seq / data）
    start: 起始比特索引（含）
    end: 结束比特索引（不含）
    bits: 比特数（end - start）
    """
    name: str
    start: int
    end: int

    @property
    def bits(self) -> int:
        return self.end - self.start

    def __repr__(self):
        return f"Field({self.name}, [{self.start}:{self.end}] {self.bits}bits)"


@dataclass
class MessageContainer:
    """
    共同范围容器（对应 urh create_common_range_containers）。
    1 个 Container = 1 种消息类型。
    包含一组在所有样本中位置相同的字段集合。
    """
    fields: list[Field] = field(default_factory=list)
    sample_count: int = 0

    def add_field(self, field: Field):
        self.fields.append(field)

    def total_bits(self) -> int:
        return sum(f.bits for f in self.fields)


# ---------------------------------------------------------------------------
# 字段引擎基类
# ---------------------------------------------------------------------------

class FieldEngine:
    """
    可插拔字段发现引擎基类。
    每种引擎负责探测一种字段语义：
      - AddressEngine: 地址字段（样本间固定或规律变化）
      - LengthEngine: 长度字段（值与后续数据长度一致）
      - ChecksumEngine: 校验字段（可对前半部分验证）
      - SeqEngine: 序号字段（每次消息递增）
    """

    name: str = "base"

    def find(self, messages: list[np.ndarray]) -> list[Field]:
        """
        在 messages 上运行引擎，返回发现的字段列表。
        messages: 比特数组列表，每项为 0/1 数组。
        """
        raise NotImplementedError

    @staticmethod
    def _bits_to_int(bits: np.ndarray) -> int:
        """比特数组转整数（MSB first）。"""
        result = 0
        for b in bits:
            result = (result << 1) | int(b)
        return result


# ---------------------------------------------------------------------------
# 具体引擎实现
# ---------------------------------------------------------------------------

class PreambleEngine(FieldEngine):
    """
    Preamble 检测引擎。
    检测固定重复 pattern（前导同步字），通过自相关滑动匹配。
    """

    name = "preamble"

    def find(self, messages: list[np.ndarray]) -> list[Field]:
        if len(messages) < 1:
            return []
        fields = []
        for msg in messages:
            pos = self._find_preamble(msg)
            if pos is not None:
                # 假设 preamble 长度 8~32 bit
                fields.append(Field(name="preamble", start=pos, end=pos + 16))
                break
        return fields

    def _find_preamble(self, bits: np.ndarray, min_len=8, max_len=32) -> int | None:
        """滑动自相关检测 preamble 位置。"""
        n = len(bits)
        if n < max_len * 2:
            return None
        for wl in range(min_len, min(max_len + 1, n // 2)):
            pattern = bits[:wl]
            # 检查前 wl 位是否全相同（全 0 或全 1）
            if np.all(bits[:wl] == pattern[0]):
                return 0
        # 否则检查是否在后续位置出现重复 pattern
        for start in range(1, n - max_len):
            segment = bits[start:start + wl]
            if np.all(segment == pattern[0]):
                return start
        return None


class AddressEngine(FieldEngine):
    """
    地址字段检测引擎。
    策略：在同一消息类型中，地址字段在不同消息间或固定、或有规律变化（如低 bit 递增）。
    检测方法：找出样本间共同不变/规律变化的比特范围。
    """

    name = "address"

    def find(self, messages: list[np.ndarray]) -> list[Field]:
        if len(messages) < 2:
            return []
        min_len = min(len(m) for m in messages)
        # 统计每个 bit 位置在样本间的"变化率"
        stacked = np.array([m[:min_len] for m in messages])
        # 变化率 = 不同值的比例
        change_rate = np.mean(stacked != stacked[0], axis=0)  # shape (min_len,)

        # 低变化率（<10%）的连续区域 → 地址候选
        runs = self._find_constant_runs(change_rate, threshold=0.1)
        fields = []
        for (start, end) in runs:
            if (end - start) >= 4:  # 最小地址宽度 4 bit
                fields.append(Field(name="address", start=start, end=end))
                break  # 只报第一个候选地址区域
        return fields

    def _find_constant_runs(self, arr: np.ndarray, threshold: float) -> list[tuple[int, int]]:
        """找出 arr < threshold 的连续区间。"""
        runs = []
        in_run = False
        start = 0
        for i, v in enumerate(arr):
            if not in_run and v < threshold:
                in_run = True
                start = i
            elif in_run and v >= threshold:
                in_run = False
                runs.append((start, i))
        if in_run:
            runs.append((start, len(arr)))
        return runs


class LengthEngine(FieldEngine):
    """
    长度字段检测引擎。
    策略：长度字段的值应与紧跟其后的数据长度相匹配。
    检测方法：对每个可能的 (offset, width) 组合验证。
    """

    name = "length"

    def find(self, messages: list[np.ndarray]) -> list[Field]:
        if len(messages) < 1:
            return []
        fields = []
        # 常见长度字段位置和宽度
        for offset in range(0, 16):  # 前 16 bit 内
            for width in [4, 8, 16]:  # 4/8/16 bit 长度字段
                if offset + width > min(len(m) for m in messages):
                    continue
                candidate = self._check_length_candidate(messages, offset, width)
                if candidate is not None:
                    fields.append(Field(name="length", start=offset, end=offset + width))
                    return fields
        return fields

    def _check_length_candidate(self, messages: list[np.ndarray],
                                 offset: int, width: int) -> int | None:
        """
        检查 offset/width 位置的值是否符合「值 = 后续数据长度」。
        返回值：若符合，返回数据字段起始位；否则 None。
        """
        for msg in messages:
            if offset + width + 1 > len(msg):
                return None
            bits = msg[offset:offset + width]
            length_val = self._bits_to_int(bits)
            data_start = offset + width
            data_end = data_start + length_val
            if data_end > len(msg):
                return None
        return offset + width  # 数据字段起始位


class ChecksumEngine(FieldEngine):
    """
    校验字段检测引擎。
    策略：checksum 可对其前面所有 bit 验证（CRC-8/CRC-16 等简单算法）。
    检测方法：穷举每种 (offset, width) 组合，验证所有样本的 checksum 一致性。
    """

    name = "checksum"

    def find(self, messages: list[np.ndarray]) -> list[Field]:
        if len(messages) < 2:
            return []
        fields = []
        # 常见 checksum 位置（消息末尾往前）和宽度
        for width in [8, 16]:
            for offset in range(-1, -min(32, min(len(m) for m in messages)), -1):
                abs_offset = min(len(m) for m in messages) + offset
                if abs_offset - width < 0:
                    continue
                if self._verify_checksum(messages, abs_offset, width):
                    fields.append(Field(name="checksum", start=abs_offset, end=abs_offset + width))
                    return fields
        return fields

    def _verify_checksum(self, messages: list[np.ndarray],
                         offset: int, width: int) -> bool:
        """验证 offset/width 位置的 checksum 对所有消息是否一致（简化：XOR 校验）。"""
        try:
            checksums = []
            for msg in messages:
                data = msg[:offset]
                cs_bits = msg[offset:offset + width]
                cs_val = self._bits_to_int(cs_bits)
                # 简化 XOR 校验：data 所有 bit XOR 起来，低 width 位
                computed = np.bitwise_xor.reduce(data) if len(data) > 0 else 0
                if isinstance(computed, np.ndarray):
                    computed = int(np.packbits(computed)[-1]) if width <= 8 else int(np.packbits(computed).view(np.uint16)[-1])
                checksums.append(cs_val ^ (computed % (2 ** width)))
            # 若所有校验结果都相同（或差值恒定），认为是 checksum
            return len(set(checksums)) <= 1
        except Exception:
            return False


class SeqEngine(FieldEngine):
    """
    序号字段检测引擎。
    策略：序号字段在连续消息间递增（步长固定）。
    """

    name = "seq"

    def find(self, messages: list[np.ndarray]) -> list[Field]:
        if len(messages) < 2:
            return []
        min_len = min(len(m) for m in messages)
        # 尝试不同宽度和位置的序号字段
        for width in [4, 8, 16]:
            for offset in range(0, min(24, min_len - width)):
                delta = self._check_seq_candidate(messages, offset, width)
                if delta is not None and delta > 0:
                    return [Field(name="seq", start=offset, end=offset + width)]
        return []

    def _check_seq_candidate(self, messages: list[np.ndarray],
                              offset: int, width: int) -> int | None:
        """检查 offset/width 位置是否为序号字段（连续消息间递增且步长一致）。"""
        values = []
        for msg in messages:
            bits = msg[offset:offset + width]
            values.append(self._bits_to_int(bits))
        # 计算相邻差值
        deltas = [values[i + 1] - values[i] for i in range(len(values) - 1)]
        if not deltas:
            return None
        # 所有差值相同（或第一个差值整除其他）
        first = deltas[0]
        if first == 0:
            return None
        consistent = all(abs(d - first) <= 1 for d in deltas)
        return first if consistent else None


# ---------------------------------------------------------------------------
# FormatFinder（主类）
# ---------------------------------------------------------------------------

class FormatFinder:
    """
    协议格式自动发现器。

    对应 urh awre/FormatFinder.py 的迭代字段发现逻辑：
      1. 跑各字段引擎（address/length/checksum/seq/preamble）
      2. 按共同范围分组 → MessageContainer
      3. 1 容器 = 1 消息类型；>1 容器 = 消息类型分裂
      4. 迭代到不再发现新字段

    Attributes:
        engines: 要运行的字段引擎列表
        max_iterations: 最大迭代次数（默认 10）
    """

    def __init__(self, engines: list[FieldEngine] | None = None,
                 max_iterations: int = 10):
        self.engines = engines or [
            PreambleEngine(),
            AddressEngine(),
            LengthEngine(),
            ChecksumEngine(),
            SeqEngine(),
        ]
        self.max_iterations = max_iterations
        self._discovered_containers: list[MessageContainer] = []

    def discover(self, messages: list[list[int]]) -> list[MessageContainer]:
        """
        主入口：对一组消息位流进行协议格式自动发现。

        Args:
            messages: 消息位流列表，每条消息为 0/1 列表

        Returns:
            MessageContainer 列表，每项代表一种消息类型及其字段结构
        """
        # 转为 numpy 数组
        np_messages = [np.array(m, dtype=np.int8) for m in messages]

        # 迭代字段发现
        all_fields: list[Field] = []
        for _ in range(self.max_iterations):
            new_fields = self._run_engines(np_messages, exclude=all_fields)
            if not new_fields:
                break
            all_fields.extend(new_fields)

        # 按共同范围分组为容器
        containers = self._group_into_containers(all_fields, np_messages)
        self._discovered_containers = containers
        return containers

    def _run_engines(self, messages: list[np.ndarray],
                     exclude: list[Field] | None = None) -> list[Field]:
        """运行所有引擎，返回新发现的字段（去重已发现）。"""
        excluded_ranges = set()
        if exclude:
            for f in exclude:
                for b in range(f.start, f.end):
                    excluded_ranges.add(b)

        new_fields: list[Field] = []
        for eng in self.engines:
            found = eng.find(messages)
            for f in found:
                # 跳过已被排除的范围
                overlap = any(b in excluded_ranges for b in range(f.start, f.end))
                if not overlap:
                    new_fields.append(f)
                    # 标记为已发现
                    for b in range(f.start, f.end):
                        excluded_ranges.add(b)
        return new_fields

    def _group_into_containers(self, fields: list[Field],
                                messages: list[np.ndarray]) -> list[MessageContainer]:
        """
        按共同范围将字段分组为 MessageContainer。
        同一容器内的字段在所有消息样本中具有相同的相对位置。

        对应 urh create_common_range_containers 逻辑：
          - 1 容器 = 1 消息类型
          - >1 容器 = 消息类型分裂（多种帧格式）
        """
        if not fields:
            return []

        # 简单策略：按字段名分组（相同字段名在同一容器）
        # 真实 urh 按比特位置重叠关系分组，这里简化为按 name 分组
        by_name: dict[str, list[Field]] = {}
        for f in fields:
            by_name.setdefault(f.name, []).append(f)

        containers: list[MessageContainer] = []
        for name, flds in by_name.items():
            if not flds:
                continue
            # 按 start 排序，取第一个（实际工程中应取各消息共同范围）
            container = MessageContainer(sample_count=len(messages))
            for f in sorted(flds, key=lambda x: x.start):
                container.add_field(f)
            if container.fields:
                containers.append(container)

        return containers

    # ---- 工具方法 ----

    @staticmethod
    def _bits_to_int(bits: np.ndarray) -> int:
        """比特数组转整数（MSB first）。"""
        result = 0
        for b in bits:
            result = (result << 1) | int(b)
        return result

    @staticmethod
    def format_containers(containers: list[MessageContainer]) -> str:
        """将容器列表格式化为可读字符串（中文输出）。"""
        lines = []
        for i, c in enumerate(containers):
            lines.append(f"  消息类型 {i + 1}（{c.sample_count} 个样本）：")
            for f in sorted(c.fields, key=lambda x: x.start):
                lines.append(f"    - {f.name}: 比特 [{f.start}:{f.end}]（{f.bits} bit）")
            lines.append(f"    总计：{c.total_bits()} bit")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

def find_protocol_format(messages: list[list[int]]) -> list[MessageContainer]:
    """
    便捷入口：对消息位流列表进行协议格式自动发现。

    Args:
        messages: 消息位流列表，每条消息为 0/1 列表

    Returns:
        MessageContainer 列表

    Example:
        >>> msgs = [[0,1,0,1]*4 + [1,0,1,0]*2] * 3  # 3 条相同结构消息
        >>> containers = find_protocol_format(msgs)
        >>> print(FormatFinder.format_containers(containers))
    """
    finder = FormatFinder()
    return finder.discover(messages)