#!/usr/bin/env python3
"""
client.py — single WebSocket client for the Go chat server.

Usage:
    python client.py [ws://localhost:8080/ws]
"""

import asyncio
import json
import sys
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosedError, WebSocketException

SERVER_URL = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8080/ws"
MESSAGES_TO_SEND = 5
LISTEN_SECONDS = 5


def ts() -> str:
    """Current time as HH:MM:SS.mmm."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def log(tag: str, text: str) -> None:
    print(f"[{ts()}] [{tag}] {text}")


def pretty(raw: str) -> str:
    """Pretty-print JSON if possible, otherwise return as-is."""
    try:
        return json.dumps(json.loads(raw), separators=(", ", ": "))
    except (json.JSONDecodeError, ValueError):
        return raw


async def listen(ws: websockets.WebSocketClientProtocol, duration: float) -> None:
    """Receive all messages for *duration* seconds, printing each one."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + duration
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            log("RECV", pretty(raw))
        except asyncio.TimeoutError:
            break
        except ConnectionClosedError:
            log("INFO", "Connection closed by server while listening")
            break


async def run() -> None:
    log("INFO", f"Connecting to {SERVER_URL}")

    try:
        async with websockets.connect(SERVER_URL) as ws:
            log("INFO", "Connected")

            # 1. Receive welcome message
            welcome = await asyncio.wait_for(ws.recv(), timeout=5)
            log("RECV", pretty(welcome))

            # 2. Send 5 messages with 1-second intervals
            for n in range(1, MESSAGES_TO_SEND + 1):
                msg = f"Hello from Python client {n}"
                log("SEND", msg)
                await ws.send(msg)
                if n < MESSAGES_TO_SEND:
                    await asyncio.sleep(1)

            # 3. Listen for echoed/broadcast messages
            log("INFO", f"Listening for {LISTEN_SECONDS}s …")
            await listen(ws, LISTEN_SECONDS)

            # 4. Graceful close
            log("INFO", "Closing connection")
            await ws.close()
            log("INFO", "Disconnected cleanly")

    except ConnectionRefusedError:
        log("ERROR", f"Connection refused — is the Go server running on {SERVER_URL}?")
        sys.exit(1)
    except asyncio.TimeoutError:
        log("ERROR", "Timed out waiting for the welcome message")
        sys.exit(1)
    except WebSocketException as exc:
        log("ERROR", f"WebSocket error: {exc}")
        sys.exit(1)
    except OSError as exc:
        log("ERROR", f"Network error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run())
