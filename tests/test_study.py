import copy
import datetime as dt
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from engine import Engine, UTC, STUDY_STOP_SENTENCE, STUDY_STOP_WAIT, validate_rule
from service import Controller
import watcher

NOW = dt.datetime(2026, 11, 27, 16, 0, tzinfo=UTC)
MIN = dt.timedelta(minutes=1)


def engine_with_rules():
    e = Engine()
    e.state['rules'] = [
        validate_rule(dict(name='YouTube', kind='web', targets=['youtube.com'], enabled=False, daily_minutes=60)),
        validate_rule(dict(name='Reddit', kind='web', targets=['reddit.com'], enabled=True, daily_minutes=30)),
        validate_rule(dict(name='Spiele', kind='games', enabled=False, daily_minutes=120)),
        validate_rule(dict(name='Roblox', kind='apps', targets=[r'C:\Games\Roblox.exe'], enabled=True, daily_minutes=30)),
        validate_rule(dict(name='Netz', kind='internet', enabled=False, daily_minutes=10)),
        validate_rule(dict(name='PC', kind='device', enabled=False, daily_minutes=10)),
    ]
    return e


class StudyEngineTests(unittest.TestCase):
    def test_overlay_blocks_every_web_app_game_rule_and_leaves_storage_alone(self):
        e = engine_with_rules()
        stored = copy.deepcopy(e.state['rules'])
        e.study_start(50, 'IPI Kapitel 9.2, Skript und Trainer', NOW)
        rules = {r['name']: r for r in e.rules(NOW + MIN)}
        for name in ('YouTube', 'Reddit', 'Spiele', 'Roblox'):
            self.assertTrue(rules[name]['enabled'] and rules[name]['blocked'] and rules[name]['locked'], name)
            self.assertEqual(rules[name]['reason'], 'Lernmodus')
        self.assertTrue(rules['YouTube']['study_forced'])
        self.assertFalse(rules['Reddit']['study_forced'])
        for name in ('Netz', 'PC'):
            self.assertFalse(rules[name]['enabled'], name)
            self.assertNotIn('study_forced', rules[name])
        self.assertEqual(e.state['rules'], stored)

    def test_previous_state_returns_when_time_runs_out(self):
        e = engine_with_rules()
        before = e.rules(NOW)
        e.study_start(25, 'Lernen', NOW)
        self.assertIsNone(e.study_expire(NOW + 24 * MIN))
        summary = e.study_expire(NOW + 26 * MIN)
        self.assertFalse(summary['early'])
        self.assertNotIn('goal', summary)  # only the short statistics are kept
        self.assertEqual(summary['minutes'], 25)
        self.assertNotIn('study', e.state)
        after = e.rules(NOW + 26 * MIN)
        self.assertEqual([(r['enabled'], r['blocked'], r['reason']) for r in before],
                         [(r['enabled'], r['blocked'], r['reason']) for r in after])

    def test_rules_cannot_be_edited_or_deleted_to_escape(self):
        e = engine_with_rules()
        e.study_start(50, 'Lernen', NOW)
        yt = e.state['rules'][0]
        with self.assertRaises(ValueError):
            e.save(dict(yt, targets=['example.org']), NOW)
        with self.assertRaises(ValueError):
            e.mutate('delete', yt['id'], NOW)
        net = e.state['rules'][4]
        e.save(dict(net, daily_minutes=20), NOW)  # internet/device rules stay editable
        e.save(dict(name='Neu', kind='web', targets=['news.example'], enabled=False), NOW)

    def test_early_stop_needs_request_wait_and_exact_sentence(self):
        e = engine_with_rules()
        e.study_start(90, 'Lernen', NOW)
        with self.assertRaises(ValueError):
            e.study_stop(STUDY_STOP_SENTENCE, NOW)
        e.study_stop_request(NOW)
        with self.assertRaises(ValueError):
            e.study_stop(STUDY_STOP_SENTENCE, NOW + dt.timedelta(seconds=STUDY_STOP_WAIT - 1))
        with self.assertRaises(ValueError):
            e.study_stop('ich beende jetzt', NOW + dt.timedelta(seconds=STUDY_STOP_WAIT + 1))
        summary = e.study_stop('  ' + STUDY_STOP_SENTENCE.replace(' ', '  '), NOW + dt.timedelta(seconds=STUDY_STOP_WAIT + 1))
        self.assertTrue(summary['early'])
        self.assertIsNone(e.study(NOW + 2 * MIN))

    def test_stale_stop_request_expires(self):
        e = engine_with_rules()
        e.study_start(90, 'Lernen', NOW)
        e.study_stop_request(NOW)
        with self.assertRaises(ValueError):
            e.study_stop(STUDY_STOP_SENTENCE, NOW + 6 * MIN)
        self.assertIsNotNone(e.study(NOW + 6 * MIN))

    def test_reports_keep_only_short_statistics(self):
        e = engine_with_rules()
        e.study_start(50, 'Lernen', NOW)
        e.study_report(True, 'Lernen', NOW)
        e.study_report(False, '  YouTube  ', NOW)
        e.study_report(False, 'YouTube', NOW)
        e.study_report(False, 'x' * 300, NOW)
        s = e.state['study']
        self.assertEqual((s['checks'], s['drifts']), (4, 3))
        self.assertEqual(s['places']['YouTube'], 2)
        self.assertTrue(all(len(k) <= 40 for k in s['places']))
        with self.assertRaises(ValueError):
            e.study_report('ja', 'x', NOW)
        e.study_report(None, '', NOW, {'in': 2000, 'out': 150})
        e.study_report(True, '', NOW, {'in': 1000, 'out': 'x'})
        self.assertEqual(s['tokens'], {'in': 3000, 'out': 150})
        self.assertEqual(s['checks'], 5)

    def test_invalid_starts(self):
        e = engine_with_rules()
        for minutes, goal in ((0, 'x'), (241, 'x'), (25.0, 'x'), ('25', 'x'), (25, '  '), (25, 'x' * 201)):
            with self.subTest(minutes=minutes, goal=goal), self.assertRaises(ValueError):
                e.study_start(minutes, goal, NOW)
        e.study_start(25, 'x', NOW)
        with self.assertRaises(ValueError):
            e.study_start(25, 'y', NOW)


