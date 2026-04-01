"""
register-mcp: MCP server for Swiss commercial and company registers.

Provides access to:
  - Zefix (Handelsregister): Swiss Federal Commercial Register via ZefixREST API
  - UID Register: Swiss Enterprise Identification (Phase 2, SOAP)

Phase 1 (no auth): ZefixREST open endpoints — zefix.admin.ch/ZefixREST/api/v1
Phase 2 (Basic Auth, free): ZefixPublicREST — request access via zefix@bj.admin.ch

Use cases:
  - Lieferantenprüfung (vendor verification before procurement)
  - Vertragspartner-Due-Diligence (contract partner due diligence)
  - Schulvertragsprüfung (school contract verification)
  - HR-Dienstleister-Screening (HR service provider screening)
"""

from __future__ import annotations

import json
import os
import re
from enum import StrEnum
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZEFIX_BASE = "https://www.zefix.admin.ch/ZefixREST/api/v1"
ZEFIX_PUBLIC_BASE = "https://www.zefix.admin.ch/ZefixPublicREST/api/v1"
REQUEST_TIMEOUT = 15.0

CANTON_CODES = [
    "AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR",
    "JU", "LU", "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG",
    "TI", "UR", "VD", "VS", "ZG", "ZH",
]

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "register_mcp",
    instructions=(
        "Provides read-only access to the Swiss Federal Commercial Register (Zefix/Handelsregister) "
        "and supporting reference data. Use this server to verify companies, check registration status, "
        "lookup UID numbers, and retrieve SHAB (Swiss Official Gazette) publication history. "
        "Ideal for procurement due diligence, vendor screening, and contract partner verification "
        "in Swiss public administration contexts."
    ),
)

# ---------------------------------------------------------------------------
# Transport configuration (Railway / Cloud deployment)
# ---------------------------------------------------------------------------

transport = os.environ.get("MCP_TRANSPORT", "stdio")
if transport == "sse":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("PORT", "8000"))

# ---------------------------------------------------------------------------
# Shared HTTP client
# ---------------------------------------------------------------------------

def _make_client() -> httpx.AsyncClient:
    """Create a shared async HTTP client with appropriate headers."""
    return httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "register-mcp/1.0 (Swiss Public Data MCP Portfolio)",
        },
        follow_redirects=True,
    )


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

def _handle_http_error(e: Exception) -> str:
    """Return an actionable, human-readable error message."""
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 400:
            return "Fehler 400: Ungültige Anfrage. Bitte Parameter prüfen (z.B. zu kurzer Suchbegriff)."
        if status == 401:
            return "Fehler 401: Keine Berechtigung. ZefixPublicREST benötigt Zugangsdaten (zefix@bj.admin.ch)."
        if status == 403:
            return "Fehler 403: Zugriff verweigert. Möglicherweise wird ein API-Key benötigt."
        if status == 404:
            return "Fehler 404: Eintrag nicht gefunden. Bitte EHRAID oder UID prüfen."
        if status == 429:
            return "Fehler 429: Rate-Limit überschritten. Bitte kurz warten und erneut versuchen."
        return f"Fehler {status}: API-Anfrage fehlgeschlagen."
    if isinstance(e, httpx.TimeoutException):
        return "Timeout: Die Zefix-API antwortet nicht. Bitte erneut versuchen."
    if isinstance(e, httpx.ConnectError):
        return "Verbindungsfehler: Zefix-API nicht erreichbar. Netzwerk prüfen."
    return f"Unerwarteter Fehler: {type(e).__name__}: {e}"


def _zefix_error_to_str(data: dict) -> str | None:
    """Extract error message from Zefix error response if present."""
    error = data.get("error")
    if not error:
        return None
    code = error.get("code", "UNKNOWN")
    if "NORESULT" in code:
        return "Keine Ergebnisse gefunden. Suchbegriff oder Filter anpassen."
    return f"Zefix-Fehler [{code}]: Keine Daten verfügbar. Filter oder Parameter anpassen."


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _uid_format(raw: str) -> str:
    """Ensure UID is in CHE-xxx.xxx.xxx format."""
    digits = re.sub(r"[^0-9]", "", raw)
    if len(digits) == 9:
        return f"CHE-{digits[:3]}.{digits[3:6]}.{digits[6:]}"
    return raw  # return as-is if not parseable


