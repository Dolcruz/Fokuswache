"""Per-session foreground observer, visible countdown for device actions and the learning-session watcher."""
import ctypes
from ctypes import wintypes
import datetime as dt
import os
from pathlib import Path
import queue
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk
from ipc import request
from windows import foreground, perform_device

HOTKEY_ID = 0x4C57  # Ctrl+Alt+L opens the learning-session start dialog
GREEN, INK, MUTED, PAPER = '#207765', '#233346', '#687787', '#ffffff'
LOG = Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData')) / 'FokusWache' / 'agent.log'


def log(message):
    """Text-only diagnostics of the learning watcher (never image data, keys or window titles)."""
    try:
        if LOG.exists() and LOG.stat().st_size > 512 * 1024:
            LOG.replace(LOG.with_suffix('.log.old'))
        with LOG.open('a', encoding='utf-8') as f:
            f.write(dt.datetime.now().isoformat(timespec='seconds') + ' ' + message.rstrip() + '\n')
    except OSError:
        pass


def run_agent():
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
    state = {'pending': [], 'connected': False, 'last': 0, 'study': None, 'summary': None, 'vision_ready': False}
    executed = {}
    ui = queue.Queue()
    def observe():
        while True:
            try:
                answer = request({'op': 'foreground', 'foreground': foreground()})
                state.update(pending=answer.get('pending', []), connected=True, last=time.monotonic(),
                             study=answer.get('study'), summary=answer.get('summary'),
                             vision_ready=bool(answer.get('vision_ready')))
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
        # The learning watcher must never stop the device-action countdown above.
        try:
            study.tick()
        except Exception:
            log('Lernmodus: ' + traceback.format_exc())
        while True:
            try:
                job = ui.get_nowait()
            except queue.Empty:
                break
            try:
                job()
            except Exception:
                log('Fensteraktion: ' + traceback.format_exc())
        root.after(500, display)
    study = StudyWatcher(root, state, ui)
    threading.Thread(target=observe, daemon=True).start()
    threading.Thread(target=hotkey_loop, args=(lambda: ui.put(study.open_start),), daemon=True).start()
    display()
    root.mainloop()


def hotkey_loop(callback):
    user32 = ctypes.windll.user32
    if not user32.RegisterHotKey(None, HOTKEY_ID, 0x0001 | 0x0002 | 0x4000, ord('L')):  # Alt+Ctrl, no repeat
        log('Tastenkürzel Strg+Alt+L nicht verfügbar (Fehler %d).' % ctypes.windll.kernel32.GetLastError())
        return
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        if msg.message == 0x0312 and msg.wParam == HOTKEY_ID:  # WM_HOTKEY
            callback()


def root_hwnd(window):
    window.update_idletasks()
    return ctypes.windll.user32.GetAncestor(window.winfo_id(), 2)  # GA_ROOT


def no_activate(window):
    """Keep a small notice from taking keyboard focus or a taskbar button away from the learning material."""
    hwnd = root_hwnd(window)
    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x00000080 | 0x00000008)  # NOACTIVATE, TOOLWINDOW, TOPMOST


def work_area():
    try:
        from watcher import foreground_monitor
        return foreground_monitor()[1]
    except Exception:
        return 0, 0, 1280, 720


class Notice:
    """Small, movable, always-on-top card. Never modal, never full-screen."""
    def __init__(self, root, title, accent=GREEN, width=380):
        self.window = w = tk.Toplevel(root)
        w.withdraw()
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.configure(bg=accent)
        self.width = width
        body = tk.Frame(w, bg=PAPER, padx=16, pady=12)
        body.pack(fill='both', expand=True, padx=(4, 0))
        head = tk.Frame(body, bg=PAPER)
        head.pack(fill='x')
        self.title = tk.Label(head, text=title, bg=PAPER, fg=INK, font=('Segoe UI Semibold', 11), anchor='w')
        self.title.pack(side='left', fill='x', expand=True)
        close = tk.Label(head, text='✕', bg=PAPER, fg=MUTED, font=('Segoe UI', 11), cursor='hand2', padx=4)
        close.pack(side='right')
        close.bind('<Button-1>', lambda e: self.hide())
        self.text = tk.Label(body, bg=PAPER, fg=INK, font=('Segoe UI', 10), justify='left', anchor='w', wraplength=width - 50)
        self.text.pack(fill='x', pady=(6, 0))
        self.small = tk.Label(body, bg=PAPER, fg=MUTED, font=('Segoe UI', 9), justify='left', anchor='w', wraplength=width - 50)
        self.small.pack(fill='x', pady=(6, 0))
        self.actions = tk.Frame(body, bg=PAPER)
        self.actions.pack(fill='x', pady=(10, 0))
        for widget in (w, body, head, self.title, self.text, self.small):
            widget.bind('<ButtonPress-1>', self.grab)
            widget.bind('<B1-Motion>', self.drag)
        no_activate(w)
        self.placed = False
        self.visible = False

    def grab(self, event):
        self.offset = (event.x_root - self.window.winfo_x(), event.y_root - self.window.winfo_y())

    def drag(self, event):
        self.window.geometry(f'+{event.x_root - self.offset[0]}+{event.y_root - self.offset[1]}')
        self.placed = True  # keep the user's chosen spot for the next notice

    def button(self, text, command, primary=False):
        b = tk.Label(self.actions, text=text, bg=GREEN if primary else '#edf3f3', fg='white' if primary else INK,
                     font=('Segoe UI Semibold', 9), padx=12, pady=5, cursor='hand2')
        b.pack(side='left', padx=(0, 8))
        b.bind('<Button-1>', lambda e: command())
        return b

    def show(self, text, small=''):
        self.text.configure(text=text)
        self.small.configure(text=small)
        self.small.pack_forget()
        if small:
            self.small.pack(fill='x', pady=(6, 0), before=self.actions)
        if not self.placed:
            left, top, right, bottom = work_area()
            self.window.update_idletasks()
            height = self.window.winfo_reqheight()
            self.window.geometry(f'{self.width}x{height}+{right - self.width - 24}+{bottom - height - 24}')
        user32 = ctypes.windll.user32
        previous = user32.GetForegroundWindow()
        self.window.deiconify()
        self.window.attributes('-topmost', True)
        self.window.update_idletasks()
        hwnd = root_hwnd(self.window)
        # Tk activates a window it maps; hand the keyboard straight back to what the user was working in.
        if previous and previous != hwnd and user32.GetForegroundWindow() == hwnd:
            user32.SetForegroundWindow(previous)
        self.visible = True

    def hide(self):
        self.window.withdraw()
        self.visible = False