class StudyControllerTests(unittest.TestCase):
    def controller(self, folder):
        c = Controller(folder, enforce=False)
        c.engine.state['rules'] = engine_with_rules().state['rules']
        return c

    def call(self, c, role, req):
        client = Mock()
        client.username.return_value = 'user'
        with patch.object(c, 'role', return_value=(role, client)):
            return c.handle(req, os.getpid())

    def test_ui_flow_and_persistence(self):
        with tempfile.TemporaryDirectory() as folder, patch('service.installed_games', return_value=[]):
            c = self.controller(folder)
            self.call(c, 'ui', {'op': 'study_start', 'minutes': 50, 'goal': 'IPI 9.2'})
            status = self.call(c, 'ui', {'op': 'status'})
            self.assertEqual(status['study']['goal'], 'IPI 9.2')
            self.assertEqual(sum(r['reason'] == 'Lernmodus' for r in status['rules']), 4)
            again = Controller(folder, enforce=False)  # survives a service restart
            self.assertIsNotNone(again.engine.study(again.now()))
            with self.assertRaises(ValueError):
                self.call(c, 'ui', {'op': 'study_stop', 'sentence': STUDY_STOP_SENTENCE})
            self.call(c, 'ui', {'op': 'study_stop_request'})
            with self.assertRaises(ValueError):
                self.call(c, 'ui', {'op': 'study_stop', 'sentence': STUDY_STOP_SENTENCE})

    def test_tick_expires_session_and_does_not_charge_forced_rules(self):
        with tempfile.TemporaryDirectory() as folder, patch('service.installed_games', return_value=[]):
            c = self.controller(folder)
            self.call(c, 'ui', {'op': 'study_start', 'minutes': 1, 'goal': 'Lernen'})
            c.tick(None)
            ids = {r['id'] for r in c.engine.rules(c.now()) if r.get('study_forced')}
            self.assertTrue(ids)
            self.assertFalse(any(c.engine.used(i, c.now()) for i in ids))
            c.epoch += 2 * MIN  # move the service clock past the end
            c.tick(None)
            self.assertNotIn('study', c.engine.state)
            self.assertEqual(c.events[-1]['message'], 'Lernmodus beendet.')
            answer = self.call(c, 'agent', {'op': 'foreground', 'foreground': {'pid': 0, 'idle': 0}})
            self.assertIsNone(answer['study'])
            self.assertIsNotNone(answer['summary'])
            self.call(c, 'agent', {'op': 'study_ack', 'id': answer['summary']['id']})
            answer = self.call(c, 'agent', {'op': 'foreground', 'foreground': {'pid': 0, 'idle': 0}})
            self.assertIsNone(answer['summary'])

    def test_agent_reports_only_for_current_session_and_key_only_while_studying(self):
        with tempfile.TemporaryDirectory() as folder, patch('service.installed_games', return_value=[]):
            c = self.controller(folder)
            self.call(c, 'ui', {'op': 'vision_set', 'key': 'sk-ant-test-' + 'a' * 30, 'model': 'claude-haiku-5-5'})
            self.assertNotIn('sk-ant', Path(folder, 'state.json').read_text('utf-8'))
            self.assertNotIn(b'sk-ant', Path(folder, 'vision.key').read_bytes())
            with self.assertRaises(ValueError):
                self.call(c, 'agent', {'op': 'vision_config'})
            self.call(c, 'agent', {'op': 'study_start', 'minutes': 25, 'goal': 'Lernen'})
            config = self.call(c, 'agent', {'op': 'vision_config'})
            self.assertEqual(config, {'key': 'sk-ant-test-' + 'a' * 30, 'model': 'claude-haiku-5-5'})
            sid = c.engine.state['study']['id']
            self.assertEqual(self.call(c, 'agent', {'op': 'study_report', 'study': 'old', 'on_task': False, 'place': 'X'}), {'ok': False})
            self.call(c, 'agent', {'op': 'study_report', 'study': sid, 'on_task': False, 'place': 'YouTube'})
            self.assertEqual(c.engine.state['study']['drifts'], 1)
            with self.assertRaises(ValueError):
                self.call(c, 'ui', {'op': 'vision_set', 'clear': True})
            with self.assertRaises(ValueError):
                self.call(c, 'agent', {'op': 'study_stop_request'})  # only the window may end early
            with self.assertRaises(ValueError):
                self.call(c, 'native', {'op': 'study_start', 'minutes': 25, 'goal': 'x'})

    def test_invalid_key_and_model_rejected(self):
        with tempfile.TemporaryDirectory() as folder, patch('service.installed_games', return_value=[]):
            c = self.controller(folder)
            for req in ({'key': 'short'}, {'key': 'sk-ant with spaces ' + 'a' * 20}, {'model': 'gpt'}):
                with self.subTest(req=req), self.assertRaises(ValueError):
                    self.call(c, 'ui', dict(op='vision_set', **req))
            self.assertFalse(Path(folder, 'vision.key').exists())


