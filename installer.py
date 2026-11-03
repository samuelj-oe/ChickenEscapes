import venv
import platform
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

if platform.system() == "Windows":
    venv.create("WinVenv", with_pip=True)

elif platform.system() == "Linux":
    venv.create("LxVenv", with_pip=True)

os.popen(f"{os.path.join(ROOT, 'WinVenv' if platform.system() == 'Windows' else 'LxVenv', 'Scripts', 'pip')} install -r {os.path.join(ROOT, 'requirements.txt')}")