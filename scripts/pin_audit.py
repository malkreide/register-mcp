#!/usr/bin/env python3
"""Prüft portfolioweit, ob die ruff-Pin-Wächter der Server halten, was sie sollen.

Anlass: In `register-mcp` und `swiss-academic-libraries-mcp` sammelten die
Wächter `rev:` aus `.pre-commit-config.yaml` zeilenweise ein, ohne zu fragen, zu
welchem `- repo:` es gehört. Ein zweiter, völlig gewöhnlicher Hook —
`end-of-file-fixer` und Kollegen — brachte damit seine eigene Version als
vermeintlichen ruff-Pin mit, und der Gate wurde rot mit einer Zahl, die niemand
geschrieben hat. Beide Male fiel es erst auf, als jemand danach suchte.

Gemessen wird schwarzkastig am echten Repo, nicht am Regex: Datei verstellen,
Wächter starten, Exit-Code lesen, Datei zurücksetzen. Ein Vergleich, der die
Implementierungen liest statt sie laufen zu lassen, misst die Lesefähigkeit des
Prüfenden, nicht ihre.

Verwendung:
    python scripts/pin_audit.py ../andere-mcp ../noch-eine-mcp
    python scripts/pin_audit.py --json ../*-mcp        # maschinenlesbar

Exit 1, sobald ein Wächter einen Fehlalarm produziert.

**Kein CI-Gate.** Das Werkzeug braucht die Schwester-Repos im Dateisystem, die in
keinem CI-Lauf liegen. Es gehört von Hand gefahren, wenn eine Pin-Konvention
geändert wird oder ein neuer Server dazukommt.

Nur Standardbibliothek, und bewusst ohne Import aus dem Nachbarskript: Das
Werkzeug wird zwischen den Servern kopiert, und `check_version_sync.ruff_specs`
gibt es dort nur in vier von zweiundvierzig. Ein Import fiele in den übrigen
schon beim Start um — eine Kopie, die nie zum Messen käme.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

PC = ".pre-commit-config.yaml"

# Ein exakter ruff-Pin im dev-Extra.
#
# Zwei Abgrenzungen, und sie tun Verschiedenes:
#   - Das geforderte `==` direkt nach `ruff` haelt `ruff-lsp==0.0.1` heraus —
#     genau die Verwechslung, die anderswo im Portfolio zweimal danebenging.
#   - `fullmatch` (nicht `search`) haelt Namen heraus, die auf `ruff` ENDEN:
#     in `my-ruff==0.16.1` faende `search` sehr wohl ein `ruff==0.16.1`.
#
# Der Preis der Strenge: `ruff==0.16.1 ; sys_platform == "linux"` gilt hier
# nicht als Pin. Das ist verkraftbar, weil der Fall sichtbar als «kein exakter
# ruff-Pin» gemeldet wird, statt still ein falsches Ergebnis zu liefern.
_PIN = re.compile(r"ruff(?:\[[^\]]*\])?==(\d+\.\d+\.\d+)")

# Wer liest die Datei? Bewusst grosszügig — der Dateiname, der Werkzeugname, das
# Schlüsselwort. Ein Treffer zu viel kostet einen Messlauf und wird von der
# Positivkontrolle als «liest die rev gar nicht» aussortiert. Ein Treffer zu
# wenig fällt dagegen nirgends auf.
#
# Die erste Fassung fragte bei Skripten stattdessen «wird sie als
# `python scripts/check_*.py` aus einem Workflow gestartet?» und suchte nur in
# `tests/` nach Inhalten. Damit fiel `meteoswiss-mcp/scripts/check_ruff_pin.py`
# durch jedes Netz: Sie liest die Datei, wird aber nicht aus einem Workflow
# gestartet — sie IST ein pre-commit-Hook. Wer eine Datei liest und wer sie
# startet, sind zwei Fragen; hier wird die erste gestellt.
LIEST = re.compile(r"\.pre-commit-config\.yaml|pre-commit|(?<!\w)rev:")

RUFF_BLOCK = """\
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v{pin}
    hooks:
      - id: ruff-check
        files: ^(src|tests|scripts)/
      - id: ruff-format
        files: ^(src|tests|scripts)/
