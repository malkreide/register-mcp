# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Hinzugefuegt

- **Frischehinweise auf `tools/list` und `server/discover`** (SEP-2549, Spec
  `2026-07-28`): `ttlMs` 300000, `cacheScope` `public`. Das SDK setzt beides von
  sich aus auf «sofort veraltet, nie geteilt» — wer nichts übergibt, verhält
  sich also nicht neutral, sondern lässt jeden Client bei jeder Verbindung neu
  auflisten, für eine Liste, die beim Import feststeht und für jeden Aufrufer
  dieselbe ist. `prompts/list` und `resources/list` bleiben ungesetzt: dieser
  Server registriert weder das eine noch das andere.


## [0.6.1] - 2026-08-15

Ein Nachtrag zu 0.6.0, gefunden beim End-to-End-Lauf gegen das
veroeffentlichte Wheel. Kein Verhalten der Werkzeuge aendert sich; wer 0.6.0
laufen hat, verpasst nichts ausser der Versionsangabe im Handshake.

### Behoben — der Server meldete im MCP-Handshake eine leere Version

`MCPServer` nimmt ein `version=`-Argument; der Server uebergab keins, und der
Vorgabewert ist die leere Zeichenkette. Gemessen am 2026-08-15 gegen das von
PyPI installierte Wheel 0.6.0:

```
Implementation(name='register_mcp', title=None, version='', …)
```

Das Paket kannte seine Version die ganze Zeit — es sagte sie nur ueber MCP
nicht. Ein Client, der Serverversionen anzeigt oder protokolliert, sah dort
nichts; ein Fehlerbericht «register_mcp, Version unbekannt» waere die Folge
gewesen. Jetzt `version=__version__`, also aus den Paket-Metadaten statt aus
einem Literal.

Gefunden hat das kein Test, sondern der End-to-End-Lauf gegen das
veroeffentlichte Paket: Handshake ueber stdio gegen den Konsolen-Einstiegspunkt
aus dem Wheel. Die Zusicherung steht jetzt in der Suite.

## [0.6.0] - 2026-08-15

Drei ausgelieferte Fehler derselben Sorte: keine Abstuerze, sondern
vollstaendig formatierte Antworten, die das Gegenteil dessen sagten, was in der
Quelle steht. Gefunden hat sie nicht die Unit-Suite — die war durchgehend
gruen —, sondern der erste Lauf der erweiterten Live-Tests und zwei Reviews.
Der Rest dieses Releases ist die Werkzeugkette, die so etwas kuenftig frueher
sichtbar macht.

Fuer Nutzende aendert sich Verhalten: `zefix_get_company_by_uid` antwortet ohne
exakten Treffer nicht mehr mit der naechstbesten Firma, und
`zefix_verify_company` beantwortet eine trefferlose Namenssuche nicht mehr mit
einer Meldung ueber EHRAID und UID.

### Behoben — zwei Antworten, die «nicht gefunden» sagten, obwohl es etwas zu finden gab

**1. `zefix_verify_company` antwortete auf eine Namenssuche mit einer
UID-Meldung.** Das Werkzeug lief mit rohem `raise_for_status()` an
`_zefix_post_search` vorbei. Zefix beantwortet eine trefferlose Suche mit HTTP
404, und die generische Behandlung machte daraus:

```
zefix_verify_company(name="Zzzqqxyznichtexistent AG")
→ Fehler 404: Eintrag nicht gefunden. Bitte EHRAID oder UID prüfen.
```

Auf eine Suche hin, bei der weder EHRAID noch UID vorkamen. Der freundliche
Zweig darunter — «Nicht im Handelsregister gefunden», mit dem Hinweis auf
Einzelunternehmen unter Schwellenwert, Behoerden und Vereine ohne Eintrag — war
unerreichbarer Code. Er wird jetzt erreicht.

**2. `docs/demo/demo.py verify` erklaerte geloeschte Firmen fuer nicht
existent.** Das Kommando fragte ohne `activeOnly: False` und bekam damit nur
aktive Eintraege. Am 2026-08-15 an der Quelle geprueft:

```
demo.py verify "Foreign Pilots Association in Swissair (F.P.A.S.)"
vorher  → ❌ Nicht im Handelsregister gefunden.
nachher → • Foreign Pilots Association … | Verein | Kloten | Status: GELOESCHT
```

