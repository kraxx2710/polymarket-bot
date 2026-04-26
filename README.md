# Polymarket AI Bot

Contrarian Trading Bot der Claude (mit Web Search) nutzt um Prediction Markets zu analysieren.

## Strategie
- Scannt Märkte mit YES-Preis zwischen 5 und 35 Cent (Markt haelt es fuer unwahrscheinlich)
- Claude recherchiert jeden Kandidaten mit Web Search
- Tradet wenn Konfidenz >= 70%
- Risk Manager verhindert Uebertrading und Daily Loss

## Lokales Setup (Mac)

```bash
git clone <dein-repo>
cd polymarket_bot

pip install -r requirements.txt

cp .env.example .env
# .env oeffnen und Keys eintragen

python bot.py    # startet im DRY RUN Modus
```

## Keys holen

**Polymarket Private Key + Wallet Address:**
1. polymarket.com einloggen
2. Profil -> Settings -> API (oder Export Private Key)
3. Private Key kopieren (0x...)
4. Wallet Adresse aus Profil kopieren (0x...)

**Anthropic API Key:**
1. platform.anthropic.com
2. API Keys -> Create Key
3. Sofort kopieren (wird nur einmal gezeigt)
4. Credits kaufen unter Plans & Billing

## Railway Deployment (24/7 ohne Mac)

1. GitHub Repo erstellen (privat!)
2. Code pushen: `git push origin main`
3. railway.app -> New Project -> Deploy from GitHub
4. Repo auswaehlen
5. Variables Tab: alle Werte aus .env eintragen
6. DRY_RUN=false setzen wenn bereit fuer Live Trading
7. Deploy -> Bot laeuft 24/7

**Wichtig:** .env NIEMALS auf GitHub pushen (ist in .gitignore)

## Kosten

- Railway Hobby Plan: ~$5/Monat
- Anthropic API: ~$0.01-0.05 pro Marktanalyse (je nach Modell)
  Bei MAX_MARKETS_PER_CYCLE=5 und SCAN_INTERVAL=300: ca. $0.50-2.50/Tag

## Konfiguration (Env Vars in Railway)

| Variable | Default | Beschreibung |
|---|---|---|
| DRY_RUN | true | false = echtes Trading |
| TRADE_SIZE_USDC | 5.0 | USD pro Trade |
| MAX_POSITIONS | 5 | Max offene Positionen |
| MAX_DAILY_LOSS | 25.0 | Daily Loss Stop in USD |
| MIN_CONFIDENCE | 0.70 | Min Claude Konfidenz |
| SCAN_INTERVAL | 300 | Sekunden zwischen Scans |
| MAX_MARKETS_PER_CYCLE | 5 | Maerkte pro Analyse |

## Dateien

```
bot.py          Hauptschleife und Orchestrierung
scanner.py      Gamma API: Maerkte filtern
analyst.py      Claude: KI-Analyse mit Web Search
trader.py       CLOB API: Orders ausfuehren
risk.py         Positionslimits und Daily Loss
```

## Wichtige Hinweise

- Mit kleinen Betragen starten (TRADE_SIZE_USDC=1.0)
- Immer zuerst DRY_RUN=true testen
- Polymarket ist nicht fuer US-User verfuegbar
- Vergangene Performance ist keine Garantie fuer zukuenftige Ergebnisse
