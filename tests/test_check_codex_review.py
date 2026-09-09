"""Gegen `scripts/check_codex_review.py` — die Entscheidung, offline.

Der Gate haengt an Textformen, die Codex aendern kann. Diese Faelle halten
fest, welche Form am 8./9.9.2026 tatsaechlich beobachtet wurde; aendert Codex
sie, faellt hier etwas, statt dass der Job in der CI still durchwinkt.

Die Eingaben sind bewusst die echten Ausschnitte aus den beobachteten
Kommentaren, nicht ausgedachte Kurzformen: Ein Test, der eine vereinfachte
Fassung prueft, kann nicht zeigen, dass das Muster auf dem echten Text greift.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_codex_review as ccr  # noqa: E402

HEAD = "eb5296937b3a96d55c2f22748372f4fc88c2b887"

# Woertlich aus PR #104, nur die Tabellenzeile gekuerzt.
TABELLE_FERTIG = """<!-- codex-pull-request-review-summary -->

## Codex Review Summary

| Review | Status | Commit | Review trigger |
| --- | --- | --- | --- |
| 📝 **Code Review** | ✅ **Completed** <relative-time datetime="2026-09-08T04:33:20Z">\
2026-09-08T04:33:20Z</relative-time> | `eb52969` | Draft marked ready |
"""

TABELLE_LAEUFT = """<!-- codex-pull-request-review-summary -->

## Codex Review Summary

