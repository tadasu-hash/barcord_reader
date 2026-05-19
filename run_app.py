from __future__ import annotations

import threading
import time
import webbrowser

import uvicorn

HOST = "127.0.0.1"
PORT = 8000


def open_browser() -> None:
    time.sleep(1.0)
    webbrowser.open(f"http://{HOST}:{PORT}/docs")


if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("app:app", host=HOST, port=PORT, reload=False)
