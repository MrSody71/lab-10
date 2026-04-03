#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GIN_URL="http://localhost:8080"
FASTAPI_URL="http://localhost:8000"
RESULTS_DIR="$(dirname "$0")/results"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
POST_DATA="$(dirname "$0")/post_data.json"

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
if ! command -v ab &>/dev/null; then
    echo "Error: 'ab' (Apache Bench) is not installed."
    echo "  Ubuntu/Debian:  sudo apt install apache2-utils"
    echo "  macOS:          brew install httpd   (ab is bundled)"
    echo "  Windows/WSL:    sudo apt install apache2-utils"
    exit 1
fi

if [[ ! -f "$POST_DATA" ]]; then
    echo "Error: post_data.json not found at $POST_DATA"
    exit 1
fi

mkdir -p "$RESULTS_DIR"

# ---------------------------------------------------------------------------
# Helper: run ab and tee to file + stdout, return the output file path
# ---------------------------------------------------------------------------
run_ab() {
    local label="$1"   # e.g. gin_ping_1k
    local url="$2"
    local n="$3"       # total requests
    local c="$4"       # concurrency
    local extra="${5:-}"  # optional extra flags (e.g. POST flags)

    local out="$RESULTS_DIR/${TIMESTAMP}_${label}.txt"
    echo ""
    echo "=== $label  (n=$n c=$c) ==="
    echo "    URL: $url"

    # shellcheck disable=SC2086
    ab -n "$n" -c "$c" -q $extra "$url" > "$out" 2>&1 || true

    echo "    Saved → $out"
    echo "$out"   # return path via stdout (captured by caller)
}

# ---------------------------------------------------------------------------
# Helper: extract "Requests per second" from an ab result file
# ---------------------------------------------------------------------------
rps() { grep -m1 "^Requests per second" "$1" | awk '{print $4}'; }

# ---------------------------------------------------------------------------
# Test 1 — GET /ping, 1 000 req, 10 concurrent
# ---------------------------------------------------------------------------
echo "################################################################"
echo "#  Test 1: GET /ping  — 1 000 req / 10 concurrent"
echo "################################################################"
f_gin_ping_1k=$(run_ab  "gin_ping_1k"     "$GIN_URL/ping"     1000  10)
f_fapi_ping_1k=$(run_ab "fastapi_ping_1k" "$FASTAPI_URL/ping" 1000  10)

# ---------------------------------------------------------------------------
# Test 2 — GET /ping, 5 000 req, 50 concurrent
# ---------------------------------------------------------------------------
echo ""
echo "################################################################"
echo "#  Test 2: GET /ping  — 5 000 req / 50 concurrent"
echo "################################################################"
f_gin_ping_5k=$(run_ab  "gin_ping_5k"     "$GIN_URL/ping"     5000  50)
f_fapi_ping_5k=$(run_ab "fastapi_ping_5k" "$FASTAPI_URL/ping" 5000  50)

# ---------------------------------------------------------------------------
# Test 3 — POST /echo, 1 000 req, 10 concurrent
# ---------------------------------------------------------------------------
POST_FLAGS="-p $POST_DATA -T application/json"
echo ""
echo "################################################################"
echo "#  Test 3: POST /echo — 1 000 req / 10 concurrent"
echo "################################################################"
f_gin_echo=$(run_ab  "gin_echo_1k"     "$GIN_URL/echo"     1000  10  "$POST_FLAGS")
f_fapi_echo=$(run_ab "fastapi_echo_1k" "$FASTAPI_URL/echo" 1000  10  "$POST_FLAGS")

# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------
col() {
    local file="$1"
    local rps_val mean_val fail_val
    rps_val=$(grep -m1 "^Requests per second"  "$file" | awk '{print $4}' || echo "N/A")
    mean_val=$(grep -m1 "^Time per request"     "$file" | head -1 | awk '{print $4}' || echo "N/A")
    fail_val=$(grep -m1 "^Failed requests"      "$file" | awk '{print $3}' || echo "N/A")
    printf "%-14s %-14s %-10s" "$rps_val" "$mean_val" "$fail_val"
}

echo ""
echo "################################################################"
echo "#  SUMMARY"
echo "################################################################"
printf "%-28s  %-14s %-14s %-10s\n" "Test"  "Req/sec"  "Mean(ms)" "Failed"
printf "%-28s  %-14s %-14s %-10s\n" "----"  "-------"  "---------" "------"
printf "%-28s  %s\n" "Gin     /ping 1k/10c"  "$(col "$f_gin_ping_1k")"
printf "%-28s  %s\n" "FastAPI /ping 1k/10c"  "$(col "$f_fapi_ping_1k")"
printf "%-28s  %s\n" "Gin     /ping 5k/50c"  "$(col "$f_gin_ping_5k")"
printf "%-28s  %s\n" "FastAPI /ping 5k/50c"  "$(col "$f_fapi_ping_5k")"
printf "%-28s  %s\n" "Gin     /echo 1k/10c"  "$(col "$f_gin_echo")"
printf "%-28s  %s\n" "FastAPI /echo 1k/10c"  "$(col "$f_fapi_echo")"

echo ""
echo "Full results saved in: $RESULTS_DIR/"
echo "Run parse_results.py for a markdown summary."
