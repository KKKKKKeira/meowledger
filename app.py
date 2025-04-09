# 喵了個帳：LINE 記帳貓貓 Bot 完整程式碼（含提醒語、指令引導、剩餘預算計算）

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
    lower_msg = msg.lower()

    # 功能選單選取後處理
    if lower_msg in ["支出", "收入"]:
        kind = "支出" if lower_msg == "支出" else "收入"
        reply = f"喵～要補{kind}多少呢？輸入格式像是：\n\n`洗頭 300` 或 `2025-04-03 洗頭 300`\n\n項目可以不填，會自動記成「懶得寫」喵！"

    elif lower_msg in ["預算"]:
        reply = "喵～請輸入本月預算金額（直接輸入數字就可以囉）"

    elif lower_msg in ["看明細"]:
        income, expense, budget, records = get_month_records(uid, year_month)
        reply = format_monthly_report(income, expense, budget, records)
        reply += "\n\n如果要看其他月份可以輸入「2025-03」這樣的格式喵～\n如果要刪除，輸入像是「刪除第 1.2.3 筆」就可以了喵！"

    elif lower_msg in ["剩餘預算"]:
        _, expense, budget, _ = get_month_records(uid, year_month)
        if budget:
            remain = budget - expense
            percent = 100 - round(expense / budget * 100)
            reply = f"喵～本月還剩 {remain} 元可用（{percent}%）喔！撐住～"
        else:
            reply = "喵？妳還沒設定預算喵～請先設定預算才看的到剩下多少錢喔！"

    elif lower_msg in ["修改/刪除"]:
        income, expense, budget, records = get_month_records(uid, year_month)
        reply = format_monthly_report(income, expense, budget, records)
        reply += "\n\n喵～要刪哪幾筆呢？輸入像是「刪除第 1.2.3 筆」就可以囉～\n如果要刪光光也可以輸入「全部刪除」喵！"

    elif lower_msg.isdigit() and context.get(uid) == "預算":
        sheet.append_row([today, "預算", "本月預算", msg, uid])
        reply = f"喵～我幫妳把這個月的預算記成 {msg} 元了！"

    elif re.match(r"刪除第[\d\s,\.]+筆", msg):
        numbers = re.findall(r"\d+", msg)
        all_rows = sheet.get_all_values()
        user_rows = [(i, row) for i, row in enumerate(all_rows[1:], start=2)
                     if row[4] == uid and row[0].startswith(year_month) and row[1] != "預算"]
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
            reply = "喵？找不到這些筆數，請再確認一下～"

    elif lower_msg == "全部刪除":
        all_rows = sheet.get_all_values()
        user_rows = [(i, row) for i, row in enumerate(all_rows[1:], start=2)
                     if row[4] == uid and row[0].startswith(year_month) and row[1] != "預算"]
        for i, _ in reversed(user_rows):
            sheet.delete_rows(i)
        reply = "喵～我幫妳把這個月的紀錄通通刪光光了喵！希望妳沒有後悔！"

    elif re.match(r"\d{4}-\d{2}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}|\D+\s*\d+", msg):
        date = today
        kind, item, amount = "支出", "懶得寫", None

        date_match = re.search(r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2})", msg)
        if date_match:
            date_str = date_match.group()
            msg = msg.replace(date_str, "").strip()
            if "/" in date_str:
                m, d = date_str.split("/")
                date = f"{today[:5]}{int(m):02d}-{int(d):02d}"
            else:
                date = date_str

        parts = msg.split()
        if len(parts) == 2 and parts[1].isdigit():
            item = parts[0]
            amount = int(parts[1])
        elif len(parts) == 1 and parts[0].isdigit():
            amount = int(parts[0])
        else:
            reply = "喵？這筆我看不懂，要不要再試一次～"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return

        sheet.append_row([date, kind, item, amount, uid])
        if kind == "收入":
            reply = f"又賺了多少錢啊喵～：{item} +{amount} 元"
        else:
            reply = f"{random.choice(success_quotes)}：{kind} {item} -{amount} 元"

    else:
        reply = "喵？我不太懂你說什麼，可以點圖文選單再來一次喔～"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
