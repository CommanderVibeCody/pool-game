"""Start screen: animated attract-mode background, main menu, how-to-play and
settings screens.

Each screen follows the same small scene protocol used by ``pool.app.App``:

* ``handle_event(event) -> Optional[str]`` returns an action
  (``"play"``, ``"howto"``, ``"settings"``, ``"menu"`` or ``"quit"``),
* ``update(dt)`` advances animations,
* ``draw(screen)`` renders the scene.
"""
from __future__ import annotations

import math
import random
from typing import List, Optional

import pygame

from .physics import Ball, PhysicsParams, PhysicsWorld, Vec2
from .render import Renderer, make_ball_sprite
from .settings import Settings
from .table import Table
from .ui import ACCENT, DIM, TEXT, MenuList, draw_panel, font, wrap_text

FIXED_DT = 1.0 / 120.0


class AttractBackground:
    """The real physics engine playing by itself behind the menus.

    It breaks a fresh rack, then keeps shooting the cue ball at random object
    balls. When the cue ball is pocketed or only a few balls are left, the
    balls are re-racked and the cycle starts again.
    """

    def __init__(self, table: Table, renderer: Renderer, rng: Optional[random.Random] = None) -> None:
        self.table = table
        self.renderer = renderer
        self.rng = rng or random.Random()
        self.accumulator = 0.0
        self.idle_time = 0.0
        self.shots = 0
        self.racks = 0
        self.enabled = True  # False freezes the animation (setting)
        self.rerack()

    def rerack(self) -> None:
        self.racks += 1
        self.balls: List[Ball] = self.table.create_balls()
        self.world = PhysicsWorld(self.balls, self.table.segments, self.table.pockets, self.table.bounds,
                                  PhysicsParams(), FIXED_DT)
        angle = self.rng.uniform(-0.03, 0.03)
        self.balls[0].vel = Vec2.from_angle(angle, self.rng.uniform(1300, 1500))
        self.idle_time = 0.0

    def _next_shot(self) -> None:
        cue = self.balls[0]
        targets = [b for b in self.balls if not b.pocketed and not b.is_cue]
        if cue.pocketed or len(targets) < 5:
            self.rerack()
            return
        target = self.rng.choice(targets)
        d = target.pos - cue.pos
        angle = math.atan2(d.y, d.x) + self.rng.uniform(-0.05, 0.05)
        cue.vel = Vec2.from_angle(angle, self.rng.uniform(600, 1300))
        self.shots += 1

    def update(self, dt: float) -> None:
        if not self.enabled:
            return
        self.accumulator += min(dt, 0.1)
        while self.accumulator >= FIXED_DT:
            self.world.step()
            self.accumulator -= FIXED_DT
        if self.world.all_stopped():
            self.idle_time += dt
            if self.idle_time > 0.8:
                self.idle_time = 0.0
                self._next_shot()
        else:
            self.idle_time = 0.0

    def draw(self, screen: pygame.Surface, dim: int = 130) -> None:
        self.renderer.draw_table(screen)
        self.renderer.draw_balls(screen, self.balls)
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        shade.fill((6, 8, 12, dim))
        screen.blit(shade, (0, 0))


