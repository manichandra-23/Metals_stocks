"""
Metals Live Dashboard
Live prices for Gold, Silver, Platinum, Palladium, Copper and Nickel in INR or USD,
using Yahoo Finance (via yfinance). Run with:  streamlit run app.py
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# --------------------------------------------------------------------------------------
# Page setup
# --------------------------------------------------------------------------------------
st.set_page_config(
    page_title="Metals Live Dashboard",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="auto",
)

# Responsive tweaks: tighter padding + smaller numbers on phones, comfy on tablet/PC.
st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px;}
      [data-testid="stMetricValue"] {font-variant-numeric: tabular-nums;}
      .unit-note {color: #898781; font-size: 0.8rem; margin-top: -0.4rem;}
      @media (max-width: 900px) {
        .block-container {padding-left: 1.25rem; padding-right: 1.25rem;}
      }
      @media (max-width: 640px) {
        .block-container {padding: 1rem 1rem 3rem 1rem;}
        h1 {font-size: 1.6rem !important;}
        [data-testid="stMetricValue"] {font-size: 1.5rem;}
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------------------
# Metals config
# --------------------------------------------------------------------------------------
TROY_OZ_G = 31.1034768
LB_PER_KG = 2.20462262
FX = "INR=X"  # USD -> INR

METALS: dict[str, dict] = {
    # usd_unit: quote unit on the exchange; inr_unit/inr_factor: Indian market convention
    "Gold": {"ticker": "GC=F", "symbol": "Au", "usd_unit": "USD / troy oz",
             "inr_unit": "INR / 10 g", "inr_factor": 10 / TROY_OZ_G, "proxy": False},
    "Silver": {"ticker": "SI=F", "symbol": "Ag", "usd_unit": "USD / troy oz",
               "inr_unit": "INR / kg", "inr_factor": 1000 / TROY_OZ_G, "proxy": False},
    "Platinum": {"ticker": "PL=F", "symbol": "Pt", "usd_unit": "USD / troy oz",
                 "inr_unit": "INR / 10 g", "inr_factor": 10 / TROY_OZ_G, "proxy": False},
    "Palladium": {"ticker": "PA=F", "symbol": "Pd", "usd_unit": "USD / troy oz",
                  "inr_unit": "INR / 10 g", "inr_factor": 10 / TROY_OZ_G, "proxy": False},
    "Copper": {"ticker": "HG=F", "symbol": "Cu", "usd_unit": "USD / lb",
               "inr_unit": "INR / kg", "inr_factor": LB_PER_KG, "proxy": False},
    # Yahoo has no nickel futures feed; the WisdomTree Nickel ETC tracks nickel futures.
    "Nickel": {"ticker": "NICK.L", "symbol": "Ni", "usd_unit": "USD / unit · ETC proxy",
               "inr_unit": "INR / unit · ETC proxy", "inr_factor": 1.0, "proxy": True},
}
BY_TICKER = {m["ticker"]: m for m in METALS.values()}

# Colour follows the metal everywhere (validated categorical palette, light + dark steps).
COLORS = {
    "light": {
        "Silver": "#2a78d6", "Copper": "#eb6834", "Platinum": "#1baf7a",
        "Gold": "#eda100", "Palladium": "#e87ba4", "Nickel": "#008300",
    },
    "dark": {
        "Silver": "#3987e5", "Copper": "#d95926", "Platinum": "#199e70",
        "Gold": "#c98500", "Palladium": "#d55181", "Nickel": "#008300",
    },
}
UP = {"light": "#006300", "dark": "#0ca30c"}
DOWN = "#d03b3b"
MUTED = "#898781"

# Range -> (yfinance interval, yfinance period, look-back days or "ytd")
RANGES = {
    "1D": ("5m", "5d", 1),
    "1W": ("30m", "1mo", 7),
    "1M": ("1h", "3mo", 30),
    "3M": ("1d", "5y", 91),
    "YTD": ("1d", "5y", "ytd"),
    "1Y": ("1d", "5y", 365),
    "5Y": ("1d", "5y", 1826),
}
GROWTH_PERIODS = {"1 Week": 7, "1 Month": 30, "3 Months": 91, "YTD": "ytd", "1 Year": 365}


def theme_mode() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:
        return "light"


MODE = theme_mode()
COLOR = COLORS[MODE]

# --------------------------------------------------------------------------------------
# Sidebar (currency first: everything below depends on it)
# --------------------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Settings")
    currency = st.radio("Currency", ["₹ INR", "$ USD"], horizontal=True, key="currency")
    CUR = "INR" if currency.startswith("₹") else "USD"
    SYM = "₹" if CUR == "INR" else "$"
    selected = st.multiselect("Metals", list(METALS), default=list(METALS))
    auto = st.toggle("Auto-refresh live prices", value=True)
    every = st.select_slider("Refresh every", options=["30s", "1m", "2m", "5m"], value="1m",
                             disabled=not auto)
    if st.button("🔄 Refresh all data now", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.caption(
        "**Data:** Yahoo Finance front-month futures (COMEX/NYMEX), can be delayed "
        "~10–15 min. **INR** = international price × live USD/INR rate, shown in Indian "
        "units (gold/platinum/palladium per 10 g, silver/copper per kg). Indian market "
        "rates (MCX, jewellers) also include import duty and 3% GST, so they will be higher. "
        "**Nickel** uses the WisdomTree Nickel ETC (NICK.L) as a proxy: its % moves track "
        "nickel, but its price is per ETC unit, not per tonne."
    )


def unit_of(meta: dict) -> str:
    return meta["inr_unit"] if CUR == "INR" else meta["usd_unit"]


# --------------------------------------------------------------------------------------
# Data layer
# --------------------------------------------------------------------------------------
def _download(tickers: tuple[str, ...], period: str, interval: str) -> dict[str, pd.DataFrame]:
    raw = yf.download(
        list(tickers),
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=True,
    )
    out: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        return out
    for t in tickers:
        try:
            sub = raw.xs(t, axis=1, level=1) if isinstance(raw.columns, pd.MultiIndex) else raw
        except KeyError:
            continue
        sub = sub.dropna(subset=["Close"])
        if sub.empty:
            continue
        idx = pd.to_datetime(sub.index)
        if idx.tz is not None:
            idx = idx.tz_convert("UTC").tz_localize(None)
        sub = sub.copy()
        sub.index = idx
        out[t] = sub[~sub.index.duplicated(keep="last")].sort_index()
    return out


@st.cache_data(ttl=60, show_spinner=False)
def fetch_live(tickers: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    """Last few daily bars (today's bar updates live) – refreshed every minute."""
    return _download(tickers, "5d", "1d")


@st.cache_data(ttl=60, show_spinner=False)
def fetch_intraday(tickers: tuple[str, ...], period: str, interval: str) -> dict[str, pd.DataFrame]:
    return _download(tickers, period, interval)


@st.cache_data(ttl=900, show_spinner=False)
def fetch_daily(tickers: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    return _download(tickers, "5y", "1d")


def _with_fx(tickers: tuple[str, ...]) -> tuple[str, ...]:
    return tickers + (FX,) if CUR == "INR" else tickers


FX_MISSING = False


def _convert(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """USD exchange prices -> INR in Indian units, using the USD/INR rate at each timestamp."""
    global FX_MISSING
    if CUR == "USD":
        return {t: df for t, df in data.items() if t != FX}
    fx = data.get(FX)
    if fx is None or fx.empty:
        FX_MISSING = True
        return {t: df for t, df in data.items() if t != FX}
    fx_close = fx["Close"]
    out = {}
    for t, df in data.items():
        if t == FX:
            continue
        rate = (fx_close.reindex(fx_close.index.union(df.index)).sort_index()
                .ffill().bfill().reindex(df.index))
        factor = rate * BY_TICKER[t]["inr_factor"]
        d = df.copy()
        for c in ("Open", "High", "Low", "Close", "Adj Close"):
            if c in d:
                d[c] = d[c] * factor
        out[t] = d
    return out


def live_data(tickers):
    return _convert(fetch_live(_with_fx(tickers)))


def intraday_data(tickers, period, interval):
    return _convert(fetch_intraday(_with_fx(tickers), period, interval))


def daily_data(tickers):
    return _convert(fetch_daily(_with_fx(tickers)))


def usd_inr() -> tuple[float, float] | None:
    fx = fetch_live((FX,)).get(FX)
    if fx is None or fx.empty:
        return None
    last = float(fx["Close"].iloc[-1])
    prev = float(fx["Close"].iloc[-2]) if len(fx) > 1 else last
    return last, prev


def get_range(tickers: tuple[str, ...], range_key: str) -> dict[str, pd.DataFrame]:
    interval, period, lookback = RANGES[range_key]
    data = daily_data(tickers) if interval == "1d" else intraday_data(tickers, period, interval)
    out = {}
    for t, df in data.items():
        if lookback == "ytd":
            start = pd.Timestamp(dt.date(df.index[-1].year, 1, 1))
        else:
            start = df.index[-1] - pd.Timedelta(days=lookback)
        sliced = df[df.index >= start]
        if not sliced.empty:
            out[t] = sliced
    return out


def pct_change_over(close: pd.Series, lookback) -> float | None:
    if close.empty:
        return None
    latest = float(close.iloc[-1])
    if lookback == "ytd":
        past = close[close.index < pd.Timestamp(dt.date(close.index[-1].year, 1, 1))]
    else:
        past = close[close.index <= close.index[-1] - pd.Timedelta(days=lookback)]
    if past.empty:
        return None
    return (latest / float(past.iloc[-1]) - 1) * 100


# --------------------------------------------------------------------------------------
# Formatting (Indian digit grouping for INR: 1,23,456.78)
# --------------------------------------------------------------------------------------
def _group_inr(n: float, decimals: int) -> str:
    whole, _, frac = f"{n:.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return whole + ("." + frac if frac else "")


def _decimals(v: float) -> int:
    return 4 if abs(v) < 10 else 2


def _num(v: float, decimals: int) -> str:
    return _group_inr(abs(v), decimals) if CUR == "INR" else f"{abs(v):,.{decimals}f}"


def fmt_price(v: float) -> str:
    return f"{SYM}{_num(v, _decimals(v))}"


def fmt_delta(v: float, ref: float) -> str:
    return f"{'+' if v >= 0 else '-'}{SYM}{_num(v, _decimals(ref))}"


def axis_fmt(v: float) -> str:
    return ",.3f" if v < 10 else (",.0f" if v >= 10000 else ",.2f")


def base_layout(fig: go.Figure, height: int = 420, money: bool = True,
                ref: float = 100.0) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=36, b=8),
        hovermode="x unified",
        dragmode=False,  # keeps page scrolling smooth on touch screens
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None),
        xaxis=dict(showgrid=False),
        yaxis=dict(gridwidth=1, side="right",
                   tickprefix=SYM if money else None,
                   tickformat=axis_fmt(ref) if money else None),
    )
    return fig


