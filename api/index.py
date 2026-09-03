"""The serverless entry point.

Vercel discovers a Python function by file, and expects an ASGI application
named `app` in it. The application itself lives in `backend/`, unchanged and
unaware of any of this — the whole file is a shim, which is the point: nothing
about the deployment target reaches into the app.

`backend/` is not a package and is not installed, so it goes on the path here
rather than being restructured to suit one host.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.main import app  # noqa: E402  (must follow the path insert)

__all__ = ["app"]
