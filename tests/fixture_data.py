"""Zugriff auf die aufgezeichneten Fixtures unter ``tests/fixtures/``.

Herkunft, Datum, Auswahlregel, **Redaktion** und SHA-256 stehen je Datei in
``tests/fixtures/PROVENANCE.md``, geschrieben von ``scripts/record_fixtures.py``.

Was dort ausdruecklich steht, weil es hier nicht verschwiegen werden darf: Die
Werte personenbezogener Felder sind redigiert. Das Amtsblatt fuehrt
Schuldbetreibungen und Schuldenrufe, und Zefix nennt in `shabPub[].message`
eingetragene Personen mit Wohnort. Die Struktur bleibt echt, die Werte sind
ersetzt, und die Liste der ersetzten Felder steht vollstaendig daneben.

Bis zum 2026-08-08 stand hier ausserdem, die Zefix-Payloads seien nicht
aufgezeichnet, weil die API Zugangsdaten verlange. Das galt der falschen
Adresse: Das Aufzeichnungsskript fragte `ZefixPublicREST`, der Server spricht
mit `ZefixREST` — und das antwortet ohne jede Anmeldung.

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
