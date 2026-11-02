# FokusWache: Komponenten, Lizenzen und Quellen

Der eigene FokusWache-Code ist Copyright (c) 2026 Falk Pfisterer und unter der MIT-Lizenz verfügbar. Die Datei `LICENSE` liegt im Programmordner. Quellcode und Build-Anleitung: https://github.com/Dolcruz/Fokuswache

Diese Windows-Ausgabe verwendet **Qt 6.11.2, PySide6 6.11.2 und Shiboken6 6.11.2 unter LGPLv3**, Copyright The Qt Company Ltd. und weitere Mitwirkende. Die vollständigen GPLv3-/LGPLv3-Texte und Komponentenhinweise befinden sich in den Unterordnern dieses Verzeichnisses. Die Qt-DLLs und Python-Bindings unter `_internal` sind dynamisch geladene Bibliotheken. Du darfst diese Bibliotheken entsprechend ihren Lizenzen durch schnittstellenkompatible geänderte Ausgaben ersetzen und die Änderungen untersuchen. Dafür werden weder ein Signaturschlüssel noch ein Freischaltcode benötigt. Unter Windows sind zum Ersetzen von Programmdateien Administratorrechte erforderlich; beende zuvor FokusWache und seinen Dienst.

Die unveränderten entsprechenden Quellen von Qt Base, Qt SVG, PySide6/Shiboken6 sowie pywin32 stehen neben dem Setup im Release als separates **FokusWache-ThirdPartySources**-Archiv bereit. Das Archiv enthält auch die geprüften SHA-256-Werte und die ursprünglichen Downloadadressen in `sources.json`.

- Releases und Quellen: https://github.com/Dolcruz/Fokuswache/releases
- Qt Base: https://github.com/qt/qtbase/tree/v6.11.2
- Qt SVG: https://github.com/qt/qtsvg/tree/v6.11.2
- PySide6/Shiboken6: https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/
- PySide6-Lizenzinformationen: https://pypi.org/project/PySide6-Essentials/6.11.2/

Weitere Laufzeitkomponenten sind Python 3.12 mit seinen Laufzeitbibliotheken, Tcl/Tk, pywin32 312, psutil 7.2.2 und tzdata 2026.3. Ihre Copyright- und Lizenztexte werden in diesem Verzeichnis beziehungsweise den mitgelieferten Laufzeitordnern aufbewahrt. Qt bringt zusätzliche Komponenten unter deren eigenen Lizenzen mit; zugehörige Hinweise aus den unveränderten Quellpaketen liegen ebenfalls hier.

Python: https://www.python.org/ · pywin32: https://github.com/mhammond/pywin32/tree/b312 · psutil: https://github.com/giampaolo/psutil · tzdata: https://github.com/python/tzdata
