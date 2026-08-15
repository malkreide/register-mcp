# CLAUDE.md

## Teil 1 — Portfolio-weite Konventionen

### Vor der Arbeit

Klon-Aktualität prüfen: `git fetch origin main && git rev-list --count HEAD..origin/main`
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

**ruff-Pin: nur in der CI.** `.pre-commit-config.yaml` existiert nicht — es gibt
keinen zweiten Pin, der abweichen könnte, aber auch kein lokales Gate. Die CI
installiert `ruff==0.16.1` (`.github/workflows/ci.yml`), `pyproject.toml [dev]`
erlaubt dagegen `ruff>=0.15.22,<0.17`. `pip install -e ".[dev]"` gibt dir also
nicht zwingend die CI-Version — vor dem Lint explizit `pip install ruff==0.16.1`.

**Gate-Befehle, wörtlich aus `ci.yml`** (Job `test`, Python 3.11/3.12/3.13):

```bash
pip install -e ".[dev]"
PYTHONPATH=src pytest tests/ -m "not live"
pip install ruff==0.16.1
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/
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
