import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
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
        with tempfile.TemporaryDirectory() as folder:
            c=Controller(folder,enforce=False);c.tick(None)
            self.assertEqual(c.errors,[])
            self.assertTrue(all(not r['enabled'] for r in c.engine.state['rules']))
            self.assertGreater(len(c.games),0)

    def test_browser_pulse_requires_browser_parent(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            c=Controller(folder,enforce=False)
            with self.assertRaises(ValueError):c.role(os.getpid())

if __name__=='__main__':unittest.main()
