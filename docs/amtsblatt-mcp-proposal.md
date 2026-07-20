# Proposal — a separate `amtsblatt-mcp` server

> **Status:** recommendation (Phase 2, Option C). **Date:** 2026-07-20.
> **Decision taken:** the broad Amtsblattportal coverage is split out of
> `register-mcp` into its own server; `register-mcp` keeps only the
> company-centric UID join (see below). This document is the *specification*
> for `amtsblatt-mcp` — the "Empfehlung statt Code" the portfolio's data-source
> probe prescribes when a data source is a server of its own, not a tool
> extension.

This is **not** built in this repository. It is the hand-off document for a
follow-up session that stands the server up via the `github-repo` /
`mcp-builder` skills. Everything below is grounded in the live probe
(`docs/probe-shab.md`, 2026-07-19).

---

## 1. Why a separate server (scope decision)

`register-mcp` is a **commercial-register** server. The Amtsblattportal is far
broader: public procurement, cantonal notices, debt-collection, bankruptcies,
building applications, inheritance calls. Applying the portfolio's own test —

> *"If the new tools mostly have nothing to do with the commercial register,
> it is a server of its own."*

— the broad Amtsblatt tools (full-text search across all rubrics/cantons,
procurement) fail the coherence test. Only the **UID join** (given a company
UID, what has been published about it) genuinely complements the register. So:

| Server | Keeps | Rationale |
|---|---|---|
| **`register-mcp`** (this repo) | Zefix (6) + `gazette_company_publications`, `gazette_get_publication`, `gazette_source_status` | UID-scoped join only. Data-protection-safe **by construction** — no free-text / person-name entry point exists. |
| **`amtsblatt-mcp`** (new) | broad gazette search, procurement, taxonomy browser | Full platform coverage of **green** rubrics, its own trust level, its own release cadence. |

The two link cleanly: `register-mcp` establishes the UID and the company's own
publications; `amtsblatt-mcp` covers everything that is *not* keyed on a single
company.

## 2. Architecture decision — Architecture A (Live-API-only)

The required endpoints respond stably without authentication and the source is
built for production use, so no bulk dump is needed for the targeted, filtered
queries this server serves:

- `GET /publications` (JSON default) — list/search, `total` + `pageRequest`.
- `GET /publications/{id}/xml` — the **only** source of the full publication text.
- `GET /rubrics` — the full rubric/subRubric taxonomy (cached 24 h in memory).
- `GET /tenants` — 29 mandates (27 CANTON, 1 SHAB, 1 NEUTRAL).

Resilience defaults carry over from `register-mcp`: retry-with-backoff on
transient 5xx, a Pydantic response envelope with `source` + `provenance`, an
egress allow-list, and the two verified quirk guardrails (Silent Ignore →
param allow-list + plausibility threshold; Silent Empty → validate every rubric
code against the taxonomy *before* the call).

## 3. The hard data-protection rule — a **fail-closed green allow-list**

The Amtsblattportal systematically publishes rubrics containing personal data of
**natural** persons. Public though it is, making it *systematically queryable by
name* through an AI agent is a repurposing the publication never intended and is
a profiling instrument under the revised Swiss FADP (revDSG). Therefore:

1. **Allow-list, never block-list.** A rubric that is not *explicitly* green is
   not queryable. New rubrics appearing upstream are closed by default.
2. **No person-based search entry** in any tool signature — no name, birth date
   or residential-address parameter. Company (legal-person) search is allowed.
3. **No persistence** of publication content. Pass-through only; at most a
   short-lived request cache. Official publications have statutory deletion
   periods — a cache that outlives them would actively undermine them.
4. When a request targets a blocked rubric: a **clear, explanatory message**
   about the deliberate scope decision — never a silent empty result, and never
   a circumvention hint.

### 3.1 Rubric traffic-light table (green / yellow / red)

Classification of the top-level rubrics from the live `/rubrics` taxonomy
(2026-07-19). **Only 🟢 green is erschlossen** in `amtsblatt-mcp`; 🟡 and 🔴 are
excluded until explicitly released.

| Class | Rubric(s) | Meaning | Natural-person data |
|---|---|---|---|
| 🟢 | `HR`, `BH` | Handelsregister + HR-Verordnungs-Bekanntmachungen | none (legal persons) |
| 🟢 | `OB-AR`, `OB-BS`, `OB-TI`, `OB-ZG` (+ `OB-BL`/`OB-VS` inactive) | Öffentliches Beschaffungswesen (Submissionen) | none |
| 🟢 | `AR-NW40`, `AR-OW40`, `AR-VS40`, `BA-SH40` | Öffentliche Beschaffung (non-simap subrubrics) | none |
| 🟢 | `KA-*`, `RS-*`, `RE-*`, `PR-*`, `RP-*` | Kantonale/kommunale Bekanntmachungen, Beschlüsse, politische Rechte, Raumplanung | institutional; incidental at most |
| 🟡 | `AZ`/`AI-*`, `SW-*`, `GB-*`/`GE-*`, `BV-*`, `AB`, `FM` | Anzeigen, Steuerwesen, gerichtliche Entscheide, Bürgerrecht, Arbeit, Finanzmarkt | possible, context-dependent |
| 🟡→🔴 | `BP-*` | Baugesuche / Baupublikationen | often owner names → treat as excluded |
| 🔴 | `KK`, `SB`, `LS`, `SR`, `NA` | Konkurse, Schuldbetreibungen, Liquidations-/Schuldenrufe, Nachlass | systematic |
| 🔴 | `ES`, `TE-*`, `VA-*`, `FZ-*`, `UV` | Erbschaft/Testament/Ableben, Familie & Zivilstand, Vorladungen | systematic |

