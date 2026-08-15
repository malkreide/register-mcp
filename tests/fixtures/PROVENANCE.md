# Herkunft der Fixtures

**Erzeugt von `scripts/record_fixtures.py`. Nicht von Hand pflegen.**

Aufgezeichnet am **2026-08-15** von `https://amtsblattportal.ch/api/v1`.

Ohne Datum ist «aufgezeichnet» nach zwei Jahren von «ausgedacht» nicht
mehr zu unterscheiden — die Datei sieht gleich aus.

## Redaktion — was diese Fixtures NICHT belegen

Das Amtsblatt fuehrt `SB` (Schuldbetreibungen) und `LS` (Schuldenrufe);
der Freitext einer Publikation nennt natuerliche Personen mit Adresse.
Eine woertliche Antwort in einem **oeffentlichen** Repo waere eine
Republikation dieser Daten. Deshalb ist die **Struktur** echt — Schluessel,
Verschachtelung, Typen und die Codes, auf die der Server verzweigt —,
und die **Werte** der folgenden Felder sind ersetzt:

- `meta.title`
- `content`

Ersatzwert: `[redigiert — siehe PROVENANCE.md]`. Alles, was hier nicht steht, ist woertlich
aufgezeichnet. Eine Fixture, die stillschweigend weniger belegt, als sie
aussieht, waere genau der Fehler, gegen den diese Aufzeichnung angeht.

## `gazette_rubrics.json`

- **Quelle:** `https://amtsblattportal.ch/api/v1/rubrics`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** unveraendert, die 7 von 152 Rubriken, gegen die die Tests validieren; keine Personendaten (reine Codeliste)
- **Groesse:** 98788 B
- **SHA-256:** `af48b0e337fd11b7e50359b0e6e1938ba6232bb0ecd7c14bfa2adb7c30541473`

## `gazette_search.json`

- **Quelle:** `https://amtsblattportal.ch/api/v1/publications?publicationStates=PUBLISHED&rubrics=HR&pageRequest.size=2`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** Huelle und Struktur unveraendert; die Werte unter meta.title, content redigiert (Personendaten). `total` ist der echte Bestandswert von diesem Tag
- **Groesse:** 3379 B
- **SHA-256:** `aa469df8c4533c3321979f9bd76b1002ab38531836c90af97d36461f3c72e5d1`

## `gazette_corpus_total.json`

- **Quelle:** `https://amtsblattportal.ch/api/v1/publications (ungefiltert, size=1)`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** nur der Gesamtbestand — die Zahl, gegen die die Quirk-1-Pruefung vergleicht; sie waechst taeglich und gehoert deshalb aufgezeichnet
- **Groesse:** 23 B
- **SHA-256:** `f75f3680a27b1abfd5cd8cc9891a828c2a7a4472d887bc90d9f91523441e68c4`

## `zefix_legal_forms.json`

- **Quelle:** `https://www.zefix.admin.ch/ZefixREST/api/v1/legalForm`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig, alle 19 Rechtsformen
- **Groesse:** 6180 B
- **SHA-256:** `3745c9b72a49c02206f24bee2b50cf4be24876a846605384a0e82d0af9cfd8b8`

## `zefix_search.json`

- **Quelle:** `https://www.zefix.admin.ch/ZefixREST/api/v1/firm/search.json`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig, Firmensuche 'Migros' — 35 Treffer aus 16 verschiedenen Gemeinden. Die Streuung ist die Auswahlregel: An ihr haengt, dass sich `legalSeatId` ueber `bfsId` aufloest und nicht ueber `id`
- **Groesse:** 19629 B
- **SHA-256:** `e1f9a35377d9d932d235211d737c43a7b79181a5b8719c489a8190971e3c073d`

## `zefix_search_by_uid.json`

- **Quelle:** `https://www.zefix.admin.ch/ZefixREST/api/v1/firm/search.json`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig, Suche nach CHE-238.945.329 — die UID im Feld `name`, `searchType: CONTAINS`. 1 Treffer. Auswahlregel ist der Kontrast: Derselbe Endpunkt beantwortet ein Payload mit `uid`-Feld am selben Tag mit HTTP 400. Die Fixture belegt damit die Form, die traegt, und das Skript prueft die, die nicht traegt
- **Groesse:** 664 B
- **SHA-256:** `2dea1f768e2720327e58b43d193a23527aab90d2fe8fad373995aa6cac07edf3`

## `zefix_firm_detail.json`

- **Quelle:** `https://www.zefix.admin.ch/ZefixREST/api/v1/firm/1287765.json`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig, Firma 1287765 (Anlagestiftung der Migros-Pensionskasse), 16 SHAB-Publikationen. **Redigiert:** Das Feld `shabPub[].message` nennt eingetragene Personen mit Wohnort; der Text ist ersetzt, die Struktur bleibt
- **Groesse:** 10365 B
- **SHA-256:** `0104b53bac2edab58da0b3bb2504f9866a249305feee4834e818ae43385b9c87`

## `zefix_communities.json`

- **Quelle:** `https://www.zefix.admin.ch/ZefixREST/api/v1/community`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** 23 von 2112 Gemeinden: zu jeder in der Suche vorkommenden `legalSeatId` die Gemeinde mit dieser `bfsId` UND die mit dieser `id`. Nach Merkmal ausgewaehlt, nicht nach Position — nur so stehen beide Kandidaten einer Verwechslung nebeneinander in der Datei
- **Groesse:** 4051 B
- **SHA-256:** `c5d287ba202c21db583ea938af9ad9a780fb217af4921d5e58f5c7dbc050bd9f`

## `zefix_no_result.json`

- **Quelle:** `https://www.zefix.admin.ch/ZefixREST/api/v1/firm/search.json (Name ohne Treffer)`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** Statuscode UND Rumpf, weil beides zusammen den Befund ausmacht: Die Quelle antwortet mit **404**, nicht mit 200 — der freundliche Zweig fuer «keine Ergebnisse» war damit unerreichbar
- **Groesse:** 265 B
- **SHA-256:** `714d9b0c25fc1075a9a56da32587d4a0a34b846ef8fe09f25051f345e65021ca`
