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

2. **Zefix brauchte angeblich Zugangsdaten -- und das war falsch gemessen.**
   Bis zum 2026-08-08 stand hier, die API antworte ohne `ZEFIX_USER` /
   `ZEFIX_PASSWORD` mit HTTP 401, und PROVENANCE.md fuehrte die Zefix-Payloads
   als NICHT AUFGEZEICHNET. Der Messwert stimmte; er galt nur einer anderen
   Adresse als der, die der Server benutzt.

   Es gibt zwei Zefix-APIs unter demselben Host. Dieses Skript fragte
   `ZefixPublicREST` -- das verlangt tatsaechlich Zugangsdaten. Der Server
   spricht mit `ZefixREST` (`ZEFIX_BASE` in `server.py`), und das antwortet
   **ohne jede Anmeldung mit HTTP 200**. Die 401 hat also die Adressliste
   dieses Skripts gemessen, nicht den Zugang zur Quelle.

   Damit das nicht noch einmal auseinanderlaeuft, wird die Basis-URL jetzt aus
   `register_mcp.server` importiert statt hier abgeschrieben. Eine Fixture vom
   falschen Endpunkt belegt die falsche Antwort -- unauffaellig, weil sie
   plausibel aussieht.

Without the retrieval date, "recorded" becomes indistinguishable from
"invented" after two years, because the file looks the same either way.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from register_mcp.server import ZEFIX_BASE as ZEFIX  # noqa: E402

GAZETTE = "https://amtsblattportal.ch/api/v1"

# Die Firma, an der die Zefix-Fixtures haengen. Eine bekannte, langlebige
# Gruppe mit vielen Treffern in mehreren Kantonen -- das braucht es, weil an
# der Streuung der `legalSeatId` einer der Befunde haengt.
ZEFIX_QUERY = "Migros"

REDACTED = "[redigiert — siehe PROVENANCE.md]"

# The complete list of what is emptied, by dotted path inside a publication
# entry. Everything not named here is recorded verbatim.
#
# `meta.title` and `content` are the two free-text carriers: a title reads
# "Konkurseröffnung über <Name>, <Adresse>" and the body spells it out. The
# structural fields around them -- rubric, subRubric, publicationDate, ids --
# are what the server actually branches on, and those stay real.
REDACT_PATHS = ("meta.title", "content")

# Zefix fuehrt in `shabPub[].message` den vollen SHAB-Text: «Eingetragene
# Personen neu oder mutierend: <Name>, von <Ort>, in <Ort>, mit
# Kollektivprokura zu zweien.» Das sind Personendaten, und sie gehoeren nicht
# als Datei in ein oeffentliches Repository. Der Server liest das Feld nicht
# (er nimmt Datum, shabId, Kanton und mutationTypes), aber die Fixture soll die
# Form belegen -- also bleibt der Schluessel und der Wert wird ersetzt.
ZEFIX_REDACT_NOTE = "[redigiert — SHAB-Volltext mit Personendaten, siehe PROVENANCE.md]"


