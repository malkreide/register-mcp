# CLAUDE.md

## Teil 1 — Portfolio-weite Konventionen

### Vor der Arbeit

Klon-Aktualität prüfen — Standard-Branch ermitteln, nicht `main` annehmen:

```bash
B=$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p')
git fetch origin "${B:?Standard-Branch nicht ermittelbar}" &&
  git rev-list --count HEAD..FETCH_HEAD
```

Drei Server im Portfolio heissen ihren Standard-Branch `master`
(`openlex-mcp`, `swiss-courts-mcp`, `swisstopo-mcp`); dort scheitert ein fest
verdrahtetes `origin/main` mit «couldn't find remote ref main». Wer das für ein
Netzproblem hält, arbeitet weiter auf genau dem veralteten Klon, vor dem dieser
Absatz warnt. Den `:?`-Schutz nicht weglassen: Bei leerem `B` fetcht git still
den Remote-HEAD und endet mit 0.

Ein veralteter Klon erzeugt eine rote CI, deren Ursache nicht im Diff steht.
Am 3.8.2026 zweimal passiert — beide Male fehlten genau die Commits, die
das Gate einführten, an dem der Branch scheiterte.

In diesem Repo nimmt einem der SessionStart-Hook
`.claude/hooks/check-clone-freshness.sh` den Handgriff ab: Er meldet den
Rückstand beim Sessionstart und schweigt, wenn keiner besteht. Er ersetzt die
Prüfung nicht, er erinnert nur an sie — er ist bewusst fail-open und geht bei
jedem Netz-, Remote- oder Werkzeugproblem still durch, statt die Session
anzuhalten. Ein stilles Durchgehen sieht also genauso aus wie ein aktueller
Klon; wer sicher sein will, fährt den Block oben von Hand.

Gates lokal fahren, mit der GEPINNTEN ruff-Version aus der CI. Eine andere
Version meldet Abweichungen, die niemand verursacht hat.

### Tests

Gegenprobe ist Pflicht. Ein Test, der grün bleibt, wenn man die
Implementierung entfernt, prüft nichts. Jede neue Zusicherung einzeln
neutralisieren und zeigen, dass genau die zugehörigen Tests fallen.
Zwei Fallen, die beide grün blieben:

- Eine Fake-Uhr, die nur beim Schlafen vorrückt, kann eine Zusicherung über
  echte Zeit nicht widerlegen.
- `monkeypatch.setattr(modul.asyncio, "sleep", ...)` greift ins Modul
  asyncio selbst und entschärft die Mechanik im ganzen Prozess. Patche
  einen Modul-Alias (`_sleep = asyncio.sleep`), nicht das fremde Modul.

Handgeschriebene Fixtures kodieren die Annahme des Autors und können sie
nicht widerlegen. Mindestens eine aufgezeichnete Antwort pro externem
Endpunkt, mit Aufnahmedatum.

### Wenn etwas rot ist

Roter Live-Test: erst die Quelle abfragen, dann einordnen. Nicht aus der
Fehlermeldung schliessen. Am 3.8.2026 hiess "nicht gefunden" nicht, dass der
Datensatz weg war, sondern dass die Quelle die Schreibweise ihrer Kopfzeile
gewechselt hatte — vier von sechs Datensätzen produktiv kaputt, alle
Unit-Tests grün.

**Ein 4xx ist kein Nein.** Am 29.8.2026 antwortete `past-publications` in
`swiss-procurement-mcp` auf jede Publikation mit Losen mit HTTP 400. Daraus war
geschlossen worden, die Quelle verweigere diese Auskunft; der Befund stand
datiert im Fixture-Nachweis, ein Test bestätigte ihn, alles blieb grün. Die
Spec desselben Endpunkts führt einen als *optional* deklarierten Parameter
`lotId` — für Publikationen mit Losen ist er Pflicht. Mit ihm antwortet
dieselbe Publikation mit 200. Ein Projekt trug sieben Vorgängerpublikationen,
die der Server als «Quelle nicht erreichbar» wegwarf.

Drei Handgriffe daraus:

- **Die Parameterliste der Spec durchgehen, bevor ein Statuscode eingeordnet
  wird.** «Optional» heisst dort oft «optional für die Mehrheit».
