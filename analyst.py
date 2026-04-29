"""
analyst.py - Claude analysiert mit Echtzeit-Daten + Web Search
"""
import anthropic
import json
import logging
import time
from data_fetcher import DataFetcher

log = logging.getLogger(__name__)

class ClaudeAnalyst:
    def __init__(self, config: dict):
        self.cfg = config
        self.client = anthropic.Anthropic()
        self.fetcher = DataFetcher()

    def analyse(self, market: dict) -> dict:
        question = market["question"]
        yes_price = market["yes_price"]
        no_price = market["no_price"]
        category = market.get("category", "other")
        days_left = market.get("days_left", 0)
        min_confidence = market.get("min_confidence", self.cfg["min_confidence"])

        market_context = self.fetcher.get_context_for_market(market)

        if category == "crypto":
            focus = "FOKUS: Fear&Greed, BTC Trend, Whale Bias, DXY, aktuelle News. Edge wenn Preis klar ueber/unter technischen Levels."
        elif category == "economy":
            focus = "FOKUS: Fed Rate, Inflation, FOMC Statements, historische Basisrate. Edge wenn Konsensus vom Marktpreis abweicht."
        elif category == "politics":
            focus = "FOKUS: Aktuelle Nachrichtenlage, Gold als Geopolitik-Barometer, offizielle Statements. Skeptisch bei Extremen."
        else:
            focus = "FOKUS: Aktuelle Fakten, Basisrate, Marktpreis vs eigene Einschaetzung."

        prompt = f"""Du bist ein professioneller Prediction Market Analyst.

{market_context}

FRAGE: {question}
KATEGORIE: {category.upper()}
YES: {yes_price:.2f} ({yes_price*100:.0f}%) | NO: {no_price:.2f} | TAGE: {days_left:.1f}

{focus}

1. Analysiere Echtzeit-Daten oben
2. Web Search fuer neueste News
3. Schaetze wahre Wahrscheinlichkeit
4. Edge muss mindestens 10 Cent sein

ANTWORTE NUR JSON:
{{"action":"BUY_YES/BUY_NO/SKIP","confidence":0.0,"true_probability_estimate":0.0,"edge":0.0,"reasoning":"2 Saetze DE","key_finding":"Wichtigster Fakt","data_signal":"Hilfreichstes Signal"}}

Min Konfidenz: {min_confidence:.0%} | Min Edge: 0.10"""

        try:
            time.sleep(15)
            response = self.client.messages.create(
                model=self.cfg["claude_model"],
                max_tokens=500,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": prompt}],
            )
            text_blocks = []
            for b in response.content:
                if hasattr(b, "text") and b.text and b.text.strip():
                    text_blocks.append(b.text.strip())
            text_content = " ".join(text_blocks).strip()
            if not text_content or text_content == "{}":
                log.warning("Claude: Leere Antwort - Web Search only, kein Text")
                return self._skip(market, "Leere Textantwort")
            if "```" in text_content:
                for part in text_content.split("```"):
                    if "{" in part:
                        text_content = part.replace("json","").strip()
                        break
            s, e = text_content.find("{"), text_content.rfind("}") + 1
            if s >= 0 and e > s:
                text_content = text_content[s:e]
            result = json.loads(text_content)
            action = result.get("action", "SKIP")
            confidence = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
            edge = float(result.get("edge", 0.0))
            if action not in ("BUY_YES","BUY_NO","SKIP"):
                action = "SKIP"
            if action != "SKIP" and abs(edge) < 0.10:
                action = "SKIP"
            decision = {
                "action": action, "confidence": confidence,
                "min_confidence": min_confidence,
                "true_probability_estimate": float(result.get("true_probability_estimate", 0.5)),
                "edge": edge, "reasoning": result.get("reasoning",""),
                "key_finding": result.get("key_finding",""),
                "data_signal": result.get("data_signal",""),
                "question": question, "category": category,
                "yes_price": yes_price, "no_price": no_price,
                "trade_size": market.get("trade_size", self.cfg["trade_size_usdc"]),
                "yes_token_id": market["yes_token_id"],
                "no_token_id": market["no_token_id"],
                "market_url": market.get("url",""),
            }
            log.info(f"Claude [{category.upper()}]: {action} Konfidenz={confidence:.0%} Edge={edge:.2f} | {question[:50]}...")
            return decision
        except Exception as e:
            log.error(f"Claude Fehler: {e}")
            return self._skip(market, str(e))

    def _skip(self, market, reason):
        return {"action":"SKIP","confidence":0.0,"min_confidence":market.get("min_confidence",0.78),"edge":0.0,"reasoning":f"Fehler: {reason}","key_finding":"","data_signal":"","question":market.get("question",""),"category":market.get("category","other"),"yes_price":market.get("yes_price",0),"no_price":market.get("no_price",0),"trade_size":market.get("trade_size",self.cfg["trade_size_usdc"]),"yes_token_id":market.get("yes_token_id",""),"no_token_id":market.get("no_token_id",""),"market_url":market.get("url",""),}
