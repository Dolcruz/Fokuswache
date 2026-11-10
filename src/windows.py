import ctypes
from ctypes import wintypes
import functools
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import winreg
import hashlib
import psutil
import win32api
import win32gui
import win32process
from engine import path_match

BROWSER_NAMES = {'chrome.exe', 'brave.exe', 'comet.exe', 'msedge.exe', 'firefox.exe', 'opera.exe', 'vivaldi.exe', 'waterfox.exe', 'librewolf.exe', 'floorp.exe', 'zen.exe', 'tor.exe', 'iexplore.exe', 'chromium.exe', 'browser.exe'}
BROWSER_PRODUCTS = {'google chrome', 'google chrome for testing', 'chromium', 'brave', 'brave browser', 'comet', 'perplexity comet', 'microsoft edge', 'opera', 'opera internet browser', 'opera gx', 'opera gx internet browser', 'vivaldi', 'firefox', 'mozilla firefox', 'firefox developer edition', 'firefox nightly', 'waterfox', 'librewolf', 'floorp', 'zen', 'zen browser', 'internet explorer'}

@functools.lru_cache(maxsize=2048)
def is_browser_exe(path):
    if Path(path).name.lower() == 'msedgewebview2.exe':
        return False
    if Path(path).name.lower() in BROWSER_NAMES:
        return True
    try:
        translations = win32api.GetFileVersionInfo(path, '\\VarFileInfo\\Translation')
        for lang, page in translations:
            product = win32api.GetFileVersionInfo(path, '\\StringFileInfo\\%04x%04x\\ProductName' % (lang, page)).lower()
            if product.strip() in BROWSER_PRODUCTS:
                return True
    except Exception:
        pass
    return False

def foreground():
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return {'pid': 0, 'idle': 99999, 'title': ''}
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    idle = ((ctypes.windll.kernel32.GetTickCount() & 0xffffffff) - info.dwTime) & 0xffffffff
    return {'pid': pid, 'idle': idle / 1000, 'title': win32gui.GetWindowText(hwnd)}

def browser_ancestor(pid):
    try:
        for p in psutil.Process(pid).parents():
            if is_browser_exe(p.exe()):
                while p.parent() and p.parent().exe().lower() == p.exe().lower():
                    p = p.parent()
                return p
    except (psutil.Error, OSError):
        pass
    return None

def browser_root(p):
    try:
        while p.parent() and p.parent().exe().lower() == p.exe().lower():
            p = p.parent()
    except psutil.Error:
        pass
    return p

