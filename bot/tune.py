"""Parameter-Tuning: Grid-Search der Elo-Parameter gegen Backtest-Log-Loss.

Probiert Kombinationen aus K-Faktor (NUMERATOR/EXPONENT) und SURFACE_BLEND und
gibt die beste Kombination aus. Werte dann manuell in .env eintragen
(ELO_K_NUMERATOR / ELO_K_EXPONENT / SURFACE_BLEND).

Hinweis: MODEL_MARKET_BLEND laesst sich hier nicht tunen (Backtest hat keine
historischen Quoten) - dafuer braucht es eine Odds-Historie (siehe README).
"""
from __future__ import annotations

import itertools
import sys

from . import backtest, config

K_NUMERATORS = [150.0, 200.0, 250.0, 300.0]
K_EXPONENTS = [0.35, 0.4, 0.45]
SURFACE_BLENDS = [0.4, 0.5, 0.6, 0.7]


def _logloss_all_tours() -> float:
    preds = []
    for tour in config.TOURS:
        preds.extend(backtest.collect_preds(tour))
    return backtest.logloss_of(preds)


def main() -> int:
    # Pruefen, ob ueberhaupt Daten vorhanden sind.
    if not _logloss_all_tours() < float("inf"):
        print("Keine Daten. Bitte zuerst: python -m bot.data.fetch_history")
        return 1

    orig = (config.ELO_K_NUMERATOR, config.ELO_K_EXPONENT, config.SURFACE_BLEND)
    results = []
    combos = list(itertools.product(K_NUMERATORS, K_EXPONENTS, SURFACE_BLENDS))
    print(f"Teste {len(combos)} Kombinationen ...")
    for num, exp, blend in combos:
        config.ELO_K_NUMERATOR = num
        config.ELO_K_EXPONENT = exp
        config.SURFACE_BLEND = blend
        ll = _logloss_all_tours()
        results.append((ll, num, exp, blend))

    config.ELO_K_NUMERATOR, config.ELO_K_EXPONENT, config.SURFACE_BLEND = orig
    results.sort()

    print("\n  Log-Loss | K_NUM | K_EXP | SURFACE_BLEND")
    for ll, num, exp, blend in results[:10]:
        print(f"  {ll:.5f} | {num:5.0f} | {exp:.2f}  | {blend:.2f}")
    best = results[0]
    print(f"\nBeste Kombination -> ELO_K_NUMERATOR={best[1]:.0f} "
          f"ELO_K_EXPONENT={best[2]:.2f} SURFACE_BLEND={best[3]:.2f} "
          f"(Log-Loss {best[0]:.5f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
