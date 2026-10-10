"""Application shell: owns the window, switches between scenes with smooth
fade transitions and runs the main loop."""
from __future__ import annotations

import random
from typing import Optional

import pygame

from .game import Game
from .menu import AttractBackground, HowToScreen, MainMenu, SettingsScreen, Title
from .render import Renderer
from .settings import Settings
from .table import WINDOW_HEIGHT, WINDOW_WIDTH, Table
from .ui import DIM, font

FADE_TIME = 0.35  # seconds for each half of a transition (out, then in)

SCENES = ("menu", "howto", "settings", "game")


class App:
    def __init__(self, settings: Optional[Settings] = None, seed: Optional[int] = None) -> None:
        self.settings = settings or Settings()
        self.size = (WINDOW_WIDTH, WINDOW_HEIGHT)
        self.table = Table()
        self.renderer = Renderer(self.table)
        self.background = AttractBackground(self.table, self.renderer, random.Random(seed))
        title = Title()
        self.menu = MainMenu(self.background, title, self.size)
        self.howto = HowToScreen(self.background, self.size)
        self.settings_screen = SettingsScreen(self.background, self.settings, self.size)
        self.game: Optional[Game] = None
        self.scene_name = "menu"
        self.scene = self.menu
        self.running = True
        self.fade = 1.0  # start black and fade in
        self.fade_dir = -1  # +1 fading out, -1 fading in, 0 idle
        self.pending: Optional[str] = None
        self.fps = 0.0
        self._fps_font = font(24)

    # ------------------------------------------------------------- scenes
    @property
    def transitioning(self) -> bool:
        return self.fade_dir == 1

    def go(self, name: str) -> None:
        """Start a fade-out; the scene switches when the screen is black."""
        if name not in SCENES or self.transitioning:
            return
        self.pending = name
        self.fade_dir = 1

    def _switch(self, name: str) -> None:
        if name == "game":
            self.game = Game(self.settings, self.renderer)
            self.scene = self.game
        elif name == "menu":
            self.game = None
            self.menu.menu.selected = 0
            self.scene = self.menu
        elif name == "howto":
            self.howto.menu.selected = 0
            self.scene = self.howto
        elif name == "settings":
            self.settings_screen.menu.selected = 0
            self.scene = self.settings_screen
        self.scene_name = name

    def perform(self, action: Optional[str]) -> None:
        if action is None:
            return
        if action == "quit":
            self.running = False
        elif action == "play":
            self.go("game")
        else:
            self.go(action)

    # -------------------------------------------------------------- loop
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
            return
        if self.transitioning:
            return  # ignore input while the screen fades out
        self.perform(self.scene.handle_event(event))

    def update(self, dt: float) -> None:
        self.background.enabled = self.settings.menu_animation
        if self.fade_dir == 1:
            self.fade = min(1.0, self.fade + dt / FADE_TIME)
            if self.fade >= 1.0:
                if self.pending is not None:
                    self._switch(self.pending)
                    self.pending = None
                self.fade_dir = -1
        elif self.fade_dir == -1:
            self.fade = max(0.0, self.fade - dt / FADE_TIME)
            if self.fade <= 0.0:
                self.fade_dir = 0
        self.scene.update(dt)

    def draw(self, screen: pygame.Surface) -> None:
        self.scene.draw(screen)
        if self.settings.show_fps:
            t = self._fps_font.render(f"{self.fps:.0f} FPS", True, DIM)
            screen.blit(t, (screen.get_width() - t.get_width() - 10, screen.get_height() - 58))
        if self.fade > 0.0:
            # smoothstep easing for a softer fade
            a = self.fade * self.fade * (3 - 2 * self.fade)
            overlay = pygame.Surface(screen.get_size())
            overlay.fill((0, 0, 0))
            overlay.set_alpha(int(255 * a))
            screen.blit(overlay, (0, 0))


def run() -> None:
    pygame.init()
    pygame.display.set_caption("Pool - 8-Ball (velocity Verlet physics)")
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    clock = pygame.time.Clock()
    app = App()
    while app.running:
        dt = clock.tick(120) / 1000.0
        app.fps = clock.get_fps()
        for event in pygame.event.get():
            app.handle_event(event)
            if not app.running:
                break
        app.update(dt)
        app.draw(screen)
        pygame.display.flip()
    pygame.quit()
