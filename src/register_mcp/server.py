"""
register-mcp: MCP server for the Swiss commercial register, with a UID join to
the official gazettes portal.

Provides access to two data sources, joined on the company UID:
  - Zefix (Handelsregister): Swiss Federal Commercial Register via ZefixREST API
    (tools prefixed `zefix_`)
  - Amtsblattportal: SHAB + cantonal official gazettes via amtsblattportal.ch/api/v1
    (tools prefixed `gazette_`)

Both sources are open (no authentication). Zefix tells you whether a company
exists; the gazette tells you what has been published about it.

SCOPE (deliberate — see README "Data Protection & Scope"): the gazette surface
here is intentionally narrow and **company-centric**. The only gazette entry
points are keyed on a company UID (`gazette_company_publications`) or an opaque
publication id (`gazette_get_publication`), plus a health probe
(`gazette_source_status`). There is NO free-text / person-name search entry and
NO broad cantonal-gazette browsing in this server — that would turn the tool
into a profiling instrument over the person-data-heavy gazette rubrics
(bankruptcies, debt-collection, calls to creditors, inheritance). Broad
platform coverage of the Amtsblattportal (procurement, cantonal notices,
full-text search) is proposed as a *separate* server, `amtsblatt-mcp`
(see docs/amtsblatt-mcp-proposal.md), so that this register server stays
coherent and data-protection-safe by construction.

See the CHANGELOG "Known findings" section for the verified amtsblattportal
quirks (Silent Ignore, Silent Empty, two-step XML fetch).

Use cases:
  - Lieferantenprüfung (vendor verification before procurement)
  - Vertragspartner-Due-Diligence (contract partner due diligence)
  - Schulvertragsprüfung (school contract verification)
  - HR-Dienstleister-Screening (HR service provider screening)
"""

from __future__ import annotations

import asyncio
import difflib
import json
import logging
import os
import random
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from time import monotonic
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import __version__
from ._log import configure_logging, log_event, logged_tool

configure_logging()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZEFIX_BASE = "https://www.zefix.admin.ch/ZefixREST/api/v1"
ZEFIX_PUBLIC_BASE = "https://www.zefix.admin.ch/ZefixPublicREST/api/v1"
# Amtsblattportal — SHAB (Swiss Official Gazette of Commerce) *and* cantonal
# gazettes. Live-verified 2026-07-18. No authentication. See the "Known
# limitations" table in the README and the CHANGELOG "Known findings" section.
GAZETTE_BASE = "https://amtsblattportal.ch/api/v1"
REQUEST_TIMEOUT = 15.0

# Egress allow-list — every outbound HTTP request from `_make_client` is
# checked against this set. Acts as a second-layer defence: even if a
# dependency tries to follow a redirect to an unexpected host or a future
# tool adds an unintended URL, the request is rejected before it leaves
# the process. Override via MCP_ALLOWED_HOSTS (comma-separated).
#
# SECURITY: `amtsblattportal.ch` was added to the DEFAULT when the gazette
# tools shipped (v0.3.0). Deployments that pin MCP_ALLOWED_HOSTS override the
# default entirely and MUST add the new host, or every gazette_* call raises
# EgressDenied. Documented as an upgrade note in the README.
_DEFAULT_ALLOWED_HOSTS = frozenset({"www.zefix.admin.ch", "amtsblattportal.ch"})
ALLOWED_HOSTS: frozenset[str] = frozenset(
    h.strip().lower()
    for h in os.environ.get("MCP_ALLOWED_HOSTS", ",".join(sorted(_DEFAULT_ALLOWED_HOSTS))).split(
        ","
    )
    if h.strip()
)


class EgressDenied(httpx.RequestError):
    """Raised when an outbound request targets a host outside ALLOWED_HOSTS."""


# ---------------------------------------------------------------------------
# Attribution (per data source) — every response is labelled so that, in a
# mixed answer that joins Zefix and gazette data, the provenance of each
# statement is never ambiguous. The gazette disclaimer is not optional: the
# operator excludes all liability for the content of individual publications.
# ---------------------------------------------------------------------------

ATTRIBUTION_ZEFIX = "Data: Zefix / Federal Office of Justice — opendata.swiss."
ATTRIBUTION_GAZETTE = (
    "Data: amtsblattportal.ch (SHAB and cantonal gazettes) — "
    "SECO / Swiss Confederation. No liability for content "
    "of individual publications."
)

# ---------------------------------------------------------------------------
# Gazette (amtsblattportal) constants & guardrails
# ---------------------------------------------------------------------------

# Total published corpus, aufgezeichnet am 2026-08-07 von der Live-Quelle
# (siehe tests/fixtures/gazette_corpus_total.json und PROVENANCE.md).
GAZETTE_CORPUS_SIZE = 2_809_194
# Anteil des Korpus, ab dem ein GEFILTERTES Ergebnis als «Filter wurde
# ignoriert» gilt (Quirk 1).
#
# WARUM ANTEILIG UND NICHT MEHR ABSOLUT. Hier stand `2_000_000`, begruendet mit
# «weit ueber jedem plausiblen Einzelfilter-Ergebnis». Das war falsch, und zwar
# fuer die wichtigste Rubrik dieses Servers: Gemessen am 2026-08-07 liefert
# `rubrics=HR` (Handelsregister) **2_279_587** Treffer — 81 % des Korpus und
# damit ueber der Schwelle. Eine voellig korrekte HR-Suche brach also mit
# «Filter wurde vom Upstream ignoriert» ab, obwohl der Filter gewirkt hatte.
# Zum Vergleich: `SB` 22_872, `LS` 70_330.
#
# Aufgefallen ist das erst, als die Fixtures aufgezeichnet statt ausgedacht
# wurden. Die alte Fixture setzte den Korpus auf 2_790_323 und liess jede
# gefilterte Suche unter 2 Mio. bleiben — Produktivcode und Mock trugen
# dieselbe Annahme, also konnte kein Test sie widerlegen.
#
# Der Pruefgegenstand ist nicht «viele Treffer», sondern «der GANZE Bestand».
# Deshalb jetzt relativ zum Korpus. Waechst der Bestand und bleibt die Konstante
# stehen, wird die Pruefung unschaerfer statt falscher — sie verfehlt dann
# hoechstens einen echten Fall, statt einen gesunden abzuweisen.
GAZETTE_IGNORED_FILTER_RATIO = 0.95
GAZETTE_IGNORED_FILTER_THRESHOLD = int(GAZETTE_CORPUS_SIZE * GAZETTE_IGNORED_FILTER_RATIO)

