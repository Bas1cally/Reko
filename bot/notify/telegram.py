"""Telegram-Benachrichtigung via Bot-API (sendMessage)."""
from __future__ import annotations

import html

import requests

from .. import config
from ..news.analyze import NewsAdjustment
from ..value.engine import ValueBet


def _api_url() -> str:
    return f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"


def send_message(text: str) -> bool:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID fehlen in .env.")
    resp = requests.post(
        _api_url(),
        json={
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("ok", False)


def format_bet(bet: ValueBet, news: NewsAdjustment | None = None) -> str:
    """Baut die Telegram-Nachricht fuer einen Value-Bet (HTML)."""
    m = bet.match
    e = html.escape
    opp = m.away if bet.selection == m.home else m.home
    lines = [
        "🎾 <b>Value-Bet gefunden</b>",
        f"<b>{e(bet.selection)}</b> vs {e(opp)}",
        f"Tour: {m.tour.upper()}  |  Start: {e(m.commence_time[:16].replace('T', ' '))}",
        "",
        f"Wette auf: <b>{e(bet.selection)}</b>",
        f"Beste Quote: <b>{bet.best_odds:.2f}</b> @ {e(bet.best_book)}",
        f"Modell-Wahrscheinlichkeit: {bet.model_prob*100:.1f}% (faire Quote {bet.fair_odds:.2f})",
    ]
    if bet.sharp_prob is not None:
        lines.append(f"Sharp-Konsens: {bet.sharp_prob*100:.1f}%")
    lines.append(f"Erwartungswert (EV): <b>+{bet.ev*100:.1f}%</b>")
    lines.append(f"Empf. Einsatz (¼-Kelly): {bet.kelly_fraction*100:.2f}% der Bankroll")

    if news and news.applied:
        sign = "+" if news.home_adjustment >= 0 else "−"
        lines += [
            "",
            f"🧠 <i>News-Layer ({sign}{abs(news.home_adjustment)*100:.1f}% auf HOME, "
            f"Konfidenz {news.confidence*100:.0f}%):</i>",
            f"<i>{e(news.reasoning)}</i>",
        ]
    lines.append("")
    lines.append("⚠️ <i>Keine Garantie - +EV-Empfehlung, kein automatischer Einsatz.</i>")
    return "\n".join(lines)
