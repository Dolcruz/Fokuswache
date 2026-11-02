# Betriebsverhalten und Grenzen

Die folgenden Werte sind im veröffentlichten Quellstand enthalten. Es gibt keine Modellinferenz, keine externe KI-API und keine eigenen Modell-Zeitlimits.

## Durchsetzung und Erfassung

| Wert | Geltungsbereich und Verhalten |
|---|---|
| Etwa 1 Sekunde | Zieltakt des Dienstes. Ein langsamer Tick wird nicht abgebrochen; zwischen Ticks liegt eine Pause von mindestens 50 ms. Eine Programmsperre wirkt deshalb periodisch. |
| Höchstens 3 Sekunden je Zählschritt | Längere Erfassungslücken werden nicht als Nutzung nachberechnet. Zeit aus Standby oder längeren Unterbrechungen wird dadurch nicht pauschal berechnet. |
| 750 ms | Vordergrundagent und Browser-Erweiterung melden ihren Zustand regelmäßig. Die Erweiterung startet keinen zweiten überlappenden Pulse-Durchlauf. |
| 3 Sekunden | Ältere Agenten- und Browsermeldungen gelten im Dienst nicht mehr als aktuelle Nutzungsbeobachtung. |
| 4 Sekunden | Frischegrenze für die Bereitschaft der Erweiterung und die Anzeige aus dem Sitzungsagenten. Veraltete Bestätigungen werden nicht als aktuell gemeldet beziehungsweise angezeigt. |
| 12 Sekunden | Verbindungslease eines bereits bestätigten Browserprozesses. Danach pausiert bei aktiven Webregeln dessen Netzwerk. Noch nie bestätigte Browser haben keine solche Toleranz. Eine Wiederverbindung gibt das Netzwerk wieder frei. |
| 60 Sekunden ohne Eingabe | Webseiten-, Internet- und Gerätezeit wird bei Inaktivität nicht weiter berechnet. Programme und Spiele zählen nach Vordergrundprozess. |
| 30 Sekunden | Erneute automatische Spieleerkennung. Neue Installationen können erst beim nächsten Suchlauf erscheinen. |
| 10 Sekunden | Überprüfung der benötigten Windows-Sitzungsagenten. |
| 2 Sekunden | Die Oberfläche fragt den Dienstzustand regelmäßig ab. |
| 60 Sekunden | Countdown vor Bildschirmverriegelung, Abmeldung oder Herunterfahren. Anzeige wird alle 500 ms aktualisiert. Derselbe Auftrag wird innerhalb von 65 Sekunden nicht erneut ausgeführt. |
| 100 Ereignisse | Gespeicherter Betriebsereignisverlauf. Ältere Ereignisse werden verdrängt; die Statusansicht erhält die letzten 30, der Agent die letzten 5. Fehlerlogs haben keine automatische Größenrotation. |

## Lokale Kommunikation

| Wert | Geltungsbereich und Verhalten |
|---|---|
| 512 KiB | Maximale lokale Nachricht. Zu große Clientanfragen werden abgewiesen; der Native-Messaging-Prozess beendet sich bei einer entsprechend zu großen eingehenden Nachricht. Antworten werden ebenfalls über 512-KiB-Lesepuffer gelesen. |
| 3 Sekunden, Versuche im Abstand von 100 ms | Verbindungsaufbau des IPC-Clients zur Windows-Pipe. Danach erscheint ein Erreichbarkeitsfehler. **Nach dem Verbindungsaufbau gibt es keine eigene Frist für blockierende Schreib-, Lese- und Flush-Aufrufe.** |
| 32 Pipe-Instanzen | Gleichzeitig angelegte Dienstverbindungen. Eine Verbindung hat einen eigenen Thread und kann diesen bei blockierender Kommunikation belegen. Weitere Verbindungen können scheitern. |
| 3.000 ms | In `CreateNamedPipe` hinterlegter Windows-Standardwartewert. Er ist keine Gesamtfrist einer Verbindung; der Client verwendet seine eigene oben beschriebene Verbindungsaufbauschleife. |
| 5.000 Tabs pro Browsermeldung | Größere Tablisten werden zurückgewiesen. Zusätzlich gilt die Nachrichtengröße, die früher erreicht werden kann. |
| 8.192 Zeichen je URL | Längere URLs werden für die lokale Prüfung abgeschnitten. Regeln mit sehr langen Pfaden können deshalb nicht vollständig geprüft werden. |

