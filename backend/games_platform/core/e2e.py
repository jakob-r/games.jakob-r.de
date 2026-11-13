"""Deterministic mode for end-to-end tests (`GAMES_E2E_FIXED=1`, set by `make e2e`).

Never enable this in production: boards become predictable and the host always opens.
"""

from __future__ import annotations

import os


def fixed_mode() -> bool:
    return os.getenv("GAMES_E2E_FIXED", "").strip() == "1"
