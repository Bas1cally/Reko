"""Backtest der Modell-Guete (Walk-Forward, out-of-sample).

Geht alle Matches chronologisch durch, sagt JEDES Match *vor* dem Elo-Update
voraus und bewertet danach: Accuracy, Brier-Score, Log-Loss und eine
Kalibrierungs-Tabelle. Das ist der wichtigste Check VOR echtem Geldeinsatz -
ein Modell, das nicht kalibriert ist, produziert Schein-Value.

Damit die Vorhersage unabhaengig vom Ergebnis ist, wird je Match deterministisch
ein "Spieler 1" gewaehlt (alphabetisch nach Schluessel) und vorhergesagt, ob
dieser gewinnt.

Hinweis: ROI/CLV gegen echte Quoten braucht eine historische Quoten-Datei (z.B.
tennis-data.co.uk) und ist als Erweiterung vorgesehen; hier wird die Modell-
Kalibrierung geprueft, die Voraussetzung fuer jeden Value ist.
"""
from __future__ import annotations

import csv
import math
import sys

from . import config
from .matching.names import normalize_key
from .model import elo
from .model.train import _PlayerState  # Wiederverwendung der State-Struktur

SURFACES = {"hard", "clay", "grass"}
EVAL_YEARS = 2  # auf den letzten N Jahren auswerten (Rest = Warmup)


def _iter_with_date(tour: str):
    rows = []
    for path in sorted(config.DATA_DIR.glob(f"{tour}_matches_*.csv")):
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                w, l, date = row.get("winner_name"), row.get("loser_name"), row.get("tourney_date")
                if not (w and l and date):
                    continue
                try:
                    sort_key = (int(date), int(row.get("match_num") or 0))
                except ValueError:
                    continue
                rows.append((sort_key, (row.get("surface") or "").strip().lower(), w, l))
    rows.sort(key=lambda r: r[0])
    for (date, _num), surface, w, l in rows:
        yield date // 10000, surface, w, l


def _predict(states, w_key, l_key, surface, player1_is_winner):
    """Blended Wahrscheinlichkeit, dass 'Spieler 1' gewinnt."""
    w = states.get(w_key)
    l = states.get(l_key)
    w_overall = w.overall if w else config.ELO_START
    l_overall = l.overall if l else config.ELO_START
    if surface in SURFACES:
        w_surf = getattr(w, surface) if w else config.ELO_START
        l_surf = getattr(l, surface) if l else config.ELO_START
    else:
        w_surf, l_surf = w_overall, l_overall
    p_w = elo.blended_win_probability(w_overall, w_surf, l_overall, l_surf)
    return p_w if player1_is_winner else (1.0 - p_w)


def _update(states, w_name, l_name, surface):
    from .model.train import _get, _update_dimension  # lokale Wiederverwendung
    winner = _get(states, w_name)
    loser = _get(states, l_name)
    _update_dimension(winner, loser, "overall", None)
    winner.n_overall += 1
    loser.n_overall += 1
    if surface in SURFACES:
        _update_dimension(winner, loser, surface, surface)
        winner.n[surface] += 1
        loser.n[surface] += 1


def backtest_tour(tour: str, eval_years: int = EVAL_YEARS):
    states: dict = {}
    preds: list[tuple[float, int]] = []  # (p_player1, label_player1_won)
    years = [y for y, *_ in _iter_with_date(tour)]
    if not years:
        return None
    cutoff = max(years) - eval_years + 1

    for year, surface, w_name, l_name in _iter_with_date(tour):
        w_key, l_key = normalize_key(w_name), normalize_key(l_name)
        if year >= cutoff:
            # Deterministische, ergebnis-unabhaengige Spieler-1-Wahl.
            player1_is_winner = w_key < l_key
            p1 = _predict(states, w_key, l_key, surface, player1_is_winner)
            label = 1 if player1_is_winner else 0
            preds.append((p1, label))
        _update(states, w_name, l_name, surface)

    return _metrics(tour, preds)


def _metrics(tour: str, preds: list[tuple[float, int]]):
    n = len(preds)
    if n == 0:
        return None
    brier = sum((p - y) ** 2 for p, y in preds) / n
    eps = 1e-12
    logloss = -sum(
        y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps))
        for p, y in preds
    ) / n
    acc = sum(1 for p, y in preds if (p >= 0.5) == bool(y)) / n

    print(f"\n=== Backtest {tour.upper()} ({n} Matches, letzte {EVAL_YEARS} Jahre) ===")
    print(f"  Accuracy : {acc*100:.1f}%")
    print(f"  Brier    : {brier:.4f}  (kleiner = besser; 0.25 = Muenzwurf)")
    print(f"  Log-Loss : {logloss:.4f}")
    print("  Kalibrierung (Vorhersage-Bucket -> tatsaechliche Trefferrate):")
    for lo in [i / 10 for i in range(0, 10)]:
        hi = lo + 0.1
        bucket = [y for p, y in preds if lo <= p < hi]
        if bucket:
            print(f"    {lo:.1f}-{hi:.1f}: vorhergesagt ~{(lo+hi)/2:.2f}, "
                  f"real {sum(bucket)/len(bucket):.2f}  (n={len(bucket)})")
    return {"tour": tour, "n": n, "accuracy": acc, "brier": brier, "logloss": logloss}


def main() -> int:
    any_done = False
    for tour in config.TOURS:
        if backtest_tour(tour) is not None:
            any_done = True
    if not any_done:
        print("Keine Daten. Bitte zuerst: python -m bot.data.fetch_history")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
