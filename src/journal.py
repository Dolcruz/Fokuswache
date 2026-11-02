"""Personal, manually recorded activities. Independent of restriction counters."""
import datetime as dt
import os
import sqlite3
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/Berlin')
SCHEMA = '''(id TEXT PRIMARY KEY, activity TEXT NOT NULL, day TEXT NOT NULL,
    start INTEGER, end INTEGER, note TEXT NOT NULL DEFAULT '',
    CHECK((start IS NULL AND end IS NULL) OR
          (start IS NOT NULL AND end IS NOT NULL AND end > start)))'''


def day_start(day):
    return int(dt.datetime.combine(day, dt.time(), ZONE).timestamp())


def duration_text(seconds):
    minutes = round(seconds / 60)
    return f'{minutes // 60} h {minutes % 60:02d} min'


class Journal:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ['LOCALAPPDATA']) / 'FokusWache' / 'zeitprotokoll.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=5)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute('CREATE TABLE IF NOT EXISTS activities ' + SCHEMA)
            columns = {r['name'] for r in self.db.execute('PRAGMA table_info(activities)')}
            if 'day' not in columns:
                self.db.execute('CREATE TABLE activities_new ' + SCHEMA)
                for row in self.db.execute('SELECT * FROM activities').fetchall():
                    day = dt.datetime.fromtimestamp(row['start'], ZONE).date().isoformat()
                    self.db.execute('INSERT INTO activities_new VALUES (?,?,?,?,?,?)',
                        (row['id'], row['activity'], day, row['start'], row['end'], row['note']))
                self.db.execute('DROP TABLE activities')
                self.db.execute('ALTER TABLE activities_new RENAME TO activities')
            self.db.execute('CREATE INDEX IF NOT EXISTS activities_start ON activities(start)')
            self.db.execute('CREATE INDEX IF NOT EXISTS activities_day ON activities(day)')
            self.db.commit()
        except Exception:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def names(self):
        return [r[0] for r in self.db.execute('SELECT DISTINCT activity FROM activities ORDER BY activity COLLATE NOCASE')]

    def entries(self, start, end):
        first = dt.datetime.fromtimestamp(start, ZONE).date().isoformat()
        last = dt.datetime.fromtimestamp(end - 1, ZONE).date().isoformat()
        return [dict(r) for r in self.db.execute(
            '''SELECT * FROM activities WHERE (start < ? AND end > ?)
               OR (start IS NULL AND day >= ? AND day <= ?)
               ORDER BY day, start IS NULL, start, rowid''', (end, start, first, last))]

    def save(self, activity, start=None, end=None, note='', entry_id=None, day=None):
        activity = activity.strip()
        if not activity:
            raise ValueError('Schreib kurz auf, was du gemacht hast.')
        timed = start is not None or end is not None
        if timed:
            if type(start) is not int or type(end) is not int or end <= start:
                raise ValueError('Das Ende muss nach dem Beginn liegen.')
            day = dt.datetime.fromtimestamp(start, ZONE).date()
        if type(day) is not dt.date:
            raise ValueError('Bitte einen Tag auswählen.')
        entry_id = entry_id or str(uuid.uuid4())
        try:
            self.db.execute('BEGIN IMMEDIATE')
            conflict = self.db.execute(
                'SELECT activity,start,end FROM activities WHERE start < ? AND end > ? AND id != ? LIMIT 1',
                (end, start, entry_id)).fetchone()
            if conflict:
                begin = dt.datetime.fromtimestamp(conflict['start'], ZONE).strftime('%d.%m. %H:%M')
                finish = dt.datetime.fromtimestamp(conflict['end'], ZONE).strftime('%d.%m. %H:%M')
                raise ValueError(f'Der Zeitraum überschneidet sich mit „{conflict["activity"]}“ ({begin} – {finish}).')
            self.db.execute('''INSERT INTO activities(id,activity,day,start,end,note) VALUES (?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET activity=excluded.activity,day=excluded.day,
                start=excluded.start,end=excluded.end,note=excluded.note''',
                (entry_id, activity, day.isoformat(), start, end, note.strip()))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return entry_id

    def delete(self, entry_id):
        with self.db:
            self.db.execute('DELETE FROM activities WHERE id=?', (entry_id,))

    def summary(self, start, end):
        return [dict(r) for r in self.db.execute('''SELECT activity,
            SUM(MIN(end, ?) - MAX(start, ?)) AS seconds FROM activities
            WHERE start < ? AND end > ? GROUP BY activity ORDER BY seconds DESC,activity''',
            (end, start, end, start))]

    def daily(self, first, last):
        totals = {}
        for entry in self.entries(day_start(first), day_start(last)):
            if entry['start'] is None:
                continue
            day = max(first, dt.datetime.fromtimestamp(entry['start'], ZONE).date())
            while day < last and day_start(day) < entry['end']:
                tomorrow = day + dt.timedelta(days=1)
                seconds = max(0, min(entry['end'], day_start(tomorrow)) - max(entry['start'], day_start(day)))
                totals[day] = totals.get(day, 0) + seconds
                day = tomorrow
        return totals

    def day_counts(self, first, last):
        counts = {}
        for entry in self.entries(day_start(first), day_start(last)):
            day = max(first, dt.date.fromisoformat(entry['day']))
            finish = (dt.datetime.fromtimestamp(entry['end'] - 1, ZONE).date()
                      if entry['end'] is not None else day)
            while day < last and day <= finish:
                counts[day] = counts.get(day, 0) + 1
                day += dt.timedelta(days=1)
        return counts
