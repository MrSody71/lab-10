#!/usr/bin/env bash
# run_all.sh — build & dependency setup for Lab-10
# Does NOT start servers (they are long-running); prints ordered manual steps instead.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
OK="[OK]"
WARN="[WARN]"
ERR="[ERR]"
STEP="[STEP]"

# ---------------------------------------------------------------------------
# Colours (disabled automatically when stdout is not a terminal)
# ---------------------------------------------------------------------------
if [ -t 1 ]; then
    GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    RED='\033[0;31m';   CYAN='\033[0;36m'
    BOLD='\033[1m';     RESET='\033[0m'
else
    GREEN=''; YELLOW=''; RED=''; CYAN=''; BOLD=''; RESET=''
fi

log_ok()   { echo -e "${GREEN}${OK}${RESET}   $*"; }
log_warn() { echo -e "${YELLOW}${WARN}${RESET} $*"; }
log_err()  { echo -e "${RED}${ERR}${RESET}   $*"; }
log_step() { echo -e "${CYAN}${STEP}${RESET} ${BOLD}$*${RESET}"; }
log_info() { echo "       $*"; }

ERRORS=0
fail() { log_err "$*"; ERRORS=$((ERRORS + 1)); }

# ---------------------------------------------------------------------------
# 1. Check Go
# ---------------------------------------------------------------------------
echo ""
log_step "Checking Go installation …"
if command -v go &>/dev/null; then
    GO_VERSION="$(go version 2>&1)"
    log_ok "Go found: ${GO_VERSION}"
else
    fail "Go is not installed or not in PATH."
    log_info "Install from https://go.dev/dl/"
    log_info "Debian/Ubuntu: sudo apt install golang-go"
    log_info "macOS:         brew install go"
    log_info "Windows:       winget install GoLang.Go"
fi

# ---------------------------------------------------------------------------
# 2. Check Python 3
# ---------------------------------------------------------------------------
echo ""
log_step "Checking Python 3 installation …"
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        PY_VER="$("$candidate" --version 2>&1)"
        if echo "$PY_VER" | grep -q "Python 3"; then
            PYTHON="$candidate"
            log_ok "Python found: ${PY_VER} (${candidate})"
            break
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    fail "Python 3 is not installed or not in PATH."
    log_info "Install from https://python.org/downloads/"
    log_info "Debian/Ubuntu: sudo apt install python3 python3-pip"
    log_info "macOS:         brew install python"
fi

# ---------------------------------------------------------------------------
# 3. Check Apache Bench (non-fatal — only needed for benchmarks)
# ---------------------------------------------------------------------------
echo ""
log_step "Checking Apache Bench (ab) …"
if command -v ab &>/dev/null; then
    AB_VERSION="$(ab -V 2>&1 | head -1)"
    log_ok "ab found: ${AB_VERSION}"
else
    log_warn "ab is not installed — benchmarks will not run."
    log_info "Debian/Ubuntu: sudo apt install apache2-utils"
    log_info "macOS:         brew install httpd   (ab is bundled)"
    log_info "Windows/WSL:   sudo apt install apache2-utils"
fi

# ---------------------------------------------------------------------------
# Abort early if hard requirements are missing
# ---------------------------------------------------------------------------
if [ "$ERRORS" -gt 0 ]; then
    echo ""
    log_err "Hard requirements missing ($ERRORS error(s)). Fix them and re-run."
    exit 1
fi

# ---------------------------------------------------------------------------
# 4. Build Go service
# ---------------------------------------------------------------------------
echo ""
log_step "Building Go service …"
cd "${ROOT}/go-service"
if go build -o server . 2>&1; then
    log_ok "Binary built: go-service/server"
else
    log_err "go build failed — check the output above."
    exit 1
fi
cd "${ROOT}"

# ---------------------------------------------------------------------------
# 5a. Install Python deps — python-service
# ---------------------------------------------------------------------------
echo ""
log_step "Installing Python dependencies: python-service …"
"$PYTHON" -m pip install --quiet --upgrade pip
"$PYTHON" -m pip install --quiet -r "${ROOT}/python-service/requirements.txt"
log_ok "python-service dependencies installed"

# ---------------------------------------------------------------------------
# 5b. Install Python deps — ws_client
# ---------------------------------------------------------------------------
echo ""
log_step "Installing Python dependencies: ws_client …"
"$PYTHON" -m pip install --quiet -r "${ROOT}/ws_client/requirements.txt"
log_ok "ws_client dependencies installed"

# ---------------------------------------------------------------------------
# 5c. Install Python deps — memory-profiling
# ---------------------------------------------------------------------------
echo ""
log_step "Installing Python dependencies: memory-profiling …"
"$PYTHON" -m pip install --quiet -r "${ROOT}/memory-profiling/requirements.txt"
log_ok "memory-profiling dependencies installed"

# ---------------------------------------------------------------------------
# 6. Print manual testing instructions
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}  Setup complete. Follow these steps in separate terminals:${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "${CYAN}  Step 1 — Start the Go service  (terminal 1)${RESET}"
echo -e "           ${BOLD}./go-service/server${RESET}"
echo -e "           Listens on http://localhost:8080"
echo ""
echo -e "${CYAN}  Step 2 — Start FastAPI          (terminal 2)${RESET}"
echo -e "           ${BOLD}uvicorn python-service.main:app --port 8000${RESET}"
echo -e "           Listens on http://localhost:8000"
echo ""
echo -e "${CYAN}  Step 3 — Test connectivity      (terminal 3)${RESET}"
echo -e "           ${BOLD}curl -s localhost:8080/ping | python3 -m json.tool${RESET}"
echo -e "           ${BOLD}curl -s localhost:8000/ping | python3 -m json.tool${RESET}"
echo -e "           ${BOLD}curl -s localhost:8000/health | python3 -m json.tool${RESET}"
echo ""
echo -e "${CYAN}  Step 4 — Run benchmarks         (terminal 3, both services up)${RESET}"
echo -e "           ${BOLD}bash benchmark/run_benchmarks.sh${RESET}"
echo -e "           ${BOLD}python3 benchmark/parse_results.py${RESET}"
echo -e "           Results → benchmark/results/summary.md"
echo ""
echo -e "${CYAN}  Step 5 — WebSocket demo         (terminal 3)${RESET}"
echo -e "           ${BOLD}python3 ws_client/client.py${RESET}        # single client"
echo -e "           ${BOLD}python3 ws_client/multi_client.py${RESET}  # broadcast demo"
echo ""
echo -e "${CYAN}  Step 6 — Memory profiling       (optional, Go pprof setup required)${RESET}"
echo -e "           See: memory-profiling/go_pprof_guide.md"
echo -e "           ${BOLD}python3 memory-profiling/python_memory_profile.py${RESET}"
echo -e "           ${BOLD}python3 memory-profiling/go_memory_profile.py${RESET}"
echo -e "           ${BOLD}python3 memory-profiling/compare_memory.py${RESET}"
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "  Stop services with ${BOLD}Ctrl-C${RESET} in their terminals."
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
