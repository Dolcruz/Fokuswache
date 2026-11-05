"""Pure policy engine: central counters, restrictions, and irreversible timed locks."""
import copy
import datetime as dt
import math
import os
import re
import unicodedata
import uuid
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
ZONE = ZoneInfo('Europe/Berlin')

def timestamp(value):
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Zeitpunkt muss eine Zeitzone enthalten.')
    return parsed.astimezone(UTC)

def web_target(pattern):
    """Split a web target the way browsers report URLs: punycode host, percent-encoded path."""
    p = urlsplit(pattern if '://' in pattern else 'https://' + pattern.lstrip('*.'))
    host = unicodedata.normalize('NFKC', p.hostname or '').lower()
    host = '.'.join(x if x.isascii() else 'xn--' + x.encode('punycode').decode('ascii') for x in host.split('.'))
    path = ''.join(c if c.isascii() and c not in ' "<>`{}' else quote(c) for c in p.path)
    return p, host, path

def host_match(url, pattern):
    try:
        u = urlsplit(url)
        if u.scheme not in ('http', 'https', 'ws', 'wss'):
            return False
        if pattern == '*':
            return True
        _, target, path = web_target(pattern)
        host, target = (u.hostname or '').lower().rstrip('.'), target.rstrip('.')
        return bool(target) and (host == target or host.endswith('.' + target)) and (path in ('', '/') or u.path.startswith(path))
    except ValueError:
        return False

def web_match(rule, url):
    return any(host_match(url, p) for p in rule['targets']) and not any(host_match(url, p) for p in rule['exceptions'])

def path_match(path, target):
    path = os.path.normcase(os.path.abspath(path))
    target = os.path.normcase(os.path.abspath(target)).rstrip('\\/')
    return path == target or path.startswith(target + os.sep)

def in_schedule(s, local):
    minute = local.hour * 60 + local.minute
    start = int(s['start'][:2]) * 60 + int(s['start'][3:])
    end = int(s['end'][:2]) * 60 + int(s['end'][3:])
    today = local.weekday()
    if start == end:
        return today in s['days']
    if start < end:
        return today in s['days'] and start <= minute < end
    return (today in s['days'] and minute >= start) or ((today - 1) % 7 in s['days'] and minute < end)

def locked(rule, now):
    end = timestamp(rule.get('locked_until'))
    return bool(end and now < end)

def decision(rule, used, now, local=None):
    if not rule['enabled']:
        return False, 'Deaktiviert'
    local = local or now.astimezone(ZONE)
    if rule.get('daily_minutes') is not None and used >= rule['daily_minutes'] * 60:
        return True, 'Tageslimit erreicht'
    if rule['schedules']:
        inside = any(in_schedule(s, local) for s in rule['schedules'])
        if (rule['schedule_mode'] == 'allowed' and not inside) or (rule['schedule_mode'] == 'blocked' and inside):
            return True, 'Zeitplan'
    end = timestamp(rule.get('timer_until'))
    if end and now < end:
        return True, 'Fokus-Timer'
    if not rule['schedules'] and rule.get('daily_minutes') is None and not rule.get('timer_until'):
        return True, 'Dauersperre'
    return False, 'Freigegeben'

