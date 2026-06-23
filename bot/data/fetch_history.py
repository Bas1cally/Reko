"""Laedt historische Match-Daten von Jeff Sackmanns GitHub-Repos.

Quelle (frei, Gold-Standard):
  https://github.com/JeffSackmann/tennis_atp
  https://github.com/JeffSackmann/tennis_wta

Pro Jahr eine CSV (``atp_matches_2024.csv`` etc.). Aeltere Jahre werden nur
geladen, wenn sie noch fehlen; das laufende und das Vorjahr werden immer neu
geladen, da Sackmann sie waehrend der Saison aktualisiert.
"""
from __future__ import annotations

import datetime as dt
import sys

import requests

from .. import config

RAW_BASE = "https://raw.githubusercontent.com/JeffSackmann"
REPOS = {"atp": "tennis_atp", "wta": "tennis_wta"}


def _url(tour: str, year: int) -> str:
    return f"{RAW_BASE}/{REPOS[tour]}/master/{tour}_matches_{year}.csv"


def _dest(tour: str, year: int):
    return config.DATA_DIR / f"{tour}_matches_{year}.csv"


def fetch(tours: list[str] | None = None, years: int | None = None) -> list:
    tours = tours or config.TOURS
    years = years or config.HISTORY_YEARS
    current_year = dt.date.today().year
    wanted_years = range(current_year - years + 1, current_year + 1)

    downloaded = []
    for tour in tours:
        if tour not in REPOS:
            print(f"  ! unbekannte Tour '{tour}' uebersprungen")
            continue
        for year in wanted_years:
            dest = _dest(tour, year)
            # Laufendes + Vorjahr immer aktualisieren.
            if dest.exists() and year < current_year - 1:
                continue
            url = _url(tour, year)
            try:
                resp = requests.get(url, timeout=60)
            except requests.RequestException as exc:
                print(f"  ! {tour} {year}: Netzwerkfehler ({exc})")
                continue
            if resp.status_code == 404:
                # Jahr existiert (noch) nicht - normal fuer ganz neue Jahre.
                continue
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            downloaded.append(dest)
            print(f"  + {dest.name} ({len(resp.content)//1024} KB)")
    return downloaded


def main() -> int:
    print(f"Lade Historie ({config.HISTORY_YEARS} Jahre) fuer: {', '.join(config.TOURS)}")
    files = fetch()
    print(f"Fertig. {len(files)} Datei(en) aktualisiert in {config.DATA_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
