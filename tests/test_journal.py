import datetime as dt
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from journal import Journal, ZONE, day_start


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'journal.sqlite3'
        self.journal = Journal(self.path)

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def test_save_edit_delete_survive_reopen(self):
        entry = self.journal.save(' Kochen ', 100, 200, ' Abendessen ')
        self.journal.close()
        self.journal = Journal(self.path)
        self.assertEqual(self.journal.entries(0, 1000)[0]['note'], 'Abendessen')
        self.journal.save('Spazierengehen', 200, 400, entry_id=entry)
        self.assertEqual(len(self.journal.entries(0, 1000)), 1)
        self.assertEqual(self.journal.summary(0, 1000), [{'activity': 'Spazierengehen', 'seconds': 200}])
        self.journal.delete(entry)
        self.assertEqual(self.journal.entries(0, 1000), [])

    def test_overlap_rolls_back_and_touching_is_allowed(self):
        entry = self.journal.save('Kochen', 100, 200)
        for start, end in [(50, 150), (150, 250), (100, 200), (50, 300), (120, 180)]:
            with self.assertRaises(ValueError):
                self.journal.save('Zocken', start, end)
        self.journal.save('Spazierengehen', 200, 300)
        with self.assertRaises(ValueError):
            self.journal.save('Kochen', 150, 250, entry_id=entry)
        self.assertEqual(self.journal.entries(0, 1000)[0]['start'], 100)

    def test_invalid_inputs(self):
        for activity, start, end in [('', 100, 200), ('A', 100, 100), ('A', 200, 100), ('A', '100', 200), ('A', 100, None)]:
            with self.assertRaises(ValueError):
                self.journal.save(activity, start, end)
        self.assertEqual(self.journal.entries(0, 1000), [])

    def test_month_boundary_clips_summary_and_daily(self):
        midnight = day_start(dt.date(2026, 10, 1))
        self.journal.save('Zocken', midnight-3600, midnight+7200)
        self.assertEqual(self.journal.summary(day_start(dt.date(2026, 9, 1)), midnight)[0]['seconds'], 3600)
        self.assertEqual(self.journal.summary(midnight, day_start(dt.date(2026, 11, 1)))[0]['seconds'], 7200)
        self.assertEqual(self.journal.daily(dt.date(2026, 9, 30), dt.date(2026, 10, 2)),
                         {dt.date(2026, 9, 30): 3600, dt.date(2026, 10, 1): 7200})

    def test_dst_days_have_real_elapsed_hours(self):
        for day, hours in [(dt.date(2026, 3, 29), 23), (dt.date(2026, 10, 25), 25)]:
            tomorrow = day + dt.timedelta(days=1)
            self.journal.save('Schlafen', day_start(day), day_start(tomorrow))
            self.assertEqual(self.journal.daily(day, tomorrow)[day], hours*3600)

    def test_separate_connections_see_saved_entries(self):
        other = Journal(self.path)
        try:
            self.journal.save('Kochen', 100, 200)
            with self.assertRaises(ValueError):
                other.save('Zocken', 150, 250)
            self.assertEqual(other.names(), ['Kochen'])
        finally:
            other.close()

    def test_corrupt_file_is_not_replaced(self):
        corrupt = Path(self.temp.name) / 'bad.sqlite3'
        corrupt.write_bytes(b'not a database')
        with self.assertRaises(sqlite3.DatabaseError):
            Journal(corrupt)
        self.assertEqual(corrupt.read_bytes(), b'not a database')

    def test_untimed_entries_persist_and_do_not_invent_hours(self):
        day = dt.date(2026, 9, 12)
        self.journal.save('Gesaugt', day=day)
        self.journal.save('Bett aufgebaut', day=day)
        start = day_start(day)
        self.journal.save('Kochen', start + 3600, start + 7200)
        self.journal.close()
        self.journal = Journal(self.path)
        entries = self.journal.entries(start, start + 86400)
        self.assertEqual(len(entries), 3)
        self.assertEqual(sum(e['start'] is None for e in entries), 2)
        self.assertEqual(self.journal.summary(start, start + 86400), [{'activity': 'Kochen', 'seconds': 3600}])
        self.assertEqual(self.journal.day_counts(day, day + dt.timedelta(days=1)), {day: 3})
        self.assertEqual(self.journal.daily(day, day + dt.timedelta(days=1)), {day: 3600})

    def test_move_untimed_entry_and_add_remove_time(self):
        day = dt.date(2026, 9, 12)
        next_day = day + dt.timedelta(days=1)
        key = self.journal.save('Gesaugt', day=day)
        self.journal.save('Gesaugt', day=next_day, entry_id=key)
        self.assertEqual(self.journal.entries(day_start(day), day_start(next_day)), [])
        start = day_start(next_day)
        self.journal.save('Gesaugt', start, start + 600, entry_id=key)
        self.assertEqual(self.journal.summary(start, start + 86400)[0]['seconds'], 600)
        self.journal.save('Gesaugt', day=next_day, entry_id=key)
        self.assertEqual(self.journal.summary(start, start + 86400), [])
        self.assertEqual(len(self.journal.entries(start, start + 86400)), 1)

    def test_long_diary_text_is_preserved(self):
        body = 'Ein ausführlicher Gedanke.\n' * 500
        self.journal.save(body, day=dt.date(2026, 9, 12))
        self.assertEqual(self.journal.entries(day_start(dt.date(2026, 9, 12)), day_start(dt.date(2026, 9, 13)))[0]['activity'], body.strip())

    def test_migration_preserves_old_timed_entries_and_ids(self):
        old = Path(self.temp.name) / 'old.sqlite3'
        db = sqlite3.connect(old)
        db.execute('CREATE TABLE activities(id TEXT PRIMARY KEY,activity TEXT NOT NULL,start INTEGER NOT NULL,end INTEGER NOT NULL CHECK(end>start),note TEXT NOT NULL)')
        stamp = day_start(dt.date(2026, 9, 12))
        db.execute('INSERT INTO activities VALUES(?,?,?,?,?)', ('old-id', 'Kochen', stamp, stamp + 3600, 'Notiz'))
        db.commit()
        db.close()
        migrated = Journal(old)
        try:
            self.assertEqual(migrated.entries(stamp, stamp + 86400)[0], dict(id='old-id', activity='Kochen', day='2026-09-12', start=stamp, end=stamp+3600, note='Notiz'))
            migrated.save('Gesaugt', day=dt.date(2026, 9, 12))
            self.assertEqual(len(migrated.entries(stamp, stamp + 86400)), 2)
        finally:
            migrated.close()

    def test_failed_migration_rolls_back_without_losing_old_rows(self):
        old = Path(self.temp.name) / 'invalid-old.sqlite3'
        db = sqlite3.connect(old)
        db.execute('CREATE TABLE activities(id TEXT PRIMARY KEY,activity TEXT NOT NULL,start INTEGER NOT NULL,end INTEGER NOT NULL CHECK(end>start),note TEXT NOT NULL)')
        original = ('old-id', 'Kochen', 10**15, 10**15+3600, 'Notiz')
        db.execute('INSERT INTO activities VALUES(?,?,?,?,?)', original)
        db.commit()
        with self.assertRaises((ValueError, OverflowError, OSError)):
            Journal(old)
        self.assertEqual(db.execute('SELECT * FROM activities').fetchone(), original)
        self.assertNotIn('day', [r[1] for r in db.execute('PRAGMA table_info(activities)')])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='activities_new'").fetchone()[0], 0)
        db.close()


if __name__ == '__main__':
    unittest.main()
