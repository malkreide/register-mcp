## Finding: SEC-021 — Egress-Control nicht erzwungen

**Severity:** medium
**Status:** open
**Server:** register-mcp
**Check-Reference:** SEC-021
**PDF-Reference:** Anhang B6 (Egress-Filter)

### Observed Behavior
Die Outbound-URLs sind im Code hartkodiert auf `zefix.admin.ch`
(`src/register_mcp/server.py:34-35`), was SSRF strukturell ausschliesst — gut.
Aber: es gibt keine Network-Policy / kein `--network`-Constraint, das den Container
faktisch nur zu `zefix.admin.ch` lässt. Da auch kein Dockerfile existiert (SEC-007),
ist Egress-Control nicht erzwingbar.

### Expected Behavior
Defense-in-Depth: zusätzlich zur Code-Härtung soll der Operator den Server in einer
Network-Policy laufen lassen, die nur DNS + `zefix.admin.ch:443` outbound zulässt.

### Evidence
- `server.py:34,35`: hardcoded base URLs → strukturell SSRF-resistent ✓
- Keine `httpx.Mount`/Allow-List-Konfiguration ✗
- Kein Dockerfile mit egress-restricted Netzwerk ✗
- README: keine Operator-Doku zu Egress-Setup

### Risk Description
Wenn eine Supply-Chain-Compromise (vergiftete `httpx`-Version oder Dependency) eine
neue URL einschleust, gibt es keinen zweiten Layer der das stoppt.

### Remediation
1. README-Sektion «Operator-Setup» mit Beispiel-Network-Policy
2. In `Dockerfile` (siehe SEC-007) ggf. `iptables`-Rule oder Container-Network bauen
3. Optional: Allow-List-Check in `_make_client()` einbauen:
   ```python
   ALLOWED_HOSTS = {"www.zefix.admin.ch"}
   # in transport-hook prüfen URL.host in ALLOWED_HOSTS
   ```

### Effort Estimate
S (Doku) + M (wenn aktiv durchgesetzt)
