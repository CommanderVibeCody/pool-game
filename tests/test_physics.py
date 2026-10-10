import math

import pytest

from pool.physics import Ball, PhysicsParams, PhysicsWorld, Pocket, Segment, Vec2
from pool.table import Table

R = 11.0


def frictionless(**kw):
    p = PhysicsParams(rolling_friction=0.0, linear_damping=0.0, stop_speed=0.0)
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def make_world(balls, params, **kw):
    return PhysicsWorld(balls, params=params, **kw)


def test_free_motion_is_exact_without_friction():
    b = Ball(0, (0, 0), R)
    w = make_world([b], frictionless())
    b.vel = Vec2(300, -120)
    for _ in range(120):  # one second
        w.step()
    assert b.pos.x == pytest.approx(300, abs=1e-6)
    assert b.pos.y == pytest.approx(-120, abs=1e-6)


@pytest.mark.parametrize("v0, mu", [(600.0, 200.0), (1500.0, 110.0), (250.0, 333.0)])
def test_velocity_verlet_matches_constant_deceleration(v0, mu):
    """With pure constant deceleration, x(t) = v0*t - mu*t^2/2 and v(t) = v0 - mu*t
    until the ball stops after v0/mu seconds at distance v0^2 / (2*mu)."""
    b = Ball(0, (0, 0), R)
    w = make_world([b], frictionless(rolling_friction=mu))
    b.vel = Vec2(v0, 0)
    t_stop = v0 / mu
    t = 0.0
    while t + w.fixed_dt < t_stop:
        w.step()
        t += w.fixed_dt
        assert b.pos.x == pytest.approx(v0 * t - 0.5 * mu * t * t, rel=1e-9, abs=1e-6)
        assert b.vel.x == pytest.approx(v0 - mu * t, rel=1e-9, abs=1e-6)
        assert b.pos.y == 0.0
    for _ in range(3):
        w.step()
    assert b.vel.length() == 0.0
    assert b.pos.x == pytest.approx(v0 * v0 / (2 * mu), rel=1e-9)


def test_linear_damping_matches_exponential_decay():
    """With damping only, v(t) = v0*exp(-k t) and x(t) = v0/k * (1 - exp(-k t))."""
    k, v0 = 0.8, 900.0
    b = Ball(0, (0, 0), R)
    w = make_world([b], frictionless(linear_damping=k))
    b.vel = Vec2(v0, 0)
    for _ in range(240):
        w.step()
    t = 2.0
    assert b.vel.x == pytest.approx(v0 * math.exp(-k * t), rel=1e-6)
    assert b.pos.x == pytest.approx(v0 / k * (1 - math.exp(-k * t)), rel=1e-6)


def test_head_on_elastic_collision_swaps_velocities():
    a = Ball(0, (100, 100), R)
    b = Ball(1, (100 + 2 * R + 5, 100), R)
    w = make_world([a, b], frictionless(ball_restitution=1.0))
    a.vel = Vec2(400, 0)
    for _ in range(60):
        w.step()
    assert a.vel.x == pytest.approx(0.0, abs=1e-6)
    assert b.vel.x == pytest.approx(400.0, rel=1e-6)


@pytest.mark.parametrize("restitution", [1.0, 0.9, 0.5])
def test_momentum_conserved_in_oblique_collision(restitution):
    a = Ball(0, (100, 100), R)
    b = Ball(1, (160, 108), R)
    w = make_world([a, b], frictionless(ball_restitution=restitution))
    a.vel = Vec2(500, 30)
    b.vel = Vec2(-50, 0)
    p0 = w.momentum()
    e0 = w.kinetic_energy()
    hits = 0
    for _ in range(60):
        hits += len(w.step().ball_hits)
    assert hits >= 1
    p1 = w.momentum()
    assert p1.x == pytest.approx(p0.x, rel=1e-9, abs=1e-6)
    assert p1.y == pytest.approx(p0.y, rel=1e-9, abs=1e-6)
    e1 = w.kinetic_energy()
    assert e1 <= e0 + 1e-6
    if restitution == 1.0:
        assert e1 == pytest.approx(e0, rel=1e-9)


def test_overlap_is_resolved():
    a = Ball(0, (100, 100), R)
    b = Ball(1, (105, 100), R)
    w = make_world([a, b], frictionless())
    w.step()
    assert (b.pos - a.pos).length() >= 2 * R - 1e-6


def test_cushion_bounce_reflects_with_restitution():
    e = 0.8
    wall = Segment(Vec2(0, 0), Vec2(0, 500))
    b = Ball(0, (100, 250), R)
    w = make_world([b], frictionless(cushion_restitution=e), segments=[wall])
    b.vel = Vec2(-300, 0)
    events = []
    for _ in range(120):
        events += w.step().cushion_hits
    v = b.vel
    assert events == [0]
    assert v.x == pytest.approx(300 * e, rel=1e-6)
    assert v.y == pytest.approx(0.0, abs=1e-9)
    assert b.pos.x >= R - 1e-6


def test_friction_stops_ball_and_speed_decreases_monotonically():
    b = Ball(0, (0, 0), R)
    w = make_world([b], PhysicsParams())
    b.vel = Vec2(800, 0)
    last = 800.0
    for step in range(20 * 120):
        w.step()
        speed = b.vel.length()
        assert speed <= last + 1e-9
        assert b.vel.x >= 0.0  # friction never reverses motion
        last = speed
        if w.all_stopped():
            break
    else:
        pytest.fail("ball never stopped")
    assert 100 < b.pos.x < 5000


def test_ball_rolling_into_pocket_is_pocketed():
    pocket = Pocket(Vec2(300, 100), 20)
    b = Ball(3, (100, 100), R)
    w = make_world([b], frictionless(), pockets=[pocket])
    b.vel = Vec2(400, 0)
    pocketed = []
    for _ in range(120):
        pocketed += w.step().pocketed
    assert b.pocketed
    assert pocketed == [(3, 0)]


def test_break_shot_on_real_table_settles_and_keeps_balls_inside():
    t = Table()
    balls = t.create_balls()
    w = PhysicsWorld(balls, t.segments, t.pockets, t.bounds, PhysicsParams())
    balls[0].vel = Vec2(1500, 3)
    for _ in range(120 * 30):
        w.step()
        if w.all_stopped():
            break
    assert w.all_stopped()
    for b in balls:
        if not b.pocketed:
            assert t.left - 1 <= b.pos.x <= t.right + 1
            assert t.top - 1 <= b.pos.y <= t.bottom + 1
    active = [b for b in balls if not b.pocketed]
    for i, a in enumerate(active):
        for c in active[i + 1:]:
            assert (a.pos - c.pos).length() >= 2 * R - 0.5
