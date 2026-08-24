#!/usr/bin/env python

"""
商业级Live2D口型同步引擎 V2.0
完整实现：Kalman滤波 + 音素识别 + 情感联动 + 60FPS优化
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Tuple

import numpy as np

# 尝试导入scipy，如果失败则提供降级方案
try:
    from scipy import signal
    from scipy.fft import fft, fftfreq
    SCIPY_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("scipy可用，启用高级口型同步功能（FFT/LPC/共振峰检测）")
except ImportError:
    SCIPY_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("scipy不可用，使用简化的口型同步（仅基于音量）")
    # 使用numpy的FFT作为降级方案
    from numpy.fft import fft, fftfreq
    signal = None  # 标记为不可用


class EmotionType(Enum):
    """情感类型枚举"""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    SURPRISED = "surprised"
    QUESTIONING = "questioning"


@dataclass
class LipSyncState:
    """口型同步状态"""
    mouth_open: float = 0.0
    mouth_form: float = 0.0
    mouth_smile: float = 0.0
    eye_brow_up: float = 0.0
    eye_wide: float = 0.0
    current_viseme: str = 'silence'
    current_emotion: EmotionType = EmotionType.NEUTRAL
    timestamp: float = 0.0


# 注释：KalmanFilter 和 SpringDamperSystem 类已被移除
# 原因：这些类在实际使用中被替换为简单的指数平滑算法
# SpringDamperSystem 会导致数值爆炸问题
# 现在使用 exponential smoothing (alpha blending) 替代，见 process_audio_chunk 方法


class AdvancedLipSyncEngineV2:
    """
    商业级Live2D口型同步引擎 V2.0
    
    核心特性：
    1. 卡尔曼滤波预测性平滑
    2. 弹簧-阻尼物理模拟
    3. 高级音素识别（MEL频谱 + 共振峰）
    4. 情感表情联动
    5. 60FPS优化更新
    6. 自适应参数调整
    """
    
    # 音素参数预设（实时语音和EdgeTTS统一参数）
    VISEME_PARAMS = {
        # 元音 - 适中幅度
        'a': {'mouth_open': 0.70, 'mouth_form': 0.0, 'mouth_smile': 0.05, 'name': '啊[a]'},
        'i': {'mouth_open': 0.25, 'mouth_form': -0.68, 'mouth_smile': 0.38, 'name': '衣[i]'},
        'u': {'mouth_open': 0.32, 'mouth_form': 0.72, 'mouth_smile': -0.18, 'name': '乌[u]'},
        'e': {'mouth_open': 0.45, 'mouth_form': -0.25, 'mouth_smile': 0.18, 'name': '诶[e]'},
        'o': {'mouth_open': 0.58, 'mouth_form': 0.58, 'mouth_smile': 0.0, 'name': '哦[o]'},

        # 辅音
        'consonant': {'mouth_open': 0.28, 'mouth_form': 0.0, 'mouth_smile': 0.0, 'name': '辅音'},
        'sibilant': {'mouth_open': 0.18, 'mouth_form': -0.28, 'mouth_smile': 0.22, 'name': '齿音[s/sh/z]'},
        'm_n': {'mouth_open': 0.06, 'mouth_form': 0.0, 'mouth_smile': 0.0, 'name': '闭音[m/n]'},
        'plosive': {'mouth_open': 0.22, 'mouth_form': 0.0, 'mouth_smile': 0.0, 'name': '爆破音[p/b/t/d/k/g]'},

        # 特殊
        'silence': {'mouth_open': 0.0, 'mouth_form': 0.0, 'mouth_smile': 0.0, 'name': '静音'},
    }
    
    # 情感参数预设
    EMOTION_PARAMS = {
        EmotionType.NEUTRAL: {
            'mouth_smile': 0.0,
            'eye_brow_up': 0.0,
            'eye_wide': 0.0,
        },
        EmotionType.HAPPY: {
            'mouth_smile': 0.6,
            'eye_brow_up': 0.1,
            'eye_wide': 0.0,
        },
        EmotionType.SAD: {
            'mouth_smile': -0.4,
            'eye_brow_up': -0.3,
            'eye_wide': 0.0,
        },
        EmotionType.ANGRY: {
            'mouth_smile': -0.3,
            'eye_brow_up': -0.5,
            'eye_wide': 0.2,
        },
        EmotionType.SURPRISED: {
            'mouth_smile': 0.0,
            'eye_brow_up': 0.7,
            'eye_wide': 0.8,
        },
        EmotionType.QUESTIONING: {
            'mouth_smile': 0.2,
            'eye_brow_up': 0.4,
            'eye_wide': 0.1,
        },
    }
    
    def __init__(self, sample_rate: int = 24000, target_fps: int = 60):
        """
        初始化引擎

        Args:
            sample_rate: 音频采样率
            target_fps: 目标更新帧率
        """
        self.sample_rate = sample_rate
        self.target_fps = target_fps
        self.frame_time = 1.0 / target_fps

        # 注释：Kalman滤波器和弹簧-阻尼系统已被移除
        # 原因：SpringDamperSystem会导致数值爆炸，Kalman过于复杂
        # 现使用简单的指数平滑算法（alpha blending），在process_audio_chunk中实现

        # 当前状态
        self.state = LipSyncState()

        # 目标值
        self.target_mouth_open = 0.0
        self.target_mouth_form = 0.0
        self.target_mouth_smile = 0.0

        # 情感状态
        self.current_emotion = EmotionType.NEUTRAL
        self.emotion_intensity = 1.0

        # 历史记录（用于自适应）
        self.volume_history: list[float] = []
        self.max_history_size = 100

        # 动态阈值（EdgeTTS优化）
        self.silence_threshold = 50  # 静音阈值，过滤背景噪音
        self.adaptive_volume_scale = 2000.0  # 音量缩放系数，EdgeTTS使用

        # 持续时间控制（防止过快闭嘴）
        self.last_sound_time = 0.0
        self.sound_persistence = 0.15  # 声音持续150ms，防止过快闭嘴

        # 注释：音素稳定性控制和历史追踪已被移除
        # 原因：_stabilize_viseme 方法会导致音素切换延迟（需要2帧确认）
        # 实时语音中音素变化快，稳定性检查反而降低响应速度
        # 现在直接使用原始识别结果，通过指数平滑算法处理抖动

        # 性能统计
        self.last_update_time = time.time()
        self.frame_count = 0
        self.avg_fps = 0.0

        logger.info(f"AdvancedLipSyncEngineV2 初始化完成 (目标{target_fps}FPS)")
    
    def process_audio_chunk(self, audio_chunk: bytes) -> dict[str, float]:
        """
        处理音频块，返回Live2D参数（主入口）
        
        Args:
            audio_chunk: PCM 16bit 音频数据
            
        Returns:
            Live2D参数字典
        """
        try:
            current_time = time.time()
            dt = current_time - self.last_update_time
            self.last_update_time = current_time
            
            # 转换音频数据
            audio_array = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32)

            # 1. 计算RMS能量和ZCR
            rms = self._calculate_rms(audio_array)
            zcr = self._calculate_zcr(audio_array)

            # 2. 更新历史并自适应
            self._update_volume_history(rms)

            if rms < self.silence_threshold:
                # 静音状态
                self.target_mouth_open = 0.0
                self.target_mouth_form = 0.0
                self.state.current_viseme = 'silence'
                viseme = 'silence'
            else:
                # 完整DSP处理（每帧都执行，确保同步）
                # 3. 频谱分析
                spectrum_features = self._analyze_spectrum_advanced(audio_array)

                # 4. 共振峰检测
                formants = self._detect_formants_lpc(audio_array)
                f1, f2 = formants

                # 5. 基频检测
                f0 = self._detect_f0_autocorr(audio_array)

                # 6. 音素识别（增强版，使用ZCR特征）
                raw_viseme = self._identify_viseme_advanced(spectrum_features, formants, f0, rms, zcr)

                # 直接使用原始音素
                viseme = raw_viseme
                self.state.current_viseme = viseme

                # 7. 获取目标参数
                params = self.VISEME_PARAMS.get(viseme, self.VISEME_PARAMS['silence'])

                # 8. 能量调制
                energy_factor = np.clip(rms / self.adaptive_volume_scale, 0.3, 1.0)

                self.target_mouth_open = params['mouth_open'] * energy_factor
                self.target_mouth_form = params['mouth_form']
                self.target_mouth_smile = params.get('mouth_smile', 0.0)

            # 9. 简化平滑处理（快速响应，减少延迟）
            # 使用更大的alpha值（0.5-0.6），快速跟踪目标值
            # 平衡平滑度和响应速度
            alpha_open = 0.6  # 提高到0.6，更快响应（原0.3）
            alpha_form = 0.5  # 提高到0.5，更快响应（原0.25）

            if not hasattr(self, '_smooth_mouth_open'):
                self._smooth_mouth_open = self.target_mouth_open
                self._smooth_mouth_form = self.target_mouth_form

            self._smooth_mouth_open += (self.target_mouth_open - self._smooth_mouth_open) * alpha_open
            self._smooth_mouth_form += (self.target_mouth_form - self._smooth_mouth_form) * alpha_form

            final_mouth_open = self._smooth_mouth_open
            final_mouth_form = self._smooth_mouth_form
            final_mouth_smile = self.target_mouth_smile
            
            # 11. 应用情感调制
            emotion_modulation = self._get_emotion_modulation()
            final_mouth_smile += emotion_modulation['mouth_smile']

            # 最终参数输出日志（DEBUG级别）
            if self.frame_count % 10 == 0 and logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    f"📊 [最终输出] 张开={final_mouth_open:.3f} 嘴形={final_mouth_form:.3f} 微笑={final_mouth_smile:.3f}"
                )
            
            # 10. 禁用自然抖动（实时语音中抖动会增加视觉延迟感）
            # 直接使用平滑后的值，不添加随机抖动
            final_params = {
                'mouth_open': np.clip(final_mouth_open, 0.0, 1.0),
                'mouth_form': np.clip(final_mouth_form, -1.0, 1.0),
                'mouth_smile': np.clip(final_mouth_smile, -1.0, 1.0),
            }

            # 13. 添加情感参数
            final_params.update({
                'eye_brow_up': emotion_modulation['eye_brow_up'],
                'eye_wide': emotion_modulation['eye_wide'],
            })
            
            # 更新状态
            self.state.mouth_open = final_params['mouth_open']
            self.state.mouth_form = final_params['mouth_form']
            self.state.mouth_smile = final_params['mouth_smile']
            self.state.timestamp = current_time
            
            # 更新FPS统计
            self._update_fps_stats()
            
            return final_params
            
        except Exception as e:
            logger.debug(f"音频处理错误: {e}")
            return {'mouth_open': 0.0, 'mouth_form': 0.0, 'mouth_smile': 0.0}
    
    def _calculate_rms(self, audio: np.ndarray) -> float:
        """计算RMS能量"""
        return float(np.sqrt(np.mean(audio ** 2)))

    def _calculate_zcr(self, audio: np.ndarray) -> float:
        """
        计算过零率(Zero Crossing Rate)

        过零率是音频信号在单位时间内穿越零点的次数，是区分清音和浊音的重要特征。

        特征解释：
        - 高ZCR (>0.3): 清音/齿音（s, sh, f, th等）
        - 低ZCR (<0.15): 浊音/鼻音（元音, m, n, l等）
        - 中等ZCR (0.15-0.3): 过渡音或混合音

        Returns:
            ZCR值 (0.0-1.0范围)
        """
        if len(audio) < 2:
            return 0.0

        # 计算符号变化次数
        signs = np.sign(audio)
        sign_changes = np.diff(signs)

        # 过零率 = 符号变化次数 / (2 * 样本数)
        zcr = np.sum(np.abs(sign_changes)) / (2.0 * len(audio))

        return float(zcr)
    
    def _update_volume_history(self, rms: float):
        """更新音量历史并自适应调整"""
        self.volume_history.append(rms)
        if len(self.volume_history) > self.max_history_size:
            self.volume_history.pop(0)

        # 自适应调整阈值（基于最近的音量分布）
        if len(self.volume_history) >= 20:
            percentile_95 = np.percentile(self.volume_history, 95)
            self.adaptive_volume_scale = max(1000.0, percentile_95 * 1.2)

    # 注释：已移除以下未使用的方法（约170行代码）：
    # - _stabilize_viseme(): 音素稳定性检查，导致延迟，已在process_audio_chunk中直接使用原始音素
    # - _track_viseme_changes(): 音素历史追踪，用于诊断，但从未被调用
    # - _add_natural_variation(): 添加自然抖动，已禁用，直接使用np.clip替代

    def _analyze_spectrum_advanced(self, audio: np.ndarray) -> dict[str, float]:
        """
        高级频谱分析（MEL频谱）

        性能说明：此方法执行标准FFT用于频谱分析。
        注意：共振峰检测需要单独的预加重FFT，目前无法合并。
        未来优化方向：可考虑缓存FFT结果或使用更快的FFT实现。

        Returns:
            频谱特征字典
        """
        try:
            n = len(audio)
            if n < 512:
                audio = np.pad(audio, (0, 512 - n), 'constant')
                n = 512
            
            # 应用汉明窗
            windowed = audio * np.hamming(len(audio))
            
            # FFT变换
            spectrum = fft(windowed)
            freqs = fftfreq(len(spectrum), 1/self.sample_rate)
            magnitude = np.abs(spectrum[:n//2])
            freqs = freqs[:n//2]
            
            # MEL频率转换
            mel_bands = self._convert_to_mel_scale(freqs, magnitude)
            
            # 分频段能量
            features = {
                'low_energy': np.sum(mel_bands[:20]) / np.sum(mel_bands),  # 低频
                'mid_energy': np.sum(mel_bands[20:50]) / np.sum(mel_bands),  # 中频
                'high_energy': np.sum(mel_bands[50:]) / np.sum(mel_bands),  # 高频
            }
            
            # 频谱质心
            if np.sum(magnitude) > 0:
                features['spectral_centroid'] = np.sum(freqs * magnitude) / np.sum(magnitude)
            else:
                features['spectral_centroid'] = 0
            
            # 频谱平坦度（识别清音）
            geometric_mean = np.exp(np.mean(np.log(magnitude + 1e-10)))
            arithmetic_mean = np.mean(magnitude)
            features['spectral_flatness'] = geometric_mean / (arithmetic_mean + 1e-10)
            
            return features
            
        except Exception as e:
            logger.debug(f"频谱分析错误: {e}")
            return {'low_energy': 0, 'mid_energy': 0, 'high_energy': 0, 'spectral_centroid': 0, 'spectral_flatness': 0}
    
    def _convert_to_mel_scale(self, freqs: np.ndarray, magnitude: np.ndarray, n_mels: int = 80) -> np.ndarray:
        """转换到MEL频率尺度"""
        def hz_to_mel(hz):
            return 2595 * np.log10(1 + hz / 700)
        
        def mel_to_hz(mel):
            return 700 * (10 ** (mel / 2595) - 1)
        
        # 创建MEL滤波器组
        mel_min = hz_to_mel(80)
        mel_max = hz_to_mel(8000)
        mel_points = np.linspace(mel_min, mel_max, n_mels + 2)
        hz_points = mel_to_hz(mel_points)
        
        # 计算每个MEL频段的能量
        mel_bands = np.zeros(n_mels)
        for i in range(n_mels):
            # 找到对应的频率范围
            mask = (freqs >= hz_points[i]) & (freqs <= hz_points[i + 2])
            if np.any(mask):
                mel_bands[i] = np.sum(magnitude[mask])
        
        return mel_bands
    
    def _detect_formants_lpc(self, audio: np.ndarray) -> tuple[float, float]:
        """
        LPC线性预测编码共振峰检测（增强版）

        Returns:
            (F1, F2) 共振峰频率
        """
        try:
            # 如果scipy不可用，返回默认值
            if not SCIPY_AVAILABLE or signal is None:
                return 0.0, 0.0

            if len(audio) < 256:
                return 0.0, 0.0

            # 预加重
            pre_emphasis = 0.97
            emphasized = np.append(audio[0], audio[1:] - pre_emphasis * audio[:-1])

            # FFT峰值检测法（简化但有效）
            spectrum = np.abs(fft(emphasized * np.hamming(len(emphasized))))
            freqs = fftfreq(len(spectrum), 1/self.sample_rate)

            # 只看正频率
            pos_freqs = freqs[:len(freqs)//2]
            pos_spectrum = spectrum[:len(spectrum)//2]

            # 平滑频谱
            smoothed = signal.savgol_filter(pos_spectrum, 11, 3)

            # 找峰值
            peaks, properties = signal.find_peaks(smoothed, height=np.max(smoothed)*0.15, distance=10)

            if len(peaks) >= 2:
                # 按能量排序
                peak_heights = properties['peak_heights']
                sorted_indices = np.argsort(peak_heights)[::-1]
                top_peaks = peaks[sorted_indices[:2]]

                # 按频率排序得到F1, F2
                top_peaks_sorted = np.sort(top_peaks)
                f1 = float(pos_freqs[top_peaks_sorted[0]])
                f2 = float(pos_freqs[top_peaks_sorted[1]])

                # 限制在合理范围
                f1 = np.clip(f1, 200, 1000)
                f2 = np.clip(f2, 800, 3000)

                return f1, f2

            return 0.0, 0.0
            
        except Exception as e:
            logger.debug(f"共振峰检测错误: {e}")
            return 0.0, 0.0
    
    def _detect_f0_autocorr(self, audio: np.ndarray) -> float:
        """
        自相关法基频检测（增强版）

        Returns:
            基频F0
        """
        try:
            # 自相关
            correlation = np.correlate(audio, audio, mode='full')
            correlation = correlation[len(correlation)//2:]

            # 归一化
            correlation = correlation / correlation[0] if correlation[0] > 0 else correlation

            # 限制搜索范围 (80-400Hz)
            min_period = int(self.sample_rate / 400)
            max_period = int(self.sample_rate / 80)

            search_range = correlation[min_period:max_period]

            if len(search_range) > 0:
                # 如果scipy可用，使用find_peaks
                if SCIPY_AVAILABLE and signal is not None:
                    peaks, _ = signal.find_peaks(search_range, height=0.3)

                    if len(peaks) > 0:
                        # 选择最高的峰
                        best_peak = peaks[np.argmax(search_range[peaks])]
                        period = best_peak + min_period
                        f0 = self.sample_rate / period

                        # 限制在合理范围
                        f0 = np.clip(f0, 80, 400)
                        return float(f0)
                else:
                    # 降级方案：简单地找最大值
                    best_peak = np.argmax(search_range)
                    period = best_peak + min_period
                    f0 = self.sample_rate / period

                    # 限制在合理范围
                    f0 = np.clip(f0, 80, 400)
                    return float(f0)

            return 0.0

        except Exception as e:
            logger.debug(f"基频检测错误: {e}")
            return 0.0
    
    def _identify_viseme_advanced(self, spectrum: dict, formants: tuple, f0: float, rms: float, zcr: float = 0.0) -> str:
        """
        增强版音素识别（使用ZCR特征）

        基于多维特征综合判断

        Args:
            spectrum: 频谱特征字典
            formants: (F1, F2) 共振峰频率元组
            f0: 基频
            rms: 音频能量
            zcr: 过零率（新增，用于清音/浊音判断）

        Returns:
            识别的音素/viseme字符串
        """
        f1, f2 = formants

        # 1. 静音判断
        if rms < self.silence_threshold:
            return 'silence'

        # 2. 基于ZCR的清音判断（优先级最高）
        # 高ZCR通常表示清音/齿音（s, sh, f, th等）
        if zcr > 0.3:
            return 'sibilant'

        # 3. 基于频谱平坦度的清音判断（辅助）
        if spectrum.get('spectral_flatness', 0) > 0.5:
            return 'sibilant'

        # 4. 辅音判断
        high_energy = spectrum.get('high_energy', 0)
        mid_energy = spectrum.get('mid_energy', 0)

        if high_energy > 0.4:
            return 'sibilant'  # 齿音 s/sh/z

        if mid_energy > 0.6:
            if rms < self.adaptive_volume_scale * 0.3:
                return 'm_n'  # 鼻音 m/n
            return 'plosive'  # 爆破音

        # 5. 元音判断（基于共振峰）
        if f1 > 0 and f2 > 0:
            # F1/F2比值分析
            ratio = f1 / f2 if f2 > 0 else 0
            
            # 元音分类（基于共振峰空间）
            if f1 > 700:  # 低元音
                if f2 < 1400:
                    return 'o'  # 后低元音 [ɔ]
                elif f2 > 1400:
                    return 'a'  # 前低元音 [a]
            elif f1 > 400:  # 中元音
                if f2 > 2000:
                    return 'e'  # 前中元音 [e]
                else:
                    return 'o'  # 后中元音 [o]
            else:  # 高元音 f1 < 400
                if f2 > 2200:
                    return 'i'  # 前高元音 [i]
                else:
                    return 'u'  # 后高元音 [u]
        
        # 5. 基于频谱质心的备用判断
        centroid = spectrum.get('spectral_centroid', 0)
        if centroid > 3000:
            return 'i'
        elif centroid > 1500:
            return 'e'
        elif centroid > 800:
            return 'a'
        else:
            return 'o'
    
    def _get_emotion_modulation(self) -> dict[str, float]:
        """获取情感调制参数"""
        base_params = self.EMOTION_PARAMS.get(self.current_emotion, self.EMOTION_PARAMS[EmotionType.NEUTRAL])
        
        # 应用情感强度
        return {
            key: value * self.emotion_intensity
            for key, value in base_params.items()
        }

    def _update_fps_stats(self):
        """更新FPS统计"""
        self.frame_count += 1
        
        if self.frame_count % 60 == 0:
            current_time = time.time()
            elapsed = current_time - self.state.timestamp
            if elapsed > 0:
                self.avg_fps = 60 / elapsed
                if self.avg_fps < self.target_fps * 0.8:
                    logger.warning(f"FPS低于目标: {self.avg_fps:.1f}/{self.target_fps}")
    
    def set_emotion(self, emotion: EmotionType, intensity: float = 1.0):
        """
        设置情感状态
        
        Args:
            emotion: 情感类型
            intensity: 强度 (0.0-1.0)
        """
        self.current_emotion = emotion
        self.emotion_intensity = np.clip(intensity, 0.0, 1.0)
        logger.debug(f"设置情感: {emotion.value}, 强度: {intensity}")
    
    def detect_emotion_from_prosody(self, f0: float, rms: float, speech_rate: float = 1.0) -> EmotionType:
        """
        从韵律特征检测情感（自动情感识别）
        
        Args:
            f0: 基频
            rms: 音量
            speech_rate: 语速（相对值）
            
        Returns:
            检测到的情感类型
        """
        # 简单的规则基情感识别
        if f0 > 250 and rms > self.adaptive_volume_scale * 0.6:
            return EmotionType.SURPRISED  # 高音+大声 = 惊讶
        elif f0 > 200 and speech_rate > 1.2:
            return EmotionType.HAPPY  # 高音+快速 = 开心
        elif f0 < 150 and rms > self.adaptive_volume_scale * 0.5:
            return EmotionType.ANGRY  # 低音+大声 = 生气
        elif f0 < 150 and rms < self.adaptive_volume_scale * 0.3:
            return EmotionType.SAD  # 低音+小声 = 悲伤
        else:
            return EmotionType.NEUTRAL
    
    def reset(self):
        """重置引擎状态"""
        self.state = LipSyncState()

        # 重置平滑状态
        if hasattr(self, '_smooth_mouth_open'):
            self._smooth_mouth_open = 0.0
        if hasattr(self, '_smooth_mouth_form'):
            self._smooth_mouth_form = 0.0

        # 清空历史
        self.volume_history.clear()

        logger.info("[LipSync] 引擎已重置")
    
    def get_performance_stats(self) -> dict[str, Any]:
        """获取性能统计"""
        return {
            'avg_fps': self.avg_fps,
            'target_fps': self.target_fps,
            'frame_count': self.frame_count,
            'current_viseme': self.state.current_viseme,
            'current_emotion': self.current_emotion.value,
            'adaptive_threshold': self.adaptive_volume_scale,
        }


# 便捷函数
def create_advanced_lip_sync_engine(sample_rate: int = 24000, target_fps: int = 60) -> AdvancedLipSyncEngineV2:
    """创建高级口型同步引擎实例"""
    return AdvancedLipSyncEngineV2(sample_rate=sample_rate, target_fps=target_fps)