Die Erweiterung versucht bei ihren weiteren regelmäßigen Meldungen erneut, eine getrennte native Verbindung herzustellen. Es gibt keine feste Gesamtzahl dieser Versuche. Die Netzregelkapazität wird außerdem vom jeweiligen Browser begrenzt; schlägt die Übernahme fehl, meldet die Erweiterung keine Bereitschaft. Es wird keine zusätzliche Browser-Standardkapazität im Projekt festgelegt.

## Regeln und Eingaben

| Grenze | Verhalten |
|---|---|
| 100 Zeichen für Regelnamen, 80 für Regel-IDs | Ungültige Regeln werden zurückgewiesen; das Namensfeld nimmt höchstens 100 Zeichen an. |
| 500 Ziele und 500 Ausnahmen je Regel, jeweils 1.024 Zeichen pro Eintrag | Überschreitungen werden bei der Regelvalidierung zurückgewiesen. |
| 50 Wochenfenster pro Regel | Weitere Fenster werden bei der Validierung zurückgewiesen. |
| Tagesbudget größer 0 bis 1.440 Minuten; Oberfläche ab 0,1 Minute | Andere Werte werden zurückgewiesen beziehungsweise vom Eingabefeld begrenzt. Ohne Tagesbudget greifen die übrigen Bedingungen. |
| 1 bis 10.080 Minuten im Timer-/Verriegelungsdialog; Vorgabe 25 Minuten | Das Eingabefeld begrenzt die Auswahl auf eine Woche. Der Dienst akzeptiert Timer bis 527.040 Minuten und Verriegelungen bis 366 Tage; größere Werte werden zurückgewiesen. |
| 2.048 Einträge im Windows-Dateiinformationscache | Ältere Cacheeinträge werden durch neuere ersetzt; sie werden bei Bedarf erneut ermittelt. |

Die Anwendung setzt keine feste Gesamtzahl von Regeln oder Tagebucheinträgen. Zeitkonten, Datenbank und Fehlerlogs werden nicht automatisch gelöscht. Große Datenbestände benötigen entsprechend mehr Speicher und Laufzeit. Qt-Textfelder ohne eigene Grenze behalten die Bibliotheksvorgaben: einzeilige `QLineEdit`-Felder nehmen standardmäßig bis zu 32.767 Zeichen an, `QTextEdit` verwendet keine eigene projektseitige Textlängengrenze.

## Speicherung, Installation und Build

- SQLite wartet bei einer gesperrten Tagebuchdatenbank **bis zu 5 Sekunden**. Danach schlägt der Zugriff mit einem Fehler fehl; Eingaben werden nicht als erfolgreich gespeichert dargestellt.
- Der Installer wartet **20 Sekunden** auf den Zustand `Running`. Das Update wartet **15 Sekunden** auf `Stopped` und **20 Sekunden** auf den erneuten Start. Eine Überschreitung löst einen Fehler aus; sie bedeutet nicht automatisch, dass alle zuvor ausgeführten Installationsschritte zurückgerollt wurden.
- Die konfigurierte Windows-Dienstwiederherstellung setzt den Fehlerzähler nach **86.400 Sekunden** zurück und sieht Neustarts nach **2, 2 und anschließend 5 Sekunden** vor. Wiederholte Dienstfehler können so weitere Starts auslösen.
- Paketdownloads verwenden die pip-Standardwerte: **15 Sekunden Netzwerk-Wartezeit, bis zu 5 Verbindungswiederholungen**. Nach Ausschöpfen bricht die Paketinstallation ab. Build und Tests setzen keine eigene gesamte Laufzeitfrist.
- Firewall- und andere Windows-API-Aufrufe verwenden das Verhalten des Betriebssystems; das Projekt fügt ihnen keinen allgemeinen Aufruf-Timeout hinzu. Blockierende Aufrufe können den jeweiligen Thread belegen.

## Schutzumfang

Der installierte Dienst und die Sitzungserfassung laufen unter dem Windows-Systemkonto. Der Regelordner ist gegen Schreibzugriffe normaler Benutzer geschützt. Ein Administrator, der abgesicherte Modus, manipulierte Erweiterungen oder eigens angepasste Browser liegen außerhalb einer zugesicherten Manipulationssicherheit.

Unterstützte Webregeln beziehen sich auf verbundene Browser. Eingebettete WebViews sind nicht automatisch gleichwertig. Die automatische Spieleerkennung kann portable Spiele oder weitere Launcher übersehen; eigene Pfade ergänzen sie. Ein Fokus-Timer ist eine lokale Regelverriegelung, kein Sicherheitsmechanismus gegen den Gerätebesitzer.
