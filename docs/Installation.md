# FokusWache installieren

## Voraussetzungen

- Windows 10 oder Windows 11, 64 Bit
- Administratorrechte für Installation, Updates und Entfernung des Dienstes
- Internet für den Download des Installers; die Anwendung selbst arbeitet lokal

## Windows-Setup

Lade **FokusWache-Setup-1.0.0-x64.exe** aus den [Releases](https://github.com/Dolcruz/Fokuswache/releases/latest) herunter und öffne sie. Python, Qt und die weiteren Laufzeitbibliotheken sind bereits enthalten. Das separate ThirdPartySources-Archiv wird für die normale Installation nicht benötigt.

Das Setup kopiert die Programme und Erweiterungen nach `%PROGRAMFILES%\FokusWache`, schützt Programm- und Regelordner mit Windows-Berechtigungen, registriert den automatisch startenden Dienst und legt einen Startmenüeintrag an. Ein Desktop-Symbol ist optional. Windows fragt nach einer Administratorbestätigung. Die Einrichtung ist auf den regulären 64-Bit-Programmordner beschränkt.

Öffne anschließend FokusWache und lege zunächst eine kurze eigene Testregel an. Mitgelieferte Vorlagen aktivieren keine Sperre von selbst.

## Chromium-Browser verbinden

Die Erweiterung muss in jedem verwendeten Browserprofil installiert werden.

1. Öffne `chrome://extensions`, `edge://extensions` beziehungsweise `brave://extensions`.
2. Aktiviere den Entwicklermodus.
3. Wähle **Entpackte Erweiterung laden**.
4. Wähle `%PROGRAMFILES%\FokusWache\extensions\chromium` über den tatsächlichen Windows-Pfad aus.
5. Prüfe in FokusWache unter **Browser & Schutz**, ob die Verbindung bestätigt ist.

Die Installation registriert den Native-Messaging-Host für Chrome, Edge und Brave. Weitere Chromium-Browser benötigen gegebenenfalls eine eigene Registrierung nach deren Vorgaben. Die Erweiterung fordert Tab-, Webseiten-, Native-Messaging- und Netzregelberechtigungen an, weil sie besuchte Adressen lokal prüfen und gesperrte Seiten blockieren muss. Sie enthält keinen Upload an einen externen Dienst.

Die Chromium-Erweiterung ist für private Fenster deaktiviert. Zusätzliche Profile oder private Fenster ohne bestätigte Verbindung können bei aktiven Webregeln eine Netzpause für den betreffenden Browser auslösen.

## Firefox

Öffne `about:debugging`, wähle **Dieser Firefox** und anschließend **Temporäres Add-on laden**. Lade `%PROGRAMFILES%\FokusWache\extensions\firefox\manifest.json` über den tatsächlichen Windows-Pfad.

Diese Installation muss nach jedem Firefox-Neustart wiederholt werden. Eine dauerhafte Installation benötigt eine signierte Erweiterung; eine solche Ausgabe ist in diesem Repository noch nicht enthalten. Ein echter Browser-End-to-End-Test der mitgelieferten Firefox-Anbindung steht noch aus.

## Updates

Lade das neue Setup herunter, schließe das FokusWache-Fenster und führe die EXE aus. Aktive Verriegelungen müssen vorher ablaufen. Das Setup prüft dies vor dem Ersetzen von Programmdateien. Es beendet und startet den eigenen Dienst und seine Hintergrundkomponenten kontrolliert neu. Persönliche Regeln, Zeitkonten und Tagebucheinträge liegen außerhalb des Programmordners.

## Entfernen und sichern

Öffne **Windows-Einstellungen → Apps → Installierte Apps → FokusWache → Deinstallieren**. Schließe vorher das FokusWache-Fenster und lass aktive Verriegelungen ablaufen. Die Deinstallation entfernt Dienst, zugehörige Firewall-Regeln, Native-Messaging-Registrierungen, Verknüpfungen und die vom Setup installierten Programmdateien. Regeln, Zeitkonten, Tagebucheinträge und eigene zusätzlich im Programmordner abgelegte Dateien bleiben erhalten. Entferne die Browser-Erweiterung zusätzlich in den verwendeten Browserprofilen.

Für eine Tagebuchsicherung schließe FokusWache und kopiere `%LOCALAPPDATA%\FokusWache\zeitprotokoll.sqlite3`. Die Regel- und Zeitkontendaten liegen geschützt unter `%PROGRAMDATA%\FokusWache`; sie sind von der Tagebuchdatei unabhängig.

## Wenn etwas nicht funktioniert

- **Dienst nicht verbunden:** Prüfe den Windows-Dienst `FokusWache` und die Protokolle unter `%PROGRAMDATA%\FokusWache`.
- **Browsernetz pausiert:** Prüfe die Erweiterung und das aktuell verwendete Profil unter **Browser & Schutz**. Eine Netzpause ist kein verbrauchtes Tagesbudget.
- **Ein Spiel wird nicht erkannt:** Ergänze die EXE oder den Spielordner in derselben Spieleregel. So bleibt das gemeinsame Tagesbudget erhalten.
- **Änderung abgewiesen:** Prüfe die Verriegelungszeit. Aktive Verriegelungen schützen auch vor regulären Updates und Deinstallation.

Das Setup und die Anwendung sind noch nicht digital signiert. Windows kann einen unbekannten Herausgeber oder eine SmartScreen-Meldung anzeigen. Vergleiche den Download bei Bedarf mit der Datei `SHA256SUMS.txt` aus demselben Release. [Eigenbau und Installationstests](Entwicklung.md) sind separat dokumentiert.
