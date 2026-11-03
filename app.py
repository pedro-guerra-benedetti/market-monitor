"""
Market monitor - US, B3 (Brazil) and Oslo Børs
Data: Yahoo Finance via yfinance (free, unofficial, ~15 min delayed)

Run:
    pip install -r requirements.txt
    streamlit run app.py
"""

from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Market monitor", page_icon="📈", layout="wide")

# ---------- Settings you can change ----------

DEFAULT_WATCHLIST = {
    "US": "SPY, QQQ, DIA, IWM, "
          "AAPL, MSFT, NVDA, AVGO, ORCL, AMD, CRM, "
          "GOOGL, META, NFLX, DIS, "
          "AMZN, TSLA, MCD, HD, "
          "WMT, COST, PG, KO, PEP, "
          "BRK-B, JPM, V, MA, BAC, GS, "
          "LLY, UNH, JNJ, ABBV, MRK, "
          "XOM, CVX, CAT, GE, BA, NEE, LIN",
    "B3": "^BVSP, "
          "ITUB4.SA, BBAS3.SA, BBDC4.SA, SANB11.SA, BPAC11.SA, B3SA3.SA, ITSA4.SA, BBSE3.SA, "
          "CXSE3.SA, HAPV3.SA, "
          "PETR4.SA, PRIO3.SA, UGPA3.SA, CSAN3.SA, "
          "VALE3.SA, SUZB3.SA, KLBN11.SA, GGBR4.SA, CSNA3.SA, "
          "AXIA3.SA, SBSP3.SA, CMIG4.SA, EQTL3.SA, CPLE3.SA, EGIE3.SA, "
          "ABEV3.SA, MBRF3.SA, RADL3.SA, RDOR3.SA, HYPE3.SA, "
          "LREN3.SA, MGLU3.SA, VBBR3.SA, RENT3.SA, "
          "WEGE3.SA, EMBJ3.SA, TOTS3.SA",
    "Oslo": "OSEBX.OL, "
            "EQNR.OL, AKRBP.OL, VAR.OL, SUBC.OL, AKSO.OL, TGS.OL, BWLPG.OL, "
            "DNB.OL, STB.OL, GJF.OL, PROT.OL, "
            "MOWI.OL, SALM.OL, BAKKA.OL, LSG.OL, ORK.OL, "
            "KOG.OL, AKER.OL, TOM.OL, AUTO.OL, AFG.OL, NEL.OL, NAS.OL, "
            "FRO.OL, HAFNI.OL, WAWI.OL, MPCC.OL, "
            "NHY.OL, YAR.OL, ELK.OL, "
            "TEL.OL, VEND.OL, NOD.OL, KIT.OL, ENTRA.OL",
}

