"""Zugriff auf die aufgezeichneten Fixtures unter ``tests/fixtures/``.

Herkunft, Datum, Auswahlregel, **Redaktion** und SHA-256 stehen je Datei in
``tests/fixtures/PROVENANCE.md``, geschrieben von ``scripts/record_fixtures.py``.

Zwei Dinge stehen dort ausdruecklich, weil sie hier nicht verschwiegen werden
duerfen: Die Werte personenbezogener Felder sind redigiert (das Amtsblatt fuehrt
Schuldbetreibungen und Schuldenrufe), und die Zefix-Payloads sind **nicht**
aufgezeichnet — die API verlangt Zugangsdaten. Was nicht aufgezeichnet ist,
traegt kein Datum und gibt auch nicht vor, eines zu haben.

Ein fehlender Name ist ein Fehler und keine leere Zeichenkette: Der
Rueckfallwert eines Lookups waere sonst die ganze Ursache.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture_json(name: str) -> Any:
    path = FIXTURES / name
    if not path.is_file():
        available = sorted(p.name for p in FIXTURES.iterdir() if p.is_file())
        raise FileNotFoundError(
            f"Keine Fixture {name!r} unter {FIXTURES}. Vorhanden: {available}. "
            "Neu aufzeichnen mit `python scripts/record_fixtures.py`."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def corpus_total() -> int:
    """Der aufgezeichnete Gesamtbestand des Amtsblatts."""
    return int(fixture_json("gazette_corpus_total.json")["total"])
