"""Hand-written 2D billiard physics based on position Verlet integration.

No physics library is used. Every ball stores its current position ``pos``
and its position from the previous sub-step ``prev``. The velocity is never
stored explicitly; it is implied by the difference of the two positions:

    v = (pos - prev) / h

One integration sub-step (position Verlet with velocity damping) is:

    x_next = x + (x - x_prev) * damping + a * h**2

where ``a`` is the rolling-friction deceleration (opposite to the direction of
motion) and ``damping = exp(-k * h)`` models speed-proportional losses.

Collisions are handled after each integration sub-step:

* Ball-ball: the overlap is removed (positional correction, ``pos`` and
  ``prev`` are shifted together so the implied velocity is untouched), then
  an impulse along the contact normal is applied with a coefficient of
  restitution. Changing a velocity in Verlet form means rewriting ``prev``.
* Ball-cushion: cushions are line segments. The closest point on the segment
  gives the contact normal; the normal velocity component is reflected and
  scaled by the cushion restitution.
* Pockets: a ball whose centre falls inside a pocket circle (or leaves the
  playing area through a pocket mouth) is removed from play.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple


class Vec2:
    """Minimal immutable-style 2D vector."""

    __slots__ = ("x", "y")

    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        self.x = float(x)
        self.y = float(y)

    def __add__(self, o: "Vec2") -> "Vec2":
        return Vec2(self.x + o.x, self.y + o.y)

    def __sub__(self, o: "Vec2") -> "Vec2":
        return Vec2(self.x - o.x, self.y - o.y)

    def __mul__(self, k: float) -> "Vec2":
        return Vec2(self.x * k, self.y * k)

    __rmul__ = __mul__

    def __truediv__(self, k: float) -> "Vec2":
        return Vec2(self.x / k, self.y / k)

    def __neg__(self) -> "Vec2":
        return Vec2(-self.x, -self.y)

    def __iter__(self):
        yield self.x
        yield self.y

    def __repr__(self) -> str:
        return f"Vec2({self.x:.3f}, {self.y:.3f})"

    def dot(self, o: "Vec2") -> float:
        return self.x * o.x + self.y * o.y

    def length_sq(self) -> float:
        return self.x * self.x + self.y * self.y

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> "Vec2":
        n = self.length()
        if n == 0.0:
            return Vec2()
        return Vec2(self.x / n, self.y / n)

    def perp(self) -> "Vec2":
        return Vec2(-self.y, self.x)

    def copy(self) -> "Vec2":
        return Vec2(self.x, self.y)

    @staticmethod
    def from_angle(angle: float, length: float = 1.0) -> "Vec2":
        return Vec2(math.cos(angle) * length, math.sin(angle) * length)


class Ball:
    """A ball in Verlet representation (current and previous position)."""

    def __init__(self, number: int, pos: Iterable[float], radius: float, mass: float = 1.0) -> None:
        self.number = number
        self.pos = Vec2(*pos)
        self.prev = self.pos.copy()
        self.radius = radius
        self.mass = mass
        self.pocketed = False
        self.pocket_index: Optional[int] = None

    @property
    def is_cue(self) -> bool:
        return self.number == 0

    def velocity(self, h: float) -> Vec2:
        return (self.pos - self.prev) / h

    def set_velocity(self, v: Vec2, h: float) -> None:
        self.prev = self.pos - v * h

    def place(self, pos: Iterable[float]) -> None:
        """Teleport the ball and put it at rest."""
        self.pos = Vec2(*pos)
        self.prev = self.pos.copy()
        self.pocketed = False
        self.pocket_index = None

    def shift(self, d: Vec2) -> None:
        """Move the ball without changing its implied velocity."""
        self.pos = self.pos + d
        self.prev = self.prev + d


@dataclass
class Segment:
    """A straight cushion segment from a to b."""

    a: Vec2
    b: Vec2


@dataclass
class Pocket:
    center: Vec2
    radius: float


@dataclass
class PhysicsParams:
    ball_restitution: float = 0.95
    cushion_restitution: float = 0.78
    rolling_friction: float = 110.0  # constant deceleration in px/s^2
    linear_damping: float = 0.30  # speed-proportional losses in 1/s
    stop_speed: float = 4.0  # below this speed (px/s) a ball is put to rest
    substeps: int = 4


@dataclass
class StepEvents:
    ball_hits: List[Tuple[int, int]] = field(default_factory=list)
    cushion_hits: List[int] = field(default_factory=list)
    pocketed: List[Tuple[int, int]] = field(default_factory=list)

    def extend(self, other: "StepEvents") -> None:
        self.ball_hits.extend(other.ball_hits)
        self.cushion_hits.extend(other.cushion_hits)
        self.pocketed.extend(other.pocketed)


def closest_point_on_segment(p: Vec2, a: Vec2, b: Vec2) -> Vec2:
    ab = b - a
    denom = ab.length_sq()
    if denom == 0.0:
        return a.copy()
    t = (p - a).dot(ab) / denom
    t = max(0.0, min(1.0, t))
    return a + ab * t


class PhysicsWorld:
    """Fixed time step simulation of a set of balls on a table."""

    def __init__(
        self,
        balls: Sequence[Ball],
        segments: Sequence[Segment] = (),
        pockets: Sequence[Pocket] = (),
        bounds: Optional[Tuple[float, float, float, float]] = None,
        params: Optional[PhysicsParams] = None,
        fixed_dt: float = 1.0 / 120.0,
    ) -> None:
        self.balls = list(balls)
        self.segments = list(segments)
        self.pockets = list(pockets)
        self.bounds = bounds  # (left, top, right, bottom) of the cushion lines
        self.params = params or PhysicsParams()
        self.fixed_dt = fixed_dt

    @property
    def h(self) -> float:
        """Length of one integration sub-step in seconds."""
        return self.fixed_dt / self.params.substeps

    def active_balls(self) -> List[Ball]:
        return [b for b in self.balls if not b.pocketed]

    # ------------------------------------------------------------------ step
    def step(self) -> StepEvents:
        """Advance the world by one fixed time step (several sub-steps)."""
        events = StepEvents()
        h = self.h
        for _ in range(self.params.substeps):
            self._integrate(h)
            self._collide_balls(h, events)
            self._collide_cushions(h, events)
            self._detect_pockets(events)
        return events

    def _integrate(self, h: float) -> None:
        p = self.params
        damping = math.exp(-p.linear_damping * h)
        friction_dv = p.rolling_friction * h  # speed lost per sub-step
        for b in self.balls:
            if b.pocketed:
                continue
            disp = b.pos - b.prev
            disp_len = disp.length()
            speed = disp_len / h
            if speed < p.stop_speed or speed * damping - friction_dv <= p.stop_speed:
                b.prev = b.pos.copy()  # come to rest, never reverse direction
                continue
            direction = disp / disp_len
            accel = direction * (-p.rolling_friction)
            new_pos = b.pos + disp * damping + accel * (h * h)
            b.prev = b.pos
            b.pos = new_pos

    def _collide_balls(self, h: float, events: StepEvents) -> None:
        e = self.params.ball_restitution
        active = self.active_balls()
        n = len(active)
        for i in range(n):
            a = active[i]
            for j in range(i + 1, n):
                b = active[j]
                d = b.pos - a.pos
                min_dist = a.radius + b.radius
                dist_sq = d.length_sq()
                if dist_sq >= min_dist * min_dist:
                    continue
                dist = math.sqrt(dist_sq)
                normal = d / dist if dist > 1e-9 else Vec2(1.0, 0.0)
                inv_a = 1.0 / a.mass
                inv_b = 1.0 / b.mass
                inv_sum = inv_a + inv_b
                # positional correction (keeps the implied velocities)
                overlap = min_dist - dist
                a.shift(normal * (-overlap * inv_a / inv_sum))
                b.shift(normal * (overlap * inv_b / inv_sum))
                # impulse along the normal
                va = a.velocity(h)
                vb = b.velocity(h)
                approach = (va - vb).dot(normal)
                if approach > 0.0:
                    j_imp = (1.0 + e) * approach / inv_sum
                    a.set_velocity(va - normal * (j_imp * inv_a), h)
                    b.set_velocity(vb + normal * (j_imp * inv_b), h)
                    events.ball_hits.append((a.number, b.number))

    def _collide_cushions(self, h: float, events: StepEvents) -> None:
        e = self.params.cushion_restitution
        for b in self.balls:
            if b.pocketed:
                continue
            for seg in self.segments:
                cp = closest_point_on_segment(b.pos, seg.a, seg.b)
                d = b.pos - cp
                dist_sq = d.length_sq()
                if dist_sq >= b.radius * b.radius:
                    continue
                dist = math.sqrt(dist_sq)
                if dist > 1e-9:
                    normal = d / dist
                else:
                    normal = (seg.b - seg.a).perp().normalized()
                b.shift(normal * (b.radius - dist))
                v = b.velocity(h)
                vn = v.dot(normal)
                if vn < 0.0:
                    b.set_velocity(v - normal * ((1.0 + e) * vn), h)
                    events.cushion_hits.append(b.number)

    def _detect_pockets(self, events: StepEvents) -> None:
        for b in self.balls:
            if b.pocketed:
                continue
            idx = self._pocket_for(b)
            if idx is not None:
                b.pocketed = True
                b.pocket_index = idx
                b.prev = b.pos.copy()
                events.pocketed.append((b.number, idx))

    def _pocket_for(self, b: Ball) -> Optional[int]:
        for i, p in enumerate(self.pockets):
            if (b.pos - p.center).length_sq() < p.radius * p.radius:
                return i
        if self.bounds is not None and self.pockets:
            left, top, right, bottom = self.bounds
            m = b.radius * 0.25
            x, y = b.pos.x, b.pos.y
            if x < left - m or x > right + m or y < top - m or y > bottom + m:
                # The only way past a cushion line is through a pocket mouth.
                return min(range(len(self.pockets)), key=lambda k: (b.pos - self.pockets[k].center).length_sq())
        return None

    # --------------------------------------------------------------- queries
    def all_stopped(self) -> bool:
        h = self.h
        limit = self.params.stop_speed
        return all(b.velocity(h).length() < limit for b in self.balls if not b.pocketed)

    def kinetic_energy(self) -> float:
        h = self.h
        return sum(0.5 * b.mass * b.velocity(h).length_sq() for b in self.balls if not b.pocketed)

    def momentum(self) -> Vec2:
        h = self.h
        total = Vec2()
        for b in self.balls:
            if not b.pocketed:
                total = total + b.velocity(h) * b.mass
        return total
