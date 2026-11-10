"""Failed Windows rule updates must remain visible and recoverable."""
from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from windows import Firewall
from service import Controller


class Rules:
    def __init__(self):
        self.items = {'Other application': SimpleNamespace(Name='Other application')}
        self.fail_remove = set()
        self.fail_add = set()

    def Remove(self, name):
        if name in self.fail_remove:
            self.fail_remove.remove(name)
            raise OSError('Windows rejected rule removal')
        self.items.pop(name, None)

    def Add(self, rule):
        if rule.Name in self.fail_add:
            self.fail_add.remove(rule.Name)
            raise OSError('Windows rejected rule creation')
        self.items[rule.Name] = rule


class FirewallTests(unittest.TestCase):
    def setUp(self):
        self.rules = Rules()
        policy = SimpleNamespace(Rules=self.rules)
        dispatch = patch('win32com.client.Dispatch', side_effect=lambda name:
                         policy if name == 'HNetCfg.FwPolicy2' else SimpleNamespace())
        dispatch.start()
        self.addCleanup(dispatch.stop)
        self.firewall = Firewall()

    def assert_released(self):
        self.assertEqual(set(self.rules.items), {'Other application'})

    def test_browser_removal_failure_is_reported_and_retried(self):
        path = r'C:\Browser\comet.exe'
        self.firewall.browser_block(path, True)
        name = next(name for name in self.rules.items if name.startswith('FokusWache'))
        self.rules.fail_remove.add(name)
        with self.assertRaisesRegex(OSError, 'removal'):
            self.firewall.browser_block(path, False)
        self.assertIn(name, self.rules.items)
        self.firewall.browser_block(path, False)
        self.assert_released()

    def test_global_removal_failure_is_reported_and_retried(self):
        self.firewall.set_blocked(True)
        self.rules.fail_remove.add(self.firewall.names[1])
        with self.assertRaisesRegex(OSError, 'removal'):
            self.firewall.set_blocked(False)
        self.assertIn(self.firewall.names[1], self.rules.items)
        self.firewall.set_blocked(False)
        self.assert_released()

    def test_partial_release_then_changed_request_restores_both_rules(self):
        self.firewall.set_blocked(True)
        self.rules.fail_remove.add(self.firewall.names[1])
        with self.assertRaises(OSError):
            self.firewall.set_blocked(False)
        self.firewall.set_blocked(True)
        self.assertTrue(all(name in self.rules.items for name in self.firewall.names))

    def test_partial_creation_then_changed_request_releases_remaining_rule(self):
        self.firewall.set_blocked(False)
        self.rules.fail_add.add(self.firewall.names[1])
        with self.assertRaisesRegex(OSError, 'creation'):
            self.firewall.set_blocked(True)
        self.assertIn(self.firewall.names[0], self.rules.items)
        self.firewall.set_blocked(False)
        self.assert_released()

    def test_absent_rules_can_be_released_without_touching_other_rules(self):
        self.firewall.set_blocked(False)
        self.firewall.browser_block(r'C:\Browser\comet.exe', False)
        self.assert_released()

    def test_failed_obsolete_rule_cleanup_survives_service_restart(self):
        path = r'C:\OldBrowser\retired.exe'
        self.firewall.browser_block(path, True)
        name = next(name for name in self.rules.items if name.startswith('FokusWache'))
        self.rules.fail_remove.add(name)
        with tempfile.TemporaryDirectory() as folder, \
             patch('service.installed_games', return_value=[]), \
             patch('service.psutil.process_iter', return_value=[]), \
             patch('service.is_browser_exe', return_value=False):
            controller = Controller(folder, enforce=True)
            controller.browser_paths.clear()
            controller.stale_browser_paths.add(path)
            controller.tick(self.firewall)
            self.assertTrue(any('removal' in error for error in controller.errors))
            self.assertIn(path, controller.stale_browser_paths)
            self.assertIn(path, json.loads(Path(folder, 'state.json').read_text('utf-8'))['browser_paths'])

            restarted = Controller(folder, enforce=True)
            self.assertIn(path, restarted.stale_browser_paths)
            restarted.tick(Firewall())
            self.assertNotIn(path, restarted.stale_browser_paths)
            self.assertNotIn(path, json.loads(Path(folder, 'state.json').read_text('utf-8'))['browser_paths'])
            self.assert_released()


if __name__ == '__main__':
    unittest.main()
