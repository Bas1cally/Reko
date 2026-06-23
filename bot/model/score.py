"""Robuster Parser fuer Tennis-Spielstaende (Sackmann ``score``-Spalte).

Beispiele: "6-4 6-3", "7-6(5) 6-7(3) 7-5", "6-2 3-6 6-4 RET", "W/O".
Liefert die von Sieger/Verlierer gewonnenen Spiele (games) und einen
Margin-of-Victory-Multiplikator fuer das Elo-Update.
"""
from __future__ import annotations

import re

_SET_RE = re.compile(r"^(\d+)-(\d+)")


def parse_games(score: str | None) -> tuple[int, int] | None:
    """(games_winner, games_loser) aus dem Score; None wenn unbrauchbar.

    Tiebreak-Klammern werden ignoriert (``7-6(5)`` -> 7-6). Aufgaben (RET) werden
    mit dem bisherigen Stand gewertet; Walkover (W/O) liefert None.
    """
    if not score:
        return None
    s = score.strip().upper()
    if not s or "W/O" in s or "WALKOVER" in s or "DEF" in s:
        return None

    gw = gl = 0
    found = False
    for token in s.split():
        if token in {"RET", "RET.", "ABD", "ABN"}:
            break
        m = _SET_RE.match(token)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        # Unplausible Set-Scores (z.B. defekte Zeilen) ueberspringen.
        if a > 30 or b > 30:
            continue
        gw += a
        gl += b
        found = True
    if not found or (gw == 0 and gl == 0):
        return None
    return gw, gl


def mov_multiplier(score: str | None) -> float:
    """Margin-of-Victory-Multiplikator (~0.8..1.3) fuer den K-Faktor.

    Dominante Siege (hoher Spielanteil) gewichten das Update staerker, knappe
    Siege schwaecher. Liefert 1.0, wenn der Score nicht parsbar ist.
    """
    games = parse_games(score)
    if games is None:
        return 1.0
    gw, gl = games
    total = gw + gl
    if total == 0:
        return 1.0
    # Spielanteil des Siegers 0.5..1.0 -> Faktor um 1.0 herum.
    share = gw / total
    return 0.7 + 0.8 * share
