import os
import gspread
import json
import re
import random
from datetime import datetime
from flask import Flask, request, abort
from oauth2client.service_account import ServiceAccountCredentials
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("CHANNEL_SECRET"))

# 建立憑證檔案
gcred_json_str = os.getenv("GCRED_JSON")
with open("gcred.json", "w") as f:
    f.write(gcred_json_str)

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("gcred.json", scope)
gc = gspread.authorize(credentials)
sheet = gc.open_by_key(os.getenv("SHEET_ID")).sheet1

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

def get_month_records(user_id, month_prefix):
    all_rows = sheet.get_all_values()[1:]
    records = []
    income, expense = 0, 0
    budget = 0
    for row in all_rows:
        date, kind, item, amount, uid = row
        if uid != user_id:
            continue
        if kind == "預算" and date.startswith(month_prefix):
            budget = int(amount)
        elif date.startswith(month_prefix):
            amount = int(amount)
            records.append((date, kind, item, amount))
            if kind == "收入":
                income += amount
            elif kind == "支出":
                expense += amount
    return income, expense, budget, records

def format_monthly_report(income, expense, budget, records):
    lines = []
    for i, (date, kind, item, amount) in enumerate(records):
        sign = "+" if kind == "收入" else "-"
        lines.append(f"{i+1}. {date}｜{item}｜{sign}{amount}")
    detail = "
".join(lines) if lines else "（這個月還沒有紀錄喵）"
    report = f"📅 收入：{income} 元
💸 支出：{expense} 元"
    if budget > 0:
        percent = round(expense / budget * 100)
        report += f"
🎯 預算：{budget} 元（已使用 {percent}%）"
        if percent >= 80:
            report += f"
⚠️ {random.choice(over_80_quotes)}"
        elif percent >= 50:
            report += f"
😿 {random.choice(over_50_quotes)}"
    return report + "

" + detail

success_quotes = [
    "已記下來了喵，希望不是亂花錢 QQ",
    "好啦好啦，錢花了我也只能記下來了喵…",
    "唉，又是一筆支出呢…我都麻了喵 🫠",
    "收到喵～雖然我覺得可以不買但我嘴硬不說 🐱",
    "花得開心就好啦（吧），我會默默記著的喵～",
    "喵：記好了，不要到月底又說錢怎麼不見了嘿。"
]

over_50_quotes = [
    "喵？已經花一半了耶…這樣月底還吃得起飯嗎…？",
    "再買下去我就要幫妳搶銀行了喵 🥲",
    "這速度…是存錢還是存破產紀錄呀喵～"
]

over_80_quotes = [
    "錢真是難用啊喵，最後只能買個寂寞 🫠",
    "剩沒幾天啦喵…我們一起吃吐司皮撐過去吧 🍞",
    "看來只剩空氣和遺憾能當宵夜了喵…"
]

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    uid = event.source.user_id
    msg = event.message.text.strip()
    today = datetime.now().strftime("%Y-%m-%d")
    year_month = today[:7]

    # 模糊查詢
    if re.search(r"(查詢|明細|帳目|看一下)", msg):
        match = re.search(r"(\d{4})-(\d{2})", msg)
        month_prefix = match.group() if match else year_month
        income, expense, budget, records = get_month_records(uid, month_prefix)
        reply = format_monthly_report(income, expense, budget, records)

    elif msg.startswith("預算"):
        parts = msg.split()
        if len(parts) == 2 and parts[1].isdigit():
            sheet.append_row([today, "預算", "本月預算", parts[1], uid])
            reply = f"喵～我幫妳把這個月的預算記成 {parts[1]} 元了！"
        else:
            reply = "請用「預算 20000」這種格式設定喵～"

    elif msg.startswith("刪除第") or msg.startswith("刪除 "):
        match = re.search(r"(\d+)", msg)
        if not match:
            reply = "喵？請用「刪除第3筆」或「刪除 2」這種格式喔"
        else:
            target_idx = int(match.group()) - 1
            all_rows = sheet.get_all_values()
            user_rows = [i for i, row in enumerate(all_rows[1:], start=2)
                         if row[4] == uid and row[0].startswith(year_month)]
            if 0 <= target_idx < len(user_rows):
                sheet.delete_rows(user_rows[target_idx])
                reply = f"第 {target_idx+1} 筆我幫妳刪掉了喵…希望不是重要回憶 QQ"
            else:
                reply = "喵…那筆編號找不到耶，請再確認一下～"

    else:
        # 判斷是否為支出/收入或懶人輸入
        date = today
        kind, item, amount = None, "懶得寫", None

        # 支援指定日期
        date_match = re.search(r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2})", msg)
        if date_match:
            date_str = date_match.group()
            msg = msg.replace(date_str, "").strip()
            if "/" in date_str:
                m, d = date_str.split("/")
                date = f"{today[:5]}{int(m):02d}-{int(d):02d}"
            else:
                date = date_str

        if re.match(r"^[-+]?\d+", msg):
            if msg.startswith("-"):
                kind = "支出"
                amount = int(msg)
            elif msg.startswith("+"):
                kind = "收入"
                amount = int(msg[1:])
            else:
                kind = "支出"
                amount = int(msg)
        else:
            parts = msg.split()
            if parts[0] in ["支出", "收入"]:
                kind = parts[0]
                if len(parts) == 2:
                    amount = int(parts[1])
                elif len(parts) >= 3 and parts[2].isdigit():
                    item = parts[1]
                    amount = int(parts[2])
            elif len(parts) == 2 and parts[0].lstrip("+-").isdigit():
                amount = int(parts[0])
                kind = "收入" if "+" in parts[0] else "支出"
                item = parts[1]

        if kind and amount:
            sheet.append_row([date, kind, item, abs(amount), uid])
            reply = f"{random.choice(success_quotes)}：{kind} {item} {abs(amount)} 元"
        else:
            reply = "喵？這筆我看不懂，要不要再試一次～"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
