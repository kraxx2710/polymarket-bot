"""
risk.py
Verwaltet Positionslimits, Daily Loss Tracking und Duplikat-Schutz.
Speichert State in einer lokalen JSON-Datei (einfach, kein DB nötig).
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path

log = logging.getLogger(__name__)

STATE_FILE = "risk_state.json"


class RiskManager:
    def __init__(self, config: dict):
        self.cfg = config
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if Path(STATE_FILE).exists():
            try:
                with open(STATE_FILE) as f:
                    state = json.load(f)
                # Reset Daily Loss wenn neuer Tag
                if state.get("date") != str(date.today()):
                    state["daily_loss_usdc"] = 0.0
                    state["date"] = str(date.today())
                    self._save_state(state)
                return state
            except Exception as e:
                log.warning(f"State laden fehlgeschlagen: {e}, erstelle neu")

        return {
            "date": str(date.today()),
            "daily_loss_usdc": 0.0,
            "open_positions": {},   # condition_id -> {size, action, timestamp}
            "trade_log": [],
        }

    def _save_state(self, state: dict = None):
        if state is None:
            state = self.state
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

    def can_trade(self, decision: dict) -> tuple[bool, str]:
        """
        Prüft ob ein Trade erlaubt ist.
        Returns: (erlaubt: bool, grund: str)
        """
        # 1. Tagesverlust prüfen
        if self.state["daily_loss_usdc"] >= self.cfg["max_daily_loss_usdc"]:
            return False, f"Daily Loss Limit erreicht: ${self.state['daily_loss_usdc']:.2f}"

        # 2. Max offene Positionen
        open_count = len(self.state["open_positions"])
        if open_count >= self.cfg["max_open_positions"]:
            return False, f"Max Positionen erreicht: {open_count}/{self.cfg['max_open_positions']}"

        # 3. Doppel-Trade auf gleichen Markt verhindern
        question = decision.get("question", "")
        for pos in self.state["open_positions"].values():
            if pos.get("question") == question:
                return False, f"Bereits Position in diesem Markt"

        return True, "OK"

    def record_trade(self, decision: dict, order_response: dict):
        """Speichert einen ausgeführten Trade."""
        condition_id = decision.get("yes_token_id", "unknown")
        self.state["open_positions"][condition_id] = {
            "question": decision["question"],
            "action": decision["action"],
            "size_usdc": self.cfg["trade_size_usdc"],
            "entry_price": decision["yes_price"] if decision["action"] == "BUY_YES" else decision["no_price"],
            "timestamp": datetime.now().isoformat(),
            "order_id": order_response.get("orderID", "unknown"),
        }
        self.state["trade_log"].append({
            "timestamp": datetime.now().isoformat(),
            "question": decision["question"][:80],
            "action": decision["action"],
            "confidence": decision["confidence"],
            "size_usdc": self.cfg["trade_size_usdc"],
            "reasoning": decision.get("reasoning", ""),
        })
        self._save_state()
        log.info(f"Trade gespeichert. Offene Positionen: {len(self.state['open_positions'])}")

    def record_loss(self, amount_usdc: float):
        """Bucht einen Verlust (bei Position-Auflösung aufrufen)."""
        self.state["daily_loss_usdc"] += amount_usdc
        self._save_state()

    def get_summary(self) -> dict:
        return {
            "daily_loss_usdc": self.state["daily_loss_usdc"],
            "open_positions": len(self.state["open_positions"]),
            "total_trades_today": len([
                t for t in self.state["trade_log"]
                if t["timestamp"].startswith(str(date.today()))
            ]),
        }
