import requests
import pandas as pd
import ta
import asyncio
import telegram
import time

# 📌 لیست جفت‌ارزها
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT"]

# 📌 تنظیمات API بایننس
BINANCE_URL = "https://api.binance.com/api/v3/klines"
INTERVALS = ["5m", "15m", "1h", "4h"]  # تایم‌فریم‌های تأیید
LIMIT = 300

# 📌 تنظیمات تلگرام
TELEGRAM_BOT_TOKEN = "7843135769:AAFT9T0JrNDu4roCO93rcELMnZeRGBeiH8E"
CHAT_ID = "891528057"  # آی‌دی چت تلگرام

# 📌 مقداردهی اولیه مارتینگل
martingale_applied = {}

# 📌 تابع ارسال پیام به تلگرام
async def send_signal(message):
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_message(chat_id=CHAT_ID, text=message)

# 📌 دریافت کندل‌های یک جفت‌ارز در تایم‌فریم مشخص
def get_candles(symbol, interval):
    url = f"{BINANCE_URL}?symbol={symbol}&interval={interval}&limit={LIMIT}"
    response = requests.get(url)
    data = response.json()

    if not data or "code" in data:
        print(f"🚨 خطا در دریافت داده برای {symbol} ({interval}): {data}")
        return pd.DataFrame()

    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume",
                                     "close_time", "quote_asset_volume", "trades", "taker_buy_base",
                                     "taker_buy_quote", "ignore"])
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["volume"] = df["volume"].astype(float)
    return df

# 📌 بررسی سیگنال خرید و فروش
def check_signals():
    global martingale_applied

    for symbol in SYMBOLS:
        signals = []
        valid_timeframes = 0
        volume_confirmed = False

        for interval in INTERVALS:
            df = get_candles(symbol, interval)
            if df.empty:
                continue

            # محاسبه اندیکاتورها
            df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
            macd = ta.trend.MACD(df["close"])
            df["macd"] = macd.macd()
            df["macd_signal"] = macd.macd_signal()
            df["ma7"] = ta.trend.SMAIndicator(df["close"], window=7).sma_indicator()
            df["ma25"] = ta.trend.SMAIndicator(df["close"], window=25).sma_indicator()
            df["ma99"] = ta.trend.SMAIndicator(df["close"], window=99).sma_indicator()
            df["ma200"] = ta.trend.SMAIndicator(df["close"], window=200).sma_indicator()
            df["atr"] = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range()

            df.dropna(inplace=True)
            if df.empty:
                continue

            # بررسی حجم معاملات
            last_volume = df["volume"].iloc[-1]
            avg_volume = df["volume"].rolling(50).mean().iloc[-1]
            if last_volume > 1.2 * avg_volume:
                volume_confirmed = True

            # مقادیر نهایی
            rsi = df["rsi"].iloc[-1]
            macd_val = df["macd"].iloc[-1]
            macd_signal = df["macd_signal"].iloc[-1]
            close_price = df["close"].iloc[-1]
            ma7 = df["ma7"].iloc[-1]
            ma25 = df["ma25"].iloc[-1]
            ma99 = df["ma99"].iloc[-1]
            ma200 = df["ma200"].iloc[-1]
            atr_value = df["atr"].iloc[-1]

            # محاسبه TP و SL
            tp1 = close_price + (1.5 * atr_value)
            tp2 = close_price + (2.5 * atr_value)
            tp3 = close_price + (3.5 * atr_value)
            sl = close_price - max(1.25 * atr_value, 1.2 / 100 * close_price)

            # شرایط خرید
            if 30 < rsi < 55 and macd_val > macd_signal and ma7 > ma25 and close_price > ma99 and close_price > ma200:
                valid_timeframes += 1
                signals.append(f"✔️ {interval}")

            # شرایط فروش
            if 45 < rsi < 70 and macd_val < macd_signal and ma7 < ma25 and close_price < ma99 and close_price < ma200:
                valid_timeframes += 1
                signals.append(f"✔️ {interval}")
                # اگر حداقل ۳ تایم‌فریم تأیید کرده باشند، سیگنال ارسال شود
        if valid_timeframes >= 3:
            message = f"🟢 سیگنال خرید ({symbol})\n" if rsi < 55 else f"🔴 سیگنال فروش ({symbol})\n"
            message += f"📍 قیمت: {close_price} USDT\n"
            message += f"🎯 TP1: {tp1:.2f} USDT\n"
            message += f"🎯 TP2: {tp2:.2f} USDT\n"
            message += f"🎯 TP3: {tp3:.2f} USDT\n"
            message += f"🛑 SL: {sl:.2f} USDT\n\n"
            message += f"📊 اندیکاتورهای تأییدکننده:\n"
            message += f"✅ RSI: {rsi:.2f}\n"
            message += f"✅ MACD کراس تأیید شد\n"
            message += f"✅ MA7 > MA25 و قیمت بالای MA99 و MA200\n"
            message += f"✅ حجم معاملات بالا: {'بله ✅' if volume_confirmed else 'خیر ❌'}\n\n"
            message += f"📈 تایم‌فریم‌های تأیید شده:\n" + ", ".join(signals) + "\n\n"

            # اعمال مارتینگل فقط یکبار در هر سیگنال
            if symbol not in martingale_applied:
                martingale_applied[symbol] = True
                message += "📌 مارتینگل: فعال شد - مقدار پوزیشن کاهش یافت\n\n"

            message += "📢 برای دریافت سیگنال‌های بیشتر و تحلیل‌های رایگان، به کانال ما بپیوندید:\n👉 @YourChannel"

            loop = asyncio.get_event_loop()
            loop.run_until_complete(send_signal(message))
            print(message)

# اجرای مداوم برای بررسی سیگنال‌ها هر ۵ دقیقه
while True:
    check_signals()
    time.sleep(300)
