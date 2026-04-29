import os
import logging
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

log = logging.getLogger(__name__)
CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137


class PolymarketTrader:
    def __init__(self, config: dict):
        self.cfg = config
        self.client = self._init_client()

    def _init_client(self):
        pk = os.getenv("POLYMARKET_PRIVATE_KEY", "")
        funder = os.getenv("POLYMARKET_FUNDER_ADDRESS", "")
        if not pk or not funder:
            raise ValueError("POLYMARKET_PRIVATE_KEY und POLYMARKET_FUNDER_ADDRESS fehlen")
        client = ClobClient(CLOB_HOST, key=pk, chain_id=CHAIN_ID,
                            signature_type=0, funder=funder)
        client.set_api_creds(client.create_or_derive_api_creds())
        log.info("CLOB Client initialisiert")
        return client

    def execute(self, decision: dict) -> dict:
        action = decision["action"]
        size = float(decision.get("trade_size", self.cfg["trade_size_usdc"]))

        if action == "BUY_YES":
            token_id = decision["yes_token_id"]
            price = decision["yes_price"]
        elif action == "BUY_NO":
            token_id = decision["no_token_id"]
            price = decision["no_price"]
        else:
            return {"status": "skipped"}

        dry_run = self.cfg.get("dry_run", True)
        if dry_run:
            log.info(f"[DRY RUN] {action} ${size} @ {price:.2f}")
            return {"status": "dry_run", "orderID": f"DRY_{token_id[:8]}", "action": action, "size": size}

        try:
            order_args = MarketOrderArgs(token_id=token_id, amount=size, side=BUY, order_type=OrderType.FOK)
            signed = self.client.create_market_order(order_args)
            resp = self.client.post_order(signed, OrderType.FOK)
            log.info(f"Order ausgefuehrt: {resp}")
            return {"status": "executed", "action": action, "size": size, **resp}
        except Exception as e:
            log.error(f"Order Fehler: {e}")
            return {"status": "error", "error": str(e)}
