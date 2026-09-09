# CLAUDE.md

## Teil 1 — Portfolio-weite Konventionen

### Vor der Arbeit

Klon-Aktualität prüfen — Standard-Branch ermitteln, nicht `main` annehmen:

```bash
B=$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p')
git fetch origin "${B:?Standard-Branch nicht ermittelbar}" &&
  git rev-list --count HEAD..FETCH_HEAD
```

Drei Server im Portfolio heissen ihren Standard-Branch `master`
(`openlex-mcp`, `swiss-courts-mcp`, `swisstopo-mcp`); dort scheitert ein fest
verdrahtetes `origin/main` mit «couldn't find remote ref main». Wer das für ein
Netzproblem hält, arbeitet weiter auf genau dem veralteten Klon, vor dem dieser
Absatz warnt. Den `:?`-Schutz nicht weglassen: Bei leerem `B` fetcht git still
den Remote-HEAD und endet mit 0.

Ein veralteter Klon erzeugt eine rote CI, deren Ursache nicht im Diff steht.
Am 3.8.2026 zweimal passiert — beide Male fehlten genau die Commits, die
das Gate einführten, an dem der Branch scheiterte.

In diesem Repo nimmt einem der SessionStart-Hook
`.claude/hooks/check-clone-freshness.sh` den Handgriff ab: Er meldet den
Rückstand beim Sessionstart und schweigt, wenn keiner besteht. Er ersetzt die
Prüfung nicht, er erinnert nur an sie — er ist bewusst fail-open und geht bei
jedem Netz-, Remote- oder Werkzeugproblem still durch, statt die Session
anzuhalten. Ein stilles Durchgehen sieht also genauso aus wie ein aktueller
Klon; wer sicher sein will, fährt den Block oben von Hand.

Gates lokal fahren, mit der GEPINNTEN ruff-Version aus der CI. Eine andere
Version meldet Abweichungen, die niemand verursacht hat.

### Tests

Gegenprobe ist Pflicht. Ein Test, der grün bleibt, wenn man die
Implementierung entfernt, prüft nichts. Jede neue Zusicherung einzeln
neutralisieren und zeigen, dass genau die zugehörigen Tests fallen.
Zwei Fallen, die beide grün blieben:

- Eine Fake-Uhr, die nur beim Schlafen vorrückt, kann eine Zusicherung über
  echte Zeit nicht widerlegen.
- `monkeypatch.setattr(modul.asyncio, "sleep", ...)` greift ins Modul
  asyncio selbst und entschärft die Mechanik im ganzen Prozess. Patche
  einen Modul-Alias (`_sleep = asyncio.sleep`), nicht das fremde Modul.

Handgeschriebene Fixtures kodieren die Annahme des Autors und können sie
nicht widerlegen. Mindestens eine aufgezeichnete Antwort pro externem
Endpunkt, mit Aufnahmedatum.

### Wenn etwas rot ist

Roter Live-Test: erst die Quelle abfragen, dann einordnen. Nicht aus der
Fehlermeldung schliessen. Am 3.8.2026 hiess "nicht gefunden" nicht, dass der
Datensatz weg war, sondern dass die Quelle die Schreibweise ihrer Kopfzeile
gewechselt hatte — vier von sechs Datensätzen produktiv kaputt, alle
Unit-Tests grün.

**Ein 4xx ist kein Nein.** Am 29.8.2026 antwortete `past-publications` in
`swiss-procurement-mcp` auf jede Publikation mit Losen mit HTTP 400. Daraus war
geschlossen worden, die Quelle verweigere diese Auskunft; der Befund stand
datiert im Fixture-Nachweis, ein Test bestätigte ihn, alles blieb grün. Die
Spec desselben Endpunkts führt einen als *optional* deklarierten Parameter
`lotId` — für Publikationen mit Losen ist er Pflicht. Mit ihm antwortet
dieselbe Publikation mit 200. Ein Projekt trug sieben Vorgängerpublikationen,
die der Server als «Quelle nicht erreichbar» wegwarf.

Drei Handgriffe daraus:

- **Die Parameterliste der Spec durchgehen, bevor ein Statuscode eingeordnet
  wird.** «Optional» heisst dort oft «optional für die Mehrheit».
- **Einer deterministischen Absage keinen Wiederholungsrat geben.** «Nicht
  erreichbar, bitte später erneut» ist bei einem 400 falsch und liest sich für
  das Modell wie eine Störung. Den Status mitführen und den fehlenden
  Parameter benennen — den Status, nicht den Antwortkörper.
- **Beide Antworten aufzeichnen, mit und ohne den Parameter.** Eine
  Aufzeichnung nur des Fehlschlags kann nicht zeigen, dass er vermeidbar war;
  dass nur der 400er aufgezeichnet war, ist der Grund, warum der falsche
  Befund nicht auffiel.

**Und ein 403 ist gar keine Auskunft.** Am 29.8.2026 sollten für 42 Repos die
Dependabot-Labels nachgemessen werden. Alle 13 Abfragen des ersten Stapels
kamen zurück als:

```
Failed to find label: API rate limit already exceeded for user ID 8864492.
```

Der gefährliche Teil steht vorn: Das Werkzeug verpackt eine Sperre als
Fund-Fehlschlag. Wer die Zeile überfliegt oder nur auf ein leeres Ergebnis
prüft, zählt 39 Repos als «Label fehlt» und hat seine eigene Erschöpfung
gemessen. Das Limit hängt am Konto, nicht am Repo — derselbe Vormittag hatte
es mit 42 eröffneten und 42 gemergten PRs verbraucht.

Das ist der Absatz darüber, andersherum gelesen: dort war ein 400 eine echte,
wiederholbare Antwort und galt als Störung; hier ist eine Störung als Antwort
verpackt. Entscheidend ist nie der Statuscode, sondern ob die Quelle überhaupt
geantwortet hat.

