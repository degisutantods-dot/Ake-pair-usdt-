import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from datetime import datetime, timezone

st.set_page_config(page_title="AKE Market Intelligence V2", page_icon="📈", layout="wide")
API = "https://api.gateio.ws/api/v4"
st.title("📈 AKE Market Intelligence — V2")
st.caption("Dashboard pemantauan multi-timeframe dari data publik Gate.io. Tidak mengeksekusi transaksi.")

with st.sidebar:
    st.header("Pengaturan")
    pair = st.text_input("Pair Gate.io", "AKE_USDT").strip().upper().replace("/", "_")
    selected_tf = st.selectbox("Grafik utama", ["15m", "1h", "4h"], index=1)
    if st.button("🔄 Refresh data", use_container_width=True):
        st.cache_data.clear()

@st.cache_data(ttl=30, show_spinner=False)
def candles(pair, interval):
    r = requests.get(f"{API}/spot/candlesticks",
        params={"currency_pair": pair, "interval": interval, "limit": 200}, timeout=20)
    r.raise_for_status()
    raw = r.json()
    if not raw: raise ValueError(f"Tidak ada data candle {pair} / {interval}.")
    d = pd.DataFrame(raw).iloc[:, :7]
    d.columns = ["time","quote_volume","close","high","low","open","base_volume"]
    for c in ["quote_volume","close","high","low","open","base_volume"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["time"] = pd.to_datetime(pd.to_numeric(d["time"]), unit="s", utc=True)
    return d.dropna().sort_values("time").reset_index(drop=True)

@st.cache_data(ttl=30, show_spinner=False)
def ticker(pair):
    r = requests.get(f"{API}/spot/tickers", params={"currency_pair": pair}, timeout=15)
    r.raise_for_status()
    data = r.json()
    if not data: raise ValueError(f"Pair {pair} tidak ditemukan.")
    return data[0]

def indicators(d):
    x = d.copy()
    x["ema20"] = x.close.ewm(span=20, adjust=False).mean()
    x["ema50"] = x.close.ewm(span=50, adjust=False).mean()
    delta = x.close.diff()
    ag = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    al = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    x["rsi"] = 100 - 100/(1 + ag/al.replace(0, np.nan))
    e12, e26 = x.close.ewm(span=12, adjust=False).mean(), x.close.ewm(span=26, adjust=False).mean()
    x["macd"] = e12-e26
    x["macd_signal"] = x.macd.ewm(span=9, adjust=False).mean()
    pc = x.close.shift(1)
    tr = pd.concat([x.high-x.low, (x.high-pc).abs(), (x.low-pc).abs()], axis=1).max(axis=1)
    x["atr14"] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    x["atr_pct"] = x.atr14/x.close*100
    return x

def trend(r):
    if r.ema20 > r.ema50 and r.macd > r.macd_signal: return "Bullish"
    if r.ema20 < r.ema50 and r.macd < r.macd_signal: return "Bearish"
    return "Netral"

try:
    with st.spinner("Mengambil data dari Gate.io..."):
        t = ticker(pair)
        frames = {tf: indicators(candles(pair, tf)) for tf in ["15m","1h","4h"]}
    main = frames[selected_tf]
    last = main.iloc[-1]
    price = float(t.get("last", last.close))
    change = float(t.get("change_percentage", 0) or 0)
    support = float(main.tail(80).low.min())
    resistance = float(main.tail(80).high.max())

    st.subheader("Ringkasan harga")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Harga terakhir", f"{price:.8g} USDT", f"{change:.2f}% / 24 jam")
    vol = t.get("quote_volume")
    c2.metric("Volume quote 24 jam", f"{float(vol):,.2f} USDT" if vol else "—")
    c3.metric("Support referensi", f"{support:.8g}")
    c4.metric("Resistance referensi", f"{resistance:.8g}")

    st.subheader("Konfirmasi multi-timeframe")
    cols = st.columns(3)
    trend_map = {}
    for col, tf in zip(cols, ["15m","1h","4h"]):
        r = frames[tf].iloc[-1]
        trend_map[tf] = trend(r)
        with col:
            st.markdown(f"### {tf} — {trend_map[tf]}")
            st.write(f"RSI 14: {r.rsi:.1f}" if pd.notna(r.rsi) else "RSI 14: —")
            st.write("MACD di atas signal" if r.macd > r.macd_signal else "MACD di bawah signal")
            st.write("EMA20 di atas EMA50" if r.ema20 > r.ema50 else "EMA20 di bawah/sama dengan EMA50")

    bull = sum(v == "Bullish" for v in trend_map.values())
    bear = sum(v == "Bearish" for v in trend_map.values())
    if bull >= 2: summary = f"Kecenderungan bullish — {bull} dari 3 timeframe searah positif."
    elif bear >= 2: summary = f"Kecenderungan bearish — {bear} dari 3 timeframe searah negatif."
    else: summary = "Kondisi campuran/netral — konfirmasi antar-timeframe belum searah."
    st.info("**Ringkasan pasar:** " + summary)

    st.subheader(f"Grafik candlestick — {selected_tf}")
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=main.time, open=main.open, high=main.high, low=main.low, close=main.close, name="Harga"))
    fig.add_trace(go.Scatter(x=main.time, y=main.ema20, name="EMA 20", line=dict(width=1.4)))
    fig.add_trace(go.Scatter(x=main.time, y=main.ema50, name="EMA 50", line=dict(width=1.4)))
    fig.add_hline(y=support, line_dash="dot", annotation_text="Support referensi")
    fig.add_hline(y=resistance, line_dash="dot", annotation_text="Resistance referensi")
    fig.update_layout(height=500, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Momentum dan volatilitas")
    a,b,c = st.columns(3)
    rsi = last.rsi
    rsi_text = "Belum cukup data" if pd.isna(rsi) else ("Jenuh beli (≥70)" if rsi >= 70 else ("Jenuh jual (≤30)" if rsi <= 30 else "Rentang tengah"))
    a.metric("RSI 14", f"{rsi:.1f}" if pd.notna(rsi) else "—", rsi_text)
    b.metric("ATR 14", f"{last.atr14:.8g}" if pd.notna(last.atr14) else "—")
    c.metric("ATR / harga", f"{last.atr_pct:.2f}%" if pd.notna(last.atr_pct) else "—")
    st.caption("ATR mengukur besar volatilitas, bukan arah harga. Support/resistance adalah low/high ekstrem 80 candle terakhir pada timeframe terpilih.")

    mf = go.Figure()
    mf.add_trace(go.Scatter(x=main.time, y=main.macd, name="MACD"))
    mf.add_trace(go.Scatter(x=main.time, y=main.macd_signal, name="Signal"))
    mf.add_trace(go.Bar(x=main.time, y=main.macd-main.macd_signal, name="Histogram"))
    mf.update_layout(height=260)
    st.plotly_chart(mf, use_container_width=True)

    with st.expander("Data candle terbaru"):
        tab = main[["time","open","high","low","close","base_volume","ema20","ema50","rsi","atr14"]].tail(15).copy()
        tab["time"] = tab.time.dt.strftime("%Y-%m-%d %H:%M UTC")
        st.dataframe(tab.sort_values("time", ascending=False), use_container_width=True, hide_index=True)
    st.caption("Pembaruan: " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))

except requests.HTTPError as e:
    st.error(f"Error HTTP Gate.io: {e}. Periksa pair atau coba lagi.")
except requests.RequestException as e:
    st.error(f"Koneksi ke Gate.io gagal: {e}")
except Exception as e:
    st.error(f"Gagal memproses data: {e}")

st.divider()
st.warning("Indikator dapat terlambat atau keliru. Pada aset berlikuiditas rendah, spread dan slippage dapat besar. Dashboard ini untuk pemantauan/edukasi, bukan instruksi transaksi atau nasihat keuangan.")
