"""
Macro and driver analysis for a single stock.

Rule based: each industry is mapped to the macro series that move it (oil, rates, currencies...),
then today's market data says whether each one is currently a tailwind or a headwind.
Company-specific signals (valuation vs peers, growth, debt, analysts) are added on top.
"""

from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import yfinance as yf

# key: (Yahoo ticker, label, kind, phrase when it rises, phrase when it falls)
# kind: "price" -> change in %, "yield" -> change in basis points
MACRO = {
    "brent": ("BZ=F", "Brent crude oil", "price", "Higher oil prices", "Lower oil prices"),
    "natgas": ("NG=F", "Natural gas (US, proxy for Europe)", "price", "Higher gas prices",
               "Lower gas prices"),
    "gold": ("GC=F", "Gold", "price", "Higher gold prices", "Lower gold prices"),
    "copper": ("HG=F", "Copper (global industry gauge)", "price", "Stronger global industrial demand",
               "Weaker global industrial demand"),
    "aluminium": ("ALI=F", "Aluminium", "price", "Higher aluminium prices", "Lower aluminium prices"),
    "iron": ("TIO=F", "Iron ore", "price", "Higher iron ore prices", "Lower iron ore prices"),
    "soy": ("ZS=F", "Soybeans", "price", "Higher soy (feed) prices", "Lower soy (feed) prices"),
    "corn": ("ZC=F", "Corn", "price", "Higher crop prices", "Lower crop prices"),
    "sugar": ("SB=F", "Sugar", "price", "Higher sugar prices", "Lower sugar prices"),
    "us10y": ("^TNX", "US 10-year yield", "yield", "Rising interest rates", "Falling interest rates"),
    "vix": ("^VIX", "VIX (market fear index)", "price", "Rising market fear", "Calmer markets"),
    "dxy": ("DX-Y.NYB", "US dollar index", "price", "A stronger US dollar", "A weaker US dollar"),
    "usdnok": ("USDNOK=X", "USD/NOK", "price", "A weaker krone vs USD", "A stronger krone vs USD"),
    "eurnok": ("EURNOK=X", "EUR/NOK", "price", "A weaker krone vs EUR", "A stronger krone vs EUR"),
    "usdbrl": ("USDBRL=X", "USD/BRL", "price", "A weaker real vs USD", "A stronger real vs USD"),
    "sp500": ("^GSPC", "S&P 500", "price", "A rising US market", "A falling US market"),
    "ibov": ("^BVSP", "Ibovespa", "price", "A rising Brazilian market", "A falling Brazilian market"),
    "osebx": ("OSEBX.OL", "Oslo Børs (OSEBX)", "price", "A rising Oslo market",
              "A falling Oslo market"),
}
MARKET_INDEX = {"US": "sp500", "B3": "ibov", "Oslo": "osebx"}

# Moves smaller than this over a month count as neutral
NEUTRAL = {"price": 2.0, "yield": 10.0}  # % for prices, basis points for yields

RATES_GROWTH = ("us10y", -1, "Growth companies are valued on profits far in the future; higher "
                             "rates make those future profits worth less today.")
RATES_CONSUMER = ("us10y", -1, "Higher rates raise loan and mortgage costs and leave consumers "
                               "less to spend.")
FEAR_CYCLICAL = ("vix", -1, "When investors get nervous they sell economically sensitive stocks "
                            "first.")
FEAR_DEFENSIVE = ("vix", +1, "Defensive: investors rotate into steady, everyday businesses when "
                             "markets get nervous.")

