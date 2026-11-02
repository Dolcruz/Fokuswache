import sys

def main():
    if '--request' in sys.argv:
        import json
        from pathlib import Path
        from ipc import request
        source = Path(sys.argv[sys.argv.index('--request') + 1])
        target = Path(sys.argv[sys.argv.index('--response') + 1])
        try:
            answer = request(json.loads(source.read_text('utf-8-sig')))
        except Exception as e:
            answer = {'error': str(e)}
        target.write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding='utf-8')
    elif '--native' in sys.argv:
        from native import run_native
        run_native()
    elif '--service' in sys.argv:
        import servicemanager
        from service import FokusService
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(FokusService)
        servicemanager.StartServiceCtrlDispatcher()
    elif '--agent' in sys.argv:
        from agent import run_agent
        run_agent()
    elif '--dev-service' in sys.argv:
        from service import Controller
        from pathlib import Path
        Controller(Path(sys.argv[sys.argv.index('--dev-service') + 1]), enforce=False).serve()
    else:
        from ui import run_ui
        run_ui()

if __name__ == '__main__':
    main()
