"""Capture the real Qt interface using sample rules and a temporary journal."""
import datetime as dt
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtCore import QDate
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication
from engine import validate_rule
from journal import ZONE
import ui

with tempfile.TemporaryDirectory(prefix='FokusWache-screenshots-') as folder:
    os.environ['LOCALAPPDATA'] = folder
    app = QApplication([])
    for font in ('segoeui.ttf', 'segoeuib.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR']) / 'Fonts' / font))
    app.setStyle('Fusion')
    app.setFont(QFont('Segoe UI', 10))
    app.setStyleSheet(ui.STYLE)
    window = ui.Application(auto_poll=False)
    rules = []
    for raw, used, blocked in [
        (dict(name='Social Media', kind='web', targets=['instagram.com', 'tiktok.com'], daily_minutes=30), 720, False),
        (dict(name='Spiele', kind='games', daily_minutes=90), 2100, False),
        (dict(name='Zeit zum Lernen', kind='web', targets=['*'], exceptions=['github.com', 'docs.python.org']), 0, True),
    ]:
        rule = validate_rule(dict(raw, enabled=True))
        rule.update(used_seconds=used, blocked=blocked, locked=False,
                    reason='Fokuszeit' if blocked else 'Freigegeben')
        rules.append(rule)
    window.render(dict(rules=rules, errors=[], browsers=[], games=[], events=[]))
    window.resize(1140, 1040)
    window.show()
    app.processEvents()
    window.grab().save(str(ROOT / 'docs/regeln.png'))
    QIcon(str(ROOT / 'src/FokusWache.ico')).pixmap(256, 256).save(str(ROOT / 'docs/icon.png'))
    window.resize(1140, 800)
    window.navigate(1)
    app.processEvents()
    window.grab().save(str(ROOT / 'docs/vorlagen.png'))
    page = window.journal_page
    day = dt.date(2026, 11, 2)
    for activity, hour, minute, duration in [('Gelernt', 8, 30, 90), ('Sport', 18, 0, 45)]:
        start = int(dt.datetime.combine(day, dt.time(hour, minute), ZONE).timestamp())
        page.journal.save(activity, start, start + duration * 60)
    page.journal.save('Ein Kapitel gelesen', day=day)
    page.calendar.setSelectedDate(QDate(day.year, day.month, day.day))
    window.navigate(3)
    app.processEvents()
    window.grab().save(str(ROOT / 'docs/tagebuch.png'))
    page.tabs.setCurrentIndex(1)
    page.refresh_stats()
    app.processEvents()
    window.grab().save(str(ROOT / 'docs/rueckblick.png'))
    page.journal.close()
    window.close()
