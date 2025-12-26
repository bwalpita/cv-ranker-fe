#!/bin/bash

# ============================================================================
# CV Ranking System - Gradio Frontend Launcher
# ============================================================================
# This script sets up environment variables and launches the Gradio app
# 
# Usage:
#   ./run_gradio.sh                    # Local development (localhost:8000)
#   ./run_gradio.sh production         # Production (Railway backend)
#   ./run_gradio.sh <custom-api-url>   # Custom backend URL
# ============================================================================

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Determine environment
ENVIRONMENT=${1:-local}

# Set API URL based on environment
case $ENVIRONMENT in
  local|development|dev)
    RANKER_API="http://127.0.0.1:8000/rank/enhanced"
    echo -e "${GREEN}✓ Local development mode${NC}"
    echo -e "  Backend: ${YELLOW}$RANKER_API${NC}"
    ;;
  production|prod|railway)
    RANKER_API="https://cv-ranker-be-production.up.railway.app/rank/enhanced"
    echo -e "${GREEN}✓ Production mode (Railway)${NC}"
    echo -e "  Backend: ${YELLOW}$RANKER_API${NC}"
    ;;
  *)
    # Assume it's a custom URL
    RANKER_API=$ENVIRONMENT
    echo -e "${GREEN}✓ Custom backend URL${NC}"
    echo -e "  Backend: ${YELLOW}$RANKER_API${NC}"
    ;;
esac

# Export environment variables
export RANKER_API
export GRADIO_SERVER_NAME="0.0.0.0"
export PORT=7860
export GRADIO_ANALYTICS_ENABLED="False"
export GRADIO_SERVER_API_DOCS="false"

# Display info
echo ""
echo -e "${GREEN}Environment Variables Set:${NC}"
echo "  RANKER_API=$RANKER_API"
echo "  GRADIO_SERVER_NAME=$GRADIO_SERVER_NAME"
echo "  PORT=$PORT"
echo ""

# Install dependencies if needed
if [ ! -d "venv" ] && [ ! -d ".venv" ]; then
  echo -e "${YELLOW}⚠ Virtual environment not found. Installing dependencies...${NC}"
  pip install -r requirements.txt
fi

# Launch Gradio
echo -e "${GREEN}🚀 Starting Gradio Interface...${NC}"
echo ""
python -u gradio_app/app_with_progress.py

# Cleanup on exit
trap 'echo -e "\n${YELLOW}Shutting down...${NC}"' EXIT
