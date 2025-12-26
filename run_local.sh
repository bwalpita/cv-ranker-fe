#!/bin/bash

# ============================================================================
# CV Ranking System - Full Local Development Setup
# ============================================================================
# This script starts BOTH the backend API and Gradio frontend
# 
# Usage:
#   ./run_local.sh              # Start both services
#   ./run_local.sh --backend    # Backend only
#   ./run_local.sh --frontend   # Frontend only
# ============================================================================

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

MODE=${1:-both}

# Check if we're in the right directory
if [ ! -f "requirements.txt" ]; then
  echo -e "${RED}❌ Error: requirements.txt not found${NC}"
  echo "Please run this script from the railway_frontend directory"
  exit 1
fi

# Function to start backend
start_backend() {
  echo -e "${BLUE}═════════════════════════════════════════${NC}"
  echo -e "${GREEN}🚀 Starting Backend API (Port 8000)${NC}"
  echo -e "${BLUE}═════════════════════════════════════════${NC}"
  echo ""
  echo "Backend Command:"
  echo "  cd .. && uvicorn api.main:app --reload --host 0.0.0.0 --port 8000"
  echo ""
  echo -e "${YELLOW}⚠️  Run this in a SEPARATE terminal:${NC}"
  echo ""
  cd .. && uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
}

# Function to start frontend
start_frontend() {
  echo -e "${BLUE}═════════════════════════════════════════${NC}"
  echo -e "${GREEN}🚀 Starting Gradio Frontend (Port 7860)${NC}"
  echo -e "${BLUE}═════════════════════════════════════════${NC}"
  echo ""
  
  # Export env variables
  export RANKER_API="http://127.0.0.1:8000/rank/enhanced"
  export GRADIO_SERVER_NAME="0.0.0.0"
  export PORT=7860
  export GRADIO_ANALYTICS_ENABLED="False"
  
  echo "Environment Variables:"
  echo "  RANKER_API=$RANKER_API"
  echo "  PORT=$PORT"
  echo ""
  echo -e "${GREEN}📍 Gradio will be available at: http://localhost:7860${NC}"
  echo ""
  
  python -u gradio_app/app_with_progress.py
}

# Main logic
case $MODE in
  --backend)
    start_backend
    ;;
  --frontend)
    start_frontend
    ;;
  both|*)
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}     ${GREEN}CV Ranking System - Local Development Setup${NC}${BLUE}             ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}📋 Starting both Backend and Frontend services...${NC}"
    echo ""
    echo -e "${YELLOW}⚠️  IMPORTANT: This script will run the FRONTEND${NC}"
    echo -e "${YELLOW}   You MUST start the BACKEND in another terminal:${NC}"
    echo ""
    echo -e "${BLUE}Terminal 1 (Backend):${NC}"
    echo -e "  ${GREEN}cd /path/to/codework2${NC}"
    echo -e "  ${GREEN}uvicorn api.main:app --reload --host 0.0.0.0 --port 8000${NC}"
    echo ""
    echo -e "${BLUE}Terminal 2 (Frontend - this will run):${NC}"
    echo -e "  ${GREEN}cd /path/to/codework2/railway_frontend${NC}"
    echo -e "  ${GREEN}./run_local.sh --frontend${NC}"
    echo ""
    echo -e "${YELLOW}Press ENTER to start the FRONTEND, or Ctrl+C to cancel${NC}"
    read -r
    start_frontend
    ;;
esac
