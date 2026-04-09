#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
echo "Starting Notifli on http://localhost:8000"
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
