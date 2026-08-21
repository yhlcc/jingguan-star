"""Backward-compatible launcher.

The application implementation now lives in the modular FastAPI packages under
``app.api``, ``app.agent``, ``app.repositories`` and ``app.services``.
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run("app.main:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()
