import os
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import pytz
from streamlit_autorefresh import st_autorefresh
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ========== CONFIGURATION ==========
st.set_page_config(page_title="Market Dashboard", layout="wide")
st_autorefresh(interval=900000, key="refresh_15min")  # Auto-refresh every 15 mins
st.title("📈 Intraday Breakout Screener with MACD (Live)")

# ========== STOCK LIST ==========
index_list = ["^NSEI", "^NSEBANK"]
stock_list = [
    "RELIANCE.NS", "HDFCBANK.NS", "INFY.NS", "TCS.NS", "ICICIBANK.NS",
    "LT.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS", "BSE.NS",
    "BHARTIARTL.NS", "TITAN.NS", "ASIANPAINT.NS", "OFSS.NS", "MARUTI.NS",
    "BOSCHLTD.NS", "TRENT.NS", "NESTLEIND.NS", "ULTRACEMCO.NS", "MCX.NS",
    "CAMS.NS", "COFORGE.NS"
] + index_list

# ========== FUNCTIONS ==========
def fetch_data(symbol):
    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    today = now.date()
    start_date = today - timedelta(days=7)

    df_15m = yf.download(symbol, interval="15m", start=start_date, end=now)
    df_15m = df_15m.tz_localize(None)
    df_15m.index = df_15m.index.tz_localize('UTC').tz_convert('Asia/Kolkata')

    df_day = yf.download(symbol, interval="1d", start=start_date, end=now)

    return df_15m, df_day

def analyze(symbol):
    try:
        df_15m, df_day = fetch_data(symbol)
    except Exception as e:
        st.error(f"Data fetch failed for {symbol}: {e}")
        return None

    result = {
        "Stock": symbol.replace(".NS", "").replace("^", ""),
        "CMP": 0,
        "Today Breakout": "",
        "2-Day Breakout": "",
        "Breakout Type": "",
        "Trend": "",
        "MACD": "",
        "Signal": "",
        "MACD Trend": ""
    }

    if df_15m.empty or df_day.empty:
        return None

    today_date = df_15m.index[-1].date()
    df_today = df_15m[df_15m.index.date == today_date]
    if df_today.empty:
        return None

    first_15m = df_today.between_time("09:15", "09:30")

    if first_15m.empty:
        st.warning(f"⚠️ {symbol} me 9:15–9:30 candle nahi mili. Skip kar rahe hain.")
        return None

    if 'High' not in first_15m.columns or 'Low' not in first_15m.columns:
        st.warning(f"⚠️ {symbol} ke 9:15–9:30 candle me High/Low column missing hai. Skip kar rahe hain.")
        return None

    if first_15m['High'].dropna().empty or first_15m['Low'].dropna().empty:
        st.warning(f"⚠️ {symbol} ke 9:15–9:30 candle me High/Low NaN ya empty hai. Skip kar rahe hain.")
        return None

    high_15m = float(first_15m['High'].dropna().max())
    low_15m = float(first_15m['Low'].dropna().min())
    current_price = float(df_today["Close"].iloc[-1])
    result["CMP"] = round(current_price, 2)

    df_2d = df_day[df_day.index.date < today_date].tail(2)
    if df_2d.empty:
        return None

    high_2d = float(df_2d["High"].max())
    low_2d = float(df_2d["Low"].min())

    if current_price > high_15m:
        result["Today Breakout"] = "🔼 Above 15m High"
    elif current_price < low_15m:
        result["Today Breakout"] = "🔽 Below 15m Low"
    if current_price > high_2d:
        result["2-Day Breakout"] = "📈 Above 2-Day High"
    elif current_price < low_2d:
        result["2-Day Breakout"] = "📉 Below 2-Day Low"

    if result["Today Breakout"] and result["2-Day Breakout"]:
        result["Breakout Type"] = "✅ Double Breakout"
    elif result["Today Breakout"]:
        result["Breakout Type"] = result["Today Breakout"]
    elif result["2-Day Breakout"]:
        result["Breakout Type"] = result["2-Day Breakout"]

    df_today["EMA12"] = df_today["Close"].ewm(span=12, adjust=False).mean()
    df_today["EMA26"] = df_today["Close"].ewm(span=26, adjust=False).mean()
    df_today["MACD"] = df_today["EMA12"] - df_today["EMA26"]
    df_today["Signal"] = df_today["MACD"].ewm(span=9, adjust=False).mean()

    macd = df_today["MACD"].iloc[-1]
    signal = df_today["Signal"].iloc[-1]
    result["MACD"] = round(macd, 2)
    result["Signal"] = round(signal, 2)

    if macd > signal:
        result["MACD Trend"] = "🟢 Bullish"
    elif macd < signal:
        result["MACD Trend"] = "🔴 Bearish"
    else:
        result["MACD Trend"] = "⚪️ Sideways"

    if current_price > high_15m and current_price > high_2d:
        result["Trend"] = "🚀 Very Bullish"
    elif current_price > high_15m or current_price > high_2d:
        result["Trend"] = "📈 Bullish"
    elif current_price < low_15m and current_price < low_2d:
        result["Trend"] = "🔻 Very Bearish"
    elif current_price < low_15m or current_price < low_2d:
        result["Trend"] = "📉 Bearish"
    else:
        result["Trend"] = "⏸️ Sideways"

    return result

