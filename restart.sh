#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/logs/restart.pid"
LOG_FILE="$ROOT_DIR/logs/restart.log"

load_env_file() {
    if [[ -f "$ROOT_DIR/.env" ]]; then
        set -a
        # shellcheck disable=SC1091
        source "$ROOT_DIR/.env"
        set +a
    fi
}

is_windows_shell() {
    [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* || "${OSTYPE:-}" == win32* ]]
}

kill_process_tree() {
    local pid="${1:-}"
    if [[ -z "$pid" ]]; then
        return 0
    fi

    if is_windows_shell; then
        taskkill /PID "$pid" /T /F >/dev/null 2>&1 || true
    else
        kill -TERM "$pid" >/dev/null 2>&1 || true
        sleep 1
        kill -KILL "$pid" >/dev/null 2>&1 || true
    fi
}

ensure_python() {
    if command -v python.exe >/dev/null 2>&1; then
        PYTHON_BIN="${PYTHON_BIN:-python.exe}"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="${PYTHON_BIN:-python3}"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN="${PYTHON_BIN:-python}"
    else
        echo "Python was not found. Install Python 3 first." >&2
        exit 1
    fi

    if ! "$PYTHON_BIN" -m pip show Flask >/dev/null 2>&1 || ! "$PYTHON_BIN" -m pip show redis >/dev/null 2>&1; then
        echo "Installing Python dependencies from requirements.txt..."
        "$PYTHON_BIN" -m pip install -r "$ROOT_DIR/requirements.txt"
    fi

    if ! "$PYTHON_BIN" -c "import flask, redis" >/dev/null 2>&1; then
        echo "Python dependencies are still unavailable after install." >&2
        exit 1
    fi
}

stop_old_listener() {
    local port="${APP_PORT:-9213}"
    local pids=()

    if command -v lsof >/dev/null 2>&1; then
        mapfile -t pids < <(lsof -ti tcp:"$port" 2>/dev/null || true)
    elif command -v ss >/dev/null 2>&1; then
        mapfile -t pids < <(ss -ltnp 2>/dev/null | grep ":${port} " | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' || true)
    elif command -v netstat >/dev/null 2>&1; then
        mapfile -t pids < <(netstat -ano 2>/dev/null | awk -v target=":${port}" '
            $0 ~ target && ($0 ~ /LISTENING/ || $0 ~ /LISTEN/) {
                print $NF
            }
        ' || true)
    fi

    if [[ ${#pids[@]} -gt 0 ]]; then
        local unique_pids=()
        local pid
        for pid in "${pids[@]}"; do
            if [[ -n "$pid" ]] && [[ "$pid" != "0" ]] && [[ ! " ${unique_pids[*]} " =~ " ${pid} " ]]; then
                unique_pids+=("$pid")
            fi
        done

        if [[ ${#unique_pids[@]} -gt 0 ]]; then
            echo "Stopping existing process(es) on port ${port}: ${unique_pids[*]}"
            for pid in "${unique_pids[@]}"; do
                kill_process_tree "$pid"
            done
        fi
    fi
}

start_daemon() {
    local cleanup_listener="${1:-1}"
    mkdir -p "$ROOT_DIR/logs"
    if [[ "$cleanup_listener" == "1" ]]; then
        stop_old_listener
    fi

    if [[ -f "$PID_FILE" ]]; then
        old_pid="$(tr -d '\r\n' < "$PID_FILE" || true)"
        if [[ -n "$old_pid" ]]; then
            kill_process_tree "$old_pid"
        fi
    fi

    cd "$ROOT_DIR"
    export APP_HOST="${APP_HOST:-0.0.0.0}"
    export APP_PORT="${APP_PORT:-9213}"

    "$PYTHON_BIN" -u app.py >>"$LOG_FILE" 2>&1 </dev/null &
    app_pid=$!
    echo "$app_pid" >"$PID_FILE"
    sleep 2
}

stop_daemon() {
    if [[ -f "$PID_FILE" ]]; then
        pid="$(tr -d '\r\n' < "$PID_FILE" || true)"
        if [[ -n "$pid" ]]; then
            kill_process_tree "$pid"
        fi
        rm -f "$PID_FILE"
    fi
    stop_old_listener
}

status_daemon() {
    if [[ -f "$PID_FILE" ]]; then
        pid="$(tr -d '\r\n' < "$PID_FILE" || true)"
        if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
            echo "running pid=$pid port=${APP_PORT:-9213}"
            return 0
        fi
    fi
    echo "stopped"
    return 1
}

main() {
    load_env_file
    ensure_python

    case "${1:-start}" in
        start)
            start_daemon 1
            echo "Started. Open http://127.0.0.1:${APP_PORT:-9213}"
            ;;
        stop)
            stop_daemon
            echo "Stopped."
            ;;
        restart)
            stop_daemon
            start_daemon 0
            echo "Restarted. Open http://127.0.0.1:${APP_PORT:-9213}"
            ;;
        status)
            status_daemon
            ;;
        *)
            echo "Usage: $0 {start|stop|restart|status}" >&2
            exit 1
            ;;
    esac
}

cd "$ROOT_DIR"
main "$@"
