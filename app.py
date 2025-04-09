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

# 狀態暫存（記錄每位用戶目前點擊的是哪個功能）
user_states = {}

gcred_json_str = os.getenv("GCRED_JSON")
with open("gcred.json", "w") as f:
    f.write(gcred_json_str)

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("gcred.json", scope)
gc = gspread.authorize(credentials)
sheet = gc.open_by_key(os.getenv("SHEET_ID")).sheet1

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
    report += f"\n\n{detail}\n\n要刪除哪筆請用「刪除第 1 2 3 筆」或「刪除全部」喵～"
    return report

success_quotes = [
    "已記下來了喵，希望不是亂花錢 QQ",
    "好啦好啦，錢花了我也只能記下來了喵…",
    "唉，又是一筆支出呢…我都麻了喵 🫠",
    "收到喵～雖然我覺得可以不買但我嘴硬不說 🐱",
    "花得開心就好啦（吧），我會默默記著的喵～",
    "喵：記好了，不要到月底又說錢怎麼不見了嘿。"
]

income_quotes = [
    "又賺了多少錢啊喵？",
    "喵喵好棒～補充點收入也是不錯的啦！",
    "喵：錢進來了我就記！",
    "收入不嫌多喵～恭喜小富貓再+1 🐾"
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

    state = user_states.get(uid, None)
    reply = ""

    # 收入或支出輸入金額階段
    if state in ["收入", "支出"]:
        match = re.match(r"(?:(\d{4}-\d{2}-\d{2})\s*)?([一-龥]*)\s*(\d+)", msg)
        if match:
            date = match.group(1) or today
            item = match.group(2) or "懶得寫"
            amount = int(match.group(3))
            sheet.append_row([date, state, item, amount, uid])
            quote = random.choice(income_quotes if state == "收入" else success_quotes)
            reply = f"{quote}：{state} {item} {amount} 元"
        else:
            reply = f"喵？這筆我看不懂，要不要再試一次～"
        user_states.pop(uid, None)

    # 預算輸入階段
    elif state == "預算":
        if msg.isdigit():
            sheet.append_row([today, "預算", "本月預算", msg, uid])
            reply = f"喵～我幫妳把這個月的預算記成 {msg} 元了！"
        else:
            reply = "請輸入正確的數字喵～"
        user_states.pop(uid, None)

    # 修改/刪除輸入階段
    elif state == "刪除":
        if "全部" in msg:
            all_rows = sheet.get_all_values()
            user_rows = [(i, row) for i, row in enumerate(all_rows[1:], start=2)
                         if row[4] == uid and row[0].startswith(year_month) and row[1] != "預算"]
            for i, _ in reversed(user_rows):
                sheet.delete_rows(i)
            reply = "已經全部刪光光了喵，希望不是誤觸…"
        else:
            nums = re.findall(r"\d+", msg)
            all_rows = sheet.get_all_values()
            user_rows = [(i, row) for i, row in enumerate(all_rows[1:], start=2)
                         if row[4] == uid and row[0].startswith(year_month) and row[1] != "預算"]
            to_delete = []
            for num in sorted(set(map(int, nums))):
                idx = num - 1
                if 0 <= idx < len(user_rows):
                    to_delete.append((num, user_rows[idx][0]))
            for _, row_idx in sorted(to_delete, key=lambda x: x[1], reverse=True):
                sheet.delete_rows(row_idx)
            if to_delete:
                reply = f"我幫妳刪掉第 {', '.join([str(n) for n, _ in to_delete])} 筆紀錄了喵～"
            else:
                reply = "找不到這些筆數喵，請再確認一下～"
        user_states.pop(uid, None)

    # 選單點擊行為
    elif msg == "支出":
        user_states[uid] = "支出"
        reply = "喵～要補支出多少呢？輸入格式像是：\n『洗頭 300』或『2025-04-03 洗頭 300』\n項目可以不填，會自動記成「懶得寫」喵！"
    elif msg == "收入":
        user_states[uid] = "收入"
        reply = "喵～要補收入多少呢？輸入格式像是：\n『洗頭 300』或『2025-04-03 洗頭 300』\n項目可以不填，會自動記成「懶得寫」喵！"
    elif msg == "預算":
        user_states[uid] = "預算"
        reply = "喵～請輸入本月預算金額（直接輸入數字就可以囉）"
    elif msg in ["看明細", "明細"]:
        income, expense, budget, records = get_month_records(uid, year_month)
        reply = format_monthly_report(income, expense, budget, records)
    elif msg in ["剩餘預算"]:
        income, expense, budget, _ = get_month_records(uid, year_month)
        remain = budget - expense
        percent = int(100 * remain / budget) if budget else 0
        reply = f"喵～本月還剩 {remain} 元可用（{percent}%）喔！撐住～"
    elif msg in ["修改", "刪除", "修改/刪除"]:
        user_states[uid] = "刪除"
        reply = "喵～要刪哪幾筆呢？輸入像是「刪除 1.2.3 筆」這樣的格式就可以囉～\n如果要刪光光也可以輸入「全部刪除」喵！"
    else:
        reply = "喵？我不太懂你說什麼，可以點圖文選單再來一次喔～"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
