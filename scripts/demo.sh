#!/usr/bin/env bash
# One command to reset and stage the live demo.
#
#   scripts/demo.sh            reset, seed, run l2_002 to the review pause, open the review page
#   scripts/demo.sh reset      reset and seed only
#   scripts/demo.sh run <id>   run one fixture ticket to the review pause, e.g. abs_001
#   scripts/demo.sh ui         open the review page only
#
set -euo pipefail
cd "$(dirname "$0")/.."

postgres() {
  if nc -z localhost 5433 2>/dev/null; then
    echo "== postgres up"
    return
  fi
  echo "== starting postgres"
  if ! docker info >/dev/null 2>&1; then
    open -a Docker
    for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done
    docker info >/dev/null 2>&1 || { echo "docker daemon did not start"; exit 1; }
  fi
  docker compose up -d
  for _ in $(seq 1 30); do nc -z localhost 5433 2>/dev/null && break; sleep 1; done
  nc -z localhost 5433 2>/dev/null || { echo "postgres did not open port 5433"; exit 1; }
  sleep 2
}

reset() {
  echo "== reset + seed"
  uv run python scripts/reset_demo.py
  uv run python scripts/seed_servicenow.py
}

run_ticket() {
  echo "== run $1"
  uv run python -m app.demo run --ticket "fixtures/tickets/$1.json"
}

ui() {
  echo "== review page"
  uv run streamlit run app/ui/review_app.py
}

postgres
case "${1:-all}" in
  reset) reset ;;
  run)   run_ticket "${2:?ticket id, e.g. l2_002}" ;;
  ui)    ui ;;
  all)   reset; run_ticket l2_002; ui ;;
  *)     echo "usage: scripts/demo.sh [all|reset|run <id>|ui]"; exit 1 ;;
esac
