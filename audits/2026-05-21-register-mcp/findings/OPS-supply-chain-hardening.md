## Finding: OPS — Supply-Chain-Härtung fehlt (Lockfile, Dependabot, SECURITY.md)

**Severity:** medium
**Status:** open
**Server:** register-mcp
**Check-Reference:** OPS (Anhang C — Operative Praxis)
**PDF-Reference:** Anhang C2 (Repo-Härtung)

### Observed Behavior
Fehlende Artefakte für reproduzierbare & gepatchte Builds:
- Kein `uv.lock` / `poetry.lock` / `requirements.lock` → Floating Dependencies
- Kein `.github/dependabot.yml` → CVE-Updates nicht automatisiert
- Keine `SECURITY.md` → Disclosure-Pfad fehlt
- Kein `CODEOWNERS` → Review-Pflicht nicht erzwingbar
- `pyproject.toml`: nur `>=`-Constraints (`mcp[cli]>=1.0.0`, `httpx>=0.27.0`)

### Expected Behavior
Ein production-tauglicher MCP-Server in der öffentlichen Verwaltung braucht
mindestens: Lock-File, Dependabot, SECURITY.md, CODEOWNERS.

### Evidence
- `ls poetry.lock uv.lock` → not found
- `ls .github/dependabot.yml SECURITY.md .github/CODEOWNERS` → not found
- `pyproject.toml:31-35` → nur Lower-Bounds

### Risk Description
- **Reproducibility:** Build heute ≠ Build in 3 Monaten → Audit-Trail bricht
- **CVE-Exposure:** Keine automatische Benachrichtigung bei vulnerable Versionen
- **Disclosure:** Security-Researcher wissen nicht, wohin sie Findings melden

### Remediation
1. `uv lock` ausführen, `uv.lock` committen
2. `.github/dependabot.yml`:
   ```yaml
   version: 2
   updates:
     - package-ecosystem: pip
       directory: /
       schedule: { interval: weekly }
     - package-ecosystem: github-actions
       directory: /
       schedule: { interval: monthly }
   ```
3. `SECURITY.md` mit Kontakt + Response-SLA
4. `.github/CODEOWNERS` für `/src/` und `/.github/`

### Effort Estimate
S (< 1d, alles Routine)
