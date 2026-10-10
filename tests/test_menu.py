"""Headless tests for the menu, scene transitions and the in-game pause menu."""
import pygame
import pytest

from pool.app import FADE_TIME, App
from pool.game import Game
from pool.settings import Settings
from pool.table import WINDOW_HEIGHT, WINDOW_WIDTH
from pool.ui import MenuList


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    yield screen
    pygame.quit()


def key(app_or_scene, k):
    return app_or_scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""))


def settle(app, seconds=None):
    """Advance past a complete fade-out + fade-in."""
    seconds = seconds if seconds is not None else 2 * FADE_TIME + 0.1
    for _ in range(int(seconds * 60) + 1):
        app.update(1 / 60)


@pytest.fixture
def app(display):
    a = App(seed=1)
    settle(a)
    return a


# ------------------------------------------------------------------ MenuList
def test_menu_list_keyboard_navigation_wraps_and_confirms():
    m = MenuList([("a", "A"), ("b", "B"), ("c", "C")], center=(500, 300))
    assert m.selected_key == "a"
    key(m, pygame.K_UP)
    assert m.selected_key == "c"  # wraps around
    key(m, pygame.K_DOWN)
    key(m, pygame.K_DOWN)
    assert m.selected_key == "b"
    assert key(m, pygame.K_RETURN) == "b"


def test_menu_list_mouse_hover_and_click():
    m = MenuList([("a", "A"), ("b", "B")], center=(500, 300))
    rect_b = m.rects()[1]
    m.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=rect_b.center, rel=(0, 0), buttons=(0, 0, 0)))
    assert m.selected_key == "b"
    outside = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(5, 5), button=1)
    assert m.handle_event(outside) is None
    click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=m.rects()[0].center, button=1)
    assert m.handle_event(click) == "a"


def test_menu_list_hover_animation_moves_to_selected():
    m = MenuList([("a", "A"), ("b", "B")], center=(500, 300))
    for _ in range(30):
        m.update(1 / 60)
    assert m.anim[0] > 0.95 and m.anim[1] < 0.05
    key(m, pygame.K_DOWN)
    m.update(1 / 60)
    assert 0.0 < m.anim[1] < 1.0  # animates instead of jumping


# ------------------------------------------------------------------- the app
def test_app_starts_in_menu_with_fade_in(display):
    a = App(seed=2)
    assert a.scene_name == "menu" and a.fade == 1.0
    settle(a)
    assert a.fade == 0.0
    a.draw(display)


def test_play_goes_to_game_after_fade(app, display):
    key(app, pygame.K_RETURN)  # "Play" is selected by default
    assert app.transitioning and app.scene_name == "menu"
    app.update(FADE_TIME / 2)
    app.draw(display)
    assert app.scene_name == "menu"  # still fading out
    settle(app)
    assert app.scene_name == "game" and isinstance(app.game, Game)
    app.draw(display)


def test_input_is_ignored_while_fading_out(app):
    key(app, pygame.K_RETURN)
    key(app, pygame.K_ESCAPE)  # must not quit during the transition
    assert app.running
    settle(app)
    assert app.scene_name == "game"


def test_howto_and_back(app, display):
    key(app, pygame.K_DOWN)
    key(app, pygame.K_RETURN)
    settle(app)
    assert app.scene_name == "howto"
    app.draw(display)
    key(app, pygame.K_ESCAPE)
    settle(app)
    assert app.scene_name == "menu" and app.running


def test_settings_toggle_aim_guide_reaches_game(app, display):
    key(app, pygame.K_DOWN)
    key(app, pygame.K_DOWN)
    key(app, pygame.K_RETURN)
    settle(app)
    assert app.scene_name == "settings"
    assert app.settings.show_aim_guide is True
    key(app, pygame.K_RETURN)  # first item: aim guide
    assert app.settings.show_aim_guide is False
    key(app, pygame.K_RIGHT)
    assert app.settings.show_aim_guide is True
    key(app, pygame.K_LEFT)
    key(app, pygame.K_DOWN)
    key(app, pygame.K_RETURN)  # show FPS
    assert app.settings.show_fps is True
    app.draw(display)
    key(app, pygame.K_ESCAPE)
    settle(app)
    assert app.scene_name == "menu"
    key(app, pygame.K_RETURN)
    settle(app)
    assert app.game.settings.show_aim_guide is False
    app.draw(display)


def test_menu_animation_setting_freezes_background(app):
    app.settings.menu_animation = False
    before = [b.pos.copy() for b in app.background.balls]
    settle(app, 1.0)
    after = [b.pos for b in app.background.balls]
    assert all(p.x == q.x and p.y == q.y for p, q in zip(before, after))


def test_escape_in_menu_quits(app):
    key(app, pygame.K_ESCAPE)
    assert app.running is False


def test_quit_item_quits(app):
    key(app, pygame.K_UP)  # wrap to "Quit"
    key(app, pygame.K_RETURN)
    assert app.running is False


def test_window_close_quits(app):
    app.handle_event(pygame.event.Event(pygame.QUIT))
    assert app.running is False


# --------------------------------------------------------------- pause menu
def enter_game(app):
    key(app, pygame.K_RETURN)
    settle(app)
    assert app.scene_name == "game"
    return app.game


def test_escape_in_game_pauses_and_resumes(app, display):
    game = enter_game(app)
    key(app, pygame.K_ESCAPE)
    assert game.paused and app.running and app.scene_name == "game"
    app.draw(display)
    key(app, pygame.K_ESCAPE)
    assert not game.paused
    key(app, pygame.K_ESCAPE)
    key(app, pygame.K_RETURN)  # "Resume"
    assert not game.paused


def test_pause_freezes_physics(app):
    game = enter_game(app)
    game.shoot(0.0, 1.0)
    key(app, pygame.K_ESCAPE)
    pos = game.cue.pos.copy()
    settle(app, 0.5)
    assert game.cue.pos.x == pos.x
    key(app, pygame.K_ESCAPE)
    settle(app, 0.2)
    assert game.cue.pos.x != pos.x


def test_pause_main_menu_returns_to_menu(app):
    enter_game(app)
    key(app, pygame.K_ESCAPE)
    key(app, pygame.K_DOWN)
    key(app, pygame.K_DOWN)
    key(app, pygame.K_RETURN)  # "Main menu"
    settle(app)
    assert app.scene_name == "menu" and app.game is None and app.running


def test_pause_restart_resets_game(app):
    game = enter_game(app)
    game.shoot(0.0, 1.0)
    settle(app, 3.0)
    key(app, pygame.K_ESCAPE)
    key(app, pygame.K_DOWN)
    key(app, pygame.K_RETURN)  # "Restart game"
    assert not game.paused
    assert game.cue.pos.x == game.table.head_spot.x
    assert game.rules.break_shot


def test_aim_guide_respected_when_drawing(display):
    called = []
    game = Game(Settings(show_aim_guide=False))
    game.draw(display)
    game.renderer.draw_aim = lambda *a: called.append(a)
    game.draw(display)
    assert called == []
    game.settings.show_aim_guide = True
    game.draw(display)
    assert len(called) == 1


def test_attract_mode_keeps_playing(display):
    a = App(seed=3)
    bg = a.background
    assert bg.racks == 1 and bg.shots == 0
    settle(a, 25.0)
    a.draw(display)
    assert bg.shots + bg.racks > 2  # it keeps shooting / re-racking by itself
    for b in bg.balls:
        if not b.pocketed:
            assert bg.table.left - 1 <= b.pos.x <= bg.table.right + 1
