"""Tests for the gazette (amtsblattportal) tools and the three upstream quirks."""

from __future__ import annotations

import json
from time import monotonic

import httpx
import pytest
import respx

from register_mcp import server
from register_mcp.server import (
    ALLOWED_GAZETTE_PARAMS,
    ALLOWED_HOSTS,
    GAZETTE_BASE,
    ZEFIX_BASE,
    EgressDenied,
    GazettePublicationInput,
    GazettePublicationsInput,
    GazetteStatusInput,
    _make_client,
    _parse_publication_xml,
    _reset_rubrics_cache,
    gazette_company_publications,
    gazette_get_publication,
    gazette_source_status,
)

# ---------------------------------------------------------------------------
# Fixtures / mock payloads
# ---------------------------------------------------------------------------

MOCK_RUBRICS = [
    {
        "code": "HR",
        "name": {"de": "Handelsregister", "en": "Commercial register"},
        "subRubrics": [
            {"code": "HR01", "name": {"de": "Neueintragungen"}},
            {"code": "HR03", "name": {"de": "Löschungen"}},
        ],
    },
    {
        # SB is Schuldbetreibungen (debt collection) — NOT Submissionen.
        # Public procurement lives in the cantonal OB-* rubrics below.
        "code": "SB",
        "name": {"de": "Schuldbetreibungen", "en": "Debt collection"},
        "subRubrics": [{"code": "SB01", "name": {"de": "Zahlungsbefehl"}}],
    },
    {
        "code": "LS",
        "name": {"de": "Schuldenrufe"},
        "subRubrics": [{"code": "LS01", "name": {"de": "Liquidationsschuldenruf"}}],
    },
    # A couple of cantonal rubrics so the optional rubric filter on the UID join
    # has more than one valid code to validate against.
    {"code": "OB-AR", "name": {"de": "Öffentliches Beschaffungswesen"}, "subRubrics": []},
    {"code": "OB-BS", "name": {"de": "Öffentliches Beschaffungswesen"}, "subRubrics": []},
    {"code": "OB-TI", "name": {"de": "Öffentliches Beschaffungswesen"}, "subRubrics": []},
    {"code": "OB-ZG", "name": {"de": "Öffentliches Beschaffungswesen"}, "subRubrics": []},
]


def _pub_item(pub_id: str, rubric: str, sub: str, date: str, title: str) -> dict:
    return {
        "meta": {
            "id": pub_id,
            "rubric": rubric,
            "subRubric": sub,
            "language": "de",
            "registrationOffice": {"id": "x", "displayName": "Bundesamt für Justiz (BJ)"},
            "publicationNumber": f"{sub}-{pub_id[:6]}",
            "publicationState": "PUBLISHED",
            "publicationDate": f"{date}T00:00:00.000Z",
            "cantons": ["ZG"],
            "title": {"de": title, "en": title},
        },
        "links": [],
        "attachments": [],
        "content": None,
    }


MOCK_SEARCH = {
    "content": [
        _pub_item("1611620c-ff25-4043-bf0d-395b0352d35b", "HR", "HR03", "2026-07-07",
                  "Löschung E-smog-free AG in Liquidation, Hünenberg"),
        _pub_item("68a62f77-8c13-4325-8e32-e3b11b33aa09", "LS", "LS01", "2024-11-11",
                  "Liquidationsschuldenruf E-smog-free AG in Liquidation"),
    ],
    "total": 4,
    "pageRequest": {"page": 0, "size": 50},
}

MOCK_SEARCH_EMPTY = {"content": [], "total": 0, "pageRequest": {"page": 0, "size": 20}}

# Quirk 1 — filter silently ignored -> full corpus returned with HTTP 200.
MOCK_SEARCH_CORPUS = {"content": [], "total": 2_790_323, "pageRequest": {"page": 0, "size": 50}}

