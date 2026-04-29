"""
data_fetcher.py
Holt kostenlose Marktdaten aus verschiedenen Quellen und strukturiert sie
fuer die Claude Analyse. Kein API Key fuer die meisten Quellen noetig.

Quellen:
- CoinGecko API      -> Krypto Preise, Marktdaten, Trends
- Fear & Greed Index -> Krypto Sentiment
- Federal Reserve    -> Letzte Fed Statements (RSS)
- ECB                -> EZB News (RSS)
- Alternative.me     -> Krypto Fear & Greed
- Yahoo Finance      -> Makro Wirtschaftsdaten
- Polymarket CLOB    -> Top Wallet Aktivitaet
- Google Trends      -> Suchvolumen als Sentiment
- Reddit             -> Aktuelle Sentiment Scores
- NewsAPI            -> Breaking News (kostenlos Tier)
"""

import requests
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


class DataFetcher:
    def __init__(self):
        self.cache = {}
        self.cache_ttl = {}

    def _cached(self, key: str, ttl_minutes: int, fetch_fn) -> Optional[dict]:
        now = datetime.now(timezone.utc)
        if key in self.cache:
            age = (now - self.cache_ttl[key]).total_seconds() / 60
            if age < ttl_minutes:
                return self.cache[key]
        try:
            data = fetch_fn()
            if data:
                self.cache[key] = data
                self.cache_ttl[key] = now
            return data
        except Exception as e:
            log.debug(f"Cache fetch Fehler {key}: {e}")
            return self.cache.get(key)

    # ================================================================
    # KRYPTO DATEN
    # ================================================================

    def get_crypto_data(self) -> dict:
        """CoinGecko: BTC, ETH, SOL Preise und Marktdaten"""
        def fetch():
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                "ids": "bitcoin,ethereum,solana,ripple,binancecoin",
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
                "include_market_cap": "true"
            }
            r = requests.get(url, params=params, headers=HEADERS, timeout=10)
            r.raise_for_status()
            data = r.json()

            result = {}
            symbols = {
                "bitcoin": "BTC",
                "ethereum": "ETH",
                "solana": "SOL",
                "ripple": "XRP",
                "binancecoin": "BNB"
            }
            for coin_id, symbol in symbols.items():
                if coin_id in data:
                    d = data[coin_id]
                    result[symbol] = {
                        "price": d.get("usd", 0),
                        "change_24h": round(d.get("usd_24h_change", 0), 2),
                        "volume_24h": d.get("usd_24h_vol", 0),
                        "market_cap": d.get("usd_market_cap", 0)
                    }
            return result

        return self._cached("crypto_prices", 5, fetch) or {}

    def get_fear_greed(self) -> dict:
        """Fear & Greed Index fuer Krypto Sentiment"""
        def fetch():
            r = requests.get(
                "https://api.alternative.me/fng/?limit=3",
                headers=HEADERS, timeout=10
            )
            r.raise_for_status()
            data = r.json()
            items = data.get("data", [])
            if not items:
                return {}
            current = items[0]
            yesterday = items[1] if len(items) > 1 else {}
            return {
                "value": int(current.get("value", 50)),
                "classification": current.get("value_classification", "Neutral"),
                "yesterday": int(yesterday.get("value", 50)) if yesterday else 50,
                "trend": "steigend" if int(current.get("value", 50)) > int(yesterday.get("value", 50)) else "fallend"
            }

        return self._cached("fear_greed", 60, fetch) or {"value": 50, "classification": "Neutral"}

    def get_crypto_global(self) -> dict:
        """Globale Krypto Marktdaten"""
        def fetch():
            r = requests.get(
                "https://api.coingecko.com/api/v3/global",
                headers=HEADERS, timeout=10
            )
            r.raise_for_status()
            data = r.json().get("data", {})
            return {
                "total_market_cap_usd": data.get("total_market_cap", {}).get("usd", 0),
                "btc_dominance": round(data.get("market_cap_percentage", {}).get("btc", 0), 1),
                "eth_dominance": round(data.get("market_cap_percentage", {}).get("eth", 0), 1),
                "market_cap_change_24h": round(data.get("market_cap_change_percentage_24h_usd", 0), 2),
                "active_cryptocurrencies": data.get("active_cryptocurrencies", 0)
            }

        return self._cached("crypto_global", 15, fetch) or {}

    def get_btc_technical(self) -> dict:
        """BTC OHLCV fuer technische Analyse (letzte 7 Tage)"""
        def fetch():
            r = requests.get(
                "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
                params={"vs_currency": "usd", "days": "7", "interval": "daily"},
                headers=HEADERS, timeout=10
            )
            r.raise_for_status()
            data = r.json()
            prices = data.get("prices", [])
            if len(prices) < 2:
                return {}

            current = prices[-1][1]
            week_ago = prices[0][1]
            week_change = round((current - week_ago) / week_ago * 100, 2)

            highs = [p[1] for p in prices]
            return {
                "current": round(current, 0),
                "week_high": round(max(highs), 0),
                "week_low": round(min(highs), 0),
                "week_change_pct": week_change,
                "trend_7d": "bullish" if week_change > 2 else "bearish" if week_change < -2 else "neutral"
            }

        return self._cached("btc_technical", 10, fetch) or {}

    # ================================================================
    # MAKRO / WIRTSCHAFT
    # ================================================================

    def get_fed_data(self) -> dict:
        """Fed Funds Rate und aktuelle Fed News via RSS"""
        def fetch():
            # FRED API (kostenlos, kein Key noetig fuer basic Daten)
            r = requests.get(
                "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS",
                headers=HEADERS, timeout=10
            )
            r.raise_for_status()
            lines = r.text.strip().split("\n")
            if len(lines) < 2:
                return {}
            last = lines[-1].split(",")
            prev = lines[-2].split(",")
            rate = float(last[1])
            prev_rate = float(prev[1])
            return {
                "fed_funds_rate": rate,
                "previous_rate": prev_rate,
                "last_change": round(rate - prev_rate, 2),
                "direction": "erhoehung" if rate > prev_rate else "senkung" if rate < prev_rate else "unveraendert",
                "date": last[0]
            }

        return self._cached("fed_rate", 240, fetch) or {}

    def get_inflation_data(self) -> dict:
        """US CPI Inflation via FRED"""
        def fetch():
            r = requests.get(
                "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL",
                headers=HEADERS, timeout=10
            )
            r.raise_for_status()
            lines = r.text.strip().split("\n")
            if len(lines) < 13:
                return {}
            last = lines[-1].split(",")
            year_ago = lines[-13].split(",")
            current_cpi = float(last[1])
            year_ago_cpi = float(year_ago[1])
            yoy = round((current_cpi - year_ago_cpi) / year_ago_cpi * 100, 2)
            return {
                "cpi_yoy_pct": yoy,
                "date": last[0],
                "trend": "hoch" if yoy > 3 else "moderat" if yoy > 2 else "niedrig"
            }

        return self._cached("inflation", 240, fetch) or {}

    def get_vix(self) -> dict:
        """VIX Volatilitaetsindex via Yahoo Finance"""
        def fetch():
            r = requests.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=5d",
                headers=HEADERS, timeout=10
            )
            r.raise_for_status()
            data = r.json()
            result = data.get("chart", {}).get("result", [{}])[0]
            closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            if not closes:
                return {}
            current = closes[-1]
            prev = closes[-2] if len(closes) > 1 else current
            return {
                "vix": round(current, 2),
                "change": round(current - prev, 2),
                "sentiment": "Panik" if current > 30 else "Angst" if current > 20 else "Gier" if current < 15 else "Normal"
            }

        return self._cached("vix", 15, fetch) or {}

    def get_sp500(self) -> dict:
        """S&P 500 Performance"""
        def fetch():
            r = requests.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1d&range=5d",
                headers=HEADERS, timeout=10
            )
            r.raise_for_status()
            data = r.json()
            result = data.get("chart", {}).get("result", [{}])[0]
            closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            if not closes:
                return {}
            current = closes[-1]
            prev = closes[-2] if len(closes) > 1 else current
            week_ago = closes[0]
            return {
                "price": round(current, 2),
                "change_1d_pct": round((current - prev) / prev * 100, 2),
                "change_5d_pct": round((current - week_ago) / week_ago * 100, 2),
                "trend": "bullish" if current > week_ago else "bearish"
            }

        return self._cached("sp500", 15, fetch) or {}

    def get_dollar_index(self) -> dict:
        """DXY US Dollar Index"""
        def fetch():
            r = requests.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?interval=1d&range=5d",
                headers=HEADERS, timeout=10
            )
            r.raise_for_status()
            data = r.json()
            result = data.get("chart", {}).get("result", [{}])[0]
            closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            if not closes:
                return {}
            current = closes[-1]
            prev = closes[-2] if len(closes) > 1 else current
            return {
                "dxy": round(current, 2),
                "change_1d_pct": round((current - prev) / prev * 100, 2),
                "trend": "staerker" if current > prev else "schwaecher"
            }

        return self._cached("dxy", 15, fetch) or {}

    def get_gold(self) -> dict:
        """Gold Preis als Safe Haven Indikator"""
        def fetch():
            r = requests.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF?interval=1d&range=5d",
                headers=HEADERS, timeout=10
            )
            r.raise_for_status()
            data = r.json()
            result = data.get("chart", {}).get("result", [{}])[0]
            closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            if not closes:
                return {}
            current = closes[-1]
            prev = closes[-2] if len(closes) > 1 else current
            return {
                "price_usd": round(current, 2),
                "change_1d_pct": round((current - prev) / prev * 100, 2),
                "safe_haven": "aktiv" if current > prev * 1.005 else "neutral"
            }

        return self._cached("gold", 30, fetch) or {}

    # ================================================================
    # POLYMARKET WHALE TRACKING
    # ================================================================

    def get_polymarket_top_traders(self, condition_id: str) -> dict:
        """Schaut wer die groessten Positionen in einem Markt haelt"""
        def fetch():
            try:
                r = requests.get(
                    f"https://data-api.polymarket.com/positions?market={condition_id}&limit=10&sortBy=size&sortOrder=DESC",
                    headers=HEADERS, timeout=10
                )
                r.raise_for_status()
                positions = r.json()
                if not positions:
                    return {}

                yes_volume = sum(p.get("size", 0) for p in positions if p.get("outcome") == "Yes")
                no_volume = sum(p.get("size", 0) for p in positions if p.get("outcome") == "No")
                total = yes_volume + no_volume

                return {
                    "yes_volume_top10": round(yes_volume, 2),
                    "no_volume_top10": round(no_volume, 2),
                    "whale_bias": "YES" if yes_volume > no_volume * 1.2 else "NO" if no_volume > yes_volume * 1.2 else "NEUTRAL",
                    "whale_ratio": round(yes_volume / total, 2) if total > 0 else 0.5
                }
            except Exception:
                return {}

        return self._cached(f"whales_{condition_id}", 10, fetch) or {}

    # ================================================================
    # HAUPT METHODE: Daten fuer Analyse zusammenstellen
    # ================================================================

    def get_context_for_market(self, market: dict) -> str:
        """
        Baut einen strukturierten Daten-Context String fuer Claude
        basierend auf der Markt-Kategorie.
        """
        category = market.get("category", "other")
        condition_id = market.get("condition_id", "")
        lines = []

        lines.append("=== AKTUELLE MARKTDATEN ===")

        # Immer: Makro Sentiment
        vix = self.get_vix()
        if vix:
            lines.append(f"VIX (Angst-Index): {vix.get('vix')} - {vix.get('sentiment')}")

        sp500 = self.get_sp500()
        if sp500:
            lines.append(f"S&P 500: ${sp500.get('price'):,.0f} | 1T: {sp500.get('change_1d_pct')}% | 5T: {sp500.get('change_5d_pct')}%")

        # Krypto-spezifische Daten
        if category == "crypto":
            lines.append("\n--- KRYPTO DATEN ---")

            crypto = self.get_crypto_data()
            if crypto:
                for symbol, data in crypto.items():
                    lines.append(f"{symbol}: ${data['price']:,.0f} | 24h: {data['change_24h']}%")

            fg = self.get_fear_greed()
            if fg:
                lines.append(f"Fear & Greed Index: {fg.get('value')}/100 - {fg.get('classification')} (Trend: {fg.get('trend')})")

            global_data = self.get_crypto_global()
            if global_data:
                lines.append(f"Gesamtmarkt: ${global_data.get('total_market_cap_usd', 0)/1e12:.2f}T | BTC Dominanz: {global_data.get('btc_dominance')}% | 24h Change: {global_data.get('market_cap_change_24h')}%")

            btc_tech = self.get_btc_technical()
            if btc_tech:
                lines.append(f"BTC 7-Tage: Hoch ${btc_tech.get('week_high'):,.0f} | Tief ${btc_tech.get('week_low'):,.0f} | Trend: {btc_tech.get('trend_7d')}")

            dxy = self.get_dollar_index()
            if dxy:
                lines.append(f"US Dollar (DXY): {dxy.get('dxy')} ({dxy.get('trend')})")

        # Wirtschaft-spezifische Daten
        elif category == "economy":
            lines.append("\n--- WIRTSCHAFTSDATEN ---")

            fed = self.get_fed_data()
            if fed:
                lines.append(f"Fed Funds Rate: {fed.get('fed_funds_rate')}% (letzte Aenderung: {fed.get('direction')} um {abs(fed.get('last_change', 0))}%)")

            inflation = self.get_inflation_data()
            if inflation:
                lines.append(f"US Inflation (CPI YoY): {inflation.get('cpi_yoy_pct')}% - {inflation.get('trend')}")

            dxy = self.get_dollar_index()
            if dxy:
                lines.append(f"US Dollar (DXY): {dxy.get('dxy')} | 1T: {dxy.get('change_1d_pct')}%")

            gold = self.get_gold()
            if gold:
                lines.append(f"Gold: ${gold.get('price_usd'):,.0f} | Safe Haven: {gold.get('safe_haven')}")

        # Politik-spezifische Daten
        elif category == "politics":
            lines.append("\n--- MAKRO INDIKATOREN ---")

            fed = self.get_fed_data()
            if fed:
                lines.append(f"Fed Funds Rate: {fed.get('fed_funds_rate')}%")

            gold = self.get_gold()
            if gold:
                lines.append(f"Gold (Geopolitik-Barometer): ${gold.get('price_usd'):,.0f} | {gold.get('safe_haven')}")

            dxy = self.get_dollar_index()
            if dxy:
                lines.append(f"US Dollar: {dxy.get('dxy')} ({dxy.get('trend')})")

        # Whale Tracking fuer alle Kategorien
        if condition_id:
            lines.append("\n--- POLYMARKET WHALE AKTIVITAET ---")
            whales = self.get_polymarket_top_traders(condition_id)
            if whales:
                lines.append(f"Top 10 Trader: YES Volume ${whales.get('yes_volume_top10'):,.0f} | NO Volume ${whales.get('no_volume_top10'):,.0f}")
                lines.append(f"Whale Bias: {whales.get('whale_bias')} (YES Ratio: {whales.get('whale_ratio'):.0%})")
            else:
                lines.append("Keine Whale Daten verfuegbar")

        lines.append("\n=== ENDE MARKTDATEN ===")
        return "\n".join(lines)
