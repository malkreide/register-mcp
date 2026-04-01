"""Tests for register-mcp — Swiss Commercial Register MCP Server."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

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
# Fixtures
# ---------------------------------------------------------------------------

MOCK_LEGAL_FORMS = [
    {"id": 3, "name": {"de": "Aktiengesellschaft", "en": "Corporation"}, "kurzform": {"de": "AG"}, "sort": 300},
    {"id": 4, "name": {"de": "Gesellschaft mit beschränkter Haftung", "en": "LLC"}, "kurzform": {"de": "GmbH"}, "sort": 400},
    {"id": 7, "name": {"de": "Stiftung", "en": "Foundation"}, "kurzform": {"de": "Stiftung"}, "sort": 700},
    {"id": 8, "name": {"de": "Öffentlich-rechtliche Körperschaft", "en": "Public entity"}, "kurzform": {"de": "Körperschaft"}, "sort": 800},
]

MOCK_FIRM_SEARCH_RESULT = {
    "list": [
        {
            "name": "Lehrmittelverlag Zürich AG",
            "ehraid": 123456,
            "uid": "CHE123456789",
            "uidFormatted": "CHE-123.456.789",
            "chid": "CH02030001234",
            "chidFormatted": "CH-020-3000123-4",
            "legalSeatId": 261,
            "legalSeat": "Zürich",
            "registerOfficeId": 20,
            "legalFormId": 3,
            "status": "EXISTIEREND",
            "rabId": 0,
            "shabDate": "2024-06-15",
            "deleteDate": None,
            "cantonalExcerptWeb": "https://zh.chregister.ch/cr-portal/auszug/auszug.xhtml?uid=CHE-123.456.789",
        }
    ],
    "hasMoreResults": False,
    "offset": 0,
    "maxEntries": 10,
    "maxOffset": 1,
}

MOCK_FIRM_DETAIL = {
    **MOCK_FIRM_SEARCH_RESULT["list"][0],
    "translation": None,
    "purpose": "Herausgabe und Vertrieb von Lehrmitteln für Schulen.",
    "shabPub": [
        {
            "shabDate": "2024-06-15",
            "shabNr": 0,
            "shabPage": 0,
            "shabId": 1005999001,
            "shabMutationStatus": 0,
            "registryOfficeId": 20,
            "registryOfficeCanton": "ZH",
            "registryOfficeJournalId": 11000,
            "registryOfficeJournalDate": "2024-06-12",
            "message": "Mutation Organe.",
            "mutationTypes": [{"id": 17, "key": "aenderungorgane"}],
        }
    ],
}

MOCK_COMMUNITIES = [
    {"id": 261, "bfsId": 261, "canton": "ZH", "name": "Zürich", "registryOfficeId": 20},
    {"id": 247, "bfsId": 132, "canton": "ZH", "name": "Schlieren", "registryOfficeId": 20},
    {"id": 150, "bfsId": 351, "canton": "BE", "name": "Bern", "registryOfficeId": 36},
]

MOCK_NO_RESULT = {
    "error": {"code": "API.ZFR.SEARCH.NORESULT", "title": "NORESULT", "message": None, "suggestion": "", "internal_message": None}
}


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
            CompanySearchInput(name="Lehrmittelverlag", response_format="markdown")
        )
    assert "Lehrmittelverlag Zürich AG" in result
    assert "CHE-123.456.789" in result
    assert "Aktiengesellschaft" in result
    assert "EXISTIEREND" in result
    assert "✅" in result


@pytest.mark.asyncio
async def test_search_companies_by_name_json():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.post(f"{ZEFIX_BASE}/firm/search.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_SEARCH_RESULT)
        )
        result = await zefix_search_companies(
            CompanySearchInput(name="Lehrmittelverlag", response_format="json")
        )
    data = json.loads(result)
    assert data["count"] == 1
    assert data["results"][0]["name"] == "Lehrmittelverlag Zürich AG"
    assert data["results"][0]["uid"] == "CHE-123.456.789"
    assert data["results"][0]["status"] == "EXISTIEREND"


@pytest.mark.asyncio
async def test_search_companies_no_results():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.post(f"{ZEFIX_BASE}/firm/search.json").mock(
            return_value=httpx.Response(200, json=MOCK_NO_RESULT)
        )
        result = await zefix_search_companies(
            CompanySearchInput(name="XxXxNichtExistentXxXx")
        )
    assert "Keine Ergebnisse" in result


@pytest.mark.asyncio
async def test_search_companies_requires_name_or_canton():
    # Runtime guard fires when both name and canton are None
    params = CompanySearchInput(name=None, canton=None)
    result = await zefix_search_companies(params)
    assert "Fehler" in result


@pytest.mark.asyncio
async def test_search_companies_invalid_canton():
    with pytest.raises(Exception):
        CompanySearchInput(name="Test", canton="XX")


@pytest.mark.asyncio
async def test_search_companies_with_legal_form_filter():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.post(f"{ZEFIX_BASE}/firm/search.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_SEARCH_RESULT)
        )
        result = await zefix_search_companies(
            CompanySearchInput(name="Lehrmittelverlag", legal_form_ids=[3], canton="ZH")
        )
    assert "Lehrmittelverlag Zürich AG" in result


# ---------------------------------------------------------------------------
# zefix_get_company
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_company_markdown():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.get(f"{ZEFIX_BASE}/firm/123456.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_DETAIL)
        )
        result = await zefix_get_company(CompanyByEhraIdInput(ehraid=123456))
    assert "Lehrmittelverlag Zürich AG" in result
    assert "Herausgabe und Vertrieb" in result
    assert "aenderungorgane" in result
    assert "Aktiengesellschaft" in result


@pytest.mark.asyncio
async def test_get_company_json():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.get(f"{ZEFIX_BASE}/firm/123456.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_DETAIL)
        )
        result = await zefix_get_company(
            CompanyByEhraIdInput(ehraid=123456, response_format="json")
        )
    data = json.loads(result)
    assert data["name"] == "Lehrmittelverlag Zürich AG"
    assert data["zweck"] == "Herausgabe und Vertrieb von Lehrmitteln für Schulen."
    assert len(data["shabPublikationen"]) == 1


@pytest.mark.asyncio
async def test_get_company_not_found():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.get(f"{ZEFIX_BASE}/firm/999999.json").mock(
            return_value=httpx.Response(404)
        )
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
        respx.get(f"{ZEFIX_BASE}/firm/123456.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_DETAIL)
        )
        result = await zefix_get_company_by_uid(
            CompanyByUidInput(uid="CHE-123.456.789")
        )
    assert "Lehrmittelverlag Zürich AG" in result
    assert "CHE-123.456.789" in result


@pytest.mark.asyncio
async def test_get_company_by_uid_unformatted():
    with respx.mock:
        _mock_legal_forms(respx)
        respx.post(f"{ZEFIX_BASE}/firm/search.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_SEARCH_RESULT)
        )
        respx.get(f"{ZEFIX_BASE}/firm/123456.json").mock(
            return_value=httpx.Response(200, json=MOCK_FIRM_DETAIL)
        )
        result = await zefix_get_company_by_uid(
            CompanyByUidInput(uid="CHE123456789")
        )
    assert "Lehrmittelverlag Zürich AG" in result


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
        result = await zefix_verify_company(
            VerifyCompanyInput(name="Lehrmittelverlag Zürich AG")
        )
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
        result = await zefix_verify_company(
            VerifyCompanyInput(name="FirmaXxNichtExistentXx")
        )
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
        result = await zefix_verify_company(
            VerifyCompanyInput(name="Gelöschte Firma AG")
        )
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
    assert len(data) == 4
    ids = [d["id"] for d in data]
    assert 3 in ids and 4 in ids


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
    assert "Zürich" in result
    assert "Bern" in result


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
    assert len(data) == 2
    assert all(c["canton"] == "ZH" for c in data)


# ---------------------------------------------------------------------------
# Live tests (excluded from CI with -m "not live")
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.asyncio
async def test_live_search_migros():
    """Live: Search for Migros in Zefix."""
    result = await zefix_search_companies(
        CompanySearchInput(name="Migros", max_results=3)
    )
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
    result = await zefix_get_company_by_uid(
        CompanyByUidInput(uid="CHE-108.954.978")
    )
    assert "Elektrizitätswerk" in result
