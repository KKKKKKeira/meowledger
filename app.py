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

user_state = {}

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

@app.route("/", methods=["GET", "HEAD"])
def home():
    return "喵～我還活著！", 200

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

def extract_month_queries(text):
    result = []
    text = text.replace("月明細", "月")
    cn2num = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10,"十一":11,"十二":12,"四月":4,"三月":3,"五月":5,"六月":6,"七月":7,"八月":8,"九月":9,"十月":10,"十一月":11,"十二月":12}
    all_rows = sheet.get_all_values()[1:]
    years = sorted(list({row[0][:4] for row in all_rows}))
    matches = re.findall(r"(20\d{2})[\/-]?(\d{1,2})|((?:20\d{2})?)\s*([一二三四五六七八九十]+|\d{1,2})月?", text)

    for full, m1, y2, m2 in matches:
        if full and m1:
            y = full
            m = f"{int(m1):02d}"
            result.append(f"{y}-{m}")
        elif m2:
            m = cn2num.get(m2, None) if m2 in cn2num else int(m2)
            m = f"{int(m):02d}"
            y = y2 if y2 else None
            if y:
                result.append(f"{y}-{m}")
            else:
                for year in years:
                    result.append(f"{year}-{m}")
    return result

success_quotes = [
    "喵：記好了，不要到月底又說錢怎麼不見了嘿。",
    "好啦好啦，錢花了我也只能記下來了喵…",
    "唉，又是一筆支出呢…我都麻了喵 🫠",
    "收到喵～雖然我覺得可以不買但我嘴硬不說 🐱",
    "花得開心就好啦（吧），我會默默記著的喵～",
    "已記下來了喵，希望不是亂花錢 QQ"
]

income_quotes = [
    "又賺了多少錢啊喵～好棒好棒！",
    "有錢進帳的感覺真不錯喵～",
    "辛苦了喵，收入我收下了 🐾"
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
    
    if uid not in user_state:
        user_state[uid] = None
    state = user_state[uid]
        # 查詢所有年份的某月份紀錄（例如輸入「3月」會抓 2023-03、2024-03 等）
    if re.fullmatch(r"0?\d{1,2}月", msg):
        target_m = int(re.match(r"0?(\d{1,2})月", msg).group(1))
        all_rows = sheet.get_all_values()[1:]
        matched_years = set()
        for row in all_rows:
            date_str = row[0]
            if not re.match(r"\d{4}-\d{2}-\d{2}", date_str):
                continue
            y, m, _ = date_str.split("-")
            if int(m) == target_m and row[4] == uid:
                matched_years.add(y)

        if not matched_years:
            reply = f"喵？查不到任何 {target_m} 月的紀錄耶～"
            return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

        replies = []
        for y in sorted(matched_years, reverse=True):  # 最新年份排前面
            prefix = f"{y}-{target_m:02d}"
            income, expense, budget, records = get_month_records(uid, prefix)
            report = format_monthly_report(income, expense, budget, records)
            replies.append(TextSendMessage(text=f"【{y} 年 {target_m} 月】\n" + report))

        return line_bot_api.reply_message(event.reply_token, replies)

    if uid not in user_state:
        user_state[uid] = None
    state = user_state[uid]

    if msg in ["支出", "收入"]:
        user_state[uid] = msg
        tip = "支出" if msg == "支出" else "收入"
        hint = "洗頭 300 或 2025-04-03 洗頭 300"
        return line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"喵～要補{tip}多少呢？輸入格式像是：\n『{hint}』\n項目可以不填，會自動記成「懶得寫」喵！")
        )

    elif msg == "預算":
        user_state[uid] = "預算"
        return line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="喵～請輸入本月預算金額（直接輸入數字就可以囉）")
        )

    if msg in ["明細", "看明細"]:
        income, expense, budget, records = get_month_records(uid, year_month)
        user_state[uid] = "刪除"
        reply = format_monthly_report(income, expense, budget, records)
        reply += "\n\n要刪除哪筆請用「刪除第 1 2 3 筆」或「刪除全部」喵～\n想看其他月份的明細可以直接輸入『3月』『202504』『4月明細』這些格式喵！"
        return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    if state == "刪除":
        matched_months = extract_month_queries(msg)
        if matched_months:
            replies = []
            for ym in matched_months:
                income, expense, budget, records = get_month_records(uid, ym)
                report = format_monthly_report(income, expense, budget, records)
                replies.append(f"【{ym}】\n" + report)
            for reply in replies:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return

    elif msg == "剩餘預算":
        income, expense, budget, _ = get_month_records(uid, year_month)
        if budget == 0:
            reply = "這個月還沒設定預算喵～要記得設定嘿！"
        else:
            remain = budget - expense
            percent = round(remain / budget * 100)
            reply = f"喵～本月剩餘預算：{remain} 元（{percent}%）"
        return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    elif msg == "修改/刪除":
        user_state[uid] = "刪除"
        income, expense, budget, records = get_month_records(uid, year_month)
        reply = format_monthly_report(income, expense, budget, records)
        reply += "\n\n喵～要刪哪幾筆呢？輸入像是「刪除第 1.2.3 筆」的格式就可以囉～\n如果要刪光光也可以輸入「全部刪除」喵！"
        return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    if state == "預算" and re.fullmatch(r"\d+", msg):
        sheet.append_row([today, "預算", "本月預算", msg, uid])
        user_state[uid] = None
        return line_bot_api.reply_message(
            event.reply_token, TextSendMessage(text=f"喵～我幫妳把這個月的預算記成 {msg} 元了！")
        )


        if "全部" in msg:
            to_delete = [i for i, _ in user_rows]
            if not to_delete:
                reply = "喵？這個月好像沒有東西能刪了喵～"
            else:
                for i in sorted(to_delete, reverse=True):
                    sheet.delete_rows(i)
                reply = f"喵～這個月的紀錄我全刪掉囉！"
            return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

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
            reply = "喵？我不太懂你說什麼，可以點圖文選單再來一次喔～"

        return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    kind = user_state.get(uid)
    if kind in ["支出", "收入"]:
        date = today
        item = "懶得寫"
        amount = None

        date_match = re.search(r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2})", msg)
        if date_match:
            date_str = date_match.group()
            msg = msg.replace(date_str, "").strip()
            if "/" in date_str:
                m, d = map(int, date_str.split("/"))
                date = f"{today[:5]}{m:02d}-{d:02d}"
            else:
                date = date_str

        match = re.match(r"^([^\d\s]+)?\s?(\d+)$", msg)
        if match:
            if match.group(1):
                item = match.group(1)
            amount = int(match.group(2))

        if amount:
            sheet.append_row([date, kind, item, amount, uid])
            user_state[uid] = kind
            if kind == "收入":
                reply = f"{random.choice(income_quotes)}：收入 {item} +{amount} 元"
            else:
                reply = f"{random.choice(success_quotes)}：支出 {item} -{amount} 元"

            return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        else:
            reply = "喵？這筆我看不懂，要不要再試一次～"
            return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    return line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="喵？我不太懂你說什麼，可以點圖文選單再來一次喔～")
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
