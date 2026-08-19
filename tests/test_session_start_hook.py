#!/usr/bin/env python3
"""Der SessionStart-Hook meldet einen veralteten Klon — und blockiert nie.

Die Reihenfolge der Zusicherungen ist die des Auftrags: Fail-open steht vor
Korrektheit. Ein Hook, der bei Netzproblemen die Arbeit anhaelt, wird nach dem
zweiten Mal abgeschaltet und schuetzt danach gar nichts.

Geprueft wird gegen echte Git-Repos in einem Temp-Verzeichnis, nicht gegen
handgeschriebene Fixtures: eine Fixture kodiert die Annahme des Autors ueber
git-Verhalten und kann sie nicht widerlegen. Genau die Annahme «Standard-Branch
heisst main» ist der Fehler, gegen den dieser Hook gebaut ist.

Kein Netz noetig — die Remotes sind lokale Pfade; `git ls-remote --symref` und
`git fetch` sprechen dieselbe Mechanik wie ueber HTTPS.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "check-clone-freshness.sh"
SETTINGS = ROOT / ".claude" / "settings.json"

# Reproduzierbare Git-Umgebung: ohne abgeklemmte globale Config entscheidet die
# `init.defaultBranch` des Ausfuehrenden mit, und der Test misst dessen Setup.
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_AUTHOR_DATE": "2026-08-19T12:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-08-19T12:00:00+00:00",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_TERMINAL_PROMPT": "0",
}


def git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, env=GIT_ENV, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def run_hook(cwd: Path, payload: str = "", **env: str) -> subprocess.CompletedProcess:
    """Den Hook so aufrufen, wie Claude Code es tut: JSON auf stdin, cwd gesetzt."""
    return subprocess.run(
        [str(HOOK)],
        cwd=cwd,
        env={**GIT_ENV, "CLAUDE_PROJECT_DIR": str(cwd), **env},
        input=payload,
        capture_output=True,
        text=True,
        timeout=120,
    )


class HookFixture(unittest.TestCase):
    """Ein Origin mit `commits` Commits und ein Klon, der `behind` zurueckliegt."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def make(self, *, default_branch: str = "main", commits: int = 4, behind: int = 0) -> Path:
        origin = self.tmp / "origin"
        origin.mkdir()
        git(origin, "init", "-q", "-b", default_branch)
        for i in range(commits):
            (origin / "datei.txt").write_text(f"commit {i}\n", encoding="utf-8")
            git(origin, "add", "datei.txt")
            git(origin, "commit", "-q", "-m", f"commit {i}")

        clone = self.tmp / "klon"
        git(self.tmp, "clone", "-q", str(origin), str(clone))
        if behind:
            git(clone, "reset", "--hard", "-q", f"HEAD~{behind}")
        return clone


class MeldetAbstand(HookFixture):
    def test_meldet_die_zahl_der_fehlenden_commits(self):
        clone = self.make(commits=5, behind=3)
        res = run_hook(clone)
        self.assertEqual(res.returncode, 0)
        self.assertIn("3 Commits", res.stdout)
        self.assertIn("origin/main", res.stdout)

    def test_singular_bei_genau_einem_commit(self):
        clone = self.make(commits=3, behind=1)
        res = run_hook(clone)
        self.assertIn("1 Commit ", res.stdout)
        self.assertNotIn("1 Commits", res.stdout)

    def test_schweigt_wenn_nichts_fehlt(self):
        """Bei 0 kein Wort — sonst gewoehnt man sich die Meldung ab."""
        clone = self.make(commits=4, behind=0)
        res = run_hook(clone)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout, "")

    def test_eigene_commits_voraus_zaehlen_nicht_als_rueckstand(self):
        """`HEAD..FETCH_HEAD`, nicht `symmetric difference`."""
        clone = self.make(commits=3, behind=0)
        (clone / "neu.txt").write_text("lokal\n", encoding="utf-8")
        git(clone, "add", "neu.txt")
        git(clone, "commit", "-q", "-m", "lokale Arbeit")
        self.assertEqual(run_hook(clone).stdout, "")


class StandardBranchWirdErmittelt(HookFixture):
    """Die teuerste Annahme im Portfolio: der Standard-Branch heisse `main`."""

    def test_master_wird_erkannt(self):
        clone = self.make(default_branch="master", commits=5, behind=2)
        res = run_hook(clone)
        self.assertIn("2 Commits", res.stdout)
        self.assertIn("origin/master", res.stdout)

    def test_beliebiger_name_wird_erkannt(self):
        clone = self.make(default_branch="entwicklung", commits=4, behind=1)
        self.assertIn("origin/entwicklung", run_hook(clone).stdout)