MOCK_XML_HR03 = """<?xml version='1.0' encoding='UTF-8'?>
<HR03:publication xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:HR03="https://shab.ch/shab/HR03-export">
<meta>
  <id>1611620c-ff25-4043-bf0d-395b0352d35b</id>
  <rubric>HR</rubric>
  <subRubric>HR03</subRubric>
  <language>de</language>
  <registrationOffice>
    <id>e15a629a</id>
    <displayName>Bundesamt für Justiz (BJ)</displayName>
  </registrationOffice>
  <publicationNumber>HR03-1006699664</publicationNumber>
  <publicationDate>2026-07-07</publicationDate>
  <title>
    <de>Löschung E-smog-free AG in Liquidation, Hünenberg</de>
    <en>Deletion E-smog-free AG in Liquidation</en>
  </title>
</meta>
<content>
  <journalNumber>13310</journalNumber>
  <publicationText>E-smog-free AG in Liquidation, in Hünenberg, CHE-116.115.052, Aktiengesellschaft. Die Liquidation ist beendet. Die Gesellschaft wird gelöscht.</publicationText>
  <commonsActual>
    <company>
      <name>E-smog-free AG in Liquidation</name>
      <uid>CHE-116.115.052</uid>
      <seat>Hünenberg</seat>
      <legalForm>0106</legalForm>
      <address>
        <street>Bösch</street>
        <houseNumber>35</houseNumber>
        <swissZipCode>6331</swissZipCode>
        <town>Hünenberg</town>
      </address>
    </company>
    <purpose>Erbringung von Dienstleistungen.</purpose>
  </commonsActual>
</content>
</HR03:publication>"""

# An unknown rubric with a namespace this code has never seen, no company block,
# and a rubric-specific element that must land in additional_fields.
MOCK_XML_UNKNOWN = """<?xml version='1.0' encoding='UTF-8'?>
<XY99:publication xmlns:XY99="https://shab.ch/shab/XY99-export">
<meta>
  <id>deadbeef-0000</id>
  <rubric>XY</rubric>
  <subRubric>XY99</subRubric>
  <title><de>Unbekannter Publikationstyp</de></title>
</meta>
<content>
  <publicationText>Amtlicher Fliesstext einer unbekannten Rubrik.</publicationText>
  <someExoticField>
    <nested>Wert</nested>
  </someExoticField>
</content>
</XY99:publication>"""


@pytest.fixture(autouse=True)
def _clear_caches():
    _reset_rubrics_cache()
    yield
    _reset_rubrics_cache()


def _seed_rubrics():
    """Populate the rubrics cache so validation makes no HTTP call."""
    server._rubrics_cache = (monotonic(), MOCK_RUBRICS)


def _mock_rubrics():
    respx.get(f"{GAZETTE_BASE}/rubrics").mock(
        return_value=httpx.Response(200, json=MOCK_RUBRICS)
    )


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_company_publications_happy_path():
    _seed_rubrics()
    with respx.mock:
        respx.get(f"{GAZETTE_BASE}/publications").mock(
            return_value=httpx.Response(200, json=MOCK_SEARCH)
        )
        result = await gazette_company_publications(
            GazettePublicationsInput(uid="CHE-116.115.052")
        )
    assert "CHE-116.115.052" in result
    assert "E-smog-free" in result
    # newest first
    assert result.index("2026-07-07") < result.index("2024-11-11")
    assert "amtsblattportal.ch" in result  # attribution footer
    assert "provenance: live_api" in result


@pytest.mark.asyncio
async def test_company_publications_json_envelope():
    _seed_rubrics()
    with respx.mock:
        respx.get(f"{GAZETTE_BASE}/publications").mock(
            return_value=httpx.Response(200, json=MOCK_SEARCH)
        )
        result = await gazette_company_publications(
            GazettePublicationsInput(uid="CHE-116.115.052", response_format="json")
        )
    data = json.loads(result)
    assert data["uid"] == "CHE-116.115.052"
    assert data["count"] == 2
    assert data["provenance"] == "live_api"
    assert "No liability" in data["attribution"]


@pytest.mark.asyncio
async def test_company_publications_rejects_bad_uid():
    # Regex guard fires BEFORE any HTTP call — 2 digits is not a valid UID.
    result = await gazette_company_publications(
        GazettePublicationsInput(uid="CHE-1.2.3")
    )
    assert "Ungültige UID" in result


@pytest.mark.asyncio
async def test_company_publications_optional_rubric_filter():
    """The UID join accepts an optional (validated) rubric filter — still UID-scoped."""
    _seed_rubrics()
    with respx.mock:
        route = respx.get(f"{GAZETTE_BASE}/publications").mock(
            return_value=httpx.Response(200, json=MOCK_SEARCH)
        )
        result = await gazette_company_publications(
            GazettePublicationsInput(uid="CHE-116.115.052", rubric="HR")
        )
    # the query is always keyed on the UID — never a free-text/person search
    assert route.calls[0].request.url.params.get("uids") == "CHE-116.115.052"
    assert route.calls[0].request.url.params.get("rubrics") == "HR"
    assert "E-smog-free" in result