# (keywords matched against the Yahoo industry, [(macro key, sign, why)])
# sign +1: the stock tends to benefit when the series rises, -1: when it falls.
INDUSTRY_RULES = [
    (("Oil & Gas E&P", "Oil & Gas Integrated", "Oil & Gas Drilling"), [
        ("brent", +1, "Revenue and profit move almost one-for-one with the oil price."),
        ("natgas", +1, "Gas is a large share of output; Norwegian producers sell most of it to "
                       "Europe at European prices (US gas shown as the closest free proxy)."),
    ]),
    (("Oil & Gas Equipment", "Oil & Gas Midstream"), [
        ("brent", +1, "Higher oil prices make producers spend more on projects, rigs, ships and "
                      "services, which fills order books (usually with a delay)."),
        FEAR_CYCLICAL,
    ]),
    (("Oil & Gas Refining",), [
        ("brent", -1, "Crude oil is the main input cost; margins shrink when crude rises faster "
                      "than fuel prices can follow."),
        FEAR_CYCLICAL,
    ]),
    (("Aluminum",), [
        ("aluminium", +1, "Aluminium prices drive revenue; costs (power, alumina) move less."),
        ("copper", +1, "Metal demand follows the global industrial cycle (construction, cars)."),
    ]),
    (("Steel",), [
        ("copper", +1, "Steel demand follows construction and industrial activity."),
        ("iron", -1, "Iron ore is the main raw material, so pricier ore squeezes margins."),
    ]),
    (("Industrial Metals", "Copper", "Other Precious"), [
        ("iron", +1, "Iron ore and base-metal prices drive revenue for miners."),
        ("copper", +1, "Mining demand follows global industry, especially China's construction."),
    ]),
    (("Gold",), [
        ("gold", +1, "Revenue moves with the gold price; costs are mostly fixed."),
        ("us10y", -1, "Gold pays no interest, so it gets less attractive when yields rise."),
    ]),
    (("Agricultural Inputs",), [
        ("natgas", -1, "Gas is the main raw material for nitrogen fertiliser; expensive "
                       "European gas squeezes margins."),
        ("corn", +1, "Higher crop prices let farmers spend more on fertiliser."),
    ]),
    (("Farm Products", "Packaged Foods", "Confectioners"), [
        ("soy", -1, "Feed (soy, grains) is one of the biggest costs for salmon farmers and meat "
                    "producers. Salmon and meat prices themselves matter most but have no free "
                    "data feed."),
        ("corn", -1, "Grain is a key feed and ingredient cost."),
        FEAR_DEFENSIVE,
    ]),
    (("Paper", "Lumber"), [
        ("copper", +1, "Pulp and packaging demand follows global industrial activity. Pulp "
                       "prices themselves have no free data feed."),
    ]),
    (("Marine Shipping",), [
        ("copper", +1, "Freight demand follows global trade and industrial activity."),
        ("brent", -1, "Fuel (bunker) is one of the largest running costs."),
        FEAR_CYCLICAL,
    ]),
    (("Airlines",), [
        ("brent", -1, "Jet fuel is roughly a quarter to a third of airline costs."),
        FEAR_CYCLICAL,
        RATES_CONSUMER,
    ]),
    (("Banks", "Capital Markets", "Credit Services", "Asset Management", "Financial Conglomerates"), [
        ("us10y", +1, "Higher rates usually widen the gap between what banks earn on loans and "
                      "pay on deposits. Very fast hikes can raise loan losses, though."),
        ("vix", -1, "Market stress means more loan losses, fewer deals and lower trading fees."),
    ]),
    (("Insurance",), [
        ("us10y", +1, "Insurers invest premiums in bonds; higher yields lift investment income."),
        ("vix", -1, "Market turmoil hits the value of insurers' investment portfolios."),
    ]),
    (("Semiconductors", "Electronic Components"), [
        RATES_GROWTH,
        ("copper", +1, "Chip demand follows the industrial and electronics cycle."),
        FEAR_CYCLICAL,
    ]),
    (("Software", "Information Technology", "Internet", "Consumer Electronics", "Computer"), [
        RATES_GROWTH,
        FEAR_CYCLICAL,
    ]),
    (("Utilities",), [
        ("us10y", -1, "Utilities are bought for steady dividends that compete with bond yields, "
                      "and they carry a lot of debt, so higher rates hurt twice."),
        FEAR_DEFENSIVE,
    ]),
    (("REIT", "Real Estate"), [
        ("us10y", -1, "Property values and financing costs both depend on interest rates."),
    ]),
    (("Beverages",), [
        ("sugar", -1, "Sugar is a key ingredient cost."),
        FEAR_DEFENSIVE,
    ]),
    (("Household", "Discount Stores", "Tobacco", "Grocery", "Pharmaceutical Retailers"), [
        FEAR_DEFENSIVE,
        RATES_CONSUMER,
    ]),
    (("Restaurants", "Retail", "Department Stores", "Home Improvement", "Auto", "Travel",
      "Leisure", "Apparel", "Rental"), [
        RATES_CONSUMER,
        FEAR_CYCLICAL,
    ]),
    (("Aerospace & Defense",), [
        ("brent", -1, "Civil aircraft demand depends on airline profits, which suffer when fuel "
                      "is expensive. Defence orders depend on budgets and geopolitics instead."),
        FEAR_CYCLICAL,
    ]),
    (("Drug Manufacturers", "Biotechnology", "Healthcare Plans", "Medical"), [
        FEAR_DEFENSIVE,
        ("us10y", -1, "Steady earners like healthcare compete with bonds for investors' money."),
    ]),
    (("Entertainment", "Internet Content", "Telecom", "Broadcasting", "Advertising"), [
        RATES_GROWTH,
        FEAR_CYCLICAL,
    ]),
    (("Conglomerates",), [
        FEAR_CYCLICAL,
    ]),
    (("Engineering & Construction", "Industrial Machinery", "Heavy Construction", "Waste",
      "Electrical Equipment", "Railroads", "Building"), [
        ("copper", +1, "Orders follow the industrial and investment cycle."),
        ("us10y", -1, "Customers finance big projects with debt, so higher rates delay orders."),
    ]),
    (("Chemicals",), [
        ("copper", +1, "Chemical demand follows global industrial activity."),
        ("natgas", -1, "Energy and gas are major input costs."),
    ]),
]



