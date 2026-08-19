#!/usr/bin/env bash
#
# SessionStart-Hook: meldet, wie viele Commits der ausgecheckte Stand hinter
# origin/<Standard-Branch> liegt. Schweigt, wenn nichts fehlt.
#
# WARUM:
# Ein veralteter Klon hat am 3.8.2026 zweimal eine rote CI erzeugt, deren
# Ursache nicht im Diff stand — die fehlenden Commits waren jeweils genau die,
# die das Gate einfuehrten, an dem der Branch scheiterte. Die Pruefung kostet
# eine Sekunde und ersetzt eine Fehlersuche in den falschen Dateien.
#
# ENTWURFSREGEL (wichtiger als das Ergebnis):
# Der Hook darf die Session NIEMALS anhalten. Kein Netz, kein Remote, detached
# HEAD, flatterndes DNS, fehlende Werkzeuge — jeder dieser Faelle geht still
# durch. Ein Hook, der bei Netzproblemen die Arbeit anhaelt, wird nach dem
# zweiten Mal abgeschaltet und schuetzt danach gar nichts.
#
# Deshalb steht hier bewusst KEIN `set -euo pipefail`: unter `-e` beendet der
# erste fehlschlagende git-Aufruf das Skript mit dessen Exit-Code, und ein
# Hook-Exit != 0 ist genau das, was hier nie passieren darf. Die Garantie
# uebernimmt stattdessen der EXIT-Trap; jeder Aufruf ist einzeln abgesichert.
#
# Ausfuehrliche Begruendung: .claude/hooks/README.md

trap 'exit 0' EXIT

# Sekunden pro Netzaufruf. Es gibt zwei davon (ls-remote, fetch), im
# pathologischen Fall also hoechstens das Doppelte; typisch < 1s insgesamt.
TIMEOUT="${CLAUDE_FRESHNESS_TIMEOUT:-5}"
REMOTE="${CLAUDE_FRESHNESS_REMOTE:-origin}"

# --- 1. Zeitlimit-Werkzeug --------------------------------------------------
# Ohne harte Obergrenze kann ein haengender DNS-Lookup den Sessionstart
# blockieren; git kennt dafuer keinen eigenen Schalter. `timeout` ist GNU
# coreutils (Linux, via Homebrew als `gtimeout`), perl liegt auf macOS ohnehin
# bei. Findet sich nichts davon, prueft der Hook lieber gar nichts.
if command -v timeout >/dev/null 2>&1; then
    bounded() { timeout -k 1 "$@"; }
elif command -v gtimeout >/dev/null 2>&1; then
    bounded() { gtimeout -k 1 "$@"; }
elif command -v perl >/dev/null 2>&1; then
    # alarm() ueberlebt exec(); das SIGALRM beendet dann das exec'te Kommando.
    bounded() { perl -e 'my $s = shift; alarm $s; exec @ARGV;' "$@"; }
else
    exit 0
fi

# --- 2. Nur bei echtem Sessionstart -----------------------------------------
# stdin traegt das Hook-JSON. `compact` ist kein Sessionstart, sondern eine
# laufende Session, die ihren Kontext zusammenfasst — dort waere die Meldung
# nur Rauschen. Gelesen wird mit Zeitlimit, damit ein offen gelassenes stdin
# den Start nicht aufhaelt; am Terminal (Aufruf von Hand) gar nicht.
if [ ! -t 0 ]; then
    payload=$(bounded 1 cat 2>/dev/null | tr -d ' \t\n\r')
    case "$payload" in
        *'"source":"compact"'*) exit 0 ;;
    esac
fi

# --- 3. Ueberhaupt ein Git-Repo? --------------------------------------------
cd "${CLAUDE_PROJECT_DIR:-$PWD}" 2>/dev/null || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
git remote get-url "$REMOTE" >/dev/null 2>&1 || exit 0

# Frisch initialisiertes Repo ohne Commit: nichts, wovon man zurueckliegen
# koennte. Bei detached HEAD loest `HEAD` dagegen normal auf — der Abstand ist
# dort genauso aussagekraeftig und wird ganz normal gemeldet.
git rev-parse --verify --quiet HEAD >/dev/null 2>&1 || exit 0

# --- 4. Git darf unter keinen Umstaenden interaktiv werden ------------------
# Ohne diese Schalter fragt git bei einem privaten Remote ohne Credentials nach
# Benutzername/Passwort — und wartet. Ein Zeitlimit allein deckt das nicht ab:
# es wuerde jeden Start um die volle Wartezeit verlaengern.
export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=true
export SSH_ASKPASS=true
export GCM_INTERACTIVE=never
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes -o ConnectTimeout=5}"

# --- 5. Standard-Branch ermitteln, nicht annehmen ---------------------------
# `main` ist eine Annahme, keine Tatsache: drei Server im Portfolio heissen
# ihren Standard-Branch `master`. Genau diese Annahme hat schon einmal einen
# Branch 15 Commits alt werden lassen, weil die Pruefung an
# "couldn't find remote ref main" scheiterte und als Netzproblem durchging.
symref=$(bounded "$TIMEOUT" git ls-remote --symref "$REMOTE" HEAD 2>/dev/null)
branch=$(printf '%s\n' "$symref" |
    sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p' | head -1)
[ -n "$branch" ] || exit 0

# --- 6. Abstand messen ------------------------------------------------------
bounded "$TIMEOUT" git fetch --quiet --no-tags "$REMOTE" "$branch" >/dev/null 2>&1 || exit 0
behind=$(git rev-list --count HEAD..FETCH_HEAD 2>/dev/null)
case "$behind" in
    '' | *[!0-9]*) exit 0 ;;
esac
[ "$behind" -gt 0 ] || exit 0

# --- 7. Nur jetzt wird geredet ----------------------------------------------
if [ "$behind" -eq 1 ]; then
    noun="Commit"
else
    noun="Commits"
fi
cat <<MSG
Klon veraltet: HEAD liegt $behind $noun hinter $REMOTE/$branch.

Genau die fehlenden Commits koennen das Gate enthalten, an dem ein Branch
spaeter scheitert — die Ursache einer roten CI steht dann nicht im Diff.
Vor der Arbeit einholen:

    git merge $REMOTE/$branch     # oder: git rebase $REMOTE/$branch
MSG

exit 0