# Silent Ignore: unbekannte Parameter -> voller Korpus statt 400. Vgl. CHANGELOG.
# Query parameters are built EXCLUSIVELY from this allow-list. No user input is
# ever passed through into the query string dynamically — a typo like `uid=`
# instead of `uids=` would otherwise be dropped silently and return all
# 2.79M records with HTTP 200 (Quirk 1).
# NOTE: `keyword` and `cantons` are deliberately NOT allow-listed. This server
# only performs UID-scoped gazette lookups; a free-text `keyword` or broad
# `cantons` filter is exactly the person-profiling entry point that Option C
# moved out to the separate `amtsblatt-mcp`. Keeping them off the allow-list is
# a fail-closed guarantee: even a future code change cannot smuggle them in.
ALLOWED_GAZETTE_PARAMS: frozenset[str] = frozenset(
    {
        "publicationStates",
        "uids",
        "rubrics",
        "subRubrics",
        "publicationDate.start",
        "publicationDate.end",
        "pageRequest.size",
        "pageRequest.page",
    }
)

# Hard page-size cap for every gazette search tool (pageRequest.size).
GAZETTE_MAX_LIMIT = 100

# Guardrail regexes — validated BEFORE any call is made.
UID_RE = re.compile(r"^CHE-\d{3}\.\d{3}\.\d{3}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Transient upstream errors that warrant a retry.
_TRANSIENT_STATUS = frozenset({502, 503, 504})

# 429 belongs here too. It was excluded while `parse_retry_after` already read
# the `Retry-After` a 429 carries — so the value was parsed and then never
# used, and a rate-limited call failed outright instead of coming back when
# the gazette said to. A 429 is the one status that names its own retry time.
_RETRYABLE_STATUS = _TRANSIENT_STATUS | {429}
GAZETTE_MAX_RETRIES = int(os.environ.get("GAZETTE_MAX_RETRIES", "3"))
GAZETTE_RETRY_BACKOFF = float(os.environ.get("GAZETTE_RETRY_BACKOFF", "0.5"))

# --- Retry policy (ARCH-014) -------------------------------------------------
# `_TRANSIENT_STATUS` settles *what* is retried. These settle *how fast* and
# *how long*.

# Ceiling on a single wait — against a ladder that grows without bound and
# against a `Retry-After` the gazette may send but that we need not sit through.
GAZETTE_MAX_DELAY_S = 20.0

# Jitter. Without it every client that hit the same outage retries in lockstep,
# and the load returns as a wave exactly when the gazette recovers — the retry
# storm extends the outage it was meant to bridge.
GAZETTE_JITTER_SPREAD = 0.5  # linear delays land in [0.5x, 1.5x]

# On a `Retry-After` the spread is one-sided: the gazette said when to come
# back, so later is polite and earlier ignores the value we just read.
GAZETTE_RETRY_AFTER_JITTER = 0.25  # lands in [1.0x, 1.25x]

# Statuses carrying a meaningful `Retry-After` (RFC 9110 §10.2.3). Both are in
# `_RETRYABLE_STATUS`, so a hinted delay now actually reaches a wait — which is
# what a source that answers "not now, come back at T" is entitled to expect.
GAZETTE_RETRY_AFTER_STATUSES = frozenset({429, 503})

# Ceiling on the *whole* call — every attempt, every wait, together.
#
# An attempt count is not a bound: three attempts at a 15s timeout plus backoff
# are close to a minute, and `GAZETTE_MAX_RETRIES` never says so. The limit that
# matters is not ours either: the caller has its own timeout, and past it nobody
# receives the answer — the work continues, the load lands on the gazette, and
# the result goes nowhere.
#
# Anchored on the Python MCP SDK's `MCP_DEFAULT_TIMEOUT = 30.0`. 25s leaves
# headroom for MCP framing and the tool layer.
GAZETTE_TOTAL_BUDGET_S = float(os.environ.get("GAZETTE_TOTAL_BUDGET", "25.0"))

# Backoff waits go through this alias so a test can skip or fake them by
# patching *this module attribute*. Patching `asyncio.sleep` itself reaches
# every module in the process, and a test that uses `asyncio.sleep(0)` to yield
# to the event loop then stops testing anything while still passing.
_sleep = asyncio.sleep


def parse_retry_after(resp: httpx.Response | None) -> float | None:
    """Seconds to wait per the response's ``Retry-After``, or None.

    RFC 9110 §10.2.3 allows delta-seconds and an HTTP-date; both occur, both are
    read. Anything unparseable yields None and the caller falls back to its own
    curve — a malformed header must not become a crash on the error path.
    """
    if resp is None or resp.status_code not in GAZETTE_RETRY_AFTER_STATUSES:
        return None
    raw = (resp.headers.get("Retry-After") or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return float(raw)
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:  # RFC 9110 dates are GMT; a naive one means UTC
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def gazette_retry_delay(attempt: int, resp: httpx.Response | None) -> float:
    """Seconds to wait after the failed ``attempt`` (1-based).

    The gazette's own answer beats our guess: a ``Retry-After`` wins over the
    linear curve, which is guessing at the same question.
    """
    hinted = parse_retry_after(resp)
    if hinted is not None:
        jittered = hinted * (1.0 + random.random() * GAZETTE_RETRY_AFTER_JITTER)
    else:
        jittered = (GAZETTE_RETRY_BACKOFF * attempt) * (
            1.0 - GAZETTE_JITTER_SPREAD + random.random() * 2 * GAZETTE_JITTER_SPREAD
        )
    # Cap *after* jitter — the other order made the cap not a bound at all.
    return min(jittered, GAZETTE_MAX_DELAY_S)


class GazetteFilterIgnored(RuntimeError):
    """Raised when the upstream silently ignored a filter (Quirk 1)."""


class GazetteInvalidCode(ValueError):
    """Raised when a rubric/subRubric code is not in the taxonomy (Quirk 2)."""


CANTON_CODES = [
    "AG",
    "AI",
    "AR",
    "BE",
    "BL",
    "BS",
    "FR",
    "GE",
    "GL",
    "GR",
    "JU",
    "LU",
    "NE",
    "NW",
    "OW",
    "SG",
    "SH",
    "SO",
    "SZ",
    "TG",
    "TI",
    "UR",
    "VD",
    "VS",
    "ZG",
    "ZH",
]

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = MCPServer(
    "register_mcp",
    instructions=(
        "Provides read-only access to two Swiss federal data sources, joined on the company "
        "UID: (1) the Federal Commercial Register (Zefix/Handelsregister, tools prefixed "
        "`zefix_`) to verify companies, check registration status and look up UID numbers; "
        "and (2) the official gazettes portal (amtsblattportal.ch — SHAB and cantonal "
        "gazettes, tools prefixed `gazette_`) to retrieve what has been published ABOUT A "
        "SPECIFIC COMPANY. Start from `zefix_get_company_by_uid` / `zefix_verify_company` "
        "to establish the UID, then `gazette_company_publications(uid=...)` for the join and "
        "`gazette_get_publication(id=...)` to read one publication's full text. "
        "The gazette entry points are UID- or id-scoped only — there is no free-text or "
        "person-name gazette search here (that would be a profiling tool over the "
        "person-data-heavy rubrics); broad Amtsblatt platform search lives in the separate "
        "`amtsblatt-mcp`. Ideal for vendor screening and contract-partner verification in "
        "Swiss public administration contexts."
    ),
)

# ---------------------------------------------------------------------------
# Transport configuration (Railway / Cloud deployment)
# ---------------------------------------------------------------------------

transport = os.environ.get("MCP_TRANSPORT", "stdio")
# mcp 2.x: MCPServer.settings no longer carries host/port, so the bind address
# lives here and is handed to uvicorn directly in main().
BIND_HOST = "0.0.0.0"  # noqa: S104 — SSE deployment target is a container
BIND_PORT = int(os.environ.get("PORT", "8000"))

# ---------------------------------------------------------------------------
# Shared HTTP client
# ---------------------------------------------------------------------------


async def _enforce_egress_allowlist(request: httpx.Request) -> None:
    """httpx event hook: reject requests to hosts outside ALLOWED_HOSTS.

    Runs before send AND on each redirect (httpx fires `request` events for
    each hop when `follow_redirects=True`), so an unexpected 3xx Location
    cannot exfiltrate the request.
    """
    host = (request.url.host or "").lower()
    if host not in ALLOWED_HOSTS:
        log_event(
            logging.ERROR,
            "egress_denied",
            host=host,
            url=str(request.url),
            allowed=sorted(ALLOWED_HOSTS),
        )
        raise EgressDenied(
            f"Egress to host {host!r} is not in ALLOWED_HOSTS",
            request=request,
        )


def _make_client() -> httpx.AsyncClient:
    """Create a shared async HTTP client with appropriate headers and egress guard."""
    return httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"register-mcp/{__version__} (Swiss Public Data MCP Portfolio)",
        },
        follow_redirects=True,
        event_hooks={"request": [_enforce_egress_allowlist]},
    )


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