def _legal_form_name(lf_id: int, legal_forms: list[dict]) -> str:
    """Resolve a legalFormId to a German name."""
    for lf in legal_forms:
        if lf.get("id") == lf_id:
            return lf.get("name", {}).get("de", str(lf_id))
    return str(lf_id)


def _format_company_summary(firm: dict, legal_forms: list[dict] | None = None) -> dict:
    """Normalise a firm dict into a clean summary."""
    lf_id = firm.get("legalFormId")
    lf_name = _legal_form_name(lf_id, legal_forms) if legal_forms and lf_id else str(lf_id)
    return {
        "name": firm.get("name"),
        "uid": firm.get("uidFormatted") or _uid_format(firm.get("uid", "")),
        "chid": firm.get("chidFormatted"),
        "ehraid": firm.get("ehraid"),
        "status": firm.get("status"),
        "rechtsform": lf_name,
        "sitz": firm.get("legalSeat"),
        "shabDate": firm.get("shabDate"),
        "deleteDate": firm.get("deleteDate"),
        "auszugUrl": firm.get("cantonalExcerptWeb"),
    }


def _format_company_detail(firm: dict, legal_forms: list[dict] | None = None) -> dict:
    """Normalise full firm detail dict."""
    summary = _format_company_summary(firm, legal_forms)
    summary["zweck"] = firm.get("purpose")
    # SHAB publications (most recent 3)
    shab_pubs = firm.get("shabPub", [])
    summary["shabPublikationen"] = [
        {
            "datum": p.get("shabDate"),
            "shabId": p.get("shabId"),
            "kanton": p.get("registryOfficeCanton"),
            "mutationsTypen": [m.get("key") for m in p.get("mutationTypes", [])],
        }
        for p in shab_pubs[:5]
    ]
    return summary


# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------

class SearchType(StrEnum):
    STARTS_WITH = "STARTS_WITH"
    CONTAINS = "CONTAINS"
    EXACT = "EXACT"
    ENDS_WITH = "ENDS_WITH"


