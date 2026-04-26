"""
bot.py - Hauptdatei des Polymarket AI Trading Bots
Strategie: Contrarian - Claude analysiert Märkte mit Web Search und tradet bei hoher Konfidenz

Setup:
  pip install -r requirements.txt
  cp .env.example .env  # dann Keys eintragen
  python bot.py         # Dry Run (kein echtes Trading)
  DRY_RUN=false python bot.py  # Live Trading
"""

import os
import time
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from scanner import MarketScanner
from analyst import ClaudeAnalyst
from trader import PolymarketTrader
from risk import RiskManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ============================================================
# KONFIGURATION
# ============================================================
CONFIG = {
    "dry_run": os.getenv("DRY_RUN", "true").lower() != "false",
    "trade_size_usdc": float(os.getenv("TRADE_SIZE_USDC", "5.0")),
    "max_open_positions": int(os.getenv("MAX_POSITIONS", "5")),
    "max_daily_loss_usdc": float(os.getenv("MAX_DAILY_LOSS", "25.0")),
    "min_yes_price": 0.03,
    "max_yes_price": 0.50,
    "min_volume_usdc": 500,
    "max_spread": 0.10,
    "min_confidence": float(os.getenv("MIN_CONFIDENCE", "0.70")),
    "claude_model": "claude-opus-4-5",
    "scan_interval_seconds": int(os.getenv("SCAN_INTERVAL", "60")),
    "max_markets_per_cycle": int(os.getenv("MAX_MARKETS_PER_CYCLE", "5")),
}
# ============================================================


def run_cycle(scanner, analyst, trader, risk):
    now = datetime.now().strftime("%H:%M:%S")
    summary = risk.get_summary()

    print(f"\n{'='*60}")
    print(f"  ZYKLUS {now}  |  Positionen: {summary['open_positions']}/{CONFIG['max_open_positions']}  |  Tagesverlust: ${summary['daily_loss_usdc']:.2f}")
    print(f"{'='*60}")

    candidates = scanner.get_tradable_markets()
    if not candidates:
        log.info("Keine Kandidaten gefunden")
        return

    print(f"\n  {len(candidates)} Contrarian-Kandidaten gefunden\n")
    trades_executed = 0

    for market in candidates:
        print(f"  >> {market['question'][:70]}...")
        print(f"     YES: {market['yes_price']:.2f} | Spread: {market['spread']:.3f} | Vol24h: ${market['volume_24h']:,.0f}")

        can_trade, reason = risk.can_trade({"question": market["question"]})
        if not can_trade:
            print(f"     SKIP (Risk): {reason}\n")
            continue

        decision = analyst.analyse(market)
        action = decision["action"]
        confidence = decision["confidence"]

        print(f"     Claude: {action} | Konfidenz: {confidence:.0%}")
        if decision.get("reasoning"):
            print(f"     Reasoning: {decision['reasoning']}")
        if decision.get("key_finding"):
            print(f"     Finding: {decision['key_finding']}")

        if action == "SKIP" or confidence < CONFIG["min_confidence"]:
            print(f"     -> SKIP\n")
            continue

        order_result = trader.execute(decision)
        status = order_result.get("status", "unknown")

        if status in ("executed", "dry_run"):
            risk.record_trade(decision, order_result)
            trades_executed += 1
            prefix = "[DRY RUN] " if status == "dry_run" else ""
            print(f"     -> {prefix}TRADE: {action} ${CONFIG['trade_size_usdc']}\n")
        else:
            print(f"     -> FEHLER: {order_result.get('error', 'unbekannt')}\n")

    print(f"\n  Zyklus fertig. {trades_executed} Trade(s). Nächster Scan in {CONFIG['scan_interval_seconds']//60} Min.\n")


def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║   POLYMARKET AI BOT  |  Contrarian + Claude Analysis     ║
╚══════════════════════════════════════════════════════════╝
""")
    mode = "DRY RUN" if CONFIG["dry_run"] else "LIVE TRADING"
    print(f"  Modus:          {mode}")
    print(f"  Trade Size:     ${CONFIG['trade_size_usdc']}")
    print(f"  Min Konfidenz:  {CONFIG['min_confidence']:.0%}")
    print(f"  Scan Intervall: {CONFIG['scan_interval_seconds']}s")
    print(f"  Max Positionen: {CONFIG['max_open_positions']}")
    print(f"  Max Tagesverlust: ${CONFIG['max_daily_loss_usdc']}\n")

    scanner = MarketScanner(CONFIG)
    analyst = ClaudeAnalyst(CONFIG)
    trader = PolymarketTrader(CONFIG)
    risk = RiskManager(CONFIG)

    log.info("Bot gestartet")

    while True:
        try:
            run_cycle(scanner, analyst, trader, risk)
        except KeyboardInterrupt:
            log.info("Bot gestoppt (Ctrl+C)")
            break
        except Exception as e:
            log.error(f"Fehler im Zyklus: {e}", exc_info=True)
            log.info("Warte 60s...")
            time.sleep(60)
            continue

        time.sleep(CONFIG["scan_interval_seconds"])


if __name__ == "__main__":
    main()