- **Einer deterministischen Absage keinen Wiederholungsrat geben.** «Nicht
  erreichbar, bitte später erneut» ist bei einem 400 falsch und liest sich für
  das Modell wie eine Störung. Den Status mitführen und den fehlenden
  Parameter benennen — den Status, nicht den Antwortkörper.
- **Beide Antworten aufzeichnen, mit und ohne den Parameter.** Eine
  Aufzeichnung nur des Fehlschlags kann nicht zeigen, dass er vermeidbar war;
  dass nur der 400er aufgezeichnet war, ist der Grund, warum der falsche
  Befund nicht auffiel.

**Und ein 403 ist gar keine Auskunft.** Am 29.8.2026 sollten für 42 Repos die
Dependabot-Labels nachgemessen werden. Alle 13 Abfragen des ersten Stapels
kamen zurück als:

```
Failed to find label: API rate limit already exceeded for user ID 8864492.
```

Der gefährliche Teil steht vorn: Das Werkzeug verpackt eine Sperre als
Fund-Fehlschlag. Wer die Zeile überfliegt oder nur auf ein leeres Ergebnis
prüft, zählt 39 Repos als «Label fehlt» und hat seine eigene Erschöpfung
gemessen. Das Limit hängt am Konto, nicht am Repo — derselbe Vormittag hatte
es mit 42 eröffneten und 42 gemergten PRs verbraucht.

Das ist der Absatz darüber, andersherum gelesen: dort war ein 400 eine echte,
wiederholbare Antwort und galt als Störung; hier ist eine Störung als Antwort
verpackt. Entscheidend ist nie der Statuscode, sondern ob die Quelle überhaupt
geantwortet hat.

- **Positivkontrolle im selben Repo.** Ein «nicht gefunden» wird erst dadurch
  zur Messung, dass eine gleichzeitige Abfrage etwas findet.
- **Die Messung entlang der Sperre teilen.** `raw.githubusercontent.com` ist
  ein CDN und nicht die REST-API. Um 11:19:27 UTC lieferte es für
  `register-mcp` HTTP 200, während die Label-Abfrage desselben Repos in
  derselben Minute die Sperre meldete. Alle 42 `dependabot.yml` kamen so
  durch, während die Label-Hälfte stand.
- **Am Token vorbei geht es nicht.** Beide Umwege enden am Agent-Proxy, und
  jeder mit einer eigenen irreführenden Begründung. `api.github.com` ohne
  Zugangsdaten:

  ```
  GitHub access is not enabled for this session. An org admin must connect
  the Claude GitHub App for this organization.
  ```

  Das ist keine Aussage über die Organisation, sondern das, was ohne Token
  kommt. Wer ihr folgt, sucht einen Admin für ein Problem, das keiner hat.
  Die HTML-Seite `github.com/<owner>/<repo>/labels` fällt ebenfalls, aber
  anders:

  ```
  This GitHub API path is not available: sessions are bound to their
  configured repositories. Use repository-scoped endpoints
  (repos/{owner}/{repo}/...).
  ```

  Der Proxy behandelt also auch `github.com` als API-Pfad; die zweite Meldung
  klingt nach einem Scope-Problem und ist doch nur dieselbe Sackgasse. Den
  Token aus der Umgebung in einen curl-Header zu setzen, blockiert der
  Klassifikator. Ob es überhaupt hülfe, ist offen: die Sperre nennt ein
  Nutzerkonto, und ob der Token zu diesem gehört, wurde nie geprüft.
- **Die Sperre gilt nicht dem Dienst, sondern dem Zugangspfad.** Unmittelbar
  nachdem eine Abfrage der Checks eines PR sauber durchlief, meldete die
  Label-Abfrage weiter die Sperre. Von einem blockierten Werkzeug also nicht
  auf «GitHub ist zu» schliessen — und umgekehrt eine gelungene Abfrage nicht
  als Entwarnung für die gesperrte nehmen.

Wann die Sperre fällt, geben diese Beobachtungen nicht her. Die Meldung nennt
keinen Zeitpunkt, und die `X-RateLimit`-Kopfzeilen sind hinter dem Proxy nicht
zu sehen. Belegt sind drei gesperrte Zeitpunkte — 11:14, 11:16 und 11:19 UTC.
Wer daraus eine Dauer macht, hat sie erfunden.