def _rule(keyword: str) -> list:
    return next(d for keys, d in INDUSTRY_RULES if keyword in keys)


SECTOR_FALLBACK = {
    "Index": [("us10y", -1, "Higher rates lower the value of stocks in general."), FEAR_CYCLICAL],
    "ETF": [("us10y", -1, "Higher rates lower the value of stocks in general."), FEAR_CYCLICAL],
    "Energy": _rule("Oil & Gas E&P"),
    "Financial Services": _rule("Banks"),
    "Technology": [RATES_GROWTH, FEAR_CYCLICAL],
    "Communication Services": [RATES_GROWTH, FEAR_CYCLICAL],
    "Consumer Cyclical": [RATES_CONSUMER, FEAR_CYCLICAL],
    "Consumer Defensive": [FEAR_DEFENSIVE],
    "Healthcare": [FEAR_DEFENSIVE],
    "Utilities": _rule("Utilities"),
    "Real Estate": _rule("Real Estate"),
    "Industrials": [("copper", +1, "Orders follow the industrial cycle."), FEAR_CYCLICAL],
    "Basic Materials": [("copper", +1, "Demand follows the global industrial cycle.")],
}

EXPORT_SECTORS = ("Energy", "Basic Materials")
EXPORT_INDUSTRIES = ("Marine Shipping", "Farm Products", "Aerospace", "Paper", "Semiconductors",
                     "Packaged Foods", "Specialty Industrial Machinery", "Waste Management",
                     "Oil & Gas")
FINANCIAL = ("Financial Services", "Real Estate")


@st.cache_data(ttl=3600)
def get_macro() -> dict:
    tickers = [m[0] for m in MACRO.values()]
    data = yf.download(tickers, period="6mo", progress=False, auto_adjust=True, threads=True)["Close"]
    out = {}
    for key, (ticker, label, kind, *_) in MACRO.items():
        try:
            close = data[ticker].dropna()
            last, date = float(close.iloc[-1]), close.index[-1]
            month = close[close.index <= date - pd.DateOffset(months=1)].iloc[-1]
            quarter = close[close.index <= date - pd.DateOffset(months=3)].iloc[-1]
            if kind == "yield":  # ^TNX is the yield in %, show changes in basis points
                m1, m3 = (last - month) * 100, (last - quarter) * 100
            else:
                m1, m3 = (last / month - 1) * 100, (last / quarter - 1) * 100
            out[key] = {"last": last, "1m": m1, "3m": m3}
        except Exception:
            continue
    return out