# Hover text for every indicator: what it is, and why it matters
HELP = {
    "Ticker": "The stock's symbol on Yahoo Finance. .SA = B3 (Brazil), .OL = Oslo Børs, ^ = index.",
    "Company": "Company name as registered on the exchange.",
    "Sector": "Broad business area (e.g. Energy, Technology). Stocks in the same sector tend to "
              "move together, so compare a stock with its sector peers, not the whole market.",
    "Industry": "Narrower business area within the sector. Best basis for peer comparison.",
    "Price": "Last closing price in the currency the stock trades in.",
    "Converted price": "Last price converted at today's exchange rate. Useful to compare what a "
                       "share costs across markets; indices are points, not money, so not converted.",
    "1D %": "Change since the previous close. Shows today's momentum and flags news-driven moves.",
    "1W %": "Change over the last 7 days. Separates a one-day blip from a short-term trend.",
    "1M %": "Change over the last month. Short-term trend.",
    "YTD %": "Change since the last close of the previous year. The standard way to compare "
             "how investments are doing this year.",
    "1Y %": "Change over the last 12 months, including dividends reinvested (adjusted prices). "
            "Long enough to smooth out noise.",
    "From 52w high %": "How far the price is below its highest close in the last year. Near 0% means "
                       "trading at the top of its range; a deep negative means a big pullback - "
                       "either a bargain or a sign of trouble.",
    "Market cap": "Share price x number of shares: what the market values the whole company at. "
                  "Bigger companies are usually more stable; smaller ones can grow (and fall) faster.",
    "Volume": "Shares traded on the last day. Unusually high volume means something is happening "
              "and that the price move has conviction behind it.",
    "Date": "Date of the last price.",
    "P/E": "Price / earnings per share over the last 12 months. How many years of current profit you "
           "pay for. Lower can mean cheap (or a business in decline), higher means investors expect "
           "growth. Compare within the same industry.",
    "Fwd P/E": "Price / analysts' expected earnings for the next 12 months. Lower than P/E means "
               "profits are expected to grow.",
    "P/B": "Price / book value (assets minus debts) per share. Below 1 means you pay less than the "
           "accounting value of the company. Most useful for banks, insurers and asset-heavy firms.",
    "P/S": "Price / revenue per share. Works even when the company has no profit, so it is handy for "
           "growth companies. Margins differ by industry, so compare peers.",
    "EV/EBITDA": "Company value including debt / operating profit before depreciation. Like P/E but "
                 "neutral to how the company is financed, so better for comparing firms with "
                 "different debt levels. Below ~8 is often considered cheap. Not meaningful for banks.",
    "Div yield %": "Annual dividend / price. The cash return you get just for holding the share. Very "
                   "high yields (10%+) can signal the market expects a dividend cut.",
    "Profit margin %": "Net profit / revenue. How much of each sale the company keeps. Higher margins "
                       "usually mean pricing power and more room to absorb bad years.",
    "ROE %": "Return on equity: net profit / shareholders' equity. How well the company turns "
             "shareholders' money into profit. Above ~15% is generally strong.",
    "Beta": "How much the stock moves versus the overall market. 1 = moves with the market, "
            "above 1 = swings more, below 1 = calmer, negative = tends to move the opposite way.",
    "EPS (ttm)": "Earnings per share: net profit over the last 12 months divided by the number of "
                 "shares. The profit each share 'owns'. Growing EPS over time is what drives share "
                 "prices up in the long run.",
    "EPS (fwd)": "Analysts' expected earnings per share for the next 12 months. Higher than EPS (ttm) "
                 "means profit growth is expected.",
    "Book value": "Equity per share: what each share would get if the company sold all its assets "
                  "and paid all its debts, at accounting values. A floor for valuing banks and "
                  "asset-heavy companies.",
    "Revenue": "Sales per share over the last 12 months. Shows the size of the business behind each "
               "share; the base for P/S.",
    "Cash": "Cash and short-term investments per share. A cushion for bad times, buybacks or "
            "acquisitions; compare with the share price.",
    "Dividend": "Expected annual dividend paid per share, in the trading currency.",
    "Analyst target": "Average 12-month price target from the analysts covering the stock. An "
                      "opinion, not a forecast you can rely on, but shows market sentiment.",
    "Upside %": "Distance from today's price to the analyst target. Positive = analysts think the "
                "stock can rise.",
    "Rating": "Analysts' consensus recommendation (strong buy to sell).",
}

SECTOR_SUMMARY_HELP = {
    "Stocks": "Number of stocks from your watchlist in this sector.",
    "Avg 1D %": "Average one-day change of the stocks in this sector.",
    "Avg 1M %": "Average one-month change of the stocks in this sector.",
    "Avg YTD %": "Average year-to-date change of the stocks in this sector.",
    "Median P/E": "Typical P/E in this sector. Use it as the benchmark when judging whether a single "
                  "stock's P/E is high or low.",
    "Median yield %": "Typical dividend yield in this sector.",
}
MARKET_CURRENCY = {"US": "USD", "B3": "BRL", "Oslo": "NOK"}

# Columns shown in each table view
VIEWS = {
    "Overview": ["Ticker", "Company", "Sector", "Price", "1D %", "1W %", "1M %", "YTD %", "1Y %",
                 "From 52w high %", "Market cap", "Volume", "Date"],
    "Valuation": ["Ticker", "Company", "Price", "P/E", "Fwd P/E", "P/B", "P/S", "EV/EBITDA",
                  "Div yield %", "Profit margin %", "ROE %", "Beta"],
    "Per share": ["Ticker", "Company", "Price", "EPS (ttm)", "EPS (fwd)", "Book value",
                  "Revenue", "Cash", "Dividend", "Analyst target", "Upside %", "Rating"],
}
PCT_COLS = ["1D %", "1W %", "1M %", "YTD %", "1Y %", "From 52w high %", "Div yield %",
            "Profit margin %", "ROE %", "Upside %"]