Das Werkzeug zeigte den GELOESCHT-Eintrag die ganze Zeit; nur die Demo nicht.
Und seit dem 404-Zweig sah der Irrtum nicht mehr nach Fehler aus, sondern nach
Auskunft — fuer ein Kommando namens «verify» die gefaehrlichere Haelfte der
Antwort.

Beide Faelle sind dieselbe Sorte: kein Absturz, keine Fehlermeldung, sondern
eine vollstaendig formatierte Antwort, die das Gegenteil dessen sagt, was in
der Quelle steht.

Aus derselben Korrektur mitgekommen, beide nur in der Demo: `_uid_fmt` gibt
jetzt einen Gedankenstrich aus statt der Leerzeichenkette, die Zefix als «keine
UID» liefert (`uid: '            '`, `uidFormatted: null`) — sichtbar wurde das
erst, als geloeschte Firmen ueberhaupt in die Ausgabe kamen. Und `cmd_search`
nennt nur noch die Trefferzahl: `maxOffset` ist keine Treffermenge (ein
Treffer, `maxOffset` 875768; bei der UID-Suche `null`, die Zeile las sich
«von ca. None»).

### Behoben — `docs/demo/demo.py` war gegen die Quelle unbenutzbar

Das Skript hinter der Terminal-Aufnahme, also das, was jede Leserin der README
als Erstes ausfuehrt. Drei Fehler, jeder einzeln ausreichend:

- **`uid` sendete ein Payload, das Zefix mit HTTP 400 quittiert.**
  `firm/search.json` kennt kein `uid`-Feld; die UID wird als `name` gesucht. Das
  Kommando lief damit in einen Traceback, nicht in eine Antwort.
- **Alle drei Kommandos endeten bei jeder trefferlosen Suche im Traceback.**
  Zefix antwortet darauf mit HTTP 404, `raise_for_status()` warf, und die
  «nicht gefunden»-Zweige der Kommandos waren unerreichbarer Code.
- **Die dokumentierte Beispiel-UID gab es nicht.** `CHE-109.741.634` liefert bei
  Zefix NORESULT; der Lehrmittelverlag Zuerich AG hat `CHE-404.020.972`,
  SHAB-Datum 2023-07-27. Die falsche Nummer stand in `demo.py`, in
  `docs/demo/README.md`, in `demo.tape` und im Beispieldialog beider READMEs,
  dort zusammen mit einem falschen SHAB-Datum.

Ausserdem raus: derselbe Rueckfall auf `firms[0]`, der auch im Werkzeug stand.
Aufgefallen ist er hier zuerst, beim ersten Lauf der neuen Live-Tests.

### Hinzugefuegt — was bisher niemand nachpruefen konnte

- **`tests/test_demo.py`** — fuer `demo.py` gab es keine Tests, und genau
  deshalb fielen die Fehler oben erst von Hand auf. Jetzt 13 Unit-Tests gegen
  aufgezeichnete Antworten plus drei Live-Tests in der woechentlichen Suite.
- **`tests/fixtures/zefix_search_by_uid.json`** — die UID-Suche mit dem Payload,
  das Server und Demo schicken. Auswahlregel ist der Kontrast: Das
  Aufzeichnungsskript prueft im selben Lauf, dass derselbe Endpunkt ein Payload
  mit `uid`-Feld mit 400 beantwortet, und bricht ab, wenn das nicht mehr gilt.
- **`tests/test_check_version_sync.py` und `tests/test_precommit_config.py`** —
  beide Gate-Skripte liefen bisher ohne eigenen Test.
- **ruff-Pin-Abgleich in `check_version_sync.py`.** Der Pin steht an drei
  Stellen, und keine merkte, wenn eine andere abwich. Fehlt er ueberall, ist die
  Menge `{None}` — die Stellen waeren dann «einig», und der Check haette
  Synchronitaet gemeldet, ohne je etwas verglichen zu haben. Auch dieser Fall
  ist geprueft.

### Geaendert — die Werkzeugkette prueft jetzt, was sie vorher nur behauptete