- **Positivkontrolle im selben Repo.** Ein «nicht gefunden» wird erst dadurch
  zur Messung, dass eine gleichzeitige Abfrage etwas findet.
- **Die Messung entlang der Sperre teilen.** `raw.githubusercontent.com` ist
  ein CDN und nicht die REST-API. Um 11:19:27 UTC lieferte es für
  `register-mcp` HTTP 200, während die Label-Abfrage desselben Repos in
  derselben Minute die Sperre meldete. Alle 42 `dependabot.yml` kamen so
  durch, während die Label-Hälfte stand.
- **Am Token vorbei geht es nicht.** Beide Umwege enden am Agent-Proxy, und
  jeder mit einer eigenen irreführenden Begründung. `api.github.com` ohne
  Zugangsdaten:

  ```
  GitHub access is not enabled for this session. An org admin must connect
  the Claude GitHub App for this organization.
  ```

  Das ist keine Aussage über die Organisation, sondern das, was ohne Token
  kommt. Wer ihr folgt, sucht einen Admin für ein Problem, das keiner hat.
  Die HTML-Seite `github.com/<owner>/<repo>/labels` fällt ebenfalls, aber
  anders:

  ```
  This GitHub API path is not available: sessions are bound to their
  configured repositories. Use repository-scoped endpoints
  (repos/{owner}/{repo}/...).
  ```

  Der Proxy behandelt also auch `github.com` als API-Pfad; die zweite Meldung
  klingt nach einem Scope-Problem und ist doch nur dieselbe Sackgasse. Den
  Token aus der Umgebung in einen curl-Header zu setzen, blockiert der
  Klassifikator. Ob es überhaupt hülfe, ist offen: die Sperre nennt ein
  Nutzerkonto, und ob der Token zu diesem gehört, wurde nie geprüft.
- **Die Sperre gilt nicht dem Dienst, sondern dem Zugangspfad.** Unmittelbar
  nachdem eine Abfrage der Checks eines PR sauber durchlief, meldete die
  Label-Abfrage weiter die Sperre. Von einem blockierten Werkzeug also nicht
  auf «GitHub ist zu» schliessen — und umgekehrt eine gelungene Abfrage nicht
  als Entwarnung für die gesperrte nehmen. Das ist dieselbe Asymmetrie wie
  bei der verschwundenen Codex-Meldung weiter unten.

Wann die Sperre fällt, geben diese Beobachtungen nicht her. Die Meldung nennt
keinen Zeitpunkt, und die `X-RateLimit`-Kopfzeilen sind hinter dem Proxy nicht
zu sehen. Belegt sind drei gesperrte Zeitpunkte — 11:14, 11:16 und 11:19 UTC.
Wer daraus eine Dauer macht, hat sie erfunden.

**Dieselbe Falle bei einer Konfigurationsoption: die Vorgabe lesen, bevor man
einen Schlüssel für wirkungslos hält.** Am 29.8.2026 fielen die
`labels:`-Zeilen aus den `dependabot.yml` des Portfolios, begründet mit
«Dependabot legt Labels nicht an». Eine Messung danach zeigte, dass
`dependencies` in 36 von 42 Repos sehr wohl existiert, 35 davon mit GitHubs
Standardbeschreibung. Das las sich zuerst wie ein Beleg, dass die Aktion
falsch war.

Die Optionsreferenz kehrt es um:

```
Dependabot creates these default labels automatically, as necessary in
your repository.

If you define more than one package manager, an additional label for the
ecosystem or language is added to each pull request.

The labels specified are used instead of the default labels.
```

Ohne `labels:` vergibt Dependabot also `dependencies` — und, sobald mehr als
ein Paketmanager deklariert ist, zusätzlich ein Ökosystem-Label — und legt sie
selbst an; eine eigene Liste **ersetzt** diesen Satz, und «if any of these
labels is not defined in the repository, it is ignored». Die Zeile war nicht
wirkungslos — sie tauschte einen sich selbst pflegenden Vorgabesatz gegen eine
starre Liste.

**Die Bedingung nicht weglassen.** Bei nur einem Paketmanager steht das
Ökosystem-Label gar nicht zu; wer es dort trotzdem erwartet, schreibt genau
den Fehlbefund auf, gegen den dieser Abschnitt geschrieben ist — der Abschnitt
liefe an sich selbst vorbei. Im Portfolio deklariert jede `dependabot.yml`
zwei (`pip` und `github-actions`), die Bedingung ist hier also überall
erfüllt; anderswo nicht unbedingt. Aufgefallen ist die fehlende Bedingung
nicht beim Schreiben, sondern durch einen Codex-Review auf
`swiss-environment-mcp` PR #113 — vierzehn Sekunden vor dem Merge desselben
PR.

Was das kostet, ist an `openlex-mcp` gemessen: zwei Ökosysteme deklariert,
also stünden `dependencies` **und** ein Ökosystem-Label zu; vorhanden ist nur
das erste, `github-actions` und `github_actions` fehlen beide (Kontrolle `bug`
vorhanden). `register-mcp` ist die Gegenprobe: dort existieren alle vier
deklarierten Namen mit handgeschriebener Beschreibung, die Liste ist gewollt
und vollständig.

**Dreimal falsch eingeordnet, in drei Richtungen.** Erst die Zeile für bloss
wirkungslos gehalten. Dann die gefundenen Labels für einen Widerspruch. Dann,
auf denselben Fund gestützt, einen richtigen PR geschlossen mit dem Argument,
das Label existiere ja — obwohl es existiert, *weil* die Vorgabe es anlegt.
Der dritte Fehler ist der teuerste, weil er wie eine Messung aussah.