class RoleTests(unittest.TestCase):
    def test_request_client_never_gets_agent_role(self):
        import sys as _sys
        with tempfile.TemporaryDirectory() as folder, patch('service.installed_games', return_value=[]):
            c = Controller(folder, enforce=False)
            proc = Mock()
            proc.exe.return_value = _sys.executable
            script = str(Path(__file__).resolve().parents[1] / 'src' / 'main.py')
            with patch('service.psutil.Process', return_value=proc), patch('service.sys.executable', _sys.executable):
                proc.cmdline.return_value = [_sys.executable, script, '--request', 'a.json', '--response', 'b.json', '--agent']
                self.assertEqual(c.role(1)[0], 'ui')
                proc.cmdline.return_value = [_sys.executable, script, '--agent']
                self.assertEqual(c.role(1)[0], 'agent')


class WatcherTests(unittest.TestCase):
    def test_pace_shortens_after_drifting_and_lengthens_with_focus(self):
        pace = watcher.Pace(random.Random(1))
        self.assertEqual(pace.bounds(), (180, 480))
        for _ in range(8):
            pace.record(True)
        self.assertEqual(pace.bounds(), (270, 720))
        pace.record(False)
        self.assertEqual(pace.bounds(), (120, 240))
        pace.record(False)
        self.assertEqual(pace.bounds(), (90, 180))
        pace.record(True)
        self.assertEqual(pace.bounds(), (198, 528))
        self.assertTrue(all(90 <= pace.next_delay() <= 720 for _ in range(50)))

    def test_drift_needs_confidence(self):
        self.assertTrue(watcher.is_drift({'learning': False, 'confidence': 'hoch'}))
        self.assertTrue(watcher.is_drift({'learning': False, 'confidence': 'mittel'}))
        self.assertFalse(watcher.is_drift({'learning': False, 'confidence': 'niedrig'}))
        self.assertFalse(watcher.is_drift({'learning': True, 'confidence': 'hoch'}))
        self.assertFalse(watcher.is_drift(None))

    def fake_client(self, response, beta_error=None):
        client = Mock()
        if beta_error:
            client.beta.messages.create.side_effect = beta_error
        else:
            client.beta.messages.create.return_value = response
        client.messages.create.return_value = response
        return lambda **kwargs: client

    def response(self, data, stop='end_turn'):
        block = types.SimpleNamespace(type='text', text=json.dumps(data))
        usage = types.SimpleNamespace(input_tokens=2100, output_tokens=180, cache_read_input_tokens=0, cache_creation_input_tokens=None)
        return types.SimpleNamespace(stop_reason=stop, usage=usage, content=[types.SimpleNamespace(type='thinking'), block])

    def test_assess_parses_and_sends_only_the_expected_request(self):
        data = {'learning': False, 'confidence': 'hoch', 'place': 'YouTube', 'message': 'Du schaust gerade ein Video.'}
        factory = self.fake_client(self.response(data))
        result, tokens = watcher.assess('k', 'claude-opus-5-5', 'IPI 9.2', b'\xff\xd8jpeg', 'Vordergrundprogramm: chrome.exe', factory)
        self.assertEqual(result['place'], 'YouTube')
        self.assertEqual(tokens, {'in': 2100, 'out': 180})
        call = factory().beta.messages.create.call_args.kwargs
        self.assertEqual(call['model'], 'claude-opus-5-5')
        self.assertEqual(call['output_config']['effort'], 'low')
        self.assertNotIn('thinking', call)
        self.assertNotIn('tool_choice', call)
        self.assertEqual(call['messages'][0]['content'][0]['source']['media_type'], 'image/jpeg')
        self.assertIn('IPI 9.2', call['messages'][0]['content'][1]['text'])

    def test_haiku_has_no_fallback_and_refusal_is_unknown(self):
        factory = self.fake_client(self.response({}, stop='refusal'))
        result, tokens = watcher.assess('k', 'claude-haiku-5-5', 'x', b'j', 'c', factory)
        self.assertIsNone(result)
        self.assertEqual(tokens['out'], 180)
        factory().beta.messages.create.assert_not_called()
        bad = self.fake_client(self.response({'learning': 'yes', 'confidence': 'hoch', 'place': '', 'message': ''}))
        self.assertIsNone(watcher.assess('k', 'claude-haiku-5-5', 'x', b'j', 'c', bad)[0])

    def test_capture_stays_in_memory_and_keeps_several_screens_readable(self):
        from PIL import Image
        import io
        for size, edge in (((3840, 2160), watcher.MAX_EDGE), ((7040, 1821), watcher.MAX_EDGE_WIDE)):
            with self.subTest(size=size), patch('PIL.ImageGrab.grab', return_value=Image.new('RGB', size, 'white')) as grab, \
                 patch('builtins.open', side_effect=AssertionError('no file access')):
                jpeg = watcher.capture()
            self.assertTrue(grab.call_args.kwargs['all_screens'])
            self.assertNotIn('bbox', grab.call_args.kwargs)
            self.assertTrue(jpeg.startswith(b'\xff\xd8'))
            self.assertEqual(max(Image.open(io.BytesIO(jpeg)).size), edge)