- **ruff exakt gepinnt statt als Spanne.** `pyproject.toml [dev]` stand auf
  `>=0.15.22,<0.17`, `uv.lock` loeste 0.16.2 auf, die CI linted mit 0.16.1 — ein
  lokal gruenes `ruff check` war damit kein Beleg fuer das Gate.
- **`.pre-commit-config.yaml` angelegt**, mit demselben Pin. Der `ruff-format`-
  Hook fuehrt `markdown` in `types_or`: Ohne das erreicht Markdown den Hook nie,
  waehrend die CI die Python-Bloecke *in* `docs/*.md` sehr wohl formatiert.
- **`docs/` im Gate-Umfang.** `docs/demo/demo.py` war die einzige Python-Datei
  ausserhalb und entsprechend ungeprueft. Der Umfang bleibt aufgezaehlt statt
  `.`, weil `ruff format .` vier datierte Findings unter `audits/` umschreiben
  wuerde.

### Geaendert — `actions/github-script` von v7 auf v9

Betrifft nur `.github/workflows/live-tests.yml`, die einzige Fundstelle dieser
Action im Repo; am ausgelieferten Paket aendert sich nichts.

v7 zielt auf Node 20. Der Live-Lauf vom 2026-08-15 endete mit `##[warning]
Node.js 20 is deprecated. … being forced to run on Node.js 24`. v8 haette das
ebenfalls behoben — es aendert nur die Laufzeit —, ist aber nicht mehr der
aktuelle Stand; der Zwischenschritt haette denselben Bump ein zweites Mal
faellig gemacht.

Die drei Bruchstellen von v9 gehen an dem Skript vorbei: kein
`require('@actions/github')`, keine eigene Deklaration von `getOctokit`, keine
`@actions/github`-Interna. Benutzt werden `github.rest.issues.*`, `context` und
`core` — ueber alle drei Versionen unveraendert.

**Von Hand verifiziert, weil die CI es nicht kann.** `live-tests.yml` laeuft
weder bei `push` noch bei `pull_request`; die Checks eines PR sagen ueber diesen
Bump also nichts. Der Beleg ist ein `workflow_dispatch` auf dem Branch vor dem
Merge: Die Action loeste auf, der Schritt lief durch, die Einordnung war `clear`
(9 von 9 Live-Tests gruen), und die Node-20-Warnung kam im vollstaendigen Log
nicht mehr vor.

### Behoben — `zefix_get_company_by_uid` antwortete notfalls mit einer fremden Firma

Ohne exakten Treffer fiel das Werkzeug auf den ersten Suchtreffer zurueck
(`exact = firms[:1]`). Das war keine Grosszuegigkeit, sondern eine falsche
Auskunft: Die UID-Suche laeuft mit `searchType: CONTAINS` ueber das Namensfeld,
und Zefix beantwortet `CHE-999.999.999` mit einer Firma namens **«CHEMAM -
999»** — UID `CHE-113.593.998`. An der Quelle geprueft am 2026-08-15.

Ausgeliefert sah das so aus:

```
zefix_get_company_by_uid(uid="CHE-999.999.999")
→ ## ❌ CHEMAM - 999
  **UID:** CHE-999.999.999          ← die Firma hat CHE-113.593.998
  | **CHID** | CH-073-1017856-6 |    ← gehoert zu CHE-113.593.998
  | **Status** | GELOESCHT |
```

Vollstaendig, plausibel, formatiert, und ueber jemand anderen — von einer
richtigen Antwort nicht zu unterscheiden. Ein Modell, das das liest, hat keinen
Anhaltspunkt, dass die Zuordnung nicht existiert.

Der Rueckfall ist raus. Ohne exakten Treffer meldet das Werkzeug, dass es
nichts gefunden hat, und ruft auch keine Detailseite mehr ab. Dieselbe Stelle in
`docs/demo/demo.py` wurde zuvor im selben Sinn korrigiert; aufgefallen ist der
Fehler dort, beim ersten Lauf der neuen Live-Tests.

### Behoben — Zefix ist doch aufzeichenbar, und das hat zwei Fehler freigelegt