Was die Messung **nicht** hergibt: wer die 36 Labels angelegt hat. Die
Referenz sagt, Dependabot tue es; die Objekt-IDs liegen aber so dicht
beieinander, dass sie eher aus einem Stapellauf stammen. Beides passt zum
Befund, keines ist belegt — die Herkunft blieb ungemessen.

Beim Aufräumen gilt deshalb dieselbe Frage wie bei `lotId`: Was ist die
*Vorgabe*, wenn man das Ding weglässt — nicht bloss, ob der aktuelle Wert
etwas bewirkt.

**`results[0]` ist nur so verlässlich wie die Zusicherung danach.** Pinnt die
Abfrage einen bekannten Datensatz, ist der erste Treffer eine Drift-Wache und
in Ordnung. Hängt die Zusicherung dagegen davon ab, *welche* Variante die
Quelle heute zuoberst hat, prüft der Test den Tag: am 25.8.2026 rot, weil die
neueste Zürcher Publikation zufällig Lose hatte, am 26.8. grün, ohne dass sich
etwas geändert hätte. Den Fall gezielt wählen und beide Zweige fahren.
PR ohne jeden Check ist selten ein Repo ohne CI, meistens ein
Merge-Konflikt: GitHub berechnet dafür keinen Merge-Commit und startet nichts.
Ein Codex-Review auf einem PR wird beantwortet oder behoben, nie ignoriert.

### Wenn Codex gar nicht erst hinsieht

Die Zeile oben unterstellt, dass es einen Befund geben *kann*. Das ist nicht
immer so, und man sieht es dem PR nicht an.

Am 21.8.2026 war das Code-Review-Kontingent zwischen 08:41 und 09:48
aufgebraucht — davor echte Reviews, danach in 30 Repos nur noch:

```
You have reached your Codex usage limits for code reviews.
```

Wie lange die Sperre dauerte, geben die Beobachtungen nur als Spanne her. Vier
Zeitpunkte sind belegt: letzter gelungener Review am 21.8. um 08:41, erste
Limit-Meldung um 09:48, letzte beobachtete Limit-Meldung am 22.8. um 11:03,
erste *andere* Meldung am 23.8. um 08:22.

Zwischen erster und letzter Limit-Meldung liegen **25 h 15 min**. Das ist der
Abstand zweier Fehlschläge, nicht die Dauer einer Sperre. Wer ihn Untergrenze
nennt, hat die durchgehende Erschöpfung schon vorausgesetzt, die er belegen
soll: Öffnete sich das Fenster zwischendurch und schloss es sich durch neue
Auslöser wieder, waren es zwei kurze Sperren und nie eine von 25 Stunden.
Untergrenze einer *einzelnen* Sperre sind die 25 h 15 min nur unter genau dieser
Annahme — und die ist unbelegt.

Nach oben trägt die Rechnung dagegen. Die längste mit den Beobachtungen
verträgliche Sperre reicht vom letzten Erfolg um 08:41 bis zur abweichenden
Meldung um 08:22, also **47 h 41 min**; länger kann keine einzelne gewesen sein.
Wer stattdessen ab der ersten Limit-Meldung rechnet, unterschlägt die 67
Minuten, in denen das Kontingent schon weg gewesen sein kann, und nennt die
Spanne zwischen zwei Beobachtungen eine Obergrenze.

Beobachtungspunkte sind keine Messreihe — die 21 Stunden vor der abweichenden
Meldung liefen ganz ohne Codex-Auslöser, dort hat niemand gemessen.

In der Zwischenzeit sind 32 PRs mit formal erfülltem Häkchen gemergt worden,
ohne dass jemand hineingesehen hat, und am 22.8. noch einmal 43.

**Vier** Gründe, warum Codex schweigt, und nur einer davon ist harmlos:

- **Kein Befund** — dafür sind **zwei** Gestalten belegt, und die zweite hat
  mit der ersten kein Wort gemeinsam. Bis zum 23.8.2026 ein gewöhnlicher
  Issue-Kommentar:

  ```
  Codex Review: Didn't find any major issues. Swish!
  ```

  Der Schlusssatz wechselt bei jedem Lauf («Delightful!», «Keep it up!»,
  «More of your lovely PRs please.»); stabil ist nur der Satz davor.

  Am 8.9.2026 kam auf `register-mcp` PR #102 dieser Satz **nicht**. Stattdessen
  eine Tabelle unter der Überschrift `## Codex Review Summary`, die schon beim
  Start gepostet und danach **in derselben Kommentar-ID editiert** wird
  (erstellt 04:12:08 als `🔄 Running`, aktualisiert 04:13:20 auf
  `✅ Completed`, mit Commit `1e186c4` und `Review trigger: Draft marked
  ready`). Kein Review-Objekt, keine Inline-Threads, kein zweiter Kommentar.

  Wer nach «Swish!» greppt, findet das nicht und zählt einen sauberen Review
  als ungeprüft — genau der Fehlalarm, den dieser Abschnitt verhindern soll,
  nur in die andere Richtung.

  PR #104 lieferte am selben Tag dieselbe Form ein zweites Mal (erstellt
  04:31:45, aktualisiert 04:33:20, Commit `97f2aa7`). Zwei Treffer für eine
  Form belegen aber nicht das Verschwinden der anderen, und beide fallen auf
  denselben Tag: Ob die alte Form weg ist oder beide nebeneinander laufen,
  bleibt **ungemessen**.

  Die Tabelle kann dafür etwas, was keine der anderen Formen konnte: Sie ist
  schon da, **während** der Review läuft, und nennt den Commit. «Läuft noch»
  ist damit zum ersten Mal ablesbar — siehe den Drei-Sekunden-Merge weiter
  unten.

  Zur 👍-Reaktion: Der Infokasten behauptet sie seit je
  («reacts with 👍 once all reviews finish with no findings»); am 23.8. kam in
  sechs Repos die Meldung und in keinem die Reaktion. Auf #102 trug der PR
  danach `+1: 1`. **Wer sie gesetzt hat, ist nicht gemessen** — die Zählung
  nennt keinen Urheber, und der PR-Autor war in derselben Minute aktiv. Ein
  einzelner Fall macht den Kasten also noch nicht zur Quelle.
