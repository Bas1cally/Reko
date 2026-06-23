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

# Verzeichnisse fuer Daten / State (per ENV ueberschreibbar, z.B. fuer Docker).
DATA_DIR = Path(os.getenv("BOT_DATA_DIR") or (BOT_DIR / "data" / "raw"))
DB_PATH = Path(os.getenv("BOT_DB_PATH") or (BOT_DIR / "state.db"))

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
KELLY_FRACTION = _get_float("KELLY_FRACTION", 0.5)   # 1/2-Kelly (aggressiv)
MAX_STAKE_FRACTION = _get_float("MAX_STAKE_FRACTION", 0.05)  # Cap pro Wette
BANKROLL = _get_float("BANKROLL", 0.0)               # 0 = keine EUR-Anzeige
MAX_NEWS_ADJUSTMENT = _get_float("MAX_NEWS_ADJUSTMENT", 0.08)
MAX_MODEL_MARKET_GAP = _get_float("MAX_MODEL_MARKET_GAP", 0.25)
SHARP_BOOKMAKERS = _get_list("SHARP_BOOKMAKERS", ["pinnacle"])
ENABLE_NEWS = _get_bool("ENABLE_NEWS", True)
TOURS = _get_list("TOURS", ["atp", "wta"])

# Markt-bewusste Wahrscheinlichkeit: p_final = BLEND*p_model + (1-BLEND)*p_sharp
MODEL_MARKET_BLEND = _get_float("MODEL_MARKET_BLEND", 0.5)
# Extra-EV-Aufschlag, wenn KEIN scharfer Buchmacher als Anker verfuegbar ist.
NO_SHARP_EV_PENALTY = _get_float("NO_SHARP_EV_PENALTY", 0.03)
# De-Vig-Methode: "power" (Favorite-Longshot-Bias-korrigiert) oder "multiplicative"
DEVIG_METHOD = _get("DEVIG_METHOD", "power").lower()

# Zuverlaessigkeits-Filter
MIN_PLAYER_MATCHES = int(_get_float("MIN_PLAYER_MATCHES", 20))
MIN_SURFACE_MATCHES = int(_get_float("MIN_SURFACE_MATCHES", 5))
MIN_BOOKS = int(_get_float("MIN_BOOKS", 2))

# Tracking / CLV
ENABLE_TRACKING = _get_bool("ENABLE_TRACKING", True)
CLOSE_WINDOW_MIN = int(_get_float("CLOSE_WINDOW_MIN", 60))  # Closing-Fenster (Min.)

# Benachrichtigungen
NOTIFY_SUMMARY = _get_bool("NOTIFY_SUMMARY", True)
NOTIFY_ERRORS = _get_bool("NOTIFY_ERRORS", True)

# ----- Modell-Parameter (Elo) -----
ELO_START = 1500.0
ELO_K_NUMERATOR = _get_float("ELO_K_NUMERATOR", 250.0)  # K = NUM/(n+OFFSET)^EXP
ELO_K_OFFSET = _get_float("ELO_K_OFFSET", 5.0)
ELO_K_EXPONENT = _get_float("ELO_K_EXPONENT", 0.4)
SURFACE_BLEND = _get_float("SURFACE_BLEND", 0.6)   # Gewicht Surface-Elo
ELO_USE_MOV = _get_bool("ELO_USE_MOV", True)       # Margin-of-Victory-Gewichtung

# Wie viele Jahre Historie beim Training geladen werden.
HISTORY_YEARS = 15

# The Odds API
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_REGIONS = "eu,uk"     # welche Buchmacher-Regionen abgefragt werden
ODDS_MARKET = "h2h"        # Moneyline (Matchsieger)
MIN_API_QUOTA_WARN = int(_get_float("MIN_API_QUOTA_WARN", 50))

# ----- Logging -----
LOG_FILE = BOT_DIR / "bot.log"
LOG_LEVEL = _get("LOG_LEVEL", "INFO").upper()