Der letzte Durchgang liess die Zefix-Payloads als Literale im Testmodul stehen
und trug sie in `PROVENANCE.md` unter **NICHT aufgezeichnet** ein, mit der
Begruendung: Die API antwortet ohne `ZEFIX_USER`/`ZEFIX_PASSWORD` mit HTTP 401.
Die Messung stimmte. Sie galt der falschen Adresse.

Es gibt zwei Zefix-APIs unter demselben Host:

| | Zugangsdaten | Antwort |
|---|---|---|
| `ZefixPublicREST` — was das Aufzeichnungsskript fragte | ja | **401** |
| `ZefixREST` — was `ZEFIX_BASE` ist und der Server benutzt | nein | **200** |

Die 401 hat also die Adressliste des Skripts gemessen, nicht den Zugang zur
Quelle. Damit das nicht noch einmal auseinanderlaeuft, importiert das Skript
die Basis-URL jetzt aus `register_mcp.server`, statt sie abzuschreiben.

**Zwei ausgelieferte Fehler kamen mit dem Aufzeichnen heraus:**

**1. `legalSeatId` wurde ueber die falsche Spalte aufgeloest.** Eine Firma
traegt ihren Sitz als `legalSeatId`; die Gemeindeliste fuehrt zwei
Zahlenspalten, `id` und `bfsId`. `legalSeatId` ist eine **BFS-Nummer**. Das
Werkzeug `zefix_list_municipalities` stellte die interne `id` in die erste
Spalte und versprach im Docstring, ueber diese Liste liesse sich `legalSeatId`
aufloesen.

Ueber `id` nachgeschlagen kommt kein Fehler heraus, sondern **eine andere,
echte Schweizer Gemeinde**. Gemessen an 12 Treffern: 0 von 12 richtig ueber
`id`, 12 von 12 ueber `bfsId`.

| `legalSeatId` | tatsaechlich | ueber `id` gelesen |
|---|---|---|
| 261 | Zürich (ZH) | **Aarwangen (BE)** |
| 2701 | Basel (BS) | **Embd (VS)** |
| 247 | Schlieren (ZH) | **Weiningen (ZH)** |

Die erfundene Fixture fuehrte fuer Zürich `{"id": 261, "bfsId": 261}` — mit
dieser Gleichheit stimmen beide Aufloesungen ueberein und die Verwechslung ist
unsichtbar. Sie gilt fuer **keine** der 2112 Gemeinden.

Neu nimmt das Werkzeug einen Parameter `legal_seat_id` und loest selbst auf,
statt die Zuordnung einem Aufrufer und zwei aehnlich aussehenden Zahlenspalten
zu ueberlassen. Die Tabelle fuehrt `BFS-ID (= legalSeatId)` zuerst und die
interne Zefix-ID ausdruecklich benannt daneben.

**2. Eine Suche ohne Treffer antwortete «Bitte EHRAID oder UID pruefen».**
Zefix meldet die leere Treffermenge mit **HTTP 404** und dem NORESULT-Umschlag
im Rumpf, nicht mit 200. `raise_for_status()` warf, und die generische
404-Meldung des Servers lautet «Eintrag nicht gefunden. Bitte EHRAID oder UID
pruefen» — auf eine **Namenssuche** hin, bei der weder EHRAID noch UID im Spiel
waren. Der freundliche Zweig `_zefix_error_to_str` war fuer Suchen damit
unerreichbar.

Die erfundene Fixture legte den NORESULT-Umschlag in eine 200er-Antwort, und
der Test dazu bestand. Die aufgezeichnete Fixture haelt **Statuscode und
Rumpf** fest, weil erst beides zusammen den Fall ausmacht.

**Nullbefund, der dazugehoert:** `mutationTypes` in `shabPub[]` gibt es
wirklich — 87 Vorkommen in sechs Firmen. Dieses Feld hatte die erfundene
Fixture richtig geraten.

### Hinzugefuegt — die Zefix-Fixtures sind aufgezeichnet

Fuenf neue Dateien: `zefix_legal_forms.json`, `zefix_search.json`,
`zefix_firm_detail.json`, `zefix_communities.json`, `zefix_no_result.json`.
`PROVENANCE.md` fuehrt keine Datei mehr unter «NICHT aufgezeichnet».

