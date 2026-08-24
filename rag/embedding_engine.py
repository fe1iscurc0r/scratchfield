"""
嵌入引擎模块 - 基于 bge-small-zh 的本地文本向量化
"""
import logging
import os
import threading
from pathlib import Path
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingEngine:
    """文本嵌入引擎 - 基于 bge-small-zh-v1.5 模型"""
    
    _instance = None
    _instance_lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        # HIGH-5: 双检锁单例模式，线程安全
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5", 
                 cache_dir: str | None = None):
        if self._initialized:
            return
        
        self.model_name = model_name
        self.cache_dir = cache_dir or self._get_default_cache_dir()
        self._model = None
        self._tokenizer = None
        self._device = 'cpu'
        self._initialized = True
    
    def _get_default_cache_dir(self) -> str:
        """获取默认的模型缓存目录"""
        from system.config import get_data_dir
        cache_dir = get_data_dir() / "rag" / "embeddings"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return str(cache_dir)
    
    def load_model(self) -> bool:
        """加载嵌入模型
        
        Returns:
            加载是否成功
        """
        if self._model is not None:
            return True
        
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
            
            logger.info(f"正在加载嵌入模型: {self.model_name}")
            
            # 设备选择策略：
            # - 优先读取环境变量 LUMO_EMBEDDING_DEVICE（cpu/cuda/auto）
            # - 未设置时默认 CPU，避免嵌入模型占用 GPU 显存导致前端 WebGL 上下文丢失
            #   （Live2D 用 WebGL 渲染，与 CUDA 嵌入共享 GPU 时易触发 context lost）
            # - 显式设置为 cuda/auto 时才检测并使用 GPU
            env_device = os.environ.get('LUMO_EMBEDDING_DEVICE', 'cpu').lower().strip()
            if env_device in ('cuda', 'auto', 'gpu'):
                if torch.cuda.is_available():
                    self._device = 'cuda'
                    logger.info(f"使用 GPU 加速（LUMO_EMBEDDING_DEVICE={env_device}）")
                else:
                    self._device = 'cpu'
                    logger.info(f"GPU 不可用，回退 CPU（LUMO_EMBEDDING_DEVICE={env_device} 但 CUDA 未就绪）")
            else:
                self._device = 'cpu'
                logger.info(f"使用 CPU 运行（LUMO_EMBEDDING_DEVICE={env_device or 'cpu'}，避免与前端 WebGL 抢 GPU）")
            
            # 加载 tokenizer 和 model
            # 优先检查 modelscope 缓存（国内环境 HuggingFace 可能不可达）
            modelscope_path = os.path.expanduser(
                f"~/.cache/modelscope/models/{self.model_name.replace('/', '--')}/snapshots/master"
            )
            if os.path.isdir(modelscope_path):
                logger.info(f"使用 modelscope 缓存的模型: {modelscope_path}")
                load_path = modelscope_path
            else:
                load_path = self.model_name

            self._tokenizer = AutoTokenizer.from_pretrained(
                load_path,
                cache_dir=self.cache_dir
            )
            # AutoModel.from_pretrained 在 Windows 多线程进程中加载 safetensors 时
            # 可能因 mmap 失败抛 [Errno 22] Invalid argument。
            # 回退策略：safetensors 失败 → 用 pytorch_model.bin 重试
            try:
                self._model = AutoModel.from_pretrained(
                    load_path,
                    cache_dir=self.cache_dir
                )
            except OSError as e:
                logger.warning(f"safetensors 加载失败 ({e})，回退到 pytorch_model.bin")
                self._model = AutoModel.from_pretrained(
                    load_path,
                    cache_dir=self.cache_dir,
                    use_safetensors=False
                )
            self._model = self._model.to(self._device)
            self._model.eval()
            
            logger.info(f"嵌入模型加载成功: device={self._device}")
            return True
            
        except ImportError as e:
            logger.error(f"缺少依赖库: {e}")
            logger.error("请执行: pip install torch transformers")
            return False
        except Exception as e:
            # 用 logger.exception 打印完整堆栈，便于排查 [Errno 22] 等模糊错误
            logger.exception(f"加载嵌入模型失败: {type(e).__name__}: {e} | cwd={os.getcwd()} | pid={os.getpid()}")
            logger.info("降级方案: 使用随机向量占位（仅用于测试）")
            return False
    
    def encode(self, texts: list[str], batch_size: int = 32) -> np.ndarray | None:
        """将文本列表编码为向量
        
        Args:
            texts: 待编码的文本列表
            batch_size: 批处理大小
            
        Returns:
            向量矩阵 (numpy array)，失败返回 None
        """
        if not texts:
            return None
        
        # 尝试加载模型
        if self._model is None:
            if not self.load_model():
                # fail-fast：不再降级为随机向量（种子 42 的随机向量会让检索“看起来正常”但结果无意义）
                logger.error("嵌入模型加载失败，encode 返回 None，由上层 fail-fast")
                return None
        
        try:
            all_embeddings = []
            
            # 批处理编码
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                
                # 编码
                inputs = self._tokenizer(
                    batch_texts,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors='pt'
                ).to(self._device)
                
                # 获取嵌入向量
                import torch
                with torch.no_grad():
                    outputs = self._model(**inputs)
                    # 使用 CLS token 的嵌入或平均池化
                    attention_mask = inputs['attention_mask']
                    embeddings = self._mean_pooling(outputs.last_hidden_state, attention_mask)
                    # 归一化
                    embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                
                all_embeddings.append(embeddings.cpu().numpy())
            
            # 合并所有批次
            result = np.concatenate(all_embeddings, axis=0)
            logger.info(f"文本编码完成: {len(texts)} 条文本 -> {result.shape} 向量")
            return result
            
        except Exception as e:
            logger.error(f"文本编码失败: {e}")
            return None
    
    def _mean_pooling(self, last_hidden_state, attention_mask):
        """平均池化获取句子嵌入"""
        import torch
        mask_expanded = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
        sum_embeddings = torch.sum(last_hidden_state * mask_expanded, dim=1)
        sum_mask = mask_expanded.sum(dim=1).clamp(min=1e-9)
        return sum_embeddings / sum_mask
    
    def get_device(self) -> str:
        """获取当前设备"""
        return self._device
    
    def get_embedding_dim(self) -> int:
        """获取嵌入维度"""
        return 384  # bge-small-zh 默认维度
    
    def is_available(self) -> bool:
        """检查嵌入引擎是否可用"""
        return self._model is not None


def get_embedding_engine() -> EmbeddingEngine:
    """获取全局嵌入引擎实例"""
    return EmbeddingEngine()
