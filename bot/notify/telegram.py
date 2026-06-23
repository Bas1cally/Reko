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


def _kelly_label() -> str:
    f = config.KELLY_FRACTION
    if abs(f - 0.5) < 1e-6:
        return "½-Kelly"
    if abs(f - 0.25) < 1e-6:
        return "¼-Kelly"
    if abs(f - 0.125) < 1e-6:
        return "⅛-Kelly"
    return f"{f:g}×Kelly"


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
        f"Beste Quote: <b>{bet.best_odds:.2f}</b> @ {e(bet.best_book)} ({bet.n_books} Bookies)",
        f"Finale Wahrscheinlichkeit: {bet.model_prob*100:.1f}% (faire Quote {bet.fair_odds:.2f})",
        f"  ↳ Modell roh: {bet.raw_model_prob*100:.1f}%",
    ]
    if bet.sharp_prob is not None:
        lines.append(f"  ↳ Sharp-Konsens: {bet.sharp_prob*100:.1f}%")
    lines.append(f"Erwartungswert (EV): <b>+{bet.ev*100:.1f}%</b>")

    stake = f"Empf. Einsatz ({_kelly_label()}): {bet.stake_fraction*100:.2f}% der Bankroll"
    if bet.stake_eur is not None:
        stake += f" ≈ <b>{bet.stake_eur:.2f} €</b>"
    lines.append(stake)

    if news and news.applied:
        sign = "+" if news.home_adjustment >= 0 else "−"
        lines += [
            "",
            f"🧠 <i>News-Layer ({sign}{abs(news.home_adjustment)*100:.1f}% auf HOME, "
            f"Konfidenz {news.confidence*100:.0f}%):</i>",
            f"<i>{e(news.reasoning)}</i>",
        ]
    lines.append("")
    lines.append("⚠️ <i>Keine Garantie - +EV-Empfehlung (½-Kelly = hohe Schwankung).</i>")
    return "\n".join(lines)


def send_summary(scanned: int, matched: int, found: int,
                 quota: int | None = None) -> bool:
    """Kurze Lauf-Zusammenfassung."""
    lines = [
        "📊 <b>Lauf-Zusammenfassung</b>",
        f"Matches gescannt: {scanned}",
        f"Namen gematcht: {matched}",
        f"Value-Bets: <b>{found}</b>",
    ]
    if quota is not None:
        lines.append(f"API-Rest: {quota}")
    return send_message("\n".join(lines))


def send_error(context: str, exc: Exception) -> bool:
    """Fehler-Alert, damit kein Cron-Lauf still scheitert."""
    e = html.escape
    return send_message(
        f"🚨 <b>Bot-Fehler</b> ({e(context)})\n<code>{e(type(exc).__name__)}: "
        f"{e(str(exc))[:300]}</code>"
    )
