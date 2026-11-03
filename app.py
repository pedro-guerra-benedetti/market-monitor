"""
Market monitor - US, B3 (Brazil) and Oslo Børs
Data: Yahoo Finance via yfinance (free, unofficial, ~15 min delayed)

Run:
    pip install -r requirements.txt
    streamlit run app.py
"""

import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Market monitor", page_icon="📈", layout="wide")

# ---------- Settings you can change ----------

DEFAULT_WATCHLIST = {
    "US": "SPY, AAPL, MSFT, NVDA, AMZN",
    "B3": "^BVSP, PETR4.SA, VALE3.SA, ITUB4.SA, BBAS3.SA",
    "Oslo": "EQNR.OL, DNB.OL, NHY.OL, MOWI.OL, KOG.OL",
}
MARKET_CURRENCY = {"US": "USD", "B3": "BRL", "Oslo": "NOK"}
FX_TICKERS = {"USD": "USDNOK=X", "BRL": "BRLNOK=X"}  # price of 1 unit in NOK


# ---------- Data ----------

@st.cache_data(ttl=86400)  # names and sectors rarely change, so keep them for a day
def get_info(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}
    name = info.get("longName") or info.get("shortName") or ""  # B3 short names are cryptic
    sector = info.get("sector") or ""
    if not sector:
        if ticker.startswith("^"):
            sector = "Index"
        elif info.get("quoteType") == "ETF":
            sector = "ETF"
    return {"Company": name, "Sector": sector}


@st.cache_data(ttl=300)  # reuse data for 5 minutes, avoids hammering Yahoo
def get_quotes(tickers: tuple) -> pd.DataFrame:
    rows = []
    for t in tickers:
        info = get_info(t)
        try:
            closes = yf.Ticker(t).history(period="5d")["Close"].dropna()
            if len(closes) < 2:
                raise ValueError("not enough data")
            last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
            rows.append({
                "Ticker": t,
                **info,
                "Price": last,
                "Change %": (last / prev - 1) * 100,
                "Date": closes.index[-1].strftime("%d %b"),
            })
        except Exception:
            rows.append({"Ticker": t, **info, "Price": None, "Change %": None, "Date": "no data"})
    return pd.DataFrame(rows)


@st.cache_data(ttl=900)
def get_fx() -> dict:
    rates = {"NOK": 1.0}
    for cur, t in FX_TICKERS.items():
        try:
            closes = yf.Ticker(t).history(period="5d")["Close"].dropna()
            rates[cur] = float(closes.iloc[-1])
        except Exception:
            rates[cur] = None
    return rates


@st.cache_data(ttl=900)
def get_history(ticker: str, period: str) -> pd.Series:
    return yf.Ticker(ticker).history(period=period)["Close"].dropna()


def parse_tickers(text: str) -> tuple:
    return tuple(t.strip().upper() for t in text.split(",") if t.strip())


def color_change(value):
    if value is None or pd.isna(value):
        return ""
    return "color: #1a9850" if value > 0 else "color: #d73027" if value < 0 else ""


# ---------- Sidebar ----------

st.sidebar.header("Watchlist")
watchlist = {
    market: parse_tickers(st.sidebar.text_input(f"{market} tickers", default))
    for market, default in DEFAULT_WATCHLIST.items()
}
st.sidebar.caption("B3 tickers end in .SA, Oslo in .OL. Indices start with ^.")

display_currency = st.sidebar.radio(
    "Also show prices in", ["Local only", "NOK", "USD", "BRL"], index=1, horizontal=True
)
threshold = st.sidebar.slider("Alert when a stock moves more than (%)", 1.0, 10.0, 3.0, 0.5)

if st.sidebar.button("Refresh now"):
    st.cache_data.clear()
    st.rerun()


# ---------- Main ----------

st.title("📈 Market monitor")
st.caption("Yahoo Finance data, delayed ~15 min. For monitoring, not trading decisions.")

fx = get_fx()  # NOK per 1 unit of each currency


def convert(amount, from_cur, to_cur):
    """Convert via NOK, so we only need two FX tickers for all three currencies."""
    if amount is None or pd.isna(amount) or not fx.get(from_cur) or not fx.get(to_cur):
        return None
    return amount * fx[from_cur] / fx[to_cur]


if fx.get("USD") and fx.get("BRL"):
    st.caption(
        f"1 USD = {convert(1, 'USD', 'NOK'):.3f} NOK  ·  "
        f"1 USD = {convert(1, 'USD', 'BRL'):.3f} BRL  ·  "
        f"1 BRL = {convert(1, 'BRL', 'NOK'):.3f} NOK"
    )

quotes = {market: get_quotes(tickers) for market, tickers in watchlist.items()}

# Alerts across all markets
alerts = []
for market, df in quotes.items():
    for _, row in df.iterrows():
        chg = row["Change %"]
        if chg is not None and not pd.isna(chg) and abs(chg) >= threshold:
            label = f"{row['Company']} ({row['Ticker']})" if row["Company"] else row["Ticker"]
            alerts.append(f"{label}, {market}: {chg:+.2f}%")
if alerts:
    st.warning("Big moves today: " + "  |  ".join(alerts))
else:
    st.success(f"Nothing moved more than {threshold:.1f}% today.")

# One tab per market
tabs = st.tabs(list(quotes.keys()))
for tab, (market, df) in zip(tabs, quotes.items()):
    with tab:
        currency = MARKET_CURRENCY[market]
        table = df.copy()

        fmt = {"Price": "{:,.2f}", "Change %": "{:+.2f}%"}
        target = display_currency
        if target != "Local only" and target != currency:
            col = f"Price ({target})"
            # Indices (^) are points, not money, so no conversion
            table[col] = [
                None if t.startswith("^") else convert(p, currency, target)
                for t, p in zip(table["Ticker"], table["Price"])
            ]
            fmt[col] = "{:,.2f}"

        table = table.rename(columns={"Price": f"Price ({currency})"})
        fmt[f"Price ({currency})"] = fmt.pop("Price")

        styled = table.style.format(fmt, na_rep="-").map(color_change, subset=["Change %"])
        st.dataframe(styled, hide_index=True, use_container_width=True)

# Chart
st.subheader("Price history")
all_tickers = [t for tickers in watchlist.values() for t in tickers]
col1, col2 = st.columns([2, 1])
selected = col1.selectbox(
    "Ticker", all_tickers,
    format_func=lambda t: f"{t} - {get_info(t)['Company']}" if get_info(t)["Company"] else t,
)
period = col2.radio("Period", ["1mo", "6mo", "1y", "5y"], index=2, horizontal=True)

if selected:
    history = get_history(selected, period)
    if history.empty:
        st.info("No history found for this ticker.")
    else:
        change = (history.iloc[-1] / history.iloc[0] - 1) * 100
        info = get_info(selected)
        if info["Company"]:
            st.caption(" · ".join(x for x in (info["Company"], info["Sector"]) if x))
        st.metric(selected, f"{history.iloc[-1]:,.2f}", f"{change:+.1f}% over {period}")
        st.line_chart(history, height=350)
