"""Hand-written 2D billiard physics based on velocity Verlet integration.

No physics library is used. Every ball stores its position ``pos`` and its
velocity ``vel`` explicitly. One integration sub-step of length ``h`` is the
classic velocity Verlet scheme:

    a_n     = a(v_n)
    x_{n+1} = x_n + v_n * h + 0.5 * a_n * h**2
    a_{n+1} = a(v_n + a_n * h)              (predicted velocity)
    v_{n+1} = v_n + 0.5 * (a_n + a_{n+1}) * h

The acceleration only comes from table friction and acts against the
direction of motion:

    a(v) = -(mu + k * |v|) * v / |v|

``mu`` is a constant rolling-friction deceleration and ``k`` a
speed-proportional damping coefficient. When friction would stop the ball
within the sub-step, the ball is moved by the remaining stopping distance and
put to rest, so friction never reverses the motion.

Collisions are handled after each integration sub-step and act directly on
the velocity:

* Ball-ball: the overlap is removed (positional correction), then an impulse
  along the contact normal is applied with a coefficient of restitution.
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
    """A ball with explicit position and velocity (px and px/s)."""

    def __init__(self, number: int, pos: Iterable[float], radius: float, mass: float = 1.0) -> None:
        self.number = number
        self.pos = Vec2(*pos)
        self.vel = Vec2()
        self.radius = radius
        self.mass = mass
        self.pocketed = False
        self.pocket_index: Optional[int] = None

    @property
    def is_cue(self) -> bool:
        return self.number == 0

    @property
    def speed(self) -> float:
        return self.vel.length()

    def place(self, pos: Iterable[float]) -> None:
        """Teleport the ball and put it at rest."""
        self.pos = Vec2(*pos)
        self.vel = Vec2()
        self.pocketed = False
        self.pocket_index = None


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
            self._collide_balls(events)
            self._collide_cushions(events)
            self._detect_pockets(events)
        return events

    def friction_acceleration(self, v: Vec2) -> Vec2:
        """Table friction: constant rolling resistance plus linear damping."""
        speed = v.length()
        if speed == 0.0:
            return Vec2()
        p = self.params
        return v * (-(p.rolling_friction + p.linear_damping * speed) / speed)

    def _integrate(self, h: float) -> None:
        p = self.params
        for b in self.balls:
            if b.pocketed:
                continue
            v = b.vel
            speed = v.length()
            if speed == 0.0 or speed < p.stop_speed:
                b.vel = Vec2()
                continue
            decel = p.rolling_friction + p.linear_damping * speed
            if decel * h >= speed:
                # Friction stops the ball inside this sub-step: move it by the
                # stopping distance (exact for constant deceleration) and rest.
                b.pos = b.pos + v * (0.5 * speed / decel)
                b.vel = Vec2()
                continue
            a0 = self.friction_acceleration(v)
            b.pos = b.pos + v * h + a0 * (0.5 * h * h)
            a1 = self.friction_acceleration(v + a0 * h)
            new_vel = v + (a0 + a1) * (0.5 * h)
            if new_vel.dot(v) <= 0.0 or new_vel.length() < p.stop_speed:
                new_vel = Vec2()
            b.vel = new_vel

    def _collide_balls(self, events: StepEvents) -> None:
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
                a.pos = a.pos - normal * (overlap * inv_a / inv_sum)
                b.pos = b.pos + normal * (overlap * inv_b / inv_sum)
                # impulse along the normal, applied directly to the velocities
                approach = (a.vel - b.vel).dot(normal)
                if approach > 0.0:
                    j_imp = (1.0 + e) * approach / inv_sum
                    a.vel = a.vel - normal * (j_imp * inv_a)
                    b.vel = b.vel + normal * (j_imp * inv_b)
                    events.ball_hits.append((a.number, b.number))

    def _collide_cushions(self, events: StepEvents) -> None:
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
                b.pos = b.pos + normal * (b.radius - dist)
                vn = b.vel.dot(normal)
                if vn < 0.0:
                    b.vel = b.vel - normal * ((1.0 + e) * vn)
                    events.cushion_hits.append(b.number)

    def _detect_pockets(self, events: StepEvents) -> None:
        for b in self.balls:
            if b.pocketed:
                continue
            idx = self._pocket_for(b)
            if idx is not None:
                b.pocketed = True
                b.pocket_index = idx
                b.vel = Vec2()
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
        limit = self.params.stop_speed
        return all(b.speed < limit for b in self.balls if not b.pocketed)

    def kinetic_energy(self) -> float:
        return sum(0.5 * b.mass * b.vel.length_sq() for b in self.balls if not b.pocketed)

    def momentum(self) -> Vec2:
        total = Vec2()
        for b in self.balls:
            if not b.pocketed:
                total = total + b.vel * b.mass
        return total
