# Drittanbieterkomponenten

FokusWache verwendet die folgenden Komponenten. Die Rechtevorbehalte für den eigenen Projektcode ersetzen deren Lizenzen nicht.

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

Dieses Repository enthält eigenen Quellcode, Browser-Erweiterungen und Dokumentation. Die Python- und Qt-Laufzeit sowie fremde Bibliotheken werden beim Eigenbau separat installiert. Für vorkompilierte Weitergaben gelten zusätzlich die jeweiligen Bedingungen für binäre Distributionen, einschließlich Lizenzhinweisen und der Anforderungen an entsprechende Quellen und das Ersetzen von LGPL-Bibliotheken. Die Dokumentation von Qt erläutert diese Bedingungen unter den oben verlinkten Lizenzinformationen.