class LoginTests(unittest.TestCase):
    def test_user_folder_is_found_without_the_session_token(self):
        # An ordinary process may not query the session token; the profile list still names the signed-in user.
        with patch('win32ts.WTSQueryUserToken', side_effect=OSError('1314')), patch.dict(os.environ, {'APPDATA': r'C:\falsch'}):
            folder, how = watcher.session_appdata()
        self.assertEqual(how, 'Profilliste')
        self.assertEqual(folder, Path.home() / 'AppData' / 'Roaming')

    def profile(self, folder, name='default', pointer=None):
        base = Path(folder, 'Anthropic')
        for part in ('configs', 'credentials'):
            (base / part).mkdir(parents=True, exist_ok=True)
            (base / part / (name + '.json')).write_text('{}', 'utf-8')
        if pointer:
            (base / 'active_config').write_text(pointer, 'utf-8')
        return base

    def test_login_is_found_only_with_config_and_credentials_of_the_active_profile(self):
        with tempfile.TemporaryDirectory() as folder, patch('watcher.session_appdata', return_value=(Path(folder), 'Test')):
            self.assertIsNone(watcher.login_dir())
            base = self.profile(folder)
            self.assertEqual(watcher.login_dir(), base)
            (base / 'credentials' / 'default.json').unlink()
            self.assertIsNone(watcher.login_dir())
            self.profile(folder, 'arbeit', pointer='arbeit ')
            self.assertEqual(watcher.login_dir(), base)
            (base / 'active_config').write_text('fehlt', 'utf-8')
            self.assertIsNone(watcher.login_dir())

    def test_key_wins_and_login_is_used_without_one(self):
        calls = []
        factory = lambda **kwargs: calls.append(kwargs) or Mock()
        with tempfile.TemporaryDirectory() as folder, patch('watcher.session_appdata', return_value=(Path(folder), 'Test')), \
             patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'stale'}):
            with self.assertRaises(RuntimeError):
                watcher.make_client(None, factory)
            watcher.make_client('sk-key', factory)
            self.assertEqual(calls[-1]['api_key'], 'sk-key')
            base = self.profile(folder)
            watcher.make_client(None, factory)
            self.assertNotIn('api_key', calls[-1])
            self.assertEqual(os.environ['ANTHROPIC_CONFIG_DIR'], str(base))
            self.assertNotIn('ANTHROPIC_API_KEY', os.environ)
            os.environ.pop('ANTHROPIC_CONFIG_DIR', None)

    def test_service_is_ready_with_a_login_reported_by_the_agent(self):
        with tempfile.TemporaryDirectory() as folder, patch('service.installed_games', return_value=[]):
            c = Controller(folder, enforce=False)
            client = Mock()
            client.username.return_value = 'user'
            def call(role, req):
                with patch.object(c, 'role', return_value=(role, client)):
                    return c.handle(req, os.getpid())
            self.assertFalse(call('ui', {'op': 'status'})['vision_ready'])
            answer = call('agent', {'op': 'foreground', 'foreground': {'pid': 0, 'idle': 0}, 'vision_login': True})
            self.assertTrue(answer['vision_ready'])
            status = call('ui', {'op': 'status'})
            self.assertEqual((status['vision_ready'], status['vision_login'], status['vision_key']), (True, True, False))
            call('agent', {'op': 'foreground', 'foreground': {'pid': 0, 'idle': 0}, 'vision_login': True, 'vision_note': 'x' * 900})
            self.assertEqual(len(call('ui', {'op': 'status'})['vision_note']), 300)
            call('agent', {'op': 'study_start', 'minutes': 25, 'goal': 'Lernen'})
            self.assertIsNone(call('agent', {'op': 'vision_config'})['key'])
            call('agent', {'op': 'foreground', 'foreground': {'pid': 0, 'idle': 0}, 'vision_login': 'ja'})
            self.assertFalse(call('ui', {'op': 'status'})['vision_login'])


