import requests
import logging

log = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"


class MarketScanner:
    def __init__(self, config: dict):
        self.cfg = config

    def get_tradable_markets(self) -> list[dict]:
        try:
            params = {
                "active": "true",
                "closed": "false",
                "limit": 200,
                "order": "liquidity",
                "ascending": "false",
            }
            resp = requests.get(f"{GAMMA_API}/markets", params=params, timeout=15)
            resp.raise_for_status()
            raw_markets = resp.json()
        except Exception as e:
            log.error(f"Gamma API Fehler: {e}")
            return []

        candidates = []
        for m in raw_markets:
            try:
                question = m.get("question", "")
                slug = m.get("slug", "")
                condition_id = m.get("conditionId", "")
                liquidity = float(m.get("liquidity") or 0)
                end_date = m.get("endDate", "")

                # Preise aus outcomePrices oder outcomes
                outcome_prices = m.get("outcomePrices", [])
                outcomes = m.get("outcomes", [])

                if not outcome_prices or len(outcome_prices) < 2:
                    continue

                # outcomePrices ist oft ein JSON-String
                if isinstance(outcome_prices, str):
                    import json
                    outcome_prices = json.loads(outcome_prices)
                if isinstance(outcomes, str):
                    import json
                    outcomes = json.loads(outcomes)

                # YES/NO Preise
                yes_price = float(outcome_prices[0])
                no_price = float(outcome_prices[1])

                # Spread
                spread = abs((yes_price + no_price) - 1.0)

                # Contrarian Filter
                if yes_price < self.cfg["min_yes_price"]:
                    continue
                if yes_price > self.cfg["max_yes_price"]:
                    continue
                if liquidity < self.cfg["min_volume_usdc"]:
                    continue
                if spread > self.cfg["max_spread"]:
                    continue

                # Token IDs fuer CLOB
                clob_token_ids = m.get("clobTokenIds", [])
                if isinstance(clob_token_ids, str):
                    import json
                    clob_token_ids = json.loads(clob_token_ids)

                yes_token_id = clob_token_ids[0] if len(clob_token_ids) > 0 else ""
                no_token_id = clob_token_ids[1] if len(clob_token_ids) > 1 else ""

                candidates.append({
                    "condition_id": condition_id,
                    "question": question,
                    "yes_token_id": yes_token_id,
                    "no_token_id": no_token_id,
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "spread": round(spread, 4),
                    "volume_24h": round(liquidity, 2),
                    "end_date": end_date,
                    "url": f"https://polymarket.com/event/{slug}",
                })

            except Exception as e:
                log.debug(f"Markt übersprungen: {e}")
                continue

        candidates.sort(key=lambda x: x["volume_24h"], reverse=True)
        top = candidates[:self.cfg["max_markets_per_cycle"]]
        log.info(f"Scanner: {len(raw_markets)} Märkte geprüft, {len(candidates)} Kandidaten, {len(top)} zur Analyse")
        return top
