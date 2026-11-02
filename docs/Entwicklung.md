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

## Umgebung und Build

Verwende CPython 3.12 auf Windows und eine eigene virtuelle Umgebung. Die direkten Abhängigkeiten sind in `requirements.txt` auf konkrete Versionen festgelegt. Pip löst deren transitive Abhängigkeiten auf; es wird kein bitidentischer Build zugesichert.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\Bauen.ps1 -Python .\.venv\Scripts\python.exe
```

PyInstaller schreibt temporäre Dateien nach `build/` und erstellt die Programme unter `app/`. Ein erneuter Build ersetzt ausschließlich den erzeugten Projektordner `app/`. Er verändert keine installierte FokusWache-Instanz. Die Ausgabe enthält gemeinsam genutzte Laufzeitdateien unter `app/_internal`; halte den Ordner vollständig zusammen.

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

Quellcode und Dokumentationsbilder gehören ins Git-Repository. `app/`, `build/`, virtuelle Umgebungen, Logs, Regelzustände und Tagebuchdateien sind ausgeschlossen.

Vor einer Verteilung ausführbarer Pakete müssen auch die Lizenztexte, Hinweise und gegebenenfalls entsprechenden Quellen der gebündelten Laufzeitbibliotheken mitgeliefert oder zugänglich gemacht werden. Die lokalen PyInstaller-Builds sind Prüf- und Eigenbauausgaben; dieses Repository verteilt derzeit keine vorkompilierten Pakete. Siehe [Drittanbieter](Drittanbieter.md).