"""

# Ein völlig gewöhnlicher zweiter Hook: eigene `rev`, mit ruff nichts zu tun.
FREMDER_HOOK = """\
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v9.9.9
    hooks:
      - id: end-of-file-fixer
"""

FEHLALARM = "FEHLALARM"
KORREKT = "KORREKT"
BLIND = "BLIND"
OHNE_REV = "OHNE_REV"
VORBEDINGUNG = "VORBEDINGUNG"

ERKLAERUNG = {
    FEHLALARM: "fremder Hook macht den Wächter rot",
    KORREKT: "liest die rev und ordnet sie dem ruff-Block zu",
    BLIND: "liest die rev nicht — die Falle ist hier nicht gestellt",
    OHNE_REV: "das Repo hat keine ruff-rev (etwa `repo: local`)",
    VORBEDINGUNG: "schon vor jeder Änderung rot — nicht messbar",
}


def pin_aus_pyproject(root: Path) -> str | None:
    """Der exakte ruff-Pin aus `[project.optional-dependencies].dev`.

    Über `tomllib` statt per Regex über den Dateitext: Kommentare, mehrzeilige
    Listen und Anführungszeichen sind damit von vornherein kein Thema. Genau an
    denen ist im Portfolio schon mehr als ein Pin-Leser gescheitert — einer las
    seinen eigenen Erklärtext als Fundort.

    `None`, wenn ruff dort nicht oder nicht exakt gepinnt ist. Das ist kein
    Befund dieses Werkzeugs, sondern die Zuständigkeit der Gates; hier heisst
    es nur: nichts zu messen.
    """
    datei = root / "pyproject.toml"
    if not datei.exists():
        return None
    try:
        daten = tomllib.loads(datei.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    dev = daten.get("project", {}).get("optional-dependencies", {}).get("dev", [])
    for eintrag in dev:
        treffer = _PIN.fullmatch(str(eintrag).strip())
        if treffer:
            return treffer.group(1)
    return None


def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=120)
    return r.stdout


def waechter_dateien(root: Path) -> list[str]:
    """Versionierte `*.py` ausserhalb `src/`, die die pre-commit-Datei erwähnen."""
    treffer = []
    for rel in git(root, "ls-files", "*.py").splitlines():
        if not rel or rel.startswith("src/"):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if LIEST.search(text):
            treffer.append(rel)
    return sorted(treffer)


def startbefehl(root: Path, rel: str, python: str, pytest: str) -> list[str]:
    """`--noconftest`: die conftest.py importiert das Paket, der Pin-Test nicht."""
    if Path(rel).name.startswith("test_"):
        return [pytest, "-q", "-p", "no:cacheprovider", "--noconftest", rel]
    return [python, rel]


def varianten(pin: str, original: str | None, sauber: str) -> list[tuple[str, str | None]]:
    """Die vier Zustände, in denen der Wächter laufen muss.

    Die Positivkontrolle ist der Kern: Ohne sie lässt sich «grün beim fremden
    Hook» nicht von «liest die Datei gar nicht» unterscheiden, und ein Grün, das
    nur Blindheit ist, sähe wie ein Freispruch aus.
    """
    basis = original if original is not None else sauber
    if original is not None:
        # Die echte Datei behalten und den fremden Hook nur davorsetzen — sonst
        # misst der Fall eine selbstgebaute Datei statt der echten.
        stelle = basis.find("  - repo:")
        mit_fremdem = basis if stelle < 0 else basis[:stelle] + FREMDER_HOOK + basis[stelle:]
    else:
        mit_fremdem = "repos:\n" + FREMDER_HOOK + RUFF_BLOCK.format(pin=pin)

    out: list[tuple[str, str | None]] = [("unveraendert", original), ("sauber", basis)]
    verstellt = basis.replace(f"rev: v{pin}", "rev: v0.15.8")
    if verstellt != basis:
        out.append(("kontrolle", verstellt))
    out.append(("fremder_hook", mit_fremdem))
    return out


def klassifiziere(rc: dict[str, int]) -> str:
    """Aus den Exit-Codes der Varianten das Urteil.

    Die erste Fassung schrieb `if rc.get("kontrolle") == 0: BLIND` — und zählte
    damit eine FEHLENDE Kontrolle als bestandene, weil `None == 0` falsch ist
    und der Fall in den Korrekt-Zweig durchfiel. Ein Repo ohne `rev` stand
    daraufhin als «ordnet richtig zu» da, ohne dass je etwas zugeordnet wurde.
    Deshalb wird das Fehlen hier zuerst und ausdrücklich behandelt.
    """
    if rc.get("unveraendert") != 0 or rc.get("sauber") != 0:
        return VORBEDINGUNG
    if "kontrolle" not in rc:
        return OHNE_REV
    if rc["kontrolle"] == 0:
        return BLIND
    return FEHLALARM if rc["fremder_hook"] != 0 else KORREKT


def messe(root: Path, python: str, pytest: str) -> dict:
    name = root.name
    if git(root, "status", "--porcelain").strip():
        return {"repo": name, "fehler": "Arbeitsverzeichnis nicht sauber — uebersprungen"}
    pin = pin_aus_pyproject(root)
    if pin is None:
        return {"repo": name, "fehler": "kein exakter ruff-Pin in pyproject.toml"}

    datei = root / PC
    original = datei.read_text(encoding="utf-8") if datei.exists() else None
    sauber = "repos:\n" + RUFF_BLOCK.format(pin=pin)
    umgebung = {**os.environ, "PATH": f"{Path(python).parent}:{os.environ.get('PATH', '')}"}

    ergebnis: dict = {
        "repo": name,
        "pin": pin,
        "hat_precommit": original is not None,
        "waechter": {},
    }
    try:
        for rel in waechter_dateien(root):
            cmd = startbefehl(root, rel, python, pytest)
            rc: dict[str, int] = {}
            for variante, inhalt in varianten(pin, original, sauber):
                if inhalt is None:
                    datei.unlink(missing_ok=True)
                else:
                    datei.write_text(inhalt, encoding="utf-8")
                try:
                    lauf = subprocess.run(
                        cmd, cwd=root, capture_output=True, text=True, timeout=300, env=umgebung
                    )
                    rc[variante] = lauf.returncode
                except subprocess.TimeoutExpired:
                    rc[variante] = 124
            ergebnis["waechter"][rel] = {"varianten": rc, "urteil": klassifiziere(rc)}
    finally:
        if original is None:
            datei.unlink(missing_ok=True)
        else:
            datei.write_text(original, encoding="utf-8")

    ergebnis["sauber_zurueck"] = not git(root, "status", "--porcelain").strip()
    return ergebnis


def main() -> int:
    p = argparse.ArgumentParser(description="ruff-Pin-Wächter im Portfolio pruefen")
    p.add_argument("repos", nargs="+", type=Path, help="Wurzelverzeichnisse der Server")
    p.add_argument("--json", action="store_true", help="Rohdaten statt Tabelle")
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--pytest", default=str(Path(sys.executable).with_name("pytest")))
    args = p.parse_args()

    daten = [messe(r.resolve(), args.python, args.pytest) for r in args.repos]
    if args.json:
        print(json.dumps(daten, ensure_ascii=False, indent=1))
    else:
        for r in sorted(daten, key=lambda d: d["repo"]):
            if "fehler" in r:
                print(f"{r['repo']:34} — {r['fehler']}")
                continue
            for rel, w in sorted(r["waechter"].items()):
                print(f"{r['repo']:34} {rel:38} {w['urteil']}")
            if not r["waechter"]:
                print(f"{r['repo']:34} {'(kein Waechter gefunden)':38} —")
        print()
        for schluessel, text in ERKLAERUNG.items():
            print(f"  {schluessel:14} {text}")

    unsauber = [r["repo"] for r in daten if r.get("sauber_zurueck") is False]
    if unsauber:
        print(f"\nNICHT ZURUECKGESETZT: {', '.join(unsauber)} — von Hand pruefen!", file=sys.stderr)
        return 1
    treffer = [
        f"{r['repo']}::{rel}"
        for r in daten
        for rel, w in r.get("waechter", {}).items()
        if w["urteil"] == FEHLALARM
    ]
    if treffer:
        print(f"\nFEHLALARM: {', '.join(treffer)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