PLOTLY_CONFIG = {"displaylogo": False, "scrollZoom": False, "responsive": True,
                 "modeBarButtonsToRemove": ["lasso2d", "select2d"]}

if not selected:
    st.info("Pick at least one metal in the sidebar.")
    st.stop()

SEL_TICKERS = tuple(METALS[m]["ticker"] for m in selected)

# --------------------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------------------
st.title("🪙 Metals Live Dashboard")
st.caption("Gold · Silver · Platinum · Palladium · Copper · Nickel: live prices, growth & trends"
           f" · prices in **{CUR}**")


# --------------------------------------------------------------------------------------
# Live price tiles (auto-refreshing fragment)
# --------------------------------------------------------------------------------------
def live_tiles():
    live = live_data(SEL_TICKERS)
    spark = intraday_data(SEL_TICKERS, "5d", "15m")
    info = f"🟢 Last checked {dt.datetime.now().strftime('%H:%M:%S')} (local time)"
    if auto:
        info += f" · auto-refresh every {every}"
    if CUR == "INR":
        fx = usd_inr()
        if fx:
            info += f" · **USD/INR ₹{fx[0]:.2f}** ({(fx[0] / fx[1] - 1) * 100:+.2f}%)"
    st.caption(info)
    if FX_MISSING:
        st.warning("Couldn't load the USD/INR rate right now, so prices are shown in USD.")

    per_row = 3
    for i in range(0, len(selected), per_row):
        cols = st.columns(per_row)
        for col, name in zip(cols, selected[i:i + per_row]):
            meta = METALS[name]
            df = live.get(meta["ticker"])
            with col:
                if df is None or len(df) < 1:
                    st.metric(f"{name} ({meta['symbol']})", "—", border=True,
                              help="No data returned right now.")
                    continue
                price = float(df["Close"].iloc[-1])
                prev = float(df["Close"].iloc[-2]) if len(df) > 1 else price
                chg = price - prev
                pct = (chg / prev * 100) if prev else 0.0
                sp = spark.get(meta["ticker"])
                chart = None
                if sp is not None and not sp.empty:
                    chart = sp["Close"][sp.index >= sp.index[-1] - pd.Timedelta(days=1)].tolist()
                st.metric(
                    label=f"{name} ({meta['symbol']})" + (" · proxy" if meta["proxy"] else ""),
                    value=fmt_price(price),
                    delta=f"{fmt_delta(chg, price)} ({pct:+.2f}%)",
                    chart_data=chart,
                    chart_type="area",
                    border=True,
                    help=f"{unit_of(meta)} · ticker {meta['ticker']} · change vs previous close; "
                         f"sparkline = last 24h",
                )
                st.markdown(f"<div class='unit-note'>{unit_of(meta)}</div>",
                            unsafe_allow_html=True)


