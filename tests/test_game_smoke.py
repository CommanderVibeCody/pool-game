"""Headless smoke test: play a break and a few shots through the full game."""
import math

import pygame

from pool.game import AIMING, GAME_OVER, MOVING, PLACING, Game
from pool.table import WINDOW_HEIGHT, WINDOW_WIDTH


def run_until_stopped(game, screen, max_frames=60 * 40):
    for _ in range(max_frames):
        game.update(1 / 60)
        game.draw(screen)
        if game.state != MOVING:
            return
    raise AssertionError("balls never came to rest")


def test_headless_break_and_shots():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    game = Game()
    game.draw(screen)
    game.shoot(0.004, 1.0)  # full-power break
    run_until_stopped(game, screen)
    assert game.state in (AIMING, PLACING, GAME_OVER)
    for k in range(6):
        if game.state == GAME_OVER:
            break
        if game.state == PLACING:
            assert game.try_place_cue(game.table.find_free_spot(game.table.head_spot, game.balls, ignore=0))
        targets = [b for b in game.balls if not b.pocketed and b.number != 0]
        tgt = targets[k % len(targets)]
        d = tgt.pos - game.cue.pos
        game.aim_angle = math.atan2(d.y, d.x)
        game.aim_guide()
        game.draw(screen)
        game.shoot(game.aim_angle, 0.6)
        run_until_stopped(game, screen)
    pygame.quit()