**Dieselbe Falle bei einer Konfigurationsoption: die Vorgabe lesen, bevor man
einen Schlüssel für wirkungslos hält.** Am 29.8.2026 fielen die
`labels:`-Zeilen aus den `dependabot.yml` des Portfolios, begründet mit
«Dependabot legt Labels nicht an». Eine Messung danach zeigte, dass
`dependencies` in 36 von 42 Repos sehr wohl existiert, 35 davon mit GitHubs
Standardbeschreibung. Das las sich zuerst wie ein Beleg, dass die Aktion
falsch war.

Die Optionsreferenz kehrt es um:

```
Dependabot creates these default labels automatically, as necessary in
your repository.

If you define more than one package manager, an additional label for the
ecosystem or language is added to each pull request.

The labels specified are used instead of the default labels.
```

Ohne `labels:` vergibt Dependabot also `dependencies` — und, sobald mehr als
ein Paketmanager deklariert ist, zusätzlich ein Ökosystem-Label — und legt sie
selbst an; eine eigene Liste **ersetzt** diesen Satz, und «if any of these
labels is not defined in the repository, it is ignored». Die Zeile war nicht
wirkungslos — sie tauschte einen sich selbst pflegenden Vorgabesatz gegen eine
starre Liste.

**Die Bedingung nicht weglassen.** Bei nur einem Paketmanager steht das
Ökosystem-Label gar nicht zu; wer es dort trotzdem erwartet, schreibt genau
den Fehlbefund auf, gegen den dieser Abschnitt geschrieben ist — der Abschnitt
liefe an sich selbst vorbei. Im Portfolio deklariert jede `dependabot.yml`
zwei (`pip` und `github-actions`), die Bedingung ist hier also überall
erfüllt; anderswo nicht unbedingt. Aufgefallen ist die fehlende Bedingung
nicht beim Schreiben, sondern durch einen Codex-Review auf
`swiss-environment-mcp` PR #113 — vierzehn Sekunden vor dem Merge desselben
PR.

Was das kostet, ist an `openlex-mcp` gemessen: zwei Ökosysteme deklariert,
also stünden `dependencies` **und** ein Ökosystem-Label zu; vorhanden ist nur
das erste, `github-actions` und `github_actions` fehlen beide (Kontrolle `bug`
vorhanden). `register-mcp` ist die Gegenprobe: dort existieren alle vier
deklarierten Namen mit handgeschriebener Beschreibung, die Liste ist gewollt
und vollständig.

**Dreimal falsch eingeordnet, in drei Richtungen.** Erst die Zeile für bloss
wirkungslos gehalten. Dann die gefundenen Labels für einen Widerspruch. Dann,
auf denselben Fund gestützt, einen richtigen PR geschlossen mit dem Argument,
das Label existiere ja — obwohl es existiert, *weil* die Vorgabe es anlegt.
Der dritte Fehler ist der teuerste, weil er wie eine Messung aussah.

Was die Messung **nicht** hergibt: wer die 36 Labels angelegt hat. Die
Referenz sagt, Dependabot tue es; die Objekt-IDs liegen aber so dicht
beieinander, dass sie eher aus einem Stapellauf stammen. Beides passt zum
Befund, keines ist belegt — die Herkunft blieb ungemessen.

Beim Aufräumen gilt deshalb dieselbe Frage wie bei `lotId`: Was ist die
*Vorgabe*, wenn man das Ding weglässt — nicht bloss, ob der aktuelle Wert
etwas bewirkt.

**`results[0]` ist nur so verlässlich wie die Zusicherung danach.** Pinnt die
Abfrage einen bekannten Datensatz, ist der erste Treffer eine Drift-Wache und
in Ordnung. Hängt die Zusicherung dagegen davon ab, *welche* Variante die
Quelle heute zuoberst hat, prüft der Test den Tag: am 25.8.2026 rot, weil die
neueste Zürcher Publikation zufällig Lose hatte, am 26.8. grün, ohne dass sich
etwas geändert hätte. Den Fall gezielt wählen und beide Zweige fahren.
PR ohne jeden Check ist selten ein Repo ohne CI, meistens ein
Merge-Konflikt: GitHub berechnet dafür keinen Merge-Commit und startet nichts.

