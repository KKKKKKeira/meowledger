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

gcred_json_str = os.getenv("GCRED_JSON")
with open("gcred.json", "w") as f:
    f.write(gcred_json_str)

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("gcred.json", scope)
gc = gspread.authorize(credentials)
sheet = gc.open_by_key(os.getenv("SHEET_ID")).sheet1

# 狀態暫存字典
user_states = {}

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
    budget_rows = []

    for row in all_rows:
        date, kind, item, amount, uid = row
        if uid != user_id:
            continue
        if kind == "預算" and date.startswith(month_prefix):
            budget_rows.append(int(amount))
        elif date.startswith(month_prefix):
            amount = int(amount)
            records.append((date, kind, item, amount))
            if kind == "收入":
                income += amount
            elif kind == "支出":
                expense += amount

    budget = budget_rows[-1] if budget_rows else 0
    return income, expense, budget, records

def format_monthly_report(income, expense, budget, records):
    lines = []
    for i, (date, kind, item, amount) in enumerate(records):
        sign = "+" if kind == "收入" else "-"
        lines.append(f"{i+1}. {date}｜{item}｜{sign}{amount}")
    detail = "\n".join(lines) if lines else "（這個月還沒有紀錄喵）"
    report = f"📅 收入：{income} 元\n💸 支出：{expense} 元"
    if budget > 0:
        percent = round(expense / budget * 100)
        report += f"\n🎯 預算：{budget} 元（已使用 {percent}%）"
        if percent >= 80:
            report += f"\n⚠️ {random.choice(over_80_quotes)}"
        elif percent >= 50:
            report += f"\n😿 {random.choice(over_50_quotes)}"
    return report + "\n\n" + detail

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

    state = user_states.get(uid)

    if msg in ["支出", "收入", "本月預算", "查詢明細", "剩餘預算", "修改或刪除"]:
        user_states[uid] = msg
        if msg == "支出":
            reply = "又要花錢了喵…請輸入金額和項目～\n例如：午餐 80（也可以只輸入金額）"
        elif msg == "收入":
            reply = "又賺了多少錢啊喵？說來聽聽～\n例如：加班 1000（也可以只輸入金額）"
        elif msg == "本月預算":
            reply = "這個月打算花多少喵？直接輸入數字吧～\n例如：20000"
        elif msg == "查詢明細":
            income, expense, budget, records = get_month_records(uid, year_month)
            reply = format_monthly_report(income, expense, budget, records)
            user_states.pop(uid, None)
        elif msg == "剩餘預算":
            _, expense, budget, _ = get_month_records(uid, year_month)
            remaining = budget - expense
            percent = round(remaining / budget * 100) if budget else 0
            reply = f"喵～你還能花 {remaining} 元（剩 {percent}%）"
            user_states.pop(uid, None)
        elif msg == "修改或刪除":
            reply = "哪幾筆想刪掉喵？告訴我吧～\n例如：刪除2、刪除1.3.5筆、全部刪除"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # 預算輸入
    if state == "本月預算" and msg.isdigit():
        sheet.append_row([today, "預算", "本月預算", msg, uid])
        reply = f"喵～我幫妳把這個月的預算記成 {msg} 元了！"
        user_states.pop(uid, None)
    # 收入或支出輸入
    elif state in ["支出", "收入"]:
        parts = msg.split()
        if len(parts) == 2 and parts[1].isdigit():
            item, amount = parts[0], int(parts[1])
        elif len(parts) == 1 and parts[0].isdigit():
            item, amount = "懶得寫", int(parts[0])
        else:
            reply = "喵？這格式我看不懂，試著像『午餐 80』或『80』這樣輸入吧～"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return
        sheet.append_row([today, state, item, amount, uid])
        reply = f"{random.choice(success_quotes)}：{state} {item} {amount} 元"
        user_states.pop(uid, None)
    else:
        reply = "喵？要不要先從選單選一下功能再輸入喵？～"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
