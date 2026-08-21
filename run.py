from __future__ import annotations

import faulthandler
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


LOG_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / "GestorDocumental"
LOG_FILE = LOG_DIR / "gestor-documental.log"


def install_error_log():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    crash_stream = LOG_FILE.open("a", encoding="utf-8")
    crash_stream.write(f"\n--- Inicio {datetime.now().isoformat(timespec='seconds')} ---\n")
    crash_stream.flush()
    faulthandler.enable(crash_stream)

    def report_exception(exception_type, exception, trace):
        traceback.print_exception(exception_type, exception, trace, file=crash_stream)
        crash_stream.flush()
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance():
                QMessageBox.critical(
                    None,
                    "Gestor de documental encontró un problema",
                    "La aplicación evitó un cierre silencioso.\n\n"
                    f"Detalle: {exception}\n\n"
                    f"Registro: {LOG_FILE}",
                )
        except Exception:
            pass

    sys.excepthook = report_exception
    return crash_stream


if __name__ == "__main__":
    _log_stream = install_error_log()
    from gestor_documental.app import main

    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        sys.excepthook(*sys.exc_info())
        raise SystemExit(1)
