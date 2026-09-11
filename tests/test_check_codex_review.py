"""Gegen `scripts/check_codex_review.py` — die Entscheidung, offline.

Der Gate haengt an Textformen, die Codex aendern kann. Diese Faelle halten
fest, welche Form am 8./9.9.2026 tatsaechlich beobachtet wurde; aendert Codex
sie, faellt hier etwas, statt dass der Job in der CI still durchwinkt.

Die Eingaben sind bewusst die echten Ausschnitte aus den beobachteten
Kommentaren, nicht ausgedachte Kurzformen: Ein Test, der eine vereinfachte
Fassung prueft, kann nicht zeigen, dass das Muster auf dem echten Text greift.
"""

from __future__ import annotations

import re
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

# Woertlich aus PR #108: Seit dem 9.9.2026 nennt auch die aeltere Form ihren
# Commit — und der Schlusssatz wechselt weiterhin.
BEFUNDLOS_MIT_COMMIT = """Codex Review: Didn't find any major issues. Another round soon, please!

**Reviewed commit:** `eb5296937b3`
"""


def _kommentar(body: str, autor: str = ccr.CODEX_LOGIN) -> dict:
    return {"user": {"login": autor}, "body": body}


def _review(commit_id: str | None, autor: str = ccr.CODEX_LOGIN) -> dict:
    """Ein Review-Objekt, wie die API es liefert — mit `commit_id`.

    Die erste Fassung dieses Tests liess das Feld weg, und genau deshalb fiel
    nicht auf, dass der Review-Zweig den Commit gar nicht prueft.
    """
    review = {"user": {"login": autor}, "body": "💡 Codex Review"}
    if commit_id is not None:
        review["commit_id"] = commit_id
    return review


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
        reviews = [_review(HEAD)]
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

    def test_ein_review_objekt_zu_einem_anderen_commit_faellt(self):
        """Das Falsch-Gruen vom 9.9.2026 auf PR #108.

        Der Review-Zweig pruefte nur den Autor, nicht den Commit. Auf dem
        neuen Head `1503a1a` lag nur ein Review zu `697ecdc` vor — der Gate
        war nach acht Sekunden gruen, 28 Sekunden BEVOR Codex den Review fuer
        diesen Commit ueberhaupt begann. Ein gruenes Haekchen fuer
        Ungeprueftes, also genau das, wogegen der Gate gebaut ist.
        """
        zustand, grund = _entscheide(reviews=[_review("697ecdc0c1b75cf6c61018bfdb0f0650")])
        self.assertEqual(zustand, ccr.GEFALLEN)
        self.assertIn("@codex review", grund)

    def test_ein_review_ohne_commit_angabe_zaehlt(self):
        """Eine fehlende Angabe wird nicht erfunden — wie bei der aelteren
        Befundlos-Form, die auch keinen Commit nennt."""
        zustand, _ = _entscheide(reviews=[_review(None)])
        self.assertEqual(zustand, ccr.BESTANDEN)

    def test_ein_passendes_review_neben_einem_veralteten_zaehlt(self):
        """Nach `@codex review` stehen beide da. Das juengere gilt."""
        reviews = [_review("697ecdc0c1b75cf6c61018bfdb0f0650"), _review(HEAD)]
        zustand, _ = _entscheide(reviews=reviews)
        self.assertEqual(zustand, ccr.BESTANDEN)

    def test_die_befundlos_form_ohne_commit_zaehlt_trotzdem(self):
        """Eine fehlende Angabe wird nicht erfunden — so sah die Form bis zum
        8.9.2026 aus."""
        body = "Codex Review: Didn't find any major issues. Swish!"
        zustand, _ = _entscheide(kommentare=[_kommentar(body)])
        self.assertEqual(zustand, ccr.BESTANDEN)

    def test_die_befundlos_form_mit_passendem_commit_zaehlt(self):
        zustand, _ = _entscheide(kommentare=[_kommentar(BEFUNDLOS_MIT_COMMIT)])
        self.assertEqual(zustand, ccr.BESTANDEN)

    def test_die_befundlos_form_zu_einem_anderen_commit_faellt(self):
        """Die dritte Stelle derselben Klasse.

        Seit dem 9.9.2026 traegt auch die Befundlos-Meldung «Reviewed commit».
        Ohne Pruefung winkte eine alte Meldung neuen Code durch — wie zuvor
        beim Review-Objekt und bei der Tabelle.
        """
        fremd = BEFUNDLOS_MIT_COMMIT.replace("eb5296937b3", "697ecdc0c1b")
        zustand, grund = _entscheide(kommentare=[_kommentar(fremd)])
        self.assertEqual(zustand, ccr.GEFALLEN)
        self.assertIn("@codex review", grund)


class DieBotAusnahme(unittest.TestCase):
    def test_bot_autor_geht_durch(self):
        """Gemessen: #101 und #103 tragen null Codex-Kommentare. Ohne diese
        Ausnahme haengt jeder Dependabot-PR fest, und ein Gate, das alles
        aufhaelt, wird abgeschaltet."""
        zustand, _ = _entscheide(autor_typ="Bot")
        self.assertEqual(zustand, ccr.BESTANDEN)

    def test_ein_mensch_geniesst_die_bot_ausnahme_nicht(self):
        zustand, _ = _entscheide(autor_typ="User")
        self.assertEqual(zustand, ccr.WARTEN)

    def test_die_bot_ausnahme_gilt_auch_im_draft(self):
        """Sonst haenge ein Dependabot-Draft am Draft-Fall fest, den es nur
        wegen menschlicher PRs gibt."""
        zustand, _ = _entscheide(autor_typ="Bot", ist_draft=True)
        self.assertEqual(zustand, ccr.BESTANDEN)