- **Der PR ist ein Draft** — darauf läuft Codex nicht an.
- **Das Kontingent ist weg** — dann schreibt er die Meldung oben.
- **Für das Repo fehlt eine Environment** — dann schreibt er:

  ```
  To use Codex here, create an environment for this repo.
  ```

Der vierte kam erst zum Vorschein, als der dritte wegfiel, und das ist kein
Zufall: Die Prüfungen liegen hintereinander. Dass es diese Reihenfolge ist und
nicht die umgekehrte, lässt sich an einem einzigen Repo ablesen — in
`swiss-public-data-mcp` bekam PR #54 am 22.8. um 10:56:55 die Kontingent-Meldung
und PR #56 am 23.8. um 08:22:20 die Environment-Meldung. Läge die
Environment-Prüfung vorn, hätte #54 sie schon am Vortag gesehen; die Environment
fehlte ja bereits. Zwei Meldungen aus demselben Repo schlagen hier jede
Vermutung über die Reihenfolge.

Praktisch heisst das: **Eine verschwundene Limit-Meldung ist keine Entwarnung.**
Sie kann bedeuten, dass das Kontingent wieder da ist — und dass jetzt etwas
anderes den Review verhindert. Belegt ist eine Prüfung erst durch ein
Review-Objekt, eine Befundlos-Meldung **oder** eine Summary-Tabelle im Zustand
`✅ Completed` — die Tabelle im Zustand `🔄 Running` belegt nichts ausser, dass
er angelaufen ist. Wer nur das Objekt gelten lässt, zählt jeden befundlosen
Review als ungeprüft — und baut sich denselben Fehlalarm ein, den dieser
Abschnitt verhindern soll, nur in die andere Richtung.

«Kein Kommentar» heisst also nicht «geprüft und sauber». Unterscheiden lässt es
sich an der Form: Ein Review **mit** Befund ist ein Review-Objekt
(«💡 Codex Review», mit Commit-Angabe); ein Review **ohne** Befund und die
beiden Ausfallmeldungen — Kontingent wie Environment — sind gewöhnliche
Issue-Kommentare und trennen sich nur im Text. Beim Draft gibt es überhaupt
nichts, weil Codex nicht anläuft; ein kommentarloser Draft ist deshalb kein
Beleg, sondern ein nicht durchgeführter Test.

Die `Codex Review Summary` ist ebenfalls ein gewöhnlicher Issue-Kommentar,
trennt sich aber nicht nur im Text von den übrigen: Sie **ändert sich unter
der Hand**. Derselbe Kommentar bedeutet um 04:12 «läuft» und um 04:13
«fertig». Ein einmal gelesener Stand ist deshalb kein Befund, sondern eine
Momentaufnahme — `updated_at` mitlesen, nicht nur `created_at`.

Das sind verschiedene Abfragen — `get_reviews` fürs Objekt, `get_comments` für
alles andere; wer nur eine nimmt, übersieht den Rest. Genau so ist die
Limit-Meldung zuerst durchgerutscht.

Der Kommentarzähler allein reicht ohnehin nicht: `comments: 1` kann die
Befundlos-, die Kontingent- **oder** die Environment-Meldung sein, seit dem
8.9.2026 zusätzlich die Summary-Tabelle — und die in zwei Zuständen, «läuft»
wie «fertig». Fünf Bedeutungen unter derselben Zahl, darunter «noch gar nichts
geprüft» und «geprüft und sauber». Den Text lesen, nicht die Zahl.

Und einen unbekannten Text wörtlich zitieren, statt ihn in eine der bekannten
Schubladen zu zwingen: Dieser Abschnitt musste schon einmal von drei auf vier
Gründe wachsen, die 👍-Reaktion stand hier zwei Fassungen lang als Tatsache,
und die Befundlos-Form, die als einziger Wortlaut dastand, hat inzwischen eine
zweite. Was hier steht, ist datiert beobachtet und nicht abgeleitet — auch das
Nächste wird eine Form haben, die hier noch nicht steht.

Und ein befundloser Lauf ist kein Freispruch. Am 23.8. lief derselbe Text durch
42 Reviews: 36 meldeten denselben P2-Befund, 6 die Befundlos-Meldung — gleiche
Eingabe, gegenteiliges Urteil, alles in denselben neun Minuten. Ein sauberer
Lauf sagt damit etwas über den Lauf, nicht über den Text. Wer sein Häkchen
daran hängt, hängt es an einen Münzwurf.

Portfolio-weit nachsehen:

```
search_pull_requests: user:malkreide commenter:chatgpt-codex-connector[bot] updated:>=<Datum>
```

Findet nur, wo er *kommentiert* hat. Repos ohne PR-Aktivität tauchen nicht auf
— das ist kein Beleg, dass dort geprüft wurde.

Zweiter Weg, den Prüfer zu verlieren, ganz ohne Kontingentproblem: zu schnell
mergen. Am 21./22.8. lagen zwischen «ready for review» und Merge mehrfach drei
bis fünf Sekunden. Codex wird beim Umschalten von Draft auf ready ausgelöst und
braucht danach Zeit; wer sofort mergt, hat das Häkchen gesetzt und den Review
nicht abgewartet.

