"""Request guards for the packaged device build.

Binding to loopback stops peers on the school Wi-Fi from reaching the API, but
it is not by itself enough. Two attacks still get through a loopback bind, and
each needs its own guard:

  * **DNS rebinding.** A page the student visits resolves its own hostname to
    127.0.0.1 and then talks to us; the socket is local, so the bind does not
    help. The Host header still carries the attacker's domain, which is what
    `_host_ok` rejects.

  * **Cross-site form POST.** `multipart/form-data` is a CORS-*simple* content
    type, so a hostile page can submit an 80 MB PDF to
    `POST /api/library/documents` with no preflight -- CORS never enters the
    picture and never gets a chance to block it.

Both are off unless `settings.packaged` is set, so development is unaffected.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})
# "none" is a direct navigation (the student typing the URL); "same-origin" is
# our own page calling its own API. Anything else is another site driving the
# request.
_ALLOWED_FETCH_SITE = frozenset({"same-origin", "none"})


def _host_ok(host_header: str) -> bool:
    host = (host_header or "").strip()
    if not host:
        return False
    # Strip the port, keeping bracketed IPv6 literals intact.
    if host.startswith("["):
        hostname = host[: host.find("]") + 1] if "]" in host else host
    else:
        hostname = host.rsplit(":", 1)[0] if ":" in host else host
    return hostname.lower() in _LOOPBACK


class LocalOnlyMiddleware(BaseHTTPMiddleware):
    """Reject anything that a local, first-party browser tab would not send."""

    async def dispatch(self, request, call_next):
        if not _host_ok(request.headers.get("host", "")):
            return JSONResponse(
                status_code=421,
                content={"detail": "Request rejected: unrecognised Host header."},
            )

        if request.method in _MUTATING:
            # Only judge the header when the client actually sent one. Every
            # Chromium build sends it, so the cross-site case is always caught;
            # a local CLI (smoke_test.py, evaluate_retrieval.py) sends nothing
            # and is a local process that could bypass us anyway.
            site = request.headers.get("sec-fetch-site")
            if site is not None and site.lower() not in _ALLOWED_FETCH_SITE:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Request rejected: cross-site write."},
                )

        return await call_next(request)
