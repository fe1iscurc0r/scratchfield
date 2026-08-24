#!/usr/bin/env python

"""
音频管理器
处理音频输入输出、录音、播放等功能
"""

import base64
import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from typing import Optional

import numpy as np

# 尝试导入pyaudio，如果失败则提供友好提示
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    pyaudio = None

logger = logging.getLogger(__name__)


class AudioManager:
    """
    音频管理器
    负责音频的录制、播放和处理
    """

    def __init__(
        self,
        input_sample_rate: int = 16000,
        output_sample_rate: int = 24000,
        chunk_size_ms: int = 20,  # 优化：降低到20ms以提高口型同步更新率（50FPS，接近60FPS目标）
        vad_threshold: float = 0.02,
        echo_suppression: bool = True
    ):
        """
        初始化音频管理器

        参数:
            input_sample_rate: 输入采样率（Hz）
            output_sample_rate: 输出采样率（Hz）
            chunk_size_ms: 音频块大小（毫秒）- 20ms提供50FPS更新率，接近Live2D 60FPS口型同步目标
            vad_threshold: 静音检测阈值（0-1）
            echo_suppression: 是否启用回声抑制
        """
        if not PYAUDIO_AVAILABLE:
            raise ImportError(
                "PyAudio is not installed. Please install it with: "
                "pip install pyaudio"
            )

        self.input_sample_rate = input_sample_rate
        self.output_sample_rate = output_sample_rate
        self.chunk_size_ms = chunk_size_ms
        self.vad_threshold = vad_threshold
        self.echo_suppression = echo_suppression

        # 计算缓冲区大小
        self.input_chunk_size = int(input_sample_rate * chunk_size_ms / 1000)
        self.output_chunk_size = int(output_sample_rate * chunk_size_ms / 1000)

        # PyAudio实例
        self.pya = None
        self.input_stream = None
        self.output_stream = None

        # 队列
        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()
        self.b64_output_queue = queue.Queue()

        # 状态控制
        self.is_running = False
        self.is_recording = False
        self.is_playing = False
        self.force_mute = False

        # AI响应状态
        self.ai_response_done = False
        self.empty_queue_count = 0

        # 🔥 异步口型同步机制（模拟EdgeTTS）
        self.lip_sync_buffer = deque(maxlen=50)  # 优化：扩大滑动窗口缓冲区到50个块（1000ms@20ms/块），提供更稳定的数据访问
        self.playback_start_time = None  # 播放开始时间戳（用于流畅的位置计算）
        self.chunk_counter = 0  # 已加入缓冲区的块总数（用于计算滑动窗口位置）
        self.lip_sync_thread = None  # 独立的口型更新线程
        self.lip_sync_running = False  # 口型线程运行标志
        self.lip_sync_fps = 60  # 口型更新帧率
        self.buffer_lock = threading.Lock()  # 缓冲区线程锁

        # 🎯 实时语音固定延迟追踪参数
        # 核心思想：target_pos跟随实际播放位置（elapsed_time），但固定落后一个延迟
        # 关键：实际播放是连续的（用户反馈"语音流畅"），应该用elapsed_time而非chunk_counter
        # 优化：将延迟从100ms降低到25ms，显著提升口型同步速度（接近EdgeTTS的实时性）
        self.fixed_delay_seconds = 0.025  # 固定延迟25ms，平衡安全性和实时性
        self.fixed_delay_samples = int(self.fixed_delay_seconds * output_sample_rate)  # 600样本

        # 实时语音专用参数（与EdgeTTS的差异补偿）
        self.realtime_mouth_open_scale = 1.0  # 优化：改为1.0，让口型变化更明显（与EdgeTTS一致）

        # 线程
        self.input_thread = None
        self.output_decoder_thread = None
        self.output_player_thread = None

        # 初始化高级口型同步引擎（提前初始化，避免首次播放时阻塞）
        self._advanced_lip_sync_v2 = None
        self._lip_sync_error_count = 0

        try:
            from voice.input.voice_realtime.core.advanced_lip_sync_v2 import AdvancedLipSyncEngineV2
            self._advanced_lip_sync_v2 = AdvancedLipSyncEngineV2(
                sample_rate=output_sample_rate,
                target_fps=60
            )
            logger.info("✅ AudioManager已启用商业级Live2D口型同步引擎V2.0（Kalman滤波+音素识别+情感联动+60FPS）")

            # 引擎预热，避免第一次调用时的scipy/FFT初始化延迟
            import numpy as np
            dummy_audio = np.zeros(480, dtype=np.int16).tobytes()  # 20ms静音音频
            self._advanced_lip_sync_v2.process_audio_chunk(dummy_audio)
            logger.debug("口型同步引擎已预热，首次响应延迟已优化")

        except ImportError as e:
            logger.warning(f"无法加载高级口型同步引擎: {e}，口型同步功能将不可用")
        except Exception as e:
            logger.error(f"初始化口型同步引擎失败: {e}")

        # 回调函数
        self.on_audio_input: Callable[[bytes], None] | None = None
        self.on_playback_started: Callable[[], None] | None = None
        self.on_playback_ended: Callable[[], None] | None = None

        # 统计信息
        self.stats = {
            'input_chunks': 0,
            'output_chunks': 0,
            'silence_chunks': 0,
            'muted_chunks': 0
        }

        logger.info(f"AudioManager initialized: input={input_sample_rate}Hz, "
                   f"output={output_sample_rate}Hz, chunk={chunk_size_ms}ms")

    def initialize(self) -> bool:
        """
        初始化音频设备

        返回:
            bool: 是否成功初始化
        """
        try:
            # 创建PyAudio实例
            self.pya = pyaudio.PyAudio()

            # 创建输入流（麦克风）
            self.input_stream = self.pya.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.input_sample_rate,
                input=True,
                frames_per_buffer=self.input_chunk_size
            )

            # 创建输出流（扬声器）
            self.output_stream = self.pya.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.output_sample_rate,
                output=True,
                frames_per_buffer=self.output_chunk_size
            )

            logger.info("Audio devices initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize audio devices: {e}")
            self._cleanup_streams()
            return False

    def start(self):
        """
        启动音频管理器
        """
        if self.is_running:
            logger.warning("AudioManager is already running")
            return

        self.is_running = True
        self.is_recording = True

        # 启动输入线程
        self.input_thread = threading.Thread(
            target=self._input_loop,
            daemon=True,
            name="AudioInput"
        )
        self.input_thread.start()

        # 启动输出解码线程
        self.output_decoder_thread = threading.Thread(
            target=self._output_decoder_loop,
            daemon=True,
            name="AudioDecoder"
        )
        self.output_decoder_thread.start()

        # 启动输出播放线程
        self.output_player_thread = threading.Thread(
            target=self._output_player_loop,
            daemon=True,
            name="AudioPlayer"
        )
        self.output_player_thread.start()

        logger.info("AudioManager started")

    def stop(self):
        """
        停止音频管理器
        """
        logger.info("Stopping AudioManager...")

        # 停止异步口型同步线程
        self._stop_lip_sync_thread()

        # 设置停止标志
        self.is_running = False
        self.is_recording = False
        self.is_playing = False
        self.force_mute = False
        self.ai_response_done = False
        self.empty_queue_count = 0

        # 清空队列
        self._clear_all_queues()

        # 等待线程结束
        for thread in [self.input_thread, self.output_decoder_thread, self.output_player_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=1.0)

        # 清理音频流
        self._cleanup_streams()

        logger.info("AudioManager stopped")

    def _cleanup_streams(self):
        """清理音频流"""
        if self.input_stream:
            try:
                if self.input_stream.is_active():
                    self.input_stream.stop_stream()
                self.input_stream.close()
            except:
                pass
            self.input_stream = None

        if self.output_stream:
            try:
                if self.output_stream.is_active():
                    self.output_stream.stop_stream()
                self.output_stream.close()
            except:
                pass
            self.output_stream = None

        if self.pya:
            try:
                self.pya.terminate()
            except:
                pass
            self.pya = None

    def _clear_all_queues(self):
        """清空所有队列"""
        for q in [self.input_queue, self.output_queue, self.b64_output_queue]:
            while not q.empty():
                with suppress(queue.Empty):
                    q.get_nowait()

    def _input_loop(self):
        """输入音频循环"""
        silence_duration = 0

        while self.is_running:
            try:
                if not self.input_stream:
                    time.sleep(0.1)
                    continue

                # 读取音频数据
                audio_data = self.input_stream.read(
                    self.input_chunk_size,
                    exception_on_overflow=False
                )

                # 统计
                self.stats['input_chunks'] += 1

                # 检查是否应该静音
                if self.force_mute or not self.is_recording:
                    self.stats['muted_chunks'] += 1
                    continue

                # 静音检测
                if self._is_silence(audio_data):
                    silence_duration += self.chunk_size_ms
                    self.stats['silence_chunks'] += 1
                    if silence_duration > 2000:  # 2秒静音跳过
                        continue
                else:
                    silence_duration = 0

                # 添加到队列
                self.input_queue.put(audio_data)

                # 触发回调
                if self.on_audio_input:
                    self.on_audio_input(audio_data)

            except Exception as e:
                if self.is_running:
                    logger.error(f"Input loop error: {e}")
                time.sleep(0.1)

    def _output_decoder_loop(self):
        """输出音频解码循环"""
        while self.is_running:
            try:
                # 从Base64队列获取数据
                audio_b64 = self.b64_output_queue.get(timeout=0.1)

                if audio_b64:
                    # 解码Base64
                    try:
                        audio_bytes = base64.b64decode(audio_b64)
                        # 添加到播放队列
                        self.output_queue.put(audio_bytes)
                    except Exception as e:
                        logger.error(f"Failed to decode audio: {e}")

            except queue.Empty:
                continue
            except Exception as e:
                if self.is_running:
                    logger.error(f"Decoder loop error: {e}")
                time.sleep(0.1)

    def _output_player_loop(self):
        """输出音频播放循环"""
        was_playing = False
        consecutive_empty = 0  # 连续空队列计数

        while self.is_running:
            try:
                # 从播放队列获取数据
                audio_chunk = None
                with suppress(queue.Empty):
                    audio_chunk = self.output_queue.get(timeout=0.1)

                if audio_chunk:
                    # 重置连续空计数
                    consecutive_empty = 0

                    # 开始播放
                    if not was_playing:
                        was_playing = True
                        self.is_playing = True
                        self.force_mute = True
                        self.empty_queue_count = 0

                        # 启动异步口型同步机制
                        self.chunk_counter = 0
                        self._start_lip_sync_thread()

                        if self.on_playback_started:
                            self.on_playback_started()
                        logger.debug("Started audio playback")

                    # 播放音频
                    if self.output_stream:
                        # 🔧 关键修复：将大的audio_chunk切分成output_chunk_size的小块
                        # 原因：从队列接收的audio_chunk可能很大（如320ms），需要切分成20ms小块

                        # 切分音频块
                        audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
                        num_small_chunks = (len(audio_array) + self.output_chunk_size - 1) // self.output_chunk_size

                        for i in range(num_small_chunks):
                            start_idx = i * self.output_chunk_size
                            end_idx = min((i + 1) * self.output_chunk_size, len(audio_array))
                            small_chunk = audio_array[start_idx:end_idx].tobytes()

                            # 将小块加入滑动窗口缓冲区
                            with self.buffer_lock:
                                self.lip_sync_buffer.append(small_chunk)
                                self.chunk_counter += 1

                        # 在第一次播放时记录开始时间
                        if self.playback_start_time is None:
                            self.playback_start_time = time.time()

                        # 播放音频块（阻塞，直到播放完成）
                        self.output_stream.write(audio_chunk)
                        self.stats['output_chunks'] += 1

                else:
                    # 队列为空，检查是否结束播放
                    if was_playing:
                        self.empty_queue_count += 1
                        consecutive_empty += 1

                        # 更智能的结束判断
                        should_end = False

                        # 如果AI已完成且连续空队列达到阈值
                        if self.ai_response_done:
                            # 检查两个队列是否都真正为空
                            b64_empty = self.b64_output_queue.empty()
                            output_empty = self.output_queue.empty()

                            # 只有当两个队列都空且连续空闲时才结束
                            if b64_empty and output_empty and consecutive_empty > 7:
                                should_end = True
                                logger.info("AI response complete, both queues empty, ending after 0.7s")
                            elif consecutive_empty > 15:
                                # 增加一个更长的安全阈值
                                should_end = True
                                logger.info("AI response complete, extended wait reached")

                        # 防止永久等待的强制结束
                        if self.empty_queue_count > 30:
                            # 强制结束前，尝试播放剩余数据
                            remaining_chunks = 0
                            while not self.output_queue.empty():
                                try:
                                    chunk = self.output_queue.get_nowait()
                                    if self.output_stream and chunk:
                                        self.output_stream.write(chunk)
                                        remaining_chunks += 1
                                except:
                                    break

                            if remaining_chunks > 0:
                                logger.info(f"Flushed {remaining_chunks} remaining chunks before forcing end")

                            should_end = True
                            logger.warning("Queue idle for 3 seconds, forcing end")

                        if should_end:
                            # 停止异步口型同步线程
                            self._stop_lip_sync_thread()

                            # 最后的清理，确保没有残留数据
                            final_chunks = 0
                            while not self.output_queue.empty():
                                try:
                                    chunk = self.output_queue.get_nowait()
                                    if self.output_stream and chunk:
                                        self.output_stream.write(chunk)
                                        final_chunks += 1
                                except:
                                    break

                            if final_chunks > 0:
                                logger.debug(f"Played {final_chunks} final chunks before ending")

                            was_playing = False
                            self.empty_queue_count = 0
                            consecutive_empty = 0

                            # 最小延迟，让最后的音频完成
                            time.sleep(0.2)
                            self.is_playing = False
                            self.force_mute = False

                            # 确保缓冲区完全清空
                            self.clear_output_buffer()

                            if self.on_playback_ended:
                                self.on_playback_ended()
                            logger.debug("Ended audio playback")
                        else:
                            if self.empty_queue_count % 10 == 0:
                                logger.debug(f"Waiting for audio: {self.empty_queue_count}/30")
                    else:
                        self.empty_queue_count = 0

            except Exception as e:
                logger.error(f"Player loop error: {e}")
                time.sleep(0.1)

    def _lip_sync_update_loop(self):
        """独立的60FPS口型同步更新线程"""
        logger.info("口型同步更新线程启动（60FPS）")
        frame_count = 0

        while self.lip_sync_running:
            try:
                # 检查是否有播放开始时间
                if self.playback_start_time is None:
                    time.sleep(0.01)
                    continue

                # 获取当前播放状态
                with self.buffer_lock:
                    buffer_size = len(self.lip_sync_buffer)
                    total_chunks = self.chunk_counter

                # 🎯 最终修复：使用elapsed_time实时追踪播放位置
                # 原因：played_chunks只在write()完成后更新，导致320ms才更新一次
                # write()虽然阻塞，但音频已经开始播放，elapsed_time就是实际播放时间

                current_time = time.time()
                elapsed_time = current_time - self.playback_start_time

                # 1. 实际播放位置 = 经过的时间 × 采样率
                actual_playback_pos = int(elapsed_time * self.output_sample_rate)

                # 2. 目标位置 = 实际播放位置 - 固定延迟（落后25ms）
                target_sample_pos = max(0, actual_playback_pos - self.fixed_delay_samples)

                # 3. 安全限制：不超过已接收的数据
                max_sample_pos = total_chunks * self.output_chunk_size
                target_sample_pos = min(target_sample_pos, max_sample_pos)

                # 从缓冲区提取音频块
                audio_chunk = self._extract_audio_from_buffer(target_sample_pos)

                if audio_chunk:
                    try:
                        # 调用引擎更新Live2D
                        self._update_live2d_with_advanced_engine(audio_chunk)
                    except Exception as e:
                        logger.error(f"口型同步处理错误: {e}")

                frame_count += 1
                # 60FPS更新频率
                time.sleep(1.0 / self.lip_sync_fps)

            except Exception as e:
                if self.lip_sync_running:
                    logger.error(f"口型同步更新循环错误: {e}")
                    import traceback
                    traceback.print_exc()
                time.sleep(0.01)

        logger.info("口型同步更新线程结束")

    def _extract_audio_from_buffer(self, target_sample_pos: int) -> bytes | None:
        """从滑动窗口缓冲区提取音频块（基于时间戳）"""
        try:
            with self.buffer_lock:
                if not self.lip_sync_buffer:
                    return None

                # 计算每个块的样本数（20ms @ 24000Hz = 480样本）
                chunk_samples = self.output_chunk_size

                # 计算当前应该在哪个块
                target_chunk_index = target_sample_pos // chunk_samples

                # 限制不超过已接收的块数（避免访问还未到达的块）
                # chunk_counter是已加入的块总数，所以最大索引是 chunk_counter - 1
                target_chunk_index = min(target_chunk_index, self.chunk_counter - 1)

                # 计算缓冲区中第一个块的索引（滑动窗口）
                # chunk_counter是已加入的块总数，buffer中最多保留50个块
                buffer_start_chunk = max(0, self.chunk_counter - len(self.lip_sync_buffer))

                # 计算相对位置
                relative_index = target_chunk_index - buffer_start_chunk

                # 优化：避免返回None导致跳帧，返回最接近的可用块
                if relative_index < 0:
                    # 目标块还未到达缓冲区，使用最早的块（缓冲区第一个）
                    relative_index = 0
                elif relative_index >= len(self.lip_sync_buffer):
                    # 目标块已超出缓冲区，使用最新的块（缓冲区最后一个）
                    relative_index = len(self.lip_sync_buffer) - 1

                # 检查是否在缓冲区范围内（优化后应该总是True）
                if 0 <= relative_index < len(self.lip_sync_buffer):
                    # 🔧 修复：直接返回单个块，移除上下文拼接
                    # 原因：上下文拼接导致返回的音频块太大（60ms而非20ms）
                    # 现在每个块是20ms，足够精细，不需要额外上下文
                    audio_chunk = self.lip_sync_buffer[relative_index]
                    return audio_chunk
                else:
                    # 优化后理论上不应该到达这里，但保留作为安全网
                    # 返回最新的块而非None
                    if len(self.lip_sync_buffer) > 0:
                        return self.lip_sync_buffer[-1]
                    return None

        except Exception as e:
            logger.error(f"提取音频块错误: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _start_lip_sync_thread(self):
        """启动独立的口型同步线程"""
        if self.lip_sync_thread and self.lip_sync_thread.is_alive():
            logger.debug("口型同步线程已在运行")
            return

        self.lip_sync_running = True
        self.lip_sync_thread = threading.Thread(
            target=self._lip_sync_update_loop,
            daemon=True,
            name="LipSyncUpdate"
        )
        self.lip_sync_thread.start()
        logger.info("口型同步线程已启动")

    def _stop_lip_sync_thread(self):
        """停止独立的口型同步线程"""
        if not self.lip_sync_running:
            return

        self.lip_sync_running = False

        # 等待线程结束
        if self.lip_sync_thread and self.lip_sync_thread.is_alive():
            self.lip_sync_thread.join(timeout=1.0)

        # 清空缓冲区
        with self.buffer_lock:
            self.lip_sync_buffer.clear()
            self.playback_start_time = None
            self.chunk_counter = 0

        # 关闭Live2D嘴巴（模仿EdgeTTS）
        try:
            live2d_widget = self._get_live2d_widget()
            if live2d_widget:
                if hasattr(live2d_widget, 'stop_speaking'):
                    live2d_widget.stop_speaking()
                    logger.debug("Live2D嘴部已关闭")
        except Exception as e:
            logger.debug(f"关闭Live2D嘴部失败: {e}")

        logger.info("口型同步线程已停止")

    def _is_silence(self, audio_data: bytes) -> bool:
        """检测音频是否为静音"""
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            energy = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
            normalized_energy = energy / 32768.0
            return normalized_energy < self.vad_threshold
        except:
            return False

    def start_recording(self):
        """开始录音"""
        self.is_recording = True
        logger.info("Recording started")

    def stop_recording(self):
        """停止录音"""
        self.is_recording = False
        logger.info("Recording stopped")

    def add_output_audio(self, audio_b64: str):
        """添加要播放的音频（Base64格式）"""
        self.ai_response_done = False
        self.empty_queue_count = 0
        self.b64_output_queue.put(audio_b64)

    def mark_response_done(self):
        """标记AI响应已完成"""
        logger.info("AI response marked as done")
        self.ai_response_done = True

    def clear_output_buffer(self):
        """清空输出缓冲区（更彻底的清理）"""
        cleared_b64 = 0
        cleared_output = 0

        # 清空Base64队列
        while not self.b64_output_queue.empty():
            with suppress(queue.Empty):
                self.b64_output_queue.get_nowait()
                cleared_b64 += 1

        # 清空输出队列
        while not self.output_queue.empty():
            with suppress(queue.Empty):
                self.output_queue.get_nowait()
                cleared_output += 1

        # 清空口型同步缓冲区
        with self.buffer_lock:
            self.lip_sync_buffer.clear()
            self.playback_start_time = None
            self.chunk_counter = 0

        # 重置状态标志
        self.ai_response_done = False
        self.empty_queue_count = 0

        if cleared_b64 > 0 or cleared_output > 0:
            logger.info(f"Output buffers cleared: b64={cleared_b64}, output={cleared_output}")
        else:
            logger.debug("Output buffers were already empty")

    def interrupt_playback(self):
        """中断AI播放"""
        logger.info("Interrupting playback")

        # 停止异步口型同步线程
        self._stop_lip_sync_thread()

        self.is_playing = False
        self.ai_response_done = True
        self.empty_queue_count = 0
        self.clear_output_buffer()

        # 重置音频流
        if self.output_stream:
            try:
                if self.output_stream.is_active():
                    self.output_stream.stop_stream()
                self.output_stream.close()

                # 重新创建输出流
                if self.pya:
                    self.output_stream = self.pya.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=self.output_sample_rate,
                        output=True,
                        frames_per_buffer=self.output_chunk_size
                    )
            except Exception as e:
                logger.error(f"Failed to reset audio stream: {e}")

        self.force_mute = False
        self.is_recording = True

        if self.on_playback_ended:
            self.on_playback_ended()

        logger.info("Playback interrupted and cleaned")

    def get_status(self) -> dict:
        """获取当前状态"""
        return {
            'is_running': self.is_running,
            'is_recording': self.is_recording,
            'is_playing': self.is_playing,
            'stats': self.stats.copy()
        }

    def _get_live2d_widget(self):
        """获取Live2D widget引用（完全复制自EdgeTTS）"""
        try:
            # 确保可以导入system.config
            import os
            import sys
            # 计算项目根目录（向上5级）
            current_file = os.path.abspath(__file__)
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file)))))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            from system.config import config

            if hasattr(config, 'window') and config.window:
                window = config.window
                if hasattr(window, 'side') and hasattr(window.side, 'live2d_widget'):
                    live2d_widget = window.side.live2d_widget
                    # 检查是否在Live2D模式且模型已加载
                    if (hasattr(window.side, 'display_mode') and
                        window.side.display_mode == 'live2d' and
                        live2d_widget and
                        hasattr(live2d_widget, 'is_model_loaded') and
                        live2d_widget.is_model_loaded()):
                        return live2d_widget
        except Exception as e:
            logger.debug(f"获取Live2D widget失败: {e}")
        return None

    def _update_live2d_with_advanced_engine(self, audio_chunk: bytes):
        """使用商业级引擎更新Live2D（完全复制自EdgeTTS）"""
        try:
            # 检查引擎是否可用
            if not self._advanced_lip_sync_v2:
                if self._lip_sync_error_count == 0:
                    logger.warning("口型同步引擎未初始化")
                    self._lip_sync_error_count = 999
                return

            live2d_widget = self._get_live2d_widget()
            if not live2d_widget:
                if self._lip_sync_error_count == 0:
                    logger.warning("Live2D widget未找到")
                    self._lip_sync_error_count = 999
                return

            # 首次成功时记录
            if self._lip_sync_error_count == 0:
                logger.info("✅ Live2D口型同步已激活（EdgeTTS风格直接调用）")
                self._lip_sync_error_count = -1

            # 使用商业级引擎处理音频
            lip_sync_params = self._advanced_lip_sync_v2.process_audio_chunk(audio_chunk)

            # 🔧 实时语音专用修正：对mouth_open应用缩放系数（补偿24000Hz采样率差异）
            if 'mouth_open' in lip_sync_params:
                mouth_open = lip_sync_params['mouth_open'] * self.realtime_mouth_open_scale
                live2d_widget.set_audio_volume(mouth_open)

            if 'mouth_form' in lip_sync_params:
                live2d_widget.set_mouth_form(lip_sync_params['mouth_form'])

            if hasattr(live2d_widget, 'set_mouth_smile') and 'mouth_smile' in lip_sync_params:
                live2d_widget.set_mouth_smile(lip_sync_params['mouth_smile'])

            if hasattr(live2d_widget, 'set_eye_brow') and 'eye_brow_up' in lip_sync_params:
                live2d_widget.set_eye_brow(lip_sync_params['eye_brow_up'])

            if hasattr(live2d_widget, 'set_eye_wide') and 'eye_wide' in lip_sync_params:
                live2d_widget.set_eye_wide(lip_sync_params['eye_wide'])

        except Exception as e:
            # 记录错误但不影响主流程
            if self._lip_sync_error_count >= 0 and self._lip_sync_error_count <= 3:
                self._lip_sync_error_count += 1
                logger.error(f"口型同步引擎错误 ({self._lip_sync_error_count}/3): {e}")
                import traceback
                traceback.print_exc()

                if self._lip_sync_error_count == 3:
                    logger.warning("后续口型同步错误将静默处理")
            elif self._lip_sync_error_count == -1:
                # 已初始化但出错，重新计数
                self._lip_sync_error_count = 1
                logger.error(f"口型同步运行时错误: {e}")
                import traceback
                traceback.print_exc()