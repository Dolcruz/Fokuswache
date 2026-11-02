# FokusWache installieren

## Voraussetzungen

- Windows 10 oder Windows 11, 64 Bit
- Python 3.12 und Git für den Eigenbau
- Administratorrechte für Installation, Updates und Entfernung des Dienstes
- Internet für den einmaligen Download der Python-Abhängigkeiten; die Anwendung selbst arbeitet lokal

## Aus dem Quellcode

Die Schritte aus der [README](../README.md#loslegen) erzeugen `app/FokusWache.exe` und `app/FokusWacheNative.exe`. Der gesamte Ordner `app` wird benötigt; die EXE ist keine alleinstehende portable Anwendung.

`Installieren.ps1` kopiert die Programme und Erweiterungen nach `%PROGRAMFILES%\FokusWache`, schützt Programm- und Regelordner mit Windows-Berechtigungen, registriert den automatisch startenden Dienst und legt Desktop- und Startmenüverknüpfungen an. Windows fragt nach einer Administratorbestätigung.

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

Baue den neuen Quellstand und führe `Aktualisieren.ps1` aus. Aktive Verriegelungen müssen vorher ablaufen. Das Skript ersetzt Programme und Erweiterungen nach Administratorbestätigung und startet den Dienst neu. Persönliche Regeln, Zeitkonten und Tagebucheinträge liegen außerhalb des Projektordners.

## Entfernen und sichern

`Deinstallieren.ps1` entfernt nach Ablauf der Verriegelungen den Dienst, die zugehörigen Firewall-Regeln, Native-Messaging-Registrierungen und Verknüpfungen. Programmdateien und gespeicherte Daten bleiben bewusst erhalten. Entferne die Browser-Erweiterung zusätzlich in den verwendeten Browserprofilen.

Für eine Tagebuchsicherung schließe FokusWache und kopiere `%LOCALAPPDATA%\FokusWache\zeitprotokoll.sqlite3`. Die Regel- und Zeitkontendaten liegen geschützt unter `%PROGRAMDATA%\FokusWache`; sie sind von der Tagebuchdatei unabhängig.

## Wenn etwas nicht funktioniert

- **Dienst nicht verbunden:** Prüfe den Windows-Dienst `FokusWache` und die Protokolle unter `%PROGRAMDATA%\FokusWache`.
- **Browsernetz pausiert:** Prüfe die Erweiterung und das aktuell verwendete Profil unter **Browser & Schutz**. Eine Netzpause ist kein verbrauchtes Tagesbudget.
- **Ein Spiel wird nicht erkannt:** Ergänze die EXE oder den Spielordner in derselben Spieleregel. So bleibt das gemeinsame Tagesbudget erhalten.
- **Änderung abgewiesen:** Prüfe die Verriegelungszeit. Aktive Verriegelungen schützen auch vor regulären Updates und Deinstallation.

Die installierte Anwendung und selbst gebaute EXE-Dateien sind nicht digital signiert. Dieses Repository enthält derzeit keinen fertigen Windows-Installer zum Herunterladen.
