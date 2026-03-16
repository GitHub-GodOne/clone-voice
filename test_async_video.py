#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试异步视频处理接口
"""

import requests
import time
import os

# 配置
API_BASE_URL = "https://clonevoice.nailai.net"
# API_BASE_URL = "http://127.0.0.1:9988"  # 本地测试

# 测试文件路径（请根据实际情况修改）
VIDEO_FILE = "/Users/pikju/program/python/clone-voice/video/input.mp4"
AUDIO_FILE = "/Users/pikju/program/python/clone-voice/video/voice.wav"
BGM_FILE = "/Users/pikju/program/python/clone-voice/video/mucis.mp3"  # 可选

# 测试 URL（如果使用 URL 方式）
VIDEO_URL = "https://dashscope-result-wlcb-acdr-1.oss-cn-wulanchabu-acdr-1.aliyuncs.com/1d/a3/20260305/a0f45588/0b47c546-c46a-40c0-92fa-a733da82fea9.mp4?Expires=1772798225&OSSAccessKeyId=LTAI5tKPD3TMqf2Lna1fASuh&Signature=s7Dc%2FB8OnAjB%2F9Fl75LTbiL9TRM%3D"  # 例如: "https://example.com/video.mp4"
AUDIO_URL = "https://clonevoice.nailai.net/static/ttslist/7aab11e154839592ff2bc78234b70341.wav"  # 例如: "https://example.com/audio.wav"
BGM_URL = ""  # 例如: "https://example.com/bgm.mp3"

# 测试文本
TEXT_CONTENT = """When anxiety grips you, it can feel overwhelming... Breathe deeply and hear these words from Isaiah 41:10: "Fear not, for I am with you; be not dismayed, for I am your God. I will strengthen you, I will help you, I will uphold you with my righteous right hand." ... Allow this promise to bring peace to your restless heart, knowing that you're never alone..."""

# 选择提交方式: 'file' 或 'url'
SUBMIT_MODE = 'url'  # 改为 'url' 使用 URL 方式


def submit_video_task_by_file():
    """通过文件上传方式提交视频处理任务"""
    print("📤 提交视频处理任务（文件上传方式）...")

    url = f"{API_BASE_URL}/process_video_async"

    # 准备文件
    files = {
        'video': open(VIDEO_FILE, 'rb'),
        'audio': open(AUDIO_FILE, 'rb'),
    }

    # 可选：添加背景音乐
    if os.path.exists(BGM_FILE):
        files['bgm'] = open(BGM_FILE, 'rb')

    # 准备参数
    data = {
        'text_content': TEXT_CONTENT,
        'language': 'en',
        'bgm_volume': '5',
        'voice_volume': '1.0',
        'max_words_per_line': '10',
        'long_token_dur_s': '0.8',
        'title': '测试标题',
        'title_start': '0',
        'title_end': '100',
        'loop_video': '1',  # 1=循环视频，0=不循环
        'subtitle_fontsize': '100',  # 字幕字体大小
        'subtitle_marginv': '100',   # 字幕底部边距
        'subtitle_y': '1700',        # 字幕Y坐标位置
        'title_fontsize': '80',      # 标题字体大小
        'title_x': '540',            # 标题X坐标
        'title_y': '300',            # 标题Y坐标
    }

    try:
        response = requests.post(url, files=files, data=data)
        result = response.json()

        # 关闭文件
        for f in files.values():
            f.close()

        if result['code'] == 0:
            print(f"✅ 任务提交成功！")
            print(f"   Task ID: {result['task_id']}")
            print(f"   提示: {result['msg']}")
            return result['task_id']
        else:
            print(f"❌ 任务提交失败: {result['msg']}")
            return None

    except Exception as e:
        print(f"❌ 请求失败: {str(e)}")
        return None


