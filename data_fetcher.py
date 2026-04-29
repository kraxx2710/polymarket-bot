import requests
import logging
import json
from datetime import datetime, timezone

log = logging.getLogger(__name__)
HEADERS = {"User-Agent": "Mozilla/5.0"}


def safe_get(url, params=None, timeout=8):
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        log.debug(f"HTTP Fehler {url}: {e}")
        return None


def get_crypto_prices() -> str:
    r = safe_get("https://api.coingecko.com/api/v3/simple/price", {
        "ids": "bitcoin,ethereum,solana,ripple",
        "vs_currencies": "usd",
        "include_24hr_change": "true"
    })
    if not r:
        return ""
    d = r.json()
    lines = []
    names = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "ripple": "XRP"}
    for k, sym in names.items():
        if k in d:
            lines.append(f"{sym}: ${d[k].get('usd', 0):,.0f} ({d[k].get('usd_24h_change', 0):+.1f}% 24h)")
    return "\n".join(lines)


def get_fear_greed() -> str:
    r = safe_get("https://api.alternative.me/fng/?limit=1")
    if not r:
        return ""
    items = r.json().get("data", [])
    if not items:
        return ""
    return f"Fear & Greed: {items[0].get('value')}/100 - {items[0].get('value_classification')}"


def get_yahoo(ticker, name) -> str:
    r = safe_get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d")
    if not r:
        return ""
    try:
        result = r.json()["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        if len(closes) < 2:
            return ""
        cur = closes[-1]
        prev = closes[-2]
        chg = (cur - prev) / prev * 100
        return f"{name}: {cur:,.2f} ({chg:+.2f}% 1T)"
    except Exception:
        return ""


def get_fed_rate() -> str:
    r = safe_get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS")
    if not r:
        return ""
    lines = r.text.strip().split("\n")
    if len(lines) < 2:
        return ""
    last = lines[-1].split(",")
    return f"Fed Funds Rate: {last[1]}% (Stand: {last[0]})"


def get_inflation() -> str:
    r = safe_get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL")
    if not r:
        return ""
    lines = r.text.strip().split("\n")
    if len(lines) < 13:
        return ""
    cur = float(lines[-1].split(",")[1])
    prev = float(lines[-13].split(",")[1])
    yoy = (cur - prev) / prev * 100
    return f"US Inflation (CPI YoY): {yoy:.1f}%"


def get_whale_bias(condition_id: str) -> str:
    if not condition_id:
        return ""
    r = safe_get(f"https://data-api.polymarket.com/positions?market={condition_id}&limit=10&sortBy=size&sortOrder=DESC")
    if not r:
        return ""
    try:
        pos = r.json()
        yes_vol = sum(p.get("size", 0) for p in pos if p.get("outcome") == "Yes")
        no_vol = sum(p.get("size", 0) for p in pos if p.get("outcome") == "No")
        total = yes_vol + no_vol
        if total == 0:
            return ""
        bias = "YES" if yes_vol > no_vol * 1.2 else "NO" if no_vol > yes_vol * 1.2 else "NEUTRAL"
        return f"Whale Bias: {bias} (YES ${yes_vol:,.0f} / NO ${no_vol:,.0f})"
    except Exception:
        return ""


def build_context(market: dict) -> str:
    category = market.get("category", "other")
    condition_id = market.get("condition_id", "")
    parts = ["=== ECHTZEIT MARKTDATEN ==="]

    vix = get_yahoo("%5EVIX", "VIX Angst-Index")
    sp500 = get_yahoo("%5EGSPC", "S&P 500")
    if vix:
        parts.append(vix)
    if sp500:
        parts.append(sp500)

    if category == "crypto":
        parts.append("\n-- KRYPTO --")
        prices = get_crypto_prices()
        fg = get_fear_greed()
        dxy = get_yahoo("DX-Y.NYB", "US Dollar DXY")
        if prices:
            parts.append(prices)
        if fg:
            parts.append(fg)
        if dxy:
            parts.append(dxy)

    elif category in ("economy", "politics"):
        parts.append("\n-- MAKRO --")
        fed = get_fed_rate()
        cpi = get_inflation()
        gold = get_yahoo("GC%3DF", "Gold")
        dxy = get_yahoo("DX-Y.NYB", "US Dollar DXY")
        if fed:
            parts.append(fed)
        if cpi:
            parts.append(cpi)
        if gold:
            parts.append(gold)
        if dxy:
            parts.append(dxy)

    whale = get_whale_bias(condition_id)
    if whale:
        parts.append(f"\n-- POLYMARKET WHALES --\n{whale}")

    parts.append("=== ENDE ===")
    return "\n".join(parts)
