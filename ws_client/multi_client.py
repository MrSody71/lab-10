#!/usr/bin/env python3
"""
multi_client.py — 3 concurrent WebSocket clients demonstrating broadcast.

Each client connects, receives the welcome, sends 3 messages, then listens
long enough to receive messages from the other clients.  All output is
interleaved in real time so you can watch broadcasts flowing between clients.

Usage:
    python multi_client.py [ws://localhost:8080/ws]
"""

import asyncio
import json
import sys
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosedError, WebSocketException

SERVER_URL = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8080/ws"

NUM_CLIENTS = 3
MSGS_PER_CLIENT = 3
SEND_INTERVAL = 0.5   # seconds between each message send
LISTEN_SECONDS = 6.0  # listen window after all sends complete

# One lock so output lines from different clients don't interleave mid-line
_print_lock = asyncio.Lock()


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


async def log(client_id: int, tag: str, text: str) -> None:
    async with _print_lock:
        print(f"[{ts()}] [Client-{client_id}] [{tag}] {text}", flush=True)


def pretty(raw: str) -> str:
    try:
        return json.dumps(json.loads(raw), separators=(", ", ": "))
    except (json.JSONDecodeError, ValueError):
        return raw


async def listen_window(
    ws: websockets.WebSocketClientProtocol,
    client_id: int,
    duration: float,
) -> int:
    """Drain incoming messages for *duration* seconds. Returns count received."""
    count = 0
    loop = asyncio.get_running_loop()
    deadline = loop.time() + duration
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            count += 1
            await log(client_id, "RECV", pretty(raw))
        except asyncio.TimeoutError:
            break
        except ConnectionClosedError:
            await log(client_id, "INFO", "Server closed connection")
            break
    return count


async def client(client_id: int, start_barrier: asyncio.Barrier) -> None:
    """Single client coroutine."""
    await log(client_id, "INFO", f"Connecting to {SERVER_URL}")

    try:
        async with websockets.connect(SERVER_URL) as ws:
            await log(client_id, "INFO", "Connected")

            # Welcome message
            welcome = await asyncio.wait_for(ws.recv(), timeout=5)
            await log(client_id, "RECV", pretty(welcome))

            # Wait until every client is connected before anyone starts sending,
            # so the broadcast demo is as clear as possible.
            await log(client_id, "INFO", "Waiting for all clients to connect …")
            await start_barrier.wait()
            await log(client_id, "INFO", "All clients ready — starting sends")

            # Send MSGS_PER_CLIENT messages
            for n in range(1, MSGS_PER_CLIENT + 1):
                msg = f"Client-{client_id} message {n}"
                await log(client_id, "SEND", msg)
                await ws.send(msg)
                await asyncio.sleep(SEND_INTERVAL)

            # Listen window — receive broadcasts from other clients
            await log(client_id, "INFO", f"Listening for {LISTEN_SECONDS}s …")
            received = await listen_window(ws, client_id, LISTEN_SECONDS)

            await ws.close()
            await log(
                client_id,
                "INFO",
                f"Disconnected — received {received} broadcast message(s)",
            )

    except ConnectionRefusedError:
        await log(client_id, "ERROR",
                  f"Connection refused — is the Go server running on {SERVER_URL}?")
    except asyncio.TimeoutError:
        await log(client_id, "ERROR", "Timed out waiting for welcome message")
    except WebSocketException as exc:
        await log(client_id, "ERROR", f"WebSocket error: {exc}")
    except OSError as exc:
        await log(client_id, "ERROR", f"Network error: {exc}")


async def main() -> None:
    print("=" * 60)
    print(f"  WebSocket broadcast demo — {NUM_CLIENTS} clients")
    print(f"  Each sends {MSGS_PER_CLIENT} messages → all others receive them")
    print(f"  Server: {SERVER_URL}")
    print("=" * 60)
    print()

    # asyncio.Barrier: all clients wait here after connecting before sending,
    # so the send phase starts simultaneously.
    barrier = asyncio.Barrier(NUM_CLIENTS)

    tasks = [
        asyncio.create_task(client(i + 1, barrier), name=f"client-{i + 1}")
        for i in range(NUM_CLIENTS)
    ]

    await asyncio.gather(*tasks, return_exceptions=True)

    print()
    print("=" * 60)
    print("  All clients finished.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
