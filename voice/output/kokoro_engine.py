# -*- coding: utf-8 -*-
"""
本地 kokoro-onnx 引擎封装（离线 TTS 回退）。

在 Edge TTS（联网）或 NagaModel（登录/付费）不可用时，作为 NEKO 语音的
纯本地兜底引擎。融合自 thewh1teagle/kokoro-onnx（MIT）。

用法：
    from voice.output.kokoro_engine import KokoroEngine
    engine = KokoroEngine()
    path = engine.generate_speech(text, voice, response_format, speed)
"""
from __future__ import annotations

import io
import logging
import sys
import tempfile
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# 引擎包（kokoro-onnx）可能的安装位置：主仓 vendor/ 或独立 site-packages
# 指向 vendor/kokoro-onnx 父目录，使 "import kokoro_onnx" 命中 vendor/kokoro-onnx/kokoro_onnx/
_ENGINE_PKG_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "vendor" / "kokoro-onnx",
]


def _import_kokoro():
    """按候选路径导入 kokoro_onnx 包，全部失败则抛 ImportError。"""
    for p in _ENGINE_PKG_CANDIDATES:
        if p.exists() and str(p) not in sys.path:
            sys.path.insert(0, str(p))
    from kokoro_onnx import Kokoro  # noqa: F401
    return Kokoro


class KokoroEngine:
    """本地 kokoro-onnx 引擎，懒加载单例。"""

    def __init__(self, model: str = "", voices: str = "", lang: str = "zh",
                 default_voice: str = "zf_002", config: str = ""):
        self._kokoro = None
        self._g2p = None
        self._g2p_lang = None

        # 模型文件定位：优先显式参数，否则读主仓 config，再否则默认路径
        models_dir = self._default_models_dir()
        self.model = model or str(models_dir / "kokoro.onnx")
        self.voices = voices or str(models_dir / "voices.bin")
        self.config = config or str(models_dir / "config.json")
        self.lang = lang
        self.default_voice = default_voice

    @staticmethod
    def _default_models_dir() -> Path:
        """默认模型目录：主仓数据目录下 models/kokoro。"""
        try:
            from system.config import get_data_dir
            return Path(get_data_dir()) / "models" / "kokoro"
        except Exception:
            return Path.home() / ".naga" / "models" / "kokoro"

    # ---- 加载 ----
    def _ensure_loaded(self):
        if self._kokoro is not None:
            return
        Kokoro = _import_kokoro()
        self._kokoro = Kokoro(self.model, self.voices, vocab_config=self.config)

    def _ensure_g2p(self, lang: str):
        if lang == self._g2p_lang:
            return
        if lang in ("zh", "ja", "ko"):
            try:
                if lang == "zh":
                    from misaki import zh
                    g2p_cls = zh.ZHG2P
                elif lang == "ja":
                    from misaki import ja
                    g2p_cls = ja.JAG2P
                else:
                    from misaki import ko
                    g2p_cls = ko.KOG2P
            except ImportError as e:
                raise RuntimeError(
                    f"本地引擎语言 {lang} 需安装 misaki-fork[{lang}]：uv pip install 'misaki-fork[{lang}]'"
                ) from e
            self._g2p = g2p_cls(version="1.1")
        else:
            self._g2p = None
        self._g2p_lang = lang

    # ---- 合成 ----
    def synthesize(self, text: str, voice: str | None = None,
                   lang: str | None = None, speed: float = 1.0) -> tuple[np.ndarray, int]:
        self._ensure_loaded()
        lang = lang or self.lang
        voice = voice or self.default_voice
        self._ensure_g2p(lang)
        if self._g2p is not None:
            phonemes, _ = self._g2p(text)
            return self._kokoro.create(phonemes, voice=voice, speed=speed, is_phonemes=True)
        return self._kokoro.create(text, voice=voice, speed=speed, lang=lang)

    def generate_speech(self, text: str, voice: str | None = None,
                        response_format: str = "wav", speed: float = 1.0) -> str:
        """返回临时音频文件路径。原生 wav；其余格式需 ffmpeg。"""
        samples, sr = self.synthesize(text, voice=voice, speed=speed)
        data = self._samples_to_wav(samples, sr)
        suffix = f".{response_format}" if response_format != "wav" else ".wav"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(data)
        tmp.close()
        return tmp.name

    @staticmethod
    def _samples_to_wav(samples: np.ndarray, sample_rate: int) -> bytes:
        import wave

        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(pcm.tobytes())
        return buf.getvalue()

    def list_voices(self) -> list[str]:
        self._ensure_loaded()
        return self._kokoro.get_voices()


def _read_tts_config():
    """读取主仓 TTS 配置，不可用时返回默认值。"""
    try:
        from system.config import config
        tts = config.tts
        return {
            "local_engine": getattr(tts, "local_engine", False),
            "local_model": getattr(tts, "local_model", ""),
            "local_voices": getattr(tts, "local_voices", ""),
            "local_lang": getattr(tts, "local_lang", "zh"),
            "local_default_voice": getattr(tts, "local_default_voice", "zf_002"),
        }
    except Exception:
        return {
            "local_engine": False,
            "local_model": "",
            "local_voices": "",
            "local_lang": "zh",
            "local_default_voice": "zf_002",
        }


_engine: KokoroEngine | None = None


def get_engine() -> KokoroEngine:
    global _engine
    if _engine is None:
        c = _read_tts_config()
        _engine = KokoroEngine(
            model=c["local_model"],
            voices=c["local_voices"],
            lang=c["local_lang"],
            default_voice=c["local_default_voice"],
        )
    return _engine


def is_available() -> bool:
    """探测本地引擎是否可用（模型文件存在 + 包可导入）。"""
    if not _read_tts_config()["local_engine"]:
        return False
    try:
        _import_kokoro()
    except ImportError:
        logger.warning("本地 kokoro 引擎未安装（kokoro_onnx 包缺失），跳过")
        return False
    eng = get_engine()
    if not Path(eng.model).exists() or not Path(eng.voices).exists():
        logger.warning("本地 kokoro 引擎模型文件缺失，跳过")
        return False
    return True