def _redact_shab_messages(firm: dict[str, Any]) -> dict[str, Any]:
    """Copy of ``firm`` with every ``shabPub[].message`` replaced."""
    out = json.loads(json.dumps(firm))
    for pub in out.get("shabPub") or []:
        if pub.get("message") is not None:
            pub["message"] = ZEFIX_REDACT_NOTE
    return out


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

    # 4) Zefix -- oeffentlich, ohne Zugangsdaten. Siehe Modul-Docstring.
    with httpx.Client(timeout=90.0, follow_redirects=True) as c:
        forms = c.get(f"{ZEFIX}/legalForm")
        forms.raise_for_status()
        write(
            "zefix_legal_forms.json",
            json.dumps(forms.json(), ensure_ascii=False, indent=2) + "\n",
            f"{ZEFIX}/legalForm",
            f"vollstaendig, alle {len(forms.json())} Rechtsformen",
        )

        hits = c.post(f"{ZEFIX}/firm/search.json", json={"name": ZEFIX_QUERY})
        hits.raise_for_status()
        search = hits.json()
        seats = {h["legalSeatId"] for h in search["list"]}
        if len(seats) < 3:
            raise SystemExit(
                f"Suche '{ZEFIX_QUERY}' liefert nur {len(seats)} verschiedene "
                "legalSeatId — zu wenig, um die Aufloesung ueber `bfsId` gegen "
                "die ueber `id` zu stellen. Anderen Suchbegriff waehlen."
            )
        write(
            "zefix_search.json",
            json.dumps(search, ensure_ascii=False, indent=2) + "\n",
            f"{ZEFIX}/firm/search.json",
            f"vollstaendig, Firmensuche '{ZEFIX_QUERY}' — {len(search['list'])} "
            f"Treffer aus {len(seats)} verschiedenen Gemeinden. Die Streuung ist "
            "die Auswahlregel: An ihr haengt, dass sich `legalSeatId` ueber "
            "`bfsId` aufloest und nicht ueber `id`",
        )

        ehraid = search["list"][0]["ehraid"]
        detail = c.get(f"{ZEFIX}/firm/{ehraid}.json")
        detail.raise_for_status()
        firm = detail.json()
        if not firm.get("shabPub"):
            raise SystemExit(
                f"Firma {ehraid} hat keine SHAB-Publikationen — dann prueft die "
                "Fixture den Zweig nicht, der sie aufbereitet."
            )
        redacted = _redact_shab_messages(firm)
        write(
            "zefix_firm_detail.json",
            json.dumps(redacted, ensure_ascii=False, indent=2) + "\n",
            f"{ZEFIX}/firm/{ehraid}.json",
            f"vollstaendig, Firma {ehraid} ({firm['name']}), "
            f"{len(firm['shabPub'])} SHAB-Publikationen. **Redigiert:** Das Feld "
            "`shabPub[].message` nennt eingetragene Personen mit Wohnort; der "
            "Text ist ersetzt, die Struktur bleibt",
        )

        comm = c.get(f"{ZEFIX}/community")
        comm.raise_for_status()
        communities = comm.json()
        # Alle Gemeinden der Kantone, in denen die Treffer sitzen, plus die
        # Gemeinden zu jeder vorkommenden legalSeatId. Ein Zuschnitt nach
        # Position haette hier genau den Befund verdeckt: Erst wenn `id` und
        # `bfsId` derselben Gemeinde ungleich sind UND beide Zahlen im
        # Wertebereich der anderen liegen, faellt die Verwechslung auf.
        wanted_bfs = {h["legalSeatId"] for h in search["list"]}
        by_bfs = {x["bfsId"] for x in communities}
        missing = sorted(wanted_bfs - by_bfs)
        if missing:
            raise SystemExit(
                f"legalSeatId {missing} kommt in keiner `bfsId` vor — die "
                "Annahme, dass legalSeatId eine BFS-Nummer ist, traegt nicht mehr."
            )
        keep_ids = wanted_bfs | {x["id"] for x in communities if x["bfsId"] in wanted_bfs}
        excerpt = [x for x in communities if x["bfsId"] in wanted_bfs or x["id"] in keep_ids]
        collisions = [x for x in excerpt if x["id"] == x["bfsId"]]
        if collisions:
            raise SystemExit(
                f"{len(collisions)} Gemeinden mit id == bfsId im Zuschnitt — an "
                "denen laesst sich die Verwechslung nicht zeigen, sie gehoeren "
                "geprueft."
            )
        write(
            "zefix_communities.json",
            json.dumps(sorted(excerpt, key=lambda x: x["name"]), ensure_ascii=False, indent=2)
            + "\n",
            f"{ZEFIX}/community",
            f"{len(excerpt)} von {len(communities)} Gemeinden: zu jeder in der "
            "Suche vorkommenden `legalSeatId` die Gemeinde mit dieser `bfsId` "
            "UND die mit dieser `id`. Nach Merkmal ausgewaehlt, nicht nach "
            "Position — nur so stehen beide Kandidaten einer Verwechslung "
            "nebeneinander in der Datei",
        )

        empty = c.post(f"{ZEFIX}/firm/search.json", json={"name": "Zzzqqxyznichtexistent"})
        if empty.status_code != 404:
            raise SystemExit(
                f"Eine Suche ohne Treffer antwortet mit HTTP {empty.status_code}, "
                "nicht 404 — dann belegt die Fixture den Befund nicht mehr."
            )
        write(
            "zefix_no_result.json",
            json.dumps(
                {"status_code": empty.status_code, "body": empty.json()},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            f"{ZEFIX}/firm/search.json (Name ohne Treffer)",
            "Statuscode UND Rumpf, weil beides zusammen den Befund ausmacht: "
            "Die Quelle antwortet mit **404**, nicht mit 200 — der freundliche "
            "Zweig fuer «keine Ergebnisse» war damit unerreichbar",
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
