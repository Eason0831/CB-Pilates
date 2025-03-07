from wxpusher import WxPusher

app_token = 'AT_JdllnL0Sz9aRSFCQgSyIJwDFzyHm1TQC'  # 这里填写您的真实 appToken

uids = [
    'UID_UeXwTkpJOBcdt32ssRUETbxHWDON',  # Eason（您自己）
    'UID_OYoby9QScGVWIHNZKFWEc31ap7xT',  # 第二个人的 UID
    'UID_y9Rbjoc3M8UMf2hrA9XpTbPzFC4W'   # 第三个人的 UID
]

def send_notification(message):
    response = WxPusher.send_message(
        content=message,
        uids=uids,  # ✅ 传递整个 UID 列表，而不是单个 uid
        token=app_token
    )
    print(response)  # 打印返回结果，便于调试

if __name__ == "__main__":
    # 发送测试通知
    send_notification("📢 学员已确认预约课程。")
