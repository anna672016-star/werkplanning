"""Start het werkrooster en open het in de standaardbrowser."""
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import webbrowser
import ctypes
import json

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8765/'

def running():
    try:
        with urllib.request.urlopen(URL + 'api/me', timeout=2) as response:
            state = json.load(response)
            return (response.status == 200 and isinstance(state, dict)
                    and isinstance(state.get('setup'), bool)
                    and 'user' in state and state.get('local') is True)
    except Exception:
        return False

def main():
    if not running():
        subprocess.Popen([sys.executable, str(ROOT / 'server.py')], cwd=str(ROOT),
                         creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(30):
            if running():
                break
            time.sleep(0.2)

    if running():
        webbrowser.open(URL)
    else:
        ctypes.windll.user32.MessageBoxW(0, 'Het werkrooster kon niet worden gestart. Probeer het opnieuw.', 'Werkrooster', 48)

if __name__ == '__main__':
    main()
