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

# Eigener Alias statt `urllib.request.urlopen` an der Aufrufstelle. Ein Test,
# der `urllib.request` patcht, greift ins fremde Modul und entschaerft es im
# ganzen Prozess — CLAUDE.md fuehrt genau das unter «Tests» als Falle. Ueber
# den Alias trifft ein `mock.patch.object(cdl, "_urlopen", ...)` nur dieses
# Modul.
_urlopen = urllib.request.urlopen

# Ein Eintrag der Liste unter `updates:` beginnt mit `- `. Welcher Schlüssel
# darin zuerst steht, ist in YAML beliebig — `package-ecosystem` wird deshalb
# im ganzen Eintrag gesucht, nicht auf seiner ersten Zeile.
_ITEM_START = re.compile(r"^(\s*)-\s?(.*)$")

_ECOSYSTEM_KEY = re.compile(r"^\s*package-ecosystem:\s*(\S+)\s*$")

# `labels: [a, b]` auf einer Zeile.
_LABELS_INLINE = re.compile(r"^\s*labels:\s*\[([^\]]*)\]\s*$")

# `labels:` allein — die Namen stehen dann als `- a` in den Folgezeilen.
_LABELS_BLOCK = re.compile(r"^(\s*)labels:\s*$")

_LIST_ITEM = re.compile(r"^(\s*)-\s*(.+?)\s*$")

_TOP_KEY = re.compile(r"^(\s*)updates:\s*$")

# Zeichen, nach denen ein neuer Skalar beginnt — nur dort eröffnet ein
# Anführungszeichen wirklich einen quotierten Wert.
_SCALAR_START = set(":,-[{ \t")


def strip_comments(text: str) -> str:
    """Zeilenkommentare entfernen, Anführungszeichen dabei respektieren.

    Ein nacktes `re.sub(r"#.*", "", …)` wäre hier falsch: `dependabot.yml`
    trägt in diesem Repo einen langen Kopfkommentar, in dem unter anderem
    «PRs #26–#30» steht. Das ist harmlos, weil die ganze Zeile Kommentar ist —
    aber ein `#` innerhalb eines quotierten Wertes (`prefix: "deps # dev"`)
    wäre es nicht, und ein Parser, der den Unterschied nicht kennt, schneidet
    still Werte ab.

    Ein Anführungszeichen quotiert in YAML aber nur, wenn es einen Skalar
    ERÖFFNET. Mitten in einem unquotierten Wert ist es ein gewöhnliches
    Zeichen: `labels: [it's-fine]  # Notiz` ist eine Liste mit einem Apostroph
    darin, kein offener String. Wer jedes `'` als Quote zählt, hält den Rest
    der Zeile für quotiert, schneidet den Kommentar nicht ab — und das Label
    heisst danach `it's-fine  # Notiz` und fehlt für immer.
    """
    out = []
    for line in text.splitlines():
        quote = None
        cut = None
        for i, ch in enumerate(line):
            if quote is not None:
                if ch == quote:
                    quote = None
            elif ch in "\"'" and (i == 0 or line[i - 1] in _SCALAR_START):
                quote = ch
            elif ch == "#":
                # Ein `#` zählt nur als Kommentar, wenn es am Zeilenanfang
                # steht oder Leerraum davor liegt. Sonst ist es Teil eines
                # unquotierten Wertes (`tag: v1#2`).
                if i == 0 or line[i - 1].isspace():
                    cut = i
                    break
        # Beim Schneiden auch den Leerraum vor dem `#` weg: er ist der Trenner
        # des Kommentars, nicht Teil des Wertes. Zeilen ohne Kommentar bleiben
        # unangetastet — diese Funktion entfernt Kommentare, sie formatiert nicht.
        out.append(line if cut is None else line[:cut].rstrip())
    return "\n".join(out)


