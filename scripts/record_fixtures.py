#!/usr/bin/env python3
"""Records the unit-test fixtures from the live upstream sources.

    python scripts/record_fixtures.py

WHY THIS EXISTS. A hand-written mock encodes its author's assumption and can
therefore never refute it: production code and fixture come from the same head,
the same hour, the same reading of the docs. Where both are wrong, both are
wrong together, and the suite stays green forever.

TWO THINGS MAKE THIS REPOSITORY A SPECIAL CASE, and both are stated in
``tests/fixtures/PROVENANCE.md`` rather than papered over.

1. **Personendaten.** The gazette carries `SB` (Schuldbetreibungen) and `LS`
   (Schuldenrufe) -- debt collection and calls to creditors -- and the free-text
   body of a publication names natural persons with their addresses. Committing
   a verbatim response into a public repository would republish that. So the
   recorded payloads keep the **shape** (keys, nesting, types, and the codes the
   server branches on) and redact the **values** of the fields that can carry
   personal data. `REDACT_PATHS` below is the complete list, and PROVENANCE.md
   repeats it: a fixture that quietly said less than it appears to would be the
   very failure this whole exercise is against.

2. **Zefix needs credentials** (`ZEFIX_USER` / `ZEFIX_PASSWORD`). Without them
   the API answers 401, and this script records nothing for it rather than
   dating a payload it never fetched. PROVENANCE.md marks those fixtures as
   NOT RECORDED, which is the honest state -- not an omission to be tidied away.

Without the retrieval date, "recorded" becomes indistinguishable from
"invented" after two years, because the file looks the same either way.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

GAZETTE = "https://amtsblattportal.ch/api/v1"
ZEFIX = "https://www.zefix.admin.ch/ZefixPublicREST/api/v1"
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

REDACTED = "[redigiert — siehe PROVENANCE.md]"

# The complete list of what is emptied, by dotted path inside a publication
# entry. Everything not named here is recorded verbatim.
#
# `meta.title` and `content` are the two free-text carriers: a title reads
# "Konkurseröffnung über <Name>, <Adresse>" and the body spells it out. The
# structural fields around them -- rubric, subRubric, publicationDate, ids --
# are what the server actually branches on, and those stay real.
REDACT_PATHS = ("meta.title", "content")


def _redact(entry: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(entry))  # deep copy
    for path in REDACT_PATHS:
        node, *rest = path.split(".")
        target, key = out, node
        for part in rest:
            if not isinstance(target.get(key), dict):
                break
            target, key = target[key], part
        if key not in target:
            continue
        value = target[key]
        if isinstance(value, dict):
            target[key] = {k: REDACTED for k in value}
        elif value is not None:
            target[key] = REDACTED
    return out


def record() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    recorded_at = datetime.now(UTC).strftime("%Y-%m-%d")
    entries: list[dict] = []
    skipped: list[dict] = []

    def write(name: str, text: str, url: str, rule: str) -> None:
        (FIXTURES / name).write_text(text, encoding="utf-8")
        entries.append(
            {
                "name": name,
                "url": url,
                "rule": rule,
                "bytes": len(text.encode("utf-8")),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
        print(f"ok  {name:<24} {len(text.encode('utf-8')):>7} B")

    with httpx.Client(timeout=90.0, follow_redirects=True) as c:
        # 1) The rubric catalogue. No personal data -- it is a code list.
        r = c.get(f"{GAZETTE}/rubrics")
        r.raise_for_status()
        rubrics = r.json()
        keep_codes = {"HR", "SB", "LS", "OB-AR", "OB-BS", "OB-TI", "OB-ZG"}
        kept = [x for x in rubrics if x.get("code") in keep_codes]
        missing = keep_codes - {x.get("code") for x in kept}
        if missing:
            raise SystemExit(
                f"rubrics: {sorted(missing)} no longer in the catalogue -- the "
                "tests validate rubric codes against it, adjust keep_codes"
            )
        write(
            "gazette_rubrics.json",
            json.dumps(kept, ensure_ascii=False, indent=2) + "\n",
            f"{GAZETTE}/rubrics",
            f"unveraendert, die {len(kept)} von {len(rubrics)} Rubriken, gegen "
            "die die Tests validieren; keine Personendaten (reine Codeliste)",
        )

        # 2) A publications search. Shape real, personal-data values redacted.
        params = {
            "publicationStates": "PUBLISHED",
            "rubrics": "HR",
            "pageRequest.size": "2",
        }
        r = c.get(f"{GAZETTE}/publications", params=params, headers={"Accept": "application/json"})
        r.raise_for_status()
        payload = r.json()
        if not payload.get("content"):
            raise SystemExit("publications: empty content -- cannot record a shape from nothing")
        payload["content"] = [_redact(e) for e in payload["content"]]
        write(
            "gazette_search.json",
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            f"{GAZETTE}/publications?{'&'.join(f'{k}={v}' for k, v in params.items())}",
            f"Huelle und Struktur unveraendert; die Werte unter "
            f"{', '.join(REDACT_PATHS)} redigiert (Personendaten). "
            f"`total` ist der echte Bestandswert von diesem Tag",
        )

        # 3) The corpus total on its own -- the number the Quirk-1 plausibility
        #    check compares against. It drifts, so it is recorded, not written
        #    down: the old fixture said 2_790_323 and the source had moved on.
        r = c.get(
            f"{GAZETTE}/publications",
            params={"publicationStates": "PUBLISHED", "pageRequest.size": "1"},
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        total = r.json().get("total")
        write(
            "gazette_corpus_total.json",
            json.dumps({"total": total}, indent=2) + "\n",
            f"{GAZETTE}/publications (ungefiltert, size=1)",
            "nur der Gesamtbestand — die Zahl, gegen die die Quirk-1-Pruefung "
            "vergleicht; sie waechst taeglich und gehoert deshalb aufgezeichnet",
        )

    # 4) Zefix -- only with credentials. No credentials, no fixture, and the
    #    absence is recorded as such.
    user, password = os.environ.get("ZEFIX_USER"), os.environ.get("ZEFIX_PASSWORD")
    if not (user and password):
        skipped.append(
            {
                "name": "zefix_*.json",
                "url": f"{ZEFIX}/company/search",
                "why": "ZEFIX_USER/ZEFIX_PASSWORD nicht gesetzt — die API "
                "antwortet ohne sie mit HTTP 401. NICHT aufgezeichnet.",
            }
        )
        print("--  zefix_*.json          uebersprungen (keine Zugangsdaten)")
    else:
        with httpx.Client(timeout=90.0, auth=(user, password)) as c:
            r = c.post(f"{ZEFIX}/company/search", json={"name": "Migros"})
            r.raise_for_status()
            write(
                "zefix_search.json",
                json.dumps(r.json(), ensure_ascii=False, indent=2) + "\n",
                f"{ZEFIX}/company/search",
                "Firmensuche 'Migros'; juristische Personen, oeffentliches Handelsregister",
            )

    _write_provenance(recorded_at, entries, skipped)
    print(f"\nPROVENANCE.md written, recording date {recorded_at}")
    return 0


def _write_provenance(recorded_at: str, entries: list[dict], skipped: list[dict]) -> None:
    lines = [
        "# Herkunft der Fixtures",
        "",
        "**Erzeugt von `scripts/record_fixtures.py`. Nicht von Hand pflegen.**",
        "",
        f"Aufgezeichnet am **{recorded_at}** von `{GAZETTE}`.",
        "",
        "Ohne Datum ist «aufgezeichnet» nach zwei Jahren von «ausgedacht» nicht",
        "mehr zu unterscheiden — die Datei sieht gleich aus.",
        "",
        "## Redaktion — was diese Fixtures NICHT belegen",
        "",
        "Das Amtsblatt fuehrt `SB` (Schuldbetreibungen) und `LS` (Schuldenrufe);",
        "der Freitext einer Publikation nennt natuerliche Personen mit Adresse.",
        "Eine woertliche Antwort in einem **oeffentlichen** Repo waere eine",
        "Republikation dieser Daten. Deshalb ist die **Struktur** echt — Schluessel,",
        "Verschachtelung, Typen und die Codes, auf die der Server verzweigt —,",
        "und die **Werte** der folgenden Felder sind ersetzt:",
        "",
    ]
    lines += [f"- `{p}`" for p in REDACT_PATHS]
    lines += [
        "",
        f"Ersatzwert: `{REDACTED}`. Alles, was hier nicht steht, ist woertlich",
        "aufgezeichnet. Eine Fixture, die stillschweigend weniger belegt, als sie",
        "aussieht, waere genau der Fehler, gegen den diese Aufzeichnung angeht.",
        "",
    ]
    if skipped:
        lines += ["## NICHT aufgezeichnet", ""]
        for s in skipped:
            lines += [
                f"### `{s['name']}`",
                "",
                f"- **Quelle:** `{s['url']}`",
                f"- **Grund:** {s['why']}",
                "",
            ]
        lines += [
            "Diese Payloads stehen weiterhin als Literale im Testmodul. Sie sind",
            "damit **ausgedacht** und tragen kein Datum — das ist der Ist-Zustand",
            "und keine Nachlaessigkeit dieses Laufs. Wer Zugangsdaten hat, setzt",
            "`ZEFIX_USER`/`ZEFIX_PASSWORD` und laesst das Skript erneut laufen.",
            "",
        ]
    for e in entries:
        lines += [
            f"## `{e['name']}`",
            "",
            f"- **Quelle:** `{e['url']}`",
            f"- **Aufgezeichnet:** {recorded_at}",
            f"- **Auswahl:** {e['rule']}",
            f"- **Groesse:** {e['bytes']} B",
            f"- **SHA-256:** `{e['sha256']}`",
            "",
        ]
    (FIXTURES / "PROVENANCE.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    try:
        raise SystemExit(record())
    except httpx.HTTPError as exc:
        print(f"ERROR: upstream unreachable: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