class MascotTests(unittest.TestCase):
    def test_every_mood_is_a_complete_distinct_face(self):
        import mascot
        faces = {}
        for mood in mascot.MOODS:
            rows = mascot.grid(mood)
            self.assertEqual(len(rows), mascot.SIZE)
            self.assertTrue(all(len(r) == mascot.SIZE for r in rows), mood)
            self.assertTrue(all(c == '.' or c in mascot.COLORS for r in rows for c in r), mood)
            faces[mood] = tuple(map(tuple, rows))
            self.assertIn(mood, mascot.SAYINGS)
        self.assertEqual(len(set(faces.values())), len(faces))

    def test_mood_follows_how_the_session_is_going(self):
        import mascot
        self.assertEqual(mascot.mood_for(0, 0), 'wach')
        self.assertEqual(mascot.mood_for(1, 0), 'zufrieden')
        self.assertEqual(mascot.mood_for(3, 0), 'stolz')
        self.assertEqual(mascot.mood_for(0, 1), 'genervt')
        self.assertEqual(mascot.mood_for(0, 2), 'traurig')
        self.assertEqual(mascot.summary_mood(9, 0), 'stolz')
        self.assertEqual(mascot.summary_mood(9, 2), 'zufrieden')
        self.assertEqual(mascot.summary_mood(4, 3), 'traurig')
        for mood in ('stolz', 'zufrieden', 'traurig'):
            self.assertIn(mood, mascot.SUMMARY_SAYINGS)


