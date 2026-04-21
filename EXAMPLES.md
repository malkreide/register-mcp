# Use Cases & Beispiele — register-mcp

Hier finden Sie praxisnahe Anwendungsfälle für den `register-mcp` Server, unterteilt nach Zielgruppen. Alle Abfragen können direkt in natürlicher Sprache an den LLM-Client (z.B. Claude) gestellt werden.

**🔑 Authentifizierung:**
Keine Authentifizierung erforderlich. Alle Daten stammen aus offenen, öffentlichen APIs (`ZefixREST`).

---

## 🏫 Bildung & Schule
Lehrpersonen, Schulbehörden, Fachreferent:innen

**Lieferantenprüfung für Lehrmittel**
«Wir möchten für unsere Schule Lizenzen beim 'Lehrmittelverlag Zürich AG' beschaffen. Ist das Unternehmen im Handelsregister aktiv und wo ist der offizielle Sitz?»
→ `zefix_verify_company(name="Lehrmittelverlag Zürich AG", canton="ZH")`
*Warum nützlich:* Schulleitungen oder Schulbehörden können vor Vertragsabschlüssen schnell und sicher prüfen, ob ein potenzieller Vertragspartner (z.B. ein Lehrmittelverlag oder IT-Dienstleister) rechtmässig existiert.

**Hintergrundcheck bei Schulbus-Anbietern**
«Suche das Transportunternehmen mit der UID CHE-105.823.149, das den neuen Schulbus-Vertrag erhalten soll. Welche Rechtsform hat es und wer ist zeichnungsberechtigt (gemäss Auszug)?»
→ `zefix_get_company_by_uid(uid="CHE-105.823.149")`
*Warum nützlich:* Ermöglicht es Beschaffungsstellen von Schulgemeinden, die rechtlichen Rahmenbedingungen und die Existenz eines Dienstleisters eindeutig über die MwSt/UID-Nummer zu verifizieren.

---

## 👨👩👧 Eltern & Schulgemeinde
Elternräte, interessierte Erziehungsberechtigte

**Prüfung von privaten Kitas oder Horten**
«Kannst du prüfen, ob der Verein 'Kinderkrippe Sonnenschein' im Kanton Bern im Handelsregister eingetragen und aktiv ist?»
→ `zefix_verify_company(name="Kinderkrippe Sonnenschein", canton="BE")`
*Warum nützlich:* Eltern können sich bei der Wahl einer familienexternen Betreuung (Kita, Hort) schnell vergewissern, ob es sich um eine offiziell registrierte, existierende Trägerschaft handelt.

**Informationen zu Nachhilfe-Instituten**
«Finde alle Unternehmen, die 'Nachhilfe' im Namen tragen und im Kanton St. Gallen registriert sind. Handelt es sich dabei eher um Einzelunternehmen oder GmbHs?»
→ `zefix_search_companies(name="Nachhilfe", canton="SG", active_only=True)`
*Warum nützlich:* Hilft Elternräten oder Elternvertretern, einen Überblick über kommerzielle Bildungsangebote in ihrer Region zu erhalten und deren rechtliche Organisation zu verstehen.

---

## 🗳️ Bevölkerung & öffentliches Interesse
Allgemeine Öffentlichkeit, politisch und gesellschaftlich Interessierte

**Transparenz bei lokalen Dienstleistern**
«Ich habe von der Baufirma 'Müller Hochbau' gehört. Ist die Firma noch aktiv im Handelsregister und gab es kürzlich Publikationen im SHAB?»
→ `zefix_verify_company(name="Müller Hochbau")`
→ `zefix_search_companies(name="Müller Hochbau")` (falls genauere Publikationsdaten nötig)
*Warum nützlich:* Bürgerinnen und Bürger können schnell und unkompliziert die Existenz und Aktualität von lokalen Gewerbebetrieben überprüfen.

**Stiftungen und gemeinnützige Organisationen finden**
«Zeige mir alle aktiven Stiftungen (Rechtsform-ID 7) im Kanton Genf an, die 'Umwelt' im Namen tragen. Was ist ihr genauer Zweck?»
→ `zefix_search_companies(name="Umwelt", canton="GE", legal_form_ids=[7], active_only=True)`
→ `zefix_get_company(ehraid=123456)` (für ausgewählte Resultate)
*Warum nützlich:* Stärkt die Zivilgesellschaft, indem interessierte Personen gemeinnützige Akteure in ihrem Kanton gezielt finden und deren Stiftungszweck einsehen können.

---

## 🤖 KI-Interessierte & Entwickler:innen
MCP-Enthusiast:innen, Forscher:innen, Prompt Engineers, öffentliche Verwaltung

**Automatisierte Due Diligence (Multi-Server)**
«Schlage die genauen Bestimmungen zur 'Aktiengesellschaft' in der Handelsregisterverordnung (HRegV) nach und vergleiche das mit dem Eintrag der Firma XYZ.»
→ `fedlex-mcp: fedlex_search_ordinances(query="Aktiengesellschaft")`
→ `register-mcp: zefix_verify_company(name="XYZ AG")`
*Warum nützlich:* Zeigt, wie Entwickler konkrete Handelsregisterdaten mit der zugrundeliegenden Gesetzgebung (HRegV) aus dem Fedlex-Server kombinieren können, um automatisierte Compliance-Checks aufzubauen. (Referenz: [fedlex-mcp](https://github.com/malkreide/fedlex-mcp))

**Stammdaten-Abgleich für CRM-Systeme**
«Liste mir alle Schweizer Rechtsformen auf und lade anschliessend die Gemeinden des Kantons Zürich. Ich brauche das, um die Dropdown-Felder in unserer neuen App zu befüllen.»
→ `zefix_list_legal_forms(language="de")`
→ `zefix_list_municipalities(canton="ZH")`
*Warum nützlich:* Hilft Entwicklern bei der initialen Befüllung von Referenzdaten für Formulare, CRM- oder ERP-Systeme direkt aus den offiziellen Bundesregistern.

---

## 🔧 Technische Referenz: Tool-Auswahl nach Anwendungsfall

| Ich möchte… | Tool(s) | Auth nötig? |
|-------------|---------|-------------|
| schnell prüfen, ob eine Firma existiert und aktiv ist | `zefix_verify_company` | Nein |
| eine Firma anhand ihrer UID (CHE-...) genau identifizieren | `zefix_get_company_by_uid` | Nein |
| Firmen nach Namen, Kanton oder Rechtsform suchen | `zefix_search_companies` | Nein |
| alle Details (Zweck, SHAB-Meldungen) einer Firma abrufen | `zefix_get_company` | Nein |
| die offiziellen Schweizer Rechtsformen auflisten | `zefix_list_legal_forms` | Nein |
| die Gemeinden eines Kantons (mit BFS-Nummer) auflisten | `zefix_list_municipalities` | Nein |
