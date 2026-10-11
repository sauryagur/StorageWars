"""Vercel entrypoint.

Vercel looks for a `FastAPI` instance named `app` in `index.py`, `app.py`,
`main.py`, `server.py`, `asgi.py` or `wsgi.py`. The real app lives in
`src/openapi_server/main.py` because the OpenAPI generator owns that layout,
and `src/` is not on the function's import path, so this shim adds it and
re-exports the same ASGI application.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from openapi_server.main import app  # noqa: E402,F401
