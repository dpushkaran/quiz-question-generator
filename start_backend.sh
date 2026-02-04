#!/bin/bash
echo "Starting Backend Server..."

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "Loaded environment variables from .env file"
else
    echo "Warning: .env file not found. Please create one with your OPENAI_API_KEY."
fi

# Default port (frontend proxies to 8000)
PORT="${PORT:-8000}"
RESTART="${RESTART:-0}"

# If port is already in use, either exit gracefully or restart
PIDS="$(lsof -tiTCP:${PORT} -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$PIDS" ]; then
    echo "Port ${PORT} is already in use (pid(s): ${PIDS})."
    if [ "$RESTART" = "1" ]; then
        echo "RESTART=1 set, stopping existing process(es)..."
        kill -9 ${PIDS} 2>/dev/null || true
        sleep 1
    else
        echo "Backend may already be running. To force restart: RESTART=1 PORT=${PORT} ./start_backend.sh"
        exit 0
    fi
fi

cd backend
PORT="${PORT}" python3 main.py