class StudyUiTests(unittest.TestCase):
    def test_dialogs_render_from_status(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from ui import Application
        from study_ui import StudyStart, StudyStop
        window = Application(auto_poll=False)
        until = (dt.datetime.now(UTC) + 30 * MIN).isoformat()
        status = {'rules': [], 'study': {'id': 's', 'goal': 'IPI 9.2', 'minutes': 50, 'until': until, 'remaining': 1800,
                                         'checks': 3, 'drifts': 1, 'places': {'YouTube': 1}, 'stop_requested': None},
                  'study_history': [], 'study_stop_sentence': STUDY_STOP_SENTENCE, 'study_stop_wait': 60,
                  'vision_ready': True, 'vision_model': 'claude-opus-5-5'}
        window.render(status)
        self.assertTrue(window.study_banner.isVisibleTo(window))
        self.assertIn('IPI 9.2', window.study_banner.text.text())
        self.assertNotIn('<', window.study_banner.text.text())  # plain-text labels show markup literally
        self.assertFalse(window.study_button.isEnabled())
        stop = StudyStop(window)
        self.assertFalse(stop.request_button.isEnabled())
        stop.entry.setText(STUDY_STOP_SENTENCE)
        self.assertTrue(stop.request_button.isEnabled())
        self.assertFalse(stop.stop_button.isEnabled())
        status['study'] = None
        status['study_history'] = [{'minutes': 49.6, 'planned_minutes': 50, 'drifts': 2, 'places': {'YouTube': 2}, 'early': False}]
        window.render(status)
        self.assertTrue(window.study_button.isEnabled())
        self.assertIn('YouTube (2×)', window.study_banner.text.text())
        StudyStart(window)
        window.close()


if __name__ == '__main__':
    unittest.main()
