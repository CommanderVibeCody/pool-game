"""Table geometry: playing area, cushions, pockets and the rack."""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

from .physics import Ball, Pocket, Segment, Vec2

BALL_RADIUS = 11.0
PLAY_WIDTH = 880.0
PLAY_HEIGHT = 440.0
CUSHION_WIDTH = 14.0
RAIL_WIDTH = 34.0
HUD_HEIGHT = 84
BOTTOM_PANEL = 52
SIDE_MARGIN = 26

CORNER_GAP = 26.0  # length of each rail opening at a corner pocket
SIDE_GAP = 21.0  # half-width of the side pocket opening
CORNER_POCKET_RADIUS = 22.0
SIDE_POCKET_RADIUS = 20.0

WINDOW_WIDTH = int(PLAY_WIDTH + 2 * (CUSHION_WIDTH + RAIL_WIDTH + SIDE_MARGIN))
WINDOW_HEIGHT = int(HUD_HEIGHT + PLAY_HEIGHT + 2 * (CUSHION_WIDTH + RAIL_WIDTH) + BOTTOM_PANEL)

# Standard rack layout, row by row from the apex. 8 sits in the middle and
# the two back corners hold one solid and one stripe.
RACK_ORDER = [[1], [10, 2], [3, 8, 11], [12, 4, 13, 5], [6, 14, 7, 15, 9]]


class Table:
    def __init__(self) -> None:
        self.left = SIDE_MARGIN + RAIL_WIDTH + CUSHION_WIDTH
        self.top = HUD_HEIGHT + RAIL_WIDTH + CUSHION_WIDTH
        self.right = self.left + PLAY_WIDTH
        self.bottom = self.top + PLAY_HEIGHT
        self.width = PLAY_WIDTH
        self.height = PLAY_HEIGHT
        self.ball_radius = BALL_RADIUS
        cx = (self.left + self.right) / 2
        cy = (self.top + self.bottom) / 2
        self.center = Vec2(cx, cy)
        self.head_spot = Vec2(self.left + self.width * 0.25, cy)
        self.foot_spot = Vec2(self.left + self.width * 0.75, cy)
        self.head_string_x = self.head_spot.x

        l, t, r, b = self.left, self.top, self.right, self.bottom
        o = 4.0  # corner pockets sit slightly outside the corner
        self.pockets: List[Pocket] = [
            Pocket(Vec2(l - o, t - o), CORNER_POCKET_RADIUS),
            Pocket(Vec2(cx, t - 8.0), SIDE_POCKET_RADIUS),
            Pocket(Vec2(r + o, t - o), CORNER_POCKET_RADIUS),
            Pocket(Vec2(l - o, b + o), CORNER_POCKET_RADIUS),
            Pocket(Vec2(cx, b + 8.0), SIDE_POCKET_RADIUS),
            Pocket(Vec2(r + o, b + o), CORNER_POCKET_RADIUS),
        ]
        g, s = CORNER_GAP, SIDE_GAP
        self.segments: List[Segment] = [
            Segment(Vec2(l + g, t), Vec2(cx - s, t)),
            Segment(Vec2(cx + s, t), Vec2(r - g, t)),
            Segment(Vec2(l + g, b), Vec2(cx - s, b)),
            Segment(Vec2(cx + s, b), Vec2(r - g, b)),
            Segment(Vec2(l, t + g), Vec2(l, b - g)),
            Segment(Vec2(r, t + g), Vec2(r, b - g)),
        ]

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        return (self.left, self.top, self.right, self.bottom)

    def rack_positions(self) -> Dict[int, Vec2]:
        """Positions of the 15 object balls in a tight triangle."""
        r = self.ball_radius + 0.05
        dx = math.sqrt(3.0) * r
        positions: Dict[int, Vec2] = {}
        for row, numbers in enumerate(RACK_ORDER):
            x = self.foot_spot.x + row * dx
            for i, n in enumerate(numbers):
                y = self.foot_spot.y + (i - row / 2.0) * 2.0 * r
                positions[n] = Vec2(x, y)
        return positions

    def create_balls(self) -> List[Ball]:
        balls = [Ball(0, self.head_spot, self.ball_radius)]
        rack = self.rack_positions()
        for n in range(1, 16):
            balls.append(Ball(n, rack[n], self.ball_radius))
        return balls

    def clamp_to_play_area(self, p: Vec2) -> Vec2:
        r = self.ball_radius
        return Vec2(
            min(max(p.x, self.left + r), self.right - r),
            min(max(p.y, self.top + r), self.bottom - r),
        )

    def is_free_spot(self, p: Vec2, balls: List[Ball], ignore: int = -1) -> bool:
        r = self.ball_radius
        if not (self.left + r <= p.x <= self.right - r and self.top + r <= p.y <= self.bottom - r):
            return False
        for b in balls:
            if b.pocketed or b.number == ignore:
                continue
            if (b.pos - p).length() < b.radius + r + 0.5:
                return False
        return True

    def find_free_spot(self, preferred: Vec2, balls: List[Ball], ignore: int = -1, direction: Vec2 = Vec2(1, 0)) -> Vec2:
        """Search along a direction (then a spiral) for a free spot."""
        step = self.ball_radius * 0.5
        p = preferred.copy()
        for _ in range(200):
            if self.is_free_spot(p, balls, ignore):
                return p
            p = self.clamp_to_play_area(p + direction * step)
        for k in range(1, 400):
            q = self.clamp_to_play_area(preferred + Vec2.from_angle(k * 0.7, step * k * 0.3))
            if self.is_free_spot(q, balls, ignore):
                return q
        return preferred
