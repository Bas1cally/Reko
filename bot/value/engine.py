"""Value-Engine: vergleicht Modell-Wahrscheinlichkeit mit Buchmacher-Quoten.

Logik:
- **Scharfe** Buchmacher (Pinnacle) entviggt = faire Markt-Wahrscheinlichkeit.
  Das Modell wird in ``run.py`` mit diesem Konsens gemischt (markt-bewusst).
- Gewettet wird gegen **weiche** Buchmacher, deren Quote dem Konsens hinterherhinkt.
- EV = p_final * Quote - 1; flaggen ab MIN_EV. Gecapptes Kelly fuer den Einsatz.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .. import config
from ..odds.odds_api import Match


@dataclass
class ValueBet:
    match: Match
    selection: str            # Spielername, auf den gewettet wird
    raw_model_prob: float     # reines Modell (Elo + News), vor Markt-Blend
    model_prob: float         # finale (geblendete) Wahrscheinlichkeit fuer EV
    sharp_prob: Optional[float]
    best_odds: float
    best_book: str
    n_books: int              # Anzahl weicher Buchmacher mit dieser Quote
    ev: float
    stake_fraction: float     # gecapptes (1/2-)Kelly

    @property
    def fair_odds(self) -> float:
        return 1.0 / self.model_prob if self.model_prob > 0 else float("inf")

    @property
    def stake_eur(self) -> Optional[float]:
        if config.BANKROLL > 0:
            return config.BANKROLL * self.stake_fraction
        return None


def implied_prob(odds: float) -> float:
    return 1.0 / odds if odds > 0 else 0.0


def _devig_power(pa: float, pb: float) -> tuple[float, float]:
    """Power-Methode: finde k mit pa^k + pb^k = 1 (Bisektion)."""
    lo, hi = 0.5, 5.0
    for _ in range(60):
        k = (lo + hi) / 2
        if pa ** k + pb ** k > 1.0:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    fa, fb = pa ** k, pb ** k
    total = fa + fb
    return fa / total, fb / total


def devig_two_way(odds_a: float, odds_b: float,
                  method: Optional[str] = None) -> tuple[float, float]:
    """Entfernt die Marge aus einem 2-Wege-Markt -> faire Wahrscheinlichkeiten."""
    pa, pb = implied_prob(odds_a), implied_prob(odds_b)
    total = pa + pb
    if total <= 0:
        return 0.0, 0.0
    method = (method or config.DEVIG_METHOD).lower()
    if method == "power" and 0 < pa < 1 and 0 < pb < 1:
        return _devig_power(pa, pb)
    # multiplicative (Standard)
    return pa / total, pb / total


def kelly(prob: float, odds: float) -> float:
    """Fraktionales Kelly (Default 1/2). 0, wenn kein positiver Edge."""
    b = odds - 1.0
    if b <= 0:
        return 0.0
    f = (prob * odds - 1.0) / b
    return max(0.0, f) * config.KELLY_FRACTION


def stake_fraction(prob: float, odds: float) -> float:
    """Gecapptes Kelly als Anteil der Bankroll."""
    return min(kelly(prob, odds), config.MAX_STAKE_FRACTION)


def sharp_consensus(match: Match, side: str) -> Optional[float]:
    """Mittlere entviggte Wahrscheinlichkeit aus scharfen Buchmachern fuer ``side``."""
    other = match.away if side == match.home else match.home
    probs = []
    for book in match.books:
        if book.key not in config.SHARP_BOOKMAKERS:
            continue
        if side in book.prices and other in book.prices:
            p_side, _ = devig_two_way(book.prices[side], book.prices[other])
            probs.append(p_side)
    if not probs:
        return None
    return sum(probs) / len(probs)


def _best_soft_offer(match: Match, side: str) -> Optional[tuple[float, str, int]]:
    """Beste (hoechste) Quote + Anzahl weicher Buchmacher fuer ``side``."""
    best: Optional[tuple[float, str]] = None
    count = 0
    for book in match.books:
        if book.key in config.SHARP_BOOKMAKERS:
            continue
        odds = book.prices.get(side)
        if odds is None:
            continue
        count += 1
        if best is None or odds > best[0]:
            best = (odds, book.title or book.key)
    if best is None:
        return None
    return best[0], best[1], count


def evaluate(match: Match, prob_home: float,
             raw_model_home: Optional[float] = None) -> list[ValueBet]:
    """Prueft beide Seiten und liefert qualifizierte Value-Bets.

    ``prob_home`` ist die finale (ggf. markt-geblendete) Wahrscheinlichkeit, mit
    der der EV berechnet wird. ``raw_model_home`` ist das reine Modell (fuer den
    Sanity-Check gegen den scharfen Konsens und die Anzeige).
    """
    if raw_model_home is None:
        raw_model_home = prob_home
    bets: list[ValueBet] = []
    sides = [
        (match.home, prob_home, raw_model_home),
        (match.away, 1.0 - prob_home, 1.0 - raw_model_home),
    ]
    for side, final_p, raw_p in sides:
        offer = _best_soft_offer(match, side)
        if offer is None:
            continue
        best_odds, best_book, n_books = offer
        if best_odds > config.MAX_ODDS or n_books < config.MIN_BOOKS:
            continue

        ev = final_p * best_odds - 1.0
        sharp_p = sharp_consensus(match, side)
        # Ohne scharfen Anker: hoehere EV-Schwelle (mehr Unsicherheit).
        min_ev = config.MIN_EV + (config.NO_SHARP_EV_PENALTY if sharp_p is None else 0.0)
        if ev < min_ev:
            continue
        # Sanity: reines Modell darf nicht absurd weit vom Sharp-Konsens weg sein
        # (meist Daten-/Namens-Mismatch, kein echter Value).
        if sharp_p is not None and abs(raw_p - sharp_p) > config.MAX_MODEL_MARKET_GAP:
            continue

        bets.append(ValueBet(
            match=match,
            selection=side,
            raw_model_prob=raw_p,
            model_prob=final_p,
            sharp_prob=sharp_p,
            best_odds=best_odds,
            best_book=best_book,
            n_books=n_books,
            ev=ev,
            stake_fraction=stake_fraction(final_p, best_odds),
        ))
    return bets


def blend_with_market(p_model: float, p_sharp: Optional[float]) -> float:
    """Markt-bewusste Mischung. Ohne Sharp -> reines Modell."""
    if p_sharp is None:
        return p_model
    w = config.MODEL_MARKET_BLEND
    return w * p_model + (1.0 - w) * p_sharp


def bet_key(bet: ValueBet) -> str:
    """Stabiler Schluessel fuer Dedupe (Match + Auswahl + Buchmacher)."""
    return f"{bet.match.id}:{bet.selection}:{bet.best_book}".lower()