class DerDraftDarfNichtBestehen(unittest.TestCase):
    """Das Zeitfenster, das die erste Fassung offen liess.

    Beim Umschalten auf «ready for review» aendert sich der Commit nicht. Bis
    der neue Lauf angelegt ist, bleibt der Draft-Lauf der juengste fuer diesen
    Commit — auf PR #106 zwei Sekunden (ready 03:28:17, neuer Lauf 03:28:19).
    Bestand er, laese ein required-Check dort gruen, und genau in diesem
    Fenster lagen die Merges.
    """

    def test_draft_faellt(self):
        zustand, _ = _entscheide(ist_draft=True)
        self.assertEqual(zustand, ccr.GEFALLEN)

    def test_der_draft_faellt_nicht_wartend_sondern_endgueltig(self):
        """WARTEN liesse den Job 300s pollen, ohne dass sich etwas aendern
        kann: Codex laeuft auf einem Draft gar nicht erst an."""
        zustand, _ = _entscheide(ist_draft=True)
        self.assertNotEqual(zustand, ccr.WARTEN)

    def test_die_meldung_nennt_den_zustand_als_erwartet(self):
        """Ein roter Check ohne Erklaerung sieht aus wie ein Defekt, und ein
        Gate, den man fuer defekt haelt, wird abgeschaltet."""
        _, grund = _entscheide(ist_draft=True)
        self.assertIn("erwartet", grund)
        self.assertIn("ready for review", grund)


class WennDieFristVerstreicht(unittest.TestCase):
    """«Laeuft noch» und «schweigt» verlangen Verschiedenes.

    Die erste Fassung kannte den Unterschied nicht und schrieb in beiden
    Faellen «bleibt es still, hat er nicht geprueft». Fuer einen laufenden
    Review ist das falsch: Es schickt jemanden Kontingent und Environment
    pruefen, waehrend Codex arbeitet.
    """

    def test_laufender_review_wird_nicht_als_ausfall_gemeldet(self):
        text = ccr.ablauf_grund("Summary-Tabelle steht auf Running.", 300)
        self.assertIn("laeuft noch", text)
        self.assertNotIn("hat sich nicht geaeussert", text)

    def test_laufender_review_nennt_den_stellhebel(self):
        text = ccr.ablauf_grund("Summary-Tabelle steht auf Running.", 300)
        self.assertIn("CODEX_FRIST_SEKUNDEN", text)

    def test_schweigen_wird_als_ungedeckt_gemeldet(self):
        text = ccr.ablauf_grund("Noch keine Aeusserung von Codex.", 300)
        self.assertIn("ungedeckt", text)
        self.assertNotIn("laeuft noch", text)

    def test_die_frist_hat_abstand_zur_gemessenen_dauer(self):
        """Gemessen brauchte Codex 79-105s (vier Laeufe, #102/#104/#105/#106).
        Die Vorgabe muss davon deutlich weg sein, sonst wird der Gate rot,
        waehrend Codex korrekt arbeitet — und ein Gate, der grundlos
        blockiert, wird abgeschaltet.

        Geprueft wird der Abstand, nicht die Zahl: Ein Test, der die Vorgabe
        bloss wiederholt, faellt bei jeder Aenderung und sagt nie, warum.
        """
        quelle = Path(ccr.__file__).read_text(encoding="utf-8")
        treffer = re.search(r'"CODEX_FRIST_SEKUNDEN", "(\d+)"', quelle)
        self.assertIsNotNone(treffer, "keine Vorgabe fuer CODEX_FRIST_SEKUNDEN gefunden")
        self.assertGreaterEqual(int(treffer.group(1)), 250, "zu nah an den gemessenen 105s")


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
        self.assertIn("ready_for_review", self._typen_zeile())

    def test_workflow_laeuft_auch_beim_zurueckstellen_auf_draft(self):
        """Sonst bleibt der GRUENE Lauf der juengste fuer denselben Commit.

        Wird ein bereits gepruefter PR zurueck auf Draft gestellt, aendert sich
        der Commit nicht. Ohne `converted_to_draft` laeuft nichts, der gruene
        Lauf bleibt stehen, und beim naechsten «ready» ist dasselbe Fenster
        wieder offen, das der rote Draft-Lauf schliessen soll. Befund aus dem
        Codex-Review auf PR #108.
        """
        self.assertIn("converted_to_draft", self._typen_zeile())

    def _typen_zeile(self) -> str:
        """Die `types:`-Zeile, nicht die Datei.

        Der Kopfkommentar erklaert dieselben Namen, und ein `assertIn` ueber den
        ganzen Text blieb gruen, als der Ausloeser aus `types:` entfernt wurde.
        """
        zeilen = self.WORKFLOW.read_text(encoding="utf-8").splitlines()
        typen = [z for z in zeilen if z.strip().startswith("types:")]
        self.assertEqual(len(typen), 1, f"erwartet: genau eine types-Zeile, gefunden: {typen}")
        return typen[0]

    def test_workflow_darf_pull_requests_lesen(self):
        """Ohne die Berechtigung sieht der Gate keine Kommentare und waere
        dauerhaft rot."""
        text = self.WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull-requests: read", text)


if __name__ == "__main__":
    unittest.main()
