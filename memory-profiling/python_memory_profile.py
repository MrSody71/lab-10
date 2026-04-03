#!/usr/bin/env python3
"""
python_memory_profile.py
Monitor FastAPI process RSS/VMS for 30 seconds while sending 100 /ping requests.
Saves results to memory_results/python_memory.json.
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

import httpx
import psutil
from tabulate import tabulate

FASTAPI_URL = "http://localhost:8000"
MONITOR_SECONDS = 30
LOAD_REQUESTS = 100
RESULTS_DIR = Path(__file__).parent / "memory_results"
OUT_FILE = RESULTS_DIR / "python_memory.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_uvicorn_pid() -> int | None:
    """Return PID of the first process whose cmdline contains 'uvicorn'."""
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
            if "uvicorn" in cmdline or ("python" in (proc.info["name"] or "").lower()
                                        and "main:app" in cmdline):
                return proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


def mb(value: int) -> float:
    return round(value / 1024 / 1024, 2)


# ---------------------------------------------------------------------------
# Async load generator
# ---------------------------------------------------------------------------

async def send_load(n: int) -> dict:
    """Send *n* GET /ping requests concurrently (batches of 20). Return stats."""
    ok = fail = 0
    async with httpx.AsyncClient(base_url=FASTAPI_URL, timeout=5) as client:
        for batch_start in range(0, n, 20):
            batch = min(20, n - batch_start)
            results = await asyncio.gather(
                *[client.get("/ping") for _ in range(batch)],
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Exception) or r.status_code != 200:
                    fail += 1
                else:
                    ok += 1
    return {"ok": ok, "failed": fail}


# ---------------------------------------------------------------------------
# Memory monitor
# ---------------------------------------------------------------------------

def monitor_memory(pid: int, duration: float) -> list[dict]:
    """Sample memory every second for *duration* seconds. Returns sample list."""
    proc = psutil.Process(pid)
    samples: list[dict] = []
    end = time.monotonic() + duration
    while time.monotonic() < end:
        try:
            mem = proc.memory_info()
            samples.append({
                "timestamp": round(time.monotonic(), 3),
                "rss_mb": mb(mem.rss),
                "vms_mb": mb(mem.vms),
            })
        except psutil.NoSuchProcess:
            print("  [WARN] FastAPI process disappeared during monitoring")
            break
        time.sleep(1)
    return samples


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[{datetime.now():%H:%M:%S}] Looking for FastAPI/uvicorn process …")
    pid = find_uvicorn_pid()
    if pid is None:
        print("  ERROR: FastAPI process not found. Is the server running?")
        print("  Start it with:  uvicorn main:app --port 8000  (inside python-service/)")
        raise SystemExit(1)
    print(f"[{datetime.now():%H:%M:%S}] Found process PID={pid}")

    # Verify reachability
    try:
        r = httpx.get(f"{FASTAPI_URL}/health", timeout=3)
        r.raise_for_status()
        print(f"[{datetime.now():%H:%M:%S}] FastAPI is reachable ({r.status_code})")
    except Exception as exc:
        print(f"  ERROR: FastAPI unreachable — {exc}")
        raise SystemExit(1)

    print(f"[{datetime.now():%H:%M:%S}] Monitoring {MONITOR_SECONDS}s "
          f"while sending {LOAD_REQUESTS} requests …")

    # Run memory monitor in the main thread; load in asyncio
    import threading
    load_result: dict = {}

    def _run_load():
        load_result.update(asyncio.run(send_load(LOAD_REQUESTS)))

    load_thread = threading.Thread(target=_run_load, daemon=True)
    load_thread.start()

    samples = monitor_memory(pid, MONITOR_SECONDS)
    load_thread.join(timeout=10)

    if not samples:
        print("  ERROR: No memory samples collected.")
        raise SystemExit(1)

    rss_values = [s["rss_mb"] for s in samples]
    vms_values = [s["vms_mb"] for s in samples]

    stats = {
        "service": "fastapi",
        "pid": pid,
        "monitor_seconds": MONITOR_SECONDS,
        "requests_sent": LOAD_REQUESTS,
        "requests_ok": load_result.get("ok", 0),
        "requests_failed": load_result.get("failed", 0),
        "rss_mb": {
            "min": min(rss_values),
            "max": max(rss_values),
            "avg": round(sum(rss_values) / len(rss_values), 2),
            "final": rss_values[-1],
        },
        "vms_mb": {
            "min": min(vms_values),
            "max": max(vms_values),
            "avg": round(sum(vms_values) / len(vms_values), 2),
            "final": vms_values[-1],
        },
        "samples": samples,
        "captured_at": datetime.now().isoformat(),
    }

    # ---- Print table ----
    print()
    table = [
        ["Metric",         "RSS (MB)",          "VMS (MB)"],
        ["Minimum",        stats["rss_mb"]["min"], stats["vms_mb"]["min"]],
        ["Maximum",        stats["rss_mb"]["max"], stats["vms_mb"]["max"]],
        ["Average",        stats["rss_mb"]["avg"], stats["vms_mb"]["avg"]],
        ["Final sample",   stats["rss_mb"]["final"], stats["vms_mb"]["final"]],
    ]
    print(tabulate(table[1:], headers=table[0], tablefmt="rounded_outline",
                   floatfmt=".2f"))
    print()
    print(f"  Requests: {stats['requests_ok']} ok / {stats['requests_failed']} failed")
    print(f"  Samples : {len(samples)}")
    print()

    OUT_FILE.write_text(json.dumps(stats, indent=2))
    print(f"Results saved to {OUT_FILE}")


if __name__ == "__main__":
    main()
