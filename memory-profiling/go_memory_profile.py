#!/usr/bin/env python3
"""
go_memory_profile.py
Fetch pprof heap data from Go service, parse runtime memory stats,
send 100 requests to /ping during profiling, save to memory_results/go_memory.json.

The Go service must expose pprof — see go_pprof_guide.md for setup instructions.
Heap endpoint: http://localhost:6060/debug/pprof/heap
"""

import asyncio
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx
from tabulate import tabulate

GO_URL = "http://localhost:8080"
PPROF_URL = "http://localhost:6060"
HEAP_ENDPOINT = f"{PPROF_URL}/debug/pprof/heap"
PPROF_INDEX   = f"{PPROF_URL}/debug/pprof/"
MONITOR_SECONDS = 30
LOAD_REQUESTS = 100
RESULTS_DIR = Path(__file__).parent / "memory_results"
OUT_FILE = RESULTS_DIR / "go_memory.json"

# Patterns for the pprof text header Go emits before the binary profile data.
# Example line:  # HeapInuse = 1597440
_STAT_RE = re.compile(r"^#\s+(\w+)\s*=\s*(\d+)", re.MULTILINE)

# Stats we care about (all in bytes in the raw output)
WANTED = {
    "HeapInuse":  "heap_inuse",
    "HeapAlloc":  "heap_alloc",
    "HeapSys":    "heap_sys",
    "HeapIdle":   "heap_idle",
    "HeapObjects":"heap_objects",
    "Sys":        "sys",
    "Alloc":      "alloc",
    "TotalAlloc": "total_alloc",
    "NumGC":      "num_gc",
}


def mb(value: int) -> float:
    return round(value / 1024 / 1024, 2)


# ---------------------------------------------------------------------------
# pprof fetch + parse
# ---------------------------------------------------------------------------

def fetch_heap_stats(client: httpx.Client) -> dict:
    """
    Fetch one heap snapshot and return parsed memory stats.
    pprof binary profiles start with a text comment block; we only need that.
    """
    resp = client.get(HEAP_ENDPOINT, timeout=10)
    resp.raise_for_status()

    # The response is binary (protobuf) but the Go runtime prepends a
    # human-readable comment header.  Read only the first 4 KB (header).
    header = resp.content[:4096].decode("utf-8", errors="replace")

    stats: dict[str, int] = {}
    for m in _STAT_RE.finditer(header):
        key, raw = m.group(1), int(m.group(2))
        if key in WANTED:
            stats[WANTED[key]] = raw

    return stats


# ---------------------------------------------------------------------------
# Async load generator (same pattern as python_memory_profile.py)
# ---------------------------------------------------------------------------

async def send_load(n: int) -> dict:
    ok = fail = 0
    async with httpx.AsyncClient(base_url=GO_URL, timeout=5) as client:
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
# Periodic sampler
# ---------------------------------------------------------------------------

def sample_loop(duration: float) -> list[dict]:
    """
    Sample heap stats every second for *duration* seconds while Go is under load.
    Returns a list of sample dicts, each tagged with elapsed time.
    """
    samples: list[dict] = []
    with httpx.Client() as client:
        # Check pprof is reachable before starting
        try:
            client.get(PPROF_INDEX, timeout=3).raise_for_status()
        except Exception as exc:
            print(f"  ERROR: pprof not reachable at {PPROF_URL} — {exc}")
            print("  See go_pprof_guide.md to enable pprof in the Go service.")
            raise SystemExit(1)

        end = time.monotonic() + duration
        while time.monotonic() < end:
            t0 = time.monotonic()
            try:
                raw = fetch_heap_stats(client)
                sample = {
                    "elapsed_s": round(t0, 2),
                    **{k: mb(v) if "objects" not in k and "num_gc" not in k else v
                       for k, v in raw.items()},
                }
                samples.append(sample)
            except httpx.HTTPStatusError as exc:
                print(f"  [WARN] pprof fetch failed: {exc}")
            elapsed = time.monotonic() - t0
            time.sleep(max(0, 1 - elapsed))
    return samples


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[{datetime.now():%H:%M:%S}] Checking Go service at {GO_URL} …")
    try:
        r = httpx.get(f"{GO_URL}/ping", timeout=3)
        r.raise_for_status()
        print(f"[{datetime.now():%H:%M:%S}] Go service reachable ({r.status_code})")
    except Exception as exc:
        print(f"  ERROR: Go service unreachable — {exc}")
        raise SystemExit(1)

    print(f"[{datetime.now():%H:%M:%S}] Starting {MONITOR_SECONDS}s profile "
          f"with {LOAD_REQUESTS} concurrent requests …")

    load_result: dict = {}

    def _run_load():
        load_result.update(asyncio.run(send_load(LOAD_REQUESTS)))

    load_thread = threading.Thread(target=_run_load, daemon=True)
    load_thread.start()

    samples = sample_loop(MONITOR_SECONDS)
    load_thread.join(timeout=10)

    if not samples:
        print("  ERROR: No samples collected — check pprof setup.")
        raise SystemExit(1)

    # Aggregate stats for fields measured in MB
    mb_fields = ["heap_inuse", "heap_alloc", "heap_sys", "heap_idle", "sys", "alloc"]
    agg: dict[str, dict] = {}
    for field in mb_fields:
        values = [s[field] for s in samples if field in s]
        if values:
            agg[field] = {
                "min": min(values),
                "max": max(values),
                "avg": round(sum(values) / len(values), 2),
                "final": values[-1],
            }

    result = {
        "service": "gin",
        "go_url": GO_URL,
        "pprof_url": PPROF_URL,
        "monitor_seconds": MONITOR_SECONDS,
        "requests_sent": LOAD_REQUESTS,
        "requests_ok": load_result.get("ok", 0),
        "requests_failed": load_result.get("failed", 0),
        "memory_mb": agg,
        "samples": samples,
        "captured_at": datetime.now().isoformat(),
    }

    # ---- Print table ----
    print()
    rows = []
    labels = {
        "heap_inuse": "HeapInuse",
        "heap_alloc": "HeapAlloc",
        "heap_sys":   "HeapSys",
        "alloc":      "Alloc (live)",
        "sys":        "Sys (OS total)",
    }
    for field, label in labels.items():
        if field in agg:
            a = agg[field]
            rows.append([label, a["min"], a["max"], a["avg"], a["final"]])

    print(tabulate(rows,
                   headers=["Metric", "Min (MB)", "Max (MB)", "Avg (MB)", "Final (MB)"],
                   tablefmt="rounded_outline", floatfmt=".2f"))
    print()
    print(f"  Requests: {result['requests_ok']} ok / {result['requests_failed']} failed")
    print(f"  Samples : {len(samples)}")
    print()

    OUT_FILE.write_text(json.dumps(result, indent=2))
    print(f"Results saved to {OUT_FILE}")


if __name__ == "__main__":
    main()
