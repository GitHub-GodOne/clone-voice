#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
视频字幕添加服务

功能：
1. 生成词级时间戳和 ASS 字幕
2. 将字幕和音频添加到视频中
3. 可选添加背景音乐

用法：
python create_video.py \
  --video input.mp4 \
  --audio voice.wav \
  --text transcript.txt \
  --output output.mp4 \
  --bgm music.mp3 \
  --bgm_volume 0.3

参数：
  --video: 输入视频文件
  --audio: 语音音频文件
  --text: 文本内容
  --output: 输出视频文件
  --bgm: 背景音乐（可选）
  --bgm_volume: 背景音乐音量（0.0-1.0，默认 0.2）
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def run_command(cmd, description):
    """运行命令并显示进度"""
    print(f"\n{'='*60}")
    print(f"🔄 {description}")
    print(f"{'='*60}")
    print(f"命令: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ 错误: {description} 失败")
        print(f"错误信息:\n{result.stderr}")
        sys.exit(1)

    print(f"✅ {description} 完成")
    return result


def generate_subtitles(audio, text, output_prefix, language="en", title=None, title_start=0.0, title_end=10.0):
    """生成 ASS 字幕文件"""
    cmd = [
        "python",
        "word_timestamps_to_ass.py",
        "--audio",
        audio,
        "--text",
        text,
        "--language",
        language,
        "--device",
        "mps",
        "--out_prefix",
        output_prefix,
        "--make_ass",
        "--max_words_per_line",
        "30",
        "--long_token_dur_s",
        "2",
        "--fast_speed_s",
        "0",
        "--highlight_last_word",
    ]

    # 添加标题参数
    if title:
        cmd.extend(["--title", title])
        cmd.extend(["--title_start", str(title_start)])
        cmd.extend(["--title_end", str(title_end)])

    run_command(cmd, "生成字幕文件")
    return f"{output_prefix}.ass"


def merge_audio_bgm(audio, bgm, bgm_volume, temp_dir, voice_volume=1.0):
    """合并语音和背景音乐（使用侧链压缩）"""
    if not bgm:
        return audio

    merged_audio = temp_dir / "merged_audio.wav"

    # 使用侧链压缩：背景音乐在语音说话时自动降低音量
    # 注意：bgm_volume 可以大于 1.0 来提升很小声的背景音乐
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        audio,
        "-i",
        bgm,
        "-filter_complex",
        f"[0:a]aresample=48000,volume={voice_volume}[voice];"
        f"[1:a]aresample=48000,pan=mono|c0=0.5*c0+0.5*c1,volume={bgm_volume}[music];"
        "[music][voice]sidechaincompress=threshold=0.02:ratio=10:attack=20:release=300:makeup=6[musicduck];"
        "[voice][musicduck]amix=inputs=2:duration=shortest[aout]",
        "-map",
        "[aout]",
        "-c:a",
        "pcm_s16le",
        str(merged_audio),
    ]

    run_command(cmd, "合并音频和背景音乐（侧链压缩）")
    return merged_audio


def add_subtitles_and_audio(video, audio, ass_file, output):
    """将字幕和音频添加到视频中"""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-vf",
        f"ass={ass_file}",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-map",
        "0:v:0",  # 使用输入视频的视频流
        "-map",
        "1:a:0",  # 使用输入音频的音频流
        "-shortest",
        str(output),
    ]

    run_command(cmd, "添加字幕和音频到视频")


def main():
    parser = argparse.ArgumentParser(description="视频字幕添加服务")

    # 必需参数
    parser.add_argument("--video", required=True, help="输入视频文件")
    parser.add_argument("--audio", required=True, help="语音音频文件")
    parser.add_argument("--text", required=True, help="文本内容文件")
    parser.add_argument("--output", required=True, help="输出视频文件")

    # 可选参数
    parser.add_argument("--bgm", help="背景音乐文件")
    parser.add_argument(
        "--bgm_volume", type=float, default=0.3, help="背景音乐音量 (0.0-5.0，默认 0.3，可以大于 1.0 提升小声音乐)"
    )
    parser.add_argument(
        "--voice_volume", type=float, default=1.0, help="语音音量 (0.0-2.0，默认 1.0)"
    )
    parser.add_argument("--language", default="en", help="语言代码")

    # 标题参数
    parser.add_argument("--title", help="视频标题（显示在字幕上方）")
    parser.add_argument("--title_start", type=float, default=0.0, help="标题开始时间（秒）")
    parser.add_argument("--title_end", type=float, default=10.0, help="标题结束时间（秒）")

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("🎬 视频字幕添加服务")
    print("=" * 60)

    # 创建临时目录
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # 步骤 1: 生成字幕
        print("\n📝 步骤 1/3: 生成字幕")
        ass_file = generate_subtitles(
            args.audio,
            args.text,
            str(temp_path / "subtitles"),
            args.language,
            title=args.title,
            title_start=args.title_start,
            title_end=args.title_end
        )

        # 步骤 2: 合并音频（如果有背景音乐）
        print("\n🎵 步骤 2/3: 处理音频")
        final_audio = merge_audio_bgm(
            args.audio,
            args.bgm,
            args.bgm_volume,
            temp_path,
            voice_volume=args.voice_volume
        )

        # 步骤 3: 添加字幕和音频到视频
        print("\n🎥 步骤 3/3: 添加字幕和音频到视频")
        add_subtitles_and_audio(args.video, final_audio, ass_file, args.output)

    print("\n" + "=" * 60)
    print(f"✅ 视频生成完成: {args.output}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
