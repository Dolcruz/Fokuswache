"""Qt regressions; no requests reach the installed service."""
import copy, os, sys, unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtWidgets import QApplication
import ui
from engine import presets
APP = QApplication.instance() or QApplication([])
from PySide6.QtGui import QFontDatabase
for font in ('segoeui.ttf','segoeuib.ttf'): QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
APP.setStyle('Fusion')
APP.setStyleSheet(ui.STYLE)

class UITests(unittest.TestCase):
    def setUp(self):
        self.window = ui.Application(auto_poll=False)
        self.rules = [dict(r, used_seconds=0, locked=False, blocked=False) for r in presets()]
        self.window.render(dict(rules=self.rules, errors=[]))
    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()
    def test_small_window_actions(self):
        self.window.resize(900,580); self.window.show(); APP.processEvents()
        self.assertTrue(self.window.new_button.isVisible())
        first=next(iter(self.window.cards.values()))
        self.assertTrue(first.toggle_button.isVisible())
        self.assertTrue(first.toggle_button.isEnabled())
        self.assertLessEqual(self.window.minimumSizeHint().width(),900)
    def test_all_templates_validate(self):
        for t in ui.TEMPLATES:
            editor=ui.RuleEditor(self.window,template=t)
            if t[4]=='apps': editor.targets.setPlainText(r'C:\Games\example.exe')
            if t[4]=='web' and not t[5]: editor.targets.setPlainText('example.org')
            self.assertEqual(editor.value()['kind'],t[4])
            self.assertNotEqual(editor.value()['id'],ui.template_rule(t)['id'])
            editor.close()
    def test_review_and_activate(self):
        editor=ui.RuleEditor(self.window,template=ui.TEMPLATES[0])
        editor.advance(); editor.minutes.setValue(45); editor.advance()
        self.assertEqual(editor.pages.currentIndex(),2)
        self.assertIn('45 Minuten',editor.review_body.text())
        with patch.object(self.window,'call') as call:
            editor.advance()
            self.assertTrue(call.call_args.args[0]['rule']['enabled'])
            self.assertEqual(call.call_args.args[0]['rule']['daily_minutes'],45)
        editor.close()
    def test_draft_and_toggle(self):
        editor=ui.RuleEditor(self.window,template=ui.TEMPLATES[1])
        with patch.object(self.window,'call') as call:
            editor.save(False)
            self.assertFalse(call.call_args.args[0]['rule']['enabled'])
        with patch.object(self.window,'confirm',return_value=True), patch.object(self.window,'mutate') as mutate:
            self.window.toggle(dict(self.rules[0],used_seconds=123))
            self.assertTrue(mutate.call_args.args[0]['rule']['enabled'])
            self.assertNotIn('used_seconds',mutate.call_args.args[0]['rule'])
        editor.close()
    def test_edit_preserves_schedules_timer(self):
        rule=copy.deepcopy(self.rules[0])
        rule.update(schedules=[dict(days=[0,2],start='22:00',end='07:00'),dict(days=[5],start='10:00',end='12:00')],timer_until='2026-09-07T10:00:00+00:00')
        editor=ui.RuleEditor(self.window,rule=rule)
        self.assertEqual(editor.value()['schedules'],rule['schedules'])
        self.assertEqual(editor.value()['timer_until'],rule['timer_until'])
        editor.close()
    def test_invalid_targets_and_empty_schedule(self):
        editor=ui.RuleEditor(self.window,template=ui.TEMPLATES[10])
        editor.advance()
        self.assertEqual(editor.pages.currentIndex(),0)
        self.assertIn('Ziel',editor.error.text())
        editor.targets.setPlainText('example.org'); editor.schedule_enabled.setChecked(True)
        for row in list(editor.schedule_rows): editor.remove_schedule(row)
        with self.assertRaises(ValueError): editor.value()
        editor.close()
    def test_offline_locked(self):
        self.window.disconnected('Offline')
        self.assertTrue(all(not c.toggle_button.isEnabled() for c in self.window.cards.values()))
        self.window.render(dict(rules=[dict(self.rules[0],enabled=True,locked=True)]))
        self.assertFalse(next(iter(self.window.cards.values())).toggle_button.isEnabled())
    def test_connection_error_visible_and_cleared_on_recovery(self):
        message='comet.exe: Netzwerk pausiert. Verbindung zur Erweiterung unterbrochen.'
        self.window.render(dict(rules=self.rules,errors=[message]))
        self.assertEqual(self.window.notice.text(),message)
        self.window.render(dict(rules=self.rules,errors=[]))
        self.assertNotIn('Netzwerk pausiert',self.window.notice.text())
    def test_footer_geometry(self):
        editor=ui.RuleEditor(self.window,template=ui.TEMPLATES[0]); editor.resize(720,550); editor.show()
        for index in range(3):
            editor.set_step(index); APP.processEvents()
            self.assertTrue(editor.next.isVisible())
            self.assertLessEqual(editor.next.geometry().bottom(),editor.height())
            self.assertLessEqual(editor.minimumSizeHint().width(),720)
        editor.close()
    def test_game_catalog_and_shared_budget_copy(self):
        self.window.render(dict(rules=self.rules, errors=[], games=[dict(name='Trackmania', launcher='Ubisoft')]))
        self.assertIn('Trackmania · Ubisoft', self.window.browser_status.text())
        self.assertIn('1 Spiele erkannt', self.window.browser_status.text())
        self.assertEqual(ui.KINDS['games'], 'Spiele')
        self.assertIn('EA', ui.effect(self.rules[0]))
if __name__=='__main__': unittest.main()
