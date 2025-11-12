#!/bin/bash
echo "Starting Backend Server..."

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "Loaded environment variables from .env file"
else
    echo "Warning: .env file not found. Please create one with your OPENAI_API_KEY."
fi
cd backend
python3 main.py
