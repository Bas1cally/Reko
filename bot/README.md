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

- **Elo-Modell = Baseline** (Surface-Elo + Margin-of-Victory), keine Edge gegen
  scharfe Bücher (Pinnacle).
- **Markt-bewusste Wahrscheinlichkeit:** Modell wird mit dem scharfen Konsens
  gemischt (`MODEL_MARKET_BLEND`) → robuster, weniger Fehlwetten.
- **Claude-News-Layer = Kern-Edge:** liest Verletzungen/Conditions/Fatigue und
  nudgt die Wahrscheinlichkeit, *bevor* weiche Bücher nachziehen.
- **Ziel = weiche Buchmacher / frühe Linien**, nicht Pinnacle selbst.
- **Zuverlässigkeits-Filter** (Mindest-Matches, Min. Buchmacher, Power-De-Vig)
  verhindern Schein-Value aus instabilen Daten.
- **CLV** (Closing Line Value) ist der Maßstab, ob die Edge echt ist — der Bot
  misst ihn automatisch (siehe Tracking).

> ⚠️ **½-Kelly ist aggressiv.** Bei leicht fehlkalibriertem Modell steigt das
> Ruin-Risiko. Schutz: Stake-Cap (`MAX_STAKE_FRACTION`) + CLV-Monitor. Ist der
> mittlere CLV über ~100+ Wetten nicht klar positiv, hat der Bot keine reale
> Edge → Einsatz runter oder pausieren.

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

## Backtest & Tuning (vor echtem Geld!)

```bash
python -m bot.backtest               # Accuracy, Brier, Log-Loss, Kalibrierung
python -m bot.tune                   # beste Elo-Parameter (in .env übernehmen)
```

Ein gut kalibriertes Modell ist Voraussetzung für echten Value.

## Self-Check & Inspektion

```bash
python -m bot.doctor                 # prüft Keys, Daten, aktive Features
python -m bot.cli top atp            # Top-Spieler nach Elo
python -m bot.cli rating "Alcaraz"   # Elo eines Spielers (je Belag)
python -m bot.cli bets               # letzte Empfehlungen + Status/CLV
```

## Laufen lassen

```bash
python -m bot.run --dry-run          # nur Konsole, kein Telegram
python -m bot.run --no-news          # reine Elo-Baseline (ohne Claude)
python -m bot.run --test-telegram    # einmalige Telegram-Test-Nachricht
python -m bot.run                    # echter Lauf -> Telegram bei Value
```

## Tracking / CLV (Feedback-Loop)

Der Bot speichert jede Empfehlung und misst, ob er den Markt schlägt:

```bash
python -m bot.track close            # Closing-Quote + CLV erfassen (stündlich)
python -m bot.track grade            # Ergebnisse holen + P&L berechnen
python -m bot.track report --send    # CLV / ROI / P&L (optional per Telegram)
```

**CLV ist der wichtigste Indikator**: positiv über viele Wetten = echte Edge.

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
Tracking- und Ratings-Refresh-Jobs per Cron (siehe `crontab.example`).

**Docker** (Alternative):
```bash
docker compose -f bot/docker-compose.yml run --rm bot python -m bot.scripts.refresh_ratings
docker compose -f bot/docker-compose.yml run --rm bot python -m bot.run
```
State (`state.db` + CSVs) liegt im Named Volume `botdata`. Host-Cron ruft die
`docker compose run`-Kommandos auf.

## Struktur

```
bot/
  config.py            # ENV + Parameter
  logging_setup.py     # zentrales Logging (Konsole + bot.log)
  data/fetch_history.py# Sackmann-CSVs laden
  model/elo.py         # Elo-Engine (rein, testbar)
  model/score.py       # Score-Parser + Margin-of-Victory
  model/train.py       # Ratings -> state.db
  odds/odds_api.py     # The Odds API (Quoten + Scores + Quota)
  matching/names.py    # Namens-Matching Odds<->Daten
  news/analyze.py      # Claude News-Layer (Kern-Edge)
  value/engine.py      # Power-De-Vig, Markt-Blend, EV, Kelly, Filter
  notify/telegram.py   # Telegram (Bets + Summary + Fehler-Alerts)
  storage/db.py        # SQLite: Ratings + Dedupe + Tracking
  run.py               # Haupt-Pipeline
  track.py             # CLV- & Ergebnis-Tracking
  backtest.py          # Modell-Güte
  tune.py              # Parameter-Grid-Search
  doctor.py            # Self-Check
  cli.py               # Inspektion (Ratings/Bets)
  scripts/refresh_ratings.py
  deploy/              # Cron / systemd
  Dockerfile, docker-compose.yml
  tests/
```

## Parameter (in `.env` anpassbar)

| Variable | Default | Bedeutung |
|---|---|---|
| `MIN_EV` | 0.05 | Mindest-Erwartungswert (5 %) |
| `MAX_ODDS` | 8.0 | Quoten-Obergrenze (Sanity) |
| `KELLY_FRACTION` | 0.5 | Bruchteil-Kelly (½ = aggressiv) |
| `MAX_STAKE_FRACTION` | 0.05 | harter Stake-Cap pro Wette |
| `BANKROLL` | 0 | für €-Anzeige (0 = nur %) |
| `MODEL_MARKET_BLEND` | 0.5 | Mischung Modell ↔ Sharp |
| `DEVIG_METHOD` | power | De-Vig (power/multiplicative) |
| `MIN_PLAYER_MATCHES` | 20 | Mindest-Historie je Spieler |
| `MIN_BOOKS` | 2 | Mindestzahl weicher Buchmacher |
| `ELO_USE_MOV` | true | Margin-of-Victory-Gewichtung |
| `MAX_NEWS_ADJUSTMENT` | 0.08 | max. News-Nudge (±8 %) |
| `SHARP_BOOKMAKERS` | pinnacle | scharfe Referenz-Bücher |
| `ENABLE_NEWS` | true | Claude-News-Layer an/aus |
| `ENABLE_TRACKING` | true | CLV-/Ergebnis-Tracking |
| `TOURS` | atp,wta | Touren |

Optimale `ELO_*`/`SURFACE_BLEND`-Werte liefert `python -m bot.tune`.
