import os
import gspread
from datetime import datetime
from flask import Flask, request, abort
from oauth2client.service_account import ServiceAccountCredentials
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# LINE Bot 認證
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("CHANNEL_SECRET"))

# Google Sheet 連線設定
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("gcred.json", scope)
gc = gspread.authorize(credentials)
sheet = gc.open_by_key(os.getenv("SHEET_ID")).sheet1

# 處理 LINE 訊息
@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    uid = event.source.user_id
    today = datetime.now().strftime("%Y-%m-%d")

    if msg.startswith("支出") or msg.startswith("收入"):
        parts = msg.split()
        if len(parts) != 3 or not parts[2].isdigit():
            reply = "喵？請用格式「支出 飲料 50」這樣我才看得懂啦～"
        else:
            kind, item, amount = parts
            amount = int(amount)
            sheet.append_row([today, kind, item, amount, uid])
            reply = f"已記下來了喵：{kind} {item} {amount} 元～（希望不是亂花錢 QQ）"
    elif "查詢" in msg and ("本月" in msg or "明細" in msg):
        data = sheet.get_all_values()
        total_in, total_out = 0, 0
        details = []
        for row in data[1:]:
            if row[4] != uid:
                continue
            date, kind, item, amount, _ = row
            if date.startswith(today[:7]):
                amount = int(amount)
                if kind == "收入":
                    total_in += amount
                elif kind == "支出":
                    total_out += amount
                    details.append(f"{date}｜{item}｜-{amount}")
        detail_text = "
".join(details[-10:] or ["（本月還沒花錢喵）"])
        reply = f"📅 本月收入：{total_in} 元
💸 支出：{total_out} 元

{detail_text}"
    else:
        reply = "喵？我目前只懂「支出 飲料 50」或「查詢本月」這種訊息喔～"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