def submit_video_task_by_url():
    """通过 URL 方式提交视频处理任务（更快，推荐）"""
    print("📤 提交视频处理任务（URL 方式）...")

    url = f"{API_BASE_URL}/process_video_async"

    # 准备参数（使用 URL 而不是文件上传）
    data = {
        'video_url': VIDEO_URL,
        'audio_url': AUDIO_URL,
        'text_content': TEXT_CONTENT,
        'language': 'en',
        'bgm_volume': '5',
        'voice_volume': '1.0',
        'max_words_per_line': '10',
        'long_token_dur_s': '0.8',
        'title': '测试标题',
        'title_start': '0',
        'title_end': '100',
        'loop_video': '1',  # 1=循环视频，0=不循环
        'subtitle_fontsize': '100',  # 字幕字体大小
        'subtitle_marginv': '100',   # 字幕底部边距
        'subtitle_y': '1700',        # 字幕Y坐标位置
        'title_fontsize': '80',      # 标题字体大小
        'title_x': '540',            # 标题X坐标
        'title_y': '300',            # 标题Y坐标
    }

    # 可选：添加背景音乐 URL
    if BGM_URL:
        data['bgm_url'] = BGM_URL

    try:
        response = requests.post(url, data=data)
        result = response.json()

        if result['code'] == 0:
            print(f"✅ 任务提交成功！")
            print(f"   Task ID: {result['task_id']}")
            print(f"   提示: {result['msg']}")
            return result['task_id']
        else:
            print(f"❌ 任务提交失败: {result['msg']}")
            return None

    except Exception as e:
        print(f"❌ 请求失败: {str(e)}")
        return None


def query_task_status(task_id):
    """查询任务状态"""
    url = f"{API_BASE_URL}/task_status/{task_id}"

    try:
        response = requests.get(url)
        result = response.json()

        if result['code'] == 0:
            return result
        else:
            print(f"❌ 查询失败: {result['msg']}")
            return None

    except Exception as e:
        print(f"❌ 查询失败: {str(e)}")
        return None


def wait_for_completion(task_id, check_interval=5, max_wait=3600):
    """等待任务完成"""
    print(f"\n⏳ 等待任务完成 (每 {check_interval} 秒查询一次)...")

    start_time = time.time()

    while True:
        # 检查是否超时
        elapsed = time.time() - start_time
        if elapsed > max_wait:
            print(f"❌ 等待超时 ({max_wait}秒)")
            return None

        # 查询状态
        status_info = query_task_status(task_id)

        if status_info is None:
            print("❌ 无法获取任务状态")
            return None

        status = status_info['status']
        task_type = status_info['type']

        print(f"   [{int(elapsed)}s] 状态: {status}")

        if status == 'completed':
            print(f"\n✅ 任务完成！")
            result = status_info['result']
            if result:
                print(f"   文件名: {result.get('filename')}")
                print(f"   下载链接: {result.get('url')}")
            return result

        elif status == 'failed':
            print(f"\n❌ 任务失败！")
            print(f"   错误信息: {status_info.get('error')}")
            return None

        elif status in ['pending', 'processing']:
            # 继续等待
            time.sleep(check_interval)

        else:
            print(f"❌ 未知状态: {status}")
            return None


def main():
    """主函数"""
    print("=" * 60)
    print("视频处理异步接口测试")
    print("=" * 60)

    # 根据模式选择提交方式
    if SUBMIT_MODE == 'url':
        print(f"📌 使用 URL 方式提交（更快）")
        if not VIDEO_URL or not AUDIO_URL:
            print(f"❌ 请配置 VIDEO_URL 和 AUDIO_URL")
            return
        task_id = submit_video_task_by_url()
    else:
        print(f"📌 使用文件上传方式提交")
        # 检查文件是否存在
        if not os.path.exists(VIDEO_FILE):
            print(f"❌ 视频文件不存在: {VIDEO_FILE}")
            return
        if not os.path.exists(AUDIO_FILE):
            print(f"❌ 音频文件不存在: {AUDIO_FILE}")
            return
        task_id = submit_video_task_by_file()

    if task_id is None:
        return

    # 2. 等待完成
    result = wait_for_completion(task_id, check_interval=5, max_wait=3600)

    if result:
        print("\n" + "=" * 60)
        print("✅ 测试成功！")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ 测试失败")
        print("=" * 60)


if __name__ == '__main__':
    main()