run_every = {"30s": 30, "1m": 60, "2m": 120, "5m": 300}[every] if auto else None
with st.spinner("Fetching live prices…"):
    st.fragment(run_every=run_every)(live_tiles)()

st.divider()

# --------------------------------------------------------------------------------------
# Growth section
# --------------------------------------------------------------------------------------
st.subheader("📊 Growth")
if CUR == "INR":
    st.caption("Growth in INR includes the rupee's move against the dollar.")
daily_all = daily_data(SEL_TICKERS)

growth_rows = []
for name in selected:
    df = daily_all.get(METALS[name]["ticker"])
    if df is None:
        continue
    close = df["Close"]
    row = {"Metal": name, "Price": float(close.iloc[-1]), "Unit": unit_of(METALS[name])}
    for label, lb in GROWTH_PERIODS.items():
        row[label] = pct_change_over(close, lb)
    growth_rows.append(row)
growth = pd.DataFrame(growth_rows)

if growth.empty:
    st.warning("Couldn't load historical data right now. Try refreshing in a minute.")
else:
    g_period = st.segmented_control(
        "Growth period", list(GROWTH_PERIODS), default="1 Month", key="growth_period",
    ) or "1 Month"

    left, right = st.columns([3, 2], gap="large")
    with left:
        gdf = growth[["Metal", g_period]].dropna().sort_values(g_period)
        fig = go.Figure(go.Bar(
            x=gdf[g_period],
            y=gdf["Metal"],
            orientation="h",
            marker=dict(color=[COLOR[m] for m in gdf["Metal"]], cornerradius=4),
            text=[f"{v:+.2f}%" for v in gdf[g_period]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>" + g_period + ": %{x:+.2f}%<extra></extra>",
        ))
        base_layout(fig, height=max(260, 56 * len(gdf) + 60), money=False)
        fig.update_layout(
            hovermode="closest",
            title=dict(text=f"{g_period} change (%) in {CUR}", font=dict(size=14)),
            xaxis=dict(showgrid=True, zeroline=True, zerolinewidth=1, ticksuffix="%"),
            yaxis=dict(side="left", showgrid=False),
            showlegend=False,
        )
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)

    with right:
        st.markdown("**All periods at a glance**")

        def _color(v):
            if pd.isna(v):
                return ""
            return f"color: {UP[MODE] if v >= 0 else DOWN}; font-weight: 600"

        table = growth.set_index("Metal")
        styled = table.style.map(_color, subset=list(GROWTH_PERIODS)).format(
            {"Price": fmt_price, **{k: "{:+.2f}%" for k in GROWTH_PERIODS}},
            na_rep="—",
        )
        st.dataframe(styled, width="stretch")
        st.caption("Green = gain, red = loss. Week = 7 days, Month = 30 days, Year = 365 days.")

