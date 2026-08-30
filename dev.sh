#!/usr/bin/env bash
# Start the backend and the frontend together. One Ctrl-C stops both.
# No Docker, no Procfile, no process manager.
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x backend/.venv/bin/uvicorn ]]; then
  echo "No backend venv. Run ./setup.sh first." >&2
  exit 1
fi

if [[ ! -f backend/.env ]]; then
  echo "No backend/.env. Run ./setup.sh first." >&2
  exit 1
fi

pids=()

cleanup() {
  trap - INT TERM EXIT
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

(cd backend && exec .venv/bin/uvicorn app.main:app --reload --port 8000) &
pids+=($!)

if [[ -d frontend/node_modules ]]; then
  (cd frontend && exec npm run dev) &
  pids+=($!)
  echo "backend :8000   frontend :5173"
else
  echo "backend :8000   (frontend not installed yet)"
fi

# Plain `wait`, not `wait -n`: macOS ships bash 3.2, where -n is a syntax error
# and the script exits immediately having started nothing you can reach.
# Ctrl-C still stops both, via the trap above.
wait
