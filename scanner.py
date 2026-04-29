import requests
import logging
import json
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)
GAMMA_API = "https://gamma-api.polymarket.com"

class MarketScanner:
    def __init__(self, config: dict):
        self.cfg = config

    def get_tradable_markets(self) -> list[dict]:
        try:
            params = {"active": "true", "closed": "false", "limit": 200, "order": "liquidity", "ascending": "false"}
            resp = requests.get(f"{GAMMA_API}/markets", params=params, timeout=15)
            resp.raise_for_status()
            raw_markets = resp.json()
        except Exception as e:
            log.error(f"Gamma API Fehler: {e}")
            return []

        now = datetime.now(timezone.utc)
        short_cutoff = now + timedelta(hours=48)
        long_min = now + timedelta(days=7)
        long_max = now + timedelta(days=30)

        short_term = []
        long_term = []

        for m in raw_markets:
            try:
                question = m.get("question", "")
                slug = m.get("slug", "")
                condition_id = m.get("conditionId", "")
                liquidity = float(m.get("liquidity") or 0)
                end_date_str = m.get("endDate", "")

                if not end_date_str:
                    continue
                end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                if end_date < now:
                    continue

                hours_left = (end_date - now).total_seconds() / 3600
                days_left = hours_left / 24

                outcome_prices = m.get("outcomePrices", [])
                if not outcome_prices or len(outcome_prices) < 2:
                    continue
                if isinstance(outcome_prices, str):
                    outcome_prices = json.loads(outcome_prices)

                yes_price = float(outcome_prices[0])
                no_price = float(outcome_prices[1])
                spread = abs((yes_price + no_price) - 1.0)

                if yes_price < self.cfg["min_yes_price"]:
                    continue
                if yes_price > self.cfg["max_yes_price"]:
                    continue
                if liquidity < self.cfg["min_volume_usdc"]:
                    continue
                if spread > self.cfg["max_spread"]:
                    continue

                clob_token_ids = m.get("clobTokenIds", [])
                if isinstance(clob_token_ids, str):
                    clob_token_ids = json.loads(clob_token_ids)

                market = {
                    "condition_id": condition_id,
                    "question": question,
                    "yes_token_id": clob_token_ids[0] if len(clob_token_ids) > 0 else "",
                    "no_token_id": clob_token_ids[1] if len(clob_token_ids) > 1 else "",
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "spread": round(spread, 4),
                    "volume_24h": round(liquidity, 2),
                    "end_date": end_date_str,
                    "hours_left": round(hours_left, 1),
                    "days_left": round(days_left, 1),
                    "url": f"https://polymarket.com/event/{slug}",
                }

                if end_date <= short_cutoff:
                    market["term"] = "short"
                    market["trade_size"] = self.cfg["trade_size_short"]
                    short_term.append(market)
                elif end_date >= long_min and end_date <= long_max:
                    market["term"] = "long"
                    market["trade_size"] = self.cfg["trade_size_long"]
                    long_term.append(market)

            except Exception as e:
                log.debug(f"Markt übersprungen: {e}")
                continue

        short_term.sort(key=lambda x: x["volume_24h"], reverse=True)
        long_term.sort(key=lambda x: x["volume_24h"], reverse=True)

        # Mix: 2 kurzfristige + 3 langfristige pro Zyklus
        candidates = short_term[:2] + long_term[:3]

        log.info(f"Scanner: {len(raw_markets)} Märkte | {len(short_term)} kurzfristig | {len(long_term)} langfristig | {len(candidates)} zur Analyse")
        return candidates
