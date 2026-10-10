"""User settings shared between the menu and the game."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Settings:
    show_aim_guide: bool = True  # dashed line, ghost ball and direction hints
    show_fps: bool = False
    menu_animation: bool = True  # balls rolling in the menu background
