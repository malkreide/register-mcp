#!/usr/bin/env python3
"""Tests fuer den ruff-Pin-Abgleich in scripts/check_version_sync.py.

Der Pin steht an zwei Stellen: dem dev-Extra in pyproject und `rev:` beim
ruff-pre-commit-Hook (pre-commit kann pyproject nicht lesen). Ein `ruff==` im
Workflow ist keine dritte Stelle mehr, sondern ein Befund — er laeuft nach dem
Install und ueberschreibt das dev-Extra, sodass eine Abweichung dort in der CI
gar nicht auffiele.

Ein Check, der das prueft, hat sechs Wege, still falsch zu liegen, und jeder
davon hat hier einen Test:

  - Er liest einen Kommentar als Fundort. Alle drei Dateien erklaeren ihren
    Pin im Fliesstext, teils woertlich mit «ruff==0.16.1».
  - Er ordnet ein `rev:` dem falschen `repo:` zu und vergleicht die Version
    eines fremden Hooks mit der von ruff.
  - Er haelt `[tool.ruff]` oder `ruff-lsp` fuer eine ruff-Abhaengigkeit.
  - Er meldet «OK», wo er gar nichts verglichen hat — weil nur eine der
    Stellen existiert.
  - Er uebersieht einen wieder eingefuegten CI-Pin. Der Gleichstand der beiden
    verbleibenden Stellen bliebe dabei gruen, und die CI liefe trotzdem auf
    einer anderen Version — deshalb wird sein Fehlen eigens geprueft.
  - Er laesst eine verschwundene ruff-Zeile in pyproject durchgehen. Ein
    Gleichstands-Vergleich wird gerade dann gruen, wenn ihm eine Seite
    abhandenkommt: Was uebrig bleibt, stimmt zwangslaeufig mit sich selbst
    ueberein.

Nur Standardbibliothek, kein Netz.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_version_sync as cvs  # noqa: E402

WORKFLOW_OHNE_PIN = """\
name: test
jobs:
  lint:
    steps:
      - run: pip install -e ".[dev]"
      - run: ruff check src/
"""

WORKFLOW = """\
name: test
jobs:
  lint:
    steps:
      - name: Install pinned ruff
        run: pip install ruff=={version}
"""

PRECOMMIT = """\
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v{version}
    hooks:
      - id: ruff-check
"""


PYPROJECT = """\
[project]
name = "demo"
version = "1.0.0"

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "ruff{spec}",
]

[tool.ruff]
line-length = 100
"""


# Dasselbe Repo, aber ohne jede ruff-Abhaengigkeit — `[tool.ruff]` bleibt
# absichtlich stehen: Ein Repo, das ruff konfiguriert und im Gate aufruft, es
# aber nicht mehr deklariert, ist genau der Fall, der still durchrutscht.
PYPROJECT_OHNE_RUFF = """\
[project]
name = "demo"
version = "1.0.0"

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
]

