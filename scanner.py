import requests
import logging
import json
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)
GAMMA_API = "https://gamma-api.polymarket.com"

CRYPTO_WORDS = ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "sol", "xrp",
                "binance", "coinbase", "blockchain", "defi", "token", "altcoin", "bnb",
                "ripple", "cardano", "ada", "polygon", "matic", "dogecoin", "doge"]

ECONOMY_WORDS = ["fed", "federal reserve", "rate cut", "interest rate", "inflation", "cpi",
                 "gdp", "recession", "unemployment", "jobs report", "ecb", "central bank",
                 "treasury", "tariff", "trade war", "fiscal", "monetary", "fomc", "powell",
                 "lagarde", "bank of england", "boe", "debt", "deficit", "nonfarm"]

POLITICS_WORDS = ["president", "election", "congress", "senate", "parliament", "minister",
                  "chancellor", "treaty", "sanctions", "nato", "ceasefire", "summit",
                  "referendum", "government", "prime minister", "secretary", "diplomat",
                  "geopolit", "nuclear", "military", "troops", "invasion", "war ends"]

SKIP_WORDS = ["vs.", " vs ", "match", "game ", "set ", "halftime", "half time", "inning",
              "quarter", "period ", "pm et", "am et", "o/u", "over/under", "moneyline",
              "handicap", "spread", "first goal", "leading at", "up or down", "score ",
              "maps ", "round ", "tournament", "championship game", "nba game", "nfl game",
              "nhl game", "mlb game", "ufc ", "mma ", "fight ", "bout ", "tennis ",
              "serve ", "ace ", "forehand", "backhand", "assist", "rebound", "touchdown",
              "field goal", "home run", "strikeout", "penalty kick", "free kick"]


def classify(question: str) -> str:
    q = question.lower()
    for w in SKIP_WORDS:
        if w in q:
            return "skip"
    c = sum(1 for w in CRYPTO_WORDS if w in q)
    e = sum(1 for w in ECONOMY_WORDS if w in q)
    p = sum(1 for w in POLITICS_WORDS if w in q)
    if c > 0 and e == 0 and p == 0:
        return "crypto"
    if e >= p and e > 0:
        return "economy"
    if p > 0:
        return "politics"
    return "skip"


class MarketScanner:
    def __init__(self, config: dict):
        self.cfg = config

    def get_tradable_markets(self) -> list:
        try:
            r = requests.get(
                f"{GAMMA_API}/markets",
                params={"active": "true", "closed": "false", "limit": 200,
                        "order": "liquidity", "ascending": "false"},
                timeout=15
            )
            r.raise_for_status()
            raw = r.json()
        except Exception as e:
            log.error(f"Gamma API Fehler: {e}")
            return []

        now = datetime.now(timezone.utc)
        crypto_list = []
        economy_politics_list = []

        for m in raw:
            try:
                q = m.get("question", "")
                category = classify(q)
                if category == "skip":
                    continue

                end_str = m.get("endDate", "")
                if not end_str:
                    continue
                end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                if end < now:
                    continue
                days = (end - now).total_seconds() / 86400

                if category == "crypto" and not (1 <= days <= 7):
                    continue
                if category in ("economy", "politics") and not (3 <= days <= 30):
                    continue

                liquidity = float(m.get("liquidity") or 0)
                if liquidity < self.cfg["min_volume_usdc"]:
                    continue

                prices = m.get("outcomePrices", [])
                if not prices or len(prices) < 2:
                    continue
                if isinstance(prices, str):
                    prices = json.loads(prices)
                yes = float(prices[0])
                no = float(prices[1])
                spread = abs(yes + no - 1.0)

                if yes < self.cfg["min_yes_price"] or yes > self.cfg["max_yes_price"]:
                    continue
                if spread > self.cfg["max_spread"]:
                    continue

                ids = m.get("clobTokenIds", [])
                if isinstance(ids, str):
                    ids = json.loads(ids)

                if category == "crypto":
                    trade_size = self.cfg.get("trade_size_crypto", 5.0)
                    min_conf = self.cfg.get("min_confidence_crypto", 0.80)
                else:
                    trade_size = self.cfg.get("trade_size_economy", 10.0)
                    min_conf = self.cfg.get("min_confidence_economy", 0.78)

                market = {
                    "condition_id": m.get("conditionId", ""),
                    "question": q,
                    "category": category,
                    "yes_token_id": ids[0] if len(ids) > 0 else "",
                    "no_token_id": ids[1] if len(ids) > 1 else "",
                    "yes_price": yes,
                    "no_price": no,
                    "spread": round(spread, 4),
                    "volume_24h": round(liquidity, 2),
                    "end_date": end_str,
                    "days_left": round(days, 1),
                    "trade_size": trade_size,
                    "min_confidence": min_conf,
                    "url": f"https://polymarket.com/event/{m.get('slug', '')}",
                }

                if category == "crypto":
                    crypto_list.append(market)
                else:
                    economy_politics_list.append(market)

            except Exception as e:
                log.debug(f"Markt skip: {e}")
                continue

        crypto_list.sort(key=lambda x: x["volume_24h"], reverse=True)
        economy_politics_list.sort(key=lambda x: x["volume_24h"], reverse=True)
        result = crypto_list[:2] + economy_politics_list[:3]

        log.info(f"Scanner: {len(raw)} Maerkte | {len(crypto_list)} Krypto | "
                 f"{len(economy_politics_list)} Eco/Pol | {len(result)} zur Analyse")
        return result