COLORED_COLS = ["1D %", "1W %", "1M %", "YTD %", "1Y %", "Upside %"]
MONEY_COLS = ["Price", "EPS (ttm)", "EPS (fwd)", "Book value", "Revenue", "Cash", "Dividend",
              "Analyst target"]
RATIO_COLS = ["P/E", "Fwd P/E", "P/B", "P/S", "EV/EBITDA", "Beta"]


# ---------- Data ----------

def _fetch_info(ticker: str) -> dict:
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}


@st.cache_data(ttl=86400)  # fundamentals change slowly, keep them for a day
def get_infos(tickers: tuple) -> dict:
    with ThreadPoolExecutor(max_workers=10) as pool:
        return dict(zip(tickers, pool.map(_fetch_info, tickers)))


@st.cache_data(ttl=300)  # reuse prices for 5 minutes, avoids hammering Yahoo
def get_prices(tickers: tuple) -> dict:
    """One year of daily closes and volumes per ticker, in a single download."""
    if not tickers:
        return {}
    data = yf.download(list(tickers), period="1y", progress=False, auto_adjust=True, threads=True)
    out = {}
    for t in tickers:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                close, volume = data["Close"][t], data["Volume"][t]
            else:
                close, volume = data["Close"], data["Volume"]
            close = close.dropna()
            out[t] = {"close": close, "volume": volume.reindex(close.index)}
        except Exception:
            out[t] = {"close": pd.Series(dtype=float), "volume": pd.Series(dtype=float)}
    return out


@st.cache_data(ttl=900)
def nok_per(currency: str):
    """NOK for 1 unit of a currency. Lets us convert anything via NOK."""
    if not currency or currency == "NOK":
        return 1.0
    try:
        closes = yf.Ticker(f"{currency}NOK=X").history(period="5d")["Close"].dropna()
        return float(closes.iloc[-1])
    except Exception:
        return None


@st.cache_data(ttl=900)
def get_history(ticker: str, period: str) -> pd.Series:
    return yf.Ticker(ticker).history(period=period)["Close"].dropna()


def convert(amount, from_cur, to_cur):
    if amount is None or pd.isna(amount):
        return None
    a, b = nok_per(from_cur), nok_per(to_cur)
    if not a or not b:
        return None
    return amount * a / b


def pct_return(close: pd.Series, since) -> float | None:
    """% change from the last close on or before `since` to the latest close."""
    past = close[close.index <= since]
    if past.empty:
        return None
    return (close.iloc[-1] / past.iloc[-1] - 1) * 100


def is_index(ticker: str, info: dict) -> bool:
    return ticker.startswith("^") or info.get("quoteType") == "INDEX"


def build_row(ticker: str, info: dict, prices: dict) -> dict:
    close, volume = prices["close"], prices["volume"]
    cur = info.get("currency")
    fin_cur = info.get("financialCurrency") or cur

    # Yahoo gives revenue and cash per share in the reporting currency (e.g. USD for Equinor),
    # while price, EPS, book value and dividend are in the trading currency (NOK).
    def to_trading(v):
        return v if fin_cur == cur else convert(v, fin_cur, cur)

    sector = info.get("sector") or ""
    if not sector:
        sector = "Index" if is_index(ticker, info) else "ETF" if info.get("quoteType") == "ETF" else ""

    row = {
        "Ticker": ticker,
        "Company": info.get("longName") or info.get("shortName") or "",
        "Sector": sector,
        "Industry": info.get("industry") or "",
    }

    if len(close) >= 2:
        last, date = float(close.iloc[-1]), close.index[-1]
        high = float(close.max())
        row.update({
            "Price": last,
            "1D %": (last / close.iloc[-2] - 1) * 100,
            "1W %": pct_return(close, date - pd.Timedelta(days=7)),
            "1M %": pct_return(close, date - pd.DateOffset(months=1)),
            "YTD %": pct_return(close, pd.Timestamp(date.year, 1, 1, tz=date.tz) - pd.Timedelta(days=1)),
            "1Y %": (last / close.iloc[0] - 1) * 100,
            "From 52w high %": (last / high - 1) * 100,
            "52w high": high,
            "52w low": float(close.min()),
            "Volume": volume.iloc[-1] if not pd.isna(volume.iloc[-1]) else None,
            "Date": date.strftime("%d %b"),
        })
    else:
        last = None
        row.update({"Price": None, "Date": "no data"})

    revenue_ps = to_trading(info.get("revenuePerShare"))
    dividend = info.get("dividendRate")
    target = info.get("targetMeanPrice")
    ev_ebitda = info.get("enterpriseToEbitda")
    if ev_ebitda is not None and fin_cur != cur:  # EV in trading currency, EBITDA in reporting
        ev_ebitda = convert(ev_ebitda, cur, fin_cur)

    def pct(v):
        return v * 100 if v is not None else None

    row.update({
        "Market cap": info.get("marketCap"),
        "Avg volume": info.get("averageVolume"),
        "P/E": info.get("trailingPE"),
        "Fwd P/E": info.get("forwardPE"),
        "P/B": info.get("priceToBook"),
        "P/S": last / revenue_ps if last and revenue_ps else None,
        "EV/EBITDA": ev_ebitda,
        "Div yield %": dividend / last * 100 if last and dividend else None,
        "Profit margin %": pct(info.get("profitMargins")),
        "ROE %": pct(info.get("returnOnEquity")),
        "Beta": info.get("beta"),
        "EPS (ttm)": info.get("trailingEps"),
        "EPS (fwd)": info.get("forwardEps"),
        "Book value": info.get("bookValue"),
        "Revenue": revenue_ps,
        "Cash": to_trading(info.get("totalCashPerShare")),
        "Dividend": dividend,
        "Analyst target": target,
        "Upside %": (target / last - 1) * 100 if last and target else None,
        "Rating": (info.get("recommendationKey") or "").replace("_", " ").replace("none", ""),
        "Analysts": info.get("numberOfAnalystOpinions"),
    })
    return row


