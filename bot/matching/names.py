"""Namens-Normalisierung und Matching zwischen Odds-API und Sackmann-Daten.

Der fragilste Teil der Pipeline: Buchmacher schreiben Namen anders als die
Match-Datenbank (``C. Alcaraz`` vs. ``Carlos Alcaraz``). Strategie:
1. Normalisieren (Kleinschreibung, Akzente weg, Satzzeichen weg)
2. Manuelle Aliase (``aliases.json``)
3. Exakter Treffer
4. Nachname + Initiale (eindeutig)
5. Fuzzy-Match (rapidfuzz) mit Schwelle + Mindestabstand zum Zweitbesten

Nicht eindeutig aufloesbare Namen geben ``None`` zurueck und werden vom Aufrufer
uebersprungen + geloggt - lieber keine Wette als eine auf falsche Daten.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz

_ALIASES_PATH = Path(__file__).resolve().parent / "aliases.json"


def normalize_key(name: str) -> str:
    """Kanonischer Schluessel: kleingeschrieben, ohne Akzente/Satzzeichen."""
    if not name:
        return ""
    # Akzente entfernen (z.B. "Cibulková" -> "cibulkova").
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = []
    for ch in ascii_name.lower():
        if ch.isalnum() or ch.isspace():
            cleaned.append(ch)
        else:
            cleaned.append(" ")  # Punkte/Bindestriche -> Trenner
    return " ".join("".join(cleaned).split())


@lru_cache(maxsize=1)
def _aliases() -> dict[str, str]:
    try:
        raw = json.loads(_ALIASES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in raw.items() if not k.startswith("_")}


@dataclass
class _Candidate:
    key: str
    name: str
    tokens: tuple[str, ...]


class NameResolver:
    """Loest Odds-API-Namen auf Rating-Schluessel auf - pro Tour instanziieren."""

    def __init__(self, ratings, fuzzy_threshold: int = 87, min_margin: int = 6):
        self.fuzzy_threshold = fuzzy_threshold
        self.min_margin = min_margin
        self._by_key: dict[str, str] = {}
        self._candidates: list[_Candidate] = []
        for r in ratings:
            self._by_key[r.player_key] = r.name
            self._candidates.append(
                _Candidate(r.player_key, r.name, tuple(r.player_key.split()))
            )

    def resolve(self, raw_name: str) -> Optional[str]:
        norm = normalize_key(raw_name)
        if not norm:
            return None

        # 2. Alias
        if norm in _aliases():
            norm = _aliases()[norm]

        # 3. Exakter Treffer
        if norm in self._by_key:
            return norm

        # 4. Nachname + Initiale (eindeutig)
        by_initial = self._match_surname_initial(norm)
        if by_initial is not None:
            return by_initial

        # 5. Fuzzy mit Mindestabstand
        return self._fuzzy(norm)

    def _match_surname_initial(self, norm: str) -> Optional[str]:
        tokens = norm.split()
        words = [t for t in tokens if len(t) > 1]
        initials = [t for t in tokens if len(t) == 1]
        if not words:
            return None

        matches = []
        for cand in self._candidates:
            cand_tokens = list(cand.tokens)
            # Alle vollen Woerter muessen als Token vorkommen.
            if not all(w in cand_tokens for w in words):
                continue
            remaining = [t for t in cand_tokens if t not in words]
            # Jede Initiale muss den Anfang eines uebrigen Tokens treffen.
            if all(any(t.startswith(i) for t in remaining) for i in initials):
                matches.append(cand.key)
        if len(set(matches)) == 1:
            return matches[0]
        return None

    def _fuzzy(self, norm: str) -> Optional[str]:
        best_key = None
        best_score = -1.0
        second_score = -1.0
        for cand in self._candidates:
            score = fuzz.token_sort_ratio(norm, cand.key)
            if score > best_score:
                second_score = best_score
                best_score = score
                best_key = cand.key
            elif score > second_score:
                second_score = score
        if best_score >= self.fuzzy_threshold and (best_score - second_score) >= self.min_margin:
            return best_key
        return None

    def display_name(self, key: str) -> str:
        return self._by_key.get(key, key)
