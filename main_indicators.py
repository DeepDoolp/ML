import streamlit as st
import pandas as pd
import numpy as np
import joblib
import requests
import ta
import os
import threading
import yfinance as yf
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
from pytrends.request import TrendReq

google_trends_cache = None
google_trends_last_call = datetime.min

google_trends_bitcoin_cache = None
google_trends_bitcoin_last_call = datetime.min

def run():
    # Автообновление каждую минуту
    st_autorefresh(interval=120_000, key="refresh_indicators")
    # Тянем модели
    clf_long = joblib.load("clf_long_4h.pkl")
    clf_short = joblib.load("clf_short_4h.pkl")
    clf_neutral = joblib.load("clf_neutral_4h.pkl")
    clf_fake_pump = joblib.load("clf_fake_pump.pkl")
    clf_fake_dump = joblib.load("clf_fake_dump.pkl")

    with open("feature_order.txt") as f:
        feature_order = [line.strip() for line in f.readlines()]
    feature_defaults = {f: 0 for f in feature_order}


    def get_candles():
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": "ETHUSDT", "interval": "1h", "limit": 150}
        r = requests.get(url, params=params)
        data = r.json()
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "num_trades",
            "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
        ])
        df = df.astype({"open": float, "high": float, "low": float,
                        "close": float, "volume": float})
        return df
    # Добавляем индикаторы
    def add_indicators(df):
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
        df["ema_7"] = ta.trend.EMAIndicator(df["close"], window=7).ema_indicator()
        df["ema_21"] = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator()
        macd = ta.trend.MACD(df["close"])
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_diff"] = macd.macd_diff()
        df["price_change"] = df["close"].pct_change()
        df["volume_diff"] = df["volume"].diff()
        df["volatility"] = df["high"] - df["low"]
        return df
   
    # Тянем внешние признаки
    def get_external_features():
        global google_trends_cache, google_trends_last_call
        global google_trends_bitcoin_cache, google_trends_bitcoin_last_call
        feats = {}
        errors = []
        # Fear & Greed Index
        try:
            fear = requests.get("https://api.alternative.me/fng/?limit=1").json()
            feats["fear_gread_index"] = int(fear['data'][0]['value'])
        except:
            errors.append("Fear & Greed API: нет данных")
        # Funding Rate
        try:
            fr = requests.get("https://fapi.binance.com/fapi/v1/fundingRate", params={"symbol": "ETHUSDT", "limit": 1}).json()[0]
            feats["funding_rate"] = float(fr['fundingRate'])
        except:
            errors.append("Funding Rate API: нет данных")
        # Open Interest
        try:
            oi = requests.get("https://fapi.binance.com/futures/data/openInterestHist", 
                         params={"symbol": "ETHUSDT", "period": "5m", "limit": 1}).json()
            feats["open_interest"] = float(oi[0]["sumOpenInterestValue"])
        except:
            errors.append("Open Interest API: нет данных")
            feats["open_interest"] = 48000

        # Google Trends
        try:
            now = datetime.utcnow()

            # BUY CRYPTO
            if google_trends_cache is None or (now - google_trends_last_call > timedelta(minutes=15)):
                pytrends = TrendReq(hl='en-US', tz=360)
                pytrends.build_payload(["buy crypto"], cat=0, timeframe='now 7-d')
                data = pytrends.interest_over_time()
                google_trends_cache = int(data["buy crypto"].iloc[-1])
                google_trends_last_call = now

            feats["google_trends_buy_crypto"] = google_trends_cache

            # BITCOIN
            if google_trends_bitcoin_cache is None or (now - google_trends_bitcoin_last_call > timedelta(minutes=15)):
                pytrends.build_payload(["bitcoin"], cat=0, timeframe='now 7-d')
                data2 = pytrends.interest_over_time()
                google_trends_bitcoin_cache = int(data2["bitcoin"].iloc[-1])
                google_trends_bitcoin_last_call = now

            feats["google_trends_bitcoin"] = google_trends_bitcoin_cache

        except:
            errors.append("Google Trends API: нет данных")
            feats["google_trends_buy_crypto"] = google_trends_cache if google_trends_cache else 25
            feats["google_trends_bitcoin"] = google_trends_bitcoin_cache if google_trends_bitcoin_cache else 35

        #  VIX через Yahoo Finance
        try:
            vix = yf.download('^VIX', period='5d', interval='1h')
            latest_vix = vix.iloc[-1]
            feats["VIX_Open ^VIX"] = float(vix["Open"].iloc[-1])
            feats["VIX_High ^VIX"] = float(vix["High"].iloc[-1])
            feats["VIX_Low ^VIX"] = float(vix["Low"].iloc[-1])
            feats["VIX_Close ^VIX"] = float(vix["Close"].iloc[-1])
            feats["VIX_Volume ^VIX"] = float(vix["Volume"].iloc[-1])
        except:
            errors.append("VIX API: нет данных")
            feats["VIX_Open ^VIX"] = 1
            feats["VIX_High ^VIX"] = 1
            feats["VIX_Low ^VIX"] = 1
            feats["VIX_Close ^VIX"] = 1
            feats["VIX_Volume ^VIX"] = 1

        return feats, errors

    #
    

    st.title("📊 ETH AI Indicator ")
    delta_threshold = st.slider("Порог уверенности (дельта между Long и Short)", min_value=5, max_value=40, value=15, step=1)

    candles = get_candles()
    candles = add_indicators(candles)
    latest = candles.iloc[-1]

    last_unix_ms = int(candles.iloc[-1]["open_time"])
    last_dt = datetime.utcfromtimestamp(last_unix_ms / 1000)
    now = datetime.utcnow()
    minutes_since = int((now - last_dt).total_seconds() // 60)
    minutes_to_next = 60 - (minutes_since % 60)

    
     # ⏱️ Запускаем таймер обновления надписи в фоне 
    st.caption(f"✅ Обновление данных из API: несколько секунд назад")
    st.caption(f"🕓 Обновление последней свечи через: {minutes_to_next} мин")  # <= тоже без лишнего отступа   

    latest["eth_open"] = latest["open"]
    latest["eth_high"] = latest["high"]
    latest["eth_low"] = latest["low"]
    latest["eth_close"] = latest["close"]
    latest["eth_volume"] = latest["volume"]

    external_feats, errors = get_external_features()
    all_feats = {**latest.to_dict(), **external_feats}
    X_dict = {f: all_feats.get(f, feature_defaults.get(f, 0)) for f in feature_order}
    X_df = pd.DataFrame([X_dict])
    X = X_df.values

    try:
        long_prob = clf_long.predict_proba(X)[0][1] * 100
        short_prob = clf_short.predict_proba(X)[0][1] * 100
        neutral_prob = clf_neutral.predict_proba(X)[0][1] * 100
        fake_pump_prob = clf_fake_pump.predict_proba(X)[0][1] * 100
        fake_dump_prob = clf_fake_dump.predict_proba(X)[0][1] * 100
    except Exception as e:
        st.error("Ошибка при расчёте вероятностей")

    fire = " 🔥" if max(long_prob, short_prob, neutral_prob) > 70 else ""
    delta_long_short = abs(long_prob - short_prob)
    if delta_long_short >= delta_threshold:
        if long_prob > short_prob:
            st.markdown(f"<h4 style='color: green;'>Long 4h — {long_prob:.1f}%{fire}</h4>", unsafe_allow_html=True)
        else:
            st.markdown(f"<h4 style='color: red;'>Short 4h — {short_prob:.1f}%{fire}</h4>", unsafe_allow_html=True)
    else:
        st.markdown(f"<h4 style='color: orange;'>Neutral 4h — {neutral_prob:.1f}%{fire}</h4>", unsafe_allow_html=True)

    # Прогресс-бары
    st.text(f"Long 4h: {long_prob:.1f}%")
    st.progress(int(long_prob))
    st.text(f"Short 4h: {short_prob:.1f}%")
    st.progress(int(short_prob))
    st.text(f"Neutral 4h: {neutral_prob:.1f}%")
    st.progress(int(neutral_prob))
    st.text(f"Fake Pump: {fake_pump_prob:.1f}%")
    st.progress(int(fake_pump_prob))
    st.text(f"Fake Dump: {fake_dump_prob:.1f}%")
    st.progress(int(fake_dump_prob))

    # === Сохраняем предсказания ===
    log_row = {
        "timestamp": datetime.utcnow().isoformat(),
        "long_4h": round(long_prob, 2),
        "short_4h": round(short_prob, 2),
        "neutral_4h": round(neutral_prob, 2),
        "fake_pump": round(fake_pump_prob, 2),
        "fake_dump": round(fake_dump_prob, 2),
        "eth_open": latest["open"],
        "eth_high": latest["high"],
        "eth_low": latest["low"],
        "eth_close": latest["close"],
        "eth_volume": latest["volume"],
        "high_confidence": (
            (long_prob > 55 or short_prob > 55)
            and abs(long_prob - short_prob) > 19
        )
    }
    log_path = "model_predictions_log.csv"
    if os.path.exists(log_path):
        pd.DataFrame([log_row]).to_csv(log_path, mode="a", index=False, header=False)
    else:
        pd.DataFrame([log_row]).to_csv(log_path, index=False)

    if errors:
        st.warning("⚠️ Проблемы с API:")
        for err in errors:
            st.text(err)

    st.markdown("---")
    # 📐 Глубина хаев/лоев
    depth = st.slider("Depth high/low", 2, 10, value=4)

    # 📈 Уровни сопротивления и поддержки
    recent_high = candles["high"].iloc[-(depth+1):-1].max()
    recent_low = candles["low"].iloc[-(depth+1):-1].min()

    # 📊 Решение на основе модели
    long_prob_val = float(long_prob)
    short_prob_val = float(short_prob)

    if long_prob_val > short_prob_val:
        if latest["close"] > recent_high:
            st.success(f"📈 Long подтверждён — цена пробила сопротивление: {recent_high:.2f}")
        else:
            st.info(f"🕵️ Вероятен Long, но сопротивление не пробито (уровень: {recent_high:.2f})")
    else:
        if latest["close"] < recent_low:
            st.success(f"📉 Short подтверждён — цена пробила поддержку: {recent_low:.2f}")
        else:
            st.info(f"🕵️ Вероятен Short, но поддержка не пробита (уровень: {recent_low:.2f})")
            
    st.markdown("---")
    st.subheader("📥 Используемые признаки:")
    st.dataframe(pd.DataFrame(X_dict.items(), columns=["feature", "value"]).set_index("feature"))
    st.markdown("<p style='text-align: center; color: gray; font-size: 13px;'>by Dmitrii Geletii</p>", unsafe_allow_html=True)


    
