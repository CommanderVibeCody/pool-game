from pool.rules import Rules, ShotResult

ALL = set(range(1, 16))


def test_scratch_gives_ball_in_hand_to_opponent():
    r = Rules(break_shot=False)
    out = r.apply_shot(ShotResult(first_hit=3, pocketed=[0], on_table=ALL, cue_scratched=True))
    assert out.foul and out.ball_in_hand
    assert r.current == 1


def test_no_ball_hit_is_foul():
    r = Rules(break_shot=False)
    out = r.apply_shot(ShotResult(first_hit=None, pocketed=[], on_table=ALL))
    assert out.foul and r.current == 1


def test_groups_assigned_after_break_and_turn_kept():
    r = Rules()
    out = r.apply_shot(ShotResult(first_hit=1, pocketed=[], on_table=ALL))  # break
    assert r.current == 1 and not out.foul
    out = r.apply_shot(ShotResult(first_hit=11, pocketed=[11], on_table=ALL - {11}))
    assert r.groups == ["solids", "stripes"]
    assert out.turn_kept and r.current == 1


def test_break_pocket_keeps_table_open_and_turn():
    r = Rules()
    out = r.apply_shot(ShotResult(first_hit=1, pocketed=[2], on_table=ALL - {2}))
    assert out.turn_kept and r.groups == [None, None]


def test_wrong_group_first_is_foul():
    r = Rules(break_shot=False, groups=["solids", "stripes"])
    out = r.apply_shot(ShotResult(first_hit=12, pocketed=[], on_table=ALL))
    assert out.foul and r.current == 1


def test_eight_ball_early_loses():
    r = Rules(break_shot=False, groups=["solids", "stripes"])
    out = r.apply_shot(ShotResult(first_hit=2, pocketed=[8], on_table=ALL - {8}))
    assert out.game_over and r.winner == 1


def test_eight_ball_after_clearing_group_wins():
    r = Rules(break_shot=False, groups=["solids", "stripes"])
    on_table = set(range(9, 16))
    out = r.apply_shot(ShotResult(first_hit=8, pocketed=[8], on_table=on_table))
    assert out.game_over and r.winner == 0


def test_eight_ball_with_scratch_loses():
    r = Rules(break_shot=False, groups=["solids", "stripes"])
    out = r.apply_shot(ShotResult(first_hit=8, pocketed=[8, 0], on_table=set(range(9, 16)), cue_scratched=True))
    assert out.game_over and r.winner == 1


def test_eight_on_break_is_respotted():
    r = Rules()
    out = r.apply_shot(ShotResult(first_hit=1, pocketed=[8], on_table=ALL - {8}))
    assert out.respot_eight and not out.game_over
