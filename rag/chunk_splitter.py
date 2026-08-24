"""
文本分块模块 - 将长文本分割为适合嵌入的块
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

Chunk = dict[str, Any]


class ChunkSplitter:
    """文本分块器"""
    
    def __init__(self, chunk_size: int = 512, overlap: int = 50):
        """初始化分块器
        
        Args:
            chunk_size: 每个块的最大 token 数（近似按字符计算）
            overlap: 相邻块的重叠字符数
        """
        self.chunk_size: int = chunk_size
        self.overlap: int = overlap
    
    def split(self, text: str, metadata: dict[str, Any] | None = None) -> list[Chunk]:
        """将文本分割为块
        
        Args:
            text: 原始文本
            metadata: 元数据（如文档ID、标签等）
            
        Returns:
            分块列表，每个块包含 content 和 metadata
        """
        if not text or not text.strip():
            return []
        
        # 先按段落分割
        paragraphs = self._split_paragraphs(text)
        
        # 然后将段落合并为接近 chunk_size 的块
        chunks: list[Chunk] = []
        current_chunk: list[str] = []
        current_length = 0
        
        for para in paragraphs:
            para_length = len(para)
            
            # 如果单个段落超过 chunk_size，需要进一步分割
            if para_length > self.chunk_size:
                if current_chunk:
                    chunks.append(self._make_chunk(current_chunk, metadata))
                    current_chunk = []
                    current_length = 0
                # 按句子分割长段落
                sentences = self._split_sentences(para)
                for sent in sentences:
                    if current_length + len(sent) > self.chunk_size:
                        if current_chunk:
                            chunks.append(self._make_chunk(current_chunk, metadata))
                        current_chunk = []
                        current_length = 0
                    current_chunk.append(sent)
                    current_length += len(sent)
            else:
                if current_length + para_length > self.chunk_size:
                    chunks.append(self._make_chunk(current_chunk, metadata))
                    # MEDIUM-1 修复：中文 overlap 按"完整语义单位"回退，
                    # 优先取最近一个句子(。！？.!?)，再退到最近一个词(标点/空白)，最后才按字符截。
                    # 防止 overlap 截在"壳聚糖"中间，导致上下文断裂 + 嵌入向量语义漂移。
                    current_chunk = self._take_overlap_sentences(current_chunk, metadata)
                    current_length = sum(len(s) for s in current_chunk)
                current_chunk.append(para)
                current_length += para_length
        
        # 添加最后一个块
        if current_chunk:
            chunks.append(self._make_chunk(current_chunk, metadata))
        
        # 过滤空块
        chunks = [c for c in chunks if c['content'].strip()]
        
        logger.info(f"文本分块完成: {len(text)} 字符 -> {len(chunks)} 个块")
        return chunks
    
    def _split_paragraphs(self, text: str) -> list[str]:
        """按段落分割文本"""
        paragraphs = re.split(r'\n\s*\n', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        return paragraphs
    
    def _split_sentences(self, text: str) -> list[str]:
        """按句子分割文本"""
        sentences = re.split(r'([。！？.!?])', text)
        result: list[str] = []
        i = 0
        while i < len(sentences):
            sent = sentences[i]
            if i + 1 < len(sentences) and sentences[i + 1] in '。！？.!?':
                sent += sentences[i + 1]
                i += 2
            else:
                i += 1
            if sent.strip():
                result.append(sent.strip())
        return result
    
    def _make_chunk(self, paragraphs: list[str], metadata: dict[str, Any] | None = None) -> Chunk:
        """创建一个文本块"""
        content = '\n\n'.join(paragraphs)
        chunk: Chunk = {
            'content': content,
            'token_count': len(content),
        }
        if metadata:
            chunk['metadata'] = metadata.copy()
        return chunk

    def _take_overlap_sentences(self, chunks: list[str], _metadata) -> list[str]:
        """MEDIUM-1：基于句界的 overlap 回退。
        策略：
        1. 从当前已完成 chunk 的末尾截取 self.overlap 个字符作为目标窗口
        2. 在窗口内找最靠后的句子边界（。！？.!?）作为 overlap 起点
        3. 找不到句界再退到标点/空白边界，再找不到才按字符硬切 overlap
        4. 以"完整句子列表"形式返回，交给上层 _make_chunk 拼接，保证 overlap 是完整语义单位
        """
        if self.overlap <= 0 or not chunks:
            return []

        tail_str = '\n\n'.join(chunks)
        if not tail_str:
            return []

        # 1) 截取末尾 overlap 窗口（在窗口内找边界，不让 overlap 超过预算）
        window = tail_str[-self.overlap:] if len(tail_str) > self.overlap else tail_str

        # 2) 在窗口内找最后一个句末标点；命中则从该位置之后作为 overlap（含句末标点本身）
        sent_boundaries = [m.start() for m in re.finditer(r'[。！？.!?]', window)]
        if sent_boundaries:
            last = sent_boundaries[-1]
            # 若句界刚好在窗口最后一位，避免 overlap 返回空；前退一句界或退回标点级
            if last == len(window) - 1:
                if len(sent_boundaries) >= 2:
                    last = sent_boundaries[-2] + 1
                else:
                    last = 0  # 整个窗口就是 overlap（退化）
            else:
                last += 1  # 包含标点
            overlap_text = window[last:]
        else:
            # 3) 无句界时，退到标点/空白分隔
            punc_boundaries = [m.start() for m in re.finditer(r'[，、；：,;:\s\-—]', window)]
            if punc_boundaries:
                last = punc_boundaries[-1]
                # 标点之后才是 overlap 起点；若标点刚好在末尾则不退化到空
                if last == len(window) - 1:
                    last = 0 if len(punc_boundaries) < 2 else punc_boundaries[-2] + 1
                else:
                    last += 1
                overlap_text = window[last:]
            else:
                # 4) 最后才按字符硬切
                overlap_text = window

        overlap_text = overlap_text.strip('\n ')
        if not overlap_text:
            return []
        # 返回单段（保持与旧接口兼容：List[str] 每元素是一段）
        return [overlap_text]

    def get_stats(self, chunks: list[Chunk]) -> dict[str, float]:
        """获取分块统计信息"""
        if not chunks:
            return {'total': 0, 'avg_length': 0, 'min_length': 0, 'max_length': 0}
        
        lengths = [len(c['content']) for c in chunks]
        return {
            'total': len(chunks),
            'avg_length': sum(lengths) / len(lengths),
            'min_length': float(min(lengths)),
            'max_length': float(max(lengths)),
        }
