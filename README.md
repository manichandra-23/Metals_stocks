# 🪙 Metals Live Dashboard

Live prices, growth (week / month / year) and charts for Gold, Silver, Platinum,
Palladium, Copper and Nickel in **INR** (Indian units) or **USD**. Works on phone, tablet and PC.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501. To use it on a phone or tablet on the same Wi-Fi, open the
"Network URL" that Streamlit prints.

## Put it online (free): Streamlit Community Cloud

1. Create a GitHub repository and upload `app.py`, `requirements.txt` and `README.md`.
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click **Create app**, pick your repo and branch, and set **Main file path** to `app.py`.
4. Click **Deploy**. You get a public link like `https://your-app-name.streamlit.app`
   that works on any device. Every push to GitHub updates the site.

## Data notes

- Prices come from Yahoo Finance futures (COMEX/NYMEX) and can be delayed ~10–15 minutes.
- INR = international price × live USD/INR rate. Gold, platinum and palladium are shown
  per 10 g, silver and copper per kg. Indian market rates (MCX, jewellers) also include
  import duty and GST, so they are higher.
- Nickel uses the WisdomTree Nickel ETC (`NICK.L`) as a proxy. Its % moves track nickel,
  but its price is per ETC unit, not per tonne.
