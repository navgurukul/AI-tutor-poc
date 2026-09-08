"""Production entrypoint:  python -m app.serve

The POC started uvicorn from a hand-written command line in start.ps1 and
run.sh, which is how `--host 0.0.0.0` ended up baked into both. Reading the
bind address from settings instead means there is one place to get it wrong,
and the packaged launcher configures the whole process through the environment
rather than shipping a .env file that can drift from the code defaults.
"""

import logging

import uvicorn

from app.config import settings

logger = logging.getLogger("ai-tutor.serve")


def main() -> None:
    if settings.bind_host not in ("127.0.0.1", "localhost", "::1"):
        # Not fatal -- a deliberate LAN deployment is a legitimate choice -- but
        # the library routes have no auth, so say so out loud.
        logger.warning(
            "Binding %s, which exposes the library upload and delete routes to "
            "the network. Loopback is the supported configuration.",
            settings.bind_host,
        )
    uvicorn.run(
        "app.main:app",
        host=settings.bind_host,
        port=settings.bind_port,
        log_level="info",
        access_log=not settings.packaged,
    )


if __name__ == "__main__":
    main()
