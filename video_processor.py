#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
视频处理模块
整合字幕生成和视频合成功能
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
import sys

# 导入 word_timestamps_to_ass 模块的函数
import word_timestamps_to_ass as wta

# 导入字幕生成模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import whisperx


def generate_subtitles_direct(
    audio_path: str,
    text_content: str,
    output_prefix: str,
    language: str = "en",
    max_words_per_line: int = 30,
    long_token_dur_s: float = 2.0,
    device: str = "mps",
    title: Optional[str] = None,
    title_start: float = 0.0,
    title_end: float = 10.0,
) -> str:
    """
    直接生成 ASS 字幕文件（使用 whisperx）
    """

    # 处理文本
    raw_text = wta.normalize_spaces(text_content)
    words, lead, trail = wta.tokenize_words_with_punc(raw_text)
    align_text = " ".join(words).strip()

    if not align_text:
        raise ValueError("No alignable words after removing punctuation.")

    # 加载音频
    audio = whisperx.load_audio(audio_path)
    dur = wta.audio_duration_seconds(audio, sample_rate=16000)
    segments = wta.build_single_segment(align_text, dur)

    # 加载对齐模型
    align_model, metadata = whisperx.load_align_model(
        language_code=language, device=device
    )

    # 对齐
    aligned = whisperx.align(
        segments,
        align_model,
        metadata,
        audio,
        device,
        return_char_alignments=True,
    )

    word_segments = aligned.get("word_segments", []) or []
    if not word_segments:
        raise RuntimeError(
            "No word_segments produced. Check language/text match and audio quality."
        )

    # 补回标点
    word_segments = wta.attach_punc_to_aligned_words(word_segments, words, lead, trail)

    # 生成 ASS 字幕
    out_ass = f"{output_prefix}.ass"
    wta.make_typewriter_ass(
        word_segments,
        out_ass,
        max_words_per_line=max_words_per_line,
        long_token_dur_s=long_token_dur_s,
        fast_speed_s=0.0,
        highlight_last_word=True,
        highlight_scale=150,
        end_gap_cs=1,
        title=title,
        title_start=title_start,
        title_end=title_end,
        title_x=540,
        title_y=300,
    )

    return out_ass


def merge_audio_with_bgm(
    audio_path: str,
    bgm_path: Optional[str],
    output_path: str,
    bgm_volume: float = 0.3,
    voice_volume: float = 1.0,
) -> str:
    """合并语音和背景音乐（使用侧链压缩）"""
    if not bgm_path:
        return audio_path

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        audio_path,
        "-i",
        bgm_path,
        "-filter_complex",
        f"[0:a]aresample=48000,volume={voice_volume}[voice];"
        f"[1:a]aresample=48000,pan=mono|c0=0.5*c0+0.5*c1,volume={bgm_volume}[music];"
        "[music][voice]sidechaincompress=threshold=0.02:ratio=10:attack=20:release=300:makeup=6[musicduck];"
        "[voice][musicduck]amix=inputs=2:duration=shortest[aout]",
        "-map",
        "[aout]",
        "-c:a",
        "pcm_s16le",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"音频合并失败: {result.stderr}")

    return output_path


def add_subtitles_and_audio_to_video(
    video_path: str, audio_path: str, ass_file: str, output_path: str
) -> str:
    """将字幕和音频添加到视频中"""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-i",
        audio_path,
        "-vf",
        f"ass={ass_file}",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-shortest",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"视频合成失败: {result.stderr}")

    return output_path


def process_video_with_subtitles(
    video_path: str,
    audio_path: str,
    text_content: str,
    output_path: str,
    language: str = "en",
    bgm_path: Optional[str] = None,
    bgm_volume: float = 0.3,
    voice_volume: float = 1.0,
    max_words_per_line: int = 30,
    long_token_dur_s: float = 2.0,
    title: Optional[str] = None,
    title_start: float = 0.0,
    title_end: float = 10.0,
) -> str:
    """完整的视频处理流程：生成字幕、合并音频、添加到视频"""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # 步骤 1: 生成字幕
        print("📝 步骤 1/3: 生成字幕")
        ass_file = generate_subtitles_direct(
            audio_path=audio_path,
            text_content=text_content,
            output_prefix=str(temp_path / "subtitles"),
            language=language,
            max_words_per_line=max_words_per_line,
            long_token_dur_s=long_token_dur_s,
            device="mps",
            title=title,
            title_start=title_start,
            title_end=title_end,
        )

        # 步骤 2: 合并音频
        print("🎵 步骤 2/3: 处理音频")
        final_audio = audio_path
        if bgm_path:
            merged_audio_path = str(temp_path / "merged_audio.wav")
            final_audio = merge_audio_with_bgm(
                audio_path=audio_path,
                bgm_path=bgm_path,
                output_path=merged_audio_path,
                bgm_volume=bgm_volume,
                voice_volume=voice_volume,
            )

        # 步骤 3: 添加字幕和音频到视频
        print("🎥 步骤 3/3: 添加字幕和音频到视频")
        result_path = add_subtitles_and_audio_to_video(
            video_path=video_path,
            audio_path=final_audio,
            ass_file=ass_file,
            output_path=output_path,
        )

        print(f"✅ 视频生成完成: {result_path}")
        return result_path