**Die Auswahlregeln sind nach Merkmal, nicht nach Position.** Die
Gemeinde-Fixture enthaelt zu jeder in der Suche vorkommenden `legalSeatId`
*beide* Kandidaten einer Verwechslung — die Gemeinde mit dieser `bfsId` **und**
die mit dieser `id`. Nur so stehen sie nebeneinander in der Datei; «die ersten
N Gemeinden» haette den Befund verdeckt. Das Skript bricht ab, wenn im
Zuschnitt eine Gemeinde mit `id == bfsId` landet, wenn die Suche zu wenige
verschiedene Sitzgemeinden liefert, oder wenn eine leere Suche nicht mehr mit
404 antwortet.

**Redigiert wird auch hier.** Zefix fuehrt in `shabPub[].message` den
SHAB-Volltext: «Eingetragene Personen neu oder mutierend: <Name>, von <Ort>, in
<Ort> …». Der Server liest das Feld nicht, die Fixture soll aber die Form
belegen — also bleibt der Schluessel und der Wert ist ersetzt, mit Vermerk in
`PROVENANCE.md`. Ein Test sichert zu, dass der redigierte Text auch nicht in
eine Antwort geraet.

**Gegenprobe gefuehrt:** Mit zurueckgedrehtem Code — Aufloesung wieder ueber
`id`, 404 wieder durchgeworfen — fallen die zwei neuen Zusicherungen.

### Behoben — eine korrekte HR-Suche galt als «Filter ignoriert»

`GAZETTE_IGNORED_FILTER_THRESHOLD` stand als absolute Zahl (`2_000_000`) im
Code, begruendet mit «weit ueber jedem plausiblen Einzelfilter-Ergebnis». Das
war falsch, und zwar fuer die wichtigste Rubrik dieses Servers. Gemessen am
2026-08-07:

| Filter | `total` |
|---|---:|
| `rubrics=HR` (Handelsregister) | **2 279 587** |
| `rubrics=LS` | 70 330 |
| `rubrics=SB` | 22 872 |
| ungefiltert (voller Korpus) | 2 809 194 |

HR ist 81 % des Korpus und lag damit ueber der Schwelle: Jede HR-Suche brach mit
«Filter wurde vom Upstream ignoriert — Ergebnis nicht vertrauenswuerdig» ab,
obwohl der Filter einwandfrei gewirkt hatte. `rubrics` ist allow-gelistet, der
Fall also ueber die oeffentliche Tool-Oberflaeche erreichbar.

Der Pruefgegenstand ist nicht «viele Treffer», sondern «der **ganze** Bestand».
Die Schwelle ist deshalb jetzt anteilig (95 % des aufgezeichneten Korpus).
Waechst der Bestand und bleibt die Konstante stehen, wird die Pruefung
unschaerfer statt falscher — sie verfehlt hoechstens einen echten Fall, statt
einen gesunden abzuweisen.

**Warum das niemand gesehen hat:** Die erfundene Fixture setzte den Korpus auf
`2_790_323` und liess jedes gefilterte Ergebnis unter 2 Mio. bleiben.
Produktivcode und Mock trugen dieselbe Annahme, also konnte kein Test sie
widerlegen. Festgehalten von
`test_the_largest_rubric_is_not_mistaken_for_an_ignored_filter`, das die
**Ordnung** der drei Groessen prueft statt drei Zahlen. Gegenprobe gefuehrt: Mit
der wiederhergestellten absoluten Schwelle faellt es.

### Hinzugefuegt — die Amtsblatt-Fixtures sind aufgezeichnet, nicht mehr ausgedacht

**`scripts/record_fixtures.py`** zeichnet von `amtsblattportal.ch` auf und
schreibt `tests/fixtures/*` samt `PROVENANCE.md` mit Quelle,
**Aufzeichnungsdatum**, Auswahlregel und SHA-256. Aufgezeichnet sind die
Rubrikentaxonomie (woertlich — eine Codeliste), eine `/publications`-Antwort und
der Gesamtbestand.

