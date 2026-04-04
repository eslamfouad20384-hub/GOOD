import streamlit as st
import pandas as pd
import requests
import numpy as np
import json
import os
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh

st.set_page_config(layout="wide")
st.title("🚀 Smart Crypto Reversal Scanner PRO")

# ==============================
# 🔄 Auto refresh كل 10 دقايق
# ==============================
st_autorefresh(interval=600000, key="refresh")

# ==============================
# 🔐 Telegram Secrets
# ==============================
TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
CHAT_ID = st.secrets["CHAT_ID"]

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

# ==============================
# 💾 JSON Memory File
# ==============================
SIGNALS_FILE = st.secrets["JSON_FILE"]

# 🔥 إنشاء الملف لو مش موجود
if not os.path.exists(SIGNALS_FILE):
    with open(SIGNALS_FILE, "w") as f:
        json.dump([], f)

def load_signals():
    if not os.path.exists(SIGNALS_FILE):
        return set()
    try:
        with open(SIGNALS_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_signals(signals):
    with open(SIGNALS_FILE, "w") as f:
        json.dump(list(signals), f)

# ==============================
# إعدادات
# ==============================
MIN_VOLUME = 10_000_000
RSI_PERIOD = 14

# ==============================
# جلب العملات
# ==============================
@st.cache_data(ttl=300)
def get_coins():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "volume_desc",
        "per_page": 100,
        "page": 1
    }
    return requests.get(url, params=params).json()

# ==============================
# RSI
# ==============================
def calculate_rsi(prices, period=14):
    delta = np.diff(prices)
    gain = np.maximum(delta, 0)
    loss = -np.minimum(delta, 0)

    avg_gain = np.mean(gain[:period])
    avg_loss = np.mean(loss[:period])

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ==============================
# تحليل العملة
# ==============================
def analyze_coin(coin):
    try:
        coin_id = coin["id"]

        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": 30}
        data = requests.get(url, params=params).json()

        prices = np.array([p[1] for p in data["prices"]])
        volumes = np.array([v[1] for v in data["total_volumes"]])

        if len(prices) < 30:
            return None

        current_price = prices[-1]
        max_price = prices.max()

        drop_percent = ((current_price - max_price) / max_price) * 100

        rsi_now = calculate_rsi(prices[-15:])
        rsi_prev = calculate_rsi(prices[-16:-1])
        rsi_condition = rsi_now < 35 and rsi_now > rsi_prev

        avg_volume = volumes[:-1].mean()
        current_volume = volumes[-1]
        volume_condition = current_volume > avg_volume * 1.5

        recent_prices = prices[-20:]
        support_zone = np.percentile(recent_prices, 20)
        near_support = current_price <= support_zone * 1.1

        ema_20 = pd.Series(prices).ewm(span=20).mean().values
        ema_condition = current_price > ema_20[-1]

        recent_lows = prices[-5:]
        higher_low = recent_lows[-1] > recent_lows.min()

        trend_condition = ema_condition or higher_low

        last = prices[-1]
        prev = prices[-2]
        prev2 = prices[-3]

        bullish_engulfing = (prev < prev2) and (last > prev) and (last > prev2)

        body = abs(last - prev)
        lower_shadow = abs(prev - prev2)
        hammer = lower_shadow > body * 2

        candle_signal = bullish_engulfing or hammer

        strong_drop = drop_percent < -40
        bounce_started = current_price > prices[-3]
        smart_reversal = strong_drop and bounce_started

        score = 0
        if drop_percent < -25: score += 2
        if rsi_condition: score += 2
        if volume_condition: score += 2
        if near_support: score += 2
        if trend_condition: score += 2
        if candle_signal: score += 2
        if smart_reversal: score += 2

        probability = min(score * 8, 95)

        if score >= 10:
            signal = "🚀 STRONG BUY"
        elif score >= 8:
            signal = "🔥 BUY"
        elif score >= 6:
            signal = "⏳ EARLY"
        else:
            signal = "❌ NO"

        return {
            "Coin": coin["symbol"].upper(),
            "Price": round(current_price, 6),
            "Score": score,
            "Chance": probability,
            "Signal": signal
        }

    except:
        return None

# ==============================
# 🚀 تشغيل السكان
# ==============================
def run_scan():
    coins = get_coins()
    results = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        data = list(executor.map(analyze_coin, coins))

    for r in data:
        if r:
            results.append(r)

    df = pd.DataFrame(results)

    if df.empty:
        st.warning("❌ مفيش فرص حالياً")
        return

    df = df.sort_values(by="Score", ascending=False)
    st.dataframe(df, use_container_width=True)

    signals = df[df["Score"] >= 8]
    strong = signals[signals["Score"] >= 10]
    buy = signals[(signals["Score"] >= 8) & (signals["Score"] < 10)]

    sent_signals = load_signals()

    new_strong = []
    new_buy = []

    for _, row in strong.iterrows():
        sid = row["Coin"] + "_STRONG"
        if sid not in sent_signals:
            new_strong.append(row)
            sent_signals.add(sid)

    for _, row in buy.iterrows():
        sid = row["Coin"] + "_BUY"
        if sid not in sent_signals:
            new_buy.append(row)
            sent_signals.add(sid)

    if new_strong or new_buy:
        message = "🚀 Crypto Signals:\n\n"

        if new_strong:
            message += "🚀 STRONG BUY:\n"
            for r in new_strong:
                message += f"- {r['Coin']} | {r['Price']}$ | Score {r['Score']}\n"

        if new_buy:
            message += "\n🔥 BUY:\n"
            for r in new_buy:
                message += f"- {r['Coin']} | {r['Price']}$ | Score {r['Score']}\n"

        send_telegram(message)
        save_signals(sent_signals)
        st.success("📩 تم إرسال إشارات جديدة على Telegram")

# ==============================
# زرار يدوي
# ==============================
if st.button("🔍 Scan السوق بالكامل"):
    run_scan()

# ==============================
# تشغيل تلقائي
# ==============================
run_scan()
