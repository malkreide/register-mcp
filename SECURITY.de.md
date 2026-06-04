# Sicherheitsrichtlinie

[🇬🇧 English Version](SECURITY.md)

## Unterstützte Versionen

`register-mcp` ist vor 1.0; nur der aktuelle `main`-Stand und das jüngste
getaggte Release erhalten Sicherheitsfixes.

| Version    | Unterstützt        |
| ---------- | ------------------ |
| `main`     | :white_check_mark: |
| `0.1.x`    | :white_check_mark: |
| `< 0.1`    | :x:                |

## Eine Schwachstelle melden

Bitte melde Sicherheitsprobleme **privat**, nicht über öffentliche GitHub Issues.

- Erstelle ein [GitHub Security Advisory](https://github.com/malkreide/register-mcp/security/advisories/new) — bevorzugt.
- Oder schreibe dem Maintainer eine E-Mail (siehe das GitHub-Profil von [@malkreide](https://github.com/malkreide)).

Wenn möglich, bitte angeben:

- Eine Beschreibung des Problems und seiner Auswirkungen
- Schritte zur Reproduktion oder einen Proof-of-Concept
- Die betroffene Version / den Commit-SHA
- Allfällige Vorschläge zur Behebung

## Reaktionsziele

| Schritt             | Ziel                  |
| ------------------- | --------------------- |
| Bestätigung         | innerhalb von 5 Arbeitstagen |
| Triage & Schweregrad| innerhalb von 10 Arbeitstagen |
| Fix oder Mitigation | nach bestem Bemühen; kritische Probleme werden priorisiert |

## Geltungsbereich

Dieses Repository liefert einen MCP-Server, der aus der öffentlichen Zefix REST API liest.
Im Geltungsbereich sind:

- Das Python-Paket `register_mcp` (Server, Middleware, Logging)
- Das veröffentlichte Docker-Image
- CI-Workflows unter `.github/workflows/`

Ausserhalb des Geltungsbereichs:

- Zefix-seitiges API-Verhalten oder Datenqualität (an `zefix@bj.admin.ch` melden)
- Probleme, die nur in einem Fork mit modifizierter Middleware / entfernter Auth reproduzierbar sind
- Findings in Abhängigkeiten — bitte beim Upstream-Projekt melden; wir patchen
  wöchentlich via Dependabot.

## Hardening-Hinweise für Betreiber

Beim öffentlichen Betrieb des SSE-Transports gilt zusätzlich zum eingebauten
`MCP_API_KEY` + Rate Limit:

1. Setze ein echtes Gateway (Cloudflare Access, Railway Internal Networking,
   API-Gateway) vor den Container.
2. Beschränke den Egress auf `www.zefix.admin.ch:443` auf Netzwerkebene.
3. Rotiere `MCP_API_KEY` nach Zeitplan und bei Personalwechseln.
4. Leite die JSON-Logs an ein SIEM weiter und alarmiere bei anhaltenden
   `auth_failed`- oder `rate_limited`-Ereignissen.