**Personendaten: Struktur echt, Werte redigiert.** Das Amtsblatt fuehrt `SB`
(Schuldbetreibungen) und `LS` (Schuldenrufe); der Freitext einer Publikation
nennt natuerliche Personen mit Adresse. Eine woertliche Antwort in einem
oeffentlichen Repo waere eine Republikation. Deshalb sind Schluessel,
Verschachtelung, Typen und alle Codes, auf die der Server verzweigt, woertlich
aufgezeichnet — und die Werte von `meta.title` und `content` ersetzt.
`PROVENANCE.md` nennt die vollstaendige Liste, und
`test_the_recorded_search_keeps_the_structure_the_server_branches_on` haelt die
Trennung fest.

**Zefix ist NICHT aufgezeichnet.** Die API verlangt `ZEFIX_USER`/`ZEFIX_PASSWORD`
und antwortet ohne sie mit HTTP 401. Diese Payloads stehen weiterhin als
Literale im Testmodul, sind also ausgedacht und tragen kein Datum.
`PROVENANCE.md` fuehrt sie ausdruecklich unter «NICHT aufgezeichnet» — das ist
der Ist-Zustand und keine Luecke, die man wegraeumt, indem man sie verschweigt.
Wer Zugangsdaten hat, setzt die beiden Variablen und laesst das Skript erneut
laufen; der Zefix-Zweig ist darin fertig vorgesehen.

