# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **`ruff` mit Obergrenze gepinnt (`>=0.15.22,<0.17`).** ruff ist pre-1.0; seine
  Minors sind die Stelle, an der Regelverhalten und neue Checks innerhalb der
  gewählten Familien landen. Ohne Cap installiert die CI die jeweils neuste
  Version und wird ohne Codeänderung rot.

  Der Cap liegt bewusst über der Version, die `uv.lock` bereits auflöst
  (`0.16.0`). Ein `<0.16` hätte die Schranke zwar gesetzt, dabei aber still auf
  `0.15.22` zurückgedreht — eine Obergrenze soll den Stand einfrieren, nicht
  nebenbei ein Downgrade auslösen. `uv.lock` ist mitgezogen; die Änderung dort
  beschränkt sich auf die eine `specifier`-Zeile.

- **Emoji aus der H1 beider READMEs entfernt** (`# 🏛️ register-mcp`). Vorher
  nach Regel E4 geprüft: beide Dateien enthalten null `](#…)`-Anker, es bricht
  also kein Link. Emoji im Fliesstext bleiben unangetastet.

  Nicht geändert wurde `The UID join — Zefix ↔ Amtsblatt`. Der Validator meldete
  die Überschrift, das war aber ein Fehlalarm: `↔` ist Typografie, kein Emoji.
  Die Ursache lag in der Erkennung selbst und ist dort behoben (`E7`).

- **`test_search_companies_invalid_canton` prüfte nicht mehr, was der Name
  behauptet.** `pytest.raises(Exception)` besteht auch dann, wenn der Kanton
  gültig ist und stattdessen ein Feldname vertippt wurde — Pydantic wirft für
  `extra_forbidden` denselben Typ. Gegengeprüft: mit `nam=` statt `name=` und
  `canton="ZH"` blieb der Test grün, ohne die Kantonsprüfung noch zu berühren.

  Erwartet wird jetzt die strukturierte Fehlerliste, `("value_error",
  ("canton",))`. Nicht per `match=` auf dem Meldungstext: der ist deutsch und
  zählt die gültigen Kürzel auf, wäre als Testanker also unnötig beweglich.

- **Capped `mcp` at `<2`.** `mcp` 2.0.0, published 2026-07-28, removed
  `mcp.server.fastmcp` — the module this server imports. With the previous
  unbounded `>=1.28.1` every fresh resolve picked 2.0.0 and failed at import
  with `ModuleNotFoundError`, in CI and for anyone running `pip install` alike.
  Verified in both directions: 2.0.0 fails, `<2` resolves to 1.29.0 and imports
  cleanly. Migrating to the 2.x API (`mcp.server.mcpserver`) stays a separate,
  deliberate piece of work.

