# Drittanbieterkomponenten

FokusWache verwendet die folgenden Komponenten. Die MIT-Lizenz des eigenen Projektcodes ersetzt deren jeweilige Lizenzen nicht.

| Komponente | Verwendung | Lizenzinformationen |
|---|---|---|
| Python | Laufzeit | [Python-Lizenz](https://docs.python.org/3/license.html) |
| PySide6 / Qt for Python | Qt-Oberfläche und Python-Anbindung | [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html) |
| Qt | Fenster, Widgets und weitere Laufzeitbibliotheken | [Qt Open Source / LGPL](https://www.qt.io/development/open-source-lgpl-obligations) |
| pywin32 | Windows-APIs, Dienst und IPC | [pywin32-Lizenz](https://github.com/mhammond/pywin32/blob/main/License.txt) |
| psutil | Prozessinformationen | [BSD-3-Clause](https://github.com/giampaolo/psutil/blob/master/LICENSE) |
| tzdata | IANA-Zeitzonendaten | [tzdata-Lizenz](https://github.com/python/tzdata/blob/main/LICENSE) |
| PyInstaller | Erzeugen lokaler Windows-Builds | [GPL mit Bootloader-Ausnahme](https://pyinstaller.org/en/stable/license.html) |

Die genauen Paketversionen stehen in [`requirements.txt`](../requirements.txt). Weitere Build-Abhängigkeiten werden durch diese Pakete installiert.

Das Windows-Setup enthält Python und die benötigten Laufzeitbibliotheken. Deren Lizenztexte und Komponentenhinweise werden unter `%PROGRAMFILES%\FokusWache\licenses` installiert. Qt/PySide6/Shiboken6 werden unter LGPLv3 verwendet; die dynamisch geladenen Bibliotheken unter `_internal` können durch schnittstellenkompatible geänderte Ausgaben ersetzt werden. Der eigene Anwendungscode bleibt unter MIT verfügbar. Die Datei `installer/ThirdPartyNotices.md` erläutert die Quellen und das Ersetzen der Bibliotheken.

Die unveränderten entsprechenden Qt-Base-, Qt-SVG-, PySide6-/Shiboken6- und pywin32-Quellen stehen neben dem Setup als separates **FokusWache-ThirdPartySources**-Archiv im Release. Das versionierte Manifest `installer/sources.json` enthält Downloadadressen und SHA-256-Werte. Der Paketbau übernimmt die Lizenz- und Copyright-Hinweise aus diesen Quellarchiven und den installierten Python-Paketen.
