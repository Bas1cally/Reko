"""News-Beschaffung je Spieler (NewsAPI.org).

Liefert die aktuellsten Schlagzeilen/Beschreibungen zu einem Spieler. Ohne
``NEWS_API_KEY`` wird eine leere Liste zurueckgegeben (News-Layer faellt dann
auf "kein Signal" zurueck, statt zu crashen).
"""
from __future__ import annotations

import datetime as dt

import requests

from .. import config

NEWS_API_URL = "https://newsapi.org/v2/everything"


def fetch_player_news(player_name: str, days: int = 4, limit: int = 5) -> list[dict]:
    if not config.NEWS_API_KEY:
        return []
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    try:
        resp = requests.get(
            NEWS_API_URL,
            params={
                "q": f'"{player_name}" tennis',
                "from": since,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": limit,
                "apiKey": config.NEWS_API_KEY,
            },
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return []
    articles = resp.json().get("articles", [])
    return [
        {
            "title": a.get("title", ""),
            "description": a.get("description", ""),
            "publishedAt": a.get("publishedAt", ""),
            "source": (a.get("source") or {}).get("name", ""),
        }
        for a in articles
    ]
