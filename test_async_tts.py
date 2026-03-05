#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试异步 TTS 接口
"""

import requests
import time

# 配置
API_BASE_URL = "https://clonevoice.nailai.net"
# API_BASE_URL = "http://127.0.0.1:9988"  # 本地测试

def submit_tts_task():
    """提交 TTS 任务"""
    print("📤 提交 TTS 任务...")

    url = f"{API_BASE_URL}/tts_async"

    # 准备参数
    data = {
        'text': '这是一段测试文本，用于测试语音合成功能。',
        'voice': 'test.wav',  # 替换为实际的声音文件名
        'language': 'zh-cn',
        'speed': '1.0',
        'model': ''  # 留空使用默认模型
    }

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

def wait_for_completion(task_id, check_interval=3, max_wait=600):
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

        print(f"   [{int(elapsed)}s] 状态: {status}")

        if status == 'completed':
            print(f"\n✅ 任务完成！")
            result = status_info['result']
            if result:
                print(f"   文件名: {result.get('name')}")
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
    print("TTS 异步接口测试")
    print("=" * 60)

    # 1. 提交任务
    task_id = submit_tts_task()
    if task_id is None:
        return

    # 2. 等待完成
    result = wait_for_completion(task_id, check_interval=3, max_wait=600)

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