**Bei einem blockierten PR nennt der Merge-Versuch den Blocker, jede Ableitung
rät.** `mergeable_state: blocked` bei grüner CI heisst: ein required Kontext
fehlt oder steht nicht auf grün. Welcher, sagt die Einstellung — und die sperrt
der Agent-Proxy mit HTTP 403, ein MCP-Werkzeug dafür gibt es nicht. Der Ausweg
ist nicht Indizienarbeit, sondern ein Merge-Versuch über die API:

```
PUT /repos/<owner>/<repo>/pulls/<n>/merge
405 Required status check "Codex hat diesen Head geprueft" is expected.
```

Der Name steht dort wörtlich so, wie er in der Branch Protection eingetragen
ist. Scheitert der Versuch, kostet er nichts.

Am 24./25.9.2026 über drei Repos vermessen, nachdem ein Gate-Workflow entfernt
worden war und seinen required Kontext ohne Berichterstatter zurückliess:

| Repo | eingetragener Kontext | Art |
|---|---|---|
| `register-mcp` | `Codex hat den PR angesehen` | Check-Run |
| `srgssr-mcp` | `review-abgeschlossen` | Check-Run |
| `fedlex-mcp` | `Codex hat diesen Head geprueft` | Check-Run |

**Warum Ableiten hier systematisch fehlgeht.** GitHub nimmt als Check-Run-Name
den **Job**-Namen, nicht den des Workflows. Zwei der drei Kontexte enthalten die
Zeichenfolge «codex-gate» nicht, obwohl sie aus `codex-gate.yml` stammen; wer in
den Einstellungen danach sucht, findet nichts und hält die Regel für abwesend.
Trug der Job kein `name:`, nimmt GitHub die Job-ID — daher `review-abgeschlossen`.

Zwei Fehlschlüsse sind dabei belegt, beide aus **einer** Beobachtung gezogen:

- Aus einem Commit-Status auf den required Kontext geschlossen. In `fedlex-mcp`
  stand der Status `codex-gate` auf dem Head auf `success` und blockierte
  nichts, während der fehlende Check-Run den Merge hielt. Am Kontroll-PR waren
  beide rot — dort ist nicht zu unterscheiden, welcher von beiden eingetragen
  ist. Genommen wurde der auffälligere.
- Aus einer Check-Run-Liste auf den required Kontext geschlossen. Die Liste
  zeigt, was **berichtet** wurde; eingetragen sein kann ein Name, der gerade
  gar nicht erscheint. Genau das ist der Fall, um den es geht.

**Ein Vorbehalt, der zur Methode gehört:** Die Absage nennt immer nur den
**ersten** fehlenden Kontext. Ist ein zweiter eingetragen, zeigt ihn erst der
nächste Versuch. Nach jeder Änderung an der Einstellung also erneut versuchen,
bis der Merge durchgeht oder ein neuer Name fällt.

Die Kosten der Ableitung sind gemessen: ein Arbeitstag, an dem der PR-Text den
falschen Namen trug und in den Einstellungen nach einer Zeichenfolge gesucht
wurde, die dort nicht steht.

### Wenn zwei Agenten dasselbe tun

Vor dem Anlegen eines Branches mit vorgegebenem Namen prüfen, ob es ihn schon
gibt:

```bash
git ls-remote --heads origin claude/<name> | wc -l
```

Steht dort `1`, arbeitet jemand anderes daran — mit Schreibrecht auf denselben
Ref.

Ein PR mit leerem Diff wird geschlossen, nicht gemergt. Der Test ist
`get_files` auf dem PR: kommt `[]` zurück, ändert er nichts. Ein grüner Check
sagt dazu nichts — die CI prüft den Head, nicht die Differenz zur Basis.

Am 21.8.2026 liefen zwei Sessions dieselbe Aufgabe über 45 Repos, auf den
Branches `claude/codex-review-audit-templates-9sn6mx` und
`claude/codex-review-audit-7ioh56`. Wo die eine zuerst nach `main` kam, wurde
`main` in den Branch der anderen gemergt und der add/add-Konflikt zugunsten
von `main` aufgelöst. Übrig blieben 14 PRs, die durch sämtliche Gates grün
liefen und nichts enthielten; sie wurden gemergt und hinterliessen leere
Merge-Commits. Mit den zwei Folge-PRs, die aus demselben Grund gegenstandslos
waren, waren 16 der 59 PRs jenes Tages reine Reibung.

