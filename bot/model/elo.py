"""Oberflaechen-spezifische Elo-Engine fuer Tennis.

Reine, zustandslose Funktionen (gut testbar). Die Trainings-Pipeline in
``train.py`` nutzt diese, um aus historischen Matches Ratings aufzubauen; die
Live-Pipeline nutzt :func:`blended_win_probability`, um die Modell-Baseline
fuer ein anstehendes Match zu berechnen.

Variante in Anlehnung an FiveThirtyEight / Tennis Abstract:
- Erwartung (Logistik, Basis 10, Skala 400)
- K-Faktor faellt mit Anzahl gespielter Matches (mehr Daten -> stabiler)
- Blend aus Surface-Elo und Overall-Elo
"""
from __future__ import annotations

from .. import config


def expected_score(rating_a: float, rating_b: float) -> float:
    """Erwartete Gewinnwahrscheinlichkeit von A gegen B aus Elo-Differenz."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def k_factor(matches_played: int) -> float:
    """Decay-K: viele gespielte Matches -> kleinerer K (Rating stabiler)."""
    return config.ELO_K_NUMERATOR / (
        (matches_played + config.ELO_K_OFFSET) ** config.ELO_K_EXPONENT
    )


def update(rating: float, score: float, expected: float, k: float) -> float:
    """Standard-Elo-Update. ``score`` = 1.0 (Sieg) oder 0.0 (Niederlage)."""
    return rating + k * (score - expected)


def blended_win_probability(
    overall_a: float,
    surface_a: float,
    overall_b: float,
    surface_b: float,
    blend: float | None = None,
) -> float:
    """Finale Modell-Wahrscheinlichkeit, dass A gewinnt.

    Mischt die Wahrscheinlichkeit aus Surface-Elo und aus Overall-Elo. Wir
    blenden die *Wahrscheinlichkeiten* (nicht die Ratings), was robuster ist,
    wenn ein Spieler auf einem Belag wenig Matches hat.
    """
    if blend is None:
        blend = config.SURFACE_BLEND
    p_surface = expected_score(surface_a, surface_b)
    p_overall = expected_score(overall_a, overall_b)
    return blend * p_surface + (1.0 - blend) * p_overall