Am 8.9.2026 lag der Ablauf auf `register-mcp` PR #102 zum ersten Mal
sekundengenau vor, und er korrigiert, was «den Prüfer verlieren» nahelegt:

```
04:12:00  ready for review
04:12:03  merged
04:12:06  Codex startet den Review
04:13:19  Codex ist fertig — kein Befund
```

Der Review fällt also **nicht** aus. Er lief, drei Sekunden nach dem Merge,
und brauchte danach 73 Sekunden. Verloren geht nicht die Prüfung, sondern der
Zeitpunkt, an dem man auf sie noch reagieren kann: Ein Befund wäre auf einem
bereits gemergten PR gelandet. Hier ging es gut aus, und das ist der
gefährliche Teil — ein Verfahren, das nur wegen des Ergebnisses nicht
auffällt, fällt beim nächsten Mal auch nicht auf.

PR #104 lief 19 Minuten später gleich ab — ready 04:31:35, gemergt 04:31:38,
also wieder nach drei Sekunden. Aus zwei Läufen wird eine Spanne, und die
beantwortet die praktische Frage, die eine Einzelmessung offen lässt:

| gemessen ab «ready» | #102 | #104 | #105 | #106 |
| --- | --- | --- | --- | --- |
| Merge | +3 s | +3 s | +5 s | +5 s |
| Codex-Kommentar erscheint (`🔄 Running`) | +8 s | +10 s | +11 s | +9 s |
| `✅ Completed` | +79 s | +105 s | +94 s | +101 s |

Zu warten sind also **rund zwei Minuten, nicht ein paar Sekunden**. Wer nach
dem Auftauchen des Kommentars mergt, ist genauso zu früh wie vorher: Zwischen
«läuft» und «fertig» liegt der ganze Review.

Vier Läufe, alle zwischen 79 und 105 Sekunden — auch #106 mit neuem Skript,
21 Tests und einem Workflow. Die Dauer hängt hier also nicht sichtbar am
Umfang des Diffs.

Die Startzeit des Reviews steht nur *während* des Laufs in der Tabelle
(«Running since»); danach überschreibt sie der Abschlusszeitpunkt. Für #102
ist sie deshalb belegt (04:12:06), für #104 nicht — dort war die Tabelle beim
Lesen schon `✅ Completed`. Wer spät hinsieht, verliert die Startzeit, nicht
bloss den Zustand.

**Und der gelesene Zustand kann minutenlang veraltet sein.** Am 9.9.2026 gab
`get_comments` auf #106 um 03:33 die Tabelle als `🔄 Running` mit
`updated_at` 03:28:26 zurück — während derselbe Endpunkt, vom Actions-Runner
aus abgefragt, schon um 03:29:58 `✅ Completed` sah. Der Job-Log ist die
Gegenprobe:

```
Summary-Tabelle steht auf Running. Erneut in 15s.   (5×)
Codex-Gate OK — Summary-Tabelle: Completed fuer 55a203d.
```

Woran die Verzögerung liegt — an einem Cache im MCP-Werkzeug oder auf
GitHubs Seite — ist **ungemessen**. Belegt ist nur, dass zwei Lesewege
derselben Sache um Minuten auseinanderlagen.

Praktisch: Ein einzelner Blick auf den Kommentarzustand belegt kein «läuft
noch». Wer daraus schliesst, Codex sei langsam oder hänge, misst seinen
Lesepfad. Genau das ist hier passiert — auf die veraltete Lesung hin wurde
eine Frist als zu knapp «behoben», die es nicht war, und beinahe eine falsche
Dauer in diesen Abschnitt geschrieben. Die Laufzeit steht im Job-Log, nicht im
Kommentar.

Ein Merge beendet den Review übrigens nicht. Auf #106 lief der Gate-Job über
den Merge hinaus weiter und wurde nicht abgebrochen; das Urteil kam 96
Sekunden nach dem Merge. «Gemergt» heisst also nicht «fertig geprüft».

Ein Merge drei Sekunden nach «ready» ist damit kein knappes Timing, sondern
eine Reihenfolge, die gar nicht aufgehen kann: Der Auslöser liegt nach dem
Merge. Disziplin im Sekundentakt hilft dagegen nicht — dreimal in Folge
gemergt hat, wer die Regel gerade selbst gelesen hatte.

**Ein Ruleset auf «den Codex-Check» geht aber nicht: Es gibt keinen.** Diese
Datei hat das eine Fassung lang als Lösung empfohlen, ohne es zu messen. Auf
PR #105 nachgezählt: fünf Check-Runs, alle aus `ci.yml`, und
`total_count: 0` bei den Commit-Status. Codex hinterlässt in diesem Repo nur
einen Issue-Kommentar. Ein Ruleset kann aber nur verlangen, was als Check
gemeldet wird.

Deshalb liegt der fehlende Check jetzt im Repo: `.github/workflows/
codex-gate.yml` ruft `scripts/check_codex_review.py`, das wartet, bis ein
Urteil vorliegt, und sonst rot wird. Was als Urteil gilt, ist wörtlich die
Definition von oben — Review-Objekt, Befundlos-Meldung oder Summary-Tabelle
auf `✅ Completed`; `🔄 Running` genügt nicht. Über den *Inhalt* eines Befunds
urteilt der Gate nicht; ihn zu beantworten bleibt Sache des Autors.

Zwei Ausnahmen, beide gemessen und beide nötig:

- **Drafts** — Codex läuft darauf nicht an, und mergen lässt sich ein Draft
  ohnehin nicht.
- **Bot-Autoren** — Codex prüft hier keine Dependabot-PRs: #101 und #103
  tragen null Codex-Kommentare (#101s einziger Kommentar war Dependabots
  eigene Schlussnotiz). Ohne die Ausnahme hinge jeder Dependency-PR dauerhaft
  fest, der Gate würde abgeschaltet, und ein abgeschalteter Gate prüft nichts.

