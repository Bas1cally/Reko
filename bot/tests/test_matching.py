from bot.matching.names import NameResolver, normalize_key
from bot.storage.db import Rating


def _rating(name):
    key = normalize_key(name)
    return Rating(key, "atp", name, 1500, 1500, 1500, 1500, 10)


def test_normalize_strips_accents_and_punctuation():
    assert normalize_key("Dominika Cibulková") == "dominika cibulkova"
    assert normalize_key("Jo-Wilfried Tsonga") == "jo wilfried tsonga"
    assert normalize_key("C. Alcaraz") == "c alcaraz"


def test_resolver_exact_match():
    r = NameResolver([_rating("Carlos Alcaraz"), _rating("Novak Djokovic")])
    assert r.resolve("Carlos Alcaraz") == "carlos alcaraz"


def test_resolver_surname_initial():
    r = NameResolver([_rating("Carlos Alcaraz"), _rating("Novak Djokovic")])
    assert r.resolve("C. Alcaraz") == "carlos alcaraz"
    assert r.resolve("Alcaraz C.") == "carlos alcaraz"


def test_resolver_fuzzy_accent():
    r = NameResolver([_rating("Stefanos Tsitsipas"), _rating("Holger Rune")])
    assert r.resolve("Stefanos Tsitsipás") == "stefanos tsitsipas"


def test_resolver_returns_none_for_unknown():
    r = NameResolver([_rating("Carlos Alcaraz"), _rating("Novak Djokovic")])
    assert r.resolve("Some Unknown Player") is None


def test_resolver_ambiguous_initial_is_none():
    # Zwei Spieler mit gleichem Nachnamen + gleicher Initiale -> nicht eindeutig.
    r = NameResolver([_rating("Alexander Zverev"), _rating("Alanna Zverev")])
    assert r.resolve("A. Zverev") is None
