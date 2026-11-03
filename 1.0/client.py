import asyncio
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading

import pygame
import websockets


ROOT = Path(__file__).resolve().parent
TEXTURES = ROOT / "textures"
VERSION = (ROOT / "version.txt").read_text(encoding="utf-8").strip()
CHARACTER_DATA = json.loads((ROOT / "characters.json").read_text(encoding="utf-8"))
CHARACTERS = CHARACTER_DATA["characters"]
SETUP = json.loads((ROOT / "server" / "mapdata" / "setup.json").read_text(encoding="utf-8"))
WIDTH, HEIGHT = 800, 600
BACKGROUND = (205, 164, 52)
PANEL = (231, 191, 76)
BUTTON_COLOR = (255, 246, 143)
BUTTON_HOVER = (255, 252, 190)
INK = (48, 34, 8)
MUTED = (102, 75, 24)
WHITE = (255, 255, 255)
PLAYER_HEIGHT = 76


class GameClient:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption(f"ChickenEscapes v{VERSION}")
        self.windowed_size = (WIDTH, HEIGHT)
        self.fullscreen = False
        self.display = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        self.screen = pygame.Surface((WIDTH, HEIGHT))
        self.viewport = pygame.Rect(0, 0, WIDTH, HEIGHT)
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.clock = pygame.time.Clock()
        self.title_font = pygame.font.SysFont("Arial", 40, bold=True)
        self.font = pygame.font.SysFont("Arial", 25)
        self.small_font = pygame.font.SysFont("Arial", 19)
        self.eyebrow_font = pygame.font.SysFont("Arial", 15, bold=True)
        icon = self.load_image(TEXTURES / "ui" / "icon.png")
        pygame.display.set_icon(icon)

        self.images = {}
        self.buttons = {}
        self.input_rects = {}
        self.focused_input = None
        self.screen_name = "story" if self.first_time() else "home"
        self.story_lines = (ROOT / "storyline.txt").read_text(encoding="utf-8").splitlines()
        self.story_index = -1
        self.story_next_at = 0
        self.message = ""
        self.character_index = 0
        self.name = ""
        self.server_address = "localhost"
        self.server_port = str(SETUP.get("port", 8765))
        self.game_map = None
        self.player_x = float(SETUP.get("spawnx", 75))
        self.player_y = float(SETUP.get("spawny", 150))
        self.player_velocity_y = 0.0
        self.player_on_ground = True
        self.player_facing_left = False
        self.attack_started = None
        self.attack_until = 0
        self.player_action = "idle"
        self.player_id = None
        self.remote_players = {}
        self.remote_attacks = {}
        self.remote_actions = {}
        self.last_state_sent = 0
        self.network_stop = None
        self.network_thread = None
        self.incoming = queue.Queue()
        self.outgoing = queue.Queue()
        self.local_server = None
        self.running = True
        self.closed = False
        self.quit_confirm = False

    @staticmethod
    def first_time():
        path = ROOT / "first_time.txt"
        if not path.exists():
            return True
        return path.read_text(encoding="utf-8").strip().lower() == "true"

    @staticmethod
    def load_image(path):
        return pygame.image.load(str(path)).convert_alpha()

    def image(self, path):
        path = Path(path)
        if path not in self.images:
            self.images[path] = self.load_image(path)
        return self.images[path]

    def run(self):
        try:
            while self.running:
                delta_time = min(self.clock.tick(60) / 1000, 0.05)
                self.handle_network_events()
                self.handle_story_timer()
                self.update_player(delta_time)
                self.send_player_state()
                self.handle_events()
                self.draw()
                self.present()
        finally:
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.network_stop:
            self.network_stop.set()
            self.network_stop = None
        if self.network_thread and self.network_thread.is_alive():
            self.network_thread.join(timeout=1)
        try:
            self.stop_local_server()
        finally:
            pygame.quit()

    def draw_text(self, text, position, color=INK, font=None, center=False):
        surface = (font or self.font).render(str(text), True, color)
        rect = surface.get_rect()
        if center:
            rect.center = position
        else:
            rect.topleft = position
        self.screen.blit(surface, rect)
        return rect

    def draw_button(self, button_id, label, rect, font=None):
        rect = pygame.Rect(rect)
        color = BUTTON_HOVER if rect.collidepoint(self.window_to_logical(pygame.mouse.get_pos())) else BUTTON_COLOR
        pygame.draw.rect(self.screen, color, rect, border_radius=10)
        self.draw_text(label, rect.center, INK, font or self.font, center=True)
        self.buttons[button_id] = rect

    def draw_input(self, input_id, label, value, rect):
        rect = pygame.Rect(rect)
        self.draw_text(label, (rect.x, rect.y - 29), INK, self.small_font)
        pygame.draw.rect(self.screen, (255, 250, 203), rect, border_radius=7)
        border = (145, 99, 27) if self.focused_input == input_id else (184, 144, 56)
        pygame.draw.rect(self.screen, border, rect, 2, border_radius=7)
        shown = value if value else ""
        if input_id == self.focused_input:
            shown += "|"
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(rect.inflate(-16, -4))
        self.draw_text(shown, (rect.x + 9, rect.y + 8), INK, self.small_font)
        self.screen.set_clip(previous_clip)
        self.input_rects[input_id] = rect

    def draw(self):
        self.buttons = {}
        self.input_rects = {}
        self.draw_menu_background()
        if self.screen_name == "story":
            self.draw_story()
        elif self.screen_name == "home":
            self.draw_home()
        elif self.screen_name == "single":
            self.draw_singleplayer()
        elif self.screen_name == "multi":
            self.draw_multiplayer()
        elif self.screen_name == "loading":
            self.draw_text("ChickenEscapes", (WIDTH // 2, 245), INK, self.title_font, center=True)
            self.draw_text("Verbinde mit dem Server ...", (WIDTH // 2, 305), INK, self.font, center=True)
        elif self.screen_name == "game":
            self.draw_game()
        elif self.screen_name == "pause":
            self.draw_game()
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((57, 38, 7, 170))
            self.screen.blit(overlay, (0, 0))
            pygame.draw.rect(self.screen, (145, 99, 27), (215, 122, 370, 390), border_radius=18)
            pygame.draw.rect(self.screen, PANEL, (215, 115, 370, 390), border_radius=18)
            self.draw_text("PAUSE", (WIDTH // 2, 148), BUTTON_COLOR, self.eyebrow_font, center=True)
            self.draw_text("Spiel pausiert", (WIDTH // 2, 188), INK, self.title_font, center=True)
            self.draw_button("resume", "Weiter spielen", (285, 235, 230, 52))
            self.draw_button("leave", "Spiel verlassen", (285, 305, 230, 52))
            self.draw_text("STEUERUNG", (WIDTH // 2, 393), MUTED, self.eyebrow_font, center=True)
            self.draw_text("A / D  Bewegen      W  Springen", (WIDTH // 2, 425), INK, self.small_font, center=True)
            self.draw_text("Leertaste  Angreifen      Esc  Pause", (WIDTH // 2, 456), INK, self.small_font, center=True)
        if self.message:
            self.draw_text(self.message, (WIDTH // 2, HEIGHT - 30), (255, 142, 145), self.small_font, center=True)

    def draw_menu_background(self):
        self.screen.fill(BACKGROUND)
        pygame.draw.circle(self.screen, (217, 177, 64), (WIDTH - 60, 75), 190)
        pygame.draw.circle(self.screen, (194, 146, 40), (48, HEIGHT - 15), 170)
        pygame.draw.rect(self.screen, (163, 117, 30), (0, 0, WIDTH, 5))

    def draw_menu_card(self, rect):
        pygame.draw.rect(self.screen, (145, 99, 27), pygame.Rect(rect).move(0, 7), border_radius=20)
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=20)

    def present(self):
        display_width, display_height = self.display.get_size()
        display_width, display_height = max(1, display_width), max(1, display_height)
        self.scale_x = display_width / WIDTH
        self.scale_y = display_height / HEIGHT
        self.viewport = self.display.get_rect()
        frame = pygame.transform.smoothscale(self.screen, (display_width, display_height))
        self.display.blit(frame, self.viewport)
        pygame.display.flip()

    def toggle_fullscreen(self):
        if self.fullscreen:
            self.fullscreen = False
            self.display = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        else:
            self.windowed_size = self.display.get_size()
            self.fullscreen = True
            self.display = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.clock.tick()

    def handle_resize(self, size):
        if not self.fullscreen:
            width, height = max(320, size[0]), max(240, size[1])
            self.windowed_size = (width, height)
            self.display = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)

    def window_to_logical(self, position):
        x = (position[0] - self.viewport.left) / self.scale_x
        y = (position[1] - self.viewport.top) / self.scale_y
        return round(x), round(y)

    def draw_story(self):
        self.draw_menu_background()
        self.draw_menu_card((125, 95, 550, 405))
        if self.story_index < 0:
            self.draw_text("CHICKEN ESCAPES", (WIDTH // 2, 175), BUTTON_COLOR, self.eyebrow_font, center=True)
            self.draw_text("Eine Geschichte", (WIDTH // 2, 230), INK, self.title_font, center=True)
            self.draw_text("Erfahre, wie das Abenteuer begann.", (WIDTH // 2, 275), MUTED, self.small_font, center=True)
            self.draw_button("play_story", "Geschichte abspielen", (160, 360, 220, 52), self.small_font)
        else:
            line = self.story_lines[self.story_index] if self.story_index < len(self.story_lines) else ""
            self.draw_text(line, (WIDTH // 2, HEIGHT // 2), INK, self.font, center=True)
        self.draw_button("skip_story", "Überspringen", (420, 360, 220, 52), self.small_font)

    def draw_home(self):
        self.draw_menu_card((140, 62, 520, 475))
        self.draw_text("CHICKEN ESCAPES", (WIDTH // 2, 135), BUTTON_COLOR, self.eyebrow_font, center=True)
        self.draw_text("Dein Abenteuer", (WIDTH // 2, 183), INK, self.title_font, center=True)
        self.draw_text(f"VERSION {VERSION}", (WIDTH // 2, 219), MUTED, self.eyebrow_font, center=True)
        self.draw_button("single", "Spiel erstellen", (245, 265, 310, 58))
        self.draw_button("multi", "Spiel beitreten", (245, 339, 310, 58))
        self.draw_button("quit", "Spiel beenden", (245, 413, 310, 58))

    def draw_character_selector(self, y):
        self.draw_text("CHARAKTER", (250, y + 10), MUTED, self.eyebrow_font)
        self.draw_button("character_previous", "<", (380, y, 42, 40), self.small_font)
        self.draw_text(CHARACTERS[self.character_index], (465, y + 8), INK, self.small_font, center=True)
        self.draw_button("character_next", ">", (510, y, 42, 40), self.small_font)

    def draw_singleplayer(self):
        self.draw_menu_card((160, 75, 480, 430))
        self.draw_text("OFFLINE/ONLINE", (WIDTH // 2, 125), BUTTON_COLOR, self.eyebrow_font, center=True)
        self.draw_text("Spiel erstellen", (WIDTH // 2, 166), INK, self.title_font, center=True)
        self.draw_button("home", "Zurück", (190, 100, 92, 38), self.small_font)
        self.draw_input("name", "Dein Name:", self.name, (250, 239, 300, 42))
        self.draw_character_selector(315)
        self.draw_button("create_game", "Spiel erstellen!", (290, 397, 220, 58))

    def draw_multiplayer(self):
        self.draw_menu_card((160, 45, 480, 520))
        self.draw_text("ONLINE", (WIDTH // 2, 91), BUTTON_COLOR, self.eyebrow_font, center=True)
        self.draw_text("Spiel beitreten", (WIDTH // 2, 124), INK, self.title_font, center=True)
        self.draw_button("home", "Zurück", (175, 65, 86, 36), self.small_font)
        self.draw_input("server", "Serveradresse:", self.server_address, (250, 185, 300, 40))
        self.draw_input("port", "Serverport:", self.server_port, (250, 275, 300, 40))
        self.draw_character_selector(350)
        self.draw_input("name", "Dein Name:", self.name, (250, 430, 300, 40))
        self.draw_button("join_game", "Beitreten!", (300, 505, 200, 48))

    def draw_game(self):
        if self.game_map is None:
            self.screen.fill(BACKGROUND)
            self.draw_text("Lade Karte ...", (WIDTH // 2, HEIGHT // 2), INK, self.font, center=True)
            return
        if self.game_map.get("theme") == "clean_barn":
            self.draw_clean_barn()
        else:
            background_path = TEXTURES / "map" / self.game_map["background"]
            background = pygame.transform.scale(self.image(background_path), (WIDTH, HEIGHT))
            self.screen.blit(background, (0, 0))
        for key, platform in self.game_map.items():
            if not key.isdigit():
                continue
            x1, y1, x2, y2 = platform["size"]
            x1, x2 = sorted((int(x1), int(x2)))
            y1, y2 = sorted((int(y1), int(y2)))
            width, height = max(1, x2 - x1), max(1, y2 - y1)
            if self.game_map.get("theme") == "clean_barn":
                self.draw_clean_platform(pygame.Rect(x1, HEIGHT - y2, width, height))
            else:
                texture = self.image(TEXTURES / "map" / platform["texture"])
                texture = pygame.transform.scale(texture, (width, height))
                self.screen.blit(texture, (x1, HEIGHT - y2))

        character = self.current_player_sprite()
        if not self.player_facing_left:
            character = pygame.transform.flip(character, True, False)
        player_rect = character.get_rect(
            midbottom=(round(self.player_x), HEIGHT - round(self.player_y))
        )
        self.screen.blit(character, player_rect)
        if self.name:
            label = self.small_font.render(self.name, True, WHITE)
            self.screen.blit(label, label.get_rect(midbottom=(player_rect.centerx, player_rect.top - 5)))

        hud = pygame.Surface((WIDTH, 45), pygame.SRCALPHA)
        hud.fill((28, 22, 16, 175))
        self.screen.blit(hud, (0, 0))
        self.draw_text(self.game_map.get("name", "Chicken Escapes"), (15, 11), WHITE, self.small_font)
        self.draw_button("pause_game", "Pause", (WIDTH - 96, 7, 82, 32), self.small_font)

        for player_id, player in self.remote_players.items():
            if player_id == self.player_id:
                continue
            self.draw_remote_player(player_id, player)

    def draw_remote_player(self, player_id, player):
        character_name = player.get("character", "Toni")
        character_dir = CHARACTER_DATA.get(character_name, "")
        if not character_dir or not (TEXTURES / character_dir / "idle.png").exists():
            character_dir = "normal_chicken"

        attack_started = self.remote_attacks.get(player_id)
        sprite = self.player_sprite_for(character_dir, attack_started)
        if not player.get("facing_left", False):
            sprite = pygame.transform.flip(sprite, True, False)
        rect = sprite.get_rect(
            midbottom=(round(float(player.get("x", 0))), HEIGHT - round(float(player.get("y", 0))))
        )
        self.screen.blit(sprite, rect)
        label = self.small_font.render(str(player.get("name", "Player")), True, WHITE)
        self.screen.blit(label, label.get_rect(midbottom=(rect.centerx, rect.top - 5)))

    def draw_clean_barn(self):
        self.screen.fill((226, 203, 158))
        pygame.draw.rect(self.screen, (237, 222, 190), (0, 0, WIDTH, 510))
        for x in range(0, WIDTH, 100):
            pygame.draw.line(self.screen, (216, 195, 160), (x, 0), (x, 510), 2)
        pygame.draw.rect(self.screen, (130, 77, 42), (22, 0, 18, 510))
        pygame.draw.rect(self.screen, (130, 77, 42), (WIDTH - 40, 0, 18, 510))
        pygame.draw.rect(self.screen, (153, 94, 49), (0, 50, WIDTH, 13))
        pygame.draw.rect(self.screen, (153, 94, 49), (0, 495, WIDTH, 15))

        window = pygame.Rect(548, 86, 145, 122)
        pygame.draw.rect(self.screen, (130, 77, 42), window.inflate(16, 16), border_radius=4)
        pygame.draw.rect(self.screen, (162, 211, 217), window)
        pygame.draw.line(self.screen, (250, 239, 209), window.midtop, window.midbottom, 7)
        pygame.draw.line(self.screen, (250, 239, 209), window.midleft, window.midright, 7)
        pygame.draw.circle(self.screen, (255, 222, 125), (window.x + 35, window.y + 32), 17)

        pygame.draw.rect(self.screen, (157, 103, 55), (0, 510, WIDTH, 90))
        for x in range(-20, WIDTH + 40, 64):
            pygame.draw.line(self.screen, (124, 77, 43), (x, 510), (x, HEIGHT), 3)
        for y in range(533, HEIGHT, 32):
            pygame.draw.line(self.screen, (124, 77, 43), (0, y), (WIDTH, y), 2)
        pygame.draw.rect(self.screen, (97, 63, 38), (0, 510, WIDTH, 6))

    def draw_clean_platform(self, rect):
        pygame.draw.rect(self.screen, (77, 54, 35), rect.move(0, 5), border_radius=5)
        pygame.draw.rect(self.screen, (157, 100, 44), rect, border_radius=5)
        pygame.draw.rect(self.screen, (244, 205, 112),
                         (rect.x, rect.y, rect.width, 8), border_radius=4)
        pygame.draw.line(self.screen, (109, 68, 34), (rect.left + 5, rect.bottom - 3),
                         (rect.right - 5, rect.bottom - 3), 2)
        for x in range(rect.left + 24, rect.right - 8, 34):
            pygame.draw.line(self.screen, (194, 139, 66), (x, rect.y + 11), (x, rect.bottom - 7), 2)
        for x in range(rect.left + 12, rect.right - 8, 50):
            pygame.draw.circle(self.screen, (91, 61, 34), (x, rect.y + 16), 2)

    def player_sprite(self, image_path, remove_green=False):
        image_path = Path(image_path)
        cache_key = (image_path, remove_green)
        if cache_key in self.images:
            return self.images[cache_key]

        sprite = self.image(image_path).copy()
        if remove_green:
            corner = sprite.get_at((0, 0))
            if corner.g > corner.r * 1.3 and corner.g > corner.b * 1.3:
                for y in range(sprite.get_height()):
                    for x in range(sprite.get_width()):
                        color = sprite.get_at((x, y))
                        if color.g > color.r * 1.3 and color.g > color.b * 1.3:
                            sprite.set_at((x, y), (color.r, color.g, color.b, 0))

        bounds = sprite.get_bounding_rect()
        if bounds.width and bounds.height:
            sprite = sprite.subsurface(bounds).copy()
        width = max(1, round(sprite.get_width() * PLAYER_HEIGHT / sprite.get_height()))
        scaled = pygame.transform.scale(sprite, (width, PLAYER_HEIGHT))
        self.images[cache_key] = scaled
        return scaled

    def player_character_dir(self):
        character_key = CHARACTER_DATA.get(CHARACTERS[self.character_index], "")
        if (TEXTURES / character_key / "idle.png").exists():
            return character_key
        return "normal_chicken"

    def current_player_sprite(self):
        character_dir = self.player_character_dir()
        return self.player_sprite_for(character_dir, self.attack_started)

    def player_sprite_for(self, character_dir, attack_started):
        if character_dir == "gerold" and attack_started is not None:
            frames = []
            for frame_number in range(1, 5):
                frame_path = TEXTURES / "gerold" / f"hit{frame_number}.png"
                if frame_number == 1 and not frame_path.exists():
                    frame_path = TEXTURES / "gerold" / "hti1.png"
                if frame_path.exists():
                    frames.append(frame_path)
            elapsed = pygame.time.get_ticks() - attack_started
            frame_duration = 120
            if frames and elapsed < len(frames) * frame_duration:
                frame = frames[min(elapsed // frame_duration, len(frames) - 1)]
                return self.player_sprite(frame)

        idle_path = TEXTURES / character_dir / "idle.png"
        return self.player_sprite(idle_path, remove_green=character_dir != "gerold")

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                self.handle_resize(event.size)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.handle_click(self.window_to_logical(event.pos))
            elif event.type == pygame.TEXTINPUT and self.focused_input:
                self.append_input(event.text)
            elif event.type == pygame.KEYDOWN:
                self.handle_key(event)

    def handle_click(self, position):
        for input_id, rect in self.input_rects.items():
            if rect.collidepoint(position):
                self.focused_input = input_id
                pygame.key.start_text_input()
                return
        self.focused_input = None
        pygame.key.stop_text_input()
        for button_id, rect in self.buttons.items():
            if rect.collidepoint(position):
                self.activate(button_id)
                return

    def handle_key(self, event):
        if event.key == pygame.K_F11 or (
            event.key == pygame.K_RETURN and event.mod & pygame.KMOD_ALT
        ):
            self.toggle_fullscreen()
            return
        if self.focused_input:
            if event.key == pygame.K_BACKSPACE:
                self.remove_input_character()
            elif event.key == pygame.K_TAB:
                self.focused_input = None
                pygame.key.stop_text_input()
            elif event.key == pygame.K_RETURN:
                self.focused_input = None
                pygame.key.stop_text_input()
            return
        if self.screen_name == "game":
            if event.key == pygame.K_ESCAPE:
                self.screen_name = "pause"
            elif event.key in (pygame.K_a, pygame.K_d, pygame.K_w, pygame.K_SPACE):
                actions = {
                    pygame.K_a: "walk_left",
                    pygame.K_d: "walk_right",
                    pygame.K_w: "jump",
                    pygame.K_SPACE: "attack",
                }
                action = actions[event.key]
                if event.key == pygame.K_a:
                    self.player_facing_left = True
                elif event.key == pygame.K_d:
                    self.player_facing_left = False
                elif event.key == pygame.K_w and self.player_on_ground:
                    self.player_velocity_y = 440
                    self.player_on_ground = False
                elif event.key == pygame.K_SPACE:
                    self.attack_started = pygame.time.get_ticks()
                    self.attack_until = self.attack_started + 480
                self.player_action = action

    def append_input(self, text):
        if self.focused_input == "port" and not text.isdigit():
            return
        current = self.input_value(self.focused_input)
        if len(current) + len(text) <= 64:
            self.set_input_value(self.focused_input, current + text)

    def remove_input_character(self):
        current = self.input_value(self.focused_input)
        self.set_input_value(self.focused_input, current[:-1])

    def input_value(self, input_id):
        return {
            "name": self.name,
            "server": self.server_address,
            "port": self.server_port,
        }[input_id]

    def set_input_value(self, input_id, value):
        if input_id == "name":
            self.name = value
        elif input_id == "server":
            self.server_address = value
        elif input_id == "port":
            self.server_port = value

    def activate(self, button_id):
        self.message = ""
        if button_id == "single":
            self.screen_name = "single"
        elif button_id == "multi":
            self.screen_name = "multi"
        elif button_id == "home":
            self.return_home()
        elif button_id == "quit":
            self.running = False
        elif button_id == "character_previous":
            self.character_index = (self.character_index - 1) % len(CHARACTERS)
        elif button_id == "character_next":
            self.character_index = (self.character_index + 1) % len(CHARACTERS)
        elif button_id == "create_game":
            if not self.name.strip():
                self.message = "Bitte gib deinen Namen ein."
            else:
                self.start_connection("localhost", int(SETUP.get("port", 8765)), local_server=True)
        elif button_id == "join_game":
            if not self.name.strip() or not self.server_address.strip() or not self.server_port:
                self.message = "Bitte fülle Serveradresse, Port und Namen aus."
            else:
                try:
                    port = int(self.server_port)
                    if not 1 <= port <= 65535:
                        raise ValueError
                except ValueError:
                    self.message = "Der Serverport muss zwischen 1 und 65535 liegen."
                else:
                    self.start_connection(self.server_address.strip(), port)
        elif button_id == "play_story":
            self.story_index = 0
            self.story_next_at = pygame.time.get_ticks() + 2500
        elif button_id == "skip_story":
            self.finish_story()
        elif button_id == "resume":
            self.screen_name = "game"
        elif button_id == "leave":
            self.stop_network()
            self.stop_local_server()
            self.return_home()
        elif button_id == "pause_game":
            self.screen_name = "pause"

    def finish_story(self):
        (ROOT / "first_time.txt").write_text("false", encoding="utf-8")
        self.screen_name = "home"

    def handle_story_timer(self):
        if self.screen_name != "story" or self.story_index < 0:
            return
        now = pygame.time.get_ticks()
        while self.story_index < len(self.story_lines) and now >= self.story_next_at:
            self.story_index += 1
            self.story_next_at += 2500
        if self.story_index >= len(self.story_lines):
            self.finish_story()

    def start_connection(self, address, port, local_server=False):
        if self.network_stop:
            self.network_stop.set()
        self.incoming = queue.Queue()
        self.outgoing = queue.Queue()
        stop_event = threading.Event()
        self.network_stop = stop_event
        self.screen_name = "loading"
        self.focused_input = None
        self.server_address = address
        self.server_port = str(port)
        if local_server:
            server_script = ROOT / "server" / "server.py"
            try:
                self.local_server = subprocess.Popen(
                    [sys.executable, str(server_script)],
                    cwd=str(server_script.parent),
                )
            except OSError as error:
                self.screen_name = "single"
                self.message = f"Spielserver konnte nicht gestartet werden: {error}"
                return
        self.network_thread = threading.Thread(
            target=self.network_worker,
            args=(address, port, stop_event, self.incoming, self.outgoing, local_server),
            daemon=True,
        )
        self.network_thread.start()

    def network_worker(self, address, port, stop_event, incoming, outgoing, retry):
        try:
            asyncio.run(self.network_session(address, port, stop_event, incoming, outgoing, retry))
        except Exception as error:
            if not stop_event.is_set():
                incoming.put(("error", f"Verbindungsfehler: {error}"))

    async def network_session(self, address, port, stop_event, incoming, outgoing, retry):
        uri = f"ws://{address}:{port}"
        deadline = asyncio.get_running_loop().time() + (12 if retry else 2)
        while True:
            if stop_event.is_set():
                return
            if retry and self.local_server and self.local_server.poll() is not None:
                incoming.put((
                    "error",
                    f"Der lokale Server wurde beim Start beendet (Exit-Code {self.local_server.returncode}).",
                ))
                return
            try:
                async with websockets.connect(uri, open_timeout=1.5) as websocket:
                    await websocket.send(json.dumps({
                        "type": "join_req",
                        "version": VERSION,
                        "name": self.name.strip(),
                        "character": CHARACTERS[self.character_index],
                    }))
                    response = json.loads(await asyncio.wait_for(websocket.recv(), timeout=5))
                    if response.get("type") != "join" or response.get("status") != "accept":
                        incoming.put(("error", response.get("explain", "Der Server hat die Verbindung abgelehnt.")))
                        return
                    incoming.put(("connected", response))
                    while not stop_event.is_set():
                        while True:
                            try:
                                outgoing_item = outgoing.get_nowait()
                            except queue.Empty:
                                break
                            await websocket.send(json.dumps(outgoing_item))
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=0.02)
                        except asyncio.TimeoutError:
                            continue
                        incoming.put(("message", json.loads(message)))
                    return
            except (OSError, websockets.WebSocketException, asyncio.TimeoutError, ValueError) as error:
                if retry and asyncio.get_running_loop().time() < deadline and not stop_event.is_set():
                    await asyncio.sleep(0.25)
                    continue
                incoming.put(("error", self.connection_error(error)))
                return
            except Exception as error:
                incoming.put(("error", f"Verbindungsfehler: {error}"))
                return

    @staticmethod
    def connection_error(error):
        text = str(error).lower()
        if "invalid uri" in text or "scheme" in text:
            return "Ungültige Serveradresse."
        if "getaddrinfo" in text:
            return "Server nicht erreichbar."
        if "refused" in text:
            return "Verbindung zum Server konnte nicht hergestellt werden."
        return f"Verbindungsfehler: {error}"

    def handle_network_events(self):
        while True:
            try:
                kind, payload = self.incoming.get_nowait()
            except queue.Empty:
                return
            if kind == "connected":
                self.player_id = payload.get("player_id")
                self.remote_players.clear()
                self.remote_attacks.clear()
                self.remote_actions.clear()
                self.screen_name = "game"
                self.message = ""
                self.player_x = float(SETUP.get("spawnx", 75))
                self.player_y = float(SETUP.get("spawny", 102))
                self.player_velocity_y = 0
                self.player_on_ground = True
            elif kind == "message":
                if payload.get("type") == "map":
                    self.game_map = payload["map"]
                elif payload.get("type") == "frame":
                    self.update_frame(payload)
                elif payload.get("type") == "player_left":
                    departed_id = payload.get("player_id")
                    self.remote_players.pop(departed_id, None)
                    self.remote_attacks.pop(departed_id, None)
                    self.remote_actions.pop(departed_id, None)
            elif kind == "error":
                self.screen_name = "single" if self.local_server else "multi"
                self.message = payload
                self.stop_network()
                if self.local_server and self.local_server.poll() is None:
                    self.stop_local_server()

    def update_frame(self, data):
        players = data.get("entities", {}).get("players", {})
        self.remote_players = players if isinstance(players, dict) else {}
        now = pygame.time.get_ticks()
        for player_id, player in self.remote_players.items():
            action = player.get("action")
            previous_action = self.remote_actions.get(player_id)
            if action == "attack" and previous_action != "attack":
                self.remote_attacks[player_id] = now
            elif action != "attack":
                self.remote_attacks.pop(player_id, None)
            self.remote_actions[player_id] = action
        active_players = set(self.remote_players)
        self.remote_attacks = {
            player_id: started
            for player_id, started in self.remote_attacks.items()
            if player_id in active_players
        }
        self.remote_actions = {
            player_id: action
            for player_id, action in self.remote_actions.items()
            if player_id in active_players
        }

    def send_player_state(self):
        if self.screen_name != "game" or not self.player_id:
            return
        now = pygame.time.get_ticks()
        if now - self.last_state_sent < 40:
            return
        self.last_state_sent = now
        if self.player_action == "attack" and now >= self.attack_until:
            self.player_action = "idle"
            self.attack_started = None

        self.outgoing.put({
            "type": "player_state",
            "state": {
                "name": self.name.strip(),
                "character": CHARACTERS[self.character_index],
                "x": self.player_x,
                "y": self.player_y,
                "facing_left": self.player_facing_left,
                "action": self.player_action,
            },
        })

    def update_player(self, delta_time):
        if self.screen_name != "game":
            return

        keys = pygame.key.get_pressed()
        direction = int(keys[pygame.K_d]) - int(keys[pygame.K_a])
        if direction:
            self.player_facing_left = direction < 0
        if self.player_action != "attack":
            self.player_action = "walk" if direction else ("jump" if not self.player_on_ground else "idle")
        self.player_x = max(22, min(WIDTH - 22, self.player_x + direction * 230 * delta_time))

        old_y = self.player_y
        gravity = max(0.1, float(SETUP.get("gravity", 1)))
        self.player_velocity_y -= 780 * gravity * delta_time
        next_y = self.player_y + self.player_velocity_y * delta_time
        landed_y = None
        if self.player_velocity_y <= 0 and self.game_map:
            player_half_width = 18
            for key, platform in self.game_map.items():
                if not key.isdigit():
                    continue
                x1, y1, x2, y2 = platform["size"]
                left, right = sorted((float(x1), float(x2)))
                surface = max(float(y1), float(y2))
                overlaps = self.player_x + player_half_width > left and self.player_x - player_half_width < right
                if overlaps and old_y >= surface >= next_y:
                    landed_y = max(landed_y or surface, surface)

        if landed_y is not None:
            self.player_y = landed_y
            self.player_velocity_y = 0
            self.player_on_ground = True
        else:
            self.player_y = next_y
            self.player_on_ground = False

        if self.player_y < -40:
            self.player_x = float(SETUP.get("spawnx", 75))
            self.player_y = float(SETUP.get("spawny", 102))
            self.player_velocity_y = 0
            self.player_on_ground = True

    def stop_network(self):
        if self.network_stop:
            self.network_stop.set()
            self.network_stop = None

    def stop_local_server(self):
        if self.local_server and self.local_server.poll() is None:
            self.local_server.terminate()
            try:
                self.local_server.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.local_server.kill()
                self.local_server.wait()
        self.local_server = None

    def return_home(self):
        self.screen_name = "home"
        self.focused_input = None
        self.message = ""


if __name__ == "__main__":
    GameClient().run()
