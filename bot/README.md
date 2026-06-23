# 🎾 Tennis Value-Betting Bot

Hintergrund-Bot für den VPS (Hetzner): holt täglich Tennis-Matchups + Buchmacher-
Quoten, berechnet mit einem **oberflächen-spezifischen Elo-Modell** faire
Wahrscheinlichkeiten, lässt **Claude** aktuelle News/Verletzungen als Kontext-Layer
einfließen, erkennt **+EV (Value) Wetten gegen weiche Buchmacher** und schickt bei
einem Treffer eine **Telegram-Nachricht**.

> ⚠️ **Ehrlicher Hinweis:** „Value" = positiver Erwartungswert *laut Modell*. Das
> ist keine Gewinngarantie. Der Bot platziert keine Wetten automatisch, er gibt
> Empfehlungen. **Vor echtem Geld** unbedingt den Backtest laufen lassen.

## Wo die Edge liegt

- **Elo-Modell = Baseline**, keine Edge gegen scharfe Bücher (Pinnacle).
- **Claude-News-Layer = Kern-Edge:** liest Verletzungen/Conditions/Fatigue und
  nudgt die Wahrscheinlichkeit, *bevor* weiche Bücher nachziehen.
- **Ziel = weiche Buchmacher / frühe Linien**, nicht Pinnacle selbst.
- **CLV** (Closing Line Value) ist der Maßstab, ob die Edge echt ist.

## Setup (lokal oder VPS)

```bash
cd bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # dann .env ausfüllen (API-Keys)
```

Benötigte Keys in `.env`:
- `THE_ODDS_API_KEY` — https://the-odds-api.com (Free-Tier reicht für 1–2 Läufe/Tag)
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — Bot via @BotFather, Chat-ID via @userinfobot
- `ANTHROPIC_API_KEY` — für den Claude-News-Layer
- `NEWS_API_KEY` — https://newsapi.org (optional; ohne ihn läuft nur die Baseline)

## Modell aufbauen

```bash
python -m bot.data.fetch_history     # lädt Jeff-Sackmann-CSVs (ATP/WTA)
python -m bot.model.train            # baut state.db (Elo-Ratings)
```

Sanity-Check: Beim Training werden die Top-5 je Tour ausgegeben — dort sollten
aktuelle Top-Spieler stehen.

## Backtest (vor echtem Geld!)

```bash
python -m bot.backtest               # Accuracy, Brier, Log-Loss, Kalibrierung
```

Ein gut kalibriertes Modell ist Voraussetzung für echten Value.

## Laufen lassen

```bash
python -m bot.run --dry-run          # nur Konsole, kein Telegram
python -m bot.run --no-news          # reine Elo-Baseline (ohne Claude)
python -m bot.run --test-telegram    # einmalige Telegram-Test-Nachricht
python -m bot.run                    # echter Lauf -> Telegram bei Value
```

## Tests

```bash
pip install pytest
pytest bot/tests
```

## Deployment auf dem VPS

Projekt z.B. nach `/opt/reko-bot`, venv anlegen, `.env` füllen, dann **eine** der
beiden Varianten:

**Cron** (einfach): siehe `deploy/crontab.example`.

**systemd-Timer** (sauberer):
```bash
sudo cp deploy/reko-bot.service deploy/reko-bot.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now reko-bot.timer
```
Ratings-Refresh per zusätzlichem Cron-Eintrag (siehe `crontab.example`).

## Struktur

```
bot/
  config.py            # ENV + Parameter
  data/fetch_history.py# Sackmann-CSVs laden
  model/elo.py         # Elo-Engine (rein, testbar)
  model/train.py       # Ratings -> state.db
  odds/odds_api.py     # The Odds API (Tennis)
  matching/names.py    # Namens-Matching Odds<->Daten
  news/analyze.py      # Claude News-Layer (Kern-Edge)
  value/engine.py      # De-Vig, EV, Kelly, Filter
  notify/telegram.py   # Telegram-Nachricht
  storage/db.py        # SQLite: Ratings + Dedupe
  run.py               # Haupt-Pipeline
  backtest.py          # Modell-Güte
  scripts/refresh_ratings.py
  deploy/              # Cron / systemd
  tests/
```

## Parameter (in `.env` anpassbar)

| Variable | Default | Bedeutung |
|---|---|---|
| `MIN_EV` | 0.05 | Mindest-Erwartungswert (5 %) |
| `MAX_ODDS` | 8.0 | Quoten-Obergrenze (Sanity) |
| `KELLY_FRACTION` | 0.25 | Bruchteil-Kelly für Stake |
| `MAX_NEWS_ADJUSTMENT` | 0.08 | max. News-Nudge (±8 %) |
| `MAX_MODEL_MARKET_GAP` | 0.25 | verwirf, wenn Modell vs. Sharp zu weit weg |
| `SHARP_BOOKMAKERS` | pinnacle | scharfe Referenz-Bücher |
| `ENABLE_NEWS` | true | Claude-News-Layer an/aus |
| `TOURS` | atp,wta | Touren |
