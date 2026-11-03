import subprocess
from pathlib import Path
import sys

import pygame

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 800, 600
BACKGROUND = (205, 164, 52)
PANEL = (231, 191, 76)
BUTTON = (255, 246, 143)
BUTTON_HOVER = (255, 252, 190)
TEXT = (48, 34, 8)
MUTED = (102, 75, 24)

class Launcher:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Chicken Escapes Launcher")
        self.windowed_size = (WIDTH, HEIGHT)
        self.display = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        self.screen = pygame.Surface((WIDTH, HEIGHT))
        self.viewport = pygame.Rect(0, 0, WIDTH, HEIGHT)
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.clock = pygame.time.Clock()
        self.title_font = pygame.font.SysFont("Arial", 40, bold=True)
        self.font = pygame.font.SysFont("Arial", 24)
        self.small_font = pygame.font.SysFont("Arial", 18)
        self.eyebrow_font = pygame.font.SysFont("Arial", 15, bold=True)
        self.versions = self.load_launch_versions(ROOT / "versions.txt")
        self.message = ""
        self.game_process = None

    @staticmethod
    def load_launch_versions(file_path):
        path = Path(file_path)
        if not path.exists():
            return []
        versions = []
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if ":" in line:
                    folder, display_name = line.split(":", 1)
                    folder = folder.strip()
                    display_name = display_name.strip()
                    if folder and display_name:
                        versions.append((folder, display_name))
        return versions

    def launch_version(self, folder):
        base_path = (ROOT / folder).resolve()
        if ROOT not in base_path.parents:
            self.message = "Ungültiger Versionspfad."
            return
        exe_path = base_path / "client.exe"
        py_path = base_path / "client.py"
        try:
            if exe_path.exists():
                self.game_process = subprocess.Popen([str(exe_path)], cwd=str(base_path), shell=False)
            elif py_path.exists():
                self.game_process = subprocess.Popen([sys.executable, str(py_path)], cwd=str(base_path), shell=False)
            else:
                self.message = f"Keine client.exe oder client.py in {base_path} gefunden."
        except OSError as error:
            self.message = f"Version konnte nicht gestartet werden: {error}"

    def draw(self):
        self.screen.fill(BACKGROUND)
        pygame.draw.circle(self.screen, (217, 177, 64), (745, 80), 180)
        pygame.draw.circle(self.screen, (194, 146, 40), (55, 585), 150)
        pygame.draw.rect(self.screen, (163, 117, 30), (0, 0, WIDTH, 5))
        pygame.draw.rect(self.screen, (145, 99, 27), (149, 67, 510, 482), border_radius=20)
        pygame.draw.rect(self.screen, PANEL, (145, 60, 510, 482), border_radius=20)
        eyebrow = self.eyebrow_font.render("CHICKEN ESCAPES", True, BUTTON)
        self.screen.blit(eyebrow, eyebrow.get_rect(center=(400, 118)))
        title = self.title_font.render("Dein Abenteuer", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(400, 165)))
        subtitle = self.small_font.render("Wähle eine Version zum Spielen", True, MUTED)
        self.screen.blit(subtitle, subtitle.get_rect(center=(400, 202)))

        self.version_buttons = []
        for index, (_, label) in enumerate(self.versions):
            rect = pygame.Rect(195, 235 + index * 75, 410, 56)
            color = BUTTON_HOVER if rect.collidepoint(self.window_to_logical(pygame.mouse.get_pos())) else BUTTON
            pygame.draw.rect(self.screen, color, rect, border_radius=10)
            pygame.draw.rect(self.screen, (186, 139, 43), rect, 1, border_radius=10)
            text = self.font.render(label, True, TEXT)
            previous_clip = self.screen.get_clip()
            self.screen.set_clip(rect.inflate(-42, -4))
            self.screen.blit(text, text.get_rect(center=rect.center))
            self.screen.set_clip(previous_clip)
            arrow = self.small_font.render("›", True, BUTTON)
            self.screen.blit(arrow, arrow.get_rect(midright=(rect.right - 18, rect.centery)))
            self.version_buttons.append(rect)
        if not self.versions:
            text = self.small_font.render("Keine Versionen in versions.txt gefunden.", True, MUTED)
            self.screen.blit(text, text.get_rect(center=(400, 260)))
        if self.message:
            text = self.small_font.render(self.message, True, (255, 142, 145))
            self.screen.blit(text, text.get_rect(center=(400, 540)))

    def present(self):
        display_width, display_height = self.display.get_size()
        display_width, display_height = max(1, display_width), max(1, display_height)
        self.scale_x = display_width / WIDTH
        self.scale_y = display_height / HEIGHT
        self.viewport = self.display.get_rect()
        self.display.blit(pygame.transform.smoothscale(self.screen, (display_width, display_height)), self.viewport)
        pygame.display.flip()

    def window_to_logical(self, position):
        x = (position[0] - self.viewport.left) / self.scale_x
        y = (position[1] - self.viewport.top) / self.scale_y
        return round(x), round(y)

    def run(self):
        running = True
        try:
            while running:
                self.draw()
                self.present()
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.VIDEORESIZE:
                        self.windowed_size = (max(320, event.w), max(240, event.h))
                        self.display = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        logical_pos = self.window_to_logical(event.pos)
                        for index, rect in enumerate(self.version_buttons):
                            if rect.collidepoint(logical_pos):
                                self.launch_version(self.versions[index][0])
                                if not self.message:
                                    running = False
                                break
                self.clock.tick(60)
        finally:
            pygame.quit()

        if self.game_process:
            try:
                self.game_process.wait()
            except KeyboardInterrupt:
                if self.game_process.poll() is None:
                    self.game_process.terminate()
                    self.game_process.wait()
                raise


if __name__ == "__main__":
    Launcher().run()