st.divider()

# --------------------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------------------
tab_price, tab_compare, tab_data = st.tabs(["📈 Price chart", "⚖️ Compare", "📋 Data"])

with tab_price:
    c1, c2 = st.columns([1, 1])
    with c1:
        metal = st.selectbox("Metal", selected, key="price_metal")
    with c2:
        ctype = st.segmented_control("Chart style", ["Line", "Area", "Candles"], default="Area",
                                     key="ctype") or "Area"
    rng = st.segmented_control("Range", list(RANGES), default="1M", key="price_range") or "1M"

    meta = METALS[metal]
    data = get_range((meta["ticker"],), rng).get(meta["ticker"])
    if data is None or data.empty:
        st.warning(f"No {rng} data available for {metal} right now.")
    else:
        first, last = float(data["Close"].iloc[0]), float(data["Close"].iloc[-1])
        hi, lo = float(data["High"].max()), float(data["Low"].min())
        chg_pct = (last / first - 1) * 100
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Last", fmt_price(last))
        s2.metric(f"{rng} change", f"{chg_pct:+.2f}%", delta=fmt_delta(last - first, last))
        s3.metric(f"{rng} high", fmt_price(hi))
        s4.metric(f"{rng} low", fmt_price(lo))

        color = COLOR[metal]
        hover_fmt = axis_fmt(last).replace(",.0f", ",.2f")
        fig = go.Figure()
        if ctype == "Candles":
            fig.add_trace(go.Candlestick(
                x=data.index, open=data["Open"], high=data["High"], low=data["Low"],
                close=data["Close"], name=metal,
                increasing=dict(line=dict(color=UP[MODE], width=1), fillcolor=UP[MODE]),
                decreasing=dict(line=dict(color=DOWN, width=1), fillcolor=DOWN),
            ))
            fig.update_layout(xaxis_rangeslider_visible=False)
        else:
            fig.add_trace(go.Scatter(
                x=data.index, y=data["Close"], name=metal, mode="lines",
                line=dict(color=color, width=2),
                fill="tozeroy" if ctype == "Area" else None,
                fillcolor=color + "22",
                hovertemplate=SYM + "%{y:" + hover_fmt + "}<extra>" + metal + "</extra>",
            ))
            pad = (hi - lo) * 0.08 or last * 0.01
            fig.update_yaxes(range=[lo - pad, hi + pad])
        base_layout(fig, ref=last)
        fig.update_layout(title=dict(text=f"{metal} · {unit_of(meta)} · {rng}",
                                     font=dict(size=14)), showlegend=False)
        # Hide weekend gaps on futures charts
        if rng != "5Y":
            fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)

