"""
analyst.py
Schickt jeden Marktkandidaten an Claude mit Web Search.
Claude bewertet ob das Event wahrscheinlicher ist als der Marktpreis impliziert
und gibt eine strukturierte Entscheidung zurück.
"""

import anthropic
import time
import json
import logging

log = logging.getLogger(__name__)


class ClaudeAnalyst:
    def __init__(self, config: dict):
        self.cfg = config
        self.client = anthropic.Anthropic()  # nutzt ANTHROPIC_API_KEY aus .env

    def analyse(self, market: dict) -> dict:
        """
        Analysiert einen Markt und gibt eine strukturierte Entscheidung zurück.

        Returns:
            {
                "action": "BUY_YES" | "BUY_NO" | "SKIP",
                "confidence": 0.0 - 1.0,
                "reasoning": "...",
                "question": "...",
            }
        """
        question = market["question"]
        yes_price = market["yes_price"]
        no_price = market["no_price"]
        end_date = market.get("end_date", "unbekannt")

        prompt = f"""Du bist ein Prediction-Market-Analyst. Analysiere diese Marktfrage:

FRAGE: {question}
AKTUELLER YES-PREIS: {yes_price:.2f} ({yes_price*100:.0f} Cent = Markt schätzt {yes_price*100:.0f}% Wahrscheinlichkeit)
AKTUELLER NO-PREIS: {no_price:.2f} ({no_price*100:.0f} Cent)
ABLAUFDATUM: {end_date}

DEINE AUFGABE:
1. Recherchiere aktuelle Informationen zu dieser Frage mit Web Search
2. Schätze die wahre Wahrscheinlichkeit des YES-Outcomes
3. Vergleiche deine Einschätzung mit dem Marktpreis

CONTRARIAN-LOGIK:
- YES-Preis ist niedrig ({yes_price*100:.0f} Cent) = Markt hält es für unwahrscheinlich
- Wenn du glaubst es ist WAHRSCHEINLICHER als {yes_price*100:.0f}% -> BUY YES
- Wenn du glaubst es ist UNWAHRSCHEINLICHER als {yes_price*100:.0f}% -> BUY NO (noch mehr Contrarian)
- Bei Unsicherheit oder keine klare Edge -> SKIP

ANTWORTE NUR MIT DIESEM JSON (kein Text davor oder danach):
{{
  "action": "BUY_YES" oder "BUY_NO" oder "SKIP",
  "confidence": 0.0 bis 1.0,
  "true_probability_estimate": 0.0 bis 1.0,
  "reasoning": "Kurze Begründung auf Deutsch, max 2 Sätze",
  "key_finding": "Der wichtigste Fakt aus deiner Recherche"
}}

WICHTIG: confidence >= 0.70 bedeutet Trade wird ausgeführt. Sei konservativ."""

        time.sleep(15)
        time.sleep(15)
        try:
            response = self.client.messages.create(
                model=self.cfg["claude_model"],
                max_tokens=800,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": prompt}],
            )

            # Text aus Response extrahieren
            text_content = ""
            for block in response.content:
                if block.type == "text":
                    text_content += block.text

            # JSON parsen
            text_content = text_content.strip()
            # Manchmal wrapped Claude in ```json ... ```
            if "```" in text_content:
                text_content = text_content.split("```")[1]
                if text_content.startswith("json"):
                    text_content = text_content[4:]

            result = json.loads(text_content.strip())

            # Validierung
            action = result.get("action", "SKIP")
            confidence = float(result.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))

            if action not in ("BUY_YES", "BUY_NO", "SKIP"):
                action = "SKIP"

            decision = {
                "action": action,
                "confidence": confidence,
                "true_probability_estimate": float(result.get("true_probability_estimate", 0.5)),
                "reasoning": result.get("reasoning", ""),
                "key_finding": result.get("key_finding", ""),
                "question": question,
                "yes_price": yes_price,
                "no_price": no_price,
                "yes_token_id": market["yes_token_id"],
                "no_token_id": market["no_token_id"],
                "market_url": market.get("url", ""),
            }

            log.info(
                f"Claude Analyse: [{action}] Konfidenz={confidence:.0%} | {question[:60]}..."
            )
            return decision

        except json.JSONDecodeError as e:
            log.error(f"Claude JSON Parse Fehler: {e} | Raw: {text_content[:200]}")
            return self._skip_decision(market, "JSON Parse Fehler")
        except Exception as e:
            log.error(f"Claude API Fehler: {e}")
            return self._skip_decision(market, str(e))

    def _skip_decision(self, market: dict, reason: str) -> dict:
        return {
            "action": "SKIP",
            "confidence": 0.0,
            "reasoning": f"Fehler: {reason}",
            "key_finding": "",
            "question": market.get("question", ""),
            "yes_price": market.get("yes_price", 0),
            "no_price": market.get("no_price", 0),
            "yes_token_id": market.get("yes_token_id", ""),
            "no_token_id": market.get("no_token_id", ""),
            "market_url": market.get("url", ""),
        }
