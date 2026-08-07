# Herkunft der Fixtures

**Erzeugt von `scripts/record_fixtures.py`. Nicht von Hand pflegen.**

Aufgezeichnet am **2026-08-07** von `https://amtsblattportal.ch/api/v1`.

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

## NICHT aufgezeichnet

### `zefix_*.json`

- **Quelle:** `https://www.zefix.admin.ch/ZefixPublicREST/api/v1/company/search`
- **Grund:** ZEFIX_USER/ZEFIX_PASSWORD nicht gesetzt — die API antwortet ohne sie mit HTTP 401. NICHT aufgezeichnet.

Diese Payloads stehen weiterhin als Literale im Testmodul. Sie sind
damit **ausgedacht** und tragen kein Datum — das ist der Ist-Zustand
und keine Nachlaessigkeit dieses Laufs. Wer Zugangsdaten hat, setzt
`ZEFIX_USER`/`ZEFIX_PASSWORD` und laesst das Skript erneut laufen.

## `gazette_rubrics.json`

- **Quelle:** `https://amtsblattportal.ch/api/v1/rubrics`
- **Aufgezeichnet:** 2026-08-07
- **Auswahl:** unveraendert, die 7 von 152 Rubriken, gegen die die Tests validieren; keine Personendaten (reine Codeliste)
- **Groesse:** 98788 B
- **SHA-256:** `af48b0e337fd11b7e50359b0e6e1938ba6232bb0ecd7c14bfa2adb7c30541473`

## `gazette_search.json`

- **Quelle:** `https://amtsblattportal.ch/api/v1/publications?publicationStates=PUBLISHED&rubrics=HR&pageRequest.size=2`
- **Aufgezeichnet:** 2026-08-07
- **Auswahl:** Huelle und Struktur unveraendert; die Werte unter meta.title, content redigiert (Personendaten). `total` ist der echte Bestandswert von diesem Tag
- **Groesse:** 3637 B
- **SHA-256:** `717ff2333a23e9056bc2eb06b637562465d3fc3ca23f109094ac8d5087950719`

## `gazette_corpus_total.json`

- **Quelle:** `https://amtsblattportal.ch/api/v1/publications (ungefiltert, size=1)`
- **Aufgezeichnet:** 2026-08-07
- **Auswahl:** nur der Gesamtbestand — die Zahl, gegen die die Quirk-1-Pruefung vergleicht; sie waechst taeglich und gehoert deshalb aufgezeichnet
- **Groesse:** 23 B
- **SHA-256:** `5d6b1bb3be29d30557454be5d744c097d572bcc9febc5cf15b4b7464ad6711c8`
