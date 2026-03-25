"""HTTP client for sending grid data to Revit via pyRevit Routes."""

from __future__ import annotations

import json

import requests
from PySide6.QtCore import QThread, Signal


REVIT_URL = "http://localhost:48884/grid-api/create_grids/"
TIMEOUT_S = 3


class RevitSenderThread(QThread):
    """Sends the grid payload to Revit on a background thread."""

    finished = Signal(bool, str)  # (success, message)

    def __init__(self, payload: dict, parent=None):
        super().__init__(parent)
        self._payload = payload

    def run(self):
        try:
            resp = requests.post(
                REVIT_URL,
                json=self._payload,
                timeout=TIMEOUT_S,
            )
            if resp.ok:
                total = len(self._payload.get("grids_x", [])) + len(
                    self._payload.get("grids_y", [])
                )
                self.finished.emit(True, f"\u2713 {total} grids creados exitosamente")
            else:
                self.finished.emit(
                    False, f"Error {resp.status_code}: {resp.text[:200]}"
                )
        except requests.ConnectionError:
            self.finished.emit(
                False,
                "No se pudo conectar con Revit. Verifica que Revit est\u00e9 abierto y pyRevit Routes activo.",
            )
        except requests.Timeout:
            self.finished.emit(False, "Timeout: Revit no respondi\u00f3 en 3 s.")
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, f"Error inesperado: {exc}")