Dieselbe Klasse wie der handgeschriebene Stub, der denselben Feldnamen annahm
wie der Code: Nichts ist rot, weil nichts geprüft wird, worauf es ankommt.

## Teil 2 — Repo-spezifisch (register-mcp)

**ruff: eine Quelle.** Derselbe Pin steht in `pyproject.toml` und `.pre-
commit-config.yaml` — und **nicht** mehr als eigener Install-Schritt in der
CI. Welche Version gerade gilt, sagt `check_version_sync.py`; hier steht sie
bewusst nicht. Sonst wäre dieser Absatz die dritte Stelle, die mitwandern
müsste, und die einzige ohne Gate.

Der CI-Schritt lief nach dem Install der Abhängigkeiten und überschrieb sie.
Eine Abweichung im Pin konnte deshalb in der CI gar nicht auffallen, sondern
nur lokal — wo niemand sie erwartet. Ein manuelles Nachinstallieren von ruff
vor den Gates ist damit nicht mehr nötig und wäre schädlich: Es würde eine
spätere Anhebung hier stillschweigend überstimmen.

`scripts/check_version_sync.py` bricht ab, wenn die verbleibenden Stellen
auseinanderlaufen **oder** wenn `ci.yml` wieder ein eigenes ruff installiert;
`tests/test_precommit_config.py` wacht darüber, dass der Hook denselben Umfang
sieht wie das Gate.

**Dependabot hebt nur eine der beiden Stellen — jedes Mal.** Das
`uv`-Ökosystem schreibt `pyproject.toml` und `uv.lock`; der `rev:` in
`.pre-commit-config.yaml` gehört für Dependabot zu keinem der drei
konfigurierten Ökosysteme und bleibt stehen. Jede ruff-Anhebung kommt deshalb
als roter PR an, mit einem einzigen roten Test unter lauter grünen:

```
AssertionError: 2 != 1 : ruff-Pins weichen ab:
[('.pre-commit-config.yaml → rev', '0.16.5'),
 ('pyproject.toml → dev-Extra', '0.16.6')]
```

Das ist kein Fehler des Gates, sondern seine Aufgabe — ohne es liefe der Hook
lokal mit einer anderen ruff-Version als das Gate in der CI, und genau das war
der Zustand, gegen den der Pin gebaut wurde. Der Handgriff ist, die zweite
Stelle im selben Commit nachzuziehen: den `rev` **und** die Version im
Kopfkommentar derselben Datei, denn den Kommentar liest kein Gate.

Zweimal ist das schon passiert (0.16.4 am 15.8.2026, 0.16.6 am 7.9.2026, beide
im CHANGELOG). Wer den roten Job für einen Regressionsfund hält, sucht in
ruff 0.16.6 nach einer Ursache, die im PR-Umfang steht.

Ein `package-ecosystem: pre-commit` in `.github/dependabot.yml` löst das
**nicht**: Gruppen greifen nur innerhalb eines Ökosystems, die Anhebung käme
also als eigener PR — und dann wären zwei PRs rot statt einem, bis beide
gemerged sind. Solange der Pin an zwei Stellen steht, führt sie ein Mensch
oder eine Session zusammen.

**Der Gate-Umfang ist aufgezählt, nicht `.` — und das ist Absicht.**
`ruff format` formatiert auch Python-Blöcke *innerhalb* von Markdown. `ruff
format .` würde vier Findings unter `audits/` umschreiben; das sind datierte
Protokolle, kein Code. `audits/` bleibt deshalb draussen. Neue Verzeichnisse mit
Code gehören dagegen in beide Listen (`ci.yml` und `.pre-commit-config.yaml`).

Vor dem Lauf `ruff --version` prüfen: ein älteres ruff früher im `PATH`
schlägt den Pin, ohne dass der Install etwas meldet.

**Gate-Befehle, wörtlich aus `ci.yml`** (Job `test`, Python 3.11/3.12/3.13):

```bash
pip install -e ".[dev]"
PYTHONPATH=src pytest tests/ -m "not live"
python scripts/check_ruff_pin.py
ruff check src/ tests/ scripts/ docs/
ruff format --check src/ tests/ scripts/ docs/
python scripts/check_version_sync.py
uv lock --locked          # Job `lockfile`, uv 0.8.x
```

