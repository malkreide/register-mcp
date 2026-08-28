"""
Die Labels aus `.github/dependabot.yml` gegen die Labels des Repos prüfen.

Dependabot wendet die unter `labels:` genannten Namen nur an, wenn es sie im
Repo schon gibt — anlegen tut es sie nicht. Fehlt eines, hängt Dependabot
stattdessen einen Kommentar an jeden Pull Request:

    The following labels could not be found: `dependencies`, `python`.
    Please create them before Dependabot can add them to a pull request.

Das ist der ganze Ausfall: kein roter Check, kein Log, nur eine Zeile in einem
PR, den niemand daraufhin liest. In diesem Repo standen so über Monate **vier**
nicht existierende Labels in der Konfiguration, und aufgefallen ist es erst,
als jemand die Kommentare eines Dependabot-PRs von Hand durchgegangen ist.

Die Meldung nennt dabei immer nur die Labels des betroffenen Ökosystems. Wer
sie als vollständige Liste liest, legt zwei Labels an und hält die Sache für
erledigt, während die der anderen Ökosysteme weiter fehlen — sichtbar erst
beim nächsten `github-actions`- oder `docker`-PR, also womöglich Wochen
später. Deshalb liest dieses Skript die Konfiguration und nicht die Meldung.

ZWEI MODI, UND NUR EINER BRAUCHT NETZ
-------------------------------------
Ohne `--repo` werden die geforderten Labels bloss aufgelistet. Das läuft
offline und ist der Modus, den die Tests fahren.

Mit `--repo OWNER/NAME` wird zusätzlich die GitHub-API gefragt und verglichen;
Exit 1, wenn eines fehlt. Dieser Modus gehört **nicht** in `ci.yml`: Ein Gate,
das bei einem API-Ausfall oder einem erschöpften Rate-Limit rot wird, macht
Pull Requests rot, die damit nichts zu tun haben — und ein Gate, das aus
fremden Gründen rot wird, wird abgeschaltet.

Verwendung:
    python scripts/check_dependabot_labels.py                    # nur auflisten
    python scripts/check_dependabot_labels.py --repo malkreide/register-mcp

`GITHUB_TOKEN` wird benutzt, wenn gesetzt — ohne Token greift das knappe
Limit für nicht angemeldete Zugriffe (60 Anfragen pro Stunde und IP).

Bewusst nur Standardbibliothek, und bewusst kein `pyyaml`: Das ist keine
Projekt-Abhängigkeit, und `tests/test_precommit_config.py` liest die
pre-commit-Konfiguration aus demselben Grund als Text.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPENDABOT = ROOT / ".github" / "dependabot.yml"

API = "https://api.github.com"

# Eine neue Liste `- package-ecosystem: uv`. Der Bindestrich ist Teil der
# Zusicherung: Er trennt die Einträge unter `updates:`, und ohne ihn würde ein
# `package-ecosystem`-Schlüssel irgendwo tiefer im Baum einen Block eröffnen.
_ECOSYSTEM = re.compile(r"^(\s*)-\s*package-ecosystem:\s*(\S+)\s*$")

# `labels: [a, b]` auf einer Zeile.
_LABELS_INLINE = re.compile(r"^\s*labels:\s*\[([^\]]*)\]\s*$")

# `labels:` allein — die Namen stehen dann als `- a` in den Folgezeilen.
_LABELS_BLOCK = re.compile(r"^(\s*)labels:\s*$")

_LIST_ITEM = re.compile(r"^(\s*)-\s*(.+?)\s*$")


def strip_comments(text: str) -> str:
    """Zeilenkommentare entfernen, Anführungszeichen dabei respektieren.

    Ein nacktes `re.sub(r"#.*", "", …)` wäre hier falsch: `dependabot.yml`
    trägt in diesem Repo einen langen Kopfkommentar, in dem unter anderem
    «PRs #26–#30» steht. Das ist harmlos, weil die ganze Zeile Kommentar ist —
    aber ein `#` innerhalb eines Wertes (`prefix: "deps # dev"`) wäre es nicht,
    und ein Parser, der den Unterschied nicht kennt, schneidet still Werte ab.
    """
    out = []
    for line in text.splitlines():
        quote = None
        cut = None
        for i, ch in enumerate(line):
            if quote is not None:
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "#":
                # Ein `#` zählt nur als Kommentar, wenn es am Zeilenanfang
                # steht oder Leerraum davor liegt. Sonst ist es Teil eines
                # unquotierten Wertes (`color: #ff0000`).
                if i == 0 or line[i - 1].isspace():
                    cut = i
                    break
        # Beim Schneiden auch den Leerraum vor dem `#` weg: er ist der Trenner
        # des Kommentars, nicht Teil des Wertes. Zeilen ohne Kommentar bleiben
        # unangetastet — diese Funktion entfernt Kommentare, sie formatiert nicht.
        out.append(line if cut is None else line[:cut].rstrip())
    return "\n".join(out)


def labels_in_dependabot(text: str) -> list[tuple[str, str]]:
    """`(ökosystem, label)` für jede Nennung, in Reihenfolge der Datei.

    Doppelte Nennungen bleiben erhalten: `dependencies` steht hier dreimal,
    einmal je Ökosystem, und beim Melden ist interessant, welches Ökosystem ein
    fehlendes Label braucht.
    """
    lines = strip_comments(text).splitlines()
    found: list[tuple[str, str]] = []

    ecosystem = None
    i = 0
    while i < len(lines):
        line = lines[i]

        start = _ECOSYSTEM.match(line)
        if start:
            ecosystem = start.group(2).strip("\"'")
            i += 1
            continue

        # Zurück auf oder über die Ebene der Liste: der Block ist zu Ende.
        # Ohne das würde ein `labels:` in einem späteren, anders eingerückten
        # Abschnitt noch dem letzten Ökosystem zugeschlagen.
        if ecosystem is not None and line.strip() and not line[0].isspace():
            ecosystem = None

        if ecosystem is None:
            i += 1
            continue

        inline = _LABELS_INLINE.match(line)
        if inline:
            for raw in inline.group(1).split(","):
                name = raw.strip().strip("\"'")
                if name:
                    found.append((ecosystem, name))
            i += 1
            continue

        block = _LABELS_BLOCK.match(line)
        if block:
            indent = len(block.group(1))
            i += 1
            while i < len(lines):
                item = _LIST_ITEM.match(lines[i])
                if not item or len(item.group(1)) <= indent:
                    break
                name = item.group(2).strip().strip("\"'")
                if name:
                    found.append((ecosystem, name))
                i += 1
            continue

        i += 1

    return found


def fetch_repo_labels(repo: str, token: str | None = None) -> set[str]:
    """Alle Label-Namen des Repos, über alle Seiten."""
    names: set[str] = set()
    page = 1
    while True:
        req = urllib.request.Request(
            f"{API}/repos/{repo}/labels?per_page=100&page={page}",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "check-dependabot-labels",
                **({"Authorization": f"Bearer {token}"} if token else {}),
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            batch = json.load(resp)
        if not batch:
            break
        names.update(item["name"] for item in batch)
        # Eine volle Seite kann die letzte sein; die nächste ist dann leer und
        # bricht oben ab. Eine unvolle Seite ist es sicher.
        if len(batch) < 100:
            break
        page += 1
    return names


def missing(required: list[tuple[str, str]], existing: set[str]) -> dict[str, list[str]]:
    """`{label: [ökosysteme]}` für alles, was im Repo fehlt."""
    gaps: dict[str, list[str]] = {}
    for ecosystem, label in required:
        if label not in existing:
            gaps.setdefault(label, [])
            if ecosystem not in gaps[label]:
                gaps[label].append(ecosystem)
    return gaps


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        metavar="OWNER/NAME",
        help="gegen die Labels dieses Repos vergleichen (fragt die GitHub-API)",
    )
    args = parser.parse_args()

    if not DEPENDABOT.exists():
        print(f"Keine {DEPENDABOT.relative_to(ROOT)} — nichts zu prüfen.")
        return

    required = labels_in_dependabot(DEPENDABOT.read_text(encoding="utf-8"))

    if not required:
        # Kein Fehler, aber auch kein bestandener Vergleich. Ohne diesen Hinweis
        # läse sich die Erfolgsmeldung unten wie «alle Labels vorhanden»,
        # während in Wahrheit nichts verglichen wurde — dieselbe Falle, die
        # `check_version_sync.py` beim einzelnen ruff-Pin benennt.
        print(
            "In .github/dependabot.yml steht kein einziges `labels:` — es gibt "
            "nichts zu vergleichen.",
        )
        return

    unique = sorted({label for _, label in required})

    if not args.repo:
        print(f"{len(unique)} Label(s) aus .github/dependabot.yml:")
        for label in unique:
            wanted = sorted({eco for eco, name in required if name == label})
            print(f"  {label}  ({', '.join(wanted)})")
        print("\nMit --repo OWNER/NAME gegen die Labels des Repos vergleichen.")
        return

    try:
        existing = fetch_repo_labels(args.repo, os.environ.get("GITHUB_TOKEN"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        # Exit 2, nicht 1: «konnte nicht vergleichen» ist nicht «Labels fehlen».
        # Ein Aufrufer, der beides gleich behandelt, meldet bei jedem API-Ausfall
        # einen Konfigurationsfehler, den es nicht gibt.
        print(f"Labels von {args.repo} nicht abrufbar: {exc}", file=sys.stderr)
        sys.exit(2)

    gaps = missing(required, existing)
    if gaps:
        print(
            f"FEHLEND: {len(gaps)} in .github/dependabot.yml genannte(s) Label(s) "
            f"gibt es in {args.repo} nicht:",
            file=sys.stderr,
        )
        for label, ecosystems in sorted(gaps.items()):
            print(f"  {label}  (gebraucht von: {', '.join(ecosystems)})", file=sys.stderr)
        print(
            "\nDependabot legt Labels nicht an — es hängt nur einen Hinweis an jeden "
            "Pull Request und lässt ihn ungelabelt. Anlegen:\n"
            + "\n".join(f"  gh label create {label} -R {args.repo}" for label in sorted(gaps))
            + "\n\nOder die Namen aus `labels:` in .github/dependabot.yml entfernen.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Dependabot-Labels OK ({len(unique)} in {args.repo} vorhanden: {', '.join(unique)})")


if __name__ == "__main__":
    main()
