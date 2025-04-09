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

# 儲存使用者狀態（如：目前是記錄收入、支出還是預算）
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

success_quotes_income = [
    "又賺了多少錢啊喵～希望不是在做違法的事吧…",
    "喵嗚～進帳真香，希望是正當收入嘿",
    "錢進來了喵！記好了！"
]

success_quotes_expense = [
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

    # 處理使用者輸入金額階段
    if state in ["支出", "收入", "預算"]:
        try:
            amount = int(re.search(r"\d+", msg).group())
            if state in ["支出", "收入"]:
                item = "懶得寫"
                match = re.match(r"([一-龥]+)?\s*(\d+)", msg)
                if match and match.group(1):
                    item = match.group(1)
                sheet.append_row([today, state, item, amount, uid])
                quote = random.choice(success_quotes_income if state == "收入" else success_quotes_expense)
                reply = f"{quote}：{state} {item} {amount} 元"
            elif state == "預算":
                sheet.append_row([today, "預算", "本月預算", amount, uid])
                reply = f"喵～我幫妳把這個月的預算記成 {amount} 元了！"
        except:
            reply = "請輸入正確的數字喵～"
        user_states[uid] = None
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # 功能選單指令判斷
    if msg == "支出" or msg == "收入":
        user_states[uid] = msg
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入金額或加上項目喵～\n範例：洗頭 300"))
        return
    elif msg == "本月預算":
        user_states[uid] = "預算"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入這個月的預算金額喵～"))
        return
    elif msg == "查詢明細":
        income, expense, budget, records = get_month_records(uid, year_month)
        reply = format_monthly_report(income, expense, budget, records)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return
    elif msg == "剩餘預算":
        income, expense, budget, _ = get_month_records(uid, year_month)
        if budget == 0:
            reply = "喵～妳還沒設定預算喔，要不要先點『本月預算』呢？"
        else:
            left = budget - expense
            percent = round(left / budget * 100)
            reply = f"喵～本月還剩 {left} 元可用（{percent}%）喔！撐住～"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return
    elif msg == "修改或刪除":
        reply = "請輸入「刪除3」或「刪除1.2.3筆」來刪除，或輸入「全部刪除」喵！"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return
    elif msg.startswith("刪除"):
        all_rows = sheet.get_all_values()
        user_rows = [(i, row) for i, row in enumerate(all_rows[1:], start=2)
                     if row[4] == uid and row[0].startswith(year_month) and row[1] != "預算"]
        if "全部" in msg:
            for i, _ in reversed(user_rows):
                sheet.delete_rows(i)
            reply = "這個月的紀錄都幫妳刪光光囉…不會後悔吧喵？"
        else:
            numbers = re.findall(r"\d+", msg)
            to_delete = []
            for num in sorted(set(map(int, numbers))):
                idx = num - 1
                if 0 <= idx < len(user_rows):
                    row_idx = user_rows[idx][0]
                    to_delete.append((num, row_idx))
            for _, row_idx in sorted(to_delete, key=lambda x: x[1], reverse=True):
                sheet.delete_rows(row_idx)
            if to_delete:
                nums = [str(n) for n, _ in to_delete]
                reply = f"我幫妳刪掉第 {', '.join(nums)} 筆紀錄了喵～"
            else:
                reply = "找不到這些筆數喵，請再確認一下～"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # 如果沒有任何功能進行中，也不是選單指令
    reply = "喵～請先從選單中選一個功能，再開始輸入金額吧！"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
