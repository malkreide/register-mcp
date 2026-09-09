"""Haelt einen Pull Request auf, bis Codex ihn wirklich angesehen hat.

Der Anlass steht in CLAUDE.md: Codex wird beim Umschalten von Draft auf ready
ausgeloest und braucht danach rund zwei Minuten. Am 8./9.9.2026 lagen zwischen
«ready for review» und Merge dreimal drei bis fuenf Sekunden. Der Review lief
jedes Mal weiter — nur landete ein Befund dann auf einem gemergten PR.

Ein Ruleset allein loest das nicht: Codex meldet in diesem Repo **keinen**
Check-Run und **keinen** Commit-Status (gemessen auf PR #105: fuenf Check-Runs,
alle aus ci.yml, und `total_count: 0` bei den Status). Es gibt also nichts, was
man als *required* fuehren koennte. Dieses Skript ist der fehlende Check: Es
liest, was Codex tatsaechlich hinterlaesst — Kommentare und Review-Objekte —
und macht daraus einen Job, der rot ist, solange kein Urteil vorliegt.

Was als Urteil gilt, ist woertlich die Definition aus CLAUDE.md: ein
Review-Objekt, eine Befundlos-Meldung **oder** eine Summary-Tabelle im Zustand
`Completed`. Die Tabelle im Zustand `Running` gilt nicht — sie belegt nur den
Anlauf.

Das Skript urteilt **nicht** ueber den Inhalt eines Befunds. Ein Review mit
Findings laesst es passieren; dass Befunde beantwortet oder behoben werden,
steht in CLAUDE.md und ist Sache des Autors. Geprueft wird nur, ob ueberhaupt
jemand hingesehen hat.

Zwei Ausnahmen, beide gemessen und beide noetig:

  - **Drafts.** Codex laeuft darauf gar nicht an, und mergen laesst sich ein
    Draft ohnehin nicht. Ein Gate, das hier rot waere, blockierte nichts und
    verbrauchte nur Laufzeit.
  - **Bot-Autoren.** Codex prueft in diesem Repo keine Dependabot-PRs: #101 und
    #103 tragen null Codex-Kommentare (#101s einziger Kommentar war
    Dependabots eigene Schlussnotiz). Ohne diese Ausnahme haenge jeder
    Dependency-PR dauerhaft fest — der Gate wuerde abgeschaltet, und ein
    abgeschalteter Gate prueft nichts.

Verwendung (in der CI, siehe .github/workflows/codex-gate.yml):

    python scripts/check_codex_review.py     # exit 1, wenn kein Urteil vorliegt

Eine Einschraenkung, die man kennen muss: Das Skript haengt an Textformen, die
Codex jederzeit aendern kann — genau davor warnt CLAUDE.md, und genau das ist
am 8.9.2026 schon einmal passiert. Deshalb faellt es bei einem *unbekannten*
Codex-Text nicht still durch, sondern bricht ab und zitiert ihn woertlich. Wer
den Job rot sieht, liest die Meldung und weiss, ob Codex geschwiegen hat oder
ob bloss dieses Skript veraltet ist.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"

# Der HTML-Kommentar, mit dem Codex seine Summary-Tabelle markiert. Stabiler als
# die Ueberschrift: Er ist fuer Maschinen gedacht, die Ueberschrift fuer Menschen.
MARKER_TABELLE = "<!-- codex-pull-request-review-summary -->"

# Die Befundlos-Meldung der aelteren Form. Der Schlusssatz wechselt bei jedem
# Lauf («Swish!», «Delightful!»), stabil ist nur dieser Satz.
TEXT_BEFUNDLOS = "Didn't find any major issues"

# Die beiden Ausfallmeldungen. Sie sind KEIN Urteil — sie sagen, dass Codex gar
# nicht hingesehen hat, und sind der Grund, warum «kein Kommentar» und «alles in
# Ordnung» sich nicht an der Kommentarzahl unterscheiden lassen.
TEXT_KONTINGENT = "You have reached your Codex usage limits for code reviews."
TEXT_ENVIRONMENT = "To use Codex here, create an environment for this repo."

# Codex postet als App; der Login traegt das Bot-Suffix.
CODEX_LOGIN = "chatgpt-codex-connector[bot]"

BESTANDEN = "bestanden"
WARTEN = "warten"
GEFALLEN = "gefallen"


def _ist_codex(autor: str) -> bool:
    """Ob ein Kommentar oder Review von Codex stammt.

    Bewusst auf `chatgpt-codex-connector` und nicht auf «codex» geprueft: Ein
    Mensch mit «codex» im Namen soll den Gate nicht erfuellen koennen.
    """
    return autor.lower().startswith("chatgpt-codex-connector")


def _tabellen_zustand(body: str) -> tuple[str | None, str | None]:
    """Zustand und Commit aus der Summary-Tabelle — (Zustand, Commit-Praefix).

    Die Tabelle wird in derselben Kommentar-ID editiert: erst `Running`, dann
    `Completed`. Gelesen wird deshalb immer der aktuelle Stand, nie der, den
    der Kommentar beim Anlegen hatte.
    """
    zustand = None
    if "Completed" in body:
        zustand = "completed"
    elif "Running" in body:
        zustand = "running"

    # Der Commit steht als kurzer SHA in Backticks in der Tabellenzeile. Eine
    # Zeichenklasse statt einer Regex ueber die ganze Zeile: Die Tabelle traegt
    # mehrere Backtick-Felder, und nur eines davon sieht aus wie ein SHA.
    commit = None
    for stueck in body.split("`"):
        kandidat = stueck.strip()
        if 7 <= len(kandidat) <= 40 and all(z in "0123456789abcdef" for z in kandidat):
            commit = kandidat
            break
    return zustand, commit


def _passt_zum_head(commit: str | None, head_sha: str) -> bool:
    """Ob ein Urteil den aktuellen Head betrifft.

    Ohne diese Pruefung genuegte ein alter Review, um einen neuen Push
    durchzuwinken — dasselbe gruene Haekchen fuer ungeprueften Code, gegen das
    dieser Gate gebaut ist. Fehlt die Commit-Angabe (die aeltere Befundlos-Form
    nennt keine), wird sie nicht erfunden: Dann zaehlt das Urteil.
    """
    if commit is None:
        return True
    return head_sha.startswith(commit) or commit.startswith(head_sha[:7])


def entscheide(
    *,
    ist_draft: bool,
    autor_typ: str,
    kommentare: list[dict],
    reviews: list[dict],
    head_sha: str,
) -> tuple[str, str]:
    """Der ganze Gate als reine Funktion — (Zustand, Begruendung).

    Reine Funktion, damit die Faelle offline pruefbar sind. Ein Gate, dessen
    Logik nur im Netz laeuft, wird von Tests nicht erreicht und driftet.
    """
    if ist_draft:
        return BESTANDEN, "Draft: Codex laeuft nicht an, und mergen laesst sich ein Draft nicht."
    if autor_typ == "Bot":
        return BESTANDEN, "Bot-Autor: Codex prueft diese PRs nicht (gemessen an #101 und #103)."

    for review in reviews:
        autor = (review.get("user") or {}).get("login", "")
        if _ist_codex(autor):
            return BESTANDEN, "Review-Objekt von Codex vorhanden."

    zustand_tabelle = None
    commit_tabelle = None
    unbekannt = []

    for kommentar in kommentare:
        autor = (kommentar.get("user") or {}).get("login", "")
        if not _ist_codex(autor):
            continue
        body = kommentar.get("body", "")

        if MARKER_TABELLE in body:
            zustand_tabelle, commit_tabelle = _tabellen_zustand(body)
            continue
        if TEXT_BEFUNDLOS in body:
            return BESTANDEN, "Befundlos-Meldung vorhanden."
        if TEXT_KONTINGENT in body:
            return (
                GEFALLEN,
                f"Codex hat nicht geprueft — Kontingent erschoepft:\n  {TEXT_KONTINGENT}",
            )
        if TEXT_ENVIRONMENT in body:
            return GEFALLEN, f"Codex hat nicht geprueft — Environment fehlt:\n  {TEXT_ENVIRONMENT}"
        unbekannt.append(body.strip()[:400])

    if zustand_tabelle == "completed":
        if _passt_zum_head(commit_tabelle, head_sha):
            return BESTANDEN, f"Summary-Tabelle: Completed fuer {commit_tabelle or 'diesen Stand'}."
        grund = (
            f"Summary-Tabelle ist Completed, aber fuer {commit_tabelle} — "
            f"Head ist {head_sha[:7]}.\n"
            "Codex laeuft auf einen blossen Push nicht neu an. "
            "`@codex review` auf dem PR kommentieren."
        )
        return GEFALLEN, grund
    if zustand_tabelle == "running":
        return WARTEN, "Summary-Tabelle steht auf Running."

    if unbekannt:
        gefunden = "\n  ".join(unbekannt)
        grund = (
            "Codex hat etwas geschrieben, das dieses Skript nicht kennt.\n"
            "Woertlich:\n  " + gefunden + "\n"
            "Entweder ist es eine neue Form (dann dieses Skript und CLAUDE.md "
            "nachziehen) oder eine Ausfallmeldung (dann hat Codex nicht geprueft)."
        )
        return GEFALLEN, grund

    return WARTEN, "Noch keine Aeusserung von Codex."


def ablauf_grund(grund: str, frist: int) -> str:
    """Warum die Frist verstrich — «laeuft noch» ist etwas anderes als «schweigt».

    Der Unterschied entscheidet, was jemand tut. Steht die Tabelle auf `Running`,
    hat Codex angefangen und ist bloss langsam: warten oder die Frist heben.
    Kam gar nichts, hat er nicht geprueft, und der Merge waere ungedeckt.

    Die erste Fassung kannte den Unterschied nicht und schrieb in beiden Faellen
    «bleibt es still, hat er nicht geprueft». Das ist fuer den Running-Fall
    falsch und schickt jemanden Kontingent und Environment pruefen, waehrend
    der Review laeuft.
    """
    if "Running" in grund:
        return (
            f"{grund}\n"
            "Codex laeuft noch — das ist kein Ausfall, sondern Dauer. Die Frist "
            f"({frist}s) ist zu knapp: `CODEX_FRIST_SEKUNDEN` heben oder den Lauf "
            "abwarten und den Job neu starten."
        )
    return (
        f"{grund}\n"
        "Codex hat sich nicht geaeussert. Ein Merge waere hier ungedeckt: "
        "entweder ist der Review nicht angelaufen (Kontingent, Environment) "
        "oder er wurde nie ausgeloest."
    )


def _hole(pfad: str, token: str) -> list[dict]:
    """Eine GitHub-Liste holen. Netzfehler sind hier kein Urteil, sondern ein Abbruch."""
    anfrage = urllib.request.Request(
        f"{API}{pfad}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "register-mcp-codex-gate",
        },
    )
    with urllib.request.urlopen(anfrage, timeout=30) as antwort:  # noqa: S310
        return json.load(antwort)


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    nummer = os.environ.get("PR_NUMMER", "")
    head_sha = os.environ.get("PR_HEAD_SHA", "")
    ist_draft = os.environ.get("PR_IST_DRAFT", "") == "true"
    autor_typ = os.environ.get("PR_AUTOR_TYP", "")
    frist = int(os.environ.get("CODEX_FRIST_SEKUNDEN", "300"))
    takt = int(os.environ.get("CODEX_TAKT_SEKUNDEN", "15"))

    if not (token and repo and nummer and head_sha):
        print(
            "Fehlende Umgebung: GITHUB_TOKEN, GITHUB_REPOSITORY, PR_NUMMER, PR_HEAD_SHA.",
            file=sys.stderr,
        )
        return 2

    zustand, grund = entscheide(
        ist_draft=ist_draft,
        autor_typ=autor_typ,
        kommentare=[],
        reviews=[],
        head_sha=head_sha,
    )
    if zustand == BESTANDEN:
        print(f"Codex-Gate OK — {grund}")
        return 0

    ende = time.monotonic() + frist
    while True:
        try:
            kommentare = _hole(f"/repos/{repo}/issues/{nummer}/comments?per_page=100", token)
            reviews = _hole(f"/repos/{repo}/pulls/{nummer}/reviews?per_page=100", token)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as fehler:
            # Ein Netzfehler ist keine Auskunft ueber Codex. Weiterversuchen,
            # bis die Frist laeuft — und dann als Abbruch melden, nicht als
            # «nicht geprueft».
            print(f"GitHub nicht erreichbar ({fehler}); neuer Versuch.", file=sys.stderr)
            kommentare, reviews = [], []

        zustand, grund = entscheide(
            ist_draft=ist_draft,
            autor_typ=autor_typ,
            kommentare=kommentare,
            reviews=reviews,
            head_sha=head_sha,
        )
        if zustand == BESTANDEN:
            print(f"Codex-Gate OK — {grund}")
            return 0
        if zustand == GEFALLEN:
            print(f"Codex-Gate rot — {grund}", file=sys.stderr)
            return 1

        if time.monotonic() >= ende:
            print(f"Codex-Gate rot — nach {frist}s: {ablauf_grund(grund, frist)}", file=sys.stderr)
            return 1
        print(f"{grund} Erneut in {takt}s.")
        time.sleep(takt)


if __name__ == "__main__":
    raise SystemExit(main())
