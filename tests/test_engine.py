import copy
import datetime as dt
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from engine import Engine, UTC, ZONE, decision, host_match, in_schedule, presets, timestamp, validate_rule, web_match

NOW = dt.datetime(2026, 9, 7, 12, 0, tzinfo=UTC)

class PolicyTests(unittest.TestCase):
    def rule(self, **kwargs):
        return validate_rule(dict(name='Test', kind='web', targets=['x.com'], enabled=True, **kwargs))

    def test_domain_boundaries(self):
        for url in ('https://x.com/a', 'https://www.x.com/a', 'https://X.COM:443/a', 'https://x.com./a'):
            self.assertTrue(host_match(url, 'x.com'))
        for url in ('https://evilx.com/', 'https://x.com.evil.org/', 'https://example.com/?x.com', 'file:///x.com'):
            self.assertFalse(host_match(url, 'x.com'))

    def test_path_prefix(self):
        self.assertTrue(host_match('https://www.example.com/foo/bar', 'example.com/foo'))
        self.assertFalse(host_match('https://example.com/other', 'example.com/foo'))

    def test_internationalized_targets_match_browser_urls(self):
        # Browsers report IDN hosts as punycode and percent-encode non-ASCII paths.
        self.assertTrue(host_match('https://www.xn--mller-kva.de/', 'Müller.de'))
        self.assertTrue(host_match('https://xn--strae-oqa.de/', 'straße.de'))
        self.assertTrue(host_match('https://de.wikipedia.org/wiki/Fu%C3%9Fball_EM', 'de.wikipedia.org/wiki/Fußball'))
        self.assertTrue(host_match('https://example.com/a%20b', 'example.com/a b'))
        self.assertFalse(host_match('https://xn--mller-kva.de.evil.org/', 'müller.de'))
        r = validate_rule({'name': 'Work', 'kind': 'web', 'targets': ['*'], 'exceptions': ['bücher.de']})
        self.assertFalse(web_match(r, 'https://xn--bcher-kva.de/'))

    def test_global_web_and_exceptions(self):
        r = validate_rule({'name':'Work', 'kind':'web', 'targets':['*'], 'exceptions':['example.org']})
        self.assertFalse(web_match(r, 'https://sub.example.org/test'))
        self.assertTrue(web_match(r, 'https://example.org.evil.com/test'))

    def test_quota_shared_and_duplicate_pulses(self):
        e = Engine(); r = e.save(self.rule(daily_minutes=.05), NOW)
        e.charge([r['id'],r['id']], 2, NOW)
        self.assertEqual(e.used(r['id'], NOW), 2)
        e.charge([r['id']], 1, NOW)
        self.assertTrue(e.rules(NOW)[0]['blocked'])

    def test_charge_rejects_sleep_nan_negative(self):
        e=Engine(); r=e.save(self.rule(daily_minutes=1),NOW)
        for seconds in (4,100000,-1,math.nan,math.inf): e.charge([r['id']],seconds,NOW)
        self.assertEqual(e.used(r['id'],NOW),0)

    def test_midnight_reset_berlin(self):
        e=Engine();r=e.save(self.rule(daily_minutes=1),NOW)
        before=dt.datetime(2026,9,7,21,59,59,tzinfo=UTC)
        e.charge([r['id']],2,before)
        self.assertEqual(e.used(r['id'],before),2)
        self.assertEqual(e.used(r['id'],before+dt.timedelta(seconds=1)),0)

    def test_restart_persists_quota(self):
        e=Engine();r=e.save(self.rule(daily_minutes=1),NOW)
        e.charge([r['id']],3,NOW)
        reloaded=Engine(json.loads(json.dumps(e.state)))
        self.assertEqual(reloaded.used(r['id'],NOW),3)

    def test_edit_preserves_usage(self):
        e=Engine();r=e.save(self.rule(daily_minutes=1),NOW)
        e.charge([r['id']],2,NOW)
        r=dict(r,name='Renamed');e.save(r,NOW)
        self.assertEqual(e.used(r['id'],NOW),2)

    def test_lock_cannot_edit_delete_disable_shorten(self):
        e=Engine();r=e.save(self.rule(daily_minutes=30),NOW)
        until=(NOW+dt.timedelta(hours=1)).isoformat()
        e.mutate('lock',r['id'],NOW,until=until)
        with self.assertRaises(ValueError):e.save(dict(r,enabled=False),NOW)
        for op in ('delete','timer','lock'):
            with self.assertRaises(ValueError):e.mutate(op,r['id'],NOW,until=until,minutes=1)
        e.mutate('delete',r['id'],NOW+dt.timedelta(hours=1))
        self.assertEqual(e.state['rules'],[])

    def test_cannot_inject_lock_on_save(self):
        e=Engine();r=e.save(self.rule(locked_until=(NOW+dt.timedelta(days=20)).isoformat()),NOW)
        self.assertIsNone(r['locked_until'])

    def test_timer_expires_without_permanent_block(self):
        e=Engine();r=e.save(self.rule(),NOW)
        e.mutate('timer',r['id'],NOW,minutes=1)
        self.assertTrue(e.rules(NOW)[0]['blocked'])
        self.assertFalse(e.rules(NOW+dt.timedelta(minutes=1))[0]['blocked'])

    def test_overnight_schedule_previous_weekday(self):
        s={'days':[0],'start':'22:00','end':'06:00'}
        for day,hour,expected in ((7,21,False),(7,22,True),(8,5,True),(8,6,False),(8,23,False)):
            self.assertEqual(in_schedule(s,dt.datetime(2026,9,day,hour,tzinfo=ZONE)),expected)

    def test_allowed_and_blocked_schedule(self):
        s=[{'days':[0],'start':'09:00','end':'17:00'}]
        self.assertFalse(decision(self.rule(schedules=s),0,NOW)[0])
        self.assertTrue(decision(self.rule(schedules=s,schedule_mode='blocked'),0,NOW)[0])
        self.assertTrue(decision(self.rule(schedules=s),0,NOW+dt.timedelta(hours=8))[0])

    def test_conditions_or_not_and(self):
        r=self.rule(daily_minutes=1,schedules=[{'days':[0],'start':'09:00','end':'17:00'}])
        self.assertTrue(decision(r,60,NOW)[0])
        self.assertTrue(decision(r,0,NOW+dt.timedelta(hours=8))[0])

    def test_dst_sunday_does_not_change_weekday(self):
        s={'days':[6],'start':'01:00','end':'04:00'}
        for h in (0,1,2):
            self.assertTrue(in_schedule(s,dt.datetime(2026,10,25,h,tzinfo=UTC).astimezone(ZONE)))

    def test_invalid_limits(self):
        for x in (-1,0,1441,math.nan,math.inf,'30',True):
            with self.assertRaises(ValueError):self.rule(daily_minutes=x)

    def test_bad_rules(self):
        for changes in ({'schedules':[{'days':[7],'start':'09:00','end':'10:00'}]}, {'schedules':[{'days':[0],'start':'24:00','end':'10:00'}]}, {'exceptions':['example.com/private']}, {'timer_until':'2026-10-01T12:00:00'}):
            with self.assertRaises(ValueError):self.rule(**changes)

    def test_disabled_presets(self):
        for r in presets():self.assertFalse(r['enabled'])

if __name__=='__main__':unittest.main()
