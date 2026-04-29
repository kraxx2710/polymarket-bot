import json
import logging
from datetime import datetime, date
from pathlib import Path

log = logging.getLogger(__name__)
STATE_FILE = "risk_state.json"


class RiskManager:
    def __init__(self, config: dict):
        self.cfg = config
        self.state = self._load()

    def _load(self) -> dict:
        if Path(STATE_FILE).exists():
            try:
                s = json.loads(Path(STATE_FILE).read_text())
                if s.get("date") != str(date.today()):
                    s["daily_loss"] = 0.0
                    s["date"] = str(date.today())
                    self._save(s)
                return s
            except Exception:
                pass
        return {"date": str(date.today()), "daily_loss": 0.0, "positions": {}, "log": []}

    def _save(self, state=None):
        Path(STATE_FILE).write_text(json.dumps(state or self.state, indent=2))

    def can_trade(self, question: str) -> tuple:
        if self.state["daily_loss"] >= self.cfg["max_daily_loss_usdc"]:
            return False, f"Daily Loss Limit erreicht: ${self.state['daily_loss']:.2f}"
        if len(self.state["positions"]) >= self.cfg["max_open_positions"]:
            return False, f"Max Positionen: {len(self.state['positions'])}"
        for pos in self.state["positions"].values():
            if pos.get("question") == question:
                return False, "Bereits in diesem Markt"
        return True, "OK"

    def record_trade(self, decision: dict, order: dict):
        key = decision.get("yes_token_id", "unknown")
        self.state["positions"][key] = {
            "question": decision["question"],
            "action": decision["action"],
            "size": decision.get("trade_size", 5.0),
            "timestamp": datetime.now().isoformat(),
            "order_id": order.get("orderID", ""),
        }
        self.state["log"].append({
            "timestamp": datetime.now().isoformat(),
            "question": decision["question"][:80],
            "action": decision["action"],
            "confidence": decision.get("confidence", 0),
            "edge": decision.get("edge", 0),
            "size": decision.get("trade_size", 5.0),
        })
        self._save()

    def summary(self) -> dict:
        return {
            "daily_loss": self.state["daily_loss"],
            "open_positions": len(self.state["positions"]),
            "trades_today": len([x for x in self.state["log"]
                                 if x["timestamp"].startswith(str(date.today()))]),
        }
