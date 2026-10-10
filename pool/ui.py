"""Small reusable UI widgets drawn with pygame primitives."""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import pygame

ACCENT = (255, 205, 60)
TEXT = (235, 235, 235)
DIM = (160, 165, 175)
PANEL = (28, 32, 40)

CONFIRM_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)
UP_KEYS = (pygame.K_UP, pygame.K_w)
DOWN_KEYS = (pygame.K_DOWN, pygame.K_s)


def font(size: int) -> pygame.font.Font:
    return pygame.font.Font(None, size)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_color(c0, c1, t: float) -> Tuple[int, int, int]:
    return tuple(int(lerp(a, b, t)) for a, b in zip(c0, c1))  # type: ignore[return-value]


def draw_panel(screen: pygame.Surface, rect: pygame.Rect, color=(14, 18, 24), alpha: int = 200, radius: int = 18,
               border=None) -> None:
    surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(surf, (*color, alpha), surf.get_rect(), border_radius=radius)
    if border is not None:
        pygame.draw.rect(surf, border, surf.get_rect(), 2, border_radius=radius)
    screen.blit(surf, rect.topleft)


def wrap_text(fnt: pygame.font.Font, text: str, width: int) -> List[str]:
    """Greedy word wrap so that every line fits into ``width`` pixels."""
    lines: List[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if fnt.size(candidate)[0] <= width or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


class MenuList:
    """Vertical list of buttons with keyboard and mouse navigation.

    ``handle_event`` returns the key of an activated item (Enter/Space or a
    left click on an item) and ``None`` otherwise. Hover/selection is animated
    smoothly in ``update``.
    """

    def __init__(self, items: Sequence[Tuple[str, str]], center: Tuple[int, int], spacing: int = 64,
                 width: int = 340, height: int = 50, font_size: int = 40) -> None:
        self.items: List[Tuple[str, str]] = list(items)
        self.center = center
        self.spacing = spacing
        self.width = width
        self.height = height
        self.font_size = font_size
        self.selected = 0
        self.anim = [0.0] * len(self.items)
        self.time = 0.0
        self._font: Optional[pygame.font.Font] = None

    # ----------------------------------------------------------------- data
    @property
    def selected_key(self) -> str:
        return self.items[self.selected][0]

    def set_label(self, key: str, label: str) -> None:
        self.items = [(k, label if k == key else l) for k, l in self.items]

    def select(self, key: str) -> None:
        for i, (k, _) in enumerate(self.items):
            if k == key:
                self.selected = i

    def rects(self) -> List[pygame.Rect]:
        cx, cy = self.center
        n = len(self.items)
        top = cy - (n - 1) * self.spacing / 2
        return [pygame.Rect(0, 0, self.width, self.height).move(cx - self.width // 2,
                                                              int(top + i * self.spacing - self.height / 2))
                for i in range(n)]

    def item_at(self, pos) -> Optional[int]:
        for i, r in enumerate(self.rects()):
            if r.collidepoint(pos):
                return i
        return None

    # ---------------------------------------------------------------- input
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        n = len(self.items)
        if event.type == pygame.KEYDOWN:
            if event.key in UP_KEYS:
                self.selected = (self.selected - 1) % n
            elif event.key in DOWN_KEYS:
                self.selected = (self.selected + 1) % n
            elif event.key in CONFIRM_KEYS:
                return self.selected_key
        elif event.type == pygame.MOUSEMOTION:
            i = self.item_at(event.pos)
            if i is not None:
                self.selected = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            i = self.item_at(event.pos)
            if i is not None:
                self.selected = i
                return self.selected_key
        return None

    # ------------------------------------------------------------ animation
    def update(self, dt: float) -> None:
        self.time += dt
        k = min(1.0, dt * 12.0)
        for i in range(len(self.anim)):
            target = 1.0 if i == self.selected else 0.0
            self.anim[i] += (target - self.anim[i]) * k

    def draw(self, screen: pygame.Surface) -> None:
        if self._font is None:
            self._font = font(self.font_size)
        for i, (rect, (_, label)) in enumerate(zip(self.rects(), self.items)):
            a = self.anim[i]
            r = rect.inflate(int(24 * a), int(6 * a))
            if a > 0.02:
                for grow, alpha in ((22, 18), (12, 30)):
                    gr = r.inflate(grow, grow)
                    glow = pygame.Surface(gr.size, pygame.SRCALPHA)
                    pygame.draw.rect(glow, (*ACCENT, int(alpha * a)), glow.get_rect(), border_radius=14 + grow // 2)
                    screen.blit(glow, gr.topleft)
            # bouncing arrows on both sides of the selected item
            draw_panel(screen, r, color=lerp_color((20, 24, 32), (52, 42, 16), a), alpha=int(190 + 50 * a), radius=14,
                       border=lerp_color((90, 95, 110), ACCENT, a))
            if a > 0.02:
                off = 6 * math.sin(self.time * 6.0) * a
                y = r.centery
                lx = r.left + 22 - off
                rx = r.right - 22 + off
                pygame.draw.polygon(screen, ACCENT, [(lx - 6, y - 8), (lx + 6, y), (lx - 6, y + 8)])
                pygame.draw.polygon(screen, ACCENT, [(rx + 6, y - 8), (rx - 6, y), (rx + 6, y + 8)])
            txt = self._font.render(label, True, lerp_color(TEXT, ACCENT, a))
            screen.blit(txt, txt.get_rect(center=r.center))