def _update_items(lines: list[str]) -> list[list[str]]:
    """Die Einträge unter `updates:`, jeder als eigene Zeilenliste.

    Getrennt wird an `- ` auf der Einrückung des ersten Eintrags. Der Rumpf
    eines Eintrags sind alle Folgezeilen, die tiefer eingerückt sind — plus
    das, was hinter dem `- ` auf der Startzeile selbst steht.
    """
    start = None
    for n, line in enumerate(lines):
        if _TOP_KEY.match(line):
            start = n + 1
            break
    if start is None:
        return []

    items: list[list[str]] = []
    indent = None
    for line in lines[start:]:
        if not line.strip():
            if items:
                items[-1].append(line)
            continue
        m = _ITEM_START.match(line)
        here = len(line) - len(line.lstrip())
        if m and (indent is None or here == indent):
            # Ein `-` weiter links als der erste Eintrag beendet `updates:`.
            if indent is not None and here < indent:
                break
            indent = here
            items.append([" " * (here + 2) + m.group(2)])
            continue
        if indent is None:
            # Etwas anderes direkt unter `updates:` — keine Liste.
            break
        if here <= indent:
            break
        if items:
            items[-1].append(line)
    return items


def _labels_in_item(item: list[str]) -> list[str]:
    """Die Label-Namen eines einzelnen `updates:`-Eintrags."""
    names: list[str] = []
    i = 0
    while i < len(item):
        line = item[i]

        inline = _LABELS_INLINE.match(line)
        if inline:
            for raw in inline.group(1).split(","):
                name = raw.strip().strip("\"'")
                if name:
                    names.append(name)
            i += 1
            continue

        block = _LABELS_BLOCK.match(line)
        if block:
            indent = len(block.group(1))
            i += 1
            while i < len(item):
                # Leerzeilen (auch solche, die vorher ein Kommentar waren)
                # trennen die Liste nicht. Wer hier abbricht, verliert alles
                # Folgende still — und meldet danach «nichts fehlt».
                if not item[i].strip():
                    i += 1
                    continue
                entry = _LIST_ITEM.match(item[i])
                # `>=`, nicht `>`: In YAML darf ein Listeneintrag auf DERSELBEN
                # Spalte stehen wie sein Schlüssel. Beides ist verbreitet, und
                # `>` verwirft die halbe Schreibweise kommentarlos.
                if not entry or len(entry.group(1)) < indent:
                    break
                name = entry.group(2).strip().strip("\"'")
                if name:
                    names.append(name)
                i += 1
            continue

        i += 1
    return names


def labels_in_dependabot(text: str) -> list[tuple[str, str]]:
    """`(ökosystem, label)` für jede Nennung, in Reihenfolge der Datei.

    Doppelte Nennungen bleiben erhalten: `dependencies` steht hier dreimal,
    einmal je Ökosystem, und beim Melden ist interessant, welches Ökosystem ein
    fehlendes Label braucht.
    """
    lines = strip_comments(text).splitlines()
    found: list[tuple[str, str]] = []
    for item in _update_items(lines):
        ecosystem = None
        for line in item:
            key = _ECOSYSTEM_KEY.match(line)
            if key:
                ecosystem = key.group(1).strip("\"'")
                break
        if ecosystem is None:
            continue
        for name in _labels_in_item(item):
            found.append((ecosystem, name))
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
        with _urlopen(req, timeout=30) as resp:
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
    """`{label: [ökosysteme]}` für alles, was im Repo fehlt.

    Verglichen wird ohne Rücksicht auf Gross-/Kleinschreibung, weil GitHub
    Label-Namen so eindeutig hält: Neben `dependencies` lässt sich kein
    `Dependencies` anlegen. Ein Vergleich, der die beiden trennt, meldet ein
    vorhandenes Label als fehlend und schickt jemanden mit einem
    `gh label create` los, das mit «already exists» scheitert.
    """
    vorhanden = {name.casefold() for name in existing}
    gaps: dict[str, list[str]] = {}
    for ecosystem, label in required:
        if label.casefold() not in vorhanden:
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
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        # Eine Proxy- oder Fehlerseite kommt als HTTP 200 mit HTML an.
        # Ohne diesen Zweig fliegt der JSONDecodeError durch, Python
        # endet mit 1 — und das heisst hier «Labels fehlen».
        json.JSONDecodeError,
        # Ein JSON, das kein Array von Objekten mit `name` ist. Flach
        # aufgezaehlt: ein verschachteltes Tupel in einer except-Klausel
        # wirft in Python 3 selbst einen TypeError, ausgerechnet im
        # Fehlerpfad.
        KeyError,
        TypeError,
    ) as exc:
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
