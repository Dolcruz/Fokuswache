import datetime as dt
import sqlite3
from collections import Counter

from PySide6.QtCore import Qt, QDate, QDateTime, QLocale, QTimeZone, Signal
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCalendarWidget, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QComboBox, QDialog, QFormLayout, QDateTimeEdit, QDateEdit, QPlainTextEdit,
    QDialogButtonBox, QMessageBox, QTabWidget, QCheckBox, QFrame, QScrollArea)
from journal import Journal, ZONE, day_start, duration_text

STYLE = '''
QWidget#diary { background: transparent; }
QFrame#capture { background: #eaf3ee; border: 1px solid #d5e5da; border-radius: 16px; }
QFrame#entry { background: #ffffff; border: 1px solid #e2e8e4; border-radius: 12px; }
QLabel#entryTitle { color: #21392f; font-size: 16px; font-weight: 600; }
QLabel#eyebrow { color: #456b58; font-size: 11px; font-weight: 700; }
QPlainTextEdit#quick { border: none; background: transparent; font-size: 17px; padding: 0; }
QPushButton#quiet { background: transparent; border: 1px solid transparent; color: #597066; padding: 8px 10px; }
QPushButton#quiet:hover { background: #eaf2ed; border-color: #d5e5da; }
QPushButton#quiet:focus { border-color: #207765; }
QPushButton#quiet:pressed { background: #dbe9e0; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: #65796e; padding: 10px 16px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #1c644d; border-bottom: 2px solid #207765; font-weight: 600; }
QTabBar::tab:hover { background: #e9f0eb; }
QCalendarWidget { background: #ffffff; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background: #eaf2ed; }
QCalendarWidget QToolButton { color: #254c39; background: transparent; padding: 7px; border: none; font-weight: 600; }
QCalendarWidget QToolButton:hover { background: #d9e8df; }
QCalendarWidget QAbstractItemView { background: #ffffff; alternate-background-color: #f5f8f5; selection-background-color: #207765; selection-color: white; outline: none; }
QTableWidget { background: white; alternate-background-color: #f5f8f6; border: 1px solid #e0e7e2; gridline-color: #edf1ee; selection-background-color: #e4efe8; selection-color: #19392b; }
QHeaderView::section { background: #edf3ef; color: #435e50; border: none; padding: 9px; font-weight: 600; }
QDateEdit { background: white; border: 1px solid #d7dfe7; border-radius: 7px; padding: 9px; }
'''


def text(value, role=None):
    widget = QLabel(value)
    widget.setTextFormat(Qt.PlainText)
    widget.setWordWrap(True)
    if role:
        widget.setObjectName(role)
    return widget


def button(caption, callback, role=None):
    widget = QPushButton(caption)
    widget.setCursor(Qt.PointingHandCursor)
    widget.setMinimumHeight(40)
    if role:
        widget.setObjectName(role)
    widget.clicked.connect(callback)
    return widget


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    widget.verticalHeader().hide()
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SingleSelection)
    widget.setAlternatingRowColors(True)
    widget.setShowGrid(False)
    return widget


