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
PR ohne jeden Check ist selten ein Repo ohne CI, meistens ein
Merge-Konflikt: GitHub berechnet dafür keinen Merge-Commit und startet nichts.
Ein Codex-Review auf einem PR wird beantwortet oder behoben, nie ignoriert.

### Wenn Codex gar nicht erst hinsieht

Die Zeile oben unterstellt, dass es einen Befund geben *kann*. Das ist nicht
immer so, und man sieht es dem PR nicht an.

Am 21.8.2026 war das Code-Review-Kontingent zwischen 08:41 und 09:48
aufgebraucht — davor echte Reviews, danach in 30 Repos nur noch:

```
You have reached your Codex usage limits for code reviews.
```

Belegt gesperrt war es dann **mindestens 25 Stunden** — von 21.8. 09:48 bis zur
letzten beobachteten Limit-Meldung am 22.8. um 11:03. Die Obergrenze liegt bei
46½ Stunden: Am 23.8. um 08:22 kam eine *andere* Meldung, dazwischen liegen 21
Stunden ohne einen einzigen Codex-Auslöser, in denen schlicht niemand gemessen
hat. Wer die Sperre auf «gut einen Tag» rundet, verwechselt die belegte
Untergrenze mit der Dauer. In der Zwischenzeit sind 32 PRs mit formal erfülltem
Häkchen gemergt worden, ohne dass jemand hineingesehen hat, und am 22.8. noch
einmal 43.

**Vier** Gründe, warum Codex schweigt, und nur einer davon ist harmlos:

- **Kein Befund** — dann reagiert er mit 👍 und schreibt nichts.
- **Der PR ist ein Draft** — darauf läuft Codex nicht an.
- **Das Kontingent ist weg** — dann schreibt er die Meldung oben.
- **Für das Repo fehlt eine Environment** — dann schreibt er:

  ```
  To use Codex here, create an environment for this repo.
  ```

Der vierte kam erst zum Vorschein, als der dritte wegfiel, und das ist kein
Zufall: Die Prüfungen liegen hintereinander. Dass es diese Reihenfolge ist und
nicht die umgekehrte, lässt sich an einem einzigen Repo ablesen — in
`swiss-public-data-mcp` bekam PR #54 am 22.8. um 10:56:55 die Kontingent-Meldung
und PR #56 am 23.8. um 08:22:20 die Environment-Meldung. Läge die
Environment-Prüfung vorn, hätte #54 sie schon am Vortag gesehen; die Environment
fehlte ja bereits. Zwei Meldungen aus demselben Repo schlagen hier jede
Vermutung über die Reihenfolge.

Praktisch heisst das: **Eine verschwundene Limit-Meldung ist keine Entwarnung.**
Sie kann bedeuten, dass das Kontingent wieder da ist — und dass jetzt etwas
anderes den Review verhindert. Erst ein Review-Objekt belegt, dass geprüft
wurde.

«Kein Kommentar» heisst also nicht «geprüft und sauber». Unterscheiden lässt es
sich an der Form: Ein echter Review ist ein Review-Objekt («💡 Codex Review»,
mit Commit-Angabe), jede Ausrede dagegen ein gewöhnlicher Issue-Kommentar. Das
sind zwei verschiedene Abfragen — `get_reviews` gegen `get_comments`; wer nur
eine davon nimmt, übersieht die andere Hälfte. Genau so ist die Limit-Meldung
zuerst durchgerutscht.

Der Kommentarzähler allein reicht nicht mehr: `comments: 1` kann die
Kontingent- **oder** die Environment-Meldung sein. Den Text lesen, nicht die
Zahl. Und einen unbekannten dritten Text wörtlich zitieren, statt ihn in eine
der bekannten Schubladen zu zwingen — dieser Abschnitt musste schon einmal von
drei auf vier Gründe wachsen.

Portfolio-weit nachsehen:

```
search_pull_requests: user:malkreide commenter:chatgpt-codex-connector[bot] updated:>=<Datum>
```

Findet nur, wo er *kommentiert* hat. Repos ohne PR-Aktivität tauchen nicht auf
— das ist kein Beleg, dass dort geprüft wurde.

Zweiter Weg, den Prüfer zu verlieren, ganz ohne Kontingentproblem: zu schnell
mergen. Am 21./22.8. lagen zwischen «ready for review» und Merge mehrfach drei
bis fünf Sekunden. Codex wird beim Umschalten von Draft auf ready ausgelöst und
braucht danach Zeit; wer sofort mergt, hat das Häkchen gesetzt und den Review
nicht abgewartet.

Das Kontingent hängt am Konto, nicht am Repo, und Code-Reviews haben einen
eigenen Topf — nur GitHub-getriggerte Reviews zählen hinein. ChatGPT-Pläne
fahren ein rollendes Fünf-Stunden-Fenster plus Wochenlimits; welches greift,
steht im Codex-Dashboard. Die 25 belegten Stunden oben schliessen das
Fünf-Stunden-Fenster als bindende Grenze aus; ob das Wochenlimit griff oder
etwas anderes, ist damit *nicht* geklärt — eine Sperre, die länger dauert als
das kürzeste Fenster, sagt nur, dass es dieses nicht war.

Zeigt das Dashboard freies Kontingent, während Reviews weiter scheitern, ist
das ein bekannter Fehler bei mehreren verbundenen Konten — dann den
GitHub-Connector in den Codex-Einstellungen trennen und neu verbinden. Die
Environment legt man unter `chatgpt.com/codex/cloud/settings/environments` an;
ob eine je Repo nötig ist oder eine fürs Konto genügt, ist offen und zeigt sich
erst am nächsten PR nach dem Anlegen.

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

**ruff: eine Quelle.** Der Pin `0.16.3` steht in `pyproject.toml` und `.pre-
commit-config.yaml` — und **nicht** mehr als eigener Install-Schritt in der
CI.

Der CI-Schritt lief nach dem Install der Abhängigkeiten und überschrieb sie.
Eine Abweichung im Pin konnte deshalb in der CI gar nicht auffallen, sondern
nur lokal — wo niemand sie erwartet. Ein manuelles Nachinstallieren von ruff
vor den Gates ist damit nicht mehr nötig und wäre schädlich: Es würde eine
spätere Anhebung hier stillschweigend überstimmen.

`scripts/check_version_sync.py` bricht ab, wenn die verbleibenden Stellen
auseinanderlaufen **oder** wenn `ci.yml` wieder ein eigenes ruff installiert;
`tests/test_precommit_config.py` wacht darüber, dass der Hook denselben Umfang
sieht wie das Gate.

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
seiner Ausgabe: `ruff-Pin 0.16.3 an beiden Stellen gleich`. Wer die zwei
Stellen von Hand vergleicht, tut Arbeit, die dieser Gate schon leistet.

**Was die Live-Suite fand, waren keine Ausfälle, sondern Antworten.** Drei
Formen von Zefix, jede hat einen ausgelieferten Fehler gekostet:

- Ohne Treffer antwortet `firm/search.json` mit **HTTP 404** plus
  NORESULT-Rumpf. Deshalb jeder Aufruf über `_zefix_post_search` — und eine
  Fixture, die den Rumpf in eine 200 legt, lässt den toten Zweig grün aussehen.
- Mit Treffern ist es noch keine Antwort: `searchType: CONTAINS` sucht über den
  Namen, `CHE-999.999.999` liefert «CHEMAM - 999». Kein Rückfall auf `firms[0]`.
- Ohne `activeOnly: False` sieht «gelöscht» aus wie «gibt es nicht».

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