def _drivers(market: str, row: dict, info: dict) -> list:
    """List of (macro key, sign, why) for this stock, most important first."""
    industry, sector = row.get("Industry") or "", row.get("Sector") or ""
    drivers = next((d for keys, d in INDUSTRY_RULES if any(k in industry for k in keys)), None)
    drivers = list(drivers or SECTOR_FALLBACK.get(sector, []))
    used = {d[0] for d in drivers}

    def add(key, sign, why):
        if key not in used:
            drivers.append((key, sign, why))
            used.add(key)

    # Currency
    fin_cur, cur = info.get("financialCurrency"), info.get("currency")
    exporter = ((sector in EXPORT_SECTORS or any(k in industry for k in EXPORT_INDUSTRIES))
                and "Refining" not in industry)  # fuel distributors sell at home
    if sector not in ("Index", "ETF"):
        if market == "Oslo":
            if fin_cur == "USD" or (exporter and "Farm" not in industry and "Packaged" not in industry):
                add("usdnok", +1, "Earns mostly in dollars but trades in krone: a weaker krone "
                                  "turns the same dollar profit into more NOK per share.")
            elif exporter or "Farm" in industry or "Packaged" in industry:
                add("eurnok", +1, "Sells largely to Europe in euros: a weaker krone lifts its "
                                  "revenue in NOK.")
        elif market == "B3":
            if exporter:
                add("usdbrl", +1, "Exporter: sells in dollars with costs in reais, so a weaker "
                                  "real widens margins.")
            else:
                add("usdbrl", -1, "Domestic business: a weaker real feeds inflation, keeps "
                                  "Brazil's Selic rate high and weighs on spending and valuations.")
        elif market == "US" and sector in ("Technology", "Consumer Defensive", "Industrials",
                                           "Basic Materials", "Healthcare"):
            add("dxy", -1, "Large share of sales abroad: a stronger dollar shrinks foreign "
                           "earnings once converted back.")

    # Debt
    de = info.get("debtToEquity")
    if de and de > 150 and sector not in FINANCIAL:
        add("us10y", -1, f"High debt (debt is {de:.0f}% of equity): higher rates raise interest "
                         "costs.")

    # Broad market, via beta
    beta = row.get("Beta")
    if beta is not None and pd.notna(beta) and beta >= 0.3:
        add(MARKET_INDEX[market], +1, f"Beta {beta:.2f}: tends to move "
            f"{'more than' if beta > 1.1 else 'roughly with' if beta >= 0.9 else 'less than'} "
            "the overall market.")
    return drivers


def _effect(sign: int, key: str, macro: dict):
    """'Tailwind', 'Headwind' or 'Neutral' for this month's move."""
    m = macro.get(key)
    if not m:
        return "No data", 0
    kind = MACRO[key][2]
    if abs(m["1m"]) < NEUTRAL[kind]:
        return "Neutral", 0
    score = 1 if (m["1m"] > 0) == (sign > 0) else -1
    return ("Tailwind" if score > 0 else "Headwind"), score


def _fmt_change(key, value):
    if value is None or pd.isna(value):
        return "-"
    return f"{value:+.0f} bp" if MACRO[key][2] == "yield" else f"{value:+.1f}%"


def _fmt_level(key, value):
    if MACRO[key][2] == "yield":
        return f"{value:.2f}%"
    return f"{value:,.2f}" if value < 1000 else f"{value:,.0f}"