[tool.ruff]
line-length = 100
"""


def make_root(
    tmp: Path,
    workflow: str | None = None,
    precommit: str | None = None,
    pyproject: str | None = None,
) -> Path:
    if workflow is not None:
        wf = tmp / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "test.yml").write_text(workflow, encoding="utf-8")
    if precommit is not None:
        (tmp / ".pre-commit-config.yaml").write_text(precommit, encoding="utf-8")
    if pyproject is not None:
        (tmp / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return tmp


@contextlib.contextmanager
def root(
    workflow: str | None = None,
    precommit: str | None = None,
    pyproject: str | None = None,
):
    with tempfile.TemporaryDirectory() as tmp:
        yield make_root(Path(tmp), workflow, precommit, pyproject)


class RuffPinTest(unittest.TestCase):
    def versions(self, **kwargs) -> list[str]:
        with root(**kwargs) as path:
            return [value for _, value in cvs.ruff_pins(path)]

    def test_beide_stellen_gefunden(self):
        got = self.versions(
            pyproject=PYPROJECT.format(spec="==0.16.1"),
            precommit=PRECOMMIT.format(version="0.16.1"),
        )
        self.assertEqual(got, ["0.16.1", "0.16.1"])

    def test_rev_verliert_das_v(self):
        """`rev: v0.16.1` und `ruff==0.16.1` bezeichnen dieselbe Version.

        Ohne das Abschneiden waeren sie als Zeichenketten ungleich, und der
        Check meldete Drift auf einem Repo, das korrekt gepinnt ist.
        """
        got = self.versions(precommit=PRECOMMIT.format(version="0.16.1"))
        self.assertEqual(got, ["0.16.1"])

    def test_abweichende_pins_bleiben_unterscheidbar(self):
        got = self.versions(
            pyproject=PYPROJECT.format(spec="==0.16.1"),
            precommit=PRECOMMIT.format(version="0.15.8"),
        )
        self.assertEqual(sorted(got), ["0.15.8", "0.16.1"])

    def test_workflow_ist_keine_pin_quelle_mehr(self):
        """Ein `ruff==` im Workflow zaehlt nicht als Stelle, an der der Pin steht.

        Zaehlte er mit, waere er im Gleichstands-Vergleich unsichtbar: Er
        stimmte ja mit den uebrigen ueberein — waehrend er sie in der CI
        gerade ueberschreibt.
        """
        self.assertEqual(self.versions(workflow=WORKFLOW.format(version="0.16.1")), [])

    def test_kommentar_im_workflow_ist_kein_fundort(self):
        with root(
            workflow="# historisch: ruff==0.9.9\n" + WORKFLOW_OHNE_PIN,
        ) as path:
            self.assertEqual(cvs.ruff_in_workflows(path), [])

    def test_auskommentiertes_rev_gilt_nicht(self):
        """Ein stehengelassenes `# rev:` steht vor dem echten und darf nicht gewinnen.

        `_PC_REV` nimmt den ersten Treffer im Block. Dass die auskommentierte
        Zeile nicht zaehlt, leistet hier die Verankerung `^\\s*rev:` — zwischen
        Zeilenanfang und `rev:` darf nur Leerraum stehen, kein `#`. Nicht das
        Ausschneiden der Kommentare: Die Zusicherung haelt auch ohne das,
        gepruefte Wirkung ist die des Ankers.
        """
        text = PRECOMMIT.format(version="0.15.8").replace(
            "    rev: v0.15.8", "    # rev: v0.9.9  (vor dem Bump)\n    rev: v0.15.8"
        )
        got = self.versions(precommit=text)
        self.assertEqual(got, ["0.15.8"])

    def test_fremder_hook_liefert_kein_rev(self):
        """Ein `rev:` gehoert dem `repo:`, unter dem es steht."""
        text = (
            "repos:\n"
            "  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
            "    rev: v9.9.9\n"
            "    hooks:\n"
            "      - id: end-of-file-fixer\n"
        ) + PRECOMMIT.format(version="0.16.1").replace("repos:\n", "")
        got = self.versions(precommit=text)
        self.assertEqual(got, ["0.16.1"])

    def test_ohne_pre_commit_datei_nur_ein_pin(self):
        got = self.versions(pyproject=PYPROJECT.format(spec="==0.16.1"))
        self.assertEqual(got, ["0.16.1"])

    def test_ohne_beide_dateien_kein_pin(self):
        self.assertEqual(self.versions(), [])

    def test_raute_in_anfuehrungszeichen_schneidet_nicht_ab(self):
        """Die Raute steht in einer Zeichenkette, der Pin dahinter — auf derselben Zeile.

        Auf zwei Zeilen verteilt bewiese der Fall nichts: Ein zu frueh
        abgeschnittener Kommentar nimmt dann nur die erste Zeile mit, und der
        Pin waere auch ohne die Anfuehrungszeichen-Behandlung noch da.
        """
        text = 'run: echo "a # b" && pip install ruff==0.16.1\n'
        with root(workflow=text) as path:
            self.assertEqual([v for _, v in cvs.ruff_in_workflows(path)], ["0.16.1"])


class PyprojectSpecTest(unittest.TestCase):
    """Das dev-Extra ist die Stelle, an der `pip install -e ".[dev]"` nachschaut."""

    def specs(self, spec: str) -> tuple[list[str], list[str]]:
        with root(pyproject=PYPROJECT.format(spec=spec)) as path:
            pins, loose = cvs.ruff_specs(path)
        return [v for _, v in pins], [v for _, v in loose]

    def test_exakter_pin_zaehlt_als_pin(self):
        self.assertEqual(self.specs("==0.16.1"), (["0.16.1"], []))

    def test_offener_bereich_ist_lose(self):
        self.assertEqual(self.specs(">=0.4.0"), ([], [">=0.4.0"]))

    def test_ohne_version_ist_lose(self):
        self.assertEqual(self.specs(""), ([], ["(ohne Version)"]))

    def test_bereich_mit_komma_ist_lose(self):
        """`==0.16.1,<0.17` faengt mit `==` an, laesst aber Spielraum.

        Ohne die Komma-Pruefung liefe so ein Bereich als exakter Pin durch —
        und `0.16.1,<0.17` waere die Version, gegen die verglichen wird.
        """
        self.assertEqual(self.specs("==0.16.1,<0.17"), ([], ["==0.16.1,<0.17"]))

    def test_tool_ruff_tabelle_ist_kein_treffer(self):
        """`[tool.ruff]` steht in jeder pyproject und ist keine Abhaengigkeit.

        Die pyproject hier nennt ruff *nur* als Konfigurationstabelle. Faende
        das Muster sie, meldete der Check eine lose ruff-Angabe an jedem Repo
        des Portfolios — und der Ausweg waere, den Check abzuschalten.
        """
        text = "[project]\nname = 'demo'\nversion = '1.0.0'\n\n[tool.ruff]\nline-length = 100\n"
        with root(pyproject=text) as path:
            self.assertEqual(cvs.ruff_specs(path), ([], []))

    def test_anderes_paket_mit_ruff_praefix(self):
        with root(
            pyproject=PYPROJECT.format(spec="==0.16.1").replace(
                '"pytest>=8.0.0"', '"ruff-lsp>=0.0.1"'
            )
        ) as path:
            pins, loose = cvs.ruff_specs(path)
        self.assertEqual(([v for _, v in pins], loose), (["0.16.1"], []))

    def test_kommentar_im_pyproject_ist_kein_fundort(self):
        """Der Pin-Kommentar dieses Repos nennt die Version in Anfuehrungszeichen.

        `bakom-mcp` schreibt sie sogar als `"ruff==0.16.1"` in den Fliesstext.
        Wird der mitgelesen, meldet der Check Einigkeit anhand von Prosa.
        """
        text = PYPROJECT.format(spec=">=0.4.0").replace(
            '    "pytest>=8.0.0",', '    # frueher: "ruff==0.16.1"\n    "pytest>=8.0.0",'
        )
        with root(pyproject=text) as path:
            pins, loose = cvs.ruff_specs(path)
        self.assertEqual((pins, [v for _, v in loose]), ([], [">=0.4.0"]))

    def test_pyproject_pin_zaehlt_beim_abgleich_mit(self):
        got = self.versions_all(
            precommit=PRECOMMIT.format(version="0.16.1"),
            pyproject=PYPROJECT.format(spec="==0.15.8"),
        )
        self.assertEqual(sorted(got), ["0.15.8", "0.16.1"])

    def versions_all(self, **kwargs) -> list[str]:
        with root(**kwargs) as path:
            return [v for _, v in cvs.ruff_pins(path)]


class MainTest(unittest.TestCase):
    """main() als Ganzes — der Abgleich entscheidet ueber den Exit-Code."""

    def run_main(self, tmp: Path) -> tuple[int, str]:
        # Nicht ueberschreiben: Faelle, die eine eigene pyproject mitbringen,
        # pruefen genau deren Inhalt.
        path = tmp / "pyproject.toml"
        if not path.exists():
            path.write_text('[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8")
        old = (cvs.ROOT, cvs.PYPROJECT, cvs.SERVER_JSON, cvs.SRC)
        cvs.ROOT, cvs.PYPROJECT = tmp, tmp / "pyproject.toml"
        cvs.SERVER_JSON, cvs.SRC = tmp / "server.json", tmp / "src"
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                cvs.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
        finally:
            cvs.ROOT, cvs.PYPROJECT, cvs.SERVER_JSON, cvs.SRC = old
        return code, out.getvalue() + err.getvalue()

    def test_abweichende_pins_sind_rot(self):
        with root(
            pyproject=PYPROJECT.format(spec="==0.16.1"),
            precommit=PRECOMMIT.format(version="0.15.8"),
        ) as path:
            code, text = self.run_main(path)
        self.assertEqual(code, 1)
        self.assertIn("DRIFT", text)
        self.assertIn("0.15.8", text)

    def test_gleiche_pins_sind_gruen(self):
        with root(
            pyproject=PYPROJECT.format(spec="==0.16.1"),
            precommit=PRECOMMIT.format(version="0.16.1"),
        ) as path:
            code, text = self.run_main(path)
        self.assertEqual(code, 0)
        self.assertIn("0.16.1", text)

    def test_loser_spec_ist_rot(self):
        with root(
            workflow=WORKFLOW_OHNE_PIN,
            pyproject=PYPROJECT.format(spec=">=0.4.0"),
        ) as path:
            code, text = self.run_main(path)
        self.assertEqual(code, 1)
        self.assertIn("LOSE", text)

    def test_exakter_pin_im_pyproject_ist_gruen(self):
        with root(
            workflow=WORKFLOW_OHNE_PIN,
            precommit=PRECOMMIT.format(version="0.16.1"),
            pyproject=PYPROJECT.format(spec="==0.16.1"),
        ) as path:
            code, text = self.run_main(path)
        self.assertEqual(code, 0)
        self.assertIn("2 Stellen", text)

    def test_eigener_ci_pin_ist_rot(self):
        """Die Gegenprobe zur Konsolidierung.

        Beide verbleibenden Stellen stimmen ueberein — der Gleichstands-Test
        allein bliebe also gruen. Rot wird es nur, weil das Fehlen des
        CI-Pins eigens geprueft wird.
        """
        with root(
            workflow=WORKFLOW.format(version="0.16.1"),
            precommit=PRECOMMIT.format(version="0.16.1"),
            pyproject=PYPROJECT.format(spec="==0.16.1"),
        ) as path:
            code, text = self.run_main(path)
        self.assertEqual(code, 1)
        self.assertIn("EIGENER CI-PIN", text)

    def test_einzelner_pin_wird_nicht_als_vergleich_ausgegeben(self):
        """Gruen, aber sichtbar ohne Gegenstueck.

        Ein blosses «OK» laese sich hier als bestandener Abgleich lesen, und
        genau der hat nicht stattgefunden.
        """
        with root(pyproject=PYPROJECT.format(spec="==0.16.1")) as path:
            code, text = self.run_main(path)
        self.assertEqual(code, 0)
        self.assertIn("nur an einer Stelle", text)

    def test_fehlende_ruff_angabe_ist_rot(self):
        """Die Gegenprobe zum Gleichstands-Vergleich.

        Die pre-commit-`rev` bleibt als einzige Stelle stehen und stimmt damit
        zwangslaeufig mit sich selbst ueberein — der DRIFT-Vergleich sieht
        nichts, und die LOSE-Pruefung auch nicht, denn es gibt keinen Spec, der
        lose sein koennte. Rot wird es nur, weil das Fehlen der Deklaration
        eigens geprueft wird.
        """
        with root(
            workflow=WORKFLOW_OHNE_PIN,
            precommit=PRECOMMIT.format(version="0.16.1"),
            pyproject=PYPROJECT_OHNE_RUFF,
        ) as path:
            code, text = self.run_main(path)
        self.assertEqual(code, 1)
        self.assertIn("KEIN PIN", text)
        self.assertNotIn("DRIFT", text)
        self.assertNotIn("LOSE", text)

    def test_fehlende_ruff_angabe_auch_ohne_pre_commit_rot(self):
        """Ohne Hook-Datei bleibt gar keine Stelle uebrig — erst recht rot."""
        with root(workflow=WORKFLOW_OHNE_PIN, pyproject=PYPROJECT_OHNE_RUFF) as path:
            code, text = self.run_main(path)
        self.assertEqual(code, 1)
        self.assertIn("KEIN PIN", text)

    def test_loser_spec_meldet_nicht_zusaetzlich_kein_pin(self):
        """`ruff>=0.4.0` ist deklariert, nur eben nicht exakt.

        Ohne diese Abgrenzung liesse sich die neue Zusicherung auch so
        schreiben, dass sie auf jede nicht-exakte Angabe anspringt — dann
        stuenden bei einem offenen Bereich zwei Befunde fuer einen Fehler.
        """
        with root(
            workflow=WORKFLOW_OHNE_PIN,
            pyproject=PYPROJECT.format(spec=">=0.4.0"),
        ) as path:
            code, text = self.run_main(path)
        self.assertEqual(code, 1)
        self.assertIn("LOSE", text)
        self.assertNotIn("KEIN PIN", text)


class RuffPinsImRepo(unittest.TestCase):
    """Gegen die echten Dateien — hier faellt auf, wenn ein Muster ins Leere greift.

    Die Faelle oben bauen sich ihre Eingabe selbst und koennen deshalb nicht
    zeigen, dass die Muster auf DIESEM Repo etwas finden. Benennt jemand eine
    Datei um oder aendert die Schreibweise des Hook-Repos, liefern sie still
    eine leere Liste, und «keine Abweichung gefunden» sieht aus wie Einigkeit.
    """

    def test_beide_stellen_liefern_einen_pin(self):
        pins = cvs.ruff_pins(cvs.ROOT)
        self.assertEqual(len(pins), 2, f"erwartet: pyproject + pre-commit, gefunden: {pins}")
        for label, pin in pins:
            self.assertRegex(pin, r"^\d+\.\d+\.\d+$", f"{label}: {pin!r} sieht nicht aus wie ruff")

    def test_die_beiden_pins_sind_gleich(self):
        pins = cvs.ruff_pins(cvs.ROOT)
        self.assertEqual(len({pin for _, pin in pins}), 1, f"ruff-Pins weichen ab: {pins}")

    def test_kein_workflow_installiert_eigenes_ruff(self):
        """Die dritte Stelle ist weg und soll wegbleiben.

        Ein wieder eingefuegter `pip install ruff==` wuerde die beiden Pins
        oben stillschweigend aushebeln — er laeuft nach dem dev-Extra und
        ueberschreibt es. Beide blieben dabei gleich, der Test oben also gruen,
        und trotzdem liefe in der CI eine andere Version.
        """
        self.assertEqual(cvs.ruff_in_workflows(cvs.ROOT), [])


if __name__ == "__main__":
    unittest.main()