Der Gate ist ein eigener Workflow, weil `ci.yml` auf der Vorgabe von
`pull_request` läuft und `ready_for_review` dort **nicht** enthalten ist —
genau der Moment, um den es geht. Ihn an `ci.yml` zu hängen hiesse, die ganze
Matrix bei jedem Umschalten von Draft auf ready ein zweites Mal zu fahren.

Damit er wirkt, muss der Check «Codex hat den PR angesehen» im UI als
*required* gesetzt werden. Bis das geschehen ist, ist er sichtbar, aber
folgenlos — ein roter Check, den niemand abwarten muss, ändert nichts.

Und die Einschränkung, die man kennen muss: Der Gate hängt an Textformen, die
Codex jederzeit ändern kann — am 8.9.2026 ist genau das passiert. Bei einem
*unbekannten* Codex-Text fällt er deshalb nicht still durch, sondern bricht ab
und zitiert ihn wörtlich. Wer ihn rot sieht, liest die Meldung und weiss, ob
Codex geschwiegen hat oder bloss das Skript veraltet ist.

Das Kontingent hängt am Konto, nicht am Repo, und Code-Reviews haben einen
eigenen Topf — nur GitHub-getriggerte Reviews zählen hinein. ChatGPT-Pläne
fahren ein rollendes Fünf-Stunden-Fenster plus Wochenlimits; welches greift,
steht im Codex-Dashboard. Welches hier griff, ist **offen**. Die Lücke oben
schliesst das Fünf-Stunden-Fenster nicht aus: Es kann sich zwischendurch
geöffnet und durch neue Auslöser wieder erschöpft haben. Das auszuschliessen
bräuchte den Nachweis, dass in der ganzen Spanne kein einziger Review durchlief
— den gibt es nicht, weil nur Fehlschläge beobachtet wurden. Eine lange Reihe
von Fehlschlägen belegt eine lange Reihe von Fehlschlägen, nicht ihre Ursache.

Zeigt das Dashboard freies Kontingent, während Reviews weiter scheitern, ist
das ein bekannter Fehler bei mehreren verbundenen Konten — dann den
GitHub-Connector in den Codex-Einstellungen trennen und neu verbinden.

Die Environment legt man unter `chatgpt.com/codex/cloud/settings/environments`
an, und zwar **je Repo**. Die Meldung sagt es selbst («for this repo»), und am
23.8. war es genau so: In `swiss-public-data-mcp` fehlte sie, dort kam kein
Review; in den übrigen Repos lief Codex am selben Morgen durch. Eine
Environment fürs Konto genügt also nicht — wer eine anlegt und den Rest für
erledigt hält, mergt weiter Ungeprüftes.

### Wenn zwei Agenten dasselbe tun

Vor dem Anlegen eines Branches mit vorgegebenem Namen prüfen, ob es ihn schon
gibt:

```bash
git ls-remote --heads origin claude/<name> | wc -l
```

Steht dort `1`, arbeitet jemand anderes daran — mit Schreibrecht auf denselben
Ref.

Ein PR mit leerem Diff wird geschlossen, nicht gemergt. Der Test ist
`get_files` auf dem PR: kommt `[]` zurück, ändert er nichts. Ein grüner Check
sagt dazu nichts — die CI prüft den Head, nicht die Differenz zur Basis.

Am 21.8.2026 liefen zwei Sessions dieselbe Aufgabe über 45 Repos, auf den
Branches `claude/codex-review-audit-templates-9sn6mx` und
`claude/codex-review-audit-7ioh56`. Wo die eine zuerst nach `main` kam, wurde
`main` in den Branch der anderen gemergt und der add/add-Konflikt zugunsten
von `main` aufgelöst. Übrig blieben 14 PRs, die durch sämtliche Gates grün
liefen und nichts enthielten; sie wurden gemergt und hinterliessen leere
Merge-Commits. Mit den zwei Folge-PRs, die aus demselben Grund gegenstandslos
waren, waren 16 der 59 PRs jenes Tages reine Reibung.

Dieselbe Klasse wie der handgeschriebene Stub, der denselben Feldnamen annahm
wie der Code: Nichts ist rot, weil nichts geprüft wird, worauf es ankommt.

## Teil 2 — Repo-spezifisch (register-mcp)

**ruff: eine Quelle.** Derselbe Pin steht in `pyproject.toml` und `.pre-
commit-config.yaml` — und **nicht** mehr als eigener Install-Schritt in der
CI. Welche Version gerade gilt, sagt `check_version_sync.py`; hier steht sie
bewusst nicht. Sonst wäre dieser Absatz die dritte Stelle, die mitwandern
müsste, und die einzige ohne Gate.

Der CI-Schritt lief nach dem Install der Abhängigkeiten und überschrieb sie.
Eine Abweichung im Pin konnte deshalb in der CI gar nicht auffallen, sondern
nur lokal — wo niemand sie erwartet. Ein manuelles Nachinstallieren von ruff
vor den Gates ist damit nicht mehr nötig und wäre schädlich: Es würde eine
spätere Anhebung hier stillschweigend überstimmen.

`scripts/check_version_sync.py` bricht ab, wenn die verbleibenden Stellen
auseinanderlaufen **oder** wenn `ci.yml` wieder ein eigenes ruff installiert;
`tests/test_precommit_config.py` wacht darüber, dass der Hook denselben Umfang
sieht wie das Gate.

