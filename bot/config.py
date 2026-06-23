"""Zentrale Konfiguration: laedt .env und stellt Parameter als Konstanten bereit.

Alle Strategie-Parameter haben sinnvolle Defaults, koennen aber per .env
ueberschrieben werden. Siehe .env.example.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# .env aus dem bot/-Verzeichnis laden (egal von wo aus gestartet wird).
BOT_DIR = Path(__file__).resolve().parent
load_dotenv(BOT_DIR / ".env")

# Verzeichnisse fuer Daten / State.
DATA_DIR = BOT_DIR / "data" / "raw"          # heruntergeladene Sackmann-CSVs
DB_PATH = BOT_DIR / "state.db"               # SQLite: Ratings + gesendete Bets

DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "ja"}


def _get_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


# ----- Secrets / API-Keys -----
THE_ODDS_API_KEY = _get("THE_ODDS_API_KEY")
TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _get("TELEGRAM_CHAT_ID")
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = _get("ANTHROPIC_MODEL", "claude-opus-4-8")
NEWS_API_KEY = _get("NEWS_API_KEY")

# ----- Strategie-Parameter -----
MIN_EV = _get_float("MIN_EV", 0.05)
MAX_ODDS = _get_float("MAX_ODDS", 8.0)
KELLY_FRACTION = _get_float("KELLY_FRACTION", 0.25)
MAX_NEWS_ADJUSTMENT = _get_float("MAX_NEWS_ADJUSTMENT", 0.08)
MAX_MODEL_MARKET_GAP = _get_float("MAX_MODEL_MARKET_GAP", 0.25)
SHARP_BOOKMAKERS = _get_list("SHARP_BOOKMAKERS", ["pinnacle"])
ENABLE_NEWS = _get_bool("ENABLE_NEWS", True)
TOURS = _get_list("TOURS", ["atp", "wta"])

# ----- Modell-Parameter (Elo) -----
ELO_START = 1500.0
ELO_K_NUMERATOR = 250.0     # K = NUM / (n + OFFSET)^EXP  (FiveThirtyEight-Variante)
ELO_K_OFFSET = 5.0
ELO_K_EXPONENT = 0.4
SURFACE_BLEND = 0.6         # Gewicht der Surface-Elo (Rest -> Overall-Elo)

# Wie viele Jahre Historie beim Training geladen werden.
HISTORY_YEARS = 15

# The Odds API
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_REGIONS = "eu,uk"     # welche Buchmacher-Regionen abgefragt werden
ODDS_MARKET = "h2h"        # Moneyline (Matchsieger)
