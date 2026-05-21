## Finding: SEC-007 — Kein Container / Sandbox für Cloud-Deployment

**Severity:** critical
**Status:** open
**Server:** register-mcp
**Check-Reference:** SEC-007
**PDF-Reference:** Hauptkatalog Sec 4 / Anhang B3 (Sandbox)

### Observed Behavior
Kein `Dockerfile`, kein `docker-compose.yml`, kein WASM-/Container-Build im Repo.
`ls Dockerfile*` → not found. `pyproject.toml` definiert nur `register-mcp = "register_mcp.server:mcp.run"`
als Console-Script.

Das README beschreibt aber explizit Railway-/Cloud-Deployment (`MCP_TRANSPORT=sse PORT=8000`),
d.h. der Server läuft in fremden Umgebungen ohne dokumentierte Isolation.

### Expected Behavior
Gemäss SOLID-Prinzip **S**andbox aus dem Skill: jeder Server, der in Cloud-Umgebungen
deployed wird, muss eine reproduzierbare Container-Image-Definition mitliefern, die:
- minimale Base-Image (`python:3.13-slim` o.ä.)
- Non-root-User
- Read-only Filesystem
- Egress-Beschränkung dokumentiert (nur `zefix.admin.ch`)

### Evidence
- Repo-Root: keine Container-Files
- README.md "Deployment"-Sektion zeigt direkten `python -m register_mcp.server`-Call
- `.github/workflows/publish.yml` publiziert nur PyPI-Wheel, kein Image

### Risk Description
Ohne Container kann der Operator nicht:
- Egress-Filter wirksam durchsetzen (Layer 5 im Defense-in-Depth-Modell)
- Dependencies reproduzierbar pinnen (kein `uv.lock` + Dockerfile → drift)
- Privilege Escalation eindämmen
- Resource-Limits (CPU/RAM) deklarativ erzwingen

### Remediation
Minimaler `Dockerfile`:
```dockerfile
FROM python:3.13-slim
WORKDIR /app
RUN adduser --disabled-password --gecos "" mcp
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .
USER mcp
ENV MCP_TRANSPORT=sse PORT=8000
EXPOSE 8000
CMD ["python", "-m", "register_mcp.server"]
```

Plus `uv.lock` / `requirements.txt` für deterministische Builds und `.github/workflows/`
Container-Build via `docker/build-push-action`.

### Effort Estimate
M (1-3d) — Dockerfile, Lock-File, CI-Workflow, README-Update