**Dependabot hebt nur eine der beiden Stellen — jedes Mal.** Das
`uv`-Ökosystem schreibt `pyproject.toml` und `uv.lock`; der `rev:` in
`.pre-commit-config.yaml` gehört für Dependabot zu keinem der drei
konfigurierten Ökosysteme und bleibt stehen. Jede ruff-Anhebung kommt deshalb
als roter PR an, mit einem einzigen roten Test unter lauter grünen:

```
AssertionError: 2 != 1 : ruff-Pins weichen ab:
[('.pre-commit-config.yaml → rev', '0.16.5'),
 ('pyproject.toml → dev-Extra', '0.16.6')]
```

Das ist kein Fehler des Gates, sondern seine Aufgabe — ohne es liefe der Hook
lokal mit einer anderen ruff-Version als das Gate in der CI, und genau das war
der Zustand, gegen den der Pin gebaut wurde. Der Handgriff ist, die zweite
Stelle im selben Commit nachzuziehen: den `rev` **und** die Version im
Kopfkommentar derselben Datei, denn den Kommentar liest kein Gate.

Zweimal ist das schon passiert (0.16.4 am 15.8.2026, 0.16.6 am 7.9.2026, beide
im CHANGELOG). Wer den roten Job für einen Regressionsfund hält, sucht in
ruff 0.16.6 nach einer Ursache, die im PR-Umfang steht.

Ein `package-ecosystem: pre-commit` in `.github/dependabot.yml` löst das
**nicht**: Gruppen greifen nur innerhalb eines Ökosystems, die Anhebung käme
also als eigener PR — und dann wären zwei PRs rot statt einem, bis beide
gemerged sind. Solange der Pin an zwei Stellen steht, führt sie ein Mensch
oder eine Session zusammen.

**Der Gate-Umfang ist aufgezählt, nicht `.` — und das ist Absicht.**
`ruff format` formatiert auch Python-Blöcke *innerhalb* von Markdown. `ruff
format .` würde vier Findings unter `audits/` umschreiben; das sind datierte
Protokolle, kein Code. `audits/` bleibt deshalb draussen. Neue Verzeichnisse mit
Code gehören dagegen in beide Listen (`ci.yml` und `.pre-commit-config.yaml`).

Vor dem Lauf `ruff --version` prüfen: ein älteres ruff früher im `PATH`
schlägt den Pin, ohne dass der Install etwas meldet.

**Gate-Befehle, wörtlich aus `ci.yml`** (Job `test`, Python 3.11/3.12/3.13):

```bash
pip install -e ".[dev]"
PYTHONPATH=src pytest tests/ -m "not live"
python scripts/check_ruff_pin.py
ruff check src/ tests/ scripts/ docs/
ruff format --check src/ tests/ scripts/ docs/
python scripts/check_version_sync.py
uv lock --locked          # Job `lockfile`, uv 0.8.x
```

Job `docker` baut zusätzlich das Image und prüft: Start ohne `MCP_API_KEY`
scheitert, Container läuft als User `mcp`.

`.github/workflows/codex-gate.yml` läuft **daneben**, nicht in `ci.yml`, und
hat eigene Auslöser (`ready_for_review` gehört dazu). Sein Job heisst «Codex
hat den PR angesehen»; die offline entscheidbare Hälfte liegt in
`tests/test_check_codex_review.py` und läuft im Gate mit.

**Live-Tests: geplanter Workflow vorhanden**, kein DRIFT-005.
`.github/workflows/live-tests.yml` läuft per `cron: "31 5 * * 1"` (wöchentlich)
plus `workflow_dispatch`, ordnet das JUnit-XML über
`scripts/classify_live_run.py` ein und öffnet/schliesst danach ein Issue.
`-m "not live"` in `ci.yml` ist hier also ein Ausschluss *mit* Auffangnetz.

**Zur Matrix:** die Gate-Liste oben gehört dem Job `test` (3.11/3.12/3.13);
`lockfile` und `docker` laufen daneben je einmal, ohne Matrix. Ein
`fail-fast: false` steht nicht da — eine rote 3.11 bricht 3.12 und 3.13 ab,
bevor sie etwas sagen.

Was `check_version_sync.py` über den ruff-Pin meldet, steht im Klartext in
seiner Ausgabe: `ruff-Pin einig auf X.Y.Z (2 Stellen)`. Wer die zwei Stellen
von Hand vergleicht, tut Arbeit, die dieser Gate schon leistet.

Bis zum 8.9.2026 stand hier ein anderer Wortlaut («an beiden Stellen gleich»)
samt fester Version — beides so nie ausgegeben. Ein Zitat, das kein Gate
nachprüft, altert still; wer danach greppt, findet nichts und schliesst auf
die falsche Stelle.

**Was die Live-Suite fand, waren keine Ausfälle, sondern Antworten.** Drei
Formen von Zefix, jede hat einen ausgelieferten Fehler gekostet:

- Ohne Treffer antwortet `firm/search.json` mit **HTTP 404** plus
  NORESULT-Rumpf. Deshalb jeder Aufruf über `_zefix_post_search` — und eine
  Fixture, die den Rumpf in eine 200 legt, lässt den toten Zweig grün aussehen.
- Mit Treffern ist es noch keine Antwort: `searchType: CONTAINS` sucht über den
  Namen, `CHE-999.999.999` liefert «CHEMAM - 999». Kein Rückfall auf `firms[0]`.
- Ohne `activeOnly: False` sieht «gelöscht» aus wie «gibt es nicht».

**Dependabot-Labels legt niemand automatisch an.** Was in
`.github/dependabot.yml` unter `labels:` steht, wendet Dependabot nur an, wenn
es das Label im Repo schon gibt. Fehlt es, kommt kein roter Check und kein Log,
sondern ein Kommentar an jedem Pull Request:

```
The following labels could not be found: `dependencies`, `python`.
```