def validate_rule(raw):
    r = {'id': raw.get('id') or str(uuid.uuid4()), 'name': str(raw.get('name', '')).strip(),
         'kind': raw.get('kind', 'web'), 'targets': raw.get('targets', []), 'exceptions': raw.get('exceptions', []),
         'enabled': raw.get('enabled', False), 'daily_minutes': raw.get('daily_minutes'),
         'schedules': raw.get('schedules', []), 'schedule_mode': raw.get('schedule_mode', 'allowed'),
         'timer_until': raw.get('timer_until'), 'locked_until': raw.get('locked_until'),
         'device_action': raw.get('device_action', 'lock')}
    if not r['name'] or len(r['name']) > 100:
        raise ValueError('Name erforderlich (maximal 100 Zeichen).')
    if not isinstance(r['id'], str) or len(r['id']) > 80:
        raise ValueError('Ungültige Regel-ID.')
    if r['kind'] not in ('web', 'apps', 'games', 'internet', 'device'):
        raise ValueError('Unbekannte Regelart.')
    if type(r['enabled']) is not bool:
        raise ValueError('Aktivierung muss wahr/falsch sein.')
    for field in ('targets', 'exceptions'):
        if not isinstance(r[field], list) or len(r[field]) > 500 or any(not isinstance(x, str) or not x.strip() or len(x) > 1024 for x in r[field]):
            raise ValueError('Ungültige Zielliste.')
        r[field] = list(dict.fromkeys(x.strip() for x in r[field]))
    if r['kind'] in ('web', 'apps') and not r['targets']:
        raise ValueError('Mindestens ein Ziel erforderlich.')
    if r['kind'] == 'web':
        for pattern in r['targets'] + r['exceptions']:
            if pattern == '*':
                continue
            p = urlsplit(pattern if '://' in pattern else 'https://' + pattern.lstrip('*.'))
            if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.query or p.fragment or '*' in pattern.lstrip('*.'):
                raise ValueError('Web-Ziele: Domain oder Domain/Pfad, ohne Suchparameter.')
        for pattern in r['exceptions']:
            if pattern != '*':
                p = urlsplit(pattern if '://' in pattern else 'https://' + pattern.lstrip('*.'))
                if p.path not in ('', '/'):
                    raise ValueError('Web-Ausnahmen gelten für vollständige Domains, nicht einzelne Pfade.')
    if r['kind'] in ('apps', 'games'):
        for p in r['targets'] + r['exceptions']:
            if not os.path.isabs(p):
                raise ValueError('Programme benötigen absolute Datei- oder Ordnerpfade.')
            protected = [os.environ.get('WINDIR', 'C:\\Windows'), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
            if any(path_match(p, x) or path_match(x, p) for x in protected):
                raise ValueError('Windows und FokusWache selbst dürfen nicht als Programmziel gesperrt werden.')
    if r['kind'] in ('internet', 'device') and (r['targets'] or r['exceptions']):
        raise ValueError('Diese Regelart verwendet keine Zielliste. Für Web-Ausnahmen bitte Webseiten wählen.')
    v = r['daily_minutes']
    if v is not None and (type(v) not in (int, float) or not math.isfinite(v) or v <= 0 or v > 1440):
        raise ValueError('Tageslimit muss zwischen 0 und 1440 Minuten liegen.')
    if r['schedule_mode'] not in ('allowed', 'blocked') or not isinstance(r['schedules'], list) or len(r['schedules']) > 50:
        raise ValueError('Ungültiger Zeitplan.')
    for s in r['schedules']:
        if not isinstance(s, dict) or not isinstance(s.get('days'), list) or not s['days'] or any(type(d) is not int or d not in range(7) for d in s['days']):
            raise ValueError('Zeitplan benötigt gültige Wochentage.')
        for k in ('start', 'end'):
            if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', str(s.get(k, ''))):
                raise ValueError('Zeitplan verwendet HH:MM.')
    for k in ('timer_until', 'locked_until'):
        timestamp(r[k])
    if r['device_action'] not in ('lock', 'logoff', 'shutdown'):
        raise ValueError('Ungültige Geräteaktion.')
    return r

class Engine:
    def __init__(self, state=None):
        self.state = state or {'rules': [], 'usage': {}, 'last_time': None}
        for rule in self.state['rules']:
            if rule['kind'] == 'steam':
                rule['kind'] = 'games'
                if rule['name'] == 'Steam-Spiele':
                    rule['name'] = 'Spiele'

    def used(self, rule_id, now):
        return self.state['usage'].get(now.astimezone(ZONE).date().isoformat(), {}).get(rule_id, 0)

    def charge(self, ids, seconds, now):
        if not math.isfinite(seconds) or seconds < 0 or seconds > 3:
            return
        day = now.astimezone(ZONE).date().isoformat()
        daily = self.state['usage'].setdefault(day, {})
        for rid in set(ids):
            daily[rid] = daily.get(rid, 0) + seconds

    def rules(self, now):
        result = []
        for rule in self.state['rules']:
            r = copy.deepcopy(rule)
            r['used_seconds'] = self.used(r['id'], now)
            r['blocked'], r['reason'] = decision(r, r['used_seconds'], now)
            r['locked'] = locked(r, now)
            result.append(r)
        return result

    def save(self, raw, now):
        r = validate_rule(raw)
        old = next((x for x in self.state['rules'] if x['id'] == r['id']), None)
        if old and locked(old, now):
            raise ValueError('Diese Regel ist bis zum Ablauf verriegelt.')
        if old:
            r['locked_until'], r['timer_until'] = old['locked_until'], old['timer_until']
            self.state['rules'][self.state['rules'].index(old)] = r
        else:
            r['locked_until'], r['timer_until'] = None, None
            self.state['rules'].append(r)
        return r

    def mutate(self, op, rid, now, until=None, minutes=None):
        r = next((x for x in self.state['rules'] if x['id'] == rid), None)
        if not r:
            raise ValueError('Regel nicht gefunden.')
        if locked(r, now):
            raise ValueError('Diese Regel ist bis zum Ablauf verriegelt.')
        if op == 'delete':
            self.state['rules'].remove(r)
        elif op == 'lock':
            end = timestamp(until)
            if not end or end <= now or end > now + dt.timedelta(days=366):
                raise ValueError('Verriegelung: Zeitpunkt in der Zukunft, höchstens 366 Tage.')
            if not r['enabled']:
                raise ValueError('Regel zuerst aktivieren.')
            r['locked_until'] = end.isoformat()
        elif op == 'timer':
            if type(minutes) not in (int, float) or not math.isfinite(minutes) or not 0 < minutes <= 527040:
                raise ValueError('Ungültige Timerdauer.')
            r['enabled'] = True
            end = now + dt.timedelta(minutes=minutes)
            r['timer_until'] = r['locked_until'] = end.isoformat()
        else:
            raise ValueError('Unbekannte Operation.')

def presets():
    return [validate_rule({'name': 'Spiele', 'kind': 'games', 'daily_minutes': 120}),
            validate_rule({'name': 'Twitter / X', 'kind': 'web', 'targets': ['twitter.com', 'x.com'], 'daily_minutes': 30})]