def get_table(tickers: tuple) -> pd.DataFrame:
    infos, prices = get_infos(tickers), get_prices(tickers)
    return pd.DataFrame([build_row(t, infos[t], prices[t]) for t in tickers])


def parse_tickers(text: str) -> tuple:
    return tuple(dict.fromkeys(t.strip().upper() for t in text.split(",") if t.strip()))


def human(n):
    if n is None or pd.isna(n):
        return "-"
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= size:
            return f"{n / size:,.1f}{unit}"
    return f"{n:,.0f}"


def color_change(value):
    if value is None or pd.isna(value):
        return ""
    return "color: #1a9850" if value > 0 else "color: #d73027" if value < 0 else ""


# ---------- Sidebar ----------

st.sidebar.header("Watchlist")
watchlist = {
    market: parse_tickers(st.sidebar.text_area(f"{market} tickers", default, height=90))
    for market, default in DEFAULT_WATCHLIST.items()
}
st.sidebar.caption("Comma separated. B3 tickers end in .SA, Oslo in .OL. Indices start with ^.")

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

usd_nok, brl_nok = nok_per("USD"), nok_per("BRL")
if usd_nok and brl_nok:
    st.caption(
        f"1 USD = {usd_nok:.3f} NOK  ·  1 USD = {usd_nok / brl_nok:.3f} BRL  ·  "
        f"1 BRL = {brl_nok:.3f} NOK"
    )

with st.spinner("Loading quotes and fundamentals (first load takes a little while)..."):
    tables = {market: get_table(tickers) for market, tickers in watchlist.items()}

# Alerts across all markets
alerts = []
for market, df in tables.items():
    for _, row in df.iterrows():
        chg = row.get("1D %")
        if chg is not None and not pd.isna(chg) and abs(chg) >= threshold:
            label = f"{row['Company']} ({row['Ticker']})" if row["Company"] else row["Ticker"]
            alerts.append(f"{label}, {market}: {chg:+.2f}%")
if alerts:
    st.warning("Big moves today: " + "  |  ".join(alerts))
else:
    st.success(f"Nothing moved more than {threshold:.1f}% today.")

view = st.radio("Show", list(VIEWS), horizontal=True, key="view")
st.caption("Hover over a column name to see what the indicator means and why it matters.")
if view == "Per share":
    st.caption("Per-share figures in the trading currency. Revenue and cash are per share, "
               "dividend is the annual rate, target is the analysts' mean price.")

FUND_TYPES = ("Index", "ETF")  # shown first, they are benchmarks rather than companies


def sector_order(df: pd.DataFrame) -> list:
    counts = df["Sector"].value_counts()
    funds = [s for s in FUND_TYPES if s in counts]
    rest = [s for s in counts.index if s not in FUND_TYPES]  # biggest sectors first
    return funds + rest


