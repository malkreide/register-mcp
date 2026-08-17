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

## Teil 2 — Repo-spezifisch (register-mcp)

**ruff: eine Quelle.** Der Pin `0.16.1` steht in `pyproject.toml` und `.pre-
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
seiner Ausgabe: `ruff-Pin 0.16.1 an beiden Stellen gleich`. Wer die zwei
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