def steam_games():
    roots = set()
    for hive, key, value in [(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                              (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')]:
        try:
            with winreg.OpenKey(hive, key) as k:
                roots.add(winreg.QueryValueEx(k, value)[0])
        except OSError:
            pass
    roots.add(r'C:\Program Files (x86)\Steam')
    for root in list(roots):
        try:
            text = (Path(root) / 'steamapps/libraryfolders.vdf').read_text(encoding='utf-8')
            roots.update(p.replace('\\\\', '\\') for p in re.findall(r'"path"\s+"([^"]+)"', text))
        except OSError:
            pass
    games = []
    for root in roots:
        for file in (Path(root) / 'steamapps').glob('appmanifest_*.acf'):
            try:
                fields = dict(re.findall(r'"([^"\r\n]+)"\s+"([^"\r\n]*)"', file.read_text(encoding='utf-8')))
                # Steam common redistributables and Wallpaper Engine are not games.
                if fields.get('appid') in ('228980', '431960'):
                    continue
                path = Path(root) / 'steamapps/common' / fields['installdir']
                games.append({'name': fields.get('name', path.name), 'path': str(path)})
            except (OSError, KeyError):
                continue
    return sorted(games, key=lambda x: x['name'].lower())

def registry_entries(key):
    """Read launcher game records in both registry views and loaded user hives.

    The service runs as SYSTEM, so HKCU alone would miss the signed-in user.
    """
    hives = [(winreg.HKEY_LOCAL_MACHINE, key)]
    try:
        with winreg.OpenKey(winreg.HKEY_USERS, '') as users:
            for i in range(winreg.QueryInfoKey(users)[0]):
                sid = winreg.EnumKey(users, i)
                if sid.startswith('S-1-5-') and not sid.endswith('_Classes'):
                    hives.append((winreg.HKEY_USERS, sid + '\\' + key))
    except OSError:
        pass
    for hive, location in hives:
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, location, 0, winreg.KEY_READ | view) as parent:
                    for i in range(winreg.QueryInfoKey(parent)[0]):
                        name = winreg.EnumKey(parent, i)
                        try:
                            with winreg.OpenKey(parent, name) as child:
                                values = dict(winreg.EnumValue(child, j)[:2] for j in range(winreg.QueryInfoKey(child)[1]))
                                yield name, values
                        except OSError:
                            continue
            except OSError:
                continue

def installed_games():
    """One catalog of installed game folders, independent of how they launch."""
    games = {}
    protected = [Path(os.environ.get('WINDIR', r'C:\Windows')), app_dir()]
    bases = {Path(os.environ.get('PROGRAMFILES', r'C:\Program Files')),
             Path(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)'))}

    def add(name, path, launcher):
        if not isinstance(path, str) or not path.strip():
            return
        if not Path(path).is_absolute():
            return
        try:
            folder = Path(os.path.expandvars(path)).resolve()
            exists = folder.is_dir()
        except (OSError, ValueError):
            return
        if not exists or folder == Path(folder.anchor) or folder in bases:
            return
        if any(path_match(str(folder), str(p)) or path_match(str(p), str(folder)) for p in protected):
            return
        key = os.path.normcase(str(folder))
        games.setdefault(key, {'name': str(name or folder.name), 'path': str(folder), 'launcher': launcher})

    for game in steam_games():
        add(game['name'], game['path'], 'Steam')
    catalogs = [(r'SOFTWARE\Ubisoft\Launcher\Installs', 'InstallDir', 'DisplayName', 'Ubisoft'),
                (r'SOFTWARE\EA Games', 'Install Dir', 'DisplayName', 'EA'),
                (r'SOFTWARE\Origin Games', 'Install Dir', 'DisplayName', 'EA'),
                (r'SOFTWARE\GOG.com\Games', 'path', 'gameName', 'GOG')]
    for key, path_field, name_field, launcher in catalogs:
        for _, values in registry_entries(key):
            path = values.get(path_field)
            add(values.get(name_field), path, launcher)

    # EA also installs games without a game-specific registry record.
    for base in bases:
        for library in ('EA Games', 'Origin Games'):
            for folder in (base / library).glob('*'):
                add(folder.name, str(folder), 'EA')

    manifests = Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData')) / 'Epic/EpicGamesLauncher/Data/Manifests'
    for file in manifests.glob('*.item'):
        try:
            item = json.loads(file.read_text(encoding='utf-8-sig'))
            # Engine/editor installations share the manifest directory with games.
            if not item.get('bIsApplication') or str(item.get('AppName', '')).startswith('UE_'):
                continue
            categories = item.get('AppCategories', [])
            if categories and 'games' not in categories:
                continue
            add(item.get('DisplayName'), item.get('InstallLocation'), 'Epic')
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return sorted(games.values(), key=lambda x: x['name'].casefold())

def terminate(p):
    try:
        children = p.children(recursive=True)
        p.kill()
        for c in children:
            try:
                c.kill()
            except psutil.Error:
                pass
        return True
    except psutil.NoSuchProcess:
        return True
    except psutil.Error:
        return False

class Firewall:
    """Only owns its two named rules; never changes profile defaults."""
    def __init__(self):
        import win32com.client
        self.policy = win32com.client.Dispatch('HNetCfg.FwPolicy2')
        self.rules = self.policy.Rules
        self.names = ['FokusWache - Gesamtnetz ausgehend', 'FokusWache - Gesamtnetz eingehend']
        self.enabled = None
        self.browser_state = {}

    def browser_block(self, path, blocked):
        path = os.path.normcase(path)
        if self.browser_state.get(path) == blocked:
            return
        self.browser_state.pop(path, None)
        import win32com.client
        name = 'FokusWache - Browser ' + hashlib.sha256(path.encode()).hexdigest()[:16]
        self.rules.Remove(name)
        if blocked:
            rule = win32com.client.Dispatch('HNetCfg.FWRule')
            rule.Name = name
            rule.ApplicationName = path
            rule.Description = 'Kein Browsernetz ohne bestätigte FokusWache-Erweiterung.'
            rule.Protocol = 256
            rule.Direction = 2
            rule.Action = 0
            rule.Profiles = 2147483647
            rule.Enabled = True
            self.rules.Add(rule)
        self.browser_state[path] = blocked

    def set_blocked(self, blocked):
        if self.enabled == blocked:
            return
        # A failed multi-rule update leaves the actual state unconfirmed.
        self.enabled = None
        import win32com.client
        for name, direction in zip(self.names, (2, 1)):
            self.rules.Remove(name)
            if blocked:
                rule = win32com.client.Dispatch('HNetCfg.FWRule')
                rule.Name = name
                rule.Description = 'Zeitlich gesteuerte Gesamtnetzsperre von FokusWache.'
                rule.Protocol = 256
                rule.Direction = direction
                rule.Action = 0
                rule.Profiles = 2147483647
                rule.Enabled = True
                self.rules.Add(rule)
        self.enabled = blocked

def perform_device(action):
    if action == 'lock':
        if not ctypes.windll.user32.LockWorkStation():
            raise OSError('Windows konnte nicht gesperrt werden.')
    elif action == 'logoff':
        # No force flag: applications retain the chance to save documents.
        if not ctypes.windll.user32.ExitWindowsEx(0, 0):
            raise OSError('Windows konnte nicht abgemeldet werden.')
    elif action == 'shutdown':
        subprocess.run([str(Path(os.environ['WINDIR']) / 'System32/shutdown.exe'), '/s', '/t', '0'], check=True, creationflags=0x08000000)

def app_dir():
    return Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent

def session_id(pid):
    value = ctypes.c_ulong()
    if not ctypes.windll.kernel32.ProcessIdToSessionId(pid, ctypes.byref(value)):
        raise OSError('Windows-Sitzung konnte nicht ermittelt werden.')
    return value.value

def ensure_session_agents(known_pids=None):
    """SYSTEM-owned session observer: ordinary Task Manager cannot terminate it."""
    import win32ts
    import win32security
    agents = set()
    if known_pids:
        candidates = []
        for pid in known_pids:
            try:
                p = psutil.Process(pid)
                p.info = p.as_dict(attrs=['pid', 'exe', 'cmdline'])
                candidates.append(p)
            except psutil.Error:
                pass
    else:
        candidates = psutil.process_iter(['pid', 'exe', 'cmdline'])
    for p in candidates:
        try:
            if p.info['exe'] and Path(p.info['exe']).resolve() == Path(sys.executable).resolve() and '--agent' in (p.info['cmdline'] or []):
                agents.add(session_id(p.pid))
        except (psutil.Error, OSError):
            pass
    for session in win32ts.WTSEnumerateSessions(None, 1, 0):
        sid = session['SessionId']
        if session['State'] != win32ts.WTSActive or sid == 0 or sid in agents:
            continue
        token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32security.TOKEN_ALL_ACCESS)
        child = None
        try:
            child = win32security.DuplicateTokenEx(token, win32security.SecurityImpersonation, win32security.TOKEN_ALL_ACCESS, win32security.TokenPrimary)
            win32security.SetTokenInformation(child, win32security.TokenSessionId, sid)
            startup = win32process.STARTUPINFO()
            startup.lpDesktop = r'winsta0\default'
            hp, ht, _, _ = win32process.CreateProcessAsUser(child, str(sys.executable), '"' + sys.executable + '" --agent', None, None, False, 0x08000000, None, str(app_dir()), startup)
            win32api.CloseHandle(hp)
            win32api.CloseHandle(ht)
        finally:
            if child is not None:
                child.Close()
            token.Close()
