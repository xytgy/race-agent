#!/bin/bash
cd /Users/xytgy/race-agent
source .venv310/bin/activate

# Load env vars
export $(cat .env | xargs)
export DATA_DIR=/Users/xytgy/race-agent/data
export HF_HUB_OFFLINE=1

# Start backend
cd backend
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/raceagent-backend.log 2>&1 &
echo "Backend PID: $!"

# Wait for backend to start
sleep 3

# Start frontend
cd ../frontend
export API_BASE_URL=http://localhost:8000
nohup streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true > /tmp/raceagent-frontend.log 2>&1 &
echo "Frontend PID: $!"

echo "Services started!"
