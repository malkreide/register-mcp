# SessionStart-Hook: Klon-Aktualitaet

`check-clone-freshness.sh` meldet beim Sessionstart, wie viele Commits der
ausgecheckte Stand hinter `origin/<Standard-Branch>` liegt. Liegt er nicht
zurueck, sagt er nichts.

## Warum

Ein veralteter Klon hat am 3.8.2026 zweimal eine rote CI erzeugt, deren Ursache
nicht im Diff stand — die fehlenden Commits waren jeweils genau die, die das
Gate einfuehrten, an dem der Branch scheiterte. Die Pruefung kostet eine
Sekunde und ersetzt eine Fehlersuche in den falschen Dateien.

`CLAUDE.md` schreibt dieselbe Pruefung als Handgriff «vor der Arbeit» vor. Ein
Handgriff, an den man sich erinnern muss, wird genau dann vergessen, wenn er
noetig gewesen waere; der Hook macht daraus einen Automatismus.

## Entwurfsregeln, in dieser Reihenfolge

1. **Der Hook blockiert nie.** Kein Netz, kein Remote, detached HEAD,
   flatterndes DNS, fehlendes `timeout`, kaputte Credentials — jeder Fall
   endet still mit Exit 0. Ein Hook, der bei Netzproblemen die Arbeit anhaelt,
   wird nach dem zweiten Mal abgeschaltet und schuetzt danach gar nichts.
   Garantiert wird das durch `trap 'exit 0' EXIT`; deshalb steht im Skript
   bewusst kein `set -euo pipefail` (unter `-e` beendet der erste
   fehlschlagende git-Aufruf das Skript mit dessen Exit-Code).
2. **Zeitlimit auf jeden Netzaufruf.** `CLAUDE_FRESHNESS_TIMEOUT` (Vorgabe: 5
   Sekunden) gilt je fuer `ls-remote` und `fetch`. Zusaetzlich laeuft git
   strikt nicht-interaktiv (`GIT_TERMINAL_PROMPT=0`, `BatchMode=yes`): ein
   privates Remote ohne Credentials fragt sonst nach einem Passwort und
   wartet — was ein Zeitlimit zwar beendet, aber erst nach voller Wartezeit.
3. **Ausgabe nur bei fehlenden Commits.** Bei 0 schweigt er.
4. **Der Standard-Branch wird ermittelt, nicht angenommen.** Drei Server im
   Portfolio heissen ihren Standard-Branch `master`. Ein fest verdrahtetes
   `main` scheitert dort mit «couldn't find remote ref main», geht als
   Netzproblem durch — und der Branch wurde 15 Commits alt.

## Was er anfasst

`git fetch --no-tags origin <Standard-Branch>` aktualisiert `FETCH_HEAD` und
`refs/remotes/origin/<Branch>`. Arbeitsverzeichnis, Index und lokale Branches
bleiben unberuehrt.

## Stellschrauben

| Variable | Vorgabe | Wirkung |
| --- | --- | --- |
| `CLAUDE_FRESHNESS_TIMEOUT` | `5` | Sekunden je Netzaufruf |
| `CLAUDE_FRESHNESS_REMOTE` | `origin` | zu pruefendes Remote |

## Von Hand pruefen

```bash
.claude/hooks/check-clone-freshness.sh; echo "exit=$?"
```

Erwartet: Exit 0 — immer. Ausgabe nur, wenn der Klon wirklich zurueckliegt.
Die automatisierte Gegenprobe steht in `tests/test_session_start_hook.py`.
