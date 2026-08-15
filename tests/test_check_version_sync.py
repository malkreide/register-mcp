#!/usr/bin/env python3
"""Tests fuer scripts/check_version_sync.py — den ruff-Pin-Abgleich.

Der Pin steht an drei Stellen: `.github/workflows/ci.yml`, `pyproject.toml
[dev]` und `.pre-commit-config.yaml`. Keine davon merkt, wenn eine andere
abweicht. Wer nur zwei anhebt, formatiert lokal mit der einen Version und
prueft im Gate mit der anderen — rot wird das erst in der CI, mit einem Diff,
in dem die Ursache nicht steht.

Der Abgleich existiert genau dagegen. Ohne Test waere er selbst die Sorte
Zusicherung, die stillschweigend nichts prueft: Ein Regex, der ins Leere
greift, liefert `None`, und `None == None` sieht aus wie Einigkeit.

Nur Standardbibliothek, kein Netz.
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_version_sync as cvs  # noqa: E402


class RuffPinsImRepo(unittest.TestCase):
    """Gegen die echten Dateien — hier faellt auf, wenn ein Regex ins Leere greift."""

    def test_alle_drei_stellen_liefern_einen_pin(self):
        pins = cvs.collect_ruff_pins()
        self.assertEqual(len(pins), 3)
        for label, pin in pins:
            self.assertIsNotNone(pin, f"{label}: kein Pin gefunden — Regex oder Datei geaendert")
            self.assertRegex(pin, r"^\d+\.\d+\.\d+$", f"{label}: {pin!r} sieht nicht aus wie ruff")

    def test_die_drei_pins_sind_gleich(self):
        pins = cvs.collect_ruff_pins()
        self.assertEqual(
            len({pin for _, pin in pins}),
            1,
            f"ruff-Pins weichen ab: {pins}",
        )

    def test_check_ruff_pins_geht_auf_dem_repo_durch(self):
        cvs.check_ruff_pins()  # kein SystemExit


class RuffPinsKuenstlich(unittest.TestCase):
    """Die beiden Fehlerfaelle, die im Repo (hoffentlich) nie eintreten."""

    def _pins_aus(self, ci: str, proj: str, pre: str):
        tmp = Path(self.tmpdir.name)
        (tmp / "ci.yml").write_text(ci, encoding="utf-8")
        (tmp / "pyproject.toml").write_text(proj, encoding="utf-8")
        (tmp / "pre-commit.yaml").write_text(pre, encoding="utf-8")
        return (
            ("ci.yml", tmp / "ci.yml", re.compile(r"pip install ruff==([0-9][^\s\"']*)")),
            ("pyproject", tmp / "pyproject.toml", re.compile(r'"ruff==([0-9][^"]*)"')),
            ("pre-commit", tmp / "pre-commit.yaml", re.compile(r"rev:\s*v([0-9][^\s]*)")),
        )

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._orig = cvs._RUFF_PINS

    def tearDown(self):
        cvs._RUFF_PINS = self._orig

    def test_abweichende_pins_beenden_mit_exit_1(self):
        cvs._RUFF_PINS = self._pins_aus(
            "run: pip install ruff==0.16.1\n",
            '    "ruff==0.16.2",\n',
            "    rev: v0.16.1\n",
        )
        with self.assertRaises(SystemExit) as cm:
            cvs.check_ruff_pins()
        self.assertEqual(cm.exception.code, 1)

    def test_ein_fehlender_pin_beendet_mit_exit_1(self):
        cvs._RUFF_PINS = self._pins_aus(
            "run: pip install ruff==0.16.1\n",
            "    # kein Pin hier\n",
            "    rev: v0.16.1\n",
        )
        with self.assertRaises(SystemExit) as cm:
            cvs.check_ruff_pins()
        self.assertEqual(cm.exception.code, 1)

    def test_wenn_ueberall_der_pin_fehlt_ist_das_kein_gruen(self):
        """Der Fall, an dem die `missing`-Pruefung als Einzige haengt.

        Fehlt an einer Stelle der Pin, faellt schon der Mengenvergleich auf
        `{"0.16.1", None}`. Fehlt er ueberall, ist die Menge `{None}` — die
        Stellen sind dann «einig», und ohne diese Pruefung meldete der Check
        Synchronitaet, ohne je etwas verglichen zu haben. Genau so verschwindet
        eine Zusicherung: nicht mit einem Fehler, sondern mit einem Haken.
        """
        cvs._RUFF_PINS = self._pins_aus(
            "run: pip install ruff\n",
            "    # kein Pin hier\n",
            "    # und hier auch nicht\n",
        )
        self.assertEqual({pin for _, pin in cvs.collect_ruff_pins()}, {None})
        with self.assertRaises(SystemExit) as cm:
            cvs.check_ruff_pins()
        self.assertEqual(cm.exception.code, 1)

    def test_gleiche_pins_gehen_durch(self):
        cvs._RUFF_PINS = self._pins_aus(
            "run: pip install ruff==0.16.1\n",
            '    "ruff==0.16.1",\n',
            "    rev: v0.16.1\n",
        )
        cvs.check_ruff_pins()

    def test_main_fuehrt_den_abgleich_wirklich_aus(self):
        """Die Verdrahtung, nicht nur die Funktion.

        `check_ruff_pins` einzeln zu pruefen belegt nicht, dass `main` sie
        aufruft — und nur `main` laeuft im Gate. Ohne diesen Test bliebe die
        Suite gruen, wenn jemand den Aufruf entfernt.
        """
        cvs._RUFF_PINS = self._pins_aus(
            "run: pip install ruff==0.16.1\n",
            '    "ruff==0.16.2",\n',
            "    rev: v0.16.1\n",
        )
        with self.assertRaises(SystemExit) as cm:
            cvs.main()
        self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
