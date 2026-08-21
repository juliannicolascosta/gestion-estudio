from __future__ import annotations

from functools import lru_cache

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer


_SHAPES = {
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "user-plus": '<path d="M15 20a6 6 0 0 0-12 0"/><circle cx="9" cy="8" r="4"/><path d="M19 8v6M16 11h6"/>',
    "location-plus": '<path d="M14.5 10.5A5.5 5.5 0 1 0 7 15.6L10 20l2.2-3.2"/><circle cx="9" cy="10.5" r="1.5"/><path d="M18 13v7M14.5 16.5h7"/>',
    "folder": '<path class="soft" d="M3 7.5a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M3 10h18"/>',
    "folder-plus": '<path class="soft" d="M3 7.5a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M3 10h18M12 12.5v5M9.5 15h5"/>',
    "folder-open": '<path class="soft" d="M3 8a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v2H7l-4 7Z"/><path d="M7 12h15l-3 7H3"/>',
    "building": '<path class="soft" d="M4 21V6l8-3 8 3v15Z"/><path d="M8 8h2M14 8h2M8 12h2M14 12h2M8 16h2M14 16h2M2 21h20"/>',
    "file": '<path class="soft" d="M6 3h8l4 4v14H6Z"/><path d="M14 3v5h4M9 12h6M9 16h6"/>',
    "file-plus": '<path class="soft" d="M6 3h8l4 4v14H6Z"/><path d="M14 3v5h4M12 11v6M9 14h6"/>',
    "file-text": '<path class="soft" d="M6 3h8l4 4v14H6Z"/><path d="M14 3v5h4M9 12h6M9 16h6"/>',
    "file-pdf": '<path class="soft" d="M6 3h8l4 4v14H6Z"/><path d="M14 3v5h4M8.5 16.5v-5h1.3a1.5 1.5 0 1 1 0 3H8.5M13 11.5v5h1a2 2 0 0 0 0-5ZM18.5 16.5v-5H21"/>',
    "file-word": '<path class="soft" d="M6 3h8l4 4v14H6Z"/><path d="M14 3v5h4M8.5 12l1.2 5 1.3-3.5 1.3 3.5 1.2-5"/>',
    "file-image": '<path class="soft" d="M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/><circle cx="9" cy="9" r="1.5"/><path d="m4 17 5-5 3.5 3.5 2-2 5.5 5"/>',
    "file-sheet": '<path class="soft" d="M6 3h8l4 4v14H6Z"/><path d="M14 3v5h4M9 11h6v6H9ZM12 11v6M9 14h6"/>',
    "paperclip": '<path d="m9 17 7.7-7.7a3 3 0 0 0-4.2-4.2L4.8 12.8a5 5 0 0 0 7.1 7.1l7-7"/>',
    "arrow-left": '<path d="m14 6-6 6 6 6M8 12h12"/>',
    "arrow-right": '<path d="m10 6 6 6-6 6M4 12h12"/>',
    "arrow-up": '<path d="m6 14 6-6 6 6M12 8v12"/>',
    "arrow-down": '<path d="m6 10 6 6 6-6M12 4v12"/>',
    "trash": '<path d="M4 7h16M9 3h6l1 4H8ZM7 7l1 14h8l1-14M10 11v6M14 11v6"/>',
    "clear": '<path d="M4 6h16M7 10h10M9 14h6M11 18h2"/>',
    "layers": '<path class="soft" d="m12 3 9 5-9 5-9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
    "signature": '<path d="M4 17c2.5-5 4-8 5-8 1.5 0-1 8 .5 8 1 0 2-4 3-4s0 4 1.5 4c1 0 1.5-2 2.5-2s1.5 2 3.5 2M4 21h16"/>',
    "external": '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 13v7H4V6h7"/>',
    "template": '<path class="soft" d="M5 4h14v16H5Z"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    "warning": '<path class="soft" d="M12 3 2.5 20h19Z"/><path d="M12 9v5M12 17.5h.01"/>',
    "edit": '<path class="soft" d="M5 19h4l10-10-4-4L5 15Z"/><path d="m13.5 6.5 4 4M5 19h14"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
}


@lru_cache(maxsize=128)
def ui_icon(name: str, color: str = "#2B7564", size: int = 24) -> QIcon:
    """Return a crisp vector icon in the product palette."""
    shape = _SHAPES.get(name, _SHAPES["file"])
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24"
         fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
      <style>.soft {{ fill: {color}; fill-opacity: .12; }}</style>
      {shape}
    </svg>
    """.encode("utf-8")
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return QIcon(pixmap)


def file_icon_name(extension: str) -> tuple[str, str]:
    extension = extension.casefold()
    if extension in {".doc", ".docx", ".dot", ".dotx", ".odt", ".rtf"}:
        return "file-word", "#2563A7"
    if extension == ".pdf":
        return "file-pdf", "#C9493C"
    if extension in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp"}:
        return "file-image", "#7B55A6"
    if extension in {".xls", ".xlsx", ".ods", ".csv"}:
        return "file-sheet", "#2B7A55"
    return "file-text", "#60736D"
