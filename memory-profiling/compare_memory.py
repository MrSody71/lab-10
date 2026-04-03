#!/usr/bin/env python3
"""
compare_memory.py
Read memory_results/python_memory.json and memory_results/go_memory.json,
print a side-by-side comparison table, and summarise which service is leaner.
"""

import json
import sys
from pathlib import Path

from tabulate import tabulate

RESULTS_DIR = Path(__file__).parent / "memory_results"
PYTHON_FILE = RESULTS_DIR / "python_memory.json"
GO_FILE     = RESULTS_DIR / "go_memory.json"


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

def load(path: Path) -> dict:
    if not path.exists():
        print(f"  ERROR: {path} not found.")
        print("  Run the corresponding profiler first:")
        if "python" in path.name:
            print("    python python_memory_profile.py")
        else:
            print("    python go_memory_profile.py")
        raise SystemExit(1)
    return json.loads(path.read_text())


def _val(data: dict, *keys, default=None):
    """Safely drill into nested dicts."""
    node = data
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k, default)
        if node is None:
            return default
    return node


# ---------------------------------------------------------------------------
# Comparison rows
# ---------------------------------------------------------------------------

def build_rows(py: dict, go: dict) -> list[list]:
    """
    Return a list of table rows.
    FastAPI memory lives at py["rss_mb"] / py["vms_mb"].
    Gin memory lives at go["memory_mb"]["heap_inuse"] etc.
    """
    rows = []

    def row(label: str, py_path: list, go_path: list, unit: str = "MB") -> list:
        pv = _val(py, *py_path)
        gv = _val(go, *go_path)
        if pv is None or gv is None:
            diff = winner = "N/A"
        else:
            diff = round(pv - gv, 2)
            if abs(diff) < 0.5:
                winner = "≈ tie"
            elif diff > 0:
                winner = f"Gin  saves {abs(diff):.2f} {unit}"
            else:
                winner = f"FastAPI saves {abs(diff):.2f} {unit}"
        return [
            label,
            f"{pv:.2f} {unit}" if isinstance(pv, (int, float)) else "N/A",
            f"{gv:.2f} {unit}" if isinstance(gv, (int, float)) else "N/A",
            winner,
        ]

    rows.append(row("RSS min",   ["rss_mb", "min"],   ["memory_mb", "alloc",      "min"]))
    rows.append(row("RSS max",   ["rss_mb", "max"],   ["memory_mb", "alloc",      "max"]))
    rows.append(row("RSS avg",   ["rss_mb", "avg"],   ["memory_mb", "alloc",      "avg"]))
    rows.append(row("RSS final", ["rss_mb", "final"], ["memory_mb", "alloc",      "final"]))
    rows.append(row("Heap min",  ["rss_mb", "min"],   ["memory_mb", "heap_inuse", "min"]))
    rows.append(row("Heap max",  ["rss_mb", "max"],   ["memory_mb", "heap_inuse", "max"]))
    rows.append(row("Heap avg",  ["rss_mb", "avg"],   ["memory_mb", "heap_inuse", "avg"]))
    rows.append(row("OS Sys avg",["vms_mb", "avg"],   ["memory_mb", "sys",        "avg"]))

    return rows


# ---------------------------------------------------------------------------
# Summary verdict
# ---------------------------------------------------------------------------

def verdict(py: dict, go: dict) -> str:
    py_avg = _val(py, "rss_mb", "avg")
    go_avg = _val(go, "memory_mb", "alloc", "avg")
    if py_avg is None or go_avg is None:
        return "Insufficient data for a verdict."

    diff = abs(py_avg - go_avg)
    pct  = diff / max(py_avg, go_avg) * 100

    if diff < 0.5:
        return "Both services use roughly the same amount of memory (< 0.5 MB apart)."
    if py_avg > go_avg:
        return (
            f"Gin uses less memory: avg alloc {go_avg:.2f} MB vs "
            f"FastAPI RSS {py_avg:.2f} MB — difference {diff:.2f} MB ({pct:.1f}%)."
        )
    return (
        f"FastAPI uses less memory: avg RSS {py_avg:.2f} MB vs "
        f"Gin alloc {go_avg:.2f} MB — difference {diff:.2f} MB ({pct:.1f}%)."
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    py = load(PYTHON_FILE)
    go = load(GO_FILE)

    py_captured = py.get("captured_at", "unknown")
    go_captured = go.get("captured_at", "unknown")

    print()
    print("=" * 70)
    print("  Memory Comparison: FastAPI (Python) vs Gin (Go)")
    print("=" * 70)
    print(f"  FastAPI profile : {py_captured}  (PID {py.get('pid', '?')})")
    print(f"  Gin profile     : {go_captured}")
    print(f"  Load            : {py.get('requests_sent', '?')} requests each")
    print()

    rows = build_rows(py, go)
    print(tabulate(
        rows,
        headers=["Metric", "FastAPI", "Gin", "Winner"],
        tablefmt="rounded_outline",
        colalign=("left", "right", "right", "left"),
    ))
    print()

    # Request success rates
    def req_row(label, data, ok_key="requests_ok", fail_key="requests_failed"):
        ok   = data.get(ok_key, 0)
        fail = data.get(fail_key, 0)
        total = ok + fail
        rate = f"{ok/total*100:.1f}%" if total else "N/A"
        return [label, ok, fail, rate]

    print(tabulate(
        [req_row("FastAPI", py), req_row("Gin", go)],
        headers=["Service", "OK", "Failed", "Success rate"],
        tablefmt="rounded_outline",
    ))
    print()

    # Verdict
    print("Verdict")
    print("-" * 70)
    print(f"  {verdict(py, go)}")
    print()

    # Note on metric alignment
    print("Note: FastAPI metric is process RSS (from psutil); "
          "Gin metric is heap Alloc\n"
          "      (from pprof) — both reflect live working-set memory "
          "but are not\n"
          "      identical measurement methods. RSS includes the Python "
          "interpreter\n"
          "      and all loaded C extensions.")
    print()


if __name__ == "__main__":
    main()
