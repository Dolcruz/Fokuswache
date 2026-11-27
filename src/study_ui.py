"""Qt dialogs for the learning session ("Lernmodus"). The service enforces every rule shown here."""
import datetime as dt

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLineEdit, QProgressBar, QComboBox

MODEL_NAMES = {'claude-opus-5-5': 'Claude Opus 5.5 (genaueste Einschätzung)',
               'claude-sonnet-5-5': 'Claude Sonnet 5.5',
               'claude-haiku-5-5': 'Claude Haiku 5.5 (günstigste)'}


def clock(value):
    try:
        return dt.datetime.fromisoformat(value).astimezone().strftime('%H:%M')
    except (TypeError, ValueError):
        return '–'


def summary_line(s):
    places = ', '.join(f'{k} ({v}×)' for k, v in sorted(s.get('places', {}).items(), key=lambda kv: -kv[1]))
    text = f"Letzte Lernzeit: {int(round(s['minutes']))} von {s['planned_minutes']} Minuten"
    text += ' · kein Abdriften bemerkt' if not s['drifts'] else f" · {s['drifts']}× abgedriftet" + (f': {places}' if places else '')
    return text + (' · vorzeitig beendet' if s.get('early') else '')


class StudyStart(QDialog):
    def __init__(self, app):
        from ui import button, column, label
        super().__init__(app)
        self.app = app
        self.setWindowTitle('Lernmodus starten')
        self.resize(560, 360)
        layout = column(self, 26)
        layout.addWidget(label('Lernmodus starten', 'title'))
        layout.addWidget(label('Woran arbeitest du? Ein Satz reicht, er ist der Maßstab für den Aufpasser.', 'muted'))
        self.goal = QLineEdit()
        self.goal.setPlaceholderText('z. B. IPI Kapitel 9.2, Skript und Trainer')
        self.goal.setMaxLength(200)
        layout.addWidget(self.goal)
        status = app.status
        aware = ('Alle Webseiten-, Programm- und Spielregeln werden für die gewählte Dauer gesperrt, auch pausierte. '
                 'Internet- und Computerpausen bleiben unverändert. Danach gilt wieder der vorherige Zustand.')
        if status.get('vision_ready'):
            aware += ('\n\nDer Aufpasser macht in zufälligen Abständen einen Screenshot und lässt ihn von '
                      + MODEL_NAMES.get(status.get('vision_model'), 'Claude').split(' (')[0]
                      + ' bewerten. Das Bild wird nicht gespeichert.')
        else:
            aware += '\n\nDer Aufpasser ist aus: Unter „Browser & Schutz“ ist noch kein API-Schlüssel hinterlegt.'
        layout.addWidget(label(aware, 'muted'))
        self.message = label('', 'muted')
        layout.addWidget(self.message)
        row = QHBoxLayout()
        self.buttons = []
        for minutes in (25, 50, 90):
            b = button(f'{minutes} Minuten', lambda checked=False, m=minutes: self.start(m), minutes == 50)
            row.addWidget(b)
            self.buttons.append(b)
        row.addStretch()
        row.addWidget(button('Abbrechen', self.reject))
        layout.addLayout(row)
        layout.addWidget(label('Tipp: Strg+Alt+L öffnet diesen Start auch ohne FokusWache-Fenster.', 'muted'))
        self.goal.returnPressed.connect(lambda: self.start(50))
        self.goal.setFocus()

    def start(self, minutes):
        if not self.goal.text().strip():
            self.message.setText('Bitte kurz angeben, woran du arbeitest.')
            return
        for b in self.buttons:
            b.setEnabled(False)
        self.app.call({'op': 'study_start', 'minutes': minutes, 'goal': self.goal.text()}, self.started, self.failed)

    def started(self, result):
        self.app.poll()
        self.accept()

    def failed(self, error):
        self.message.setText(str(error))
        for b in self.buttons:
            b.setEnabled(True)


class StudyStop(QDialog):
    """Deliberately slow: type a sentence, then wait; the service checks both."""
    def __init__(self, app):
        from ui import button, column, label
        super().__init__(app)
        self.app = app
        self.sentence = app.status.get('study_stop_sentence', '')
        self.wait = app.status.get('study_stop_wait', 60)
        self.setWindowTitle('Lernmodus vorzeitig beenden')
        self.resize(580, 380)
        layout = column(self, 26)
        layout.addWidget(label('Wirklich jetzt aufhören?', 'title'))
        study = app.status.get('study') or {}
        layout.addWidget(label(f"Geplant bis {clock(study.get('until'))}. Wenn du trotzdem aufhören möchtest, "
                               f'tippe den Satz ab und warte danach {self.wait} Sekunden.', 'muted'))
        layout.addWidget(label('„' + self.sentence + '“'))
        self.entry = QLineEdit()
        self.entry.textChanged.connect(self.changed)
        layout.addWidget(self.entry)
        self.progress = QProgressBar()
        self.progress.setRange(0, self.wait)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.message = label('', 'muted')
        layout.addWidget(self.message)
        row = QHBoxLayout()
        self.request_button = button('Wartezeit starten', self.request_stop)
        self.request_button.setEnabled(False)
        self.stop_button = button('Lernmodus beenden', self.stop)
        self.stop_button.setObjectName('danger')
        self.stop_button.setEnabled(False)
        row.addWidget(self.request_button)
        row.addWidget(self.stop_button)
        row.addStretch()
        row.addWidget(button('Weiterlernen', self.reject, True))
        layout.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.count)
        self.left = None

    def matches(self):
        return ' '.join(self.entry.text().split()) == self.sentence

    def changed(self):
        self.request_button.setEnabled(self.matches() and self.left is None)
        self.stop_button.setEnabled(self.matches() and self.left == 0)

    def request_stop(self):
        self.request_button.setEnabled(False)
        self.entry.setReadOnly(True)
        self.app.call({'op': 'study_stop_request'}, self.requested, self.failed)

    def requested(self, result):
        self.left = int(result.get('wait', self.wait)) + 1
        self.progress.setVisible(True)
        self.timer.start(1000)
        self.count()

    def count(self):
        self.left = max(0, self.left - 1)
        self.progress.setValue(self.wait - min(self.wait, self.left))
        self.message.setText(f'Noch {self.left} Sekunden. Du kannst jederzeit weiterlernen.' if self.left else
                             'Du kannst jetzt beenden.')
        if not self.left:
            self.timer.stop()
        self.changed()

    def stop(self):
        self.stop_button.setEnabled(False)
        self.app.call({'op': 'study_stop', 'sentence': self.entry.text()}, self.stopped, self.failed)

    def stopped(self, result):
        self.app.poll()
        self.accept()

    def failed(self, error):
        self.message.setText(str(error))
        self.entry.setReadOnly(False)
        self.left = None
        self.timer.stop()
        self.progress.setVisible(False)
        self.changed()


