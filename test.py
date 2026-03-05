# import os
# import re


# def get_models(path):
#     objs={}
#     for it in os.listdir(path):
#         if re.match(r'^[0-9a-zA-Z_-]+$',it):
#             objs[it]=None
#     return objs

# print(get_models(r'E:\python\tts\tts\mymodels\xiaoyi'))
#
#
#
import requests
import time

import requests
import time

# 1. 提交异步TTS任务
res = requests.post(
    "https://clonevoice.nailai.net/tts_async",
    data={"text": "hello everyone", "voice": "output.wav", "language": "en"},
)
task_id = res.json()["task_id"]

# 2. 轮询查询状态
while True:
    status = requests.get(f"https://clonevoice.nailai.net/task_status/{task_id}").json()
    if status["status"] in ("completed", "failed"):
        print(status)
        break
    time.sleep(3)  # 每3秒查一次
# 响应
{
    'code': 0,
    'error': None,
    'result': {
        'code': 0,
        'filename': '/Users/apple/Documents/python/clone-voice/static/ttslist/7ba525aa30052c0b3afff1cbfa388b90.wav',
        'msg': '',
        'name': '7ba525aa30052c0b3afff1cbfa388b90.wav',
        'url': 'https://clonevoice.nailai.net/static/ttslist/7ba525aa30052c0b3afff1cbfa388b90.wav',
    },
    'status': 'completed',
    'task_id': '701613c6-2c93-4a20-81f0-efa9b2e70b3f',
    'type': 'tts',
}