Job `docker` baut zusätzlich das Image und prüft: Start ohne `MCP_API_KEY`
scheitert, Container läuft als User `mcp`.

**Live-Tests: geplanter Workflow vorhanden**, kein DRIFT-005.
`.github/workflows/live-tests.yml` läuft per `cron: "31 5 * * 1"` (wöchentlich)
plus `workflow_dispatch`, ordnet das JUnit-XML über
`scripts/classify_live_run.py` ein und öffnet/schliesst danach ein Issue.
`-m "not live"` in `ci.yml` ist hier also ein Ausschluss *mit* Auffangnetz.

**Zur Matrix:** die Gate-Liste oben gehört dem Job `test` (3.11/3.12/3.13);
`lockfile` und `docker` laufen daneben je einmal, ohne Matrix. Ein
`fail-fast: false` steht nicht da — eine rote 3.11 bricht 3.12 und 3.13 ab,
bevor sie etwas sagen.

Was `check_version_sync.py` über den ruff-Pin meldet, steht im Klartext in
seiner Ausgabe: `ruff-Pin einig auf X.Y.Z (2 Stellen)`. Wer die zwei Stellen
von Hand vergleicht, tut Arbeit, die dieser Gate schon leistet.

Bis zum 8.9.2026 stand hier ein anderer Wortlaut («an beiden Stellen gleich»)
samt fester Version — beides so nie ausgegeben. Ein Zitat, das kein Gate
nachprüft, altert still; wer danach greppt, findet nichts und schliesst auf
die falsche Stelle.

**Was die Live-Suite fand, waren keine Ausfälle, sondern Antworten.** Drei
Formen von Zefix, jede hat einen ausgelieferten Fehler gekostet:

- Ohne Treffer antwortet `firm/search.json` mit **HTTP 404** plus
  NORESULT-Rumpf. Deshalb jeder Aufruf über `_zefix_post_search` — und eine
  Fixture, die den Rumpf in eine 200 legt, lässt den toten Zweig grün aussehen.
- Mit Treffern ist es noch keine Antwort: `searchType: CONTAINS` sucht über den
  Namen, `CHE-999.999.999` liefert «CHEMAM - 999». Kein Rückfall auf `firms[0]`.
- Ohne `activeOnly: False` sieht «gelöscht» aus wie «gibt es nicht».

**Dependabot-Labels legt niemand automatisch an.** Was in
`.github/dependabot.yml` unter `labels:` steht, wendet Dependabot nur an, wenn
es das Label im Repo schon gibt. Fehlt es, kommt kein roter Check und kein Log,
sondern ein Kommentar an jedem Pull Request:

```
The following labels could not be found: `dependencies`, `python`.
```

Die Meldung nennt immer nur die Labels des betroffenen Ökosystems. Wer sie für
die vollständige Liste hält, legt zwei an und übersieht die übrigen bis zum
nächsten `github-actions`- oder `docker`-PR — hier fehlten **alle vier**.
Deshalb die Konfiguration lesen, nicht die Meldung:

```bash
python scripts/check_dependabot_labels.py                    # nur auflisten
python scripts/check_dependabot_labels.py --repo malkreide/register-mcp
```

Der zweite Modus fragt die GitHub-API und gehört bewusst **nicht** in `ci.yml`:
Ein Gate, das bei einem erschöpften Rate-Limit rot wird, macht fremde PRs rot
und wird abgeschaltet. Er ist auch **kein** `@pytest.mark.live` — die
Live-Suite ist bis in den Issue-Titel auf `zefix.admin.ch` gemünzt und würde
ein Issue über Zefix aufmachen, in dem es nicht um Zefix geht. Im Gate läuft
nur der offline entscheidbare Teil (`tests/test_dependabot_labels.py`).

Exit 2 heisst «konnte nicht vergleichen», Exit 1 «Labels fehlen». Wer beides
gleich behandelt, meldet bei jedem API-Ausfall einen Konfigurationsfehler, den
es nicht gibt.

