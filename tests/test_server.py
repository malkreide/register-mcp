"""Tests for register-mcp — Swiss Commercial Register MCP Server.

Die Zefix-Payloads sind **aufgezeichnet, nicht ausgedacht**: Quelle, Datum,
Auswahlregel, Redaktion und SHA-256 je Datei stehen in
`tests/fixtures/PROVENANCE.md`, neu aufzeichnen mit
`python scripts/record_fixtures.py`.

Bis zum 2026-08-08 standen sie hier als Literale, weil das Aufzeichnungsskript
auf HTTP 401 lief und Zefix als «braucht Zugangsdaten» galt. Der Messwert
stimmte und galt der falschen Adresse: Das Skript fragte `ZefixPublicREST`,
der Server spricht mit `ZefixREST` — und das antwortet ohne jede Anmeldung.
Was der Vergleich mit der echten Quelle ergeben hat, steht im CHANGELOG.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fixture_data import fixture_json
from pydantic import ValidationError

from register_mcp.server import (
    ZEFIX_BASE,
    CompanyByEhraIdInput,
    CompanyByUidInput,
    CompanySearchInput,
    LegalFormsInput,
    MunicipalitiesInput,
    VerifyCompanyInput,
    zefix_get_company,
    zefix_get_company_by_uid,
    zefix_list_legal_forms,
    zefix_list_municipalities,
    zefix_search_companies,
    zefix_verify_company,
)

# ---------------------------------------------------------------------------
# Aufgezeichnete Antworten
# ---------------------------------------------------------------------------

MOCK_LEGAL_FORMS = fixture_json("zefix_legal_forms.json")
MOCK_FIRM_SEARCH_RESULT = fixture_json("zefix_search.json")
MOCK_FIRM_DETAIL = fixture_json("zefix_firm_detail.json")
MOCK_COMMUNITIES = fixture_json("zefix_communities.json")

# Statuscode UND Rumpf, weil beides zusammen den Befund ausmacht: Eine Suche
# ohne Treffer kommt mit HTTP 404, nicht mit 200.
_NO_RESULT = fixture_json("zefix_no_result.json")
NO_RESULT_STATUS = _NO_RESULT["status_code"]
MOCK_NO_RESULT = _NO_RESULT["body"]

# Aus den Fixtures gelesen statt danebengeschrieben — eine Kopie waere eine
# zweite Stelle, an der die Angabe falsch sein kann.
FIRST_HIT = MOCK_FIRM_SEARCH_RESULT["list"][0]
FIRST_NAME = FIRST_HIT["name"]
FIRST_EHRAID = FIRST_HIT["ehraid"]
FIRST_UID = FIRST_HIT["uidFormatted"]
DETAIL_EHRAID = MOCK_FIRM_DETAIL["ehraid"]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _mock_legal_forms(route_mock):
    """Helper to add legal forms mock to respx router."""
    route_mock.get(f"{ZEFIX_BASE}/legalForm").mock(
        return_value=httpx.Response(200, json=MOCK_LEGAL_FORMS)
    )


# ---------------------------------------------------------------------------
# zefix_search_companies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_companies_by_name_markdown():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.post(f"{ZEFIX_BASE}/firm/search.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_SEARCH_RESULT)
        )
        result = await zefix_search_companies(
            CompanySearchInput(name=FIRST_NAME.split()[0], response_format="markdown")
        )
    assert FIRST_NAME in result
    assert FIRST_UID in result
    form = next(f for f in MOCK_LEGAL_FORMS if f["id"] == FIRST_HIT["legalFormId"])
    assert form["name"]["de"] in result
    assert FIRST_HIT["status"] in result
    assert "✅" in result


@pytest.mark.asyncio
async def test_search_companies_by_name_json():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.post(f"{ZEFIX_BASE}/firm/search.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_SEARCH_RESULT)
        )
        result = await zefix_search_companies(
            CompanySearchInput(name=FIRST_NAME.split()[0], response_format="json")
        )
    data = json.loads(result)
    # Die aufgezeichnete Suche liefert 35 Treffer aus mehreren Kantonen — der
    # erfundene Vorgaenger hatte genau einen, und damit hat kein Test je eine
    # Trefferliste gesehen, die laenger ist als ihre Kopfzeile.
    assert len(MOCK_FIRM_SEARCH_RESULT["list"]) > 1
    assert data["count"] == len(MOCK_FIRM_SEARCH_RESULT["list"])
    assert data["results"][0]["name"] == FIRST_NAME
    assert data["results"][0]["uid"] == FIRST_UID
    assert data["results"][0]["status"] == FIRST_HIT["status"]


@pytest.mark.asyncio
async def test_search_companies_no_results():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.post(f"{ZEFIX_BASE}/firm/search.json").mock(
            return_value=httpx.Response(200, json=MOCK_NO_RESULT)
        )
        result = await zefix_search_companies(CompanySearchInput(name="XxXxNichtExistentXxXx"))
    assert "Keine Ergebnisse" in result


@pytest.mark.asyncio
async def test_search_companies_requires_name_or_canton():
    # Runtime guard fires when both name and canton are None
    params = CompanySearchInput(name=None, canton=None)
    result = await zefix_search_companies(params)
    assert "Fehler" in result


@pytest.mark.asyncio
async def test_search_companies_invalid_canton():
    # `ValidationError` allein pinnt das nicht: ein Tippfehler in `name=` wuerde
    # als `extra_forbidden` denselben Typ werfen und der Test bliebe gruen.
    # Geprueft wird deshalb auf Fehlertyp und Feld — nicht auf den Meldungstext,
    # der deutsch ist und die Kantonsliste enthaelt.
    with pytest.raises(ValidationError) as excinfo:
        CompanySearchInput(name="Test", canton="XX")
    assert [(e["type"], e["loc"]) for e in excinfo.value.errors()] == [("value_error", ("canton",))]


@pytest.mark.asyncio
async def test_search_companies_with_legal_form_filter():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.post(f"{ZEFIX_BASE}/firm/search.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_SEARCH_RESULT)
        )
        result = await zefix_search_companies(
            CompanySearchInput(name=FIRST_NAME.split()[0], legal_form_ids=[3], canton="ZH")
        )
    assert FIRST_NAME in result


# ---------------------------------------------------------------------------
# zefix_get_company
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_company_markdown():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.get(f"{ZEFIX_BASE}/firm/{DETAIL_EHRAID}.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_DETAIL)
        )
        result = await zefix_get_company(CompanyByEhraIdInput(ehraid=DETAIL_EHRAID))
    # Erwartungen aus der Fixture abgeleitet, nicht danebengeschrieben.
    assert MOCK_FIRM_DETAIL["name"] in result
    assert MOCK_FIRM_DETAIL["purpose"][:40] in result
    mutation_keys = {
        m["key"] for p in MOCK_FIRM_DETAIL["shabPub"] for m in p.get("mutationTypes", [])
    }
    assert mutation_keys, "Fixture ohne mutationTypes — dann prueft das nichts"
    assert any(k in result for k in mutation_keys)
    form = next(f for f in MOCK_LEGAL_FORMS if f["id"] == MOCK_FIRM_DETAIL["legalFormId"])
    assert form["name"]["de"] in result
    # Der SHAB-Volltext ist in der Fixture redigiert und darf auch nicht in die
    # Antwort geraten: Er nennt eingetragene Personen mit Wohnort.
    assert "redigiert" not in result


@pytest.mark.asyncio
async def test_get_company_json():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.get(f"{ZEFIX_BASE}/firm/{DETAIL_EHRAID}.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_DETAIL)
        )
        result = await zefix_get_company(
            CompanyByEhraIdInput(ehraid=DETAIL_EHRAID, response_format="json")
        )
    data = json.loads(result)
    assert data["name"] == MOCK_FIRM_DETAIL["name"]
    assert data["zweck"] == MOCK_FIRM_DETAIL["purpose"]
    assert len(data["shabPublikationen"]) == min(5, len(MOCK_FIRM_DETAIL["shabPub"]))


@pytest.mark.asyncio
async def test_get_company_not_found():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.get(f"{ZEFIX_BASE}/firm/999999.json").mock(return_value=httpx.Response(404))
        result = await zefix_get_company(CompanyByEhraIdInput(ehraid=999999))
    assert "Fehler 404" in result


# ---------------------------------------------------------------------------
# zefix_get_company_by_uid
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_company_by_uid_formatted():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.post(f"{ZEFIX_BASE}/firm/search.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_SEARCH_RESULT)
        )
        respx.get(f"{ZEFIX_BASE}/firm/{DETAIL_EHRAID}.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_DETAIL)
        )
        result = await zefix_get_company_by_uid(CompanyByUidInput(uid=FIRST_UID))
    assert FIRST_NAME in result
    assert FIRST_UID in result


@pytest.mark.asyncio
async def test_get_company_by_uid_unformatted():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.post(f"{ZEFIX_BASE}/firm/search.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_SEARCH_RESULT)
        )
        respx.get(f"{ZEFIX_BASE}/firm/{DETAIL_EHRAID}.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_DETAIL)
        )
        result = await zefix_get_company_by_uid(
            CompanyByUidInput(uid=FIRST_UID.replace("-", "").replace(".", ""))
        )
    assert FIRST_NAME in result


@pytest.mark.asyncio
async def test_get_company_by_uid_invalid():
    # 9 chars total but only 6 digits → fails the 9-digit check inside the function
    result = await zefix_get_company_by_uid(CompanyByUidInput(uid="CHE123456"))
    assert "Ungültige UID" in result


# ---------------------------------------------------------------------------
# zefix_verify_company
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_company_active():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.post(f"{ZEFIX_BASE}/firm/search.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_SEARCH_RESULT)
        )
        result = await zefix_verify_company(VerifyCompanyInput(name="Lehrmittelverlag Zürich AG"))
    assert "✅" in result
    assert "Aktive Einträge" in result
    assert "Lehrmittelverlag Zürich AG" in result


@pytest.mark.asyncio
async def test_verify_company_not_found():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.post(f"{ZEFIX_BASE}/firm/search.json").mock(
            return_value=httpx.Response(200, json=MOCK_NO_RESULT)
        )
        result = await zefix_verify_company(VerifyCompanyInput(name="FirmaXxNichtExistentXx"))
    assert "Nicht im Handelsregister gefunden" in result


@pytest.mark.asyncio
async def test_verify_company_dissolved():
    dissolved_result = {
        "list": [
            {
                **MOCK_FIRM_SEARCH_RESULT["list"][0],
                "status": "GELOESCHT",
                "deleteDate": "2023-01-15",
            }
        ],
        "hasMoreResults": False,
        "offset": 0,
        "maxEntries": 10,
        "maxOffset": 1,
    }
    with respx.mock:
        _mock_legal_forms(respx)
        respx.post(f"{ZEFIX_BASE}/firm/search.json").mock(
            return_value=httpx.Response(200, json=dissolved_result)
        )
        result = await zefix_verify_company(VerifyCompanyInput(name="Gelöschte Firma AG"))
    assert "❌" in result
    assert "Keine aktiven Einträge" in result


# ---------------------------------------------------------------------------
# zefix_list_legal_forms
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_legal_forms_markdown():
    with respx.mock:
        respx.get(f"{ZEFIX_BASE}/legalForm").mock(
            return_value=httpx.Response(200, json=MOCK_LEGAL_FORMS)
        )
        result = await zefix_list_legal_forms(LegalFormsInput())
    assert "Aktiengesellschaft" in result
    assert "AG" in result
    assert "| 3 |" in result


@pytest.mark.asyncio
async def test_list_legal_forms_json():
    with respx.mock:
        respx.get(f"{ZEFIX_BASE}/legalForm").mock(
            return_value=httpx.Response(200, json=MOCK_LEGAL_FORMS)
        )
        result = await zefix_list_legal_forms(LegalFormsInput(response_format="json"))
    data = json.loads(result)
    assert len(data) == len(MOCK_LEGAL_FORMS)
    assert [d["id"] for d in data] == [f["id"] for f in MOCK_LEGAL_FORMS]


@pytest.mark.asyncio
async def test_list_legal_forms_english():
    with respx.mock:
        respx.get(f"{ZEFIX_BASE}/legalForm").mock(
            return_value=httpx.Response(200, json=MOCK_LEGAL_FORMS)
        )
        result = await zefix_list_legal_forms(LegalFormsInput(language="en"))
    assert "Corporation" in result


# ---------------------------------------------------------------------------
# zefix_list_municipalities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_municipalities_all():
    with respx.mock:
        respx.get(f"{ZEFIX_BASE}/community").mock(
            return_value=httpx.Response(200, json=MOCK_COMMUNITIES)
        )
        result = await zefix_list_municipalities(MunicipalitiesInput())
    for c in MOCK_COMMUNITIES[:5]:
        assert c["name"] in result


@pytest.mark.asyncio
async def test_list_municipalities_canton_filter():
    with respx.mock:
        respx.get(f"{ZEFIX_BASE}/community").mock(
            return_value=httpx.Response(200, json=MOCK_COMMUNITIES)
        )
        result = await zefix_list_municipalities(MunicipalitiesInput(canton="ZH"))
    assert "Zürich" in result
    assert "Schlieren" in result
    assert "Bern" not in result


@pytest.mark.asyncio
async def test_list_municipalities_json():
    with respx.mock:
        respx.get(f"{ZEFIX_BASE}/community").mock(
            return_value=httpx.Response(200, json=MOCK_COMMUNITIES)
        )
        result = await zefix_list_municipalities(
            MunicipalitiesInput(canton="ZH", response_format="json")
        )
    data = json.loads(result)
    expected = [c for c in MOCK_COMMUNITIES if c["canton"] == "ZH"]
    assert expected, "Fixture ohne ZH-Gemeinden — Auswahlregel pruefen"
    assert len(data) == len(expected)
    assert all(c["canton"] == "ZH" for c in data)


# ---------------------------------------------------------------------------
# Live tests (excluded from CI with -m "not live")
# ---------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_search_migros():
    """Live: Search for Migros in Zefix."""
    result = await zefix_search_companies(CompanySearchInput(name="Migros", max_results=3))
    assert "Migros" in result
    assert "CHE-" in result


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_verify_ewz():
    """Live: Verify Elektrizitätswerk der Stadt Zürich (EWZ)."""
    result = await zefix_verify_company(
        VerifyCompanyInput(name="Elektrizitätswerk der Stadt Zürich", canton="ZH")
    )
    assert "✅" in result


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_get_company_by_uid_ewz():
    """Live: Lookup EWZ by known UID."""
    result = await zefix_get_company_by_uid(CompanyByUidInput(uid="CHE-108.954.978"))
    assert "Elektrizitätswerk" in result


# ---------------------------------------------------------------------------
# Die zwei Befunde, die beim Aufzeichnen herauskamen
# ---------------------------------------------------------------------------


def test_legal_seat_id_is_a_bfs_number_not_an_internal_id():
    """Warum das Werkzeug die Auflösung selbst macht.

    Eine Firma trägt ihren Sitz als `legalSeatId`. Die Gemeindeliste führt zwei
    Zahlenspalten, `id` und `bfsId`, und `legalSeatId` trifft die zweite. Über
    die erste nachgeschlagen kommt kein Fehler heraus, sondern **eine andere,
    echte Schweizer Gemeinde** — die unangenehmste Sorte falsch: vollständig,
    plausibel, formatiert, und über woanders.

    Die erfundene Vorgänger-Fixture hatte für Zürich `{"id": 261, "bfsId": 261}`
    stehen. Mit dieser Gleichheit stimmen beide Auflösungen überein, und die
    Verwechslung ist unsichtbar. Sie gilt für **keine** der 2112 Gemeinden.
    """
    by_id = {c["id"]: c for c in MOCK_COMMUNITIES}
    by_bfs = {c["bfsId"]: c for c in MOCK_COMMUNITIES}
    assert not [c for c in MOCK_COMMUNITIES if c["id"] == c["bfsId"]], (
        "Zuschnitt mit id == bfsId — daran laesst sich die Verwechslung nicht zeigen"
    )

    checked = collisions = 0
    for hit in MOCK_FIRM_SEARCH_RESULT["list"]:
        seat_id, seat = hit["legalSeatId"], hit["legalSeat"]
        if seat_id not in by_bfs:
            continue
        checked += 1
        assert by_bfs[seat_id]["name"] == seat
        if seat_id in by_id:
            collisions += 1
            assert by_id[seat_id]["name"] != seat, (
                f"legalSeatId {seat_id}: ueber `id` faellt dieselbe Gemeinde "
                "heraus — dann belegt der Zuschnitt den Befund nicht mehr"
            )
    assert checked >= 5, "zu wenige aufloesbare Sitze im Zuschnitt"
    assert collisions >= 1, (
        "keine legalSeatId, die auch als `id` vorkommt — genau die Faelle "
        "machen die Verwechslung still statt laut"
    )


@pytest.mark.asyncio
async def test_municipality_lookup_resolves_via_bfs_id():
    """Die Auflösung liefert den Sitz, nicht die gleichnamige Zahl."""
    hit = next(
        h
        for h in MOCK_FIRM_SEARCH_RESULT["list"]
        if any(
            c["bfsId"] == h["legalSeatId"] and c["id"] != h["legalSeatId"] for c in MOCK_COMMUNITIES
        )
    )
    wrong = next((c for c in MOCK_COMMUNITIES if c["id"] == hit["legalSeatId"]), None)
    with respx.mock:
        respx.get(f"{ZEFIX_BASE}/community").mock(
            return_value=httpx.Response(200, json=MOCK_COMMUNITIES)
        )
        result = await zefix_list_municipalities(
            MunicipalitiesInput(legal_seat_id=hit["legalSeatId"], response_format="json")
        )
    data = json.loads(result)
    assert len(data) == 1
    assert data[0]["name"] == hit["legalSeat"]
    assert data[0]["bfsId"] == hit["legalSeatId"]
    if wrong is not None:
        assert data[0]["name"] != wrong["name"]


@pytest.mark.asyncio
async def test_search_without_hits_answers_in_the_terms_of_a_search():
    """Zefix meldet «keine Treffer» mit HTTP 404, nicht mit 200.

    Die erfundene Fixture legte den NORESULT-Umschlag in eine 200er-Antwort,
    und der Test dazu bestand. Gegen die echte Quelle warf `raise_for_status()`,
    und die generische 404-Meldung antwortete auf eine **Namenssuche** mit
    «Bitte EHRAID oder UID prüfen» — nach zwei Angaben, die der Aufrufer nie
    gemacht hatte. Der freundliche Zweig war unerreichbar.
    """
    assert NO_RESULT_STATUS == 404, (
        "Die Quelle antwortet nicht mehr mit 404 — neu aufzeichnen und diesen Zweig pruefen."
    )
    with respx.mock:
        _mock_legal_forms(respx)
        respx.post(f"{ZEFIX_BASE}/firm/search.json").mock(
            return_value=httpx.Response(NO_RESULT_STATUS, json=MOCK_NO_RESULT)
        )
        result = await zefix_search_companies(CompanySearchInput(name="XxXxNichtExistentXxXx"))
    assert "Keine Ergebnisse" in result
    assert "EHRAID" not in result and "UID" not in result
