# Mitwirken an register-mcp

[🇬🇧 English Version](CONTRIBUTING.md)

Vielen Dank für dein Interesse an einer Mitwirkung! Dieser Server ist Teil des [Swiss Public Data MCP Portfolios](https://github.com/malkreide).

---

## Probleme melden

Nutze [GitHub Issues](https://github.com/malkreide/register-mcp/issues), um Fehler zu melden oder Funktionen vorzuschlagen.

Bitte gib an:
- Python-Version und Betriebssystem
- Vollständige Fehlermeldung oder Beschreibung des unerwarteten Verhaltens
- Schritte zur Reproduktion

---

## Pull Requests

1. Repository forken
2. Feature-Branch erstellen: `git checkout -b feat/dein-feature`
3. Änderungen vornehmen und Tests ergänzen
4. Sicherstellen, dass alle Tests bestehen: `PYTHONPATH=src pytest tests/ -m "not live"`
5. Mit [Conventional Commits](https://www.conventionalcommits.org/) committen: `feat: add new tool`
6. Pushen und einen Pull Request gegen `main` öffnen

---

## Code-Stil

- Python 3.11+
- [Ruff](https://github.com/astral-sh/ruff) für Linting und Formatierung
- Type Hints für alle öffentlichen Funktionen erforderlich
- Tests für neue Tools erforderlich (`tests/test_server.py`)
- Den bestehenden FastMCP-/Pydantic-v2-Mustern in `server.py` folgen

---

## Datenquellen

Dieser Server nutzt die Zefix REST API — ohne Authentifizierung (Phase 1):

| Quelle | Dokumentation |
|--------|--------------|
| Zefix (Handelsregister) | [zefix.admin.ch](https://www.zefix.admin.ch/) |
| SHAB | In Zefix-Firmendatensätzen eingebettet |

Beim Hinzufügen neuer Datenquellen gilt das **No-Auth-First**-Prinzip: Phase 1 nutzt ausschliesslich offene, authentifizierungsfreie Endpunkte. Authentifizierte APIs werden in späteren Phasen mit Graceful Degradation eingeführt.

### Phase 2 (ZefixPublicREST)

Um an Phase 2 zu arbeiten, fordere API-Zugangsdaten an: E-Mail an `zefix@bj.admin.ch` mit deinem Namen, deiner Organisation und dem geplanten Verwendungszweck. Zugangsdaten via Umgebungsvariablen hinterlegen: `ZEFIX_USER` und `ZEFIX_PASSWORD`.

---

## Lizenz

Mit deinem Beitrag erklärst du dich einverstanden, dass deine Beiträge unter der [MIT-Lizenz](LICENSE) lizenziert werden.
