"""Stable Qt data roles shared by independent view components."""

from PyQt6.QtCore import Qt


PATH_ROLE = int(Qt.ItemDataRole.UserRole)
TYPE_ROLE = PATH_ROLE + 1
ROOT_ROLE = TYPE_ROLE + 1
MOVEMENT_ROLE = ROOT_ROLE + 1
