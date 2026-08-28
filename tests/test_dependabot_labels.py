#!/usr/bin/env python3
"""Die Labels in `.github/dependabot.yml` müssen im Repo existieren.

Dependabot legt Labels nicht an. Steht unter `labels:` ein Name, den das Repo
nicht kennt, hängt Dependabot an jeden Pull Request:

    The following labels could not be found: `dependencies`, `python`.

Kein roter Check, kein Log — nur diese Zeile. In diesem Repo fehlten so alle
vier konfigurierten Labels, über Monate, und die PRs blieben ungelabelt.

WAS HIER GEPRÜFT WIRD, UND WAS NICHT
------------------------------------
Ob ein Label im Repo *existiert*, steht nicht im Repo: Labels sind
GitHub-Zustand, kein Dateiinhalt. Diese Tests können das deshalb nicht
feststellen, und sie tun auch nicht so — sie prüfen den Teil, der offline
entscheidbar ist: dass der Parser die Namen vollständig und richtig aus der
Konfiguration liest, und dass er sie aus der *echten* Datei dieses Repos
tatsächlich findet.

Der Vergleich mit dem Repo läuft von Hand über
`scripts/check_dependabot_labels.py --repo OWNER/NAME`. Bewusst kein Gate in
`ci.yml`: Ein Check, der die GitHub-API braucht, wird bei jedem API-Ausfall und
jedem erschöpften Rate-Limit rot — und macht damit Pull Requests rot, die damit
nichts zu tun haben. Bewusst auch kein `@pytest.mark.live`: Die Live-Suite
dieses Repos ist auf `zefix.admin.ch` gemünzt, bis in den Issue-Titel und das
Label `upstream` («Vertrag mit einer externen Quelle betroffen»). Ein
GitHub-API-Test dort würde ein Issue über Zefix aufmachen, in dem es nicht um
Zefix geht — genau die Vermischung, gegen die `live-tests.yml` argumentiert.

Der Parser liest die Datei als Text, nicht als YAML: `pyyaml` ist keine
Projekt-Abhängigkeit, und `tests/test_precommit_config.py` verfährt aus
demselben Grund so.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_dependabot_labels as cdl  # noqa: E402

DEPENDABOT = ROOT / ".github" / "dependabot.yml"


class Parser(unittest.TestCase):
    def test_inline_liste(self):
        text = """
version: 2
updates:
  - package-ecosystem: uv
    directory: /
    labels: [dependencies, python]
"""
        self.assertEqual(
            cdl.labels_in_dependabot(text),
            [("uv", "dependencies"), ("uv", "python")],
        )

    def test_block_liste(self):
        """Die andere YAML-Schreibweise derselben Sache.

        Ein Parser, der nur die Inline-Form kennt, meldet hier «keine Labels» —
        und das sähe aus wie eine Konfiguration ohne Labels, also wie nichts zu
        tun.
        """
        text = """
updates:
  - package-ecosystem: docker
    labels:
      - dependencies
      - docker
"""
        self.assertEqual(
            cdl.labels_in_dependabot(text),
            [("docker", "dependencies"), ("docker", "docker")],
        )

    def test_mehrere_oekosysteme_werden_getrennt_gefuehrt(self):
        """Welches Ökosystem ein Label braucht, gehört in die Meldung.

        Dependabots eigener Hinweis nennt nur die Labels des betroffenen
        Ökosystems. Wer daraus schliesst, das seien alle, legt zwei an und
        übersieht die übrigen.
        """
        text = """
updates:
  - package-ecosystem: uv
    labels: [dependencies, python]
  - package-ecosystem: github-actions
    labels: [dependencies, ci]
"""
        self.assertEqual(
            cdl.labels_in_dependabot(text),
            [
                ("uv", "dependencies"),
                ("uv", "python"),
                ("github-actions", "dependencies"),
                ("github-actions", "ci"),
            ],
        )

    def test_ohne_labels_kommt_nichts(self):
        text = """
updates:
  - package-ecosystem: uv
    directory: /
    schedule:
      interval: weekly
"""
        self.assertEqual(cdl.labels_in_dependabot(text), [])

    def test_anfuehrungszeichen_werden_abgestreift(self):
        text = """
updates:
  - package-ecosystem: uv
    labels: ["dependencies", 'python']
"""
        self.assertEqual(
            cdl.labels_in_dependabot(text),
            [("uv", "dependencies"), ("uv", "python")],
        )

    def test_kommentierte_labels_zaehlen_nicht(self):
        """Eine auskommentierte Zeile ist keine Konfiguration.

        Ohne diese Zusicherung meldete das Skript ein Label als «gebraucht»,
        das niemand angefordert hat — und schickte jemanden los, es anzulegen.
        """
        text = """
updates:
  - package-ecosystem: uv
    labels: [dependencies]
    # labels: [frueher-mal, abgeschafft]
