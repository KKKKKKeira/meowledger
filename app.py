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

pending_action = {}

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
        remain = budget - expense
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

income_quotes = [
    "又賺了多少錢啊喵 💰",
    "喵嗚～錢錢來惹，真好 🐱",
    "收入來了～希望下次更多喵 😽",
    "記好了喵，下次記得也請我吃罐罐嘿 🍣"
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

    if uid in pending_action:
        action = pending_action.pop(uid)
        if action == "set_budget" and msg.isdigit():
            sheet.append_row([today, "預算", "本月預算", msg, uid])
            reply = f"喵～我幫妳把這個月的預算記成 {msg} 元了！"
        elif action == "add_income":
            kind = "收入"
            reply = handle_record_input(uid, today, kind, msg)
        elif action == "add_expense":
            kind = "支出"
            reply = handle_record_input(uid, today, kind, msg)
        elif action == "delete_mode":
            reply = handle_deletion(uid, msg, year_month)
        else:
            reply = "喵？這筆我看不懂，要不要再試一次～"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # 導引指令
    if msg == "支出":
        pending_action[uid] = "add_expense"
        reply = ("喵～要補支出多少呢？輸入格式像是：\n"
                 "『洗頭 300』或『2025-04-03 洗頭 300』\n"
                 "項目可以不填，會自動記成「懶得寫」喵！")
    elif msg == "收入":
        pending_action[uid] = "add_income"
        reply = ("喵～要補收入多少呢？輸入格式像是：\n"
                 "『洗頭 300』或『2025-04-03 洗頭 300』\n"
                 "項目可以不填，會自動記成「懶得寫」喵！")
    elif msg == "預算":
        pending_action[uid] = "set_budget"
        reply = "喵～請輸入本月預算金額（直接輸入數字就可以囉）"
    elif msg == "剩餘預算":
        income, expense, budget, _ = get_month_records(uid, year_month)
        remain = budget - expense
        percent = round(remain / budget * 100) if budget > 0 else 0
        reply = f"喵～本月還剩 {remain} 元可用（{percent}%）喔！撐住～"
    elif msg == "看明細":
        income, expense, budget, records = get_month_records(uid, year_month)
        reply = format_monthly_report(income, expense, budget, records) + "\n\n要刪除哪筆請用「刪除第 1 2 3 筆」或「刪除全部」喵～"
    elif msg == "修改/刪除":
        pending_action[uid] = "delete_mode"
        reply = "喵～要刪哪幾筆呢？輸入像是「刪除 1.2.3 筆」這樣的格式就可以囉～\n如果要刪光光也可以輸入「全部刪除」喵！"
    else:
        reply = "喵？我不太懂你說什麼，可以點圖文選單再來一次喔～"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

def handle_record_input(uid, today, kind, msg):
    date = today
    item = "懶得寫"
    amount = None
    match = re.search(r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2})", msg)
    if match:
        date_str = match.group()
        msg = msg.replace(date_str, "").strip()
        if "/" in date_str:
            m, d = date_str.split("/")
            date = f"{today[:5]}{int(m):02d}-{int(d):02d}"
        else:
            date = date_str

    msg = msg.replace("元", "")
    match = re.match(r"([一-龥A-Za-z]*)\s*(\d+)$", msg)
    if match:
        item, amount = match.groups()
        item = item or "懶得寫"
    elif msg.isdigit():
        amount = msg

    if amount:
        sheet.append_row([date, kind, item, int(amount), uid])
        if kind == "支出":
            return f"{random.choice(success_quotes)}：{kind} {item} -{amount} 元"
        else:
            return f"{random.choice(income_quotes)}：{kind} {item} +{amount} 元"
    return "喵？這筆我看不懂，要不要再試一次～"

def handle_deletion(uid, msg, year_month):
    if "全部刪除" in msg:
        all_rows = sheet.get_all_values()
        rows = [(i, row) for i, row in enumerate(all_rows[1:], start=2)
                if row[4] == uid and row[0].startswith(year_month) and row[1] != "預算"]
        for i, _ in reversed(rows):
            sheet.delete_rows(i)
        return "喵～已經把這個月的紀錄全部刪掉囉！"

    match = re.findall(r"\d+", msg)
    if match:
        numbers = list(map(int, match))
        all_rows = sheet.get_all_values()
        user_rows = [(i, row) for i, row in enumerate(all_rows[1:], start=2)
                     if row[4] == uid and row[0].startswith(year_month) and row[1] != "預算"]
        to_delete = []
        for num in sorted(set(numbers)):
            idx = num - 1
            if 0 <= idx < len(user_rows):
                row_idx = user_rows[idx][0]
                to_delete.append((num, row_idx))
        for _, row_idx in sorted(to_delete, key=lambda x: x[1], reverse=True):
            sheet.delete_rows(row_idx)
        if to_delete:
            nums = [str(n) for n, _ in to_delete]
            return f"我幫妳刪掉第 {', '.join(nums)} 筆紀錄了喵～"
    return "喵？格式怪怪的，再試一次看看～"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
