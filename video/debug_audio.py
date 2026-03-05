#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
调试版本：检查每一步的音频输出
"""

import subprocess
import sys
from pathlib import Path

def test_audio(file_path, description):
    """测试音频文件"""
    print(f"\n{'='*60}")
    print(f"🔍 检查: {description}")
    print(f"{'='*60}")

    if not Path(file_path).exists():
        print(f"❌ 文件不存在: {file_path}")
        return False

    # 获取音频信息
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_name,sample_rate,channels",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1",
        file_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)

    # 检查音量
    cmd = [
        "ffmpeg", "-i", file_path,
        "-af", "volumedetect",
        "-f", "null", "-"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    for line in result.stderr.split('\n'):
        if 'mean_volume' in line or 'max_volume' in line:
            print(line.strip())

    return True

# 测试原始音频
test_audio("voice.wav", "原始语音")
test_audio("mucis.mp3", "背景音乐")

# 测试混音后的音频
if Path("merged_audio.wav").exists():
    test_audio("merged_audio.wav", "混音后的音频")
else:
    print("\n❌ merged_audio.wav 不存在，需要先运行混音")

# 测试最终视频的音频
if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
    print(f"\n{'='*60}")
    print(f"🎥 提取最终视频的音频")
    print(f"{'='*60}")

    cmd = [
        "ffmpeg", "-y",
        "-i", sys.argv[1],
        "-vn", "-acodec", "pcm_s16le",
        "final_audio_extracted.wav"
    ]

    subprocess.run(cmd, capture_output=True)
    test_audio("final_audio_extracted.wav", "最终视频的音频")