def _handle_http_error(e: Exception) -> str:
    """Return an actionable, human-readable error message."""
    if isinstance(e, GazetteFilterIgnored):
        return str(e)
    if isinstance(e, GazetteInvalidCode):
        return str(e)
    if isinstance(e, EgressDenied):
        return f"Egress verweigert: {e}. Ziel-Host nicht in ALLOWED_HOSTS."
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


async def _zefix_post_search(client: httpx.AsyncClient, body: dict) -> dict:
    """POST an Zefix `firm/search.json` — inklusive der leeren Treffermenge.

    Zefix beantwortet eine Suche ohne Treffer mit **HTTP 404** und dem
    NORESULT-Umschlag im Rumpf, nicht mit 200. Das ist vertretbar und war hier
    trotzdem falsch behandelt: `raise_for_status()` warf, und die generische
    404-Meldung lautet «Eintrag nicht gefunden. Bitte EHRAID oder UID prüfen» —
    auf eine Namenssuche hin, bei der weder EHRAID noch UID im Spiel waren.
    Der freundliche Zweig in `_zefix_error_to_str` war damit unerreichbar.

    Aufgefallen ist das erst beim Aufzeichnen: Die erfundene Fixture legte den
    NORESULT-Umschlag in eine 200er-Antwort, und der Test dazu bestand.
    """
    r = await client.post(f"{ZEFIX_BASE}/firm/search.json", json=body)
    if r.status_code == 404:
        try:
            body_json = r.json()
        except ValueError:
            body_json = {}
        if isinstance(body_json, dict) and body_json.get("error"):
            return body_json
    r.raise_for_status()
    return r.json()


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
    legal_seat_id: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Die `legalSeatId` einer Firma (aus zefix_search_companies oder "
            "zefix_get_company). Löst genau eine Gemeinde auf. Bevorzugt "
            "gegenüber dem Nachschlagen in der Tabelle: `legalSeatId` ist eine "
            "BFS-Nummer und trifft die Spalte «BFS-ID», nicht die interne «ID»."
        ),
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

LEGAL_FORMS_TTL_SECONDS = float(os.environ.get("LEGAL_FORMS_TTL", "86400"))
_legal_forms_cache: tuple[float, list[dict]] | None = None


async def _fetch_legal_forms(ttl: float | None = None) -> list[dict]:
    """Fetch all legal forms from Zefix with a TTL cache (default 24h).

    The list changes at most a few times per year; caching avoids a second
    upstream call on every search/detail tool invocation.
    """
    global _legal_forms_cache
    effective_ttl = LEGAL_FORMS_TTL_SECONDS if ttl is None else ttl
    now = monotonic()
    if _legal_forms_cache and now - _legal_forms_cache[0] < effective_ttl:
        return _legal_forms_cache[1]
    async with _make_client() as client:
        r = await client.get(f"{ZEFIX_BASE}/legalForm")
        r.raise_for_status()
        data = r.json()
    _legal_forms_cache = (now, data)
    return data