def test_keyword_and_cantons_are_not_allow_listed():
    """Fail-closed: the person-profiling params can never reach the query string."""
    assert "keyword" not in ALLOWED_GAZETTE_PARAMS
    assert "cantons" not in ALLOWED_GAZETTE_PARAMS
    # the UID-scoped params the join actually needs are present
    assert {"uids", "rubrics", "subRubrics"} <= ALLOWED_GAZETTE_PARAMS


@pytest.mark.asyncio
async def test_get_publication_hr_full_text():
    with respx.mock:
        respx.get(f"{GAZETTE_BASE}/publications/abc-1234-xyz/xml").mock(
            return_value=httpx.Response(200, text=MOCK_XML_HR03)
        )
        result = await gazette_get_publication(GazettePublicationInput(id="abc-1234-xyz"))
    assert "Die Liquidation ist beendet" in result
    assert "E-smog-free AG in Liquidation" in result
    assert "CHE-116.115.052" in result
    assert "Bösch" in result  # nested address rendered


@pytest.mark.asyncio
async def test_get_publication_json():
    with respx.mock:
        respx.get(f"{GAZETTE_BASE}/publications/abc-1234-xyz/xml").mock(
            return_value=httpx.Response(200, text=MOCK_XML_HR03)
        )
        result = await gazette_get_publication(
            GazettePublicationInput(id="abc-1234-xyz", response_format="json")
        )
    data = json.loads(result)
    assert data["company"]["uid"] == "CHE-116.115.052"
    assert "publicationText" in data
    assert data["provenance"] == "live_api"


@pytest.mark.asyncio
async def test_source_status_reports_both():
    with respx.mock:
        respx.get(f"{ZEFIX_BASE}/legalForm").mock(return_value=httpx.Response(200, json=[]))
        _mock_rubrics()
        result = await gazette_source_status(GazetteStatusInput())
    assert "Zefix" in result
    assert "Amtsblattportal" in result
    assert "✅" in result


# ---------------------------------------------------------------------------
# Resilience: retry, timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_on_503_then_success(monkeypatch):
    monkeypatch.setattr(server, "GAZETTE_RETRY_BACKOFF", 0.0)
    _seed_rubrics()
    with respx.mock:
        route = respx.get(f"{GAZETTE_BASE}/publications").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json=MOCK_SEARCH),
            ]
        )
        result = await gazette_company_publications(
            GazettePublicationsInput(uid="CHE-116.115.052")
        )
    assert route.call_count == 2
    assert "E-smog-free" in result


@pytest.mark.asyncio
async def test_timeout_is_clean_error():
    _seed_rubrics()
    with respx.mock:
        respx.get(f"{GAZETTE_BASE}/publications").mock(
            side_effect=httpx.ConnectTimeout("boom")
        )
        result = await gazette_company_publications(
            GazettePublicationsInput(uid="CHE-116.115.052")
        )
    assert isinstance(result, str)
    assert "Timeout" in result
    assert "Traceback" not in result


@pytest.mark.asyncio
async def test_network_error_is_clean_error():
    _seed_rubrics()
    with respx.mock:
        respx.get(f"{GAZETTE_BASE}/publications").mock(
            side_effect=httpx.ConnectError("no route")
        )
        result = await gazette_company_publications(
            GazettePublicationsInput(uid="CHE-116.115.052")
        )
    assert "Verbindungsfehler" in result


# ---------------------------------------------------------------------------
# Quirk 1 — Silent Ignore
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quirk1_filter_ignored_is_rejected():
    _seed_rubrics()
    with respx.mock:
        respx.get(f"{GAZETTE_BASE}/publications").mock(
            return_value=httpx.Response(200, json=MOCK_SEARCH_CORPUS)
        )
        result = await gazette_company_publications(
            GazettePublicationsInput(uid="CHE-116.115.052")
        )
    assert "ignoriert" in result
    assert "nicht vertrauenswürdig" in result


