"""All drawing code. Everything is built from pygame primitives."""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import pygame

from .physics import Ball, Vec2
from .rules import Rules, balls_of
from .table import CUSHION_WIDTH, RAIL_WIDTH, Table

FELT = (22, 110, 62)
FELT_DARK = (16, 88, 48)
CUSHION = (18, 95, 52)
WOOD = (110, 62, 28)
WOOD_DARK = (72, 38, 16)
WOOD_LIGHT = (150, 92, 44)
POCKET = (8, 8, 8)
BG = (24, 26, 32)
TEXT = (235, 235, 235)
DIM = (150, 150, 160)
ACCENT = (255, 205, 60)

BALL_COLORS: Dict[int, Tuple[int, int, int]] = {
    0: (245, 245, 236),
    1: (247, 200, 30),
    2: (30, 70, 200),
    3: (210, 35, 35),
    4: (105, 45, 150),
    5: (240, 120, 20),
    6: (20, 125, 65),
    7: (125, 25, 35),
    8: (18, 18, 18),
}
for _n in range(9, 16):
    BALL_COLORS[_n] = BALL_COLORS[_n - 8]

SUPERSAMPLE = 4


def _font(size: int) -> pygame.font.Font:
    return pygame.font.Font(None, size)


def make_ball_sprite(number: int, radius: float) -> pygame.Surface:
    """Render a ball at high resolution and scale it down (anti-aliasing)."""
    ss = SUPERSAMPLE
    R = int(round(radius * ss))
    size = 2 * R
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = (R, R)
    color = BALL_COLORS[number]
    if number >= 9:
        pygame.draw.circle(surf, (245, 245, 236), c, R)
        h = 0.58  # half height of the stripe relative to the radius
        a0 = math.asin(h)
        pts = []
        steps = 24
        for i in range(steps + 1):
            a = -a0 + 2 * a0 * i / steps
            pts.append((R + math.cos(a) * R, R + math.sin(a) * R))
        for i in range(steps + 1):
            a = math.pi - a0 + 2 * a0 * i / steps
            pts.append((R + math.cos(a) * R, R + math.sin(a) * R))
        pygame.draw.polygon(surf, color, pts)
    else:
        pygame.draw.circle(surf, color, c, R)
    if number != 0:
        pygame.draw.circle(surf, (250, 250, 245), c, int(R * 0.5))
        font = _font(int(R * 0.95))
        txt = font.render(str(number), True, (15, 15, 15))
        surf.blit(txt, txt.get_rect(center=(R, R + ss)))
    else:
        pygame.draw.circle(surf, (200, 40, 40), c, int(R * 0.12))
    # soft shading: darker lower-right rim, glossy highlight top-left
    shade = pygame.Surface((size, size), pygame.SRCALPHA)
    for k in range(6):
        alpha = 10 + k * 6
        pygame.draw.circle(shade, (0, 0, 0, alpha), (int(R + R * 0.08 * k), int(R + R * 0.08 * k)), R, max(1, int(R * 0.12)))
    mask = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), c, R)
    shade.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surf.blit(shade, (0, 0))
    pygame.draw.circle(surf, (255, 255, 255, 120), (int(R * 0.62), int(R * 0.58)), int(R * 0.28))
    pygame.draw.circle(surf, (255, 255, 255, 200), (int(R * 0.6), int(R * 0.56)), int(R * 0.12))
    pygame.draw.circle(surf, (0, 0, 0, 90), c, R, max(1, ss // 2))
    out_size = int(round(2 * radius))
    return pygame.transform.smoothscale(surf, (out_size, out_size))


class Renderer:
    def __init__(self, table: Table) -> None:
        self.table = table
        self.sprites = {n: make_ball_sprite(n, table.ball_radius) for n in range(16)}
        self.small_sprites = {n: pygame.transform.smoothscale(s, (16, 16)) for n, s in self.sprites.items()}
        self.font_big = _font(44)
        self.font = _font(28)
        self.font_small = _font(22)
        self.font_tiny = _font(19)
        self.table_surface: Optional[pygame.Surface] = None

    # ---------------------------------------------------------------- table
    def _build_table(self, size: Tuple[int, int]) -> pygame.Surface:
        t = self.table
        surf = pygame.Surface(size)
        surf.fill(BG)
        C, W = CUSHION_WIDTH, RAIL_WIDTH
        outer = pygame.Rect(int(t.left - C - W), int(t.top - C - W), int(t.width + 2 * (C + W)), int(t.height + 2 * (C + W)))
        # wooden rails with a simple bevel and grain
        pygame.draw.rect(surf, WOOD_DARK, outer.inflate(6, 6), border_radius=22)
        pygame.draw.rect(surf, WOOD, outer, border_radius=20)
        pygame.draw.rect(surf, WOOD_LIGHT, outer, 3, border_radius=20)
        for i in range(0, outer.width, 7):
            shade = (WOOD[0] - 8 + (i * 37) % 16, WOOD[1] - 6 + (i * 17) % 10, WOOD[2])
            pygame.draw.line(surf, shade, (outer.left + i, outer.top + 4), (outer.left + i, outer.top + W - 4), 1)
            pygame.draw.line(surf, shade, (outer.left + i, outer.bottom - W + 4), (outer.left + i, outer.bottom - 4), 1)
        felt = pygame.Rect(int(t.left - C), int(t.top - C), int(t.width + 2 * C), int(t.height + 2 * C))
        pygame.draw.rect(surf, FELT, felt)
        # subtle felt vignette
        for k in range(12):
            pygame.draw.rect(surf, (FELT[0] - k // 3, FELT[1] - k, FELT[2] - k // 2), felt.inflate(-k * 2, -k * 2), 1)
        play = pygame.Rect(int(t.left), int(t.top), int(t.width), int(t.height))
        pygame.draw.rect(surf, FELT, play.inflate(-24, -24))
        # cushions as trapezoids behind every cushion segment
        for seg in t.segments:
            a, b = seg.a, seg.b
            d = (b - a).normalized()
            n = d.perp()
            mid = (a + b) * 0.5
            if (t.center - mid).dot(n) > 0:
                n = -n  # outward normal
            pts = [a, b, b + n * C + d * C * 0.9, a + n * C - d * C * 0.9]
            pygame.draw.polygon(surf, CUSHION, [(p.x, p.y) for p in pts])
            pygame.draw.line(surf, (40, 140, 80), (a.x, a.y), (b.x, b.y), 2)
        # diamonds
        for i in range(1, 8):
            if i == 4:
                continue
            x = t.left + t.width * i / 8
            for y in (t.top - C - W / 2, t.bottom + C + W / 2):
                pygame.draw.circle(surf, (235, 225, 190), (int(x), int(y)), 3)
        for i in range(1, 4):
            y = t.top + t.height * i / 4
            for x in (t.left - C - W / 2, t.right + C + W / 2):
                pygame.draw.circle(surf, (235, 225, 190), (int(x), int(y)), 3)
        # pockets
        for p in t.pockets:
            pygame.draw.circle(surf, (40, 30, 20), (int(p.center.x), int(p.center.y)), int(p.radius + 5))
            pygame.draw.circle(surf, POCKET, (int(p.center.x), int(p.center.y)), int(p.radius + 1))
        # head string and spots
        pygame.draw.line(surf, FELT_DARK, (t.head_string_x, t.top + 2), (t.head_string_x, t.bottom - 2), 1)
        for spot in (t.head_spot, t.foot_spot):
            pygame.draw.circle(surf, FELT_DARK, (int(spot.x), int(spot.y)), 3)
        return surf

    def draw_table(self, screen: pygame.Surface) -> None:
        if self.table_surface is None or self.table_surface.get_size() != screen.get_size():
            self.table_surface = self._build_table(screen.get_size())
        screen.blit(self.table_surface, (0, 0))

    # ---------------------------------------------------------------- balls
    def draw_balls(self, screen: pygame.Surface, balls: List[Ball], hide_cue: bool = False) -> None:
        shadow = pygame.Surface((screen.get_width(), screen.get_height()), pygame.SRCALPHA)
        for b in balls:
            if b.pocketed or (hide_cue and b.is_cue):
                continue
            pygame.draw.circle(shadow, (0, 0, 0, 70), (int(b.pos.x + 3), int(b.pos.y + 4)), int(b.radius))
        screen.blit(shadow, (0, 0))
        for b in balls:
            if b.pocketed or (hide_cue and b.is_cue):
                continue
            s = self.sprites[b.number]
            screen.blit(s, s.get_rect(center=(round(b.pos.x), round(b.pos.y))))

    def draw_ghost_cue(self, screen: pygame.Surface, pos: Vec2, valid: bool) -> None:
        s = self.sprites[0].copy()
        s.set_alpha(170)
        screen.blit(s, s.get_rect(center=(round(pos.x), round(pos.y))))
        color = (90, 230, 120) if valid else (230, 60, 60)
        pygame.draw.circle(screen, color, (round(pos.x), round(pos.y)), int(self.table.ball_radius + 3), 2)

    # ------------------------------------------------------------ aim & cue
    def draw_aim(self, screen: pygame.Surface, start: Vec2, guide) -> None:
        end, ghost, target_dir, cue_dir = guide
        _dashed_line(screen, (240, 240, 240), start, end, 8, 6)
        if ghost is not None:
            pygame.draw.circle(screen, (240, 240, 240), (round(ghost.x), round(ghost.y)), int(self.table.ball_radius), 1)
            if target_dir is not None:
                tgt = ghost + target_dir * (self.table.ball_radius * 2)
                p2 = tgt + target_dir * 70
                pygame.draw.line(screen, ACCENT, (tgt.x, tgt.y), (p2.x, p2.y), 2)
            if cue_dir is not None:
                p2 = ghost + cue_dir * 45
                pygame.draw.line(screen, (170, 200, 255), (ghost.x, ghost.y), (p2.x, p2.y), 1)

    def draw_cue_stick(self, screen: pygame.Surface, cue_pos: Vec2, angle: float, pull: float) -> None:
        d = Vec2.from_angle(angle)
        n = d.perp()
        tip_off = self.table.ball_radius + 5 + pull
        length = 340
        tip = cue_pos - d * tip_off
        butt = cue_pos - d * (tip_off + length)

        def quad(p0: Vec2, p1: Vec2, w0: float, w1: float, color, surf: pygame.Surface = screen) -> None:
            pts = [p0 + n * w0, p1 + n * w1, p1 - n * w1, p0 - n * w0]
            pygame.draw.polygon(surf, color, [(p.x, p.y) for p in pts])

        shadow = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        shadow_off = Vec2(5, 8)
        quad(tip + shadow_off, butt + shadow_off, 2.5, 6, (0, 0, 0, 80), shadow)
        screen.blit(shadow, (0, 0))
        ferrule = tip - d * 8
        joint = tip - d * (length * 0.6)
        quad(tip, ferrule, 2.5, 2.6, (240, 240, 230))
        quad(ferrule, joint, 2.6, 4.4, (222, 184, 120))
        quad(joint, butt, 4.4, 6.0, (70, 30, 15))
        quad(joint - d * 6, joint - d * 14, 4.5, 4.6, (220, 220, 220))
        quad(tip + d * 0.1, tip - d * 2, 2.4, 2.4, (60, 110, 200))  # chalked tip

    # ------------------------------------------------------------------- HUD
    def draw_hud(self, screen: pygame.Surface, rules: Rules, balls: List[Ball], message: str, power: float, state_hint: str) -> None:
        w = screen.get_width()
        on_table = {b.number for b in balls if not b.pocketed and b.number != 0}
        for idx in (0, 1):
            active = rules.current == idx and rules.winner is None
            rect = pygame.Rect(16 if idx == 0 else w - 16 - 250, 10, 250, 64)
            pygame.draw.rect(screen, (44, 48, 60) if active else (34, 36, 44), rect, border_radius=10)
            if active:
                pygame.draw.rect(screen, ACCENT, rect, 2, border_radius=10)
            name = self.font.render(Rules.player_name(idx), True, ACCENT if active else TEXT)
            screen.blit(name, (rect.x + 12, rect.y + 8))
            group = rules.groups[idx]
            label = group.capitalize() if group else "Open table"
            g = self.font_small.render(label, True, DIM)
            screen.blit(g, (rect.right - 12 - g.get_width(), rect.y + 12))
            if group:
                for k, n in enumerate(sorted(balls_of(group))):
                    s = self.small_sprites[n].copy()
                    if n not in on_table:
                        s.set_alpha(60)
                    screen.blit(s, (rect.x + 12 + k * 20, rect.y + 38))
                if not (on_table & balls_of(group)):
                    s = self.small_sprites[8]
                    screen.blit(s, (rect.x + 12 + 7 * 20 + 8, rect.y + 38))
        msg = self.font_small.render(message, True, TEXT)
        max_w = w - 2 * (16 + 250 + 12)
        if msg.get_width() > max_w:
            msg = pygame.transform.smoothscale(msg, (max_w, int(msg.get_height() * max_w / msg.get_width())))
        screen.blit(msg, msg.get_rect(center=(w // 2, 34)))
        hint = self.font_small.render(state_hint, True, DIM)
        screen.blit(hint, hint.get_rect(center=(w // 2, 58)))

        # power bar
        h = screen.get_height()
        bar = pygame.Rect(16, h - 36, 180, 18)
        pygame.draw.rect(screen, (40, 42, 50), bar, border_radius=6)
        fill = bar.copy()
        fill.width = int(bar.width * max(0.0, min(1.0, power)))
        if fill.width > 0:
            col = (int(80 + 175 * power), int(220 - 150 * power), 70)
            pygame.draw.rect(screen, col, fill, border_radius=6)
        pygame.draw.rect(screen, (90, 92, 100), bar, 1, border_radius=6)
        screen.blit(self.font_small.render("Power", True, DIM), (bar.right + 8, bar.y + 1))
        controls = "Mouse: aim  |  Hold LMB + pull back, release: shoot  |  RMB: cancel  |  R: new game  |  Esc: pause menu"
        c = self.font_tiny.render(controls, True, DIM)
        screen.blit(c, (w - 16 - c.get_width(), h - 32))

    def draw_game_over(self, screen: pygame.Surface, text: str) -> None:
        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        screen.blit(overlay, (0, 0))
        t = self.font_big.render(text, True, ACCENT)
        screen.blit(t, t.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2 - 10)))
        s = self.font.render("Press R to play again or Esc for the menu", True, TEXT)
        screen.blit(s, s.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2 + 30)))


def _dashed_line(screen: pygame.Surface, color, a: Vec2, b: Vec2, dash: float, gap: float) -> None:
    d = b - a
    length = d.length()
    if length < 1e-6:
        return
    u = d / length
    pos = 0.0
    while pos < length:
        p0 = a + u * pos
        p1 = a + u * min(pos + dash, length)
        pygame.draw.line(screen, color, (p0.x, p0.y), (p1.x, p1.y), 2)
        pos += dash + gap