def _reset_legal_forms_cache() -> None:
    """Test helper: clear the cache between tests."""
    global _legal_forms_cache
    _legal_forms_cache = None


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
@logged_tool("zefix_search_companies")
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
            data = await _zefix_post_search(client, body)
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
        return json.dumps(
            {
                "results": summaries,
                "count": len(summaries),
                "offset": params.offset,
                "hasMoreResults": has_more,
                "totalApproximate": total,
            },
            ensure_ascii=False,
            indent=2,
        )

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
@logged_tool("zefix_get_company")
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
@logged_tool("zefix_get_company_by_uid")
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
            data = await _zefix_post_search(client, body)
    except Exception as e:
        return _handle_http_error(e)

    err = _zefix_error_to_str(data) if isinstance(data, dict) else None
    if err:
        return f"Keine Firma mit UID {uid_formatted} im Handelsregister gefunden.\n\n{err}"

    firms = data.get("list", [])
    # Nur der exakte Treffer. Bis zum 2026-08-15 fiel dieser Zweig auf
    # `firms[:1]` zurueck, und das war keine Grosszuegigkeit, sondern eine
    # falsche Auskunft: Die Suche laeuft mit `searchType: CONTAINS` ueber das
    # Namensfeld, und Zefix beantwortet CHE-999.999.999 mit «CHEMAM - 999»
    # (UID CHE-113.593.998, an der Quelle geprueft). Der Rueckfall gab diese
    # Firma als Handelsregister-Eintrag zur angefragten UID aus — vollstaendig,
    # plausibel, formatiert, und ueber jemand anderen. Ein Modell, das die
    # Antwort liest, hat keinen Anhaltspunkt, dass die Zuordnung nicht stimmt.
    #
    # Eine Trefferliste ist noch keine Antwort. Ohne exakten Treffer sagt das
    # Werkzeug, dass es nichts gefunden hat.
    exact = [f for f in firms if re.sub(r"[^0-9]", "", f.get("uid", "")) == uid_clean]
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
@logged_tool("zefix_verify_company")
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
        # Ueber `_zefix_post_search`, nicht ueber `raise_for_status()`: Zefix
        # beantwortet eine Suche ohne Treffer mit HTTP 404 und dem
        # NORESULT-Umschlag. Der rohe Aufruf warf darauf, und `_handle_http_error`
        # antwortete «Eintrag nicht gefunden. Bitte EHRAID oder UID pruefen» —
        # auf eine Namenssuche hin, bei der weder EHRAID noch UID im Spiel
        # waren. Der freundliche Zweig darunter war damit unerreichbar.
        async with _make_client() as client:
            data = await _zefix_post_search(client, body)
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
@logged_tool("zefix_list_legal_forms")
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
@logged_tool("zefix_list_municipalities")
async def zefix_list_municipalities(params: MunicipalitiesInput) -> str:
    """Listet Schweizer Gemeinden auf und löst die `legalSeatId` einer Firma auf.

    **`legalSeatId` ist eine BFS-Nummer.** Sie trifft die Spalte `BFS-ID`, nicht
    die interne `ID` der Gemeinde. Die beiden sind bei **keiner** der 2112
    Gemeinden gleich, und beide Wertebereiche überlappen sich — wer über die
    falsche Spalte nachschlägt, bekommt keinen Fehler, sondern eine andere,
    echte Schweizer Gemeinde: `legalSeatId=261` ist Zürich, über `ID` gelesen
    aber Aarwangen (BE); `2701` ist Basel, über `ID` gelesen Embd (VS).

    Deshalb macht `legal_seat_id` die Auflösung selbst, statt sie dem Aufrufer
    und einer Tabelle mit zwei ähnlich aussehenden Zahlenspalten zu überlassen.

    Args:
        params (MunicipalitiesInput):
            - legal_seat_id (Optional[int]): `legalSeatId` einer Firma → genau eine Gemeinde.
            - canton (Optional[str]): Kanton-Filter (z.B. 'ZH'). Ohne Filter: alle ~2'100 Gemeinden.
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

    if params.legal_seat_id is not None:
        # Ueber `bfsId`, nicht ueber `id`. Siehe Docstring.
        match = [c for c in communities if c.get("bfsId") == params.legal_seat_id]
        if not match:
            wrong = next((c for c in communities if c.get("id") == params.legal_seat_id), None)
            hint = (
                f" Es gibt allerdings eine Gemeinde mit der internen ID "
                f"{params.legal_seat_id} ({wrong['name']}, {wrong['canton']}) — "
                "das ist eine andere Gemeinde und nicht der Sitz dieser Firma."
                if wrong
                else ""
            )
            return f"Keine Gemeinde mit BFS-Nummer {params.legal_seat_id} gefunden.{hint}"
        communities = match

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
        "_`legalSeatId` einer Firma entspricht der Spalte **BFS-ID**, nicht der "
        "internen Zefix-ID._",
        "",
        "| BFS-ID (= legalSeatId) | Name | Kanton | interne Zefix-ID | HR-Kreis |",
        "|-----------------------|------|--------|------------------|----------|",
    ]
    for c in sorted(communities, key=lambda x: x.get("name", ""))[:100]:
        lines.append(
            f"| {c.get('bfsId', '—')} | {c['name']} | {c['canton']} "
            f"| {c['id']} | {c.get('registryOfficeId', '—')} |"
        )

    if len(communities) > 100:
        lines += [
            "",
            f"_Zeige 100 von {len(communities)} Gemeinden. "
            "Kanton-Filter verwenden für vollständige Liste._",
        ]
    return "\n".join(lines)


# ===========================================================================
# Amtsblattportal (gazette) — SHAB + cantonal official gazettes
# ===========================================================================
#
# The join key with Zefix is the UID. Zefix tells you whether a company
# exists; the gazette tells you what it does. Three verified upstream quirks
# shape this code (see README "Known limitations" and CHANGELOG "Known
# findings"):
#   Quirk 1 — Silent Ignore: unknown query params -> full 2.79M corpus, HTTP 200.
#   Quirk 2 — Silent Empty:  invalid rubric code -> HTTP 200, empty, total 0/null.
#   Quirk 3 — Two-step fetch: list = meta only; full text lives in the XML.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Gazette HTTP core (retry on transient 5xx)
# ---------------------------------------------------------------------------


async def _gazette_get(
    path: str,
    params: dict | None = None,
    *,
    total_budget: float = GAZETTE_TOTAL_BUDGET_S,
) -> httpx.Response:
    """GET a gazette endpoint, retrying what is worth retrying (ARCH-014).

    The shared core of :func:`_gazette_get_json` and :func:`_gazette_get_text`.
    Both used to carry their own copy of this loop, which meant the retry
    policy — and now the budget — would have had to be maintained twice.

    Retried: transient 5xx, 429, and **network errors and timeouts**. The last
    group is the one an outage actually produces: a refused connection or a
    read that never completes used to end the call on the first failure, while
    a 503 from the very same outage got three attempts. That asymmetry made the
    retry look present and leave the common case uncovered.

    Not retried: any other 4xx — a statement about the request, not about the
    moment, and it reads the same on the third attempt.

    How fast and how long: a jittered linear backoff capped at
    ``GAZETTE_MAX_DELAY_S``, a ``Retry-After`` from the gazette overriding that
    curve, and ``total_budget`` bounding the whole call.
    """
    # Monotonic, so an NTP step cannot hand out or revoke budget.
    deadline = monotonic() + total_budget
    last_error: Exception | None = None

    async def _wait(attempt: int, resp: httpx.Response | None, why: object) -> bool:
        """Sleep before the next attempt; False if the budget forbids it."""
        delay = gazette_retry_delay(attempt, resp)
        # A wait that outlasts the budget is a wait for nobody: the caller has
        # given up by the time it ends.
        if delay >= deadline - monotonic():
            return False
        log_event(
            logging.WARNING,
            "gazette_retry",
            path=path,
            reason=why,
            attempt=attempt,
            delay=round(delay, 2),
        )
        await _sleep(delay)
        return True

    async with _make_client() as client:
        for attempt in range(1, GAZETTE_MAX_RETRIES + 1):
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            try:
                # httpx applies its timeout per operation (connect/read/write/
                # pool) and the read timeout restarts with every chunk — that
                # bounds each step, not the call. `asyncio.timeout` is the
                # wall-clock deadline the budget actually promises.
                async with asyncio.timeout(remaining):
                    r = await client.get(f"{GAZETTE_BASE}{path}", params=params, timeout=remaining)
            except TimeoutError as exc:
                # The deadline fired, so the budget is spent by definition —
                # say that rather than surfacing a bare TimeoutError whose
                # message names neither the budget nor the endpoint.
                raise TimeoutError(
                    f"gazette budget of {total_budget:g}s spent before a usable answer ({path})"
                ) from exc
            except httpx.RequestError as exc:
                last_error = exc
                if attempt >= GAZETTE_MAX_RETRIES:
                    break
                if not await _wait(attempt, None, type(exc).__name__):
                    break
                continue

            if r.status_code in _RETRYABLE_STATUS and attempt < GAZETTE_MAX_RETRIES:
                if await _wait(attempt, r, r.status_code):
                    continue
            r.raise_for_status()
            return r

    if last_error is not None:
        raise last_error
    raise TimeoutError(f"gazette budget of {total_budget:g}s spent before a usable answer ({path})")


async def _gazette_get_json(path: str, params: dict | None = None) -> Any:
    """GET a gazette JSON endpoint with retry on transient 5xx (502/503/504)."""
    return (await _gazette_get(path, params)).json()


async def _gazette_get_text(path: str, params: dict | None = None) -> str:
    """GET a gazette endpoint returning raw text (XML), with the same retry."""
    return (await _gazette_get(path, params)).text


def _build_gazette_params(raw: dict[str, Any]) -> dict[str, Any]:
    """Build the query dict EXCLUSIVELY from the allow-list.

    Silent Ignore: unbekannte Parameter -> voller Korpus statt 400. Vgl. CHANGELOG.
    User input is never forwarded as an arbitrary key — only allow-listed keys
    with non-empty values reach the query string.
    """
    params: dict[str, Any] = {"publicationStates": "PUBLISHED"}
    for key, value in raw.items():
        if value in (None, "", []):
            continue
        if key not in ALLOWED_GAZETTE_PARAMS:
            continue  # defensive: drop anything not explicitly allowed
        params[key] = value
    return params


async def _gazette_search(raw_params: dict[str, Any]) -> dict:
    """Run a /publications search and enforce the Quirk-1 plausibility check."""
    params = _build_gazette_params(raw_params)
    data = await _gazette_get_json("/publications", params=params)
    if not isinstance(data, dict):
        return {"content": [], "total": 0}
    total = data.get("total")
    # Quirk 1 plausibility check: a filtered request that still reports the
    # whole corpus means the filter was silently dropped upstream. This is the
    # only defence against a silent parameter rename on the provider side.
    if isinstance(total, int) and total > GAZETTE_IGNORED_FILTER_THRESHOLD:
        log_event(
            logging.ERROR,
            "gazette_filter_ignored",
            total=total,
            params=sorted(params),
        )
        raise GazetteFilterIgnored(
            f"Filter wurde vom Upstream ignoriert — Ergebnis nicht vertrauenswürdig "
            f"(total={total:,}, erwartet < {GAZETTE_IGNORED_FILTER_THRESHOLD:,}). "
            "Ursache: Silent Ignore unbekannter Parameter (Quirk 1, vgl. CHANGELOG)."
        )
    return data


# ---------------------------------------------------------------------------
# Rubric taxonomy — cached 24h, used to validate codes BEFORE any call (Quirk 2)
# ---------------------------------------------------------------------------

RUBRICS_TTL_SECONDS = float(os.environ.get("RUBRICS_TTL", "86400"))
_rubrics_cache: tuple[float, list[dict]] | None = None


async def _fetch_rubrics(ttl: float | None = None) -> tuple[list[dict], bool]:
    """Fetch the rubric/subRubric taxonomy with a TTL cache (default 24h).

    Returns (data, from_cache). Mirrors the LEGAL_FORMS_TTL pattern.
    """
    global _rubrics_cache
    effective_ttl = RUBRICS_TTL_SECONDS if ttl is None else ttl
    now = monotonic()
    if _rubrics_cache and now - _rubrics_cache[0] < effective_ttl:
        return _rubrics_cache[1], True
    data = await _gazette_get_json("/rubrics")
    if not isinstance(data, list):
        data = []
    _rubrics_cache = (now, data)
    return data, False


def _reset_rubrics_cache() -> None:
    """Test helper: clear the rubrics cache between tests."""
    global _rubrics_cache
    _rubrics_cache = None


def _extract_rubric_codes(rubrics_data: list[dict]) -> tuple[set[str], set[str]]:
    """Return (rubric_codes, subRubric_codes) from the taxonomy, defensively."""
    rubric_codes: set[str] = set()
    sub_codes: set[str] = set()
    for r in rubrics_data:
        if not isinstance(r, dict):
            continue
        code = r.get("code")
        if code:
            rubric_codes.add(code)
        for s in r.get("subRubrics", []) or []:
            if isinstance(s, dict) and s.get("code"):
                sub_codes.add(s["code"])
    return rubric_codes, sub_codes


async def _validate_rubric_code(code: str, kind: str) -> None:
    """Validate a rubric/subRubric code against the cached taxonomy.

    Quirk 2 (Silent Empty): an invalid code returns HTTP 200 with an empty
    result, which is indistinguishable from a legitimate no-hit. We therefore
    validate BEFORE issuing any /publications call and fail with the five
    closest valid codes.
    """
    rubrics_data, _ = await _fetch_rubrics()
    rubric_codes, sub_codes = _extract_rubric_codes(rubrics_data)
    valid = rubric_codes if kind == "rubric" else sub_codes
    if code in valid:
        return
    suggestions = difflib.get_close_matches(code, sorted(valid), n=5, cutoff=0.0)
    hint = ", ".join(suggestions) if suggestions else "— (z.B. HR, BH, KK, SB)"
    raise GazetteInvalidCode(
        f"Ungültiger {kind}-Code «{code}». Nächstliegende gültige Codes: {hint}."
    )


# ---------------------------------------------------------------------------
# Formatting / parsing helpers
# ---------------------------------------------------------------------------


def _gazette_meta_summary(item: dict) -> dict:
    """Normalise a publication list item (meta only, Quirk 3) into a summary."""
    meta = item.get("meta") if isinstance(item, dict) else None
    meta = meta if isinstance(meta, dict) else (item if isinstance(item, dict) else {})
    ro = meta.get("registrationOffice")
    ro_name = ro.get("displayName") if isinstance(ro, dict) else ro
    title = meta.get("title")
    if isinstance(title, dict):
        title = title.get("de") or next(iter(title.values()), None)
    date = meta.get("publicationDate")
    if isinstance(date, str) and "T" in date:
        date = date.split("T", 1)[0]
    return {
        "id": meta.get("id"),
        "rubric": meta.get("rubric"),
        "subRubric": meta.get("subRubric"),
        "publicationNumber": meta.get("publicationNumber"),
        "publicationDate": date,
        "registrationOffice": ro_name,
        "title": title,
        "cantons": meta.get("cantons"),
    }


def _localname(tag: str) -> str:
    """Strip any XML namespace, returning the bare local element name."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else tag