class BlockiertNie(HookFixture):
    """Jede Stoerung endet mit Exit 0 und ohne Ausgabe."""

    def assert_still(self, res: subprocess.CompletedProcess):
        self.assertEqual(res.returncode, 0, f"Hook blockiert: {res.stderr}")
        self.assertEqual(res.stdout, "")

    def test_kein_git_repo(self):
        plain = self.tmp / "kein_repo"
        plain.mkdir()
        self.assert_still(run_hook(plain))

    def test_repo_ohne_remote(self):
        solo = self.tmp / "solo"
        solo.mkdir()
        git(solo, "init", "-q", "-b", "main")
        (solo / "a.txt").write_text("a\n", encoding="utf-8")
        git(solo, "add", "a.txt")
        git(solo, "commit", "-q", "-m", "a")
        self.assert_still(run_hook(solo))

    def test_repo_ohne_commits(self):
        leer = self.tmp / "leer"
        leer.mkdir()
        git(leer, "init", "-q", "-b", "main")
        git(leer, "remote", "add", "origin", str(self.tmp / "gibt-es-nicht"))
        self.assert_still(run_hook(leer))

    def test_unerreichbares_remote(self):
        """Der Fall, der den Hook sonst abschaltet: Remote antwortet nicht."""
        clone = self.make(commits=4, behind=2)
        git(clone, "remote", "set-url", "origin", str(self.tmp / "weg"))
        self.assert_still(run_hook(clone))

    def test_geloeschtes_remote_verzeichnis(self):
        clone = self.make(commits=4, behind=2)
        subprocess.run(["rm", "-rf", str(self.tmp / "origin")], check=True)
        self.assert_still(run_hook(clone))

    def test_detached_head_geht_durch(self):
        clone = self.make(commits=5, behind=0)
        git(clone, "checkout", "-q", "--detach", "HEAD~2")
        res = run_hook(clone)
        # Der Abstand ist auch losgeloest aussagekraeftig — Hauptsache, der
        # Hook stolpert nicht darueber.
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("2 Commits", res.stdout)

    def test_ohne_stdin_kein_haenger(self):
        """Aufruf von Hand, ohne Hook-JSON: darf nicht auf stdin warten."""
        clone = self.make(commits=4, behind=1)
        res = subprocess.run(
            [str(HOOK)],
            cwd=clone,
            env={**GIT_ENV, "CLAUDE_PROJECT_DIR": str(clone)},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("1 Commit", res.stdout)


class ZeitlimitGreift(HookFixture):
    """Das Zeitlimit ist die Zusicherung, die im Alltag am seltensten ausloest
    und am meisten kostet, wenn sie fehlt: ein haengender Netzaufruf haelt den
    Sessionstart auf, bis jemand den Hook abschaltet.

    Ein unerreichbares Remote taugt dafuer nicht als Probe — durch einen Proxy
    kommt sofort eine Absage zurueck, und der Test waere gruen, ohne je ein
    Zeitlimit beruehrt zu haben. Deshalb ein `git`, das wirklich haengt.
    """

    def hangs_on(self, verb: str) -> Path:
        """PATH-Verzeichnis mit einem `git`, das bei `verb` 30s haengt."""
        real_git = shutil.which("git") or "/usr/bin/git"
        shim_dir = self.tmp / f"shim-{verb}"
        shim_dir.mkdir()
        shim = shim_dir / "git"
        shim.write_text(
            "#!/usr/bin/env bash\n"
            'for a in "$@"; do\n'
            f'    if [ "$a" = "{verb}" ]; then sleep 30; exit 0; fi\n'
            "done\n"
            f'exec {real_git} "$@"\n',
            encoding="utf-8",
        )
        shim.chmod(0o755)
        return shim_dir

    def assert_bounded(self, verb: str):
        clone = self.make(commits=4, behind=2)
        shim = self.hangs_on(verb)
        start = time.monotonic()
        res = run_hook(
            clone,
            '{"source":"startup"}',
            PATH=f"{shim}{os.pathsep}{os.environ['PATH']}",
            CLAUDE_FRESHNESS_TIMEOUT="2",
        )
        elapsed = time.monotonic() - start
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout, "")
        # Grosszuegig gegenueber langsamer CI, aber weit unter den 30s des
        # Shims: ohne Zeitlimit laeuft dieser Test in den Timeout von run_hook.
        self.assertLess(elapsed, 15, f"{verb} nicht begrenzt: {elapsed:.1f}s")

    def test_haengendes_ls_remote_wird_abgebrochen(self):
        # Zugleich die Probe darauf, dass die Kommandosubstitution nicht auf
        # einem Kindprozess haengen bleibt, der stdout noch offen haelt.
        self.assert_bounded("ls-remote")

    def test_haengendes_fetch_wird_abgebrochen(self):
        self.assert_bounded("fetch")


class QuelleUndRegistrierung(HookFixture):
    def test_compact_ist_kein_sessionstart(self):
        clone = self.make(commits=5, behind=3)
        payload = json.dumps({"hook_event_name": "SessionStart", "source": "compact"})
        self.assertEqual(run_hook(clone, payload).stdout, "")

    def test_startup_meldet(self):
        clone = self.make(commits=5, behind=3)
        payload = json.dumps({"hook_event_name": "SessionStart", "source": "startup"})
        self.assertIn("3 Commits", run_hook(clone, payload).stdout)

    def test_hook_ist_ausfuehrbar(self):
        self.assertTrue(HOOK.is_file(), f"{HOOK} fehlt")
        self.assertTrue(os.access(HOOK, os.X_OK), f"{HOOK} ist nicht ausfuehrbar")

    def test_in_settings_registriert(self):
        conf = json.loads(SETTINGS.read_text(encoding="utf-8"))
        commands = [
            h.get("command", "")
            for entry in conf.get("hooks", {}).get("SessionStart", [])
            for h in entry.get("hooks", [])
        ]
        self.assertTrue(commands, "Kein SessionStart-Hook in .claude/settings.json")
        self.assertTrue(
            any(HOOK.name in c for c in commands),
            f"{HOOK.name} nicht in SessionStart registriert: {commands}",
        )
        for c in commands:
            resolved = c.replace("$CLAUDE_PROJECT_DIR", str(ROOT))
            self.assertTrue(Path(resolved).is_file(), f"Registrierter Pfad fehlt: {c}")

    def test_begruendung_ist_hinterlegt(self):
        """Ohne das Datum ist die Meldung eine Meinung; mit ihm ein Befund."""
        readme = (HOOK.parent / "README.md").read_text(encoding="utf-8")
        self.assertIn("3.8.2026", readme)
        self.assertIn("3.8.2026", HOOK.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
