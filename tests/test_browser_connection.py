"""Connection interruptions must never terminate a browser or reset its quota."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from service import Controller


class BrowserConnectionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        with patch('service.installed_games', return_value=[]):
            self.controller = Controller(self.folder.name, enforce=True)
        self.base = self.controller.started
        self.controller.last_discovery = self.base + 1000
        self.rule = next(r for r in self.controller.engine.state['rules'] if r['kind'] == 'web')
        self.rule['enabled'] = True
        self.process = Mock()
        self.process.pid = 314
        self.process.info = dict(pid=314, name='comet.exe', exe=r'C:\Browser\comet.exe', ppid=0)
        self.process.exe.return_value = self.process.info['exe']
        self.process.name.return_value = 'comet.exe'
        self.process.create_time.return_value = 42
        self.firewall = Mock()
        self.kill = patch('service.terminate').start()
        self.patches = [patch('service.psutil.process_iter', return_value=[self.process]),
                        patch('service.psutil.pid_exists', return_value=True),
                        patch('service.psutil.Process', return_value=self.process),
                        patch('service.browser_root', return_value=self.process)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        self.kill.assert_not_called()
        patch.stopall()
        self.folder.cleanup()

    def tick(self, seconds, focused=None):
        mono = self.base + seconds
        fg = dict(pid=314, idle=0)
        self.controller.agents[123] = dict(time=mono, fg=fg)
        if focused is not None:
            self.controller.hosts[991] = dict(root=314, created=self.process.create_time(), time=mono,
                ready=True, focused=focused, fg=fg, url='https://example.org')
        with patch('service.time.monotonic', return_value=mono):
            self.controller.tick(self.firewall)
        browser = self.controller.browsers[0]
        self.assertIn(unittest.mock.call(self.process.exe(), browser['network_blocked']), self.firewall.browser_block.call_args_list)
        self.firewall.reset_mock()
        return browser

    def test_unconfirmed_browser_has_no_network_lease(self):
        self.assertTrue(self.tick(100)['network_blocked'])
        self.assertFalse(self.tick(101, True)['network_blocked'])

    def test_old_browser_focus_transition_does_not_close_or_block(self):
        self.tick(100, True)
        self.tick(200, True)
        state = self.tick(201, False)
        self.assertFalse(state['connected'])
        self.assertFalse(state['network_blocked'])
        self.assertIn('fenster', state['connection_reason'])
        self.assertFalse(self.tick(202, True)['network_blocked'])

    def test_missing_heartbeat_blocks_only_after_lease_then_recovers(self):
        self.tick(100, True)
        self.assertFalse(self.tick(104)['network_blocked'])
        self.assertFalse(self.tick(111)['network_blocked'])
        self.assertTrue(self.tick(112)['network_blocked'])
        self.assertFalse(self.tick(113, True)['network_blocked'])
        self.assertFalse(self.tick(117)['network_blocked'])
        messages = [e['message'] for e in self.controller.events]
        self.assertEqual(sum('Browsernetz pausiert' in x for x in messages), 1)
        self.assertEqual(sum('Browsernetz freigegeben' in x for x in messages), 1)

    def test_new_process_cannot_inherit_previous_lease(self):
        self.tick(100, True)
        self.process.create_time.return_value = 43
        self.assertTrue(self.tick(101)['network_blocked'])

    def test_disabling_web_rule_releases_network_and_preserves_usage(self):
        self.controller.engine.charge([self.rule['id']], 2, self.controller.now())
        self.assertTrue(self.tick(100)['network_blocked'])
        self.rule['enabled'] = False
        self.assertFalse(self.tick(101)['network_blocked'])
        self.assertEqual(self.controller.engine.used(self.rule['id'], self.controller.now()), 2)


if __name__ == '__main__':
    unittest.main()
