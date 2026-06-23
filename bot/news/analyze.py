"""News-/Kontext-Layer via Claude - die eigentliche Edge des Bots.

Claude liest aktuelle News zu beiden Spielern und uebersetzt qualitative
Signale (Verletzung, Krankheit, Aufgabe-Risiko, Conditions, Fatigue, Motivation)
in einen **begrenzten, begruendeten Nudge** auf die Elo-Baseline.

Bewusst konservativ: der Adjust ist auf +/- MAX_NEWS_ADJUSTMENT gekappt, damit
ein einzelnes News-Signal das kalibrierte Modell nicht ueberstimmt.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .. import config
from ..odds.odds_api import Match
from . import sources


@dataclass
class NewsAdjustment:
    home_adjustment: float    # additiv auf p(home), bereits gekappt
    confidence: float         # 0..1
    reasoning: str

    @property
    def applied(self) -> bool:
        return abs(self.home_adjustment) > 1e-9


_ZERO = NewsAdjustment(0.0, 0.0, "kein News-Signal")

_SYSTEM = (
    "Du bist ein quantitativer Tennis-Analyst. Du bekommst eine Modell-"
    "Wahrscheinlichkeit (aus Surface-Elo) und aktuelle News zu beiden Spielern. "
    "Bewerte ausschliesslich, ob die News einen kleinen, begruendeten Adjust auf "
    "die Siegwahrscheinlichkeit des HOME-Spielers rechtfertigen: Verletzung, "
    "Krankheit, Aufgabe-Risiko, Wetter/Conditions, Fatigue (Vortags-Last, Reise), "
    "Motivation. Wenn die News irrelevant oder nur Werbung/Vorschau ohne Substanz "
    "sind, gib 0.0. Antworte AUSSCHLIESSLICH mit JSON: "
    '{"home_adjustment": <float -0.08..0.08>, "confidence": <float 0..1>, '
    '"reasoning": "<kurz, deutsch>"}'
)


def _client():
    # Import lokal halten, damit der Rest des Bots ohne anthropic-Paket laeuft.
    from anthropic import Anthropic
    return Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _format_news(name: str, articles: list[dict]) -> str:
    if not articles:
        return f"{name}: (keine aktuellen News gefunden)"
    lines = [f"{name}:"]
    for a in articles:
        title = a.get("title", "").strip()
        desc = a.get("description", "").strip()
        when = a.get("publishedAt", "")[:10]
        lines.append(f"  - [{when}] {title}. {desc}")
    return "\n".join(lines)


def _extract_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def analyze_match(match: Match, model_prob_home: float) -> NewsAdjustment:
    if not config.ENABLE_NEWS or not config.ANTHROPIC_API_KEY:
        return _ZERO

    home_news = sources.fetch_player_news(match.home)
    away_news = sources.fetch_player_news(match.away)
    if not home_news and not away_news:
        return _ZERO

    prompt = (
        f"Match: {match.home} (HOME) vs {match.away} (AWAY)\n"
        f"Belag/Turnier-Key: {match.sport_key}\n"
        f"Modell-Wahrscheinlichkeit p(HOME gewinnt) = {model_prob_home:.3f}\n\n"
        f"NEWS:\n{_format_news(match.home, home_news)}\n"
        f"{_format_news(match.away, away_news)}\n\n"
        "Liefere den JSON-Adjust."
    )

    try:
        resp = _client().messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=400,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
    except Exception as exc:  # API-Fehler darf die Pipeline nicht kippen
        print(f"  ! News-Analyse fehlgeschlagen ({match.home} vs {match.away}): {exc}")
        return _ZERO

    data = _extract_json(text)
    if not data:
        return _ZERO

    cap = config.MAX_NEWS_ADJUSTMENT
    adj = max(-cap, min(cap, float(data.get("home_adjustment", 0.0) or 0.0)))
    conf = max(0.0, min(1.0, float(data.get("confidence", 0.0) or 0.0)))
    reasoning = str(data.get("reasoning", "")).strip() or "kein News-Signal"
    return NewsAdjustment(home_adjustment=adj, confidence=conf, reasoning=reasoning)
