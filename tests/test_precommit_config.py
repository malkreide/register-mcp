#!/usr/bin/env python3
"""Der pre-commit-Hook muss denselben Umfang sehen wie das Gate.

`ruff format` formatiert auch Python-Bloecke *innerhalb* von Markdown, und die
CI faehrt `ruff format --check … docs/`. Der Hook `ruff-format` bringt aber von
Haus aus `types_or: [python, pyi, jupyter]` mit — Markdown erreicht ihn damit
nie. Ein neuer ```python-Block in einer Doku committet dann sauber durch und
faellt erst im Gate: genau die Sorte roter CI, deren Ursache nicht im Diff
steht.

Der Test liest die Config als Text und nicht als YAML, weil `pyyaml` keine
Projekt-Abhaengigkeit ist und dieser Check keine rechtfertigt.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRECOMMIT = ROOT / ".pre-commit-config.yaml"
CI = ROOT / ".github" / "workflows" / "ci.yml"


class HookUmfang(unittest.TestCase):
    def setUp(self):
        self.text = PRECOMMIT.read_text(encoding="utf-8")

    def test_ruff_format_sieht_auch_markdown(self):
        block = re.search(r"- id: ruff-format\n(.*?)(?=\n *- id: |\Z)", self.text, re.DOTALL)
        self.assertIsNotNone(block, "Hook `ruff-format` nicht gefunden")
        types_or = re.search(r"types_or:\s*\[([^\]]*)\]", block.group(1))
        self.assertIsNotNone(
            types_or,
            "`ruff-format` ohne eigenes `types_or` — der Standard laesst Markdown aus, "
            "waehrend die CI `docs/` mitformatiert",
        )
        declared = {t.strip() for t in types_or.group(1).split(",")}
        self.assertIn("markdown", declared)
        # Die Standardtypen duerfen dabei nicht verloren gehen: `types_or`
        # ersetzt die Vorgabe des Hooks, es ergaenzt sie nicht.
        self.assertLessEqual({"python", "pyi"}, declared)

    def test_hooks_decken_den_gate_umfang_ab(self):
        """Dieselben Verzeichnisse wie `ruff … src/ tests/ scripts/ docs/`."""
        gate = re.search(r"ruff format --check ([^\n]+)", CI.read_text(encoding="utf-8"))
        self.assertIsNotNone(gate, "Format-Schritt in ci.yml nicht gefunden")
        dirs = {d.strip().rstrip("/") for d in gate.group(1).split() if d.strip()}
        self.assertTrue(dirs, "Gate ohne Verzeichnisse — dann prueft dieser Test nichts")
        for pattern in re.findall(r"files:\s*\^\(([^)]*)\)/", self.text):
            covered = set(pattern.split("|"))
            self.assertEqual(
                covered,
                dirs,
                f"pre-commit deckt {sorted(covered)} ab, das Gate {sorted(dirs)}",
            )


if __name__ == "__main__":
    unittest.main()
