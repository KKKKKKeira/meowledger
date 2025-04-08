# 喵了個帳 LINE Bot

這是一隻厭世但可愛的 LINE 記帳貓 Bot 🐱💸

## 部署方式（Render + GitHub）

1. Fork 此專案到你的 GitHub 帳號
2. 前往 [https://render.com](https://render.com)，選擇 New → Web Service
3. 選擇你的 repo，設定以下內容：

### Build Command:
```
pip install -r requirements.txt
```

### Start Command:
```
python app.py
```

### 環境變數（Environment Variables）：
- `CHANNEL_SECRET`
- `CHANNEL_ACCESS_TOKEN`
- `SHEET_ID`

4. 部署完成後，到 LINE Developer 後台，把 Webhook 設成：
```
https://你的render網址/webhook
```
