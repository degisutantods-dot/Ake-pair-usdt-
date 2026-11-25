import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from datetime import datetime, timezone

st.set_page_config(page_title="AKE/USDT Market Dashboard", page_icon="📊", layout="wide")

API = "https://api.gateio.ws/api/v4"

st.title("📊 AKE/USDT — Market Dashboard")
st.caption("Pemantauan pasar berbasis data publik Gate.io. Sinyal dihitung otomatis dari indikator teknikal; bukan jaminan hasil.")

with st.sidebar:
    st.header("Pengaturan")
    pair = st.text_input("Pair Gate.io", value="AKE_USDT").strip().upper().replace("/", "_")
    timeframe = st.selectbox("Timeframe utama", ["15m", "1h", "4h"], index=1)
    refresh = st.button("🔄 Muat ulang data", use_container_width=True)
    st.caption("Data dibaca dari API publik Gate.io. Tidak perlu API key dan aplikasi tidak dapat mengeksekusi order.")

@st.cache_data(ttl=30, show_spinner=False)
def get_ticker(pair):
    r = requests.get(f"{API}/spot/tickers", params={"currency_pair": pair}, timeout=15)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise ValueError(f"Pair {pair} tidak ditemukan di Gate.io.")
    return data[0]

@st.cache_data(ttl=30, show_spinner=False)
def get_candles(pair, interval, limit=200):
    r = requests.get(
        f"{API}/spot/candlesticks",
        params={"currency_pair": pair, "interval": interval, "limit": limit},
        timeout=20
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise ValueError("Gate.io tidak mengembalikan data candle untuk pair/timeframe ini.")
    # Gate.io candle format: [timestamp, quote_volume, close, high, low, open, base_volume, ...]
    df = pd.DataFrame(rows)
    if df.shape[1] < 7:
        raise ValueError("Format data candle dari bursa tidak sesuai.")
    df = df.iloc[:, :7]
    df.columns = ["time", "quote_volume", "close", "high", "low", "open", "base_volume"]
    for col in ["quote_volume", "close", "high", "low", "open", "base_volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["time"] = pd.to_datetime(pd.to_numeric(df["time"]), unit="s", utc=True)
    df = df.dropna().sort_values("time").reset_index(drop=True)
    return df

def indicators(df):
    x = df.copy()
    x["ema20"] = x["close"].ewm(span=20, adjust=False).mean()
    x["ema50"] = x["close"].ewm(span=50, adjust=False).mean()
    delta = x["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    x["rsi"] = 100 - (100 / (1 + rs))
    ema12 = x["close"].ewm(span=12, adjust=False).mean()
    ema26 = x["close"].ewm(span=26, adjust=False).mean()
    x["macd"] = ema12 - ema26
    x["macd_signal"] = x["macd"].ewm(span=9, adjust=False).mean()
    x["macd_hist"] = x["macd"] - x["macd_signal"]
    return x

def assess(row):
    # Rules-based educational signal: trend + momentum confirmation.
    bullish = row["ema20"] > row["ema50"] and row["macd"] > row["macd_signal"] and 50 <= row["rsi"] < 70
    bearish = row["ema20"] < row["ema50"] and row["macd"] < row["macd_signal"] and 30 < row["rsi"] <= 50
    if bullish:
        return "BUY", "Tren EMA20 di atas EMA50; MACD bullish; RSI mendukung momentum."
    if bearish:
        return "SELL", "Tren EMA20 di bawah EMA50; MACD bearish; RSI menunjukkan momentum lemah."
    return "WAIT", "Indikator belum searah atau momentum berada di area yang kurang meyakinkan."

if refresh:
    st.cache_data.clear()

try:
    with st.spinner("Mengambil data dari Gate.io..."):
        ticker = get_ticker(pair)
        raw = get_candles(pair, timeframe)
        df = indicators(raw)
    latest = df.iloc[-1]
    signal, reason = assess(latest)

    price = float(ticker.get("last", latest["close"]))
    change = float(ticker.get("change_percentage", 0) or 0)
    high = float(ticker.get("high_24h", np.nan))
    low = float(ticker.get("low_24h", np.nan))
    quote_vol = float(ticker.get("quote_volume", np.nan))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Harga terakhir", f"{price:.8g} USDT", f"{change:.2f}% (24 jam)")
    c2.metric("RSI 14", f"{latest['rsi']:.1f}" if pd.notna(latest["rsi"]) else "Belum cukup data")
    c3.metric("EMA 20", f"{latest['ema20']:.8g}")
    c4.metric("EMA 50", f"{latest['ema50']:.8g}")

    st.subheader("Ringkasan indikator")
    color = {"BUY": "🟢", "SELL": "🔴", "WAIT": "🟡"}[signal]
    st.markdown(f"### {color} Kondisi teknikal: **{signal}**")
    st.write(reason)
    st.caption("Sinyal ini murni hasil aturan EMA/RSI/MACD pada candle terakhir timeframe terpilih. Konfirmasi timeframe lain dan kondisi likuiditas sebelum mengambil keputusan.")

    left, right = st.columns([2, 1])
    with left:
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df["time"], open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="Harga"
        ))
        fig.add_trace(go.Scatter(x=df["time"], y=df["ema20"], name="EMA 20", line=dict(width=1.5)))
        fig.add_trace(go.Scatter(x=df["time"], y=df["ema50"], name="EMA 50", line=dict(width=1.5)))
        fig.update_layout(height=520, xaxis_rangeslider_visible=False, margin=dict(l=10,r=10,t=30,b=10))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.markdown("**Data 24 jam**")
        st.write(f"High: `{high:.8g}`" if pd.notna(high) else "High: —")
        st.write(f"Low: `{low:.8g}`" if pd.notna(low) else "Low: —")
        st.write(f"Volume quote: `{quote_vol:,.2f} USDT`" if pd.notna(quote_vol) else "Volume quote: —")
        st.markdown("**Pembacaan RSI**")
        rsi = latest["rsi"]
        if pd.isna(rsi):
            st.write("Data belum cukup.")
        elif rsi >= 70:
            st.write("RSI ≥ 70: momentum tinggi; waspadai kondisi jenuh beli.")
        elif rsi <= 30:
            st.write("RSI ≤ 30: momentum lemah; waspadai kondisi jenuh jual.")
        else:
            st.write("RSI berada di rentang tengah (30–70).")

    st.subheader("MACD")
    macd_fig = go.Figure()
    macd_fig.add_trace(go.Scatter(x=df["time"], y=df["macd"], name="MACD"))
    macd_fig.add_trace(go.Scatter(x=df["time"], y=df["macd_signal"], name="Signal"))
    macd_fig.add_trace(go.Bar(x=df["time"], y=df["macd_hist"], name="Histogram"))
    macd_fig.update_layout(height=260, margin=dict(l=10,r=10,t=20,b=10))
    st.plotly_chart(macd_fig, use_container_width=True)

    st.subheader("Data candle terbaru")
    view = df[["time","open","high","low","close","base_volume","ema20","ema50","rsi","macd","macd_signal"]].tail(12).copy()
    view["time"] = view["time"].dt.strftime("%Y-%m-%d %H:%M UTC")
    st.dataframe(view.sort_values("time", ascending=False), use_container_width=True, hide_index=True)

    st.caption(f"Terakhir diperbarui: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
except requests.HTTPError as e:
    st.error(f"Gate.io mengembalikan error HTTP: {e}. Periksa nama pair atau coba lagi.")
except requests.RequestException as e:
    st.error(f"Gagal terhubung ke Gate.io: {e}")
except Exception as e:
    st.error(f"Tidak dapat memuat analisis: {e}")

st.divider()
st.warning("Manajemen risiko: indikator teknikal dapat menghasilkan sinyal keliru, terutama pada aset berlikuiditas rendah. Jangan gunakan leverage hanya berdasarkan sinyal ini. Aplikasi ini hanya membaca data dan tidak mengirim order.")
st.caption("Bukan nasihat keuangan. Selalu verifikasi harga, spread, volume, dan berita secara mandiri.")
