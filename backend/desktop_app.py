from __future__ import annotations

import argparse
import sys
import threading
import time
import urllib.error
import urllib.request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Kidsnote app in a desktop window.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--title", default="Kidsnote Backup Console")
    parser.add_argument("--startup-timeout", type=float, default=20.0)
    parser.add_argument("--width", type=int, default=1320)
    parser.add_argument("--height", type=int, default=920)
    parser.add_argument("--min-width", type=int, default=1080)
    parser.add_argument("--min-height", type=int, default=760)
    parser.add_argument("--smoke-test", action="store_true")
    return parser.parse_args()


def server_url(host: str, port: int) -> str:
    browser_host = "127.0.0.1" if host == "0.0.0.0" else host
    return f"http://{browser_host}:{port}"


def start_server(host: str, port: int):
    import uvicorn
    from main import app

    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="kidsnote-local-server")
    thread.start()
    return server, thread


def wait_for_server(url: str, timeout: float, server, thread: threading.Thread) -> None:
    deadline = time.time() + timeout
    health_url = f"{url}/api/health"
    while time.time() < deadline:
        if not thread.is_alive():
            raise RuntimeError("local server stopped before startup completed")
        try:
            with urllib.request.urlopen(health_url, timeout=1.0) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.25)
    raise RuntimeError(f"local server did not start within {timeout:.1f}s")


def stop_server(server, thread: threading.Thread) -> None:
    if getattr(server, "should_exit", False):
        return
    server.should_exit = True
    thread.join(timeout=5)


def main() -> int:
    args = parse_args()
    url = server_url(args.host, args.port)
    server, thread = start_server(args.host, args.port)
    try:
        wait_for_server(url, args.startup_timeout, server, thread)
        if args.smoke_test:
            print(f"[kidsnote] desktop smoke test passed at {url}")
            return 0

        import webview

        webview.create_window(
            args.title,
            url,
            width=args.width,
            height=args.height,
            min_size=(args.min_width, args.min_height),
            text_select=True,
        )
        webview.start()
        return 0
    finally:
        stop_server(server, thread)


if __name__ == "__main__":
    raise SystemExit(main())