Der Rahmen dazu steht im Skill [`mcp-data-fidelity`](https://github.com/malkreide/mcp-data-fidelity-skill)
unter Regel 5 und im Katalog-Check `OPS-009`.


### Hinzugefuegt — die Live-Suite laeuft geplant, statt nur markiert zu sein

`ci.yml` faehrt `pytest tests/ -m "not live"`. Das ist richtig — ein fremder 503
darf keinen fremden Pull Request rot machen — und es liess die Live-Tests seit
ihrer Entstehung an keiner Stelle laufen. **`-m "not live"` ist kein Ort, an dem
Tests laufen; es ist die Abwesenheit eines solchen.**

Ausgerechnet sie sind die einzigen im Repo, die einer falschen Grundannahme
ueber zefix.admin.ch widersprechen koennen: Jeder andere Test prueft gegen eine
Fixture, und die Fixture ist aus derselben Annahme geschrieben wie der Code. Bei
`meteoswiss-mcp` fielen am 30.7.2026 beim ersten Lauf seit Monaten drei von sechs
Tests; bei `zh-education-mcp` lief am 3.8.2026 der Code monatelang gegen
umbenannte Feldnamen, ohne dass ein Test rot wurde.

`.github/workflows/live-tests.yml`: montags 05:31 UTC auf einer ungeraden Minute, dazu
`workflow_dispatch`. Der PR-Lauf bleibt unveraendert — dies ist ein
*zusaetzlicher* Lauf, kein Umbau.

**Drei Antworten, nicht zwei.** `if: failure()` kennt rot und nicht rot; ein
gescheitertes `pip install` saehe damit aus wie ein gebrochener Vertrag mit der
Quelle. `scripts/classify_live_run.py` liest deshalb das JUnit-XML und trennt
`clear`, `finding` und `unknown`. Ein `unknown` schliesst nie ein Issue:
zuzumachen hiesse zu behaupten, der Vergleich sei gelaufen.

Der Fall, der die Einordnung noetig macht, ist der uebersprungene Lauf: pytest
endet mit 0, wenn jeder Test uebersprungen wurde. `tests - skipped == 0` ist
deshalb `unknown` — gemessen am 7.8.2026 an `swiss-transport-mcp`, wo ohne
`TRANSPORT_API_KEY` alle sechs Live-Tests uebersprungen werden und ein
Exit-Code-Check gruen gemeldet haette.

Die Einordnung steht in einem Skript mit eigenem Test, nicht in einem
`run:`-Block: Sie entscheidet, ob ein Issue auf- oder zugeht, und das ist der
einzige Teil des Workflows, der etwas behauptet.

Ein Issue mit stabilem Titel-Praefix und Label `upstream` wird kommentiert statt
verdoppelt. Die pytest-Ausgabe geht ueber `env` ins Skript, nicht ueber `${ }`
— sie ist fremder Text, der sonst in einem JavaScript-Template-Literal landet.

Kadenz und Zustaendigkeit stehen in CONTRIBUTING (beide Sprachen). Gemessen mit
`live_schedule_probe` aus `mcp-continuous-auditor`: vorher `LIVE_UNSCHEDULED`,
jetzt `LIVE_SCHEDULED`.

### Behoben

- **Netzwerkfehler und Timeouts wurden nie wiederholt.** Die Schleife deckte
  nur Status-Codes ab: Ein 503 aus einem Ausfall bekam drei Versuche, eine
  abgelehnte Verbindung oder ein haengender Read aus *demselben* Ausfall keinen
  einzigen. Damit sah der Retry vorhanden aus und liess den haeufigsten Fall
  ungedeckt — genau diese Form von Ausfall hat am 1. August in `swiss-efv-mcp`
  vier Live-Tests gekippt und die ganze ARCH-014-Runde ausgeloest.

  `httpx.RequestError` wird jetzt wie ein transienter Status behandelt:
  dieselbe Versuchszahl, dieselbe gestreute Wartezeit, dasselbe Budget. Der
  letzte Fehler wird unverpackt durchgereicht, damit sein Typ die Meldung
  traegt — `httpx.ConnectError` hat ein leeres `str()`, der Typ ist dort das
  Einzige, was uebrig bleibt (OBS-007).

- **Ein 429 wurde gelesen und dann ignoriert.** `parse_retry_after` kannte 429
  bereits, `_TRANSIENT_STATUS` nicht — der geparste `Retry-After` lief also ins
  Leere und der Aufruf scheiterte sofort. Ein 429 ist der einzige Status, der
  seine eigene Wiederkehrzeit nennt; ihn nicht zu wiederholen heisst, eine
  ausdrueckliche Angabe der Quelle einzuholen und wegzuwerfen. 4xx im Uebrigen
  scheitert weiterhin sofort.

- **Ein aufgebrauchtes Budget meldete sich als nackter `TimeoutError`.** Feuert
  die `asyncio.timeout`-Deadline, ist das Budget definitionsgemaess weg — die
  Meldung nennt jetzt Budget und Endpunkt statt gar nichts, mit dem
  urspruenglichen Timeout als `__cause__`.

- **Die `fake_clock`-Fixture patchte `asyncio.sleep` global.** Das trifft jeden
  Import im Prozess; ein Test, der `asyncio.sleep(0)` benutzt, um dem
  Event-Loop das Wort zu geben, haette danach still nichts mehr geprueft. Der
  Backoff laeuft jetzt ueber den Modul-Alias `server._sleep`.

### Added

- **Retry-Politik gegenueber dem Amtsblattportal** (ARCH-014): `Retry-After`
  wird gelesen und schlaegt die lineare Kurve, der Backoff ist gestreut, und ein
  Gesamtbudget von 25 s begrenzt den ganzen Aufruf.

  `Retry-After` bei 429/503 in beiden Formen der RFC 9110 §10.2.3. Ein
  unbrauchbarer Header fuehrt zurueck auf die Kurve statt zum Absturz.

  Jitter: `GAZETTE_RETRY_BACKOFF * attempt` war deterministisch, alle Clients
  retryen im Gleichtakt. Neu [0.5x, 1.5x]; auf einem `Retry-After` einseitig
  [1.0x, 1.25x]. Gedeckelt bei 20 s **nach** dem Jittern, damit der Deckel eine
  echte Schranke ist. Das Log-Event `gazette_retry` nennt neu die tatsaechliche
  Wartezeit.

  Gesamtbudget verankert an `MCP_DEFAULT_TIMEOUT = 30.0` des Python-SDK, per
  `GAZETTE_TOTAL_BUDGET` konfigurierbar wie die uebrigen Gazette-Knoepfe. Der
  Request liegt in einer `asyncio.timeout`-Deadline, weil httpx' Timeout pro
  Operation gilt und den Aufruf nicht begrenzen kann.

### Changed

- **`_gazette_get_json` und `_gazette_get_text` teilen sich einen Retry-Kern.**
  Beide trugen eine wortgleiche Kopie derselben Schleife; die Retry-Politik —
  und jetzt auch das Budget — haette an zwei Orten gepflegt werden muessen, und
  die zweite waere beim naechsten Refactoring die vergessene gewesen. Neu rufen
  beide `_gazette_get` auf und unterscheiden sich nur noch in `.json()` gegen
  `.text`.


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
