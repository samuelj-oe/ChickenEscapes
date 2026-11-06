import asyncio
import json
import os
import time
import uuid

import websockets


ROOT = os.path.dirname(os.path.abspath(__file__))
MAP_DATA_PATH = os.path.join(ROOT, "mapdata")
VERSION = open(os.path.join(ROOT, "version.txt"), encoding="utf-8").read().strip()
GAMEPLAY_PROTOCOL = 2
WIDTH, HEIGHT = 800, 600
PLAYER_HALF_WIDTH = 18


class Server:
    def __init__(self):
        print("[Server] Lade Servereinstellungen ...")
        with open(os.path.join(ROOT, "settings.json"), encoding="utf-8") as settings_file:
            settings = json.load(settings_file)
        self.port = settings["port"]
        self.hostname = settings["host"]
        self.host = None if self.hostname == "0.0.0.0" else self.hostname
        self.clients = set()
        self.player_states = {}
        self.load_game_data()
        print("[Server] Servereinstellungen geladen!")
        print(f"[Server] Initialisiere Server auf version v{VERSION}...")
        print("[Server] Spieldaten geladen und Server bereit.")

    def load_game_data(self):
        print("[Server] Lade Spieldaten ...")
        with open(os.path.join(MAP_DATA_PATH, "setup.json"), encoding="utf-8") as game_data_file:
            game_data = json.load(game_data_file)
        self.waves = game_data["waves_int"]
        self.waves_data = game_data["wave"]
        self.spawn = (float(game_data["spawnx"]), float(game_data["spawny"]))
        map_file = game_data.get("map_file")
        if map_file:
            map_path = os.path.join(MAP_DATA_PATH, map_file)
            with open(map_path, encoding="utf-8") as map_file_handle:
                self.map = json.load(map_file_handle)
        else:
            self.map = game_data["map"]
        self.gravity_param = max(0.1, float(game_data["gravity"]))
        self.speed_param = max(0.1, float(game_data["speed"]))
        self.damage_param = game_data["damage"]
        print("[Server] Spieldaten geladen!")

        print("[Server] Lade Animationen ...")
        animations_path = os.path.join(ROOT, "animations.json")
        if os.path.exists(animations_path):
            with open(animations_path, encoding="utf-8") as animations_file:
                self.animations = json.load(animations_file)
        else:
            self.animations = {}
            print("[Server] Keine animations.json gefunden; fahre ohne Serveranimationen fort.")
        print("[Server] Animationen geladen!")

        self.join_data = {
            "type": "join",
            "status": "accept",
            "gameplay_protocol": GAMEPLAY_PROTOCOL,
            "welcome_msg": game_data["welcome_message"],
        }
        self.map_data = {
            "type": "map",
            "map": self.map,
        }

    async def handler(self, websocket):
        player_id = None
        print("[Join] jmd hat sich verbunden, warte auf Beitrittsanfrage...")

        async def send(data):
            await websocket.send(json.dumps(data))

        try:
            async for message in websocket:
                recv = json.loads(message)
                if not isinstance(recv, dict):
                    continue

                if recv.get("type") == "join_req" and player_id is None:
                    if (
                        recv.get("version") == VERSION
                        and recv.get("gameplay_protocol") == GAMEPLAY_PROTOCOL
                    ):
                        player_id = uuid.uuid4().hex
                        name = recv.get("name")
                        if not isinstance(name, str) or not name.strip():
                            name = "Player"
                        character = recv.get("character")
                        if not isinstance(character, str):
                            character = "Toni"
                        self.player_states[player_id] = {
                            "name": name.strip()[:32],
                            "x": self.spawn[0],
                            "y": self.spawn[1],
                            "velocity_y": 0.0,
                            "direction": 0,
                            "on_ground": True,
                            "attack_until": 0.0,
                            "attack_cooldown_until": 0.0,
                            "character": character[:32],
                            "facing_left": False,
                            "action": "idle",
                        }
                        self.clients.add(websocket)
                        await send({**self.join_data, "player_id": player_id})
                        print(f"[Join] {player_id} ist beigetreten")
                        await send(self.map_data)
                        print(f"[Join] Karte an {player_id} gesendet")
                    else:
                        reason = (
                            "[Version] Host has another Game version"
                            if recv.get("version") != VERSION
                            else "Client and server need an update for authoritative gameplay."
                        )
                        await send({
                            "type": "join",
                            "status": "decline",
                            "explain": reason,
                        })
                elif recv.get("type") == "input" and player_id in self.player_states:
                    self.process_player_input(player_id, recv)
        except Exception as error:
            print(f"[Error] Verbindung beendet {player_id}: {error}")
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

    def process_player_input(self, player_id, data):
        player = self.player_states[player_id]
        direction = data.get("direction")
        if type(direction) is int and direction in (-1, 0, 1):
            player["direction"] = direction
            if direction:
                player["facing_left"] = direction < 0

        if data.get("jump") is True and player["on_ground"]:
            player["velocity_y"] = 440.0
            player["on_ground"] = False

        now = time.monotonic()
        if data.get("attack") is True and now >= player["attack_cooldown_until"]:
            player["attack_until"] = now + 0.48
            player["attack_cooldown_until"] = player["attack_until"]

    def update_player(self, player, delta_time, now):
        player["x"] = max(
            PLAYER_HALF_WIDTH,
            min(WIDTH - PLAYER_HALF_WIDTH,
                player["x"] + player["direction"] * 230 * self.speed_param * delta_time),
        )

        old_y = player["y"]
        player["velocity_y"] -= 780 * self.gravity_param * delta_time
        next_y = old_y + player["velocity_y"] * delta_time
        landed_y = None
        if player["velocity_y"] <= 0:
            for key, platform in self.map.items():
                if not key.isdigit():
                    continue
                x1, y1, x2, y2 = platform["size"]
                left, right = sorted((float(x1), float(x2)))
                surface = max(float(y1), float(y2))
                overlaps = (
                    player["x"] + PLAYER_HALF_WIDTH > left
                    and player["x"] - PLAYER_HALF_WIDTH < right
                )
                if overlaps and old_y >= surface >= next_y:
                    landed_y = max(landed_y or surface, surface)

        if landed_y is not None:
            player["y"] = landed_y
            player["velocity_y"] = 0.0
            player["on_ground"] = True
        else:
            player["y"] = next_y
            player["on_ground"] = False

        if player["y"] < -40:
            player["x"], player["y"] = self.spawn
            player["velocity_y"] = 0.0
            player["direction"] = 0
            player["on_ground"] = True

        if now < player["attack_until"]:
            player["action"] = "attack"
        elif not player["on_ground"]:
            player["action"] = "jump"
        elif player["direction"]:
            player["action"] = "walk"
        else:
            player["action"] = "idle"

    async def gameloop(self):
        print("[Server] Gameloop gestartet!")
        previous_update = time.monotonic()
        while True:
            now = time.monotonic()
            delta_time = min(max(now - previous_update, 0.0), 0.05)
            previous_update = now
            for player in self.player_states.values():
                self.update_player(player, delta_time, now)

            frame_update = {
                "type": "frame",
                "map": self.map,
                "entities": {
                    "players": {
                        player_id: {
                            "name": state["name"],
                            "x": state["x"],
                            "y": state["y"],
                            "character": state["character"],
                            "facing_left": state["facing_left"],
                            "action": state["action"],
                        }
                        for player_id, state in self.player_states.items()
                    }
                },
            }

            for client in tuple(self.clients):
                try:
                    await client.send(json.dumps(frame_update))
                except websockets.exceptions.ConnectionClosed:
                    self.clients.discard(client)

            await asyncio.sleep(0.016)

    async def main(self):
        async with websockets.serve(self.handler, self.host, self.port):
            print(f"[Server] laufe auf {self.hostname}:{self.port}")
            await self.gameloop()

    def start(self):
        print("[Server] Starte ...")
        asyncio.run(self.main())


if __name__ == "__main__":
    Server().start()
