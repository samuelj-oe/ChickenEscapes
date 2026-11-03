import websockets
import asyncio
import json
import math
import os
import time
import uuid

xpath = os.path.join(os.path.dirname(__file__))
guidatapath =  f"{xpath}/mapdata"
error = ""
version = open(f"{xpath}/version.txt").read().strip()


class Server():
    print("[Server] Lade Servereinstellungen ...")
    settings_file = open(f"{xpath}/settings.json", "r")
    settings = json.load(settings_file)
    clients = set()
    character_data = {}
    player_states = {}  # Track player state: {player_id: {x, y, action, ...}}
    port = settings["port"]
    hostname = settings["host"]
    if hostname == "0.0.0.0":
        host = None
    print("[Server] Servereinstellungen geladen!")

    def __init__(self):
        print(f"[Server] Initialisiere Server auf version v{version}...")
        self.load_game_data()
        print("[Server] Spieldaten geladen und Server bereit.")

    def load_game_data(self):
            print("[Server] Lade Spieldaten ...")
            game_data_file = open(f"{guidatapath}/setup.json")
            game_data = json.load(game_data_file)
            self.waves = game_data["waves_int"]
            self.waves_data = game_data["wave"]
            self.spawn = (game_data["spawnx"], game_data["spawny"])
            map_file = game_data.get("map_file")
            if map_file:
                map_path = os.path.join(guidatapath, map_file)
                with open(map_path, "r", encoding="utf-8") as map_file_handle:
                    self.map = json.load(map_file_handle)
            else:
                self.map = game_data["map"]
            self.gravity_param = game_data["gravity"]
            self.speed_param = game_data["speed"]
            self.damage_param = game_data["damage"]
            print("[Server] Spieldaten geladen!")

            print("[Server] Lade Animationen ...")
            animations_file = open(f"{xpath}/animations.json", "r")
            self.animations = json.load(animations_file)
            print("[Server] Animationen geladen!")

            self.join_data = {
                "type": "join",
                "status": "accept",
                "welcome_msg": game_data["welcome_message"]
            }

            self.map_data = {
                "type": "map",
                "map": self.map
            }

    async def handler(self, websocket):
        self.clients.add(websocket)
        player_id = None
        print("[Join] jmd hat sich verbunden, warte auf Beitrittsanfrage...")

        async def send(data):
            await websocket.send(json.dumps(data))

        try:
            async for message in websocket:
                recv = json.loads(message)
                
                if recv["type"] == "join_req":
                    if recv["version"] == version:
                        player_id = uuid.uuid4().hex
                        self.player_states[player_id] = {
                            "name": str(recv.get("name", "Player"))[:32],
                            "x": self.spawn[0],
                            "y": self.spawn[1],
                            "character": str(recv.get("character", "Toni"))[:32],
                            "facing_left": False,
                            "action": "idle"
                        }
                        print(str(self.player_states[player_id]["character"]))
                        await send({**self.join_data, "player_id": player_id})
                        print(f"[Join] {player_id} ist beigetreten")
                        await send(self.map_data)
                        print(f"[Join] Karte an {player_id} gesendet")
                    else:
                        join_decline = {
                            "type": "join",
                            "status": "decline",
                            "explain": "[Version] Host has another Game version"
                        }
                        await send(join_decline)
                
                elif recv["type"] == "action":
                    if player_id and player_id in self.player_states:
                        await self.process_player_action(player_id, recv["action"])
                elif recv["type"] == "player_state":
                    if player_id and player_id in self.player_states:
                        self.update_player_state(player_id, recv.get("state", {}))
                        
        except Exception as e:
            print(f"[Error] Verbindung beendet {player_id}: {e}")
        finally:
            self.clients.discard(websocket)
            if player_id and player_id in self.player_states:
                del self.player_states[player_id]
                departure = json.dumps({"type": "player_left", "player_id": player_id})
                for client in tuple(self.clients):
                    try:
                        await client.send(departure)
                    except websockets.exceptions.ConnectionClosed:
                        self.clients.discard(client)
                print(f"[Disconnect] {player_id} hat die Verbindung beendet")

    def update_player_state(self, player_id, state):
        if not isinstance(state, dict):
            return
        player = self.player_states[player_id]
        for field in ("x", "y"):
            value = state.get(field)
            if isinstance(value, (int, float)) and math.isfinite(value):
                player[field] = max(-100, min(900, float(value)))
        if isinstance(state.get("facing_left"), bool):
            player["facing_left"] = state["facing_left"]
        if state.get("action") in {"idle", "walk", "jump", "attack"}:
            player["action"] = state["action"]

    async def process_player_action(self, player_id, action):
        """Handle player actions"""
        if action in ["walk_left", "walk_right", "jump", "attack"]:
            self.player_states[player_id]["action"] = action
            # Update position based on action
            if action == "walk_left":
                self.player_states[player_id]["x"] -= 5
            elif action == "walk_right":
                self.player_states[player_id]["x"] += 5
        else:
            self.player_states[player_id]["action"] = action
        print(f"[DEBUG] Processed action '{action}' for player '{player_id}'")

    async def gameloop(self):
        print("[Server] Gameloop gestartet!")
        while True:

            self.frame_update = {
                "type": "frame",
                "map": self.map,
                "entities": {"players": {
                    player_id: dict(state)
                    for player_id, state in self.player_states.items()
                }}
            }
            
            for client in self.clients:
                try:
                    await client.send(json.dumps(self.frame_update))
                except websockets.exceptions.ConnectionClosed:
                    continue
            
            await asyncio.sleep(0.016)  # ~60 FPS

    async def main(self):
        async with websockets.serve(self.handler, self.host, self.port):
            print(f"[Server] laufe auf {self.hostname}:{self.port}")
            await asyncio.gather(
                asyncio.Future(),
                self.gameloop()
            )

    def start(self):
        print("[Server] Starte ...")
        time.sleep(0.8)
        asyncio.run(self.main())

sxyz = Server()
sxyz.start()