with tab_compare:
    st.markdown("Every metal rebased to **100** at the start of the range, so you can compare "
                f"relative performance (in {CUR}) on one scale.")
    crng = st.segmented_control("Range", list(RANGES)[1:], default="1Y", key="cmp_range") or "1Y"
    cdata = get_range(SEL_TICKERS, crng)
    fig = go.Figure()
    end_vals = []
    for name in selected:
        df = cdata.get(METALS[name]["ticker"])
        if df is None or df.empty:
            continue
        idx = df["Close"] / float(df["Close"].iloc[0]) * 100
        end_vals.append((name, float(idx.iloc[-1])))
        fig.add_trace(go.Scatter(
            x=idx.index, y=idx, name=name, mode="lines",
            line=dict(color=COLOR[name], width=2),
            hovertemplate="%{y:.1f}<extra>" + name + "</extra>",
        ))
    if not fig.data:
        st.warning("No comparison data available right now.")
    else:
        fig.add_hline(y=100, line=dict(color=MUTED, width=1, dash="dot"))
        base_layout(fig, height=460, money=False)
        fig.update_layout(title=dict(text=f"Indexed performance · {crng} (start = 100)",
                                     font=dict(size=14)))
        if crng != "5Y":
            fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
        ranked = sorted(end_vals, key=lambda x: x[1], reverse=True)
        st.caption("**Ranking:** " + " · ".join(f"{n} {v - 100:+.1f}%" for n, v in ranked))

with tab_data:
    st.markdown(f"**Daily closing prices ({CUR})**, last 5 years")
    closes = pd.DataFrame({
        f"{name} ({unit_of(METALS[name])})": daily_all[METALS[name]["ticker"]]["Close"]
        for name in selected if METALS[name]["ticker"] in daily_all
    }).sort_index(ascending=False)
    closes.index = closes.index.date
    closes.index.name = "Date"
    st.dataframe(closes.round(2 if CUR == "INR" else 4), width="stretch", height=420)
    st.download_button(
        "⬇️ Download CSV", closes.to_csv().encode(),
        file_name=f"metals_daily_closes_{CUR.lower()}.csv", mime="text/csv",
    )