"""
        self.assertEqual(cdl.labels_in_dependabot(text), [("uv", "dependencies")])

    def test_raute_wird_wie_in_yaml_behandelt(self):
        """`#` beginnt einen Kommentar — ausser in Quotes oder ohne Leerraum davor.

        Die erste Fassung dieses Tests verlangte, dass `color: #ff0000`
        unversehrt bleibt. Das war falsch, und zwar auf die Art, die ein Test
        aufdecken soll: In YAML ist ` #` *immer* ein Kommentarbeginn, `color:
        #ff0000` heisst dort `color: null`. Genau deshalb schreibt man
        Hex-Farben in YAML gequotet. Ein Parser, der die Zeile «rettet», wäre
        grosszügiger als YAML und läse Werte, die es nicht gibt.

        Was wirklich zu schützen ist, steht unten: Quotes und ein `#` ohne
        Leerraum davor.
        """
        # In Quotes: kein Kommentar.
        self.assertEqual(cdl.strip_comments('    prefix: "deps # dev"'), '    prefix: "deps # dev"')
        self.assertEqual(cdl.strip_comments('    color: "#ff0000"'), '    color: "#ff0000"')
        # Ohne Leerraum davor: Teil des Wertes.
        self.assertEqual(cdl.strip_comments("    tag: v1#2"), "    tag: v1#2")
        # Mit Leerraum davor: Kommentar, und zwar auch hinter echten Werten.
        self.assertEqual(cdl.strip_comments("    labels: [a]  # Notiz"), "    labels: [a]")
        self.assertEqual(cdl.strip_comments("# ganze Zeile"), "")

    def test_kommentar_hinter_inline_liste_kostet_kein_label(self):
        """Der Fall, der den Kommentar-Stripper wirklich braucht.

        Die erste Fassung dieser Testklasse prüfte nur einen Kommentar *vor*
        `labels:` — dort greift der Regex ohnehin nicht, und die Gegenprobe
        zeigte es: Ohne `strip_comments()` blieben alle Tests grün. Hinter dem
        Wert ist es umgekehrt. `labels: [a]  # Notiz` endet nicht mehr auf `]`,
        der Regex verfehlt die Zeile, und die Labels verschwinden lautlos aus
        der Anforderungsliste — der Vergleich meldet dann «nichts fehlt».
        """
        text = """
updates:
  - package-ecosystem: uv
    labels: [dependencies, python]  # gilt fuer alle uv-PRs
"""
        self.assertEqual(
            cdl.labels_in_dependabot(text),
            [("uv", "dependencies"), ("uv", "python")],
        )

    def test_kommentar_hinter_block_eintrag_gehoert_nicht_zum_namen(self):
        """Sonst hiesse das Label `dependencies  # Notiz` — und fehlte immer."""
        text = """
updates:
  - package-ecosystem: docker
    labels:
      - dependencies  # quer ueber alle Oekosysteme
      - docker
"""
        self.assertEqual(
            cdl.labels_in_dependabot(text),
            [("docker", "dependencies"), ("docker", "docker")],
        )

    def test_labels_ausserhalb_eines_oekosystems_zaehlen_nicht(self):
        """Nur was unter einem `- package-ecosystem:` steht, ist eine Anforderung."""
        text = """
labels: [nicht-von-dependabot]
updates:
  - package-ecosystem: uv
    labels: [dependencies]
