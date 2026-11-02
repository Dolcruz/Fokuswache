"""Close the installed Qt window through WM_CLOSE, including a hidden CI window."""
import os
import sys
import win32con
import win32gui
import win32process

if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_OS') != 'Windows':
    raise RuntimeError('This UI check requires the disposable Windows runner.')

pid = int(sys.argv[1])
windows = []


def visit(handle, _):
    if (win32process.GetWindowThreadProcessId(handle)[1] == pid
            and win32gui.GetWindowText(handle) == 'FokusWache'):
        windows.append(handle)


win32gui.EnumWindows(visit, None)
if len(windows) != 1:
    raise RuntimeError(f'Expected one installed FokusWache window; found {len(windows)}.')
win32gui.PostMessage(windows[0], win32con.WM_CLOSE, 0, 0)
print('Sent the normal close request to the installed FokusWache window.')