class ResponseFormat(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"


class CompanySearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    name: str | None = Field(
        default=None,
        description=(
            "Firmenname oder Teilname. Mindestens 3 Zeichen. "
            "Beispiele: 'Migros', 'Schulamt', 'Stadt Zürich'"
        ),
        min_length=2,
        max_length=200,
    )
    canton: str | None = Field(
        default=None,
        description=(
            "Kantonskürzel zur Filterung (2 Buchstaben). "
            "Beispiele: 'ZH', 'BE', 'GE'. Ohne Name-Filter nicht verwendbar."
        ),
        min_length=2,
        max_length=2,
    )
    legal_form_ids: list[int] | None = Field(
        default=None,
        description=(
            "Liste von Rechtsform-IDs (aus zefix_list_legal_forms). "
            "Häufig: 3=AG, 4=GmbH, 7=Stiftung, 8=öffentlich-rechtliche Körperschaft"
        ),
        max_length=10,
    )
    active_only: bool = Field(
        default=True,
        description="Nur aktive (existierende) Einträge anzeigen. Standard: True.",
    )
    search_type: SearchType = Field(
        default=SearchType.CONTAINS,
        description="Suchmodus: CONTAINS (Standard), STARTS_WITH, EXACT, ENDS_WITH",
    )
    max_results: int = Field(
        default=10,
        description="Maximale Anzahl Ergebnisse (1–50). Standard: 10.",
        ge=1,
        le=50,
    )
    offset: int = Field(
        default=0,
        description="Offset für Paginierung. Standard: 0.",
        ge=0,
    )
    language: str = Field(
        default="de",
        description="Sprache für Rechtsform-Namen: 'de', 'fr', 'it', 'en'. Standard: 'de'.",
        pattern=r"^(de|fr|it|en)$",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' (lesbar) oder 'json' (maschinenlesbar)",
    )

    @field_validator("canton")
    @classmethod
    def validate_canton(cls, v: str | None) -> str | None:
        if v and v.upper() not in CANTON_CODES:
            raise ValueError(f"Ungültiges Kantonskürzel '{v}'. Gültig: {', '.join(CANTON_CODES)}")
        return v.upper() if v else v


class CompanyByEhraIdInput(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    ehraid: int = Field(
        ...,
        description=(
            "Interne Zefix-ID der Firma (EHRAID). "
            "Wird aus zefix_search_companies oder zefix_get_company_by_uid zurückgegeben."
        ),
        ge=1,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


class CompanyByUidInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    uid: str = Field(
        ...,
        description=(
            "Unternehmens-Identifikationsnummer (UID/MwSt-Nummer). "
            "Format: CHE-xxx.xxx.xxx oder CHExxxxxxxxxxx (9 Ziffern). "
            "Beispiel: 'CHE-116.281.510' oder 'CHE116281510'"
        ),
        min_length=9,
        max_length=20,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


class LegalFormsInput(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    language: str = Field(
        default="de",
        description="Sprache: 'de', 'fr', 'it', 'en'. Standard: 'de'.",
        pattern=r"^(de|fr|it|en)$",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


class VerifyCompanyInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    name: str = Field(
        ...,
        description=(
            "Exakter oder annähernder Firmenname zur Verifikation. "
            "Beispiel: 'Lehrmittelverlag Zürich AG'"
        ),
        min_length=3,
        max_length=200,
    )
    canton: str | None = Field(
        default=None,
        description="Kantonskürzel zur Eingrenzung (z.B. 'ZH')",
        min_length=2,
        max_length=2,
    )

    @field_validator("canton")
    @classmethod
    def validate_canton(cls, v: str | None) -> str | None:
        if v and v.upper() not in CANTON_CODES:
            raise ValueError(f"Ungültiges Kantonskürzel '{v}'.")
        return v.upper() if v else v


class MunicipalitiesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    canton: str | None = Field(
        default=None,
        description="Kantonskürzel zur Filterung (z.B. 'ZH'). Ohne Filter: alle Gemeinden.",
        min_length=2,
        max_length=2,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )

    @field_validator("canton")
    @classmethod
    def validate_canton(cls, v: str | None) -> str | None:
        if v and v.upper() not in CANTON_CODES:
            raise ValueError(f"Ungültiges Kantonskürzel '{v}'.")
        return v.upper() if v else v


# ---------------------------------------------------------------------------
# Shared data fetchers
# ---------------------------------------------------------------------------

async def _fetch_legal_forms() -> list[dict]:
    """Fetch and return all legal forms from Zefix."""
    async with _make_client() as client:
        r = await client.get(f"{ZEFIX_BASE}/legalForm")
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Tool: Search Companies
# ---------------------------------------------------------------------------

@mcp.tool(
    name="zefix_search_companies",
    annotations={
        "title": "Firmen im Handelsregister suchen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def zefix_search_companies(params: CompanySearchInput) -> str:
    """Sucht Unternehmen im Schweizer Handelsregister (Zefix) nach Name, Kanton und Rechtsform.

    Gibt eine Liste von Firmen zurück mit Name, UID, Status, Rechtsform, Sitz und SHAB-Datum.
    Ideal für Lieferantenprüfungen, Vertragspartner-Screenings und Beschaffungs-Due-Diligence.

    Args:
        params (CompanySearchInput): Suchparameter:
            - name (Optional[str]): Firmenname (mind. 2 Zeichen)
            - canton (Optional[str]): Kanton (z.B. 'ZH')
            - legal_form_ids (Optional[list[int]]): Rechtsform-IDs
            - active_only (bool): Nur aktive Einträge (Standard: True)
            - search_type (str): CONTAINS, STARTS_WITH, EXACT, ENDS_WITH
            - max_results (int): 1–50 (Standard: 10)
            - offset (int): Paginierung (Standard: 0)
            - language (str): 'de', 'fr', 'it', 'en'
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Gefundene Firmen mit Name, UID, Status, Rechtsform, Sitz, SHAB-Datum, Auszug-URL.
             Enthält Paginierungsinfo (hasMoreResults, offset, total).
    """
    if not params.name and not params.canton:
        return "Fehler: Mindestens 'name' oder 'canton' muss angegeben werden."

    body: dict[str, Any] = {
        "languageKey": params.language,
        "maxEntries": params.max_results,
        "offset": params.offset,
        "activeOnly": params.active_only,
        "searchType": params.search_type.value,
    }
    if params.name:
        body["name"] = params.name
    if params.canton:
        body["canton"] = params.canton
    if params.legal_form_ids:
        body["legalFormIds"] = params.legal_form_ids

    try:
        legal_forms = await _fetch_legal_forms()
        async with _make_client() as client:
            r = await client.post(f"{ZEFIX_BASE}/firm/search.json", json=body)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return _handle_http_error(e)

    err = _zefix_error_to_str(data) if isinstance(data, dict) else None
    if err:
        return err

    firms = data.get("list", [])
    has_more = data.get("hasMoreResults", False)
    total = data.get("maxOffset", "?")

    summaries = [_format_company_summary(f, legal_forms) for f in firms]

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({
            "results": summaries,
            "count": len(summaries),
            "offset": params.offset,
            "hasMoreResults": has_more,
            "totalApproximate": total,
        }, ensure_ascii=False, indent=2)

    # Markdown output
    lines = [
        f"## Handelsregister-Suche: «{params.name or ''}»",
        f"Gefunden: **{len(summaries)} Einträge**"
        + (f" (von ca. {total})" if total else "")
        + (" | Weitere Ergebnisse verfügbar → offset erhöhen" if has_more else ""),
        "",
    ]
    for s in summaries:
        status_icon = "✅" if s["status"] == "EXISTIEREND" else "❌"
        lines += [
            f"### {status_icon} {s['name']}",
            f"- **UID:** {s['uid']} | **Rechtsform:** {s['rechtsform']}",
            f"- **Sitz:** {s['sitz']} | **Status:** {s['status']}",
            f"- **SHAB-Datum:** {s['shabDate']} | **EHRAID:** {s['ehraid']}",
        ]
        if s.get("auszugUrl"):
            lines.append(f"- **Auszug:** {s['auszugUrl']}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: Get Company by EHRAID
# ---------------------------------------------------------------------------

@mcp.tool(
    name="zefix_get_company",
    annotations={
        "title": "Firmenprofil nach EHRAID abrufen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def zefix_get_company(params: CompanyByEhraIdInput) -> str:
    """Ruft vollständige Firmendetails aus dem Handelsregister ab (nach interner EHRAID).

    Liefert: Name, UID, Rechtsform, Sitz, Status, Zweck (Gesellschaftszweck),
    SHAB-Publikationshistorie (letzte 5 Einträge) und Link zum kantonalen Auszug.

    Die EHRAID wird aus zefix_search_companies oder zefix_get_company_by_uid zurückgegeben.

    Args:
        params (CompanyByEhraIdInput):
            - ehraid (int): Interne Zefix-Firmen-ID
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Vollständiges Firmenprofil inkl. Zweck und SHAB-Publikationen.
    """
    try:
        legal_forms = await _fetch_legal_forms()
        async with _make_client() as client:
            r = await client.get(f"{ZEFIX_BASE}/firm/{params.ehraid}.json")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return _handle_http_error(e)

    err = _zefix_error_to_str(data) if isinstance(data, dict) else None
    if err:
        return err

    detail = _format_company_detail(data, legal_forms)

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(detail, ensure_ascii=False, indent=2)

    status_icon = "✅" if detail["status"] == "EXISTIEREND" else "❌"
    lines = [
        f"## {status_icon} {detail['name']}",
        "",
        "| Feld | Wert |",
        "|------|------|",
        f"| **UID** | {detail['uid']} |",
        f"| **CHID** | {detail['chid']} |",
        f"| **EHRAID** | {detail['ehraid']} |",
        f"| **Rechtsform** | {detail['rechtsform']} |",
        f"| **Sitz** | {detail['sitz']} |",
        f"| **Status** | {detail['status']} |",
        f"| **Letzte SHAB-Publikation** | {detail['shabDate']} |",
    ]
    if detail.get("deleteDate"):
        lines.append(f"| **Gelöscht am** | {detail['deleteDate']} |")
    if detail.get("auszugUrl"):
        lines.append(f"| **Kantonaler Auszug** | [{detail['auszugUrl']}]({detail['auszugUrl']}) |")
    lines.append("")

    if detail.get("zweck"):
        lines += ["### Gesellschaftszweck", detail["zweck"], ""]

    pubs = detail.get("shabPublikationen", [])
    if pubs:
        lines.append("### SHAB-Publikationen (letzte Einträge)")
        for p in pubs:
            typen = ", ".join(p.get("mutationsTypen", [])) or "—"
            lines.append(f"- **{p['datum']}** | {p['kanton']} | ID: {p['shabId']} | {typen}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: Get Company by UID
# ---------------------------------------------------------------------------

@mcp.tool(
    name="zefix_get_company_by_uid",
    annotations={
        "title": "Firma nach UID/MwSt-Nummer suchen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def zefix_get_company_by_uid(params: CompanyByUidInput) -> str:
    """Findet eine Firma im Handelsregister anhand ihrer UID (Unternehmensidentifikationsnummer).

    Die UID ist die eindeutige Schweizer Unternehmens-ID (CHE-xxx.xxx.xxx),
    identisch mit der MwSt-Nummer. Gibt vollständige Firmendetails zurück.

    Args:
        params (CompanyByUidInput):
            - uid (str): UID im Format CHE-xxx.xxx.xxx oder CHExxxxxxxxxxx
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Vollständiges Firmenprofil (Name, Rechtsform, Status, Zweck, SHAB-Publikationen).
             Enthält EHRAID für Folgeabfragen mit zefix_get_company.
    """
    # Normalize UID to search format (strip CHE prefix and dots)
    uid_clean = re.sub(r"[^0-9]", "", params.uid)
    if len(uid_clean) != 9:
        return (
            f"Fehler: Ungültige UID '{params.uid}'. "
            "Erwartet: 9 Ziffern (z.B. CHE-116.281.510 oder CHE116281510)."
        )

    uid_formatted = f"CHE-{uid_clean[:3]}.{uid_clean[3:6]}.{uid_clean[6:]}"

    # Search by exact UID
    body = {
        "languageKey": "de",
        "maxEntries": 5,
        "name": uid_formatted,
        "searchType": "CONTAINS",
        "activeOnly": False,  # include deleted for full transparency
    }

    try:
        legal_forms = await _fetch_legal_forms()
        async with _make_client() as client:
            r = await client.post(f"{ZEFIX_BASE}/firm/search.json", json=body)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return _handle_http_error(e)

    err = _zefix_error_to_str(data) if isinstance(data, dict) else None
    if err:
        return f"Keine Firma mit UID {uid_formatted} im Handelsregister gefunden.\n\n{err}"

    firms = data.get("list", [])
    # Filter to exact UID match
    exact = [f for f in firms if re.sub(r"[^0-9]", "", f.get("uid", "")) == uid_clean]
    if not exact:
        # Try broader: return first result
        exact = firms[:1]

    if not exact:
        return f"Keine Firma mit UID {uid_formatted} im Handelsregister gefunden."

    # Fetch full detail for first match
    ehraid = exact[0]["ehraid"]
    try:
        async with _make_client() as client:
            r = await client.get(f"{ZEFIX_BASE}/firm/{ehraid}.json")
            r.raise_for_status()
            detail_data = r.json()
    except Exception:
        # Return summary if detail fails
        detail_data = exact[0]

    detail = _format_company_detail(detail_data, legal_forms)

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(detail, ensure_ascii=False, indent=2)

    status_icon = "✅" if detail["status"] == "EXISTIEREND" else "❌"
    lines = [
        f"## {status_icon} {detail['name']}",
        f"**UID:** {uid_formatted}",
        "",
        "| Feld | Wert |",
        "|------|------|",
        f"| **CHID** | {detail.get('chid', '—')} |",
        f"| **EHRAID** | {detail['ehraid']} |",
        f"| **Rechtsform** | {detail['rechtsform']} |",
        f"| **Sitz** | {detail['sitz']} |",
        f"| **Status** | {detail['status']} |",
        f"| **Letzte SHAB-Publikation** | {detail['shabDate']} |",
    ]
    if detail.get("deleteDate"):
        lines.append(f"| **Gelöscht am** | {detail['deleteDate']} |")
    if detail.get("auszugUrl"):
        lines.append(f"| **Kantonaler Auszug** | [{detail['auszugUrl']}]({detail['auszugUrl']}) |")
    lines.append("")

    if detail.get("zweck"):
        lines += ["### Gesellschaftszweck", detail["zweck"], ""]

    pubs = detail.get("shabPublikationen", [])
    if pubs:
        lines.append("### SHAB-Publikationen")
        for p in pubs:
            typen = ", ".join(p.get("mutationsTypen", [])) or "—"
            lines.append(f"- **{p['datum']}** | {p['kanton']} | {typen}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: Verify Company (quick check)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="zefix_verify_company",
    annotations={
        "title": "Firma schnell verifizieren (aktiv/gelöscht?)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def zefix_verify_company(params: VerifyCompanyInput) -> str:
    """Schnell-Verifikation: Ist ein Unternehmen im Handelsregister eingetragen und aktiv?

    Gibt eine klare Ja/Nein-Antwort plus Basisdetails zurück. Ideal als erster Check
    vor Vertragsabschlüssen, Beschaffungen oder Subventionsvergaben.

    Stellt fest:
    - Ist die Firma im Handelsregister eingetragen?
    - Ist sie aktiv (EXISTIEREND) oder gelöscht?
    - Welche Rechtsform hat sie?
    - Wo ist sie domiziliert?
    - Gibt es mehrere ähnliche Firmen (Verwechslungsgefahr)?

    Args:
        params (VerifyCompanyInput):
            - name (str): Firmenname (mind. 3 Zeichen)
            - canton (Optional[str]): Kantonskürzel zur Eingrenzung

    Returns:
        str: Verifizierungsergebnis mit Status, Rechtsform, Sitz und Warnungen.
    """
    body: dict[str, Any] = {
        "languageKey": "de",
        "maxEntries": 10,
        "name": params.name,
        "searchType": "CONTAINS",
        "activeOnly": False,  # show all to detect dissolved firms
    }
    if params.canton:
        body["canton"] = params.canton

    try:
        legal_forms = await _fetch_legal_forms()
        async with _make_client() as client:
            r = await client.post(f"{ZEFIX_BASE}/firm/search.json", json=body)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return _handle_http_error(e)

    err = _zefix_error_to_str(data) if isinstance(data, dict) else None
    if err:
        return (
            f"## ❓ Verifikation: «{params.name}»\n\n"
            f"**Ergebnis:** Nicht im Handelsregister gefunden.\n\n"
            "Die Firma ist entweder nicht im Handelsregister eingetragen "
            "(z.B. Einzelunternehmen unter Schwellenwert, Behörde, Verein ohne Eintrag) "
            "oder der Firmenname ist abweichend. Suchbegriff prüfen."
        )

    firms = data.get("list", [])
    if not firms:
        return (
            f"## ❓ Verifikation: «{params.name}»\n\n"
            "**Ergebnis:** Nicht im Handelsregister gefunden."
        )

    summaries = [_format_company_summary(f, legal_forms) for f in firms]
    active = [s for s in summaries if s["status"] == "EXISTIEREND"]
    inactive = [s for s in summaries if s["status"] != "EXISTIEREND"]

    lines = [f"## 🔍 Verifikation: «{params.name}»", ""]

    if active:
        lines += [
            f"**✅ Aktive Einträge: {len(active)}**",
            "",
        ]
        for s in active[:3]:
            lines += [
                f"### ✅ {s['name']}",
                f"- **UID:** {s['uid']} | **Rechtsform:** {s['rechtsform']}",
                f"- **Sitz:** {s['sitz']} | **SHAB:** {s['shabDate']}",
            ]
            if s.get("auszugUrl"):
                lines.append(f"- **Auszug:** {s['auszugUrl']}")
            lines.append("")
    else:
        lines += ["**⚠️ Keine aktiven Einträge gefunden.**", ""]

    if inactive:
        lines += [
            f"**❌ Gelöschte/inaktive Einträge: {len(inactive)}**",
            "",
        ]
        for s in inactive[:2]:
            lines += [
                f"- ❌ {s['name']} | {s['rechtsform']} | {s['sitz']} "
                f"| gelöscht: {s.get('deleteDate', '?')}",
            ]
        lines.append("")

    if len(summaries) > 1:
        lines += [
            "---",
            f"⚠️ **Verwechslungsgefahr:** {len(summaries)} ähnliche Einträge gefunden. "
            "Bitte UID oder EHRAID für eindeutige Identifikation verwenden.",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: List Legal Forms
# ---------------------------------------------------------------------------

@mcp.tool(
    name="zefix_list_legal_forms",
    annotations={
        "title": "Schweizer Rechtsformen auflisten",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def zefix_list_legal_forms(params: LegalFormsInput) -> str:
    """Listet alle im Schweizer Handelsregister verwendeten Rechtsformen auf.

    Nützlich zur Ermittlung der legalFormId-Werte für die Filterung in zefix_search_companies.
    Häufige IDs: 1=Einzelunternehmen, 2=KlG, 3=AG, 4=GmbH, 5=KmG, 6=Genossenschaft,
    7=Stiftung, 8=öffentlich-rechtliche Körperschaft, 9=Verein.

    Args:
        params (LegalFormsInput):
            - language (str): Sprache ('de', 'fr', 'it', 'en'). Standard: 'de'
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Alle Rechtsformen mit ID, Name (in gewählter Sprache) und Kurzform.
    """
    try:
        legal_forms = await _fetch_legal_forms()
    except Exception as e:
        return _handle_http_error(e)

    lang = params.language

    if params.response_format == ResponseFormat.JSON:
        result = [
            {
                "id": lf["id"],
                "name": lf.get("name", {}).get(lang, lf.get("name", {}).get("de", "")),
                "kurzform": lf.get("kurzform", {}).get(lang, ""),
                "sort": lf.get("sort"),
            }
            for lf in sorted(legal_forms, key=lambda x: x.get("sort", 9999))
        ]
        return json.dumps(result, ensure_ascii=False, indent=2)

    lines = [
        "## Schweizer Rechtsformen (Handelsregister)",
        "",
        "| ID | Kurzform | Name | Filter-Tipp |",
        "|----|----------|------|-------------|",
    ]
    for lf in sorted(legal_forms, key=lambda x: x.get("sort", 9999)):
        lf_id = lf["id"]
        name = lf.get("name", {}).get(lang, "")
        kurzform = lf.get("kurzform", {}).get(lang, "")
        lines.append(f"| {lf_id} | {kurzform} | {name} | `legal_form_ids=[{lf_id}]` |")

    lines += [
        "",
        "_Verwende die ID in `zefix_search_companies` mit dem Parameter `legal_form_ids`._",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: List Municipalities
# ---------------------------------------------------------------------------

@mcp.tool(
    name="zefix_list_municipalities",
    annotations={
        "title": "Schweizer Gemeinden und BFS-IDs auflisten",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def zefix_list_municipalities(params: MunicipalitiesInput) -> str:
    """Listet Schweizer Gemeinden mit BFS-ID und Handelsregisterkreis auf.

    Die interne legalSeatId aus Zefix kann über diese Liste auf Gemeindenamen
    und BFS-IDs gemappt werden. Nützlich für geografische Analysen und Berichte.

    Args:
        params (MunicipalitiesInput):
            - canton (Optional[str]): Kanton-Filter (z.B. 'ZH'). Ohne Filter: alle ~2'300 Gemeinden.
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Gemeindeliste mit Name, Kanton, BFS-ID und Handelsregisterkreis-ID.
    """
    try:
        async with _make_client() as client:
            r = await client.get(f"{ZEFIX_BASE}/community")
            r.raise_for_status()
            communities = r.json()
    except Exception as e:
        return _handle_http_error(e)

    if params.canton:
        communities = [c for c in communities if c.get("canton") == params.canton]

    if not communities:
        return f"Keine Gemeinden für Kanton '{params.canton}' gefunden."

    if params.response_format == ResponseFormat.JSON:
        result = [
            {
                "id": c["id"],
                "name": c["name"],
                "canton": c["canton"],
                "bfsId": c.get("bfsId"),
                "registryOfficeId": c.get("registryOfficeId"),
            }
            for c in sorted(communities, key=lambda x: x.get("name", ""))
        ]
        return json.dumps(result, ensure_ascii=False, indent=2)

    canton_label = params.canton or "alle Kantone"
    lines = [
        f"## Gemeinden: {canton_label} ({len(communities)} Einträge)",
        "",
        "| ID | Name | Kanton | BFS-ID | HR-Kreis |",
        "|----|------|--------|--------|----------|",
    ]
    for c in sorted(communities, key=lambda x: x.get("name", ""))[:100]:
        lines.append(
            f"| {c['id']} | {c['name']} | {c['canton']} "
            f"| {c.get('bfsId', '—')} | {c.get('registryOfficeId', '—')} |"
        )

    if len(communities) > 100:
        lines += [
            "",
            f"_Zeige 100 von {len(communities)} Gemeinden. "
            "Kanton-Filter verwenden für vollständige Liste._",
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport=transport)
