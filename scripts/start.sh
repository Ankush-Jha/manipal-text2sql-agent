#!/usr/bin/env bash
# One command for the demo:  scripts/start.sh            (writer + API, "Always answer" works)
#                            scripts/start.sh --judge    (also the judge, needed for "Careful" mode)
# Opens http://localhost:8000. Stop everything with: scripts/start.sh --stop
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs

find_model() { for d in models "$HOME/Downloads"; do [ -f "$d/$1" ] && { echo "$d/$1"; return; }; done; echo "missing model $1 (put it in models/ or ~/Downloads)" >&2; exit 1; }
up() { curl -s -m 2 "localhost:$1/health" | grep -q ok; }
wait_up() { for _ in $(seq 1 90); do up "$1" && return; sleep 2; done; echo "port $1 did not come up; see logs/" >&2; exit 1; }

if [ "${1:-}" = "--stop" ]; then
  pkill -f "uvicorn api.server" || true; pkill -f "llama-server" || true; echo "stopped"; exit 0
fi

if ! up 8081; then
  nohup llama-server -m "$(find_model Arctic-Text2SQL-R1-7B.Q4_K_M.gguf)" --port 8081 -c 16384 -np 2 --alias writer > logs/writer.log 2>&1 &
  echo "starting writer…"; wait_up 8081
fi
if [ "${1:-}" = "--judge" ] && ! up 8082; then
  # small context and one slot: the judge only reads short prompts and answers with one token
  nohup llama-server -m "$(find_model Qwen3-8B-Q4_K_M.gguf)" --port 8082 -c 4096 -np 1 --alias judge > logs/judge.log 2>&1 &
  echo "starting judge…"; wait_up 8082
fi
if ! curl -s -m 2 localhost:8000/api/health > /dev/null; then
  nohup .venv/bin/uvicorn api.server:app --port 8000 > logs/api.log 2>&1 &
  for _ in $(seq 1 30); do curl -s -m 2 localhost:8000/api/health > /dev/null && break; sleep 1; done
fi
echo "ready: http://localhost:8000"; memory_pressure | tail -1
open http://localhost:8000 2>/dev/null || true
