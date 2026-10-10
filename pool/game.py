"""Game state machine: input handling, shot bookkeeping and the main loop."""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import pygame

from .physics import Ball, PhysicsParams, PhysicsWorld, Vec2
from .render import Renderer
from .rules import EIGHT, Rules, ShotResult
from .table import WINDOW_HEIGHT, WINDOW_WIDTH, Table

FIXED_DT = 1.0 / 120.0
MAX_SHOT_SPEED = 1500.0  # px/s at full power
MAX_PULL = 180.0  # how far the mouse has to be pulled back for full power

AIMING = "aiming"
MOVING = "moving"
PLACING = "placing"
GAME_OVER = "game_over"


class Game:
    def __init__(self) -> None:
        self.table = Table()
        self.renderer: Optional[Renderer] = None
        self.reset()

    # ----------------------------------------------------------------- setup
    def reset(self) -> None:
        self.balls: List[Ball] = self.table.create_balls()
        self.world = PhysicsWorld(
            self.balls,
            self.table.segments,
            self.table.pockets,
            self.table.bounds,
            PhysicsParams(),
            FIXED_DT,
        )
        self.rules = Rules()
        self.state = AIMING
        self.aim_angle = 0.0
        self.charging = False
        self.charge_start = Vec2()
        self.power = 0.0
        self.mouse = Vec2(*self.table.foot_spot)
        self.place_pos = self.table.head_spot.copy()
        self.accumulator = 0.0
        self.shot_first_hit: Optional[int] = None
        self.shot_pocketed: List[int] = []
        self.message = "Player 1 breaks!"
        self.frames_moving = 0

    @property
    def cue(self) -> Ball:
        return self.balls[0]

    def object_balls_on_table(self) -> set:
        return {b.number for b in self.balls if b.number != 0 and not b.pocketed}

    # ---------------------------------------------------------------- shots
    def shoot(self, angle: float, power: float) -> None:
        power = max(0.0, min(1.0, power))
        self.cue.vel = Vec2.from_angle(angle, MAX_SHOT_SPEED * power)
        self.state = MOVING
        self.shot_first_hit = None
        self.shot_pocketed = []
        self.charging = False
        self.power = 0.0
        self.frames_moving = 0

    def update(self, dt: float) -> None:
        if self.state != MOVING:
            return
        self.accumulator += min(dt, 0.1)
        while self.accumulator >= FIXED_DT:
            events = self.world.step()
            self.accumulator -= FIXED_DT
            self.frames_moving += 1
            for a, b in events.ball_hits:
                if self.shot_first_hit is None and 0 in (a, b):
                    self.shot_first_hit = b if a == 0 else a
            for number, _pocket in events.pocketed:
                self.shot_pocketed.append(number)
            if self.world.all_stopped():
                self.accumulator = 0.0
                self.end_shot()
                return

    def end_shot(self) -> None:
        shot = ShotResult(
            first_hit=self.shot_first_hit,
            pocketed=list(self.shot_pocketed),
            on_table=self.object_balls_on_table(),
            cue_scratched=0 in self.shot_pocketed,
        )
        outcome = self.rules.apply_shot(shot)
        self.message = outcome.message
        if outcome.respot_eight:
            eight = self.balls[EIGHT]
            spot = self.table.find_free_spot(self.table.foot_spot, self.balls, ignore=EIGHT)
            eight.place(spot)
        if outcome.game_over:
            self.state = GAME_OVER
            return
        if outcome.ball_in_hand:
            self.cue.pocketed = True  # lifted from the table until placed
            self.place_pos = self.table.find_free_spot(self.table.head_spot, self.balls, ignore=0)
            self.state = PLACING
        else:
            self.state = AIMING

    def try_place_cue(self, pos: Vec2) -> bool:
        pos = self.table.clamp_to_play_area(pos)
        if not self.table.is_free_spot(pos, self.balls, ignore=0):
            return False
        self.cue.place(pos)
        self.state = AIMING
        self.message = f"{Rules.player_name(self.rules.current)} to shoot."
        return True

    # ---------------------------------------------------------------- input
    def current_pull(self) -> float:
        d = Vec2.from_angle(self.aim_angle)
        return max(0.0, min(MAX_PULL, -(self.mouse - self.charge_start).dot(d)))

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Process one event. Returns False when the game should quit."""
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return False
            if event.key == pygame.K_r:
                self.reset()
            return True
        if event.type == pygame.MOUSEMOTION:
            self.mouse = Vec2(*event.pos)
            if self.state == AIMING and not self.charging:
                d = self.mouse - self.cue.pos
                if d.length_sq() > 1.0:
                    self.aim_angle = math.atan2(d.y, d.x)
            elif self.state == AIMING and self.charging:
                self.power = self.current_pull() / MAX_PULL
            elif self.state == PLACING:
                self.place_pos = self.table.clamp_to_play_area(self.mouse)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self.mouse = Vec2(*event.pos)
            if event.button == 1:
                if self.state == AIMING:
                    self.charging = True
                    self.charge_start = self.mouse
                    self.power = 0.0
                elif self.state == PLACING:
                    if not self.try_place_cue(self.mouse):
                        self.message = "The cue ball can't be placed there."
            elif event.button == 3 and self.charging:
                self.charging = False
                self.power = 0.0
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.state == AIMING and self.charging:
                self.charging = False
                if self.power > 0.02:
                    self.shoot(self.aim_angle, self.power)
                self.power = 0.0
        return True

    # ------------------------------------------------------------ aim guide
    def aim_guide(self) -> Tuple[Vec2, Optional[Vec2], Optional[Vec2], Optional[Vec2]]:
        """Ray-cast the cue ball path to the first ball or cushion.

        Returns (end point, ghost ball position, object ball direction,
        cue ball deflection direction)."""
        c = self.cue.pos
        d = Vec2.from_angle(self.aim_angle)
        r = self.cue.radius
        best_t = math.inf
        target: Optional[Ball] = None
        for b in self.balls:
            if b.pocketed or b.is_cue:
                continue
            m = c - b.pos
            bq = m.dot(d)
            cq = m.length_sq() - (r + b.radius) ** 2
            disc = bq * bq - cq
            if disc < 0:
                continue
            t = -bq - math.sqrt(disc)
            if 0 < t < best_t:
                best_t, target = t, b
        t_wall = math.inf
        t = self.table
        if d.x > 1e-9:
            t_wall = min(t_wall, (t.right - r - c.x) / d.x)
        elif d.x < -1e-9:
            t_wall = min(t_wall, (t.left + r - c.x) / d.x)
        if d.y > 1e-9:
            t_wall = min(t_wall, (t.bottom - r - c.y) / d.y)
        elif d.y < -1e-9:
            t_wall = min(t_wall, (t.top + r - c.y) / d.y)
        t_wall = max(0.0, t_wall)
        if target is not None and best_t < t_wall:
            ghost = c + d * best_t
            tdir = (target.pos - ghost).normalized()
            cdir = d - tdir * d.dot(tdir)
            cdir = cdir.normalized() if cdir.length() > 0.05 else None
            return ghost, ghost, tdir, cdir
        end = c + d * t_wall
        return end, end, None, None

    # ------------------------------------------------------------ rendering
    def state_hint(self) -> str:
        if self.state == PLACING:
            return f"Ball in hand: {Rules.player_name(self.rules.current)}, click to place the cue ball"
        if self.state == MOVING:
            return "Balls rolling..."
        if self.state == GAME_OVER:
            return "Game over"
        return f"{Rules.player_name(self.rules.current)} to shoot"

    def draw(self, screen: pygame.Surface) -> None:
        if self.renderer is None:
            self.renderer = Renderer(self.table)
        r = self.renderer
        r.draw_table(screen)
        r.draw_balls(screen, self.balls)
        if self.state == AIMING:
            r.draw_aim(screen, self.cue.pos, self.aim_guide())
            pull = self.current_pull() if self.charging else 0.0
            r.draw_cue_stick(screen, self.cue.pos, self.aim_angle, pull)
        elif self.state == PLACING:
            valid = self.table.is_free_spot(self.place_pos, self.balls, ignore=0)
            r.draw_ghost_cue(screen, self.place_pos, valid)
        r.draw_hud(screen, self.rules, self.balls, self.message, self.power, self.state_hint())
        if self.state == GAME_OVER and self.rules.winner is not None:
            r.draw_game_over(screen, f"{Rules.player_name(self.rules.winner)} wins!")


def run() -> None:
    pygame.init()
    pygame.display.set_caption("Pool - 8-Ball (velocity Verlet physics)")
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    clock = pygame.time.Clock()
    game = Game()
    running = True
    while running:
        dt = clock.tick(120) / 1000.0
        for event in pygame.event.get():
            if not game.handle_event(event):
                running = False
                break
        game.update(dt)
        game.draw(screen)
        pygame.display.flip()
    pygame.quit()
