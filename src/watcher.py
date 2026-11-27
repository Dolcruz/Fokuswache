"""Learning-session watcher: in-memory screenshot, one vision call, adaptive pacing.

The screenshot exists only as bytes in memory for the duration of one check. It is never
written to disk, sent through the local pipe, or logged. Only a yes/no result and a short
place label (e.g. "YouTube") reach the service.
"""
import base64
import ctypes
from ctypes import wintypes
import io
import json
import os
from pathlib import Path
import random

MAX_EDGE = 1568        # one screen
MAX_EDGE_WIDE = 2576   # several screens side by side in one picture
SYSTEM_PROMPT = """Du bist der Lern-Aufpasser von FokusWache. Du bekommst einen Screenshot vom Bildschirm einer Person, \
die gerade lernen möchte, und ihr eigenes Lernziel in einem Satz. Hat sie mehrere Bildschirme, zeigt das Bild alle nebeneinander. Beurteile nur, ob sie in diesem Moment an diesem Ziel arbeitet.

Als Lernen zählt alles, was plausibel zum Ziel gehört: Skript, Folien oder PDF lesen, Übungsblätter, Lerntrainer, Quiz, \
Code-Editor oder Terminal, Notizen, Suche, Dokumentation, Wikipedia oder ein KI-Chat zum Thema, Dateien öffnen, Fenster sortieren. \
Ein Musikplayer oder eine Uhr nebenbei ist kein Abdriften. Auf einem Nebenbildschirm zählt nur, was dort erkennbar gerade läuft oder benutzt wird (Video, Stream, Spiel, Feed); ein bloß offenes, ruhendes Fenster wie eine Chatliste, ein Postfach oder ein anderes Programm zählt nicht. Im Zweifel gilt: lernt.

Abgedriftet ist, wer gerade sichtbar etwas ohne Bezug zum Ziel tut: Videos, Streams, Serien, Social Media, Messenger-Chats, \
News, Shopping, Spiele, Foren oder Webseiten zu anderen Themen.

Eine Sperrseite von FokusWache bedeutet nur einen kurzen Versuch; bewerte sie mit confidence "niedrig".
Der kleine Pixel-Hund am Bildschirmrand gehört zu FokusWache. Beachte ihn nicht.

Antwortfelder:
- learning: true oder false
- confidence: "hoch", "mittel" oder "niedrig"
- place: bei Abdriften ein kurzer Name der Ablenkung, höchstens drei Wörter (z. B. "YouTube", "WhatsApp", "Reddit", "Spiel"). \
Keine Adressen, keine Personennamen, keine Inhalte. Beim Lernen "Lernen".
- message: nur bei Abdriften ein bis zwei kurze, freundliche Sätze auf Deutsch in der Du-Form: konkret sagen, was du siehst, \
und zum Ziel zurücklenken. Kein Vorwurf, keine Ausrufezeichen-Ketten, keine privaten Inhalte wiedergeben. Beim Lernen leer."""

SCHEMA = {
    'type': 'object',
    'properties': {
        'learning': {'type': 'boolean'},
        'confidence': {'type': 'string', 'enum': ['hoch', 'mittel', 'niedrig']},
        'place': {'type': 'string'},
        'message': {'type': 'string'},
    },
    'required': ['learning', 'confidence', 'place', 'message'],
    'additionalProperties': False,
}
# Server-side refusal fallback exists for Opus/Sonnet 5.5, not for Haiku 5.5.
FALLBACK_MODELS = ('claude-opus-5-5', 'claude-sonnet-5-5')


class Pace:
    """Random gaps of about 3-8 minutes; shorter after drifting, longer after steady learning."""
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.focus_streak = 0
        self.drift_streak = 0

    def record(self, on_task):
        if on_task:
            self.focus_streak += 1
            self.drift_streak = 0
        else:
            self.drift_streak += 1
            self.focus_streak = 0

    def bounds(self):
        if self.drift_streak >= 2:
            return 90, 180
        if self.drift_streak == 1:
            return 120, 240
        factor = 1 + min(self.focus_streak, 5) * 0.1
        return round(180 * factor), round(480 * factor)

    def next_delay(self, failed=False):
        if failed:
            return self.rng.uniform(120, 240)
        return self.rng.uniform(*self.bounds())


def is_drift(result):
    return bool(result) and result['learning'] is False and result['confidence'] in ('hoch', 'mittel')


