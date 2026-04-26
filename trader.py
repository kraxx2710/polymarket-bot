"""
trader.py
Führt Orders über die Polymarket CLOB API aus.
Nutzt py-clob-client für Authentication und Order Signing.
"""

import os
import logging
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

log = logging.getLogger(__name__)

CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon


class PolymarketTrader:
    def __init__(self, config: dict):
        self.cfg = config
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialisiert den CLOB Client mit Credentials aus .env"""
        private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
        funder = os.getenv("POLYMARKET_FUNDER_ADDRESS")

        if not private_key or not funder:
            raise ValueError(
                "POLYMARKET_PRIVATE_KEY und POLYMARKET_FUNDER_ADDRESS müssen in .env gesetzt sein"
            )

        self.client = ClobClient(
            CLOB_HOST,
            key=private_key,
            chain_id=CHAIN_ID,
            signature_type=1,   # Für email/Magic Wallet - auf 0 ändern für MetaMask
            funder=funder,
        )
        self.client.set_api_creds(self.client.create_or_derive_api_creds())
        log.info("CLOB Client initialisiert")

    def get_balance(self) -> float:
        """Gibt USDC Balance zurück."""
        try:
            balance = self.client.get_balance()
            return float(balance)
        except Exception as e:
            log.error(f"Balance Fehler: {e}")
            return 0.0

    def execute(self, decision: dict) -> dict:
        """
        Führt einen Trade aus basierend auf Claude's Entscheidung.

        Im DRY RUN Modus wird kein echter Trade platziert.
        """
        action = decision["action"]
        size = self.cfg["trade_size_usdc"]

        # Token ID basierend auf Action auswählen
        if action == "BUY_YES":
            token_id = decision["yes_token_id"]
            price = decision["yes_price"]
        elif action == "BUY_NO":
            token_id = decision["no_token_id"]
            price = decision["no_price"]
        else:
            return {"status": "skipped", "reason": "Action ist SKIP"}

        if self.cfg["dry_run"]:
            log.info(f"[DRY RUN] Würde kaufen: {action} | Token {token_id[:16]}... | ${size} @ {price:.2f}")
            return {
                "status": "dry_run",
                "action": action,
                "token_id": token_id,
                "size_usdc": size,
                "price": price,
                "orderID": "DRY_RUN_" + token_id[:8],
            }

        # Echter Trade
        try:
            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=size,
                side=BUY,
                order_type=OrderType.FOK,  # Fill-or-Kill: sofort oder gar nicht
            )
            signed_order = self.client.create_market_order(order_args)
            response = self.client.post_order(signed_order, OrderType.FOK)

            log.info(f"Order ausgeführt: {response}")
            return {
                "status": "executed",
                "action": action,
                "token_id": token_id,
                "size_usdc": size,
                "price": price,
                **response,
            }

        except Exception as e:
            log.error(f"Order Fehler: {e}")
            return {"status": "error", "error": str(e)}