**Portfolio-Regel, entschieden am 28.8.2026: neue Server tragen kein
`labels:`.** Am selben Tag standen im Portfolio zwei gegensätzliche Antworten
auf dieselbe Frage nebeneinander — 19 Repos hatten die Zeile bereits entfernt
(`bakom-mcp` begründet es in seiner eigenen Konfiguration), 24 führten sie
weiter. Zwei Sessions hatten unabhängig voneinander dasselbe Problem gefunden
und verschieden gelöst; das ist der Fall aus «Wenn zwei Agenten dasselbe tun»,
nur über Tage statt über Stunden.

Entschieden wurde gegen die Labels, und zwar nicht aus Geschmack: Die Aussage
steht ohnehin dreifach im PR — Autor `dependabot[bot]`, Commit-Prefix
(`deps`/`ci`/`docker`) und Branchname `dependabot/<ökosystem>/…` nennen
dasselbe. Ein Label ist damit eine zweite Quelle für eine Information, die
schon da ist, und dieses Repo kennt die Kosten davon (ruff-Pin an zwei Stellen,
`pin_audit.py` an drei, der Hook an drei — jedes braucht einen Gate oder einen
Absatz wie diesen). Hier wäre selbst das nicht möglich: Ein Label ist
GitHub-Zustand und kein Dateiinhalt, also kann kein Gate es prüfen.

**Dieses Repo ist die Ausnahme und behält seine Zeile.** Die vier Labels
existieren hier seit dem 28.8.2026; ab da kostet sie nichts mehr. Wer die Regel
liest und `register-mcp` als Widerspruch sieht, hat beides richtig verstanden.

Zwei Sonderformen fielen beim Sweep nebenbei auf, die in *keiner* der beiden
Antworten richtig sind: `meteoswiss-mcp` fordert `ecosystem:pip`,
`ecosystem:docker`, `ecosystem:github-actions` — ein eigenes Namensschema —,
und `srgssr-mcp` fordert `github-actions` statt `ci`. Beide lösen sich auf,
wenn die Zeile fällt.

**`pin_audit.py` steht an drei Stellen.** `swiss-electricity-mcp`, `bakom-mcp`
und `register-mcp` halten byteweise dieselbe `scripts/pin_audit.py` samt
`tests/test_pin_audit.py`. Wer eine ändert, ändert alle drei im selben Commit —
sonst misst der eine Server anders als der andere, und das ist genau die Drift,
gegen die das Werkzeug gebaut ist. Kein Gate erzwingt das, es gibt nur diesen
Absatz. Aus dem Verzeichnis, in dem die Server nebeneinander liegen:

```bash
sha256sum */scripts/pin_audit.py */tests/test_pin_audit.py |
  awk '{print $1}' | sort | uniq -c
```

Erwartet: **zwei** Zeilen mit je **3**. Die Anzahl mitlesen, nicht nur die Zahl
der Zeilen — findet der Glob nur ein Repo, stehen dort auch zwei Zeilen, und
«einig» hiesse dann bloss, dass nichts verglichen wurde.

**Der SessionStart-Hook steht an drei Stellen.** `swiss-electricity-mcp`,
`bakom-mcp` und `register-mcp` halten byteweise dieselben drei Dateien:
`.claude/hooks/check-clone-freshness.sh`, `.claude/hooks/README.md` und
`tests/test_session_start_hook.py`. Wer eine ändert, ändert alle drei im selben
Commit — sonst driften die Fassungen auseinander, und genau das war der
Ausgangszustand: drei eigenständige Implementierungen mit drei Dateinamen, von
denen eine ohne `timeout` im PATH ungebremst ins Netz ging und die Session
anhalten konnte. `.claude/settings.json` ist bewusst **nicht** Teil der Regel
(dort steht Repo-Eigenes); geprüft wird es stattdessen vom Test, der die
Registrierung des Hooks nachweist.

Kein Gate erzwingt die Gleichheit, es gibt nur diesen Absatz. Aus dem
Verzeichnis, in dem die Server nebeneinander liegen:

```bash
sha256sum */.claude/hooks/check-clone-freshness.sh */.claude/hooks/README.md \
          */tests/test_session_start_hook.py |
  awk '{print $1}' | sort | uniq -c
```

Erwartet: **drei** Zeilen mit je **3**. Die Anzahl mitlesen, nicht nur die Zahl
der Zeilen — findet der Glob nur ein Repo, stehen dort auch drei Zeilen, und
«einig» hiesse dann bloss, dass nichts verglichen wurde.
