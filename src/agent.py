"""Per-session foreground observer and visible countdown for device actions."""
import datetime as dt
import threading
import time
import tkinter as tk
from tkinter import ttk
from ipc import request
from windows import foreground, perform_device

def run_agent():
    import ctypes
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, 'Local\\FokusWacheAgent')
    if ctypes.windll.kernel32.GetLastError() == 183:
        return
    root = tk.Tk()
    root.withdraw()
    root.title('FokusWache – Geräteaktion')
    root.geometry('510x210')
    root.attributes('-topmost', True)
    root.protocol('WM_DELETE_WINDOW', lambda: None)
    label = ttk.Label(root, font=('Segoe UI', 13), padding=24, wraplength=460, justify='center')
    label.pack(fill='both', expand=True)
    state = {'pending': [], 'connected': False, 'last': 0}
    executed = {}
    def observe():
        while True:
            try:
                answer = request({'op': 'foreground', 'foreground': foreground()})
                state.update(pending=answer.get('pending', []), connected=True, last=time.monotonic())
            except Exception:
                state['connected'] = False
            time.sleep(.75)
    def display():
        pending = state['pending'] if state['connected'] and time.monotonic() - state['last'] < 4 else []
        now = dt.datetime.now(dt.timezone.utc)
        if pending:
            p = min(pending, key=lambda x: x['due'])
            left = max(0, int(p['remaining'] - (time.monotonic() - state['last'])))
            names = {'lock': 'gesperrt', 'logoff': 'abgemeldet', 'shutdown': 'heruntergefahren'}
            label.configure(text=f"{p['name']}\n\nDer Rechner wird in {left} Sekunden {names[p['action']]}.\nBitte offene Arbeit speichern.")
            root.deiconify()
            if left == 0 and time.monotonic() - executed.get(p['id'], -1000) > 65:
                executed[p['id']] = time.monotonic()
                try:
                    perform_device(p['action'])
                except Exception as e:
                    label.configure(text='Geräteaktion fehlgeschlagen: ' + str(e))
        else:
            root.withdraw()
            executed.clear()
        root.after(500, display)
    threading.Thread(target=observe, daemon=True).start()
    display()
    root.mainloop()
