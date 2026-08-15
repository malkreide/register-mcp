"""Tests für `docs/demo/demo.py` — das Skript hinter der Terminal-Aufnahme.

WARUM DIESE DATEI EXISTIERT. Bis zum 2026-08-15 schickte `demo.py uid` ein
Payload mit `uid`-Feld an `firm/search.json`. Zefix kennt dort kein solches
Feld und antwortete mit HTTP 400 — das Kommando war unbenutzbar, und zwar für
jeden, der der README folgte. Aufgefallen ist das nicht der Suite, sondern
einem Aufruf von Hand: Für `demo.py` gab es keine Tests.

Zwei Behauptungen tragen hier die Last, und beide hängen an einer
aufgezeichneten Antwort, nicht an einer ausgedachten:

1. `firm/search.json` löst eine UID über das Feld `name` auf. `tests/fixtures/
   zefix_search_by_uid.json` ist genau diese Antwort; `scripts/
   record_fixtures.py` prüft beim Aufzeichnen zusätzlich, dass derselbe
   Endpunkt ein Payload mit `uid`-Feld am selben Tag mit 400 quittiert.
2. Eine Suche ohne Treffer kommt mit HTTP **404** und dem NORESULT-Umschlag,
   nicht mit einer leeren Liste bei 200. `zefix_no_result.json` hält
   Statuscode und Rumpf zusammen fest, weil erst beides den Befund ausmacht.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest
import respx
from fixture_data import fixture_json

DEMO_PATH = Path(__file__).resolve().parent.parent / "docs" / "demo" / "demo.py"


def _load_demo():
    """`demo.py` liegt ausserhalb des Pakets und wird über den Pfad geladen."""
    spec = importlib.util.spec_from_file_location("demo_cli", DEMO_PATH)
    assert spec and spec.loader, f"Kein Modul unter {DEMO_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules["demo_cli"] = module
    spec.loader.exec_module(module)
    return module


demo = _load_demo()
ZEFIX = demo.ZEFIX_BASE

# ---------------------------------------------------------------------------
# Aufgezeichnete Antworten — Herkunft und Datum in fixtures/PROVENANCE.md
# ---------------------------------------------------------------------------

MOCK_LEGAL_FORMS = fixture_json("zefix_legal_forms.json")
MOCK_SEARCH = fixture_json("zefix_search.json")
MOCK_SEARCH_BY_UID = fixture_json("zefix_search_by_uid.json")

_NO_RESULT = fixture_json("zefix_no_result.json")
NO_RESULT_STATUS = _NO_RESULT["status_code"]
NO_RESULT_BODY = _NO_RESULT["body"]

# Aus den Fixtures gelesen statt danebengeschrieben.
UID_HIT = MOCK_SEARCH_BY_UID["list"][0]
UID_FORMATTED = UID_HIT["uidFormatted"]
UID_DIGITS = "".join(c for c in UID_FORMATTED if c.isdigit())

# Ein Treffer, der in der aufgezeichneten Namenssuche NICHT an erster Stelle
# steht. Daran hängt die Gegenprobe zu `firms[0]`: Wer den ersten Treffer nimmt
# statt den exakten, druckt hier einen anderen Namen.
LATER_HIT = next(h for h in MOCK_SEARCH["list"][1:] if h["name"] != MOCK_SEARCH["list"][0]["name"])
FIRST_HIT_NAME = MOCK_SEARCH["list"][0]["name"]


def _mock_legal_forms():
    respx.get(f"{ZEFIX}/legalForm").mock(return_value=httpx.Response(200, json=MOCK_LEGAL_FORMS))


def _mock_search(payload, status=200):
    return respx.post(f"{ZEFIX}/firm/search.json").mock(
        return_value=httpx.Response(status, json=payload)
    )


def _sent_body(route):
    """Das JSON, das die Demo tatsächlich gesendet hat."""
    return json.loads(route.calls.last.request.content)


# ---------------------------------------------------------------------------
# cmd_uid — die Anfrage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_uid_sends_the_payload_the_source_accepts(capsys):
    """Regression auf den 400er: kein `uid`-Feld, UID steht unter `name`."""
    with respx.mock:
        _mock_legal_forms()
        route = _mock_search(MOCK_SEARCH_BY_UID)
        await demo.cmd_uid(UID_FORMATTED)
    body = _sent_body(route)
    assert "uid" not in body, "Zefix beantwortet ein Payload mit `uid`-Feld mit HTTP 400"
    assert body["name"] == UID_FORMATTED
    assert body["searchType"] == "CONTAINS"
    assert body["activeOnly"] is False
    assert body["languageKey"] == "de"
    assert UID_HIT["name"] in capsys.readouterr().out


@pytest.mark.asyncio
async def test_uid_normalises_unformatted_input():
    """`CHE238945329` und `CHE-238.945.329` müssen dieselbe Anfrage erzeugen.

    Die alte Normalisierung strich nur `-` und `.` und liess das Präfix stehen.
    """
    with respx.mock:
        _mock_legal_forms()
        route = _mock_search(MOCK_SEARCH_BY_UID)
        await demo.cmd_uid(f"CHE{UID_DIGITS}")
    assert _sent_body(route)["name"] == UID_FORMATTED


@pytest.mark.asyncio
async def test_uid_rejects_a_malformed_uid_without_asking_the_source(capsys):
    with respx.mock:
        forms = respx.get(f"{ZEFIX}/legalForm").mock(
            return_value=httpx.Response(200, json=MOCK_LEGAL_FORMS)
        )
        route = _mock_search(MOCK_SEARCH_BY_UID)
        await demo.cmd_uid("abc")
    assert not route.called, "Eine UID ohne neun Ziffern gehört nicht an die Quelle geschickt"
    assert not forms.called
    assert "Ungültige UID" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cmd_uid — die Auswertung
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_uid_picks_the_exact_match_not_the_first_hit(capsys):
    """Gegen `firms[0]`: die Trefferliste beginnt mit einer anderen Firma."""
    with respx.mock:
        _mock_legal_forms()
        _mock_search(MOCK_SEARCH)
        await demo.cmd_uid(LATER_HIT["uidFormatted"])
    out = capsys.readouterr().out
    assert LATER_HIT["name"] in out
    assert FIRST_HIT_NAME not in out


@pytest.mark.asyncio
async def test_uid_without_an_exact_match_reports_nothing_found(capsys):
    """Kein Rückfall auf `firms[0]` — eine Trefferliste ist noch keine Antwort.

    Die Suche läuft mit `searchType: CONTAINS` über das Namensfeld. Zefix
    beantwortet `CHE-999.999.999` mit «CHEMAM - 999» (UID CHE-113.593.998, an
    der Quelle geprüft am 2026-08-15). Wer den ersten Treffer nimmt, gibt diese
    Firma als Antwort auf eine Abfrage nach einer ganz anderen UID aus:
    vollständig, plausibel, formatiert, und über jemand anderen.
    """
    absent = "999999999"
    assert not [
        h for h in MOCK_SEARCH["list"] if "".join(c for c in h["uid"] if c.isdigit()) == absent
    ], "Die Fixture enthaelt diese UID doch — dann prueft der Test den Rueckfall nicht"
    with respx.mock:
        _mock_legal_forms()
        _mock_search(MOCK_SEARCH)
        await demo.cmd_uid("CHE-999.999.999")
    out = capsys.readouterr().out
    assert "Keine Firma mit UID CHE-999.999.999 gefunden" in out
    assert FIRST_HIT_NAME not in out


@pytest.mark.asyncio
async def test_uid_reports_a_missing_company_instead_of_raising(capsys):
    """Der NORESULT-Fall kommt mit 404 — vorher endete das im Traceback."""
    with respx.mock:
        _mock_legal_forms()
        _mock_search(NO_RESULT_BODY, status=NO_RESULT_STATUS)
        await demo.cmd_uid(UID_FORMATTED)
    assert "Keine Firma mit UID" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cmd_verify / cmd_search — derselbe 404-Zweig, dieselbe Quelle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_prints_the_recorded_companies(capsys):
    with respx.mock:
        _mock_legal_forms()
        _mock_search(MOCK_SEARCH)
        await demo.cmd_verify("Migros")
    out = capsys.readouterr().out
    assert FIRST_HIT_NAME in out
    assert MOCK_SEARCH["list"][0]["uidFormatted"] in out
    assert MOCK_SEARCH["list"][0]["status"] in out


@pytest.mark.asyncio
async def test_verify_reports_no_hits_instead_of_raising(capsys):
    with respx.mock:
        _mock_legal_forms()
        _mock_search(NO_RESULT_BODY, status=NO_RESULT_STATUS)
        await demo.cmd_verify("Zzzqqxyznichtexistent")
    assert "Nicht im Handelsregister gefunden" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_search_passes_the_canton_filter_uppercased():
    with respx.mock:
        _mock_legal_forms()
        route = _mock_search(MOCK_SEARCH)
        await demo.cmd_search("Migros", "zh")
    assert _sent_body(route)["canton"] == "ZH"


@pytest.mark.asyncio
async def test_search_reports_no_hits_instead_of_raising(capsys):
    with respx.mock:
        _mock_legal_forms()
        _mock_search(NO_RESULT_BODY, status=NO_RESULT_STATUS)
        await demo.cmd_search("Zzzqqxyznichtexistent", None)
    assert "0 Ergebnisse" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Live-Tests (in der CI mit -m "not live" ausgeschlossen, woechentlich in
# .github/workflows/live-tests.yml)
# ---------------------------------------------------------------------------
#
# Die Tests oben laufen gegen aufgezeichnete Antworten und pruefen damit die
# Demo gegen Zefix vom Aufzeichnungstag. Aendert die Quelle ihren Vertrag,
# bleiben sie gruen — die Fixture ist aus derselben Annahme geschrieben wie der
# Code. Genau der Fall lag hier vor: Das Payload mit `uid`-Feld war seit jeher
# falsch, und keine Fixture konnte das widerlegen.
#
# Diese drei Tests sind die Gegenprobe an der Quelle selbst.

# Die dokumentierte Beispiel-Firma aus docs/demo/README.md und demo.tape.
# Faellt dieser Test, stimmt entweder die Anfrage nicht mehr oder das Beispiel.
LIVE_UID = "CHE-404.020.972"
LIVE_NAME = "Lehrmittelverlag Zürich AG"


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_uid_resolves_the_documented_company(capsys):
    """Live: `firm/search.json` loest eine UID weiterhin ueber das Feld `name` auf."""
    await demo.cmd_uid(LIVE_UID)
    out = capsys.readouterr().out
    assert LIVE_NAME in out
    assert LIVE_UID in out


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_verify_and_search_return_hits(capsys):
    """Live: die beiden Namenssuchen liefern weiterhin Treffer."""
    await demo.cmd_verify("Migros")
    verify_out = capsys.readouterr().out
    assert "CHE-" in verify_out
    assert "✅" in verify_out

    await demo.cmd_search("Migros", "ZH")
    search_out = capsys.readouterr().out
    assert "CHE-" in search_out
    assert "0 Ergebnisse" not in search_out


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_a_search_without_hits_stays_an_answer(capsys):
    """Live: die trefferlose Suche endet in einer Meldung, nicht im Traceback.

    Zefix beantwortet sie mit HTTP 404 und dem NORESULT-Umschlag. Der Test
    behauptet den Statuscode nicht — er behauptet, dass die Demo damit umgeht,
    welchen Weg die Quelle auch waehlt.
    """
    await demo.cmd_verify("Zzzqqxyznichtexistent")
    assert "Nicht im Handelsregister gefunden" in capsys.readouterr().out

    await demo.cmd_uid("CHE-999.999.999")
    assert "Keine Firma mit UID" in capsys.readouterr().out