class StudyBanner(QFrame):
    def __init__(self, app):
        from ui import button, label
        super().__init__()
        self.app = app
        self.setObjectName('card')
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 14, 20, 14)
        self.text = label('')
        row.addWidget(self.text, 1)
        self.stop_button = button('Vorzeitig beenden …', lambda: StudyStop(app).exec())
        row.addWidget(self.stop_button)

    def render(self, status):
        study = status.get('study')
        history = status.get('study_history') or []
        if study:
            left = int(study['remaining'] // 60)
            self.setStyleSheet('QFrame#card { background: #fdf6e8; border: 1px solid #ecd9b2; }')
            self.text.setText(f"<b>Lernmodus läuft</b> bis {clock(study['until'])} · noch {left} min"
                              f"<br>{study['goal']}" + (f" · {study['drifts']}× abgedriftet" if study['drifts'] else ''))
            self.stop_button.setVisible(True)
            self.stop_button.setEnabled(self.app.connected)
            self.setVisible(True)
        elif history:
            self.setStyleSheet('')
            self.text.setText(summary_line(history[-1]))
            self.stop_button.setVisible(False)
            self.setVisible(True)
        else:
            self.setVisible(False)


class VisionCard:
    """API key and model for the watcher; the key goes to the service and is never shown again."""
    def __init__(self, app, layout):
        from ui import button, card, label
        self.app = app
        box, info = card()
        info.addWidget(label('Lernmodus-Aufpasser', 'heading'))
        info.addWidget(label('Während des Lernmodus macht FokusWache in zufälligen Abständen einen Screenshot und lässt ihn über '
                             'die Claude-API bewerten. Was gerade auf dem Bildschirm ist, wird dafür an Anthropic gesendet. '
                             'Das Bild wird nicht gespeichert; übrig bleibt nur die Kurzstatistik. Außerhalb des Lernmodus '
                             'werden keine Bilder gemacht.', 'muted'))
        self.state = label('', 'muted')
        info.addWidget(self.state)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText('API-Schlüssel (sk-ant-…)')
        info.addWidget(self.key)
        self.model = QComboBox()
        for model_id, name in MODEL_NAMES.items():
            self.model.addItem(name, model_id)
        info.addWidget(self.model)
        row = QHBoxLayout()
        self.save_button = button('Speichern', self.save, True)
        self.clear_button = button('Schlüssel entfernen', self.clear)
        row.addWidget(self.save_button)
        row.addWidget(self.clear_button)
        row.addStretch()
        info.addLayout(row)
        layout.addWidget(box)
        self.synced = None

    def render(self, status):
        ready = status.get('vision_ready')
        self.state.setText('Schlüssel hinterlegt (verschlüsselt im Dienst).' if ready else 'Noch kein Schlüssel hinterlegt. Ohne Schlüssel gelten im Lernmodus nur die Sperren.')
        model = status.get('vision_model')
        if model != self.synced and self.model.findData(model) >= 0:
            self.model.setCurrentIndex(self.model.findData(model))
            self.synced = model
        studying = bool(status.get('study'))
        self.clear_button.setEnabled(bool(ready) and not studying and self.app.connected)
        self.save_button.setEnabled(self.app.connected)
        self.key.setEnabled(not studying)

    def save(self):
        payload = {'op': 'vision_set', 'model': self.model.currentData()}
        if self.key.text().strip():
            payload['key'] = self.key.text().strip()
        self.app.call(payload, self.saved, self.app.failed)

    def clear(self):
        if self.app.confirm('Schlüssel entfernen', 'API-Schlüssel aus FokusWache entfernen? Der Aufpasser ist danach aus.'):
            self.app.call({'op': 'vision_set', 'clear': True, 'model': self.model.currentData()}, self.saved, self.app.failed)

    def saved(self, result):
        self.key.clear()
        self.synced = None
        self.app.notice.setText('Aufpasser-Einstellungen gespeichert.')
        self.app.poll()
