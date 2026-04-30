import anthropic
import json
import logging
import time
from data_fetcher import build_context

log = logging.getLogger(__name__)


class ClaudeAnalyst:
    def __init__(self, config: dict):
        self.cfg = config
        self.client = anthropic.Anthropic()

    def analyse(self, market: dict) -> dict:
        question = market["question"]
        yes_price = market["yes_price"]
        no_price = market["no_price"]
        category = market.get("category", "other")
        days_left = market.get("days_left", 0)
        min_conf = market.get("min_confidence", self.cfg["min_confidence"])

        context = build_context(market)

        focus_map = {
            "crypto": "Fokus: Aktueller Preis vs Ziel, Fear&Greed, DXY Einfluss, Momentum.",
            "economy": "Fokus: Fed Rate, Inflation, FOMC Erwartungen, historische Basisrate.",
            "politics": "Fokus: Aktuelle Nachrichtenlage, Gold als Barometer, offizielle Statements.",
        }
        focus = focus_map.get(category, "Fokus: Aktuelle Fakten und Basisrate.")

        prompt = f"""Du bist ein professioneller Prediction Market Analyst.

{context}

MARKTFRAGE: {question}
KATEGORIE: {category.upper()}
YES-PREIS: {yes_price:.2f} ({yes_price*100:.0f}% Marktwahrscheinlichkeit)
NO-PREIS: {no_price:.2f}
TAGE BIS ABLAUF: {days_left:.1f}

{focus}

Aufgabe:
1. Analysiere die Echtzeit-Daten
2. Suche mit Web Search nach aktuellen News
3. Schaetze die wahre Wahrscheinlichkeit
4. Kalkuliere den Edge (deine Einschaetzung minus Marktpreis)

Regeln:
- BUY_YES: deine Einschaetzung > Marktpreis + 0.10
- BUY_NO: deine Einschaetzung < Marktpreis - 0.10
- SKIP: Edge kleiner als 0.10 oder zu unsicher

Antworte AUSSCHLIESSLICH mit diesem JSON-Format:
{{"action":"SKIP","confidence":0.75,"true_probability_estimate":0.45,"edge":-0.05,"reasoning":"Kurze Begruendung auf Deutsch.","key_finding":"Wichtigster Fakt."}}"""

        time.sleep(12)

        for attempt in range(2):
            try:
                if attempt == 0:
                    response = self.client.messages.create(
                        model=self.cfg["claude_model"],
                        max_tokens=400,
                        tools=[{"type": "web_search_20250305", "name": "web_search"}],
                        messages=[{"role": "user", "content": prompt}],
                    )
                else:
                    response = self.client.messages.create(
                        model=self.cfg["claude_model"],
                        max_tokens=400,
                        messages=[{"role": "user", "content": prompt}],
                    )

                text = ""
                for block in response.content:
                    if hasattr(block, "text") and block.text:
                        text += block.text

                start = text.find("{")
                end = text.rfind("}") + 1
                if start < 0 or end <= start:
                    log.warning(f"Kein JSON in Antwort (Versuch {attempt+1})")
                    continue

                result = json.loads(text[start:end])
                action = result.get("action", "SKIP")
                confidence = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
                edge = float(result.get("edge", 0.0))

                if action not in ("BUY_YES", "BUY_NO", "SKIP"):
                    action = "SKIP"
                if action != "SKIP" and abs(edge) < 0.07:
                    action = "SKIP"

                log.info(f"Claude [{category.upper()}]: {action} Konfidenz={confidence:.0%} "
                         f"Edge={edge:+.2f} | {question[:55]}...")

                return {
                    "action": action,
                    "confidence": confidence,
                    "min_confidence": min_conf,
                    "edge": edge,
                    "true_probability_estimate": float(result.get("true_probability_estimate", 0.5)),
                    "reasoning": result.get("reasoning", ""),
                    "key_finding": result.get("key_finding", ""),
                    "question": question,
                    "category": category,
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "trade_size": market.get("trade_size", self.cfg["trade_size_usdc"]),
                    "yes_token_id": market["yes_token_id"],
                    "no_token_id": market["no_token_id"],
                    "market_url": market.get("url", ""),
                }

            except json.JSONDecodeError as e:
                log.error(f"JSON Fehler (Versuch {attempt+1}): {e}")
            except Exception as e:
                log.error(f"API Fehler (Versuch {attempt+1}): {e}")

        return self._skip(market, "Beide Versuche fehlgeschlagen")

    def _skip(self, market, reason=""):
        return {
            "action": "SKIP", "confidence": 0.0,
            "min_confidence": market.get("min_confidence", 0.78),
            "edge": 0.0, "reasoning": reason, "key_finding": "",
            "question": market.get("question", ""),
            "category": market.get("category", "other"),
            "yes_price": market.get("yes_price", 0),
            "no_price": market.get("no_price", 0),
            "trade_size": market.get("trade_size", self.cfg["trade_size_usdc"]),
            "yes_token_id": market.get("yes_token_id", ""),
            "no_token_id": market.get("no_token_id", ""),
            "market_url": market.get("url", ""),
        }
