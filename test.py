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

# 1. 提交异步TTS任务
# res = requests.post(
#     "http://localhost:9988/tts_async",
#     data={"text": "hello everyone", "voice": "output.wav", "language": "en"},
# )
# task_id = res.json()
# print(task_id)

# 2. 轮询查询状态
# while True:
status = requests.get(
    f"http://localhost:9988/task_status/0db6528a-e7e3-4d9a-a643-919907f5a36f"
).json()
print(status)
#     if status["status"] in ("completed", "failed"):
#         print(status)
#         break
#     time.sleep(3)  # 每3秒查一次