| Review | Status | Commit | Review trigger |
| --- | --- | --- | --- |
| 📝 **Code Review** | 🔄 **Running** since <relative-time datetime="2026-09-08T04:31:45Z">\
2026-09-08T04:31:45Z</relative-time> | `eb52969` | Draft marked ready |
"""

TABELLE_FREMDER_COMMIT = TABELLE_FERTIG.replace("`eb52969`", "`1e186c4`")


def _kommentar(body: str, autor: str = ccr.CODEX_LOGIN) -> dict:
    return {"user": {"login": autor}, "body": body}


def _entscheide(**abweichung):
    argumente = {
        "ist_draft": False,
        "autor_typ": "User",
        "kommentare": [],
        "reviews": [],
        "head_sha": HEAD,
    }
    argumente.update(abweichung)
    return ccr.entscheide(**argumente)


class DieBeobachtetenFormen(unittest.TestCase):
    def test_summary_tabelle_completed_laesst_durch(self):
        zustand, _ = _entscheide(kommentare=[_kommentar(TABELLE_FERTIG)])
        self.assertEqual(zustand, ccr.BESTANDEN)

    def test_summary_tabelle_running_haelt_auf(self):
        """Der Zustand, in dem drei PRs gemergt wurden — er darf nicht genuegen."""
        zustand, _ = _entscheide(kommentare=[_kommentar(TABELLE_LAEUFT)])
        self.assertEqual(zustand, ccr.WARTEN)

    def test_aeltere_befundlos_meldung_laesst_durch(self):
        body = "Codex Review: Didn't find any major issues. Swish!"
        zustand, _ = _entscheide(kommentare=[_kommentar(body)])
        self.assertEqual(zustand, ccr.BESTANDEN)

    def test_wechselnder_schlusssatz_aendert_nichts(self):
        """Nur der Satz davor ist stabil; «Swish!» wechselt bei jedem Lauf."""
        body = "Codex Review: Didn't find any major issues. Delightful!"
        zustand, _ = _entscheide(kommentare=[_kommentar(body)])
        self.assertEqual(zustand, ccr.BESTANDEN)

    def test_review_objekt_laesst_durch(self):
        """Ein Befund ist ein Urteil. Ihn zu beheben ist Sache des Autors."""
        reviews = [{"user": {"login": ccr.CODEX_LOGIN}, "body": "💡 Codex Review"}]
        zustand, _ = _entscheide(reviews=reviews)
        self.assertEqual(zustand, ccr.BESTANDEN)


class AusfaelleSindKeinUrteil(unittest.TestCase):
    """Die beiden Meldungen, hinter denen dreissig bzw. dreiundvierzig PRs
    ungeprueft durchgingen. Sie sehen aus wie eine Aeusserung von Codex und
    heissen doch: hat nicht hingesehen."""

    def test_kontingent_faellt(self):
        zustand, grund = _entscheide(kommentare=[_kommentar(ccr.TEXT_KONTINGENT)])
        self.assertEqual(zustand, ccr.GEFALLEN)
        self.assertIn("Kontingent", grund)

    def test_environment_faellt(self):
        zustand, grund = _entscheide(kommentare=[_kommentar(ccr.TEXT_ENVIRONMENT)])
        self.assertEqual(zustand, ccr.GEFALLEN)
        self.assertIn("Environment", grund)

    def test_schweigen_haelt_auf(self):
        zustand, _ = _entscheide(kommentare=[])
        self.assertEqual(zustand, ccr.WARTEN)


class UnbekanntesWirdZitiertStattEingeordnet(unittest.TestCase):
    """CLAUDE.md: einen unbekannten Text woertlich zitieren, statt ihn in eine
    der bekannten Schubladen zu zwingen. Der Abschnitt musste schon von drei
    auf vier Gruende wachsen, und die Befundlos-Form hat inzwischen eine
    zweite."""

    def test_unbekannter_codex_text_faellt(self):
        zustand, _ = _entscheide(kommentare=[_kommentar("Codex is taking a nap.")])
        self.assertEqual(zustand, ccr.GEFALLEN)

    def test_der_unbekannte_text_steht_woertlich_in_der_meldung(self):
        zustand, grund = _entscheide(kommentare=[_kommentar("Codex is taking a nap.")])
        self.assertEqual(zustand, ccr.GEFALLEN)
        self.assertIn("Codex is taking a nap.", grund)


class NurCodexZaehlt(unittest.TestCase):
    def test_ein_mensch_kann_den_gate_nicht_erfuellen(self):
        """Sonst genuegte ein Kommentar mit dem richtigen Wortlaut."""
        kommentare = [_kommentar(TABELLE_FERTIG, autor="malkreide")]
        zustand, _ = _entscheide(kommentare=kommentare)
        self.assertEqual(zustand, ccr.WARTEN)

    def test_ein_fremder_bot_zaehlt_nicht(self):
        kommentare = [_kommentar(TABELLE_FERTIG, autor="dependabot[bot]")]
        zustand, _ = _entscheide(kommentare=kommentare)
        self.assertEqual(zustand, ccr.WARTEN)


class DasUrteilGehoertZumHead(unittest.TestCase):
    def test_urteil_ueber_einen_anderen_commit_faellt(self):
        """Sonst winkt ein alter Review neuen Code durch — dasselbe gruene
        Haekchen fuer Ungeprueftes, gegen das der Gate gebaut ist."""
        zustand, grund = _entscheide(kommentare=[_kommentar(TABELLE_FREMDER_COMMIT)])
        self.assertEqual(zustand, ccr.GEFALLEN)
        self.assertIn("@codex review", grund)

    def test_die_befundlos_form_nennt_keinen_commit_und_zaehlt_trotzdem(self):
        """Eine fehlende Angabe wird nicht erfunden."""
        body = "Codex Review: Didn't find any major issues. Swish!"
        zustand, _ = _entscheide(kommentare=[_kommentar(body)])
        self.assertEqual(zustand, ccr.BESTANDEN)


class DieBeidenAusnahmen(unittest.TestCase):
    def test_draft_geht_durch(self):
        """Codex laeuft darauf nicht an, und mergen laesst sich ein Draft nicht."""
        zustand, _ = _entscheide(ist_draft=True)
        self.assertEqual(zustand, ccr.BESTANDEN)

    def test_bot_autor_geht_durch(self):
        """Gemessen: #101 und #103 tragen null Codex-Kommentare. Ohne diese
        Ausnahme haengt jeder Dependabot-PR fest, und ein Gate, das alles
        aufhaelt, wird abgeschaltet."""
        zustand, _ = _entscheide(autor_typ="Bot")
        self.assertEqual(zustand, ccr.BESTANDEN)

    def test_ein_mensch_geniesst_die_bot_ausnahme_nicht(self):
        zustand, _ = _entscheide(autor_typ="User")
        self.assertEqual(zustand, ccr.WARTEN)


class DerGateIstRegistriert(unittest.TestCase):
    """Ein Skript, das kein Workflow aufruft, prueft nichts."""

    WORKFLOW = Path(__file__).resolve().parent.parent / ".github/workflows/codex-gate.yml"

    def test_workflow_existiert(self):
        self.assertTrue(self.WORKFLOW.is_file(), f"fehlt: {self.WORKFLOW}")

    def test_workflow_ruft_das_skript_auf(self):
        text = self.WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("scripts/check_codex_review.py", text)

    def test_workflow_laeuft_auf_ready_for_review(self):
        """Der Ausloeser, um den es geht. Die Vorgabe von `pull_request` enthaelt
        `ready_for_review` NICHT — ohne die Zeile liefe der Gate genau in dem
        Moment nicht, in dem Codex anlaeuft.

        Geprueft wird die `types:`-Zeile, nicht die Datei: Der Kopfkommentar
        erklaert denselben Namen, und ein `assertIn` ueber den ganzen Text blieb
        gruen, als der Ausloeser aus `types:` entfernt wurde. Genau dieser
        Fehlalarm — ein Muster, das die Prosa trifft statt die Konfiguration —
        ist bei der Gegenprobe aufgefallen.
        """
        zeilen = self.WORKFLOW.read_text(encoding="utf-8").splitlines()
        typen = [z for z in zeilen if z.strip().startswith("types:")]
        self.assertEqual(len(typen), 1, f"erwartet: genau eine types-Zeile, gefunden: {typen}")
        self.assertIn("ready_for_review", typen[0])

    def test_workflow_darf_pull_requests_lesen(self):
        """Ohne die Berechtigung sieht der Gate keine Kommentare und waere
        dauerhaft rot."""
        text = self.WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull-requests: read", text)


if __name__ == "__main__":
    unittest.main()
