"""Stable Qt data roles shared by independent view components."""

from PyQt6.QtCore import Qt


PATH_ROLE = int(Qt.ItemDataRole.UserRole)
TYPE_ROLE = PATH_ROLE + 1
ROOT_ROLE = TYPE_ROLE + 1
MOVEMENT_ROLE = ROOT_ROLE + 1
ACTIVITY_ROLE = MOVEMENT_ROLE + 1
PENDING_DUE_ROLE = ACTIVITY_ROLE + 1
MODIFIED_ROLE = PENDING_DUE_ROLE + 1
SIZE_ROLE = MODIFIED_ROLE + 1
