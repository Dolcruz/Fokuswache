"""Length-limited local named pipe protocol. No network listener."""
import json
import time
import win32file
import win32pipe
import pywintypes

PIPE = r'\\.\pipe\FokusWache.v1'
MAX_MESSAGE = 512 * 1024

def request(payload, timeout=3):
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    if len(data) > MAX_MESSAGE:
        raise ValueError('Nachricht zu groß.')
    deadline = time.monotonic() + timeout
    while True:
        try:
            h = win32file.CreateFile(PIPE, win32file.GENERIC_READ | win32file.GENERIC_WRITE, 0, None, win32file.OPEN_EXISTING, 0, None)
            break
        except pywintypes.error:
            if time.monotonic() >= deadline:
                raise RuntimeError('FokusWache-Dienst nicht erreichbar.')
            time.sleep(.1)
    try:
        win32pipe.SetNamedPipeHandleState(h, win32pipe.PIPE_READMODE_MESSAGE, None, None)
        win32file.WriteFile(h, data)
        _, answer = win32file.ReadFile(h, MAX_MESSAGE)
        result = json.loads(answer)
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result
    finally:
        win32file.CloseHandle(h)