# ---------------------------------------------------------------------------
# Quirk 2 — Silent Empty (invalid rubric, validated before any call)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quirk2_invalid_rubric_suggests_no_http():
    _seed_rubrics()
    with respx.mock:
        pub_route = respx.get(f"{GAZETTE_BASE}/publications").mock(
            return_value=httpx.Response(200, json=MOCK_SEARCH)
        )
        result = await gazette_company_publications(
            GazettePublicationsInput(uid="CHE-116.115.052", rubric="ZZZZ")
        )
    assert "Ungültiger rubric-Code" in result
    # closest valid codes suggested
    assert any(code in result for code in ("HR", "SB", "LS"))
    # No /publications call was made — validation short-circuited it.
    assert pub_route.call_count == 0


@pytest.mark.asyncio
async def test_quirk2_invalid_subrubric():
    _seed_rubrics()
    with respx.mock:
        respx.get(f"{GAZETTE_BASE}/publications").mock(
            return_value=httpx.Response(200, json=MOCK_SEARCH)
        )
        result = await gazette_company_publications(
            GazettePublicationsInput(uid="CHE-116.115.052", sub_rubric="HR99")
        )
    assert "Ungültiger subRubric-Code" in result
    assert "HR01" in result or "HR03" in result


# ---------------------------------------------------------------------------
# Quirk 3 — defensive XML parsing
# ---------------------------------------------------------------------------

def test_quirk3_unknown_rubric_xml_falls_back():
    parsed = _parse_publication_xml(MOCK_XML_UNKNOWN)
    # mandatory publicationText survived
    assert parsed["publicationText"] == "Amtlicher Fliesstext einer unbekannten Rubrik."
    # no company block on this rubric — empty, not an exception
    assert parsed["company"] == {}
    # the exotic rubric-specific element landed best-effort in additional_fields
    assert "someExoticField" in parsed["additional_fields"]


def test_quirk3_hr_xml_extracts_company():
    parsed = _parse_publication_xml(MOCK_XML_HR03)
    assert parsed["company"]["uid"] == "CHE-116.115.052"
    assert parsed["company"]["seat"] == "Hünenberg"
    assert isinstance(parsed["company"]["address"], dict)
    assert parsed["meta"]["rubric"] == "HR"


@pytest.mark.asyncio
async def test_get_publication_malformed_xml():
    with respx.mock:
        respx.get(f"{GAZETTE_BASE}/publications/bad-1234-xyz/xml").mock(
            return_value=httpx.Response(200, text="<not-well-formed>")
        )
        result = await gazette_get_publication(GazettePublicationInput(id="bad-1234-xyz"))
    assert "konnte nicht geparst werden" in result
    assert "Traceback" not in result


# ---------------------------------------------------------------------------
# Egress — the new host is allowed; redirects to unlisted hosts are blocked
# ---------------------------------------------------------------------------

def test_amtsblattportal_in_default_allowlist():
    assert "amtsblattportal.ch" in ALLOWED_HOSTS


@respx.mock
async def test_gazette_host_passes_egress():
    respx.get(f"{GAZETTE_BASE}/rubrics").mock(return_value=httpx.Response(200, json=[]))
    async with _make_client() as client:
        r = await client.get(f"{GAZETTE_BASE}/rubrics")
    assert r.status_code == 200


@respx.mock
async def test_gazette_redirect_to_evil_blocked():
    respx.get(f"{GAZETTE_BASE}/publications").mock(
        return_value=httpx.Response(302, headers={"location": "https://evil.example.com/"})
    )
    async with _make_client() as client:
        with pytest.raises(EgressDenied):
            await client.get(f"{GAZETTE_BASE}/publications")


# ---------------------------------------------------------------------------
# Live tests (excluded from CI with -m "not live")
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.asyncio
async def test_live_company_publications_join():
    """Live: the UID join — CHE-116.115.052 has publications."""
    _reset_rubrics_cache()
    result = await gazette_company_publications(
        GazettePublicationsInput(uid="CHE-116.115.052")
    )
    assert "CHE-116.115.052" in result


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_get_publication_reads_full_text():
    """Live: reading a single HR publication returns its full official text."""
    _reset_rubrics_cache()
    listing = await gazette_company_publications(
        GazettePublicationsInput(uid="CHE-116.115.052", rubric="HR", response_format="json")
    )
    data = json.loads(listing)
    pubs = data.get("publications") or []
    if not pubs:
        pytest.skip("no HR publications for this UID at test time")
    result = await gazette_get_publication(GazettePublicationInput(id=pubs[0]["id"]))
    assert "amtsblattportal.ch" in result