def render_table(df: pd.DataFrame, currency: str, key: str):
    cols = [c for c in VIEWS[view] if c in df.columns]
    if "Industry" not in cols and view == "Overview":
        cols.insert(cols.index("Sector") + 1, "Industry")
    table = df[cols].copy()

    fmt = {c: "{:+.2f}%" for c in PCT_COLS if c in cols}
    fmt.update({c: "{:,.2f}" for c in MONEY_COLS if c in cols})
    fmt.update({c: "{:.1f}" for c in RATIO_COLS if c in cols})
    fmt.update({c: human for c in ("Market cap", "Volume") if c in cols})
    for c in ("Div yield %", "Profit margin %", "ROE %"):
        if c in cols:
            fmt[c] = "{:.1f}%"

    help_text = {c: HELP.get(c) for c in cols}

    target = display_currency
    if target not in ("Local only", currency):
        col = f"Price ({target})"
        table.insert(cols.index("Price") + 1, col, [
            None if s == "Index" else convert(p, currency, target)
            for s, p in zip(df["Sector"], df["Price"])
        ])
        fmt[col] = "{:,.2f}"
        help_text[col] = HELP["Converted price"]

    price_col = f"Price ({currency})"
    table = table.rename(columns={"Price": price_col})
    fmt[price_col] = fmt.pop("Price")
    help_text[price_col] = help_text.pop("Price")

    styled = table.style.format(fmt, na_rep="-").map(
        color_change, subset=[c for c in COLORED_COLS if c in table.columns]
    )
    st.dataframe(
        styled, hide_index=True, width="stretch", key=key,
        column_config={c: st.column_config.Column(help=h) for c, h in help_text.items() if h},
    )


def sector_summary(df: pd.DataFrame, sectors: list) -> pd.DataFrame:
    rows = []
    for s in sectors:
        sub = df[df["Sector"] == s]
        rows.append({
            "Sector": s,
            "Stocks": len(sub),
            "Avg 1D %": sub["1D %"].mean(),
            "Avg 1M %": sub["1M %"].mean(),
            "Avg YTD %": sub["YTD %"].mean(),
            "Median P/E": sub["P/E"].median(),
            "Median yield %": sub["Div yield %"].median(),
        })
    return pd.DataFrame(rows)


# One tab per market
tabs = st.tabs(list(tables))
for tab, (market, df) in zip(tabs, tables.items()):
    with tab:
        currency = MARKET_CURRENCY[market]
        df = df.assign(Sector=df["Sector"].replace("", "Other"))
        df = df.sort_values("Market cap", ascending=False, na_position="first")
        all_sectors = sector_order(df)

        c1, c2 = st.columns([4, 1])
        chosen = c1.multiselect(
            "Sectors", all_sectors, placeholder="All sectors", key=f"sectors_{market}",
            help="Pick one or more sectors to narrow the list. Leave empty to show all.",
        ) or all_sectors
        grouped = c2.toggle("Group by sector", value=True, key=f"group_{market}",
                            help="Show one table per sector, so you compare each stock with its peers.")

        companies = [s for s in chosen if s not in FUND_TYPES]
        if companies:
            with st.expander("Sector summary", expanded=False):
                summary = sector_summary(df, companies)
                st.dataframe(
                    summary.style.format({
                        "Avg 1D %": "{:+.2f}%", "Avg 1M %": "{:+.2f}%", "Avg YTD %": "{:+.2f}%",
                        "Median P/E": "{:.1f}", "Median yield %": "{:.1f}%",
                    }, na_rep="-").map(color_change, subset=["Avg 1D %", "Avg 1M %", "Avg YTD %"]),
                    hide_index=True, width="stretch", key=f"summary_{market}",
                    column_config={c: st.column_config.Column(help=h)
                                   for c, h in SECTOR_SUMMARY_HELP.items()},
                )

        if grouped:
            for s in chosen:
                sub = df[df["Sector"] == s]
                avg = sub["1D %"].mean()
                today = f" · avg today {avg:+.2f}%" if pd.notna(avg) else ""
                st.markdown(f"**{s}** · {len(sub)} {'item' if len(sub) == 1 else 'items'}{today}")
                render_table(sub, currency, key=f"table_{market}_{s}")
        else:
            render_table(df[df["Sector"].isin(chosen)], currency, key=f"table_{market}")

# ---------- Single stock detail ----------