class StudyWatcher:
    def __init__(self, root, state, ui):
        self.root, self.state, self.ui = root, state, ui
        self.session = None
        self.due = None
        self.busy = False
        self.failures = 0
        self.pace = None
        self.nudge = None
        self.info = None
        self.summary_window = None
        self.start_window = None
        self.summary_shown = set()

    # Runs on the Tk thread every 500 ms.
    def tick(self):
        study = self.state['study'] if self.state['connected'] else None
        if study and study['id'] != self.session:
            from watcher import Pace
            self.session, self.pace, self.failures = study['id'], Pace(), 0
            self.due = time.monotonic() + self.pace.next_delay()
            log('Lernmodus erkannt; Aufpasser %s, erste Prüfung in %d s.' % (
                'an' if self.state['vision_ready'] else 'aus (kein Schlüssel)', self.due - time.monotonic()))
            if not self.state['vision_ready']:
                self.show_info('Lernmodus läuft', 'Der Aufpasser ist aus, weil noch kein API-Schlüssel hinterlegt ist. '
                               'Die Sperren gelten trotzdem.', 'Schlüssel: FokusWache → Browser & Schutz')
        elif not study and self.session:
            self.session = None
            if self.nudge:
                self.nudge.hide()
        if study and self.state['vision_ready'] and not self.busy and time.monotonic() >= self.due:
            self.busy = True
            if self.nudge and self.nudge.visible:
                self.nudge.hide()  # the notice itself must not be judged in the next screenshot
            goal, sid = study['goal'], study['id']
            self.root.after(150, lambda: threading.Thread(target=self.check, args=(sid, goal), daemon=True).start())
        summary = self.state.get('summary')
        if summary and summary['id'] not in self.summary_shown and not study:
            self.summary_shown.add(summary['id'])
            self.show_summary(summary)

    # Runs on a worker thread; the image lives only inside this function.
    def check(self, sid, goal):
        result, tokens = None, None
        try:
            from watcher import assess, capture, foreground_context
            config = request({'op': 'vision_config'})
            if config.get('key'):
                jpeg = capture()
                try:
                    result, tokens = assess(config['key'], config['model'], goal, jpeg, foreground_context())
                finally:
                    del jpeg
        except Exception as error:
            result, problem = None, type(error).__name__ + ': ' + str(error)[:160]
            log('Prüfung fehlgeschlagen: ' + problem)
        else:
            problem = 'Keine eindeutige Antwort.'
            if result is None:
                log('Prüfung ohne eindeutige Antwort.')
        self.ui.put(lambda: self.checked(sid, result, problem, tokens))

    def checked(self, sid, result, problem, tokens=None):
        from watcher import is_drift
        self.busy = False
        if sid != self.session:
            return
        if result is None:
            if tokens:
                threading.Thread(target=self.report, args=(sid, None, '', tokens), daemon=True).start()
            self.failures += 1
            self.due = time.monotonic() + self.pace.next_delay(failed=True)
            if self.failures == 3:
                self.show_info('Aufpasser pausiert kurz', 'Die Bildauswertung hat dreimal nicht geklappt. Die Sperren gelten weiter; '
                               'ich versuche es in ein paar Minuten erneut.', problem)
            return
        self.failures = 0
        drift = is_drift(result)
        counted = result['learning'] or drift
        if counted:
            self.pace.record(not drift)
        threading.Thread(target=self.report, args=(sid, (not drift) if counted else None, result['place'], tokens), daemon=True).start()
        self.due = time.monotonic() + self.pace.next_delay()
        log('Prüfung: %s (%s), nächste in %d s.' % ('abgedriftet' if drift else 'lernt' if result['learning'] else 'unsicher',
                                                    result['confidence'], self.due - time.monotonic()))
        if drift:
            self.show_nudge(result)

    def report(self, sid, on_task, place, tokens=None):
        try:
            request({'op': 'study_report', 'study': sid, 'on_task': on_task, 'place': place, 'tokens': tokens})
        except Exception:
            log('Meldung an den Dienst fehlgeschlagen: ' + traceback.format_exc(limit=1))

    def show_nudge(self, result):
        if not self.nudge:
            self.nudge = Notice(self.root, 'Kurz zurück zum Lernen?')
            self.nudge.button('Zurück zum Lernen', lambda: self.nudge.hide(), primary=True)
        goal = (self.state.get('study') or {}).get('goal', '')
        self.nudge.show(result['message'] or 'Gerade sieht es nicht nach deinem Lernziel aus.', 'Dein Ziel: ' + goal)

    def show_info(self, title, text, small=''):
        if not self.info:
            self.info = Notice(self.root, title, accent='#a77832')
            self.info.button('Okay', lambda: self.info.hide())
        self.info.title.configure(text=title)
        self.info.show(text, small)

    def show_summary(self, s):
        if self.summary_window:
            self.summary_window.hide()
        n = Notice(self.root, 'Lernmodus beendet' + (' (vorzeitig)' if s.get('early') else ''), width=420)
        self.summary_window = n
        minutes = int(round(s['minutes']))
        lines = [f"{minutes} Minuten gelernt (geplant {s['planned_minutes']}).",
                 'Kein Abdriften bemerkt.' if not s['drifts'] else
                 f"{s['drifts']}× abgedriftet bei {s['checks']} Prüfungen."]
        places = ', '.join(f'{k} ({v}×)' for k, v in sorted(s.get('places', {}).items(), key=lambda kv: -kv[1]))
        n.button('Schließen', lambda: n.hide(), primary=True)
        n.show('\n'.join(lines), 'Wohin: ' + places if places else '')
        threading.Thread(target=lambda: request({'op': 'study_ack', 'id': s['id']}), daemon=True).start()

    def open_start(self):
        if self.start_window and self.start_window.winfo_exists():
            self.start_window.deiconify()
            self.start_window.focus_force()
            return
        w = tk.Toplevel(self.root)
        self.start_window = w
        w.title('FokusWache – Lernmodus')
        w.attributes('-topmost', True)
        w.configure(bg=PAPER, padx=22, pady=18)
        w.resizable(False, False)
        study = self.state.get('study')
        if study:
            end = dt.datetime.fromisoformat(study['until']).astimezone()
            tk.Label(w, text='Der Lernmodus läuft', bg=PAPER, fg=INK, font=('Segoe UI Semibold', 13)).pack(anchor='w')
            tk.Label(w, text=f"bis {end:%H:%M} · {study['goal']}", bg=PAPER, fg=MUTED, font=('Segoe UI', 10),
                     wraplength=380, justify='left').pack(anchor='w', pady=(4, 12))
            ttk.Button(w, text='Schließen', command=w.destroy).pack(anchor='e')
        else:
            tk.Label(w, text='Lernmodus starten', bg=PAPER, fg=INK, font=('Segoe UI Semibold', 13)).pack(anchor='w')
            tk.Label(w, text='Woran arbeitest du? Ein Satz reicht.', bg=PAPER, fg=MUTED, font=('Segoe UI', 10)).pack(anchor='w', pady=(4, 6))
            goal = ttk.Entry(w, width=48, font=('Segoe UI', 11))
            goal.pack(fill='x')
            message = tk.Label(w, text='Alle Webseiten-, Programm- und Spielregeln werden für die gewählte Dauer gesperrt.',
                               bg=PAPER, fg=MUTED, font=('Segoe UI', 9), wraplength=400, justify='left')
            message.pack(anchor='w', pady=(10, 10))
            row = tk.Frame(w, bg=PAPER)
            row.pack(fill='x')
            def start(minutes):
                def work():
                    try:
                        request({'op': 'study_start', 'minutes': minutes, 'goal': goal.get()})
                        self.ui.put(w.destroy)
                    except Exception as e:
                        self.ui.put(lambda: message.configure(text=str(e), fg='#ae4343'))
                threading.Thread(target=work, daemon=True).start()
            for minutes in (25, 50, 90):
                ttk.Button(row, text=f'{minutes} Minuten', command=lambda m=minutes: start(m)).pack(side='left', padx=(0, 8))
            ttk.Button(row, text='Abbrechen', command=w.destroy).pack(side='right')
            goal.bind('<Return>', lambda e: start(50))
            w.after(50, goal.focus_force)
        w.update_idletasks()
        left, top, right, bottom = work_area()
        w.geometry(f'+{(left + right - w.winfo_width()) // 2}+{(top + bottom - w.winfo_height()) // 3}')
        w.focus_force()
