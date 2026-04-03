#!/usr/bin/env python3
"""
parse_results.py — parse Apache Bench output files from results/
and produce a comparison table (stdout + results/summary.md).
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class BenchResult:
    label: str
    rps: float | None = None        # Requests per second
    mean_ms: float | None = None    # Time per request (mean, ms)
    failed: int | None = None       # Failed requests


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_RPS_RE    = re.compile(r"^Requests per second:\s+([\d.]+)", re.MULTILINE)
_MEAN_RE   = re.compile(r"^Time per request:\s+([\d.]+)\s+\[ms\] \(mean\)", re.MULTILINE)
_FAILED_RE = re.compile(r"^Failed requests:\s+(\d+)", re.MULTILINE)


def parse_file(path: Path) -> BenchResult:
    text = path.read_text(errors="replace")
    label = path.stem  # strip timestamp prefix if present

    def _float(pattern: re.Pattern) -> float | None:
        m = pattern.search(text)
        return float(m.group(1)) if m else None

    def _int(pattern: re.Pattern) -> int | None:
        m = pattern.search(text)
        return int(m.group(1)) if m else None

    return BenchResult(
        label=label,
        rps=_float(_RPS_RE),
        mean_ms=_float(_MEAN_RE),
        failed=_int(_FAILED_RE),
    )


# ---------------------------------------------------------------------------
# Label helpers — map raw filename stems to human-readable names
# ---------------------------------------------------------------------------

_LABEL_MAP = {
    "gin_ping_1k":     ("Gin",     "GET /ping",  "1 000 req / 10c"),
    "fastapi_ping_1k": ("FastAPI", "GET /ping",  "1 000 req / 10c"),
    "gin_ping_5k":     ("Gin",     "GET /ping",  "5 000 req / 50c"),
    "fastapi_ping_5k": ("FastAPI", "GET /ping",  "5 000 req / 50c"),
    "gin_echo_1k":     ("Gin",     "POST /echo", "1 000 req / 10c"),
    "fastapi_echo_1k": ("FastAPI", "POST /echo", "1 000 req / 10c"),
}

# Canonical test ordering for the output table
_TEST_ORDER = [
    ("GET /ping",  "1 000 req / 10c"),
    ("GET /ping",  "5 000 req / 50c"),
    ("POST /echo", "1 000 req / 10c"),
]


def _short_key(stem: str) -> str:
    """Strip leading YYYYMMDD_HHMMSS_ timestamp if present."""
    # stems look like "20240101_120000_gin_ping_1k"
    parts = stem.split("_", 2)
    if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
        return parts[2]
    return stem


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt(value: float | int | None, unit: str = "") -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:,.2f}{unit}"
    return f"{value:,}{unit}"


def _table_row(service: str, endpoint: str, load: str, r: BenchResult | None) -> tuple[str, ...]:
    if r is None:
        return (service, endpoint, load, "—", "—", "—")
    return (
        service,
        endpoint,
        load,
        _fmt(r.rps,     " req/s"),
        _fmt(r.mean_ms, " ms"),
        _fmt(r.failed),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    results_dir = Path(__file__).parent / "results"
    if not results_dir.is_dir():
        print(f"Error: results directory not found at {results_dir}", file=sys.stderr)
        sys.exit(1)

    txt_files = sorted(results_dir.glob("*.txt"))
    if not txt_files:
        print("No .txt result files found in results/. Run run_benchmarks.sh first.",
              file=sys.stderr)
        sys.exit(1)

    # Parse every file; keep the *latest* result per short key
    by_key: dict[str, BenchResult] = {}
    for path in txt_files:
        key = _short_key(path.stem)
        by_key[key] = parse_file(path)  # later files (sorted) win

    # Build rows in canonical order
    HEADERS = ("Service", "Endpoint", "Load", "Req/sec", "Mean latency", "Failed")
    rows: list[tuple[str, ...]] = []

    for endpoint, load in _TEST_ORDER:
        for service in ("Gin", "FastAPI"):
            # find the matching key
            canonical_key = next(
                (k for k, (svc, ep, ld) in _LABEL_MAP.items()
                 if svc == service and ep == endpoint and ld == load),
                None,
            )
            result = by_key.get(canonical_key) if canonical_key else None
            rows.append(_table_row(service, endpoint, load, result))

    # ---- stdout: aligned plain table ----
    col_widths = [
        max(len(h), max(len(r[i]) for r in rows))
        for i, h in enumerate(HEADERS)
    ]

    def _plain_row(cells: tuple[str, ...]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cells, col_widths))

    separator = "  ".join("-" * w for w in col_widths)
    print()
    print("Benchmark Results")
    print("=" * len(separator))
    print(_plain_row(HEADERS))
    print(separator)
    prev_test = None
    for r in rows:
        test_id = (r[1], r[2])
        if prev_test and test_id != prev_test:
            print(separator)
        print(_plain_row(r))
        prev_test = test_id
    print()

    # ---- markdown table ----
    def _md_row(cells: tuple[str, ...]) -> str:
        return "| " + " | ".join(cells) + " |"

    def _md_sep(n: int) -> str:
        return "| " + " | ".join(["---"] * n) + " |"

    md_lines = [
        "# Benchmark Results\n",
        _md_row(HEADERS),
        _md_sep(len(HEADERS)),
    ]
    prev_test = None
    for r in rows:
        test_id = (r[1], r[2])
        if prev_test and test_id != prev_test:
            md_lines.append(_md_row(("", "", "", "", "", "")))  # blank separator row
        md_lines.append(_md_row(r))
        prev_test = test_id

    summary_path = results_dir / "summary.md"
    summary_path.write_text("\n".join(md_lines) + "\n")
    print(f"Markdown summary saved to {summary_path}")


if __name__ == "__main__":
    main()