st.subheader("Stock detail")
all_rows = {r["Ticker"]: (market, r) for market, df in tables.items() for _, r in df.iterrows()}
col1, col2 = st.columns([2, 1])
selected = col1.selectbox(
    "Ticker", list(all_rows),
    format_func=lambda t: f"{t} - {all_rows[t][1]['Company']}" if all_rows[t][1]["Company"] else t,
)
period = col2.radio("Period", ["1mo", "6mo", "1y", "5y", "max"], index=2, horizontal=True)

if selected:
    market, r = all_rows[selected]
    info = get_infos(watchlist[market])[selected]
    cur = info.get("currency") or MARKET_CURRENCY[market]

    def val(key, fmt="{:,.2f}", suffix=""):
        v = r.get(key)
        return "-" if v is None or pd.isna(v) else fmt.format(v) + suffix

    st.caption(" · ".join(x for x in (r["Company"], r["Sector"], r["Industry"],
                                      info.get("country")) if x))

    m = st.columns(5)
    m[0].metric(f"Price ({cur})", val("Price"), val("1D %", "{:+.2f}", "%"),
                help=HELP["Price"] + " Arrow: " + HELP["1D %"])
    m[1].metric("1 month", val("1M %", "{:+.1f}", "%"), help=HELP["1M %"])
    m[2].metric("Year to date", val("YTD %", "{:+.1f}", "%"), help=HELP["YTD %"])
    m[3].metric("1 year", val("1Y %", "{:+.1f}", "%"), help=HELP["1Y %"])
    m[4].metric("52w range", f"{val('52w low')} – {val('52w high')}",
                help="Lowest and highest close over the last year. Shows where today's price sits "
                     "in its recent range.")

    m = st.columns(5)
    m[0].metric("Market cap", human(r.get("Market cap")), help=HELP["Market cap"])
    m[1].metric("P/E (fwd)", f"{val('P/E', '{:.1f}')} ({val('Fwd P/E', '{:.1f}')})",
                help=HELP["P/E"] + "\n\nIn brackets: " + HELP["Fwd P/E"])
    m[2].metric("Dividend / yield", f"{val('Dividend')} / {val('Div yield %', '{:.1f}', '%')}",
                help=HELP["Dividend"] + "\n\n" + HELP["Div yield %"])
    m[3].metric("EPS ttm (fwd)", f"{val('EPS (ttm)')} ({val('EPS (fwd)')})",
                help=HELP["EPS (ttm)"] + "\n\nIn brackets: " + HELP["EPS (fwd)"])
    analysts = r.get("Analysts")
    coverage = (f"\n\nConsensus: {r['Rating'] or 'no rating'}, {int(analysts)} analysts."
                if analysts and pd.notna(analysts) else "")
    m[4].metric(
        "Analyst target", val("Analyst target"),
        val("Upside %", "{:+.1f}", "% upside") if pd.notna(r.get("Upside %")) else None,
        help=HELP["Analyst target"] + coverage,
    )

    history = get_history(selected, period)
    if history.empty:
        st.info("No history found for this ticker.")
    else:
        change = (history.iloc[-1] / history.iloc[0] - 1) * 100
        st.caption(f"{change:+.1f}% over {period}")
        st.line_chart(history, height=350)

    with st.expander("More about this company"):
        facts = {
            "Industry": info.get("industry"),
            "Country": info.get("country"),
            "Employees": f"{info['fullTimeEmployees']:,}" if info.get("fullTimeEmployees") else None,
            "Website": info.get("website"),
            "Reporting currency": info.get("financialCurrency"),
            "Avg daily volume": human(r.get("Avg volume")) if r.get("Avg volume") else None,
            "Beta": val("Beta", "{:.2f}"),
            "Profit margin": val("Profit margin %", "{:.1f}", "%"),
            "Return on equity": val("ROE %", "{:.1f}", "%"),
            "Book value / share": val("Book value"),
            "Revenue / share": val("Revenue"),
            "Cash / share": val("Cash"),
        }
        st.table(pd.DataFrame(
            [(k, v) for k, v in facts.items() if v and v != "-"], columns=["", "Value"]
        ).set_index(""))
        if info.get("longBusinessSummary"):
            st.write(info["longBusinessSummary"])

# ---------- Glossary ----------

with st.expander("What do these indicators mean?"):
    skip = {"Ticker", "Company", "Date", "Converted price"}
    for name, text in HELP.items():
        if name not in skip:
            st.markdown(f"**{name}** - {text}")
