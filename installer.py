import venv
import platform
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
pypath = None

if platform.system() == "Windows":
    venv.create("WinVenv", with_pip=True)
    py_path = os.path.join(ROOT, "WinVenv", "Scripts", "python.exe")

elif platform.system() == "Linux":
    venv.create("LxVenv", with_pip=True)
    py_path = os.path.join(ROOT, "LxVenv", "bin", "python")

os.popen(f"{py_path} -m pip install -r {os.path.join(ROOT, 'requirements.txt')}")