def _company_signals(row: dict, info: dict, peers: pd.DataFrame):
    up, down = [], []
    sector = row.get("Sector")
    financial = sector in FINANCIAL

    def num(v):
        return v if v is not None and pd.notna(v) else None

    upside, rating = num(row.get("Upside %")), row.get("Rating")
    if upside is not None and upside >= 10:
        up.append(f"Analysts' average target is {upside:.0f}% above today's price"
                  f"{f' (consensus: {rating})' if rating else ''}.")
    elif upside is not None and upside <= -5:
        down.append(f"Trades {-upside:.0f}% above analysts' average target - little room left "
                    "in their view.")

    eps, fwd = num(row.get("EPS (ttm)")), num(row.get("EPS (fwd)"))
    if eps and fwd and eps > 0:
        growth = (fwd / eps - 1) * 100
        if growth >= 100:
            up.append("Analysts expect earnings per share to more than double next year, from a "
                      "low base. Delivering that would support the price.")
        elif growth >= 5:
            up.append(f"Analysts expect earnings per share to grow about {growth:.0f}% next year. "
                      "Delivering that would support the price.")
        elif growth <= -5:
            down.append(f"Analysts expect earnings per share to fall about {-growth:.0f}% next year.")
    if eps is not None and eps < 0:
        down.append("Currently loss-making: the price relies on a future turnaround.")

    rev = num(info.get("revenueGrowth"))
    if rev is not None:
        if rev >= 0.10:
            up.append(f"Revenue is growing {rev * 100:.0f}% year on year.")
        elif rev < 0:
            down.append(f"Revenue is shrinking ({rev * 100:.0f}% year on year).")

    pe = num(row.get("P/E"))
    sector_pe = peers.loc[peers["Sector"] == sector, "P/E"].median() if sector else None
    if pe and sector_pe and pd.notna(sector_pe) and pe > 0:
        if pe < sector_pe * 0.8:
            up.append(f"Cheaper than its sector peers (P/E {pe:.1f} vs {sector_pe:.1f} median). "
                      "Room to re-rate if results hold up.")
        elif pe > sector_pe * 1.3:
            down.append(f"Priced at a premium to peers (P/E {pe:.1f} vs {sector_pe:.1f} median). "
                        "Disappointments tend to hit expensive stocks harder.")

    yld, payout = num(row.get("Div yield %")), num(info.get("payoutRatio"))
    if yld and yld >= 10:
        down.append(f"Dividend yield of {yld:.1f}% is very high; the market may expect a cut.")
    elif yld and yld >= 4 and (payout is None or payout < 0.8):
        up.append(f"Solid {yld:.1f}% dividend yield"
                  f"{f', with {payout * 100:.0f}% of profit paid out' if payout else ''}.")
    if payout and payout > 1 and not financial:
        down.append(f"Pays out {payout * 100:.0f}% of profit as dividends - more than it earns.")

    debt, cash = num(info.get("totalDebt")), num(info.get("totalCash"))
    de = num(info.get("debtToEquity"))
    if not financial:
        if debt is not None and cash is not None and cash > debt:
            up.append("Holds more cash than debt, which gives room for buybacks, dividends or "
                      "acquisitions and a cushion in downturns.")
        elif de and de > 150:
            down.append(f"High debt (debt is {de:.0f}% of equity) adds risk if rates rise or "
                        "business slows.")

    beta = num(row.get("Beta"))
    if beta and beta > 1.3:
        down.append(f"High beta ({beta:.2f}): tends to fall more than the market in sell-offs.")

    m1, off_high = num(row.get("1M %")), num(row.get("From 52w high %"))
    if m1 is not None and m1 >= 5 and off_high is not None and off_high > -5:
        up.append(f"Strong momentum: up {m1:.0f}% in a month and close to its 12-month high.")
    elif m1 is not None and m1 <= -10:
        down.append(f"Negative momentum: down {-m1:.0f}% over the last month.")
    if off_high is not None and off_high <= -25 and upside and upside > 0:
        up.append(f"Down {-off_high:.0f}% from its 12-month high, so a recovery has room to run "
                  "if sentiment turns.")

    short = num(info.get("shortPercentOfFloat"))
    if short and short >= 0.05:
        down.append(f"{short * 100:.0f}% of tradable shares are sold short - many investors "
                    "are betting on a fall (this can also cause sharp rallies if they buy back).")
    return up, down


def _next_earnings(info: dict):
    now = datetime.now(timezone.utc).timestamp()
    stamps = [info.get(k) for k in ("earningsTimestamp", "earningsTimestampStart")]
    future = [s for s in stamps if s and s > now]
    return datetime.fromtimestamp(min(future), timezone.utc) if future else None


