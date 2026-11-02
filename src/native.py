import json
import struct
import sys
from ipc import request
from windows import foreground

def read_exact(stream, length):
    result = b''
    while len(result) < length:
        data = stream.read(length - len(result))
        if not data:
            raise EOFError()
        result += data
    return result

def run_native():
    import msvcrt
    import os
    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    while True:
        try:
            length = struct.unpack('<I', read_exact(sys.stdin.buffer, 4))[0]
            if length > 512 * 1024:
                return
            payload = json.loads(read_exact(sys.stdin.buffer, length))
            payload['op'] = 'pulse'
            payload['foreground'] = foreground()
            try:
                response = request(payload)
            except Exception as e:
                response = {'error': str(e), 'unavailable': True}
            data = json.dumps(response, ensure_ascii=False).encode('utf-8')
            sys.stdout.buffer.write(struct.pack('<I', len(data)) + data)
            sys.stdout.buffer.flush()
        except (EOFError, BrokenPipeError):
            return
