import datetime as dt
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from service import Controller
from engine import UTC

class ControllerTests(unittest.TestCase):
    def test_windows_system_processes_are_not_browsers(self):
        from windows import is_browser_exe, BROWSER_PRODUCTS
        self.assertNotIn('chrome remote desktop',BROWSER_PRODUCTS)
        self.assertNotIn('microsoft windows operating system',BROWSER_PRODUCTS)
        for name in ('lsass.exe','RuntimeBroker.exe','sihost.exe','fontdrvhost.exe','notepad.exe'):
            self.assertFalse(is_browser_exe('C:\\Windows\\System32\\'+name),name)
        self.assertTrue(is_browser_exe('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'))
        self.assertTrue(is_browser_exe('C:\\Users\\Example\\AppData\\Local\\Perplexity\\Comet\\Application\\comet.exe'))
    def test_restart_and_atomic_state(self):
        with tempfile.TemporaryDirectory() as folder:
            c=Controller(folder,enforce=False)
            self.assertEqual(len(c.engine.state['rules']),2)
            rid=c.engine.state['rules'][0]['id']
            c.engine.charge([rid],2,c.now());c.persist()
            other=Controller(folder,enforce=False)
            self.assertEqual(other.engine.used(rid,other.now()),2)
            self.assertFalse(Path(folder,'state.tmp').exists())

    def test_corrupt_state_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder,'state.json');p.write_text('broken')
            with self.assertRaises(json.JSONDecodeError):Controller(folder,enforce=False)
            self.assertEqual(p.read_text(),'broken')

    def test_real_tick_does_not_enforce_in_test_mode(self):
        for games in ([], [dict(name='Example',path=r'C:\Games\Example',launcher='Steam')]):
            with self.subTest(games=games), tempfile.TemporaryDirectory() as folder, \
                 patch('service.installed_games',return_value=games), patch('service.terminate') as terminate:
                c=Controller(folder,enforce=False);c.tick(None)
                self.assertEqual(c.errors,[])
                self.assertTrue(all(not r['enabled'] for r in c.engine.state['rules']))
                self.assertEqual(c.games,games)
                terminate.assert_not_called()

    def test_malformed_foreground_report_cannot_stop_enforcement(self):
        # Any FokusWache.exe started with --agent may send reports; odd values must not halt ticks.
        import os
        with tempfile.TemporaryDirectory() as folder, patch('service.installed_games',return_value=[]):
            c=Controller(folder,enforce=False)
            rule=c.engine.save(dict(name='Netz',kind='internet',enabled=True,daily_minutes=1),c.now())
            client=Mock();client.username.return_value='user'
            for fg in (None,5,'x',[],{'pid':None},{'pid':'1','idle':'0'},{'pid':os.getpid(),'idle':None},{'pid':os.getpid(),'idle':math.nan}):
                with self.subTest(fg=fg):
                    with patch.object(c,'role',return_value=('agent',client)):
                        c.handle({'op':'foreground','foreground':fg},os.getpid())
                    c.tick(None)
                    with patch.object(c,'role',return_value=('ui',client)):
                        self.assertEqual(c.handle({'op':'status'},os.getpid())['activity'][0]['pid'],
                                         fg['pid'] if isinstance(fg,dict) and type(fg['pid']) is int else 0)
            self.assertEqual(c.engine.used(rule['id'],c.now()),0)

    def test_browser_pulse_requires_browser_parent(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            c=Controller(folder,enforce=False)
            with self.assertRaises(ValueError):c.role(os.getpid())

if __name__=='__main__':unittest.main()