"""
        self.assertEqual(cdl.labels_in_dependabot(text), [("uv", "dependencies")])


class Vergleich(unittest.TestCase):
    """`missing()` gegen eine gesetzte Label-Menge — ohne Netz."""

    REQUIRED = [
        ("uv", "dependencies"),
        ("uv", "python"),
        ("github-actions", "dependencies"),
        ("github-actions", "ci"),
    ]

    def test_alles_vorhanden(self):
        existing = {"dependencies", "python", "ci", "bug"}
        self.assertEqual(cdl.missing(self.REQUIRED, existing), {})

    def test_fehlende_werden_mit_ihren_oekosystemen_gemeldet(self):
        self.assertEqual(
            cdl.missing(self.REQUIRED, {"dependencies"}),
            {"python": ["uv"], "ci": ["github-actions"]},
        )

    def test_ein_label_mehrerer_oekosysteme_wird_einmal_gemeldet(self):
        """`dependencies` steht dreimal in der Datei, fehlt aber nur einmal.

        Eine Meldung pro Nennung liesse dieselbe Zeile dreimal erscheinen und
        die Zahl der fehlenden Labels zu hoch aussehen.
        """
        gaps = cdl.missing(self.REQUIRED, set())
        self.assertEqual(gaps["dependencies"], ["uv", "github-actions"])
        self.assertEqual(sorted(gaps), ["ci", "dependencies", "python"])


class Paginierung(unittest.TestCase):
    """`fetch_repo_labels()` mit gefälschtem `urlopen` — ohne Netz.

    Die Seitenlogik ist der Teil, der still zu wenig liefern kann: Wer nur die
    erste Seite liest, hält ab dem 101. Label jedes weitere für nicht
    vorhanden und meldet Lücken, die es nicht gibt.
    """

    def _fake_urlopen(self, pages):
        """Gibt der Reihe nach die übergebenen Seiten zurück."""
        calls = []

        class Response:
            def __init__(self, payload):
                self._payload = payload

            def read(self):
                return json.dumps(self._payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake(req, timeout=None):
            calls.append(req.full_url)
            index = len(calls) - 1
            return Response(pages[index] if index < len(pages) else [])

        return fake, calls

    def test_liest_alle_seiten(self):
        seite1 = [{"name": f"label-{i}"} for i in range(100)]
        seite2 = [{"name": "letztes"}]
        fake, calls = self._fake_urlopen([seite1, seite2])
        with mock.patch.object(cdl.urllib.request, "urlopen", fake):
            names = cdl.fetch_repo_labels("owner/repo")
        self.assertEqual(len(names), 101)
        self.assertIn("letztes", names)
        self.assertEqual(len(calls), 2)
        self.assertIn("page=2", calls[1])

    def test_unvolle_erste_seite_beendet_die_abfrage(self):
        """Eine Seite mit weniger als 100 Einträgen ist sicher die letzte.

        Ohne diesen Abbruch folgte auf jede Abfrage eine weitere, die nur
        leere Ergebnisse holt — pro Aufruf eine überflüssige Anfrage gegen ein
        Rate-Limit, das ohne Token bei 60 pro Stunde liegt.
        """
        fake, calls = self._fake_urlopen([[{"name": "a"}, {"name": "b"}]])
        with mock.patch.object(cdl.urllib.request, "urlopen", fake):
            names = cdl.fetch_repo_labels("owner/repo")
        self.assertEqual(names, {"a", "b"})
        self.assertEqual(len(calls), 1)

    def test_token_wird_als_header_geschickt(self):
        """Ohne Token greift das knappe Limit für anonyme Zugriffe."""
        seen = {}

        class Response:
            def read(self):
                return b"[]"

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake(req, timeout=None):
            seen.update(req.headers)
            return Response()

        with mock.patch.object(cdl.urllib.request, "urlopen", fake):
            cdl.fetch_repo_labels("owner/repo", token="geheim")
        # urllib schreibt Header-Namen in Titel-Schreibweise.
        self.assertEqual(seen.get("Authorization"), "Bearer geheim")


class DieseKonfiguration(unittest.TestCase):
    """Gegen die echte `.github/dependabot.yml` dieses Repos."""

    def setUp(self):
        if not DEPENDABOT.exists():
            self.skipTest("keine .github/dependabot.yml")
        self.found = cdl.labels_in_dependabot(DEPENDABOT.read_text(encoding="utf-8"))

    def test_der_parser_findet_die_labels_dieses_repos(self):
        """Die Zusicherung, die verhindert, dass alles andere leer durchläuft.

        Ohne sie bliebe die ganze Datei grün, wenn der Parser an der echten
        Konfiguration nichts findet — jeder Vergleich vergliche dann eine leere
        Menge und meldete «nichts fehlt».
        """
        self.assertTrue(
            self.found,
            "Der Parser findet in .github/dependabot.yml kein einziges Label. "
            "Entweder ist dort keins konfiguriert — dann gehört diese Datei "
            "angepasst — oder der Parser liest die Schreibweise nicht.",
        )

    def test_jedes_oekosystem_mit_labels_nennt_dependencies(self):
        """Hausregel dieses Repos, und der Grund, warum es das Label gibt.

        `dependencies` ist das Label, über das sich Dependabot-PRs quer über
        alle Ökosysteme filtern lassen. Ein Ökosystem, das es auslässt, fällt
        aus jeder solchen Ansicht heraus, ohne dass irgendwo etwas rot wird.
        """
        mit_labels = {eco for eco, _ in self.found}
        for eco in sorted(mit_labels):
            self.assertIn(
                "dependencies",
                [label for e, label in self.found if e == eco],
                f"Ökosystem {eco!r} führt Labels, aber nicht `dependencies`",
            )

    def test_keine_doppelten_labels_je_oekosystem(self):
        """Ein zweimal genanntes Label ist ein Tippfehler, kein Wunsch."""
        for eco in sorted({e for e, _ in self.found}):
            labels = [label for e, label in self.found if e == eco]
            self.assertEqual(
                len(labels), len(set(labels)), f"Ökosystem {eco!r} nennt ein Label doppelt"
            )


if __name__ == "__main__":
    unittest.main()
