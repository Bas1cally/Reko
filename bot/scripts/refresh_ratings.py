"""Periodischer Refresh: neue Match-Ergebnisse laden + Elo neu berechnen.

Per Cron z.B. woechentlich laufen lassen (siehe deploy/crontab.example).
"""
from __future__ import annotations

import sys

from ..data import fetch_history
from ..model import train


def main() -> int:
    print("== Schritt 1/2: Historie aktualisieren ==")
    fetch_history.main()
    print("\n== Schritt 2/2: Elo-Ratings neu berechnen ==")
    return train.main()


if __name__ == "__main__":
    sys.exit(main())
