# ChickenEscapes

ChickenEscapes ist ein kleines Multiplayer-Spiel: Verteidige dich gegen die ausgebrochenen, verrückten Hühner und spiele gemeinsam mit anderen.

## Features

- Multiplayer über öffentliche oder selbst gehostete Server
- Spielversionen bequem über den Launcher starten
- Windows- und Linux-Installation

## Installation

### Windows

Führe `installer.exe` im Projektordner aus. Der Installer erstellt die virtuelle Umgebung `WinVenv` und installiert die benötigten Pakete.

Starte den Launcher anschließend aus dem Projektordner:

```powershell
.\WinVenv\Scripts\python.exe launcher.py
```

### Linux

Installiere Python 3.12 oder neuer. Öffne ein Terminal im Projektordner und führe den Installer aus:

```bash
python3 installer.py
```

Der Installer erstellt die virtuelle Umgebung `LxVenv` und installiert die benötigten Pakete. Starte den Launcher danach mit:

```bash
./LxVenv/bin/python launcher.py
```

Starte den Launcher mit dem Python-Interpreter aus der virtuellen Umgebung. Er verwendet dieselbe Umgebung, um das Spiel zu starten. Die Abhängigkeiten (`pygame` und `websockets`) werden vom Installer anhand der `requirements.txt` eingerichtet.

## Spielen

Wähle im Launcher eine verfügbare Version. Für gemeinsames Spielen müssen Client und Server dieselbe Spielversion verwenden.

Steuerung im Spiel:

- **A / D**: nach links / rechts bewegen
- **W**: springen
- **Leertaste**: angreifen
- **Esc**: Pausemenü öffnen

## Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).
