# Live-Probe — Amtsblattportal (SHAB/SOGC) mit Fokus Beschaffungswesen

> **Phase 1 — Live-Probe.** Dieses Dokument hält den empirischen Befund der
> REST-API von [amtsblattportal.ch](https://amtsblattportal.ch/) fest, so wie
> die Quelle sich am Probe-Datum tatsächlich verhielt — nicht wie die Doku sie
> beschreibt. Grundlage ist die Methodik des Skills `mcp-data-source-probe`
> («Dokumentation ist ein Foto, Live-Probe ist der aktuelle Zustand»).
>
> **Probe-Datum:** 2026-07-19 · **Auth:** keine (für Datenabruf) ·
> **Ergebnis:** API produktiv nutzbar, JSON verfügbar, Rubriken-Taxonomie über
> Endpoint abrufbar. **Wichtigster Vorbehalt:** öffentliches Beschaffungswesen
> ist ausschliesslich eine *kantonale* Rubrik und existiert **nur in 4 aktiven
> Kantonen (AR, BS, TI, ZG) — nicht in Zürich.** Die Anchor Demo Query lässt
> sich für den Kanton Zürich über diese Quelle **nicht** beantworten (siehe
> Abschnitt 10).

---

## 1. Steckbrief der Quelle

| Feld | Wert |
|---|---|
| Betreiber | SECO / Staatssekretariat für Wirtschaft (eSHAB), Bund |
| Portal | `https://amtsblattportal.ch/` |
| API-Doku | `https://amtsblattportal.ch/docs/api/` (Asciidoctor-Einzelseite) |
| API-Basis | `https://amtsblattportal.ch/api/v1` |
| Umfang | SHAB (Schweizerisches Handelsamtsblatt / SOGC) **plus** kantonale Amtsblätter im selben Portal |
| Korpusgrösse | **2 789 951** publizierte Publikationen (live gemessen; wächst täglich) |
| Auth für Abruf | **keine** — «The API is freely accessible for anyone to use» |
| Auth für Publish / unveröffentlichte Eigen-Publikationen | Login (`POST /api/v1/login`) nötig → **Phase 1 out of scope** |
| Lizenz | Keine formelle CC-Lizenz. Frei nutzbar, aber **ohne Gewähr für Vollständigkeit/Richtigkeit**; rechtsverbindlich ist allein das signierte PDF; der Betreiber haftet nicht für den Inhalt einzelner Publikationen. |

**No-Auth-First bestätigt:** Sämtliche über die Web-UI sichtbaren Daten sind
ohne Credentials über die offene REST-API abrufbar. Authentifizierung ist
laut Doku nur für zwei Vorgänge nötig — beide für Phase 1 irrelevant:

- **Einreichen** von Publikationen (Publish-Endpunkte).
- Abruf **nicht-publizierter** Publikationen der *eigenen* Meldestelle.

---

## 2. Befund-Tabelle (Endpoints)

Alle Calls am 2026-07-19 gegen `https://amtsblattportal.ch/api/v1`.

| Endpoint | HTTP | Status | Records / Befund | Bemerkung |
|---|---|---|---|---|
| `GET /publications` (Accept: application/json) | 200 | ✅ funktioniert | `{content[], total, pageRequest}` | **JSON ist Default** — kein Pfad-Suffix nötig |
| `GET /publications/xml?publicationStates=PUBLISHED&rubrics=KK&…` | 200 | ✅ funktioniert | XML-Bulk-Liste, `<total>`, `<pageRequest>` | Doku-Beispiel, wie beschrieben |
| `GET /publications/csv?publicationStates=PUBLISHED&…` | 200 | ✅ funktioniert | `application/csv`, `;`-getrennt | flache Meta-Spalten, kein Inhalt |
| `GET /publications/pdf` · `/docx` | – | ✅ (dokumentiert) | Sammel-Export gekürzt | nicht im Detail geprobt |
| `GET /publications/{id}` (JSON) | 200 | ✅ funktioniert | `meta` inkl. **`meta.uid`**, aber `content: null` | Einzel-JSON liefert **keinen** Inhaltstext |
| `GET /publications/{id}/xml` | 200 | ✅ funktioniert | Voller Inhalt inkl. `<uid>…</uid>` | **einzige** Quelle für den vollständigen Publikationsinhalt |
| `GET /rubrics` | 200 | ✅ funktioniert | 152 Rubriken / 825 Sub-Rubriken (671 KB) | vollständige Taxonomie, mehrsprachig |
| `GET /tenants` | 200 | ✅ funktioniert | 29 Mandanten (27 CANTON, 1 SHAB, 1 NEUTRAL) | kantonale Amtsblätter → **selbes Portal** |
| `GET /publications/{id}/xml` (Einzelabruf) | 200 | ✅ | – | für Zwei-Schritt-Abruf |
| `GET /publications/json?…` | 404 | ❌ existiert nicht | `PublicationNotFoundException` | JSON läuft **nicht** über Pfad-Suffix |
| `GET /publications/{ungültige-GUID}/xml` | 404 | ❌ | `PublicationNotFoundException` | sauberer Fehler |
| `GET /subrubrics`, `/rubric`, `/cantons` | 404 | ❌ existiert nicht | – | Sub-Rubriken stecken im `/rubrics`-Baum |

### Reality-Check gegen Portal-Zahlen

- Voller Korpus live: **2 789 951** (Code-Konstante `GAZETTE_CORPUS_SIZE` =
  2 790 323 vom 2026-07-18 → plausibel, wächst täglich).
- `rubrics=HR` (Handelsregister) all-time: **2 262 954**.
- `rubrics=KK` (Konkurse) all-time: **213 413**.
- `rubrics=OB-BS` (Beschaffung Basel-Stadt) all-time: **3 065**.

Die Grössenordnungen sind konsistent — kein Hinweis auf eine defekte oder
künstlich gedrosselte API.

---

## 3. Response-Formate

| Format | Aufruf | Inhalt | Eignung |
|---|---|---|---|
| **JSON** | `GET /publications` + `Accept: application/json` (Default) | `content[]` mit `meta`, plus `total` & `pageRequest` | **Primärformat für den MCP-Server** |
| XML | `…/xml` | Bulk-Liste mit `ref`-Links; Einzel-XML mit vollem Inhalt | nötig für **Publikationsinhalt** (`<uid>`, Volltext) |
| CSV | `…/csv` | flache Meta-Tabelle (`;`-getrennt) | Bulk-Auswertung, keine Inhalte |
| PDF / DOCX | `…/pdf` · `…/docx` | gekürzte Volltexte, keine Liste | Mensch-lesbarer Export |

### Zwei-Schritt-Abruf (wichtiger Quirk)

Weder die **Bulk-Liste** (JSON/XML) noch das CSV enthalten den
Publikations­inhalt. Für den vollständigen Inhalt ist ein zweiter Call nötig:

1. **Liste:** `GET /publications?…` → pro Treffer `meta.id` / XML-`ref`.
2. **Einzel:** `GET /publications/{id}/xml` → voller Inhalt inkl. `<uid>`.

> ⚠️ **Einzel-JSON ist unvollständig:** `GET /publications/{id}` (JSON) liefert
> `content: null` — der eigentliche Publikationstext fehlt. Nur die
> **XML**-Variante `…/{id}/xml` enthält den vollständigen Inhalt. Die
> UID ist zwar auch im Einzel-**JSON** unter `meta.uid` (als Array) vorhanden,
> für Volltext + strukturierte Felder ist aber XML zwingend.

---

## 4. Query-Parameter (empirisch bestätigt)

`publicationStates` ist **Pflicht** (`PUBLISHED` oder `CANCELLED`).

| Parameter | Wirkung | Live-Test |
|---|---|---|
| `publicationStates` | Pflicht; `PUBLISHED` \| `CANCELLED` | ✅ |
| `rubrics` | eine/mehrere Rubrik-Codes (Plural = mehrfach anhängbar: `rubrics=KK&rubrics=NA`) | ✅ |
| `subRubrics` | eine/mehrere Sub-Rubrik-Codes; wirkt auch ohne `rubrics` | ✅ (dok.) |
| `cantons` | Kantonscode(s), z. B. `cantons=ZH` | ✅ `HR&cantons=ZH` → 422 565 |
| `keyword` | Volltextsuche | ✅ `Informatik` → 21 572; **`Schulinformatik` → 0** |
| `uids` | Publikations-UIDs (nicht Firmen-UID!) | ✅ (dok.) |
| `publicationDate.start` / `.end` | Zeitraumfilter (`YYYY-MM-DD`) | ✅ verengt korrekt |
| `municipalityId` / `municipalityZipCodes` / `municipalityName` | Gemeinde-Filter (BFS-Nr. → wird über «Korrespondenztabelle» zu PLZ, kann unscharf sein) | dok. |
| `pageRequest.page` / `pageRequest.size` | Paginierung; Response spiegelt `pageRequest` + `total` | ✅ |

### Paginierung

Response-Envelope (JSON): `{ "content": [...], "total": <int>,
"pageRequest": { "sortOrders": [], "page": <int>, "size": <int> } }`. Über
`total` und `size` lässt sich die Seitenzahl berechnen. **Empfehlung:** harte
Obergrenze `pageRequest.size ≤ 100` (deckt sich mit `GAZETTE_MAX_LIMIT`).

### Sortierung — funktioniert **nicht** steuerbar

`pageRequest.sortOrders[0].fieldName=publicationDate&…direction=ASC|DESC`
wurde mit HTTP 200 akzeptiert, hatte aber **keinen Effekt**: ASC und DESC
lieferten beide dieselbe (neueste) Publikation. → Sortier-Parameter werden
still ignoriert; **Default-Reihenfolge ist `publicationDate` absteigend
(neueste zuerst)**. Für den MCP-Server heisst das: nicht auf serverseitige
Sortierung verlassen, ggf. clientseitig nachsortieren.

---

## 5. Quirks (nicht verhandelbar für die Implementation)

Beide Quirks sind in `server.py` bereits als Guardrails kodiert und wurden
in dieser Probe erneut bestätigt:

1. **Silent Ignore (unbekannter Parametername → voller Korpus).**
   `…&bogusParam=xyz` → HTTP 200, `total = 2 789 951`. Ein Tippfehler wie
   `uid=` statt `uids=` würde den Filter still verwerfen und **den ganzen
   Korpus** zurückgeben. → Query-Params **ausschliesslich** aus einer
   Allow-List bauen (`ALLOWED_GAZETTE_PARAMS`); zusätzlich Plausibilitäts-
   Guard: gefiltertes Ergebnis > `GAZETTE_IGNORED_FILTER_THRESHOLD`
   (2 000 000) ⇒ `GazetteFilterIgnored` werfen.

2. **Silent Empty (unbekannter Rubrik-*Wert* → 0 Treffer).**
   `rubrics=ZZZ_NOPE` → HTTP 200, `total = 0` (kein Fehler). → Rubrik-/Sub-
   Rubrik-Codes **vor** dem Call gegen die Taxonomie validieren
   (`GazetteInvalidCode`), sonst sieht der Nutzer ein leeres Ergebnis, das wie
   «nichts publiziert» aussieht, obwohl der Code schlicht ungültig war.

> **Metapher fürs CHANGELOG:** Der Amtsblatt-Filter ist wie ein
> Pförtner, der bei einem unbekannten *Ausweis* (Parametername) einfach
> jeden durchwinkt, bei einem unbekannten *Namen auf gültigem Ausweis*
> (Rubrik-Wert) aber niemanden findet.

---

## 6. Rubriken-Taxonomie

`GET /rubrics` liefert die **vollständige** Taxonomie als JSON-Baum:

```json
[{
  "code": "KK",
  "name": { "de": "Konkurse", "fr": "Faillites", "it": "...", "en": "..." },
  "active": true,
  "tenantId": "shab",
  "allowSecondaryTenants": true,
  "subRubrics": [ { "code": "KK01", "name": {…}, "active": true }, … ]
}]
```

- **152 Top-Level-Rubriken, 825 Sub-Rubriken**, mehrsprachig (de/fr/it/en).
- Jede Rubrik trägt `tenantId` (Mandant) und `active`-Flag.
- Sub-Rubriken gibt es **nicht** über einen eigenen Endpoint — sie stecken im
  `subRubrics`-Array jeder Rubrik.

### Kantonale Amtsblätter — im selben Portal

`GET /tenants` → **29 Mandanten** im gleichen Portal:

- **1 × SHAB** (`shab`, Typ `SHAB`) — der Bund.
- **27 × CANTON** — je ein kantonales Amtsblatt (`kabzh`, `kabbe`, `kabti`, …);
  darunter `kabda` = «ePublikation» für Gemeinden/Städte.
- **1 × NEUTRAL** (`neutral`).

Kantonale Publikationen sind also **nicht separat** — dieselbe API, gefiltert
über `rubrics`/`subRubrics` (die kantonale Codes tragen, z. B. `OB-BS`) bzw.
`cantons`. **Aber:** nur **16 der 29 Mandanten** exponieren im `/rubrics`-Baum
eigene Rubrik-Definitionen; die übrigen Kantone (u. a. AG, FR, GE, GL, JU, LU,
NE, UR) tauchen dort (noch) nicht mit eigener Taxonomie auf — ihre
Gazette-Integration ist unvollständig. **Known limitation.**

---

## 7. Rubriken-Mapping-Tabelle (Fokus: Beschaffung · Handelsregister · Konkurse)

### 7a. Öffentliches Beschaffungswesen / Submissionen

Beschaffung ist **keine SHAB-(Bundes-)Rubrik** — es gibt sie ausschliesslich
kantonal, Code-Muster `OB-<Kanton>`. Viele Kantone importieren Submissionen
gar nicht ins Amtsblatt, sondern publizieren sie auf **simap.ch** (die
föderale Beschaffungsplattform), das **nicht** Teil dieses Portals ist.

| Rubrik-Code | Mandant | Kanton | `active` | Bemerkung |
|---|---|---|---|---|
| `OB-AR` | kabar | AR | ✅ aktiv | Sub: Ausschreibung/Wettbewerb/Zuschlag/Freihändig |
| `OB-BS` | kabbs | BS | ✅ aktiv | 3 065 Publikationen all-time |
| `OB-TI` | kabti | TI | ✅ aktiv | inkl. «nicht gemäss GATT/WTO» |
| `OB-ZG` | kabzg | ZG | ✅ aktiv | «bis Ende Februar 2024 via simap.ch importiert» |
| `OB-BL` | kabbl | BL | ❌ **inaktiv** | «über Simap importiert (INAKTIV)» |
| `OB-VS` | kabvs | VS | ❌ **inaktiv** | «bis Ende 2023 über simap.ch importiert» |
| `AR-NW › AR-NW40` | kabnw | NW | ✅ | «Öffentliche Beschaffung (nicht über simap.ch importiert)» |
| `AR-OW › AR-OW40` | kabow | OW | ✅ | dito |
| `AR-VS › AR-VS40` | kabvs | VS | ✅ | «Marchés publics (non importés via simap.ch)» |
| **`OB-ZH`** | **—** | **ZH** | **existiert nicht** | **Zürich hat keine Beschaffungs-Rubrik im Portal** |

> **Kernbefund Beschaffung:** Über amtsblattportal.ch sind Submissionen nur für
> **4 aktive Kantone (AR, BS, TI, ZG)** plus einige Nicht-simap-Sub-Rubriken
> (NW, OW, VS) zuverlässig abrufbar. Für die meisten Kantone — **inklusive
> Zürich** — laufen Ausschreibungen über **simap.ch** und sind hier **nicht**
> enthalten.

### 7b. Handelsregister (Firmen-bezogen → Zefix-Join)

| Rubrik | Mandant | Bedeutung | Sub-Rubriken |
|---|---|---|---|
| `HR` | shab | Handelsregistereintragungen | `HR01`, `HR02`, `HR03` |
| `BH` | shab | Bekanntmachungen nach Handelsregisterverordnung | `BH00`–`BH07` |

`HR`-Publikationen tragen im **Einzelabruf** die Firmen-UID (`<uid>CHE-…</uid>`)
→ zentraler Anknüpfungspunkt an Zefix (siehe Abschnitt 9).

### 7c. Konkurse / Insolvenz (Firmen-bezogen)

| Rubrik | Mandant | Bedeutung | Sub-Rubriken |
|---|---|---|---|
| `KK` | shab | Konkurse | `KK01`–`KK12` |
| `NA` | shab | Nachlassverfahren | `NA01`–`NA12` |
| `SB` | shab | Schuldbetreibungen | `SB01`–`SB07` |
| `LS` | shab | Liquidationsschuldenrufe | `LS01`–`LS08` |
| `SR` | shab | Weitere gesellschaftsrechtliche Schuldenrufe | `SR01`–`SR06` |

Die vollständige Top-Level-Liste aller 152 Rubriken steht in **Anhang A**.

---

## 8. Sortierung, Volltext, Zeitraum — Zusammenfassung

| Fähigkeit | Verfügbar? | Detail |
|---|---|---|
| Volltextsuche | ✅ | `keyword=`; token-basiert — `Schulinformatik` (0) vs. `Informatik` (21 572) |
| Zeitraumfilter | ✅ | `publicationDate.start` / `.end`, `YYYY-MM-DD` |
| Rubrik-/Kanton-Filter | ✅ | `rubrics`, `subRubrics`, `cantons` |
| Paginierung | ✅ | `pageRequest.page` / `.size`, `total` im Envelope |
| Sortierung | ⚠️ **nein** | Parameter still ignoriert; Default = Datum absteigend |

---

## 9. Zefix-Join-Pfad (UID) — Verknüpfbarkeit mit den bestehenden Tools

Ziel gemäss Auftrag: eine SHAB-Publikation über die **UID** an einen
Zefix-Datensatz anschliessen. Empirisch bestätigter Pfad:

```
Zefix-Tool (uid=CHE-xxx.xxx.xxx)
        │  z. B. company_details_by_uid / search_company
        ▼
  UID  ──────────────────────────────────────────────┐
                                                      │
Amtsblatt-Suche:  GET /publications?                  │
     publicationStates=PUBLISHED&rubrics=HR|KK|…      │
        │  Bulk-Liste (meta.uid ist hier NULL!)       │
        ▼                                             │
  pro Treffer  meta.id                                │
        │                                             │
        ▼                                             │
Einzelabruf:  GET /publications/{id}/xml              │
        │  enthält <uid>CHE-…</uid> + <name> + Inhalt │
        ▼                                             │
  Match gegen Zefix-UID  ◄───────────────────────────┘
```

**Wichtige Nuance für die Implementation:** Die Firmen-UID steht **nicht** in
der Bulk-Liste (`meta.uid = null`), sondern erst im **Einzelabruf**
(`GET /publications/{id}` → `meta.uid` als Array, bzw.
`GET /publications/{id}/xml` → `<uid>` mit vollem Inhalt). Ein UID-getriebener
Join erfordert daher entweder (a) Volltext-`keyword`-Suche nach der UID-
Zeichenkette, oder (b) Rubrik-gefilterte Liste + Einzelabruf-Fan-out. Das
Verhalten von `keyword=CHE-…` ist in Phase 2 zu proben.

Dieser Join-Pfad ist in Phase 2 in der README unter «Zefix ↔ Amtsblatt»
festzuhalten.

---

## 10. Anchor Demo Query — Reality-Check

> «Welche öffentlichen Ausschreibungen im Bereich Schulinformatik wurden im
> Kanton Zürich in den letzten drei Monaten publiziert?»

**Diese Query ist über amtsblattportal.ch nicht beantwortbar — aus zwei
unabhängigen Gründen, beide live verifiziert:**

1. **Kein `OB-ZH`.** Zürich führt im Portal **keine** Beschaffungs-Rubrik
   (Abschnitt 7a). ZH-Ausschreibungen laufen über **simap.ch**, eine separate
   Plattform ausserhalb dieses Portals.
2. **`keyword=Schulinformatik` → 0 Treffer** im **gesamten** Korpus (nicht nur
   ZH). Selbst `OB-BS&keyword=Informatik` in den letzten 3 Monaten → 0.

**Konsequenz für Phase 2 — die Anchor Demo Query muss neu gefasst werden.**
Ehrliche, tatsächlich beantwortbare Varianten:

- **A (Beschaffung, machbarer Kanton):** «Welche öffentlichen Ausschreibungen
  im Bereich Informatik wurden im Kanton **Basel-Stadt** (`OB-BS`) in den
  letzten drei Monaten publiziert?»
- **B (portfolio-stärkste Query, nutzt den Zefix-Join):** «Zeige alle
  SHAB-Handelsregister- und Konkurs-Publikationen zur Firma mit UID
  `CHE-xxx.xxx.xxx` (aus Zefix) — was wurde zuletzt über sie publiziert?»
  → Das ist die Query, die die **Komplementarität** zu den Zefix-/UID-Tools
  zeigt und den in Abschnitt 9 beschriebenen Join demonstriert.

Variante B wird als neue Anchor Demo Query empfohlen, weil sie genau die
Verknüpfbarkeit belegt, die dieser Server dem Portfolio hinzufügt.

---

## 11. Empfehlung für Phase 2 (zur Freigabe)

**Architektur-Entscheid (Vorschlag): Architektur A — Live-API-only.** Die
nötigen Endpoints (`/publications`, `/publications/{id}/xml`, `/rubrics`,
`/tenants`) funktionieren stabil und ohne Auth; die Quelle ist «für den
produktiven Einsatz ausgelegt». Ein Bulk-Dump ist für den Anwendungsfall
(gezielte, gefilterte Abfragen) nicht erforderlich. Resilienz-Defaults
(Retry mit Backoff, Pydantic-Envelope mit `source`/`provenance`, Allow-List
gegen Silent Ignore, Code-Validierung gegen Silent Empty) sind im bestehenden
`gazette_*`-Code bereits umgesetzt.

**Tool-Skizze** (abgestimmt auf die bestehenden Zefix-/UID-Tools; Details in
Phase 2 nach Freigabe):

| Vorgeschlagenes Tool | Realisierbar? | Anmerkung aus der Probe |
|---|---|---|
| `list_gazette_rubrics()` | ✅ direkt | aus `/rubrics`; nach Mandant/Kanton filterbar |
| `search_gazette_publications(rubric, keyword, canton, date_from, date_to)` | ✅ | `cantons`, `rubrics`, `keyword`, `publicationDate.*`; Sortierung clientseitig |
| `get_publication(publication_id)` | ✅ | **XML-Variante** verwenden (JSON-Einzel liefert keinen Inhalt) |
| `search_procurement_notices(cpv_or_keyword, canton, date_from)` | ⚠️ eingeschränkt | nur Kantone AR/BS/TI/ZG (aktiv) + NW/OW/VS-Subrubriken; **kein ZH**; **kein CPV** — Amtsblatt kennt keine CPV-Codes, nur Rubriken + Freitext |

> **Hinweis zu CPV:** Die Amtsblatt-API bietet **keine** CPV-Klassifizierung.
> `search_procurement_notices` kann nur über `keyword` (Freitext) + `OB-*`-
> Rubrik + Kanton + Datum arbeiten. Ein CPV-Parameter wäre irreführend und
> sollte entweder entfallen oder klar als reine Keyword-Übersetzung
> dokumentiert werden.

**Phase 1 endet hier.** Keine Tool-Implementation ohne explizite Freigabe.

---

## Anhang A — Vollständige Top-Level-Rubrikenliste (152 Rubriken, 16 Mandanten mit eigener Taxonomie)

> Quelle: `GET /rubrics`, live abgerufen 2026-07-19. Zahl in Klammern =
> Anzahl Sub-Rubriken. `[INAKTIV]` = `active: false`. Mandanten ohne eigene
> Rubrik-Definitionen (u. a. AG, AI, FR, GE, GL, JU, LU, NE, UR) sind hier
> nicht aufgeführt.

**shab** (16 Rubriken — Bund / SHAB):
- `AB` — Arbeit (8) · `AW` — Abhandengekommene Wertpapiere und andere Titel (3) · `AZ` — Anzeigen (2) · `BB` — Weitere Register und Bekanntmachungen Bund (6) · `BH` — Bekanntmachungen nach Handelsregisterverordnung (8) · `EK` — Edelmetallkontrolle (6) · `ES` — Erbschaft (6) · `FM` — Finanzmarkt (12) · `HR` — Handelsregistereintragungen (3) · `KK` — Konkurse (12) · `LS` — Liquidationsschuldenrufe (8) · `NA` — Nachlassverfahren (12) · `SB` — Schuldbetreibungen (7) · `SR` — Weitere gesellschaftsrechtliche Schuldenrufe (6) · `UP` — Mitteilungen an Gesellschafter (6) · `UV` — Gerichtliche Entscheide und Vorladungen im SHAB (5)

**kabar** (AR, 12): `AI-AR` Anzeigen und Inserate (3) · `BP-AR` Baugesuche (1) · `FZ-AR` Familie und Zivilstandswesen (1) · `GB-AR` Kant. gerichtliche Entscheide (9) · `KA-AR` Weitere kantonale Bekanntmachungen (1) · `KO-AR` Weitere kommunale Bekanntmachungen (4) · **`OB-AR` Öffentliches Beschaffungswesen (10)** · `RP-AR` Raumplanung (3) · `RS-AR` Beschlüsse und politische Rechte (12) · `SW-AR` Steuerwesen (4) · `TE-AR` Kommunale erbschaftsamtliche Bekanntmachungen (4) · `VE-AR` Umwelt, Verkehr und Energie (6)

**kabbe** (BE, 12): `BP-BE` Baugesuche (2) · `BV-BE` Bürgerrecht und Aufenthalt (2) · `EG-BE` Entsendegesetz (4) · `FZ-BE` Familie und Zivilstandswesen (1) · `GB-BE` Kant. gerichtliche Entscheide (8) · `KA-BE` Weitere kantonale Bekanntmachungen (3) · `KO-BE` Weitere kommunale Bekanntmachungen (3) · `RP-BE` Raumplanung (4) · `RS-BE` Beschlüsse und politische Rechte (7) · `SJ-BE` Staats- und Jugendanwaltschaft (2) · `TE-BE` Kant. erbschaftsamtliche Bekanntmachungen (9) · `VE-BE` Umwelt, Verkehr und Energie (8)

**kabbl** (BL, 11): `BP-BL` Baugesuche (1) · `GB-BL` Gerichtliche Bekanntmachungen (3) · `GR-BL` Grundbuch (1) · `KW-BL` Kirchenwesen (1) · **`OB-BL` Öffentliches Beschaffungswesen [INAKTIV] (6)** · `PL-BL` Politische Rechte (4) · `RP-BL` Raumplanung (2) · `RS-BL` Landrat und Regierungsrat (2) · `SW-BL` Steuerwesen (2) · `TE-BL` Kant. erbschaftsamtliche Bekanntmachungen (5) · `WB-BL` Allgemeine Bekanntmachungen (12)

**kabbs** (BS, 18): `AI-BS` Kantonale Anzeigen und Inserate (3) · `BE-BS` Bewilligungen/Betriebsbewilligungen (10) · `BP-BS` Baupublikationen und Nutzungsgesuche (3) · `BV-BS` Bürgerrecht und Aufenthalt (2) · `BW-BS` Bildungswesen (4) · `FZ-BS` Familie und Zivilstandswesen (2) · `GB-BS` Kant. gerichtliche Entscheide (9) · `GR-BS` Grundbuch (2) · `KA-BS` Weitere kantonale Bekanntmachungen (6) · `KO-BS` Weitere kommunale Bekanntmachungen (3) · `KW-BS` Kirchenwesen (1) · **`OB-BS` Öffentliches Beschaffungswesen (8)** · `PR-BS` Politische Rechte (2) · `RP-BS` Raumplanung (2) · `RS-BS` Beschlüsse und Erlasse (10) · `SW-BS` Steuerwesen (5) · `TE-BS` Kant. erbschaftsamtliche Bekanntmachungen (5) · `VE-BS` Umwelt, Verkehr und Energie (9)

**kabda** (DA/ePublikation, 4): `AM-DA` ePublikation für Gemeinden und Städte (26) · `OR-DA` Bekanntmachungen öff.-rechtl. Körperschaften [INAKTIV] (5) · `RK-DA` Rechtssammlung öff.-rechtl. Körperschaften [INAKTIV] (1) · `RS-DA` Kommunale Rechtssammlung [INAKTIV] (14)

**kabgr** (GR, 1): `AA-GR` Meldungskatalog (8)

**kabnw** (NW, 7): `AL-NW` Allgemeine amtliche Bekanntmachungen und Anzeigen (2) · `AR-NW` Wirtschaft, Arbeit und Bildung (8, inkl. **`AR-NW40` Öffentliche Beschaffung nicht simap**) · `BA-NW` Bau, Raum, Verkehr, Umwelt und Energie (12) · `BU-NW` Bürgerrecht, Steuer- und Zivilstandswesen (6) · `GE-NW` Gerichtliche Entscheide (5) · `RE-NW` Rechtsetzung und politische Rechte (8) · `VA-NW` Verschollenheit, Ableben und Erbschaft (9)

**kabow** (OW, 6): `AL-OW` Allgemeine Bekanntmachungen und Anzeigen (5) · `AR-OW` Wirtschaft und Arbeit (5, inkl. **`AR-OW40` Öffentliche Beschaffung nicht simap**) · `BA-OW` Bau, Raum, Verkehr, Umwelt und Energie (10) · `BU-OW` Steuer- und Zivilstandswesen (2) · `GE-OW` Gerichtliche Bekanntmachungen (6) · `RE-OW` Behörden, politische Rechte und Rechtsetzung (7)

**kabsh** (SH, 7): `AL-SH` Allgemeine amtliche Bekanntmachungen (1) · `AR-SH` Wirtschaft, Arbeit und Bildung (4) · `BA-SH` Bau, Raum, Verkehr und Energie (10, inkl. `BA-SH40` Öffentliche Ausschreibung Landwirtschaft) · `BU-SH` Bürgerrecht, Steuer- und Zivilstandswesen (2) · `GE-SH` Gerichtliche Entscheide (7) · `RE-SH` Beschlüsse und politische Rechte (6) · `VA-SH` Ableben und Erbschaft (5)

**kabso** (SO, 7): `AL-SO` Allgemeine amtliche Bekanntmachungen und Anzeigen (3) · `AR-SO` Wirtschaft, Arbeit und Bildung (5) · `BA-SO` Bau, Raum, Verkehr und Energie (9) · `BU-SO` Bürgerrecht, Steuer- und Zivilstandswesen (8) · `GE-SO` Gerichtliche Entscheide (5) · `RE-SO` Behörden und politische Rechte (8) · `VA-SO` Verschollenheit, Ableben und Erbschaft (9)

**kabsz** (SZ, 7): `AL-SZ` Allgemeine amtliche Bekanntmachungen und Anzeigen (3) · `AR-SZ` Wirtschaft, Arbeit und Bildung (5) · `BA-SZ` Bau, Raum, Verkehr und Energie (10) · `BU-SZ` Bürgerrecht, Steuer- und Zivilstandswesen (4) · `GE-SZ` Gerichtliche Entscheide (4) · `RE-SZ` Beschlüsse und politische Rechte (11) · `VA-SZ` Verschollenheit, Ableben und Erbschaft (3)

**kabti** (TI, 12): `AI-TI` Kantonale Anzeigen und Inserate (2) · `BP-TI` Baugesuch (2) · `BW-TI` Bildungswesen (5) · `GB-TI` Kant. gerichtliche Entscheide (8) · `KA-TI` Weitere kantonale Bekanntmachungen (3) · `KO-TI` Weitere kommunale Bekanntmachungen (4) · **`OB-TI` Öffentliches Beschaffungswesen (9)** · `PR-TI` Gesetze und Politische Rechte (8) · `RP-TI` Raumplanung (4) · `SW-TI` Steuerwesen (5) · `TE-TI` Todesfälle und Erbschaft (7) · `VE-TI` Umwelt, Verkehr und Energie (8)

**kabvs** (VS, 8): `AL-VS` Allgemeine amtliche Bekanntmachungen und Anzeigen (3) · `AR-VS` Wirtschaft, Arbeit und Bildung (8, inkl. **`AR-VS40` Marchés publics non simap**) · `BA-VS` Bau, Raum, Verkehr und Energie (11) · `BU-VS` Bürgerrecht, Steuer- und Zivilstandswesen (7) · `GE-VS` Gerichtliche Entscheide (5) · **`OB-VS` Öffentliches Beschaffungswesen [INAKTIV] (5)** · `RE-VS` Behörden und politische Rechte (6) · `VA-VS` Verschollenheit, Ableben und Erbschaft (6)

**kabzg** (ZG, 12): `BE-ZG` Bewilligungen/Betriebsbewilligungen (1) · `BP-ZG` Baugesuche (1) · `BW-ZG` Bildungswesen (1) · `GB-ZG` Gerichtliche Entscheide (7) · `KA-ZG` Weitere kantonale Bekanntmachungen (2) · `KO-ZG` Weitere kommunale Bekanntmachungen (5) · **`OB-ZG` Öffentliches Beschaffungswesen (5)** · `RP-ZG` Raumplanung (2) · `RS-ZG` Beschlüsse und politische Rechte (13) · `SW-ZG` Steuerwesen (1) · `TE-ZG` Bekanntmachungen zu Erbschaften (4) · `VE-ZG` Umwelt, Verkehr und Energie (7)

**kabzh** (ZH, 12): `AI-ZH` Anzeigen und Inserate (3) · `BP-ZH` Kommunale Bauprojekte (1) · `BV-ZH` Bürgerrecht und Aufenthalt (2) · `FZ-ZH` Familie und Zivilstandswesen (3) · `GB-ZH` Kant. gerichtliche Entscheide (7) · `KA-ZH` Weitere kantonale Bekanntmachungen (2) · `KO-ZH` Weitere kommunale Bekanntmachungen (6) · `RP-ZH` Raumplanung (7) · `RS-ZH` Rechtsetzung und politische Rechte (10) · `SW-ZH` Steuerwesen (3) · `TE-ZH` Kant. Testamentseröffnungen und Erbenaufrufe (2) · `VE-ZH` Umwelt, Verkehr und Energie (7) — **⚠️ kein `OB-ZH` / keine Beschaffungsrubrik**

---

## Anhang B — Reproduzierbare Probe-Calls

```bash
B="https://amtsblattportal.ch/api/v1"

# JSON-Liste (Default-Format via Accept-Header)
curl -sL -H "Accept: application/json" \
  "$B/publications?publicationStates=PUBLISHED&rubrics=KK&pageRequest.size=2"

# Vollständige Rubriken-Taxonomie
curl -sL "$B/rubrics"        # 152 Rubriken / 825 Sub-Rubriken
curl -sL "$B/tenants"        # 29 Mandanten (27 CANTON, 1 SHAB, 1 NEUTRAL)

# Beschaffung Basel-Stadt, letzte 3 Monate
curl -sL -H "Accept: application/json" \
  "$B/publications?publicationStates=PUBLISHED&rubrics=OB-BS&publicationDate.start=2026-04-19&publicationDate.end=2026-07-19"

# Zwei-Schritt: Einzelabruf mit Firmen-UID (Zefix-Join)
curl -sL "$B/publications/{publicationId}/xml"   # enthält <uid>CHE-…</uid>

# Quirk-Nachweise
curl -sL -H "Accept: application/json" "$B/publications?publicationStates=PUBLISHED&bogusParam=x&pageRequest.size=1"   # total=2.79M (Silent Ignore)
curl -sL -H "Accept: application/json" "$B/publications?publicationStates=PUBLISHED&rubrics=ZZZ&pageRequest.size=1"      # total=0    (Silent Empty)
```