> The green set is encoded as an explicit `frozenset` in code and re-verified
> against the live `/rubrics` taxonomy at build time. The default corpus-wide
> search injects the green top-level rubrics (`HR`, `BH`, `OB-*`) so a
> keyword-only query can **never** reach a red rubric.

### 3.2 Note on `register-mcp`'s retained UID join

`gazette_company_publications` in `register-mcp` intentionally keeps *full*
rubric access (incl. a firm's own `KK`/`SB`) — but only ever keyed on a company
**UID** (a legal person). A firm's bankruptcy is corporate data, not
natural-person profiling, and the UID scoping makes name-based enumeration
impossible. This is the deliberate boundary between the two servers.

## 4. Tool signatures (all `readOnlyHint=True`)

| Tool | Signature (sketch) | Notes |
|---|---|---|
| `search_publications` | `(keyword?, rubric?, sub_rubric?, canton?, date_start?, date_end?, limit=20)` | rubric/sub_rubric must be **green** (else explanatory block message); no rubric → green rubrics injected. **No `uid`-of-person, no name param.** |
| `search_procurement` | `(keyword?, canton?, date_start?, date_end?, include_inactive=False, limit=20)` | `OB-*` only; canton without `OB-*` (incl. ZH) → simap.ch explainer, no call. No CPV (source has none). |
| `get_publication` | `(id, format=markdown)` | single publication, XML full text, defensively parsed. |
| `list_rubrics` | `(language=de, format=markdown, class=green)` | taxonomy browser; may annotate each rubric with its traffic-light class. |
| `source_status` | `(format=markdown)` | reachability + cache ages; graceful-degradation status. |

Reuse the extracted implementations from `register-mcp`'s git history
(`gazette_search_publications`, `gazette_search_procurement`,
`gazette_list_rubrics`, the `PROCUREMENT_RUBRICS` map, `_gazette_search`, the
XML parser) as the starting point — then add the green allow-list gate in front
of every rubric that reaches the query string.

## 5. Anchor demo query

The original "Zürich procurement" anchor is **not answerable** via this source
(no `OB-ZH`; ZH tenders live on simap.ch — a separate platform). Honest,
answerable anchors:

- **Procurement (feasible canton):** *"Which public IT tenders were published in
  canton Basel-Stadt (`OB-BS`) in the last three months?"*
- **Cross-server (portfolio-strongest):** establish a company's UID in
  `register-mcp`, then read its gazette history — demonstrating exactly the
  complementarity the split preserves.

## 6. Known limitations (to carry into the README)

- **Uneven cantonal coverage.** Only 16 of 29 mandates expose their own rubric
  taxonomy; AG, FR, GE, GL, JU, LU, NE, UR are (still) incomplete.
- **Deletion periods.** Publications drop out of the API over time — hence no
  persistence, only pass-through.
- **Procurement boundary.** Most cantons (incl. ZH) route tenders through
  simap.ch, outside this portal; no CPV classification exists here.
- **No push.** Polling only; no subscription/webhook mechanism.
- **Sorting is not steerable** upstream (default: newest first); sort
  client-side if needed.

## 7. Test plan (mirrors the portfolio mandatory set)

1. Green-rubric search returns hits with a correct source URL.
2. **Blocked (red) rubric → clean explanatory message, no data** (the key test).
3. Canton filter (ZH green rubrics) works.
4. Procurement with a deadline → correct remaining-time calc (Europe/Zurich, fixed "today").
5. Pagination across a page boundary.
6. No language duplicates in the result.
7. Inconsistent boolean values normalised via a shared `_to_bool()` helper.
8. API unreachable → explanatory error, not an empty result.

Fixtures from real, shortened responses — **no real personal data**, consistently
anonymised.

## 8. Repo hand-off (for the `github-repo` skill)

- **Name:** `amtsblatt-mcp`
- **Description:** `MCP server for amtsblattportal.ch (SHAB + cantonal gazettes) — procurement and official notices, person-data rubrics excluded by design`
- **Topics:** `mcp`, `model-context-protocol`, `llm`, `python`, `swiss-open-data`, `amtsblatt`, `shab`, `procurement`
- **License:** MIT (source: freely usable, no formal CC licence; attribution + liability disclaimer mandatory).
- **Cluster (Notion):** Legal / Registers.
- **Link:** cross-reference `register-mcp` for the UID join.
