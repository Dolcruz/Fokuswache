# Entwicklung und Build

## Aufbau

| Pfad | Aufgabe |
|---|---|
| `src/engine.py` | Validierung, Zeitpläne, Tagesbudgets und Verriegelungen |
| `src/service.py` | Windows-Dienst, Regelzustand, Prozess- und Browserdurchsetzung |
| `src/windows.py` | Windows-Prozesse, Spieleerkennung, Firewall und Sitzungsagenten |
| `src/agent.py` | Vordergrunderfassung und Countdown für Geräteaktionen |
| `src/ui.py` | Qt-Oberfläche für Regeln und Verbindungszustand |
| `src/journal.py`, `src/journal_ui.py` | SQLite-Tagebuch und Rückblick |
| `src/native.py`, `src/ipc.py` | Browser-Brücke und lokale Windows-Pipe |
| `extensions/` | Chromium- und Firefox-Erweiterung |
| `tests/` | Python-Tests und JavaScript-Prüfungen |
| `tools/` | Isolierter Testlauf und Screenshot-Erzeugung |
| `installer/` | Inno-Setup-Assistent, zentrale Windows-Einrichtung und Quellenmanifest |

## Umgebung und Build

Verwende CPython 3.12 auf Windows und eine eigene virtuelle Umgebung. Die direkten Abhängigkeiten sind in `requirements.txt` auf konkrete Versionen festgelegt. Pip löst deren transitive Abhängigkeiten auf; es wird kein bitidentischer Build zugesichert.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\Bauen.ps1 -Python .\.venv\Scripts\python.exe
```

PyInstaller schreibt temporäre Dateien nach `build/` und erstellt die Programme unter `app/`. Ein erneuter Build ersetzt ausschließlich den erzeugten Projektordner `app/`. Er verändert keine installierte FokusWache-Instanz. Die Ausgabe enthält gemeinsam genutzte Laufzeitdateien unter `app/_internal`; halte den Ordner vollständig zusammen.

Für den Windows-Installer benötigst du zusätzlich **Inno Setup 6.7 oder neuer**:

```powershell
.\Paketieren.ps1 -Python .\.venv\Scripts\python.exe
```

Der Compiler wird über PATH und die üblichen Inno-Setup-Installationsordner gesucht; alternativ gibst du seinen Pfad mit `-Iscc` an. Der Build lädt die in `installer/sources.json` festgelegten offiziellen Quellarchive einmalig nach `build/sources`, prüft deren SHA-256-Werte und sammelt die Laufzeit-Lizenzhinweise. Das Setup, das separate Quellarchiv und `SHA256SUMS.txt` entstehen unter `dist/`. Der Paketbau installiert nichts auf dem Build-Rechner.

Das Setup besitzt genau einen Windows-Einrichtungsablauf in `installer/Windows.ps1`. Inno Setup verwaltet die installierten Dateien und den Eintrag unter „Installierte Apps“. Die Windows-Einrichtung übernimmt die Verriegelungsprüfung, den eigenen Dienst, geschützte Verzeichnisse und die Native-Messaging-Registrierung. Updates und Deinstallation verwenden denselben Ablauf; frühere separate Installationsskripte werden nicht benötigt.

## Prüfen

Zusätzlich zu den Python-Abhängigkeiten benötigt die JavaScript-Prüfung Node.js.

```powershell
.\.venv\Scripts\python.exe tools/check.py
```

Der Runner führt `unittest discover` und die JavaScript-Prüfungen aus. Er verwendet temporäres `LOCALAPPDATA` sowie Qt mit `QT_QPA_PLATFORM=offscreen`. Controller-Tests verwenden temporäre Zustände und gemockte Durchsetzung; es wird kein Windows-Dienst gestartet. Der Test-Runner setzt keine eigene Laufzeitfrist.

```powershell
.\.venv\Scripts\python.exe tools/screenshots.py
```

Dies erzeugt die Dokumentationsbilder aus der echten Qt-Oberfläche. Regeln und Tagebucheinträge sind fest definierte Beispieldaten in einem temporären Profil; es wird keine Verbindung zum installierten Dienst aufgebaut.

## Veröffentlichen

Quellcode und Dokumentationsbilder gehören ins Git-Repository. `app/`, `build/`, `dist/`, virtuelle Umgebungen, Logs, Regelzustände und Tagebuchdateien sind ausgeschlossen.

Der Workflow **Windows installer** baut auf einem frischen GitHub-Windows-Runner und führt zuerst die Python- und JavaScript-Prüfungen aus. Anschließend prüft `tests/test_installer.ps1` das wirkliche Setup: Erstinstallation, kompilierter IPC-Client, Qt-Oberflächenstart, Update mit vorhandenen Regeln, Abweisung bei offenem Fenster oder aktiver Verriegelung sowie Deinstallation mit Erhalt der Nutzerdaten und unregistrierter eigener Dateien. Dieser Test verweigert die Ausführung auf dem normalen Arbeitsplatz und bei vorhandenen FokusWache-Daten.

Nur ein erfolgreicher Testlauf lädt das Setup als `windows-installer`-Artefakt hoch. Für den Job gilt GitHubs Standardfrist von 360 Minuten; Artefakte bleiben 7 Tage erhalten. Der Oberflächenstart muss im Integrationstest innerhalb von 20 Sekunden seine Windows-Nachrichtenschleife erreichen. Die Anwendung selbst bekommt dadurch keine zusätzliche Laufzeitfrist.

Release-Artefakte werden aus einem erfolgreichen Lauf übernommen und zusammen mit dem geprüften Commit getaggt. Vor der Veröffentlichung werden Setup und Quellarchiv gegen `SHA256SUMS.txt` geprüft. Siehe [Drittanbieter](Drittanbieter.md) für die mitinstallierten Lizenzen und entsprechenden Quellen.
