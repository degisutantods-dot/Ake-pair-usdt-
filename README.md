# AKE/USDT Market Dashboard

Dashboard Streamlit untuk membaca data publik Gate.io dan menampilkan candlestick, EMA20/EMA50, RSI14, MACD, serta ringkasan kondisi teknikal berbasis aturan.

## Jalankan lokal
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy ke Streamlit Community Cloud
1. Buat repository GitHub baru.
2. Upload `app.py`, `requirements.txt`, dan `README.md`.
3. Di Streamlit Community Cloud, pilih repository dan file utama `app.py`.
4. Deploy.

Pair default: `AKE_USDT`. Ubah melalui sidebar bila simbol pair berbeda di Gate.io.

Aplikasi hanya membaca API publik dan tidak mengeksekusi order.