def render(market: str, row: dict, info: dict, peers: pd.DataFrame):
    macro = get_macro()
    st.markdown("#### Macro and drivers")

    # Backdrop
    idx_key = MARKET_INDEX[market]
    parts = []
    if idx_key in macro:
        parts.append(f"{MACRO[idx_key][1]} {_fmt_change(idx_key, macro[idx_key]['1m'])} over the month")
    if "vix" in macro:
        v = macro["vix"]["last"]
        mood = "calm" if v < 15 else "normal" if v < 20 else "nervous" if v < 30 else "stressed"
        parts.append(f"VIX {v:.1f} ({mood} markets)")
    if "us10y" in macro:
        parts.append(f"US 10-year yield {macro['us10y']['last']:.2f}% "
                     f"({_fmt_change('us10y', macro['us10y']['1m'])} in a month)")
    if parts:
        st.caption("Backdrop: " + " · ".join(parts))

    # Macro drivers table
    drivers = _drivers(market, row, info)
    rows, up, down, score = [], [], [], 0
    for key, sign, why in drivers:
        effect, s = _effect(sign, key, macro)
        score += s
        m = macro.get(key, {})
        rows.append({
            "Driver": MACRO[key][1],
            "Latest": _fmt_level(key, m["last"]) if m else "-",
            "1 month": _fmt_change(key, m.get("1m")),
            "3 months": _fmt_change(key, m.get("3m")),
            "Effect now": effect,
            "Why it matters": why,
        })
        rise, fall = MACRO[key][3], MACRO[key][4]
        good, bad = (rise, fall) if sign > 0 else (fall, rise)
        now = f" **Happening now ({_fmt_change(key, m.get('1m'))} this month).**"
        # (is it happening now, text): current moves are listed before the "what ifs"
        up.append((effect == "Tailwind", f"{good}.{now if effect == 'Tailwind' else ''}"))
        down.append((effect == "Headwind", f"{bad}.{now if effect == 'Headwind' else ''}"))
    up = [t for _, t in sorted(up, key=lambda x: not x[0])]
    down = [t for _, t in sorted(down, key=lambda x: not x[0])]

    if rows:
        table = pd.DataFrame(rows)

        def color(v):
            return ("color: #1a9850" if v == "Tailwind" else "color: #d73027" if v == "Headwind"
                    else "")

        st.dataframe(
            table.style.map(color, subset=["Effect now"]), hide_index=True, width="stretch",
            column_config={
                "Driver": st.column_config.Column(help="Macro factor that historically moves "
                                                       "this kind of company."),
                "1 month": st.column_config.Column(help="Change in the driver over the last month "
                                                        "(basis points for yields, 1 bp = 0.01%)."),
                "Effect now": st.column_config.Column(
                    help="Whether the driver's move over the last month helps (tailwind) or hurts "
                         "(headwind) this stock. Moves under 2% (10 bp for yields) count as neutral."),
                "Why it matters": st.column_config.Column(width="large"),
            },
        )
        verdict = ("mostly supportive" if score >= 2 else "slightly supportive" if score == 1
                   else "mostly working against it" if score <= -2
                   else "slightly against it" if score == -1 else "mixed or neutral")
        st.caption(f"Overall, the macro picture over the last month is **{verdict}** for this "
                   "stock.")

    # Company specifics
    c_up, c_down = _company_signals(row, info, peers)
    col_up, col_down = st.columns(2)
    with col_up:
        st.markdown("**📈 What could push it up**")
        for text in c_up + up:
            st.markdown(f"- {text}")
    with col_down:
        st.markdown("**📉 What could push it down**")
        for text in c_down + down:
            st.markdown(f"- {text}")

    nxt = _next_earnings(info)
    if nxt:
        st.caption(f"Next earnings report: around {nxt:%d %b %Y}. Results and guidance are usually "
                   "the biggest single-day mover for a stock.")
    st.caption("Rule-based view built from public market data and typical industry sensitivities. "
               "A starting point for your own research, not investment advice.")
