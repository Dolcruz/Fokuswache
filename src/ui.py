"""Qt desktop client. Policy and accounting remain owned by the Windows service."""
import copy
import datetime as dt
import os
import threading
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QObject, Signal, QTime
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea, QStackedWidget,
    QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QTimeEdit, QDialog, QDialogButtonBox, QMessageBox, QFileDialog, QProgressBar)
from ipc import request
from engine import validate_rule
from journal_ui import JournalPage

KINDS = {'web': 'Webseiten', 'apps': 'Programme', 'games': 'Spiele',
         'internet': 'Gesamtes Internet', 'device': 'Computer'}
DAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
FIELDS = ('id', 'name', 'kind', 'targets', 'exceptions', 'enabled', 'daily_minutes',
          'schedules', 'schedule_mode', 'timer_until', 'locked_until', 'device_action')
TEMPLATES = [
    ('YouTube', 'Videos bewusst genießen', 'YT', '#e94b4b', 'web', ['youtube.com', 'youtu.be'], 30),
    ('Instagram', 'Weniger scrollen, mehr erleben', 'ig', '#b94ba0', 'web', ['instagram.com'], 20),
    ('Twitter / X', 'Dein Limit für den Feed', 'X', '#263244', 'web', ['x.com', 'twitter.com'], 30),
    ('TikTok', 'Kurze Videos, klare Grenzen', 'tk', '#246b70', 'web', ['tiktok.com'], 20),
    ('Reddit', 'Diskussionen mit Zeitbudget', 'r', '#e76b39', 'web', ['reddit.com'], 30),
    ('Facebook', 'Platz für andere Dinge', 'f', '#3971d9', 'web', ['facebook.com'], 20),
    ('Twitch', 'Streams mit Feierabend', 'tw', '#8450c6', 'web', ['twitch.tv'], 60),
    ('Streaming', 'Netflix, Disney+ und Prime Video', 'TV', '#47649e', 'web', ['netflix.com', 'disneyplus.com', 'primevideo.com'], 90),
    ('Spiele', 'Ein Budget für alle erkannten Spiele', 'G', '#38546d', 'games', [], 120),
    ('Eigene Programme', 'Apps oder ganze Ordner wählen', '+', '#6973b7', 'apps', [], 60),
    ('Eigene Webseiten', 'Deine persönliche Auswahl', 'www', '#258376', 'web', [], 30),
    ('Internetpause', 'Das gesamte Netzwerk begrenzen', 'IP', '#a77832', 'internet', [], None),
    ('Computerpause', 'Bildschirm nach Zeitplan sperren', 'PC', '#677a8b', 'device', [], None),
]
STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 14px; color: #233346; }
QMainWindow, QDialog, QWidget#page { background: #f5f7fa; }
QWidget#sidebar { background: #142c32; }
QLabel { background: transparent; }
QLabel#muted { color: #687787; }
QLabel#title { font-size: 29px; font-weight: 700; color: #172d36; }
QLabel#heading { font-size: 19px; font-weight: 600; }
QLabel#metric { font-size: 27px; font-weight: 700; }
QLabel#brand { color: #f4fffc; font-size: 21px; font-weight: 700; }
QLabel#sidecopy { color: #a9c1c1; font-size: 12px; }
QFrame#card { background: white; border: 1px solid #e3e8ee; border-radius: 14px; }
QFrame#hero { background: #e6f2ec; border: 1px solid #d2e6db; border-radius: 16px; }
QPushButton { background: white; border: 1px solid #dce3e9; border-radius: 8px; padding: 10px 15px; font-weight: 600; }
QPushButton:hover { background: #edf3f3; border-color: #a8bfc1; }
QPushButton:pressed { background: #dbe8e5; }
QPushButton:focus { border: 2px solid #298574; }
QPushButton:disabled { color: #9aa5ae; background: #edf0f3; border-color: #e4e8ed; }
QPushButton#primary { color: white; background: #207765; border: 1px solid #207765; }
QPushButton#primary:hover { background: #185e50; }
QPushButton#primary:disabled { background: #99b8ae; border-color: #99b8ae; }
QPushButton#nav { text-align: left; background: transparent; border: none; color: #bcd0cf; padding: 13px 16px; }
QPushButton#nav:checked { background: #2b474b; color: white; }
QPushButton#nav:hover { background: #223f44; }
QPushButton#danger { color: #ae4343; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTimeEdit, QDateTimeEdit {
 background: white; border: 1px solid #d7dfe7; border-radius: 7px; padding: 9px; selection-background-color: #207765; }
QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #207765; }
QCheckBox { spacing: 9px; padding: 5px 0; }
QCheckBox::indicator { width: 18px; height: 18px; }
QProgressBar { border: none; background: #edf1f4; border-radius: 4px; height: 7px; max-height: 7px; }
QProgressBar::chunk { background: #398f7a; border-radius: 4px; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { width: 9px; background: transparent; margin: 2px; }
QScrollBar::handle:vertical { background: #cad4dc; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def clean_rule(rule):
    return {key: copy.deepcopy(rule[key]) for key in FIELDS if key in rule}


def local_time(value):
    try:
        return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone().strftime('%d.%m. · %H:%M')
    except (ValueError, AttributeError):
        return '–'


def label(text, style=None, wrap=True):
    obj = QLabel(text)
    obj.setTextFormat(Qt.PlainText)
    obj.setWordWrap(wrap)
    if style:
        obj.setObjectName(style)
    return obj


def button(text, callback, primary=False):
    obj = QPushButton(text.replace('&', '&&'))
    obj.setCursor(Qt.PointingHandCursor)
    if primary:
        obj.setObjectName('primary')
    obj.clicked.connect(callback)
    return obj


def column(parent=None, margins=0, spacing=14):
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(margins, margins, margins, margins)
    layout.setSpacing(spacing)
    return layout


def card():
    obj = QFrame()
    obj.setObjectName('card')
    return obj, column(obj, 22)


def scroll(body):
    body.setObjectName('page')
    obj = QScrollArea()
    obj.setWidgetResizable(True)
    obj.setWidget(body)
    return obj


def badge(mark, color):
    obj = label(mark, wrap=False)
    obj.setAlignment(Qt.AlignCenter)
    obj.setFixedSize(46, 46)
    obj.setStyleSheet(f'background: {color}; color: white; border-radius: 12px; font-size: 18px; font-weight: 700;')
    return obj


def template_rule(template):
    name, _, _, _, kind, targets, minutes = template
    return dict(id=str(uuid.uuid4()), name=name, kind=kind, targets=list(targets),
                exceptions=[], enabled=False, daily_minutes=minutes, schedules=[],
                schedule_mode='blocked', timer_until=None, locked_until=None, device_action='lock')


def describe(rule):
    parts = []
    if rule.get('daily_minutes') is not None:
        parts.append(f"{rule['daily_minutes']:g} Minuten pro Tag. Danach wird gesperrt. Das Budget beginnt täglich um Mitternacht neu (Europe/Berlin).")
    if rule.get('schedules'):
        parts.append('In diesen Zeitfenstern gesperrt:' if rule['schedule_mode'] == 'blocked' else 'Nur in diesen Zeitfenstern erlaubt:')
        for s in rule['schedules']:
            parts.append(f"{', '.join(DAYS[d] for d in s['days'])} · {s['start']}–{s['end']}" + (' (ganzer Tag)' if s['start'] == s['end'] else ''))
    if rule.get('timer_until'):
        parts.append('Fokus-Timer bis ' + local_time(rule['timer_until']) + '.')
    if not parts:
        parts.append('Dauerhaft gesperrt, sobald du die Regel aktivierst.')
    if rule.get('daily_minutes') is not None and rule.get('schedules'):
        parts.append('Das Tagesbudget gilt zusätzlich zum Zeitplan.')
    return '\n'.join(parts)


def effect(rule):
    return {'web': 'Gilt browserübergreifend. Browser benötigen eine verbundene FokusWache-Erweiterung. Bei einer anhaltenden Verbindungsstörung pausiert ihr Netzwerk; Fenster und Tabs bleiben geöffnet.',
            'apps': 'Betroffene Programme werden bei einer Sperre beendet. Speichere deine Arbeit vorher.',
            'games': 'Erkannte Spiele von Steam, Ubisoft, EA, Epic und GOG teilen sich ein Budget. Bei einer Sperre werden die Spiele beendet.',
            'internet': 'Bei einer Sperre wird das gesamte Netzwerk für alle Programme blockiert.',
            'device': 'Bei einer Sperre: ' + {'lock': 'Bildschirm sperren.', 'logoff': 'Abmelden. Ungespeicherte Arbeit kann verloren gehen.', 'shutdown': 'Herunterfahren. Ungespeicherte Arbeit kann verloren gehen.'}[rule.get('device_action', 'lock')]}[rule['kind']]


class ScheduleRow(QFrame):
    def __init__(self, data, remove):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.days = []
        for i, day in enumerate(DAYS):
            b = QPushButton(day)
            b.setCheckable(True)
            b.setChecked(i in data['days'])
            b.setStyleSheet('QPushButton {padding: 8px 5px;} QPushButton:checked {background: #dcefe7; color: #175c4d; border-color: #8cb9a9;}')
            layout.addWidget(b)
            self.days.append(b)
        self.start, self.end = QTimeEdit(), QTimeEdit()
        for widget, key in ((self.start, 'start'), (self.end, 'end')):
            widget.setDisplayFormat('HH:mm')
            widget.setTime(QTime.fromString(data[key], 'HH:mm'))
            layout.addWidget(widget)
        delete = button('×', lambda: remove(self))
        delete.setAccessibleName('Zeitfenster entfernen')
        layout.addWidget(delete)

    def value(self):
        return dict(days=[i for i, b in enumerate(self.days) if b.isChecked()],
                    start=self.start.time().toString('HH:mm'), end=self.end.time().toString('HH:mm'))


class RuleEditor(QDialog):
    def __init__(self, app, rule=None, template=None):
        super().__init__(app)
        self.app = app
        self.existing = rule is not None
        self.rule = clean_rule(rule) if rule else template_rule(template or TEMPLATES[10])
        self.setWindowTitle('Regel bearbeiten' if rule else 'Neue Fokusregel')
        self.resize(790, 750)
        self.setMinimumSize(720, 550)
        self.setModal(True)
        outer = column(self, 26, 16)
        outer.addWidget(label('Deine Fokusregel', 'title'))
        self.steps = label('', 'muted')
        outer.addWidget(self.steps)
        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)
        self.error = label('')
        self.error.setStyleSheet('color: #ae4343;')
        outer.addWidget(self.error)
        footer = QHBoxLayout()
        self.back = button('Zurück', self.previous)
        self.cancel = button('Abbrechen', self.reject)
        self.draft = button('Als Entwurf speichern', lambda: self.save(False))
        self.next = button('Weiter', self.advance, True)
        for b in (self.cancel, self.back):
            footer.addWidget(b)
        footer.addStretch()
        footer.addWidget(self.draft)
        footer.addWidget(self.next)
        outer.addLayout(footer)
        self.build_targets()
        self.build_timing()
        review = QWidget()
        review_layout = column(review)
        box, layout = card()
        self.review_title = label('', 'heading')
        self.review_body = label('')
        self.review_effect = label('', 'muted')
        for obj in (self.review_title, self.review_body, self.review_effect):
            layout.addWidget(obj)
        review_layout.addWidget(box)
        review_layout.addWidget(label('Du kannst aktive Regeln später pausieren oder bearbeiten. Erst eine ausdrücklich gestartete Verriegelung verhindert Änderungen.', 'muted'))
        review_layout.addStretch()
        self.pages.addWidget(scroll(review))
        self.set_step(0)

    def build_targets(self):
        page = QWidget()
        layout = column(page, 1)
        layout.addWidget(label('Was möchtest du begrenzen?', 'heading'))
        layout.addWidget(label('Name der Regel', 'muted'))
        self.name = QLineEdit(self.rule['name'])
        self.name.setMaxLength(100)
        layout.addWidget(self.name)
        self.kind = QComboBox()
        for key, title in KINDS.items():
            self.kind.addItem(title, key)
        self.kind.setCurrentIndex(list(KINDS).index(self.rule['kind']))
        layout.addWidget(self.kind)
        self.target_box = QWidget()
        targets_layout = column(self.target_box)
        self.target_hint = label('', 'muted')
        targets_layout.addWidget(self.target_hint)
        self.targets = QPlainTextEdit('\n'.join(self.rule['targets']))
        self.targets.setMaximumHeight(115)
        targets_layout.addWidget(self.targets)
        self.picker = QWidget()
        picker_layout = QHBoxLayout(self.picker)
        picker_layout.setContentsMargins(0, 0, 0, 0)
        picker_layout.addWidget(button('Programm auswählen …', self.pick_file))
        picker_layout.addWidget(button('Ordner auswählen …', self.pick_folder))
        picker_layout.addStretch()
        targets_layout.addWidget(self.picker)
        targets_layout.addWidget(label('Ausnahmen · optional, ein Eintrag pro Zeile', 'muted'))
        self.exceptions = QPlainTextEdit('\n'.join(self.rule['exceptions']))
        self.exceptions.setMaximumHeight(80)
        targets_layout.addWidget(self.exceptions)
        layout.addWidget(self.target_box)
        self.action = QComboBox()
        for text, value in [('Bildschirm sperren', 'lock'), ('Abmelden', 'logoff'), ('Herunterfahren', 'shutdown')]:
            self.action.addItem(text, value)
        self.action.setCurrentIndex(['lock', 'logoff', 'shutdown'].index(self.rule.get('device_action', 'lock')))
        layout.addWidget(self.action)
        self.kind_info = label('', 'muted')
        layout.addWidget(self.kind_info)
        layout.addStretch()
        self.pages.addWidget(scroll(page))
        self.kind.currentIndexChanged.connect(self.kind_changed)
        self.kind_changed()

    def kind_changed(self):
        kind = self.kind.currentData()
        self.target_box.setVisible(kind in ('web', 'apps', 'games'))
        self.picker.setVisible(kind in ('apps', 'games'))
        self.action.setVisible(kind == 'device')
        self.target_hint.setText('Domains oder Domain/Pfad · ein Eintrag pro Zeile. Ausnahmen gelten für ganze Domains.' if kind == 'web' else 'Programme oder Ordner · ein Pfad pro Zeile.' if kind == 'apps' else 'Installierte Spiele werden automatisch erkannt. Weitere Spiele als EXE oder Spielordner hinzufügen; ausgenommene Spiele als Ordner eintragen.')
        self.targets.setPlaceholderText('youtube.com\ninstagram.com' if kind == 'web' else 'Programm oder Ordner auswählen …')
        self.kind_info.setText(effect(dict(kind=kind, device_action=self.action.currentData())))

    def pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Programm auswählen', '', 'Programme (*.exe)')
        if path:
            self.targets.appendPlainText(os.path.normpath(path))

    def pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Programmordner auswählen')
        if path:
            self.targets.appendPlainText(os.path.normpath(path))

    def build_timing(self):
        page = QWidget()
        layout = column(page, 1)
        layout.addWidget(label('Wie viel Zeit ist genug?', 'heading'))
        self.quota_enabled = QCheckBox('Tägliches Zeitbudget')
        self.quota_enabled.setChecked(self.rule.get('daily_minutes') is not None)
        layout.addWidget(self.quota_enabled)
        row = QHBoxLayout()
        self.minutes = QDoubleSpinBox()
        self.minutes.setRange(0.1, 1440)
        self.minutes.setDecimals(1)
        self.minutes.setSuffix(' min / Tag')
        self.minutes.setValue(self.rule.get('daily_minutes') or 30)
        row.addWidget(self.minutes)
        for n in (15, 30, 60, 120):
            row.addWidget(button(f'{n} min', lambda checked=False, n=n: self.minutes.setValue(n)))
        layout.addLayout(row)
        layout.addWidget(label('Gezählt wird die Nutzung im Vordergrund. Webseiten teilen sich ihr Budget über alle verbundenen Browser.', 'muted'))
        self.schedule_enabled = QCheckBox('Wiederkehrende Zeitfenster')
        self.schedule_enabled.setChecked(bool(self.rule['schedules']))
        layout.addWidget(self.schedule_enabled)
        self.schedule_box = QWidget()
        schedules = column(self.schedule_box)
        self.mode = QComboBox()
        self.mode.addItem('In diesen Zeitfenstern sperren', 'blocked')
        self.mode.addItem('Nur in diesen Zeitfenstern erlauben', 'allowed')
        self.mode.setCurrentIndex(0 if self.rule['schedule_mode'] == 'blocked' else 1)
        schedules.addWidget(self.mode)
        self.schedule_rows = []
        self.rows_layout = QVBoxLayout()
        schedules.addLayout(self.rows_layout)
        for s in self.rule['schedules'] or [dict(days=[0, 1, 2, 3, 4], start='09:00', end='17:00')]:
            self.add_schedule(s)
        schedules.addWidget(button('+ Zeitfenster hinzufügen', lambda: self.add_schedule()))
        schedules.addWidget(label('Zeitpläne verwenden Europe/Berlin. Fenster über Mitternacht sind möglich. Gleiche Start- und Endzeit bedeutet ganztägig.', 'muted'))
        layout.addWidget(self.schedule_box)
        self.timing_hint = label('', 'muted')
        layout.addWidget(self.timing_hint)
        layout.addStretch()
        self.pages.addWidget(scroll(page))
        self.quota_enabled.toggled.connect(self.timing_changed)
        self.schedule_enabled.toggled.connect(self.timing_changed)
        self.timing_changed()

    def add_schedule(self, data=None):
        row = ScheduleRow(data or dict(days=[0, 1, 2, 3, 4], start='09:00', end='17:00'), self.remove_schedule)
        self.schedule_rows.append(row)
        self.rows_layout.addWidget(row)

    def remove_schedule(self, row):
        self.schedule_rows.remove(row)
        row.deleteLater()

    def timing_changed(self):
        self.minutes.setEnabled(self.quota_enabled.isChecked())
        self.schedule_box.setVisible(self.schedule_enabled.isChecked())
        self.timing_hint.setText('Ohne Tagesbudget und Zeitfenster ist diese Regel eine Dauersperre.' if not self.quota_enabled.isChecked() and not self.schedule_enabled.isChecked() else 'Tagesbudget und Zeitplan können kombiniert werden. Eine erfüllte Sperrbedingung reicht aus.')

    def value(self, enabled=None):
        r = clean_rule(self.rule)
        kind = self.kind.currentData()
        r.update(name=self.name.text().strip(), kind=kind,
                 targets=[s.strip() for s in self.targets.toPlainText().splitlines() if s.strip()] if kind in ('web', 'apps', 'games') else [],
                 exceptions=[s.strip() for s in self.exceptions.toPlainText().splitlines() if s.strip()] if kind in ('web', 'apps', 'games') else [],
                 daily_minutes=self.minutes.value() if self.quota_enabled.isChecked() else None,
                 schedules=[s.value() for s in self.schedule_rows] if self.schedule_enabled.isChecked() else [],
                 schedule_mode=self.mode.currentData(), device_action=self.action.currentData())
        if self.schedule_enabled.isChecked() and not r['schedules']:
            raise ValueError('Füge mindestens ein Zeitfenster hinzu oder schalte Zeitfenster aus.')
        if enabled is not None:
            r['enabled'] = enabled
        return validate_rule(r)

    def set_step(self, index):
        self.pages.setCurrentIndex(index)
        self.steps.setText(['01  Ziele auswählen     /     02  Zeit festlegen     /     03  Prüfen & starten',
                            '01  Ziele ausgewählt     /     02  Zeit festlegen     /     03  Prüfen & starten',
                            '01  Ziele ausgewählt     /     02  Zeit festgelegt     /     03  Prüfen & starten'][index])
        self.back.setVisible(index > 0)
        self.draft.setVisible(index == 2 and not self.existing)
        self.next.setText(('Änderungen speichern' if self.existing else 'Regel aktivieren') if index == 2 else 'Weiter →')

    def previous(self):
        self.error.clear()
        self.set_step(self.pages.currentIndex() - 1)

    def advance(self):
        try:
            r = self.value()
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.error.clear()
        index = self.pages.currentIndex()
        if index == 2:
            self.save(self.rule['enabled'] if self.existing else True)
            return
        self.review_title.setText(r['name'])
        targets = '\n'.join(r['targets']) or KINDS[r['kind']]
        self.review_body.setText(targets + ('\n\nAusnahmen: ' + ', '.join(r['exceptions']) if r['exceptions'] else '') + '\n\n' + describe(r))
        self.review_effect.setText(effect(r))
        self.set_step(index + 1)

    def save(self, enabled):
        try:
            r = self.value(enabled)
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.next.setEnabled(False)
        self.draft.setEnabled(False)
        self.back.setEnabled(False)
        self.app.call({'op': 'save', 'rule': r}, self.saved, self.failed)

    def saved(self, result):
        self.app.notice.setText('Regel gespeichert. Deine Übersicht wird aktualisiert.')
        self.app.poll()
        self.accept()

    def failed(self, error):
        self.error.setText(str(error))
        self.next.setEnabled(True)
        self.draft.setEnabled(True)
        self.back.setEnabled(True)


class ReplyBus(QObject):
    completed = Signal(object, object, object)


class RuleCard(QFrame):
    def __init__(self, app, rule):
        super().__init__()
        self.setObjectName('card')
        self.app = app
        layout = column(self, 20, 11)
        top = QHBoxLayout()
        match = next((t for t in TEMPLATES if t[0] == rule['name']), None)
        top.addWidget(badge(match[2] if match else KINDS[rule['kind']][:1], match[3] if match else '#368375'))
        titles = QVBoxLayout()
        titles.setSpacing(3)
        titles.addWidget(label(rule['name'], 'heading'))
        titles.addWidget(label(KINDS[rule['kind']], 'muted'))
        top.addLayout(titles, 1)
        self.state = label('', wrap=False)
        top.addWidget(self.state)
        layout.addLayout(top)
        self.usage = label('')
        layout.addWidget(self.usage)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.detail = label('', 'muted')
        layout.addWidget(self.detail)
        actions = QHBoxLayout()
        self.toggle_button = button('', lambda: app.toggle(self.rule), True)
        self.manage_button = button('Details & Optionen', lambda: app.details(self.rule))
        actions.addWidget(self.toggle_button)
        actions.addWidget(self.manage_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.update_rule(rule)

    def update_rule(self, rule):
        self.rule = rule
        enabled, blocked = rule['enabled'], rule.get('blocked', False)
        self.state.setText('ENTWURF' if not enabled else 'GESPERRT' if blocked else 'AKTIV')
        self.state.setStyleSheet('font-size: 11px; font-weight: 700; color: ' + ('#987036' if blocked else '#237563' if enabled else '#758494') + ';')
        quota, used = rule.get('daily_minutes'), rule.get('used_seconds', 0)
        self.usage.setText((f'{max(0, quota - used / 60):.1f} min übrig   /   {quota:g} min pro Tag' if quota else 'Zeitplan aktiv' if rule['schedules'] else 'Dauersperre' if not rule.get('timer_until') else 'Fokus-Timer') if enabled else 'Pausiert · Keine Zeit wird gezählt')
        self.progress.setVisible(quota is not None)
        self.progress.setValue(min(1000, int(used / (quota * 60) * 1000)) if quota else 0)
        self.detail.setText('Verriegelt bis ' + local_time(rule.get('locked_until')) if rule.get('locked') else rule.get('reason', 'Bereit') if enabled else 'Aktivieren, sobald du bereit bist.')
        self.toggle_button.setText('Pausieren' if enabled else 'Aktivieren')
        self.toggle_button.setEnabled(self.app.connected and not self.app.pending and not rule.get('locked'))


class Application(QMainWindow):
    def __init__(self, auto_poll=True):
        super().__init__()
        self.setWindowTitle('FokusWache')
        self.resize(1140, 800)
        self.setMinimumSize(900, 580)
        self.connected = False
        self.pending = False
        self.polling = False
        self.status = {}
        self.cards = {}
        self.signature = None
        self.bus = ReplyBus(self)
        self.bus.completed.connect(lambda callback, result, _: callback(result))
        root = QWidget()
        self.setCentralWidget(root)
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(216)
        side = column(sidebar, 22, 12)
        side.addWidget(label('FokusWache', 'brand'))
        side.addWidget(label('Raum für das Wesentliche.', 'sidecopy'))
        side.addSpacing(35)
        self.nav = []
        for i, title in enumerate(('Meine Regeln', 'Vorlagen', 'Browser & Schutz', 'Tagebuch')):
            b = button(title, lambda checked=False, i=i: self.navigate(i))
            b.setObjectName('nav')
            b.setCheckable(True)
            side.addWidget(b)
            self.nav.append(b)
        side.addStretch()
        self.health = label('Verbindung wird hergestellt …', 'sidecopy')
        side.addWidget(self.health)
        side.addWidget(label('Lokal auf deinem Computer', 'sidecopy'))
        row.addWidget(sidebar)
        content = QWidget()
        content.setObjectName('page')
        content_layout = column(content, 30, 18)
        self.pages = QStackedWidget()
        content_layout.addWidget(self.pages, 1)
        self.notice = label('Deine Regeln und Zeitbudgets werden geladen.', 'muted')
        content_layout.addWidget(self.notice)
        row.addWidget(content, 1)
        self.build_overview()
        self.build_templates()
        self.build_protection()
        self.journal_page = JournalPage(self)
        self.pages.addWidget(self.journal_page)
        self.navigate(0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        if auto_poll:
            self.timer.start(2000)
            self.poll()

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        self.notice.setVisible(index != 3)
        if index == 3:
            self.journal_page.refresh()
        for i, b in enumerate(self.nav):
            b.setChecked(index == i)

    def build_overview(self):
        page = QWidget()
        layout = column(page)
        top = QHBoxLayout()
        top.addWidget(label('Dein Fokus. Deine Regeln.', 'title'), 1)
        self.new_button = button('+ Neue Regel', lambda: self.navigate(1), True)
        top.addWidget(self.new_button)
        layout.addLayout(top)
        layout.addWidget(label('Bewusst entscheiden, wie du deine Zeit verbringst.', 'muted'))
        hero = QFrame()
        hero.setObjectName('hero')
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(22, 20, 22, 20)
        self.metrics = []
        for caption in ('Aktive Regeln', 'Gerade gesperrt', 'Entwürfe & Pausen'):
            metric = QVBoxLayout()
            value = label('–', 'metric')
            metric.addWidget(value)
            metric.addWidget(label(caption, 'muted'))
            hero_layout.addLayout(metric, 1)
            self.metrics.append(value)
        layout.addWidget(hero)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Regeln durchsuchen …')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_cards)
        self.filter = QComboBox()
        self.filter.addItems(['Alle Regeln', 'Aktiv', 'Pausiert'])
        self.filter.currentIndexChanged.connect(self.filter_cards)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.filter)
        layout.addLayout(filters)
        rules_body = QWidget()
        self.rules_layout = column(rules_body, 1, 14)
        self.empty = label('Noch keine Regeln. Wähle eine Vorlage und starte mit einem passenden Zeitbudget.', 'muted')
        self.rules_layout.addWidget(self.empty)
        self.rules_layout.addStretch()
        layout.addWidget(scroll(rules_body), 1)
        self.pages.addWidget(page)

    def build_templates(self):
        page = QWidget()
        layout = column(page)
        layout.addWidget(label('Womit möchtest du anfangen?', 'title'))
        layout.addWidget(label('Wähle eine Vorlage. Ziele und Zeitbudget kannst du im nächsten Schritt anpassen.', 'muted'))
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(1, 1, 1, 1)
        grid.setSpacing(14)
        self.template_buttons = []
        for i, t in enumerate(TEMPLATES):
            box, cells = card()
            top = QHBoxLayout()
            top.addWidget(badge(t[2], t[3]))
            top.addWidget(label(t[0], 'heading'), 1)
            cells.addLayout(top)
            cells.addWidget(label(t[1], 'muted'))
            b = button('Vorlage verwenden →', lambda checked=False, t=t: self.editor(template=t))
            cells.addWidget(b)
            self.template_buttons.append(b)
            grid.addWidget(box, i // 2, i % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addWidget(scroll(body), 1)
        self.pages.addWidget(page)

    def build_protection(self):
        page = QWidget()
        layout = column(page)
        layout.addWidget(label('Browser & Schutz', 'title'))
        layout.addWidget(label('Damit deine Regeln überall greifen.', 'muted'))
        body = QWidget()
        cells = column(body, 1)
        box, info = card()
        info.addWidget(label('Browser verbinden', 'heading'))
        info.addWidget(label('Für Webseiten-Regeln benötigt jeder verwendete Browser die FokusWache-Erweiterung. Das Zeitbudget gilt gemeinsam für alle Browser.'))
        info.addWidget(label('Chrome, Edge, Brave und Comet: Entwicklermodus in der Erweiterungsverwaltung einschalten und den Ordner „chromium“ als entpackte Erweiterung laden. Firefox: Die enthaltene Test-Erweiterung gilt nur bis zum Browser-Neustart.', 'muted'))
        info.addWidget(button('Erweiterungsordner öffnen', self.open_extensions))
        cells.addWidget(box)
        self.browser_status = label('Noch keine Statusmeldung.', 'muted')
        box, info = card()
        info.addWidget(label('Aktueller Status', 'heading'))
        info.addWidget(self.browser_status)
        cells.addWidget(box)
        self.events = QPlainTextEdit()
        self.events.setReadOnly(True)
        self.events.setMinimumHeight(180)
        cells.addWidget(label('Letzte Ereignisse', 'heading'))
        cells.addWidget(self.events)
        layout.addWidget(scroll(body), 1)
        self.pages.addWidget(page)

    def call(self, payload, success, failure):
        def work():
            try:
                result = request(payload)
                self.bus.completed.emit(success, result, None)
            except Exception as exc:
                self.bus.completed.emit(failure, str(exc), None)
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        if not self.polling:
            self.polling = True
            self.call({'op': 'status'}, self.render, self.disconnected)

    def disconnected(self, error):
        self.polling = False
        self.connected = False
        self.health.setText('● Dienst nicht erreichbar')
        self.notice.setText('Verbindung unterbrochen. Die angezeigten Daten können veraltet sein. Neuer Versuch läuft automatisch.')
        self.controls()

    def controls(self):
        for b in self.template_buttons:
            b.setEnabled(self.connected and not self.pending)
        for obj in self.cards.values():
            obj.update_rule(obj.rule)

    def render(self, status):
        self.polling = False
        was_connected = self.connected
        self.connected = True
        previous_errors = self.status.get('errors')
        self.status = status
        self.health.setText('● Schutz prüfen' if status.get('errors') else '● Dienst verbunden')
        if status.get('errors'):
            self.notice.setText(status['errors'][0])
        elif not was_connected or previous_errors:
            self.notice.setText('Zeitbudgets gelten täglich · Deine Daten bleiben auf diesem Computer.')
        rules = status.get('rules', [])
        signature = [(r['id'], r['name'], r['kind']) for r in rules]
        if signature != self.signature:
            for obj in self.cards.values():
                self.rules_layout.removeWidget(obj)
                obj.deleteLater()
            self.cards = {}
            for r in rules:
                obj = RuleCard(self, r)
                self.cards[r['id']] = obj
                self.rules_layout.insertWidget(self.rules_layout.count() - 1, obj)
            self.signature = signature
        for r in rules:
            self.cards[r['id']].update_rule(r)
        for obj, n in zip(self.metrics, (sum(r['enabled'] for r in rules), sum(r['enabled'] and r.get('blocked', False) for r in rules), sum(not r['enabled'] for r in rules))):
            obj.setText(str(n))
        self.filter_cards()
        lines = [f"{b['name']} · " + ('Netzwerk pausiert' if b.get('network_blocked') else 'Verbunden' if b.get('connected') else 'Verbindung wird geprüft') + ('\n' + b['connection_reason'] if b.get('connection_reason') else '') for b in status.get('browsers', [])]
        lines = lines or ['Aktuell kein Browser gemeldet.']
        lines += ['\n' + e for e in status.get('errors', [])]
        games = status.get('games', [])
        lines += [f'\n{len(games)} Spiele erkannt.']
        lines += [g['name'] + ' · ' + g['launcher'] for g in games]
        self.browser_status.setText('\n'.join(lines))
        events = '\n'.join(f"{local_time(e.get('time'))}   {e.get('message', '')}" for e in reversed(status.get('events', [])))
        if self.events.toPlainText() != events:
            self.events.setPlainText(events)
        self.controls()

    def filter_cards(self):
        visible = 0
        for obj in self.cards.values():
            r = obj.rule
            match = self.search.text().casefold() in r['name'].casefold() and (self.filter.currentIndex() == 0 or r['enabled'] == (self.filter.currentIndex() == 1))
            obj.setVisible(match)
            visible += match
        self.empty.setVisible(visible == 0)
        self.empty.setText('Keine passenden Regeln gefunden.' if self.cards else 'Noch keine Regeln. Wähle „Neue Regel“ und starte mit einer passenden Vorlage.')

    def editor(self, rule=None, template=None):
        if self.connected and not self.pending and not (rule and rule.get('locked')):
            RuleEditor(self, rule, template).exec()

    def mutate(self, payload):
        if self.pending or not self.connected:
            return
        self.pending = True
        self.notice.setText('Änderung wird übernommen …')
        self.controls()
        self.call(payload, self.done, self.failed)

    def done(self, result):
        self.pending = False
        self.notice.setText('Änderung übernommen.')
        self.poll()
        self.controls()

    def failed(self, error):
        self.pending = False
        self.notice.setText(str(error))
        self.controls()

    def confirm(self, title, text):
        return QMessageBox.question(self, title, text, QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Yes

    def toggle(self, rule):
        r = clean_rule(rule)
        r['enabled'] = not r['enabled']
        if r['enabled'] and not self.confirm('Regel aktivieren', r['name'] + '\n\n' + describe(r) + '\n\n' + effect(r)):
            return
        self.mutate({'op': 'save', 'rule': r})

    def details(self, rule):
        dialog = QDialog(self)
        dialog.setWindowTitle(rule['name'])
        dialog.resize(640, 640)
        outer = column(dialog, 26)
        outer.addWidget(label(rule['name'], 'title'))
        body = QWidget()
        layout = column(body)
        layout.addWidget(label(describe(rule)))
        layout.addWidget(label(effect(rule), 'muted'))
        if rule['targets']:
            layout.addWidget(label('Ziele\n' + '\n'.join(rule['targets']), 'muted'))
        if rule['exceptions']:
            layout.addWidget(label('Ausnahmen\n' + '\n'.join(rule['exceptions']), 'muted'))
        if rule.get('locked'):
            layout.addWidget(label('Verriegelt bis ' + local_time(rule['locked_until']) + '. Änderungen sind bis dahin gesperrt.'))
        else:
            edit = button('Regel bearbeiten', lambda: (dialog.accept(), self.editor(rule)))
            edit.setEnabled(self.connected and not self.pending)
            layout.addWidget(edit)
            layout.addWidget(label('Verbindlich fokussieren', 'heading'))
            layout.addWidget(label('Fokus-Timer sperrt sofort. Verriegeln schützt die bestehende Regel vor Änderungen. Beides kann bis zum Ablauf nicht abgebrochen werden.', 'muted'))
            minutes = QSpinBox()
            minutes.setRange(1, 10080)
            minutes.setValue(25)
            minutes.setSuffix(' Minuten')
            layout.addWidget(minutes)
            for title, op in [('Jetzt sperren & Timer starten', 'timer'), ('Regel für diese Dauer verriegeln', 'lock')]:
                b = button(title, lambda checked=False, op=op: self.commit_time(dialog, rule, op, minutes.value()))
                b.setEnabled(self.connected and not self.pending and (op == 'timer' or rule['enabled']))
                layout.addWidget(b)
            delete = button('Regel löschen', lambda: self.delete_rule(dialog, rule))
            delete.setObjectName('danger')
            delete.setEnabled(self.connected and not self.pending)
            layout.addWidget(delete)
        layout.addStretch()
        outer.addWidget(scroll(body), 1)
        outer.addWidget(button('Schließen', dialog.accept))
        dialog.exec()

    def commit_time(self, dialog, rule, op, minutes):
        text = f"„{rule['name']}“ für {minutes} Minuten " + ('sofort sperren und verriegeln?' if op == 'timer' else 'gegen Änderungen verriegeln?')
        if not self.confirm('Verbindlich starten', text + '\n\nBis zum Ablauf sind Ändern, Pausieren und Löschen gesperrt.' + ('\n\n' + effect(rule) if op == 'timer' else '')):
            return
        payload = dict(op=op, id=rule['id'])
        payload.update(minutes=minutes) if op == 'timer' else payload.update(until=(dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)).isoformat())
        dialog.accept()
        self.mutate(payload)

    def delete_rule(self, dialog, rule):
        if self.confirm('Regel löschen', f"„{rule['name']}“ dauerhaft löschen?"):
            dialog.accept()
            self.mutate({'op': 'delete', 'id': rule['id']})

    def open_extensions(self):
        path = self.status.get('extension_path')
        if path:
            try:
                os.startfile(path)
            except OSError as exc:
                self.notice.setText(str(exc))
        else:
            self.notice.setText('Der Erweiterungsordner ist erst bei verbundenem Dienst verfügbar.')


def run_ui():
    app = QApplication.instance() or QApplication([])
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    app.setWindowIcon(QIcon(str(Path(__file__).with_name('FokusWache.ico'))))
    window = Application()
    window.show()
    app.exec()


if __name__ == '__main__':
    run_ui()
