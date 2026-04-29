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
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

CONFIG = {
    "dry_run": os.getenv("DRY_RUN", "true").lower() != "false",
    "trade_size_usdc": float(os.getenv("TRADE_SIZE_USDC", "5.0")),
    "trade_size_crypto": float(os.getenv("TRADE_SIZE_CRYPTO", "5.0")),
    "trade_size_economy": float(os.getenv("TRADE_SIZE_ECONOMY", "10.0")),
    "max_open_positions": int(os.getenv("MAX_POSITIONS", "6")),
    "max_daily_loss_usdc": float(os.getenv("MAX_DAILY_LOSS", "30.0")),
    "min_yes_price": 0.05,
    "max_yes_price": 0.70,
    "min_volume_usdc": 2000,
    "max_spread": 0.08,
    "min_confidence": float(os.getenv("MIN_CONFIDENCE", "0.78")),
    "min_confidence_crypto": float(os.getenv("MIN_CONFIDENCE_CRYPTO", "0.80")),
    "min_confidence_economy": float(os.getenv("MIN_CONFIDENCE_ECONOMY", "0.78")),
    "claude_model": "claude-haiku-4-5-20251001",
    "scan_interval_seconds": int(os.getenv("SCAN_INTERVAL", "900")),
}


def run_cycle(scanner, analyst, trader, risk):
    now = datetime.now().strftime("%H:%M:%S")
    s = risk.summary()
    print(f"\n{'='*55}")
    print(f"  ZYKLUS {now} | Positionen: {s['open_positions']}/{CONFIG['max_open_positions']} | Verlust: ${s['daily_loss']:.2f}")
    print(f"{'='*55}")

    markets = scanner.get_tradable_markets()
    if not markets:
        log.info("Keine Kandidaten")
        return

    print(f"\n  {len(markets)} Maerkte zur Analyse\n")
    trades = 0

    for m in markets:
        print(f"  [{m['category'].upper()}] {m['question'][:65]}...")
        print(f"  YES: {m['yes_price']:.2f} | Tage: {m['days_left']} | Vol: ${m['volume_24h']:,.0f}")

        ok, reason = risk.can_trade(m["question"])
        if not ok:
            print(f"  -> SKIP (Risk: {reason})\n")
            continue

        d = analyst.analyse(m)
        action = d["action"]
        conf = d["confidence"]
        edge = d["edge"]
        min_conf = d["min_confidence"]

        print(f"  Claude: {action} | Konfidenz: {conf:.0%} | Edge: {edge:+.2f}")
        if d.get("reasoning"):
            print(f"  Grund: {d['reasoning']}")
        if d.get("key_finding"):
            print(f"  Finding: {d['key_finding']}")

        if action == "SKIP" or conf < min_conf:
            print(f"  -> SKIP (Konfidenz {conf:.0%} < {min_conf:.0%} oder SKIP)\n")
            continue

        result = trader.execute(d)
        status = result.get("status", "")

        if status in ("executed", "dry_run"):
            risk.record_trade(d, result)
            trades += 1
            prefix = "[DRY RUN] " if status == "dry_run" else ""
            print(f"  -> {prefix}TRADE: {action} ${d['trade_size']}\n")
        else:
            print(f"  -> FEHLER: {result.get('error', 'unbekannt')}\n")

    print(f"\n  {trades} Trade(s). Naechster Scan in {CONFIG['scan_interval_seconds']//60} Min.\n")


def main():
    print("""
╔══════════════════════════════════════════════════════╗
║  POLYMARKET AI BOT  |  Krypto + Wirtschaft + Politik  ║
║  Powered by Claude Haiku + Echtzeit Marktdaten        ║
╚══════════════════════════════════════════════════════╝
""")
    mode = "DRY RUN" if CONFIG["dry_run"] else "LIVE TRADING"
    print(f"  Modus:          {mode}")
    print(f"  Krypto Trade:   ${CONFIG['trade_size_crypto']}")
    print(f"  Eco/Pol Trade:  ${CONFIG['trade_size_economy']}")
    print(f"  Min Konfidenz:  {CONFIG['min_confidence']:.0%}")
    print(f"  Scan Intervall: {CONFIG['scan_interval_seconds']}s")
    print(f"  Max Verlust:    ${CONFIG['max_daily_loss_usdc']}/Tag\n")

    scanner = MarketScanner(CONFIG)
    analyst = ClaudeAnalyst(CONFIG)
    trader = PolymarketTrader(CONFIG)
    risk = RiskManager(CONFIG)

    log.info("Bot gestartet")

    while True:
        try:
            run_cycle(scanner, analyst, trader, risk)
        except KeyboardInterrupt:
            log.info("Bot gestoppt")
            break
        except Exception as e:
            log.error(f"Zyklus Fehler: {e}", exc_info=True)
            time.sleep(60)
            continue
        time.sleep(CONFIG["scan_interval_seconds"])


if __name__ == "__main__":
    main()
