"""Simplified 8-ball rules for two players."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set

SOLIDS = frozenset(range(1, 8))
STRIPES = frozenset(range(9, 16))
EIGHT = 8


def group_of(number: int) -> Optional[str]:
    if number in SOLIDS:
        return "solids"
    if number in STRIPES:
        return "stripes"
    return None


def balls_of(group: str) -> frozenset:
    return SOLIDS if group == "solids" else STRIPES


def other_group(group: str) -> str:
    return "stripes" if group == "solids" else "solids"


@dataclass
class ShotResult:
    """What happened during a single shot (collected by the game)."""

    first_hit: Optional[int]
    pocketed: List[int]
    on_table: Set[int]  # object balls still on the table after the shot
    cue_scratched: bool = False


@dataclass
class ShotOutcome:
    foul: bool = False
    turn_kept: bool = False
    ball_in_hand: bool = False
    respot_eight: bool = False
    game_over: bool = False
    message: str = ""


@dataclass
class Rules:
    current: int = 0
    groups: List[Optional[str]] = field(default_factory=lambda: [None, None])
    winner: Optional[int] = None
    break_shot: bool = True
    ball_in_hand: bool = False

    @property
    def opponent(self) -> int:
        return 1 - self.current

    @staticmethod
    def player_name(index: int) -> str:
        return f"Player {index + 1}"

    def remaining_for(self, player: int, on_table: Iterable[int]) -> Set[int]:
        group = self.groups[player]
        if group is None:
            return set()
        return set(on_table) & balls_of(group)

    def apply_shot(self, shot: ShotResult) -> ShotOutcome:
        out = ShotOutcome()
        p, opp = self.current, self.opponent
        name, opp_name = self.player_name(p), self.player_name(opp)
        was_break = self.break_shot
        self.break_shot = False
        group = self.groups[p]
        object_pocketed = [n for n in shot.pocketed if n != 0]

        # group balls this player still had to pocket at the start of the shot
        before = set(shot.on_table) | set(object_pocketed)
        remaining_before = (before & balls_of(group)) if group else None

        reason = ""
        if shot.cue_scratched:
            reason = "Scratch - the cue ball was pocketed"
        elif shot.first_hit is None:
            reason = "No ball was hit"
        elif group is not None:
            legal = {EIGHT} if not remaining_before else remaining_before
            if shot.first_hit not in legal:
                reason = f"Wrong ball hit first ({shot.first_hit})"
        elif shot.first_hit == EIGHT and not was_break:
            reason = "The 8-ball may not be hit first on an open table"
        out.foul = bool(reason)

        # --- the 8-ball decides the game (except on the break)
        if EIGHT in object_pocketed:
            if was_break:
                out.respot_eight = True
                object_pocketed = [n for n in object_pocketed if n != EIGHT]
            else:
                out.game_over = True
                if group is not None and not remaining_before and not out.foul:
                    self.winner = p
                    out.message = f"{name} pockets the 8-ball and wins!"
                else:
                    self.winner = opp
                    why = reason if out.foul else "8-ball pocketed too early"
                    out.message = f"{why}. {opp_name} wins!"
                return out

        # --- group assignment after the break on an open table
        assigned = ""
        if not out.foul and group is None and not was_break and object_pocketed:
            first = group_of(object_pocketed[0])
            if first is not None:
                self.groups[p] = first
                self.groups[opp] = other_group(first)
                group = first
                assigned = f"{name} plays {first}. "

        # --- does the player keep the turn?
        if group is not None:
            scored = any(n in balls_of(group) for n in object_pocketed)
        else:
            scored = bool(object_pocketed)
        prefix = "8-ball on the break - re-spotted. " if out.respot_eight else ""

        if out.foul:
            self.current = opp
            self.ball_in_hand = True
            out.ball_in_hand = True
            out.message = f"{prefix}Foul: {reason}. {opp_name} has ball in hand."
        elif scored:
            out.turn_kept = True
            out.message = f"{prefix}{assigned}{name} continues."
        else:
            self.current = opp
            out.message = f"{prefix}{assigned}{opp_name}'s turn."
        if not out.foul:
            self.ball_in_hand = False
        return out