def send_email_alert(stock):
    sender_email = "rajasinha2000@gmail.com"
    receiver_email = "mdrinfotech79@gmail.com"
    password = "hefy otrq yfji ictv"

    subject = f"🚨 DOUBLE BREAKOUT in {stock}"
    body = f"The stock {stock} has triggered a ✅ DOUBLE BREAKOUT."

    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        print(f"✅ Email sent for {stock}")
    except Exception as e:
        print(f"❌ Email sending failed: {e}")

# ========== MAIN ==========
results = []

with st.spinner("🔄 Fetching live data... Please wait..."):
    for stock in stock_list:
        res = analyze(stock)
        if res:
            results.append(res)

df_result = pd.DataFrame(results)

if not df_result.empty and "Breakout Type" in df_result.columns:
    df_result = df_result[df_result["Breakout Type"] != ""]

    priority = {"🚀 Very Bullish": 1, "🔻 Very Bearish": 2, "📈 Bullish": 3, "📉 Bearish": 4, "⏸️ Sideways": 5}
    df_result["SortKey"] = df_result["Trend"].map(priority)
    df_result = df_result.sort_values("SortKey").drop(columns="SortKey")

    st.dataframe(df_result, use_container_width=True)

    csv = df_result.to_csv(index=False).encode("utf-8")
    st.download_button("💾 Download Breakout CSV", data=csv, file_name="breakout_screener.csv", mime="text/csv")

    EMAIL_LOG_FILE = "emailed_stocks.txt"
    def load_emailed_stocks():
        if os.path.exists(EMAIL_LOG_FILE):
            with open(EMAIL_LOG_FILE, "r") as f:
                return set(f.read().splitlines())
        return set()

    def save_emailed_stock(stock):
        with open(EMAIL_LOG_FILE, "a") as f:
            f.write(f"{stock}\n")

    emailed_stocks = load_emailed_stocks()
    double_breakouts = df_result[df_result["Breakout Type"] == "✅ Double Breakout"]

    if not double_breakouts.empty:
        st.markdown("""
            <div style='padding:20px; background-color:#ffcccc; border:3px solid red; border-radius:10px; animation: flash 1s infinite; text-align:center; font-size:24px; font-weight:bold;'>
                🚨 DOUBLE BREAKOUT ALERT! 🚨
            </div>
            <style>
            @keyframes flash {
                0% {opacity: 1;}
                50% {opacity: 0.5;}
                100% {opacity: 1;}
            }
            </style>
        """, unsafe_allow_html=True)
        st.dataframe(double_breakouts)

        for row in double_breakouts.itertuples():
            if row.Stock not in emailed_stocks:
                send_email_alert(row.Stock)
                save_emailed_stock(row.Stock)
                emailed_stocks.add(row.Stock)

    if st.button("🔄 Reset Email Log"):
        if os.path.exists(EMAIL_LOG_FILE):
            os.remove(EMAIL_LOG_FILE)
            st.success("✅ Email log file cleared.")
        else:
            st.info("ℹ️ No email log file found.")
else:
    st.warning("⚠️ No valid breakout data found.")