## [0.5.0] - 2026-07-20
### Changed — scope decision (Option C): register-mcp reduced to the UID join
- **The gazette surface is now company-scoped only (9 tools, down from 12).**
  Following an explicit scope review, `register-mcp` keeps exactly the three
  gazette tools that complement the commercial register via the company UID:
  - `gazette_company_publications` — the UID join (keeps full firm-scoped rubric
    access; a firm's own `KK`/`SB` is corporate data about a legal person).
  - `gazette_get_publication` — read one publication's XML full text (by id).
  - `gazette_source_status` — reachability of both sources + cache ages.
- **Removed** `gazette_search_publications`, `gazette_search_procurement` and
  `gazette_list_rubrics`. These are broad, non-company **platform** features
  (corpus-wide full-text search, cantonal procurement, taxonomy browsing) that
  do not belong in a commercial-register server. They are specified for a
  separate `amtsblatt-mcp` in `docs/amtsblatt-mcp-proposal.md`.
- **Data protection by construction (revDSG).** Every remaining gazette entry
  point is keyed on a company UID or an opaque publication id — there is no
  free-text / person-name search entry, so the server cannot be used to profile
  natural persons across the person-data-heavy rubrics (bankruptcy,
  debt-collection, calls to creditors, inheritance). `keyword` and `cantons`
  were removed from `ALLOWED_GAZETTE_PARAMS` so no future change can smuggle a
  corpus-wide keyword search in (fail-closed). New **"Data Protection & Scope"**
  section added to both READMEs.
- Zefix behaviour is unchanged. The three verified amtsblattportal quirks and
  their guardrails (Silent Ignore, Silent Empty, two-step XML fetch) are
  retained for the UID-scoped calls.

## [0.4.0] - 2026-07-19
### Added
- **`gazette_search_procurement` — public procurement / Submissionen search**
  (12 tools total). Searches the cantonal `OB-<canton>` rubrics by `canton`,
  free-text `keyword` and date range, newest first. Backed by the Phase-1 live
  probe (`docs/probe-shab.md`):
  - Procurement is **cantonal only** — active in AR, BS, TI, ZG; inactive in
    BL, VS (opt in via `include_inactive=True`). A canton without an `OB-*`
    rubric — **including Zürich** — returns an explanatory message pointing at
    **simap.ch** (a separate platform this server does not cover) instead of a
    misleading empty list.
  - The source carries **no CPV classification**; a keyword that looks like a
    CPV code (8 digits) triggers a warning. Filtering is free-text + canton +
    date only.
- README (EN + DE): new **"The UID join"** section documenting the
  Zefix ↔ Amtsblatt join path (bulk list has no company UID → single fetch
  carries `meta.uid`/`<uid>`), and a **procurement coverage** table.

### Fixed / Known findings
- **`SB` is *Schuldbetreibungen* (debt collection), not *Submissionen*.** The
  plural spelling had mislabelled `SB` as procurement in the tool description,
  the README probe tables and the test fixtures. Procurement is the cantonal
  `OB-*` family. Corrected across code, docs and tests.

## [0.3.0] - 2026-07-18
### Added
- **Second data source — the Amtsblattportal (SHAB + cantonal gazettes),
  `amtsblattportal.ch/api/v1`, no authentication.** Five new tools (prefix
  `gazette_`, 11 tools total), joined to Zefix on the UID:
  - `gazette_company_publications` — the UID join (core feature). All gazette
    publications for a `CHE-XXX.XXX.XXX` UID via `uids=`, newest first,
    optional rubric/time filters.
  - `gazette_search_publications` — full-text search via `keyword=` plus
    `rubrics`, `subRubrics`, `cantons`, and a `publicationDate` range. Rejects a
    call with no effective filter instead of paginating the 2.79M-record corpus.
  - `gazette_get_publication` — single publication incl. the XML full text,
    defensively parsed (rubric-specific schema).
  - `gazette_list_rubrics` — the rubric/subRubric taxonomy (prerequisite for
    valid filters), cached 24h in memory (`RUBRICS_TTL`, mirrors
    `LEGAL_FORMS_TTL`).
  - `gazette_source_status` — reachability of both upstreams and cache ages.
- Per-source attribution in every response envelope (`ATTRIBUTION_ZEFIX`,
  `ATTRIBUTION_GAZETTE`) so provenance is never ambiguous in a mixed answer;
  every `gazette_*` response also carries `provenance: "live_api" | "cached"`.
  The gazette liability disclaimer is mandatory (operator excludes liability
  for the content of individual publications).
- Guardrails: UID regex-validated before any call; `limit` hard-capped at 100
  (`pageRequest.size`); transient-5xx retry (502/503/504); all new tools
  `readOnlyHint=True`, `destructiveHint=False`, `idempotentHint=True`.
- New test module `tests/test_gazette.py` (happy path per tool, 503 retry,
  timeout/network error, the three quirks, gazette egress) plus `@live` tests.

### Security
- **Egress allow-list default widened** from `{www.zefix.admin.ch}` to
  `{www.zefix.admin.ch, amtsblattportal.ch}`. The httpx request hook is
  unchanged and stays strict — it still fires on the initial request **and on
  every redirect**, so a `Location` to an unlisted host raises `EgressDenied`.
  This widening is called out explicitly rather than shipped silently.
  **Upgrade note:** deployments that pin `MCP_ALLOWED_HOSTS` override the
  default entirely and MUST add `amtsblattportal.ch`, or every `gazette_*`
  call raises `EgressDenied`.

### Known findings
Three upstream quirks were verified live on 2026-07-18 and are defended in code:
- **Quirk 1 — Silent Ignore (critical).** Unknown query parameters are dropped
  without error: `uid=` (instead of `uids=`) or `text=` (instead of `keyword=`)
  both return HTTP 200 with the **full 2.79M-record corpus**. Defences: query
  strings are built exclusively from the `ALLOWED_GAZETTE_PARAMS` allow-list
  (no dynamic pass-through of user input), and every filtered response is
  plausibility-checked — a `total` above 2,000,000 is rejected as
  «Filter wurde vom Upstream ignoriert — Ergebnis nicht vertrauenswürdig». This
  check is the only defence against a silent provider-side parameter rename.
- **Quirk 2 — Silent Empty.** An invalid rubric code returns HTTP 200 with an
  empty result and `total: 0/null`, indistinguishable from a real no-hit.
  Defence: the `/rubrics` taxonomy is cached 24h and every rubric/subRubric code
  is validated **before** any call; an invalid code fails with the five closest
  valid codes via `difflib.get_close_matches`.
- **Quirk 3 — Two-step fetch.** The JSON list carries only `meta`; the actual
  content lives only in the XML at `/publications/{id}/xml`, under a
  rubric-specific, namespaced schema (`HR03-export`, `SB01-export`, …). Defence:
  namespace-agnostic, defensive parsing — `meta` and `content/publicationText`
  are mandatory, `commonsActual/company/*` is read for HR rubrics, and
  everything else falls best-effort into `additional_fields`; rubric-specific
  paths are never hard-coded.

## [0.2.0] - 2026-05-21
### Added
- **Defence-in-depth (Sprint 3 of mcp-audit-skill remediation):**
  - Egress allow-list: `_make_client` registers an httpx request hook
    that rejects any outbound URL whose host is not in `ALLOWED_HOSTS`
    (default `{www.zefix.admin.ch}`; override via `MCP_ALLOWED_HOSTS`).
    Fires on the initial request and on every redirect, so a malicious
    `Location` header cannot exfiltrate. Closes `SEC-021`.
  - Optional OpenTelemetry tracing behind `OTEL_EXPORTER_OTLP_ENDPOINT`,
    activated by the `[otel]` extra. No-op without env var or deps.
  - 6 new tests in `tests/test_egress.py` (allowed pass, evil host blocked,
    AWS-IMDS blocked, redirect-to-evil blocked, case normalisation).

### Added
- **Supply-chain & container hardening (Sprint 2 of mcp-audit-skill remediation):**
  - `Dockerfile` (multi-stage, `python:3.13-slim`, non-root `mcp` user,
    `uv sync --frozen --no-dev` from `uv.lock`); closes audit finding `SEC-007`.
  - `compose.yaml` for local dev with `read_only`, `cap_drop: ALL`,
    `no-new-privileges`.
  - `uv.lock` committed for reproducible builds.
  - `.github/dependabot.yml` with weekly pip + docker, monthly actions updates.
  - `SECURITY.md` with disclosure pathway and response SLAs.
  - `.github/CODEOWNERS` requiring review on security-sensitive surfaces.
  - CI extended: `lockfile` job runs `uv lock --locked`; `docker` job builds
    the image and smoke-tests (must fail without `MCP_API_KEY`, must run as
    user `mcp`). Together these close audit finding `OPS-Supply-Chain`.

### Added
- **SSE transport hardening (Sprint 1 of mcp-audit-skill remediation):**
  - Bearer-token authentication via `MCP_API_KEY` env var — server refuses to
    start in SSE mode without it (closes audit finding `SEC-AUTH-SSE`).
  - In-memory sliding-window rate limit (`MCP_RATE_LIMIT` / `MCP_RATE_WINDOW`,
    defaults 60/60s) per bearer-token hash; returns HTTP 429 with
    `Retry-After` (closes `SEC-023`).
  - Structured JSON logging on stderr for every tool call with `tool`, `status`,
    `latency_ms`; auth-failures and rate-limit events at WARNING (closes `OBS-001`).
  - TTL cache (24h, `LEGAL_FORMS_TTL`) on Zefix `legalForm` reference data
    (closes `ARCH-CACHE`).
- 11 new tests under `tests/test_security.py` covering auth, rate-limit, cache.

### Changed
- `register-mcp` console script now points at `register_mcp.server:main` instead
  of `mcp.run` directly, so the SSE entry-point can install middleware.

## [0.1.0] - 2026-04-01

### Added
- Initial release with Phase 1 implementation (no authentication required)
- **Zefix tools**: `zefix_search_companies`, `zefix_get_company`, `zefix_get_company_by_uid`, `zefix_verify_company`
- **Reference data**: `zefix_list_legal_forms`, `zefix_list_municipalities`
- Dual transport: stdio (Claude Desktop) + SSE (cloud/Railway)
- GitHub Actions CI (Python 3.11, 3.12, 3.13)
- Bilingual documentation (DE/EN)
- Unit and integration tests (mocked HTTP via respx)
