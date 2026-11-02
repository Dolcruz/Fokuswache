import copy
import ctypes
import datetime as dt
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback

import psutil
import pythoncom
import pywintypes
import win32file
import win32pipe
import win32security
import win32service
import win32serviceutil
import servicemanager

from engine import Engine, UTC, decision, locked, path_match, presets, timestamp, web_match
from ipc import PIPE, MAX_MESSAGE
from windows import Firewall, app_dir, browser_ancestor, browser_root, is_browser_exe, installed_games, terminate, ensure_session_agents

DATA = Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData')) / 'FokusWache'
BROWSER_CONNECTION_LEASE = 12

class Controller:
    def __init__(self, data=DATA, enforce=True):
        self.data = Path(data)
        self.data.mkdir(parents=True, exist_ok=True)
        self.file = self.data / 'state.json'
        self.mutex = threading.RLock()
        self.stop = threading.Event()
        self.enforce = enforce
        if self.file.exists():
            state = json.loads(self.file.read_text('utf-8'))
            if not isinstance(state.get('rules'), list) or not isinstance(state.get('usage'), dict):
                raise ValueError('Gespeicherte Regeln sind beschädigt; keine leeren Ersatzregeln angelegt.')
            self.engine = Engine(state)
        else:
            self.engine = Engine()
            self.engine.state['rules'] = presets()
        now = dt.datetime.now(UTC)
        saved = timestamp(self.engine.state.get('last_time'))
        self.epoch = max(now, saved) if saved else now
        self.started = time.monotonic()
        self.last_tick = self.started
        self.agents = {}
        self.agent_pids = set()
        self.hosts = {}
        self.browsers = []
        self.games = installed_games()
        self.last_discovery = 0
        self.last_agent_check = 0
        self.sample_interval = 0
        self.browser_confirmed = {}
        self.browser_blocked = set()
        known_paths = set(self.engine.state.get('browser_paths', []))
        self.browser_paths = {p for p in known_paths if is_browser_exe(p)}
        self.stale_browser_paths = known_paths - self.browser_paths
        for base in (Path(os.environ.get('PROGRAMFILES', r'C:\Program Files')), Path(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)'))):
            for suffix in ('Google/Chrome/Application/chrome.exe', 'BraveSoftware/Brave-Browser/Application/brave.exe', 'Microsoft/Edge/Application/msedge.exe', 'Mozilla Firefox/firefox.exe'):
                if (base / suffix).exists():
                    self.browser_paths.add(str(base / suffix))
        self.pending = {}
        self.errors = []
        self.events = self.engine.state.get('events', [])[-100:]
        self.previous_ids = set()
        self.persist()

    def now(self):
        return self.epoch + dt.timedelta(seconds=time.monotonic() - self.started)

    def persist(self):
        self.engine.state['last_time'] = self.now().isoformat()
        self.engine.state['events'] = self.events[-100:]
        tmp = self.file.with_suffix('.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(self.engine.state, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.file)

    def event(self, message):
        if self.events and self.events[-1]['message'] == message:
            return
        self.events.append({'time': self.now().astimezone().isoformat(), 'message': message})
        self.events = self.events[-100:]

    def role(self, pid):
        p = psutil.Process(pid)
        expected = Path(sys.executable).resolve()
        client = Path(p.exe()).resolve()
        native_exe = expected.with_name('FokusWacheNative.exe')
        if client not in (expected, native_exe):
            raise ValueError('Nicht autorisierter IPC-Client.')
        args = p.cmdline()
        if not getattr(sys, 'frozen', False):
            # Source mode is a development-only process, never used by installed service.
            expected_script = Path(__file__).with_name('main.py').resolve()
            if not any(Path(a).resolve() == expected_script for a in args[1:] if a.endswith('.py')):
                raise ValueError('Nicht autorisierter Entwicklungsclient.')
        if '--native' in args or client == native_exe:
            root = browser_ancestor(pid)
            if not root:
                raise ValueError('Browser-Herkunft konnte nicht bestätigt werden.')
            return 'native', root
        if '--agent' in args:
            return 'agent', p
        return 'ui', p

    def handle(self, req, pid):
        with self.mutex:
            role, process = self.role(pid)
            op = req.get('op')
            now, mono = self.now(), time.monotonic()
            if role == 'native' and op == 'pulse':
                tabs = req.get('tabs', [])
                if not isinstance(tabs, list) or len(tabs) > 5000:
                    raise ValueError('Ungültige Browsermeldung.')
                tabs = [{'id': x['id'], 'url': str(x.get('url', ''))[:8192]} for x in tabs if isinstance(x, dict) and type(x.get('id')) is int]
                active = str(req.get('active_url', ''))[:8192] if req.get('focused') else ''
                fg = req.get('foreground', {})
                self.hosts[pid] = {'root': process.pid, 'created': process.create_time(), 'time': mono,
                                   'url': active, 'fg': fg, 'focused': bool(req.get('focused')), 'name': process.name(), 'ready': bool(req.get('ready'))}
                rules = self.engine.rules(now)
                web_rules = [r for r in rules if r['enabled'] and r['kind'] == 'web']
                blocked_rules = [r for r in web_rules if r['blocked']]
                blocked_tabs = [t['id'] for t in tabs if any(web_match(r, t['url']) for r in blocked_rules)]
                return {'blocked_tabs': blocked_tabs, 'web_rules': blocked_rules,
                        'watching': bool(web_rules), 'time': now.isoformat()}
            if role == 'agent' and op == 'foreground':
                self.agent_pids.add(pid)
                self.agents[pid] = {'time': mono, 'fg': req.get('foreground', {}), 'session': process.username()}
                # Agent acknowledges display and execution; the service remains the authority.
                return {'pending': [dict(p, remaining=max(0, (timestamp(p['due'])-now).total_seconds())) for p in self.pending.values()], 'events': self.events[-5:]}
            if role != 'ui':
                raise ValueError('Operation für diesen Client nicht erlaubt.')
            if op == 'status':
                return {'rules': self.engine.rules(now), 'browsers': self.browsers, 'games': self.games,
                        'events': self.events[-30:], 'service_time': now.isoformat(),
                        'sample_interval': self.sample_interval,
                        'activity': [{'pid': a['fg'].get('pid'), 'idle': a['fg'].get('idle'), 'age': mono-a['time']} for a in self.agents.values()],
                        'protection': 'Windows-Dienst', 'errors': self.errors,
                        'extension_path': str(app_dir() / 'extensions')}
            if op not in ('save', 'delete', 'lock', 'timer'):
                raise ValueError('Unbekannte Operation.')
            before = copy.deepcopy(self.engine.state)
            try:
                if op == 'save':
                    self.engine.save(req['rule'], now)
                else:
                    self.engine.mutate(op, req.get('id'), now, req.get('until'), req.get('minutes'))
                self.persist()
            except Exception:
                self.engine.state = before
                raise
            self.event('Regel gespeichert.' if op == 'save' else {'delete': 'Regel gelöscht.', 'lock': 'Regel verriegelt.', 'timer': 'Fokus-Timer gestartet.'}[op])
            return {'ok': True}

    def app_matches(self, rule, path):
        targets = rule['targets'] + ([g['path'] for g in self.games] if rule['kind'] == 'games' else [])
        return any(path_match(path, p) for p in targets) and not any(path_match(path, p) for p in rule['exceptions'])

    def tick(self, firewall):
        with self.mutex:
            mono, now = time.monotonic(), self.now()
            elapsed = mono - self.last_tick
            self.sample_interval = elapsed
            self.last_tick = mono
            self.errors = []
            if mono - self.last_discovery > 30:
                self.games = installed_games()
                self.last_discovery = mono
            self.hosts = {pid: h for pid, h in self.hosts.items() if mono - h['time'] < 3 and psutil.pid_exists(pid)}
            self.agents = {pid: a for pid, a in self.agents.items() if mono - a['time'] < 3 and psutil.pid_exists(pid)}
            rules = self.engine.rules(now)
            active_rules = [r for r in rules if r['enabled']]
            ids = set()
            foregrounds = [a['fg'] for a in self.agents.values()]
            foregrounds += [h['fg'] for h in self.hosts.values()]
            for fg in foregrounds:
                try:
                    p = psutil.Process(int(fg.get('pid', 0)))
                    path = p.exe()
                    for r in active_rules:
                        if r['kind'] in ('apps', 'games') and self.app_matches(r, path):
                            ids.add(r['id'])
                        if r['kind'] in ('device', 'internet') and fg.get('idle', 999) < 60:
                            ids.add(r['id'])
                except (psutil.Error, ValueError):
                    pass
            for h in self.hosts.values():
                if not h['focused'] or h['fg'].get('idle', 999) >= 60:
                    continue
                try:
                    fgroot = browser_root(psutil.Process(h['fg'].get('pid', 0)))
                    if fgroot.pid != h['root']:
                        continue
                except psutil.Error:
                    continue
                for r in active_rules:
                    if r['kind'] == 'web' and web_match(r, h['url']):
                        ids.add(r['id'])
            # Require activity at both boundaries; never charge time asleep or offline.
            self.engine.charge(ids & self.previous_ids, elapsed, now)
            self.previous_ids = ids
            rules = self.engine.rules(now)
            web_on = any(r['enabled'] and r['kind'] == 'web' for r in rules)
            blocked_apps = [r for r in rules if r['blocked'] and r['kind'] in ('apps', 'games')]
            roots = {}
            processes = {p.pid: p for p in psutil.process_iter(['pid', 'name', 'exe', 'ppid'])}
            for p in processes.values():
                path = p.info.get('exe')
                if not path:
                    continue
                try:
                    if is_browser_exe(path):
                        root = p
                        while root.info['ppid'] in processes:
                            parent = processes[root.info['ppid']]
                            if not parent.info['exe'] or parent.info['exe'].lower() != path.lower():
                                break
                            root = parent
                        roots[root.pid] = root
                    if self.enforce and any(self.app_matches(r, path) for r in blocked_apps):
                        if terminate(p):
                            self.event('Programm gesperrt: ' + p.info['name'])
                        else:
                            self.errors.append('Programm konnte nicht beendet werden: ' + path)
                except psutil.Error:
                    pass
            self.browsers = []
            path_ready = {}
            browser_keys = set()
            blocked_keys = set()
            current_fg = {f.get('pid') for f in foregrounds}
            for pid, p in roots.items():
                try:
                    key = (pid, p.create_time())
                    browser_keys.add(key)
                    connected = [h for h in self.hosts.values() if h['root'] == pid and h['created'] == p.create_time() and h['ready']]
                    # A second browser profile cannot borrow an inactive profile's pulse.
                    fg_in_root = pid in current_fg
                    focused_ok = any(h['focused'] for h in connected)
                    okay = bool(connected) and (not fg_in_root or focused_ok)
                    if okay:
                        self.browser_confirmed[key] = max(h['time'] for h in connected)
                    confirmed = self.browser_confirmed.get(key)
                    # A successful handshake grants a short renewable connection lease.
                    # A new/unconfirmed browser has no lease; a brief interruption of an
                    # established connection does not destroy the user's browser session.
                    lease_valid = confirmed is not None and mono - confirmed < BROWSER_CONNECTION_LEASE
                    network_blocked = web_on and not lease_valid
                    reason = ('Aktives Browserfenster nicht bestätigt' if connected else
                              'Verbindung zur Erweiterung unterbrochen' if confirmed is not None else
                              'Erweiterung noch nicht verbunden')
                    path = p.exe()
                    self.browser_paths.add(path)
                    path_ready[path] = path_ready.get(path, True) and lease_valid
                    self.browsers.append({'name': p.name(), 'pid': pid, 'connected': okay,
                                          'network_blocked': network_blocked,
                                          'connection_reason': '' if okay else reason})
                    if network_blocked:
                        blocked_keys.add(key)
                        self.errors.append(p.name() + ': Netzwerk pausiert. ' + reason + '.')
                        if key not in self.browser_blocked:
                            self.event('Browsernetz pausiert: ' + p.name() + ' · ' + reason + '. Tabs bleiben geöffnet.')
                    elif key in self.browser_blocked:
                        self.event('Browsernetz freigegeben: ' + p.name())
                except psutil.Error:
                    pass
            self.browser_confirmed = {k: t for k, t in self.browser_confirmed.items() if k in browser_keys}
            self.browser_blocked = blocked_keys
            if self.enforce:
                for path in self.stale_browser_paths:
                    firewall.browser_block(path, False)
                self.stale_browser_paths.clear()
                for path in self.browser_paths:
                    try:
                        firewall.browser_block(path, web_on and not path_ready.get(path, False))
                    except Exception as e:
                        self.errors.append('Browsersperre nicht bestätigt: ' + str(e))
            self.engine.state['browser_paths'] = sorted(self.browser_paths)
            net_blocked = any(r['blocked'] and r['kind'] == 'internet' for r in rules)
            if self.enforce:
                try:
                    firewall.set_blocked(net_blocked)
                except Exception as e:
                    self.errors.append('Netzsperre nicht bestätigt: ' + str(e))
            device = [r for r in rules if r['blocked'] and r['kind'] == 'device']
            wanted = {r['id'] for r in device}
            self.pending = {k: v for k, v in self.pending.items() if k in wanted}
            for r in device:
                self.pending.setdefault(r['id'], {'id': r['id'], 'name': r['name'], 'action': r['device_action'],
                                                  'due': (now + dt.timedelta(seconds=60)).isoformat()})
            if active_rules and not self.agents:
                self.errors.append('Nutzungserfassung in der Windows-Sitzung nicht verbunden.')
            self.persist()

    def run_ticks(self):
        pythoncom.CoInitialize()
        try:
            fw = Firewall() if self.enforce else None
            while not self.stop.is_set():
                began = time.monotonic()
                try:
                    if self.enforce and began - self.last_agent_check >= 10:
                        self.agent_pids = {pid for pid in self.agent_pids if psutil.pid_exists(pid)}
                        ensure_session_agents(self.agent_pids)
                        self.last_agent_check = time.monotonic()
                    self.tick(fw)
                except Exception as e:
                    with self.mutex:
                        self.errors = ['Dienstfehler: ' + str(e)]
                        self.event('Dienstfehler: ' + str(e))
                    with (self.data / 'errors.log').open('a', encoding='utf-8') as f:
                        f.write(traceback.format_exc())
                self.stop.wait(max(.05, 1 - (time.monotonic() - began)))
        finally:
            pythoncom.CoUninitialize()

    def serve(self):
        security = pywintypes.SECURITY_ATTRIBUTES()
        security.SECURITY_DESCRIPTOR = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
            'D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;IU)', win32security.SDDL_REVISION_1)
        threading.Thread(target=self.run_ticks, daemon=True).start()
        while not self.stop.is_set():
            h = win32pipe.CreateNamedPipe(PIPE, win32pipe.PIPE_ACCESS_DUPLEX,
                    win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT | 8,
                    32, MAX_MESSAGE, MAX_MESSAGE, 3000, security)
            try:
                win32pipe.ConnectNamedPipe(h, None)
                pid = ctypes.c_ulong()
                if not ctypes.windll.kernel32.GetNamedPipeClientProcessId(int(h), ctypes.byref(pid)):
                    raise OSError('Client-ID nicht lesbar.')
                self.role(pid.value)
                threading.Thread(target=self.connection, args=(h, pid.value), daemon=True).start()
            except Exception:
                win32file.CloseHandle(h)

    def connection(self, h, pid):
        try:
            _, raw = win32file.ReadFile(h, MAX_MESSAGE)
            try:
                result = self.handle(json.loads(raw), pid)
            except Exception as e:
                result = {'error': str(e)}
            win32file.WriteFile(h, json.dumps(result, ensure_ascii=False).encode('utf-8'))
            win32file.FlushFileBuffers(h)
        except (pywintypes.error, OSError):
            pass
        finally:
            win32file.CloseHandle(h)

class FokusService(win32serviceutil.ServiceFramework):
    _svc_name_ = 'FokusWache'
    _svc_display_name_ = 'FokusWache Sperrdienst'
    _svc_description_ = 'Zentrale Zeitkonten und Sperrregeln von FokusWache.'

    def SvcStop(self):
        # Service permissions reserve stop for administrators; an administrator remains able to repair Windows.
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.ReportServiceStatus(win32service.SERVICE_STOPPED)
        os._exit(0)

    def SvcDoRun(self):
        try:
            Controller().serve()
        except Exception:
            DATA.mkdir(parents=True, exist_ok=True)
            (DATA / 'startup-error.log').write_text(traceback.format_exc(), encoding='utf-8')
            raise