Die Meldung nennt immer nur die Labels des betroffenen Ökosystems. Wer sie für
die vollständige Liste hält, legt zwei an und übersieht die übrigen bis zum
nächsten `github-actions`- oder `docker`-PR — hier fehlten **alle vier**.
Deshalb die Konfiguration lesen, nicht die Meldung:

```bash
python scripts/check_dependabot_labels.py                    # nur auflisten
python scripts/check_dependabot_labels.py --repo malkreide/register-mcp
```

Der zweite Modus fragt die GitHub-API und gehört bewusst **nicht** in `ci.yml`:
Ein Gate, das bei einem erschöpften Rate-Limit rot wird, macht fremde PRs rot
und wird abgeschaltet. Er ist auch **kein** `@pytest.mark.live` — die
Live-Suite ist bis in den Issue-Titel auf `zefix.admin.ch` gemünzt und würde
ein Issue über Zefix aufmachen, in dem es nicht um Zefix geht. Im Gate läuft
nur der offline entscheidbare Teil (`tests/test_dependabot_labels.py`).

Exit 2 heisst «konnte nicht vergleichen», Exit 1 «Labels fehlen». Wer beides
gleich behandelt, meldet bei jedem API-Ausfall einen Konfigurationsfehler, den
es nicht gibt.

**Portfolio-Regel, entschieden am 28.8.2026: neue Server tragen kein
`labels:`.** Am selben Tag standen im Portfolio zwei gegensätzliche Antworten
auf dieselbe Frage nebeneinander — 19 Repos hatten die Zeile bereits entfernt
(`bakom-mcp` begründet es in seiner eigenen Konfiguration), 24 führten sie
weiter. Zwei Sessions hatten unabhängig voneinander dasselbe Problem gefunden
und verschieden gelöst; das ist der Fall aus «Wenn zwei Agenten dasselbe tun»,
nur über Tage statt über Stunden.

Entschieden wurde gegen die Labels, und zwar nicht aus Geschmack: Die Aussage
steht ohnehin dreifach im PR — Autor `dependabot[bot]`, Commit-Prefix
(`deps`/`ci`/`docker`) und Branchname `dependabot/<ökosystem>/…` nennen
dasselbe. Ein Label ist damit eine zweite Quelle für eine Information, die
schon da ist, und dieses Repo kennt die Kosten davon (ruff-Pin an zwei Stellen,
`pin_audit.py` an drei, der Hook an drei — jedes braucht einen Gate oder einen
Absatz wie diesen). Hier wäre selbst das nicht möglich: Ein Label ist
GitHub-Zustand und kein Dateiinhalt, also kann kein Gate es prüfen.

**Dieses Repo ist die Ausnahme und behält seine Zeile.** Die vier Labels
existieren hier seit dem 28.8.2026; ab da kostet sie nichts mehr. Wer die Regel
liest und `register-mcp` als Widerspruch sieht, hat beides richtig verstanden.

Zwei Sonderformen fielen beim Sweep nebenbei auf, die in *keiner* der beiden
Antworten richtig sind: `meteoswiss-mcp` fordert `ecosystem:pip`,
`ecosystem:docker`, `ecosystem:github-actions` — ein eigenes Namensschema —,
und `srgssr-mcp` fordert `github-actions` statt `ci`. Beide lösen sich auf,
wenn die Zeile fällt.

**`pin_audit.py` steht an drei Stellen.** `swiss-electricity-mcp`, `bakom-mcp`
und `register-mcp` halten byteweise dieselbe `scripts/pin_audit.py` samt
`tests/test_pin_audit.py`. Wer eine ändert, ändert alle drei im selben Commit —
sonst misst der eine Server anders als der andere, und das ist genau die Drift,
gegen die das Werkzeug gebaut ist. Kein Gate erzwingt das, es gibt nur diesen
Absatz. Aus dem Verzeichnis, in dem die Server nebeneinander liegen:

```bash
sha256sum */scripts/pin_audit.py */tests/test_pin_audit.py |
  awk '{print $1}' | sort | uniq -c
```

Erwartet: **zwei** Zeilen mit je **3**. Die Anzahl mitlesen, nicht nur die Zahl
der Zeilen — findet der Glob nur ein Repo, stehen dort auch zwei Zeilen, und
«einig» hiesse dann bloss, dass nichts verglichen wurde.

**Der SessionStart-Hook steht an drei Stellen.** `swiss-electricity-mcp`,
`bakom-mcp` und `register-mcp` halten byteweise dieselben drei Dateien:
`.claude/hooks/check-clone-freshness.sh`, `.claude/hooks/README.md` und
`tests/test_session_start_hook.py`. Wer eine ändert, ändert alle drei im selben
Commit — sonst driften die Fassungen auseinander, und genau das war der
Ausgangszustand: drei eigenständige Implementierungen mit drei Dateinamen, von
denen eine ohne `timeout` im PATH ungebremst ins Netz ging und die Session
anhalten konnte. `.claude/settings.json` ist bewusst **nicht** Teil der Regel
(dort steht Repo-Eigenes); geprüft wird es stattdessen vom Test, der die
Registrierung des Hooks nachweist.

Kein Gate erzwingt die Gleichheit, es gibt nur diesen Absatz. Aus dem
Verzeichnis, in dem die Server nebeneinander liegen:

```bash
sha256sum */.claude/hooks/check-clone-freshness.sh */.claude/hooks/README.md \
          */tests/test_session_start_hook.py |
  awk '{print $1}' | sort | uniq -c
```

Erwartet: **drei** Zeilen mit je **3**. Die Anzahl mitlesen, nicht nur die Zahl
der Zeilen — findet der Glob nur ein Repo, stehen dort auch drei Zeilen, und
«einig» hiesse dann bloss, dass nichts verglichen wurde.
