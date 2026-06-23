"""Value-Engine: vergleicht Modell-Wahrscheinlichkeit mit Buchmacher-Quoten.

Logik:
- **Scharfe** Buchmacher (Pinnacle) entviggt = faire Markt-Wahrscheinlichkeit,
  dient als Plausibilitaetsanker.
- Gewettet wird gegen **weiche** Buchmacher, deren Quote dem Konsens hinterherhinkt.
- EV = p_model * Quote - 1; flaggen ab MIN_EV. Kelly fuer die Stake-Empfehlung.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .. import config
from ..odds.odds_api import BookOdds, Match


@dataclass
class ValueBet:
    match: Match
    selection: str            # Spielername, auf den gewettet wird
    model_prob: float
    sharp_prob: Optional[float]
    best_odds: float
    best_book: str
    ev: float
    kelly_fraction: float

    @property
    def fair_odds(self) -> float:
        return 1.0 / self.model_prob if self.model_prob > 0 else float("inf")


def implied_prob(odds: float) -> float:
    return 1.0 / odds if odds > 0 else 0.0


def devig_two_way(odds_a: float, odds_b: float) -> tuple[float, float]:
    """Entfernt die Marge aus einem 2-Wege-Markt -> faire Wahrscheinlichkeiten."""
    pa, pb = implied_prob(odds_a), implied_prob(odds_b)
    total = pa + pb
    if total <= 0:
        return 0.0, 0.0
    return pa / total, pb / total


def kelly(prob: float, odds: float) -> float:
    """Fraktionales Kelly. Gibt 0 zurueck, wenn kein positiver Edge."""
    b = odds - 1.0
    if b <= 0:
        return 0.0
    f = (prob * odds - 1.0) / b
    return max(0.0, f) * config.KELLY_FRACTION


def _sharp_fair_prob(match: Match, side: str) -> Optional[float]:
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


def _best_soft_offer(match: Match, side: str) -> Optional[tuple[float, str]]:
    """Beste (hoechste) Quote fuer ``side`` unter den *weichen* Buchmachern."""
    best: Optional[tuple[float, str]] = None
    for book in match.books:
        if book.key in config.SHARP_BOOKMAKERS:
            continue
        odds = book.prices.get(side)
        if odds is None:
            continue
        if best is None or odds > best[0]:
            best = (odds, book.title or book.key)
    return best


def evaluate(match: Match, model_prob_home: float) -> list[ValueBet]:
    """Prueft beide Seiten eines Matches und liefert qualifizierte Value-Bets."""
    bets: list[ValueBet] = []
    sides = [
        (match.home, model_prob_home),
        (match.away, 1.0 - model_prob_home),
    ]
    for side, model_p in sides:
        offer = _best_soft_offer(match, side)
        if offer is None:
            continue
        best_odds, best_book = offer
        if best_odds > config.MAX_ODDS:
            continue

        ev = model_p * best_odds - 1.0
        if ev < config.MIN_EV:
            continue

        sharp_p = _sharp_fair_prob(match, side)
        # Sanity: Modell darf nicht absurd weit vom scharfen Konsens abweichen
        # (meist ein Daten-/Namens-Mismatch, kein echter Value).
        if sharp_p is not None and abs(model_p - sharp_p) > config.MAX_MODEL_MARKET_GAP:
            continue

        bets.append(ValueBet(
            match=match,
            selection=side,
            model_prob=model_p,
            sharp_prob=sharp_p,
            best_odds=best_odds,
            best_book=best_book,
            ev=ev,
            kelly_fraction=kelly(model_p, best_odds),
        ))
    return bets


def bet_key(bet: ValueBet) -> str:
    """Stabiler Schluessel fuer Dedupe (Match + Auswahl + Buchmacher)."""
    return f"{bet.match.id}:{bet.selection}:{bet.best_book}".lower()
