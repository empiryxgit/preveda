"""Runs the two listeners of the container in one process:  python -m preveda_dr.server
   API  (REST, /docs, /madhu/*, /health, /metrics)  on PREVEDA_API_PORT  (default 8080)
   Web  (the browser app + its /ui-api)             on PREVEDA_WEB_PORT  (default 8081)
Both share one model, one database and one folder scanner."""
from __future__ import annotations
import asyncio, contextlib, signal
import uvicorn
from .api.main import create_pair
from .core.settings import get_settings


async def _serve() -> None:
    s = get_settings()
    api, web = create_pair()
    servers = [
        uvicorn.Server(uvicorn.Config(api, host=s.bind_host, port=s.api_port, log_config=None, access_log=False)),
        uvicorn.Server(uvicorn.Config(web, host=s.bind_host, port=s.web_port, log_config=None, access_log=False, lifespan="off")),
    ]
    for sv in servers:     # one shared shutdown handler instead of one per server
        sv.install_signal_handlers = lambda: None
        sv.capture_signals = lambda: contextlib.nullcontext()

    def stop() -> None:
        for sv in servers:
            sv.should_exit = True

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, stop)
    await asyncio.gather(*(sv.serve() for sv in servers))


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