class QuickCapture(QPlainTextEdit):
    submitted = Signal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
            self.submitted.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class EntryEditor(QDialog):
    def __init__(self, journal, day, parent=None, entry=None, draft=''):
        super().__init__(parent)
        self.journal = journal
        self.entry = entry
        self.setWindowTitle('Eintrag bearbeiten' if entry else 'Moment festhalten')
        self.resize(540, 500)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(text('Was möchtest du festhalten?', 'heading'))
        self.activity = QPlainTextEdit(entry['activity'] if entry else draft)
        self.activity.setAccessibleName('Eintrag')
        self.activity.setPlaceholderText('Zum Beispiel: Bett aufgebaut. Endlich fertig!')
        self.activity.setMinimumHeight(90)
        layout.addWidget(self.activity)
        self.day = QDateEdit(QDate.fromString(entry['day'], Qt.ISODate) if entry else QDate(day.year, day.month, day.day))
        self.day.setCalendarPopup(True)
        self.day.setDisplayFormat('dd. MMMM yyyy')
        self.day.setLocale(QLocale(QLocale.German, QLocale.Germany))
        self.day.setAccessibleName('Tag')
        form = QFormLayout()
        form.addRow('An welchem Tag?', self.day)
        layout.addLayout(form)
        self.with_time = QCheckBox('Uhrzeit ergänzen')
        self.with_time.setChecked(entry is not None and entry['start'] is not None)
        layout.addWidget(self.with_time)
        self.time_fields = QWidget()
        time_form = QFormLayout(self.time_fields)
        time_form.setContentsMargins(0, 0, 0, 0)
        self.start = QDateTimeEdit()
        self.end = QDateTimeEdit()
        for edit, name in [(self.start, 'Beginn'), (self.end, 'Ende')]:
            edit.setCalendarPopup(True)
            edit.setDisplayFormat('dd.MM.yyyy HH:mm')
            edit.setAccessibleName(name)
        begin = dt.datetime.combine(day, dt.time(18), ZONE)
        if day == dt.datetime.now(ZONE).date():
            begin = dt.datetime.now(ZONE).replace(second=0, microsecond=0) - dt.timedelta(hours=1)
        zone = QTimeZone(b'Europe/Berlin')
        start = entry['start'] if entry and entry['start'] is not None else int(begin.timestamp())
        end = entry['end'] if entry and entry['end'] is not None else start + 3600
        self.start.setDateTime(QDateTime.fromSecsSinceEpoch(start, zone))
        self.end.setDateTime(QDateTime.fromSecsSinceEpoch(end, zone))
        time_form.addRow('Beginn', self.start)
        time_form.addRow('Ende', self.end)
        self.duration = text('', 'muted')
        time_form.addRow(self.duration)
        layout.addWidget(self.time_fields)
        layout.addWidget(text('Mehr dazu (optional)', 'muted'))
        self.note = QPlainTextEdit(entry['note'] if entry else '')
        self.note.setAccessibleName('Notiz')
        self.note.setPlaceholderText('Ein Gedanke, ein Detail, eine Erinnerung …')
        layout.addWidget(self.note)
        self.error = text('')
        self.error.setStyleSheet('color:#a53030')
        layout.addWidget(self.error)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText('Speichern')
        self.buttons.button(QDialogButtonBox.Save).setObjectName('primary')
        self.buttons.button(QDialogButtonBox.Cancel).setText('Abbrechen')
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.with_time.toggled.connect(self.toggle_time)
        self.day.dateChanged.connect(self.change_day)
        self.start.dateTimeChanged.connect(self.update_duration)
        self.start.dateTimeChanged.connect(lambda value: self.day.setDate(value.date()) if self.with_time.isChecked() else None)
        self.end.dateTimeChanged.connect(self.update_duration)
        self.toggle_time(self.with_time.isChecked())
        self.update_duration()

    def toggle_time(self, enabled):
        self.time_fields.setVisible(enabled)
        self.day.setEnabled(not enabled)
        if enabled:
            self.day.setDate(self.start.date())

    def change_day(self, date):
        if not self.with_time.isChecked():
            offset = self.start.date().daysTo(date)
            self.start.setDateTime(self.start.dateTime().addDays(offset))
            self.end.setDateTime(self.end.dateTime().addDays(offset))

    def update_duration(self):
        seconds = self.start.dateTime().secsTo(self.end.dateTime())
        self.duration.setText('Dauer: ' + duration_text(seconds) if seconds > 0 else 'Bitte Ende nach Beginn wählen.')

    def save(self):
        timed = self.with_time.isChecked()
        try:
            self.journal.save(self.activity.toPlainText(),
                self.start.dateTime().toSecsSinceEpoch() if timed else None,
                self.end.dateTime().toSecsSinceEpoch() if timed else None,
                self.note.toPlainText(), self.entry['id'] if self.entry else None,
                day=self.day.date().toPython())
        except (ValueError, sqlite3.Error) as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class JournalPage(QWidget):
    def __init__(self, parent=None, path=None):
        super().__init__(parent)
        self.setObjectName('diary')
        self.setStyleSheet(STYLE)
        self.journal = None
        self.rows = []
        self.cards = []
        self.marked = []
        self.draft_day = None
        self.drafts = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(text('Dein Tag, festgehalten.', 'title'))
        layout.addWidget(text('Kleine Dinge. Gute Momente. Alles, was zu deinem Tag gehört.', 'muted'))
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        calendar_page = QWidget()
        calendar_layout = QHBoxLayout(calendar_page)
        calendar_layout.setContentsMargins(0, 16, 0, 0)
        calendar_layout.setSpacing(20)
        self.calendar = QCalendarWidget()
        self.calendar.setLocale(QLocale(QLocale.German, QLocale.Germany))
        self.calendar.setFirstDayOfWeek(Qt.Monday)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.setGridVisible(False)
        self.calendar.setMinimumWidth(260)
        self.calendar.setSelectedDate(QDate.currentDate())
        self.calendar.selectionChanged.connect(self.refresh_day)
        self.calendar.currentPageChanged.connect(self.month_changed)
        self.calendar.activated.connect(lambda _: self.quick.setFocus())
        left = QWidget()
        left.setFixedWidth(274)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(16)
        left_layout.addWidget(self.calendar)
        self.month_total = text('', 'heading')
        left_layout.addWidget(self.month_total)
        self.month_caption = text('', 'muted')
        left_layout.addWidget(self.month_caption)
        left_layout.addStretch()
        self.message = text('Nur für dich. Auf diesem Computer gespeichert.', 'muted')
        left_layout.addWidget(self.message)
        calendar_layout.addWidget(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        day_bar = QHBoxLayout()
        self.day_title = text('', 'heading')
        day_bar.addWidget(self.day_title, 1)
        self.today_button = button('Heute', lambda: self.calendar.setSelectedDate(QDate.currentDate()), 'quiet')
        day_bar.addWidget(self.today_button)
        right_layout.addLayout(day_bar)
        capture = QFrame()
        capture.setObjectName('capture')
        capture_layout = QVBoxLayout(capture)
        capture_layout.setContentsMargins(16, 14, 16, 12)
        capture_layout.setSpacing(8)
        self.capture_label = text('WAS HAST DU HEUTE GEMACHT?', 'eyebrow')
        capture_layout.addWidget(self.capture_label)
        self.quick = QuickCapture()
        self.quick.setObjectName('quick')
        self.quick.setAccessibleName('Was hast du gemacht?')
        self.quick.setPlaceholderText('Gesaugt, Bett aufgebaut, draußen gewesen …')
        self.quick.setFixedHeight(74)
        self.quick.submitted.connect(self.quick_save)
        self.quick.textChanged.connect(self.update_save_button)
        capture_layout.addWidget(self.quick)
        capture_actions = QHBoxLayout()
        self.details_button = button('+ Details', self.add, 'quiet')
        self.details_button.setAccessibleName('Datum, Uhrzeit und Notiz ergänzen')
        capture_actions.addWidget(self.details_button)
        capture_actions.addStretch()
        self.save_button = button('Festhalten', self.quick_save, 'primary')
        capture_actions.addWidget(self.save_button)
        capture_layout.addLayout(capture_actions)
        self.feedback = text('Enter zum Speichern · Umschalt+Enter für eine neue Zeile', 'muted')
        capture_layout.addWidget(self.feedback)
        right_layout.addWidget(capture)
        self.day_total = text('', 'muted')
        right_layout.addWidget(self.day_total)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAccessibleName('Einträge dieses Tages')
        right_layout.addWidget(self.scroll, 1)
        calendar_layout.addWidget(right, 1)
        self.tabs.addTab(calendar_page, 'Tagebuch')
        self.build_stats()
        try:
            self.journal = Journal(path)
            self.refresh()
        except (sqlite3.Error, OSError) as exc:
            self.message.setText('Tagebuch konnte nicht geöffnet werden: ' + str(exc))
            self.tabs.setEnabled(False)
        self.update_save_button()

    def build_stats(self):
        stats = QWidget()
        layout = QVBoxLayout(stats)
        layout.setContentsMargins(0, 16, 0, 0)
        bar = QHBoxLayout()
        self.period = QComboBox()
        self.period.addItems(['Monat', 'Jahr'])
        self.period.currentIndexChanged.connect(self.refresh_stats)
        prev = button('←', lambda: self.shift(-1))
        prev.setAccessibleName('Vorheriger Zeitraum')
        nxt = button('→', lambda: self.shift(1))
        nxt.setAccessibleName('Nächster Zeitraum')
        self.period_title = text('', 'heading')
        bar.addWidget(self.period)
        bar.addWidget(prev)
        bar.addWidget(self.period_title, 1)
        bar.addWidget(nxt)
        layout.addLayout(bar)
        self.stats_total = text('')
        layout.addWidget(self.stats_total)
        self.categories = table(['Aktivität', 'Zeit', 'Anteil'])
        self.categories.setAccessibleName('Zeit nach Aktivität')
        self.trend = table(['Zeitraum', 'Erfasste Zeit', 'Einträge'])
        self.trend.setAccessibleName('Verlauf')
        layout.addWidget(self.categories, 1)
        layout.addWidget(text('Dein Rückblick', 'heading'))
        layout.addWidget(self.trend, 1)
        layout.addWidget(text('Einträge ohne Uhrzeit zählen als Erinnerungen. Nur eingetragene Zeiträume fließen in die Stunden und Anteile ein.', 'muted'))
        self.tabs.addTab(stats, 'Rückblick')

    def selected_day(self):
        return self.calendar.selectedDate().toPython()

    def month_range(self):
        first = dt.date(self.calendar.yearShown(), self.calendar.monthShown(), 1)
        return first, dt.date(first.year + (first.month == 12), first.month % 12 + 1, 1)

    def update_save_button(self):
        self.save_button.setEnabled(self.journal is not None and bool(self.quick.toPlainText().strip()))

    def quick_save(self):
        if not self.journal or not self.quick.toPlainText().strip():
            return
        try:
            self.journal.save(self.quick.toPlainText(), day=self.selected_day())
        except (ValueError, sqlite3.Error) as exc:
            self.feedback.setStyleSheet('color:#a53030')
            self.feedback.setText(str(exc))
            return
        self.quick.clear()
        self.drafts.pop(self.selected_day(), None)
        self.refresh()
        self.feedback.setStyleSheet('color:#287554')
        self.feedback.setText('✓ Festgehalten. Noch etwas von diesem Tag?')
        self.quick.setFocus()

    def refresh(self):
        if not self.journal:
            return
        try:
            first, last = self.month_range()
            for day in self.marked:
                self.calendar.setDateTextFormat(QDate(day.year, day.month, day.day), QTextCharFormat())
            counts = self.journal.day_counts(first, last)
            self.marked = list(counts)
            for day, count in counts.items():
                fmt = QTextCharFormat()
                fmt.setBackground(QColor('#d8eee5'))
                fmt.setForeground(QColor('#154c3d'))
                fmt.setFontWeight(700)
                fmt.setToolTip(f'{count} Einträge')
                self.calendar.setDateTextFormat(QDate(day.year, day.month, day.day), fmt)
            entries = self.journal.entries(day_start(first), day_start(last))
            self.month_total.setText(f'{len(entries)} ' + ('festgehaltene Momente' if len(entries) != 1 else 'festgehaltener Moment'))
            self.month_caption.setText(f'An {len(counts)} ' + ('Tagen' if len(counts) != 1 else 'Tag') + ' in diesem Monat.\nAuch kleine Dinge zählen.')
            self.refresh_day()
            self.refresh_stats()
        except sqlite3.Error as exc:
            self.message.setText('Daten konnten nicht geladen werden: ' + str(exc))

    def month_changed(self, *_):
        self.refresh()

    def refresh_day(self):
        if not self.journal:
            return
        day = self.selected_day()
        if self.draft_day != day:
            if self.draft_day is not None:
                self.drafts[self.draft_day] = self.quick.toPlainText()
            self.draft_day = day
            self.quick.setPlainText(self.drafts.get(day, ''))
            self.feedback.setText('Enter zum Speichern · Umschalt+Enter für eine neue Zeile')
            self.feedback.setStyleSheet('')
        start, end = day_start(day), day_start(day + dt.timedelta(days=1))
        self.rows = self.journal.entries(start, end)
        today = day == dt.datetime.now(ZONE).date()
        caption = self.calendar.locale().toString(self.calendar.selectedDate(), 'd. MMMM')
        self.day_title.setText(('Heute' if today else self.calendar.locale().toString(self.calendar.selectedDate(), 'dddd')) + ' · ' + caption)
        self.capture_label.setText('WAS HAST DU HEUTE GEMACHT?' if today else 'WAS MÖCHTEST DU VON DIESEM TAG FESTHALTEN?')
        self.today_button.setVisible(not today)
        total = sum(min(r['end'], end) - max(r['start'], start) for r in self.rows if r['start'] is not None)
        self.day_total.setText((f'{len(self.rows)} ' + ('Einträge' if len(self.rows) != 1 else 'Eintrag') +
            (' · ' + duration_text(total) + ' mit Uhrzeit' if total else '')) if self.rows else 'Dein Tag muss nicht spektakulär sein, um ihn festzuhalten.')
        content = QWidget()
        cards_layout = QVBoxLayout(content)
        cards_layout.setContentsMargins(0, 0, 2, 0)
        cards_layout.setSpacing(10)
        self.cards = []
        for entry in reversed(self.rows):
            card = QFrame()
            card.setObjectName('entry')
            card.entry_id = entry['id']
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 12, 16, 12)
            card_layout.setSpacing(6)
            bar = QHBoxLayout()
            if entry['start'] is None:
                period = 'Von diesem Tag'
            else:
                begin = dt.datetime.fromtimestamp(entry['start'], ZONE)
                finish = dt.datetime.fromtimestamp(entry['end'], ZONE)
                fmt = '%H:%M' if begin.date() == finish.date() else '%d.%m. %H:%M'
                seconds = min(entry['end'], end) - max(entry['start'], start)
                period = begin.strftime(fmt) + ' – ' + finish.strftime(fmt) + ' · ' + duration_text(seconds)
            bar.addWidget(text(period, 'muted'), 1)
            card.edit_button = button('Bearbeiten', lambda checked=False, e=entry: self.edit(e), 'quiet')
            card.delete_button = button('Löschen', lambda checked=False, e=entry: self.delete(e), 'quiet')
            bar.addWidget(card.edit_button)
            bar.addWidget(card.delete_button)
            card_layout.addLayout(bar)
            title = text(entry['activity'], 'entryTitle')
            title.setTextInteractionFlags(Qt.TextSelectableByMouse)
            card_layout.addWidget(title)
            if entry['note']:
                card_layout.addWidget(text(entry['note'], 'muted'))
            cards_layout.addWidget(card)
            self.cards.append(card)
        if not self.rows:
            empty = QFrame()
            empty.setObjectName('entry')
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(20, 24, 20, 24)
            empty_layout.addWidget(text('Platz für deinen Tag.', 'heading'))
            empty_layout.addWidget(text('Ein Satz reicht. Was hast du erledigt, ausprobiert oder genossen?', 'muted'))
            cards_layout.addWidget(empty)
        cards_layout.addStretch()
        old = self.scroll.takeWidget()
        self.scroll.setWidget(content)
        if old:
            old.deleteLater()

    def add(self):
        if not self.journal:
            return
        if EntryEditor(self.journal, self.selected_day(), self, draft=self.quick.toPlainText()).exec():
            self.quick.clear()
            self.drafts.pop(self.selected_day(), None)
            self.refresh()
            self.feedback.setText('✓ Festgehalten.')

    def edit(self, entry):
        if EntryEditor(self.journal, self.selected_day(), self, entry).exec():
            self.refresh()

    def delete(self, entry):
        dialog = QMessageBox(QMessageBox.Question, 'Eintrag löschen',
                             'Diesen Eintrag dauerhaft löschen?', parent=self)
        confirm = dialog.addButton('Löschen', QMessageBox.DestructiveRole)
        cancel = dialog.addButton('Behalten', QMessageBox.RejectRole)
        dialog.setDefaultButton(cancel)
        dialog.exec()
        if dialog.clickedButton() is confirm:
            try:
                self.journal.delete(entry['id'])
                self.refresh()
            except sqlite3.Error as exc:
                self.message.setText(str(exc))

    def shift(self, amount):
        day = QDate(self.calendar.yearShown(), self.calendar.monthShown(), 1)
        day = day.addYears(amount) if self.period.currentIndex() else day.addMonths(amount)
        self.calendar.setCurrentPage(day.year(), day.month())

    def refresh_stats(self):
        if not self.journal:
            return
        first, last = self.month_range()
        year = self.period.currentIndex() == 1
        if year:
            first, last = dt.date(first.year, 1, 1), dt.date(first.year + 1, 1, 1)
        self.period_title.setText(str(first.year) if year else self.calendar.locale().toString(QDate(first.year, first.month, 1), 'MMMM yyyy'))
        start, end = day_start(first), day_start(last)
        summary = self.journal.summary(start, end)
        entries = self.journal.entries(start, end)
        total = sum(row['seconds'] for row in summary)
        untimed = sum(row['start'] is None for row in entries)
        self.stats_total.setText(f'{len(entries)} Einträge · {untimed} ohne Uhrzeit · ' + duration_text(total) + ' mit Uhrzeit')
        self.categories.setRowCount(len(summary))
        for i, row in enumerate(summary):
            values = [row['activity'], duration_text(row['seconds']), f'{row["seconds"] / total:.1%}'.replace('.', ',')]
            for col, value in enumerate(values):
                self.categories.setItem(i, col, QTableWidgetItem(value))
        daily = self.journal.daily(first, last)
        entry_days = Counter(max(first, dt.date.fromisoformat(e['day'])) for e in entries)
        points = []
        if year:
            for month in range(1, 13):
                count = sum(count for day, count in entry_days.items() if day.month == month)
                points.append((self.calendar.locale().monthName(month), sum(v for d, v in daily.items() if d.month == month), count))
        else:
            day = first
            while day < last:
                count = entry_days[day]
                points.append((day.strftime('%d.%m.%Y'), daily.get(day, 0), count))
                day += dt.timedelta(days=1)
        self.trend.setRowCount(len(points))
        for i, (caption, seconds, count) in enumerate(points):
            for col, value in enumerate([caption, duration_text(seconds), str(count)]):
                self.trend.setItem(i, col, QTableWidgetItem(value))
        self.categories.resizeRowsToContents()
        self.trend.resizeRowsToContents()