def _el_text(el: ET.Element) -> str:
    """Collapse an element's full text content (incl. inline markup children)."""
    return "".join(el.itertext()).strip()


def _first_local(root: ET.Element, name: str) -> ET.Element | None:
    """First descendant (or self) whose local name matches — namespace-agnostic."""
    for c in root.iter():
        if _localname(c.tag) == name:
            return c
    return None


def _node_to_value(el: ET.Element) -> Any:
    """Leaf element -> text; container -> {localName: value} (best-effort)."""
    children = list(el)
    if not children:
        return _el_text(el)
    return {_localname(c.tag): _node_to_value(c) for c in children}


def _parse_publication_xml(xml_text: str) -> dict:
    """Defensively parse a single-publication XML (Quirk 3).

    The schema is rubric-specific (HR03-export, SB01-export, …) and uses a
    per-rubric namespace, so we NEVER hard-code rubric-specific paths. Only
    two things are reliably present and therefore treated as mandatory:
    the meta block and content/publicationText. HR rubrics additionally carry
    commonsActual/company. Everything else lands best-effort in
    additional_fields. Malformed XML raises ET.ParseError to the caller.
    """
    root = ET.fromstring(xml_text)
    meta_el = _first_local(root, "meta")
    meta: dict[str, Any] = {}
    if meta_el is not None:
        for child in meta_el:
            meta[_localname(child.tag)] = _node_to_value(child)

    content_el = _first_local(root, "content")
    search_root = content_el if content_el is not None else root

    pt_el = _first_local(search_root, "publicationText")
    publication_text = _el_text(pt_el) if pt_el is not None else None

    company: dict[str, Any] = {}
    comp_el = _first_local(search_root, "company")
    if comp_el is not None:
        for key in ("name", "uid", "seat", "legalForm", "address"):
            el = _first_local(comp_el, key)
            if el is not None:
                company[key] = _node_to_value(el)

    additional: dict[str, Any] = {}
    if content_el is not None:
        for child in content_el:
            ln = _localname(child.tag)
            if ln == "publicationText":
                continue
            additional[ln] = _node_to_value(child)

    return {
        "meta": meta,
        "publicationText": publication_text,
        "company": company,
        "additional_fields": additional,
    }


