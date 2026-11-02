"""Game discovery, one shared budget, and preservation of existing accounts."""
import copy
import datetime as dt
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from engine import Engine, UTC, validate_rule
from service import Controller
from windows import installed_games, registry_entries
import winreg


class DiscoveryTests(unittest.TestCase):
    def test_catalogs_custom_paths_deduplication_and_epic_editor_exclusion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folders = {name: root / name for name in ('Steam', 'Trackmania', 'EA', 'GOG', 'Epic', 'Editor')}
            for folder in folders.values():
                folder.mkdir()
            manifests = root / 'Epic/EpicGamesLauncher/Data/Manifests'
            manifests.mkdir(parents=True)
            for name, app, category in [('Epic', 'Game', 'games'), ('Editor', 'UE_5.6', 'engines')]:
                (manifests / (name + '.item')).write_text(json.dumps(dict(
                    bIsApplication=True, AppName=app, AppCategories=[category],
                    DisplayName=name, InstallLocation=str(folders[name]))))
            (manifests / 'broken.item').write_text('broken')
            catalogs = {
                r'SOFTWARE\Ubisoft\Launcher\Installs': [('5595', dict(InstallDir=str(folders['Trackmania'])))],
                r'SOFTWARE\EA Games': [('EA', {'Install Dir': str(folders['EA'])})],
                r'SOFTWARE\Origin Games': [('EA', {'Install Dir': str(folders['EA'])})],
                r'SOFTWARE\GOG.com\Games': [('42', dict(path=str(folders['GOG']), gameName='GOG'))],
            }
            with patch('windows.steam_games', return_value=[dict(name='Steam', path=str(folders['Steam']))]), \
                 patch('windows.registry_entries', side_effect=lambda key: catalogs[key]), \
                 patch.dict(os.environ, PROGRAMDATA=temp, PROGRAMFILES=str(root/'Programs'), **{'PROGRAMFILES(X86)': str(root/'Programs32')}):
                games = installed_games()
            self.assertEqual({g['launcher'] for g in games}, {'Steam', 'Ubisoft', 'EA', 'Epic', 'GOG'})
            self.assertEqual(len(games), 5)
            self.assertIn('Trackmania', [g['name'] for g in games])
            self.assertNotIn('Editor', [g['name'] for g in games])

    def test_missing_and_unsafe_install_records_are_not_games(self):
        records = [('bad', dict(InstallDir=p)) for p in ('', None, 'relative/path', 'C:\\', r'C:\Windows', r'C:\Program Files', r'C:\missing-game')]
        with patch('windows.steam_games', return_value=[]), patch('windows.registry_entries', return_value=records), \
             patch('windows.Path.glob', return_value=[]):
            self.assertEqual(installed_games(), [])

    def test_registry_reads_machine_and_loaded_user_in_both_views(self):
        users, parent, child = Mock(), Mock(), Mock()
        for key in (users, parent, child):
            key.__enter__ = Mock(return_value=key)
            key.__exit__ = Mock(return_value=False)
        def open_key(hive, location, *args):
            if hive == winreg.HKEY_USERS and location == '':
                return users
            return child if hive is parent else parent
        with patch('windows.winreg.OpenKey', side_effect=open_key) as opened, \
             patch('windows.winreg.QueryInfoKey', side_effect=lambda k: (1, 1, 0)), \
             patch('windows.winreg.EnumKey', side_effect=lambda k, i: 'S-1-5-21-123' if k is users else '5595'), \
             patch('windows.winreg.EnumValue', return_value=('InstallDir', r'D:\Games\Trackmania', winreg.REG_SZ)):
            entries = list(registry_entries(r'SOFTWARE\Ubisoft\Launcher\Installs'))
        self.assertEqual(len(entries), 4)
        for hive, prefix in ((winreg.HKEY_LOCAL_MACHINE, ''), (winreg.HKEY_USERS, 'S-1-5-21-123\\')):
            for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
                opened.assert_any_call(hive, prefix + r'SOFTWARE\Ubisoft\Launcher\Installs', 0, winreg.KEY_READ | view)

    def test_corrupt_path_does_not_discard_valid_installations(self):
        with tempfile.TemporaryDirectory() as temp:
            records = [('bad', dict(InstallDir='C:\\bad\x00game')), ('game', dict(InstallDir=temp))]
            with patch('windows.steam_games', return_value=[]), patch('windows.registry_entries', return_value=records), \
                 patch('windows.Path.glob', return_value=[]):
                games = installed_games()
            self.assertEqual(len(games), 1)
            self.assertEqual(games[0]['path'], str(Path(temp).resolve()))


class GameRuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.games = [dict(name=n, path='C:\\Games\\' + n, launcher=n) for n in ('Steam', 'Ubisoft', 'EA', 'Epic', 'GOG')]
        with patch('service.installed_games', return_value=self.games):
            self.controller = Controller(self.temp.name, enforce=True)
        self.base = self.controller.started
        self.controller.last_discovery = self.base + 1000
        self.rule = self.controller.engine.state['rules'][0]
        self.rule.update(enabled=True, daily_minutes=.05)
        self.processes = {}
        for pid, game in enumerate(self.games, 100):
            p = Mock(pid=pid)
            p.info = dict(pid=pid, name=game['name'] + '.exe', exe=game['path'] + '\\game.exe', ppid=0)
            p.exe.return_value = p.info['exe']
            self.processes[pid] = p
        self.launcher = Mock(pid=200)
        self.launcher.info = dict(pid=200, name='upc.exe', exe=r'C:\Launchers\Ubisoft\upc.exe', ppid=0)
        self.launcher.exe.return_value = self.launcher.info['exe']
        self.processes[200] = self.launcher
        self.fw = Mock()

    def tearDown(self):
        self.temp.cleanup()

    def tick(self, seconds, foreground):
        mono = self.base + seconds
        self.controller.agents[999] = dict(time=mono, fg=dict(pid=foreground, idle=999))
        with patch('service.time.monotonic', return_value=mono), \
             patch('service.psutil.Process', side_effect=lambda pid: self.processes[pid]), \
             patch('service.psutil.pid_exists', return_value=True), \
             patch('service.psutil.process_iter', return_value=list(self.processes.values())), \
             patch('service.is_browser_exe', return_value=False), \
             patch('service.terminate', return_value=True) as kill:
            self.controller.tick(self.fw)
        return kill

    def test_switching_launchers_uses_one_budget_and_blocks_all_games(self):
        self.tick(1, 100)
        self.tick(2, 101)
        self.tick(3, 102)
        kill = self.tick(4, 103)
        self.assertEqual(self.controller.engine.used(self.rule['id'], self.controller.now()), 3)
        self.assertEqual(kill.call_count, 5)
        self.assertNotIn(unittest.mock.call(self.launcher), kill.call_args_list)

    def test_idle_launcher_does_not_charge_time(self):
        self.tick(1, 200)
        self.tick(2, 200)
        self.assertEqual(self.controller.engine.used(self.rule['id'], self.controller.now()), 0)

    def test_exceptions_and_additional_standalone_games(self):
        self.rule['exceptions'] = [self.games[1]['path']]
        self.rule['targets'] = [r'D:\Standalone\game.exe']
        self.assertFalse(self.controller.app_matches(self.rule, self.processes[101].exe()))
        self.assertTrue(self.controller.app_matches(self.rule, r'D:\Standalone\game.exe'))
        self.assertFalse(self.controller.app_matches(self.rule, r'C:\Games\SteamExtra\game.exe'))
        self.rule['daily_minutes'] = None
        kill = self.tick(1, 200)
        self.assertEqual(kill.call_count, 4)

    def test_legacy_rule_migration_preserves_id_usage_and_locks(self):
        now = dt.datetime.now(UTC)
        rule = validate_rule(dict(name='Spiele', kind='games', enabled=True, daily_minutes=120))
        rule.update(kind='steam', name='Steam-Spiele', locked_until=(now + dt.timedelta(hours=1)).isoformat())
        state = dict(rules=[rule], usage={}, last_time=now.isoformat())
        engine = Engine(state)
        engine.charge([rule['id']], 2, now)
        original = copy.deepcopy(engine.state)
        # Simulate the existing on-disk Steam state, then restart the controller twice.
        state['rules'][0].update(kind='steam', name='Steam-Spiele')
        Path(self.temp.name, 'state.json').write_text(json.dumps(state), encoding='utf-8')
        with patch('service.installed_games', return_value=self.games):
            c = Controller(self.temp.name, enforce=False)
            restarted = Controller(self.temp.name, enforce=False)
        self.assertEqual(c.engine.state['rules'], original['rules'])
        self.assertEqual(restarted.engine.state['rules'], original['rules'])
        self.assertEqual(restarted.engine.used(rule['id'], now), 2)
        with self.assertRaisesRegex(ValueError, 'verriegelt'):
            restarted.engine.save(original['rules'][0], now)


if __name__ == '__main__':
    unittest.main()
