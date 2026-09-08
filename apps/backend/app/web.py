"""Serving the built frontend from the backend process.

The POC ran Vite alongside uvicorn, which meant a packaged device needed
Node.js at *runtime* just to hand over static files. Mounting `dist/` here
collapses that to one process and makes the app same-origin, so the browser
never issues a cross-origin request and CORS stops being needed at all.

Routing in the frontend is hash-based (`#setup`), so there is deliberately no
SPA history fallback: every real path is either an API route or a file on disk.
"""

from pathlib import Path
from typing import Optional

from starlette.responses import Response
from starlette.staticfiles import StaticFiles

# Vite fingerprints everything under assets/ (index-a91f2.js), so those may be
# cached forever. index.html must never be cached: it is the file that names
# the current fingerprints, and a stale copy pins the browser to the previous
# app version through an update.
_IMMUTABLE = "public, max-age=31536000, immutable"
_NO_STORE = "no-store, must-revalidate"


class SpaFiles(StaticFiles):
    """StaticFiles with cache headers that survive an app update."""

    def file_response(self, full_path, stat_result, scope, status_code=200) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        name = Path(full_path).name
        if name == "index.html":
            response.headers["Cache-Control"] = _NO_STORE
        elif "/assets/" in str(full_path).replace("\\", "/"):
            response.headers["Cache-Control"] = _IMMUTABLE
        return response


def resolve_web_dir(configured: str) -> Optional[Path]:
    """The directory to serve, or None if the mount should be skipped.

    Relative paths resolve against the backend package's parent, so the
    packaged launcher can pass `..\\web` and a developer can pass an absolute
    path without either of them caring which one the other used.
    """
    raw = (configured or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = (Path(__file__).resolve().parent.parent / path).resolve()
    return path if (path / "index.html").is_file() else None