def _gazette_md(lines: list[str], provenance: str) -> str:
    """Append the mandatory gazette attribution + provenance footer (Markdown)."""
    return "\n".join([*lines, "", "---", f"_{ATTRIBUTION_GAZETTE}_", f"_provenance: {provenance}_"])


def _gazette_json(payload: dict, provenance: str) -> str:
    """Wrap a JSON payload with the mandatory attribution + provenance fields."""
    enriched = {**payload, "attribution": ATTRIBUTION_GAZETTE, "provenance": provenance}
    return json.dumps(enriched, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Gazette input models
# ---------------------------------------------------------------------------


class GazettePublicationsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    uid: str = Field(
        ...,
        description=(
            "UID der Firma (Join-Schlüssel). Format CHE-XXX.XXX.XXX oder "
            "CHEXXXXXXXXX (9 Ziffern). Beispiel: 'CHE-116.115.052'."
        ),
        min_length=9,
        max_length=20,
    )
    rubric: str | None = Field(
        default=None,
        description="Optionaler Rubrik-Code zur Eingrenzung (z.B. 'HR'). Wird vorab validiert.",
        max_length=12,
    )
    sub_rubric: str | None = Field(
        default=None,
        description="Optionaler Subrubrik-Code (z.B. 'HR03'). Wird vorab validiert.",
        max_length=12,
    )
    date_start: str | None = Field(
        default=None,
        description="Zeitraum-Start (YYYY-MM-DD).",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    date_end: str | None = Field(
        default=None,
        description="Zeitraum-Ende (YYYY-MM-DD).",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    limit: int = Field(
        default=50,
        description="Maximale Anzahl Publikationen (1–100). Standard: 50.",
        ge=1,
        le=GAZETTE_MAX_LIMIT,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


class GazettePublicationInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    id: str = Field(
        ...,
        description=(
            "System-ID der Publikation (aus gazette_company_publications). "
            "Beispiel: '1611620c-ff25-4043-bf0d-395b0352d35b'."
        ),
        min_length=8,
        max_length=64,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


class GazetteStatusInput(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


# ---------------------------------------------------------------------------
# Tool: gazette_company_publications (the UID join — core feature)
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gazette_company_publications",
    annotations={
        "title": "Amtsblatt-Publikationen zu einer UID (Join)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@logged_tool("gazette_company_publications")
async def gazette_company_publications(params: GazettePublicationsInput) -> str:
    """Alle Amtsblatt-Publikationen (SHAB + kantonal) zu einer Firmen-UID.

    Das Kernfeature: der Join zwischen Handelsregister und Amtsblatt über die
    UID. Zefix sagt, ob eine Firma existiert — das Amtsblatt sagt, was über sie
    publiziert wurde (HR-Mutationen, Schuldenrufe, Konkurse, Schuldbetreibungen …).
    Der Einstieg ist ausschliesslich die Firmen-UID (juristische Person); ein
    Personen-Sucheinstieg existiert bewusst nicht (siehe README «Data Protection
    & Scope»).

    Args:
        params (GazettePublicationsInput):
            - uid (str): UID CHE-XXX.XXX.XXX (Pflicht, Regex-validiert)
            - rubric / sub_rubric (Optional[str]): Rubrik-/Subrubrik-Filter
            - date_start / date_end (Optional[str]): Zeitraum YYYY-MM-DD
            - limit (int): 1–100 (Standard 50)
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Publikationen (neueste zuerst) mit Datum, Rubrik, Titel, ID.
    """
    # Guardrail: eine unvalidierte UID würde bei Silent Ignore 2.79 Mio.
    # Records auslösen — daher Regex-Validierung VOR dem Call.
    uid = _uid_format(params.uid)
    if not UID_RE.match(uid):
        return (
            f"Fehler: Ungültige UID «{params.uid}». "
            "Erwartet: CHE-XXX.XXX.XXX (9 Ziffern, z.B. CHE-116.115.052)."
        )

    try:
        if params.rubric:
            await _validate_rubric_code(params.rubric, "rubric")
        if params.sub_rubric:
            await _validate_rubric_code(params.sub_rubric, "subRubric")
        data = await _gazette_search(
            {
                "uids": uid,
                "rubrics": params.rubric,
                "subRubrics": params.sub_rubric,
                "publicationDate.start": params.date_start,
                "publicationDate.end": params.date_end,
                "pageRequest.size": min(params.limit, GAZETTE_MAX_LIMIT),
            }
        )
    except Exception as e:
        return _handle_http_error(e)

    content = data.get("content", []) or []
    total = data.get("total")
    summaries = [_gazette_meta_summary(i) for i in content]
    summaries.sort(key=lambda s: s.get("publicationDate") or "", reverse=True)

    if params.response_format == ResponseFormat.JSON:
        return _gazette_json(
            {"uid": uid, "count": len(summaries), "total": total, "publications": summaries},
            "live_api",
        )

    lines = [
        f"## Amtsblatt-Publikationen: {uid}",
        f"Gefunden: **{len(summaries)}** (total gemeldet: {total})",
        "",
    ]
    if not summaries:
        lines.append("_Keine Publikationen zu dieser UID gefunden._")
    for s in summaries:
        title = s.get("title") or "—"
        lines += [
            f"### {s.get('publicationDate') or '—'} · {s.get('rubric') or '?'}/{s.get('subRubric') or '?'}",
            f"- **Titel:** {title}",
            f"- **Amt:** {s.get('registrationOffice') or '—'} | **Kantone:** "
            f"{', '.join(s['cantons']) if isinstance(s.get('cantons'), list) else (s.get('cantons') or '—')}",
            f"- **Publ.-Nr.:** {s.get('publicationNumber') or '—'} | **ID:** `{s.get('id')}`",
            "",
        ]
    lines.append("_Detail-Volltext via `gazette_get_publication(id=…)`._")
    return _gazette_md(lines, "live_api")


# ---------------------------------------------------------------------------
# Tool: gazette_get_publication (single publication incl. XML full text)
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gazette_get_publication",
    annotations={
        "title": "Einzelpublikation inkl. XML-Volltext",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@logged_tool("gazette_get_publication")
async def gazette_get_publication(params: GazettePublicationInput) -> str:
    """Einzelne Publikation inkl. amtlichem Volltext (aus dem XML, defensiv geparst).

    Quirk 3: Die Listen-API liefert nur meta — der eigentliche Inhalt steht nur
    im rubrikspezifischen XML unter /publications/{id}/xml. Pflichtfelder:
    meta, publicationText. Bei HR-Rubriken zusätzlich company. Alles Übrige
    landet best-effort in additional_fields.

    Args:
        params (GazettePublicationInput):
            - id (str): Publikations-ID
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Volltext + Firmenangaben (falls HR) + Zusatzfelder.
    """
    try:
        xml_text = await _gazette_get_text(f"/publications/{params.id}/xml")
    except Exception as e:
        return _handle_http_error(e)

    try:
        parsed = _parse_publication_xml(xml_text)
    except ET.ParseError as e:
        return f"Fehler: XML der Publikation {params.id} konnte nicht geparst werden ({e})."

    meta = parsed["meta"]
    if params.response_format == ResponseFormat.JSON:
        return _gazette_json(parsed, "live_api")

    title = meta.get("title")
    if isinstance(title, dict):
        title = title.get("de") or next(iter(title.values()), None)
    lines = [
        f"## {title or 'Publikation'} ",
        "",
        "| Feld | Wert |",
        "|------|------|",
        f"| **ID** | `{meta.get('id', params.id)}` |",
        f"| **Rubrik** | {meta.get('rubric', '?')} / {meta.get('subRubric', '?')} |",
        f"| **Datum** | {meta.get('publicationDate', '—')} |",
        f"| **Publ.-Nr.** | {meta.get('publicationNumber', '—')} |",
    ]
    ro = meta.get("registrationOffice")
    if isinstance(ro, dict):
        ro = ro.get("displayName")
    if ro:
        lines.append(f"| **Amt** | {ro} |")
    lines.append("")

    company = parsed.get("company") or {}
    if company:
        lines.append("### Firma")
        for key in ("name", "uid", "seat", "legalForm"):
            if company.get(key):
                lines.append(f"- **{key}:** {company[key]}")
        addr = company.get("address")
        if isinstance(addr, dict):
            addr_str = " ".join(str(v) for v in addr.values() if v)
            lines.append(f"- **address:** {addr_str}")
        elif addr:
            lines.append(f"- **address:** {addr}")
        lines.append("")

    if parsed.get("publicationText"):
        lines += ["### Amtlicher Text", parsed["publicationText"], ""]

    extra = parsed.get("additional_fields") or {}
    if extra:
        extra_keys = ", ".join(sorted(extra.keys()))
        lines += [f"_Zusatzfelder (additional_fields): {extra_keys}_"]

    return _gazette_md(lines, "live_api")


# ---------------------------------------------------------------------------
# Tool: gazette_source_status (reachability + cache ages)
# ---------------------------------------------------------------------------


async def _probe_endpoint(url: str) -> dict:
    """Lightweight reachability probe: reports reachable/status/latency."""
    start = monotonic()
    try:
        async with _make_client() as client:
            r = await client.get(url)
            r.raise_for_status()
        return {
            "reachable": True,
            "status": r.status_code,
            "latency_ms": int((monotonic() - start) * 1000),
        }
    except Exception as e:
        return {
            "reachable": False,
            "error": type(e).__name__,
            "latency_ms": int((monotonic() - start) * 1000),
        }


def _cache_age(cache: tuple[float, Any] | None) -> str:
    if not cache:
        return "nicht geladen"
    age = int(monotonic() - cache[0])
    if age < 90:
        return f"{age}s"
    if age < 5400:
        return f"{age // 60}min"
    return f"{age // 3600}h"


@mcp.tool(
    name="gazette_source_status",
    annotations={
        "title": "Erreichbarkeit beider Quellen + Cache-Alter",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@logged_tool("gazette_source_status")
async def gazette_source_status(params: GazetteStatusInput) -> str:
    """Status beider Datenquellen (Zefix + Amtsblattportal) und Cache-Alter.

    Prüft die Erreichbarkeit beider Upstreams und meldet das Alter der
    In-Memory-Caches (Rubriken, Rechtsformen).

    Args:
        params (GazetteStatusInput):
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Erreichbarkeit, Latenz und Cache-Alter je Quelle.
    """
    zefix = await _probe_endpoint(f"{ZEFIX_BASE}/legalForm")
    gazette = await _probe_endpoint(f"{GAZETTE_BASE}/rubrics")
    legal_forms_age = _cache_age(_legal_forms_cache)
    rubrics_age = _cache_age(_rubrics_cache)

    payload = {
        "zefix": {**zefix, "base": ZEFIX_BASE, "legal_forms_cache_age": legal_forms_age},
        "gazette": {**gazette, "base": GAZETTE_BASE, "rubrics_cache_age": rubrics_age},
    }

    if params.response_format == ResponseFormat.JSON:
        return _gazette_json(payload, "live_api")

    def _icon(ok: bool) -> str:
        return "✅" if ok else "❌"

    lines = [
        "## Quellen-Status",
        "",
        "| Quelle | Erreichbar | Latenz | Cache-Alter |",
        "|--------|-----------|--------|-------------|",
        f"| Zefix (Handelsregister) | {_icon(zefix['reachable'])} | "
        f"{zefix['latency_ms']}ms | Rechtsformen: {legal_forms_age} |",
        f"| Amtsblattportal | {_icon(gazette['reachable'])} | "
        f"{gazette['latency_ms']}ms | Rubriken: {rubrics_age} |",
    ]
    return _gazette_md(lines, "live_api")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

DEFAULT_RATE_LIMIT = int(os.environ.get("MCP_RATE_LIMIT", "60"))
DEFAULT_RATE_WINDOW = float(os.environ.get("MCP_RATE_WINDOW", "60"))


def _build_sse_app():
    """Build the SSE Starlette app with auth + rate-limit middleware.

    Requires `MCP_API_KEY` env var to be set. Fails loud at startup otherwise —
    no implicit "auth disabled" mode is supported for SSE.
    """
    from ._middleware import BearerAuthMiddleware, RateLimitMiddleware

    api_key = os.environ.get("MCP_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "MCP_API_KEY must be set when MCP_TRANSPORT=sse. "
            "Generate a random key (e.g. `openssl rand -hex 32`) and pass it via env."
        )

    app = mcp.sse_app()
    # Rate limit runs *after* auth so the bucket key is the bearer-token hash.
    # Middleware added later runs first → add rate-limit first, then auth.
    app.add_middleware(RateLimitMiddleware, limit=DEFAULT_RATE_LIMIT, window=DEFAULT_RATE_WINDOW)
    app.add_middleware(BearerAuthMiddleware, expected_key=api_key)
    log_event(
        logging.INFO,
        "sse_app_built",
        rate_limit=DEFAULT_RATE_LIMIT,
        rate_window=DEFAULT_RATE_WINDOW,
    )
    return app


def main() -> None:
    from ._otel import init_otel

    init_otel()
    if transport == "stdio":
        log_event(logging.INFO, "starting", transport="stdio")
        mcp.run(transport="stdio")
        return
    if transport == "sse":
        import uvicorn

        app = _build_sse_app()
        host = BIND_HOST
        port = BIND_PORT
        log_event(logging.INFO, "starting", transport="sse", host=host, port=port)
        uvicorn.run(app, host=host, port=port, log_level=mcp.settings.log_level.lower())
        return
    raise SystemExit(f"Unsupported MCP_TRANSPORT={transport!r} (expected 'stdio' or 'sse')")


if __name__ == "__main__":
    main()
