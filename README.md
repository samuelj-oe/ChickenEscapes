# ChickenEscapes

ChickenEscapes ist ein kleines Spiel in dem Sie sich gegen die ausgebrochenen, verrücktesten Hühner verteidigen müssen.

## Features

- Multiplayer
- Public/Self-hosted Server
- mehrere Version durch den Launcher installieren

## Installation

### Windows

Führe `installer.exe` im Projektordner aus. Der Installer erstellt die virtuelle Python-Umgebung `WinVenv` und installiert die benötigten Pakete.

Starte den Launcher anschließend mit:

```powershell
.\WinVenv\Scripts\python.exe launcher.py
```

### Linux

Installiere Python 3.12 oder neuer. Öffne ein Terminal im Projektordner und führe den Installer aus:

```bash
python3 installer.py
```

Der Installer erstellt die virtuelle Python-Umgebung `LxVenv` und installiert die benötigten Pakete. Starte danach den Launcher mit:

```bash
./LxVenv/bin/python launcher.py
```

Der Launcher verwendet die virtuelle Umgebung auch zum Starten des Spiels. Starte ihn daher wie oben gezeigt und nicht mit einem global installierten Python. Über den Launcher kannst du die verfügbaren Spielversionen starten. Zum gemeinsamen Spielen müssen Client und Server dieselbe Spielversion verwenden.

## Screenshots

![App Screenshot](https://dummyimage.com/468x300?text=Screenshots+später!)

## Copyright

[MIT-License](https://github.com/samuelj-oe/ChickenEscapes/blob/main/LICENSE)
