#!/usr/bin/env bash
# Convenience launcher for local dev. Starts the FastAPI backend and the
# React dev server together, and shuts both down on Ctrl-C.
#
# Prereqs: backend/.env created from .env.example with an API key,
# backend deps installed (pip install -r backend/requirements.txt),
# and frontend deps installed (cd frontend && npm install).
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "▶ starting backend on :8000"
( cd "$ROOT/backend" && uvicorn app.main:app --reload --port 8000 ) &
BACKEND_PID=$!

echo "▶ starting frontend on :3000"
( cd "$ROOT/frontend" && npm start ) &
FRONTEND_PID=$!

trap "echo; echo '■ stopping'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" INT TERM
wait