class RECT(ctypes.Structure):
    _fields_ = [('left', wintypes.LONG), ('top', wintypes.LONG), ('right', wintypes.LONG), ('bottom', wintypes.LONG)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', RECT), ('rcWork', RECT), ('dwFlags', wintypes.DWORD)]


def foreground_monitor():
    """Physical bounds and work area of the monitor showing the foreground window."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    r, w = info.rcMonitor, info.rcWork
    return (r.left, r.top, r.right, r.bottom), (w.left, w.top, w.right, w.bottom)


def capture():
    """JPEG bytes of the whole desktop (all screens in one picture), scaled down, held only in memory."""
    from PIL import Image, ImageGrab
    user32 = ctypes.windll.user32
    previous = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2 for physical pixels
    try:
        image = ImageGrab.grab(all_screens=True)
    finally:
        if previous:
            user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(previous))
    image = image.convert('RGB')
    edge = MAX_EDGE_WIDE if image.width > 2.2 * image.height else MAX_EDGE
    image.thumbnail((edge, edge), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG', quality=72, optimize=True)
    image.close()
    return buffer.getvalue()


def foreground_context():
    """Title and program of the foreground window: extra context for the model, never stored."""
    try:
        import psutil
        from windows import foreground
        fg = foreground()
        name = psutil.Process(fg['pid']).name() if fg['pid'] else ''
        return f"Vordergrundprogramm: {name or 'unbekannt'} · Fenstertitel: {fg.get('title', '')[:200]}"
    except Exception:
        return 'Vordergrundprogramm: unbekannt'


def usage_of(response):
    usage = getattr(response, 'usage', None)
    tokens_in = sum(int(getattr(usage, k, 0) or 0) for k in ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'))
    return {'in': tokens_in, 'out': int(getattr(usage, 'output_tokens', 0) or 0)}


def assess(key, model, goal, jpeg, context, client_factory=None):
    """One vision call. Returns (parsed result or None when the answer cannot be trusted, token usage)."""
    response = request_assessment(key, model, goal, jpeg, context, client_factory)
    return parse(response), usage_of(response)


def login_dir():
    """Folder of the signed-in user's `ant auth login` profile, or None when there is no login.

    The session agent runs as SYSTEM inside the user's session, so the user's roaming folder
    is looked up through the session's own token instead of this process's environment.
    """
    base = None
    try:
        import win32process
        import win32profile
        import win32ts
        session = win32process.ProcessIdToSessionId(os.getpid())
        token = win32ts.WTSQueryUserToken(session)
        try:
            base = Path(win32profile.GetUserProfileDirectory(token)) / 'AppData' / 'Roaming'
        finally:
            token.Close()
    except Exception:
        base = Path(os.environ['APPDATA']) if os.environ.get('APPDATA') else None  # ordinary user process
    if not base:
        return None
    folder = base / 'Anthropic'
    try:
        pointer = folder / 'active_config'
        profile = (pointer.read_text('utf-8').strip() if pointer.is_file() else '') or 'default'
        if (folder / 'configs' / (profile + '.json')).is_file() and (folder / 'credentials' / (profile + '.json')).is_file():
            return folder
    except OSError:
        pass
    return None


def make_client(key, client_factory=None):
    """A stored API key wins; otherwise the SDK uses the user's `ant auth login` profile."""
    import anthropic
    factory = client_factory or anthropic.Anthropic
    if key:
        return factory(api_key=key, max_retries=2, timeout=90.0)
    folder = login_dir()
    if not folder:
        raise RuntimeError('Weder Anmeldung noch API-Schlüssel vorhanden.')
    os.environ['ANTHROPIC_CONFIG_DIR'] = str(folder)
    for name in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN'):
        os.environ.pop(name, None)  # a stray variable would silently outrank the login
    return factory(max_retries=2, timeout=90.0)


def request_assessment(key, model, goal, jpeg, context, client_factory=None):
    import anthropic
    client = make_client(key, client_factory)
    content = [
        {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg',
                                     'data': base64.standard_b64encode(jpeg).decode('ascii')}},
        {'type': 'text', 'text': f'Lernziel: {goal}\n{context}\nArbeitet die Person gerade an ihrem Lernziel?'},
    ]
    params = dict(model=model, max_tokens=4000, system=SYSTEM_PROMPT,
                  output_config={'effort': 'low', 'format': {'type': 'json_schema', 'schema': SCHEMA}},
                  messages=[{'role': 'user', 'content': content}])
    response = None
    if model in FALLBACK_MODELS:
        try:
            response = client.beta.messages.create(betas=['server-side-fallback-2026-07-01'], fallbacks='default', **params)
        except anthropic.BadRequestError:
            response = None  # fallback option not accepted for this request: ask without it
    if response is None:
        response = client.messages.create(**params)
    return response


def parse(response):
    if response.stop_reason != 'end_turn':
        return None  # refusal or truncation: unknown, never counted as drifting
    text = next((b.text for b in response.content if b.type == 'text'), '')
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if type(data.get('learning')) is not bool or data.get('confidence') not in ('hoch', 'mittel', 'niedrig'):
        return None
    data['place'] = ' '.join(str(data.get('place', '')).split())[:40]
    data['message'] = ' '.join(str(data.get('message', '')).split())[:400]
    return data