class Title:
    """Big glowing 'POOL' logo with drop shadow and a bobbing 8-ball."""

    def __init__(self) -> None:
        self.time = 0.0
        big = font(190)
        self.text = big.render("POOL", True, ACCENT)
        self.shadow = big.render("POOL", True, (0, 0, 0))
        self.shadow.set_alpha(170)
        w, h = self.text.get_size()
        # Glow: orange text on black, blurred by down- and up-scaling. It is
        # blitted additively, so black adds nothing and only the halo shows.
        glow_src = big.render("POOL", True, (255, 140, 20), (0, 0, 0))
        pad = 40
        canvas = pygame.Surface((w + 2 * pad, h + 2 * pad))
        canvas.fill((0, 0, 0))
        canvas.blit(glow_src, (pad, pad))
        blur = canvas
        for factor in (4, 8):
            small = pygame.transform.smoothscale(canvas, (canvas.get_width() // factor, canvas.get_height() // factor))
            blur = pygame.transform.smoothscale(small, canvas.get_size())
            canvas = blur
        self.glow = blur
        self.glow_pad = pad
        self.subtitle = font(34).render("8-Ball  -  hand-made velocity Verlet physics", True, TEXT)
        self.eight = make_ball_sprite(8, 30)

    def update(self, dt: float) -> None:
        self.time += dt

    def draw(self, screen: pygame.Surface, center_y: int = 140) -> None:
        cx = screen.get_width() // 2
        rect = self.text.get_rect(center=(cx + 30, center_y))
        backdrop = pygame.Rect(0, 0, rect.width + 260, rect.height + 120)
        backdrop.center = (cx, center_y + 30)
        for k in range(6):  # soft-edged dark backdrop behind the logo
            draw_panel(screen, backdrop.inflate(-k * 14, -k * 10), color=(4, 6, 10), alpha=28, radius=60)
        pulse = 0.55 + 0.45 * math.sin(self.time * 2.2)
        glow = self.glow.copy()
        level = int(255 * pulse)
        glow.fill((level, level, level), special_flags=pygame.BLEND_RGB_MULT)
        screen.blit(glow, (rect.x - self.glow_pad, rect.y - self.glow_pad), special_flags=pygame.BLEND_RGB_ADD)
        screen.blit(self.shadow, rect.move(6, 8))
        screen.blit(self.text, rect)
        bob = 6 * math.sin(self.time * 3.0)
        e = self.eight.get_rect(center=(rect.left - 46, center_y - 6 + bob))
        pygame.draw.ellipse(screen, (0, 0, 0), pygame.Rect(e.x + 6, e.bottom + 4 - bob / 2, e.width - 12, 10))
        screen.blit(self.eight, e)
        sub = self.subtitle.get_rect(center=(cx, center_y + 88))
        screen.blit(self.subtitle, sub)


class MainMenu:
    ITEMS = [("play", "Play (2 players)"), ("howto", "How to Play"), ("settings", "Settings"), ("quit", "Quit")]

    def __init__(self, background: AttractBackground, title: Title, size) -> None:
        self.background = background
        self.title = title
        w, h = size
        self.menu = MenuList(self.ITEMS, center=(w // 2, int(h * 0.62)), spacing=66, width=360)
        self.hint = font(24).render("Up/Down or mouse to select  -  Enter or click to confirm  -  Esc to quit",
                                    True, DIM)

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return "quit"
        return self.menu.handle_event(event)

    def update(self, dt: float) -> None:
        self.background.update(dt)
        self.title.update(dt)
        self.menu.update(dt)

    def draw(self, screen: pygame.Surface) -> None:
        self.background.draw(screen)
        self.title.draw(screen)
        self.menu.draw(screen)
        screen.blit(self.hint, self.hint.get_rect(center=(screen.get_width() // 2, screen.get_height() - 28)))


HOWTO_CONTROLS = [
    ("Move mouse", "Aim the cue"),
    ("Hold LMB + pull back", "Set the power"),
    ("Release LMB", "Shoot"),
    ("Right mouse button", "Cancel the shot"),
    ("Click (ball in hand)", "Place the cue ball"),
    ("R", "Restart the game"),
    ("Esc", "Pause menu / back"),
]

HOWTO_RULES = [
    "Player 1 breaks. The table stays open after the break.",
    "The first legally pocketed ball decides your group: solids (1-7) or stripes (9-15).",
    "Pocket one of your own balls to shoot again.",
    "Fouls (scratch, no ball hit, wrong ball hit first) give your opponent ball in hand.",
    "Clear your group, then pocket the 8-ball to win. The 8-ball too early or with a foul loses.",
]


class HowToScreen:
    def __init__(self, background: AttractBackground, size) -> None:
        self.background = background
        w, h = size
        self.size = size
        self.menu = MenuList([("menu", "Back")], center=(w // 2, h - 70), width=220)
        self.h1 = font(64)
        self.h2 = font(36)
        self.body = font(27)

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            return "menu"
        return self.menu.handle_event(event)

    def update(self, dt: float) -> None:
        self.background.update(dt)
        self.menu.update(dt)

    def draw(self, screen: pygame.Surface) -> None:
        self.background.draw(screen, dim=170)
        w, _ = screen.get_size()
        title = self.h1.render("How to Play", True, ACCENT)
        screen.blit(title, title.get_rect(center=(w // 2, 70)))
        left = pygame.Rect(40, 120, w // 2 - 60, 420)
        right = pygame.Rect(w // 2 + 20, 120, w // 2 - 60, 420)
        for rect, heading in ((left, "Controls"), (right, "Rules (8-ball)")):
            draw_panel(screen, rect, alpha=210, border=(90, 95, 110))
            hd = self.h2.render(heading, True, ACCENT)
            screen.blit(hd, (rect.x + 24, rect.y + 20))
        y = left.y + 70
        for key, action in HOWTO_CONTROLS:
            k = self.body.render(key, True, TEXT)
            a = self.body.render(action, True, DIM)
            screen.blit(k, (left.x + 24, y))
            screen.blit(a, (left.x + 250, y))
            y += 44
        y = right.y + 70
        for rule in HOWTO_RULES:
            for i, line in enumerate(wrap_text(self.body, rule, right.width - 64)):
                if i == 0:
                    pygame.draw.circle(screen, ACCENT, (right.x + 30, y + 9), 4)
                t = self.body.render(line, True, TEXT)
                screen.blit(t, (right.x + 44, y))
                y += 30
            y += 14
        self.menu.draw(screen)


class SettingsScreen:
    TOGGLES = [
        ("show_aim_guide", "Aim guide"),
        ("show_fps", "Show FPS"),
        ("menu_animation", "Menu animation"),
    ]

    def __init__(self, background: AttractBackground, settings: Settings, size) -> None:
        self.background = background
        self.settings = settings
        w, h = size
        items = [(key, "") for key, _ in self.TOGGLES] + [("menu", "Back")]
        self.menu = MenuList(items, center=(w // 2, int(h * 0.55)), spacing=70, width=420)
        self._refresh_labels()
        self.h1 = font(64)
        self.hint = font(24).render("Enter, click or Left/Right to toggle  -  Esc to go back", True, DIM)

    def _refresh_labels(self) -> None:
        for key, label in self.TOGGLES:
            state = "On" if getattr(self.settings, key) else "Off"
            self.menu.set_label(key, f"{label}: {state}")

    def toggle(self, key: str) -> None:
        setattr(self.settings, key, not getattr(self.settings, key))
        self._refresh_labels()

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                return "menu"
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d):
                if self.menu.selected_key != "menu":
                    self.toggle(self.menu.selected_key)
                return None
        action = self.menu.handle_event(event)
        if action is not None and action != "menu":
            self.toggle(action)
            return None
        return action

    def update(self, dt: float) -> None:
        self.background.update(dt)
        self.menu.update(dt)

    def draw(self, screen: pygame.Surface) -> None:
        self.background.draw(screen, dim=160)
        w, h = screen.get_size()
        title = self.h1.render("Settings", True, ACCENT)
        tr = title.get_rect(center=(w // 2, 150))
        draw_panel(screen, tr.inflate(60, 24), alpha=200, border=(90, 95, 110))
        screen.blit(title, tr)
        self.menu.draw(screen)
        screen.blit(self.hint, self.hint.get_rect(center=(w // 2, h - 28)))
