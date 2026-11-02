import datetime as dt
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import sqlite3

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import Qt, QDate, QDateTime
from PySide6.QtTest import QTest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QDialog
from journal_ui import JournalPage, EntryEditor
from journal import day_start

APP = QApplication.instance() or QApplication([])


class JournalUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.page = JournalPage(path=Path(self.temp.name) / 'test.sqlite3')
        self.day = dt.date(2026, 9, 12)
        self.page.calendar.setSelectedDate(QDate(2026, 9, 12))

    def tearDown(self):
        self.page.journal.close()
        self.page.close()
        self.page.deleteLater()
        APP.processEvents()
        self.temp.cleanup()

    def test_form_save_and_statistics(self):
        editor = EntryEditor(self.page.journal, self.day, self.page)
        editor.activity.setPlainText('Kochen')
        editor.with_time.setChecked(True)
        editor.start.setDateTime(QDateTime.fromSecsSinceEpoch(day_start(self.day) + 3600))
        editor.end.setDateTime(QDateTime.fromSecsSinceEpoch(day_start(self.day) + 7200))
        editor.save()
        self.assertEqual(editor.result(), QDialog.Accepted)
        self.page.refresh()
        self.assertEqual(len(self.page.cards), 1)
        self.assertEqual(self.page.categories.item(0, 1).text(), '1 h 00 min')
        self.page.period.setCurrentIndex(1)
        self.assertEqual(self.page.trend.rowCount(), 12)
        self.assertEqual(self.page.trend.item(8, 1).text(), '1 h 00 min')

    def test_invalid_form_keeps_input_and_does_not_save(self):
        editor = EntryEditor(self.page.journal, self.day, self.page)
        editor.activity.setPlainText('Kochen')
        editor.with_time.setChecked(True)
        editor.note.setPlainText('Behalten')
        editor.end.setDateTime(editor.start.dateTime())
        editor.save()
        self.assertIn('Ende', editor.error.text())
        self.assertEqual(editor.note.toPlainText(), 'Behalten')
        self.assertEqual(self.page.journal.names(), [])

    def test_overnight_day_view_and_edit(self):
        midnight = day_start(self.day)
        key = self.page.journal.save('Zocken', midnight-1800, midnight+5400, 'Notiz')
        self.page.refresh()
        self.assertIn('1 h 30 min', self.page.day_total.text())
        self.assertTrue(self.page.cards[0].edit_button.isEnabled())
        entry = self.page.rows[0]
        editor = EntryEditor(self.page.journal, self.day, self.page, entry)
        editor.activity.setPlainText('Computer')
        editor.save()
        self.assertEqual(self.page.journal.entries(midnight, midnight+86400)[0]['id'], key)
        self.assertEqual(self.page.journal.names(), ['Computer'])

    def test_empty_month_and_navigation(self):
        self.assertEqual(self.page.categories.rowCount(), 0)
        self.assertFalse(self.page.save_button.isEnabled())
        self.page.shift(1)
        self.assertEqual(self.page.calendar.monthShown(), 10)
        self.assertEqual(self.page.trend.rowCount(), 31)

    def test_each_card_edits_its_own_entry_without_selection(self):
        midnight = day_start(self.day)
        key = self.page.journal.save('Kochen', midnight, midnight + 3600, 'Abendessen')
        self.page.journal.save('Gesaugt', day=self.day)
        self.page.refresh()
        card = next(c for c in self.page.cards if c.entry_id == key)
        self.assertTrue(card.edit_button.isEnabled())
        self.assertTrue(card.delete_button.isEnabled())
        with patch('journal_ui.EntryEditor') as editor:
            editor.return_value.exec.return_value = 0
            card.edit_button.click()
            self.assertEqual(editor.call_args.args[3]['id'], key)

    def test_enter_saves_without_time_and_marks_calendar(self):
        self.page.quick.setPlainText('Heute gesaugt')
        QTest.keyClick(self.page.quick, Qt.Key_Return)
        self.assertEqual(self.page.quick.toPlainText(), '')
        self.assertEqual(self.page.rows[0]['activity'], 'Heute gesaugt')
        self.assertIsNone(self.page.rows[0]['start'])
        self.assertIn(self.day, self.page.marked)
        self.assertEqual(self.page.categories.rowCount(), 0)
        self.assertEqual(self.page.trend.item(11, 2).text(), '1')
        self.assertIn('Festgehalten', self.page.feedback.text())

    def test_shift_enter_and_changing_day_keep_draft(self):
        self.page.quick.setPlainText('Erster Gedanke')
        self.page.quick.moveCursor(QTextCursor.End)
        QTest.keyClick(self.page.quick, Qt.Key_Return, Qt.ShiftModifier)
        self.assertEqual(self.page.quick.toPlainText(), 'Erster Gedanke\n')
        self.assertEqual(self.page.rows, [])
        self.page.calendar.setSelectedDate(QDate(2026, 9, 13))
        self.assertEqual(self.page.quick.toPlainText(), '')
        self.page.calendar.setSelectedDate(QDate(2026, 9, 12))
        self.assertEqual(self.page.quick.toPlainText(), 'Erster Gedanke\n')

    def test_save_failure_keeps_quick_input(self):
        self.page.quick.setPlainText('Bett aufgebaut')
        with patch.object(self.page.journal, 'save', side_effect=sqlite3.OperationalError('database is locked')):
            self.page.quick_save()
        self.assertEqual(self.page.quick.toPlainText(), 'Bett aufgebaut')
        self.assertEqual(self.page.rows, [])
        self.assertIn('locked', self.page.feedback.text())

    def test_editor_defaults_to_no_time_and_can_add_time_later(self):
        editor = EntryEditor(self.page.journal, self.day, self.page, draft='Bett aufgebaut')
        self.assertFalse(editor.with_time.isChecked())
        editor.save()
        self.assertEqual(editor.result(), QDialog.Accepted)
        self.page.refresh()
        entry = self.page.rows[0]
        self.assertIsNone(entry['start'])
        change = EntryEditor(self.page.journal, self.day, self.page, entry)
        change.with_time.setChecked(True)
        change.save()
        self.page.refresh()
        self.assertEqual(len(self.page.rows), 1)
        self.assertEqual(self.page.rows[0]['id'], entry['id'])
        self.assertIsNotNone(self.page.rows[0]['start'])


if __name__ == '__main__':
    unittest.main()
